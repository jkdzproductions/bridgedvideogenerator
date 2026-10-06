# Bridged Frame Types and Design-System Snapshot — Design

Date: 2026-10-06
Builds on: `2026-10-05-bridged-video-generator-design.md` (the Bridged generator, built and pushed).

## Purpose

Josh built the Bridged design system in Claude Design ("Bridged Design System (Final)"). The Bridged generator still carries 7 placeholder graphic types and a placeholder snapshot. Replace them with the real Bridged design so Stage 1 (director) picks Bridged frame types and Stage 3 (motion graphics) renders them in the Bridged style.

Success: a Bridged script with graphic moments produces a shot list using the new types; Stage 3 renders one clip of each new type in Claude Design using the Bridged design system; Josh signs off on the rendered frames.

## Decisions (agreed with Josh)

- **Scope 1 (first pass): 7 standalone types.** The three footage-overlay types are deferred until Stage 4 can composite over footage.
- **Source of truth for the snapshot:** the design system's readme, `guidelines/bridged-style.md` and `guidelines/frame-archetypes.md` as read from Claude Design on 2026-10-06. Where the readme and the guideline files disagree, `bridged-style.md` wins (it says so itself).
- **Multi-country colour rule stays exactly as it is in the pipeline** (Josh, 2026-10-06): when two or more neighbouring countries are highlighted, each gets its own distinct colour, never blue, and the shared border is drawn as a clearly visible line. A single territory uses the Bridged territory style (cyan) and is not affected.
- **The pipeline's page-highlight green stays `#30fe3e`** (Josh's own frame colour), not the design system's `#08FF02`.
- Version control: work on a branch, merge to `main` when done; no push until Josh says so.

## The 7 frame types (replace the placeholder 7)

`ARCHETYPES` in `shot_list/models.py` becomes exactly these. The snapshot heading stays "The 7 frame types (choosing one from the script line)", so the director prompt's wording "the 7 frame types" remains true.

| `archetype` | Use when the fact is... | Data to extract from the script line | Ground |
|---|---|---|---|
| `diamond_flow` | who pays or does what to whom; what moves where | `actors` (name, what glyph or photo shows them, role colour), `flows` (from, to, label), `money` (amounts shown as green hex badges) | peach paper |
| `fan_out` | what one thing depends on | `subject` (name, glyph), `inputs` (name, glyph or photo each), `heavy` (true if one source dominates, drawn as a double trunk) | peach paper |
| `year_range` | a period and a rate | `start`, `end`, `rate` (value + unit, e.g. "20 / Per year"), optional `flag` (country code) | peach paper |
| `then_vs_now` | how much something shrank or grew | `then` (count, label), `now` (count, label), `unit_glyph`, `title` | peach paper |
| `chart_card` | a quantity over time or a comparison of series | `title`, `subtitle` (range or unit), `series` (label, points), `highlight_period`, `source` | peach paper |
| `territory_map` | where something is; the extent or control of land | `territories` (names), `style` (`fill` / `tint` / `outline`), `pins` (specific sites), optional `date` | dark satellite |
| `network_map` | routes or a network between places | `cities` (names), `route` (order), `vehicle` (ship / plane / train / truck glyph) | dark satellite |

Data is free-form JSON, as today: nothing in code fixes its keys. The "data to extract" column is guidance the director reads from the snapshot. A linked graph image (italic + image link) still arrives as provided data and is built as `chart_card`.

**Not allowed yet** (the director must not choose them; the snapshot lists them as "coming"): `footage_callout`, `pin_chip`, `split_compare`. They are drawn on top of footage, and Stage 4 cannot composite a graphic over footage yet.

**Not graphic types:** article highlight (handled by the existing `page_highlight` beats) and source exhibit (handled by the existing show-as-is image beats).

## Snapshot content

`design_system/bridged-design-system.md` replaces the placeholder. It carries, in this order:
1. Header and pipeline notes (what the file is, where it comes from, refresh rule, the 7 allowed types, the 3 coming types, the two not-graphic types).
2. "The one rule" (the readme's rule, verbatim: structure is ink, colour has a job, with the role-colour table).
3. "The 7 frame types" table above, with an extra "Look" column drawn from the design system's template descriptions.
4. "Content fundamentals" and "Visual foundations" (from the readme, with the exact hex values).
5. The design system's rules from `bridged-style.md` that matter for a rendered frame (two grounds, ink structure, chips, maps, glyphs filled never outline, no arrowheads, no drop shadows, glow only on figures and map labels).
6. "Pre-ship checklist" (kept; the reviewer depends on it), rewritten for Bridged: exactly one of the 7 types with the right data; structure in ink with colour only for a nameable role; filled glyphs only; no arrowheads, no rounded chips, no drop shadows; the multi-country colour rule; one subject per frame; legible at phone size (480p).

No Versed or Nagel-as-Versed wording; "Nagel" is now legitimately the Bridged typeface, so the guard tests that ban "nagel" in prompts and the snapshot change to ban only "versed" (see Tests).

## Code and doc changes

- `shot_list/models.py`: `ARCHETYPES` = the 7 types above.
- `shot_list/director_prompt.py`: the list of type names in the prompt, and the example entry (`"archetype": "chart_card"` stays valid). Golden fixture `tests/fixtures/director_prompt_no_links.txt` updated to match.
- `motion_graphics/prompt_writer_prompt.py` and `reviewer_prompt.py`: remove wording that assumes the old types or Versed colours; the prompt-writer tells the Claude Design AI to use the Bridged design system's own template for the chosen type and its role-colour rules; the reviewer judges against the new Pre-ship checklist.
- `CLAUDE.md` and `HANDOFF.md`: Stage 3 no longer "must not run"; document the 7 types, the 3 deferred overlay types, the publish question once answered, and `GRAPHICS_DESIGN_SYSTEM_NAME` (already set to `Bridged Design System (Final)` in `.env`).
- Tests: `test_models`, `test_director_output`, `test_director_prompt`, `test_prompt_writer_prompt`, `test_reviewer_prompt`, `test_motion_graphics_shotlist_integration`, `test_design_system_snapshot` and `test_prompts_are_bridged` updated for the new type names. The guard tests that banned "nagel" now ban only "versed".

## Verification

- Full suite passes.
- `tests/test_design_system_snapshot.py` pins the five headings and that the snapshot lists exactly the 7 types and names none of the 3 deferred ones as allowed.
- Live Stage 3 spike (needs Josh's logged-in Chrome and the `claude-in-chrome` extension): one graphic of each of the 7 types rendered in Claude Design with "Bridged Design System (Final)" attached. This also settles whether the design system must be published for the picker to list it; if it must, Josh publishes it.
- Josh reviews each rendered frame (the automated check cannot see them) and signs off.

## Known gaps and risks

- The design system's readme and `frame-archetypes.md` disagreed on 2026-10-06 (12 types with "Org/structure" and "Source exhibit" vs 11 templates with "Chart card"). This spec follows the 11 templates. If the final system differs, the type table changes with it.
- Per Josh's chat in Claude Design, the Bridged templates' layouts may still partly be Versed's; the live spike will show it.
- Photos inside diamonds come from Wikimedia Commons through the design system's own image check; the pipeline's era rule (historical years get period-appropriate imagery) stays.
- The YouTube quota is shared with Versed (same key), as before.

## Out of scope

Overlay compositing and the three overlay types; any change to the page-highlight colour; publishing the design system (Josh's call); changes to Versed's generator (it keeps its own design system).
