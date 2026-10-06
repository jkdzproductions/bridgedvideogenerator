# tests/test_mixed_build.py
import json
import os

import pytest

import footage.archival_build as ab
import footage.mixed_build as mb
from footage.archive_search import ArchivalSearchError
from footage.archive_types import ArchiveCandidate, ArchiveError
from footage.combined_build import CombinedCandidate
from footage.envato import EnvatoCandidate
from footage.mixed_build import (
    finish_mixed, load_stock_candidates, mixed_prompt_path, mixed_state_path, prepare_mixed, save_stock_candidates,
)
from footage.pexels import PexelsCandidate, VideoFile
from footage.scoring_output import ScoringOutputError
from footage.youtube import YouTubeCandidate

BEAT = {"beat_index": 4, "start": 10.0, "end": 16.0, "era": 1700, "subject": "Boston harbor", "medium": "artwork_or_stock",
        "archival_query": "Boston harbor 1700", "archival_broad_query": "Boston 1700s", "query": "harbor ships"}
ENV = "profile"


def _still(i, kind="photo", source="met"):
    return ArchiveCandidate(source=source, item_id=str(i), kind=kind, title=f"Still {i}", year=1700, creator="Anon",
                            rights="CC0", page_url=f"https://x/{i}", media_url=f"https://x/{i}.jpg",
                            thumbnail_url=f"https://x/{i}_t.jpg", width=2000, height=1500)


def _pexels(i):
    return CombinedCandidate("pexels", str(i), f"/t/p{i}.jpg", PexelsCandidate(
        id=i, url="u", thumbnail_url="t", duration=9, width=1920, height=1080,
        video_files=[VideoFile("hd", "video/mp4", 1920, 1080, "https://l")]))


def _fake_fetch(url, dest):
    os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
    open(dest, "wb").write(b"img")
    return dest


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(mb, "fetch_to_file", _fake_fetch)
    monkeypatch.setattr(ab, "fetch_to_file", _fake_fetch)
    return tmp_path


def _prepare(beat=BEAT, used=()):
    return prepare_mixed(beat, [list(u) for u in used], "pk", "yk", frozenset({"ch"}), ENV)


def _patch_prepare(monkeypatch, artwork=(), photos=(), stock=()):
    calls = {"artwork": [], "photos": [], "stock": []}

    def art(era, query, broad, exclude=frozenset()):
        calls["artwork"].append((era, query, broad, exclude))
        return list(artwork)

    def photo(era, query, broad, exclude=frozenset()):
        calls["photos"].append((era, query, broad, exclude))
        if isinstance(photos, Exception):
            raise photos
        return list(photos)

    def combined(**kw):
        calls["stock"].append(kw)
        if isinstance(stock, Exception):
            raise stock
        return list(stock), "ignored prompt"

    monkeypatch.setattr(mb, "search_artwork", art)
    monkeypatch.setattr(mb, "search_photos", photo)
    monkeypatch.setattr(mb, "prepare_combined_scoring", combined)
    return calls


def test_artwork_or_stock_searches_artwork_and_stock_but_not_photos(workdir, monkeypatch):
    calls = _patch_prepare(monkeypatch, artwork=[_still(1, "photo"), _still(2, "photo")], stock=[_pexels(7)])

    counts = _prepare(used=[("archive", "met:9"), ("pexels", "3")])

    assert counts == {"artwork": 2, "photo": 0, "stock": 1}
    assert calls["artwork"] == [(1700, "Boston harbor 1700", "Boston 1700s", frozenset({"met:9"}))]
    assert calls["photos"] == []
    kw = calls["stock"][0]
    assert kw["query"] == "harbor ships" and kw["subject"] == "Boston harbor"
    assert kw["exclude_ids"] == frozenset({("archive", "met:9"), ("pexels", "3")})
    assert kw["thumbnails_dir"] == "thumbnails/beat_4"
    prompt = open(mixed_prompt_path(4)).read()
    assert "Still 1" in prompt and "type=stock" in prompt and "type=artwork" in prompt
    state = json.load(open(mixed_state_path(4)))
    assert state["still_types"] == ["artwork", "artwork"]
    assert state["stock"][0]["source"] == "pexels" and state["stock"][0]["payload"]["id"] == 7


def test_photo_or_artwork_searches_both_and_never_stock(workdir, monkeypatch):
    calls = _patch_prepare(monkeypatch, artwork=[_still(1)], photos=[_still(2, source="loc")])

    counts = _prepare({**BEAT, "medium": "photo_or_artwork"}, used=[("archive", "met:9")])

    assert counts == {"artwork": 1, "photo": 1, "stock": 0}
    assert calls["artwork"][0][3] == calls["photos"][0][3] == frozenset({"met:9"})
    assert calls["stock"] == []
    prompt = open(mixed_prompt_path(4)).read()
    assert "type=artwork" in prompt and "type=photo" in prompt and "type=stock" not in prompt


def test_photo_search_failure_continues_with_artwork_only(workdir, monkeypatch, capsys):
    _patch_prepare(monkeypatch, artwork=[_still(1)], photos=ArchivalSearchError("nothing"))

    assert _prepare({**BEAT, "medium": "photo_or_artwork"}) == {"artwork": 1, "photo": 0, "stock": 0}
    assert "WARNING" in capsys.readouterr().out


def test_artwork_empty_with_photos_present_works(workdir, monkeypatch):
    _patch_prepare(monkeypatch, artwork=[], photos=[_still(2, source="loc")])

    assert _prepare({**BEAT, "medium": "photo_or_artwork"}) == {"artwork": 0, "photo": 1, "stock": 0}


def test_artwork_empty_gives_a_stock_only_prompt(workdir, monkeypatch):
    _patch_prepare(monkeypatch, stock=[_pexels(7)])

    assert _prepare() == {"artwork": 0, "photo": 0, "stock": 1}
    assert "type=stock" in open(mixed_prompt_path(4)).read()


def test_no_stock_candidates_gives_a_stills_only_prompt(workdir, monkeypatch, capsys):
    _patch_prepare(monkeypatch, artwork=[_still(1)], stock=ValueError("no candidates found for query"))

    assert _prepare() == {"artwork": 1, "photo": 0, "stock": 0}
    assert "type=stock" not in open(mixed_prompt_path(4)).read()
    assert "WARNING" in capsys.readouterr().out


def test_everything_empty_raises_naming_the_beat(workdir, monkeypatch):
    _patch_prepare(monkeypatch, stock=ValueError("no candidates found"))

    with pytest.raises(ArchivalSearchError, match="beat 4"):
        _prepare()


def test_a_still_whose_thumbnail_fails_is_dropped_and_everything_stays_aligned(workdir, monkeypatch, capsys):
    def flaky(url, dest):
        if "/2_t" in url:
            raise ArchiveError("404")
        return _fake_fetch(url, dest)

    monkeypatch.setattr(ab, "fetch_to_file", flaky)
    _patch_prepare(monkeypatch, artwork=[_still(1), _still(2)], photos=[_still(3, source="loc")])

    assert _prepare({**BEAT, "medium": "photo_or_artwork"}) == {"artwork": 1, "photo": 1, "stock": 0}
    state = json.load(open(mixed_state_path(4)))
    assert [c["item_id"] for c in state["stills"]] == ["1", "3"]
    assert state["still_types"] == ["artwork", "photo"]
    prompt = open(mixed_prompt_path(4)).read()
    assert "Still 2" not in prompt and "WARNING" in capsys.readouterr().out


def _prepared(still_types, stock=()):
    stills = [_still(i + 1, kind="photo", source="met" if t == "artwork" else "loc") for i, t in enumerate(still_types)]
    os.makedirs(ab.WORK_DIR, exist_ok=True)
    mb._save_state(4, stills, list(still_types), list(stock))
    return stills


def _verdict(picks, rejected=(), reasoning="ok"):
    return json.dumps({"picks": picks, "rejected": [{"index": i, "reason": "bad"} for i in rejected],
                       "reasoning": reasoning})


def _patch_render(monkeypatch, fail=False):
    rendered = []

    def render(paths, dest, target, work_dir):
        if fail:
            raise RuntimeError("render boom")
        rendered.append((list(paths), dest, target, work_dir))
        return dest

    monkeypatch.setattr(mb, "render_photo_beat", render)
    return rendered


def test_finish_stills_renders_in_order_and_records_item_and_pick_kinds(workdir, monkeypatch):
    _prepared(["artwork", "photo", "artwork"])
    rendered = _patch_render(monkeypatch)
    beat = {**BEAT, "end": 20.0}

    assert finish_mixed(beat, _verdict([1, 0], rejected=[2]), ENV) == "stills"

    paths, dest, target, work_dir = rendered[0]
    assert [os.path.basename(p) for p in paths] == ["loc_2.jpg", "met_1.jpg"]
    assert dest == os.path.join("footage_output", "beat_4.mp4") and target == 10.0
    assert work_dir == os.path.join("archival_work", "render_4")
    pick = json.load(open(ab.PICKS_PATH))[0]
    assert pick["kind"] == "mixed"
    assert [(i["display_id"], i["kind"]) for i in pick["items"]] == [("loc:2", "photo"), ("met:1", "artwork")]
    assert [r["display_id"] for r in pick["rejected"]] == ["met:3"]
    assert json.load(open(ab.USED_IDS_PATH)) == [["archive", "loc:2"], ["archive", "met:1"]]


def test_finish_stills_pick_kind_is_artwork_when_all_artwork(workdir, monkeypatch):
    _prepared(["artwork", "artwork"])
    _patch_render(monkeypatch)

    finish_mixed(BEAT, _verdict([0, 1]), ENV)

    assert json.load(open(ab.PICKS_PATH))[0]["kind"] == "artwork"


def test_finish_stills_trims_to_what_fits_the_cut(workdir, monkeypatch):
    _prepared(["artwork", "photo", "artwork"])
    rendered = _patch_render(monkeypatch)
    beat = {**BEAT, "end": 13.5}  # 3.5 s fits one still

    finish_mixed(beat, _verdict([0, 1, 2]), ENV)

    assert len(rendered[0][0]) == 1
    pick = json.load(open(ab.PICKS_PATH))[0]
    assert [i["display_id"] for i in pick["items"]] == ["met:1"] and pick["kind"] == "artwork"
    assert json.load(open(ab.USED_IDS_PATH)) == [["archive", "met:1"]]


def test_finish_stock_resolves_with_the_stock_relative_index_and_records(workdir, monkeypatch):
    _prepared(["artwork", "photo"], stock=[_pexels(5), _pexels(7)])
    seen = {}

    def resolve(candidates, index, dest, target, profile):
        seen.update(candidates=candidates, index=index, dest=dest, target=target, profile=profile)
        return dest

    monkeypatch.setattr(mb, "resolve_combined_winner", resolve)

    assert finish_mixed(BEAT, _verdict([3], rejected=[0, 2]), ENV) == "stock"

    assert seen["index"] == 1 and len(seen["candidates"]) == 2 and seen["profile"] == ENV
    assert seen["dest"] == os.path.join("footage_output", "beat_4.mp4") and seen["target"] == 6.0
    assert json.load(open(ab.USED_IDS_PATH)) == [["pexels", "7"]]
    pick = json.load(open(ab.PICKS_PATH))[0]
    assert pick["kind"] == "stock" and len(pick["items"]) == 1
    item = pick["items"][0]
    assert (item["source"], item["display_id"]) == ("pexels", "7")
    assert item["title"] == "stock footage (pexels)" and item["rights"] == "stock license (pexels)"
    assert item["local_path"] == "/t/p7.jpg"
    assert [r["display_id"] for r in pick["rejected"]] == ["met:1", "5"]


def test_finish_stock_failure_records_nothing(workdir, monkeypatch):
    _prepared(["artwork"], stock=[_pexels(7)])

    def boom(*a):
        raise RuntimeError("download boom")

    monkeypatch.setattr(mb, "resolve_combined_winner", boom)

    with pytest.raises(RuntimeError):
        finish_mixed(BEAT, _verdict([1]), ENV)
    assert not os.path.exists(ab.PICKS_PATH) and not os.path.exists(ab.USED_IDS_PATH)


def test_finish_with_no_picks_returns_none_and_writes_nothing(workdir, monkeypatch):
    _prepared(["artwork"], stock=[_pexels(7)])
    rendered = _patch_render(monkeypatch)

    assert finish_mixed(BEAT, _verdict([], reasoning="all graphic"), ENV) == "none"

    assert rendered == []
    assert not os.path.exists(ab.PICKS_PATH) and not os.path.exists(ab.USED_IDS_PATH)
    assert not os.path.exists("footage_output")


def test_malformed_verdict_raises_scoring_output_error(workdir, monkeypatch):
    _prepared(["artwork"])
    _patch_render(monkeypatch)

    with pytest.raises(ScoringOutputError):
        finish_mixed(BEAT, "not json", ENV)


def test_render_failure_propagates_and_records_nothing(workdir, monkeypatch):
    _prepared(["artwork", "photo"])
    _patch_render(monkeypatch, fail=True)

    with pytest.raises(RuntimeError, match="render boom"):
        finish_mixed(BEAT, _verdict([0, 1]), ENV)
    assert not os.path.exists(ab.PICKS_PATH) and not os.path.exists(ab.USED_IDS_PATH)


def test_stock_candidates_round_trip(workdir):
    candidates = [
        _pexels(7),
        CombinedCandidate("youtube", "vid", "/t/y.jpg", YouTubeCandidate("vid", "T", "ch", "Chan", "https://t", 42.0)),
        CombinedCandidate("envato", "e-1", "/t/e.jpg", EnvatoCandidate("e-1", "T", "https://t", "Auth", "https://d")),
    ]
    path = str(workdir / "stock.json")

    save_stock_candidates(path, candidates)

    assert load_stock_candidates(path) == candidates


def test_other_value_errors_from_stock_search_propagate(workdir, monkeypatch):
    _patch_prepare(monkeypatch, artwork=[_still(1)], stock=ValueError("bad api key format"))

    with pytest.raises(ValueError, match="bad api key"):
        _prepare()


def test_unknown_medium_raises_naming_it(workdir, monkeypatch):
    _patch_prepare(monkeypatch, artwork=[_still(1)])

    with pytest.raises(ValueError, match="'photo'"):
        _prepare({**BEAT, "medium": "photo"})


def _yt(i):
    return CombinedCandidate("youtube", f"v{i}", f"/t/y{i}.jpg", YouTubeCandidate(f"v{i}", "T", "ch", "C", "u", 30.0))


def _env(i):
    return CombinedCandidate("envato", f"e{i}", f"/t/e{i}.jpg", EnvatoCandidate(f"e{i}", "T", "u", "A", "d"))


@pytest.mark.parametrize("make,pair", [(_pexels, ["pexels", "7"]), (_yt, ["youtube", "v7"]), (_env, ["envato", "e7"])])
def test_stock_winner_goes_through_append_pick_appending_and_replacing(workdir, monkeypatch, make, pair):
    _prepared(["artwork"], stock=[make(7)])
    monkeypatch.setattr(mb, "resolve_combined_winner", lambda c, i, d, t, p: d)
    json.dump([["pexels", "1"]], open(ab.USED_IDS_PATH, "w"))
    json.dump([{"beat_index": 4, "items": [], "kind": "old"}, {"beat_index": 2, "items": [], "kind": "x"}],
              open(ab.PICKS_PATH, "w"))

    finish_mixed(BEAT, _verdict([1]), ENV)

    assert json.load(open(ab.USED_IDS_PATH)) == [["pexels", "1"], pair]
    picks = json.load(open(ab.PICKS_PATH))
    assert [p["beat_index"] for p in picks] == [2, 4] and picks[1]["kind"] == "stock"
    assert picks[1]["items"][0]["local_path"] == os.path.abspath(f"/t/{make(7).thumbnail_path[3:]}")


def test_used_ids_are_written_before_the_picks(workdir, monkeypatch):
    _prepared(["artwork"], stock=[_pexels(7)])
    monkeypatch.setattr(mb, "resolve_combined_winner", lambda c, i, d, t, p: d)
    real = os.replace

    def replace(src, dst):
        if dst == ab.PICKS_PATH:
            raise OSError("crash")
        return real(src, dst)

    monkeypatch.setattr(ab.os, "replace", replace)

    with pytest.raises(OSError):
        finish_mixed(BEAT, _verdict([1]), ENV)
    assert json.load(open(ab.USED_IDS_PATH)) == [["pexels", "7"]]
    assert not os.path.exists(ab.PICKS_PATH)


def test_stock_local_path_is_absolute(workdir, monkeypatch):
    c = _pexels(7)
    c.thumbnail_path = "thumbnails/beat_4/p7.jpg"
    _prepared(["artwork"], stock=[c])
    monkeypatch.setattr(mb, "resolve_combined_winner", lambda c, i, d, t, p: d)

    finish_mixed(BEAT, _verdict([1]), ENV)

    assert json.load(open(ab.PICKS_PATH))[0]["items"][0]["local_path"] == os.path.abspath("thumbnails/beat_4/p7.jpg")


def test_a_loc_item_returned_by_both_searches_appears_once_as_artwork(workdir, monkeypatch):
    _patch_prepare(monkeypatch, artwork=[_still(1, source="met"), _still(5, source="loc")],
                   photos=[_still(5, source="loc"), _still(6, source="commons")])

    counts = _prepare({**BEAT, "medium": "photo_or_artwork"})

    assert counts == {"artwork": 2, "photo": 1, "stock": 0}
    state = json.load(open(mixed_state_path(4)))
    assert [(c["source"], c["item_id"]) for c in state["stills"]] == [("met", "1"), ("loc", "5"), ("commons", "6")]
    assert state["still_types"] == ["artwork", "artwork", "photo"]
    assert open(mixed_prompt_path(4)).read().count("Still 5") == 1


def test_types_stay_aligned_when_a_deduped_and_a_failing_thumbnail_are_dropped(workdir, monkeypatch):
    def flaky(url, dest):
        if "/1_t" in url or "/6_t" in url:
            raise ArchiveError("404")
        return _fake_fetch(url, dest)

    monkeypatch.setattr(ab, "fetch_to_file", flaky)
    _patch_prepare(monkeypatch, artwork=[_still(1), _still(5, source="loc")],
                   photos=[_still(5, source="loc"), _still(6, source="commons"), _still(7, source="commons")])

    _prepare({**BEAT, "medium": "photo_or_artwork"})

    state = json.load(open(mixed_state_path(4)))
    assert [(c["source"], c["item_id"]) for c in state["stills"]] == [("loc", "5"), ("commons", "7")]
    assert state["still_types"] == ["artwork", "photo"]
