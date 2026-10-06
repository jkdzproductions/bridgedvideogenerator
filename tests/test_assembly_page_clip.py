import os
import shutil
import subprocess

import pytest

from assembly.beats import BeatClip, MissingClipsError, resolve_beat_clips
from assembly.build import normalize_all
from assembly.normalize import NormalizeError, build_page_clip_command, run_page_clip
from shot_list.models import Beat, PageSpec, ShotList

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def _png(path, color, size="1920x1080"):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"color=c={color}:s={size}",
                    "-frames:v", "1", path], check=True, capture_output=True)


def _probe(path, entries):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", entries,
                          "-of", "default=nw=1", path], capture_output=True, text=True, check=True).stdout
    return dict(line.split("=") for line in out.split())


def _page_shot_list():
    return ShotList(beats=[Beat(0.0, 4.0, "page_highlight", page=PageSpec(italic_index=2))], duration=4.0)


def test_command_layers_the_finished_still_over_the_plain_one_and_forces_the_duration():
    cmd = build_page_clip_command("page_stills/page_2.png", "page_stills/page_2_plain.png", "out.mp4", 3.4)

    assert cmd[0:2] == ["ffmpeg", "-y"]
    inputs = [cmd[i + 1] for i, c in enumerate(cmd) if c == "-i"]
    assert inputs == ["page_stills/page_2_plain.png", "page_stills/page_2.png"]
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert "fade=t=in:st=0.3:d=0.5:alpha=1" in graph and "zoompan" in graph and "setsar=1" in graph
    assert cmd[cmd.index("-t") + 1] == "3.4"
    assert "-an" in cmd and cmd[-1] == "out.mp4"


def test_run_page_clip_raises_on_ffmpeg_failure(monkeypatch):
    import assembly.normalize as normalize_mod

    class Failed:
        returncode = 1
        stderr = "No such file or directory"
    monkeypatch.setattr(normalize_mod.subprocess, "run", lambda *a, **kw: Failed())

    with pytest.raises(NormalizeError, match="No such file"):
        run_page_clip("a.png", "b.png", "out.mp4", 3.0)


@needs_ffmpeg
@pytest.mark.parametrize("duration", [3.4, 0.4, 4.699999999999999])
def test_page_clip_is_exactly_the_beat_duration_at_1920x1080(tmp_path, duration):
    _png(str(tmp_path / "plain.png"), "gray")
    _png(str(tmp_path / "final.png"), "green")
    dest = str(tmp_path / "out.mp4")

    run_page_clip(str(tmp_path / "final.png"), str(tmp_path / "plain.png"), dest, duration)

    info = _probe(dest, "stream=width,height,pix_fmt,r_frame_rate")
    assert (info["width"], info["height"], info["pix_fmt"], info["r_frame_rate"]) == ("1920", "1080", "yuv420p", "30/1")
    assert abs(float(_probe(dest, "format=duration")["duration"]) - duration) < 0.05


@needs_ffmpeg
def test_a_long_page_clip_past_the_zoom_cap_is_still_exactly_the_beat_duration(tmp_path):
    # the push-in zoom is capped at 1.06, which only bites after about 5.7 seconds
    _png(str(tmp_path / "plain.png"), "gray")
    _png(str(tmp_path / "final.png"), "green")
    dest = str(tmp_path / "out.mp4")

    run_page_clip(str(tmp_path / "final.png"), str(tmp_path / "plain.png"), dest, 7.0)

    info = _probe(dest, "stream=width,height")
    assert (info["width"], info["height"]) == ("1920", "1080")
    assert abs(float(_probe(dest, "format=duration")["duration"]) - 7.0) < 0.05


def test_resolve_beat_clips_returns_the_page_clip_with_its_still(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs("page_stills")
    for name in ("page_2.png", "page_2_plain.png"):
        (tmp_path / "page_stills" / name).write_bytes(b"x")

    assert resolve_beat_clips(_page_shot_list()) == [
        BeatClip(index=0, start=0.0, end=4.0, type="page_highlight", source_path="page_stills/page_2.png")]


def test_resolve_beat_clips_lists_every_missing_still(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs("page_stills")
    (tmp_path / "page_stills" / "page_2.png").write_bytes(b"x")  # the plain still is missing

    with pytest.raises(MissingClipsError) as exc_info:
        resolve_beat_clips(_page_shot_list())

    assert "beat 0 (page_highlight): expected page_stills/page_2_plain.png" in str(exc_info.value)


@needs_ffmpeg
def test_normalize_all_builds_a_page_clip_from_the_stills(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs("page_stills")
    _png("page_stills/page_2.png", "green")
    _png("page_stills/page_2_plain.png", "gray")
    clips = [BeatClip(index=0, start=0.0, end=2.5, type="page_highlight", source_path="page_stills/page_2.png")]

    paths = normalize_all(clips, "staging")

    assert abs(float(_probe(paths[0], "format=duration")["duration"]) - 2.5) < 0.05
