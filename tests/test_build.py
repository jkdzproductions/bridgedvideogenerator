import pytest
from shot_list.align import WordTiming
from shot_list.build import assemble_shot_list, prepare_director_input
from shot_list.markup import parse_markup
from shot_list.models import validate_shot_list


SCRIPT = "The city grew fast. *Population tripled in a decade.* Then it slowed."

WORD_TIMINGS = [
    WordTiming("The", 0.0, 0.2), WordTiming("city", 0.2, 0.5),
    WordTiming("grew", 0.5, 0.8), WordTiming("fast.", 0.8, 1.2),
    WordTiming("Population", 1.2, 1.8), WordTiming("tripled", 1.8, 2.2),
    WordTiming("in", 2.2, 2.3), WordTiming("a", 2.3, 2.4), WordTiming("decade.", 2.4, 2.9),
    WordTiming("Then", 2.9, 3.1), WordTiming("it", 3.1, 3.2), WordTiming("slowed.", 3.2, 3.6),
]


def test_prepare_director_input_returns_segments_and_prompt():
    parsed = parse_markup(SCRIPT)

    segments, prompt = prepare_director_input(parsed.plain_text, parsed.graphic_spans)

    assert [s.kind for s in segments] == ["plain", "graphic", "plain"]
    assert "Population tripled in a decade." in prompt
    assert '"count": 3' in prompt


def test_assemble_shot_list_produces_valid_coverage():
    parsed = parse_markup(SCRIPT)
    segments, _ = prepare_director_input(parsed.plain_text, parsed.graphic_spans)
    director_specs = [
        {"type": "footage", "query": "city growth timelapse", "subject": "a growing city"},
        {"type": "graphic", "archetype": "chart_card", "data": {"value": "2x"}},
        {"type": "footage", "query": "city slowing down, empty streets", "subject": "a slowing city"},
    ]

    shot_list = assemble_shot_list(
        segments, parsed.plain_text, WORD_TIMINGS, director_specs, total_duration=3.6
    )

    validate_shot_list(shot_list)  # does not raise
    assert shot_list.beats[0].type == "footage"
    assert shot_list.beats[1].type == "graphic"
    assert shot_list.beats[1].graphic.archetype == "chart_card"
    assert shot_list.beats[-1].end == 3.6


def _specs_for(segments):
    return [
        {"type": "graphic", "archetype": "chart_card", "data": {"value": "3x"}}
        if s.kind == "graphic"
        else {"type": "footage", "query": "city street", "subject": "a city"}
        for s in segments
    ]


def test_assemble_shot_list_is_contiguous_with_realistic_non_touching_word_timings():
    # Real speech: 0.4s of leading silence, pauses between sentences, and a tail of
    # audio after the last word. No segment's word range touches its neighbour's.
    parsed = parse_markup(SCRIPT)
    segments, _ = prepare_director_input(parsed.plain_text, parsed.graphic_spans)
    word_timings = [
        WordTiming("The", 0.4, 0.6), WordTiming("city", 0.62, 0.9),
        WordTiming("grew", 0.92, 1.2), WordTiming("fast.", 1.22, 1.6),
        # 0.35s pause
        WordTiming("Population", 1.95, 2.5), WordTiming("tripled", 2.52, 2.9),
        WordTiming("in", 2.92, 3.0), WordTiming("a", 3.02, 3.1), WordTiming("decade.", 3.12, 3.6),
        # 0.4s pause
        WordTiming("Then", 4.0, 4.2), WordTiming("it", 4.22, 4.3), WordTiming("slowed.", 4.32, 4.8),
    ]
    total_duration = 5.3  # 0.5s tail after the last word

    shot_list = assemble_shot_list(
        segments, parsed.plain_text, word_timings, _specs_for(segments), total_duration
    )

    validate_shot_list(shot_list)  # does not raise
    assert shot_list.beats[0].start == 0.0
    assert shot_list.beats[-1].end == total_duration
    # each boundary is one shared timestamp, placed inside the pause between segments
    assert 1.6 < shot_list.beats[0].end == shot_list.beats[1].start < 1.95
    assert 3.6 < shot_list.beats[1].end == shot_list.beats[2].start < 4.0


def test_assemble_shot_list_rejects_duration_shorter_than_the_speech():
    parsed = parse_markup(SCRIPT)
    segments, _ = prepare_director_input(parsed.plain_text, parsed.graphic_spans)

    with pytest.raises(ValueError, match="total_duration"):
        assemble_shot_list(
            segments, parsed.plain_text, WORD_TIMINGS, _specs_for(segments), total_duration=3.0
        )


@pytest.mark.parametrize("script", [
    "The city grew fast. *Population tripled in a decade*. Then it slowed.",
    "*Tokyo*'s subway moves fourteen million people. It is busy.",
    "It began here. *Fact one.* *Fact two.* Then it ended.",
])
def test_natural_markup_patterns_assemble_into_a_valid_shot_list(script):
    parsed = parse_markup(script)
    segments, _ = prepare_director_input(parsed.plain_text, parsed.graphic_spans)
    words = parsed.plain_text.split()
    word_timings = [WordTiming(w, 0.2 + i * 0.5, 0.2 + i * 0.5 + 0.4) for i, w in enumerate(words)]

    shot_list = assemble_shot_list(
        segments, parsed.plain_text, word_timings, _specs_for(segments),
        total_duration=word_timings[-1].end + 0.5,
    )

    validate_shot_list(shot_list)  # does not raise


def test_prepare_director_input_fails_fast_on_degenerate_markup():
    # raises before any prompt is built, so no director subagent call is wasted
    with pytest.raises(ValueError, match="contains no whole word"):
        prepare_director_input(*_parsed("The city of Tok*yo* grew."))


def _parsed(script):
    p = parse_markup(script)
    return p.plain_text, p.graphic_spans


def test_assemble_shot_list_raises_when_spec_count_differs_from_segments():
    parsed = parse_markup(SCRIPT)
    segments, _ = prepare_director_input(parsed.plain_text, parsed.graphic_spans)

    with pytest.raises(ValueError, match="expected 3 director specs, got 2"):
        assemble_shot_list(
            segments, parsed.plain_text, WORD_TIMINGS, _specs_for(segments)[:2], total_duration=3.6
        )


def test_assemble_shot_list_raises_when_script_changed_after_alignment():
    # word_timings.json was produced from an older version of the script file
    edited = parse_markup("The town grew fast. *Population tripled in a decade.* Then it slowed.")
    segments, _ = prepare_director_input(edited.plain_text, edited.graphic_spans)

    with pytest.raises(ValueError, match="word timings don't match the script"):
        assemble_shot_list(
            segments, edited.plain_text, WORD_TIMINGS, _specs_for(segments), total_duration=3.6
        )


def test_assemble_shot_list_subdivides_long_plain_segments():
    long_script = "*Rome fell.* " + ("The empire crumbled slowly over centuries. " * 6)
    parsed = parse_markup(long_script)
    # 30 words after "Rome fell.", spread over 60 seconds => forces subdivision
    word_timings = [WordTiming("Rome", 0.0, 0.4), WordTiming("fell.", 0.4, 0.9)]
    words_after = parsed.plain_text.split()[2:]
    t = 0.9
    for w in words_after:
        word_timings.append(WordTiming(w, t, t + 2.0))
        t += 2.0

    segments, _ = prepare_director_input(parsed.plain_text, parsed.graphic_spans)
    director_specs = [
        {"type": "graphic", "archetype": "chart_card", "data": {"value": "476 AD"}},
        {"type": "footage", "query": "crumbling ruins", "subject": "the fall of Rome"},
    ]

    shot_list = assemble_shot_list(
        segments, parsed.plain_text, word_timings, director_specs, total_duration=t
    )

    validate_shot_list(shot_list)
    footage_beats = [b for b in shot_list.beats if b.type == "footage"]
    assert len(footage_beats) > 1  # the long plain segment got split into multiple cuts
    for beat in footage_beats:
        assert beat.footage.query == "crumbling ruins"  # all cuts share the segment's one idea
