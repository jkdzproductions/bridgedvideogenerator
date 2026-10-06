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
