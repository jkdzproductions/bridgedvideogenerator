"""End-to-end dry run of the shot-list pipeline against the real fixture (Task 10).

Runs the real Whisper alignment on tests/fixtures/audio.wav, segments the script, then
assembles and validates a full shot list. The director step is an Opus subagent spawned
from a Claude Code session (CLAUDE.md Step 4), so it can't run here — a canned director
response (one valid entry per segment) is fed through parse_director_output instead.
Everything else is the real code path.

Usage (after ./tests/fixtures/generate_fixture.sh):
    .venv/bin/python tests/fixtures/dry_run.py
"""
import json
from pathlib import Path

from shot_list.align import align_words
from shot_list.build import assemble_shot_list, prepare_director_input
from shot_list.director_output import parse_director_output
from shot_list.markup import parse_markup
from shot_list.models import validate_shot_list

FIXTURES = Path(__file__).parent


def _canned_director_response(segments) -> str:
    entries = []
    for i, s in enumerate(segments):
        if s.kind == "graphic":
            entries.append({"index": i, "type": "graphic", "archetype": "chart_card",
                            "data": {"text": s.text}})
        else:
            entries.append({"index": i, "type": "footage", "query": s.text[:40], "subject": s.text})
    return json.dumps({"count": len(segments), "entries": entries})


def main() -> None:
    parsed = parse_markup((FIXTURES / "script.txt").read_text())
    alignment = align_words(str(FIXTURES / "audio.wav"), parsed.plain_text)
    segments, _ = prepare_director_input(parsed.plain_text, parsed.graphic_spans)

    print(f"{len(alignment.words)} words aligned, audio duration {alignment.audio_duration:.3f}s")
    for t in alignment.words:
        print(f"  {t.start:6.2f}-{t.end:6.2f} {'   ' if t.matched else '(i)'} {t.word}")
    print(f"{len(segments)} segments:")
    for s in segments:
        print(f"  [{s.kind}] {s.text!r}")

    specs = parse_director_output(_canned_director_response(segments), segments)
    shot_list = assemble_shot_list(
        segments, parsed.plain_text, alignment.words, specs, alignment.audio_duration
    )
    validate_shot_list(shot_list)

    print(f"shot list: {len(shot_list.beats)} beats, duration {shot_list.duration:.3f}s")
    for b in shot_list.beats:
        print(f"  {b.start:7.3f}-{b.end:7.3f} {b.type}")
    print("validate_shot_list: OK")


if __name__ == "__main__":
    main()
