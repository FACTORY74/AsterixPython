from __future__ import annotations

from fractions import Fraction

from asterix import DecodeContext, SchemaRegistry, decode_message, encode_record


def test_cat048_data_source_identifier_known_wire() -> None:
    wire = bytes.fromhex("300006800102")
    message = decode_message(wire, context=DecodeContext(editions={48: "1.32"}))
    item = message.records[0].by_id("I048/010")
    assert item is not None
    assert item.value["SAC"].value == 1
    assert item.value["SIC"].value == 2


def test_cat048_data_source_identifier_round_trip() -> None:
    wire = encode_record(
        category=48,
        edition="1.32",
        items={"I048/010": {"SAC": 1, "SIC": 2}},
    )
    assert wire == bytes.fromhex("300006800102")


def test_quantity_is_exact_fraction() -> None:
    registry = SchemaRegistry.builtin()
    # CAT048 I140 is time of day, 24 unsigned bits with LSB 1/128 second.
    wire = encode_record(
        category=48,
        edition="1.32",
        items={"I048/140": {"ToD": Fraction(1, 128)}},
        registry=registry,
    )
    message = decode_message(
        wire,
        context=DecodeContext(editions={48: "1.32"}),
        registry=registry,
    )
    item = message.records[0].by_id("I048/140")
    assert item is not None
    assert item.value.value == Fraction(1, 128)
