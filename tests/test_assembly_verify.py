import json
import pytest
from assembly.verify import FinalOutputVerificationError, verify_final_output


def _fake_result(returncode, stdout="", stderr=""):
    class FakeResult:
        pass
    r = FakeResult()
    r.returncode = returncode
    r.stdout = stdout
    r.stderr = stderr
    return r


def test_raises_when_file_does_not_exist(tmp_path):
    with pytest.raises(FinalOutputVerificationError, match="no file"):
        verify_final_output(str(tmp_path / "missing.mp4"), expected_duration=10.0)


def test_raises_when_video_stream_missing(tmp_path, monkeypatch):
    import assembly.verify as verify_mod

    path = tmp_path / "out.mp4"
    path.write_bytes(b"x")
    payload = {"streams": [{"codec_type": "audio"}], "format": {"duration": "10.0"}}
    monkeypatch.setattr(
        verify_mod.subprocess, "run", lambda *a, **kw: _fake_result(0, stdout=json.dumps(payload))
    )

    with pytest.raises(FinalOutputVerificationError, match="video=False"):
        verify_final_output(str(path), expected_duration=10.0)


def test_raises_when_audio_stream_missing(tmp_path, monkeypatch):
    import assembly.verify as verify_mod

    path = tmp_path / "out.mp4"
    path.write_bytes(b"x")
    payload = {
        "streams": [{"codec_type": "video", "width": 1920, "height": 1080}],
        "format": {"duration": "10.0"},
    }
    monkeypatch.setattr(
        verify_mod.subprocess, "run", lambda *a, **kw: _fake_result(0, stdout=json.dumps(payload))
    )

    with pytest.raises(FinalOutputVerificationError, match="audio=False"):
        verify_final_output(str(path), expected_duration=10.0)


def test_finds_video_stream_resolution_even_when_audio_stream_listed_first(tmp_path, monkeypatch):
    import assembly.verify as verify_mod

    path = tmp_path / "out.mp4"
    path.write_bytes(b"x")
    payload = {
        "streams": [
            {"codec_type": "audio"},
            {"codec_type": "video", "width": 1920, "height": 1080},
        ],
        "format": {"duration": "10.0"},
    }
    monkeypatch.setattr(
        verify_mod.subprocess, "run", lambda *a, **kw: _fake_result(0, stdout=json.dumps(payload))
    )

    verify_final_output(str(path), expected_duration=10.0)  # must not raise


def test_raises_on_wrong_resolution(tmp_path, monkeypatch):
    import assembly.verify as verify_mod

    path = tmp_path / "out.mp4"
    path.write_bytes(b"x")
    payload = {
        "streams": [{"codec_type": "video", "width": 1280, "height": 720},
                    {"codec_type": "audio"}],
        "format": {"duration": "10.0"},
    }
    monkeypatch.setattr(
        verify_mod.subprocess, "run", lambda *a, **kw: _fake_result(0, stdout=json.dumps(payload))
    )

    with pytest.raises(FinalOutputVerificationError, match="1280x720"):
        verify_final_output(str(path), expected_duration=10.0)


def test_raises_on_duration_mismatch(tmp_path, monkeypatch):
    import assembly.verify as verify_mod

    path = tmp_path / "out.mp4"
    path.write_bytes(b"x")
    payload = {
        "streams": [{"codec_type": "video", "width": 1920, "height": 1080},
                    {"codec_type": "audio"}],
        "format": {"duration": "5.0"},
    }
    monkeypatch.setattr(
        verify_mod.subprocess, "run", lambda *a, **kw: _fake_result(0, stdout=json.dumps(payload))
    )

    with pytest.raises(FinalOutputVerificationError, match=r"expected close to 10\.000s"):
        verify_final_output(str(path), expected_duration=10.0)
