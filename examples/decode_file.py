"""Decode a file containing one or more concatenated ASTERIX messages.

Edition selection is explicit because an ASTERIX data block carries no edition
identifier on the wire.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from asterix import DecodeContext, Decoder, SchemaRegistry
from asterix.json import to_jsonable

EDITIONS = {21: "2.7", 48: "1.32", 62: "1.21"}


def decode_file(path: Path) -> None:
    registry = SchemaRegistry.builtin()
    decoder = Decoder(
        registry=registry,
        context=DecodeContext(editions=EDITIONS, validation="compatible"),
    )

    with path.open("rb") as stream:
        while chunk := stream.read(64 * 1024):
            for message in decoder.feed(chunk):
                print(json.dumps(to_jsonable(message), ensure_ascii=False))

    decoder.finish()  # raises if the final message is truncated


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("capture", type=Path)
    args = parser.parse_args()
    decode_file(args.capture)


if __name__ == "__main__":
    main()
