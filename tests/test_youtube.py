import pytest
from footage.youtube import (
    YouTubeCandidate,
    YouTubeError,
    VideoDetails,
    _parse_iso8601_duration,
    _parse_search_response,
    _parse_subscriber_counts,
    _parse_video_details_response,
    search_youtube,
)
from footage.youtube import _fetch_channel_stats_json as real_fetch_channel_stats

@pytest.fixture(autouse=True)
def small_channels_by_default(monkeypatch):
    """Unless a test says otherwise every channel is small, so no test touches the network."""
    import footage.youtube as youtube_mod

    monkeypatch.setattr(
        youtube_mod, "_fetch_channel_stats_json",
        lambda ids, k: {"items": [_channel_item(i, 5000) for i in ids]},
    )


def _channel_item(channel_id, subscribers, hidden=False):
    stats = {"hiddenSubscriberCount": hidden}
    if not hidden:
        stats["subscriberCount"] = str(subscribers)
    return {"id": channel_id, "statistics": stats}


def _search_item(video_id, channel_id="UC_good1"):
    return {
        "id": {"kind": "youtube#video", "videoId": video_id},
        "snippet": {
            "title": f"Title {video_id}", "channelId": channel_id, "channelTitle": "Chan",
            "thumbnails": {"high": {"url": f"https://img/{video_id}.jpg"}},
        },
    }


SEARCH_RESPONSE = {
    "items": [
        {
            "id": {"kind": "youtube#video", "videoId": "abc123"},
            "snippet": {
                "title": "Tokyo Subway B-Roll 4K", "channelId": "UC_good1",
                "channelTitle": "Free Stock Footage Co", "publishedAt": "2023-01-01T00:00:00Z",
                "thumbnails": {"high": {"url": "https://img/abc123.jpg", "width": 480, "height": 360}},
            },
        },
        {
            "id": {"kind": "youtube#video", "videoId": "excluded1"},
            "snippet": {
                "title": "WSJ: Tokyo Subway Report", "channelId": "UC_wsj",
                "channelTitle": "WSJ", "publishedAt": "2023-01-01T00:00:00Z",
                "thumbnails": {"high": {"url": "https://img/excluded1.jpg", "width": 480, "height": 360}},
            },
        },
    ],
}

def _details_item(video_id, duration, width="1280", height="720"):
    # Real videos.list shape for part=contentDetails,player with maxWidth set: embedWidth and
    # embedHeight come back as strings, alongside embedHtml.
    player = {"embedHtml": f'<iframe width="{width}" height="{height}" ...></iframe>'}
    if width is not None:
        player["embedWidth"] = width
    if height is not None:
        player["embedHeight"] = height
    return {"id": video_id, "contentDetails": {"duration": duration}, "player": player}


DETAILS_RESPONSE = {
    "items": [
        _details_item("abc123", "PT4M13S"),
        _details_item("excluded1", "PT2M0S"),
    ],
}

LANDSCAPE = VideoDetails(duration_seconds=253.0, width=1280, height=720)


def test_parse_iso8601_duration_handles_hours_minutes_seconds():
    assert _parse_iso8601_duration("PT1H2M3S") == 3723.0


def test_parse_iso8601_duration_handles_minutes_and_seconds_only():
    assert _parse_iso8601_duration("PT4M13S") == 253.0


def test_parse_iso8601_duration_handles_seconds_only():
    assert _parse_iso8601_duration("PT45S") == 45.0


def test_parse_iso8601_duration_raises_on_zero_duration():
    with pytest.raises(YouTubeError, match="zero or invalid"):
        _parse_iso8601_duration("PT0S")


def test_parse_iso8601_duration_raises_on_live_stream_format():
    with pytest.raises(YouTubeError, match="could not parse"):
        _parse_iso8601_duration("P0D")


def test_parse_video_details_response_skips_unparseable_durations():
    payload = {"items": [_details_item("good", "PT10S"), _details_item("bad", "P0D")]}
    assert _parse_video_details_response(payload) == {
        "good": VideoDetails(duration_seconds=10.0, width=1280, height=720),
    }


def test_parse_video_details_response_reads_embed_dimensions():
    payload = {"items": [_details_item("short", "PT12S", width="1280", height="2276")]}
    assert _parse_video_details_response(payload) == {
        "short": VideoDetails(duration_seconds=12.0, width=1280, height=2276),
    }


def test_parse_video_details_response_skips_entries_without_usable_dimensions():
    payload = {"items": [
        _details_item("no_height", "PT10S", height=None),
        _details_item("garbage", "PT10S", width="abc"),
        _details_item("zero", "PT10S", height="0"),
        _details_item("good", "PT10S"),
    ]}
    assert list(_parse_video_details_response(payload)) == ["good"]


def test_parse_search_response_excludes_channels_and_attaches_durations():
    candidates = _parse_search_response(
        {"items": [i for i in SEARCH_RESPONSE["items"] if i["snippet"]["channelId"] != "UC_wsj"]},
        details={"abc123": LANDSCAPE},
    )

    assert len(candidates) == 1
    assert candidates[0] == YouTubeCandidate(
        video_id="abc123", title="Tokyo Subway B-Roll 4K", channel_id="UC_good1",
        channel_title="Free Stock Footage Co", thumbnail_url="https://img/abc123.jpg",
        duration_seconds=253.0,
    )


def test_parse_search_response_skips_candidates_with_no_usable_duration():
    candidates = _parse_search_response(SEARCH_RESPONSE, details={"abc123": LANDSCAPE})
    assert [c.video_id for c in candidates] == ["abc123"]  # excluded1 has no entry in details


def test_parse_search_response_drops_portrait_and_square_videos():
    payload = {"items": [
        _search_item("landscape1"), _search_item("short1"), _search_item("square1"),
        _search_item("landscape2"),
    ]}
    details = {
        "landscape1": VideoDetails(30.0, 1280, 720),
        "short1": VideoDetails(12.0, 1280, 2276),  # real embed dims of a 9:16 YouTube Short
        "square1": VideoDetails(20.0, 1280, 1280),
        "landscape2": VideoDetails(90.0, 1280, 960),  # 4:3 is still landscape
    }
    candidates = _parse_search_response(payload, details)
    assert [c.video_id for c in candidates] == ["landscape1", "landscape2"]


def test_search_youtube_filters_excluded_channels_end_to_end(monkeypatch):
    import footage.youtube as youtube_mod

    monkeypatch.setattr(youtube_mod, "_fetch_search_json", lambda q, k, n: SEARCH_RESPONSE)
    monkeypatch.setattr(youtube_mod, "_fetch_video_details_json", lambda ids, k: DETAILS_RESPONSE)

    result = search_youtube(
        "tokyo subway", api_key="fake-key", excluded_channel_ids=frozenset({"UC_wsj"})
    )

    assert [c.video_id for c in result.candidates] == ["abc123"]
    assert result.raw_count == 2
    assert result.excluded_channel_count == 1


def test_search_youtube_never_returns_portrait_videos(monkeypatch):
    import footage.youtube as youtube_mod

    search_payload = {"items": [
        _search_item("short1"), _search_item("landscape1"), _search_item("short2"),
        _search_item("landscape2"),
    ]}
    details_payload = {"items": [
        _details_item("short1", "PT11S", width="1280", height="2276"),
        _details_item("landscape1", "PT1M18S"),
        _details_item("short2", "PT45S", width="1280", height="1600"),
        _details_item("landscape2", "PT30S"),
    ]}
    monkeypatch.setattr(youtube_mod, "_fetch_search_json", lambda q, k, n: search_payload)
    monkeypatch.setattr(youtube_mod, "_fetch_video_details_json", lambda ids, k: details_payload)

    result = search_youtube("q", api_key="fake-key", excluded_channel_ids=frozenset())

    assert [c.video_id for c in result.candidates] == ["landscape1", "landscape2"]
    assert result.non_landscape_count == 2


def test_search_youtube_counts_what_each_filter_removed(monkeypatch):
    import footage.youtube as youtube_mod

    search_payload = {"items": [
        _search_item("blocked", channel_id="UC_wsj"), _search_item("short1"),
        _search_item("live1"), _search_item("good1"),
    ]}
    details_payload = {"items": [
        _details_item("short1", "PT11S", width="1280", height="2276"),
        _details_item("live1", "P0D"),
        _details_item("good1", "PT30S"),
    ]}
    monkeypatch.setattr(youtube_mod, "_fetch_search_json", lambda q, k, n: search_payload)
    monkeypatch.setattr(youtube_mod, "_fetch_video_details_json", lambda ids, k: details_payload)

    result = search_youtube("q", api_key="fake-key", excluded_channel_ids=frozenset({"UC_wsj"}))

    assert [c.video_id for c in result.candidates] == ["good1"]
    assert (result.raw_count, result.excluded_channel_count, result.non_landscape_count,
            result.unusable_count) == (4, 1, 1, 1)


def test_search_youtube_skips_details_call_when_every_result_is_channel_excluded(monkeypatch):
    import footage.youtube as youtube_mod

    monkeypatch.setattr(
        youtube_mod, "_fetch_search_json",
        lambda q, k, n: {"items": [_search_item("x", channel_id="UC_wsj")]},
    )

    def fail_details(ids, k):
        raise AssertionError("should not spend a videos.list call on zero surviving results")

    monkeypatch.setattr(youtube_mod, "_fetch_video_details_json", fail_details)

    result = search_youtube("q", api_key="fake-key", excluded_channel_ids=frozenset({"UC_wsj"}))

    assert result.candidates == []
    assert (result.raw_count, result.excluded_channel_count) == (1, 1)


def test_fetch_video_details_requests_player_dimensions(monkeypatch):
    import footage.youtube as youtube_mod

    captured = {}

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"items": []}

    def fake_get(url, params, timeout):
        captured.update(params)
        return FakeResponse()

    monkeypatch.setattr(youtube_mod.requests, "get", fake_get)
    youtube_mod._fetch_video_details_json(["a", "b"], "fake-key")

    assert set(captured["part"].split(",")) == {"contentDetails", "player"}
    assert captured["maxWidth"] > 0  # without maxWidth/maxHeight, embedWidth/Height are omitted
    assert captured["id"] == "a,b"


def test_search_youtube_raises_youtube_error_on_non_200(monkeypatch):
    import footage.youtube as youtube_mod

    class FakeResponse:
        status_code = 403
        text = "quotaExceeded"

    monkeypatch.setattr(youtube_mod.requests, "get", lambda *a, **kw: FakeResponse())

    with pytest.raises(YouTubeError, match="403"):
        search_youtube("tokyo subway", api_key="bad-key", excluded_channel_ids=frozenset())


def test_parse_subscriber_counts_reads_counts_and_leaves_hidden_ones_out():
    payload = {"items": [
        _channel_item("UC_small", 1200), _channel_item("UC_hidden", 0, hidden=True),
    ]}
    assert _parse_subscriber_counts(payload) == {"UC_small": 1200}


def test_search_youtube_drops_channels_over_one_million_subscribers(monkeypatch):
    import footage.youtube as youtube_mod

    search_payload = {"items": [
        _search_item("big1", channel_id="UC_big"), _search_item("edge1", channel_id="UC_edge"),
        _search_item("hidden1", channel_id="UC_hidden"),
        _search_item("gone1", channel_id="UC_gone"), _search_item("small1", channel_id="UC_small"),
    ]}
    channels_payload = {"items": [
        _channel_item("UC_big", 1_000_001), _channel_item("UC_edge", 1_000_000),
        _channel_item("UC_hidden", 0, hidden=True), _channel_item("UC_small", 40_000),
    ]}  # UC_gone is missing from the response entirely
    asked_for_videos = []

    def fake_details(ids, k):
        asked_for_videos.extend(ids)
        return {"items": [_details_item(i, "PT30S") for i in ids]}

    monkeypatch.setattr(youtube_mod, "_fetch_search_json", lambda q, k, n: search_payload)
    monkeypatch.setattr(youtube_mod, "_fetch_channel_stats_json", lambda ids, k: channels_payload)
    monkeypatch.setattr(youtube_mod, "_fetch_video_details_json", fake_details)

    result = search_youtube("q", api_key="fake-key", excluded_channel_ids=frozenset())

    assert [c.video_id for c in result.candidates] == ["edge1", "small1"]  # exactly 1M stays
    assert asked_for_videos == ["edge1", "small1"]  # no videos.list quota spent on dropped ones
    # Dropped channels count as excluded channels; there is no separate over-1M number.
    assert (result.raw_count, result.excluded_channel_count) == (5, 3)


def test_search_youtube_asks_for_each_channel_once_and_skips_blacklisted_ones(monkeypatch):
    import footage.youtube as youtube_mod

    search_payload = {"items": [
        _search_item("a", channel_id="UC_one"), _search_item("b", channel_id="UC_one"),
        _search_item("c", channel_id="UC_wsj"),
    ]}
    seen = []

    def fake_channels(ids, k):
        seen.append(list(ids))
        return {"items": [_channel_item(i, 10) for i in ids]}

    monkeypatch.setattr(youtube_mod, "_fetch_search_json", lambda q, k, n: search_payload)
    monkeypatch.setattr(youtube_mod, "_fetch_channel_stats_json", fake_channels)
    monkeypatch.setattr(
        youtube_mod, "_fetch_video_details_json",
        lambda ids, k: {"items": [_details_item(i, "PT30S") for i in ids]},
    )

    search_youtube("q", api_key="fake-key", excluded_channel_ids=frozenset({"UC_wsj"}))

    assert seen == [["UC_one"]]


def test_search_youtube_skips_channel_call_when_every_result_is_blacklisted(monkeypatch):
    import footage.youtube as youtube_mod

    monkeypatch.setattr(
        youtube_mod, "_fetch_search_json",
        lambda q, k, n: {"items": [_search_item("x", channel_id="UC_wsj")]},
    )

    def fail_channels(ids, k):
        raise AssertionError("should not spend a channels.list call on zero surviving results")

    monkeypatch.setattr(youtube_mod, "_fetch_channel_stats_json", fail_channels)

    result = search_youtube("q", api_key="fake-key", excluded_channel_ids=frozenset({"UC_wsj"}))
    assert result.candidates == []


def test_fetch_channel_stats_requests_statistics_for_the_given_channels(monkeypatch):
    import footage.youtube as youtube_mod

    captured = {}

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"items": []}

    def fake_get(url, params, timeout):
        captured["url"] = url
        captured.update(params)
        return FakeResponse()

    monkeypatch.setattr(youtube_mod.requests, "get", fake_get)
    real_fetch_channel_stats(["UC_a", "UC_b"], "fake-key")

    assert captured["url"].endswith("/youtube/v3/channels")
    assert captured["part"] == "statistics"
    assert captured["id"] == "UC_a,UC_b"
    assert captured["maxResults"] == 50


def test_fetch_channel_stats_raises_youtube_error_on_non_200(monkeypatch):
    import footage.youtube as youtube_mod

    class FakeResponse:
        status_code = 403
        text = "quotaExceeded"

    monkeypatch.setattr(youtube_mod.requests, "get", lambda *a, **kw: FakeResponse())

    with pytest.raises(YouTubeError, match="403"):
        real_fetch_channel_stats(["UC_a"], "fake-key")
