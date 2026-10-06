# tests/fixtures/assembly_dry_run.py
"""Real end-to-end check of the final assembly pipeline. Generates tiny synthetic test clips
with ffmpeg's own lavfi sources (no real Pexels/YouTube/motion-graphics output needed), runs
the real normalize -> concat -> mux -> verify chain, and checks the real output artifact — per
this project's standing lesson that a script printing OK is not evidence anything happened."""
import os
import subprocess

from assembly.beats import BeatClip
from assembly.build import assemble

WORK_DIR = "tests/fixtures/assembly_dry_run_work"
STAGING_DIR = f"{WORK_DIR}/staging"
FINAL_PATH = f"{WORK_DIR}/final_output/assembled.mp4"
VOICEOVER_PATH = f"{WORK_DIR}/voiceover.wav"

# Each beat's TARGET duration (what the final video must contain) is deliberately different
# from its SOURCE clip's generated duration, so this dry run exercises both the trim path and
# the freeze-frame-pad path for real, not just the exact-match case — matching this plan's
# Review Focus item on exact-duration enforcement regardless of source length.
BEAT_DURATIONS = [3.0, 2.5, 4.0]          # target durations — sum must equal the voiceover length
SOURCE_DURATIONS = [5.0, 1.0, 4.0]        # beat 0: source LONGER than target (tests trim)
                                           # beat 1: source SHORTER than target (tests freeze-pad)
                                           # beat 2: source EXACTLY matches target (control case)
TOTAL_DURATION = sum(BEAT_DURATIONS)

os.makedirs(WORK_DIR, exist_ok=True)


def _make_synthetic_clip(path: str, duration: float, color: str, pix_fmt: str = None) -> None:
    """A small real video clip (no audio) — stands in for a real footage/graphic beat clip.

    `pix_fmt`, when given, forces a genuinely different real pixel format on this source clip
    (e.g. yuv444p or a 10-bit format) — proving normalize really re-encodes to a uniform format
    rather than just nominally matching width/height, per Finding 1 of the final review.
    """
    cmd = [
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", f"color=c={color}:s=640x360:d={duration}:r=25",
    ]
    if pix_fmt:
        cmd += ["-pix_fmt", pix_fmt]
    cmd.append(path)
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 0, f"failed to generate synthetic clip {path}: {result.stderr}"


def _make_voiceover(path: str, duration: float) -> None:
    cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=mono:d={duration}", path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 0, f"failed to generate synthetic voiceover: {result.stderr}"


print("Generating synthetic test clips (source durations deliberately mismatch target durations)...")
starts = [0.0]
for d in BEAT_DURATIONS[:-1]:
    starts.append(starts[-1] + d)

clips = []
colors = ["red", "green", "blue"]
# Beat 1's source is deliberately generated as yuv444p (not the default yuv420p) — a real,
# genuinely different pixel format standing in for e.g. a graphics-export RGB/yuv444p source or
# a 10-bit HDR YouTube download (Finding 1). This proves normalize() really re-encodes every
# clip to an identical, real yuv420p output rather than just nominally matching width/height.
source_pix_fmts = [None, "yuv444p", None]
for i, (start, target_duration, source_duration, color, source_pix_fmt) in enumerate(
    zip(starts, BEAT_DURATIONS, SOURCE_DURATIONS, colors, source_pix_fmts)
):
    source_path = f"{WORK_DIR}/source_beat_{i}.mp4"
    _make_synthetic_clip(source_path, source_duration, color, pix_fmt=source_pix_fmt)
    clips.append(BeatClip(
        index=i, start=start, end=start + target_duration,
        type="footage", source_path=source_path,
    ))

_make_voiceover(VOICEOVER_PATH, TOTAL_DURATION)

print(f"Running assemble() for real: {len(clips)} beats, {TOTAL_DURATION}s total")
final_path = assemble(
    clips=clips, audio_path=VOICEOVER_PATH, staging_dir=STAGING_DIR,
    final_path=FINAL_PATH, total_duration=TOTAL_DURATION,
)

size_bytes = os.path.getsize(final_path)
print(f"Assembled real video at {final_path}: {size_bytes} bytes")
assert size_bytes > 10_000, "assembled output suspiciously small for a real multi-second video"

# assemble() already calls verify_final_output internally — reaching here without an
# exception means it already passed. Print an independent probe as a human-readable summary.
probe = subprocess.run(
    ["ffprobe", "-v", "error", "-show_entries",
     "stream=codec_type,width,height:format=duration", "-of",
     "default=noprint_wrappers=1", FINAL_PATH],
    capture_output=True, text=True,
)
print(probe.stdout)

# Real, non-mocked proof of Finding 1's fix: even though one source clip (beat 1) was generated
# with a genuinely different real pixel format (yuv444p), the assembled output's ACTUAL pix_fmt
# (not just its nominal resolution) must be the uniform yuv420p normalize.py now forces —
# otherwise a container-copy concat of mismatched real formats would silently produce a file
# whose header only reflects the first segment.
pix_fmt_probe = subprocess.run(
    ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
     "stream=pix_fmt", "-of", "default=noprint_wrappers=1:nokey=1", FINAL_PATH],
    capture_output=True, text=True,
)
actual_pix_fmt = pix_fmt_probe.stdout.strip()
print(f"assembled output pix_fmt: {actual_pix_fmt}")
assert actual_pix_fmt == "yuv420p", (
    f"expected uniform yuv420p output despite mismatched real source pixel formats "
    f"(one source was yuv444p), got {actual_pix_fmt!r}"
)

print("assembly_dry_run: OK")
