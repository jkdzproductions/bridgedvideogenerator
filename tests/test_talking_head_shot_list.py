import json

import pytest

from shot_list.align import WordTiming
from shot_list.build import assemble_shot_list, prepare_director_input
from shot_list.director_output import DirectorOutputError, parse_director_output
from shot_list.director_prompt import build_director_prompt
from shot_list.markup import parse_markup
from shot_list.models import (
    Beat, FootageSpec, GraphicSpec, ShotList, ShotListValidationError, validate_shot_list,
)
from shot_list.segments import Segment, segment_script

SCRIPT = "Intro words here. **Talk to camera now.** Outro words follow."


def _segments():
    parsed = parse_markup(SCRIPT)
    return parsed, segment_script(parsed.plain_text, parsed.graphic_spans, parsed.talking_head_spans)


def test_segment_script_makes_a_talking_head_segment():
    _, segments = _segments()

    assert [(s.kind, s.text) for s in segments] == [
        ("plain", "Intro words here."),
        ("talking_head", "Talk to camera now."),
        ("plain", "Outro words follow."),
    ]


def test_talking_head_span_with_no_whole_word_raises():
    parsed = parse_markup('The word "**Mexico**" matters.')

    with pytest.raises(ValueError, match="contains no whole word"):
        segment_script(parsed.plain_text, parsed.graphic_spans, parsed.talking_head_spans)


def test_prepare_director_input_passes_talking_head_spans_through():
    parsed = parse_markup(SCRIPT)

    segments, prompt = prepare_director_input(
        parsed.plain_text, parsed.graphic_spans, None, parsed.talking_head_spans)

    assert [s.kind for s in segments] == ["plain", "talking_head", "plain"]
    assert "[1] (talking_head) Talk to camera now." in prompt


def test_director_prompt_tells_the_director_to_skip_talking_head_segments():
    prompt = build_director_prompt([Segment("talking_head", "Talk to camera.", 0, 15)])

    assert '"talking_head"' in prompt
    assert '{"index": i, "type": "talking_head"}' in prompt
    assert "do not plan footage or a graphic" in prompt


def _raw(*entries):
    return json.dumps({"count": len(entries), "entries": list(entries)})


def test_parse_director_output_accepts_a_talking_head_marker_entry():
    _, segments = _segments()
    raw = _raw(
        {"index": 0, "type": "footage", "query": "q", "subject": "s"},
        {"index": 1, "type": "talking_head"},
        {"index": 2, "type": "footage", "query": "q2", "subject": "s2"},
    )

    assert parse_director_output(raw, segments)[1] == {"type": "talking_head"}


@pytest.mark.parametrize("wrong_entry", [
    {"index": 1, "type": "footage", "query": "q", "subject": "s"},
    {"index": 1, "type": "graphic", "archetype": "territory_map", "data": {"x": 1}},
])
def test_parse_director_output_rejects_footage_or_graphic_for_a_talking_head(wrong_entry):
    _, segments = _segments()
    raw = _raw(
        {"index": 0, "type": "footage", "query": "q", "subject": "s"},
        wrong_entry,
        {"index": 2, "type": "footage", "query": "q2", "subject": "s2"},
    )

    with pytest.raises(DirectorOutputError, match="segment 1 is 'talking_head'"):
        parse_director_output(raw, segments)


def test_assemble_shot_list_emits_a_gapless_talking_head_beat():
    parsed, segments = _segments()
    words = parsed.plain_text.split()
    timings = [WordTiming(word=w, start=float(i), end=i + 0.5) for i, w in enumerate(words)]
    specs = [
        {"type": "footage", "query": "q", "subject": "s"},
        {"type": "talking_head"},
        {"type": "footage", "query": "q2", "subject": "s2"},
    ]

    shot_list = assemble_shot_list(segments, parsed.plain_text, timings, specs, total_duration=10.0)

    assert [b.type for b in shot_list.beats] == ["footage", "talking_head", "footage"]
    talking = shot_list.beats[1]
    assert talking.footage is None and talking.graphic is None
    assert shot_list.beats[0].end == talking.start
    assert talking.end == shot_list.beats[2].start
    validate_shot_list(shot_list)


def test_long_talking_head_stays_one_beat_and_is_never_split_by_pacing():
    parsed = parse_markup("Start. **" + " ".join(["talk"] * 40) + "** End.")
    segments = segment_script(parsed.plain_text, parsed.graphic_spans, parsed.talking_head_spans)
    words = parsed.plain_text.split()
    timings = [WordTiming(word=w, start=float(i), end=i + 0.5) for i, w in enumerate(words)]
    specs = [
        {"type": "footage", "query": "q", "subject": "s"},
        {"type": "talking_head"},
        {"type": "footage", "query": "q2", "subject": "s2"},
    ]

    shot_list = assemble_shot_list(segments, parsed.plain_text, timings, specs, total_duration=float(len(words)))

    assert [b.type for b in shot_list.beats] == ["footage", "talking_head", "footage"]


def _shot_list(beat):
    return ShotList(beats=[beat], duration=beat.end)


def test_validate_accepts_a_talking_head_beat_with_no_spec():
    validate_shot_list(_shot_list(Beat(0.0, 5.0, "talking_head")))


def test_validate_rejects_a_talking_head_beat_that_carries_a_spec():
    with pytest.raises(ShotListValidationError, match="talking_head"):
        validate_shot_list(_shot_list(Beat(0.0, 5.0, "talking_head", footage=FootageSpec("q", "s"))))
    with pytest.raises(ShotListValidationError, match="talking_head"):
        validate_shot_list(_shot_list(
            Beat(0.0, 5.0, "talking_head", graphic=GraphicSpec("territory_map", {"x": 1}))))


def test_validate_rejects_an_unknown_beat_type():
    with pytest.raises(ShotListValidationError, match="unknown beat type"):
        validate_shot_list(_shot_list(Beat(0.0, 5.0, "hologram")))


def test_stage_2_and_3_selectors_skip_talking_head_beats():
    from footage.shotlist_integration import footage_beats
    from motion_graphics.shotlist_integration import graphic_beats

    shot_list = ShotList(
        beats=[
            Beat(0.0, 3.0, "footage", footage=FootageSpec("q", "s")),
            Beat(3.0, 6.0, "talking_head"),
            Beat(6.0, 9.0, "graphic", graphic=GraphicSpec("territory_map", {"x": 1})),
        ],
        duration=9.0,
    )

    assert [i for i, _, _ in footage_beats(shot_list)] == [0]
    assert [i for i, _, _ in graphic_beats(shot_list)] == [2]


def test_no_whole_word_error_includes_surrounding_context():
    parsed = parse_markup('The word "**Mexico**" matters.')

    with pytest.raises(ValueError, match="contains no whole word") as info:
        segment_script(parsed.plain_text, parsed.graphic_spans, parsed.talking_head_spans)

    assert "near" in str(info.value)
    assert 'The word "Mexico" matters.' in str(info.value)
