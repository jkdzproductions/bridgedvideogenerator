import os
import shutil
import subprocess

import pytest

from assembly.beats import BeatClip, MissingClipsError, resolve_beat_clips
from assembly.build import normalize_all
from assembly.normalize import (
    NormalizeError, build_image_clip_command, build_image_frame_command, run_image_clip)
from shot_list.models import Beat, ImageSpec, ShotList

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def _solid(path, color, size, extra=()):
    result = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"color=c={color}:s={size}",
         "-frames:v", "1", *extra, path], capture_output=True)
    return result.returncode == 0


def _probe(path, entries):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", entries,
                          "-of", "default=nw=1", path], capture_output=True, text=True, check=True).stdout
    return dict(line.split("=") for line in out.split())


def _image_shot_list(index=3):
    return ShotList(beats=[Beat(0.0, 4.0, "image", image=ImageSpec(italic_index=index))], duration=4.0)


def test_frame_command_blurs_a_copy_behind_and_centers_the_sharp_original():
    cmd = build_image_frame_command("image_stills/image_3.jpg", "frame.png")

    assert cmd[0:2] == ["ffmpeg", "-y"]
    assert cmd[cmd.index("-i") + 1] == "image_stills/image_3.jpg"
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert "split=2" in graph and "boxblur" in graph and "eq=brightness" in graph
    assert "force_original_aspect_ratio=increase" in graph      # the background fills the frame
    assert "force_original_aspect_ratio=decrease" in graph      # the original fits inside it
    assert "overlay=(W-w)/2:(H-h)/2" in graph
    assert cmd[cmd.index("-frames:v") + 1] == "1" and cmd[-1] == "frame.png"


def test_clip_command_loops_the_frame_with_the_page_push_in_and_forces_the_duration():
    cmd = build_image_clip_command("frame.png", "out.mp4", 3.4)

    inputs = [cmd[i + 1] for i, c in enumerate(cmd) if c == "-i"]
    assert inputs == ["frame.png"]
    assert "-loop" in cmd
    graph = cmd[cmd.index("-vf") + 1]
    assert "zoompan" in graph and "setsar=1" in graph and "min(1+0.00035*on,1.06)" in graph
    assert cmd[cmd.index("-t") + 1] == "3.4"
    assert "-an" in cmd and cmd[-1] == "out.mp4"


def test_run_image_clip_raises_on_ffmpeg_failure(monkeypatch, tmp_path):
    import assembly.normalize as normalize_mod

    class Failed:
        returncode = 1
        stderr = "No such file or directory"
    monkeypatch.setattr(normalize_mod.subprocess, "run", lambda *a, **kw: Failed())

    with pytest.raises(NormalizeError, match="No such file"):
        run_image_clip("a.png", str(tmp_path / "out.mp4"), 3.0)


@needs_ffmpeg
@pytest.mark.parametrize("size,duration", [("570x631", 3.4), ("570x631", 0.4), ("1600x900", 4.699999999999999)])
def test_image_clip_is_exactly_the_beat_duration_at_1920x1080(tmp_path, size, duration):
    _solid(str(tmp_path / "in.png"), "red", size)
    dest = str(tmp_path / "out.mp4")

    run_image_clip(str(tmp_path / "in.png"), dest, duration)

    info = _probe(dest, "stream=width,height,pix_fmt,r_frame_rate")
    assert (info["width"], info["height"], info["pix_fmt"], info["r_frame_rate"]) == ("1920", "1080", "yuv420p", "30/1")
    assert abs(float(_probe(dest, "format=duration")["duration"]) - duration) < 0.05


@needs_ffmpeg
def test_a_long_image_clip_past_the_zoom_cap_is_still_exactly_the_beat_duration(tmp_path):
    _solid(str(tmp_path / "in.png"), "red", "570x631")
    dest = str(tmp_path / "out.mp4")

    run_image_clip(str(tmp_path / "in.png"), dest, 7.0)

    assert abs(float(_probe(dest, "format=duration")["duration"]) - 7.0) < 0.05


@needs_ffmpeg
def test_a_portrait_image_sits_sharp_in_the_middle_over_a_darker_blurred_copy(tmp_path):
    PIL_Image = pytest.importorskip("PIL.Image")
    _solid(str(tmp_path / "in.png"), "red", "570x631")
    frame = tmp_path / "out_frame.png"

    run_image_clip(str(tmp_path / "in.png"), str(tmp_path / "out.mp4"), 1.0)

    pixels = PIL_Image.open(frame).convert("RGB")
    assert pixels.size == (1920, 1080)
    center, side = pixels.getpixel((960, 540)), pixels.getpixel((20, 540))
    assert center[0] > 200 and center[1] < 60                 # the image itself, still red
    assert side[0] < center[0] - 80                           # the side bar is the darkened blur


@needs_ffmpeg
def test_a_gif_uses_its_first_frame(tmp_path):
    assert _solid(str(tmp_path / "in.gif"), "blue", "64x64")
    dest = str(tmp_path / "out.mp4")

    run_image_clip(str(tmp_path / "in.gif"), dest, 2.0)

    assert abs(float(_probe(dest, "format=duration")["duration"]) - 2.0) < 0.05


@needs_ffmpeg
def test_a_webp_image_works(tmp_path):
    if not _solid(str(tmp_path / "in.webp"), "green", "64x64"):
        pytest.skip("this ffmpeg build cannot encode webp")
    dest = str(tmp_path / "out.mp4")

    run_image_clip(str(tmp_path / "in.webp"), dest, 2.0)

    assert abs(float(_probe(dest, "format=duration")["duration"]) - 2.0) < 0.05


def test_resolve_beat_clips_returns_the_image_clip_with_its_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs("image_stills")
    (tmp_path / "image_stills" / "image_3.jpg").write_bytes(b"x")

    assert resolve_beat_clips(_image_shot_list()) == [
        BeatClip(index=0, start=0.0, end=4.0, type="image", source_path="image_stills/image_3.jpg")]


def test_resolve_beat_clips_lists_a_missing_image(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    with pytest.raises(MissingClipsError) as exc_info:
        resolve_beat_clips(_image_shot_list())

    assert "beat 0 (image): expected image_stills/image_3.*" in str(exc_info.value)


@needs_ffmpeg
def test_normalize_all_builds_an_image_clip_from_the_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs("image_stills")
    _solid("image_stills/image_3.png", "red", "570x631")
    clips = [BeatClip(index=0, start=0.0, end=2.5, type="image", source_path="image_stills/image_3.png")]

    paths = normalize_all(clips, "staging")

    assert abs(float(_probe(paths[0], "format=duration")["duration"]) - 2.5) < 0.05


@needs_ffmpeg
def test_a_transparent_png_is_flattened_onto_white_not_black(tmp_path):
    PIL_Image = pytest.importorskip("PIL.Image")
    from PIL import ImageDraw
    src = PIL_Image.new("RGBA", (570, 631), (0, 0, 0, 0))
    draw = ImageDraw.Draw(src)
    draw.rectangle([0, 0, 569, 630], outline=(0, 0, 0, 255), width=3)
    draw.rectangle([235, 265, 334, 364], fill=(255, 0, 0, 255))
    src.save(tmp_path / "in.png")
    dest = tmp_path / "out.mp4"

    run_image_clip(str(tmp_path / "in.png"), str(dest), 1.0)

    frame = PIL_Image.open(tmp_path / "out_frame.png").convert("RGB")
    assert frame.size == (1920, 1080)
    center, clear, side = frame.getpixel((960, 540)), frame.getpixel((960 - 250, 540)), frame.getpixel((20, 540))
    assert center[0] > 200 and center[1] < 60                 # the red square
    assert min(clear) > 200                                   # transparent area looks white
    assert side != (0, 0, 0) and 20 < side[0] < 235 and side[0] < min(clear)  # darkened blur of the white
    info = _probe(str(dest), "stream=width,height")
    assert (info["width"], info["height"]) == ("1920", "1080")
    assert abs(float(_probe(str(dest), "format=duration")["duration"]) - 1.0) < 0.05
