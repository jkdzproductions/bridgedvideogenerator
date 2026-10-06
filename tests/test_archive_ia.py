# tests/test_archive_ia.py
import pytest

import footage.archive_ia as ia
from footage.archive_ia import (
    build_ia_query, candidate_from_metadata, film_year_range, parse_ia_search, search_ia_film,
)
from footage.archive_types import ArchiveError

_PD = "http://creativecommons.org/licenses/publicdomain/"


def _doc(identifier="reel1", license_=_PD, year=1938, **over):
    d = {"identifier": identifier, "title": "City Reel", "year": year, "licenseurl": license_, "creator": "Prelinger"}
    d.update(over)
    return d


def _meta(files):
    return {"files": files}


def _file(name="reel1.mp4", fmt="h.264", length="382.39", width="640", height="480"):
    return {"name": name, "format": fmt, "length": length, "width": width, "height": height}


def test_film_year_range_is_clipped_to_when_film_existed_and_the_cutoff():
    assert film_year_range(1938) == (1923, 1953)
    assert film_year_range(1955) == (1940, 1959)       # never reaches 1960
    assert film_year_range(1900) == (1895, 1915)
    assert film_year_range(1863) is None               # film did not exist yet
    assert film_year_range(1847) is None


def test_the_query_is_anded_words_limited_to_the_two_film_collections_and_the_years():
    q = build_ia_query("Atlanta railroad depot 1860s, the city's", (1895, 1915))

    assert q == ("(Atlanta AND railroad AND depot AND city) AND collection:(prelinger OR universal_newsreels) "
                 "AND mediatype:movies AND year:[1895 TO 1915]")


def test_a_query_with_no_searchable_words_stops_loudly():
    with pytest.raises(ArchiveError, match="searchable"):
        build_ia_query("the 1860s of a", (1895, 1915))


def test_only_public_domain_licensed_docs_survive_the_search_parse():
    payload = {"response": {"docs": [
        _doc("a"), _doc("b", license_="https://creativecommons.org/licenses/by/4.0/"),
        _doc("c", license_=None), _doc("d", license_=["http://creativecommons.org/publicdomain/zero/1.0/"]),
    ]}}

    assert [d["identifier"] for d in parse_ia_search(payload)] == ["a", "d"]


def test_a_doc_and_its_metadata_become_a_film_candidate_with_a_direct_download_url():
    c = candidate_from_metadata(_doc(), _meta([_file("a b.mp4"), _file("reel1_512kb.mp4", "512Kb MPEG4", "382.35", "320", "240")]))

    assert (c.source, c.item_id, c.kind, c.year) == ("ia", "reel1", "film", 1938)
    assert c.media_url == "https://archive.org/download/reel1/a%20b.mp4"      # the h.264 file wins, name url-quoted
    assert c.thumbnail_url == "https://archive.org/services/img/reel1"
    assert c.page_url == "https://archive.org/details/reel1"
    assert (c.width, c.height) == (640, 480) and c.duration_seconds == pytest.approx(382.39)
    assert c.rights == "Public domain" and c.creator == "Prelinger"


def test_a_512kb_mp4_is_used_when_there_is_no_h264_file():
    c = candidate_from_metadata(_doc(), _meta([_file("x_512kb.mp4", "512Kb MPEG4")]))

    assert c.media_url.endswith("x_512kb.mp4")


@pytest.mark.parametrize("files", [
    [],                                              # no playable file
    [_file("x.ogv", "Ogg Video")],
    [_file(length="2.0")],                           # shorter than the 3 s floor
    [_file(length="n/a")],                           # unreadable length
])
def test_a_film_without_a_usable_video_file_is_dropped(files):
    assert candidate_from_metadata(_doc(), _meta(files)) is None


def test_search_ia_film_skips_the_network_for_an_era_before_film_existed(monkeypatch):
    monkeypatch.setattr(ia, "get_json", lambda *a, **k: pytest.fail("must not search"))

    assert search_ia_film("Atlanta railroad 1847", 1847) == []


def test_search_ia_film_searches_once_then_reads_metadata_for_each_licensed_doc(monkeypatch):
    calls = []

    def fake_get_json(url, params):
        calls.append((url, params))
        if "advancedsearch" in url:
            return {"response": {"docs": [_doc("a"), _doc("b", license_=None), _doc("c")]}}
        return _meta([_file(f"{url.rsplit('/', 1)[1]}.mp4")])

    monkeypatch.setattr(ia, "get_json", fake_get_json)

    films = search_ia_film("Atlanta street", 1938, limit=5)

    assert [f.item_id for f in films] == ["a", "c"]                       # the unlicensed doc never costs a metadata call
    assert [u for u, _ in calls] == ["https://archive.org/advancedsearch.php",
                                     "https://archive.org/metadata/a", "https://archive.org/metadata/c"]
    params = calls[0][1]
    assert params["rows"] == 5 and params["output"] == "json" and "year:[1923 TO 1953]" in params["q"]
    assert "identifier" in params["fl[]"] and "licenseurl" in params["fl[]"]


def test_a_metadata_failure_for_one_film_skips_that_film_not_the_search(monkeypatch):
    def fake_get_json(url, params):
        if "advancedsearch" in url:
            return {"response": {"docs": [_doc("a"), _doc("c")]}}
        if url.endswith("/a"):
            raise ArchiveError("boom")
        return _meta([_file()])

    monkeypatch.setattr(ia, "get_json", fake_get_json)

    assert [f.item_id for f in search_ia_film("Atlanta street", 1938)] == ["c"]


@pytest.mark.parametrize("width,height,expected_height", [("640x480", "480", 480), ("n/a", None, 0), ("", "abc", 0)])
def test_a_malformed_width_or_height_becomes_zero_instead_of_crashing(width, height, expected_height):
    video = _file(width=width)
    video["height"] = height

    candidate = candidate_from_metadata(_doc(), _meta([video]))

    assert candidate is not None and candidate.width == 0 and candidate.height == expected_height


@pytest.mark.parametrize("length", ["nan", "inf", "-inf"])
def test_a_non_finite_duration_is_rejected(length):
    assert candidate_from_metadata(_doc(), _meta([_file(length=length)])) is None
