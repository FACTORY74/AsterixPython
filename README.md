# Asterix

A Python 3.15 implementation of the EUROCONTROL ASTERIX presentation format.
It uses versioned, declarative specifications and supports incremental framing,
decoding, encoding, validation, inspection, and optional integrations.

The project is under active development. See `architecture.md` for the design,
`docs/coverage.md` for the exact category/edition ledger, and `examples/` for
runnable programs.

## ASTERIX message categories

An ASTERIX category identifies the application-level layout of a message. It
does **not** identify the edition on the wire, so callers must also configure
the expected edition and, where applicable, UAP and Reserved Expansion Field
(REF) edition. Selecting the wrong edition can produce a plausible but
incorrect decode.

The catalogue below covers every category allocated in EUROCONTROL's status
table dated 22 October 2025. Numbers not listed in these tables are unallocated
and available for future assignment. The allocation ranges are:

- CAT000-CAT127: standard civil and military applications;
- CAT128-CAT240: special civil and military applications;
- CAT241-CAT255: civil and military non-standard applications.

Library status has a precise meaning:

- **Implemented**: at least one packaged edition can be decoded and encoded;
- **Pending**: a public definition exists but has not yet been transcribed;
- **Development/reserved**: no stable public edition can be implemented;
- **Historical**: obsolete or replaced, with no current maintained definition;
- **Unavailable**: allocated, but its specification is not public on the
  EUROCONTROL ASTERIX website.

### CAT000-CAT127: standard applications

| CAT | Message purpose | Latest public/official state | Library |
| --- | --- | --- | --- |
| 000 | Security wrapper | Reserved and under development | Development |
| 001 | Monoradar target reports | 1.4; replaced by CAT048 | Implemented |
| 002 | Monoradar service messages | 1.2; replaced by CAT034 | Implemented |
| 003 | Synthetic air-traffic distribution | MADAP use terminated | Historical |
| 004 | Safety-net messages | 1.13 | Implemented |
| 005 | Airport Safety Support System messages | Under development | Development |
| 007 | Directed interrogation messages | 1.12 | Implemented |
| 008 | Monoradar-derived weather information | 1.3 | Implemented |
| 009 | Multisensor-derived weather information | 2.1 | Implemented |
| 010 | Monosensor surface-movement data | 1.1 | Implemented |
| 011 | Advanced-SMGCS data | 1.3 | Implemented |
| 012 | Monoradar target reports for PAR | Reserved | Reserved |
| 013 | Monoradar service messages for PAR | Reserved | Reserved |
| 014 | Monoradar weather reports for PAR | Reserved | Reserved |
| 015 | INCS target reports | 1.2 | Implemented |
| 016 | INCS configuration reports | 1.0 | Implemented |
| 017 | Mode S surveillance-coordination messages | 1.3 | Implemented |
| 018 | Mode S data-link messages | 1.8 | Implemented |
| 019 | Multilateration-system status messages | 1.3 | Implemented |
| 020 | Multilateration target reports | 1.11 | Implemented |
| 021 | ADS-B target reports | 2.7 | Implemented |
| 022 | TIS-B management messages | Reserved | Reserved |
| 023 | CNS/ATM ground-station service messages | 1.3 | Implemented |
| 024 | ADS-C messages | Reserved | Reserved |
| 025 | CNS/ATM ground-system status reports | 1.6 | Implemented |
| 030 | Air-situation picture exchange | Obsolete ARTAS category | Historical |
| 031 | Sensor-information messages | Obsolete ARTAS category | Historical |
| 032 | Miniplan reports to an SDPS | 1.2 | Implemented |
| 033 | FAA ADS-B messages | 1.1 | Pending |
| 034 | Monoradar service messages | 1.29; successor to CAT002 | Implemented |
| 048 | Monoradar target reports | 1.32; successor to CAT001 | Implemented |
| 053 | Next-generation ADS-B target reports | Under development | Development |
| 061 | SDPS session and service-control messages | 1.2 | Pending |
| 062 | System-track data | 1.21 | Implemented |
| 063 | Sensor-status messages | 1.7 | Implemented |
| 065 | SDPS service-status messages | 1.6 | Implemented |
| 094 | Next-generation system-track data | Under development | Development |

### CAT128-CAT240: special and military applications

| CAT | Message purpose | Latest public/official state | Library |
| --- | --- | --- | --- |
| 128 | C3I-message exchange | 1.0; Austrian Air Force | Unavailable |
| 129 | UAS identification reports | 1.2 | Pending |
| 130 | Vertical Stack List reports | NATS allocation | Unavailable |
| 150 | Flight-data messages | 3.0; MADAP | Implemented |
| 151 | Association messages | 3.0; MADAP | Pending |
| 152 | Timestamp messages | 3.0; MADAP | Pending |
| 153 | Special-purpose messages | 3.0; MADAP | Pending |
| 155 | NATO ACCS sensor monitoring | NATO ACCS | Unavailable |
| 156 | NATO ACCS radar control | NATO ACCS | Unavailable |
| 157 | NATO ACCS service data | NATO ACCS | Unavailable |
| 158 | NATO ACCS strobe reports | NATO ACCS | Unavailable |
| 159 | NATO ACCS target reports | NATO ACCS | Unavailable |
| 160 | NATO ACCS passive-sensor data | NATO ACCS | Unavailable |
| 180 | NATO ACCS TBM tracks | NATO ACCS | Unavailable |
| 201 | NATO ACCS joint-environment picture | NATO ACCS | Unavailable |
| 203 | NATO ACCS IDCP data | NATO ACCS | Unavailable |
| 204 | Recognised Air Picture | 1.0; German Air Force | Pending |
| 205 | Radio-direction-finder reports | 1.0 | Implemented |
| 237 | Aeronautical-data messages | 1.2 | Pending |
| 238 | Service-prediction reports | 1.1 | Pending |
| 239 | Foreign-object-debris reports | 1.0 | Pending |
| 240 | Radar-video transmission | 1.3 | Implemented |

The NATO ACCS specifications for CAT155-CAT203 are explicitly not available
from the EUROCONTROL ASTERIX website, so their allocations can be documented
but their wire formats cannot be implemented from the public source set.

### CAT241-CAT255: non-standard applications

| CAT | Message purpose | Latest public/official state | Library |
| --- | --- | --- | --- |
| 241 | RMCDE/RMCDS technical messages | Not publicly available | Unavailable |
| 242 | POEMS development | Reserved | Reserved |
| 243 | POEMS development | Reserved | Reserved |
| 244 | Reference-trajectory state vectors | 0.5; SASS-C | Pending |
| 245 | POEMS development | Reserved | Reserved |
| 246 | POEMS development | Reserved | Reserved |
| 247 | Version-number exchange | 1.3 | Implemented |
| 248 | Industry-internal use | Not publicly available | Unavailable |
| 249 | Industry-internal use | Not publicly available | Unavailable |
| 250 | Industry-internal use | Not publicly available | Unavailable |
| 251 | Supplemental/BIRDTAM data | Not publicly available | Unavailable |
| 252 | ARTAS session and service control | Removed from ASTERIX website | Historical |
| 253 | Remote-station monitoring and control | 12.0 | Pending |
| 254 | Up-line memory-dump information | Reserved; not publicly available | Reserved |
| 255 | Down-line program-load information | Reserved; not publicly available | Reserved |

The exact packaged editions and verification level for each implemented
category are recorded in [`docs/coverage.md`](docs/coverage.md). EUROCONTROL's
[ASTERIX page](https://www.eurocontrol.int/asterix) and its
[category-status publication](https://www.eurocontrol.int/publication/list-asterix-categories-and-their-statuses)
remain authoritative for allocations and current editions.

## Development

```powershell
uv sync --extra dev
uv run --python 3.15 pytest
```

The bundled structured schemas are derived from the BSD-licensed
`zoranbosnjak/asterix-specs` project and retain its attribution in
`src/asterix/schemas/THIRD_PARTY_NOTICES.txt`. EUROCONTROL publications remain
the normative source.

