import difflib
import re
from dataclasses import dataclass


@dataclass
class WordTiming:
    word: str
    start: float
    end: float
    # True when the word was actually found in the recognized audio; False when its
    # timing was interpolated between matched neighbours (whisper dropped or misheard it).
    matched: bool = True


@dataclass
class Alignment:
    words: list[WordTiming]
    audio_duration: float  # real length of the audio file, not the last word's end


# --- Mismatch thresholds -------------------------------------------------------------
# Whisper routinely mis-transcribes a handful of script words (numbers written out vs.
# digits, names, contractions), so some interpolation is normal. What is NOT normal is the
# script and the audio disagreeing about a whole passage. These thresholds separate the two;
# anything past them means the audio doesn't match the script, and we fail loudly rather
# than invent timecodes (spec: "stop and report the mismatch rather than guessing").
#
# 8 consecutive unmatched script words is ~3s of narration at a typical 2.5-3 words/s —
# longer than any realistic mis-transcription (a number or name is 1-4 words), shorter
# than a sentence that was cut, re-worded, or never recorded.
MAX_INTERPOLATED_RUN = 8
# Unmatched words at the very start/end of the script have only the audio edge to bound
# them. If there is less than this much audio per such word, they physically can't have
# been spoken in it — the recording is cut off (or starts late). Fast speech is ~0.15s/word.
MIN_SECONDS_PER_EDGE_WORD = 0.1
# Audio continuing well past the last matched word means the recording holds speech the
# script doesn't (or the script is truncated). Allow a generous silent/music tail, plus
# time for any trailing words whisper misheard.
MAX_UNEXPLAINED_TAIL = 5.0
TAIL_ALLOWANCE_PER_TRAILING_WORD = 0.6
# A recognized word can't end after the audio does; allow a little timestamp slop.
TIMESTAMP_TOLERANCE = 0.5

_CURLY_TO_STRAIGHT = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"'})


def _normalize(word: str) -> str:
    # Versed scripts use typographic quotes (Tokyo’s); whisper emits straight ones
    # (Tokyo's). Straighten first, then strip surrounding punctuation.
    return word.translate(_CURLY_TO_STRAIGHT).lower().strip(".,!?\"'—-")


_NUMBER_TAIL = re.compile(r"^[,.]\d+[%a-z]*[.,!?]*$", re.IGNORECASE)
_NUMBER_HEAD = re.compile(r"^[$£€]?\d[\d,.]*\d$|^[$£€]?\d$")


def _merge_split_numbers(recognized: list[dict]) -> list[dict]:
    """Whisper often writes one number as two tokens ("156" + ",000", "3" + ".8"), while the
    script holds it as one word. Join a token that is just a comma/point plus digits onto the
    digit-ending token before it, so the number can match the script's single word."""
    merged: list[dict] = []
    for w in recognized:
        if merged and _NUMBER_TAIL.match(w["word"]) and _NUMBER_HEAD.match(merged[-1]["word"]):
            prev = merged[-1]
            merged[-1] = {"word": prev["word"] + w["word"], "start": prev["start"], "end": w["end"]}
        else:
            merged.append(w)
    return merged


def _align_to_script(
    recognized: list[dict], script_text: str, *, audio_duration: float
) -> list[WordTiming]:
    script_words = script_text.split()
    if not script_words:
        raise ValueError("script has no words to align")
    recognized = _merge_split_numbers(recognized)
    recognized_norm = [_normalize(w["word"]) for w in recognized]
    script_norm = [_normalize(w) for w in script_words]

    matcher = difflib.SequenceMatcher(a=recognized_norm, b=script_norm, autojunk=False)
    matched_blocks = matcher.get_matching_blocks()

    matched_word_count = sum(block.size for block in matched_blocks)
    if matched_word_count == 0 or (
        len(script_words) >= 5 and matched_word_count / len(script_words) < 0.5
    ):
        raise ValueError(
            f"alignment quality too low: only {matched_word_count}/{len(script_words)} "
            "script words matched the recognized audio"
        )

    timings: list[WordTiming | None] = [None] * len(script_words)
    for block in matched_blocks:
        for i in range(block.size):
            r_idx = block.a + i
            s_idx = block.b + i
            timings[s_idx] = WordTiming(
                word=script_words[s_idx],
                start=float(recognized[r_idx]["start"]),
                end=float(recognized[r_idx]["end"]),
            )

    _check_for_mismatch(timings, script_words, audio_duration)
    _fill_gaps(timings, script_words, audio_duration)
    return timings  # type: ignore[return-value]


def _check_for_mismatch(
    timings: list["WordTiming | None"], script_words: list[str], audio_duration: float
) -> None:
    matched_idx = [i for i, t in enumerate(timings) if t is not None]
    first, last = matched_idx[0], matched_idx[-1]

    # longest run of consecutive unmatched script words
    run_start, run_len, cur_start, cur_len = 0, 0, 0, 0
    for i, t in enumerate(timings):
        if t is None:
            if cur_len == 0:
                cur_start = i
            cur_len += 1
            if cur_len > run_len:
                run_start, run_len = cur_start, cur_len
        else:
            cur_len = 0
    if run_len > MAX_INTERPOLATED_RUN:
        passage = " ".join(script_words[run_start:run_start + run_len])
        raise ValueError(
            f"alignment mismatch: {run_len} consecutive script words (words {run_start}-"
            f"{run_start + run_len - 1}) were not found in the audio: {passage!r}"
        )

    last_end = timings[last].end  # type: ignore[union-attr]
    if last_end > audio_duration + TIMESTAMP_TOLERANCE:
        raise ValueError(
            f"alignment mismatch: recognized speech ends at {last_end:.2f}s but the audio is "
            f"only {audio_duration:.2f}s long"
        )

    leading = first
    if leading and timings[first].start / leading < MIN_SECONDS_PER_EDGE_WORD:  # type: ignore[union-attr]
        raise ValueError(
            f"alignment mismatch: the first {leading} script words were not found in the "
            f"audio and there is no time before {timings[first].start:.2f}s for them to "
            "have been spoken — the recording may start mid-script"
        )

    trailing = len(timings) - 1 - last
    if trailing and (audio_duration - last_end) / trailing < MIN_SECONDS_PER_EDGE_WORD:
        raise ValueError(
            f"alignment mismatch: the last {trailing} script words were not found in the "
            f"audio and there is no time after {last_end:.2f}s (audio ends at "
            f"{audio_duration:.2f}s) for them to have been spoken — the recording may be "
            "truncated"
        )

    tail = audio_duration - last_end
    if tail > MAX_UNEXPLAINED_TAIL + TAIL_ALLOWANCE_PER_TRAILING_WORD * trailing:
        raise ValueError(
            f"alignment mismatch: the audio continues {tail:.1f}s after the last matched "
            f"script word ({script_words[last]!r} ends at {last_end:.2f}s) — the audio may "
            "contain speech that isn't in the script, or the script may be truncated"
        )


def _fill_gaps(
    timings: list["WordTiming | None"], script_words: list[str], audio_duration: float
) -> None:
    """Interpolate unmatched words evenly between their matched neighbours (or the audio's
    start/end), flagging them matched=False. Never places a word outside the audio."""
    n = len(timings)
    i = 0
    while i < n:
        if timings[i] is not None:
            i += 1
            continue
        j = i
        while j < n and timings[j] is None:
            j += 1
        prev_end = timings[i - 1].end if i > 0 else 0.0
        next_start = timings[j].start if j < n else audio_duration
        span = max(next_start - prev_end, 0.01)
        step = span / (j - i + 1)
        for k in range(i, j):
            start = prev_end + step * (k - i)
            timings[k] = WordTiming(
                word=script_words[k], start=start, end=start + step * 0.8, matched=False
            )
        i = j


def _run_whisper(audio_path: str) -> tuple[list[dict], float]:
    """Returns (recognized words, real audio duration in seconds).

    The audio is decoded once with whisper's own loader (ffmpeg -> 16 kHz mono), so the
    duration comes from the same samples the model hears and works for any format ffmpeg
    reads (wav, mp3, ...), not just PCM WAV.
    """
    import whisper

    audio = whisper.audio.load_audio(audio_path)
    duration = len(audio) / whisper.audio.SAMPLE_RATE

    model = whisper.load_model("base")
    result = model.transcribe(audio, word_timestamps=True)
    words: list[dict] = []
    for segment in result["segments"]:
        for w in segment["words"]:
            words.append({"word": w["word"].strip(), "start": float(w["start"]), "end": float(w["end"])})
    return words, float(duration)


def align_words(audio_path: str, script_text: str) -> Alignment:
    recognized, audio_duration = _run_whisper(audio_path)
    return Alignment(
        words=_align_to_script(recognized, script_text, audio_duration=audio_duration),
        audio_duration=audio_duration,
    )
