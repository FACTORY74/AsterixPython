# ASTERIX definition coverage

This ledger prevents “generic decoder” from being confused with verified
category coverage. It records the state at the bundled schema revision shown in
`src/asterix/schemas/manifest.json`.

## Implemented structured definitions

The package contains 68 category-edition definitions across 27 categories and
seven Reserved Expansion Field definitions. Every definition loads, every UAP
reference resolves, and every UAP item is exercised by the generated
encode/decode smoke suite.

| Category | Editions |
|---:|:---|
| 001 | 1.2, 1.3, 1.4 |
| 002 | 1.0, 1.1, 1.2 |
| 004 | 1.12, 1.13 |
| 007 | 1.12 |
| 008 | 1.2, 1.3 |
| 009 | 2.1 |
| 010 | 1.1 |
| 011 | 1.2, 1.3 |
| 015 | 1.0, 1.1, 1.2 |
| 016 | 1.0 |
| 017 | 1.3 |
| 018 | 1.7, 1.8 |
| 019 | 1.3 |
| 020 | 1.9, 1.10, 1.11 |
| 021 | 0.23–0.26, 2.1–2.7 |
| 023 | 1.2, 1.3 |
| 025 | 1.5, 1.6 |
| 032 | 1.1, 1.2 |
| 034 | 1.27–1.29 |
| 048 | 1.27–1.32 |
| 062 | 1.16–1.21 |
| 063 | 1.6, 1.7 |
| 065 | 1.4–1.6 |
| 150 | 3.0 |
| 205 | 1.0 |
| 240 | 1.3 |
| 247 | 1.2, 1.3 |

## Published definitions not yet transcribed

EUROCONTROL's public status table and the mirrored publications also contain
definitions that are not present in the BSD-licensed structured corpus. These
remain implementation work; the library fails with `SchemaNotFoundError`
instead of guessing their layouts.

- historical CAT003 from the published MADAP interface document;
- CAT033, CAT061, CAT129, CAT151, CAT152, CAT153, CAT204;
- CAT237, CAT238, CAT239, CAT244, and CAT253.

The PDFs are mirrored under `reference/eurocontrol/`. Each must be independently
transcribed into the declarative model, checked against its UAP and examples,
and given semantic wire vectors before it moves into the implemented table.
Categories which EUROCONTROL marks reserved, under development, unavailable,
confidential, or managed without a public definition are not implementable from
public information and must not be represented by invented schemas.

Category-level support does not imply that every published REF or appendix is
packaged. The current manifest contains seven REF definitions for CAT021,
CAT048, and CAT062. Published REFs and appendices outside that set are tracked
as separate schema work because their editions evolve independently of the
basic category.

## Verification levels

- **Schema smoke**: definition loads and generated zero-value UAP item vectors
  round-trip. This is the current baseline for every implemented definition.
- **Wire vector**: known bytes decode to expected values and re-encode exactly.
  CAT048 1.32 and CAT062 1.21 currently have such tests in
  `tests/test_codec.py` and `tests/test_wire_vectors.py`.
- **Operational capture**: independently produced captures and boundary cases
  have been checked. No category has this label yet.

Consequently, this release is an implementable core and broad first schema
batch, not a claim of complete conformance for every allocated category number.
