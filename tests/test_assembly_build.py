import os
import pytest
from assembly.beats import BeatClip
from assembly.build import assemble, normalize_all
from assembly.verify import FinalOutputVerificationError


def _clip(index, start, end, type_="footage"):
    return BeatClip(index=index, start=start, end=end, type=type_, source_path=f"src_{index}.mp4")


def test_normalize_all_creates_staging_dir_and_calls_run_normalize_per_clip(tmp_path, monkeypatch):
    import assembly.build as build_mod

    calls = []
    monkeypatch.setattr(
        build_mod, "run_normalize",
        lambda source_path, dest_path, target_duration: calls.append(
            (source_path, dest_path, target_duration)
        ),
    )
    staging_dir = str(tmp_path / "staging")
    clips = [_clip(0, 0.0, 4.0), _clip(1, 4.0, 9.0, "graphic")]

    result = normalize_all(clips, staging_dir)

    assert os.path.isdir(staging_dir)
    assert result == [
        os.path.join(staging_dir, "beat_0.mp4"),
        os.path.join(staging_dir, "beat_1.mp4"),
    ]
    assert calls == [
        ("src_0.mp4", os.path.join(staging_dir, "beat_0.mp4"), 4.0),
        ("src_1.mp4", os.path.join(staging_dir, "beat_1.mp4"), 5.0),
    ]


def test_assemble_runs_the_full_pipeline_in_order_and_returns_final_path(tmp_path, monkeypatch):
    import assembly.build as build_mod

    call_order = []
    monkeypatch.setattr(
        build_mod, "run_normalize",
        lambda source_path, dest_path, target_duration: call_order.append("normalize"),
    )
    monkeypatch.setattr(
        build_mod, "run_concat",
        lambda clip_paths, dest_path, list_file_path: call_order.append("concat"),
    )
    def fake_run_mux(video_path, audio_path, dest_path):
        call_order.append("mux")
        os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
        with open(dest_path, "w") as f:
            f.write("fake mux output")

    monkeypatch.setattr(build_mod, "run_mux", fake_run_mux)
    monkeypatch.setattr(
        build_mod, "verify_final_output",
        lambda path, expected_duration, **kw: call_order.append("verify"),
    )

    staging_dir = str(tmp_path / "staging")
    final_path = str(tmp_path / "final_output" / "assembled.mp4")
    clips = [_clip(0, 0.0, 4.0)]

    result = assemble(clips, "voiceover.wav", staging_dir, final_path, total_duration=4.0)

    assert result == final_path
    assert call_order == ["normalize", "concat", "mux", "verify"]
    assert os.path.isdir(os.path.dirname(final_path))
    assert os.path.exists(final_path)
    candidate_path = os.path.join(staging_dir, "final_candidate.mp4")
    assert not os.path.exists(candidate_path), (
        "candidate file should have been moved into place, not left behind"
    )


def test_assemble_propagates_a_normalize_failure_without_running_later_steps(tmp_path, monkeypatch):
    import assembly.build as build_mod
    from assembly.normalize import NormalizeError

    call_order = []

    def failing_normalize(source_path, dest_path, target_duration):
        raise NormalizeError("bad input file")

    monkeypatch.setattr(build_mod, "run_normalize", failing_normalize)
    monkeypatch.setattr(build_mod, "run_concat", lambda *a, **kw: call_order.append("concat"))
    monkeypatch.setattr(build_mod, "run_mux", lambda *a, **kw: call_order.append("mux"))
    monkeypatch.setattr(build_mod, "verify_final_output", lambda *a, **kw: call_order.append("verify"))

    clips = [_clip(0, 0.0, 4.0)]

    with pytest.raises(NormalizeError, match="bad input file"):
        assemble(
            clips, "voiceover.wav", str(tmp_path / "staging"),
            str(tmp_path / "final_output" / "assembled.mp4"), total_duration=4.0,
        )

    assert call_order == []


def test_assemble_does_not_touch_final_path_when_verification_fails(tmp_path, monkeypatch):
    """A verification failure must not clobber (or leave behind an unverified file at)
    final_path — including a stale file left over from a previous successful run."""
    import assembly.build as build_mod

    monkeypatch.setattr(build_mod, "run_normalize", lambda *a, **kw: None)
    monkeypatch.setattr(build_mod, "run_concat", lambda *a, **kw: None)

    def fake_run_mux(video_path, audio_path, dest_path):
        os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
        with open(dest_path, "w") as f:
            f.write("fake mux output")

    monkeypatch.setattr(build_mod, "run_mux", fake_run_mux)

    def failing_verify(path, expected_duration, **kw):
        raise FinalOutputVerificationError(f"{path} is bogus")

    monkeypatch.setattr(build_mod, "verify_final_output", failing_verify)

    final_path = str(tmp_path / "final_output" / "assembled.mp4")
    os.makedirs(os.path.dirname(final_path), exist_ok=True)
    with open(final_path, "w") as f:
        f.write("previous run's real deliverable")

    clips = [_clip(0, 0.0, 4.0)]

    with pytest.raises(FinalOutputVerificationError):
        assemble(
            clips, "voiceover.wav", str(tmp_path / "staging"),
            final_path, total_duration=4.0,
        )

    with open(final_path) as f:
        assert f.read() == "previous run's real deliverable", (
            "a failed verification must leave a pre-existing final_path completely untouched"
        )


def test_normalize_all_makes_a_black_clip_for_a_talking_head_and_normalizes_the_rest(tmp_path, monkeypatch):
    import assembly.build as build_mod

    normalize_calls, black_calls = [], []
    monkeypatch.setattr(
        build_mod, "run_normalize",
        lambda source_path, dest_path, target_duration: normalize_calls.append(
            (source_path, dest_path, target_duration)))
    monkeypatch.setattr(
        build_mod, "run_black_clip",
        lambda dest_path, duration: black_calls.append((dest_path, duration)))
    staging_dir = str(tmp_path / "staging")
    clips = [
        _clip(0, 0.0, 4.0),
        BeatClip(index=1, start=4.0, end=9.5, type="talking_head", source_path=""),
    ]

    result = normalize_all(clips, staging_dir)

    assert result == [
        os.path.join(staging_dir, "beat_0.mp4"),
        os.path.join(staging_dir, "beat_1.mp4"),
    ]
    assert normalize_calls == [("src_0.mp4", os.path.join(staging_dir, "beat_0.mp4"), 4.0)]
    assert black_calls == [(os.path.join(staging_dir, "beat_1.mp4"), 5.5)]


def test_normalize_all_does_not_let_per_clip_frame_rounding_add_up_to_drift(tmp_path, monkeypatch):
    # 30 beats of 5.88 s: rounding each one down to whole frames at 30 fps lost 0.013 s a clip,
    # 0.4 s in all (found on a real 138.5 s video, where the mux guard then refused the video)
    import assembly.build as build_mod

    durations = []
    monkeypatch.setattr(
        build_mod, "run_normalize",
        lambda source_path, dest_path, target_duration: durations.append(target_duration),
    )
    clips = [_clip(i, i * 5.88, (i + 1) * 5.88) for i in range(30)]

    normalize_all(clips, str(tmp_path / "staging"))

    total_frames = sum(round(d * 30) for d in durations)
    assert abs(total_frames / 30 - 30 * 5.88) <= 1 / 30
    # every clip is a whole number of frames, so ffmpeg cuts exactly what is asked
    assert all(abs(d * 30 - round(d * 30)) < 1e-6 for d in durations)
    assert all(d > 0 for d in durations)
