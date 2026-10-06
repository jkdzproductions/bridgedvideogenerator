from footage.build import prepare_footage_scoring, resolve_footage_winner
from footage.pexels import PexelsCandidate, VideoFile


def test_prepare_footage_scoring_returns_candidates_and_prompt(tmp_path, monkeypatch):
    import footage.build as build_mod

    fake_candidates = [
        PexelsCandidate(1, "url1", "thumb1.jpg", 10, 1920, 1080, []),
        PexelsCandidate(2, "url2", "thumb2.jpg", 10, 1280, 720, []),
    ]
    monkeypatch.setattr(build_mod, "search_pexels", lambda query, api_key, per_page: fake_candidates)
    monkeypatch.setattr(
        build_mod, "download_thumbnails",
        lambda candidates, out_dir: {c.id: f"{out_dir}/{c.id}.jpg" for c in candidates},
    )

    candidates, prompt = prepare_footage_scoring(
        query="tokyo subway", subject="Tokyo's subway system",
        api_key="fake-key", thumbnails_dir=str(tmp_path),
    )

    assert candidates == fake_candidates
    assert "Tokyo's subway system" in prompt
    assert str(tmp_path) in prompt


def test_prepare_footage_scoring_raises_on_no_candidates(tmp_path, monkeypatch):
    import footage.build as build_mod
    import pytest

    monkeypatch.setattr(build_mod, "search_pexels", lambda query, api_key, per_page: [])

    with pytest.raises(ValueError, match="no Pexels candidates"):
        prepare_footage_scoring(
            query="something pexels has nothing for", subject="x",
            api_key="fake-key", thumbnails_dir=str(tmp_path),
        )


def test_resolve_footage_winner_downloads_the_chosen_candidate(tmp_path, monkeypatch):
    import footage.build as build_mod

    calls = []
    monkeypatch.setattr(
        build_mod, "download_winning_video",
        lambda candidate, dest_path, **kw: calls.append((candidate.id, dest_path)) or dest_path,
    )

    candidates = [
        PexelsCandidate(1, "url1", "thumb1.jpg", 10, 1920, 1080, [
            VideoFile("hd", "video/mp4", 1920, 1080, "hd1.mp4"),
        ]),
        PexelsCandidate(2, "url2", "thumb2.jpg", 10, 1280, 720, [
            VideoFile("hd", "video/mp4", 1280, 720, "hd2.mp4"),
        ]),
    ]
    dest = str(tmp_path / "beat_3.mp4")

    result = resolve_footage_winner(candidates, winner_index=1, dest_path=dest)

    assert result == dest
    assert calls == [(2, dest)]


def _fake_candidates(ids):
    return [PexelsCandidate(i, f"url{i}", f"thumb{i}.jpg", 10, 1920, 1080, []) for i in ids]


def _patch_search_and_thumbnails(monkeypatch, results, search_calls):
    import footage.build as build_mod

    def fake_search(query, api_key, per_page):
        search_calls.append(per_page)
        return results[:per_page]

    monkeypatch.setattr(build_mod, "search_pexels", fake_search)
    monkeypatch.setattr(
        build_mod, "download_thumbnails",
        lambda candidates, out_dir: {c.id: f"{out_dir}/{c.id}.jpg" for c in candidates},
    )


def test_prepare_footage_scoring_without_exclusions_searches_default_page_size(tmp_path, monkeypatch):
    search_calls = []
    _patch_search_and_thumbnails(monkeypatch, _fake_candidates(range(1, 81)), search_calls)

    candidates, _ = prepare_footage_scoring(
        query="q", subject="s", api_key="k", thumbnails_dir=str(tmp_path),
    )

    assert search_calls == [7]
    assert [c.id for c in candidates] == [1, 2, 3, 4, 5, 6, 7]


def test_prepare_footage_scoring_excludes_used_ids_and_keeps_first_seven_fresh(tmp_path, monkeypatch):
    search_calls = []
    _patch_search_and_thumbnails(monkeypatch, _fake_candidates(range(1, 81)), search_calls)

    candidates, prompt = prepare_footage_scoring(
        query="q", subject="s", api_key="k", thumbnails_dir=str(tmp_path),
        exclude_ids=frozenset({1, 3, 5}),
    )

    assert search_calls == [80]  # widened search, since Pexels has no server-side exclusion
    assert [c.id for c in candidates] == [2, 4, 6, 7, 8, 9, 10]
    assert f"{tmp_path}/1.jpg" not in prompt


def test_prepare_footage_scoring_returns_fewer_than_seven_when_exclusions_exhaust_results(
    tmp_path, monkeypatch
):
    search_calls = []
    _patch_search_and_thumbnails(monkeypatch, _fake_candidates(range(1, 10)), search_calls)

    candidates, _ = prepare_footage_scoring(
        query="q", subject="s", api_key="k", thumbnails_dir=str(tmp_path),
        exclude_ids=frozenset({1, 2, 3, 4, 5, 6}),
    )

    assert [c.id for c in candidates] == [7, 8, 9]


def test_prepare_footage_scoring_raises_when_every_result_already_used(tmp_path, monkeypatch):
    import pytest

    search_calls = []
    _patch_search_and_thumbnails(monkeypatch, _fake_candidates([1, 2]), search_calls)

    with pytest.raises(ValueError, match="no Pexels candidates.*already-used"):
        prepare_footage_scoring(
            query="q", subject="s", api_key="k", thumbnails_dir=str(tmp_path),
            exclude_ids=frozenset({1, 2}),
        )
