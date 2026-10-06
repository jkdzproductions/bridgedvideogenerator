import dataclasses

import pytest

from footage.shotlist_integration import archival_beats, footage_beats
from shot_list.models import (
    ARCHIVAL_CUTOFF_YEAR, PHOTO_EARLIEST_YEAR, Beat, FootageSpec, GraphicSpec, ShotList, ShotListValidationError,
    beat_from_dict, is_archival, needs_archival, validate_shot_list,
)


def _beat(start, end, **spec):
    return Beat(start, end, "footage", footage=FootageSpec("stock query", "a subject", **spec))


def test_the_cutoff_is_1960():
    assert ARCHIVAL_CUTOFF_YEAR == 1960


def test_is_archival_only_for_a_year_strictly_before_the_cutoff():
    assert not is_archival(FootageSpec("q", "s"))                    # era None = modern
    assert not is_archival(FootageSpec("q", "s", era=1960))
    assert not is_archival(FootageSpec("q", "s", era=1985))          # a year, but not old: still modern
    assert is_archival(FootageSpec("q", "s", era=1959))
    assert is_archival(FootageSpec("q", "s", era=1847))


def test_a_shot_list_dict_written_before_era_existed_loads_as_modern():
    old = {"start": 0.0, "end": 4.0, "type": "footage",
           "footage": {"query": "tokyo subway", "subject": "Tokyo"}}

    beat = beat_from_dict(old)

    assert beat.footage == FootageSpec("tokyo subway", "Tokyo")
    assert beat.footage.era is None


def test_era_and_queries_survive_the_asdict_round_trip():
    beat = _beat(0.0, 4.0, era=1847, archival_query="Atlanta 1847", archival_broad_query="Atlanta 1840s")

    assert beat_from_dict(dataclasses.asdict(beat)) == beat


@pytest.mark.parametrize("query,broad", [("", "Atlanta 1840s"), ("Atlanta 1847", ""), ("  ", "x"), ("x", "  ")])
def test_an_archival_beat_needs_both_archival_queries(query, broad):
    shot_list = ShotList([_beat(0.0, 4.0, era=1847, archival_query=query, archival_broad_query=broad)], 4.0)

    with pytest.raises(ShotListValidationError, match="archival_query"):
        validate_shot_list(shot_list)


def test_an_archival_beat_with_both_queries_is_valid():
    validate_shot_list(ShotList(
        [_beat(0.0, 4.0, era=1847, archival_query="Atlanta 1847", archival_broad_query="Atlanta 1840s")], 4.0))


def test_a_modern_beat_needs_no_archival_queries():
    validate_shot_list(ShotList([_beat(0.0, 4.0), _beat(4.0, 8.0, era=1985)], 8.0))


def test_footage_beats_is_modern_only_and_archival_beats_lists_the_rest():
    shot_list = ShotList([
        _beat(0.0, 4.0),
        _beat(4.0, 9.0, era=1847, archival_query="Atlanta railroad 1847", archival_broad_query="Atlanta 1840s"),
        Beat(9.0, 12.0, "graphic", graphic=GraphicSpec("chart_card", {})),
        _beat(12.0, 15.0, era=1985),
    ], 15.0)

    assert footage_beats(shot_list) == [(0, "stock query", "a subject"), (3, "stock query", "a subject")]
    assert archival_beats(shot_list) == [{
        "beat_index": 1, "start": 4.0, "end": 9.0, "era": 1847, "subject": "a subject",
        "archival_query": "Atlanta railroad 1847", "archival_broad_query": "Atlanta 1840s",
        "medium": "photo_or_artwork", "query": "stock query",
    }]


def test_a_cut_before_the_cutoff_is_archival_whatever_the_year():
    assert PHOTO_EARLIEST_YEAR == 1839
    assert is_archival(FootageSpec("q", "s", era=1838))
    assert is_archival(FootageSpec("q", "s", era=1839))
    assert is_archival(FootageSpec("q", "s", era=1959))
    assert not is_archival(FootageSpec("q", "s", era=1960))


def test_every_era_before_1960_is_archival_and_the_medium_follows_the_year():
    from shot_list.models import archival_medium, needs_archival
    for era in (1781, 1838, 1839, 1863, 1899, 1900, 1959):
        assert needs_archival(era)
    assert not needs_archival(1960) and not needs_archival(None)
    assert archival_medium(1781) == "artwork_or_stock" and archival_medium(1838) == "artwork_or_stock"
    assert archival_medium(1839) == "photo_or_artwork" and archival_medium(1863) == "photo_or_artwork"
    assert archival_medium(1899) == "photo_or_artwork"
    assert archival_medium(1900) == "photo" and archival_medium(1959) == "photo"


def test_mixed_era_beats_are_archival_need_their_queries_and_are_listed_with_medium_and_stock_query():
    old = Beat(0.0, 4.0, "footage", footage=FootageSpec(
        "ship at sea", "a ship", era=1781, archival_query="naval battle 1781", archival_broad_query="18th century naval"))
    civil = Beat(4.0, 8.0, "footage", footage=FootageSpec(
        "battlefield", "a battle", era=1863, archival_query="Gettysburg battle 1863", archival_broad_query="Civil War battle"))
    shot_list = ShotList([old, civil], 8.0)
    validate_shot_list(shot_list)
    assert footage_beats(shot_list) == []
    listed = archival_beats(shot_list)
    assert [(b["beat_index"], b["medium"], b["query"]) for b in listed] == [
        (0, "artwork_or_stock", "ship at sea"), (1, "photo_or_artwork", "battlefield")]
    assert listed[0]["archival_query"] == "naval battle 1781" and listed[1]["era"] == 1863


@pytest.mark.parametrize("era", [1781, 1863, 1930])
def test_an_archival_era_beat_without_archival_queries_is_rejected(era):
    beat = Beat(0.0, 4.0, "footage", footage=FootageSpec("q", "s", era=era))
    with pytest.raises(ShotListValidationError, match="archival_query"):
        validate_shot_list(ShotList([beat], 4.0))
