from footage.shotlist_integration import footage_beats
from shot_list.models import Beat, FootageSpec, GraphicSpec, ShotList


def test_footage_beats_extracts_only_footage_beats_with_original_index():
    shot_list = ShotList(
        beats=[
            Beat(0.0, 4.0, "footage", footage=FootageSpec("tokyo subway", "Tokyo's subway")),
            Beat(4.0, 9.0, "graphic", graphic=GraphicSpec("chart_card", {"value": "14M"})),
            Beat(9.0, 13.0, "footage", footage=FootageSpec("crowded platform", "rush hour crowd")),
        ],
        duration=13.0,
    )

    result = footage_beats(shot_list)

    assert result == [
        (0, "tokyo subway", "Tokyo's subway"),
        (2, "crowded platform", "rush hour crowd"),
    ]


def test_footage_beats_returns_empty_list_when_all_graphic():
    shot_list = ShotList(
        beats=[Beat(0.0, 5.0, "graphic", graphic=GraphicSpec("chart_card", {}))],
        duration=5.0,
    )

    assert footage_beats(shot_list) == []
