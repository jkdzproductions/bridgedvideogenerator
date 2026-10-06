from motion_graphics.driver import CanvasHandle, ClaudeDesignDriver
from tests.fake_claude_design_driver import FakeClaudeDesignDriver


def test_canvas_handle_holds_its_id():
    handle = CanvasHandle(canvas_id="abc123")
    assert handle.canvas_id == "abc123"


def test_fake_driver_satisfies_the_protocol():
    driver = FakeClaudeDesignDriver()
    assert isinstance(driver, ClaudeDesignDriver)


def test_fake_driver_records_created_canvases_and_returns_unique_handles():
    driver = FakeClaudeDesignDriver()

    handle1 = driver.create_canvas("proj-1")
    handle2 = driver.create_canvas("proj-1")

    assert driver.created_canvases == ["proj-1", "proj-1"]
    assert handle1.canvas_id != handle2.canvas_id


def test_fake_driver_records_sent_prompts():
    driver = FakeClaudeDesignDriver()
    canvas = driver.create_canvas("proj-1")

    driver.send_prompt(canvas, "make a chart card")

    assert driver.sent_prompts == [(canvas.canvas_id, "make a chart card")]


def test_fake_driver_returns_configured_screenshot_path():
    driver = FakeClaudeDesignDriver()
    canvas = driver.create_canvas("proj-1")
    driver.screenshot_paths[canvas.canvas_id] = "/tmp/shot.png"

    assert driver.screenshot_canvas(canvas) == "/tmp/shot.png"


def test_fake_driver_click_export_writes_a_real_file(tmp_path):
    driver = FakeClaudeDesignDriver()
    canvas = driver.create_canvas("proj-1")
    dest = str(tmp_path / "beat_0.mp4")
    driver.export_contents[dest] = b"fake-video-bytes"

    result = driver.click_export(canvas, dest)

    assert result == dest
    assert (tmp_path / "beat_0.mp4").read_bytes() == b"fake-video-bytes"
    assert driver.exported_paths == [(canvas.canvas_id, dest)]
