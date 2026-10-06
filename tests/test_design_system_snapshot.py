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


def _text():
    return open(DESIGN_SYSTEM_SNAPSHOT, encoding="utf-8").read()


def test_snapshot_is_the_bridged_file_and_exists():
    assert os.path.basename(DESIGN_SYSTEM_SNAPSHOT) == "bridged-design-system.md"
    assert os.path.isabs(DESIGN_SYSTEM_SNAPSHOT) and os.path.exists(DESIGN_SYSTEM_SNAPSHOT)


def test_snapshot_keeps_every_section_the_prompts_read():
    text = _text()
    for heading in REQUIRED_HEADINGS:
        assert heading in text, f"snapshot lost the section {heading!r}"


def test_snapshot_lists_exactly_the_archetypes_the_code_accepts():
    text = _text()
    for name in ARCHETYPES:
        assert f"`{name}`" in text


def test_snapshot_carries_no_versed_content():
    lowered = _text().lower()
    assert not re.search(r"(?<![a-z])versed", lowered) and "nagel" not in lowered
