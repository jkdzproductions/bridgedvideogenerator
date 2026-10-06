# tests/test_archival_build.py
import json
import os

import pytest

import footage.archival_build as build
from footage.archival_build import (
    append_pick, candidates_path, finish_film, finish_photos, frames_path, load_candidates, prepare_film,
    prepare_photos, prompt_path, render_manual_photos, reset_archival_state, save_candidates,
)
from footage.archive_search import ArchivalSearchError
from footage.archive_types import ArchiveCandidate, ArchiveError
from footage.scoring_output import ScoringOutputError

_REAL_EXTRACT_FRAMES = build._extract_frames

BEAT = {"beat_index": 4, "start": 10.0, "end": 14.0, "era": 1847, "subject": "Atlanta depot",
        "archival_query": "Atlanta depot 1847", "archival_broad_query": "Atlanta 1840s"}


def _photo(i, **over):
    base = dict(source="loc", item_id=str(i), kind="photo", title=f"Photo {i}", year=1860, creator="Brady",
                rights="No known restrictions", page_url=f"https://loc.gov/{i}", media_url=f"https://loc.gov/{i}.jpg",
                thumbnail_url=f"https://loc.gov/{i}_t.jpg", width=2000, height=1500)
    base.update(over)
    return ArchiveCandidate(**base)


def _film(i, duration=60.0):
    return ArchiveCandidate("ia", f"reel{i}", "film", f"Reel {i}", 1938, "Prelinger", "Public domain",
                            f"https://archive.org/details/reel{i}", f"https://archive.org/download/reel{i}/a.mp4",
                            f"https://archive.org/services/img/reel{i}", 640, 480, duration)


def _fake_fetch(url, dest):
    os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
    open(dest, "wb").write(b"img")
    return dest


def _fake_frames(candidate, target, directory):
    os.makedirs(directory, exist_ok=True)
    paths = [os.path.join(directory, f"{candidate.safe_id}_{k}.jpg") for k in range(3)]
    for path in paths:
        open(path, "wb").write(b"frame")
    return paths


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(build, "fetch_to_file", _fake_fetch)
    monkeypatch.setattr(build, "_extract_frames", _fake_frames)
    return tmp_path


def test_candidates_round_trip_through_json(workdir):
    path = str(workdir / "c.json")
    save_candidates(path, [_photo(1), _film(2)])

    assert load_candidates(path) == [_photo(1), _film(2)]


def test_prepare_film_returns_false_when_there_is_no_film_long_enough_for_the_cut(workdir, monkeypatch):
    monkeypatch.setattr(build, "search_film", lambda q, e, exclude: [_film(1, duration=3.5)])   # cut is 4.0 s

    assert prepare_film(BEAT, []) is False
    assert not os.path.exists(prompt_path("film", 4))


def test_prepare_film_passes_the_used_archive_ids_and_writes_the_prompt_and_candidates(workdir, monkeypatch):
    seen = {}
    monkeypatch.setattr(build, "search_film", lambda q, e, exclude: seen.update(q=q, e=e, ex=exclude) or [_film(1)])

    assert prepare_film(BEAT, [["pexels", "9"], ["archive", "ia:reel0"]]) is True

    assert seen == {"q": "Atlanta depot 1847", "e": 1847, "ex": frozenset({"ia:reel0"})}
    assert "Reel 1" in open(prompt_path("film", 4)).read()
    assert load_candidates(candidates_path("film", 4)) == [_film(1)]


def test_prepare_photos_writes_prompt_and_candidates(workdir, monkeypatch):
    seen = {}

    def fake_search(era, query, broad, exclude):
        seen.update(era=era, query=query, broad=broad, ex=exclude)
        return [_photo(1), _photo(2)]

    monkeypatch.setattr(build, "search_photos", fake_search)

    prepare_photos(BEAT, [["archive", "loc:7"]])

    assert seen == {"era": 1847, "query": "Atlanta depot 1847", "broad": "Atlanta 1840s", "ex": frozenset({"loc:7"})}
    prompt = open(prompt_path("photo", 4)).read()
    assert "Photo 1" in prompt and "Photo 2" in prompt and "1847" in prompt
    assert len(load_candidates(candidates_path("photo", 4))) == 2


def test_prepare_photos_lets_a_search_failure_stop_the_stage(workdir, monkeypatch):
    def boom(*a, **k): raise ArchivalSearchError("no archival photos found")
    monkeypatch.setattr(build, "search_photos", boom)

    with pytest.raises(ArchivalSearchError):
        prepare_photos(BEAT, [])


def _prepared(workdir, kind, candidates):
    os.makedirs(build.WORK_DIR, exist_ok=True)
    save_candidates(candidates_path(kind, 4), candidates)


def test_finish_film_with_no_winner_returns_false_and_records_nothing(workdir):
    _prepared(workdir, "film", [_film(1)])

    assert finish_film(BEAT, json.dumps({"winner_index": None, "reasoning": "all graphic"})) is False
    assert not os.path.exists(build.PICKS_PATH)


def test_finish_film_renders_records_the_pick_and_marks_it_used(workdir, monkeypatch):
    _prepared(workdir, "film", [_film(1), _film(2)])
    rendered = {}
    monkeypatch.setattr(build, "render_film_beat", lambda c, dest, target: rendered.update(id=c.item_id, dest=dest, t=target) or dest)

    raw = json.dumps({"winner_index": 1, "rejected": [{"index": 0, "reason": "mostly titles"}], "reasoning": "good street"})
    assert finish_film(BEAT, raw) is True

    assert rendered == {"id": "reel2", "dest": os.path.join("footage_output", "beat_4.mp4"), "t": 4.0}
    [pick] = json.load(open(build.PICKS_PATH))
    assert pick["kind"] == "film" and pick["beat_index"] == 4 and pick["era"] == 1847
    assert pick["items"][0]["display_id"] == "ia:reel2" and pick["items"][0]["rights"] == "Public domain"
    assert pick["rejected"] == [{"display_id": "ia:reel1", "title": "Reel 1", "page_url": "https://archive.org/details/reel1",
                                 "reason": "mostly titles"}]
    assert json.load(open(build.USED_IDS_PATH)) == [["archive", "ia:reel2"]]


def test_finish_photos_downloads_the_picks_in_order_renders_and_records(workdir, monkeypatch):
    _prepared(workdir, "photo", [_photo(1), _photo(2), _photo(3)])
    rendered = {}

    def fake_render(paths, dest, target, work_dir):
        rendered.update(paths=[os.path.basename(p) for p in paths], dest=dest, target=target)
        return dest

    monkeypatch.setattr(build, "render_photo_beat", fake_render)

    finish_photos(BEAT, json.dumps({"picks": [2, 0], "rejected": [{"index": 1, "reason": "modern"}], "reasoning": "r"}))

    assert rendered == {"paths": ["loc_3.jpg", "loc_1.jpg"], "dest": os.path.join("footage_output", "beat_4.mp4"), "target": 4.0}
    [pick] = json.load(open(build.PICKS_PATH))
    assert pick["kind"] == "photo" and [i["display_id"] for i in pick["items"]] == ["loc:3", "loc:1"]
    assert all(os.path.exists(i["local_path"]) for i in pick["items"])
    assert json.load(open(build.USED_IDS_PATH)) == [["archive", "loc:3"], ["archive", "loc:1"]]


def test_finish_photos_stops_loudly_on_a_bad_verdict(workdir):
    _prepared(workdir, "photo", [_photo(1)])

    with pytest.raises(ScoringOutputError):
        finish_photos(BEAT, json.dumps({"picks": [], "reasoning": "none"}))


def test_append_pick_replaces_a_record_for_the_same_beat_and_keeps_used_ids_unique(workdir):
    base = {"beat_index": 4, "items": [{"display_id": "loc:1"}], "kind": "photo"}
    append_pick(dict(base))
    append_pick({"beat_index": 4, "items": [{"display_id": "loc:1"}, {"display_id": "loc:2"}], "kind": "photo"})
    append_pick({"beat_index": 9, "items": [{"display_id": "ia:r"}], "kind": "film"})

    picks = json.load(open(build.PICKS_PATH))
    assert [p["beat_index"] for p in picks] == [4, 9] and len(picks[0]["items"]) == 2
    assert json.load(open(build.USED_IDS_PATH)) == [["archive", "loc:1"], ["archive", "loc:2"], ["archive", "ia:r"]]


def test_reset_archival_state_clears_the_previous_videos_files(workdir):
    os.makedirs(build.WORK_DIR)
    for p in (build.PICKS_PATH, build.REVIEW_PATH, os.path.join(build.WORK_DIR, "x.json")):
        open(p, "w").write("x")

    reset_archival_state()

    assert not os.path.exists(build.WORK_DIR) and not os.path.exists(build.PICKS_PATH) and not os.path.exists(build.REVIEW_PATH)
    reset_archival_state()  # nothing there: still fine


# --- thumbnails that fail to download (photos) ---

def _fetch_failing_for(*bad_urls):
    def fetch(url, dest):
        if url in bad_urls:
            raise ArchiveError(f"download of {url} returned status 404")
        return _fake_fetch(url, dest)
    return fetch


def test_a_photo_whose_thumbnail_fails_is_dropped_with_a_warning_and_the_rest_are_judged(workdir, monkeypatch, capsys):
    monkeypatch.setattr(build, "fetch_to_file", _fetch_failing_for("https://loc.gov/2_t.jpg"))
    monkeypatch.setattr(build, "search_photos", lambda *a: [_photo(1), _photo(2), _photo(3)])

    prepare_photos(BEAT, [])

    assert "WARNING: dropped loc:2: thumbnail download failed (" in capsys.readouterr().out
    prompt = open(prompt_path("photo", 4)).read()
    assert "Photo 1" in prompt and "Photo 3" in prompt and "Photo 2" not in prompt and "Below are 2 candidates" in prompt
    assert [c.item_id for c in load_candidates(candidates_path("photo", 4))] == ["1", "3"]


def test_prepare_photos_raises_naming_the_beat_when_every_thumbnail_fails(workdir, monkeypatch):
    monkeypatch.setattr(build, "fetch_to_file", _fetch_failing_for("https://loc.gov/1_t.jpg", "https://loc.gov/2_t.jpg"))
    monkeypatch.setattr(build, "search_photos", lambda *a: [_photo(1), _photo(2)])

    with pytest.raises(ArchivalSearchError, match=r"beat 4.*every candidate's thumbnail failed to download"):
        prepare_photos(BEAT, [])


# --- film frames ---

def test_the_film_prompt_lists_every_extracted_frame_of_every_candidate(workdir, monkeypatch):
    monkeypatch.setattr(build, "search_film", lambda q, e, exclude: [_film(1), _film(2)])

    assert prepare_film(BEAT, []) is True

    prompt = open(prompt_path("film", 4)).read()
    for reel in ("reel1", "reel2"):
        for k in range(3):
            assert f"ia_{reel}_{k}.jpg" in prompt
    assert "view all frames of each clip" in prompt
    assert json.load(open(frames_path(4)))["ia:reel1"][0].endswith("ia_reel1_0.jpg")


def test_a_film_candidate_with_no_frames_is_dropped_with_a_warning(workdir, monkeypatch, capsys):
    monkeypatch.setattr(build, "search_film", lambda q, e, exclude: [_film(1), _film(2)])
    monkeypatch.setattr(build, "_extract_frames",
                        lambda c, t, d: [] if c.item_id == "reel1" else _fake_frames(c, t, d))

    assert prepare_film(BEAT, []) is True

    assert "WARNING: dropped ia:reel1: " in capsys.readouterr().out
    prompt = open(prompt_path("film", 4)).read()
    assert "Reel 2" in prompt and "Reel 1" not in prompt
    assert [c.item_id for c in load_candidates(candidates_path("film", 4))] == ["reel2"]


def test_prepare_film_returns_false_when_no_candidate_has_frames(workdir, monkeypatch):
    monkeypatch.setattr(build, "search_film", lambda q, e, exclude: [_film(1)])
    monkeypatch.setattr(build, "_extract_frames", lambda c, t, d: [])

    assert prepare_film(BEAT, []) is False
    assert not os.path.exists(prompt_path("film", 4))


def test_finish_film_records_the_winners_first_frame_so_the_review_sheet_shows_an_image(workdir, monkeypatch):
    monkeypatch.setattr(build, "search_film", lambda q, e, exclude: [_film(1), _film(2)])
    prepare_film(BEAT, [])
    monkeypatch.setattr(build, "render_film_beat", lambda c, dest, target: dest)

    finish_film(BEAT, json.dumps({"winner_index": 1, "reasoning": "r"}))

    [pick] = json.load(open(build.PICKS_PATH))
    local = pick["items"][0]["local_path"]
    assert os.path.isabs(local) and local.endswith("ia_reel2_0.jpg") and os.path.exists(local)


def test_extract_frames_runs_ffmpeg_per_time_and_keeps_only_the_frames_that_were_written(workdir, monkeypatch):
    import subprocess
    calls = []

    def fake_run(cmd, capture_output, text, timeout):
        calls.append(cmd)
        if len(calls) == 2:
            return subprocess.CompletedProcess(cmd, 1, "", "boom")
        open(cmd[-1], "wb").write(b"f")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(build.subprocess, "run", fake_run)
    monkeypatch.setattr(build, "_extract_frames", _REAL_EXTRACT_FRAMES)

    paths = build._extract_frames(_film(1), 4.0, str(workdir / "frames"))

    assert len(calls) == 3 and len(paths) == 2
    assert [os.path.basename(p) for p in paths] == ["ia_reel1_0.jpg", "ia_reel1_2.jpg"]


# --- photos actually rendered ---

def test_finish_photos_records_and_marks_used_only_the_photos_that_fit_the_cut(workdir, monkeypatch):
    _prepared(workdir, "photo", [_photo(1), _photo(2), _photo(3)])
    downloads, rendered = [], {}
    real_fetch = build.fetch_to_file
    monkeypatch.setattr(build, "fetch_to_file", lambda url, dest: downloads.append(url) or real_fetch(url, dest))
    monkeypatch.setattr(build, "render_photo_beat",
                        lambda paths, dest, target, work_dir: rendered.update(n=len(paths)) or dest)
    short_beat = dict(BEAT, start=10.0, end=13.5)       # 3.5 s: only one 2 s photo fits

    finish_photos(short_beat, json.dumps({"picks": [2, 0, 1], "rejected": [], "reasoning": "r"}))

    assert downloads == ["https://loc.gov/3.jpg"] and rendered == {"n": 1}
    [pick] = json.load(open(build.PICKS_PATH))
    assert [i["display_id"] for i in pick["items"]] == ["loc:3"]
    assert json.load(open(build.USED_IDS_PATH)) == [["archive", "loc:3"]]


# --- supplying photos by hand ---

def _files(tmp_path, *names):
    paths = []
    for n in names:
        p = tmp_path / n
        p.write_bytes(b"img")
        paths.append(str(p))
    return paths


def test_render_manual_photos_renders_the_beat_and_records_a_manual_pick(workdir, monkeypatch):
    rendered = {}
    monkeypatch.setattr(build, "render_photo_beat",
                        lambda paths, dest, target, work_dir: rendered.update(paths=paths, dest=dest, t=target, w=work_dir) or dest)
    photos = _files(workdir, "depot.jpg", "yard.png")

    render_manual_photos(BEAT, photos, "Library of Congress, no known restrictions")

    assert rendered == {"paths": photos, "dest": os.path.join("footage_output", "beat_4.mp4"), "t": 4.0,
                        "w": os.path.join(build.WORK_DIR, "render_4")}
    [pick] = json.load(open(build.PICKS_PATH))
    assert pick["kind"] == "photo" and pick["beat_index"] == 4 and pick["reasoning"] == "supplied by Josh"
    assert pick["rejected"] == []
    first = pick["items"][0]
    assert first == {"source": "manual", "item_id": "manual:depot.jpg", "display_id": "manual:depot.jpg",
                     "title": "depot.jpg", "year": None, "creator": "",
                     "rights": "Library of Congress, no known restrictions", "page_url": "",
                     "local_path": os.path.abspath(photos[0])}
    assert [i["display_id"] for i in pick["items"]] == ["manual:depot.jpg", "manual:yard.png"]
    assert json.load(open(build.USED_IDS_PATH)) == [["archive", "manual:depot.jpg"], ["archive", "manual:yard.png"]]


def test_render_manual_photos_replaces_an_earlier_pick_for_the_same_beat(workdir, monkeypatch):
    monkeypatch.setattr(build, "render_photo_beat", lambda paths, dest, target, work_dir: dest)
    append_pick({"beat_index": 4, "items": [{"display_id": "loc:1"}], "kind": "photo"})

    render_manual_photos(BEAT, _files(workdir, "a.jpg"), "own scan")

    picks = json.load(open(build.PICKS_PATH))
    assert len(picks) == 1 and picks[0]["items"][0]["source"] == "manual"


@pytest.mark.parametrize("note", ["", "   ", None])
def test_render_manual_photos_requires_a_source_note(workdir, monkeypatch, note):
    monkeypatch.setattr(build, "render_photo_beat", lambda *a: pytest.fail("must not render"))

    with pytest.raises(ValueError, match="source"):
        render_manual_photos(BEAT, _files(workdir, "a.jpg"), note)
    assert not os.path.exists(build.PICKS_PATH)


def test_render_manual_photos_stops_on_a_missing_file_or_an_empty_list(workdir, monkeypatch):
    monkeypatch.setattr(build, "render_photo_beat", lambda *a: pytest.fail("must not render"))

    with pytest.raises(ValueError, match="nope.jpg"):
        render_manual_photos(BEAT, [str(workdir / "nope.jpg")], "src")
    with pytest.raises(ValueError, match="no photo"):
        render_manual_photos(BEAT, [], "src")
    assert not os.path.exists(build.PICKS_PATH)


# --- bounded frame extraction ---

def test_frame_extraction_limits_have_the_stated_values():
    assert build.FRAME_TIMEOUT_SECONDS == 30 and build.MAX_FILM_CANDIDATES_FOR_FRAMES == 5


def test_a_frame_timeout_stops_that_candidates_remaining_frames_and_drops_it(workdir, monkeypatch, capsys):
    import subprocess
    calls = []

    def fake_run(cmd, capture_output, text, timeout):
        calls.append((cmd[5], timeout))
        raise subprocess.TimeoutExpired(cmd, timeout)

    monkeypatch.setattr(build.subprocess, "run", fake_run)
    monkeypatch.setattr(build, "_extract_frames", _REAL_EXTRACT_FRAMES)
    monkeypatch.setattr(build, "search_film", lambda q, e, exclude: [_film(1), _film(2)])

    assert prepare_film(BEAT, []) is False

    assert len(calls) == 2 and {c[1] for c in calls} == {30}      # one timeout per candidate, then it stops
    out = capsys.readouterr().out
    assert "WARNING: dropped ia:reel1" in out and "timed out" in out


def test_only_the_first_five_film_candidates_get_frame_extraction(workdir, monkeypatch, capsys):
    seen = []
    monkeypatch.setattr(build, "search_film", lambda q, e, exclude: [_film(i) for i in range(6)])
    monkeypatch.setattr(build, "_extract_frames", lambda c, t, d: seen.append(c.item_id) or _fake_frames(c, t, d))

    assert prepare_film(BEAT, []) is True

    assert seen == [f"reel{i}" for i in range(5)]
    assert [c.item_id for c in load_candidates(candidates_path("film", 4))] == seen
    out = capsys.readouterr().out
    assert "film candidate ia:reel0: 3 frames" in out and "film candidate ia:reel4: 3 frames" in out


# --- manual photo limits ---

def test_render_manual_photos_refuses_more_than_three_photos(workdir, monkeypatch):
    monkeypatch.setattr(build, "render_photo_beat", lambda *a: pytest.fail("must not render"))

    with pytest.raises(ValueError, match="at most 3"):
        render_manual_photos(BEAT, _files(workdir, "a.jpg", "b.jpg", "c.jpg", "d.jpg"), "src")


def test_render_manual_photos_records_only_the_photos_that_fit_the_cut(workdir, monkeypatch):
    rendered = {}
    monkeypatch.setattr(build, "render_photo_beat",
                        lambda paths, dest, target, work_dir: rendered.update(paths=paths) or dest)
    photos = _files(workdir, "a.jpg", "b.jpg", "c.jpg")

    render_manual_photos(dict(BEAT, start=10.0, end=13.5), photos, "src")

    assert rendered["paths"] == photos[:1]
    [pick] = json.load(open(build.PICKS_PATH))
    assert [i["title"] for i in pick["items"]] == ["a.jpg"]
    assert json.load(open(build.USED_IDS_PATH)) == [["archive", "manual:a.jpg"]]
