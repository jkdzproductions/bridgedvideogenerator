"""The "Page highlights" section of Stage 1's final report."""


def build_page_highlights_report(page_readings: dict, skipped_page_links: list) -> str:
    lines = []
    if not page_readings:
        lines.append("Page highlights: none.")
    else:
        lines.append(f"Page highlights ({len(page_readings)}):")
        for italic_index in sorted(page_readings):
            entry = page_readings[italic_index]
            lines += [
                f"- Italic phrase: {entry['italic_text']!r} (graphic span {italic_index})",
                f"  URL: {entry['url']}",
                f"  Passage: {entry['passage']}",
                f"  Page title: {entry['title'] or '(none)'}",
                f"  Still (open and check it): {entry['still_path']}",
            ]
            if entry["uncovered"]:
                lines.append(f"  Could not clear (check the still): {', '.join(entry['uncovered'])}")
    if skipped_page_links:
        lines.append(
            'Page links with no highlight (no page still is made; the italic phrase will still be '
            'built as an ordinary graphic from its own text unless you replace the link — open the '
            'page, select the text, use Chrome\'s "Copy link to highlight", and link that):')
        lines += [f"- {link['text'].strip()!r} -> {link['url']}" for link in skipped_page_links]
    else:
        lines.append("Page links with no highlight: none.")
    return "\n".join(lines)
