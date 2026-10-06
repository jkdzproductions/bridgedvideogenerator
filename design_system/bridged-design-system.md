# Bridged Design System — rules snapshot

**Snapshot of the claude.ai/design project "Bridged Design System (Final)", read 2026-10-06.**
This file is what the Stage 1 director, Stage 3 prompt-writer and Stage 3 reviewer read as their
design rules. The design system itself lives in claude.ai/design (attached to every Stage 3 canvas
by name via `GRAPHICS_DESIGN_SYSTEM_NAME`); this file is only a local copy so unattended subagents
can read the rules. **Refresh it (re-read the design system's readme, `guidelines/bridged-style.md`
and `guidelines/frame-archetypes.md`) whenever that design system changes.** Where the readme and
`bridged-style.md` disagree, `bridged-style.md` wins.

Pipeline notes (not part of the design system's readme):
- The 7 frame types below are the **only** graphic archetypes the director may choose:
  `diamond_flow`, `fan_out`, `year_range`, `then_vs_now`, `chart_card`, `territory_map`,
  `network_map`.
- `footage_callout`, `pin_chip` and `split_compare` exist in the design system but are drawn on top
  of footage, which this pipeline cannot composite yet: they are **coming, not allowed**.
- Article highlight and source exhibit are not graphic types: a real article quote is a
  `page_highlight` beat and a report's own chart or map shown as it is is a show-as-is image beat.
- **Multiple highlighted countries/territories (Josh's rule, overrides the single-territory map
  style for that case): never give them all the same colour.** Each highlighted country gets its
  own distinct fill and edge. Never use blue for a highlight when two or more neighbouring
  countries are highlighted. The shared border between two highlighted countries must be drawn as
  a clearly visible line so they never read as one country. A single highlighted territory uses
  the territory style below.

## The one rule

**Structure is ink; colour has a job.** Every coloured thing on a frame maps to one role a viewer
could name: red is industry, blue is labour, cyan is institutions and territory, green is money,
pink is the key term or a pin, and yellow is a figure over footage. Everything structural (chips,
diamonds, connectors) is black ink.

## The 7 frame types (choosing one from the script line)

| Type (`archetype` value) | Use when the fact is... | Data to extract from the script line | Look |
|---|---|---|---|
| `diamond_flow` | who pays or does what to whom; what moves where | `actors` (name, glyph or photo, role colour), `flows` (from, to, label), `money` (amounts as green hex badges) | Peach paper. Actors as black diamonds joined by stepped ink connectors; money as green hex badges. |
| `fan_out` | what one thing depends on | `subject` (name, glyph), `inputs` (name and glyph or photo each), `heavy` (true if one source dominates: double trunk) | Peach paper. Title chip, big filled glyph of the subject, rounded bracket tree to the inputs. |
| `year_range` | a period and a rate | `start`, `end`, `rate` (value and unit, e.g. "20 / Per year"), optional `flag` (country code) | Peach paper. Two big year chips joined by an ink dash, stepped connector to a diamond with a flag, rate chip beneath. |
| `then_vs_now` | how much something shrank or grew | `then` (count, label), `now` (count, label), `unit_glyph`, `title` | Peach paper. Two isotype counts (navy then, maroon now) with stacked chips and an ink bar between; title chip on top. |
| `chart_card` | a quantity over time or a comparison of series | `title`, `subtitle` (range or unit), `series` (label, points), `highlight_period`, `source` | Peach paper. All text (title, subtitle, band label, series labels, axis labels, source) is plain ink text on the paper, NO black chips. An area chart (highlighted period) or a red and blue line chart. |
| `territory_map` | where something is; the extent or control of land | `territories` (names), `style` (`fill`, `tint` or `outline`), `pins` (specific sites), optional `date` | Dark NASA Blue Marble satellite. Country in solid cyan, translucent teal tint or glowing outline, with a white edge, white chips and a pink pin. |
| `network_map` | routes or a network between places | `cities` (names), `route` (order), `vehicle` (ship, plane, train or truck glyph) | Dark NASA Blue Marble satellite. Glowing blue city dots with glowing white names, dashed glowing route, vehicle glyph at the head. |

## Content fundamentals

Frames carry almost no text. A chip, a figure, a place. The narration leads.

- Tone: factual, sober. No exclamation, no hype.
- Chips: sentence or title case, Nagel Regular, square corners ("Naval Shipbuilding", "Jones Act
  Fleet Collapse", "Bank").
- Charts (chart_card): every piece of text on a chart (title, subtitle, band label, series labels, axis labels, source) is plain ink text on the paper, never inside a black chip. Black chips are for diagrams and for labels on footage and maps.
- Value and qualifier stack as two chips ("400 Ships" / "1950", "20/Per year").
- Year ranges: two large chips joined by an ink dash ("1955 — 1985"). Decades: "1970s-1980s".
- Dates on footage: spelled out in a white chip with a pink pin ("April 30th, 2025").
- Figures: comma-formatted (1,300) with a short label beneath ("Naval Vessels", "Years").
- Person: impersonal on screen. Emoji: never.

## Visual foundations

- **Colour.** Peach `#FDE6C8` ground, ink `#1A1C1B`, white. Glyph colours: red `#E3121B`, blue
  `#098DF6`, navy `#2C4B9D`, cyan `#02ABDD`, neon green `#2BFF3B`. Accents: pink `#F0386B` (pins,
  the accent chip), yellow `#FFE24A` (glowing figures), orange `#F28C28` (split-label underline),
  maroon `#8E1B2A` ("after" counts). Map territory cyan `#1E9BCB` or teal tint `#3F9A9E`; city dots
  `#2F4BFF`.
- **Grounds.** Peach paper with a fine diagonal crosshatch for every explainer diagram (flows,
  trees, counts, year ranges, charts). Darkened satellite for place and networks.
- **Type.** Nagel Regular only; hierarchy by size and chip treatment. Year chips 96, title chips
  56-72, chips 44, map tags 34, cities 30.
- **Shape.** Black diamonds (45 degree squares) holding a filled colour glyph or a photo;
  overlapping repeats for plurals; black hexagons with a green `$` for money; pink pentagon pins;
  square-cornered chips. Glyphs are always filled silhouettes, never outline icons.
- **Lines.** 6px ink step connectors with two rounded elbows; bracket trees fanning one source to
  several inputs (double trunk for a heavy source). No arrowheads. On maps, dashed white routes
  with a soft glow.
- **Maps.** Darkened satellite. Territory as solid cyan with a white edge (a country), translucent
  teal with thin white internal borders (a large country with states), or a glowing white outline
  with faint cyan inside (a city footprint). White place dots and labels, or glowing blue city
  dots for networks. The pink pentagon pin marks the specific site. No graticule, no legend.
  The satellite ground is NASA Blue Marble, never the EOX Sentinel-2 mosaic (its stitched
  satellite passes leave visible diagonal or vertical seams). A highlighted territory is drawn
  with the detailed coastline (for example Natural Earth 1:10m) and a crisp thin white edge,
  never the coarse blocky template outline. NASA imagery is public domain, so no credit line goes
  on screen.
- **Texture.** Fine diagonal crosshatch and light grain on paper. No vignette on diagrams.
- **Shadows.** None on shapes. Glow only: yellow on figures, white on map labels and routes.
- **Layout.** 1920x1080. Title chip centred at the top; diagrams read left to right along
  connectors; one subject per frame; generous peach space.
- **Imagery.** Real photos (Wikimedia Commons) inside diamonds; photos are never drawn or
  generated. A historical subject gets period-appropriate imagery.
- **Don't.** No arrowheads, no rounded chips, no outline icons, no drop shadows.

## Pre-ship checklist (derived from the rules above; use when judging a rendered frame)

<!-- Pipeline-added section (not in the design system's readme): the reviewer prompt depends on it; it must survive snapshot refreshes. -->

- Is it exactly one of the 7 frame types, matching the target archetype and data (no wrong,
  missing or fabricated values)?
- On a chart_card, is every piece of text plain ink text with no black chip behind it?
- Is structure ink (black chips, diamonds, connectors), with colour only where it has a nameable
  role (red industry, blue labour, cyan institutions/territory, green money, pink key term or
  pin, yellow figure over footage)?
- Are all glyphs filled silhouettes (no outline icons), and are there no arrowheads, no rounded
  chips and no drop shadows?
- If two or more neighbouring countries are highlighted, does each have its own distinct colour
  (never blue) with the border between them clearly drawn so they do not read as one country?
- Is every piece of text in Nagel Regular, with numbers comma-formatted and labels short?
- Is there one clear subject and one clear focal point, with generous empty space?
- Is the ground right for the type (peach paper for diagrams, darkened satellite for maps)?
- Does it read at phone size (480p)?
- Is a map's ground smooth NASA Blue Marble with no visible seams or bands, and is any highlighted
  territory drawn with the detailed coastline and a crisp white edge (no blocky outline, no credit
  line on screen)?
