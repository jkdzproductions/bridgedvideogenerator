import pytest
from assembly.beats import BeatClip, MissingClipsError, resolve_beat_clips
from shot_list.models import Beat, FootageSpec, GraphicSpec, ShotList


def _shot_list():
    return ShotList(
        beats=[
            Beat(0.0, 4.0, "footage", footage=FootageSpec("q1", "s1")),
            Beat(4.0, 9.0, "graphic", graphic=GraphicSpec("chart_card", {"value": "1"})),
        ],
        duration=9.0,
    )


def test_resolve_beat_clips_returns_all_when_every_file_exists(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "footage_output").mkdir()
    (tmp_path / "graphics_output").mkdir()
    (tmp_path / "footage_output" / "beat_0.mp4").write_bytes(b"x")
    (tmp_path / "graphics_output" / "beat_1.mp4").write_bytes(b"x")

    result = resolve_beat_clips(_shot_list())

    assert result == [
        BeatClip(index=0, start=0.0, end=4.0, type="footage", source_path="footage_output/beat_0.mp4"),
        BeatClip(index=1, start=4.0, end=9.0, type="graphic", source_path="graphics_output/beat_1.mp4"),
    ]


def test_resolve_beat_clips_raises_listing_every_missing_beat(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    with pytest.raises(MissingClipsError) as exc_info:
        resolve_beat_clips(_shot_list())

    message = str(exc_info.value)
    assert "2 beat clip(s) missing" in message
    assert "beat 0 (footage): expected footage_output/beat_0.mp4" in message
    assert "beat 1 (graphic): expected graphics_output/beat_1.mp4" in message


def test_resolve_beat_clips_lists_only_the_beats_actually_missing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "footage_output").mkdir()
    (tmp_path / "footage_output" / "beat_0.mp4").write_bytes(b"x")

    with pytest.raises(MissingClipsError) as exc_info:
        resolve_beat_clips(_shot_list())

    message = str(exc_info.value)
    assert "1 beat clip(s) missing" in message
    assert "beat 1 (graphic)" in message
    assert "beat 0" not in message


def test_resolve_beat_clips_needs_no_file_for_a_talking_head_beat(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "footage_output").mkdir()
    (tmp_path / "footage_output" / "beat_0.mp4").write_bytes(b"x")
    shot_list = ShotList(
        beats=[
            Beat(0.0, 4.0, "footage", footage=FootageSpec("q1", "s1")),
            Beat(4.0, 9.0, "talking_head"),
        ],
        duration=9.0,
    )

    result = resolve_beat_clips(shot_list)

    assert result == [
        BeatClip(index=0, start=0.0, end=4.0, type="footage", source_path="footage_output/beat_0.mp4"),
        BeatClip(index=1, start=4.0, end=9.0, type="talking_head", source_path=""),
    ]


def test_missing_footage_is_still_reported_when_a_talking_head_is_present(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    shot_list = ShotList(
        beats=[
            Beat(0.0, 4.0, "footage", footage=FootageSpec("q1", "s1")),
            Beat(4.0, 9.0, "talking_head"),
        ],
        duration=9.0,
    )

    with pytest.raises(MissingClipsError, match="1 beat clip\\(s\\) missing"):
        resolve_beat_clips(shot_list)
