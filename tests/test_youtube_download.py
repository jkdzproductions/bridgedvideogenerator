import os
import pytest
from footage.youtube import YouTubeCandidate
from footage.youtube_download import (
    YouTubeDownloadError,
    download_youtube_clip,
    download_youtube_thumbnails,
)


def test_download_youtube_thumbnails_maps_video_id_to_absolute_path(tmp_path, monkeypatch):
    import footage.youtube_download as yt_download_mod

    monkeypatch.setattr(
        yt_download_mod, "download_file",
        lambda url, dest: open(dest, "wb").write(b"fake-jpg"),
    )

    candidates = [
        YouTubeCandidate("abc123", "Title A", "UC1", "Channel A", "https://img/a.jpg", 253.0),
        YouTubeCandidate("def456", "Title B", "UC2", "Channel B", "https://img/b.jpg", 120.0),
    ]

    paths = download_youtube_thumbnails(candidates, str(tmp_path))

    assert set(paths.keys()) == {"abc123", "def456"}
    for path in paths.values():
        assert os.path.isabs(path)
        assert os.path.exists(path)


def _install_fake_yt_dlp(monkeypatch, captured_opts, write_bytes=b"fake-mp4-bytes"):
    """Fake yt_dlp.YoutubeDL that records its opts and (optionally) writes the output file the
    way the real one would. write_bytes=None simulates a download that silently produces
    nothing."""
    import footage.youtube_download as yt_download_mod

    class FakeYoutubeDL:
        def __init__(self, opts):
            captured_opts.update(opts)

        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

        def download(self, urls):
            captured_opts["_downloaded_urls"] = urls
            if write_bytes is not None:
                with open(captured_opts["outtmpl"], "wb") as f:
                    f.write(write_bytes)

    fake_yt_dlp = type("FakeModule", (), {"YoutubeDL": FakeYoutubeDL})
    monkeypatch.setattr(yt_download_mod, "yt_dlp", fake_yt_dlp)


def test_download_youtube_clip_requests_only_the_needed_time_range(tmp_path, monkeypatch):
    captured_opts = {}
    _install_fake_yt_dlp(monkeypatch, captured_opts)
    dest = str(tmp_path / "beat_0.mp4")

    result = download_youtube_clip("abc123", dest, duration_seconds=15.0)

    assert result == dest
    assert captured_opts["_downloaded_urls"] == ["https://www.youtube.com/watch?v=abc123"]
    assert captured_opts["outtmpl"] == dest

    # Actually invoke the range callable the way yt-dlp does (info_dict, ydl) and check the
    # range that would really be requested — not just that some key is present.
    ranges = list(captured_opts["download_ranges"]({"id": "abc123"}, None))
    assert ranges == [{"start_time": 0, "end_time": 15.0}]
    assert captured_opts["force_keyframes_at_cuts"] is True


def test_download_youtube_clip_forces_overwrite_of_an_existing_file(tmp_path, monkeypatch):
    captured_opts = {}
    _install_fake_yt_dlp(monkeypatch, captured_opts)

    download_youtube_clip("abc123", str(tmp_path / "beat_0.mp4"), duration_seconds=5.0)

    # yt-dlp's default keeps an existing video file and reports success — must be off.
    assert captured_opts["overwrites"] is True


def test_download_youtube_clip_replaces_stale_file_content(tmp_path, monkeypatch):
    dest = tmp_path / "beat_0.mp4"
    dest.write_bytes(b"stale footage from some earlier video")
    _install_fake_yt_dlp(monkeypatch, {}, write_bytes=b"fresh footage")

    download_youtube_clip("abc123", str(dest), duration_seconds=5.0)

    assert dest.read_bytes() == b"fresh footage"


def test_download_youtube_clip_raises_if_a_stale_file_survives_a_no_op_download(tmp_path, monkeypatch):
    # A "successful" download call that writes nothing must not let a leftover file from an
    # earlier run pass as this video's clip.
    dest = tmp_path / "beat_0.mp4"
    dest.write_bytes(b"stale footage from some earlier video")
    _install_fake_yt_dlp(monkeypatch, {}, write_bytes=None)

    with pytest.raises(YouTubeDownloadError, match="no file was produced"):
        download_youtube_clip("abc123", str(dest), duration_seconds=5.0)

    assert not dest.exists()


def test_download_youtube_clip_raises_if_output_file_missing(tmp_path, monkeypatch):
    _install_fake_yt_dlp(monkeypatch, {}, write_bytes=None)

    with pytest.raises(YouTubeDownloadError, match="no file was produced"):
        download_youtube_clip("abc123", str(tmp_path / "beat_0.mp4"), duration_seconds=5.0)


def test_download_youtube_clip_raises_if_output_file_empty(tmp_path, monkeypatch):
    dest = tmp_path / "beat_0.mp4"
    _install_fake_yt_dlp(monkeypatch, {}, write_bytes=b"")

    with pytest.raises(YouTubeDownloadError, match="empty"):
        download_youtube_clip("abc123", str(dest), duration_seconds=5.0)

    assert not dest.exists()


def _fake_ffprobe(monkeypatch, stdout, returncode=0, stderr=""):
    import subprocess
    import footage.youtube_download as yt_download_mod

    calls = []

    def fake_run(cmd, capture_output, text):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, returncode, stdout=stdout, stderr=stderr)

    monkeypatch.setattr(yt_download_mod.subprocess, "run", fake_run)
    return calls


def test_probe_video_dimensions_reads_ffprobe_width_and_height(monkeypatch):
    from footage.youtube_download import probe_video_dimensions

    calls = _fake_ffprobe(monkeypatch, '{"streams": [{"width": 640, "height": 360, "tags": {}}]}')

    assert probe_video_dimensions("/x/beat_0.mp4") == (640, 360)
    assert calls[0][0] == "ffprobe"
    assert calls[0][-1] == "/x/beat_0.mp4"


def test_probe_video_dimensions_accounts_for_rotation_side_data(monkeypatch):
    from footage.youtube_download import probe_video_dimensions

    _fake_ffprobe(monkeypatch, '{"streams": [{"width": 1920, "height": 1080, "side_data_list": '
                               '[{"side_data_type": "Display Matrix", "rotation": -90}]}]}')

    assert probe_video_dimensions("/x/beat_0.mp4") == (1080, 1920)  # displayed as portrait


def test_probe_video_dimensions_accounts_for_legacy_rotate_tag(monkeypatch):
    from footage.youtube_download import probe_video_dimensions

    _fake_ffprobe(monkeypatch, '{"streams": [{"width": 1920, "height": 1080, "tags": {"rotate": "270"}}]}')

    assert probe_video_dimensions("/x/beat_0.mp4") == (1080, 1920)


def test_probe_video_dimensions_raises_when_ffprobe_fails(monkeypatch):
    from footage.youtube_download import probe_video_dimensions

    _fake_ffprobe(monkeypatch, "{}", returncode=1, stderr="No such file or directory")

    with pytest.raises(YouTubeDownloadError, match="ffprobe failed"):
        probe_video_dimensions("/x/missing.mp4")


def test_probe_video_dimensions_raises_when_no_video_stream(monkeypatch):
    from footage.youtube_download import probe_video_dimensions

    _fake_ffprobe(monkeypatch, '{"streams": []}')

    with pytest.raises(YouTubeDownloadError, match="no video stream"):
        probe_video_dimensions("/x/audio_only.mp4")


def test_probe_video_dimensions_raises_on_unreadable_output(monkeypatch):
    from footage.youtube_download import probe_video_dimensions

    _fake_ffprobe(monkeypatch, "not json")

    with pytest.raises(YouTubeDownloadError, match="could not read ffprobe output"):
        probe_video_dimensions("/x/beat_0.mp4")


def test_probe_video_dimensions_on_a_real_file(tmp_path):
    # Real ffprobe against a real (ffmpeg-generated) 320x180 file — not mocked.
    import shutil
    import subprocess
    from footage.youtube_download import probe_video_dimensions

    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("ffmpeg/ffprobe not installed")
    path = str(tmp_path / "landscape.mp4")
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=320x180:d=0.2",
         "-pix_fmt", "yuv420p", path],
        check=True,
    )

    assert probe_video_dimensions(path) == (320, 180)


def test_download_youtube_clip_wraps_failures(tmp_path, monkeypatch):
    import footage.youtube_download as yt_download_mod

    class FailingYoutubeDL:
        def __init__(self, opts):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

        def download(self, urls):
            raise RuntimeError("network error")

    fake_yt_dlp = type("FakeModule", (), {"YoutubeDL": FailingYoutubeDL})
    monkeypatch.setattr(yt_download_mod, "yt_dlp", fake_yt_dlp)

    with pytest.raises(YouTubeDownloadError, match="failed to download"):
        download_youtube_clip("abc123", str(tmp_path / "beat_0.mp4"), duration_seconds=15.0)
