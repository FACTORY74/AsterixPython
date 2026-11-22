"""Immutable public ASTERIX value model."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from fractions import Fraction
from types import MappingProxyType
from typing import Any

from .errors import Diagnostic


@dataclass(frozen=True, slots=True)
class ElementValue:
    raw: int | bytes
    value: int | Fraction | str | bytes
    label: str | None = None
    unit: str | None = None


def freeze_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(dict(value))


@dataclass(frozen=True, slots=True)
class DataItem:
    frn: int
    item_id: str
    name: str
    value: Any
    raw: bytes


@dataclass(frozen=True, slots=True)
class UnknownTail:
    raw: bytes
    reason: str


@dataclass(frozen=True, slots=True)
class DataRecord:
    fields: tuple[DataItem, ...]
    fspec: bytes
    raw: bytes
    unknown_tail: UnknownTail | None = None

    def by_id(self, item_id: str) -> DataItem | None:
        return next((item for item in self.fields if item.item_id == item_id), None)

    def by_frn(self, frn: int) -> DataItem | None:
        return next((item for item in self.fields if item.frn == frn), None)


@dataclass(frozen=True, slots=True)
class AsterixMessage:
    category: int
    edition: str
    records: tuple[DataRecord, ...]
    raw: bytes
    ref_edition: str | None = None
    uap: str | None = None
    diagnostics: tuple[Diagnostic, ...] = field(default_factory=tuple)
