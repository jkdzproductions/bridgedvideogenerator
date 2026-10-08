import pytest

import footage.archive_types as types_mod
from footage.archive_loc import parse_loc_photos_response, search_loc_photos

_OPEN = "No known restrictions on publication. For information, see \"Civil war photographs\"."


def _result(**over):
    r = {
        "id": "http://www.loc.gov/item/2018666985/", "url": "https://www.loc.gov/item/2018666985/",
        "title": "[Atlanta, Ga. Atlanta Intelligencer office by the railroad depot]", "date": "1864",
        "access_restricted": False, "online_format": ["image"],
        "image_url": [
            "https://tile.loc.gov/storage-services/service/pnp/cwpb/03300/03359_150px.jpg#h=150&w=129",
            "https://tile.loc.gov/storage-services/service/pnp/cwpb/03300/03359r.jpg#h=640&w=551",
            "https://tile.loc.gov/storage-services/service/pnp/cwpb/03300/03359v.jpg#h=1600&w=1378",
        ],
        "item": {"rights_advisory": _OPEN}, "contributor": ["Barnard, George N., photographer"],
    }
    r.update(over)
    return r


def test_an_open_photo_becomes_a_candidate_using_the_largest_image():
    [c] = parse_loc_photos_response({"results": [_result()]})

    assert (c.source, c.item_id, c.kind, c.year) == ("loc", "2018666985", "photo", 1864)
    assert c.media_url == "https://tile.loc.gov/storage-services/service/pnp/cwpb/03300/03359v.jpg"
    assert c.thumbnail_url == "https://tile.loc.gov/storage-services/service/pnp/cwpb/03300/03359r.jpg"  # first image >= 400 px
    assert (c.width, c.height) == (1378, 1600)
    assert c.title.startswith("[Atlanta, Ga.") and c.creator == "Barnard, George N., photographer"
    assert c.rights == _OPEN and c.page_url == "https://www.loc.gov/item/2018666985/"


def test_the_judge_thumbnail_is_the_smallest_derivative_of_at_least_400px_whatever_the_list_order():
    big_first = list(reversed(_result()["image_url"]))
    [c] = parse_loc_photos_response({"results": [_result(image_url=big_first)]})

    assert c.thumbnail_url == "https://tile.loc.gov/storage-services/service/pnp/cwpb/03300/03359r.jpg"
    assert c.media_url == "https://tile.loc.gov/storage-services/service/pnp/cwpb/03300/03359v.jpg"


def test_rights_may_be_a_list():
    [c] = parse_loc_photos_response({"results": [_result(item={"rights_advisory": [_OPEN, "More text."]})]})

    assert "No known restrictions" in c.rights


@pytest.mark.parametrize("over", [
    {"item": {"rights_advisory": "Rights status not evaluated. Contact the repository."}},
    {"item": {"rights_advisory": "Not in the public domain."}},
    {"item": {"rights_advisory": "Rights status not evaluated. Public domain status unknown."}},
    {"item": {"rights_advisory": "May still be protected; public domain status not determined"}},
    {"item": {"rights_advisory": ["No known restrictions on publication.", "Restricted: see repository"]}},
    {"item": {"rights_advisory": ["Contact the repository", "No known restrictions on publication."]}},
    {"item": {}},                                      # no rights statement at all
    {"access_restricted": True},
    {"online_format": ["online text"]},                # not an image item
    {"image_url": []},
    {"image_url": ["https://tile.loc.gov/x/y.gif#h=900&w=900"]},   # not a jpg/png
    {"image_url": ["https://tile.loc.gov/x/y_150px.jpg#h=150&w=129"]},  # only a tiny image
])
def test_unclear_restricted_or_unusable_items_never_become_candidates(over):
    assert parse_loc_photos_response({"results": [_result(**over)]}) == []


def test_public_domain_wording_is_accepted():
    assert len(parse_loc_photos_response({"results": [_result(item={"rights_advisory": "Public domain."})]})) == 1


def test_a_known_year_outside_the_range_is_dropped():
    results = {"results": [_result(date="1864"), _result(id="http://www.loc.gov/item/2/", date="1920")]}

    assert [c.item_id for c in parse_loc_photos_response(results, year_range=(1850, 1880))] == ["2018666985"]


def test_an_empty_or_missing_results_list_is_no_candidates():
    assert parse_loc_photos_response({"results": []}) == []
    assert parse_loc_photos_response({}) == []


def test_search_asks_for_digitized_images_in_the_date_range(monkeypatch):
    seen = {}

    class Resp:
        status_code = 200
        def json(self): return {"results": [_result()]}

    def fake_get(url, params=None, headers=None, timeout=None, **kw):
        seen.update(url=url, params=params, headers=headers)
        return Resp()

    monkeypatch.setattr(types_mod.requests, "get", fake_get)

    assert len(search_loc_photos("atlanta railroad", (1855, 1875), limit=9)) == 1
    assert seen["url"] == "https://www.loc.gov/photos/"
    assert seen["params"] == {"q": "atlanta railroad", "fo": "json", "c": 9,
                              "fa": "online-format:image", "dates": "1855/1875"}
    assert seen["headers"]["User-Agent"] == "BridgedVideoGenerator/0.1"


def test_search_without_a_range_sends_no_dates(monkeypatch):
    seen = {}

    class Resp:
        status_code = 200
        def json(self): return {"results": []}

    monkeypatch.setattr(types_mod.requests, "get", lambda url, params=None, **k: seen.update(params=params) or Resp())

    search_loc_photos("x y")

    assert "dates" not in seen["params"]


class _OkResp:
    status_code = 200
    def json(self): return {"results": []}


@pytest.mark.parametrize("query, sent", [
    ("Atlanta railroad depot 1847", "Atlanta railroad depot"),
    ("Atlanta Georgia 1840s", "Atlanta Georgia"),
])
def test_search_strips_year_and_decade_words_but_keeps_the_dates_filter(monkeypatch, query, sent):
    seen = {}
    monkeypatch.setattr(types_mod.requests, "get", lambda url, params=None, **k: seen.update(params=params) or _OkResp())

    search_loc_photos(query, (1837, 1857))

    assert seen["params"]["q"] == sent and seen["params"]["dates"] == "1837/1857"


def test_a_query_of_only_year_words_is_an_error(monkeypatch):
    monkeypatch.setattr(types_mod.requests, "get", lambda *a, **k: pytest.fail("must not search"))

    with pytest.raises(types_mod.ArchiveError, match="1860s 1847"):
        search_loc_photos("1860s 1847", (1840, 1870))
