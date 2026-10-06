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

## Stage 3 live status (2026-10-06)
Live-verified on "Bridged Design System (Final)": all 7 types rendered once each (one test clip
per type, data from Josh's frames, 4.0 s, 1920x1080, ffprobe-checked, reviewer approved all).
- `diamond_flow`: approved first try; Josh approved it.
- `chart_card`: approved first try, then Josh asked for plain ink text with no black chips; the
  snapshot says so (commit 05f458d) and the re-render was approved by the reviewer and Josh.
- `fan_out`: one correction (first drew a ferry glyph; Claude Design hand-drew a warship because
  its icon set has none). Reviewer-approved only.
- `year_range`, `then_vs_now`, `territory_map`, `network_map`: approved first try by the reviewer;
  Josh has not individually signed them off.

Open items for Josh:
- (a) The fan-out warship is hand-drawn by Claude Design, not from the design system (his own
  frame 10 has a custom warship illustration).
- (b) Glyph icons (ships, bank, oil well, hammer, factory, hard hat) are Font Awesome Free solid
  stand-ins, not Bridged's icon set. Flags load from flagcdn.com (needs internet to preview or
  export).
- (c) Satellite imagery needs a credit (CC BY 4.0). The territory map clip kept a small on-screen
  credit; the network map clip hid it. Josh has not ruled on on-screen vs description. Description
  text: "Sentinel-2 cloudless by EOX IT Services GmbH (contains modified Copernicus Sentinel data
  2016), CC BY 4.0".
- (d) Fan-out lays out ship-on-top with the tree below (his frame 10 has ship left, tree right);
  year_range sits slightly left of centre.
- (e) The design system's own Chart card template still draws a black chip around the title
  (its chip component always draws a box). Josh may want the template changed to plain text; only
  he can do that in Claude Design.

Photo credit: when a Commons photo is used, credit it in the video description (diamond_flow's
Onassis photo: Pieter Jongerhuis for Anefo, Dutch National Archives, via Wikimedia Commons).
Operational lessons for Stage 3 runs are in CLAUDE.md ("Live-run notes (2026-10-06)").

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
Publishing the design system is not required: the Stage 3 picker lists it by name while it is
unpublished.

## Shared with the Versed generator
- The same `PEXELS_API_KEY` and `YOUTUBE_API_KEY` (YouTube's daily quota is per key, so the two
  generators share 10,000 units a day; each project's tracker only sees its own spend).
- A copy of the Envato login profile (`.envato_automation_profile/`, gitignored). If Envato says
  the session expired, re-run `tests/fixtures/envato_automation_spike.py` and log in with email and
  password (not "Sign in with Google").

## Not committed on purpose
`design-assets/` (your font and frames), `.env`, the Envato profile and the `.venv` are gitignored.
