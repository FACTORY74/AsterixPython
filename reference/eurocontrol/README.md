# EUROCONTROL ASTERIX references

Source: [EUROCONTROL library search](https://www.eurocontrol.int/library/search?keywords=asterix&sort_by=search_api_relevance&f%5B0%5D=topic%3A973)

Run the synchroniser from the repository root:

```powershell
uv run --python 3.15 python tools/sync_eurocontrol_references.py
```

This refreshes `catalog.json` and downloads each publication archive into
`archives/`. Archives are extracted into `documents/<node-id>/`. Existing
archives with a matching size are retained; use `--catalog-only` to refresh
metadata without downloading files.

The catalogue and script are intended to be version controlled. Downloaded and
extracted files are ignored because they are large and reproducible. Every
catalogue entry records its source page and archive URL, and downloaded entries
also receive a SHA-256 checksum.

EUROCONTROL remains the authoritative source. Check the source page for newer
editions before relying on a local copy.

