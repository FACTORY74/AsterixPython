# Asterix architecture

## Implementation status

The first implementation now provides the schema registry, bounded framing,
generic encoder/decoder, immutable wire model, JSON projection, CAT021/CAT048/
CAT062 track normalisation, UDP/file examples, and a Kody v1 GeoJSON adapter.
The bundled structured batch covers 68 editions in 27 categories plus seven
REF editions. Exact status and the remaining publicly documented categories are
kept in `docs/coverage.md`; this architecture describes the completed core and
the larger conformance programme, not a claim that every planned subsystem has
already landed.

## 1. Purpose

This project will provide Python 3.15 libraries and applications for working
with every publicly available ASTERIX category and published edition for which
an implementable specification can be obtained. The architecture must support
more than decoding a few popular categories: it must represent the common
ASTERIX rules, category editions, legacy exceptions, encoding, validation,
transport, diagnostics, and optional surveillance-processing applications
without coupling those concerns together.

The coverage target includes current and superseded published editions, legacy
categories with rules outside the latest Part I, category appendices and REF
definitions, and categories coordinated with rather than managed by the
ASTERIX Maintenance Group when their definitions are public. A category is not
silently omitted because it is uncommon, obsolete, difficult, or unrelated to
aircraft tracking.

ASTERIX is primarily a presentation protocol. It defines how information is
organised and encoded, not how a network session is managed or how tracks are
formed, associated, filtered, or extrapolated. That distinction determines the
main boundary in this project:

```text
category specifications -> schemas -> codec -> records
                                            |
                          transport adapters + tools
                                            |
                      optional surveillance processing
```

The codec and schemas are the core product. Tx/Rx adapters, command-line tools,
and track processing are separately installable layers built on the core.

### 1.1 Dependency rule

Dependencies point inward. Schema and codec modules know nothing about sockets,
asyncio, dataframes, mapping libraries, or tracking. Transports depend on the
codec; normalisers depend on the public wire model; tracking depends only on
normalised events. Applications compose these layers. This rule is enforced in
tests so optional dependencies never become accidental core requirements.

## 2. Scope and non-scope

### 2.1 Core scope

The core library will:

- frame ASTERIX messages from complete buffers or arbitrary byte chunks;
- decode and encode ASTERIX Data Blocks and ASTERIX Records;
- implement FSPEC, UAP, FRN, and all standard data-item structures;
- support multiple categories and multiple published editions per category;
- preserve unknown or uninterpreted data where the wire structure permits it;
- distinguish structural decoding from semantic and application validation;
- expose immutable, typed records and a lossless raw representation;
- provide diagnostics with byte, bit, FRN, and item locations;
- load, validate, and compile declarative category schemas;
- run synchronously without requiring a network or event loop.

Complete coverage is tracked by `(category, edition, profile/appendix)`, not by
category number alone. Each entry is labelled `planned`, `schema-drafted`,
`decode-supported`, `encode-supported`, `verified`, or `blocked`, with a reason
and source citation. "All categories" is therefore a measurable support matrix,
not a claim inferred from having a generic decoder.

"Preserve" is deliberately qualified. If a non-blocking record contains a set
FRN unknown to the selected schema, the decoder can preserve the remaining
record bytes as one `UnknownTail` because outer LEN supplies a boundary; it
cannot safely split that tail into invented items. In a blocked legacy message,
an unknown variable-length item may also make the next record boundary
unknowable. The decoder must then preserve or reject the unparsed block
remainder according to policy, never scan for a plausible FSPEC and pretend it
is synchronised.

### 2.2 Adjacent scope

Separate packages may provide:

- UDP, TCP, multicast, file, and packet-capture Tx/Rx adapters;
- asynchronous pipelines with bounded queues and backpressure;
- inspection, conversion, replay, recording, and schema tools;
- normalisation into a category-independent observation model;
- track stores, extrapolation, filtering, and display services.

### 2.3 Explicit non-scope of the codec

The codec will not:

- infer an edition from payload bytes when the wire format does not identify it;
- silently repair malformed records;
- define network reliability, session management, or security protocols;
- associate plots, create tracks, fuse sensors, or predict trajectories;
- treat decoded numeric values as automatically safe for operational use;
- promise support for confidential or unpublished category definitions.

## 3. Normative model

The implementation is based on Part I edition 3.1 and the applicable category
specification. Some legacy categories, notably CAT001, CAT002, and CAT008, have
category-specific rules and are not governed completely by Part I edition 3.1.
The category-status publication determines whether blocking is permitted.

### 3.1 Wire hierarchy

The outer header is always:

```text
+------------+------------------+----------------------------------+
| CAT: 1 B   | LEN: 2 B, big-endian | payload: LEN - 3 B          |
+------------+------------------+----------------------------------+
```

`LEN` includes CAT and LEN and can represent at most 65,535 octets. The
payload has one of two meanings:

- **Blocking category:** an ASTERIX Data Block may contain one or more Data
  Records of the same category. Individual record lengths are implicit from
  FSPEC and item structures.
- **Non-blocking category:** an ASTERIX Record contains exactly one Data
  Record. Its outer `LEN` provides a safe boundary for forward-compatible
  skipping.

A Data Record consists of a variable-length FSPEC followed by present data
items in increasing FRN order. Each non-FX FSPEC bit maps through the category
edition's UAP to a data item, spare entry, REF, or SPF.

### 3.2 Required item structures

The schema and codec must model:

1. fixed-length items;
2. extended/variable-length items whose subitems use FX continuation;
3. explicit-length items with an inclusive one-octet length;
4. repetitive items with a REP count and fixed-structure repetitions;
5. compound items with their own extensible presence map and non-compound
   child items;
6. Special Purpose Fields (SPF), whose explicit-length body is user-defined;
7. Reserved Expansion Fields (REF), including their item indicator and
   category-specific definitions.

Elements within items include unsigned values, two's-complement signed values,
negative-LSB values, enumerations, scaled values, text/character encodings,
octal or hexadecimal representations, flags, spare bits, reserved values,
"information not available" values, and category-specific transforms.

### 3.3 Editions and compatibility

An edition is part of the decoding context, not normally part of a message.
Edition selection must therefore be configured by `(source, category)` with a
default registry fallback. CAT247 version reports may inform configuration but
do not remove the need for an explicit policy.

Schemas are immutable and addressed by a stable key such as:

```text
(category=48, edition="1.32", profile="standard")
```

The registry must allow several editions to coexist. Applications choose an
edition policy; the codec never silently chooses the numerically newest one.
Forward-compatible decoding may skip appended unknown items only when a known
boundary makes that safe. It must not guess the length of an unknown item in a
blocked legacy record.

Edition strings are identifiers, not decimal numbers: `"1.10"` must not sort
as a number below `"1.9"`. A source-specific policy may be exact, negotiated,
or explicitly configured to use a default. If no policy resolves uniquely,
decoding fails with `EditionResolutionError` while retaining the framed bytes.

## 4. Architectural layers

### 4.1 Schema source layer

Category definitions should be data, not hand-written decoder control flow.
A human-reviewable schema format will capture:

- category number, title, edition, date, status, and source document;
- blocking policy, UAP variants, and the configured or encoded rule used to
  select a UAP;
- FRN-to-item assignments and spare positions;
- item format, length, subitems, FX position, REP size, and explicit lengths;
- bit ranges, signedness, scale/LSB, unit, range, and display precision;
- enumerated values, reserved values, and unavailable-value meanings;
- message-type encoding rules: mandatory, conditional, optional, never;
- REF definitions and recognised SPF profiles;
- notes and provenance down to document section/page where practical.

YAML is suitable for maintained source because it supports comments and is
reviewable. Runtime code must not depend on YAML: release builds compile it to
a deterministic JSON or compact binary resource, then validate and freeze it.
All arithmetic values such as `1/128` should be stored exactly as integers or
rational numerator/denominator pairs rather than binary floating-point.

Most schemas should be declarative. A small, registered transform interface is
needed for genuinely non-standard encodings. Such transforms must be pure,
named, tested functions; schemas must never contain executable expressions.
Conditional presence rules use a deliberately small condition AST (field
exists, equality, membership, bit test, and/or/not), validated by the compiler.
They are not Python snippets or general-purpose templating expressions.

Schema transcription is a high-risk engineering activity. Each schema change
requires a source citation, independent review of UAP and bit layouts, and
generated visual tables that can be compared with the publication. OCR output
may assist discovery but is never an authoritative schema input.

### 4.2 Schema compiler and registry

The compiler performs checks before a schema can ship:

- unique category/edition/profile keys and item references;
- unique FRNs and legal UAP growth;
- complete, non-overlapping bit allocation;
- item and subitem lengths consistent with element layouts;
- legal FX placement and no element crossing an FX bit;
- compound children are not compound;
- enum encodings fit their fields;
- valid ranges fit their encoded widths and signedness;
- message-type rules refer to valid items and conditions;
- REF/SPF placement and blocking rules are coherent;
- source and edition metadata are present.

The runtime `SchemaRegistry` provides explicit lookup, source-specific edition
overrides, plugin registration, and an audit-friendly listing API. Registration
is complete before concurrent decoding starts; runtime mutation is avoided.
After construction the registry and compiled schemas are thread-safe read-only
objects. A service replaces a complete registry snapshot to deploy an update;
it does not mutate schemas while messages are in flight.

Legacy UAP variants require particular care. When a category defines a UAP
selector in the wire data, the schema compiler represents that selection rule;
when it does not, the profile is part of `DecodeContext`. A decoder must not
trial-decode several UAPs and choose the one producing the fewest errors, as
that turns corruption into apparently valid but potentially wrong values.

### 4.3 Framing layer

`MessageFramer` accepts a `bytes`, `bytearray`, `memoryview`, file-like object,
or sequence of arbitrary chunks. It:

- buffers partial three-octet headers and payloads;
- reads CAT and big-endian LEN;
- rejects `LEN < 3` and configured oversize messages;
- yields complete messages without assuming TCP read boundaries;
- optionally resynchronises after corruption using an explicit, conservative
  policy and reports every discarded byte range;
- supports end-of-stream handling for truncated messages.

Datagram adapters normally pass one datagram at a time but must allow multiple
ASTERIX messages per datagram and a message policy for trailing bytes. Stream
adapters use the same framer and must impose buffer and idle-time limits.

Framing is category-agnostic. Splitting multiple Data Records inside a blocked
message belongs to the record decoder because it requires a schema.

A view is zero-copy only when the complete message already lives in one stable,
read-only input buffer. Messages assembled across chunks require owned storage.
The public API documents ownership: retained raw data is immutable `bytes` by
default; an advanced borrowed-view mode is opt-in and valid only for the
documented callback lifetime.

### 4.4 Binary codec layer

The codec has a cursor-based internal API over `memoryview`. It must never read
past the declared outer boundary or an item boundary. The principal operations
are:

```python
message = decode_message(data, context=DecodeContext(...))
wire = encode_message(message, context=EncodeContext(...))

for result in decoder.feed(chunk):
    ...
```

Decoding stages are:

1. validate the CAT/LEN envelope;
2. resolve the category schema and edition policy;
3. determine blocking behaviour;
4. read FSPEC with a configured extension limit;
5. map set bits to FRNs through the UAP;
6. decode items in increasing FRN order;
7. repeat records until the block boundary, if blocking is allowed;
8. apply structural and semantic validation policies;
9. return values, raw slices, provenance, and diagnostics.

Encoding reverses those stages. It derives FSPEC from supplied fields, orders
items by FRN, computes all item and outer lengths, checks presence rules, and
emits canonical spare and FX bits. An explicit `preserve_wire=True` mode may
reuse original raw encodings for unchanged fields to support lossless
round-trips; canonical encoding is the default for newly created records.
`UnknownTail` can be re-emitted only in preserve-wire mode and only if no prior
field, FSPEC, schema, or edition change could invalidate its position.

### 4.5 Public data model

The public model should be immutable dataclasses or equivalent frozen value
objects:

```python
@dataclass(frozen=True, slots=True)
class AsterixMessage:
    category: int
    edition: str
    records: tuple[DataRecord, ...]
    raw: memoryview | None = None
    diagnostics: tuple[Diagnostic, ...] = ()

@dataclass(frozen=True, slots=True)
class DataRecord:
    fields: tuple[DataItem, ...]  # increasing FRN, with indexed lookup helpers
    fspec: bytes
    raw: memoryview | None = None
```

`DataItem` retains its FRN, item identifier, typed value, raw bytes, and
children.
Scaled values use `int`, `Fraction`, `Decimal`, or explicit quantity wrappers;
the library must not introduce avoidable floating-point error. Units are
metadata and may optionally integrate with a units package at an API boundary.
The concrete core representation should be `ScaledInteger(raw, numerator,
denominator, unit)`: it preserves the transmitted integer exactly and converts
explicitly to `Fraction`, `Decimal`, or float. JSON output represents the raw
integer and rational scale, avoiding environment-dependent decimal formatting.

The model needs two views:

- **wire view:** exact category items, subitems, flags, raw bytes, and unknowns;
- **normalised view:** optional domain objects such as position, velocity,
  identity, quality, and timestamp, with explicit provenance.

Normalisation is never lossy replacement. Multiple items can express similar
concepts with different reference frames, timestamps, accuracy, and semantics.

### 4.6 Validation and error model

Validation is divided into layers:

- **framing:** CAT/LEN and available bytes;
- **structural:** FSPEC termination, item lengths, FX chains, REP counts;
- **schema:** UAP mapping, spare bits, ranges, enum and reserved values;
- **record:** mandatory/conditional/never-present rules by message type;
- **application:** source agreements, expected rates, coordinate domains, and
  operational plausibility.

Policies are `strict`, `compatible`, and `inspect`:

- `strict` raises on the first standards violation;
- `compatible` returns safely decodable content with diagnostics;
- `inspect` maximises forensic visibility without inventing values.

These policy names do not weaken memory-safety rules: all modes enforce hard
boundaries and resource limits. They differ only in whether a standards defect
stops semantic decoding, becomes a diagnostic, or leaves opaque raw content.

The current codec applies the following policy table. Conditions not listed
here are structural/schema failures rather than recoverable validation issues
and remain fatal in every mode.

| Condition | Strict | Compatible | Inspect |
| --- | --- | --- | --- |
| Non-zero spare bits | Raise `ValidationError` | Decode and warn | Decode and warn |
| FSPEC selects a UAP spare | Raise `ValidationError` | Warn and continue | Warn and continue |
| Undefined table value while decoding | Raise `ValidationError` | Preserve raw value and warn | Preserve raw value and warn |
| Extended item exceeds the schema | Raise `ValidationError` | Preserve unknown extent and warn | Preserve unknown extent and warn |
| Compound FSPEC selects a spare | Raise `ValidationError` | Warn and continue | Warn and continue |
| FRN exceeds the selected UAP | Raise `ValidationError` | Preserve remaining record bytes as `UnknownTail` and warn | Preserve remaining record bytes as `UnknownTail` and warn |
| Undefined numeric table value while encoding | Raise `EncodeError` | Encode the supplied raw value | Encode the supplied raw value |

An unselected REF edition is not a standards violation: its explicit field is
retained as opaque bytes. Invalid lengths, truncation, unterminated FSPEC/FX,
schema inconsistencies, and configured resource-limit violations are unsafe to
continue and therefore raise in all modes.

Exceptions and diagnostics contain category, edition, record index, FRN/item,
byte offset, bit range, raw value, rule, and severity. Network receivers catch
per-message failures so one malformed message does not terminate a service.

## 5. Tx/Rx and pipeline layer

Tx/Rx support is valuable but should consume the core API rather than define
it. Adapters include:

- UDP unicast, broadcast where supported, and multicast;
- TCP client/server byte streams;
- binary files and timestamped capture/replay formats;
- optional PCAP ingestion/export through an extra dependency;
- user-provided sync and async byte sources/sinks.

The async pipeline should look conceptually like:

```text
source -> frame -> decode -> validate -> route -> application -> encode -> sink
```

Each stage has bounded queues, cancellation, backpressure, counters, latency
metrics, and a dead-letter/diagnostic output. Ordering is preserved per source;
cross-source ordering requires a timestamp/reordering policy and is not implied.

Receiver configuration includes bind/interface, multicast membership, maximum
message size, edition mapping, source identity, timeouts, queue limits, and
malformed-message policy. Transmitter configuration includes destination,
interface/TTL where relevant, batching, pacing, edition, MTU policy, and error
handling. The library must not fragment ASTERIX payloads at the presentation
layer unless an explicitly specified surrounding protocol does so.

Socket endpoints are operational metadata, not ASTERIX source identity. An
edition/source mapping may initially key on endpoint, but applications should
confirm it against decoded SAC/SIC and configured expectations and report
changes or conflicts. SAC/SIC itself is an identifier, not authentication.

Transport security is external to ASTERIX. Deployments needing authenticity,
confidentiality, replay resistance, or access control must use an appropriate
network/security layer and document it in their ICD.

### 5.1 Kody destination adapter

Kody is designed around independently runnable map microservices, so ASTERIX
integration should be a separate `asterix-tracks` service rather than an
in-process import into Kody core. The service composes the layers as follows:

```text
ASTERIX UDP/TCP/file source
    -> frame/decode/validate
    -> category normalisers
    -> latest-track store and optional extrapolator
    -> GeoJSON projection
    -> Kody dataLayer HTTP API
```

The service implements Kody API version 1:

- `GET /api/kody/manifest` declares a `geojson` `dataLayer`, its data path,
  refresh interval, and optional activity path;
- `GET /api/data` returns a GeoJSON `FeatureCollection` with an opaque revision,
  WGS-84 coordinates in `[longitude, latitude]` order, and source health;
- `POST /api/activity` can suspend or resume upstream reception when the layer
  is disabled, if operational policy permits;
- selectable tracks have stable string IDs plus `properties.kody.selectable`
  and a safe `selectionLabel`;
- optional track inspection is a manifest-declared feature action, not a custom
  URL embedded in feature properties.

The adapter owns its receiver settings, edition mapping, track retention,
normalisation, and display projection. Kody owns rendering, selection, polling,
and operator presentation. The GeoJSON representation is a display contract,
not the canonical decoded ASTERIX model: it contains only safe, explicitly
chosen properties and never raw messages by default.

Kody currently targets CPython 3.15 as well, which allows the adapter to share a
deployment environment, but it remains an independent service and dependency
set. It can be launched by Kody's runtime catalogue or run externally and be
registered by URL. `examples/kody_tracks_service.py` defines the intended
minimal integration shape.

## 6. Surveillance processing layer

Track processing is an optional subsystem, not an extension of decoding.
ASTERIX categories transport sensor plots, ADS-B reports, system tracks,
service/status data, and other information; they do not prescribe a universal
tracking algorithm.

### 6.1 Normalisation boundary

Category-specific adapters can produce immutable domain events:

- `PlotObservation`;
- `AdsbObservation`;
- `TrackUpdate`;
- `TrackTermination`;
- `SensorStatus`;
- `ServiceStatus`.

Every event retains source message/item provenance, source identity (including
SAC/SIC where applicable), event time, reception time, coordinate reference,
quality information, and edition. Missing values remain missing rather than
being filled with misleading defaults.

### 6.2 Coordinate and time services

Processing may require WGS-84, polar, Cartesian, local tangent-plane, and
stereographic transformations. Coordinate transforms belong behind an explicit
service interface with declared datum, origin, axis convention, units, and
tested error bounds. A mature geodesy dependency is preferable to custom
formulae.

Time handling must distinguish time of applicability, message reception time,
and processing time. Time-of-day fields require a date/rollover policy. Clock
offsets, out-of-sequence tolerance, leap seconds, stale-data thresholds, and
replay clocks are deployment configuration, not decoder guesses.

### 6.3 Track store and extrapolation

A basic track store may ingest already-formed track updates (for example
CAT062), maintain identity and lifecycle, and expose a snapshot at a requested
time. Extrapolation strategies are replaceable and explicitly selected:

- no extrapolation / last known state;
- constant velocity;
- constant acceleration;
- domain-specific filters such as alpha-beta or Kalman variants.

Each predicted state records its source state, model, horizon, and uncertainty.
Limits on extrapolation age, speed, acceleration, turn rate, and covariance are
configuration. Extrapolated state must never be indistinguishable from measured
or received state.

The track store has an explicit late-data policy and never rewrites historical
state silently. Identity changes, merges, splits, cancellations, and end-of-
track indications are auditable events. Persistence is behind an interface;
the initial in-memory store is not presented as a durable operational database.

### 6.4 Plot tracking and fusion

Plot-to-track association, initiation, coasting, termination, multi-sensor
fusion, duplicate suppression, and identity correlation are a separate,
advanced package. They need scenario-specific performance requirements,
probabilistic models, tuning data, and safety assessment. They are not required
for a standards-compliant ASTERIX library and should not be claimed until
validated against representative truth data.

## 7. Repository structure

```text
asterix/
  .python-version             # pins the development interpreter to Python 3.15
  .gitignore                  # excludes reproducible and machine-local outputs
  .coverage                   # generated coverage database, ignored
  pyproject.toml              # build metadata, dependencies, and tool settings
  uv.lock                     # reproducible development dependency resolution
  README.md                   # installation and project entry point
  architecture.md             # this design and ownership document
  LICENSE                     # licence for independently authored project code
  docs/
    coverage.md               # exact category/edition support ledger
  examples/
    decode_file.py            # incremental capture-file decoder
    encode_record.py          # record construction and encoding example
    receive_udp.py            # multicast UDP receiver example
    kody_tracks_service.py    # Kody v1 GeoJSON microservice example
  reference/
    README.md                 # provenance and reference-mirror instructions
    eurocontrol/
      catalog.json            # downloaded-publication catalogue and metadata
      README.md               # EUROCONTROL mirror details
      archives/               # original downloaded files, normally ignored
      documents/              # extracted/normalised reference documents
  src/asterix/
    __init__.py               # deliberately exported public API
    codec.py                  # schema interpreter, decoder, and encoder
    context.py                # editions, UAPs, policies, and resource limits
    cursor.py                 # bounds-checked byte/bit readers and bit writer
    errors.py                 # exceptions and structured diagnostics
    framing.py                # CAT/LEN stream and datagram framing
    json.py                   # deterministic lossless JSON projection
    model.py                  # immutable wire model
    normalize.py              # CAT021/048/062-to-track adapter
    schema.py                 # checksummed packaged-schema registry
    schemas/                  # compressed, generated runtime definitions
      manifest.json           # upstream revision, hashes, and definition index
      THIRD_PARTY_NOTICES.txt # schema-data attribution and licence notice
      catNNN/{cat,ref}/       # versioned category and REF JSON resources
  src/asterix_codec.egg-info/ # generated Python distribution metadata
  tests/
    test_codec.py             # concrete wire vectors and exact quantities
    test_framing.py           # stream boundaries and resource limits
    test_normalize.py         # surveillance-domain projection
    test_schemas.py           # all-definition/UAP generated smoke sweep
  tools/
    sync_eurocontrol_references.py # reproducible public-reference mirror
    sync_structured_specs.py  # verify and vendor structured definitions
  dist/                       # generated wheel and source archive
  tmp/                        # disposable downloads, extraction, and research
  .venv/                      # local uv-managed Python environment
  .pytest_cache/              # generated pytest cache
  .ruff_cache/                # generated Ruff cache
  htmlcov/                    # optional generated HTML coverage report
```

`src/asterix` is the only import package. Keeping it below `src/` prevents a
checkout's working directory from accidentally satisfying `import asterix`;
tests therefore exercise the installed/editable package configuration.

### 7.1 Generated packaging metadata

`src/asterix_codec.egg-info` is created by setuptools when `uv sync`, an
editable install, or a package build asks Python for distribution metadata. It
is **not** application source and is not imported as `asterix_codec`. The name
comes from the distribution name `asterix-codec` in `pyproject.toml`, while the
actual Python import remains `asterix`.

Its usual files have these purposes:

- `PKG-INFO` is the generated package name, version, requirements, classifiers,
  licence metadata, and long description;
- `SOURCES.txt` is setuptools' generated source-distribution file inventory;
- `requires.txt` records generated dependency and optional-extra metadata;
- `top_level.txt` records the installed top-level import package (`asterix`);
- `dependency_links.txt` is a legacy setuptools metadata file and is normally
  empty for this project.

The complete `*.egg-info/` directory is ignored by Git. It may be removed when
no packaging process is using it and will be regenerated on the next sync or
build. It must never be manually edited, reviewed as authoritative metadata, or
used to store project data; `pyproject.toml` is the source of truth.

The other generated directories follow the same ownership rule: `.venv/`,
`.pytest_cache/`, `.ruff_cache/`, `htmlcov/`, `tmp/`, `build/`, and `dist/` are
reproducible local outputs and are ignored. The `.coverage` database is the
file equivalent of these caches. `dist/` is retained only when a wheel or
source archive is deliberately being handed off. Python `__pycache__/`
directories and `*.pyc` files may occur under any source or example directory
and are also disposable.

### 7.2 Generated schemas and reference publications

Packaged files below `src/asterix/schemas/` are generated but intentionally
shipped in the wheel because decoding must work offline. The sync tool records
their upstream revision and verifies every uncompressed definition with the
SHA-256 values in `manifest.json`; generated category files are not edited by
hand. Their BSD attribution is carried in `THIRD_PARTY_NOTICES.txt`.

Large EUROCONTROL publications have different ownership. They remain in the
reproducible `reference/` mirror and are not included in the Python wheel.
Downloaded archives and extracted documents are normally ignored so a checkout
can reconstruct them from `catalog.json` without committing hundreds of large
files.

The distribution is named `asterix-codec` and its import package is `asterix`.
Internal modules may change before the first stable release; public imports are
re-exported deliberately from `asterix.__init__`.

## 8. Public APIs and extension points

Initial stable APIs should be small:

- `decode_message`, `decode_many`, and `encode_message`;
- `Decoder.feed` for incremental input;
- `SchemaRegistry` and read-only schema introspection;
- `DecodeContext`, `EncodeContext`, validation policies, and limits;
- immutable message, record, item, diagnostic, and unknown-value types.
- `normalise(message)` yielding typed domain events for supported categories;
- explicit builders for creating records by item identifier without requiring
  callers to calculate FSPEC or LEN.

Extension points are registered explicitly:

- category schema packages;
- non-standard element transforms;
- SPF profiles scoped by organisation/category/profile identifier;
- normalisers;
- byte sources/sinks and pipeline stages;
- extrapolation strategies.

No module import should automatically open sockets, discover plugins, mutate a
global registry, or configure logging. Entry-point discovery, if supported, is
an explicit application action.

## 9. Performance and resource safety

The first implementation should optimise correctness and bounded resource use,
then profile real captures. Design choices that preserve future performance:

- parse from `memoryview` with a monotonic cursor;
- avoid per-bit strings and unnecessary byte copies;
- compile schema access paths and element decoders once;
- use frozen/slotted objects for common models;
- offer lazy item decoding only if profiling justifies its complexity;
- permit a callback/iterator mode that does not retain full captures;
- isolate optional dataframe/Arrow conversion from the core.

Every variable-length mechanism has a configurable bound: outer LEN, buffered
bytes, FSPEC octets, FX extensions, REP count, compound presence octets,
explicit item length, records per block, diagnostics per message, and retained
raw data. These are correctness and denial-of-service protections.

The two-octet outer LEN caps an individual message at 65,535 bytes, but an
attacker can still send an unbounded sequence of incomplete headers, tiny
records, or high-REP items. Limits therefore apply per message, per connection,
per source, and over time; services also need rate limiting and idle-buffer
expiry.

## 10. Observability and operations

Library code emits diagnostics and uses standard logging without configuring
handlers. Services should expose counters for bytes, messages, records,
categories, editions, decode outcomes, unknown fields, dropped input, queue
depth, and processing latency. Logs must rate-limit repeated malformed traffic
and avoid dumping sensitive operational payloads by default.

Capture and replay require metadata: source endpoint, interface, reception
timestamp, monotonic ordering, original datagram/stream boundaries, and tool
version. Deterministic replay uses an injectable clock and controllable speed.

## 11. Security and robustness

ASTERIX input is untrusted binary data. The implementation must:

- check boundaries before every read and arithmetic allocation;
- reject impossible or cyclic lengths and unterminated extension chains;
- cap buffering, repetitions, nesting, and diagnostic volume;
- avoid schema expressions evaluated as Python;
- never import executable code from a received message;
- distinguish transport source metadata from authenticated identity;
- support fuzzing without sockets or global state;
- document that successful decoding is not proof of authenticity or validity.

Schema updates are supply-chain inputs. Releases should record source document
hashes, generated-resource hashes, compiler version, and review status.
Downloaded reference documents are not automatically redistributable merely
because they are public. Packaging and test-fixture choices must respect each
publisher's terms; provenance metadata and independently authored schemas are
kept separate from third-party documents.

## 12. Testing and conformance

Testing is layered:

1. **bit primitives:** signed values, scaling, enums, text, masks, and FX;
2. **item structures:** fixed, extended, explicit, repetitive, compound, REF,
   and SPF boundary cases;
3. **schema validation:** invalid layouts and edition evolution rules;
4. **category vectors:** hand-checked examples for every supported edition;
5. **round trips:** `decode(encode(model))` and canonical wire stability;
6. **lossless inspection:** unchanged decoded messages reproduce original wire,
   including opaque tails where safe;
7. **streaming:** every possible chunk split, concatenation, and truncation;
8. **property/fuzz:** malformed lengths, FSPEC/FX chains, REP counts, unknowns;
9. **transport integration:** loopback, multicast where available, backpressure;
10. **tracking:** deterministic clocks, coordinate fixtures, lifecycle and model
    error bounds, separately from codec conformance.

Public examples in specifications are converted into traceable fixtures where
licensing permits. Captures must be synthetic, redistributable, or kept out of
the repository. A support claim means all mandatory structures for a named
category edition are implemented and tested; partial support is labelled.

Schema test generation should cover every FRN, item structure, enum code, edge
of range, signed boundary, extension depth, and message-type presence rule.
Round-trip tests alone are insufficient because an encoder and decoder can
share the same mistake; independent expected bytes are required.

## 13. Documentation and governance

For each supported category, publish a generated support page listing edition,
source, blocking policy, UAP, implemented items, known limitations, and tests.
Schema changes require review against the cited specification and regenerated
artifacts must be reproducible. The project should use semantic versioning for
Python APIs while treating category-schema additions and corrections as
separately visible compatibility changes.

Operational deployments need an Interface Control Document (ICD) covering at
least transports, endpoints, category editions, SPF agreements, absent
extended-subitem interpretation where ambiguous, maximum block size, source
identifiers, timing, malformed-data policy, migration, and security controls.

Compatibility has three independently versioned dimensions: Python API,
compiled schema content, and normalised domain model. Release notes identify
all three. Correcting a schema can change decoded values without changing the
Python call signature and must therefore be prominent and machine-queryable.

## 14. Delivery plan

### Phase 0 - foundation

- package metadata for Python 3.15, linting, typing, and CI;
- source-document catalogue and schema conventions;
- cursor, limits, diagnostics, schema model, and compiler skeleton.

### Phase 1 - standards core

- framing plus all standard item structures;
- immutable wire model, decoding, encoding, and validation;
- one small category and one representative complex category end-to-end;
- exhaustive chunking and malformed-input tests.

CAT048 or CAT062 is useful as the complex category, but an intentionally small
category should be implemented first to validate the schema/compiler workflow.

### Phase 2 - category breadth and tools

- all publicly specified category editions, implemented in prioritised batches;
- dump/JSON/encode CLI, schema inspection, capture, and replay;
- CAT021, CAT048, and CAT062 normalisers;
- UDP/TCP/file adapters and async pipelines.

The batch order affects delivery order only. It does not reduce the coverage
target. Each batch updates the generated support matrix, and the phase is not
complete while a public specification remains unclassified or omitted.

### Phase 3 - compatibility and hardening

- legacy blocking categories and their explicit exceptions;
- REF/SPF profiles, edition migration tests, fuzzing, and benchmarks;
- generated category support matrix and conformance corpus.

### Phase 4 - optional applications

- track update store and clearly labelled extrapolation;
- visualisation or service APIs;
- plot tracking/fusion only after separate requirements, data, and validation
  criteria are agreed.

## 15. Decisions to settle before implementation

1. Which category editions form the first supported release and in what order
   will the remaining public editions follow?
2. Is schema YAML acceptable as a build-time dependency and review format?
3. Which exact numeric public representation is preferred: `Fraction`,
   `Decimal`, scaled integer plus metadata, or configurable conversion?
4. Is lossless raw preservation required by default or opt-in?
5. Which capture format should preserve both timing and datagram boundaries?
6. Which transport and async features belong in the base distribution versus
   extras?
7. Does the first application need only received-track extrapolation, or actual
   plot association and multi-sensor tracking?
8. What conformance evidence is required before a category is called supported?
9. What is the support policy for release-candidate Python 3.15 until its final
   release, and which CI platforms are mandatory?

Until those decisions are made, the core should remain conservative: explicit
edition selection, exact values, bounded decoding, no silent repair, and clean
separation between wire truth and derived surveillance state.

## 16. Standards reviewed for this architecture

This design was checked against the locally mirrored public EUROCONTROL
documents, in particular:

- ASTERIX Part I, edition 3.1: general organisation, Data Block versus Record,
  FSPEC/UAP, standard item formats, REF/SPF, compatibility, and addressing;
- CAT021, edition 2.7: a large ADS-B category with compound and repetitive
  structures, data ages, and REF evolution;
- CAT048, edition 1.32: a blocked monoradar category with repetitive and
  compound items plus category-specific REF usage;
- CAT062, edition 1.21: a large system-track category used to challenge the
  schema and optional track-normalisation boundary.

The machine-readable publication provenance and checksums are maintained in
`reference/eurocontrol/catalog.json`. The category specification and the
deployment ICD remain authoritative when this architecture and a source
publication differ.
