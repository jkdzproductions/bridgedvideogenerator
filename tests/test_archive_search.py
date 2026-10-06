# tests/test_archive_search.py
import pytest

import footage.archive_search as search
from footage.archive_search import (
    ArchivalSearchError, broadening_ladder, decade_form, search_film, search_photos,
)
from footage.archive_types import ArchiveCandidate, ArchiveError


def _photo(source, item_id, year=1860):
    return ArchiveCandidate(source, item_id, "photo", f"t{item_id}", year, "", "Public domain", "p", "m", "t", 2000, 1500)


def test_decade_form_replaces_a_year_with_its_decade_or_appends_the_decade():
    assert decade_form("Atlanta railroad depot 1847", 1847) == "Atlanta railroad depot 1840s"
    assert decade_form("Atlanta railroad depot", 1863) == "Atlanta railroad depot 1860s"
    assert decade_form("Atlanta 1847 and 1861", 1847) == "Atlanta 1840s and 1860s"


def test_the_ladder_goes_from_specific_to_broad_with_widening_year_ranges():
    ladder = broadening_ladder(1847, "Atlanta depot 1847", "Atlanta Georgia 1840s")

    assert ladder == [
        ("Atlanta depot 1847", (1837, 1857)),
        ("Atlanta depot 1840s", (1832, 1862)),
        ("Atlanta Georgia 1840s", (1822, 1872)),
        ("Atlanta Georgia 1840s", (1807, 1887)),
    ]


def test_photo_search_stops_climbing_the_ladder_once_it_has_enough_photos(monkeypatch):
    calls = []

    def source(query, year_range):
        calls.append(query)
        return [_photo("loc", f"{len(calls)}-{n}") for n in range(4)]

    result = search_photos(1847, "specific", "broad", sources=[source])

    assert len(calls) == 2 and len(result) == 8        # 4 + 4 >= the target of 6; the rest of the ladder never runs


def test_photo_search_broadens_when_the_specific_query_finds_too_little():
    queries = []

    def source(query, year_range):
        queries.append(query)
        return [_photo("loc", "only")] if "specific" in query else [_photo("loc", f"b{n}") for n in range(7)]

    result = search_photos(1847, "specific 1847", "broad", sources=[source])

    assert queries == ["specific 1847", "specific 1840s", "broad"]
    assert len(result) == 8 and result[0].item_id == "only"


def test_candidates_are_deduplicated_across_sources_and_steps():
    same = _photo("loc", "dup")

    def a(query, year_range): return [same, _photo("loc", "a")]
    def b(query, year_range): return [same, _photo("commons", "b")]

    result = search_photos(1847, "q", "broad", sources=[a, b])

    assert [c.display_id for c in result] == ["loc:dup", "loc:a", "commons:b"]


def test_items_already_used_in_an_earlier_cut_are_excluded():
    def src(query, year_range): return [_photo("loc", "used"), _photo("loc", "fresh")]

    result = search_photos(1847, "q", "b", exclude=frozenset({"loc:used"}), sources=[src])

    assert [c.display_id for c in result] == ["loc:fresh"]


def test_a_photo_with_too_short_a_long_side_is_dropped():
    small = ArchiveCandidate("loc", "s", "photo", "t", 1860, "", "pd", "p", "m", "t", 640, 480)

    def src(query, year_range): return [small, _photo("loc", "ok")]

    assert [c.item_id for c in search_photos(1847, "q", "b", sources=[src])] == ["ok"]


def test_the_result_is_capped_at_the_candidate_maximum():
    def src(query, year_range): return [_photo("loc", str(n)) for n in range(40)]

    assert len(search_photos(1847, "q", "b", sources=[src])) == search.PHOTO_MAX_CANDIDATES


def test_one_failing_source_is_a_warning_while_another_still_works(capsys):
    def broken(query, year_range): raise ArchiveError("loc.gov returned status 429")
    def fine(query, year_range): return [_photo("commons", str(n)) for n in range(7)]

    result = search_photos(1847, "q", "b", sources=[broken, fine])

    assert len(result) == 7
    assert "429" in capsys.readouterr().out


def test_every_source_failing_stops_loudly_naming_the_queries_and_errors():
    def broken(query, year_range): raise ArchiveError("status 500")

    with pytest.raises(ArchivalSearchError) as excinfo:
        search_photos(1847, "specific 1847", "broad", sources=[broken])

    message = str(excinfo.value)
    assert "specific 1847" in message and "broad" in message and "status 500" in message


def test_all_ladder_steps_empty_also_stops_loudly():
    with pytest.raises(ArchivalSearchError, match="no archival photos"):
        search_photos(1847, "q", "b", sources=[lambda query, year_range: []])


def test_film_search_excludes_used_items_and_swallows_an_archive_error(monkeypatch, capsys):
    film = ArchiveCandidate("ia", "reel", "film", "t", 1938, "", "pd", "p", "m", "t", duration_seconds=60.0)
    monkeypatch.setattr(search, "search_ia_film", lambda q, e: [film])
    assert search_film("q", 1938, exclude=frozenset({"ia:reel"})) == []
    assert search_film("q", 1938) == [film]

    def boom(q, e): raise ArchiveError("status 503")
    monkeypatch.setattr(search, "search_ia_film", boom)
    assert search_film("q", 1938) == []
    assert "503" in capsys.readouterr().out


def test_decade_form_leaves_a_query_that_already_has_a_decade_alone():
    assert decade_form("Atlanta depot 1860s", 1847) == "Atlanta depot 1860s"
    assert decade_form("Atlanta 1840s and 1861", 1847) == "Atlanta 1840s and 1860s"
    assert decade_form("Atlanta depot", 1847) == "Atlanta depot 1840s"


def test_photo_results_interleave_the_sources_so_one_cannot_fill_the_cap():
    def loc(query, year_range): return [_photo("loc", str(n)) for n in range(12)]
    def commons(query, year_range): return [_photo("commons", str(n)) for n in range(12)]

    result = search_photos(1847, "q", "b", sources=[loc, commons])

    assert len(result) == search.PHOTO_MAX_CANDIDATES
    assert sum(c.source == "loc" for c in result) == 6 and sum(c.source == "commons" for c in result) == 6
    assert [c.display_id for c in result[:4]] == ["loc:0", "commons:0", "loc:1", "commons:1"]


def test_interleaving_still_dedupes_and_applies_exclusions_and_the_size_floor():
    small = ArchiveCandidate("commons", "s", "photo", "t", 1860, "", "pd", "p", "m", "t", 640, 480)
    same = _photo("loc", "dup")

    def a(query, year_range): return [same, _photo("loc", "used"), _photo("loc", "a")]
    def b(query, year_range): return [small, same, _photo("commons", "b")]

    result = search_photos(1847, "q", "x", exclude=frozenset({"loc:used"}), sources=[a, b])

    assert [c.display_id for c in result] == ["loc:dup", "loc:a", "commons:b"]


def test_a_photo_of_unknown_size_is_kept_while_a_known_small_one_is_dropped():
    unknown = ArchiveCandidate("met", "u", "photo", "t", 1700, "", "pd", "p", "m", "t", 0, 0)
    small = ArchiveCandidate("loc", "s", "photo", "t", 1700, "", "pd", "p", "m", "t", 640, 480)

    def src(query, year_range): return [small, unknown]

    assert [c.item_id for c in search_photos(1700, "q", "b", sources=[src])] == ["u"]


def test_search_photos_uses_an_explicit_ladder_when_given():
    calls = []

    def source(q, r):
        calls.append((q, r))
        return [_photo("loc", "1")] if len(calls) == 2 else []

    result = search_photos(1776, "ignored", "ignored", sources=[source], ladder=[("a", (1, 2)), ("b", (3, 4)), ("c", (5, 6))])

    assert calls == [("a", (1, 2)), ("b", (3, 4)), ("c", (5, 6))]
    assert [c.display_id for c in result] == ["loc:1"]
