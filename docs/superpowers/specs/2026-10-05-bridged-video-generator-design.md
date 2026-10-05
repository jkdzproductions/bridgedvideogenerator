# Bridged Video Generator — Design

Date: 2026-10-05

## Purpose

Josh runs two YouTube channels, Versed and Bridged (logistics, natural resources, supply chains). Versed already has a working video generator (`~/versed-video-generator/`) that turns a marked-up script plus its voiceover into a finished documentary video. Bridged has only a script generator (`~/bridged/`).

Goal: a Bridged video generator that works exactly like the Versed one, differing only in the design style of its motion graphics, which Josh will create himself in Claude Design.

Success: given a Bridged script (marked up the same way as Versed scripts) and its voiceover, the new project produces a finished video through the same four stages, with graphics in the Bridged design style.

## Decisions (agreed with Josh)

- **Approach: copy and adapt.** The new project is a copy of the Versed generator with the Bridged design system swapped in. No shared package, and the Versed generator is not touched.
- **Separate project:** `~/bridged-video-generator/`, its own git repo and its own private GitHub repo. Separate from Versed's generator and from the Bridged script generator (`~/bridged/`).
- **Fresh git history:** the copy starts as a clean repo, not carrying Versed's commit history.
- **Script markup unchanged:** italic = motion graphic, bold = talking-head placeholder, italic+image link = linked graph, italic+`#:~:text=` page link = page highlight, non-italic image link = show-as-is image. `.txt`/`.md` scripts use `*graphic*` and `**talking head**`.
- **Envato login profile is copied** (`.envato_automation_profile/`, about 1 GB, gitignored), so no fresh login is needed. API keys `PEXELS_API_KEY` and `YOUTUBE_API_KEY` are reused in the new `.env`.
- **Footage query tuning for logistics** (ships, ports, trains, warehouses) is out of scope for the first build. It happens after a first real test.

## What is copied unchanged

All pipeline code and tests: `shot_list/`, `footage/`, `assembly/`, `motion_graphics/`, `script_input/`, `graph_intake/`, `page_intake/`, the archival-imagery code, `pyproject.toml`, `tests/`, and the CLAUDE.md stage workflow (with the Versed-to-Bridged renames below).

## What changes

1. **Prompts.** "Versed documentary" becomes "Bridged documentary" in `shot_list/director_prompt.py`, `shot_list/cut_planner.py`, `motion_graphics/prompt_writer_prompt.py` and `motion_graphics/reviewer_prompt.py`, and the director prompt text file / golden fixtures that mention it.
2. **Design system snapshot.** `design_system/copy-of-versed-design-system.md` is replaced by `design_system/bridged-design-system.md`. The `DESIGN_SYSTEM_SNAPSHOT` path constants in the director, prompt-writer and reviewer prompts point at it. Until Josh's design system exists, the file is a clearly marked placeholder, and the Versed content is not carried over into it. The snapshot must keep a "Pre-ship checklist" section (the reviewer depends on it).
3. **Archetypes.** `ARCHETYPES` in `shot_list/models.py` (and the test asserting it) must match the Bridged design system's frame types. Until the design system exists, the 7 Versed types stay as placeholders.
4. **`.env`.** `GRAPHICS_DESIGN_SYSTEM_NAME` is set to the exact display name of the Bridged design system in Claude Design once it exists. `YOUTUBE_DAILY_QUOTA_UNITS` optional as before.
5. **Renames.** User-agent `VersedVideoGenerator/0.1` becomes `BridgedVideoGenerator/0.1`; the page-capture JavaScript names `__versedRange` and `'versed'` become Bridged names; `pyproject.toml` project name; CLAUDE.md and a new HANDOFF.md written for Bridged.

## What is left out of the copy

Versed's design system snapshot, `design-assets/` (the licensed Nagel font and Versed frames), `archival_work/`, `assembly_staging/`, all generated run files (candidates, prompts, responses, shot lists, outputs, thumbnails, page stills), the `.venv`, and `docs/superpowers/` history. A new `.venv` is built with `pip install -e ".[dev,align,youtube,envato,docx,page]"` and `playwright install chromium`.

## Shared-resource caveat

The YouTube Data API daily quota is per API key. With the same key, Bridged and Versed share one 10,000-unit daily budget, and the local quota tracker (`youtube_quota_usage.json`) is per project, so each project's tracker will not see the other's spend. Josh can create a second key to separate them.

## Josh's side vs. mine

- **Josh:** builds the Bridged design system in Claude Design (palette, fonts, frame types), then gives me its exact name, and the readme contents for the snapshot.
- **Mine:** everything above. Stages 1, 2 and 4 (shot list, footage, assembly) work without the design system. Stage 3 (motion graphics) is blocked until it exists.

## Testing and verification

- Full test suite passes in the new project (Versed's suite is about 600 tests; the ARCHETYPES and prompt-fixture tests are adjusted for the renames).
- A fresh `pip install -e .` followed by plain `python -c "import <package>"` for every top-level package, with no `PYTHONPATH` (the packaging-list regression noted in Versed's history).
- No leftover "Versed" in code, prompts or snapshot except in deliberate comments; checked by grep.
- Envato profile check: a real Envato search from the new location succeeds without re-login.
- Josh's end-to-end run with a real Bridged script and voiceover is the final acceptance test, once he has them.

## Out of scope

Sharing code between the two generators; changing the script markup; logistics-specific footage tuning; wiring the video generator into the script generator; building the Bridged design system itself.
