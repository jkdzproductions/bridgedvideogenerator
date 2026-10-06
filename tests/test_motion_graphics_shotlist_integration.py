from motion_graphics.shotlist_integration import graphic_beats
from shot_list.models import Beat, FootageSpec, GraphicSpec, ShotList


def test_graphic_beats_extracts_only_graphic_beats_with_index_and_duration():
    chart = GraphicSpec("chart_card", {"value": "14M"})
    shot_list = ShotList(
        beats=[
            Beat(0.0, 4.0, "footage", footage=FootageSpec("tokyo subway", "Tokyo's subway")),
            Beat(4.0, 9.5, "graphic", graphic=chart),
            Beat(9.5, 13.0, "footage", footage=FootageSpec("crowded platform", "rush hour crowd")),
        ],
        duration=13.0,
    )

    result = graphic_beats(shot_list)

    assert result == [(1, chart, 5.5)]


def test_graphic_beats_returns_empty_list_when_all_footage():
    shot_list = ShotList(
        beats=[Beat(0.0, 5.0, "footage", footage=FootageSpec("q", "s"))],
        duration=5.0,
    )

    assert graphic_beats(shot_list) == []


def test_graphic_beats_preserves_order_across_multiple_graphic_beats():
    spec_a = GraphicSpec("distance", {"rows": []})
    spec_b = GraphicSpec("chart_card", {"series": []})
    shot_list = ShotList(
        beats=[
            Beat(0.0, 3.0, "graphic", graphic=spec_a),
            Beat(3.0, 6.0, "footage", footage=FootageSpec("q", "s")),
            Beat(6.0, 9.0, "graphic", graphic=spec_b),
        ],
        duration=9.0,
    )

    result = graphic_beats(shot_list)

    assert result == [(0, spec_a, 3.0), (2, spec_b, 3.0)]
