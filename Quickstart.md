# Quickstart

This guide shows the shortest path to installing the project, decoding and
encoding ASTERIX data, processing a stream, and converting results to JSON.

The project is currently pre-alpha. Its schemas cover many category editions,
but verification depth varies by category. See `docs/coverage.md` before using
an edition operationally.

## Requirements

- Python 3.15
- [uv](https://docs.astral.sh/uv/)

From the repository root, create the development environment and run the test
suite:

```powershell
uv sync --extra dev
uv run --python 3.15 pytest
```

Run all examples from the repository root so the `examples` package and local
project are importable.

## Decode one message

An ASTERIX data block contains its category, but it does not identify its
edition. The caller must supply the edition expected from each data source.

```python
from asterix import DecodeContext, decode_message

wire = bytes.fromhex("300006800102")

message = decode_message(
    wire,
    context=DecodeContext(editions={48: "1.32"}),
)

print(message.category)  # 48
print(message.edition)   # 1.32

record = message.records[0]
source = record.by_id("I048/010")
assert source is not None

print(source.value["SAC"].value)  # 1
print(source.value["SIC"].value)  # 2
print(source.raw.hex())            # 0102
```

Decoded scalar fields are represented by `ElementValue` objects:

- `raw` is the integer or bytes present on the wire;
- `value` is the interpreted value;
- `label` contains an optional table label;
- `unit` contains an optional unit from the schema.

Scaled values use `fractions.Fraction` where possible, preserving the exact
value instead of introducing floating-point rounding.

## Encode one record

Supply item identifiers and structured values. The encoder derives FSPEC and
the outer ASTERIX length.

```python
from asterix import encode_record

wire = encode_record(
    category=48,
    edition="1.32",
    items={
        "I048/010": {"SAC": 1, "SIC": 2},
    },
)

assert wire == bytes.fromhex("300006800102")
```

An item may be supplied as its full identifier (`I048/010`) or by the final
schema name (`010`). Nested mappings use the element names found in the
category definition.

Values must fit the field and be exactly representable at its published scale.
For example, use `Fraction` when a quantity is not an integer:

```python
from fractions import Fraction

from asterix import encode_record

wire = encode_record(
    category=48,
    edition="1.32",
    items={"I048/140": {"ToD": Fraction(1, 128)}},
)
```

## Decode a stream or datagram

Use `Decoder.feed()` when message boundaries do not match input chunks. Call
`finish()` at end of stream to detect a truncated final message.

```python
from asterix import DecodeContext, Decoder

decoder = Decoder(
    context=DecodeContext(
        editions={21: "2.7", 48: "1.32", 62: "1.21"},
        validation="compatible",
    )
)

with open("capture.ast", "rb") as stream:
    while chunk := stream.read(64 * 1024):
        for message in decoder.feed(chunk):
            print(message.category, len(message.records))

decoder.finish()
```

For a UDP payload that may contain one or more complete ASTERIX messages, use
`decode_datagram()` instead:

```python
messages = decoder.decode_datagram(payload)
```

Validation policy applies to the recoverable standards conditions recognized by
the codec. Framing, truncation, schema-resolution, and resource-limit errors
remain fatal in every mode. See the validation table in `architecture.md` for
the precise behavior of `strict`, `compatible`, and `inspect`.

## Select a UAP or REF edition

Some category editions define multiple User Application Profiles (UAPs). Select
the profile explicitly by category:

```python
from asterix import DecodeContext

context = DecodeContext(
    editions={category: edition},
    uaps={category: "profile-name"},
)
```

Reserved Expansion Field definitions have editions independent of the main
category edition. Configure them separately when their contents should be
decoded:

```python
context = DecodeContext(
    editions={48: "1.32"},
    ref_editions={48: "1.13"},
)
```

If no REF edition is selected, the field is retained as opaque bytes rather
than guessed. Use `SchemaRegistry` to inspect the editions and UAP names that
are packaged:

```python
from asterix import SchemaRegistry

registry = SchemaRegistry.builtin()

print(registry.editions(48))
print(registry.editions(48, kind="ref"))

schema = registry.get(48, "1.32")
print(schema.title)
print(schema.uap_names)
```

Schema objects are recursively immutable and safe to share for read-only
introspection. A registry lazily caches loaded definitions.

## Convert a message to JSON

The public model contains bytes, enums, dataclasses, and exact fractions, so it
should not be passed directly to `json.dumps()`. Convert it first:

```python
import json

from asterix.json import to_jsonable

document = to_jsonable(message)
print(json.dumps(document, indent=2, ensure_ascii=False))
```

Bytes become hexadecimal strings. Fractions become objects with `numerator`
and `denominator` fields.

## Normalise surveillance tracks

`normalise()` can project supported CAT021, CAT048, and CAT062 records into a
small category-independent track model. Records without both a usable identity
and position are skipped.

```python
from datetime import UTC, datetime

from asterix import NormalisationContext, TrackUpdate, normalise

for event in normalise(
    message,
    NormalisationContext(received_at=datetime.now(UTC)),
):
    if isinstance(event, TrackUpdate):
        print(event.track_id, event.latitude_degrees, event.longitude_degrees)
```

CAT048 Cartesian positions require a deployment-specific
`cartesian_projector`. CAT048 `TRE` and CAT062 `TSE` last-report indicators
produce `TrackTermination` events even when the terminating record has no
position. CAT021 has no equivalent supported indicator, so long-running
applications should also expire stale tracks. The Kody example defaults to 30
seconds and accepts `ASTERIX_TRACK_EXPIRY_SECONDS` as an environment setting.

## Common exceptions

All library exceptions derive from `AsterixError`. Common cases include:

- `FramingError`: invalid CAT/LEN framing or a configured framing limit;
- `TruncatedDataError`: the input ends before the declared structure;
- `SchemaNotFoundError`: the requested category or edition is not packaged;
- `EditionResolutionError`: multiple editions exist but none was selected;
- `UapResolutionError`: a category requires an explicit UAP;
- `DecodeError`: data cannot be decoded using the selected definition;
- `EncodeError`: supplied values cannot be encoded;
- `ValidationError`: content violates an enforced validation rule.

Catch narrow exception types when recovery differs, or catch `AsterixError` at
an application boundary:

```python
from asterix import AsterixError, decode_message

try:
    message = decode_message(wire, context=context)
except AsterixError as error:
    print(f"ASTERIX input rejected: {error}")
```

## Runnable examples

The repository includes these complete examples:

```powershell
uv run --python 3.15 python examples/decode_file.py capture.ast
uv run --python 3.15 python examples/encode_record.py output.ast
uv run --python 3.15 python examples/receive_udp.py --group 239.1.2.3 --port 8600
uv run --python 3.15 --with fastapi --with uvicorn uvicorn examples.kody_tracks_service:app --port 8018
```

For exact category and edition coverage, verification levels, and known gaps,
continue with `docs/coverage.md`. For design rationale and the longer-term
roadmap, see `architecture.md`.
