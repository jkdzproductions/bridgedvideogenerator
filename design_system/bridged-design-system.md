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
