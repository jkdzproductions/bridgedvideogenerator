import os

from shot_list.director_prompt import build_director_prompt
from shot_list.segments import Segment

SNAPSHOT = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "design_system", "bridged-design-system.md"))


def test_prompt_includes_every_segment_indexed_in_order():
    segments = [
        Segment("plain", "The city grew fast.", 0, 20),
        Segment("graphic", "Population tripled in a decade.", 20, 52),
        Segment("plain", "Then it slowed.", 52, 68),
    ]

    prompt = build_director_prompt(segments)

    assert SNAPSHOT in prompt
    assert os.path.isabs(SNAPSHOT) and os.path.exists(SNAPSHOT)
    assert '"count": 3' in prompt
    assert "[0] (plain) The city grew fast." in prompt
    assert "[1] (graphic) Population tripled in a decade." in prompt
    assert "[2] (plain) Then it slowed." in prompt


def test_prompt_instructs_exactly_one_entry_per_segment():
    segments = [Segment("plain", "Only one segment here.", 0, 23)]

    prompt = build_director_prompt(segments)

    assert "exactly one entry per segment" in prompt
    assert '"count": 1' in prompt


def test_prompt_lists_all_seven_types_and_note_rule():
    prompt = build_director_prompt([Segment("graphic", "x", 0, 5)])

    for name in ("chart_card", "definition", "distance", "org_chart",
                 "place_chip", "route_overlay", "territory_map"):
        assert name in prompt
    assert '"note"' in prompt
    assert '"archetype": "chart_card"' in prompt


def test_prompt_states_exact_graphic_entry_keys():
    prompt = build_director_prompt([Segment("graphic", "x", 0, 5)])
    assert "exactly the keys index, type, archetype, data" in prompt
