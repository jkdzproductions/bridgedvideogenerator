import pytest
from footage.youtube_channels import (
    EXCLUDED_CHANNEL_URLS,
    ChannelResolutionError,
    extract_handle,
    resolve_channel_ids,
)


def test_excluded_channel_urls_has_all_eight_channels():
    assert len(EXCLUDED_CHANNEL_URLS) == 10
    assert "https://www.youtube.com/@wsj" in EXCLUDED_CHANNEL_URLS
    assert "https://www.youtube.com/@Survivethejive" in EXCLUDED_CHANNEL_URLS


def test_extract_handle_parses_simple_url():
    assert extract_handle("https://www.youtube.com/@CNN") == "CNN"


def test_extract_handle_parses_url_with_trailing_path():
    assert extract_handle("https://www.youtube.com/@BBC/videos") == "BBC"


def test_extract_handle_raises_when_no_handle_in_url():
    with pytest.raises(ChannelResolutionError, match="could not extract"):
        extract_handle("https://www.youtube.com/channel/UC12345")


def test_resolve_channel_ids_returns_ids_for_all_handles(monkeypatch):
    import footage.youtube_channels as ch_mod

    def fake_fetch(handle, api_key):
        return {"items": [{"id": f"UC_{handle}"}]}

    monkeypatch.setattr(ch_mod, "_fetch_channel_json", fake_fetch)

    result = resolve_channel_ids(["https://www.youtube.com/@wsj", "https://www.youtube.com/@CNN"], "key")

    assert result == frozenset({"UC_wsj", "UC_CNN"})


def test_resolve_channel_ids_raises_when_a_handle_is_not_found(monkeypatch):
    import footage.youtube_channels as ch_mod

    def fake_fetch(handle, api_key):
        return {"items": []}

    monkeypatch.setattr(ch_mod, "_fetch_channel_json", fake_fetch)

    with pytest.raises(ChannelResolutionError, match="no YouTube channel found"):
        resolve_channel_ids(["https://www.youtube.com/@wsj"], "key")


def test_resolve_channel_ids_raises_on_api_error(monkeypatch):
    import footage.youtube_channels as ch_mod

    class FakeResponse:
        status_code = 403
        text = "quotaExceeded"

    monkeypatch.setattr(ch_mod.requests, "get", lambda *a, **kw: FakeResponse())

    with pytest.raises(ChannelResolutionError, match="403"):
        resolve_channel_ids(["https://www.youtube.com/@wsj"], "key")
