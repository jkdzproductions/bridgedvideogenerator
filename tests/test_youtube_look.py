import os
import subprocess

import pytest

from footage.youtube_download import probe_video_dimensions
from footage.youtube_look import (
    GRAIN_STRENGTH,
    VIGNETTE_STRENGTH,
    ZOOM,
    YouTubeLookError,
    apply_youtube_look,
    build_look_command,
)


def _make_clip(path, seconds=1.0, width=640, height=360):
    """Red left half, blue right half, so a mirror image is easy to detect."""
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=blue:s={width}x{height}:r=30:d={seconds}",
         "-vf", f"drawbox=x=0:y=0:w={width // 2}:h={height}:color=red:t=fill",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)],
        check=True, capture_output=True,
    )


def _pixel(path, x, y):
    out = subprocess.run(
        ["ffmpeg", "-i", str(path), "-vf", f"crop=2:2:{x}:{y}", "-frames:v", "1",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        check=True, capture_output=True,
    ).stdout
    return tuple(out[:3])


def _duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        check=True, capture_output=True, text=True,
    ).stdout
    return float(out)


def test_command_mirrors_zooms_slightly_and_adds_light_grain():
    cmd = build_look_command("in.mp4", "out.mp4", 1920, 1080)
    chain = cmd[cmd.index("-vf") + 1]
    assert chain.startswith("hflip,")
    assert "crop=1864:1048," in chain  # 1920/1.03 and 1080/1.03, kept even
    assert "scale=1920:1080" in chain  # back to the original size
    assert f"noise=alls={GRAIN_STRENGTH}:allf=t" in chain
    assert f"blend=all_opacity={VIGNETTE_STRENGTH}" in chain and "vignette=" in chain
    assert VIGNETTE_STRENGTH == 0.5  # half strength, as Josh picked
    assert ZOOM == pytest.approx(1.03)
    assert 0 < GRAIN_STRENGTH <= 8  # "very subtle"
    assert "-an" in cmd and "-t" not in cmd  # keeps the clip's length


def test_apply_look_really_mirrors_and_keeps_size_and_length(tmp_path):
    clip = tmp_path / "beat_0.mp4"
    _make_clip(clip)
    before = (probe_video_dimensions(str(clip)), _duration(clip))

    result = apply_youtube_look(str(clip))

    assert result == str(clip)
    assert probe_video_dimensions(str(clip)) == before[0]
    assert _duration(clip) == pytest.approx(before[1], abs=0.1)
    left, right = _pixel(clip, 20, 180), _pixel(clip, 620, 180)
    assert left[2] > left[0] and right[0] > right[2]  # now blue on the left, red on the right
    assert not (tmp_path / "beat_0.look.mp4").exists()  # no leftover work file


def test_apply_look_changes_the_pixels(tmp_path):
    clip = tmp_path / "beat_0.mp4"
    _make_clip(clip)
    before = clip.read_bytes()
    apply_youtube_look(str(clip))
    assert clip.read_bytes() != before


def test_apply_look_failure_deletes_the_clip_and_the_work_file(tmp_path):
    clip = tmp_path / "beat_0.mp4"
    clip.write_bytes(b"not a video")
    with pytest.raises(YouTubeLookError):
        apply_youtube_look(str(clip))
    # A leftover beat_<n>.mp4 would be treated as a finished beat on resume.
    assert not clip.exists()
    assert not (tmp_path / "beat_0.look.mp4").exists()


def test_apply_look_darkens_the_corners_but_not_the_centre(tmp_path):
    clip = tmp_path / "beat_0.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=0x9a9a9a:s=640x360:r=30:d=1",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clip)],
        check=True, capture_output=True,
    )
    apply_youtube_look(str(clip))
    centre, corner = _pixel(clip, 319, 179), _pixel(clip, 2, 2)
    assert sum(corner) < sum(centre) - 60  # clearly darker in the corner...
    assert sum(centre) > 3 * 0x9a - 30  # ...while the middle is left (nearly) as it was
