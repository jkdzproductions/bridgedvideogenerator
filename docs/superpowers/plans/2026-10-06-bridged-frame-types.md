# Bridged Frame Types and Design-System Snapshot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the placeholder graphic types and placeholder snapshot with Josh's real Bridged design (7 graphic types), so Stage 1 picks Bridged types and Stage 3 renders them with "Bridged Design System (Final)".

**Architecture:** `ARCHETYPES` (the allowed type names) and the director prompt's type list change to the 7 Bridged types; the snapshot `design_system/bridged-design-system.md` becomes the real rules (the director, prompt-writer and reviewer subagents read it); the prompt-writer learns which Claude Design template to start from for each type. The data shape for each type is guidance in the snapshot, not code. A final live Stage 3 run in Josh's Chrome proves it.

**Tech Stack:** Python 3.9, pytest, claude-in-chrome (live spike only).

**Spec:** `docs/superpowers/specs/2026-10-06-bridged-frame-types-design.md`

## Global Constraints

- The 7 allowed types, exactly: `diamond_flow`, `fan_out`, `year_range`, `then_vs_now`, `chart_card`, `territory_map`, `network_map`.
- NOT allowed yet (director must not choose them): `footage_callout`, `pin_chip`, `split_compare`. Not graphic types at all: article highlight (existing `page_highlight` beats) and source exhibit (existing show-as-is image beats).
- The snapshot keeps these exact headings (prompts read them by name): `## The one rule`, `## The 7 frame types (choosing one from the script line)`, `## Content fundamentals`, `## Visual foundations`, `## Pre-ship checklist`.
- Multi-country rule stays exactly as in the pipeline: two or more neighbouring highlighted countries each get a distinct colour, never blue, with the shared border drawn as a clearly visible line.
- The page-highlight green stays `#30fe3e` (do not change `page_intake/capture.py`).
- `GRAPHICS_DESIGN_SYSTEM_NAME` is `Bridged Design System (Final)` (already in `.env`; never print or commit `.env`).
- No "Versed" anywhere in code, prompts, snapshot or CLAUDE.md (the guard tests use the regex that ignores "reversed"). "Nagel" may appear in the snapshot (it is Bridged's typeface) but the prompts and CLAUDE.md need not mention it.
- Commits end with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`. Work on a branch `build-frame-types`; merge to `main` at the end; no push until Josh says.
- Never modify `~/versed-video-generator/`.

## Review Focus

- **A stale old type name left anywhere** (`definition`, `distance`, `org_chart`, `place_chip`, `route_overlay`) in code, fixtures, tests or CLAUDE.md: the director would be told about types that no longer exist. Task 1 greps for them.
- **The snapshot listing a deferred type as allowed** (so the director picks `pin_chip` and the pipeline STOPs on "unknown archetype"). Task 2's test checks the allowed-types table has exactly the 7 and none of the 3 deferred names.
- **The snapshot losing a heading the prompts read.** Task 2's test pins all five.
- **The prompt-writer sending Claude Design to the wrong template** (or a Versed one). Task 3 maps each type to the exact template name and tests every type.
- **Stage 3 still marked "must not run" in the docs after it can run** (an operator would skip it), or marked ready when the live run has not passed. Task 4 edits the docs; Task 5's live result decides the final wording.

---

### Task 1: The 7 type names in code, the director prompt, the fixture and the tests

**Files:**
- Modify: `shot_list/models.py:4-12`, `shot_list/director_prompt.py` (the type-name list sentence), `tests/fixtures/director_prompt_no_links.txt:3`
- Modify (tests): `tests/test_models.py`, `tests/test_director_output.py`, `tests/test_director_prompt.py`, `tests/test_prompt_writer_prompt.py`, `tests/test_reviewer_prompt.py`, `tests/test_motion_graphics_shotlist_integration.py`

**Interfaces:**
- Consumes: the existing `ARCHETYPES` set, `build_director_prompt`, `parse_director_output`
- Produces: `ARCHETYPES == {"diamond_flow", "fan_out", "year_range", "then_vs_now", "chart_card", "territory_map", "network_map"}`; the director prompt lists exactly those names in that order

- [ ] **Step 1: Create the branch**

```bash
cd ~/bridged-video-generator && git checkout -b build-frame-types && git status --short | head -3
```

- [ ] **Step 2: Write the failing tests (update the existing ones to the new set)**

```bash
python3 - <<'E'
def sub(path, pairs):
    s = open(path, encoding="utf-8").read()
    for old, new in pairs:
        assert old in s, (path, old)
        s = s.replace(old, new)
    open(path, "w", encoding="utf-8").write(s)

NEW_SET = '''{
        "diamond_flow", "fan_out", "year_range", "then_vs_now",
        "chart_card", "territory_map", "network_map",
    }'''

sub("tests/test_models.py", [(
'''def test_archetypes_are_exactly_the_seven():
    from shot_list.models import ARCHETYPES
    assert ARCHETYPES == {
        "chart_card", "definition", "distance", "org_chart",
        "place_chip", "route_overlay", "territory_map",
    }''',
f'''def test_archetypes_are_exactly_the_seven_bridged_types():
    from shot_list.models import ARCHETYPES
    assert ARCHETYPES == {NEW_SET}


def test_overlay_types_are_not_allowed_yet():
    from shot_list.models import ARCHETYPES
    for name in ("footage_callout", "pin_chip", "split_compare"):
        assert name not in ARCHETYPES''')])

sub("tests/test_director_output.py", [(
'''@pytest.mark.parametrize("archetype", [
    "chart_card", "definition", "distance", "org_chart",
    "place_chip", "route_overlay", "territory_map",
])''',
'''@pytest.mark.parametrize("archetype", [
    "diamond_flow", "fan_out", "year_range", "then_vs_now",
    "chart_card", "territory_map", "network_map",
])'''),
('''def test_unknown_archetype_is_rejected():''',
'''@pytest.mark.parametrize("archetype", ["footage_callout", "pin_chip", "split_compare", "distance", "org_chart"])
def test_deferred_and_old_archetypes_are_rejected(archetype):
    with pytest.raises(DirectorOutputError, match="unknown archetype"):
        parse_director_output(_valid_raw({"archetype": archetype}), SEGMENTS)


def test_unknown_archetype_is_rejected():''')])

sub("tests/test_director_prompt.py", [(
'''    for name in ("chart_card", "definition", "distance", "org_chart",
                 "place_chip", "route_overlay", "territory_map"):
        assert name in prompt''',
'''    for name in ("diamond_flow", "fan_out", "year_range", "then_vs_now",
                 "chart_card", "territory_map", "network_map"):
        assert name in prompt
    for old in ("definition", "distance", "org_chart", "place_chip", "route_overlay",
                "footage_callout", "pin_chip", "split_compare"):
        assert old not in prompt''')])

sub("tests/test_prompt_writer_prompt.py", [
 ('archetype="org_chart", data={}', 'archetype="fan_out", data={}'),
 ('archetype="distance", data={}', 'archetype="year_range", data={}'),
 ('for archetype in ("place_chip", "chart_card", "territory_map"):', 'for archetype in ("network_map", "chart_card", "territory_map"):'),
 ('prompt = build_prompt_writer_prompt("place_chip", {}, 4.0)', 'prompt = build_prompt_writer_prompt("network_map", {}, 4.0)'),
])

sub("tests/test_reviewer_prompt.py", [(
'''    prompt = _prompt(archetype="distance", data={"time": "6 hours", "distance": "110 mi"},
                     screenshot_path="/tmp/beat_1_attempt_1.png")

    assert "distance" in prompt
    assert "6 hours" in prompt
    assert "110 mi" in prompt''',
'''    prompt = _prompt(archetype="then_vs_now", data={"then": "400 Ships", "now": "100 Ships"},
                     screenshot_path="/tmp/beat_1_attempt_1.png")

    assert "then_vs_now" in prompt
    assert "400 Ships" in prompt
    assert "100 Ships" in prompt''')])

sub("tests/test_motion_graphics_shotlist_integration.py", [
 ('GraphicSpec("distance", {"rows": []})', 'GraphicSpec("year_range", {"rows": []})')])
E
.venv/bin/python -m pytest tests/test_models.py tests/test_director_output.py tests/test_director_prompt.py -q 2>&1 | tail -6
```

Expected: FAIL (the code still has the old set).

- [ ] **Step 3: Change the code and the golden fixture**

```bash
python3 - <<'E'
def sub(path, pairs):
    s = open(path, encoding="utf-8").read()
    for old, new in pairs:
        assert old in s, (path, old)
        s = s.replace(old, new)
    open(path, "w", encoding="utf-8").write(s)

sub("shot_list/models.py", [(
'''ARCHETYPES = {
    "chart_card",
    "definition",
    "distance",
    "org_chart",
    "place_chip",
    "route_overlay",
    "territory_map",
}''',
'''ARCHETYPES = {
    "diamond_flow",
    "fan_out",
    "year_range",
    "then_vs_now",
    "chart_card",
    "territory_map",
    "network_map",
}''')])

sub("shot_list/director_prompt.py", [(
"chart_card, definition, distance, org_chart, place_chip, route_overlay, territory_map.",
"diamond_flow, fan_out, year_range, then_vs_now, chart_card, territory_map, network_map.")])

sub("tests/fixtures/director_prompt_no_links.txt", [(
"chart_card, definition, distance, org_chart, place_chip, route_overlay, territory_map.",
"diamond_flow, fan_out, year_range, then_vs_now, chart_card, territory_map, network_map.")])
E
git grep -n -E "definition|\bdistance\b|org_chart|place_chip|route_overlay" -- shot_list motion_graphics tests ':!tests/test_director_prompt.py' ':!tests/test_director_output.py' ':!tests/test_models.py'
```

Expected: the grep prints nothing except any unrelated English use of the word "definition" or "distance" in prose; read each hit: only a stale ARCHETYPE name is a defect. (`motion_graphics/prompt_writer_prompt.py` and `reviewer_prompt.py` currently contain none.)

- [ ] **Step 4: Run the full suite**

Run: `.venv/bin/python -m pytest tests -q` with `timeout: 600000` (about 2 minutes).
Expected: all pass (1 skipped is normal). `tests/test_design_system_snapshot.py` still passes because the placeholder snapshot still lists the old names in backticks only if they match `ARCHETYPES`: it will FAIL on `test_snapshot_lists_exactly_the_archetypes_the_code_accepts` until Task 2. That one failure is expected here; any other failure is a bug.

- [ ] **Step 5: Commit**

```bash
git add shot_list tests
git commit -m "Allowed graphic types: the 7 Bridged types

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: The real Bridged snapshot and its tests

**Files:**
- Modify (replace content): `design_system/bridged-design-system.md`
- Modify: `tests/test_design_system_snapshot.py`

**Interfaces:**
- Consumes: Task 1's `ARCHETYPES`; `DESIGN_SYSTEM_SNAPSHOT` from `shot_list.director_prompt`
- Produces: a snapshot with the five required headings and an allowed-types table with exactly 7 rows

- [ ] **Step 1: Write the failing tests**

Replace `tests/test_design_system_snapshot.py` with:

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

DEFERRED = ("footage_callout", "pin_chip", "split_compare")


def _text():
    with open(DESIGN_SYSTEM_SNAPSHOT, encoding="utf-8") as f:
        return f.read()


def _types_table():
    """The text between the frame-types heading and the next heading."""
    text = _text()
    start = text.index("## The 7 frame types")
    end = text.index("\n## ", start + 5)
    return text[start:end]


def test_snapshot_is_the_bridged_file_and_exists():
    assert os.path.basename(DESIGN_SYSTEM_SNAPSHOT) == "bridged-design-system.md"
    assert os.path.isabs(DESIGN_SYSTEM_SNAPSHOT) and os.path.exists(DESIGN_SYSTEM_SNAPSHOT)


def test_snapshot_keeps_every_section_the_prompts_read():
    text = _text()
    for heading in REQUIRED_HEADINGS:
        assert heading in text, f"snapshot lost the section {heading!r}"


def test_the_types_table_has_exactly_the_archetypes_the_code_accepts():
    rows = re.findall(r"^\| `([a-z_]+)` \|", _types_table(), flags=re.M)
    assert set(rows) == ARCHETYPES
    assert len(rows) == 7


def test_deferred_types_are_not_in_the_allowed_table():
    table = _types_table()
    for name in DEFERRED:
        assert f"`{name}` |" not in table


def test_snapshot_says_the_deferred_types_are_coming():
    text = _text()
    for name in DEFERRED:
        assert name in text  # mentioned in the pipeline notes as not yet allowed


def test_snapshot_carries_no_versed_content():
    assert not re.search(r"(?<![a-z])versed", _text().lower())


def test_snapshot_states_the_multi_country_colour_rule():
    text = _text().lower()
    assert "distinct" in text and "never blue" in text and "border" in text
```

Run: `.venv/bin/python -m pytest tests/test_design_system_snapshot.py -q`
Expected: FAIL (the placeholder snapshot has the old table).

- [ ] **Step 2: Write the real snapshot**

Replace the whole of `design_system/bridged-design-system.md` with exactly this:

````markdown
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
| `chart_card` | a quantity over time or a comparison of series | `title`, `subtitle` (range or unit), `series` (label, points), `highlight_period`, `source` | Peach paper. Ink title chip over an area chart (highlighted period) or a red and blue line chart. |
| `territory_map` | where something is; the extent or control of land | `territories` (names), `style` (`fill`, `tint` or `outline`), `pins` (specific sites), optional `date` | Dark satellite. Country in solid cyan, translucent teal tint or glowing outline, with a white edge, white chips and a pink pin. |
| `network_map` | routes or a network between places | `cities` (names), `route` (order), `vehicle` (ship, plane, train or truck glyph) | Dark satellite. Glowing blue city dots with glowing white names, dashed glowing route, vehicle glyph at the head. |

## Content fundamentals

Frames carry almost no text. A chip, a figure, a place. The narration leads.

- Tone: factual, sober. No exclamation, no hype.
- Chips: sentence or title case, Nagel Regular, square corners ("Naval Shipbuilding", "Jones Act
  Fleet Collapse", "Bank").
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
````

- [ ] **Step 3: Run the snapshot tests and the prompt tests**

Run: `.venv/bin/python -m pytest tests/test_design_system_snapshot.py tests/test_prompts_are_bridged.py tests/test_director_prompt.py tests/test_reviewer_prompt.py tests/test_prompt_writer_prompt.py -q`
Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add design_system tests/test_design_system_snapshot.py
git commit -m "Snapshot: the real Bridged design system rules and the 7 allowed frame types

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: The prompt-writer starts from the right Claude Design template

**Files:**
- Modify: `motion_graphics/prompt_writer_prompt.py`
- Test: `tests/test_prompt_writer_prompt.py`

**Interfaces:**
- Consumes: `build_prompt_writer_prompt(archetype: str, data: dict, target_duration: float) -> str`
- Produces: `TEMPLATE_NAMES: dict[str, str]` mapping each archetype to the design system's template display name, and a sentence in the prompt telling the Claude Design AI to start from that template

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_prompt_writer_prompt.py`:

```python
import pytest

from motion_graphics.prompt_writer_prompt import TEMPLATE_NAMES
from shot_list.models import ARCHETYPES


def test_every_archetype_has_a_template_name():
    assert set(TEMPLATE_NAMES) == ARCHETYPES


@pytest.mark.parametrize("archetype,template", [
    ("diamond_flow", "Diamond flow"), ("fan_out", "Fan-out"), ("year_range", "Year range"),
    ("then_vs_now", "Then vs now"), ("chart_card", "Chart card"),
    ("territory_map", "Territory map"), ("network_map", "Network map"),
])
def test_prompt_tells_claude_design_to_start_from_the_matching_template(archetype, template):
    prompt = build_prompt_writer_prompt(archetype, {"x": 1}, 4.0)
    assert f'start from the design system\'s "{template}" template' in prompt
```

Run: `.venv/bin/python -m pytest tests/test_prompt_writer_prompt.py -q`
Expected: FAIL (`TEMPLATE_NAMES` does not exist).

- [ ] **Step 2: Implement**

```bash
python3 - <<'E'
def sub(path, pairs):
    s = open(path, encoding="utf-8").read()
    for old, new in pairs:
        assert old in s, (path, old)
        s = s.replace(old, new, 1)
    open(path, "w", encoding="utf-8").write(s)

sub("motion_graphics/prompt_writer_prompt.py", [
('''def build_prompt_writer_prompt(archetype: str, data: dict, target_duration: float) -> str:
    data_json = json.dumps(data, indent=2)
''',
'''# The display name of each type's starting template in the Bridged design system.
TEMPLATE_NAMES = {
    "diamond_flow": "Diamond flow",
    "fan_out": "Fan-out",
    "year_range": "Year range",
    "then_vs_now": "Then vs now",
    "chart_card": "Chart card",
    "territory_map": "Territory map",
    "network_map": "Network map",
}


def build_prompt_writer_prompt(archetype: str, data: dict, target_duration: float) -> str:
    data_json = json.dumps(data, indent=2)
    template_name = TEMPLATE_NAMES[archetype]
'''),
("so tell the AI to use it rather than re-describing every token.",
 "so tell the AI to use it rather than re-describing every token, and to start from the design system's \\\"{template_name}\\\" template for this frame type (the instruction must contain exactly the words: start from the design system's \"{template_name}\" template)."),
])
E
sed -n 24,34p motion_graphics/prompt_writer_prompt.py; .venv/bin/python -m pytest tests/test_prompt_writer_prompt.py tests/test_prompts_are_bridged.py -q 2>&1 | tail -4
```

Expected: the printed lines show the new sentence inside the f-string; tests pass. If the quote escaping makes the f-string a syntax error, open `motion_graphics/prompt_writer_prompt.py` and write that sentence so the final prompt text contains exactly `start from the design system's "Diamond flow" template` (with the real template name) when built, then re-run.

- [ ] **Step 3: Run the prompt tests once more and the full suite**

Run: `.venv/bin/python -m pytest tests -q` with `timeout: 600000`.
Expected: all pass (1 skipped).

- [ ] **Step 4: Commit**

```bash
git add motion_graphics tests/test_prompt_writer_prompt.py
git commit -m "Prompt-writer: start from the Bridged design system's template for each type

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Docs: CLAUDE.md and HANDOFF.md

**Files:**
- Modify: `CLAUDE.md` (the Stage 3 design-system paragraph)
- Replace: `HANDOFF.md`
- Test: `tests/test_docs_are_bridged.py` (existing; must still pass)

**Interfaces:**
- Consumes: Tasks 1-3
- Produces: docs that say Stage 3 is runnable with the 7 types, name the 3 deferred overlay types, and keep the live-run result as the thing Josh must confirm

- [ ] **Step 1: Edit CLAUDE.md**

```bash
python3 - <<'E'
p = "CLAUDE.md"
s = open(p, encoding="utf-8").read()
pairs = [
('(not set yet: the Bridged\ndesign system has to be created first)',
 '(currently\n`GRAPHICS_DESIGN_SYSTEM_NAME="Bridged Design System (Final)"`)'),
("This is the Bridged design system project in\nClaude Design, which Josh builds from his own Bridged frames and font. Until it exists the local\nsnapshot is a placeholder and Stage 3 must NOT be run. The placeholder lists 7 archetypes (`chart_card`, `definition`,\n`distance`, `org_chart`, `place_chip`, `route_overlay`, `territory_map`). The",
 "This is the Bridged design system project in\nClaude Design, built from Josh's 18 Bridged frames and the Nagel font. It has 11 frame types; this\npipeline renders 7 of them as graphics (`diamond_flow`, `fan_out`, `year_range`, `then_vs_now`,\n`chart_card`, `territory_map`, `network_map`). `footage_callout`, `pin_chip` and `split_compare` are\ndrawn on top of footage and need overlay compositing that Stage 4 does not have yet, so the\ndirector cannot choose them. Article highlight and source exhibit are not graphic types: they are\nthe page-highlight and show-as-is image features. The"),
("header pipeline notes (the 7 archetypes)", "header pipeline notes (the 7 allowed types, the 3 coming ones, the multi-country colour rule)"),
]
for old, new in pairs:
    assert old in s, old
    s = s.replace(old, new, 1)
open(p, "w", encoding="utf-8").write(s)
E
git grep -n -iE "(^|[^a-z])versed|placeholder lists|must NOT be run" -- CLAUDE.md
```

Expected: the grep prints only hits that are harmless prose (the word "placeholder" in "talking-head placeholder"); no "Versed", no "placeholder lists", no "must NOT be run". If `assert old in s` fails, the wrap differs: open CLAUDE.md around the "Stage 3 (Motion Graphics)" opening paragraph and make the same three edits by hand.

- [ ] **Step 2: Replace HANDOFF.md**

Write `HANDOFF.md` with exactly:

```markdown
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
```

- [ ] **Step 3: Run the doc tests and the guard tests**

Run: `.venv/bin/python -m pytest tests/test_docs_are_bridged.py tests/test_no_versed_left.py tests/test_scaffold.py -q`
Expected: all pass. (`test_docs_are_bridged` needs "design system", `GRAPHICS_DESIGN_SYSTEM_NAME` and `ARCHETYPES` in HANDOFF.md, the "# Bridged Video Generator" title, and the word "placeholder" somewhere in CLAUDE.md: the talking-head placeholder text provides it.)

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md HANDOFF.md
git commit -m "Docs: Stage 3 runs with the Bridged design system; 7 types, 3 coming

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Live Stage 3 spike (run by the controller with Josh, not a subagent)

This task needs Josh's logged-in Chrome with the `claude-in-chrome` extension, so it runs in the main session, following CLAUDE.md "Stage 3 (Motion Graphics)" exactly. A subagent cannot do it.

**Files:** none tracked. Creates local, gitignored run files (`graphic_beats.json`, `graphics_output/`, `canvas_*.json`...) in a scratch copy of the project or after cleaning them up.

- [ ] **Step 1: Build a 7-beat test shot list.** Write `shot_list.json` by hand-assembling (via `shot_list.models`) a ShotList with 7 graphic beats, one per type, each 4 seconds, with realistic data taken from Josh's frames: diamond_flow (Onassis: ships, bank, oil well, `$` badges), fan_out (Naval Shipbuilding with 4 inputs), year_range (1955 to 1985, 20 per year, US flag), then_vs_now (400 ships 1950, 100 today), chart_card (Decline of US shipbuilding, naval vs commercial, 1960-2020), territory_map (Japan, fill, "1970s-1980s", pin), network_map (Memphis, Birmingham, Atlanta, Charlotte, Jackson, New Orleans, plane).

- [ ] **Step 2: Check the design system is selectable.** Follow Stage 3 Step 2b.2 for the first beat. If "Bridged Design System (Final)" is not in the picker, tell Josh to publish it (Published checkbox in Claude Design) and retry once; record whether publishing was required.

- [ ] **Step 3: Render each beat** through the CLAUDE.md Stage 3 procedure (prompt-writer subagent, canvas, reviewer subagent, correction loop max 3, export, `ffprobe` check).

- [ ] **Step 4: Josh reviews each exported clip** (open `graphics_output/beat_<n>.mp4`) and says approve or what is wrong. Record per type: approved first time, approved after N corrections, or rejected and why.

- [ ] **Step 5: Record the result.** If publishing was required, add that to HANDOFF.md and CLAUDE.md's "Before the first run" list. If a type could not be rendered acceptably, say which and why in HANDOFF.md under "Not built yet". Commit those doc edits.

```bash
git add CLAUDE.md HANDOFF.md
git commit -m "Docs: live Stage 3 result for the 7 Bridged types

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 6: Final checks and merge.** Run the full suite once more (`timeout: 600000`), confirm `git status` is clean, then `git checkout main && git merge --ff-only build-frame-types`. Do not push; ask Josh.
