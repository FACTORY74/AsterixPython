"""Optional projection of decoded surveillance records into track events.

Normalisation is deliberately separate from the wire codec.  It covers common
CAT021 and CAT062 fields and only emits an update when a geographical position
is available.  CAT048 Cartesian positions require a site-specific projector.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from fractions import Fraction
from typing import Any

from .model import AsterixMessage, DataItem, DataRecord, ElementValue


@dataclass(frozen=True, slots=True)
class Provenance:
    category: int
    edition: str
    record_index: int
    sac: int | None = None
    sic: int | None = None


@dataclass(frozen=True, slots=True)
class TrackUpdate:
    track_id: str
    latitude_degrees: float
    longitude_degrees: float
    observed_at: datetime
    provenance: Provenance
    callsign: str | None = None
    altitude_feet: float | None = None
    ground_speed_knots: float | None = None
    heading_degrees: float | None = None


@dataclass(frozen=True, slots=True)
class TrackTermination:
    track_id: str
    observed_at: datetime
    provenance: Provenance


CartesianProjector = Callable[[float, float, Provenance], tuple[float, float]]


@dataclass(frozen=True, slots=True)
class NormalisationContext:
    """Deployment-specific choices that do not belong in ASTERIX schemas."""

    received_at: datetime | None = None
    cartesian_projector: CartesianProjector | None = None


def _plain(value: Any) -> Any:
    return value.value if isinstance(value, ElementValue) else value


def _leaf(value: Any, name: str) -> Any | None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if str(key).casefold() == name.casefold():
                return _plain(child)
        for child in value.values():
            found = _leaf(child, name)
            if found is not None:
                return found
    elif isinstance(value, (list, tuple)):
        for child in value:
            found = _leaf(child, name)
            if found is not None:
                return found
    return None


def _item(record: DataRecord, number: str) -> DataItem | None:
    suffix = f"/{number}"
    return next((item for item in record.fields if item.item_id.endswith(suffix)), None)


def _item_value(record: DataRecord, number: str, leaf: str | None = None) -> Any | None:
    item = _item(record, number)
    if item is None:
        return None
    return _plain(item.value) if leaf is None else _leaf(item.value, leaf)


def _number(value: Any | None) -> float | None:
    return float(value) if isinstance(value, (int, float, Fraction)) else None


def _observed_at(seconds: Any | None, received_at: datetime) -> datetime:
    numeric = _number(seconds)
    if numeric is None:
        return received_at
    midnight = received_at.replace(hour=0, minute=0, second=0, microsecond=0)
    candidate = midnight + timedelta(seconds=numeric)
    if candidate - received_at > timedelta(hours=12):
        candidate -= timedelta(days=1)
    elif received_at - candidate > timedelta(hours=12):
        candidate += timedelta(days=1)
    return candidate


def _source(record: DataRecord) -> tuple[int | None, int | None]:
    for number in ("010", "015"):
        item = _item(record, number)
        if item is not None:
            return _int_or_none(_leaf(item.value, "SAC")), _int_or_none(_leaf(item.value, "SIC"))
    return None, None


def _int_or_none(value: Any | None) -> int | None:
    return int(value) if isinstance(value, (int, Fraction)) else None


def _identity(message: AsterixMessage, record: DataRecord) -> str | None:
    candidates = {
        21: (("080", None, "addr"), ("161", "TRN", "track")),
        48: (("220", None, "addr"), ("161", "TRN", "track")),
        62: (("040", None, "track"), ("380", "ADR", "addr")),
    }.get(message.category, ())
    for number, leaf, label in candidates:
        value = _item_value(record, number, leaf)
        if isinstance(value, (int, Fraction)):
            width = 6 if label == "addr" else 1
            return f"{message.category:03d}:{label}:{int(value):0{width}X}"
    return None


def _position(
    message: AsterixMessage,
    record: DataRecord,
    provenance: Provenance,
    projector: CartesianProjector | None,
) -> tuple[float, float] | None:
    wgs_item = {21: "130", 62: "105"}.get(message.category)
    if wgs_item:
        lat = _number(_item_value(record, wgs_item, "LAT"))
        lon = _number(_item_value(record, wgs_item, "LON"))
        if lat is not None and lon is not None:
            return lat, lon
    if message.category == 48 and projector is not None:
        x = _number(_item_value(record, "042", "X"))
        y = _number(_item_value(record, "042", "Y"))
        if x is not None and y is not None:
            return projector(x, y, provenance)
    return None


def _velocity(message: AsterixMessage, record: DataRecord) -> tuple[float | None, float | None]:
    if message.category == 21:
        speed = _number(_item_value(record, "160", "GS"))
        heading = _number(_item_value(record, "160", "TA"))
        return (speed * 3600 if speed is not None else None), heading
    if message.category == 48:
        speed = _number(_item_value(record, "200", "GSP"))
        heading = _number(_item_value(record, "200", "HDG"))
        return (speed * 3600 if speed is not None else None), heading
    if message.category == 62:
        vx = _number(_item_value(record, "185", "VX"))
        vy = _number(_item_value(record, "185", "VY"))
        if vx is not None and vy is not None:
            return math.hypot(vx, vy) * 1.9438444924406, math.degrees(math.atan2(vx, vy)) % 360
    return None, None


def _altitude(message: AsterixMessage, record: DataRecord) -> float | None:
    if message.category == 62:
        geometric = _number(_item_value(record, "130"))
        if geometric is not None:
            return geometric
        flight_level = _number(_item_value(record, "136"))
        return flight_level * 100 if flight_level is not None else None
    if message.category == 48:
        value = _number(_item_value(record, "090", "FL"))
        return value * 100 if value is not None else None
    if message.category == 21:
        value = _number(_item_value(record, "145"))
        return value * 100 if value is not None else None
    return None


def normalise(
    message: AsterixMessage, context: NormalisationContext | None = None
) -> Iterator[TrackUpdate | TrackTermination]:
    """Yield conservative track events from supported surveillance categories."""

    if message.category not in (21, 48, 62):
        return
    context = context or NormalisationContext()
    received_at = context.received_at or datetime.now(UTC)
    if received_at.tzinfo is None:
        raise ValueError("received_at must be timezone-aware")
    received_at = received_at.astimezone(UTC)
    time_item = {21: "071", 48: "140", 62: "070"}[message.category]
    callsign_item = {21: "170", 48: "240", 62: "245"}[message.category]
    for index, record in enumerate(message.records):
        sac, sic = _source(record)
        provenance = Provenance(message.category, message.edition, index, sac, sic)
        position = _position(message, record, provenance, context.cartesian_projector)
        if position is None:
            continue
        track_id = _identity(message, record)
        if track_id is None:
            continue
        speed, heading = _velocity(message, record)
        callsign_value = _item_value(record, callsign_item, "CHR")
        if callsign_value is None:
            callsign_value = _item_value(record, callsign_item)
        callsign = str(callsign_value).strip() if isinstance(callsign_value, str) else None
        yield TrackUpdate(
            track_id=track_id,
            latitude_degrees=position[0],
            longitude_degrees=position[1],
            observed_at=_observed_at(_item_value(record, time_item), received_at),
            provenance=provenance,
            callsign=callsign or None,
            altitude_feet=_altitude(message, record),
            ground_speed_knots=speed,
            heading_degrees=heading,
        )
