from __future__ import annotations

from fractions import Fraction

import pytest

from asterix import (
    DecodeContext,
    EncodeContext,
    Limits,
    SchemaRegistry,
    TruncatedDataError,
    decode_message,
)
from asterix.codec import _RecordState, _VariationDecoder, _VariationEncoder
from asterix.cursor import ByteCursor
from asterix.errors import DecodeError
from asterix.json import to_jsonable
from asterix.model import ElementValue

REGISTRY = SchemaRegistry.builtin()


def _element(bits: int, rule: dict[str, object]) -> dict[str, object]:
    return {"tag": "Element", "contents": {"bitSize": bits, "rule": rule}}


def _item(name: str, rule: dict[str, object]) -> dict[str, object]:
    return {"tag": "Item", "contents": {"name": name, "rule": rule}}


def _encode(node: dict[str, object], value: object) -> bytes:
    encoder = _VariationEncoder(EncodeContext(), REGISTRY, 48, "1.32")
    return encoder.encode(node, value, ("test",))


def _decode(
    node: dict[str, object], wire: bytes, *, limits: Limits | None = None
) -> tuple[object, tuple[str, ...]]:
    context = DecodeContext(validation="inspect", limits=limits or Limits())
    state = _RecordState({}, [], 48, "1.32")
    decoder = _VariationDecoder(context, REGISTRY, 48, "1.32")
    value = decoder.decode(node, ByteCursor.from_bytes(wire), state, ("test",))
    return value, tuple(diagnostic.code for diagnostic in state.diagnostics)


@pytest.mark.parametrize(
    ("value", "wire"),
    [(-128, b"\x80"), (-1, b"\xff"), (0, b"\x00"), (127, b"\x7f")],
)
def test_signed_integer_boundary_vectors(value: int, wire: bytes) -> None:
    node = _element(
        8,
        {"tag": "ContentInteger", "contents": {"signedness": {"tag": "Signed"}}},
    )
    assert _encode(node, value) == wire
    decoded, _ = _decode(node, wire)
    assert decoded.value == value


@pytest.mark.parametrize(
    ("rule", "value", "wire", "decoded_value"),
    [
        (
            {"tag": "ContentTable", "contents": [[0, "zero"], [5, "five"]]},
            "five",
            b"\x05",
            5,
        ),
        (
            {"tag": "ContentString", "contents": {"tag": "StringAscii"}},
            "AB",
            b"AB",
            "AB",
        ),
        (
            {"tag": "ContentString", "contents": {"tag": "StringICAO"}},
            "AB  ",
            bytes.fromhex("042820"),
            "AB",
        ),
        (
            {"tag": "ContentString", "contents": {"tag": "StringOctal"}},
            "12345670",
            bytes.fromhex("29cbb8"),
            "12345670",
        ),
    ],
)
def test_table_and_text_vectors(
    rule: dict[str, object], value: object, wire: bytes, decoded_value: object
) -> None:
    node = _element(len(wire) * 8, rule)
    assert _encode(node, value) == wire
    decoded, diagnostics = _decode(node, wire)
    assert decoded.value == decoded_value
    assert diagnostics == ()


def test_exact_quantity_vector() -> None:
    rule = {
        "tag": "ContentQuantity",
        "contents": {
            "signedness": {"tag": "Unsigned"},
            "lsb": {
                "tag": "NumDiv",
                "contents": {
                    "numerator": {"tag": "NumInt", "contents": 1},
                    "denominator": {"tag": "NumInt", "contents": 128},
                },
            },
            "unit": "s",
        },
    }
    node = _element(16, rule)
    assert _encode(node, Fraction(257, 128)) == bytes.fromhex("0101")
    decoded, _ = _decode(node, bytes.fromhex("0101"))
    assert decoded.value == Fraction(257, 128)


def test_extended_item_vector() -> None:
    entry = _item("V", _element(7, {"tag": "ContentRaw"}))
    node = {"tag": "Extended", "contents": [entry, None, entry, None]}
    value = [{"V": 0x12}, {"V": 0x34}]
    assert _encode(node, value) == bytes.fromhex("2568")
    decoded, _ = _decode(node, bytes.fromhex("2568"))
    assert [extent["V"].raw for extent in decoded] == [0x12, 0x34]


def test_explicit_item_vector() -> None:
    node = {"tag": "Explicit", "contents": {"tag": "SpecialPurpose"}}
    assert _encode(node, bytes.fromhex("aabb")) == bytes.fromhex("03aabb")
    decoded, _ = _decode(node, bytes.fromhex("03aabb"))
    assert decoded == {"length": 3, "data": bytes.fromhex("aabb")}


def test_regular_repetition_vector() -> None:
    node = {
        "tag": "Repetitive",
        "contents": {
            "type": {"tag": "RepetitiveRegular", "contents": {"byteSize": 1}},
            "variation": _element(8, {"tag": "ContentRaw"}),
        },
    }
    assert _encode(node, [1, 2]) == bytes.fromhex("020102")
    decoded, _ = _decode(node, bytes.fromhex("020102"))
    assert [value.raw for value in decoded] == [1, 2]


def test_compound_item_vector() -> None:
    children = [
        _item("A", _element(8, {"tag": "ContentRaw"})),
        _item("B", _element(8, {"tag": "ContentRaw"})),
    ]
    node = {"tag": "Compound", "contents": children}
    assert _encode(node, {"B": 0x7F}) == bytes.fromhex("407f")
    decoded, _ = _decode(node, bytes.fromhex("407f"))
    assert decoded["_fspec"] == b"\x40"
    assert decoded["B"].raw == 0x7F


def test_dependent_rule_vector() -> None:
    raw = {"tag": "ContentRaw"}
    dependent = {
        "tag": "Dependent",
        "contents": {
            "path": [["SEL"]],
            "cases": [[[1], raw]],
            "default": {
                "tag": "ContentInteger",
                "contents": {"signedness": {"tag": "Signed"}},
            },
        },
    }
    node = {
        "tag": "Group",
        "contents": [
            _item("SEL", _element(8, raw)),
            _item("VALUE", _element(8, dependent)),
        ],
    }
    assert _encode(node, {"SEL": 1, "VALUE": 255}) == bytes.fromhex("01ff")
    decoded, _ = _decode(node, bytes.fromhex("01ff"))
    assert decoded["VALUE"].value == 255


def test_reserved_expansion_and_multi_octet_fspec_vector() -> None:
    # FRN 28 is CAT048 RE. The explicit body contains an empty one-byte REF FSPEC.
    wire = bytes.fromhex("300009010101020200")
    message = decode_message(
        wire,
        context=DecodeContext(editions={48: "1.32"}, ref_editions={48: "1.13"}),
    )
    item = message.records[0].by_id("I048/RE")
    assert item is not None
    assert item.value == {"edition": "1.13", "fspec": b"\x00", "items": {}}


def test_malformed_nested_structures_are_bounded() -> None:
    explicit = {"tag": "Explicit", "contents": {"tag": "SpecialPurpose"}}
    with pytest.raises(TruncatedDataError):
        _decode(explicit, bytes.fromhex("03aa"))

    repetitive = {
        "tag": "Repetitive",
        "contents": {
            "type": {"tag": "RepetitiveRegular", "contents": {"byteSize": 1}},
            "variation": _element(8, {"tag": "ContentRaw"}),
        },
    }
    with pytest.raises(DecodeError, match="repetition count"):
        _decode(repetitive, b"\x02", limits=Limits(max_repetitions=1))


def test_to_jsonable_preserves_exact_values() -> None:
    assert to_jsonable(
        {"scaled": Fraction(1, 128), "raw": b"\xaa", "element": ElementValue(1, 1)}
    ) == {
        "scaled": {"numerator": 1, "denominator": 128},
        "raw": "aa",
        "element": {"raw": 1, "value": 1, "label": None, "unit": None},
    }
