# tests/test_mixed_chain.py
"""The real search_artwork, search_photos, prepare_mixed, build_mixed_scoring_prompt, parse_mixed_verdict and
finish_mixed chained together; only the leaf clients, the download and the renderer are mocked."""
import json
import os

import pytest

import footage.archival_build as ab
import footage.archive_artwork as art
import footage.archive_search as search
import footage.mixed_build as mb
from footage.archive_types import ArchiveCandidate
from footage.combined_build import CombinedCandidate
from footage.pexels import PexelsCandidate, VideoFile

ENV = "profile"


def _item(source, i, year=1863):
    return ArchiveCandidate(source=source, item_id=str(i), kind="photo", title=f"{source} item {i}", year=year,
                            creator="Anon", rights="Public domain", page_url=f"https://x/{source}/{i}",
                            media_url=f"https://x/{source}/{i}.jpg", thumbnail_url=f"https://x/{source}/{i}_t.jpg",
                            width=2000, height=1500)


def _beat(medium, era):
    return {"beat_index": 3, "start": 0.0, "end": 6.0, "era": era, "subject": "the battle", "medium": medium,
            "archival_query": "battle scene", "archival_broad_query": "battle", "query": "ships at sea"}


@pytest.fixture
def chain(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    def fetch(url, dest):
        os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
        open(dest, "wb").write(b"img")
        return dest

    rendered, resolved = [], []

    def render(paths, dest, target, work_dir):
        rendered.append((list(paths), dest))
        return dest

    def resolve(candidates, index, dest, target, profile):
        resolved.append((candidates[index].source, candidates[index].display_id, index))
        return dest

    stock = [CombinedCandidate("pexels", "7", "/t/p7.jpg", PexelsCandidate(
        id=7, url="u", thumbnail_url="t", duration=9, width=1920, height=1080,
        video_files=[VideoFile("hd", "video/mp4", 1920, 1080, "https://l")]))]
    # Leaf clients only. The same LoC item is returned on the artwork path and the photo path.
    monkeypatch.setattr(art, "search_met_artwork", lambda q, r: [_item("met", 1)])
    monkeypatch.setattr(art, "search_loc_photos", lambda q, r: [_item("loc", 5)])
    monkeypatch.setattr(search, "search_loc_photos", lambda q, r: [_item("loc", 5)])
    monkeypatch.setattr(search, "search_commons_photos", lambda q, r: [_item("commons", 6)])
    monkeypatch.setattr(ab, "fetch_to_file", fetch)
    monkeypatch.setattr(mb, "fetch_to_file", fetch)
    monkeypatch.setattr(mb, "render_photo_beat", render)
    monkeypatch.setattr(mb, "prepare_combined_scoring", lambda **kw: (list(stock), "ignored"))
    monkeypatch.setattr(mb, "resolve_combined_winner", resolve)
    return rendered, resolved


def _prepare(beat):
    return mb.prepare_mixed(beat, [], "pk", "yk", frozenset(), ENV)


def test_1863_photo_or_artwork_shows_each_loc_item_once_and_records_the_right_kinds(chain):
    rendered, _ = chain
    beat = _beat("photo_or_artwork", 1863)

    counts = _prepare(beat)

    assert counts == {"artwork": 2, "photo": 1, "stock": 0}
    prompt = open(mb.mixed_prompt_path(3)).read()
    assert prompt.count("loc item 5") == 1
    assert "[0] type=artwork source=met" in prompt and "[1] type=artwork source=loc" in prompt
    assert "[2] type=photo source=commons" in prompt and "type=stock" not in prompt
    verdict = json.dumps({"picks": [1, 2], "rejected": [{"index": 0, "reason": "dull"}], "reasoning": "best two"})

    assert mb.finish_mixed(beat, verdict, ENV) == "stills"

    assert [os.path.basename(p) for p in rendered[0][0]] == ["loc_5.jpg", "commons_6.jpg"]
    pick = json.load(open(ab.PICKS_PATH))[0]
    assert pick["kind"] == "mixed"
    assert [(i["display_id"], i["kind"]) for i in pick["items"]] == [("loc:5", "artwork"), ("commons:6", "photo")]
    assert json.load(open(ab.USED_IDS_PATH)) == [["archive", "loc:5"], ["archive", "commons:6"]]


def test_1781_artwork_or_stock_resolves_a_stock_verdict_by_the_stock_index(chain):
    _, resolved = chain
    beat = _beat("artwork_or_stock", 1781)

    counts = _prepare(beat)

    assert counts == {"artwork": 2, "photo": 0, "stock": 1}
    assert "[2] type=stock source=pexels duration=9s resolution=1920x1080" in open(mb.mixed_prompt_path(3)).read()
    verdict = json.dumps({"picks": [2], "rejected": [{"index": 0, "reason": "x"}], "reasoning": "stock fits"})

    assert mb.finish_mixed(beat, verdict, ENV) == "stock"

    assert resolved == [("pexels", "7", 0)]
    assert json.load(open(ab.USED_IDS_PATH)) == [["pexels", "7"]]
    assert json.load(open(ab.PICKS_PATH))[0]["kind"] == "stock"


def test_an_empty_picks_verdict_returns_none_and_writes_nothing(chain):
    rendered, resolved = chain
    beat = _beat("photo_or_artwork", 1863)
    _prepare(beat)

    assert mb.finish_mixed(beat, json.dumps({"picks": [], "rejected": [], "reasoning": "all graphic"}), ENV) == "none"

    assert rendered == [] and resolved == []
    assert not os.path.exists(ab.PICKS_PATH) and not os.path.exists(ab.USED_IDS_PATH)
    assert not os.path.exists("footage_output")
