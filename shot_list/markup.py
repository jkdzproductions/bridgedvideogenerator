import re
from dataclasses import dataclass


@dataclass
class ParsedScript:
    plain_text: str
    graphic_spans: list[tuple[int, int]]  # *italic* -> motion graphic
    talking_head_spans: list[tuple[int, int]]  # **bold** -> talking-head placeholder


_MARKER = re.compile(r"\*\*|\*")
_LABELS = {"graphic": "*...*", "talking_head": "**...**"}


def parse_markup(script_text: str) -> ParsedScript:
    """`*text*` marks a graphic (italic), `**text**` a talking head (bold). Spans may not
    overlap or nest; every opening marker needs a closing marker of the same kind."""
    plain_parts: list[str] = []
    spans: dict[str, list[tuple[int, int]]] = {"graphic": [], "talking_head": []}
    cursor = 0
    plain_len = 0
    open_kind = None
    open_start = 0

    for match in _MARKER.finditer(script_text):
        kind = "talking_head" if match.group(0) == "**" else "graphic"
        chunk = script_text[cursor:match.start()]
        plain_parts.append(chunk)
        plain_len += len(chunk)
        cursor = match.end()
        if open_kind is None:
            open_kind, open_start = kind, plain_len
        elif open_kind == kind:
            spans[kind].append((open_start, plain_len))
            open_kind = None
        else:
            raise ValueError(
                f"Script has overlapping or nested markers: a {_LABELS[open_kind]} span is "
                f"interrupted by a {_LABELS[kind]} marker. Spans cannot overlap or nest."
            )

    if open_kind is not None:
        raise ValueError(
            f"Script contains unbalanced markers ({_LABELS[open_kind].split('...')[0]}). "
            "Every opening * or ** must have a corresponding closing marker of the same kind."
        )
    plain_parts.append(script_text[cursor:])
    return ParsedScript(
        plain_text="".join(plain_parts),
        graphic_spans=spans["graphic"],
        talking_head_spans=spans["talking_head"],
    )
