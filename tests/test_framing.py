from __future__ import annotations

import pytest

from asterix import FramingError, Limits, MessageFramer, TruncatedDataError, split_messages

ONE = bytes.fromhex("30000400")
TWO = bytes.fromhex("15000400")


def test_split_concatenated_messages() -> None:
    assert split_messages(ONE + TWO) == (ONE, TWO)


@pytest.mark.parametrize("split", range(len(ONE) + 1))
def test_incremental_framer_accepts_every_split(split: int) -> None:
    framer = MessageFramer()
    assert framer.feed(ONE[:split]) + framer.feed(ONE[split:]) == (ONE,)
    framer.finish()


def test_framer_rejects_invalid_length() -> None:
    with pytest.raises(FramingError):
        MessageFramer().feed(b"\x30\x00\x02")


def test_finish_rejects_truncated_message() -> None:
    framer = MessageFramer()
    framer.feed(ONE[:-1])
    with pytest.raises(TruncatedDataError):
        framer.finish()


def test_large_chunk_of_complete_messages_does_not_count_as_buffered_data() -> None:
    framer = MessageFramer(Limits(max_buffer_bytes=3))
    assert framer.feed(ONE + TWO) == (ONE, TWO)
    assert framer.buffered_bytes == 0
