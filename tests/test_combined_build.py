# tests/test_combined_build.py
import os

import pytest

from footage.combined_build import (
    CombinedCandidate,
    prepare_combined_scoring,
    resolve_combined_winner,
)
from footage.envato import EnvatoCandidate, EnvatoCandidateDetails, EnvatoError
from footage.pexels import PexelsCandidate, VideoFile
from footage.youtube import YouTubeCandidate, YouTubeSearchResult
from footage.youtube_download import PortraitVideoError

ENVATO_PROFILE_DIR = "/fake/envato/profile"


def _pexels(id_, duration=10, width=1920, height=1080):
    return PexelsCandidate(id_, f"url{id_}", f"thumb{id_}.jpg", duration, width, height, [
        VideoFile("hd", "video/mp4", width, height, f"{id_}.mp4"),
    ])


def _youtube(video_id, duration=60.0):
    return YouTubeCandidate(video_id, f"Title {video_id}", "UC1", "Channel", f"{video_id}.jpg", duration)


def _envato(item_id, title=None, author="Author"):
    return EnvatoCandidate(
        item_id=item_id,
        title=title or f"Envato {item_id}",
        thumbnail_url=f"thumb{item_id}.jpg",
        author=author,
        detail_url=f"https://app.envato.com/item/{item_id}",
    )


def _search_result(candidates):
    return YouTubeSearchResult(candidates, len(candidates), 0, 0, 0)


def _envato_details_for(candidates, duration=15.0, width=1920, height=1080):
    return {c.item_id: EnvatoCandidateDetails(duration, width, height) for c in candidates}


def _patch(monkeypatch, pexels_results, youtube_result, envato_results=None):
    import footage.combined_build as combined_mod

    envato_results = [] if envato_results is None else envato_results

    monkeypatch.setattr(combined_mod, "search_pexels", lambda query, api_key, per_page: pexels_results)
    monkeypatch.setattr(
        combined_mod, "download_thumbnails",
        lambda candidates, out_dir: {c.id: f"{out_dir}/pexels_{c.id}.jpg" for c in candidates},
    )
    monkeypatch.setattr(
        combined_mod, "search_youtube",
        lambda query, api_key, excluded_channel_ids, max_results: youtube_result,
    )
    monkeypatch.setattr(
        combined_mod, "download_youtube_thumbnails",
        lambda candidates, out_dir: {c.video_id: f"{out_dir}/youtube_{c.video_id}.jpg" for c in candidates},
    )
    monkeypatch.setattr(
        combined_mod, "search_envato",
        # Mirrors real search_envato's own exclude_ids filtering (done inside search_envato
        # itself, not by the caller) so the cross-beat-exclusion test actually exercises it.
        lambda query, exclude_ids, profile_dir, max_results: [
            c for c in envato_results if c.item_id not in exclude_ids
        ][:max_results],
    )
    monkeypatch.setattr(
        combined_mod, "fetch_envato_details",
        lambda candidates, profile_dir: _envato_details_for(candidates),
    )
    monkeypatch.setattr(
        combined_mod, "download_thumbnails_from_urls",
        lambda urls_by_id, out_dir: {item_id: f"{out_dir}/envato_{item_id}.jpg" for item_id in urls_by_id},
    )


def test_prepare_combined_scoring_returns_candidates_from_both_sources(tmp_path, monkeypatch):
    _patch(monkeypatch, [_pexels(1), _pexels(2)], _search_result([_youtube("a"), _youtube("b")]))

    candidates, prompt = prepare_combined_scoring(
        query="tokyo subway", subject="Tokyo's subway system",
        pexels_api_key="pk", youtube_api_key="yk", excluded_channel_ids=frozenset(),
        thumbnails_dir=str(tmp_path), envato_profile_dir=ENVATO_PROFILE_DIR,
    )

    assert [c.source for c in candidates] == ["pexels", "pexels", "youtube", "youtube"]
    assert [c.display_id for c in candidates] == ["1", "2", "a", "b"]
    assert "Tokyo's subway system" in prompt
    assert "source=pexels" in prompt
    assert "source=youtube" in prompt


def test_prepare_combined_scoring_truncates_to_the_fixed_split(tmp_path, monkeypatch):
    pexels_results = [_pexels(i) for i in range(1, 10)]
    youtube_results = _search_result([_youtube(str(i)) for i in range(10)])
    envato_results = [_envato(f"e{i}") for i in range(5)]
    _patch(monkeypatch, pexels_results, youtube_results, envato_results=envato_results)

    candidates, _ = prepare_combined_scoring(
        query="q", subject="s", pexels_api_key="pk", youtube_api_key="yk",
        excluded_channel_ids=frozenset(), thumbnails_dir=str(tmp_path),
        envato_profile_dir=ENVATO_PROFILE_DIR,
    )

    pexels_ids = [c.display_id for c in candidates if c.source == "pexels"]
    youtube_ids = [c.display_id for c in candidates if c.source == "youtube"]
    envato_ids = [c.display_id for c in candidates if c.source == "envato"]
    assert pexels_ids == ["1", "2", "3", "4"]
    assert youtube_ids == ["0", "1", "2"]
    assert envato_ids == ["e0", "e1", "e2"]


def test_prepare_combined_scoring_excludes_already_used_ids_per_source(tmp_path, monkeypatch):
    _patch(
        monkeypatch,
        [_pexels(1), _pexels(2), _pexels(3)],
        _search_result([_youtube("a"), _youtube("b")]),
    )

    candidates, _ = prepare_combined_scoring(
        query="q", subject="s", pexels_api_key="pk", youtube_api_key="yk",
        excluded_channel_ids=frozenset(), thumbnails_dir=str(tmp_path),
        envato_profile_dir=ENVATO_PROFILE_DIR,
        exclude_ids=frozenset({("pexels", "1"), ("youtube", "a")}),
    )

    assert [c.display_id for c in candidates] == ["2", "3", "b"]


def test_prepare_combined_scoring_raises_when_both_sources_have_nothing(tmp_path, monkeypatch):
    _patch(monkeypatch, [], _search_result([]))

    with pytest.raises(ValueError, match="no candidates found"):
        prepare_combined_scoring(
            query="q", subject="s", pexels_api_key="pk", youtube_api_key="yk",
            excluded_channel_ids=frozenset(), thumbnails_dir=str(tmp_path),
            envato_profile_dir=ENVATO_PROFILE_DIR,
        )


def test_prepare_combined_scoring_succeeds_when_only_one_source_has_candidates(tmp_path, monkeypatch):
    _patch(monkeypatch, [_pexels(1)], _search_result([]))

    candidates, _ = prepare_combined_scoring(
        query="q", subject="s", pexels_api_key="pk", youtube_api_key="yk",
        excluded_channel_ids=frozenset(), thumbnails_dir=str(tmp_path),
        envato_profile_dir=ENVATO_PROFILE_DIR,
    )

    assert [c.source for c in candidates] == ["pexels"]


def test_resolve_combined_winner_downloads_from_pexels_when_pexels_wins(tmp_path, monkeypatch):
    import footage.combined_build as combined_mod

    calls = []
    monkeypatch.setattr(
        combined_mod, "download_winning_video",
        lambda candidate, dest_path, **kw: calls.append((candidate.id, dest_path)) or dest_path,
    )

    winner = CombinedCandidate("pexels", "1", "thumb.jpg", _pexels(1))
    dest = str(tmp_path / "beat_0.mp4")

    result = resolve_combined_winner(
        [winner], 0, dest, target_duration=10.0, envato_profile_dir=ENVATO_PROFILE_DIR,
    )

    assert result == dest
    assert calls == [(1, dest)]


def test_resolve_combined_winner_removes_stale_pexels_file_before_downloading(tmp_path, monkeypatch):
    import footage.combined_build as combined_mod

    dest = tmp_path / "beat_0.mp4"
    dest.write_bytes(b"stale content from a previous video/attempt")

    def fake_download(candidate, dest_path, **kw):
        open(dest_path, "wb").write(b"fresh content")
        return dest_path

    monkeypatch.setattr(combined_mod, "download_winning_video", fake_download)

    winner = CombinedCandidate("pexels", "1", "thumb.jpg", _pexels(1))

    result = resolve_combined_winner(
        [winner], 0, str(dest), target_duration=10.0, envato_profile_dir=ENVATO_PROFILE_DIR,
    )

    assert result == str(dest)
    assert dest.read_bytes() == b"fresh content"


def test_resolve_combined_winner_removes_partial_pexels_file_on_download_failure(tmp_path, monkeypatch):
    import footage.combined_build as combined_mod

    dest = tmp_path / "beat_0.mp4"

    def fake_download(candidate, dest_path, **kw):
        # simulate download_file's "wb" truncate-then-write-partial-chunks-then-fail behavior
        open(dest_path, "wb").write(b"partial")
        raise RuntimeError("network error mid-stream")

    monkeypatch.setattr(combined_mod, "download_winning_video", fake_download)

    winner = CombinedCandidate("pexels", "1", "thumb.jpg", _pexels(1))

    with pytest.raises(RuntimeError, match="network error mid-stream"):
        resolve_combined_winner(
            [winner], 0, str(dest), target_duration=10.0, envato_profile_dir=ENVATO_PROFILE_DIR,
        )

    assert not dest.exists()  # no partial file left behind that could look like a real clip


def test_resolve_combined_winner_downloads_and_clamps_from_youtube_when_youtube_wins(tmp_path, monkeypatch):
    import footage.combined_build as combined_mod

    calls = []
    monkeypatch.setattr(
        combined_mod, "download_youtube_clip",
        lambda video_id, dest_path, duration_seconds: calls.append(
            (video_id, dest_path, duration_seconds)
        ) or dest_path,
    )
    monkeypatch.setattr(combined_mod, "probe_video_dimensions", lambda path: (1920, 1080))
    looked = []
    monkeypatch.setattr(combined_mod, "apply_youtube_look", lambda p: looked.append(p) or p)

    winner = CombinedCandidate("youtube", "a", "thumb.jpg", _youtube("a", duration=8.0))
    dest = str(tmp_path / "beat_0.mp4")

    result = resolve_combined_winner(
        [winner], 0, dest, target_duration=10.0, envato_profile_dir=ENVATO_PROFILE_DIR,
    )

    assert result == dest
    assert calls == [("a", dest, 8.0)]  # clamped to the video's real 8s, not the beat's 10s
    assert looked == [dest]  # mirrored, zoomed and grained after the download


def test_resolve_combined_winner_leaves_pexels_clips_untouched(tmp_path, monkeypatch):
    import footage.combined_build as combined_mod

    monkeypatch.setattr(
        combined_mod, "download_winning_video", lambda candidate, dest_path, **kw: dest_path
    )

    def fail(path):
        raise AssertionError("only YouTube clips get the mirrored look")

    monkeypatch.setattr(combined_mod, "apply_youtube_look", fail)

    winner = CombinedCandidate("pexels", "1", "thumb.jpg", _pexels(1))
    dest = str(tmp_path / "beat_0.mp4")
    assert resolve_combined_winner(
        [winner], 0, dest, target_duration=10.0, envato_profile_dir=ENVATO_PROFILE_DIR
    ) == dest


def test_resolve_combined_winner_leaves_envato_clips_untouched(tmp_path, monkeypatch):
    import footage.combined_build as combined_mod

    monkeypatch.setattr(
        combined_mod, "download_envato_clip", lambda payload, dest_path, **kw: dest_path
    )
    monkeypatch.setattr(combined_mod, "probe_video_dimensions", lambda path: (1920, 1080))

    def fail(path):
        raise AssertionError("only YouTube clips get the mirrored look")

    monkeypatch.setattr(combined_mod, "apply_youtube_look", fail)

    winner = CombinedCandidate("envato", "e1", "thumb.jpg", _envato("e1"))
    dest = str(tmp_path / "beat_0.mp4")
    assert resolve_combined_winner(
        [winner], 0, dest, target_duration=10.0, envato_profile_dir=ENVATO_PROFILE_DIR
    ) == dest


def test_resolve_combined_winner_rejects_and_deletes_a_portrait_youtube_clip(tmp_path, monkeypatch):
    import footage.combined_build as combined_mod

    dest = tmp_path / "beat_0.mp4"

    def fake_download(video_id, dest_path, duration_seconds):
        open(dest_path, "wb").write(b"portrait")
        return dest_path

    monkeypatch.setattr(combined_mod, "download_youtube_clip", fake_download)
    monkeypatch.setattr(combined_mod, "probe_video_dimensions", lambda path: (360, 640))

    winner = CombinedCandidate("youtube", "a", "thumb.jpg", _youtube("a"))

    with pytest.raises(PortraitVideoError, match="360x640"):
        resolve_combined_winner(
            [winner], 0, str(dest), target_duration=5.0, envato_profile_dir=ENVATO_PROFILE_DIR,
        )

    assert not dest.exists()  # a bad clip must not look like a sourced beat on resume


def test_prepare_combined_scoring_includes_envato_candidates(tmp_path, monkeypatch):
    _patch(
        monkeypatch, [_pexels(1)], _search_result([_youtube("a")]),
        envato_results=[_envato("e1")],
    )

    candidates, prompt = prepare_combined_scoring(
        query="tokyo subway", subject="Tokyo's subway system",
        pexels_api_key="pk", youtube_api_key="yk", excluded_channel_ids=frozenset(),
        thumbnails_dir=str(tmp_path), envato_profile_dir=ENVATO_PROFILE_DIR,
    )

    envato_candidates = [c for c in candidates if c.source == "envato"]
    assert len(envato_candidates) == 1
    assert isinstance(envato_candidates[0].payload, EnvatoCandidate)
    assert "source=envato" in prompt


def test_combined_split_totals_ten_with_three_sources():
    # The per-beat pool is 10 candidates across the three sources.
    from footage.combined_build import ENVATO_SPLIT, PEXELS_SPLIT, YOUTUBE_SPLIT

    assert PEXELS_SPLIT + YOUTUBE_SPLIT + ENVATO_SPLIT == 10


def test_scoring_prompt_rejects_title_cards_and_wrong_country():
    from footage.combined_build import build_combined_scoring_prompt

    prompt = build_combined_scoring_prompt("q", "Costa Rica churches", [])
    assert "title card" in prompt
    assert "different country" in prompt


def test_envato_candidates_excluded_by_prior_beat_usage(tmp_path, monkeypatch):
    _patch(
        monkeypatch, [], _search_result([]),
        envato_results=[_envato("e1"), _envato("e2")],
    )

    candidates, _ = prepare_combined_scoring(
        query="q", subject="s", pexels_api_key="pk", youtube_api_key="yk",
        excluded_channel_ids=frozenset(), thumbnails_dir=str(tmp_path),
        envato_profile_dir=ENVATO_PROFILE_DIR,
        exclude_ids=frozenset({("envato", "e1")}),
    )

    envato_ids = [c.display_id for c in candidates if c.source == "envato"]
    assert envato_ids == ["e2"]


def test_scoring_prompt_includes_envato_candidate_lines(tmp_path, monkeypatch):
    _patch(monkeypatch, [], _search_result([]), envato_results=[_envato("e1", author="Acme")])

    candidates, prompt = prepare_combined_scoring(
        query="q", subject="s", pexels_api_key="pk", youtube_api_key="yk",
        excluded_channel_ids=frozenset(), thumbnails_dir=str(tmp_path),
        envato_profile_dir=ENVATO_PROFILE_DIR,
    )

    envato_candidate = next(c for c in candidates if c.source == "envato")
    assert 'source=envato title="Envato e1" author="Acme"' in prompt
    assert "duration=15s" in prompt
    assert envato_candidate.thumbnail_path in prompt


def test_one_source_failing_does_not_block_the_others(tmp_path, monkeypatch):
    import footage.combined_build as combined_mod

    _patch(monkeypatch, [_pexels(1)], _search_result([_youtube("a")]))

    def raise_envato_error(query, exclude_ids, profile_dir, max_results):
        raise EnvatoError("landed on a login page — the Envato session has expired")

    monkeypatch.setattr(combined_mod, "search_envato", raise_envato_error)

    candidates, _ = prepare_combined_scoring(
        query="q", subject="s", pexels_api_key="pk", youtube_api_key="yk",
        excluded_channel_ids=frozenset(), thumbnails_dir=str(tmp_path),
        envato_profile_dir=ENVATO_PROFILE_DIR,
    )

    assert [c.source for c in candidates] == ["pexels", "youtube"]


def test_resolve_combined_winner_rejects_portrait_envato_video(tmp_path, monkeypatch):
    import footage.combined_build as combined_mod

    dest = tmp_path / "beat_0.mp4"

    def fake_download(candidate, dest_path, target_duration_seconds, profile_dir):
        open(dest_path, "wb").write(b"portrait")
        return dest_path

    monkeypatch.setattr(combined_mod, "download_envato_clip", fake_download)
    monkeypatch.setattr(combined_mod, "probe_video_dimensions", lambda path: (360, 640))

    winner = CombinedCandidate("envato", "e1", "thumb.jpg", _envato("e1"))

    with pytest.raises(PortraitVideoError, match="360x640"):
        resolve_combined_winner(
            [winner], 0, str(dest), target_duration=5.0, envato_profile_dir=ENVATO_PROFILE_DIR,
        )

    assert not dest.exists()  # a bad clip must not look like a sourced beat on resume


def test_resolve_combined_winner_cleans_up_dest_when_envato_download_fails(tmp_path, monkeypatch):
    # C2: a failed Envato download/trim must not leave a stale or partial file at dest_path —
    # Stage 2's resume logic treats any existing footage_output/beat_<n>.mp4 as a finished beat.
    import footage.combined_build as combined_mod
    from footage.envato_download import EnvatoDownloadError

    dest = tmp_path / "beat_0.mp4"
    dest.write_bytes(b"stale leftover from an earlier interrupted run")

    def fake_download(candidate, dest_path, target_duration_seconds, profile_dir):
        # What a real failed ffmpeg trim leaves behind: a 0-byte output file, then a raise.
        assert not os.path.exists(dest_path), "stale dest_path should be removed before downloading"
        open(dest_path, "wb").close()
        raise EnvatoDownloadError("ffmpeg trim failed: Could not write header")

    monkeypatch.setattr(combined_mod, "download_envato_clip", fake_download)
    winner = CombinedCandidate("envato", "e1", "thumb.jpg", _envato("e1"))

    with pytest.raises(EnvatoDownloadError, match="Could not write header"):
        resolve_combined_winner(
            [winner], 0, str(dest), target_duration=5.0, envato_profile_dir=ENVATO_PROFILE_DIR,
        )

    assert not dest.exists()


def test_playwright_error_in_envato_does_not_block_the_others_and_warns(tmp_path, monkeypatch, capsys):
    # I2: a real Playwright failure (timeout, locked profile) is additive-source trouble, not a
    # reason to STOP the beat — and I1: it must be visibly reported, not silently swallowed.
    import footage.combined_build as combined_mod
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

    _patch(monkeypatch, [_pexels(1)], _search_result([_youtube("a")]))

    def raise_playwright_error(query, exclude_ids, profile_dir, max_results):
        raise PlaywrightTimeoutError("Timeout 30000ms exceeded")

    monkeypatch.setattr(combined_mod, "search_envato", raise_playwright_error)

    candidates, _ = prepare_combined_scoring(
        query="q", subject="s", pexels_api_key="pk", youtube_api_key="yk",
        excluded_channel_ids=frozenset(), thumbnails_dir=str(tmp_path),
        envato_profile_dir=ENVATO_PROFILE_DIR,
    )

    assert [c.source for c in candidates] == ["pexels", "youtube"]
    out = capsys.readouterr().out
    assert "WARNING" in out and "Envato" in out and "Timeout 30000ms exceeded" in out


def test_envato_error_is_reported_visibly(tmp_path, monkeypatch, capsys):
    import footage.combined_build as combined_mod

    _patch(monkeypatch, [_pexels(1)], _search_result([]))

    def raise_envato_error(query, exclude_ids, profile_dir, max_results):
        raise EnvatoError("landed on Envato's sign-in page")

    monkeypatch.setattr(combined_mod, "search_envato", raise_envato_error)

    prepare_combined_scoring(
        query="q", subject="s", pexels_api_key="pk", youtube_api_key="yk",
        excluded_channel_ids=frozenset(), thumbnails_dir=str(tmp_path),
        envato_profile_dir=ENVATO_PROFILE_DIR,
    )

    out = capsys.readouterr().out
    assert "WARNING" in out and "landed on Envato's sign-in page" in out


def test_portrait_and_square_envato_candidates_dropped_before_scoring(tmp_path, monkeypatch):
    # I4: Envato search has no orientation URL filter — portrait/square items must be dropped
    # using fetch_envato_details' width/height before scoring, not after a multi-GB download.
    import footage.combined_build as combined_mod

    _patch(
        monkeypatch, [], _search_result([]),
        envato_results=[_envato("wide"), _envato("tall"), _envato("square")],
    )
    dims = {"wide": (1920, 1080), "tall": (1080, 1920), "square": (1080, 1080)}
    monkeypatch.setattr(combined_mod, "ENVATO_SPLIT", 3)
    monkeypatch.setattr(
        combined_mod, "fetch_envato_details",
        lambda candidates, profile_dir: {
            c.item_id: EnvatoCandidateDetails(15.0, *dims[c.item_id]) for c in candidates
        },
    )

    candidates, prompt = prepare_combined_scoring(
        query="q", subject="s", pexels_api_key="pk", youtube_api_key="yk",
        excluded_channel_ids=frozenset(), thumbnails_dir=str(tmp_path),
        envato_profile_dir=ENVATO_PROFILE_DIR,
    )

    assert [c.display_id for c in candidates] == ["wide"]
    assert "Envato tall" not in prompt and "Envato square" not in prompt


def test_scoring_prompt_rejects_clips_with_burned_in_text_signs_and_logos():
    # a "Welcome to Naval Station Norfolk" sign and an NBC News banner both won a beat once
    from footage.combined_build import build_combined_scoring_prompt

    prompt = build_combined_scoring_prompt("q", "A navy carrier at Norfolk", [])
    lowered = prompt.lower()
    assert "news" in lowered and "banner" in lowered
    assert "logo" in lowered and "watermark" in lowered
    assert "sign" in lowered
    assert "unless the subject itself is" in lowered


def test_scoring_prompt_rejects_any_readable_text_on_youtube_candidates():
    # YouTube clips are mirrored, so even small background text would show up reversed
    from footage.combined_build import build_combined_scoring_prompt

    prompt = build_combined_scoring_prompt("q", "A container port", [])
    lowered = prompt.lower()
    assert 'for a "source=youtube" candidate the rule above is stricter' in lowered
    assert "mirrored" in lowered and "any readable text" in lowered


def test_envato_browser_work_never_overlaps_across_threads(tmp_path, monkeypatch):
    """Batch prep runs beats in a thread pool, but every Envato call opens the SAME persistent Chromium profile,
    which two browsers cannot share: the Envato part of each beat must run one at a time."""
    import threading
    import time as _time

    import footage.combined_build as combined_mod

    _patch(monkeypatch, [_pexels(1)], _search_result([]), envato_results=[_envato("e1")])
    active, peak, guard = [0], [0], threading.Lock()

    def slow_search(query, exclude_ids, profile_dir, max_results):
        with guard:
            active[0] += 1
            peak[0] = max(peak[0], active[0])
        _time.sleep(0.05)
        with guard:
            active[0] -= 1
        return [_envato("e1")]

    monkeypatch.setattr(combined_mod, "search_envato", slow_search)
    threads = [
        threading.Thread(target=prepare_combined_scoring, kwargs=dict(
            query="q", subject="s", pexels_api_key="k", youtube_api_key="k", excluded_channel_ids=frozenset(),
            thumbnails_dir=str(tmp_path / f"beat_{i}"), envato_profile_dir=ENVATO_PROFILE_DIR))
        for i in range(4)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert peak[0] == 1
