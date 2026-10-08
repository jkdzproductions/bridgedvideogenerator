import os
import subprocess
import time

import pytest

from footage.envato_download import (
    EnvatoDownloadError,
    find_completed_download,
    trim_envato_clip,
)


def test_find_completed_download_matches_only_files_newer_than_started(tmp_path):
    old_file = tmp_path / "unrelated-old-clip.mov"
    old_file.write_bytes(b"old")
    os.utime(old_file, (time.time() - 3600, time.time() - 3600))

    started = time.time()
    time.sleep(0.05)
    new_file = tmp_path / "cityscape-aerial-2026-09-28-utc.mov"
    new_file.write_bytes(b"new")

    result = find_completed_download(str(tmp_path), started, deadline_seconds=2)
    assert result == str(new_file)


def test_find_completed_download_waits_for_pending_crdownload_to_clear(tmp_path):
    started = time.time()
    pending = tmp_path / "Unconfirmed 123.crdownload"
    pending.write_bytes(b"partial")
    final = tmp_path / "clip-2026-09-28-utc.mov"

    import threading

    def finish_download():
        time.sleep(0.3)
        pending.unlink()
        final.write_bytes(b"complete")

    threading.Thread(target=finish_download).start()

    result = find_completed_download(str(tmp_path), started, deadline_seconds=3)
    assert result == str(final)


def test_find_completed_download_raises_after_deadline_with_nothing_new(tmp_path):
    started = time.time()
    with pytest.raises(EnvatoDownloadError, match="no finished"):
        find_completed_download(str(tmp_path), started, deadline_seconds=1)


def test_find_completed_download_raises_when_more_than_one_new_file(tmp_path):
    started = time.time()
    time.sleep(0.05)
    (tmp_path / "a-2026-09-28-utc.mov").write_bytes(b"a")
    (tmp_path / "b-2026-09-28-utc.mov").write_bytes(b"b")

    with pytest.raises(EnvatoDownloadError, match="expected exactly one"):
        find_completed_download(str(tmp_path), started, deadline_seconds=1)


def test_trim_envato_clip_produces_a_file_of_the_requested_duration(tmp_path):
    if not _ffmpeg_available():
        pytest.skip("ffmpeg/ffprobe not installed")
    source = str(tmp_path / "source.mov")
    dest = str(tmp_path / "trimmed.mov")
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=blue:s=320x180:d=10",
         "-c:v", "prores_ks", "-pix_fmt", "yuv422p10le", source],
        check=True,
    )

    result = trim_envato_clip(source, dest, duration_seconds=3.0)

    assert result == dest
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
         "default=noprint_wrappers=1:nokey=1", dest],
        capture_output=True, text=True,
    )
    assert abs(float(probe.stdout.strip()) - 3.0) < 0.5


def test_trim_envato_clip_reencodes_prores_into_a_playable_h264_mp4(tmp_path):
    # C1: the real production destination is footage_output/beat_<n>.mp4, and a stream-copy
    # cannot mux ProRes into .mp4 (ffmpeg rc=234 "Could not write header"). Must re-encode.
    if not _ffmpeg_available():
        pytest.skip("ffmpeg/ffprobe not installed")
    import json

    source = str(tmp_path / "source.mov")
    dest = str(tmp_path / "beat_0.mp4")
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=s=320x180:d=10:r=25",
         "-c:v", "prores_ks", "-pix_fmt", "yuv422p10le", source],
        check=True,
    )

    result = trim_envato_clip(source, dest, duration_seconds=3.0)

    assert result == dest
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=codec_name,pix_fmt,width,height:format=duration,format_name",
         "-of", "json", dest],
        capture_output=True, text=True, check=True,
    )
    info = json.loads(probe.stdout)
    stream = info["streams"][0]
    assert stream["codec_name"] == "h264"
    assert stream["pix_fmt"] == "yuv420p"
    assert (stream["width"], stream["height"]) == (320, 180)
    assert "mp4" in info["format"]["format_name"]
    assert abs(float(info["format"]["duration"]) - 3.0) < 0.5
    decode = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", dest, "-f", "null", "-"], capture_output=True, text=True,
    )
    assert decode.returncode == 0 and decode.stderr.strip() == ""


def test_trim_envato_clip_raises_on_ffmpeg_failure(tmp_path):
    with pytest.raises(EnvatoDownloadError, match="ffmpeg"):
        trim_envato_clip(str(tmp_path / "does-not-exist.mov"), str(tmp_path / "out.mov"), 3.0)


def _make_video(path, size, seconds):
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", f"testsrc=s={size}:d={seconds}:r=25",
         "-c:v", "prores_ks", "-pix_fmt", "yuv422p10le", str(path)],
        check=True,
    )


def _probe_size_and_duration(path):
    import json
    info = json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height:format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout)
    s = info["streams"][0]
    return (s["width"], s["height"]), float(info["format"]["duration"])


def test_trim_envato_clip_extracts_the_largest_video_from_a_zip_download(tmp_path):
    # Live finding 2026-10-07/08: some Envato winners download as a .zip and ffmpeg cannot read it.
    if not _ffmpeg_available():
        pytest.skip("ffmpeg/ffprobe not installed")
    import zipfile

    _make_video(tmp_path / "preview.mov", "160x90", 1)
    _make_video(tmp_path / "master.mov", "320x180", 10)
    archive = tmp_path / "Envato_item.zip"  # the suggested filename can be anything
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("license.txt", "licensed")
        z.write(tmp_path / "preview.mov", "item/preview.mov")
        z.write(tmp_path / "master.mov", "item/footage/MASTER.MOV")
    dest = tmp_path / "beat_7.mp4"

    assert trim_envato_clip(str(archive), str(dest), duration_seconds=3.0) == str(dest)

    size, duration = _probe_size_and_duration(dest)
    assert size == (320, 180) and abs(duration - 3.0) < 0.5


def test_trim_envato_clip_raises_when_a_zip_holds_no_video(tmp_path):
    import zipfile

    archive = tmp_path / "item.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("license.txt", "licensed")
        z.writestr("readme.pdf", "x")

    with pytest.raises(EnvatoDownloadError, match="no video file.*license.txt"):
        trim_envato_clip(str(archive), str(tmp_path / "out.mp4"), 3.0)


def test_trim_envato_clip_creates_the_output_directory(tmp_path):
    # Stage 2 Step 1 deletes footage_output/; the trim must recreate it.
    if not _ffmpeg_available():
        pytest.skip("ffmpeg/ffprobe not installed")
    _make_video(tmp_path / "source.mov", "320x180", 4)
    dest = tmp_path / "footage_output" / "beat_3.mp4"

    assert trim_envato_clip(str(tmp_path / "source.mov"), str(dest), 2.0) == str(dest)
    assert dest.exists()


def _ffmpeg_available() -> bool:
    import shutil
    return bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


# --- download_envato_clip retry behaviour (mocked Playwright, no real browser) ---

import tempfile  # noqa: E402
from types import SimpleNamespace  # noqa: E402
from unittest.mock import MagicMock, patch  # noqa: E402

pytest.importorskip("playwright")
from playwright.sync_api import Error as PlaywrightError  # noqa: E402

from footage import envato_download  # noqa: E402

_SUGGESTED = "DJI_0001.MOV"
_CANCELED = "Download.path: canceled"


def _make_download(tmp_path, name, path_error=None, path_side_effect=None):
    src = tmp_path / f"internal_{name}"
    src.write_bytes(b"master")
    download = MagicMock()
    download.suggested_filename = _SUGGESTED
    download.source = src
    if path_side_effect is not None:
        download.path.side_effect = path_side_effect
    elif path_error is not None:
        download.path.side_effect = path_error
    else:
        download.path.return_value = str(src)
    return download


def _raising_trim(src, dest, duration):
    if not os.path.exists(src):
        raise AssertionError(f"trim got missing file {src}")
    return dest


def _run_download(tmp_path, downloads, click_error=None, close_side_effect=None):
    """Runs download_envato_clip with one fake context per attempt.

    Returns a namespace with result/error, contexts, click, trim, sleep, raw_dir, and
    partial_at_launch (whether the raw file existed as each attempt launched).
    """
    run = SimpleNamespace(contexts=[], raw_dir=None, partial_at_launch=[], result=None)

    real_tmpdir = tempfile.TemporaryDirectory

    def recording_tmpdir(*args, **kwargs):
        td = real_tmpdir(*args, **kwargs)
        run.raw_dir = td.name
        return td

    def make_context(*args, **kwargs):
        run.partial_at_launch.append(os.path.exists(os.path.join(run.raw_dir, _SUGGESTED)))
        ctx = MagicMock()
        if close_side_effect is not None:
            ctx.close.side_effect = lambda: close_side_effect(len(run.contexts) - 1, run)
        idx = len(run.contexts)
        run.contexts.append(ctx)
        ctx.new_page.return_value.expect_download.return_value.__enter__.return_value.value = (
            downloads[idx]
        )
        return ctx

    fake_pw = MagicMock()
    fake_pw.__enter__.return_value.chromium.launch_persistent_context.side_effect = make_context
    candidate = MagicMock(detail_url="https://example.test/item")
    with patch("playwright.sync_api.sync_playwright", return_value=fake_pw), \
            patch.object(envato_download.tempfile, "TemporaryDirectory", recording_tmpdir), \
            patch.object(envato_download.time, "sleep") as sleep, \
            patch.object(envato_download, "_click_download_button",
                         side_effect=click_error) as click, \
            patch.object(envato_download, "trim_envato_clip",
                         side_effect=_raising_trim) as trim:
        run.click, run.trim, run.sleep = click, trim, sleep
        try:
            run.result = envato_download.download_envato_clip(
                candidate, str(tmp_path / "out.mp4"), 3.0, str(tmp_path / "profile"))
        except BaseException as exc:  # noqa: BLE001 - tests inspect it
            run.error = exc
        else:
            run.error = None
    return run


def test_download_retries_after_canceled_and_succeeds_on_second_attempt(tmp_path):
    downloads = [
        _make_download(tmp_path, "a", path_error=PlaywrightError(_CANCELED)),
        _make_download(tmp_path, "b"),
    ]
    run = _run_download(tmp_path, downloads)
    assert run.error is None
    assert run.result == str(tmp_path / "out.mp4")
    assert len(run.contexts) == 2
    assert run.trim.call_count == 1
    assert run.sleep.call_count == 1


def test_download_gives_up_after_three_canceled_attempts(tmp_path):
    err = PlaywrightError(_CANCELED)
    downloads = [_make_download(tmp_path, str(i), path_error=err) for i in range(3)]
    run = _run_download(tmp_path, downloads)
    assert isinstance(run.error, EnvatoDownloadError)
    assert "3 attempts" in str(run.error) and "canceled" in str(run.error)
    assert run.error.__cause__ is err
    assert run.trim.call_count == 0
    assert len(run.contexts) == 3
    assert run.sleep.call_count == 2  # attempts - 1, none after the final failure


def test_download_does_not_retry_non_canceled_playwright_error_from_click(tmp_path):
    boom = PlaywrightError("Timeout 15000ms exceeded waiting for Download button")
    run = _run_download(tmp_path, [MagicMock()] * 3, click_error=boom)
    assert run.error is boom
    assert run.click.call_count == 1
    assert run.sleep.call_count == 0
    run.contexts[0].close.assert_called_once()


def test_download_does_not_retry_non_canceled_playwright_error_from_path(tmp_path):
    boom = PlaywrightError("Download.path: Target closed")
    run = _run_download(tmp_path, [_make_download(tmp_path, "a", path_error=boom)] * 3)
    assert run.error is boom
    assert len(run.contexts) == 1
    assert run.sleep.call_count == 0


def test_download_does_not_retry_non_playwright_error_mentioning_canceled(tmp_path):
    boom = RuntimeError("operation canceled by user")
    run = _run_download(tmp_path, [_make_download(tmp_path, "a", path_error=boom)] * 3)
    assert run.error is boom
    assert len(run.contexts) == 1
    assert run.sleep.call_count == 0


def test_download_closes_context_on_every_attempt(tmp_path):
    err = PlaywrightError(_CANCELED)
    downloads = [
        _make_download(tmp_path, "a", path_error=err),
        _make_download(tmp_path, "b", path_error=err),
        _make_download(tmp_path, "c"),
    ]
    run = _run_download(tmp_path, downloads)
    assert run.error is None
    assert len(run.contexts) == 3
    for ctx in run.contexts:
        ctx.close.assert_called_once()


def test_download_moves_file_out_before_closing_context(tmp_path):
    # Playwright deletes its internal temp file when the context closes, so the move must
    # happen first. Simulate that cleanup on close, and assert the moved file already exists.
    download = _make_download(tmp_path, "a")

    def on_close(idx, run):
        assert os.path.exists(os.path.join(run.raw_dir, _SUGGESTED)), "closed before move"
        download.source.unlink(missing_ok=True)

    run = _run_download(tmp_path, [download], close_side_effect=on_close)
    assert run.error is None
    assert run.trim.call_count == 1


def test_download_removes_partial_file_before_next_attempt(tmp_path):
    # A cross-filesystem shutil.move can leave a partial copy at the destination when it fails.
    first = _make_download(tmp_path, "a")
    second = _make_download(tmp_path, "b")
    real_move = envato_download.shutil.move
    calls = []

    def move(src, dst):
        calls.append(dst)
        if len(calls) == 1:
            with open(dst, "wb") as f:
                f.write(b"partial")
            raise PlaywrightError(_CANCELED)
        return real_move(src, dst)

    with patch.object(envato_download.shutil, "move", side_effect=move):
        run = _run_download(tmp_path, [first, second])
    assert run.error is None
    assert len(calls) == 2
    assert run.partial_at_launch == [False, False]  # attempt 1's partial gone before attempt 2


def test_download_secondary_close_error_does_not_mask_canceled_retry(tmp_path):
    downloads = [
        _make_download(tmp_path, "a", path_error=PlaywrightError(_CANCELED)),
        _make_download(tmp_path, "b"),
    ]

    def bad_close(idx, run):
        if idx == 0:
            raise RuntimeError("browser already gone")

    run = _run_download(tmp_path, downloads, close_side_effect=bad_close)
    assert run.error is None
    assert len(run.contexts) == 2
