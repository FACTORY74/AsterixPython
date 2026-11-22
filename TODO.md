# TODO

This file tracks concrete defects and engineering gaps found during the initial
code review. It is ordered by risk rather than estimated effort.

## Medium priority

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

