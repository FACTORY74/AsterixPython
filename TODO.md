# TODO

This file tracks concrete defects and engineering gaps found during the initial
code review. It is ordered by risk rather than estimated effort.

## High priority

### Fix multi-octet FX repetition encoding

`_VariationEncoder._encode_repetitive()` sets the FX continuation bit on the
wrong octets when a `RepetitiveFx` count needs more than seven bits. For 128
repetitions the encoder currently writes a prefix beginning `02 01`; the decoder
therefore reads a count of one.

This affects schema structures present in multiple editions, including CAT048
and CAT062.

Acceptance criteria:

- Encode FX repetition counts using most-significant seven-bit groups first.
- Set FX on every count octet except the final octet.
- Add independent expected-byte tests for counts 0, 1, 127, 128, 16,383, and
  16,384.
- Test at least one real packaged item that uses `RepetitiveFx`.
- Verify that decoding the encoded value returns the original count and data.

### Define and implement validation-mode semantics

`ValidationMode` exposes `strict`, `compatible`, and `inspect`, but the decoder
currently checks the selected mode only when an FSPEC maps to a UAP spare.
`EncodeContext.validation` is not currently consulted.

The behavior promised in `architecture.md` therefore does not match the public
API. Non-zero spare bits, unknown FRNs, reserved values, conditional presence,
and other schema violations do not consistently vary by policy.

Acceptance criteria:

- Create a behavior table for every recognized validation condition under all
  three modes.
- Make strict mode raise for each standards violation identified as fatal.
- Make compatible mode retain safely decoded content and attach diagnostics.
- Make inspect mode preserve opaque content where semantic decoding is unsafe.
- Keep framing, bounds, and resource-limit failures fatal in every mode.
- Either implement meaningful encode policies or remove validation from
  `EncodeContext` until they exist.
- Add policy-specific tests for every condition in the behavior table.

## Medium priority

### Make registry schemas deeply immutable

`SchemaRegistry.get()` protects only the outer schema mappings. Nested
dictionaries and lists in `catalogue`, `uap_definition`, and `raw` remain
mutable. A caller performing schema introspection can therefore alter the
cached rules used by later decodes in the same registry.

Acceptance criteria:

- Recursively freeze schema mappings and sequences, or expose immutable typed
  nodes separate from the interpreter's internal data.
- Confirm that public schema introspection cannot mutate a cached definition.
- Retain thread-safe lazy caching.
- Add a regression test that attempts nested mutation.

### Implement or withdraw `TrackTermination`

`normalise()` declares `TrackTermination` as an output type, and the Kody
example knows how to remove a terminated track, but the normalizer never emits
one. The example also has no age-based expiry, so stale tracks can remain in the
display indefinitely.

Acceptance criteria:

- Identify and document termination indicators for each supported surveillance
  category and edition.
- Emit `TrackTermination` when an applicable decoded record terminates a track,
  with the same stable identity rules used for updates.
- Add category-specific termination fixtures and lifecycle tests.
- Add configurable stale-track expiry to the service adapter if operational
  feeds cannot be assumed to send termination records.
- If termination semantics are intentionally deferred, remove the type from the
  current return annotation and public examples until implemented.

### Add independent structural and wire-vector tests

The generated schema sweep encodes and decodes zero values with the same
interpreter. This is a useful smoke test, but it cannot detect defects shared by
the encoder and decoder.

Acceptance criteria:

- Add independent expected bytes for signed boundaries, scaling, tables, ASCII,
  ICAO strings, octal strings, extended items, explicit items, repetitive
  items, compound items, REF fields, dependent rules, and multi-octet FSPEC/FX.
- Add malformed-input tests for lengths, unterminated FX/FSPEC chains,
  repetition limits, unknown FRNs, and truncated nested structures.
- Give every claimed wire-vector verification level a traceable fixture.
- Test `asterix.json.to_jsonable()` directly, including exact `Fraction`
  conversion.

## Project quality

### Add automated quality gates

The repository does not yet contain CI, a type-checker configuration, a
coverage threshold, or pre-commit checks. Ruff also reports two auto-fixable
findings in `tools/sync_eurocontrol_references.py`.

Acceptance criteria:

- Run Ruff across `src`, `tests`, `examples`, and `tools` with no findings.
- Add and enforce static type checking.
- Run tests on every supported platform and Python version.
- Build both wheel and source distribution in CI.
- Install the built wheel in an isolated environment and verify that packaged
  schema resources load.
- Verify that generated schema artifacts are reproducible and the worktree
  remains clean.

