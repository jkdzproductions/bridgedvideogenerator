import os
import shutil
import subprocess

import pytest

from assembly.beats import resolve_beat_clips
from assembly.build import assemble
from shot_list.models import Beat, FootageSpec, GraphicSpec, ShotList

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def _run(*args):
    subprocess.run(list(args), check=True, capture_output=True)


def _color_clip(path, color, seconds):
    _run("ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c={color}:s=640x360:r=30",
         "-t", str(seconds), "-c:v", "libx264", "-pix_fmt", "yuv420p", path)


def _mean_luma_at(video, seconds):
    out = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", str(seconds), "-i", video, "-frames:v", "1",
         "-vf", "scale=1:1,format=gray", "-f", "rawvideo", "-"],
        capture_output=True, check=True).stdout
    return out[0]


def test_talking_head_span_is_black_in_the_final_video_between_real_clips(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs("footage_output")
    os.makedirs("graphics_output")
    _color_clip("footage_output/beat_0.mp4", "white", 3)
    _color_clip("graphics_output/beat_2.mp4", "white", 3)
    _run("ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "9", "voice.wav")
    shot_list = ShotList(
        beats=[
            Beat(0.0, 3.0, "footage", footage=FootageSpec("q", "s")),
            Beat(3.0, 6.0, "talking_head"),
            Beat(6.0, 9.0, "graphic", graphic=GraphicSpec("territory_map", {"x": 1})),
        ],
        duration=9.0,
    )

    clips = resolve_beat_clips(shot_list)
    final = assemble(clips=clips, audio_path="voice.wav", staging_dir="assembly_staging",
                     final_path="final_output/assembled.mp4", total_duration=shot_list.duration)

    assert _mean_luma_at(final, 1.5) > 100   # footage beat (white)
    assert _mean_luma_at(final, 4.5) <= 20   # talking-head beat (black)
    assert _mean_luma_at(final, 7.5) > 100   # graphic beat (white)
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height", "-of", "csv=p=0", final], capture_output=True, text=True, check=True)
    assert probe.stdout.strip() == "1920,1080"
