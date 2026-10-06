import json
import pytest
from assembly.mux import MuxError, check_durations_match, run_mux


def _fake_result(returncode, stdout="", stderr=""):
    class FakeResult:
        pass
    r = FakeResult()
    r.returncode = returncode
    r.stdout = stdout
    r.stderr = stderr
    return r


def test_check_durations_match_passes_within_tolerance(monkeypatch):
    import assembly.mux as mux_mod

    responses = [
        _fake_result(0, stdout=json.dumps({"format": {"duration": "10.05"}})),
        _fake_result(0, stdout=json.dumps({"format": {"duration": "10.0"}})),
    ]
    monkeypatch.setattr(mux_mod.subprocess, "run", lambda *a, **kw: responses.pop(0))

    check_durations_match("video.mp4", "audio.mp4", tolerance=0.1)


def test_check_durations_match_raises_outside_tolerance(monkeypatch):
    import assembly.mux as mux_mod

    responses = [
        _fake_result(0, stdout=json.dumps({"format": {"duration": "10.5"}})),
        _fake_result(0, stdout=json.dumps({"format": {"duration": "10.0"}})),
    ]
    monkeypatch.setattr(mux_mod.subprocess, "run", lambda *a, **kw: responses.pop(0))

    with pytest.raises(MuxError, match="differ by more than"):
        check_durations_match("video.mp4", "audio.mp4", tolerance=0.1)


def test_check_durations_match_raises_on_ffprobe_failure(monkeypatch):
    import assembly.mux as mux_mod

    monkeypatch.setattr(
        mux_mod.subprocess, "run", lambda *a, **kw: _fake_result(1, stderr="bad file")
    )

    with pytest.raises(MuxError, match="ffprobe failed"):
        check_durations_match("video.mp4", "audio.mp4")


def test_run_mux_raises_on_duration_mismatch_without_calling_ffmpeg_mux(monkeypatch):
    import assembly.mux as mux_mod

    responses = [
        _fake_result(0, stdout=json.dumps({"format": {"duration": "20.0"}})),
        _fake_result(0, stdout=json.dumps({"format": {"duration": "10.0"}})),
    ]
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        return responses.pop(0)

    monkeypatch.setattr(mux_mod.subprocess, "run", fake_run)

    with pytest.raises(MuxError, match="differ by more than"):
        run_mux("video.mp4", "audio.mp4", "out.mp4")

    assert len(calls) == 2
    assert all(c[0] == "ffprobe" for c in calls)


def test_run_mux_succeeds_when_durations_match(monkeypatch):
    import assembly.mux as mux_mod

    responses = [
        _fake_result(0, stdout=json.dumps({"format": {"duration": "10.0"}})),
        _fake_result(0, stdout=json.dumps({"format": {"duration": "10.02"}})),
        _fake_result(0),
    ]
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        return responses.pop(0)

    monkeypatch.setattr(mux_mod.subprocess, "run", fake_run)

    run_mux("video.mp4", "audio.mp4", "out.mp4")

    assert len(calls) == 3
    assert calls[2][0] == "ffmpeg"
    assert calls[2][-1] == "out.mp4"
