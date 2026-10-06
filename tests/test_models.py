import pytest
from shot_list.models import (
    Beat,
    FootageSpec,
    GraphicSpec,
    ShotList,
    ShotListValidationError,
    validate_shot_list,
)


def _footage_beat(start: float, end: float) -> Beat:
    return Beat(start=start, end=end, type="footage", footage=FootageSpec("tokyo subway", "Tokyo subway"))


def _graphic_beat(start: float, end: float, archetype: str = "chart_card") -> Beat:
    return Beat(
        start=start, end=end, type="graphic",
        graphic=GraphicSpec(archetype=archetype, data={"value": "37M"}),
    )


def test_valid_gapless_shot_list_passes():
    shot_list = ShotList(
        beats=[_footage_beat(0.0, 6.0), _graphic_beat(6.0, 11.0), _footage_beat(11.0, 20.0)],
        duration=20.0,
    )
    validate_shot_list(shot_list)  # does not raise


def test_gap_between_beats_raises():
    shot_list = ShotList(
        beats=[_footage_beat(0.0, 6.0), _footage_beat(6.5, 20.0)],
        duration=20.0,
    )
    with pytest.raises(ShotListValidationError, match="gap or overlap"):
        validate_shot_list(shot_list)


def test_first_beat_not_starting_at_zero_raises():
    shot_list = ShotList(beats=[_footage_beat(1.0, 20.0)], duration=20.0)
    with pytest.raises(ShotListValidationError, match="first beat starts"):
        validate_shot_list(shot_list)


def test_last_beat_not_reaching_duration_raises():
    shot_list = ShotList(beats=[_footage_beat(0.0, 15.0)], duration=20.0)
    with pytest.raises(ShotListValidationError, match="last beat ends"):
        validate_shot_list(shot_list)


def test_unknown_archetype_raises():
    shot_list = ShotList(beats=[_graphic_beat(0.0, 20.0, archetype="pie_chart_3d")], duration=20.0)
    with pytest.raises(ShotListValidationError, match="unknown archetype"):
        validate_shot_list(shot_list)


def test_graphic_beat_missing_graphic_spec_raises():
    shot_list = ShotList(beats=[Beat(start=0.0, end=20.0, type="graphic")], duration=20.0)
    with pytest.raises(ShotListValidationError, match="missing graphic spec"):
        validate_shot_list(shot_list)


def test_unknown_beat_type_raises():
    shot_list = ShotList(beats=[Beat(start=0.0, end=20.0, type="not_a_real_type")], duration=20.0)  # type: ignore
    with pytest.raises(ShotListValidationError, match="unknown beat type"):
        validate_shot_list(shot_list)


def test_beat_with_non_positive_duration_raises():
    shot_list = ShotList(
        beats=[_footage_beat(0.0, 6.0), _footage_beat(6.0, 6.0), _footage_beat(6.0, 20.0)],
        duration=20.0,
    )
    with pytest.raises(ShotListValidationError, match="non-positive duration"):
        validate_shot_list(shot_list)


def test_archetypes_are_exactly_the_seven():
    from shot_list.models import ARCHETYPES
    assert ARCHETYPES == {
        "chart_card", "definition", "distance", "org_chart",
        "place_chip", "route_overlay", "territory_map",
    }


import dataclasses

from shot_list.models import PageSpec, beat_from_dict


def _page_shot_list(**beat_overrides):
    beat = dict(start=0.0, end=4.0, type="page_highlight", page=PageSpec(italic_index=2))
    beat.update(beat_overrides)
    return ShotList(beats=[Beat(**beat)], duration=4.0)


def test_page_highlight_beat_with_a_page_spec_is_valid():
    validate_shot_list(_page_shot_list())


def test_page_highlight_beat_without_a_page_spec_is_rejected():
    with pytest.raises(ShotListValidationError, match="page_highlight beat at 0.0 missing page spec"):
        validate_shot_list(_page_shot_list(page=None))


def test_page_highlight_beat_must_not_carry_footage_or_graphic():
    with pytest.raises(ShotListValidationError, match="must not carry a footage or graphic spec"):
        validate_shot_list(_page_shot_list(footage=FootageSpec("q", "s")))


def test_beat_from_dict_round_trips_a_page_highlight_beat():
    original = Beat(0.0, 4.0, "page_highlight", page=PageSpec(italic_index=2))

    assert beat_from_dict(dataclasses.asdict(original)) == original


def test_beat_from_dict_loads_an_old_beat_with_no_page_key():
    old = {"start": 0.0, "end": 3.0, "type": "talking_head", "footage": None, "graphic": None}

    assert beat_from_dict(old) == Beat(0.0, 3.0, "talking_head")


def test_beat_from_dict_loads_footage_and_graphic_beats():
    footage = {"start": 0.0, "end": 3.0, "type": "footage", "footage": {"query": "q", "subject": "s"},
               "graphic": None, "page": None}
    graphic = {"start": 3.0, "end": 6.0, "type": "graphic", "footage": None,
               "graphic": {"archetype": "chart_card", "data": {"a": 1}}, "page": None}

    assert beat_from_dict(footage).footage.query == "q"
    assert beat_from_dict(graphic).graphic.archetype == "chart_card"
