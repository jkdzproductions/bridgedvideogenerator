from graph_intake.report import build_linked_graphs_report

READINGS = {0: {
    "italic_text": "GDP per capita", "url": "https://i.redd.it/x.jpeg",
    "image_path": "/abs/graph_inputs/graph_0.jpg", "width": 1080, "height": 1350,
    "reading": {
        "title": "GDP Per Capita", "subtitle": None, "graph_kind": "choropleth map",
        "unit": "US dollars", "source_line": "Source: IMF October 2024 World Economic Outlook",
        "notes": "No data for Cuba.",
        "values": [
            {"label": "Guyana", "display": "$29K", "value": 29000, "readable": True},
            {"label": "BLZ", "display": "$8?", "value": None, "readable": False},
        ],
    },
}}


def test_report_lists_every_value_with_the_verify_flag():
    report = build_linked_graphs_report(READINGS, [])

    assert "Linked graphs (1):" in report
    assert "'GDP per capita'" in report
    assert "https://i.redd.it/x.jpeg" in report
    assert "/abs/graph_inputs/graph_0.jpg" in report
    assert "GDP Per Capita" in report and "choropleth map" in report
    assert "Source: IMF October 2024 World Economic Outlook" in report
    assert "read from an image — verify against the source before publishing" in report
    assert "- Guyana: $29K (29000)" in report
    assert "- BLZ: UNREADABLE (printed as '$8?') — left out of the graphic" in report
    assert "No data for Cuba." in report


def test_report_lists_ignored_links():
    report = build_linked_graphs_report({}, [{"text": " this article ", "url": "https://example.com"}])

    assert "Linked graphs: none." in report
    assert "'this article' -> https://example.com" in report


def test_report_with_nothing_says_so():
    report = build_linked_graphs_report({}, [])

    assert report == "Linked graphs: none.\nLinks on text that is not italic: none."
