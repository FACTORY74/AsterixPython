"""Incremental ASTERIX CAT/LEN message framing."""

from __future__ import annotations

from .context import Limits
from .errors import FramingError, TruncatedDataError


def split_messages(
    data: bytes | bytearray | memoryview, limits: Limits | None = None
) -> tuple[bytes, ...]:
    limits = limits or Limits()
    view = memoryview(data).cast("B")
    offset = 0
    messages: list[bytes] = []
    while offset < len(view):
        if len(view) - offset < 3:
            raise TruncatedDataError(f"truncated ASTERIX header at offset {offset}")
        length = int.from_bytes(view[offset + 1 : offset + 3], "big")
        if length < 3:
            raise FramingError(f"invalid ASTERIX LEN {length} at offset {offset}")
        if length > limits.max_message_bytes:
            raise FramingError(f"ASTERIX LEN {length} exceeds limit {limits.max_message_bytes}")
        if offset + length > len(view):
            raise TruncatedDataError(
                f"message at offset {offset} declares {length} bytes, "
                f"only {len(view) - offset} remain"
            )
        messages.append(bytes(view[offset : offset + length]))
        offset += length
    return tuple(messages)


class MessageFramer:
    def __init__(self, limits: Limits | None = None) -> None:
        self.limits = limits or Limits()
        self._buffer = bytearray()

    @property
    def buffered_bytes(self) -> int:
        return len(self._buffer)

    def feed(self, chunk: bytes | bytearray | memoryview) -> tuple[bytes, ...]:
        self._buffer.extend(chunk)
        messages: list[bytes] = []
        while len(self._buffer) >= 3:
            length = int.from_bytes(self._buffer[1:3], "big")
            if length < 3:
                raise FramingError(f"invalid ASTERIX LEN {length}")
            if length > self.limits.max_message_bytes:
                raise FramingError(
                    f"ASTERIX LEN {length} exceeds limit {self.limits.max_message_bytes}"
                )
            if len(self._buffer) < length:
                break
            messages.append(bytes(self._buffer[:length]))
            del self._buffer[:length]
        if len(self._buffer) > self.limits.max_buffer_bytes:
            raise FramingError(f"framing buffer exceeds limit {self.limits.max_buffer_bytes} bytes")
        return tuple(messages)

    def finish(self) -> None:
        if self._buffer:
            raise TruncatedDataError(f"stream ended with {len(self._buffer)} buffered bytes")
