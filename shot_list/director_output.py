import json
import re

from shot_list.models import ARCHETYPES
from shot_list.segments import Segment, map_readings_to_segments


class DirectorOutputError(ValueError):
    pass


# Opus often wraps a JSON-only answer in a ```json ... ``` fence despite being told not to.
_CODE_FENCE = re.compile(r"\A\s*```[A-Za-z]*[ \t]*\n(.*?)\n\s*```\s*\Z", re.DOTALL)

def _strip_code_fence(raw: str) -> str:
    match = _CODE_FENCE.match(raw)
    return match.group(1) if match else raw


def parse_director_output(raw_json: str, segments: list[Segment]) -> list[dict]:
    try:
        payload = json.loads(_strip_code_fence(raw_json))
    except json.JSONDecodeError as e:
        raise DirectorOutputError(f"director output is not valid JSON: {e}") from e

    entries = payload.get("entries", [])
    if len(entries) != len(segments):
        raise DirectorOutputError(f"expected {len(segments)} entries, got {len(entries)}")

    by_index = {e.get("index"): e for e in entries}
    results: list[dict] = []

    for i, segment in enumerate(segments):
        entry = by_index.get(i)
        if entry is None:
            raise DirectorOutputError(f"missing entry for segment {i}")

        entry_type = entry.get("type")
        expected_type = {"plain": "footage", "graphic": "graphic", "talking_head": "talking_head", "page_highlight": "page_highlight", "image": "image"}[segment.kind]
        if entry_type != expected_type:
            raise DirectorOutputError(
                f"segment {i} is '{segment.kind}' but entry type is '{entry_type}'"
            )

        if entry_type in ("talking_head", "page_highlight", "image"):
            results.append({"type": entry_type})
            continue

        if entry_type == "footage":
            if not entry.get("query") or not entry.get("subject"):
                raise DirectorOutputError(f"segment {i} footage entry missing query/subject")
            results.append({"type": "footage", "query": entry["query"], "subject": entry["subject"]})
        else:
            archetype = entry.get("archetype")
            if archetype not in ARCHETYPES:
                raise DirectorOutputError(f"segment {i}: unknown archetype '{archetype}'")
            data = entry.get("data")
            if not data or not isinstance(data, dict):
                # a graphic with nothing to visualize can't be built downstream
                raise DirectorOutputError(f"segment {i} graphic entry missing data")
            results.append({
                "type": "graphic", "archetype": archetype, "data": data,
            })

    return results


# Keys that describe a graphic's values without being one.
_NON_VALUE_KEYS = {"note", "source"}


def check_linked_graphic_data(
    segments: list[Segment], specs: list[dict], graph_readings: dict
) -> None:
    """Run after parse_director_output: a graphic segment that links to a graph must come back
    with values in its data, not just a note or a source (parse_director_output only checks
    that data is a non-empty dict)."""
    for segment_index, entry in map_readings_to_segments(segments, graph_readings).items():
        data = specs[segment_index].get("data") or {}
        if not set(data) - _NON_VALUE_KEYS:
            raise DirectorOutputError(
                f"segment {segment_index} ({entry['italic_text']!r}) links to a graph but the "
                f"director returned no values in its data: {data!r}")
