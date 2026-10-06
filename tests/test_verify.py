import json
import pytest
from motion_graphics.verify import ClipVerificationError, verify_exported_clip


def _fake_ffprobe_result(returncode, stdout="", stderr=""):
    class FakeResult:
        pass
    result = FakeResult()
    result.returncode = returncode
    result.stdout = stdout
    result.stderr = stderr
    return result


def test_raises_when_file_does_not_exist(tmp_path):
    missing = str(tmp_path / "does_not_exist.mp4")
    with pytest.raises(ClipVerificationError, match="no file"):
        verify_exported_clip(missing, target_duration=5.0)


def test_raises_when_file_is_too_small(tmp_path, monkeypatch):
    path = tmp_path / "tiny.mp4"
    path.write_bytes(b"x" * 100)

    with pytest.raises(ClipVerificationError, match="too small"):
        verify_exported_clip(str(path), target_duration=5.0)


def test_raises_when_ffprobe_fails(tmp_path, monkeypatch):
    import motion_graphics.verify as verify_mod

    path = tmp_path / "clip.mp4"
    path.write_bytes(b"x" * 10_000)
    monkeypatch.setattr(
        verify_mod.subprocess, "run",
        lambda *a, **kw: _fake_ffprobe_result(1, stderr="invalid data"),
    )

    with pytest.raises(ClipVerificationError, match="ffprobe failed"):
        verify_exported_clip(str(path), target_duration=5.0)


def test_raises_when_duration_is_outside_tolerance(tmp_path, monkeypatch):
    import motion_graphics.verify as verify_mod

    path = tmp_path / "clip.mp4"
    path.write_bytes(b"x" * 10_000)
    stdout = json.dumps({"format": {"duration": "2.0"}})
    monkeypatch.setattr(
        verify_mod.subprocess, "run", lambda *a, **kw: _fake_ffprobe_result(0, stdout=stdout),
    )

    with pytest.raises(ClipVerificationError, match="2.0s"):
        verify_exported_clip(str(path), target_duration=5.0, duration_tolerance=1.0)


def test_passes_when_duration_is_within_tolerance(tmp_path, monkeypatch):
    import motion_graphics.verify as verify_mod

    path = tmp_path / "clip.mp4"
    path.write_bytes(b"x" * 10_000)
    stdout = json.dumps({"format": {"duration": "5.4"}})
    monkeypatch.setattr(
        verify_mod.subprocess, "run", lambda *a, **kw: _fake_ffprobe_result(0, stdout=stdout),
    )

    verify_exported_clip(str(path), target_duration=5.0, duration_tolerance=1.0)  # no raise


def test_short_duration_beat_still_uses_the_same_absolute_tolerance(tmp_path, monkeypatch):
    import motion_graphics.verify as verify_mod

    path = tmp_path / "clip.mp4"
    path.write_bytes(b"x" * 10_000)
    stdout = json.dumps({"format": {"duration": "1.4"}})
    monkeypatch.setattr(
        verify_mod.subprocess, "run", lambda *a, **kw: _fake_ffprobe_result(0, stdout=stdout),
    )

    # target 1.0s, actual 1.4s, tolerance 1.0s -> within tolerance, should pass
    verify_exported_clip(str(path), target_duration=1.0, duration_tolerance=1.0)


def test_raises_when_ffprobe_output_has_no_duration(tmp_path, monkeypatch):
    import motion_graphics.verify as verify_mod

    path = tmp_path / "clip.mp4"
    path.write_bytes(b"x" * 10_000)
    stdout = json.dumps({"format": {}})
    monkeypatch.setattr(
        verify_mod.subprocess, "run", lambda *a, **kw: _fake_ffprobe_result(0, stdout=stdout),
    )

    with pytest.raises(ClipVerificationError, match="could not read a duration"):
        verify_exported_clip(str(path), target_duration=5.0)
