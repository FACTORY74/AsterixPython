"""Explicit edition, UAP, validation, and resource policies."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType


class ValidationMode(StrEnum):
    STRICT = "strict"
    COMPATIBLE = "compatible"
    INSPECT = "inspect"


@dataclass(frozen=True, slots=True)
class Limits:
    max_message_bytes: int = 65_535
    max_buffer_bytes: int = 1_048_576
    max_fspec_octets: int = 32
    max_fx_octets: int = 64
    max_repetitions: int = 65_535
    max_records_per_block: int = 16_384


@dataclass(frozen=True, slots=True)
class DecodeContext:
    editions: Mapping[int, str] = field(default_factory=dict)
    ref_editions: Mapping[int, str] = field(default_factory=dict)
    uaps: Mapping[int, str] = field(default_factory=dict)
    validation: ValidationMode | str = ValidationMode.STRICT
    limits: Limits = field(default_factory=Limits)

    def __post_init__(self) -> None:
        object.__setattr__(self, "editions", MappingProxyType(dict(self.editions)))
        object.__setattr__(self, "ref_editions", MappingProxyType(dict(self.ref_editions)))
        object.__setattr__(self, "uaps", MappingProxyType(dict(self.uaps)))
        object.__setattr__(self, "validation", ValidationMode(self.validation))


@dataclass(frozen=True, slots=True)
class EncodeContext:
    validation: ValidationMode | str = ValidationMode.STRICT
    limits: Limits = field(default_factory=Limits)

    def __post_init__(self) -> None:
        object.__setattr__(self, "validation", ValidationMode(self.validation))
