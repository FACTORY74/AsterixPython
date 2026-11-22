"""Bounds-checked byte and bit cursors."""

from __future__ import annotations

from dataclasses import dataclass

from .errors import TruncatedDataError


@dataclass(slots=True)
class ByteCursor:
    data: memoryview
    pos: int = 0

    @classmethod
    def from_bytes(cls, data: bytes | bytearray | memoryview) -> ByteCursor:
        return cls(memoryview(data).cast("B"))

    @property
    def remaining(self) -> int:
        return len(self.data) - self.pos

    def take(self, size: int) -> bytes:
        if size < 0 or size > self.remaining:
            raise TruncatedDataError(
                f"need {size} bytes at offset {self.pos}, only {self.remaining} remain"
            )
        start = self.pos
        self.pos += size
        return bytes(self.data[start : self.pos])

    def take_cursor(self, size: int) -> ByteCursor:
        return ByteCursor.from_bytes(self.take(size))

    def u8(self) -> int:
        return self.take(1)[0]

    def uint(self, size: int) -> int:
        return int.from_bytes(self.take(size), "big")


@dataclass(slots=True)
class BitCursor:
    data: bytes
    bit_pos: int = 0

    @property
    def remaining(self) -> int:
        return len(self.data) * 8 - self.bit_pos

    def read(self, size: int) -> int:
        if size < 0 or size > self.remaining:
            raise TruncatedDataError(
                f"need {size} bits at bit {self.bit_pos}, only {self.remaining} remain"
            )
        value = 0
        for _ in range(size):
            byte = self.data[self.bit_pos // 8]
            shift = 7 - (self.bit_pos % 8)
            value = (value << 1) | ((byte >> shift) & 1)
            self.bit_pos += 1
        return value


class BitWriter:
    def __init__(self) -> None:
        self._bits: list[int] = []

    @property
    def size(self) -> int:
        return len(self._bits)

    def write(self, value: int, size: int) -> None:
        if value < 0 or value >= 1 << size:
            raise ValueError(f"{value} does not fit in {size} bits")
        self._bits.extend((value >> shift) & 1 for shift in range(size - 1, -1, -1))

    def bytes(self) -> bytes:
        if len(self._bits) % 8:
            raise ValueError("bit writer is not octet aligned")
        output = bytearray(len(self._bits) // 8)
        for index, bit in enumerate(self._bits):
            output[index // 8] |= bit << (7 - index % 8)
        return bytes(output)
