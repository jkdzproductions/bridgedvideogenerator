# Bridged Video Generator — Handoff

Created 2026-10-05 as a copy of the Versed video generator; updated 2026-10-06 for the real
Bridged design system. Designs: `docs/superpowers/specs/`. Plans: `docs/superpowers/plans/`.

## NEXT SESSION: start here (written 2026-10-06, end of session)

State: `main` is pushed and clean at `ce28988` (all 7 Bridged frame types built, reviewed, merged, live-tested). Nothing is half-done in git.

### 1. Decision to implement: maps (Josh's ruling, 2026-10-06)
Josh saw diagonal lines through the un-highlighted land and sea of the territory map (`graphics_output/beat_5.mp4`; the network map `beat_6.mp4` has darker vertical bands too). Cause: the free EOX Sentinel-2 satellite mosaic is stitched from separate satellite passes, so the seams are in the photo itself (not an overlay). Josh compared three fixes (comparison image: `design-assets/map-options/japan_map_options_2026-10-06.png`, local only) and ruled:
- **Use option 2's basemap: NASA Blue Marble** (smooth, no seams, public domain so no on-screen credit line is needed).
- **But the highlight must look like option 1:** Japan (and any highlighted territory) drawn with the DETAILED coastline and clean white border, not the template's coarse blocky polygon (option 2 and the flat map came out with a blocky Japan; option 1 used a finer coastline dataset and looked right).
- Not chosen: option 1 (blurred EOX satellite: too murky) and option 3 (flat teal/sand map: different look from his frame 8).
The three test canvases still exist in Claude Design (Josh's account): option 1 `https://claude.ai/design/p/a7a870c2-7ce0-466e-8b4a-e321ea7c5491`, option 2 (NASA, coarse Japan) `https://claude.ai/design/p/96ff8f77-6156-452c-b7ea-e1556512509b`, option 3 (flat) `https://claude.ai/design/p/e4fdfb87-7760-4543-bd3d-fc8b3b2fb6fd`. Two of those tabs may still be open in Josh's Chrome.

### 2. Tasks, in order
1. **Fix the map clips:** re-render the Japan territory map using the NASA Blue Marble basemap with the detailed coastline (easiest: open the option 2 canvas and send a chat correction asking for the detailed coastline dataset like option 1 used, with a crisp white edge, nothing else changed), then re-review with the reviewer subagent and re-export `graphics_output/beat_5.mp4`. Re-render the network map (`beat_6`) on the NASA basemap too. Procedure and click path: CLAUDE.md Stage 3 plus its "Live-run notes (2026-10-06)".
2. **Put the rule in the snapshot** (`design_system/bridged-design-system.md`, map rule / Visual foundations / Pre-ship checklist): satellite grounds use NASA Blue Marble (not EOX Sentinel-2, whose seams show); highlighted territories use the detailed coastline; no on-screen credit line is needed for NASA imagery. Add a test in `tests/test_design_system_snapshot.py` like the chart-text one. Do it with the subagent-driven process (implementer then reviewer; never fix it in the controller session); also update the "Open items" below.
3. **Josh's sign-off** is still pending on 5 of the 7 test clips: fan_out (hand-drawn warship), year_range, then_vs_now, territory_map (being redone), network_map (being redone). He has approved diamond_flow and chart_card only.
4. Then: first real end-to-end test video with a real Bridged script + voiceover (Stages 1, 2, 4 work without Stage 3); logistics-specific footage tuning after that; overlay types (footage_callout, pin_chip, split_compare) need overlay compositing in Stage 4.
5. Optional: "(except chart_card)" wording for the snapshot's "Title chip centred at the top" / "title chips 56-72" lines; the director prompt does not point at the "Data to extract" column; old-format shot lists fail with a bare `KeyError` at Stage 3 step 2a (`TEMPLATE_NAMES`); CLAUDE.md snapshot-refresh text still says "re-copy the readme" while this file says to read the readme plus both guideline files.

### 3. How Josh likes to work
Plain-language explanations; he asks before anything is pushed (he said "push" explicitly each time); use the subagent-driven-development process with a reviewer after every task; verify things rather than assert; he reviews rendered frames himself. Bridged and Versed are separate projects (separate folders, repos and design systems): changes to one are never made in the other unless he says both.

### 4. Session scratch
Generated test files (`graphic_beats.json`, `canvas_*.json`, `reviewer_*`, `authoring_prompt_*`, `graphics_screenshots/`, `graphics_output/` with the 7 test clips) are gitignored in this folder and can be deleted or left. The 7+3 test projects in Josh's Claude Design account can be deleted by him.

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
