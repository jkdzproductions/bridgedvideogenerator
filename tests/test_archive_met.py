# tests/test_archive_met.py
import pytest

import footage.archive_met as met
from footage.archive_met import parse_met_object, search_met_artwork
from footage.archive_types import ArchiveError


def _obj(**over):
    base = {
        "objectID": 746201, "isPublicDomain": True,
        "primaryImage": "https://images.metmuseum.org/CRDImages/dp/original/DP880111.jpg",
        "primaryImageSmall": "https://images.metmuseum.org/CRDImages/dp/web-large/DP880111.jpg",
        "title": "Bataille", "artistDisplayName": "Quentin Pierre Chedel", "objectDate": "18th century",
        "objectBeginDate": 1715, "objectEndDate": 1763, "classification": "Prints", "medium": "Etching",
        "objectURL": "https://www.metmuseum.org/art/collection/search/746201",
        "creditLine": "Harris Brisbane Dick Fund, 1953",
    }
    base.update(over)
    return base


def test_a_public_domain_object_becomes_an_artwork_candidate():
    c = parse_met_object(_obj())

    assert (c.source, c.item_id, c.kind, c.title) == ("met", "746201", "photo", "Bataille")
    assert c.year == 1739                                  # midpoint of the object's begin/end dates
    assert c.creator == "Quentin Pierre Chedel" and c.rights == "Public domain (The Met Open Access)"
    assert c.media_url.endswith("DP880111.jpg") and "original" in c.media_url
    assert c.thumbnail_url.endswith("web-large/DP880111.jpg")
    assert c.page_url == "https://www.metmuseum.org/art/collection/search/746201"
    assert c.display_id == "met:746201"


@pytest.mark.parametrize("over", [
    {"isPublicDomain": False}, {"isPublicDomain": "False"}, {"primaryImage": ""}, {"primaryImage": None},
    {"title": ""},
])
def test_non_public_domain_or_imageless_objects_are_dropped(over):
    assert parse_met_object(_obj(**over)) is None


def test_an_object_with_unusable_dates_has_an_unknown_year():
    assert parse_met_object(_obj(objectBeginDate=0, objectEndDate=0)).year is None


def test_search_runs_one_v11_search_then_one_object_fetch_per_id(monkeypatch):
    calls = []

    def fake_get_json(url, params):
        calls.append((url, dict(params)))
        if url == met.MET_SEARCH_URL:
            return {"total": 3, "objectIDs": [1, 2, 3]}
        return _obj(objectID=int(url.rsplit("/", 1)[1]))

    monkeypatch.setattr(met, "get_json", fake_get_json)

    result = search_met_artwork("naval battle", (1750, 1800), limit=3)

    assert [c.item_id for c in result] == ["1", "2", "3"]
    search_url, params = calls[0]
    assert search_url == "https://collectionapi.metmuseum.org/public/collection/v1.1/search"
    assert params == {"q": "naval battle", "hasImages": "true", "isPublicDomain": "true",
                      "dateBegin": 1750, "dateEnd": 1800, "limit": 3, "offset": 0}
    assert [u for u, _ in calls[1:]] == [f"https://collectionapi.metmuseum.org/public/collection/v1/objects/{i}" for i in (1, 2, 3)]


def test_year_and_decade_words_are_stripped_from_the_met_query(monkeypatch):
    seen = {}
    monkeypatch.setattr(met, "get_json", lambda url, params: seen.update(q=params["q"]) or {"total": 0, "objectIDs": []})

    search_met_artwork("naval battle 1781 1780s")

    assert seen["q"] == "naval battle"


def test_no_results_is_an_empty_list_and_no_year_range_sends_no_dates(monkeypatch):
    seen = {}
    monkeypatch.setattr(met, "get_json", lambda url, params: seen.update(params=dict(params)) or {"total": 0, "objectIDs": None})

    assert search_met_artwork("zzz") == []
    assert "dateBegin" not in seen["params"] and "dateEnd" not in seen["params"]


def test_one_failing_object_fetch_skips_that_object_only(monkeypatch):
    def fake_get_json(url, params):
        if url == met.MET_SEARCH_URL:
            return {"total": 2, "objectIDs": [1, 2]}
        if url.endswith("/1"):
            raise ArchiveError("object 1: 404")
        return _obj(objectID=2)

    monkeypatch.setattr(met, "get_json", fake_get_json)

    assert [c.item_id for c in search_met_artwork("x")] == ["2"]


def test_a_failing_search_call_propagates_as_archive_error(monkeypatch):
    def boom(url, params): raise ArchiveError("search: 500")
    monkeypatch.setattr(met, "get_json", boom)

    with pytest.raises(ArchiveError, match="500"):
        search_met_artwork("x")


def _clock(monkeypatch, times):
    it = iter(times)
    monkeypatch.setattr(met.time, "monotonic", lambda: next(it))


def test_the_fetch_budget_stops_further_object_calls_and_returns_what_was_fetched(monkeypatch, capsys):
    fetched = []

    def fake_get_json(url, params):
        if url == met.MET_SEARCH_URL:
            return {"objectIDs": [1, 2, 3, 4]}
        fetched.append(url)
        return _obj(objectID=int(url.rsplit("/", 1)[1]))

    monkeypatch.setattr(met, "get_json", fake_get_json)
    assert met.MET_STEP_BUDGET_SECONDS == 45
    _clock(monkeypatch, [0, 1, 2, 46, 47])  # start, before obj 1, before obj 2, before obj 3 (over budget)

    result = search_met_artwork("x")

    assert [c.item_id for c in result] == ["1", "2"] and len(fetched) == 2
    assert "WARNING: Met object fetch budget used up after 2 objects" in capsys.readouterr().out


def test_two_consecutive_object_failures_stop_the_fetching(monkeypatch, capsys):
    fetched = []

    def fake_get_json(url, params):
        if url == met.MET_SEARCH_URL:
            return {"objectIDs": [1, 2, 3, 4]}
        fetched.append(url)
        raise ArchiveError("down")

    monkeypatch.setattr(met, "get_json", fake_get_json)

    assert search_met_artwork("x") == []
    assert len(fetched) == 2 and "WARNING" in capsys.readouterr().out


def test_a_success_resets_the_consecutive_failure_count(monkeypatch):
    def fake_get_json(url, params):
        if url == met.MET_SEARCH_URL:
            return {"objectIDs": [1, 2, 3, 4, 5]}
        i = int(url.rsplit("/", 1)[1])
        if i in (1, 3):
            raise ArchiveError("blip")
        return _obj(objectID=i)

    monkeypatch.setattr(met, "get_json", fake_get_json)

    assert [c.item_id for c in search_met_artwork("x", limit=5)] == ["2", "4", "5"]


def test_a_query_that_is_only_year_words_raises_naming_the_original_query(monkeypatch):
    monkeypatch.setattr(met, "get_json", lambda *a: pytest.fail("no request should be made"))

    with pytest.raises(ArchiveError, match="1781 1780s"):
        search_met_artwork("1781 1780s")


def test_an_object_whose_dates_do_not_overlap_the_range_is_dropped(monkeypatch):
    objs = {1: _obj(objectID=1, objectBeginDate=1900, objectEndDate=1910),
            2: _obj(objectID=2, objectBeginDate=1770, objectEndDate=1790),
            3: _obj(objectID=3, objectBeginDate=0, objectEndDate=0),
            4: _obj(objectID=4, objectBeginDate=1700, objectEndDate=1740)}

    def fake_get_json(url, params):
        if url == met.MET_SEARCH_URL:
            return {"objectIDs": [1, 2, 3, 4]}
        return objs[int(url.rsplit("/", 1)[1])]

    monkeypatch.setattr(met, "get_json", fake_get_json)

    assert [c.item_id for c in search_met_artwork("x", (1750, 1800))] == ["2", "3"]


def test_a_missing_object_id_and_a_non_list_object_ids_are_skipped_not_raised(monkeypatch):
    def fake_get_json(url, params):
        if url == met.MET_SEARCH_URL:
            return {"objectIDs": [1, 2]}
        if url.endswith("/1"):
            o = _obj()
            del o["objectID"]
            return o
        return _obj(objectID=2)

    monkeypatch.setattr(met, "get_json", fake_get_json)
    assert [c.item_id for c in search_met_artwork("x")] == ["2"]
    assert parse_met_object({k: v for k, v in _obj().items() if k != "objectID"}) is None

    monkeypatch.setattr(met, "get_json", lambda url, params: {"objectIDs": "oops"})
    assert search_met_artwork("x") == []
