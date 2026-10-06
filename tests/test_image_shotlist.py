import json

import pytest

from shot_list.align import WordTiming
from shot_list.build import assemble_shot_list, prepare_director_input
from shot_list.director_output import DirectorOutputError, check_linked_graphic_data, parse_director_output
from shot_list.markup import parse_markup
from shot_list.models import ImageSpec, validate_shot_list
from shot_list.segments import (
    Segment, apply_image_readings, apply_page_readings, map_readings_to_segments, segment_script,
    segment_time_range)

# Italic spans in order: 0 = "Incomes" (a graph), 1 = "less than forty people" (a page), 2 = "the old map" (an image).
MARKED = ("Footage first. *Incomes* vary a lot. Then *less than forty people* live there. "
          "See *the old map* now. Footage last.")
IMAGE_READINGS = {2: {"italic_text": "the old map", "url": "https://e.com/m.jpg", "still_path": "s",
                      "width": 1, "height": 1}}
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


def test_apply_image_readings_rekinds_the_named_italic_span():
    _, segments = _segments()

    result = apply_image_readings(segments, IMAGE_READINGS)

    assert [s.kind for s in result] == ["plain", "graphic", "plain", "graphic", "plain", "image", "plain"]
    assert [s.kind for s in segments][5] == "graphic"  # input untouched


def test_apply_image_readings_with_no_readings_returns_the_same_kinds():
    _, segments = _segments()

    assert [s.kind for s in apply_image_readings(segments, {})] == [s.kind for s in segments]


def test_apply_image_readings_rejects_an_index_that_does_not_exist():
    _, segments = _segments()

    with pytest.raises(ValueError, match="image_readings.json is from another script"):
        apply_image_readings(segments, {9: dict(IMAGE_READINGS[2])})


def test_apply_image_readings_rejects_a_span_whose_text_does_not_match():
    _, segments = _segments()
    bad = {2: dict(IMAGE_READINGS[2], italic_text="something else entirely")}

    with pytest.raises(ValueError, match="image_readings.json is from another script"):
        apply_image_readings(segments, bad)


def test_page_highlights_and_images_can_both_be_rekinded_in_one_script():
    _, segments = _segments()

    result = apply_image_readings(apply_page_readings(segments, PAGE_READINGS), IMAGE_READINGS)

    assert [s.kind for s in result] == [
        "plain", "graphic", "plain", "page_highlight", "plain", "image", "plain"]
    assert list(map_readings_to_segments(result, GRAPH_READINGS)) == [1]  # the graph is still found


def test_page_error_messages_are_unchanged_by_the_shared_helper():
    _, segments = _segments()

    with pytest.raises(ValueError, match="page highlight for .* page_readings.json is from another script"):
        apply_page_readings(segments, {9: dict(PAGE_READINGS[1])})


def test_prepare_director_input_marks_image_segments_and_the_prompt_explains_them():
    parsed = parse_markup(MARKED)

    segments, prompt = prepare_director_input(
        parsed.plain_text, parsed.graphic_spans, GRAPH_READINGS, parsed.talking_head_spans,
        PAGE_READINGS, IMAGE_READINGS)

    assert segments[5].kind == "image"
    assert "(image) the old map" in prompt
    assert '"type": "image"' in prompt
    assert "PROVIDED DATA" in prompt and "(page_highlight)" in prompt  # the other kinds still work


def test_prompt_without_image_segments_has_no_image_instructions():
    parsed = parse_markup("Footage first. *Incomes* vary. Footage last.")

    _, prompt = prepare_director_input(parsed.plain_text, parsed.graphic_spans)

    assert '"type": "image"' not in prompt


def test_parse_director_output_accepts_an_image_marker():
    segments = [Segment("plain", "a", 0, 1), Segment("image", "b", 2, 3)]
    raw = json.dumps({"count": 2, "entries": [
        {"index": 0, "type": "footage", "query": "q", "subject": "s"},
        {"index": 1, "type": "image"}]})

    assert parse_director_output(raw, segments)[1] == {"type": "image"}


def test_parse_director_output_rejects_the_wrong_type_for_an_image_segment():
    segments = [Segment("image", "b", 0, 1)]
    raw = json.dumps({"count": 1, "entries": [
        {"index": 0, "type": "graphic", "archetype": "chart_card", "data": {"a": 1}}]})

    with pytest.raises(DirectorOutputError, match="is 'image' but entry type is 'graphic'"):
        parse_director_output(raw, segments)


def test_check_linked_graphic_data_ignores_image_segments():
    parsed = parse_markup(MARKED)
    segments, _ = prepare_director_input(
        parsed.plain_text, parsed.graphic_spans, GRAPH_READINGS, parsed.talking_head_spans,
        PAGE_READINGS, IMAGE_READINGS)
    specs = [{"type": "footage"}, {"type": "graphic", "data": {"values": 1}}, {"type": "footage"},
             {"type": "page_highlight"}, {"type": "footage"}, {"type": "image"}, {"type": "footage"}]

    check_linked_graphic_data(segments, specs, GRAPH_READINGS)  # must not raise


def test_an_image_segment_must_actually_be_spoken():
    plain = "one two three four"
    segment = Segment("image", "three four", plain.index("three"), len(plain))
    timings = [WordTiming(w, i, i + 0.5, matched=(w in ("one", "two"))) for i, w in enumerate(plain.split())]

    with pytest.raises(ValueError, match="was not spoken in the audio"):
        segment_time_range(segment, plain, timings)


def test_assemble_shot_list_makes_image_beats_with_the_italic_index():
    parsed = parse_markup(MARKED)
    segments, _ = prepare_director_input(
        parsed.plain_text, parsed.graphic_spans, GRAPH_READINGS, parsed.talking_head_spans,
        PAGE_READINGS, IMAGE_READINGS)
    words = parsed.plain_text.split()
    timings = [WordTiming(w, i * 0.5, i * 0.5 + 0.4, matched=True) for i, w in enumerate(words)]
    total = timings[-1].end + 0.5
    specs = [
        {"type": "footage", "query": "q0", "subject": "s0"},
        {"type": "graphic", "archetype": "chart_card", "data": {"values": 1}},
        {"type": "footage", "query": "q2", "subject": "s2"},
        {"type": "page_highlight"},
        {"type": "footage", "query": "q4", "subject": "s4"},
        {"type": "image"},
        {"type": "footage", "query": "q6", "subject": "s6"},
    ]

    shot_list = assemble_shot_list(segments, parsed.plain_text, timings, specs, total)

    validate_shot_list(shot_list)
    images = [b for b in shot_list.beats if b.type == "image"]
    assert len(images) == 1
    assert images[0].image == ImageSpec(italic_index=2)
    assert images[0].footage is None and images[0].graphic is None and images[0].page is None
