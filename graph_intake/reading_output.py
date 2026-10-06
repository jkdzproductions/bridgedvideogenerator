"""Parse and strictly validate the graph-reading subagent's JSON answer."""
import json
import re

_FENCE_PATTERN = re.compile(r"^```(?:json)?\s*\n(.*)\n```\s*$", re.DOTALL)
READING_KEYS = {"title", "subtitle", "graph_kind", "unit", "source_line", "values", "notes"}
VALUE_KEYS = {"label", "display", "value", "readable"}
_TEXT_KEYS = ("title", "subtitle", "graph_kind", "unit", "source_line", "notes")


class GraphReadingError(ValueError):
    """The reading is malformed or has nothing usable; the message names the italic phrase."""


def _strip_code_fence(raw: str) -> str:
    match = _FENCE_PATTERN.match(raw.strip())
    return match.group(1) if match else raw


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def parse_reading_output(raw: str, italic_text: str) -> dict:
    where = f"graph reading for {italic_text!r}"
    try:
        payload = json.loads(_strip_code_fence(raw))
    except json.JSONDecodeError as e:
        raise GraphReadingError(f"{where}: not valid JSON: {e}") from e
    if not isinstance(payload, dict):
        raise GraphReadingError(f"{where}: must be a JSON object, got {type(payload).__name__}")
    if set(payload) != READING_KEYS:
        raise GraphReadingError(
            f"{where}: keys must be exactly {sorted(READING_KEYS)}; missing "
            f"{sorted(READING_KEYS - set(payload))}, unexpected {sorted(set(payload) - READING_KEYS)}")
    for key in _TEXT_KEYS:
        if payload[key] is not None and not isinstance(payload[key], str):
            raise GraphReadingError(f"{where}: {key!r} must be a string or null")

    values = payload["values"]
    if not isinstance(values, list):
        raise GraphReadingError(f"{where}: 'values' must be a list")
    for i, item in enumerate(values):
        if not isinstance(item, dict) or set(item) != VALUE_KEYS:
            raise GraphReadingError(
                f"{where}: values[{i}] must be an object with exactly the keys {sorted(VALUE_KEYS)}")
        if not isinstance(item["label"], str) or not item["label"].strip():
            raise GraphReadingError(f"{where}: values[{i}] has an empty label")
        if not isinstance(item["display"], str):
            raise GraphReadingError(f"{where}: values[{i}] ({item['label']!r}) display must be a string")
        if not isinstance(item["readable"], bool):
            raise GraphReadingError(f"{where}: values[{i}] ({item['label']!r}) readable must be true/false")
        if item["value"] is not None and not _is_number(item["value"]):
            raise GraphReadingError(
                f"{where}: values[{i}] ({item['label']!r}) value must be a number or null, "
                f"got {item['value']!r}")
        if item["readable"] and (item["value"] is None or not item["display"].strip()):
            raise GraphReadingError(
                f"{where}: values[{i}] ({item['label']!r}) is marked readable but has no "
                "number or no printed display")

    if not any(item["readable"] for item in values):
        raise GraphReadingError(
            f"{where}: zero readable values were read from the image — nothing to build the "
            "graphic from; check the image link")
    return payload
