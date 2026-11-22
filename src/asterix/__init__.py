"""Public API for the ASTERIX codec."""

from .codec import Decoder, decode_message, encode_record
from .context import DecodeContext, EncodeContext, Limits, ValidationMode
from .errors import (
    AsterixError,
    DecodeError,
    Diagnostic,
    EditionResolutionError,
    EncodeError,
    FramingError,
    SchemaError,
    SchemaNotFoundError,
    TruncatedDataError,
    UapResolutionError,
    ValidationError,
)
from .framing import MessageFramer, split_messages
from .model import AsterixMessage, DataItem, DataRecord, ElementValue, UnknownTail
from .normalize import (
    NormalisationContext,
    Provenance,
    TrackTermination,
    TrackUpdate,
    normalise,
)
from .schema import CategorySchema, SchemaKey, SchemaRegistry

__all__ = [
    "AsterixError",
    "AsterixMessage",
    "CategorySchema",
    "DataItem",
    "DataRecord",
    "DecodeContext",
    "DecodeError",
    "Decoder",
    "Diagnostic",
    "EditionResolutionError",
    "ElementValue",
    "EncodeContext",
    "EncodeError",
    "FramingError",
    "Limits",
    "MessageFramer",
    "NormalisationContext",
    "Provenance",
    "SchemaError",
    "SchemaKey",
    "SchemaNotFoundError",
    "SchemaRegistry",
    "TrackTermination",
    "TrackUpdate",
    "TruncatedDataError",
    "UapResolutionError",
    "UnknownTail",
    "ValidationError",
    "ValidationMode",
    "decode_message",
    "encode_record",
    "normalise",
    "split_messages",
]
