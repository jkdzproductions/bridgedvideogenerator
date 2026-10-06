import pytest
from assembly.normalize import (
    TARGET_FPS, TARGET_HEIGHT, TARGET_WIDTH, NormalizeError,
    build_normalize_command, run_normalize,
)


def test_build_normalize_command_includes_scale_pad_fps_mute_and_duration():
    cmd = build_normalize_command("in.mp4", "out.mp4", target_duration=5.5)

    assert cmd[0:4] == ["ffmpeg", "-y", "-i", "in.mp4"]
    assert "-an" in cmd
    assert cmd[-1] == "out.mp4"

    filter_chain = cmd[cmd.index("-vf") + 1]
    assert f"scale={TARGET_WIDTH}:{TARGET_HEIGHT}" in filter_chain
    assert f"fps={TARGET_FPS}" in filter_chain
    assert "tpad=stop_mode=clone:stop_duration=5.5" in filter_chain
    assert "setsar=1" in filter_chain

    assert cmd[cmd.index("-t") + 1] == "5.5"

    assert cmd[cmd.index("-c:v") + 1] == "libx264"
    assert cmd[cmd.index("-pix_fmt") + 1] == "yuv420p"


def test_run_normalize_raises_on_ffmpeg_failure(monkeypatch):
    import assembly.normalize as normalize_mod

    class FakeResult:
        returncode = 1
        stderr = "Invalid data found when processing input"

    monkeypatch.setattr(normalize_mod.subprocess, "run", lambda *a, **kw: FakeResult())

    with pytest.raises(NormalizeError, match="Invalid data found"):
        run_normalize("bad.mp4", "out.mp4", target_duration=5.0)


def test_run_normalize_succeeds_without_raising(monkeypatch):
    import assembly.normalize as normalize_mod

    class FakeResult:
        returncode = 0
        stderr = ""

    calls = []
    monkeypatch.setattr(
        normalize_mod.subprocess, "run",
        lambda cmd, **kw: calls.append(cmd) or FakeResult(),
    )

    run_normalize("in.mp4", "out.mp4", target_duration=3.0)

    assert len(calls) == 1
    assert calls[0][-1] == "out.mp4"


import shutil
import subprocess

from assembly.normalize import build_black_clip_command, run_black_clip


def test_build_black_clip_command_uses_a_black_lavfi_source_at_the_target_format():
    cmd = build_black_clip_command("out.mp4", 5.5)

    assert cmd[:2] == ["ffmpeg", "-y"]
    source = cmd[cmd.index("-i") + 1]
    assert source == f"color=c=black:s={TARGET_WIDTH}x{TARGET_HEIGHT}:r={TARGET_FPS}"
    assert cmd[cmd.index("-f") + 1] == "lavfi"
    assert "-an" in cmd
    assert cmd[cmd.index("-t") + 1] == "5.5"
    assert cmd[cmd.index("-c:v") + 1] == "libx264"
    assert cmd[cmd.index("-pix_fmt") + 1] == "yuv420p"
    assert cmd[-1] == "out.mp4"


def test_run_black_clip_raises_on_ffmpeg_failure(monkeypatch):
    import assembly.normalize as normalize_mod

    class FakeResult:
        returncode = 1
        stderr = "boom"

    monkeypatch.setattr(normalize_mod.subprocess, "run", lambda *a, **kw: FakeResult())

    with pytest.raises(NormalizeError, match="boom"):
        run_black_clip("out.mp4", 5.0)


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_run_black_clip_makes_a_real_black_1080p_clip_of_the_right_length(tmp_path):
    dest = str(tmp_path / "black.mp4")

    run_black_clip(dest, 2.0)

    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,pix_fmt:format=duration", "-of", "csv=p=0", dest],
        capture_output=True, text=True, check=True).stdout.split()
    fields = probe[0].split(",")
    assert "1920" in fields and "1080" in fields and "yuv420p" in fields
    assert abs(float(probe[1]) - 2.0) < 0.1
    pixel = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", dest, "-frames:v", "1", "-vf", "scale=1:1,format=gray",
         "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
    assert pixel[0] <= 20  # black in limited-range video is 16
