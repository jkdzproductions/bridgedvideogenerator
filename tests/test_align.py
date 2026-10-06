import pytest
from shot_list.align import WordTiming, _align_to_script, align_words


def _recognize(words, start=0.0, step=0.4):
    """Whisper-style recognition: one dict per word, `step` seconds each, back to back."""
    return [{"word": w, "start": start + i * step, "end": start + (i + 1) * step} for i, w in enumerate(words)]


SCRIPT_20 = (
    "Tokyo built its first subway line in nineteen twenty seven and the network "
    "kept growing for almost a century afterward."
)


def test_align_to_script_matches_clean_recognition():
    recognized = [
        {"word": "The", "start": 0.0, "end": 0.2},
        {"word": "city", "start": 0.2, "end": 0.5},
        {"word": "grew", "start": 0.5, "end": 0.8},
        {"word": "fast.", "start": 0.8, "end": 1.2},
    ]
    script_text = "The city grew fast."

    timings = _align_to_script(recognized, script_text, audio_duration=1.5)

    assert [t.word for t in timings] == ["The", "city", "grew", "fast."]
    assert timings[0].start == 0.0
    assert timings[-1].end == 1.2
    assert all(t.matched for t in timings)


def test_align_to_script_handles_contractions_and_punctuation():
    recognized = [
        {"word": "It's", "start": 0.0, "end": 0.3},
        {"word": "not", "start": 0.3, "end": 0.5},
        {"word": "Tokyo's", "start": 0.5, "end": 0.9},
        {"word": "subway,", "start": 0.9, "end": 1.3},
    ]
    script_text = "It's not Tokyo's subway,"

    timings = _align_to_script(recognized, script_text, audio_duration=1.5)

    assert len(timings) == 4
    assert timings[2].word == "Tokyo's"
    assert timings[2].start == 0.5


def test_align_to_script_matches_curly_apostrophes_against_straight_ones():
    # real Versed scripts use typographic quotes; whisper emits straight ones
    recognized = _recognize(["It's", "not", "Tokyo's", "subway.", "They", "said", '"never."'])
    script_text = "It’s not Tokyo’s subway. They said “never.”"

    timings = _align_to_script(recognized, script_text, audio_duration=3.0)

    assert [t.word for t in timings] == script_text.split()
    assert all(t.matched for t in timings)
    assert timings[2].start == recognized[2]["start"]


def test_align_to_script_interpolates_missing_words():
    # whisper drops "quietly" entirely from recognition
    recognized = [
        {"word": "It", "start": 0.0, "end": 0.2},
        {"word": "grew", "start": 0.2, "end": 0.5},
        {"word": "fast.", "start": 1.0, "end": 1.4},
    ]
    script_text = "It grew quietly fast."

    timings = _align_to_script(recognized, script_text, audio_duration=1.6)

    assert [t.word for t in timings] == ["It", "grew", "quietly", "fast."]
    # interpolated word sits strictly between its neighbors, and is flagged as such
    assert timings[1].end <= timings[2].start <= timings[3].start
    assert [t.matched for t in timings] == [True, True, False, True]


def test_trailing_unrecognized_word_is_placed_inside_the_audio_not_past_it():
    recognized = _recognize("The network kept growing for almost a".split())  # "century." unheard
    script_text = "The network kept growing for almost a century."

    timings = _align_to_script(recognized, script_text, audio_duration=3.4)

    assert timings[-1].matched is False
    assert timings[-1].end <= 3.4


def test_align_to_script_raises_when_too_few_words_match():
    recognized = [{"word": "Completely", "start": 0.0, "end": 0.5},
                  {"word": "unrelated.", "start": 0.5, "end": 1.0}]
    script_text = "The city of Tokyo has thirty seven million people living in its metro area today."

    with pytest.raises(ValueError, match="alignment quality too low"):
        _align_to_script(recognized, script_text, audio_duration=1.0)


def test_short_script_with_no_matching_words_raises():
    # below the 5-word threshold of the ratio gate, but nothing matched at all
    with pytest.raises(ValueError, match="alignment quality too low"):
        _align_to_script(_recognize(["Hello", "there."]), "Goodbye now.", audio_duration=1.0)


def test_empty_script_raises():
    with pytest.raises(ValueError, match="no words"):
        _align_to_script(_recognize(["Hello"]), "   ", audio_duration=1.0)


def test_truncated_recording_at_55_percent_coverage_raises():
    # recording cut off after 11 of 20 words: passes the 50% match gate, but the last 9
    # script words were never spoken — they must not be extrapolated past the audio's end
    words = SCRIPT_20.split()
    assert len(words) == 20
    recognized = _recognize(words[:11])

    with pytest.raises(ValueError, match="alignment mismatch"):
        _align_to_script(recognized, SCRIPT_20, audio_duration=recognized[-1]["end"] + 0.1)


def test_recording_cut_off_a_few_words_early_raises():
    # only 2 words missing (below the run threshold), but the audio ends right after the
    # last recognized word, leaving no time in which those 2 words could have been spoken
    words = SCRIPT_20.split()
    recognized = _recognize(words[:18])

    with pytest.raises(ValueError, match="alignment mismatch.*after"):
        _align_to_script(recognized, SCRIPT_20, audio_duration=recognized[-1]["end"] + 0.05)


def test_long_run_of_unrecognized_words_mid_script_raises():
    words = (SCRIPT_20 + " " + SCRIPT_20).split()  # 40 words
    heard = words[:12] + ["something"] * 10 + words[22:]  # 10 script words replaced
    recognized = _recognize(heard)

    with pytest.raises(ValueError, match="alignment mismatch.*consecutive"):
        _align_to_script(recognized, " ".join(words), audio_duration=recognized[-1]["end"] + 0.3)


def test_audio_continuing_long_after_the_last_matched_word_raises():
    recognized = _recognize("The city grew fast and then slowed.".split())

    with pytest.raises(ValueError, match="alignment mismatch.*continues"):
        _align_to_script(recognized, "The city grew fast and then slowed.", audio_duration=20.0)


def test_align_words_returns_real_audio_duration_not_last_word_end(monkeypatch):
    import shot_list.align as align

    recognized = [{"word": "The", "start": 0.3, "end": 0.5}, {"word": "end.", "start": 0.5, "end": 0.9}]
    monkeypatch.setattr(align, "_run_whisper", lambda path: (recognized, 1.75))

    result = align.align_words("voiceover.wav", "The end.")

    assert result.audio_duration == 1.75  # real audio length, including the silent tail
    assert [t.word for t in result.words] == ["The", "end."]


def test_number_split_by_whisper_at_the_comma_matches_the_script_number():
    # whisper writes "156,000" as two tokens, "156" and ",000" (seen on a real voiceover)
    recognized = [
        {"word": "over", "start": 0.0, "end": 0.3},
        {"word": "156", "start": 0.3, "end": 0.9},
        {"word": ",000", "start": 0.9, "end": 1.3},
        {"word": "troops.", "start": 1.5, "end": 1.9},
    ]

    timings = _align_to_script(recognized, "over 156,000 troops.", audio_duration=2.0)

    assert [t.word for t in timings] == ["over", "156,000", "troops."]
    assert all(t.matched for t in timings)
    # the merged number spans both tokens
    assert timings[1].start == 0.3 and timings[1].end == 1.3


def test_decimal_split_by_whisper_matches_the_script_number():
    recognized = [
        {"word": "It", "start": 0.0, "end": 0.2},
        {"word": "is", "start": 0.2, "end": 0.4},
        {"word": "3", "start": 0.4, "end": 0.7},
        {"word": ".8", "start": 0.7, "end": 1.0},
        {"word": "million.", "start": 1.0, "end": 1.5},
    ]

    timings = _align_to_script(recognized, "It is 3.8 million.", audio_duration=1.6)

    assert all(t.matched for t in timings)


def test_ordinary_words_and_numbers_are_not_merged():
    # a comma after a number and a separate number must stay two words
    recognized = [
        {"word": "In", "start": 0.0, "end": 0.2},
        {"word": "1944,", "start": 0.2, "end": 0.7},
        {"word": "500", "start": 0.7, "end": 1.0},
        {"word": "ships", "start": 1.0, "end": 1.4},
        {"word": "sailed.", "start": 1.4, "end": 1.9},
    ]

    timings = _align_to_script(recognized, "In 1944, 500 ships sailed.", audio_duration=2.0)

    assert [t.word for t in timings] == ["In", "1944,", "500", "ships", "sailed."]
    assert all(t.matched for t in timings)


def test_currency_and_unit_numbers_split_by_whisper_are_joined():
    recognized = [
        {"word": "costs", "start": 0.0, "end": 0.3},
        {"word": "$5", "start": 0.3, "end": 0.6},
        {"word": ",000", "start": 0.6, "end": 0.9},
        {"word": "or", "start": 0.9, "end": 1.0},
        {"word": "3", "start": 1.0, "end": 1.2},
        {"word": ".8%", "start": 1.2, "end": 1.5},
    ]

    timings = _align_to_script(recognized, "costs $5,000 or 3.8%", audio_duration=1.6)

    assert all(t.matched for t in timings)


def test_sentence_final_number_is_not_merged_with_a_following_decimal_token():
    recognized = [
        {"word": "Of", "start": 0.0, "end": 0.2},
        {"word": "5.", "start": 0.2, "end": 0.5},
        {"word": ".25", "start": 0.5, "end": 0.9},
    ]

    timings = _align_to_script(recognized, "Of 5. .25", audio_duration=1.0)

    assert [t.word for t in timings] == ["Of", "5.", ".25"]
    assert all(t.matched for t in timings)


def test_comma_digits_token_after_a_plain_word_is_not_merged():
    recognized = [
        {"word": "word", "start": 0.0, "end": 0.3},
        {"word": ",000", "start": 0.3, "end": 0.6},
    ]

    timings = _align_to_script(recognized, "word ,000", audio_duration=0.7)

    assert all(t.matched for t in timings)
