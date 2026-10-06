import json

import pytest

from graph_intake.reading_output import GraphReadingError, parse_reading_output


def _reading(**overrides):
    reading = {
        "title": "GDP Per Capita",
        "subtitle": "Across Latin and South America",
        "graph_kind": "choropleth map",
        "unit": "GDP per capita, US dollars",
        "source_line": "Source: IMF October 2024 World Economic Outlook",
        "values": [
            {"label": "Guyana", "display": "$29K", "value": 29000, "readable": True},
            {"label": "BLZ", "display": "$8K", "value": None, "readable": False},
        ],
        "notes": None,
    }
    reading.update(overrides)
    return reading


def test_parses_a_valid_reading():
    assert parse_reading_output(json.dumps(_reading()), "GDP per capita") == _reading()


def test_strips_a_json_code_fence():
    raw = "```json\n" + json.dumps(_reading()) + "\n```"
    assert parse_reading_output(raw, "GDP per capita")["title"] == "GDP Per Capita"


def test_not_json_raises_naming_the_italic_phrase():
    with pytest.raises(GraphReadingError, match="'GDP per capita'.*not valid JSON"):
        parse_reading_output("I could not open the image.", "GDP per capita")


def test_zero_readable_values_raises():
    values = [{"label": "Guyana", "display": "$2?K", "value": None, "readable": False}]
    with pytest.raises(GraphReadingError, match="'GDP per capita'.*zero readable values"):
        parse_reading_output(json.dumps(_reading(values=values)), "GDP per capita")


def test_empty_values_list_raises():
    with pytest.raises(GraphReadingError, match="zero readable values"):
        parse_reading_output(json.dumps(_reading(values=[])), "GDP")


def test_missing_key_raises():
    reading = _reading()
    del reading["unit"]
    with pytest.raises(GraphReadingError, match=r"missing \['unit'\]"):
        parse_reading_output(json.dumps(reading), "GDP")


def test_extra_key_raises():
    with pytest.raises(GraphReadingError, match=r"unexpected \['colour'\]"):
        parse_reading_output(json.dumps(_reading(colour="green")), "GDP")


@pytest.mark.parametrize("bad_value, message", [
    ({"label": "Guyana", "display": "$29K", "value": "29000", "readable": True}, "must be a number or null"),
    ({"label": "Guyana", "display": "$29K", "value": True, "readable": True}, "must be a number or null"),
    ({"label": "Guyana", "display": "$29K", "value": 29000, "readable": "yes"}, "readable must be true/false"),
    ({"label": "", "display": "$29K", "value": 29000, "readable": True}, "empty label"),
    ({"label": "Guyana", "display": "$29K", "value": 29000}, "exactly the keys"),
    ({"label": "Guyana", "display": "$29K", "value": None, "readable": True}, "marked readable but has no number"),
    ("Guyana $29K", "exactly the keys"),
])
def test_malformed_value_raises(bad_value, message):
    values = [{"label": "Haiti", "display": "$2K", "value": 2000, "readable": True}, bad_value]
    with pytest.raises(GraphReadingError, match=message):
        parse_reading_output(json.dumps(_reading(values=values)), "GDP")


def test_values_not_a_list_raises():
    with pytest.raises(GraphReadingError, match="'values' must be a list"):
        parse_reading_output(json.dumps(_reading(values={"Guyana": 29000})), "GDP")
