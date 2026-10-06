import json

import pytest

from shot_list.align import WordTiming
from shot_list.build import assemble_shot_list, prepare_director_input
from shot_list.director_output import DirectorOutputError, check_linked_graphic_data, parse_director_output
from shot_list.director_prompt import build_director_prompt
from shot_list.markup import parse_markup
from shot_list.models import PageSpec, validate_shot_list
from shot_list.segments import Segment, apply_page_readings, map_readings_to_segments, segment_script, segment_time_range

# Italic spans in order: 0 = "Incomes" (a graph), 1 = "less than forty people" (a page).
MARKED = "Footage first. *Incomes* vary a lot. Then *less than forty people* live there. Footage last."
PAGE_READINGS = {1: {"italic_text": "less than forty people", "url": "https://e.com/a#:~:text=x",
                     "passage": "p", "title": "t", "still_path": "s", "plain_path": "sp", "uncovered": []}}
GRAPH_READINGS = {0: {"italic_text": "Incomes", "url": "https://i.redd.it/x.jpeg", "image_path": "i",
                      "width": 1, "height": 1,
                      "reading": {"title": "T", "subtitle": None, "graph_kind": "map", "unit": "$",
                                  "source_line": "IMF", "notes": None,
                                  "values": [{"label": "A", "display": "$1", "value": 1, "readable": True}]}}}


def _segments(marked=MARKED):
    parsed = parse_markup(marked)
    return parsed, segment_script(parsed.plain_text, parsed.graphic_spans, parsed.talking_head_spans)


def test_apply_page_readings_rekinds_the_named_italic_span():
    _, segments = _segments()

    result = apply_page_readings(segments, PAGE_READINGS)

    assert [s.kind for s in result] == ["plain", "graphic", "plain", "page_highlight", "plain"]
    assert [s.kind for s in segments] == ["plain", "graphic", "plain", "graphic", "plain"]  # input untouched


def test_apply_page_readings_with_no_readings_returns_the_same_kinds():
    _, segments = _segments()

    assert [s.kind for s in apply_page_readings(segments, {})] == [s.kind for s in segments]


def test_apply_page_readings_rejects_an_index_that_does_not_exist():
    _, segments = _segments()
    bad = {7: dict(PAGE_READINGS[1])}

    with pytest.raises(ValueError, match="another script"):
        apply_page_readings(segments, bad)


def test_apply_page_readings_rejects_a_span_whose_text_does_not_match():
    _, segments = _segments()
    bad = {1: dict(PAGE_READINGS[1], italic_text="something else entirely")}

    with pytest.raises(ValueError, match="another script"):
        apply_page_readings(segments, bad)


def test_graph_readings_still_map_after_a_page_span_was_rekinded():
    _, segments = _segments()
    rekinded = apply_page_readings(segments, PAGE_READINGS)

    mapped = map_readings_to_segments(rekinded, GRAPH_READINGS)

    assert list(mapped) == [1]  # segment 1 is the "Incomes" graphic


def test_prepare_director_input_marks_page_segments_and_prompt_explains_them():
    parsed = parse_markup(MARKED)

    segments, prompt = prepare_director_input(
        parsed.plain_text, parsed.graphic_spans, GRAPH_READINGS, parsed.talking_head_spans, PAGE_READINGS)

    assert segments[3].kind == "page_highlight"
    assert "(page_highlight) less than forty people" in prompt
    assert '"type": "page_highlight"' in prompt
    assert "PROVIDED DATA" in prompt  # the graph is still provided data


def test_prompt_without_page_segments_has_no_page_instructions():
    parsed = parse_markup("Footage first. *Incomes* vary. Footage last.")

    _, prompt = prepare_director_input(parsed.plain_text, parsed.graphic_spans)

    assert "page_highlight" not in prompt


def test_parse_director_output_accepts_a_page_highlight_marker():
    segments = [Segment("plain", "a", 0, 1), Segment("page_highlight", "b", 2, 3)]
    raw = json.dumps({"count": 2, "entries": [
        {"index": 0, "type": "footage", "query": "q", "subject": "s"},
        {"index": 1, "type": "page_highlight"}]})

    assert parse_director_output(raw, segments)[1] == {"type": "page_highlight"}


def test_parse_director_output_rejects_the_wrong_type_for_a_page_segment():
    segments = [Segment("page_highlight", "b", 0, 1)]
    raw = json.dumps({"count": 1, "entries": [
        {"index": 0, "type": "graphic", "archetype": "chart_card", "data": {"a": 1}}]})

    with pytest.raises(DirectorOutputError, match="is 'page_highlight' but entry type is 'graphic'"):
        parse_director_output(raw, segments)


def test_check_linked_graphic_data_ignores_page_segments():
    parsed = parse_markup(MARKED)
    segments, _ = prepare_director_input(
        parsed.plain_text, parsed.graphic_spans, GRAPH_READINGS, parsed.talking_head_spans, PAGE_READINGS)
    specs = [{"type": "footage"}, {"type": "graphic", "data": {"values": 1}}, {"type": "footage"},
             {"type": "page_highlight"}, {"type": "footage"}]

    check_linked_graphic_data(segments, specs, GRAPH_READINGS)  # must not raise


def test_page_segment_must_actually_be_spoken():
    plain = "one two three four"
    segment = Segment("page_highlight", "three four", plain.index("three"), len(plain))
    timings = [WordTiming(w, i, i + 0.5, matched=(w in ("one", "two"))) for i, w in enumerate(plain.split())]

    with pytest.raises(ValueError, match="was not spoken in the audio"):
        segment_time_range(segment, plain, timings)


def test_assemble_shot_list_makes_page_highlight_beats_with_the_italic_index():
    parsed = parse_markup(MARKED)
    segments, _ = prepare_director_input(
        parsed.plain_text, parsed.graphic_spans, GRAPH_READINGS, parsed.talking_head_spans, PAGE_READINGS)
    words = parsed.plain_text.split()
    timings = [WordTiming(w, i * 0.5, i * 0.5 + 0.4, matched=True) for i, w in enumerate(words)]
    total = timings[-1].end + 0.5
    specs = [
        {"type": "footage", "query": "q0", "subject": "s0"},
        {"type": "graphic", "archetype": "chart_card", "data": {"values": 1}},
        {"type": "footage", "query": "q2", "subject": "s2"},
        {"type": "page_highlight"},
        {"type": "footage", "query": "q4", "subject": "s4"},
    ]

    shot_list = assemble_shot_list(segments, parsed.plain_text, timings, specs, total)

    validate_shot_list(shot_list)
    pages = [b for b in shot_list.beats if b.type == "page_highlight"]
    assert len(pages) == 1
    assert pages[0].page == PageSpec(italic_index=1)
    assert pages[0].footage is None and pages[0].graphic is None
    graphics = [b for b in shot_list.beats if b.type == "graphic"]
    assert len(graphics) == 1
