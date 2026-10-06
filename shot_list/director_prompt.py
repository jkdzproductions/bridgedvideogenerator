import json
import os
from typing import Optional

from shot_list.segments import Segment

DESIGN_SYSTEM_SNAPSHOT = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "design_system", "copy-of-versed-design-system.md"))


PROVIDED_DATA_HEADER = (
    "PROVIDED DATA (read from a linked graph — use ONLY these values in `data`, do not add or "
    "invent others; keep the graph's stated source in `data.source`)"
)


def _value_line(item: dict) -> str:
    if item["readable"]:
        return f"    - {item['label']}: {item['display']} (value {json.dumps(item['value'])}, readable)"
    return (f"    - {item['label']}: printed as {item['display']!r} — UNREADABLE, leave it out of "
            "`data` (do not estimate it)")


def _provided_data_block(segment_index: int, entry: dict) -> str:
    reading = entry["reading"]
    lines = [
        f"[{segment_index}] {PROVIDED_DATA_HEADER}:",
        f"  title: {reading['title'] or '(none printed)'}",
        f"  subtitle: {reading['subtitle'] or '(none printed)'}",
        f"  graph kind: {reading['graph_kind'] or '(not stated)'}",
        f"  unit: {reading['unit'] or '(not stated)'}",
        f"  source line: {reading['source_line'] or '(none printed)'}",
        "  values:",
    ]
    lines += [_value_line(item) for item in reading["values"]]
    if reading["notes"]:
        lines.append(f"  reader's notes: {reading['notes']}")
    return "\n".join(lines)


def _provided_data_section(provided_data: dict) -> str:
    blocks = "\n\n".join(
        _provided_data_block(i, provided_data[i]) for i in sorted(provided_data))
    return f"""
Some graphic segments link to a graph image whose printed numbers have already been read. For \
each segment listed below, build "data" from its PROVIDED DATA block instead of from the \
segment's text: include only the values marked readable, exactly as given; leave out every \
UNREADABLE value; add no other numbers; put the source line in "data.source". The segment's \
text and the block's graph kind still decide which of the 7 frame types fits best.

{blocks}
"""


_PAGE_HIGHLIGHT_NOTE = """
Each "page_highlight" segment is a screenshot of a real web page, captured separately with the \
quoted passage highlighted: do not plan footage or a graphic for it; answer it with just \
{"index": i, "type": "page_highlight"}.
"""


_IMAGE_NOTE = """
Each "image" segment is a picture that will be shown on screen exactly as supplied, with no \
redrawing: do not plan footage or a graphic for it; answer it with just \
{"index": i, "type": "image"}.
"""


def build_director_prompt(segments: list[Segment], provided_data: Optional[dict] = None) -> str:
    """provided_data: {segment index: graph_readings entry} for graphic segments that link to a
    graph (see shot_list.segments.map_readings_to_segments). Without it the prompt is exactly
    the prompt for a script with no linked graphs."""
    indexed_lines = "\n".join(
        f"[{i}] ({seg.kind}) {seg.text}" for i, seg in enumerate(segments)
    )
    provided_section = _provided_data_section(provided_data) if provided_data else ""
    page_note = _PAGE_HIGHLIGHT_NOTE if any(s.kind == "page_highlight" for s in segments) else ""
    image_note = _IMAGE_NOTE if any(s.kind == "image" for s in segments) else ""

    return f"""You are the director agent for a Versed documentary video.

First, Read {DESIGN_SYSTEM_SNAPSHOT} (the Versed design system). Do not invoke any \
skill. Its "The 7 frame types" table defines the only graphic archetypes you may use: \
chart_card, definition, distance, org_chart, place_chip, route_overlay, territory_map.

Below is the script, already split into {len(segments)} ordered segments. Each "graphic" \
segment must become a motion graphic. Each "plain" segment is real stock footage; do not \
subdivide it yourself, just describe the single footage idea for it — cuts are handled \
separately. Each "talking_head" segment is a placeholder that will be filled with \
talking-head footage recorded separately: do not plan footage or a graphic for it; answer \
it with just {{"index": i, "type": "talking_head"}}.

Segments:
{indexed_lines}
{provided_section}{page_note}{image_note}
For each "graphic" segment: choose the one of the 7 frame types whose "Use when the fact \
is..." column best matches the fact in that segment's text, and extract the actual data \
to visualize directly from the text (the numbers, the place(s), the term, the comparison \
values). Each graphic segment MUST map to one of the 7 types. If the fact fits none of them \
well, choose the closest and add a one-line "note" inside "data" explaining the mismatch.

For each "plain" segment: write a short, specific footage search query and a one-line \
subject description capturing exactly what's named in that segment's text — prefer the \
specific place/subject named over a generic stand-in.

Graphic entries have exactly the keys index, type, archetype, data; put any note inside \
data.

Respond with ONLY a JSON object, no other text, with exactly one entry per segment in \
{{"count": {len(segments)}, "entries": [...]}} in the same order as above:

{{
  "count": {len(segments)},
  "entries": [
    {{"index": 0, "type": "footage", "query": "...", "subject": "..."}},
    {{"index": 1, "type": "graphic", "archetype": "chart_card", "data": {{...}}}}
  ]
}}
"""
