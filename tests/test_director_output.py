import json
import pytest
from shot_list.director_output import DirectorOutputError, parse_director_output
from shot_list.segments import Segment


SEGMENTS = [
    Segment("plain", "The city grew fast.", 0, 20),
    Segment("graphic", "Population tripled in a decade.", 20, 52),
]


def test_parses_valid_output_in_order():
    raw = json.dumps({
        "count": 2,
        "entries": [
            {"index": 0, "type": "footage", "query": "city growth timelapse", "subject": "urban growth"},
            {"index": 1, "type": "graphic", "archetype": "chart_card",
             "data": {"value": "2x"}},
        ],
    })

    result = parse_director_output(raw, SEGMENTS)

    assert result[0] == {"type": "footage", "query": "city growth timelapse", "subject": "urban growth"}
    assert result[1] == {"type": "graphic", "archetype": "chart_card",
                          "data": {"value": "2x"}}


def test_malformed_json_raises():
    with pytest.raises(DirectorOutputError, match="not valid JSON"):
        parse_director_output("not json at all", SEGMENTS)


def test_wrong_entry_count_raises():
    raw = json.dumps({
        "count": 1,
        "entries": [{"index": 0, "type": "footage", "query": "x", "subject": "y"}],
    })

    with pytest.raises(DirectorOutputError, match="expected 2 entries, got 1"):
        parse_director_output(raw, SEGMENTS)


def test_type_mismatch_with_segment_kind_raises():
    # segment 1 is "graphic" but the entry says "footage"
    raw = json.dumps({
        "count": 2,
        "entries": [
            {"index": 0, "type": "footage", "query": "x", "subject": "y"},
            {"index": 1, "type": "footage", "query": "x", "subject": "y"},
        ],
    })

    with pytest.raises(DirectorOutputError, match="segment 1 is 'graphic' but entry type is 'footage'"):
        parse_director_output(raw, SEGMENTS)


def test_unknown_archetype_raises():
    raw = json.dumps({
        "count": 2,
        "entries": [
            {"index": 0, "type": "footage", "query": "x", "subject": "y"},
            {"index": 1, "type": "graphic", "archetype": "pie_chart_3d", "data": {}},
        ],
    })

    with pytest.raises(DirectorOutputError, match="unknown archetype"):
        parse_director_output(raw, SEGMENTS)


def test_duplicate_index_leaves_another_segment_missing_raises():
    # right entry COUNT (2), but both entries claim index 0 — segment 1 has none
    raw = json.dumps({
        "count": 2,
        "entries": [
            {"index": 0, "type": "footage", "query": "x", "subject": "y"},
            {"index": 0, "type": "footage", "query": "x", "subject": "y"},
        ],
    })

    with pytest.raises(DirectorOutputError, match="missing entry for segment 1"):
        parse_director_output(raw, SEGMENTS)


def _valid_raw(graphic_overrides=None):
    graphic = {"index": 1, "type": "graphic", "archetype": "chart_card",
               "data": {"value": "2x"}}
    graphic.update(graphic_overrides or {})
    return json.dumps({"count": 2, "entries": [
        {"index": 0, "type": "footage", "query": "x", "subject": "y"}, graphic,
    ]})


@pytest.mark.parametrize("overrides", [{"data": {}}, {"data": None}])
def test_graphic_with_empty_data_raises(overrides):
    with pytest.raises(DirectorOutputError, match="segment 1 graphic entry missing data"):
        parse_director_output(_valid_raw(overrides), SEGMENTS)


def test_graphic_with_no_data_field_raises():
    raw = json.loads(_valid_raw())
    del raw["entries"][1]["data"]

    with pytest.raises(DirectorOutputError, match="segment 1 graphic entry missing data"):
        parse_director_output(json.dumps(raw), SEGMENTS)


@pytest.mark.parametrize("fence", ["```json", "```"])
def test_json_wrapped_in_a_code_fence_is_accepted(fence):
    raw = f"{fence}\n{_valid_raw()}\n```\n"

    result = parse_director_output(raw, SEGMENTS)

    assert result[1]["data"] == {"value": "2x"}


@pytest.mark.parametrize("archetype", [
    "diamond_flow", "fan_out", "year_range", "then_vs_now",
    "chart_card", "territory_map", "network_map",
])
def test_each_of_the_seven_archetypes_is_accepted(archetype):
    result = parse_director_output(_valid_raw({"archetype": archetype}), SEGMENTS)
    assert result[1]["archetype"] == archetype


@pytest.mark.parametrize("archetype", ["footage_callout", "pin_chip", "split_compare", "distance", "org_chart"])
def test_deferred_and_old_archetypes_are_rejected(archetype):
    with pytest.raises(DirectorOutputError, match="unknown archetype"):
        parse_director_output(_valid_raw({"archetype": archetype}), SEGMENTS)


def test_unknown_archetype_is_rejected():
    with pytest.raises(DirectorOutputError, match="unknown archetype"):
        parse_director_output(_valid_raw({"archetype": "bar_chart"}), SEGMENTS)


def test_extra_entry_level_key_is_tolerated_and_dropped():
    result = parse_director_output(_valid_raw({"note": "fits poorly", "reasoning": "x"}), SEGMENTS)
    assert result[1] == {"type": "graphic", "archetype": "chart_card", "data": {"value": "2x"}}
