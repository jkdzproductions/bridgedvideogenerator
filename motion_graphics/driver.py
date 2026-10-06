"""ClaudeDesignDriver Protocol. NOT used by the real Stage 3 workflow; kept on purpose.

Status (2026-09-28): the real motion-graphics stage in CLAUDE.md ("Stage 3 (Motion Graphics)")
does not use this Protocol, `tests/fake_claude_design_driver.py`, or
`motion_graphics/build.py`'s `create_canvas_and_submit` / `submit_correction` /
`finalize_export`. Nothing in production calls them.

Why: this boundary assumed a Python class would drive claude.ai/design with its own browser
automation (the plan's original Task 10, a Playwright-based `ClaudeDesignBrowserDriver`). A real
attempt showed that can't work. claude.ai/design sits behind Cloudflare bot detection, which flags
any Playwright-launched Chrome (`navigator.webdriver === true`) and re-challenges it on every
process launch, even with a valid saved login. Getting past that would take bot-detection evasion,
which is off the table. Josh chose the alternative: the Claude Code agent running CLAUDE.md drives
Josh's real, already-logged-in Chrome itself through its `claude-in-chrome` tools, following the
step-by-step browser prose in Stage 3. That doesn't trip Cloudflare because it isn't a newly
launched automated browser. Python's part of Stage 3 is prompt building, small JSON state files,
and `motion_graphics/verify.py`'s real ffprobe check. The canvas identity is still stored in the
`CanvasHandle` shape (`canvas_<n>.json` = `{"canvas_id": <full claude.ai/design canvas URL>}`).

The Protocol, the fake, and build.py's three functions are left in place, with their tests,
because they are correct, already reviewed, and harmless. Don't read their existence as a sign
that a Python driver exists or is expected. Don't write one without first re-checking the
Cloudflare situation.
"""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class CanvasHandle:
    canvas_id: str


@runtime_checkable
class ClaudeDesignDriver(Protocol):
    """Protocol for driving claude.ai/design's Animation template to author a motion graphic.

    Unused in production: see the module docstring. The real Stage 3 is agent-driven through
    `claude-in-chrome`, and nothing constructs an implementation of this Protocol.

    Historical design note: this Protocol was designed for a Python-driven approach in which
    CLAUDE.md's Stage 3 would have constructed a driver instance fresh, with no constructor
    arguments, in a brand-new Python process for every step, so a real implementation would have
    had to reattach to an existing canvas purely from the `canvas_id` string persisted by an
    earlier step (see `CanvasHandle`). That approach was abandoned (Cloudflare bot detection).
    """

    def create_canvas(self, design_system_project_id: str) -> CanvasHandle: ...
    def send_prompt(self, canvas: CanvasHandle, prompt: str) -> None: ...
    def screenshot_canvas(self, canvas: CanvasHandle) -> str: ...
    def click_export(self, canvas: CanvasHandle, dest_path: str) -> str: ...
