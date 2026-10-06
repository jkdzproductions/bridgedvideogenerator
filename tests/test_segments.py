import pytest
from shot_list.align import WordTiming
from shot_list.markup import parse_markup
from shot_list.segments import segment_script, segment_time_range


def test_segment_script_alternates_plain_and_italic_in_order():
    plain_text = "The city grew fast. Population tripled in a decade. Then it slowed."
    italic_spans = [(20, 51)]  # "Population tripled in a decade."

    segments = segment_script(plain_text, italic_spans)

    assert [s.kind for s in segments] == ["plain", "graphic", "plain"]
    assert segments[1].text == "Population tripled in a decade."
    assert _words(segments) == plain_text.split()


def _words(segments):
    return [w for s in segments for w in s.text.split()]


def test_punctuation_just_outside_italic_belongs_to_one_segment_only():
    # "*Population tripled in a decade*. Then it slowed." -> "decade." straddles the italic edge
    parsed = parse_markup("The city grew fast. *Population tripled in a decade*. Then it slowed.")

    segments = segment_script(parsed.plain_text, parsed.graphic_spans)

    assert [s.kind for s in segments] == ["plain", "graphic", "plain"]
    assert segments[1].text == "Population tripled in a decade."
    assert segments[2].text == "Then it slowed."
    assert _words(segments) == parsed.plain_text.split()  # every word exactly once


def test_italic_ending_mid_word_keeps_the_word_whole():
    parsed = parse_markup("*Tokyo*'s subway is busy.")

    segments = segment_script(parsed.plain_text, parsed.graphic_spans)

    assert [(s.kind, s.text) for s in segments] == [("graphic", "Tokyo's"), ("plain", "subway is busy.")]


def test_back_to_back_italic_spans_produce_no_whitespace_segment():
    parsed = parse_markup("*Fact one.* *Fact two.*")

    segments = segment_script(parsed.plain_text, parsed.graphic_spans)

    assert [(s.kind, s.text) for s in segments] == [("graphic", "Fact one."), ("graphic", "Fact two.")]


def test_italic_span_with_no_whole_word_raises():
    # the italic span starts mid-word, so no word begins inside it — the graphic would vanish
    parsed = parse_markup("The city of Tok*yo* grew.")

    with pytest.raises(ValueError, match="contains no whole word"):
        segment_script(parsed.plain_text, parsed.graphic_spans)


def test_segment_time_range_does_not_let_neighbouring_segments_share_a_word():
    parsed = parse_markup("It grew. *Population tripled in a decade*. Then it slowed.")
    word_timings = [WordTiming(w, i * 1.0, i * 1.0 + 0.5) for i, w in enumerate(parsed.plain_text.split())]
    segments = segment_script(parsed.plain_text, parsed.graphic_spans)

    ranges = [segment_time_range(s, parsed.plain_text, word_timings) for s in segments]

    for (_, prev_end), (next_start, _) in zip(ranges, ranges[1:]):
        assert prev_end <= next_start


def test_segment_script_with_no_italic_spans_returns_single_plain_segment():
    plain_text = "This entire script is plain narration."
    segments = segment_script(plain_text, [])

    assert len(segments) == 1
    assert segments[0].kind == "plain"
    assert segments[0].text == plain_text


def test_segment_script_starting_with_italic_has_no_leading_empty_segment():
    plain_text = "Tokyo has 37 million people. It is dense."
    italic_spans = [(0, 29)]  # "Tokyo has 37 million people."

    segments = segment_script(plain_text, italic_spans)

    assert [s.kind for s in segments] == ["graphic", "plain"]


def test_segment_time_range_covers_the_segments_words():
    plain_text = "The city grew fast. Population tripled."
    word_timings = [
        WordTiming("The", 0.0, 0.2), WordTiming("city", 0.2, 0.5),
        WordTiming("grew", 0.5, 0.8), WordTiming("fast.", 0.8, 1.2),
        WordTiming("Population", 1.2, 1.8), WordTiming("tripled.", 1.8, 2.3),
    ]
    segments = segment_script(plain_text, [(20, 39)])  # "Population tripled."

    start, end = segment_time_range(segments[1], plain_text, word_timings)

    assert start == 1.2
    assert end == 2.3


def test_segment_time_range_raises_when_italic_text_not_in_audio():
    # What align_words really returns when italic text was added to the script after
    # recording: one timing per script word, but the italic span's words were never heard,
    # so all of their timings are interpolated (matched=False).
    plain_text = "The city grew fast. Population tripled in a decade. Then it slowed."
    word_timings = [
        WordTiming("The", 0.0, 0.2), WordTiming("city", 0.2, 0.5),
        WordTiming("grew", 0.5, 0.8), WordTiming("fast.", 0.8, 1.2),
        WordTiming("Population", 1.2, 1.24, matched=False),
        WordTiming("tripled", 1.25, 1.29, matched=False),
        WordTiming("in", 1.3, 1.34, matched=False),
        WordTiming("a", 1.35, 1.39, matched=False),
        WordTiming("decade.", 1.4, 1.44, matched=False),
        WordTiming("Then", 1.5, 1.7), WordTiming("it", 1.7, 1.8), WordTiming("slowed.", 1.8, 2.2),
    ]
    segments = segment_script(plain_text, [(20, 51)])

    with pytest.raises(ValueError, match="graphic segment .* was not spoken"):
        segment_time_range(segments[1], plain_text, word_timings)


def test_italic_segment_with_a_few_misheard_words_is_accepted():
    # whisper writes "fourteen" as "14", so that word is interpolated — the fact was spoken
    plain_text = "Fourteen million people ride daily."
    word_timings = [
        WordTiming("Fourteen", 0.0, 0.3, matched=False), WordTiming("million", 0.3, 0.6),
        WordTiming("people", 0.6, 0.9), WordTiming("ride", 0.9, 1.1), WordTiming("daily.", 1.1, 1.5),
    ]
    segments = segment_script(plain_text, [(0, len(plain_text))])

    assert segment_time_range(segments[0], plain_text, word_timings) == (0.0, 1.5)
