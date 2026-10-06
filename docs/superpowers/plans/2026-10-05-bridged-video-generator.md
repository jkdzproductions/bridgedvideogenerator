# Bridged Video Generator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create `~/bridged-video-generator/`, a working copy of the Versed video generator with every Versed-specific name and design rule replaced, ready for Josh's Bridged design system.

**Architecture:** Export the tracked files of the Versed generator's `main` (commit `b293084`) into the new repo, leaving out Versed's design assets, docs and handoff. Then change the few Versed-specific places (prompts, snapshot path, JS names, user-agent, docs) and add a placeholder Bridged design-system snapshot. No pipeline logic changes: the Bridged generator behaves exactly like Versed's, including the YouTube blacklist (10 channels), the 1M-subscriber rule and the mirrored/zoomed/grained/half-vignette YouTube look.

**Tech Stack:** Python 3.9 (this machine's only Python), pytest, ffmpeg, yt-dlp, Playwright (Chromium), openai-whisper, python-docx, Pillow.

**Spec:** `docs/superpowers/specs/2026-10-05-bridged-video-generator-design.md`

## Global Constraints

- Separate project at `~/bridged-video-generator/`, its own git repo, fresh history (no Versed commits).
- The Versed generator at `~/versed-video-generator/` is never modified by this plan.
- Source of the copy is Versed's `main` at commit `b293084`, tracked files only (`git archive`).
- Script markup unchanged: italic = graphic, bold = talking head, italic+image link = graph, italic+`#:~:text=` link = page highlight, non-italic image link = show-as-is image.
- Left out of the copy: `design-assets/` (the licensed Nagel font and Versed frames), Versed's `docs/`, Versed's `HANDOFF.md`, `design_system/copy-of-versed-design-system.md`, `.env`, `.venv`, every generated run file.
- Copied locally, not through git: `.envato_automation_profile/` (about 1 GB) and the `PEXELS_API_KEY` and `YOUTUBE_API_KEY` lines of `.env`. `GRAPHICS_DESIGN_SYSTEM_NAME` is NOT set (the Bridged design system does not exist yet).
- The font (`*.otf`, `*.ttf`) never goes into git (licensed).
- The 7 Versed archetypes stay in `ARCHETYPES` as placeholders until the Bridged design system defines its own.
- No GitHub repo is created by this plan. Josh decides when (outward-facing).
- Every code block in CLAUDE.md uses `.venv/bin/python -c` directly; commits end with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
- Python packaging: `pyproject.toml`'s `[tool.setuptools.packages.find] include` must list every top-level package: `shot_list*`, `footage*`, `assembly*`, `motion_graphics*`, `script_input*`, `graph_intake*`, `page_intake*`, `image_intake*`.

## Review Focus

- **A leftover "Versed" or "Nagel" in a prompt a subagent reads** (it would tell a Bridged subagent to follow Versed's font and look). Task 3 adds a test that no built prompt contains either word.
- **The licensed font or Versed frames slipping into the new repo** via the copy. Task 1 checks `git ls-files` for font files and `design-assets/`, and adds font patterns to `.gitignore`.
- **The placeholder snapshot missing a section a prompt depends on** ("The 7 frame types", "The one rule", "Visual foundations", "Content fundamentals", "Pre-ship checklist"), which would make the director or reviewer read an incomplete file. Task 2 adds a test that pins those headings, so the real design system's readme has to keep them.
- **Versed's per-run state or secrets copied by accident** (`.env`, `shot_list.json`, `candidates_*.json`, `youtube_quota_usage.json`). Task 1 checks they are absent; Task 6 creates only the two API-key lines.
- **The copied Envato login not working in the new location** (expired session, locked profile). Task 6 does a real Envato search and, on a sign-in redirect, stops and reports instead of retrying or using Google sign-in.

---

### Task 1: Export Versed into the new repo and make it installable

**Files:**
- Create: everything exported from Versed (see step 2), except the exclusions
- Modify: `pyproject.toml` (project name), `.gitignore` (font patterns)
- Test: `tests/test_scaffold.py`

**Interfaces:**
- Consumes: `~/versed-video-generator` git history (commit `b293084`), `~/bridged-video-generator/` with `.git` and `docs/superpowers/specs/` already present
- Produces: a repo whose packages import and install; `.venv` with all extras; later tasks rely on `tests/` and the package directories being present

- [ ] **Step 1: Export the tracked files to a temp folder, then drop the exclusions**

```bash
set -e
TMP=/private/tmp/claude-501/-Users-joshkades/4e607812-07ca-4f3c-9fc0-35d0786e4cab/scratchpad/bridged_export
rm -rf "$TMP" && mkdir -p "$TMP"
cd ~/versed-video-generator
git archive b293084 | tar -x -C "$TMP"
rm -rf "$TMP/design-assets" "$TMP/docs" "$TMP/HANDOFF.md" "$TMP/design_system"
ls "$TMP"
```

Expected: the listing shows `CLAUDE.md assembly footage graph_intake image_intake motion_graphics page_intake pyproject.toml script_input shot_list tests` (no `design-assets`, `docs`, `HANDOFF.md`, `design_system`). `.gitignore` is a dotfile and is not shown by `ls`.

- [ ] **Step 2: Copy it into the new repo without touching its existing docs and design-assets**

```bash
set -e
TMP=/private/tmp/claude-501/-Users-joshkades/4e607812-07ca-4f3c-9fc0-35d0786e4cab/scratchpad/bridged_export
cp -R "$TMP"/. ~/bridged-video-generator/
cd ~/bridged-video-generator
ls -a | head -30
git status --short | head
```

Expected: `docs/superpowers/specs/...` and `docs/superpowers/plans/...` still exist; `.gitignore`, `pyproject.toml`, `CLAUDE.md` and the package folders are new and untracked.

- [ ] **Step 3: Write the failing scaffold test**

Create `tests/test_scaffold.py`:

```python
import os
import subprocess

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

PACKAGES = [
    "shot_list", "footage", "assembly", "motion_graphics",
    "script_input", "graph_intake", "page_intake", "image_intake",
]


def _tracked_or_untracked_files():
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout
    return [line for line in out.splitlines() if line]


def test_no_font_files_or_versed_assets_in_the_repo():
    files = _tracked_or_untracked_files()
    assert [f for f in files if f.lower().endswith((".otf", ".ttf"))] == []
    assert [f for f in files if f.startswith("design-assets/")] == []


def test_no_secrets_or_run_state_in_the_repo():
    files = set(_tracked_or_untracked_files())
    for name in (".env", "shot_list.json", "youtube_quota_usage.json", "excluded_channel_ids.json"):
        assert name not in files
    assert not [f for f in files if f.startswith(("candidates_", "footage_output/", ".envato_automation_profile/"))]


def test_pyproject_names_the_bridged_project_and_lists_every_package():
    text = open(os.path.join(ROOT, "pyproject.toml")).read()
    assert 'name = "bridged-video-generator"' in text
    for package in PACKAGES:
        assert f'"{package}*"' in text


def test_every_package_imports_with_no_pythonpath():
    code = "; ".join(f"import {p}" for p in PACKAGES)
    result = subprocess.run(
        [os.path.join(ROOT, ".venv", "bin", "python"), "-c", code],
        cwd="/", capture_output=True, text=True,  # run from / so the project folder is not on the path
    )
    assert result.returncode == 0, result.stderr
```

- [ ] **Step 4: Rename the project and ignore fonts**

```bash
cd ~/bridged-video-generator
python3 - <<'E'
p = "pyproject.toml"
s = open(p).read().replace('name = "versed-video-generator"', 'name = "bridged-video-generator"')
open(p, "w").write(s)
p = ".gitignore"
s = open(p).read().rstrip("\n") + "\n\n# Licensed fonts never go into git\ndesign-assets/*.otf\ndesign-assets/*.ttf\ndesign-assets/*.woff\ndesign-assets/*.woff2\n"
open(p, "w").write(s)
E
grep -n 'name = ' pyproject.toml; tail -6 .gitignore
```

- [ ] **Step 5: Build the venv and install everything**

```bash
cd ~/bridged-video-generator
python3 -m venv .venv
.venv/bin/pip install --upgrade pip setuptools wheel
.venv/bin/pip install -e ".[dev,align,youtube,envato,docx,page]"
.venv/bin/playwright install chromium
```

Use `timeout: 600000` (openai-whisper pulls in torch and is slow). A system pip too old for the editable install is why the upgrade comes first.

- [ ] **Step 6: Run the scaffold test**

Run: `.venv/bin/python -m pytest tests/test_scaffold.py -v`
Expected: 4 passed.

- [ ] **Step 7: Commit**

```bash
cd ~/bridged-video-generator
git add -A
git status --short | grep -iE "\.env$|\.otf|design-assets/|\.venv|envato_automation" && echo "STOP: something that must not be committed is staged" || echo "clean"
git commit -m "Scaffold from the Versed video generator (b293084)

Tracked files only; Versed's design assets, docs and handoff are left out.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

Expected: prints `clean` before the commit. If it prints STOP, `git reset` and fix `.gitignore` first.

---

### Task 2: Placeholder Bridged design-system snapshot and the new snapshot path

**Files:**
- Create: `design_system/bridged-design-system.md`
- Modify: `shot_list/director_prompt.py:7-8`, `tests/test_director_prompt.py:6-7`
- Test: `tests/test_design_system_snapshot.py`

**Interfaces:**
- Consumes: Task 1's tree (`shot_list/director_prompt.py` defines `DESIGN_SYSTEM_SNAPSHOT`, which `motion_graphics/prompt_writer_prompt.py` and `reviewer_prompt.py` import)
- Produces: `design_system/bridged-design-system.md` containing the headings `## The one rule`, `## The 7 frame types (choosing one from the script line)`, `## Content fundamentals`, `## Visual foundations`, `## Pre-ship checklist`; `DESIGN_SYSTEM_SNAPSHOT` pointing at it

- [ ] **Step 1: Write the failing test**

Create `tests/test_design_system_snapshot.py`:

```python
import os
import re

from shot_list.director_prompt import DESIGN_SYSTEM_SNAPSHOT
from shot_list.models import ARCHETYPES

# The director, prompt-writer and reviewer prompts tell their subagents to read these sections.
REQUIRED_HEADINGS = [
    "## The one rule",
    "## The 7 frame types (choosing one from the script line)",
    "## Content fundamentals",
    "## Visual foundations",
    "## Pre-ship checklist",
]


def _text():
    return open(DESIGN_SYSTEM_SNAPSHOT, encoding="utf-8").read()


def test_snapshot_is_the_bridged_file_and_exists():
    assert os.path.basename(DESIGN_SYSTEM_SNAPSHOT) == "bridged-design-system.md"
    assert os.path.isabs(DESIGN_SYSTEM_SNAPSHOT) and os.path.exists(DESIGN_SYSTEM_SNAPSHOT)


def test_snapshot_keeps_every_section_the_prompts_read():
    text = _text()
    for heading in REQUIRED_HEADINGS:
        assert heading in text, f"snapshot lost the section {heading!r}"


def test_snapshot_lists_exactly_the_archetypes_the_code_accepts():
    text = _text()
    for name in ARCHETYPES:
        assert f"`{name}`" in text


def test_snapshot_carries_no_versed_content():
    lowered = _text().lower()
    assert not re.search(r"(?<![a-z])versed", lowered) and "nagel" not in lowered
```

- [ ] **Step 2: Run it to see it fail**

Run: `.venv/bin/python -m pytest tests/test_design_system_snapshot.py -v`
Expected: FAIL (`DESIGN_SYSTEM_SNAPSHOT` still names `copy-of-versed-design-system.md`, which does not exist).

- [ ] **Step 3: Create the placeholder snapshot**

Create `design_system/bridged-design-system.md`:

````markdown
# Bridged Design System — rules snapshot (PLACEHOLDER)

**This is a placeholder. The Bridged design system has not been created yet. Do NOT run Stage 3
(motion graphics) until Josh replaces this file with the real design system's readme and sets
`GRAPHICS_DESIGN_SYSTEM_NAME` in `.env`.**

This file is what the Stage 1 director, Stage 3 prompt-writer, and Stage 3 reviewer read as
their design rules. The design system itself lives in claude.ai/design (attached to every
Stage 3 canvas by name via `GRAPHICS_DESIGN_SYSTEM_NAME`); this file is only a local copy so
unattended subagents can read the rules. **Refresh it (re-copy the design system's readme)
whenever that design system changes.**

Pipeline notes (not part of the design system's readme):
- The 7 frame types below are the **only** graphic archetypes: `chart_card`, `definition`,
  `distance`, `org_chart`, `place_chip`, `route_overlay`, `territory_map`. They are placeholders
  carried over so the code works; when the Bridged design system defines its own set, update
  `ARCHETYPES` in `shot_list/models.py`, the lists in `shot_list/director_prompt.py` and the
  tests together.
- The headings below are read by name by the prompts. A refresh must keep "The one rule",
  "The 7 frame types", "Content fundamentals", "Visual foundations" and "Pre-ship checklist".

## The one rule

(Defined by the Bridged design system.)

## The 7 frame types (choosing one from the script line)

| Type (`archetype` value) | Use when the fact is... | Look |
|---|---|---|
| `place_chip` | a place named over real photography | (defined by the Bridged design system) |
| `definition` | a term and its dictionary-style definition/quote | (defined by the Bridged design system) |
| `chart_card` | a quantity over time or a comparison of series | (defined by the Bridged design system) |
| `org_chart` | who controls/contains whom | (defined by the Bridged design system) |
| `distance` | distance or travel time between two places | (defined by the Bridged design system) |
| `route_overlay` | movement or a route between places | (defined by the Bridged design system) |
| `territory_map` | the extent or control of land | (defined by the Bridged design system) |

## Content fundamentals

(Defined by the Bridged design system.)

## Visual foundations

(Defined by the Bridged design system.)

## Pre-ship checklist (derived from the rules above; use when judging a rendered frame)

<!-- Pipeline-added section (not in the design system's readme): the reviewer prompt depends on it; it must survive snapshot refreshes. -->

- Is it exactly one of the frame types, matching the target archetype and data (no wrong,
  missing or fabricated values)?
- If two or more countries/territories are highlighted, does each have its own distinct color
  (never all the same, no blue) with the border between them clearly drawn so they do not read
  as one country?
- Is there one clear focal point?
- Is every piece of text in the design system's typeface?
- Are numbers comma-formatted, titles in the right case, labels short (no paragraphs)?
- Does it read at phone size (480p)?
````

- [ ] **Step 4: Point the code and the existing test at the new file**

```bash
cd ~/bridged-video-generator
python3 - <<'E'
for p in ("shot_list/director_prompt.py", "tests/test_director_prompt.py"):
    s = open(p).read()
    assert "copy-of-versed-design-system.md" in s
    open(p, "w").write(s.replace("copy-of-versed-design-system.md", "bridged-design-system.md"))
E
git grep -n "copy-of-versed" -- . ':!docs' ':!CLAUDE.md'
```

Expected: the grep prints nothing (CLAUDE.md is handled in Task 5).

- [ ] **Step 5: Run the snapshot tests and the prompt tests**

Run: `.venv/bin/python -m pytest tests/test_design_system_snapshot.py tests/test_director_prompt.py tests/test_reviewer_prompt.py tests/test_prompt_writer_prompt.py tests/test_director_provided_data.py -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add design_system tests/test_design_system_snapshot.py shot_list/director_prompt.py tests/test_director_prompt.py
git commit -m "Add placeholder Bridged design-system snapshot and point the prompts at it

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Make the four subagent prompts Bridged (no Versed, no Nagel)

**Files:**
- Modify: `shot_list/director_prompt.py:80,82`, `shot_list/cut_planner.py:68`, `motion_graphics/prompt_writer_prompt.py:10,12,25,29`, `motion_graphics/reviewer_prompt.py:15,18,28-30`, `tests/fixtures/director_prompt_no_links.txt:1,3`, `tests/test_prompt_writer_prompt.py:26-27`
- Test: `tests/test_prompts_are_bridged.py`

**Interfaces:**
- Consumes: `build_director_prompt(segments)` (`shot_list.director_prompt`), `build_prompt_writer_prompt(archetype, data, target_duration)` (`motion_graphics.prompt_writer_prompt`), the reviewer prompt builder in `motion_graphics/reviewer_prompt.py`, and the cut planner prompt builder in `shot_list/cut_planner.py`
- Produces: prompts that say "Bridged documentary video", never mention a specific typeface, and take the design rule from the snapshot

- [ ] **Step 1: Write the failing test**

Create `tests/test_prompts_are_bridged.py`:

```python
import re

from motion_graphics.prompt_writer_prompt import build_prompt_writer_prompt
from motion_graphics.reviewer_prompt import build_reviewer_prompt
from shot_list.cut_planner import FootageCut, build_cut_planner_prompt
from shot_list.director_prompt import build_director_prompt
from shot_list.segments import Segment


def _all_prompts():
    return {
        "director": build_director_prompt([Segment("graphic", "Cargo moved through the port.", 0, 5)]),
        "prompt_writer": build_prompt_writer_prompt(archetype="chart_card", data={}, target_duration=3.0),
        "reviewer": build_reviewer_prompt(
            archetype="territory_map", data={"territory": "Panama"},
            screenshot_path="/tmp/x.png", attempt=1, max_attempts=3,
        ),
        "cut_planner": build_cut_planner_prompt(
            [FootageCut(0, 0.0, 4.0, "Ships queue at the canal", "Panama Canal")]
        ),
    }


def test_no_prompt_mentions_versed_or_a_specific_typeface():
    for name, prompt in _all_prompts().items():
        lowered = prompt.lower()
        assert not re.search(r"(?<![a-z])versed", lowered), f"{name} prompt still says Versed"
        assert "nagel" not in lowered, f"{name} prompt still names the Nagel font"


def test_every_prompt_says_bridged_documentary_video():
    for name, prompt in _all_prompts().items():
        assert "Bridged documentary video" in prompt, f"{name} prompt does not say Bridged"
```

- [ ] **Step 2: Run it to see it fail**

Run: `.venv/bin/python -m pytest tests/test_prompts_are_bridged.py -v`
Expected: FAIL ("prompt still says Versed").

- [ ] **Step 3: Edit the prompts, the golden fixture and the old test**

```bash
cd ~/bridged-video-generator
python3 - <<'E'
def sub(path, pairs):
    s = open(path, encoding="utf-8").read()
    for old, new in pairs:
        assert old in s, (path, old)
        s = s.replace(old, new)
    open(path, "w", encoding="utf-8").write(s)

sub("shot_list/director_prompt.py", [
    ("director agent for a Versed documentary video", "director agent for a Bridged documentary video"),
    ("(the Versed design system)", "(the Bridged design system)"),
])
sub("shot_list/cut_planner.py", [
    ("footage planner for a Versed documentary video", "footage planner for a Bridged documentary video"),
])
sub("motion_graphics/prompt_writer_prompt.py", [
    ("one motion-graphic beat of a Versed documentary video", "one motion-graphic beat of a Bridged documentary video"),
    ("(the Versed design system rules)", "(the Bridged design system rules)"),
    ("The Versed design system is already attached", "The Bridged design system is already attached"),
    ('the design system\'s rules — "Red marks the subject" and \\\nnothing else, Nagel is the only typeface, and the correct ground/texture for this frame type.',
     'the design system\'s rules — its "one rule" from \\\n"The one rule", its single typeface, and the correct ground/texture for this frame type.'),
])
sub("motion_graphics/reviewer_prompt.py", [
    ("rendered motion-graphic beat for a Versed documentary video", "rendered motion-graphic beat for a Bridged documentary video"),
    ("(the Versed design system rules)", "(the Bridged design system rules)"),
    ("red only marking the \\\nsubject; one clear focal point; a single typeface (Nagel), no serif; the right ground/texture \\\nfor this frame type and no drop shadows on shapes;",
     "the design system's one rule \\\nobeyed; one clear focal point; the design system's single typeface; the right ground/texture \\\nfor this frame type;"),
])
sub("tests/fixtures/director_prompt_no_links.txt", [
    ("director agent for a Versed documentary video", "director agent for a Bridged documentary video"),
    ("(the Versed design system)", "(the Bridged design system)"),
])
sub("tests/test_prompt_writer_prompt.py", [
    ('    assert "Nagel" in prompt\n    assert "Red marks the subject" in prompt\n',
     '    assert "The one rule" in prompt\n    assert "Nagel" not in prompt\n'),
])
E
git grep -n -iE "(^|[^a-z])versed|nagel" -- shot_list motion_graphics tests/fixtures/director_prompt_no_links.txt tests/test_prompt_writer_prompt.py
```

Expected: the grep prints nothing (the pattern skips words like "reversed"). If an `assert old in s` fails, the line wrapping in the file differs from this plan: open the file at the quoted line numbers and make the same edit by hand (the intent is stated in step 4's replacements), then re-run the grep.

- [ ] **Step 4: Run the prompt tests and the whole suite**

Run: `.venv/bin/python -m pytest tests/test_prompts_are_bridged.py tests/test_reviewer_prompt.py tests/test_prompt_writer_prompt.py tests/test_director_prompt.py tests/test_director_provided_data.py -q`
Expected: all pass. Then `.venv/bin/python -m pytest tests -q` with `timeout: 400000`; expected: all pass (1 skipped is normal).

- [ ] **Step 5: Commit**

```bash
git add -A shot_list motion_graphics tests
git commit -m "Prompts: Bridged documentary video, no hard-coded typeface or colour rule

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Rename the remaining Versed identifiers in code

**Files:**
- Modify: `footage/archive_types.py:13`, `tests/test_archive_commons.py:224`, `tests/test_archive_loc.py:92`, `page_intake/capture.py` (every `__versedRange` and `'versed'`), `tests/test_page_capture.py:70,143,147`, `shot_list/align.py:49`, `tests/test_align.py:50`, `page_intake/capture.py:133`
- Test: `tests/test_no_versed_left.py`

**Interfaces:**
- Consumes: Tasks 1-3
- Produces: no tracked file outside `docs/`, `HANDOFF.md` and `CLAUDE.md` contains the word "versed" (any case)

- [ ] **Step 1: Write the failing test**

Create `tests/test_no_versed_left.py`:

```python
import os
import subprocess

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def test_no_versed_left_in_code_or_tests():
    out = subprocess.run(
        # (^|[^a-z])versed skips words like "reversed" but still catches __versedRange, VersedVideo...
        ["git", "grep", "-nIiE", "(^|[^a-z])versed", "--", ".", ":!docs", ":!HANDOFF.md", ":!CLAUDE.md",
         ":!tests/test_no_versed_left.py", ":!tests/test_scaffold.py",
         ":!tests/test_prompts_are_bridged.py", ":!tests/test_design_system_snapshot.py",
         ":!tests/test_docs_are_bridged.py"],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert out.stdout == "", "leftover Versed names:\n" + out.stdout
```

- [ ] **Step 2: Run it to see it fail**

Run: `.venv/bin/python -m pytest tests/test_no_versed_left.py -v`
Expected: FAIL listing the `VersedVideoGenerator/0.1` user-agent lines, the `__versedRange` lines and the two comments.

- [ ] **Step 3: Make the renames**

```bash
cd ~/bridged-video-generator
python3 - <<'E'
def sub(path, pairs):
    s = open(path, encoding="utf-8").read()
    for old, new in pairs:
        assert old in s, (path, old)
        s = s.replace(old, new)
    open(path, "w", encoding="utf-8").write(s)

sub("footage/archive_types.py", [("VersedVideoGenerator/0.1", "BridgedVideoGenerator/0.1")])
sub("tests/test_archive_commons.py", [("VersedVideoGenerator/0.1", "BridgedVideoGenerator/0.1")])
sub("tests/test_archive_loc.py", [("VersedVideoGenerator/0.1", "BridgedVideoGenerator/0.1")])
sub("page_intake/capture.py", [
    ("__versedRange", "__bridgedRange"),
    ("::highlight(versed)", "::highlight(bridged)"),
    ("CSS.highlights.set('versed'", "CSS.highlights.set('bridged'"),
    ("CSS.highlights.delete('versed')", "CSS.highlights.delete('bridged')"),
    ("# sampled from Josh's frame design-assets/frames/Screenshot 2026-10-03 at 1.07.30 PM.png",
     "# the highlight green Josh chose"),
])
sub("tests/test_page_capture.py", [("__versedRange", "__bridgedRange")])
sub("shot_list/align.py", [("# Versed scripts use typographic quotes", "# Scripts use typographic quotes")])
sub("tests/test_align.py", [("# real Versed scripts use typographic quotes", "# real scripts use typographic quotes")])
E
git grep -nIiE '(^|[^a-z])versed' -- . ':!docs' ':!HANDOFF.md' ':!CLAUDE.md' ':!tests/test_no_versed_left.py' ':!tests/test_scaffold.py' ':!tests/test_prompts_are_bridged.py' ':!tests/test_design_system_snapshot.py' ':!tests/test_docs_are_bridged.py'
```

Expected: the final grep prints nothing. If the `HIGHLIGHT_GREEN` comment text differs, open `page_intake/capture.py` around line 133 and keep only the colour value; the comment must not contain "versed".

- [ ] **Step 4: Run the affected tests**

Run: `.venv/bin/python -m pytest tests/test_no_versed_left.py tests/test_page_capture.py tests/test_archive_commons.py tests/test_archive_loc.py tests/test_align.py -q`
Expected: all pass (the page-capture tests drive real Chromium and take a minute).

- [ ] **Step 5: Commit**

```bash
git add -A footage page_intake shot_list tests
git commit -m "Rename the remaining Versed identifiers (user-agent, page-capture JS names, comments)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: CLAUDE.md and a fresh HANDOFF.md

**Files:**
- Modify: `CLAUDE.md:1,269,898-910`
- Create: `HANDOFF.md`
- Test: `tests/test_docs_are_bridged.py`

**Interfaces:**
- Consumes: Tasks 1-4
- Produces: CLAUDE.md that names the Bridged snapshot and says Stage 3 is blocked until the design system exists; a HANDOFF.md describing the project's real state

- [ ] **Step 1: Write the failing test**

Create `tests/test_docs_are_bridged.py`:

```python
import os
import re

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _read(name):
    return open(os.path.join(ROOT, name), encoding="utf-8").read()


def test_claude_md_is_bridged():
    text = _read("CLAUDE.md")
    assert text.startswith("# Bridged Video Generator")
    assert not re.search(r"(?<![a-z])versed", text.lower()) and "nagel" not in text.lower()
    assert "design_system/bridged-design-system.md" in text
    assert "placeholder" in text.lower()


def test_handoff_exists_and_says_what_is_next():
    text = _read("HANDOFF.md")
    assert text.startswith("# Bridged Video Generator")
    for needle in ("design system", "GRAPHICS_DESIGN_SYSTEM_NAME", "ARCHETYPES"):
        assert needle in text
```

- [ ] **Step 2: Run it to see it fail**

Run: `.venv/bin/python -m pytest tests/test_docs_are_bridged.py -v`
Expected: FAIL (CLAUDE.md still starts with "# Versed Video Generator").

- [ ] **Step 3: Edit CLAUDE.md**

```bash
cd ~/bridged-video-generator
python3 - <<'E'
p = "CLAUDE.md"
s = open(p, encoding="utf-8").read()
pairs = [
    ("# Versed Video Generator — Shot List Generation Workflow", "# Bridged Video Generator — Shot List Generation Workflow"),
    ("copy-of-versed-design-system.md", "bridged-design-system.md"),
    ('(currently\n`GRAPHICS_DESIGN_SYSTEM_NAME="Copy of Versed Design System"`)', "(not set yet: the Bridged\ndesign system has to be created first)"),
    ("This is the Design System project built via `/design-sync`\nfrom Josh's 8 published Versed frames plus the Nagel VF font. It defines exactly 7 graphic archetypes (`chart_card`, `definition`,",
     "This is the Bridged design system project in\nClaude Design, which Josh builds from his own Bridged frames and font. Until it exists the local\nsnapshot is a placeholder and Stage 3 must NOT be run. The placeholder lists 7 archetypes (`chart_card`, `definition`,"),
]
for old, new in pairs:
    assert old in s, old
    s = s.replace(old, new)
open(p, "w", encoding="utf-8").write(s)
E
grep -n -iE "(^|[^a-z])versed|nagel" CLAUDE.md
```

Expected: the grep prints nothing. If an assertion fails, open CLAUDE.md at the lines quoted (1, 269, 898-910), make the same edit by hand, and re-run the grep until it is empty.

- [ ] **Step 4: Create HANDOFF.md**

Create `HANDOFF.md`:

```markdown
# Bridged Video Generator — Handoff

Created 2026-10-05 as a copy of the Versed video generator (Versed's `main` at `b293084`),
with the Bridged design system left to be built. Design: `docs/superpowers/specs/2026-10-05-bridged-video-generator-design.md`.
Plan: `docs/superpowers/plans/2026-10-05-bridged-video-generator.md`.

## What works today
Stages 1, 2 and 4 (shot list, footage sourcing, final assembly) work exactly as in the original,
including the 10-channel YouTube blacklist (`footage/youtube_channels.py`), the 1,000,000-subscriber
rule, and the YouTube look (mirror, 3% zoom, light grain, half-strength vignette).

## What is blocked: Stage 3 (motion graphics)
`design_system/bridged-design-system.md` is a PLACEHOLDER. Do not run Stage 3 until:
1. Josh builds the Bridged design system in claude.ai/design (palette, typeface, frame types) and
   puts his example frames and font in `design-assets/` (the font is gitignored).
2. The design system's readme is copied over `design_system/bridged-design-system.md`, keeping the
   headings "The one rule", "The 7 frame types", "Content fundamentals", "Visual foundations" and
   "Pre-ship checklist" (`tests/test_design_system_snapshot.py` pins them).
3. `GRAPHICS_DESIGN_SYSTEM_NAME` is added to `.env`: the design system's exact display name.
4. If the design system defines a different set of frame types, `ARCHETYPES` in
   `shot_list/models.py`, the lists in `shot_list/director_prompt.py` and the tests change together.

## Shared with the Versed generator
- The same `PEXELS_API_KEY` and `YOUTUBE_API_KEY` (YouTube's daily quota is per key, so the two
  generators share 10,000 units a day; each project's tracker only sees its own spend).
- A copy of the Envato login profile (`.envato_automation_profile/`, gitignored). If Envato says
  the session expired, re-run `tests/fixtures/envato_automation_spike.py` and log in with email and
  password (not "Sign in with Google").

## Not done yet
- No GitHub repo (Josh decides when).
- Logistics-specific footage query tuning (after a first real test with a Bridged script and voiceover).
- A first real end-to-end run.
```

- [ ] **Step 5: Run the doc tests and the "no Versed" test**

Run: `.venv/bin/python -m pytest tests/test_docs_are_bridged.py tests/test_no_versed_left.py -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add CLAUDE.md HANDOFF.md tests/test_docs_are_bridged.py
git commit -m "Docs: CLAUDE.md for Bridged, fresh HANDOFF.md

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Environment, Envato login, and full verification

**Files:**
- Create (not committed): `.env`, `.envato_automation_profile/`
- Modify: none
- Test: the full suite plus the live Envato check

**Interfaces:**
- Consumes: Tasks 1-5; `search_envato(query: str, exclude_ids: frozenset[str], profile_dir: str, max_results: int = 7)` from `footage.envato`
- Produces: a project that is ready for a first real run of Stages 1, 2 and 4

- [ ] **Step 1: Create `.env` with only the two API keys (values are never printed)**

```bash
cd ~/bridged-video-generator
grep -E '^(PEXELS_API_KEY|YOUTUBE_API_KEY)=' ~/versed-video-generator/.env > .env
sed 's/=.*/=<set>/' .env
git check-ignore .env
```

Expected: shows `PEXELS_API_KEY=<set>` and `YOUTUBE_API_KEY=<set>` only (no `GRAPHICS_DESIGN_SYSTEM_NAME`), and `git check-ignore` prints `.env`.

- [ ] **Step 2: Copy the Envato login profile**

Make sure no Chromium/Playwright process is using the Versed profile, then copy:

```bash
pgrep -fl "envato_automation_profile" || echo "no process using it"
cp -R ~/versed-video-generator/.envato_automation_profile ~/bridged-video-generator/.envato_automation_profile
du -sh ~/bridged-video-generator/.envato_automation_profile
git -C ~/bridged-video-generator check-ignore .envato_automation_profile
```

Expected: `no process using it`, a size near 1.0G, and the folder name echoed by `check-ignore`. If a process is listed, stop and ask Josh to close it; do not kill it.

- [ ] **Step 3: Live Envato check from the new location**

```bash
cd ~/bridged-video-generator
.venv/bin/python -c "
from footage.envato import search_envato
results = search_envato('container ship at sea', frozenset(), '.envato_automation_profile', max_results=3)
print(len(results), 'result(s)')
for r in results: print(r.item_id, r.title)
"
```

Use `timeout: 300000`. Expected: `3 result(s)` with titles. If it raises `EnvatoError: landed on Envato's sign-in page`, STOP and tell Josh: the copied session did not carry over and he needs to log in again with the spike script (email and password). Do not retry in a loop and do not use Google sign-in.

- [ ] **Step 4: Full suite from a clean state**

Run: `cd ~/bridged-video-generator && .venv/bin/python -m pytest tests -q` with `timeout: 400000`.
Expected: everything passes (1 skipped is normal).

- [ ] **Step 5: Install check with nothing on the path**

```bash
cd / && ~/bridged-video-generator/.venv/bin/python -c "import shot_list, footage, assembly, motion_graphics, script_input, graph_intake, page_intake, image_intake; print('all 8 packages import')"
cd ~/bridged-video-generator && git status --short && git log --oneline
```

Expected: prints `all 8 packages import`; `git status` is clean (the venv, `.env` and the Envato profile are ignored); the log shows the spec, plan and five task commits.

- [ ] **Step 6: Commit anything left and report**

Nothing should be left to commit. Report to Josh: tests passed, Envato search result, and that the GitHub repo has not been created. Ask whether to create the private GitHub repo `bridgedvideogenerator` and push.
