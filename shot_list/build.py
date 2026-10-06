from typing import Optional

from shot_list.align import WordTiming
from shot_list.director_prompt import build_director_prompt
from shot_list.models import Beat, FootageSpec, GraphicSpec, ImageSpec, PageSpec, ShotList
from shot_list.pacing import subdivide_footage_range
from shot_list.segments import (
    Segment,
    apply_image_readings,
    apply_page_readings,
    map_readings_to_segments,
    segment_script,
    segment_time_range,
)


def prepare_director_input(
    plain_text: str,
    graphic_spans: list[tuple[int, int]],
    graph_readings: Optional[dict] = None,
    talking_head_spans: Optional[list[tuple[int, int]]] = None,
    page_readings: Optional[dict] = None,
    image_readings: Optional[dict] = None,
) -> tuple[list[Segment], str]:
    """graph_readings: graph_readings.json keyed by int italic_index (graph_intake.build.
    load_graph_readings); None or {} for a script with no linked graphs. talking_head_spans:
    the `**...**` spans from parse_markup (placeholders the director does not plan). page_readings: page_readings.json keyed by int
    italic_index; None or {} when the script has no page highlights. image_readings: image_readings.json keyed by int
    italic_index; None or {} when the script has no show-as-is images."""
    segments = segment_script(plain_text, graphic_spans, talking_head_spans or [])
    provided_data = map_readings_to_segments(segments, graph_readings or {})
    segments = apply_page_readings(segments, page_readings or {})
    segments = apply_image_readings(segments, image_readings or {})
    prompt = build_director_prompt(segments, provided_data)
    return segments, prompt


def _contiguous_boundaries(
    word_ranges: list[tuple[float, float]], total_duration: float
) -> list[float]:
    """Turn per-segment spoken ranges (which never touch in real speech — there is silence
    between words) into a single shared timestamp at every boundary.

    The timeline starts at 0.0 and ends at the real audio duration; each interior boundary
    is the midpoint of the pause between one segment's last word and the next segment's
    first word. Both neighbouring beats use that same number, so coverage is gapless by
    construction.
    """
    boundaries = [0.0]
    for (_, prev_end), (next_start, _) in zip(word_ranges, word_ranges[1:]):
        boundaries.append((prev_end + next_start) / 2)
    boundaries.append(total_duration)

    for i, (a, b) in enumerate(zip(boundaries, boundaries[1:])):
        if not a < b:
            raise ValueError(
                f"segment {i} has a non-positive time range ({a:.3f}-{b:.3f}); "
                "word timings are out of order"
            )
    return boundaries


def assemble_shot_list(
    segments: list[Segment],
    plain_text: str,
    word_timings: list[WordTiming],
    director_specs: list[dict],
    total_duration: float,
) -> ShotList:
    if len(director_specs) != len(segments):
        raise ValueError(f"expected {len(segments)} director specs, got {len(director_specs)}")
    # Each workflow step re-reads the script from disk; catch it being edited after alignment.
    if [w.word for w in word_timings] != plain_text.split():
        raise ValueError(
            "word timings don't match the script — the script changed after alignment; "
            "re-run alignment against the current script"
        )

    word_ranges = [segment_time_range(s, plain_text, word_timings) for s in segments]
    last_word_end = word_ranges[-1][1]
    if total_duration < last_word_end:
        raise ValueError(
            f"total_duration {total_duration:.3f}s is shorter than the last spoken word "
            f"(ends {last_word_end:.3f}s) — pass the real audio duration"
        )
    boundaries = _contiguous_boundaries(word_ranges, total_duration)

    beats: list[Beat] = []
    italic_count = 0
    for i, (segment, spec) in enumerate(zip(segments, director_specs)):
        start, end = boundaries[i], boundaries[i + 1]
        italic_index = italic_count
        if segment.kind in ("graphic", "page_highlight", "image"):
            italic_count += 1

        if segment.kind == "graphic":
            beats.append(Beat(
                start=start, end=end, type="graphic",
                graphic=GraphicSpec(archetype=spec["archetype"], data=spec["data"]),
            ))
        elif segment.kind == "page_highlight":
            beats.append(Beat(start=start, end=end, type="page_highlight", page=PageSpec(italic_index=italic_index)))
        elif segment.kind == "image":
            beats.append(Beat(start=start, end=end, type="image", image=ImageSpec(italic_index=italic_index)))
        elif segment.kind == "talking_head":
            beats.append(Beat(start=start, end=end, type="talking_head"))
        else:
            cuts = subdivide_footage_range(start, end)
            for cut_start, cut_end in cuts:
                beats.append(Beat(
                    start=cut_start, end=cut_end, type="footage",
                    footage=FootageSpec(query=spec["query"], subject=spec["subject"]),
                ))

    return ShotList(beats=beats, duration=total_duration)
