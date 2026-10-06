"""The "Linked graphs" section of Stage 1's final report."""
import json

VERIFY_FLAG = "read from an image — verify against the source before publishing"


def _value_line(item: dict) -> str:
    if item["readable"]:
        return f"    - {item['label']}: {item['display']} ({json.dumps(item['value'])})"
    printed = item["display"] or "nothing legible"
    return f"    - {item['label']}: UNREADABLE (printed as {printed!r}) — left out of the graphic"


def build_linked_graphs_report(graph_readings: dict, ignored_links: list) -> str:
    lines = []
    if not graph_readings:
        lines.append("Linked graphs: none.")
    else:
        lines.append(f"Linked graphs ({len(graph_readings)}):")
        for italic_index in sorted(graph_readings):
            entry = graph_readings[italic_index]
            reading = entry["reading"]
            lines += [
                f"- Italic phrase: {entry['italic_text']!r} (graphic span {italic_index})",
                f"  URL: {entry['url']}",
                f"  Saved image: {entry['image_path']}",
                f"  Title: {reading['title'] or '(none printed)'}",
                f"  Graph kind: {reading['graph_kind'] or '(not stated)'}",
                f"  Source line: {reading['source_line'] or '(none printed)'}",
                f"  Values ({VERIFY_FLAG}):",
            ]
            lines += [_value_line(item) for item in reading["values"]]
            if reading["notes"]:
                lines.append(f"  Reader's notes: {reading['notes']}")
    if ignored_links:
        lines.append("Links on text that is not italic (ignored — not graphics):")
        lines += [f"- {link['text'].strip()!r} -> {link['url']}" for link in ignored_links]
    else:
        lines.append("Links on text that is not italic: none.")
    return "\n".join(lines)
