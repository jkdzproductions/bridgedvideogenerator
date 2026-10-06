import dataclasses

import pytest

from shot_list.models import (
    Beat, FootageSpec, GraphicSpec, ImageSpec, PageSpec, ShotList, ShotListValidationError,
    beat_from_dict, validate_shot_list)


def _validate(beat):
    validate_shot_list(ShotList(beats=[beat], duration=beat.end))


def test_an_image_beat_with_an_image_spec_is_valid():
    _validate(Beat(0.0, 4.0, "image", image=ImageSpec(italic_index=2)))


def test_an_image_beat_without_an_image_spec_is_rejected():
    with pytest.raises(ShotListValidationError, match="image beat at 0.0 missing image spec"):
        _validate(Beat(0.0, 4.0, "image"))


@pytest.mark.parametrize("extra", [
    {"footage": FootageSpec("q", "s")},
    {"graphic": GraphicSpec("chart_card", {"a": 1})},
    {"page": PageSpec(italic_index=1)},
])
def test_an_image_beat_must_not_carry_another_spec(extra):
    with pytest.raises(ShotListValidationError, match="image beat at 0.0 must not carry"):
        _validate(Beat(0.0, 4.0, "image", image=ImageSpec(italic_index=2), **extra))


def test_beat_from_dict_round_trips_an_image_beat():
    original = Beat(0.0, 4.0, "image", image=ImageSpec(italic_index=2))

    assert beat_from_dict(dataclasses.asdict(original)) == original


def test_a_shot_list_written_before_image_beats_existed_still_loads():
    old = {"start": 0.0, "end": 4.0, "type": "talking_head", "footage": None, "graphic": None, "page": None}

    assert beat_from_dict(old).image is None
