"""Build glue over ClaudeDesignDriver. NOT used by the real Stage 3; see motion_graphics/driver.py's module docstring."""

import os

from motion_graphics.driver import CanvasHandle, ClaudeDesignDriver
from motion_graphics.verify import verify_exported_clip


def create_canvas_and_submit(
    driver: ClaudeDesignDriver, design_system_project_id: str, authoring_prompt: str
) -> tuple[CanvasHandle, str]:
    canvas = driver.create_canvas(design_system_project_id)
    driver.send_prompt(canvas, authoring_prompt)
    screenshot_path = driver.screenshot_canvas(canvas)
    return canvas, screenshot_path


def submit_correction(
    driver: ClaudeDesignDriver, canvas: CanvasHandle, correction_instructions: str
) -> str:
    driver.send_prompt(canvas, correction_instructions)
    return driver.screenshot_canvas(canvas)


def finalize_export(
    driver: ClaudeDesignDriver, canvas: CanvasHandle, dest_path: str, target_duration: float
) -> str:
    os.makedirs(os.path.dirname(dest_path) or ".", exist_ok=True)
    try:
        path = driver.click_export(canvas, dest_path)
        verify_exported_clip(path, target_duration)
    except Exception:
        if os.path.exists(dest_path):
            os.remove(dest_path)
        raise
    return path
