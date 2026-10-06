import json
import os

import pytest

from shot_list.build import prepare_director_input
from shot_list.director_output import (
    DirectorOutputError,
    check_linked_graphic_data,
    parse_director_output,
)
from shot_list.director_prompt import (
    DESIGN_SYSTEM_SNAPSHOT,
    PROVIDED_DATA_HEADER,
    build_director_prompt,
)
from shot_list.markup import parse_markup
from shot_list.segments import Segment, map_readings_to_segments

SCRIPT = ("Latin America is uneven. *Population tripled in a decade.* Incomes differ. "
          "*GDP per capita ranges widely* across the region.")
READING = {
    "title": "GDP Per Capita", "subtitle": "Across Latin and South America",
    "graph_kind": "choropleth map", "unit": "GDP per capita, US dollars",
    "source_line": "Source: IMF October 2024 World Economic Outlook", "notes": None,
    "values": [
        {"label": "Guyana", "display": "$29K", "value": 29000, "readable": True},
        {"label": "BLZ", "display": "$8?", "value": None, "readable": False},
    ],
}
# graphic span 1 is the second * pair: "GDP per capita ranges widely"
READINGS = {1: {"italic_text": "GDP per capita ranges widely", "url": "https://i.redd.it/x.jpeg",
                "image_path": "/abs/graph_inputs/graph_1.jpg", "width": 1080, "height": 1350,
                "reading": READING}}


def _prepare(readings):
    parsed = parse_markup(SCRIPT)
    return prepare_director_input(parsed.plain_text, parsed.graphic_spans, graph_readings=readings)


def test_provided_data_block_only_for_the_linked_segment():
    segments, prompt = _prepare(READINGS)

    assert [s.kind for s in segments] == ["plain", "graphic", "plain", "graphic", "plain"]
    assert prompt.count(PROVIDED_DATA_HEADER) == 1
    assert f"[3] {PROVIDED_DATA_HEADER}:" in prompt
    assert "[1] PROVIDED DATA" not in prompt
    assert "- Guyana: $29K (value 29000, readable)" in prompt
    assert "- BLZ: printed as '$8?' — UNREADABLE, leave it out of `data`" in prompt
    assert "source line: Source: IMF October 2024 World Economic Outlook" in prompt
    assert "graph kind: choropleth map" in prompt


def test_exact_provided_data_wording():
    assert PROVIDED_DATA_HEADER == (
        "PROVIDED DATA (read from a linked graph — use ONLY these values in `data`, do not add "
        "or invent others; keep the graph's stated source in `data.source`)")


@pytest.mark.parametrize("readings", [None, {}])
def test_no_readings_gives_todays_prompt(readings):
    segments, prompt = _prepare(readings)

    assert "PROVIDED DATA" not in prompt
    assert prompt == build_director_prompt(segments)
    assert "[4] (plain) across the region.\n\nFor each \"graphic\" segment" in prompt


@pytest.mark.parametrize("readings", [None, {}])
def test_no_readings_prompt_is_byte_identical_to_the_pre_change_prompt(readings):
    golden_path = os.path.join(os.path.dirname(__file__), "fixtures", "director_prompt_no_links.txt")
    with open(golden_path) as f:
        golden = f.read()

    _, prompt = _prepare(readings)

    assert prompt == golden.replace("{DESIGN_SYSTEM}", DESIGN_SYSTEM_SNAPSHOT)


def test_readings_for_a_missing_graphic_span_raise():
    stale = {5: READINGS[1]}
    with pytest.raises(ValueError, match="has 2 graphic spans.*another script"):
        _prepare(stale)


def test_readings_whose_text_does_not_match_the_span_raise():
    stale = {0: READINGS[1]}  # graphic span 0 is "Population tripled in a decade."
    with pytest.raises(ValueError, match="'Population tripled in a decade.'.*another script"):
        _prepare(stale)


def _director_response(segments, linked_data):
    entries = []
    for i, s in enumerate(segments):
        if s.kind == "plain":
            entries.append({"index": i, "type": "footage", "query": "q", "subject": "s"})
        else:
            data = linked_data if i == 3 else {"value": "3x"}
            entries.append({"index": i, "type": "graphic", "archetype": "territory_map", "data": data})
    return json.dumps({"count": len(segments), "entries": entries})


def test_check_passes_when_the_linked_graphic_has_values():
    segments, _ = _prepare(READINGS)
    data = {"values": [{"label": "Guyana", "value": 29000}], "source": "IMF"}
    specs = parse_director_output(_director_response(segments, data), segments)

    check_linked_graphic_data(segments, specs, READINGS)  # does not raise


@pytest.mark.parametrize("data", [{"source": "IMF"}, {"note": "map fits poorly"},
                                  {"note": "x", "source": "IMF"}])
def test_check_rejects_a_linked_graphic_without_values(data):
    segments, _ = _prepare(READINGS)
    specs = parse_director_output(_director_response(segments, data), segments)

    with pytest.raises(DirectorOutputError, match="segment 3 .'GDP per capita ranges widely'. links to a graph"):
        check_linked_graphic_data(segments, specs, READINGS)


def test_map_readings_to_segments_tolerates_line_breaks_in_the_italic_text():
    segments = [Segment("graphic", "GDP per\ncapita", 0, 14)]
    entry = dict(READINGS[1], italic_text="GDP per capita")

    assert map_readings_to_segments(segments, {0: entry}) == {0: entry}
