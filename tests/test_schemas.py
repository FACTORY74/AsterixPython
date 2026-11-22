from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from asterix import DecodeContext, EncodeContext, SchemaRegistry, decode_message, encode_record


def _item(node: Mapping[str, Any]) -> Mapping[str, Any]:
    return node["contents"] if node.get("tag") == "Item" else node


def _zero(node: Mapping[str, Any] | None) -> Any:
    if node is None:
        return None
    tag = node.get("tag")
    contents = node.get("contents")
    if tag == "ContextFree":
        return _zero(contents)
    if tag == "Dependent":
        return _zero(contents["default"])
    if tag == "Item":
        item = _item(node)
        return {str(item["name"]): _zero(item["rule"])}
    if tag == "Element":
        return 0
    if tag == "Spare":
        return None
    if tag == "Group":
        result: dict[str, Any] = {}
        for child in contents:
            if child is None or child.get("tag") == "Spare":
                continue
            item = _item(child)
            result[str(item["name"])] = _zero(item["rule"])
        return result
    if tag == "Extended":
        result: dict[str, Any] = {}
        for child in contents:
            if child is None:
                break
            if child.get("tag") == "Spare":
                continue
            item = _item(child)
            result[str(item["name"])] = _zero(item["rule"])
        return [result]
    if tag == "Explicit":
        return b""
    if tag == "Repetitive":
        return []
    if tag == "Compound":
        for child in contents:
            if child is not None:
                item = _item(child)
                return {str(item["name"]): _zero(item["rule"])}
        raise AssertionError("empty compound")
    raise AssertionError(f"no zero-value builder for {tag}")


@pytest.fixture(scope="module")
def registry() -> SchemaRegistry:
    return SchemaRegistry.builtin()


def test_manifest_has_all_packaged_definitions(registry: SchemaRegistry) -> None:
    assert len(registry.keys("cat")) == 68
    assert len(registry.keys("ref")) == 7
    assert len({key.category for key in registry.keys("cat")}) == 27


def test_every_definition_loads_and_references_valid_uap_items(registry: SchemaRegistry) -> None:
    for key in registry.keys("cat"):
        schema = registry.get(key.category, key.edition)
        for profile in schema.uap_names:
            _, entries = schema.uap(profile)
            for entry in entries:
                if entry.get("tag") != "UapItem":
                    continue
                name = str(entry["contents"])
                assert name in schema.catalogue or name in {"SP", "SPF", "RE", "REF"}


def test_each_uap_item_zero_round_trip(registry: SchemaRegistry) -> None:
    for key in registry.keys("cat"):
        schema = registry.get(key.category, key.edition)
        for profile in schema.uap_names:
            _, entries = schema.uap(profile)
            for entry in entries:
                if entry.get("tag") != "UapItem":
                    continue
                name = str(entry["contents"])
                if name in {"SP", "SPF", "RE", "REF"}:
                    value: Any = b""
                else:
                    value = _zero(schema.catalogue[name]["rule"])
                wire = encode_record(
                    category=key.category,
                    edition=key.edition,
                    items={name: value},
                    registry=registry,
                    context=EncodeContext(validation="inspect"),
                    uap=profile,
                )
                message = decode_message(
                    wire,
                    registry=registry,
                    context=DecodeContext(
                        editions={key.category: key.edition},
                        uaps={key.category: profile},
                        validation="inspect",
                    ),
                )
                assert message.category == key.category
                assert message.edition == key.edition
                assert len(message.records) == 1
