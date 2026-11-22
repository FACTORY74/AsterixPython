"""Generic interpreter for structured ASTERIX category definitions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from .context import DecodeContext, EncodeContext, ValidationMode
from .cursor import BitCursor, BitWriter, ByteCursor
from .errors import DecodeError, Diagnostic, EncodeError, SchemaError, Severity, ValidationError
from .framing import MessageFramer, split_messages
from .model import AsterixMessage, DataItem, DataRecord, ElementValue, UnknownTail
from .schema import CategorySchema, SchemaRegistry


def _unwrap_item(node: Mapping[str, Any]) -> Mapping[str, Any]:
    return node.get("contents", node) if node.get("tag") == "Item" else node


def _numeric(node: Mapping[str, Any]) -> Fraction:
    tag = node["tag"]
    contents = node["contents"]
    if tag == "NumInt":
        return Fraction(int(contents), 1)
    if tag == "NumPow":
        return Fraction(int(contents["base"])) ** int(contents["exponent"])
    if tag == "NumDiv":
        return _numeric(contents["numerator"]) / _numeric(contents["denominator"])
    raise SchemaError(f"unsupported numeric tag {tag!r}")


def _signed(raw: int, bits: int, signedness: Mapping[str, Any]) -> int:
    if signedness.get("tag") != "Signed":
        return raw
    sign = 1 << (bits - 1)
    return raw - (1 << bits) if raw & sign else raw


def _icao_character(code: int) -> str:
    if 1 <= code <= 26:
        return chr(ord("A") + code - 1)
    if code == 32:
        return " "
    if 48 <= code <= 57:
        return chr(code)
    return "#"


def _content_value(node: Mapping[str, Any], raw: int, bits: int) -> ElementValue:
    tag = node["tag"]
    contents = node.get("contents")
    if tag == "ContentRaw":
        return ElementValue(raw=raw, value=raw)
    if tag == "ContentTable":
        table = {int(key): str(label) for key, label in contents}
        return ElementValue(raw=raw, value=raw, label=table.get(raw))
    if tag == "ContentInteger":
        value = _signed(raw, bits, contents["signedness"])
        return ElementValue(raw=raw, value=value)
    if tag == "ContentQuantity":
        integer = _signed(raw, bits, contents["signedness"])
        value = integer * _numeric(contents["lsb"])
        return ElementValue(raw=raw, value=value, unit=contents.get("unit"))
    if tag == "ContentString":
        string_tag = contents["tag"]
        if string_tag == "StringAscii":
            size = (bits + 7) // 8
            value = raw.to_bytes(size, "big").decode("ascii", errors="replace").rstrip("\x00 ")
        elif string_tag == "StringICAO":
            chars = [_icao_character((raw >> shift) & 0x3F) for shift in range(bits - 6, -1, -6)]
            value = "".join(chars).rstrip()
        elif string_tag == "StringOctal":
            value = format(raw, f"0{(bits + 2) // 3}o")
        else:
            raise SchemaError(f"unsupported string tag {string_tag!r}")
        return ElementValue(raw=raw, value=value)
    if tag in ("ContentBds", "BdsAt", "BdsWithAddress"):
        return ElementValue(raw=raw, value=raw.to_bytes((bits + 7) // 8, "big"))
    raise SchemaError(f"unsupported content tag {tag!r}")


def _static_bits(node: Mapping[str, Any] | None) -> int:
    if node is None:
        return 1
    tag = node.get("tag")
    contents = node.get("contents")
    if tag == "ContextFree":
        return _static_bits(contents)
    if tag == "Item":
        return _static_bits(contents["rule"])
    if tag == "Element":
        return int(contents["bitSize"])
    if tag == "Spare":
        return int(contents)
    if tag == "Group":
        return sum(_static_bits(child) for child in contents)
    raise SchemaError(f"{tag!r} is not fixed length")


@dataclass(slots=True)
class _RecordState:
    values: dict[tuple[str, ...], ElementValue]
    diagnostics: list[Diagnostic]
    category: int
    edition: str


class _VariationDecoder:
    def __init__(
        self,
        context: DecodeContext,
        registry: SchemaRegistry,
        category: int,
        edition: str,
    ) -> None:
        self.context = context
        self.registry = registry
        self.category = category
        self.edition = edition

    def decode(
        self,
        node: Mapping[str, Any],
        cursor: ByteCursor,
        state: _RecordState,
        path: tuple[str, ...],
    ) -> Any:
        tag = node.get("tag")
        if tag == "ContextFree":
            return self.decode(node["contents"], cursor, state, path)
        if tag == "Group" or tag == "Element":
            size = _static_bits(node)
            if size % 8:
                raise SchemaError(f"top-level fixed item at {path} is not octet aligned")
            raw = cursor.take(size // 8)
            return self._decode_bits(node, BitCursor(raw), state, path)
        if tag == "Extended":
            return self._decode_extended(node, cursor, state, path)
        if tag == "Explicit":
            return self._decode_explicit(node, cursor, state, path)
        if tag == "Repetitive":
            return self._decode_repetitive(node, cursor, state, path)
        if tag == "Compound":
            return self._decode_compound(node, cursor, state, path)
        raise SchemaError(f"unsupported variation tag {tag!r} at {'/'.join(path)}")

    def _decode_bits(
        self,
        node: Mapping[str, Any] | None,
        bits: BitCursor,
        state: _RecordState,
        path: tuple[str, ...],
    ) -> Any:
        if node is None:
            bits.read(1)
            return None
        tag = node.get("tag")
        contents = node.get("contents")
        if tag == "ContextFree":
            return self._decode_bits(contents, bits, state, path)
        if tag == "Dependent":
            selected = self._select_dependent(contents, state)
            return self._decode_bits(selected, bits, state, path)
        if tag == "Item":
            item = contents
            name = str(item["name"])
            value = self._decode_bits(item["rule"], bits, state, (*path, name))
            return name, value
        if tag == "Spare":
            raw = bits.read(int(contents))
            if raw:
                state.diagnostics.append(
                    Diagnostic(
                        "nonzero-spare",
                        f"spare bits at {'/'.join(path)} are non-zero",
                        Severity.WARNING,
                        category=state.category,
                        edition=state.edition,
                    )
                )
            return None
        if tag == "Group":
            result: dict[str, Any] = {}
            for child in contents:
                decoded = self._decode_bits(child, bits, state, path)
                if isinstance(decoded, tuple) and len(decoded) == 2:
                    result[decoded[0]] = decoded[1]
            return result
        if tag == "Element":
            size = int(contents["bitSize"])
            raw = bits.read(size)
            rule = contents["rule"]
            if rule.get("tag") == "ContextFree":
                rule = rule["contents"]
            elif rule.get("tag") == "Dependent":
                rule = self._select_dependent(rule["contents"], state)
            value = _content_value(rule, raw, size)
            state.values[path] = value
            return value
        raise SchemaError(f"unsupported fixed-layout tag {tag!r} at {'/'.join(path)}")

    def _select_dependent(
        self, contents: Mapping[str, Any], state: _RecordState
    ) -> Mapping[str, Any]:
        values: list[int] = []
        for alternatives in contents["path"]:
            key = tuple(str(part) for part in alternatives)
            found = state.values.get(key)
            if found is None:
                found = next(
                    (value for path, value in state.values.items() if path[-len(key) :] == key),
                    None,
                )
            if found is None or not isinstance(found.raw, int):
                return contents["default"]
            values.append(found.raw)
        for expected, rule in contents["cases"]:
            if [int(value) for value in expected] == values:
                return rule
        return contents["default"]

    def _decode_extended(
        self,
        node: Mapping[str, Any],
        cursor: ByteCursor,
        state: _RecordState,
        path: tuple[str, ...],
    ) -> list[dict[str, Any]]:
        entries = node["contents"]
        segments: list[list[Mapping[str, Any] | None]] = []
        current: list[Mapping[str, Any] | None] = []
        for entry in entries:
            current.append(entry)
            if entry is None:
                segments.append(current)
                current = []
        if current:
            segments.append(current)
        result: list[dict[str, Any]] = []
        extension = True
        index = 0
        while extension:
            if index >= self.context.limits.max_fx_octets:
                raise DecodeError("extended item exceeds FX limit")
            segment = segments[index] if index < len(segments) else None
            segment_size = (
                1 if segment is None else sum(_static_bits(child) for child in segment) // 8
            )
            if segment is not None and sum(_static_bits(child) for child in segment) % 8:
                raise SchemaError(f"extended segment at {'/'.join(path)} is not octet aligned")
            octets = cursor.take(segment_size)
            extension = bool(octets[-1] & 1)
            if segment is None:
                result.append({"_unknown_extension": octets})
            else:
                bit_cursor = BitCursor(octets)
                decoded: dict[str, Any] = {}
                for child in segment:
                    if child is None:
                        bit_cursor.read(1)
                        continue
                    value = self._decode_bits(child, bit_cursor, state, path)
                    if isinstance(value, tuple):
                        decoded[value[0]] = value[1]
                result.append(decoded)
            index += 1
        return result

    def _decode_explicit(
        self,
        node: Mapping[str, Any],
        cursor: ByteCursor,
        state: _RecordState,
        path: tuple[str, ...],
    ) -> Any:
        length = cursor.u8()
        if length < 1:
            raise DecodeError("explicit item length is zero")
        body = cursor.take_cursor(length - 1)
        inner = node.get("contents")
        if inner is None:
            return {"length": length, "data": body.take(body.remaining)}
        if inner.get("tag") == "SpecialPurpose":
            return {"length": length, "data": body.take(body.remaining)}
        if inner.get("tag") == "ReservedExpansion":
            ref_edition = self.context.ref_editions.get(self.category)
            if ref_edition is None:
                return {"length": length, "data": body.take(body.remaining), "decoded": False}
            schema = self.registry.get(self.category, ref_edition, "ref")
            return self._decode_expansion(schema, body, state, path)
        return {"length": length, "data": body.take(body.remaining)}

    def _decode_expansion(
        self, schema: CategorySchema, cursor: ByteCursor, state: _RecordState, path: tuple[str, ...]
    ) -> dict[str, Any]:
        contents = schema.raw["contents"]
        fspec_size = int(contents["fspecByteSize"])
        fspec = cursor.take(fspec_size)
        present: list[int] = []
        for octet_index, octet in enumerate(fspec):
            for bit in range(7):
                if octet & (0x80 >> bit):
                    present.append(octet_index * 7 + bit + 1)
        values: dict[str, Any] = {}
        items = contents["items"]
        for frn in present:
            if frn > len(items):
                values["_unknown_tail"] = cursor.take(cursor.remaining)
                break
            item = items[frn - 1]
            if item is None:
                continue
            item = _unwrap_item(item)
            name = str(item["name"])
            values[name] = self.decode(item["rule"], cursor, state, (*path, name))
        if cursor.remaining:
            values["_trailing"] = cursor.take(cursor.remaining)
        return {"edition": schema.key.edition, "fspec": fspec, "items": values}

    def _decode_repetitive(
        self,
        node: Mapping[str, Any],
        cursor: ByteCursor,
        state: _RecordState,
        path: tuple[str, ...],
    ) -> list[Any]:
        contents = node["contents"]
        repeat_type = contents["type"]
        if repeat_type["tag"] == "RepetitiveRegular":
            count = cursor.uint(int(repeat_type["contents"]["byteSize"]))
        elif repeat_type["tag"] == "RepetitiveFx":
            count = 0
            for _ in range(self.context.limits.max_fx_octets):
                octet = cursor.u8()
                count = (count << 7) | (octet >> 1)
                if not octet & 1:
                    break
            else:
                raise DecodeError("unterminated FX repetition indicator")
        else:
            raise SchemaError(f"unsupported repetition type {repeat_type['tag']!r}")
        if count > self.context.limits.max_repetitions:
            raise DecodeError(f"repetition count {count} exceeds limit")
        return [
            self.decode(contents["variation"], cursor, state, (*path, str(index)))
            for index in range(count)
        ]

    def _decode_compound(
        self,
        node: Mapping[str, Any],
        cursor: ByteCursor,
        state: _RecordState,
        path: tuple[str, ...],
    ) -> dict[str, Any]:
        fspec, present = _read_fspec(cursor, self.context.limits.max_fspec_octets)
        children = node["contents"]
        values: dict[str, Any] = {"_fspec": fspec}
        for frn in present:
            if frn > len(children):
                raise DecodeError(f"unknown compound subitem {frn} at {'/'.join(path)}")
            child = children[frn - 1]
            if child is None:
                state.diagnostics.append(
                    Diagnostic(
                        "compound-spare", f"compound spare subitem {frn} is set", Severity.WARNING
                    )
                )
                continue
            child = _unwrap_item(child)
            name = str(child["name"])
            values[name] = self.decode(child["rule"], cursor, state, (*path, name))
        return values


def _mapping_value(values: Mapping[str, Any], name: str) -> Any:
    if name in values:
        return values[name]
    folded = name.casefold()
    for key, value in values.items():
        if str(key).casefold() == folded:
            return value
    raise EncodeError(f"missing value for element {name}")


def _unsigned_value(value: Any, rule: Mapping[str, Any], bits: int) -> int:
    if isinstance(value, Mapping) and len(value) == 1:
        value = next(iter(value.values()))
    if isinstance(value, ElementValue):
        return int(value.raw)
    tag = rule["tag"]
    contents = rule.get("contents")
    if tag in ("ContentRaw", "ContentBds", "BdsAt", "BdsWithAddress"):
        if isinstance(value, bytes):
            return int.from_bytes(value, "big")
        return int(value)
    if tag == "ContentTable":
        if isinstance(value, str):
            matches = [int(raw) for raw, label in contents if str(label) == value]
            if len(matches) != 1:
                raise EncodeError(f"table label {value!r} is not unique or not defined")
            return matches[0]
        return int(value)
    if tag in ("ContentInteger", "ContentQuantity"):
        signedness = contents["signedness"]
        numeric = Fraction(value)
        if tag == "ContentQuantity":
            numeric /= _numeric(contents["lsb"])
        if numeric.denominator != 1:
            raise EncodeError(f"{value!r} is not exactly representable in {bits} bits")
        integer = int(numeric)
        if signedness.get("tag") == "Signed" and integer < 0:
            integer += 1 << bits
        return integer
    if tag == "ContentString":
        string_tag = contents["tag"]
        text = str(value)
        if string_tag == "StringAscii":
            return int.from_bytes(text.encode("ascii").ljust((bits + 7) // 8, b" "), "big")
        if string_tag == "StringOctal":
            return int(text, 8)
        if string_tag == "StringICAO":
            codes: list[int] = []
            for char in text.upper().ljust(bits // 6):
                if "A" <= char <= "Z":
                    codes.append(ord(char) - ord("A") + 1)
                elif "0" <= char <= "9" or char == " ":
                    codes.append(ord(char))
                else:
                    raise EncodeError(f"character {char!r} is not in the ASTERIX ICAO alphabet")
            raw = 0
            for code in codes[: bits // 6]:
                raw = (raw << 6) | code
            return raw
    raise EncodeError(f"cannot encode content tag {tag!r}")


class _VariationEncoder:
    def __init__(
        self,
        context: EncodeContext,
        registry: SchemaRegistry,
        category: int,
        edition: str,
    ) -> None:
        self.context = context
        self.registry = registry
        self.category = category
        self.edition = edition
        self.state = _RecordState({}, [], category, edition)

    def encode(self, node: Mapping[str, Any], value: Any, path: tuple[str, ...]) -> bytes:
        tag = node.get("tag")
        if tag == "ContextFree":
            return self.encode(node["contents"], value, path)
        if tag in ("Group", "Element"):
            writer = BitWriter()
            self._encode_bits(node, value, writer, path)
            return writer.bytes()
        if tag == "Extended":
            return self._encode_extended(node, value, path)
        if tag == "Explicit":
            return self._encode_explicit(node, value, path)
        if tag == "Repetitive":
            return self._encode_repetitive(node, value, path)
        if tag == "Compound":
            return self._encode_compound(node, value, path)
        raise EncodeError(f"unsupported variation tag {tag!r} at {'/'.join(path)}")

    def _encode_bits(
        self,
        node: Mapping[str, Any] | None,
        value: Any,
        writer: BitWriter,
        path: tuple[str, ...],
    ) -> None:
        if node is None:
            writer.write(0, 1)
            return
        tag = node.get("tag")
        contents = node.get("contents")
        if tag == "ContextFree":
            self._encode_bits(contents, value, writer, path)
            return
        if tag == "Dependent":
            selected = _VariationDecoder(
                DecodeContext(), self.registry, self.category, self.edition
            )._select_dependent(contents, self.state)
            self._encode_bits(selected, value, writer, path)
            return
        if tag == "Spare":
            writer.write(0, int(contents))
            return
        if tag == "Item":
            item = contents
            name = str(item["name"])
            child_value = _mapping_value(value, name)
            self._encode_bits(item["rule"], child_value, writer, (*path, name))
            return
        if tag == "Group":
            if not isinstance(value, Mapping):
                raise EncodeError(f"group {'/'.join(path)} requires a mapping")
            for child in contents:
                if child is None or child.get("tag") == "Spare":
                    self._encode_bits(child, None, writer, path)
                else:
                    self._encode_bits(child, value, writer, path)
            return
        if tag == "Element":
            size = int(contents["bitSize"])
            rule = contents["rule"]
            if rule.get("tag") == "ContextFree":
                rule = rule["contents"]
            elif rule.get("tag") == "Dependent":
                rule = _VariationDecoder(
                    DecodeContext(), self.registry, self.category, self.edition
                )._select_dependent(rule["contents"], self.state)
            raw = _unsigned_value(value, rule, size)
            if raw < 0 or raw >= 1 << size:
                raise EncodeError(f"value {value!r} does not fit {size} bits at {'/'.join(path)}")
            writer.write(raw, size)
            decoded = _content_value(rule, raw, size)
            self.state.values[path] = decoded
            return
        raise EncodeError(f"unsupported fixed-layout tag {tag!r} at {'/'.join(path)}")

    def _encode_extended(self, node: Mapping[str, Any], value: Any, path: tuple[str, ...]) -> bytes:
        values = value if isinstance(value, list) else [value]
        entries = node["contents"]
        segments: list[list[Mapping[str, Any] | None]] = []
        current: list[Mapping[str, Any] | None] = []
        for entry in entries:
            current.append(entry)
            if entry is None:
                segments.append(current)
                current = []
        if current:
            segments.append(current)
        if len(values) > self.context.limits.max_fx_octets:
            raise EncodeError("extended item exceeds FX limit")
        output = bytearray()
        for index, segment_value in enumerate(values):
            if index >= len(segments):
                if isinstance(segment_value, Mapping) and "_unknown_extension" in segment_value:
                    octets = bytearray(segment_value["_unknown_extension"])
                    octets[-1] = (octets[-1] & 0xFE) | (index < len(values) - 1)
                    output.extend(octets)
                    continue
                raise EncodeError(f"schema has no extension {index + 1} at {'/'.join(path)}")
            writer = BitWriter()
            for child in segments[index]:
                if child is None:
                    writer.write(1 if index < len(values) - 1 else 0, 1)
                elif child.get("tag") == "Spare":
                    self._encode_bits(child, None, writer, path)
                else:
                    self._encode_bits(child, segment_value, writer, path)
            output.extend(writer.bytes())
        return bytes(output)

    def _encode_explicit(self, node: Mapping[str, Any], value: Any, path: tuple[str, ...]) -> bytes:
        if isinstance(value, Mapping):
            body = bytes(value.get("data", b""))
        else:
            body = bytes(value)
        length = len(body) + 1
        if length > 255:
            raise EncodeError("explicit item exceeds one-octet length")
        return bytes([length]) + body

    def _encode_repetitive(
        self, node: Mapping[str, Any], value: Any, path: tuple[str, ...]
    ) -> bytes:
        values = list(value)
        if len(values) > self.context.limits.max_repetitions:
            raise EncodeError("repetition count exceeds limit")
        contents = node["contents"]
        repeat_type = contents["type"]
        if repeat_type["tag"] == "RepetitiveRegular":
            size = int(repeat_type["contents"]["byteSize"])
            try:
                prefix = len(values).to_bytes(size, "big")
            except OverflowError as error:
                raise EncodeError("repetition count does not fit REP field") from error
        elif repeat_type["tag"] == "RepetitiveFx":
            chunks = [len(values) & 0x7F]
            remaining = len(values) >> 7
            while remaining:
                chunks.append(remaining & 0x7F)
                remaining >>= 7
            prefix = bytes(
                (chunk << 1) | (index > 0) for index, chunk in enumerate(reversed(chunks))
            )
        else:
            raise EncodeError(f"unsupported repetition type {repeat_type['tag']!r}")
        return prefix + b"".join(
            self.encode(contents["variation"], item, (*path, str(index)))
            for index, item in enumerate(values)
        )

    def _encode_compound(self, node: Mapping[str, Any], value: Any, path: tuple[str, ...]) -> bytes:
        if not isinstance(value, Mapping):
            raise EncodeError(f"compound {'/'.join(path)} requires a mapping")
        children = node["contents"]
        selected: list[tuple[int, Mapping[str, Any], Any]] = []
        for frn, child in enumerate(children, 1):
            if child is None:
                continue
            item = _unwrap_item(child)
            name = str(item["name"])
            try:
                child_value = _mapping_value(value, name)
            except EncodeError:
                continue
            selected.append((frn, item, child_value))
        if not selected:
            raise EncodeError(f"compound {'/'.join(path)} has no populated subitems")
        fspec = _encode_fspec([frn for frn, _, _ in selected])
        return fspec + b"".join(
            self.encode(item["rule"], child_value, (*path, str(item["name"])))
            for _, item, child_value in selected
        )


def _encode_fspec(frns: list[int]) -> bytes:
    if not frns:
        return b"\x00"
    octets = (max(frns) + 6) // 7
    output = bytearray(octets)
    for frn in frns:
        output[(frn - 1) // 7] |= 0x80 >> ((frn - 1) % 7)
    for index in range(octets - 1):
        output[index] |= 1
    return bytes(output)


def encode_record(
    *,
    category: int,
    edition: str,
    items: Mapping[str, Any],
    registry: SchemaRegistry | None = None,
    context: EncodeContext | None = None,
    uap: str | None = None,
) -> bytes:
    registry = registry or SchemaRegistry.builtin()
    context = context or EncodeContext()
    schema = registry.get(category, edition)
    _, entries = schema.uap(uap)
    by_name: dict[str, tuple[int, Mapping[str, Any]]] = {}
    for frn, entry in enumerate(entries, 1):
        if entry.get("tag") == "UapItem":
            by_name[str(entry["contents"])] = (frn, entry)
    selected: list[tuple[int, str, Any]] = []
    for supplied_name, value in items.items():
        name = str(supplied_name).split("/")[-1]
        if name not in by_name:
            raise EncodeError(f"item {supplied_name!r} is not in the selected UAP")
        selected.append((by_name[name][0], name, value))
    selected.sort()
    encoder = _VariationEncoder(context, registry, category, edition)
    payload = bytearray(_encode_fspec([frn for frn, _, _ in selected]))
    for _frn, name, value in selected:
        if name in ("SP", "SPF"):
            node = {"tag": "Explicit", "contents": {"tag": "SpecialPurpose", "contents": []}}
        elif name in ("RE", "REF"):
            node = {"tag": "Explicit", "contents": {"tag": "ReservedExpansion", "contents": []}}
        else:
            node = schema.catalogue[name]["rule"]
        payload.extend(encoder.encode(node, value, (name,)))
    length = len(payload) + 3
    if length > context.limits.max_message_bytes:
        raise EncodeError(f"encoded message is {length} bytes, above configured limit")
    return bytes([category]) + length.to_bytes(2, "big") + bytes(payload)


def _read_fspec(cursor: ByteCursor, limit: int) -> tuple[bytes, tuple[int, ...]]:
    fspec = bytearray()
    present: list[int] = []
    for octet_index in range(limit):
        octet = cursor.u8()
        fspec.append(octet)
        for bit in range(7):
            if octet & (0x80 >> bit):
                present.append(octet_index * 7 + bit + 1)
        if not octet & 1:
            return bytes(fspec), tuple(present)
    raise DecodeError(f"FSPEC exceeds {limit} octets")


def decode_message(
    data: bytes | bytearray | memoryview,
    *,
    context: DecodeContext,
    registry: SchemaRegistry | None = None,
) -> AsterixMessage:
    registry = registry or SchemaRegistry.builtin()
    raw = bytes(data)
    if len(raw) < 3:
        raise DecodeError("ASTERIX message is shorter than CAT/LEN")
    if len(raw) > context.limits.max_message_bytes:
        raise DecodeError(
            f"ASTERIX message is {len(raw)} bytes, above configured limit "
            f"{context.limits.max_message_bytes}"
        )
    category = raw[0]
    length = int.from_bytes(raw[1:3], "big")
    if length != len(raw):
        raise DecodeError(f"LEN declares {length} bytes but buffer contains {len(raw)}")
    edition = registry.resolve_edition(category, context.editions.get(category))
    schema = registry.get(category, edition)
    uap_name, uap = schema.uap(context.uaps.get(category))
    cursor = ByteCursor.from_bytes(raw[3:])
    variation = _VariationDecoder(context, registry, category, edition)
    records: list[DataRecord] = []
    diagnostics: list[Diagnostic] = []
    while cursor.remaining:
        if len(records) >= context.limits.max_records_per_block:
            raise DecodeError("record count exceeds configured limit")
        start = cursor.pos
        fspec, present = _read_fspec(cursor, context.limits.max_fspec_octets)
        state = _RecordState({}, diagnostics, category, edition)
        items: list[DataItem] = []
        unknown_tail: UnknownTail | None = None
        for frn in present:
            if frn > len(uap):
                unknown_tail = UnknownTail(cursor.take(cursor.remaining), f"FRN {frn} exceeds UAP")
                break
            entry = uap[frn - 1]
            entry_tag = entry.get("tag")
            if entry_tag != "UapItem":
                message = f"FRN {frn} maps to {entry_tag}"
                if context.validation is ValidationMode.STRICT:
                    raise ValidationError(message)
                diagnostics.append(
                    Diagnostic(
                        "uap-spare",
                        message,
                        Severity.WARNING,
                        category=category,
                        edition=edition,
                        frn=frn,
                    )
                )
                continue
            name = str(entry["contents"])
            item_start = cursor.pos
            if name in ("SP", "SPF"):
                node = {"tag": "Explicit", "contents": {"tag": "SpecialPurpose", "contents": []}}
                title = "Special Purpose Field"
            elif name in ("RE", "REF"):
                node = {"tag": "Explicit", "contents": {"tag": "ReservedExpansion", "contents": []}}
                title = "Reserved Expansion Field"
            else:
                try:
                    definition = schema.catalogue[name]
                except KeyError as error:
                    raise SchemaError(f"UAP references missing item {name}") from error
                node = definition["rule"]
                title = str(definition.get("title", ""))
            value = variation.decode(node, cursor, state, (name,))
            items.append(
                DataItem(
                    frn=frn,
                    item_id=f"I{category:03d}/{name}",
                    name=title,
                    value=value,
                    raw=bytes(cursor.data[item_start : cursor.pos]),
                )
            )
        records.append(
            DataRecord(
                fields=tuple(items),
                fspec=fspec,
                raw=bytes(cursor.data[start : cursor.pos]),
                unknown_tail=unknown_tail,
            )
        )
        if unknown_tail is not None:
            break
    return AsterixMessage(
        category=category,
        edition=edition,
        records=tuple(records),
        raw=raw,
        ref_edition=context.ref_editions.get(category),
        uap=uap_name,
        diagnostics=tuple(diagnostics),
    )


class Decoder:
    def __init__(self, *, registry: SchemaRegistry | None = None, context: DecodeContext) -> None:
        self.registry = registry or SchemaRegistry.builtin()
        self.context = context
        self._framer = MessageFramer(context.limits)

    def feed(self, chunk: bytes | bytearray | memoryview) -> tuple[AsterixMessage, ...]:
        return tuple(
            decode_message(message, context=self.context, registry=self.registry)
            for message in self._framer.feed(chunk)
        )

    def decode_datagram(
        self, payload: bytes | bytearray | memoryview
    ) -> tuple[AsterixMessage, ...]:
        return tuple(
            decode_message(message, context=self.context, registry=self.registry)
            for message in split_messages(payload, self.context.limits)
        )

    def finish(self) -> None:
        self._framer.finish()
