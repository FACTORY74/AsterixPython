#!/usr/bin/env python3
"""Mirror public ASTERIX references from the EUROCONTROL library."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import shutil
import ssl
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path


BASE_URL = "https://www.eurocontrol.int"
SEARCH_PATH = "/library/search"
SEARCH_QUERY = {
    "keywords": "asterix",
    "sort_by": "search_api_relevance",
    "f[0]": "topic:973",
    # Keep the complete result set on one page. Relevance ordering is not
    # stable enough for reliable offset pagination and can repeat entries.
    "items_per_page": "50",
}
USER_AGENT = "Asterix-reference-sync/1.0 (+public EUROCONTROL documents)"
PAGE_RE = re.compile(r"[?&]page=(\d+)")
ROW_RE = re.compile(
    r'<div class="views-row">(?P<row>.*?)(?=<div class="views-row">|<nav[^>]+pager|\Z)',
    re.DOTALL,
)
TITLE_RE = re.compile(
    r'<p class="h6 mb-2">\s*<a href="(?P<path>[^"]+)"[^>]*>(?P<title>.*?)</a>',
    re.DOTALL,
)
VERSION_RE = re.compile(
    r'field-label-inline">Edition/Version</div>(?P<version>.*?)</div>', re.DOTALL
)
DATE_RE = re.compile(r'<time datetime="(?P<date>[^"]+)"')
DOWNLOAD_RE = re.compile(r'<a href="(?P<path>/archive_download/all/node/(?P<id>\d+))"')
TAG_RE = re.compile(r"<[^>]+>")


def clean(value: str) -> str:
    return " ".join(html.unescape(TAG_RE.sub("", value)).split())


def decode_source(value: bytes) -> str:
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError:
        return value.decode("windows-1252")


def fetch(url: str) -> tuple[bytes, dict[str, str]]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.read(), dict(response.headers.items())
    except urllib.error.URLError as error:
        if not isinstance(error.reason, ssl.SSLCertVerificationError):
            raise
        curl = shutil.which("curl.exe") or shutil.which("curl")
        if not curl:
            raise
        result = subprocess.run(
            [
                curl,
                "--fail",
                "--location",
                "--silent",
                "--show-error",
                "--user-agent",
                USER_AGENT,
                url,
            ],
            check=True,
            capture_output=True,
        )
        return result.stdout, {}


def download_url(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with (
            urllib.request.urlopen(request, timeout=120) as response,
            destination.open("wb") as output,
        ):
            shutil.copyfileobj(response, output)
    except urllib.error.URLError as error:
        if not isinstance(error.reason, ssl.SSLCertVerificationError):
            raise
        curl = shutil.which("curl.exe") or shutil.which("curl")
        if not curl:
            raise
        subprocess.run(
            [
                curl,
                "--fail",
                "--location",
                "--silent",
                "--show-error",
                "--user-agent",
                USER_AGENT,
                "--output",
                str(destination),
                url,
            ],
            check=True,
        )


def search_url(page: int = 0) -> str:
    query = dict(SEARCH_QUERY)
    if page:
        query["page"] = str(page)
    return f"{BASE_URL}{SEARCH_PATH}?{urllib.parse.urlencode(query)}"


def parse_page(source: str) -> list[dict[str, str]]:
    publications: list[dict[str, str]] = []
    for match in ROW_RE.finditer(source):
        row = match.group("row")
        title = TITLE_RE.search(row)
        download = DOWNLOAD_RE.search(row)
        if not title or not download:
            continue
        version = VERSION_RE.search(row)
        date = DATE_RE.search(row)
        publications.append(
            {
                "node_id": download.group("id"),
                "title": clean(title.group("title")),
                "edition": clean(version.group("version")) if version else "",
                "publication_date": date.group("date") if date else "",
                "source_url": urllib.parse.urljoin(BASE_URL, html.unescape(title.group("path"))),
                "archive_url": urllib.parse.urljoin(BASE_URL, download.group("path")),
            }
        )
    return publications


def discover() -> list[dict[str, str]]:
    first_bytes, _ = fetch(search_url())
    first = decode_source(first_bytes)
    pages = [int(value) for value in PAGE_RE.findall(html.unescape(first))]
    last_page = max(pages, default=0)
    records = parse_page(first)
    for page in range(1, last_page + 1):
        body, _ = fetch(search_url(page))
        records.extend(parse_page(decode_source(body)))
    return list({record["node_id"]: record for record in records}.values())


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def file_signature(path: Path) -> bytes:
    with path.open("rb") as stream:
        return stream.read(4)


def download(record: dict[str, str], archive_dir: Path, document_dir: Path) -> None:
    candidates = list(archive_dir.glob(f"download_{record['node_id']}.*"))
    archive = next((path for path in candidates if path.suffix != ".part"), None)
    if archive is None:
        temporary = archive_dir / f"download_{record['node_id']}.part"
        download_url(record["archive_url"], temporary)
        signature = file_signature(temporary)
        if signature.startswith(b"PK\x03\x04"):
            archive = temporary.with_suffix(".zip")
        elif signature == b"%PDF":
            archive = temporary.with_suffix(".pdf")
        else:
            raise RuntimeError(f"unrecognised file format for node {record['node_id']}")
        temporary.replace(archive)
    else:
        signature = file_signature(archive)
        if signature == b"%PDF" and archive.suffix != ".pdf":
            corrected = archive.with_suffix(".pdf")
            archive.replace(corrected)
            archive = corrected

    record["archive_path"] = archive.relative_to(archive_dir.parent).as_posix()
    record["archive_bytes"] = str(archive.stat().st_size)
    record["sha256"] = sha256(archive)

    if archive.suffix == ".zip":
        destination = document_dir / record["node_id"]
        if not destination.exists():
            destination.mkdir(parents=True)
            with zipfile.ZipFile(archive) as package:
                package.extractall(destination)
        record["document_path"] = destination.relative_to(document_dir.parent).as_posix()
    else:
        record["document_path"] = record["archive_path"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog-only", action="store_true", help="do not download archives")
    args = parser.parse_args()

    repository = Path(__file__).resolve().parents[1]
    reference_dir = repository / "reference" / "eurocontrol"
    archive_dir = reference_dir / "archives"
    document_dir = reference_dir / "documents"
    archive_dir.mkdir(parents=True, exist_ok=True)
    document_dir.mkdir(parents=True, exist_ok=True)

    try:
        records = discover()
        if not records:
            raise RuntimeError("the catalogue returned no publications")
        records.sort(key=lambda item: (item["title"].casefold(), item["node_id"]))
        if not args.catalog_only:
            for index, record in enumerate(records, 1):
                print(f"[{index:02}/{len(records):02}] {record['title']}", flush=True)
                download(record, archive_dir, document_dir)
    except (
        OSError,
        subprocess.CalledProcessError,
        urllib.error.URLError,
        zipfile.BadZipFile,
        RuntimeError,
    ) as error:
        print(f"sync failed: {error}", file=sys.stderr)
        return 1

    catalog = {
        "source": search_url(),
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "publication_count": len(records),
        "publications": records,
    }
    catalog_path = reference_dir / "catalog.json"
    catalog_path.write_text(
        json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"Wrote {len(records)} entries to {catalog_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
