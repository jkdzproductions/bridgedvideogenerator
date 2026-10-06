# Bridged Video Generator — Handoff

Created 2026-10-05 as a copy of the Versed video generator; updated 2026-10-06 for the real
Bridged design system. Designs: `docs/superpowers/specs/`. Plans: `docs/superpowers/plans/`.

## What works
Stages 1, 2 and 4 (shot list, footage sourcing, final assembly) work as in the original, including
the 10-channel YouTube blacklist (`footage/youtube_channels.py`), the 1,000,000-subscriber rule and
the YouTube look (mirror, 3% zoom, light grain, half-strength vignette).

Stage 3 (motion graphics) uses "Bridged Design System (Final)" (`GRAPHICS_DESIGN_SYSTEM_NAME` in
`.env`) and the local rules snapshot `design_system/bridged-design-system.md`. The director can
choose 7 graphic types: `diamond_flow`, `fan_out`, `year_range`, `then_vs_now`, `chart_card`,
`territory_map`, `network_map`. The allowed list lives in `ARCHETYPES` in `shot_list/models.py`;
change it, the type list in `shot_list/director_prompt.py`, `TEMPLATE_NAMES` in
`motion_graphics/prompt_writer_prompt.py` and the tests together.

## Not built yet
- `footage_callout`, `pin_chip` and `split_compare` (the design system has them) are drawn over
  footage. Stage 4 cannot composite a graphic over footage yet, so the director cannot choose them.
  Building that (transparent clips from Stage 3 plus a compositing step in Stage 4) is the next
  piece of work.
- Article highlight and source exhibit are not graphic types: use a linked page (`#:~:text=`
  highlight) and a non-italic image link in the script.
- Logistics-specific footage query tuning (after a first real test video).
- A first real end-to-end run with a real Bridged script and voiceover.

## Keeping the snapshot in sync
When the design system changes, re-read its readme, `guidelines/bridged-style.md` and
`guidelines/frame-archetypes.md` in claude.ai/design and update the snapshot. Keep the five
headings (`tests/test_design_system_snapshot.py` pins them) and the Pre-ship checklist.
The design system was not published when this was written; if the Stage 3 design-system picker
cannot find it, publish it in Claude Design.

## Shared with the Versed generator
- The same `PEXELS_API_KEY` and `YOUTUBE_API_KEY` (YouTube's daily quota is per key, so the two
  generators share 10,000 units a day; each project's tracker only sees its own spend).
- A copy of the Envato login profile (`.envato_automation_profile/`, gitignored). If Envato says
  the session expired, re-run `tests/fixtures/envato_automation_spike.py` and log in with email and
  password (not "Sign in with Google").

## Not committed on purpose
`design-assets/` (your font and frames), `.env`, the Envato profile and the `.venv` are gitignored.
