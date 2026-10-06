# tests/test_archival_render.py
import os
import shutil
import subprocess

import pytest

import footage.archival_render as render
from footage.archival_render import (
    ArchivalRenderError, build_film_command, build_frame_command, film_frame_times, film_start_offset, photo_shares, render_film_beat, render_photo_beat,
)
from footage.archive_types import ArchiveCandidate

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


@pytest.mark.parametrize("total,count,expected", [
    (2.5, 3, [2.5]),                 # too short for two 2 s photos: exactly one
    (3.9, 3, [3.9]),
    (4.0, 3, [2.0, 2.0]),
    (6.0, 3, [2.0, 2.0, 2.0]),
    (6.0, 2, [3.0, 3.0]),            # never more photos than were picked
    (5.0, 1, [5.0]),
    (1.0, 2, [1.0]),                 # a very short cut still gets its one photo
])
def test_photo_shares_never_make_a_photo_shorter_than_two_seconds_unless_the_cut_itself_is(total, count, expected):
    assert photo_shares(total, count) == pytest.approx(expected)


def test_film_starts_20_percent_in_so_it_skips_leader_and_titles_but_always_has_room_for_the_cut():
    assert film_start_offset(100.0, 5.0) == pytest.approx(20.0)
    assert film_start_offset(10.0, 5.0) == pytest.approx(2.0)
    assert film_start_offset(6.0, 5.0) == pytest.approx(1.0)       # only 1 s of room before the cut would run out
    assert film_start_offset(5.0, 5.0) == 0.0


def test_the_film_command_seeks_before_the_input_and_reuses_the_normalize_filters():
    cmd = build_film_command("https://archive.org/download/r/a.mp4", "out.mp4", 5.0, 100.0)

    assert cmd[:4] == ["ffmpeg", "-y", "-ss", "20.00"]
    assert cmd[4:6] == ["-i", "https://archive.org/download/r/a.mp4"]
    assert "scale=1920:1080" in cmd[cmd.index("-vf") + 1]
    assert cmd[cmd.index("-t") + 1] == "5.0" and "-an" in cmd and cmd[-1] == "out.mp4"


def _film(duration=100.0):
    return ArchiveCandidate("ia", "reel", "film", "t", 1938, "", "pd", "p", "https://archive.org/download/reel/a.mp4",
                            "t", 640, 480, duration)


def test_render_film_beat_runs_ffmpeg_and_returns_the_destination(monkeypatch, tmp_path):
    seen = {}

    def fake_run(cmd, capture_output, text):
        seen["cmd"] = cmd
        open(cmd[-1], "wb").write(b"x")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(render.subprocess, "run", fake_run)
    dest = str(tmp_path / "beat_3.mp4")

    assert render_film_beat(_film(), dest, 5.0) == dest
    assert seen["cmd"][2:4] == ["-ss", "20.00"]


def test_a_failed_film_render_raises_and_leaves_no_partial_file(monkeypatch, tmp_path):
    def fake_run(cmd, capture_output, text):
        open(cmd[-1], "wb").write(b"partial")
        return subprocess.CompletedProcess(cmd, 1, "", "HTTP error 403")

    monkeypatch.setattr(render.subprocess, "run", fake_run)
    dest = str(tmp_path / "beat_3.mp4")

    with pytest.raises(ArchivalRenderError, match="403"):
        render_film_beat(_film(), dest, 5.0)
    assert not os.path.exists(dest)


def test_a_film_shorter_than_the_cut_is_refused_loudly(tmp_path):
    with pytest.raises(ArchivalRenderError, match="shorter"):
        render_film_beat(_film(duration=3.0), str(tmp_path / "x.mp4"), 5.0)


def test_one_photo_is_rendered_straight_to_the_destination(monkeypatch, tmp_path):
    clips = []

    def fake_clip(source, dest, duration):
        clips.append((source, duration))
        open(dest, "wb").write(b"c")

    monkeypatch.setattr(render, "run_image_clip", fake_clip)
    monkeypatch.setattr(render, "run_concat", lambda *a, **k: pytest.fail("one photo needs no concat"))
    dest = str(tmp_path / "beat_1.mp4")

    assert render_photo_beat(["a.jpg", "b.jpg"], dest, 3.0, str(tmp_path / "work")) == dest
    assert clips == [("a.jpg", 3.0)] and os.path.exists(dest)       # a 3 s cut uses only the first photo


def test_several_photos_are_rendered_and_concatenated_in_order(monkeypatch, tmp_path):
    clips, concat = [], {}

    def fake_clip(source, dest, duration):
        clips.append((os.path.basename(source), duration))
        open(dest, "wb").write(b"c")

    def fake_concat(paths, dest, list_file):
        concat.update(paths=[os.path.basename(p) for p in paths])
        open(dest, "wb").write(b"all")

    monkeypatch.setattr(render, "run_image_clip", fake_clip)
    monkeypatch.setattr(render, "run_concat", fake_concat)
    dest = str(tmp_path / "beat_2.mp4")

    render_photo_beat(["a.jpg", "b.jpg", "c.jpg"], dest, 6.0, str(tmp_path / "work"))

    assert clips == [("a.jpg", 2.0), ("b.jpg", 2.0), ("c.jpg", 2.0)]
    assert concat["paths"] == ["photo_0.mp4", "photo_1.mp4", "photo_2.mp4"]
    assert open(dest, "rb").read() == b"all"


def test_a_failed_photo_render_leaves_no_partial_destination(monkeypatch, tmp_path):
    def fake_clip(source, dest, duration):
        raise RuntimeError("ffmpeg image clip failed")

    monkeypatch.setattr(render, "run_image_clip", fake_clip)
    dest = tmp_path / "beat_1.mp4"
    dest.write_bytes(b"stale")

    with pytest.raises(RuntimeError):
        render_photo_beat(["a.jpg"], str(dest), 3.0, str(tmp_path / "work"))
    assert not dest.exists()


@needs_ffmpeg
def test_real_ffmpeg_renders_two_photos_into_one_1920x1080_clip_of_the_right_length(tmp_path):
    for name, color in (("a.png", "red"), ("b.png", "blue")):
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"color=c={color}:s=1200x800",
                        "-frames:v", "1", str(tmp_path / name)], check=True)
    dest = str(tmp_path / "beat.mp4")

    render_photo_beat([str(tmp_path / "a.png"), str(tmp_path / "b.png")], dest, 4.0, str(tmp_path / "work"))

    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height:format=duration", "-of", "default=nw=1", dest],
                         capture_output=True, text=True, check=True).stdout
    values = dict(line.split("=") for line in out.split())
    assert (values["width"], values["height"]) == ("1920", "1080")
    assert float(values["duration"]) == pytest.approx(4.0, abs=0.2)


def test_an_empty_photo_list_raises_and_writes_nothing(tmp_path):
    work = tmp_path / "work"
    with pytest.raises(ArchivalRenderError, match="no photos"):
        render_photo_beat([], str(tmp_path / "b.mp4"), 3.0, str(work))
    assert not work.exists() and not (tmp_path / "b.mp4").exists()


@pytest.mark.parametrize("bad", [0, 0.0, -2.0])
def test_a_zero_or_negative_duration_is_refused_for_photos_and_film(tmp_path, bad):
    with pytest.raises(ArchivalRenderError, match="duration"):
        render_photo_beat(["a.jpg"], str(tmp_path / "p.mp4"), bad, str(tmp_path / "work"))
    with pytest.raises(ArchivalRenderError, match="duration"):
        render_film_beat(_film(), str(tmp_path / "f.mp4"), bad)
    assert not (tmp_path / "work").exists() and not (tmp_path / "p.mp4").exists() and not (tmp_path / "f.mp4").exists()


def test_ffmpeg_missing_becomes_an_archival_render_error_with_no_file_left(monkeypatch, tmp_path):
    def fake_run(cmd, capture_output, text):
        raise FileNotFoundError("ffmpeg")

    monkeypatch.setattr(render.subprocess, "run", fake_run)
    dest = tmp_path / "beat.mp4"
    with pytest.raises(ArchivalRenderError, match="ffmpeg"):
        render_film_beat(_film(), str(dest), 5.0)
    assert not dest.exists()


def _fake_clip_and_concat(monkeypatch):
    def fake_clip(source, dest, duration):
        open(dest, "wb").write(b"c")

    def fake_concat(paths, dest, list_file):
        open(dest, "wb").write(b"all")

    monkeypatch.setattr(render, "run_image_clip", fake_clip)
    monkeypatch.setattr(render, "run_concat", fake_concat)


@pytest.mark.parametrize("photos,duration", [(["a.jpg"], 3.0), (["a.jpg", "b.jpg"], 4.0)])
def test_photo_beat_creates_a_missing_destination_directory(monkeypatch, tmp_path, photos, duration):
    # Stage 2 Step 1 deletes footage_output/; an all-archival video has nothing else to recreate it.
    _fake_clip_and_concat(monkeypatch)
    dest = str(tmp_path / "footage_output" / "nested" / "beat_3.mp4")

    assert render_photo_beat(photos, dest, duration, str(tmp_path / "work")) == dest
    assert os.path.exists(dest)


@needs_ffmpeg
def test_real_ffmpeg_photo_beat_into_a_missing_directory(tmp_path):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=red:s=1200x800",
                    "-frames:v", "1", str(tmp_path / "a.png")], check=True)
    dest = str(tmp_path / "footage_output" / "beat_3.mp4")

    render_photo_beat([str(tmp_path / "a.png")], dest, 3.0, str(tmp_path / "work"))

    assert os.path.getsize(dest) > 0


def test_film_frame_times_are_three_sorted_times_inside_the_played_segment():
    times = film_frame_times(100.0, 6.0)

    assert times == pytest.approx([20.0, 23.0, 25.5])
    assert times == sorted(times) and all(20.0 <= t <= 26.0 for t in times)


@pytest.mark.parametrize("duration,target", [(6.0, 5.0), (5.0, 5.0), (3.0, 3.0), (10.0, 0.3)])
def test_film_frame_times_are_clamped_inside_the_film_for_short_films(duration, target):
    start = film_start_offset(duration, target)
    times = film_frame_times(duration, target)

    assert len(times) == 3 and times == sorted(times)
    assert all(start <= t <= min(start + target, duration) for t in times)


def test_the_frame_command_seeks_before_the_input_and_writes_one_scaled_frame():
    cmd = build_frame_command("https://archive.org/download/r/a.mp4", 23.0, "/w/a_1.jpg")

    assert cmd == ["ffmpeg", "-y", "-ss", "23.00", "-i", "https://archive.org/download/r/a.mp4",
                   "-frames:v", "1", "-vf", "scale=640:-2", "/w/a_1.jpg"]


@needs_ffmpeg
def test_real_ffmpeg_extracts_a_frame_from_a_local_video(tmp_path):
    video = str(tmp_path / "v.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=1280x720:rate=10",
                    "-t", "4", video], check=True)
    out = str(tmp_path / "f.jpg")

    result = subprocess.run(build_frame_command(video, 1.0, out), capture_output=True, text=True)

    assert result.returncode == 0 and os.path.getsize(out) > 0
