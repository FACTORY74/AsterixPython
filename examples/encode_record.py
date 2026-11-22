"""Create and encode one CAT062 system-track record.

The values are illustrative rather than an operational track report. The
builder validates item names and values against CAT062 edition 1.21.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from asterix import EncodeContext, SchemaRegistry, encode_record


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    registry = SchemaRegistry.builtin()
    wire = encode_record(
        category=62,
        edition="1.21",
        items={
            "I062/010": {"SAC": 0, "SIC": 42},
            "I062/040": 1234,
            "I062/070": 45_296,
            # These deliberately lie exactly on CAT062's binary WGS-84 grid.
            "I062/105": {"LAT": 45, "LON": -45},
        },
        registry=registry,
        context=EncodeContext(validation="strict"),
    )
    args.output.write_bytes(wire)


if __name__ == "__main__":
    main()
