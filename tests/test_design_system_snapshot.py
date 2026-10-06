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


def test_chart_card_text_is_plain_ink_not_black_chips():
    table = _types_table()
    row = next(line for line in table.splitlines() if line.startswith("| `chart_card` |"))
    assert "NO black chips" in row
    text = _text()
    assert "never inside a black chip" in text
    assert "On a chart_card, is every piece of text plain ink text" in text
