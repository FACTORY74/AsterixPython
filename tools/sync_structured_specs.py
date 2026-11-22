#!/usr/bin/env python3
"""Vendor compressed structured ASTERIX definitions with provenance."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import shutil
import ssl
import subprocess
import urllib.error
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

ARCHIVE_URL = "https://zoranbosnjak.github.io/asterix-specs/specs.zip"
MANIFEST_URL = "https://zoranbosnjak.github.io/asterix-specs/manifest.json"
REVISION_URL = "https://zoranbosnjak.github.io/asterix-specs/gitrev.txt"
LICENSE_URL = "https://raw.githubusercontent.com/zoranbosnjak/asterix-specs/master/LICENSE"
USER_AGENT = "Asterix-schema-sync/1.0"


def check_packaged(destination: Path) -> None:
    manifest = json.loads((destination / "manifest.json").read_text(encoding="utf-8"))
    expected_paths: set[Path] = set()
    for entry in manifest["definitions"]:
        relative = Path(str(entry["path"]))
        expected_paths.add(relative)
        packaged = destination / relative
        raw = gzip.decompress(packaged.read_bytes())
        if hashlib.sha256(raw).hexdigest() != entry["sha256"]:
            raise ValueError(f"schema checksum mismatch: {relative.as_posix()}")
        output = io.BytesIO()
        with gzip.GzipFile(filename="", mode="wb", fileobj=output, mtime=0) as compressed:
            compressed.write(raw)
        if output.getvalue() != packaged.read_bytes():
            raise ValueError(f"schema gzip is not reproducible: {relative.as_posix()}")
    actual_paths = {path.relative_to(destination) for path in destination.rglob("*.json.gz")}
    if actual_paths != expected_paths:
        missing = sorted(path.as_posix() for path in expected_paths - actual_paths)
        unexpected = sorted(path.as_posix() for path in actual_paths - expected_paths)
        raise ValueError(f"schema file set differs: missing={missing}, unexpected={unexpected}")


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return response.read()
    except urllib.error.URLError as error:
        if not isinstance(error.reason, ssl.SSLCertVerificationError):
            raise
        curl = shutil.which("curl.exe") or shutil.which("curl")
        if not curl:
            raise
        return subprocess.run(
            [curl, "--fail", "--location", "--silent", "--show-error", url],
            check=True,
            capture_output=True,
        ).stdout


def definition_key(path: PurePosixPath) -> tuple[str, int, str] | None:
    parts = path.parts
    if path.name != "definition.json" or len(parts) < 5:
        return None
    category_part = next((part for part in parts if part.startswith("cat")), None)
    if not category_part or not category_part[3:].isdigit():
        return None
    category = int(category_part[3:])
    if "cats" in parts:
        edition_part = next(part for part in parts if part.startswith("cat") and "." in part)
        return "cat", category, edition_part[3:]
    if "refs" in parts:
        edition_part = next(
            part for part in parts if part.startswith("ref") and part[3:] and part[3].isdigit()
        )
        return "ref", category, edition_part[3:]
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, help="use an existing specs.zip")
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify packaged checksums, file set, and deterministic compression",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    destination = root / "src" / "asterix" / "schemas"
    if args.check:
        check_packaged(destination)
        return 0
    destination.mkdir(parents=True, exist_ok=True)
    for stale_definition in destination.rglob("*.json.gz"):
        stale_definition.unlink()
    archive = args.archive.read_bytes() if args.archive else fetch(ARCHIVE_URL)
    upstream_manifest = json.loads(fetch(MANIFEST_URL))
    revision = fetch(REVISION_URL).decode("ascii").strip()
    license_text = fetch(LICENSE_URL).decode("utf-8")

    entries: list[dict[str, object]] = []
    with zipfile.ZipFile(io.BytesIO(archive)) as package:
        for member in package.infolist():
            path = PurePosixPath(member.filename)
            key = definition_key(path)
            if key is None:
                continue
            kind, category, edition = key
            raw = package.read(member)
            json.loads(raw)  # validate before writing
            relative = Path(f"cat{category:03d}") / kind / f"{edition}.json.gz"
            output = destination / relative
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("wb") as stream:
                with gzip.GzipFile(filename="", mode="wb", fileobj=stream, mtime=0) as compressed:
                    compressed.write(raw)
            entries.append(
                {
                    "kind": kind,
                    "category": category,
                    "edition": edition,
                    "path": relative.as_posix(),
                    "sha256": hashlib.sha256(raw).hexdigest(),
                }
            )

    entries.sort(key=lambda item: (int(item["category"]), str(item["kind"]), str(item["edition"])))
    manifest = {
        "source": ARCHIVE_URL,
        "revision": revision,
        "archive_sha256": hashlib.sha256(archive).hexdigest(),
        "upstream_manifest": upstream_manifest,
        "definitions": entries,
    }
    (destination / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    (destination / "THIRD_PARTY_NOTICES.txt").write_text(
        "Structured ASTERIX definitions\n"
        "==============================\n\n"
        f"Source: {ARCHIVE_URL}\nRevision: {revision}\n\n{license_text}",
        encoding="utf-8",
    )
    print(f"Wrote {len(entries)} definitions from revision {revision}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
