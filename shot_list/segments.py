import dataclasses
import re
from dataclasses import dataclass
from typing import Literal, Optional

from shot_list.align import WordTiming


@dataclass
class Segment:
    kind: Literal["plain", "graphic", "talking_head", "page_highlight", "image"]
    text: str
    char_start: int  # start of the segment's first word in plain_text
    char_end: int  # end of the segment's last word in plain_text


_WORD = re.compile(r"\S+")

# A graphic or talking-head segment is a stated moment timed to when it's said. If fewer than
# half its words were recognized in the audio, its timing is mostly interpolation — it was
# likely never spoken (e.g. added after recording).
# Half (not "all") leaves room for whisper mis-transcribing a number or name.
MIN_MARKED_MATCHED_FRACTION = 0.5
_MARKED_KINDS = ("graphic", "talking_head", "page_highlight", "image")
# Segments that come from an italic span (a page highlight or a show-as-is image is an italic span with a link).
_ITALIC_KINDS = ("graphic", "page_highlight", "image")


def _script_word_spans(plain_text: str) -> list[tuple[int, int]]:
    """Char span of every whitespace-delimited word — the same tokens as plain_text.split(),
    which is also how align_words tokenizes the script."""
    return [(m.start(), m.end()) for m in _WORD.finditer(plain_text)]


_KIND_LABELS = {"graphic": "graphic (*...*)", "talking_head": "talking-head (**...**)"}


def segment_script(
    plain_text: str,
    graphic_spans: list[tuple[int, int]],
    talking_head_spans: Optional[list[tuple[int, int]]] = None,
) -> list["Segment"]:
    """Split the script into ordered plain/graphic/talking_head segments made of whole words.

    Each word belongs to exactly one segment: the one whose markup covers the word's FIRST
    character. So punctuation or a suffix just outside a marker (`*decade*.`, `*Tokyo*'s`)
    stays with its word instead of being claimed by two segments, and whitespace between
    back-to-back marked spans never becomes its own footage slot. Each marked span stays its own
    segment (one graphic / talking head per span), even when two are adjacent; consecutive
    plain words merge into one segment.
    """
    word_spans = _script_word_spans(plain_text)
    if not word_spans:
        raise ValueError("script has no words")

    marked = [("graphic", s, e) for s, e in graphic_spans] + [
        ("talking_head", s, e) for s, e in (talking_head_spans or [])
    ]

    def owner(word_start: int) -> Optional[int]:
        for span_idx, (_, b_start, b_end) in enumerate(marked):
            if b_start <= word_start < b_end:
                return span_idx
        return None

    groups: list[tuple[Optional[int], int, int]] = []  # (marked span idx or None, char_start, char_end)
    for w_start, w_end in word_spans:
        key = owner(w_start)
        if groups and groups[-1][0] == key:
            groups[-1] = (key, groups[-1][1], w_end)
        else:
            groups.append((key, w_start, w_end))

    owned = {key for key, _, _ in groups if key is not None}
    for span_idx, (kind, b_start, b_end) in enumerate(marked):
        if span_idx not in owned:
            context = " ".join(plain_text[max(0, b_start - 25):b_end + 25].split())
            raise ValueError(
                f"{_KIND_LABELS[kind]} span {plain_text[b_start:b_end]!r} contains no whole word "
                f"(a marked span must start at the beginning of a word; near {context!r}) — fix the markup"
            )

    return [
        Segment("plain" if key is None else marked[key][0], plain_text[c_start:c_end], c_start, c_end)
        for key, c_start, c_end in groups
    ]


def segment_time_range(
    segment: "Segment", plain_text: str, word_timings: list[WordTiming]
) -> tuple[float, float]:
    """Spoken time range of the segment: first word's start to last word's end.

    Word i of the script is word_timings[i] (align_words returns exactly one timing per
    script word, in order). A word belongs to the segment whose char range contains its
    first character, matching segment_script's assignment.
    """
    covered = [
        wt
        for (c_start, _), wt in zip(_script_word_spans(plain_text), word_timings)
        if segment.char_start <= c_start < segment.char_end
    ]
    if not covered:
        raise ValueError(
            f"no word timings found for segment {segment.char_start}-{segment.char_end}: "
            f"{segment.text!r}"
        )
    if segment.kind in _MARKED_KINDS:
        matched = sum(wt.matched for wt in covered)
        if matched / len(covered) < MIN_MARKED_MATCHED_FRACTION:
            raise ValueError(
                f"{segment.kind} segment {segment.text!r} was not spoken in the audio: only "
                f"{matched}/{len(covered)} of its words were recognized (the rest are "
                "interpolated guesses) — was it added to the script after recording?"
            )
    return covered[0].start, covered[-1].end


def map_readings_to_segments(segments: list["Segment"], graph_readings: dict) -> dict:
    """{italic_index: entry} (graph_readings.json, keyed by the order of the graphic (*...*) spans) ->
    {segment index: entry}. segment_script gives every graphic span exactly one segment, in
    order, so the Nth graphic segment is graphic span N. Raises if the readings don't fit this
    script (left over from a different one)."""
    italic_positions = [i for i, s in enumerate(segments) if s.kind in _ITALIC_KINDS]
    mapped = {}
    for italic_index, entry in sorted(graph_readings.items()):
        if not 0 <= italic_index < len(italic_positions):
            raise ValueError(
                f"linked graph for {entry['italic_text']!r} belongs to graphic span {italic_index}, but "
                f"the script has {len(italic_positions)} graphic spans — graph_readings.json is from "
                "another script; re-run Stage 1 from Step 1a")
        segment_index = italic_positions[italic_index]
        if " ".join(entry["italic_text"].split()) not in " ".join(segments[segment_index].text.split()):
            raise ValueError(
                f"linked graph for {entry['italic_text']!r} belongs to graphic span {italic_index}, but "
                f"that span reads {segments[segment_index].text!r} — graph_readings.json is from "
                "another script; re-run Stage 1 from Step 1a")
        mapped[segment_index] = entry
    return mapped


def _rekind_italic_spans(
    segments: list["Segment"], readings: dict, kind: str, noun: str, filename: str
) -> list["Segment"]:
    """A copy of `segments` in which each italic span named by `readings` ({italic_index: entry})
    has the given kind. Raises if the readings don't fit this script (left over from a different one)."""
    italic_positions = [i for i, s in enumerate(segments) if s.kind in _ITALIC_KINDS]
    result = list(segments)
    for italic_index, entry in sorted(readings.items()):
        if not 0 <= italic_index < len(italic_positions):
            raise ValueError(
                f"{noun} for {entry['italic_text']!r} belongs to graphic span {italic_index}, but "
                f"the script has {len(italic_positions)} graphic spans — {filename} is from "
                "another script; re-run Stage 1 from Step 1a")
        position = italic_positions[italic_index]
        if " ".join(entry["italic_text"].split()) not in " ".join(segments[position].text.split()):
            raise ValueError(
                f"{noun} for {entry['italic_text']!r} belongs to graphic span {italic_index}, but "
                f"that span reads {segments[position].text!r} — {filename} is from "
                "another script; re-run Stage 1 from Step 1a")
        result[position] = dataclasses.replace(segments[position], kind=kind)
    return result


def apply_page_readings(segments: list["Segment"], page_readings: dict) -> list["Segment"]:
    """{italic_index: page reading} (page_readings.json) -> a copy of `segments` in which each
    italic span that links to a page is re-kinded "page_highlight"."""
    return _rekind_italic_spans(segments, page_readings, "page_highlight", "page highlight", "page_readings.json")


def apply_image_readings(segments: list["Segment"], image_readings: dict) -> list["Segment"]:
    """{italic_index: image reading} (image_readings.json) -> a copy of `segments` in which each
    span that links to a show-as-is image is re-kinded "image"."""
    return _rekind_italic_spans(segments, image_readings, "image", "image", "image_readings.json")
