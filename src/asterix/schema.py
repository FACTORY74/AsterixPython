"""Runtime access to immutable structured ASTERIX definitions."""

from __future__ import annotations

import gzip
import hashlib
import json
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from types import MappingProxyType
from typing import Any

from .errors import EditionResolutionError, SchemaError, SchemaNotFoundError, UapResolutionError


def _deep_freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _deep_freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_deep_freeze(item) for item in value)
    return value


@dataclass(frozen=True, slots=True)
class SchemaKey:
    kind: str
    category: int
    edition: str


@dataclass(frozen=True, slots=True)
class CategorySchema:
    key: SchemaKey
    title: str
    date: tuple[int, int, int] | None
    catalogue: Mapping[str, Mapping[str, Any]]
    uap_definition: Mapping[str, Any]
    raw: Mapping[str, Any]

    @property
    def uap_names(self) -> tuple[str, ...]:
        tag = self.uap_definition.get("tag")
        if tag == "Uap":
            return ("standard",)
        if tag == "Uaps":
            return tuple(str(case[0]) for case in self.uap_definition["contents"]["cases"])
        raise SchemaError(f"unsupported UAP tag {tag!r}")

    def uap(self, name: str | None = None) -> tuple[str, tuple[Mapping[str, Any], ...]]:
        tag = self.uap_definition.get("tag")
        if tag == "Uap":
            if name not in (None, "standard"):
                raise UapResolutionError(f"category {self.key.category:03d} has only standard UAP")
            return "standard", tuple(self.uap_definition["contents"])
        if tag != "Uaps":
            raise SchemaError(f"unsupported UAP tag {tag!r}")
        cases = {str(key): tuple(items) for key, items in self.uap_definition["contents"]["cases"]}
        if name is None:
            raise UapResolutionError(
                f"category {self.key.category:03d} edition {self.key.edition} requires one of "
                f"{', '.join(cases)}"
            )
        try:
            return name, cases[name]
        except KeyError as error:
            raise UapResolutionError(
                f"unknown UAP {name!r}; expected one of {', '.join(cases)}"
            ) from error


class SchemaRegistry:
    """Read-only registry of packaged category and REF definitions."""

    def __init__(self, manifest: Mapping[str, Any], root: Path | Any) -> None:
        self._manifest = MappingProxyType(dict(manifest))
        self._root = root
        self._entries = {
            SchemaKey(str(item["kind"]), int(item["category"]), str(item["edition"])): dict(item)
            for item in manifest["definitions"]
        }
        self._cache: dict[SchemaKey, CategorySchema] = {}
        self._cache_lock = threading.RLock()

    @classmethod
    def builtin(cls) -> SchemaRegistry:
        root = files("asterix").joinpath("schemas")
        manifest = json.loads(root.joinpath("manifest.json").read_text(encoding="utf-8"))
        return cls(manifest, root)

    @property
    def revision(self) -> str:
        return str(self._manifest["revision"])

    def keys(self, kind: str | None = None) -> tuple[SchemaKey, ...]:
        return tuple(
            sorted(
                (key for key in self._entries if kind is None or key.kind == kind),
                key=lambda key: (
                    key.category,
                    key.kind,
                    tuple(int(x) for x in key.edition.split(".")),
                ),
            )
        )

    def editions(self, category: int, kind: str = "cat") -> tuple[str, ...]:
        return tuple(key.edition for key in self.keys(kind) if key.category == category)

    def resolve_edition(self, category: int, edition: str | None, kind: str = "cat") -> str:
        available = self.editions(category, kind)
        if not available:
            raise SchemaNotFoundError(f"no {kind} definitions for category {category:03d}")
        if edition is None:
            if len(available) != 1:
                raise EditionResolutionError(
                    f"category {category:03d} requires explicit edition; "
                    f"available: {', '.join(available)}"
                )
            return available[0]
        if edition not in available:
            raise SchemaNotFoundError(
                f"category {category:03d} has no {kind} edition {edition}; "
                f"available: {', '.join(available)}"
            )
        return edition

    def get(self, category: int, edition: str | None, kind: str = "cat") -> CategorySchema:
        selected = self.resolve_edition(category, edition, kind)
        key = SchemaKey(kind, category, selected)
        with self._cache_lock:
            cached = self._cache.get(key)
            if cached is not None:
                return cached
            entry = self._entries[key]
            compressed = self._root.joinpath(str(entry["path"])).read_bytes()
            raw_bytes = gzip.decompress(compressed)
            if hashlib.sha256(raw_bytes).hexdigest() != entry["sha256"]:
                raise SchemaError(f"schema checksum mismatch for {key}")
            document = _deep_freeze(json.loads(raw_bytes))
            if document.get("tag") not in ("AsterixBasic", "AsterixExpansion"):
                raise SchemaError(f"unsupported root tag in {key}")
            contents = document["contents"]
            if kind == "ref":
                catalogue = MappingProxyType({})
                uap = _deep_freeze({"tag": "Uap", "contents": contents.get("items", ())})
            else:
                catalogue = MappingProxyType(
                    {str(item["name"]): item for item in contents["catalogue"]}
                )
                uap = contents.get("uap")
            schema = CategorySchema(
                key=key,
                title=str(contents.get("title", "")),
                date=(
                    int(contents["date"]["year"]),
                    int(contents["date"]["month"]),
                    int(contents["date"]["day"]),
                )
                if contents.get("date")
                else None,
                catalogue=catalogue,
                uap_definition=uap,
                raw=document,
            )
            self._cache[key] = schema
            return schema
