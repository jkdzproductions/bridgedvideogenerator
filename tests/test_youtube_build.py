import pytest

from footage.youtube import YouTubeCandidate, YouTubeSearchResult
from footage.youtube_build import prepare_youtube_scoring, resolve_youtube_winner


def _candidate(video_id: str, duration: float = 60.0) -> YouTubeCandidate:
    return YouTubeCandidate(video_id, f"Title {video_id}", "UC1", "Channel", f"{video_id}.jpg", duration)


def _result(candidates, raw_count=None, excluded_channel_count=0, non_landscape_count=0,
            unusable_count=0) -> YouTubeSearchResult:
    if raw_count is None:
        raw_count = len(candidates) + excluded_channel_count + non_landscape_count + unusable_count
    return YouTubeSearchResult(
        candidates=candidates, raw_count=raw_count, excluded_channel_count=excluded_channel_count,
        non_landscape_count=non_landscape_count, unusable_count=unusable_count,
    )


def _fake_thumbnails(monkeypatch):
    import footage.youtube_build as build_mod

    monkeypatch.setattr(
        build_mod, "download_youtube_thumbnails",
        lambda candidates, out_dir: {c.video_id: f"{out_dir}/{c.video_id}.jpg" for c in candidates},
    )


def _fake_search(monkeypatch, result, captured=None):
    import footage.youtube_build as build_mod

    def fake_search(query, api_key, excluded_channel_ids, max_results):
        if captured is not None:
            captured["max_results"] = max_results
        return result

    monkeypatch.setattr(build_mod, "search_youtube", fake_search)


def test_prepare_youtube_scoring_returns_candidates_and_prompt(tmp_path, monkeypatch):
    fake_candidates = [_candidate("a"), _candidate("b")]
    _fake_search(monkeypatch, _result(fake_candidates))
    _fake_thumbnails(monkeypatch)

    candidates, prompt = prepare_youtube_scoring(
        query="tokyo subway", subject="Tokyo's subway system", api_key="fake-key",
        excluded_channel_ids=frozenset(), thumbnails_dir=str(tmp_path),
    )

    assert candidates == fake_candidates
    assert "Tokyo's subway system" in prompt


def test_prepare_youtube_scoring_always_searches_a_full_page(tmp_path, monkeypatch):
    # search.list costs 100 units regardless of maxResults, so there's no reason to ask for
    # fewer — even with no used-video exclusions.
    import footage.youtube_build as build_mod

    captured = {}
    _fake_search(monkeypatch, _result([_candidate(str(i)) for i in range(20)]), captured)
    _fake_thumbnails(monkeypatch)

    candidates, _ = prepare_youtube_scoring(
        query="q", subject="s", api_key="fake-key", excluded_channel_ids=frozenset(),
        thumbnails_dir=str(tmp_path),
    )

    assert captured["max_results"] == build_mod.YOUTUBE_MAX_PER_PAGE
    assert len(candidates) == 7  # still only the top max_results reach the scorer


def test_prepare_youtube_scoring_filters_excluded_video_ids(tmp_path, monkeypatch):
    _fake_search(monkeypatch, _result([_candidate("used1"), _candidate("used2"), _candidate("fresh1")]))
    _fake_thumbnails(monkeypatch)

    candidates, _ = prepare_youtube_scoring(
        query="q", subject="s", api_key="fake-key", excluded_channel_ids=frozenset(),
        thumbnails_dir=str(tmp_path), exclude_video_ids=frozenset({"used1", "used2"}),
    )

    assert [c.video_id for c in candidates] == ["fresh1"]


def _empty_pool_error(tmp_path, monkeypatch, result, exclude_video_ids=frozenset()) -> str:
    _fake_search(monkeypatch, result)
    with pytest.raises(ValueError) as exc_info:
        prepare_youtube_scoring(
            query="q", subject="s", api_key="fake-key", excluded_channel_ids=frozenset({"UC_x"}),
            thumbnails_dir=str(tmp_path), exclude_video_ids=exclude_video_ids,
        )
    message = str(exc_info.value)
    assert message.startswith("no YouTube candidates found for query: 'q'")
    return message


def test_prepare_youtube_scoring_attributes_empty_pool_to_zero_raw_results(tmp_path, monkeypatch):
    message = _empty_pool_error(tmp_path, monkeypatch, _result([], raw_count=0))
    assert "search returned zero results" in message
    assert "excluded channel" not in message.split("(")[0]


def test_prepare_youtube_scoring_attributes_empty_pool_to_channel_exclusion(tmp_path, monkeypatch):
    message = _empty_pool_error(tmp_path, monkeypatch, _result([], excluded_channel_count=4))
    assert "all 4 result(s) were from excluded channels" in message


def test_prepare_youtube_scoring_attributes_empty_pool_to_portrait_or_unusable(tmp_path, monkeypatch):
    message = _empty_pool_error(
        tmp_path, monkeypatch,
        _result([], excluded_channel_count=1, non_landscape_count=3, unusable_count=1),
    )
    assert "portrait/square or had no usable duration/dimensions" in message
    assert "3 portrait/square" in message


def test_prepare_youtube_scoring_attributes_empty_pool_to_used_video_exclusion(tmp_path, monkeypatch):
    message = _empty_pool_error(
        tmp_path, monkeypatch,
        _result([_candidate("used1"), _candidate("used2")], excluded_channel_count=2),
        exclude_video_ids=frozenset({"used1", "used2", "unrelated"}),
    )
    assert "all 2 remaining result(s) were already used by earlier beats" in message


def test_resolve_youtube_winner_clamps_to_the_videos_real_duration(monkeypatch):
    import footage.youtube_build as build_mod

    calls = []
    monkeypatch.setattr(
        build_mod, "download_youtube_clip",
        lambda video_id, dest_path, duration_seconds: calls.append(
            (video_id, dest_path, duration_seconds)
        ) or dest_path,
    )
    monkeypatch.setattr(build_mod, "probe_video_dimensions", lambda path: (640, 360))

    candidates = [_candidate("short_clip", duration=8.0)]

    result = resolve_youtube_winner(candidates, winner_index=0, dest_path="/tmp/beat_0.mp4", target_duration=10.0)

    assert result == "/tmp/beat_0.mp4"
    assert calls == [("short_clip", "/tmp/beat_0.mp4", 8.0)]  # clamped to the video's real 8s, not 10s


def test_resolve_youtube_winner_rejects_and_deletes_a_downloaded_portrait_clip(tmp_path, monkeypatch):
    import footage.youtube_build as build_mod
    import pytest
    from footage.youtube_download import PortraitVideoError, YouTubeDownloadError

    dest = tmp_path / "beat_0.mp4"

    def fake_download(video_id, dest_path, duration_seconds):
        open(dest_path, "wb").write(b"portrait clip")
        return dest_path

    monkeypatch.setattr(build_mod, "download_youtube_clip", fake_download)
    monkeypatch.setattr(build_mod, "probe_video_dimensions", lambda path: (360, 640))

    with pytest.raises(PortraitVideoError, match="360x640"):
        resolve_youtube_winner([_candidate("short1")], 0, str(dest), target_duration=5.0)

    # Must not leave the bad clip behind where a resumed run would treat the beat as sourced.
    assert not dest.exists()
    assert issubclass(PortraitVideoError, YouTubeDownloadError)  # Step 2d's STOP rule covers it


def test_resolve_youtube_winner_rejects_a_square_clip(tmp_path, monkeypatch):
    import footage.youtube_build as build_mod
    import pytest
    from footage.youtube_download import PortraitVideoError

    monkeypatch.setattr(
        build_mod, "download_youtube_clip",
        lambda video_id, dest_path, duration_seconds: open(dest_path, "wb").write(b"x") and dest_path,
    )
    monkeypatch.setattr(build_mod, "probe_video_dimensions", lambda path: (480, 480))

    with pytest.raises(PortraitVideoError):
        resolve_youtube_winner([_candidate("sq")], 0, str(tmp_path / "b.mp4"), target_duration=5.0)


def test_resolve_youtube_winner_deletes_the_clip_if_it_cannot_be_probed(tmp_path, monkeypatch):
    import footage.youtube_build as build_mod
    import pytest
    from footage.youtube_download import YouTubeDownloadError

    dest = tmp_path / "beat_0.mp4"

    def fake_download(video_id, dest_path, duration_seconds):
        open(dest_path, "wb").write(b"unreadable")
        return dest_path

    def failing_probe(path):
        raise YouTubeDownloadError("ffprobe failed on it")

    monkeypatch.setattr(build_mod, "download_youtube_clip", fake_download)
    monkeypatch.setattr(build_mod, "probe_video_dimensions", failing_probe)

    with pytest.raises(YouTubeDownloadError, match="ffprobe failed"):
        resolve_youtube_winner([_candidate("x")], 0, str(dest), target_duration=5.0)

    assert not dest.exists()  # an unverified clip must not look like a sourced beat
