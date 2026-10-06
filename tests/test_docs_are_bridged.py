import os
import re

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _read(name):
    return open(os.path.join(ROOT, name), encoding="utf-8").read()


def test_claude_md_is_bridged():
    text = _read("CLAUDE.md")
    assert text.startswith("# Bridged Video Generator")
    assert not re.search(r"(?<![a-z])versed", text.lower()) and "nagel" not in text.lower()
    assert "design_system/bridged-design-system.md" in text
    assert "placeholder" in text.lower()


def test_handoff_exists_and_says_what_is_next():
    text = _read("HANDOFF.md")
    assert text.startswith("# Bridged Video Generator")
    for needle in ("design system", "GRAPHICS_DESIGN_SYSTEM_NAME", "ARCHETYPES"):
        assert needle in text
