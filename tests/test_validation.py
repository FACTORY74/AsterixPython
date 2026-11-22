from __future__ import annotations

import pytest

from asterix import (
    DecodeContext,
    EncodeContext,
    EncodeError,
    SchemaRegistry,
    ValidationError,
    decode_message,
    encode_record,
)
from asterix.codec import _RecordState, _VariationDecoder
from asterix.cursor import ByteCursor


def _cat048_with_nonzero_spare() -> bytes:
    wire = bytearray(
        encode_record(
            category=48,
            edition="1.32",
            items={"I048/070": {"V": 0, "G": 0, "L": 0, "MODE3A": "0000"}},
        )
    )
    # I048/070 has V/G/L, one spare bit, then its 12-bit Mode-3/A value.
    wire[-2] |= 0x10
    return bytes(wire)


def test_strict_decode_rejects_nonzero_spare() -> None:
    with pytest.raises(ValidationError, match="spare bits"):
        decode_message(
            _cat048_with_nonzero_spare(),
            context=DecodeContext(editions={48: "1.32"}, validation="strict"),
        )


@pytest.mark.parametrize("mode", ["compatible", "inspect"])
def test_tolerant_decode_reports_nonzero_spare(mode: str) -> None:
    message = decode_message(
        _cat048_with_nonzero_spare(),
        context=DecodeContext(editions={48: "1.32"}, validation=mode),
    )
    assert [diagnostic.code for diagnostic in message.diagnostics] == ["nonzero-spare"]


def test_strict_decode_rejects_unknown_frn() -> None:
    # CAT048 edition 1.32 has 28 UAP entries; this sets FRN 29.
    wire = bytes.fromhex("3000080101010180")
    with pytest.raises(ValidationError, match="FRN 29"):
        decode_message(wire, context=DecodeContext(editions={48: "1.32"}))


@pytest.mark.parametrize("mode", ["compatible", "inspect"])
def test_tolerant_decode_preserves_unknown_frn_tail(mode: str) -> None:
    wire = bytes.fromhex("30000a0101010180aabb")
    message = decode_message(
        wire,
        context=DecodeContext(editions={48: "1.32"}, validation=mode),
    )
    assert message.records[0].unknown_tail is not None
    assert message.records[0].unknown_tail.raw == bytes.fromhex("aabb")
    assert [diagnostic.code for diagnostic in message.diagnostics] == ["unknown-frn"]


def test_strict_encode_rejects_undefined_table_value() -> None:
    with pytest.raises(EncodeError, match="table value 127 is not defined"):
        encode_record(category=48, edition="1.32", items={"I048/030": [127]})


@pytest.mark.parametrize("mode", ["compatible", "inspect"])
def test_tolerant_encode_allows_undefined_table_value(mode: str) -> None:
    wire = encode_record(
        category=48,
        edition="1.32",
        items={"I048/030": [127]},
        context=EncodeContext(validation=mode),
    )
    assert wire.endswith(bytes.fromhex("fe"))


def test_strict_decode_rejects_undefined_table_value() -> None:
    wire = encode_record(
        category=48,
        edition="1.32",
        items={"I048/030": [127]},
        context=EncodeContext(validation="compatible"),
    )
    with pytest.raises(ValidationError, match="not defined by its table"):
        decode_message(wire, context=DecodeContext(editions={48: "1.32"}))


@pytest.mark.parametrize("mode", ["compatible", "inspect"])
def test_tolerant_decode_preserves_undefined_table_value(mode: str) -> None:
    wire = encode_record(
        category=48,
        edition="1.32",
        items={"I048/030": [127]},
        context=EncodeContext(validation="compatible"),
    )
    message = decode_message(
        wire,
        context=DecodeContext(editions={48: "1.32"}, validation=mode),
    )
    assert message.records[0].by_id("I048/030").value[0].raw == 127
    assert [diagnostic.code for diagnostic in message.diagnostics] == ["unknown-table-value"]


def test_uap_spare_follows_validation_policy() -> None:
    # CAT001 1.2 plot UAP maps FRN 16 to UapItemSpare.
    wire = bytes.fromhex("010006010140")
    strict = DecodeContext(editions={1: "1.2"}, uaps={1: "plot"})
    with pytest.raises(ValidationError, match="UapItemSpare"):
        decode_message(wire, context=strict)

    compatible = DecodeContext(
        editions={1: "1.2"}, uaps={1: "plot"}, validation="compatible"
    )
    message = decode_message(wire, context=compatible)
    assert [diagnostic.code for diagnostic in message.diagnostics] == ["uap-spare"]


def _synthetic_decoder(mode: str) -> tuple[_VariationDecoder, _RecordState]:
    context = DecodeContext(validation=mode)
    registry = SchemaRegistry.builtin()
    return _VariationDecoder(context, registry, 48, "1.32"), _RecordState({}, [], 48, "1.32")


@pytest.mark.parametrize(
    ("node", "wire", "code"),
    [
        (
            {
                "tag": "Extended",
                "contents": [
                    {
                        "tag": "Element",
                        "contents": {"bitSize": 7, "rule": {"tag": "ContentRaw"}},
                    },
                    None,
                ],
            },
            b"\x01\x00",
            "unknown-extension",
        ),
        ({"tag": "Compound", "contents": [None]}, b"\x80", "compound-spare"),
    ],
)
def test_nested_validation_conditions_follow_policy(
    node: dict[str, object], wire: bytes, code: str
) -> None:
    decoder, state = _synthetic_decoder("strict")
    with pytest.raises(ValidationError):
        decoder.decode(node, ByteCursor.from_bytes(wire), state, ("test",))

    decoder, state = _synthetic_decoder("compatible")
    decoder.decode(node, ByteCursor.from_bytes(wire), state, ("test",))
    assert [diagnostic.code for diagnostic in state.diagnostics] == [code]

