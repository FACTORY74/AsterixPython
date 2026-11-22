"""Exceptions and diagnostics for ASTERIX processing."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class Diagnostic:
    code: str
    message: str
    severity: Severity = Severity.ERROR
    offset: int | None = None
    category: int | None = None
    edition: str | None = None
    record_index: int | None = None
    frn: int | None = None
    item_id: str | None = None


class AsterixError(Exception):
    """Base class for all library exceptions."""


class FramingError(AsterixError):
    """The CAT/LEN envelope or byte stream is invalid."""


class TruncatedDataError(FramingError):
    """A message or item ends before its declared structure."""


class SchemaError(AsterixError):
    """A structured specification is invalid or unsupported."""


class SchemaNotFoundError(SchemaError):
    """No definition exists for the requested category and edition."""


class EditionResolutionError(SchemaError):
    """The message edition was not selected unambiguously."""


class UapResolutionError(SchemaError):
    """A category with multiple UAPs needs an explicit profile."""


class DecodeError(AsterixError):
    """A framed message cannot be decoded using the selected schema."""


class EncodeError(AsterixError):
    """A model cannot be represented by the selected schema."""


class ValidationError(AsterixError):
    """Decoded or supplied content violates a schema rule."""
