import pytest
from footage.envato import (
    EnvatoCandidate,
    EnvatoCandidateDetails,
    EnvatoError,
    _build_search_url,
    _parse_detail_page_text,
    _parse_search_results,
)


def test_build_search_url_encodes_query_and_fixes_category():
    url = _build_search_url("tokyo subway station")
    assert url == (
        "https://app.envato.com/search"
        "?term=tokyo+subway+station&itemType=stock-video&filter.categories=Stock+Footage"
    )


def test_build_search_url_never_omits_stock_footage_category():
    # Global Constraint: never search without the category filter, whatever the query is.
    url = _build_search_url("")
    assert "filter.categories=Stock+Footage" in url


# Raw shape returned by a fake page's DOM query — a list of dicts, one per result link, with
# exactly the fields the real extraction step (Task 2 Step 3) is responsible for pulling out of
# the page. This is the seam between "talk to a real browser" and "build our data model."
RAW_RESULTS = [
    {
        "href": "/search/stock-video/822c42d5-d733-4462-bc48-542a73ab8833?term=x",
        "title": "Cityscape Aerial View with Modern Architecture",
        "thumbnail_src": "https://envato-cdn.example/thumbs/822c42d5.jpg",
        "author": "Mizunee",
    },
    {
        "href": "/search/stock-video/a206739b-7927-42d0-b0bb-0dc885181f30?term=x",
        "title": "Downtown Skyline at Dusk",
        "thumbnail_src": "https://envato-cdn.example/thumbs/a206739b.jpg",
        "author": "JIAYUELIANG",
    },
]


def test_parse_search_results_extracts_item_id_from_href():
    candidates = _parse_search_results(RAW_RESULTS)
    assert candidates[0] == EnvatoCandidate(
        item_id="822c42d5-d733-4462-bc48-542a73ab8833",
        title="Cityscape Aerial View with Modern Architecture",
        thumbnail_url="https://envato-cdn.example/thumbs/822c42d5.jpg",
        author="Mizunee",
        detail_url="https://app.envato.com/search/stock-video/822c42d5-d733-4462-bc48-542a73ab8833?term=x",
    )
    assert candidates[1].item_id == "a206739b-7927-42d0-b0bb-0dc885181f30"


def test_parse_search_results_handles_empty_list():
    assert _parse_search_results([]) == []


def test_parse_search_results_raises_on_unparseable_href():
    with pytest.raises(EnvatoError, match="could not extract an item id"):
        _parse_search_results([{
            "href": "/not-a-stock-video-link", "title": "x",
            "thumbnail_src": "https://x/y.jpg", "author": "x",
        }])


# Raw text pulled from a real item detail page's metadata block — exactly the field labels
# observed live: "30 seconds", "1920 x 1080 px", "50 fps", "Horizontal".
DETAIL_PAGE_TEXT = """Cityscape Aerial View with Modern Architecture
by Mizunee
30 seconds
1920 x 1080 px
50 fps
No Alpha Channel
Not Looped
Horizontal
ProRes"""


def test_parse_detail_page_text_extracts_duration_and_dimensions():
    details = _parse_detail_page_text(DETAIL_PAGE_TEXT)
    assert details == EnvatoCandidateDetails(duration_seconds=30.0, width=1920, height=1080)


def test_parse_detail_page_text_raises_when_duration_missing():
    with pytest.raises(EnvatoError, match="duration"):
        _parse_detail_page_text("Some Title\nby Someone\n1920 x 1080 px\n50 fps")


def test_parse_detail_page_text_raises_when_dimensions_missing():
    with pytest.raises(EnvatoError, match="resolution"):
        _parse_detail_page_text("Some Title\nby Someone\n30 seconds\n50 fps")


def test_logged_out_url_detection_matches_real_envato_sign_in_redirect():
    # I1: the real logged-out redirect observed live in Task 1 contains no "login" at all.
    from footage.envato import _is_logged_out_url

    assert _is_logged_out_url("https://account.envato.com/sign_in?to=envatoapp&state=abc123")
    assert _is_logged_out_url("https://app.envato.com/login")
    assert not _is_logged_out_url(
        "https://app.envato.com/search?term=tokyo&itemType=stock-video&filter.categories=Stock+Footage"
    )
    # A search term that merely mentions logging in must not look like a logged-out redirect.
    assert not _is_logged_out_url(
        "https://app.envato.com/search?term=login+screen&itemType=stock-video"
    )
