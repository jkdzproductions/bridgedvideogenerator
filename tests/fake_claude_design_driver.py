"""Shared in-memory test double for motion_graphics.driver.ClaudeDesignDriver. Every
motion_graphics test that needs a driver without live browser automation imports this —
this environment doesn't have claude-in-chrome installed, so no test exercises the real thing."""
import itertools

from motion_graphics.driver import CanvasHandle


class FakeClaudeDesignDriver:
    def __init__(self):
        self._counter = itertools.count(1)
        self.created_canvases: list[str] = []
        self.sent_prompts: list[tuple[str, str]] = []
        self.screenshot_paths: dict[str, str] = {}
        self.exported_paths: list[tuple[str, str]] = []
        self.export_contents: dict[str, bytes] = {}

    def create_canvas(self, design_system_project_id: str) -> CanvasHandle:
        self.created_canvases.append(design_system_project_id)
        return CanvasHandle(canvas_id=f"canvas-{next(self._counter)}")

    def send_prompt(self, canvas: CanvasHandle, prompt: str) -> None:
        self.sent_prompts.append((canvas.canvas_id, prompt))

    def screenshot_canvas(self, canvas: CanvasHandle) -> str:
        return self.screenshot_paths.get(
            canvas.canvas_id, f"/fake/screenshot/{canvas.canvas_id}.png"
        )

    def click_export(self, canvas: CanvasHandle, dest_path: str) -> str:
        self.exported_paths.append((canvas.canvas_id, dest_path))
        content = self.export_contents.get(dest_path, b"fake-exported-video-bytes")
        with open(dest_path, "wb") as f:
            f.write(content)
        return dest_path
