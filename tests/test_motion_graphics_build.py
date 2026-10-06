import os

import pytest
from motion_graphics.build import create_canvas_and_submit, finalize_export, submit_correction
from motion_graphics.verify import ClipVerificationError
from tests.fake_claude_design_driver import FakeClaudeDesignDriver


def test_create_canvas_and_submit_creates_canvas_sends_prompt_and_returns_screenshot():
    driver = FakeClaudeDesignDriver()

    canvas, screenshot_path = create_canvas_and_submit(driver, "proj-1", "make a chart card")

    assert driver.created_canvases == ["proj-1"]
    assert driver.sent_prompts == [(canvas.canvas_id, "make a chart card")]
    assert screenshot_path == driver.screenshot_paths.get(
        canvas.canvas_id, f"/fake/screenshot/{canvas.canvas_id}.png"
    )


def test_submit_correction_sends_the_correction_and_returns_a_fresh_screenshot():
    driver = FakeClaudeDesignDriver()
    canvas, _ = create_canvas_and_submit(driver, "proj-1", "initial prompt")
    driver.screenshot_paths[canvas.canvas_id] = "/fake/after_correction.png"

    result = submit_correction(driver, canvas, "make the number bigger")

    assert driver.sent_prompts[-1] == (canvas.canvas_id, "make the number bigger")
    assert result == "/fake/after_correction.png"


def test_finalize_export_succeeds_and_returns_the_verified_path(tmp_path, monkeypatch):
    import motion_graphics.build as build_mod

    driver = FakeClaudeDesignDriver()
    canvas, _ = create_canvas_and_submit(driver, "proj-1", "initial prompt")
    dest = str(tmp_path / "beat_0.mp4")

    monkeypatch.setattr(build_mod, "verify_exported_clip", lambda path, target_duration: None)

    result = finalize_export(driver, canvas, dest, target_duration=5.0)

    assert result == dest
    assert driver.exported_paths == [(canvas.canvas_id, dest)]


def test_finalize_export_deletes_the_file_and_reraises_on_verification_failure(tmp_path, monkeypatch):
    import motion_graphics.build as build_mod

    driver = FakeClaudeDesignDriver()
    canvas, _ = create_canvas_and_submit(driver, "proj-1", "initial prompt")
    dest = str(tmp_path / "beat_0.mp4")

    def failing_verify(path, target_duration):
        raise ClipVerificationError("wrong duration")

    monkeypatch.setattr(build_mod, "verify_exported_clip", failing_verify)

    with pytest.raises(ClipVerificationError, match="wrong duration"):
        finalize_export(driver, canvas, dest, target_duration=5.0)

    assert not (tmp_path / "beat_0.mp4").exists()


def test_finalize_export_creates_missing_parent_directory(tmp_path, monkeypatch):
    import motion_graphics.build as build_mod

    driver = FakeClaudeDesignDriver()
    canvas, _ = create_canvas_and_submit(driver, "proj-1", "initial prompt")
    dest = str(tmp_path / "nested" / "beat_0.mp4")

    monkeypatch.setattr(build_mod, "verify_exported_clip", lambda path, target_duration: None)

    result = finalize_export(driver, canvas, dest, target_duration=5.0)

    assert result == dest
    assert os.path.exists(dest)


def test_finalize_export_deletes_the_file_and_reraises_on_any_exception(tmp_path, monkeypatch):
    import motion_graphics.build as build_mod

    driver = FakeClaudeDesignDriver()
    canvas, _ = create_canvas_and_submit(driver, "proj-1", "initial prompt")
    dest = str(tmp_path / "beat_0.mp4")

    def failing_verify(path, target_duration):
        raise RuntimeError("some other failure")

    monkeypatch.setattr(build_mod, "verify_exported_clip", failing_verify)

    with pytest.raises(RuntimeError, match="some other failure"):
        finalize_export(driver, canvas, dest, target_duration=5.0)

    assert not (tmp_path / "beat_0.mp4").exists()
