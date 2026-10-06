import os
import pytest
from assembly.concat import ConcatError, build_concat_list, run_concat


def test_build_concat_list_formats_each_path_as_a_file_directive():
    result = build_concat_list(["/tmp/beat_0.mp4", "/tmp/beat_1.mp4"])

    assert result == "file '/tmp/beat_0.mp4'\nfile '/tmp/beat_1.mp4'\n"


def test_build_concat_list_escapes_single_quotes_in_paths():
    result = build_concat_list(["/tmp/it's a clip.mp4"])

    assert result == "file '/tmp/it'\\''s a clip.mp4'\n"


def test_build_concat_list_uses_absolute_paths(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    result = build_concat_list(["relative.mp4"])

    assert str(tmp_path / "relative.mp4") in result


def test_run_concat_writes_the_list_file_and_raises_on_ffmpeg_failure(tmp_path, monkeypatch):
    import assembly.concat as concat_mod

    class FakeResult:
        returncode = 1
        stderr = "concat error"

    monkeypatch.setattr(concat_mod.subprocess, "run", lambda *a, **kw: FakeResult())
    list_file = str(tmp_path / "list.txt")

    with pytest.raises(ConcatError, match="concat error"):
        run_concat(["a.mp4", "b.mp4"], str(tmp_path / "out.mp4"), list_file)

    assert os.path.exists(list_file)
    content = open(list_file).read()
    assert "a.mp4" in content and "b.mp4" in content


def test_run_concat_succeeds_without_raising(tmp_path, monkeypatch):
    import assembly.concat as concat_mod

    class FakeResult:
        returncode = 0
        stderr = ""

    monkeypatch.setattr(concat_mod.subprocess, "run", lambda *a, **kw: FakeResult())

    run_concat(["a.mp4"], str(tmp_path / "out.mp4"), str(tmp_path / "list.txt"))
