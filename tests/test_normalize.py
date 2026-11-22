from datetime import UTC, datetime

from asterix import DecodeContext, SchemaRegistry, decode_message, encode_record
from asterix.normalize import NormalisationContext, TrackUpdate, normalise


def test_cat062_normalises_to_track_update() -> None:
    registry = SchemaRegistry.builtin()
    wire = encode_record(
        category=62,
        edition="1.21",
        items={
            "I062/010": {"SAC": 1, "SIC": 2},
            "I062/040": 1234,
            "I062/070": 3600,
            "I062/105": {"LAT": 45, "LON": -45},
        },
        registry=registry,
    )
    message = decode_message(
        wire,
        registry=registry,
        context=DecodeContext(editions={62: "1.21"}),
    )
    received = datetime(2026, 1, 2, 1, 2, tzinfo=UTC)

    events = list(normalise(message, NormalisationContext(received_at=received)))

    assert len(events) == 1
    update = events[0]
    assert isinstance(update, TrackUpdate)
    assert update.track_id == "062:track:4D2"
    assert update.latitude_degrees == 45
    assert update.longitude_degrees == -45
    assert update.observed_at == datetime(2026, 1, 2, 1, 0, tzinfo=UTC)
    assert (update.provenance.sac, update.provenance.sic) == (1, 2)


def test_non_surveillance_category_produces_no_events() -> None:
    registry = SchemaRegistry.builtin()
    wire = encode_record(
        category=34,
        edition="1.29",
        items={"I034/010": {"SAC": 1, "SIC": 2}},
        registry=registry,
    )
    message = decode_message(
        wire,
        registry=registry,
        context=DecodeContext(editions={34: "1.29"}),
    )

    assert list(normalise(message)) == []
