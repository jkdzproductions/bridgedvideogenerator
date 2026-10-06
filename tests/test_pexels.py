import pytest
from footage.pexels import (
    PexelsCandidate,
    PexelsError,
    VideoFile,
    _parse_search_response,
    search_pexels,
    select_best_video_file,
)

FIXTURE_RESPONSE = {
    "page": 1,
    "per_page": 2,
    "total_results": 500,
    "url": "https://www.pexels.com/search/tokyo%20subway/",
    "videos": [
        {
            "id": 3129957, "width": 1920, "height": 1080, "duration": 20,
            "url": "https://www.pexels.com/video/tokyo-subway-station-3129957/",
            "image": "https://images.pexels.com/videos/3129957/free-video-3129957.jpg",
            "user": {"id": 123, "name": "Some Creator", "url": "https://pexels.com/@someone"},
            "video_files": [
                {"id": 1, "quality": "hd", "file_type": "video/mp4", "width": 1920, "height": 1080,
                 "link": "https://player.vimeo.com/external/111.hd.mp4"},
                {"id": 2, "quality": "sd", "file_type": "video/mp4", "width": 640, "height": 360,
                 "link": "https://player.vimeo.com/external/111.sd.mp4"},
            ],
            "video_pictures": [],
        },
        {
            "id": 4242424, "width": 1280, "height": 720, "duration": 12,
            "url": "https://www.pexels.com/video/city-street-4242424/",
            "image": "https://images.pexels.com/videos/4242424/free-video-4242424.jpg",
            "user": {"id": 456, "name": "Another Creator", "url": "https://pexels.com/@another"},
            "video_files": [
                {"id": 3, "quality": "hd", "file_type": "video/mp4", "width": 1280, "height": 720,
                 "link": "https://player.vimeo.com/external/222.hd.mp4"},
            ],
            "video_pictures": [],
        },
    ],
}


def test_parse_search_response_extracts_candidates_in_order():
    candidates = _parse_search_response(FIXTURE_RESPONSE)

    assert len(candidates) == 2
    assert candidates[0] == PexelsCandidate(
        id=3129957,
        url="https://www.pexels.com/video/tokyo-subway-station-3129957/",
        thumbnail_url="https://images.pexels.com/videos/3129957/free-video-3129957.jpg",
        duration=20, width=1920, height=1080,
        video_files=[
            VideoFile("hd", "video/mp4", 1920, 1080, "https://player.vimeo.com/external/111.hd.mp4"),
            VideoFile("sd", "video/mp4", 640, 360, "https://player.vimeo.com/external/111.sd.mp4"),
        ],
    )


def test_parse_search_response_handles_empty_results():
    assert _parse_search_response({"videos": []}) == []


def test_search_pexels_raises_pexels_error_on_401(monkeypatch):
    import footage.pexels as pexels_mod

    class FakeResponse:
        status_code = 401
        text = "Unauthorized"

        def json(self):
            return {}

    monkeypatch.setattr(pexels_mod.requests, "get", lambda *a, **kw: FakeResponse())

    with pytest.raises(PexelsError, match="401"):
        search_pexels("tokyo subway", api_key="bad-key")


def test_search_pexels_raises_pexels_error_on_429(monkeypatch):
    import footage.pexels as pexels_mod

    class FakeResponse:
        status_code = 429
        text = "Too Many Requests"

        def json(self):
            return {}

    monkeypatch.setattr(pexels_mod.requests, "get", lambda *a, **kw: FakeResponse())

    with pytest.raises(PexelsError, match="429"):
        search_pexels("tokyo subway", api_key="some-key")


def test_search_pexels_returns_empty_list_for_no_results(monkeypatch):
    import footage.pexels as pexels_mod

    class FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            return {"videos": []}

    monkeypatch.setattr(pexels_mod.requests, "get", lambda *a, **kw: FakeResponse())

    assert search_pexels("a query pexels has nothing for", api_key="some-key") == []


def test_search_pexels_sends_query_per_page_and_landscape_orientation(monkeypatch):
    import footage.pexels as pexels_mod

    captured = {}

    class FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            return FIXTURE_RESPONSE

    def fake_get(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr(pexels_mod.requests, "get", fake_get)

    candidates = search_pexels("tokyo subway", api_key="some-key", per_page=40)

    assert captured["url"] == "https://api.pexels.com/videos/search"
    assert captured["headers"] == {"Authorization": "some-key"}
    assert captured["params"]["query"] == "tokyo subway"
    assert captured["params"]["per_page"] == 40
    assert captured["params"]["orientation"] == "landscape"
    assert [c.id for c in candidates] == [3129957, 4242424]


def test_select_best_video_file_prefers_smallest_file_at_or_above_target():
    files = [
        VideoFile("sd", "video/mp4", 640, 360, "sd.mp4"),
        VideoFile("hd", "video/mp4", 1920, 1080, "hd.mp4"),
        VideoFile("hd", "video/mp4", 3840, 2160, "4k.mp4"),
    ]
    assert select_best_video_file(files, target_width=1920).link == "hd.mp4"


def test_select_best_video_file_falls_back_to_highest_when_all_below_target():
    files = [
        VideoFile("sd", "video/mp4", 640, 360, "sd.mp4"),
        VideoFile("sd", "video/mp4", 960, 540, "mid.mp4"),
    ]
    assert select_best_video_file(files, target_width=1920).link == "mid.mp4"


def test_select_best_video_file_raises_when_no_mp4_files():
    files = [VideoFile("hd", "video/webm", 1920, 1080, "hd.webm")]
    with pytest.raises(PexelsError, match="no mp4"):
        select_best_video_file(files)
