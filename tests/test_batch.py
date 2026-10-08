# tests/test_batch.py
"""footage/batch.py: Stage 2 in batches (prep many beats with a small thread pool, judges in parallel, then apply
the verdicts in beat order). No live API is called: every search/download function is replaced."""
import json
import os
import threading
import time

import pytest

import footage.batch as batch
from footage.archival_build import candidates_path, save_candidates
from footage.archive_types import ArchiveCandidate
from footage.combined_build import CombinedCandidate
from footage.mixed_build import _save_state, save_stock_candidates
from footage.pexels import PexelsCandidate, VideoFile
from footage.youtube import YouTubeCandidate


def _pexels(i):
    return CombinedCandidate("pexels", str(i), f"/t/p{i}.jpg", PexelsCandidate(
        id=i, url="u", thumbnail_url="t", duration=9, width=1920, height=1080,
        video_files=[VideoFile("hd", "video/mp4", 1920, 1080, "https://l")]))


def _youtube(vid):
    return CombinedCandidate("youtube", vid, f"/t/{vid}.jpg", YouTubeCandidate(vid, "T", "UC", "Ch", "t.jpg", 60.0))


def _still(i, source="loc"):
    return ArchiveCandidate(source=source, item_id=str(i), kind="photo", title=f"Still {i}", year=1900, creator="",
                            rights="No known restrictions", page_url=f"https://x/{i}", media_url=f"https://x/{i}.jpg",
                            thumbnail_url=f"https://x/{i}_t.jpg", width=2000, height=1500)


def _film(i):
    return ArchiveCandidate(source="ia", item_id=f"film{i}", kind="film", title=f"Film {i}", year=1930, creator="",
                            rights="Public domain", page_url="p", media_url="m", thumbnail_url="t",
                            duration_seconds=60.0)


def _archival_beat(n, medium="photo", era=1930):
    return {"beat_index": n, "start": 0.0, "end": 6.0, "era": era, "subject": f"subject {n}", "medium": medium,
            "query": f"q{n}", "archival_query": f"aq{n}", "archival_broad_query": f"bq{n}"}


@pytest.fixture
def run(tmp_path, monkeypatch):
    """A fresh Stage 2 working directory after Step 1: modern beats 1, 2, 3 and archival beats 10-14."""
    monkeypatch.chdir(tmp_path)
    json.dump([[1, "q1", "s1"], [2, "q2", "s2"], [3, "q3", "s3"]], open("footage_beats.json", "w"))
    json.dump([_archival_beat(10), _archival_beat(11), _archival_beat(12, "photo_or_artwork", 1870),
               _archival_beat(13, "artwork_or_stock", 1800), _archival_beat(14)], open("archival_beats.json", "w"))
    json.dump({str(n): 6.0 for n in (1, 2, 3, 10, 11, 12, 13, 14)}, open("beat_durations.json", "w"))
    json.dump(["UCx"], open("excluded_channel_ids.json", "w"))
    json.dump([], open("used_footage_ids.json", "w"))
    return tmp_path


def _used():
    return json.load(open("used_footage_ids.json"))


# --- prep-modern ---------------------------------------------------------------------------------

def _fake_prepare_combined(pool, active=None, peak=None, fail_query=None):
    guard = threading.Lock()

    def fake(**kw):
        if active is not None:
            with guard:
                active[0] += 1
                peak[0] = max(peak[0], active[0])
            time.sleep(0.05)
            with guard:
                active[0] -= 1
        if kw["query"] == fail_query:
            raise ValueError(f"no candidates found for query: {fail_query!r}")
        return list(pool), f"PROMPT for {kw['query']} / {kw['subject']} excluding {sorted(kw['exclude_ids'])}"
    return fake


def test_prep_modern_runs_beats_in_parallel_and_writes_each_beats_files(run, monkeypatch):
    active, peak, spends = [0], [0], []
    monkeypatch.setattr(batch, "prepare_combined_scoring", _fake_prepare_combined([_pexels(7), _youtube("v")], active, peak))
    monkeypatch.setattr(batch, "record_spend", lambda units, path: spends.append((units, path)))
    json.dump([["pexels", "99"]], open("used_footage_ids.json", "w"))

    results = batch.prep_modern(workers=4, pexels_api_key="pk", youtube_api_key="yk", envato_profile_dir="env")

    assert sorted(results) == [1, 2, 3] and all(r.status == "ok" for r in results.values())
    assert peak[0] > 1
    assert spends == [(102, "youtube_quota_usage.json")] * 3
    saved = json.load(open("candidates_2.json"))
    assert [c["display_id"] for c in saved] == ["7", "v"] and saved[0]["payload"]["video_files"][0]["link"] == "https://l"
    assert open("scoring_prompt_2.txt").read() == "PROMPT for q2 / s2 excluding [('pexels', '99')]"


def test_prep_modern_deletes_a_stale_judge_response_so_it_is_never_applied_to_new_candidates(run, monkeypatch):
    monkeypatch.setattr(batch, "prepare_combined_scoring", _fake_prepare_combined([_pexels(7)]))
    monkeypatch.setattr(batch, "record_spend", lambda units, path: None)
    open("scoring_response_1.txt", "w").write('{"winner_index": 0}')

    batch.prep_modern([1], workers=1, pexels_api_key="pk", youtube_api_key="yk", envato_profile_dir="env")

    assert not os.path.exists("scoring_response_1.txt")


def test_prep_modern_stops_starting_beats_after_an_error_and_records_no_spend_for_it(run, monkeypatch):
    spends = []
    monkeypatch.setattr(batch, "prepare_combined_scoring", _fake_prepare_combined([_pexels(7)], fail_query="q1"))
    monkeypatch.setattr(batch, "record_spend", lambda units, path: spends.append(units))

    results = batch.prep_modern([1, 2, 3], workers=1, pexels_api_key="pk", youtube_api_key="yk",
                                envato_profile_dir="env")

    assert results[1].status == "error" and "no candidates found" in results[1].message
    assert results[2].status == results[3].status == "not_started"
    assert spends == []


def test_prep_modern_by_default_skips_beats_that_already_have_a_clip(run, monkeypatch):
    seen = []
    fake = _fake_prepare_combined([_pexels(7)])
    monkeypatch.setattr(batch, "prepare_combined_scoring", lambda **kw: seen.append(kw["query"]) or fake(**kw))
    monkeypatch.setattr(batch, "record_spend", lambda units, path: None)
    os.makedirs("footage_output")
    open("footage_output/beat_2.mp4", "wb").write(b"done")

    batch.prep_modern(workers=2, pexels_api_key="pk", youtube_api_key="yk", envato_profile_dir="env")

    assert sorted(seen) == ["q1", "q3"]


def test_prep_rejects_a_beat_that_is_not_in_its_list(run):
    with pytest.raises(ValueError, match="beat 10 is not a modern footage beat"):
        batch.prep_modern([10], workers=1, pexels_api_key="pk", youtube_api_key="yk", envato_profile_dir="env")
    with pytest.raises(ValueError, match="beat 12 is not a photo beat"):
        batch.prep_film([12], workers=1)
    with pytest.raises(ValueError, match="beat 10 is not a mixed beat"):
        batch.prep_mixed([10], workers=1, pexels_api_key="pk", youtube_api_key="yk", envato_profile_dir="env")


def test_each_beats_printed_lines_are_labelled_with_the_beat(run, monkeypatch, capsys):
    def noisy(**kw):
        print(f"WARNING: Envato contributed 0 candidates for {kw['query']}")
        time.sleep(0.02)
        print(f"second line for {kw['query']}")
        return [_pexels(int(kw["query"][1:]))], "p"

    monkeypatch.setattr(batch, "prepare_combined_scoring", noisy)
    monkeypatch.setattr(batch, "record_spend", lambda units, path: None)

    batch.prep_modern(workers=3, pexels_api_key="pk", youtube_api_key="yk", envato_profile_dir="env")

    lines = capsys.readouterr().out.splitlines()
    for n in (1, 2, 3):
        first = lines.index(f"[beat {n}] WARNING: Envato contributed 0 candidates for q{n}")
        assert lines.index(f"[beat {n}] second line for q{n}") > first


# --- apply-modern --------------------------------------------------------------------------------

def _modern_ready(n, pool, response):
    save_stock_candidates(f"candidates_{n}.json", pool)
    open(f"scoring_prompt_{n}.txt", "w").write("p")
    if response is not None:
        open(f"scoring_response_{n}.txt", "w").write(response)


def _fake_resolve(downloads, fail_for=None):
    def fake(candidates, winner_index, dest_path, target_duration, envato_profile_dir):
        winner = candidates[winner_index]
        if winner.display_id == fail_for:
            raise RuntimeError(f"download failed for {fail_for}")
        downloads.append((winner.display_id, dest_path, target_duration))
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        open(dest_path, "wb").write(b"clip")
        return dest_path
    return fake


def test_apply_modern_applies_in_beat_order_and_refuses_a_duplicate_winner(run, monkeypatch):
    downloads = []
    monkeypatch.setattr(batch, "resolve_combined_winner", _fake_resolve(downloads))
    _modern_ready(1, [_pexels(7), _youtube("v")], '{"winner_index": 1, "reasoning": "r"}')
    _modern_ready(2, [_youtube("v"), _pexels(8)], '{"winner_index": 0, "reasoning": "same clip"}')
    _modern_ready(3, [_pexels(9)], '```json\n{"winner_index": 0, "reasoning": "r"}\n```')

    results = batch.apply_modern(envato_profile_dir="env")

    assert [r.status for r in results.values()] == ["done", "duplicate", "done"]
    assert "youtube v" in results[2].message and "prep-modern 2" in results[2].message
    assert downloads == [("v", "footage_output/beat_1.mp4", 6.0), ("9", "footage_output/beat_3.mp4", 6.0)]
    assert _used() == [["youtube", "v"], ["pexels", "9"]]
    assert not os.path.exists("footage_output/beat_2.mp4")


def test_apply_modern_flags_no_acceptable_and_carries_on(run, monkeypatch):
    downloads = []
    monkeypatch.setattr(batch, "resolve_combined_winner", _fake_resolve(downloads))
    _modern_ready(1, [_pexels(7)], '{"winner_index": null, "reasoning": "all show Mexico"}')
    _modern_ready(2, [_pexels(8)], '{"winner_index": 0, "reasoning": "r"}')

    results = batch.apply_modern([1, 2], envato_profile_dir="env")

    assert results[1].status == "no_acceptable" and "all show Mexico" in results[1].message
    assert results[2].status == "done"


def test_apply_modern_stops_at_a_download_error_and_never_substitutes(run, monkeypatch):
    downloads = []
    monkeypatch.setattr(batch, "resolve_combined_winner", _fake_resolve(downloads, fail_for="7"))
    _modern_ready(1, [_pexels(7), _pexels(70)], '{"winner_index": 0, "reasoning": "r"}')
    _modern_ready(2, [_pexels(8)], '{"winner_index": 0, "reasoning": "r"}')

    results = batch.apply_modern([1, 2], envato_profile_dir="env")

    assert results[1].status == "error" and "download failed for 7" in results[1].message
    assert results[2].status == "not_started"
    assert downloads == [] and _used() == []


def test_apply_modern_keep_going_continues_past_an_error(run, monkeypatch):
    downloads = []
    monkeypatch.setattr(batch, "resolve_combined_winner", _fake_resolve(downloads, fail_for="7"))
    _modern_ready(1, [_pexels(7)], '{"winner_index": 0, "reasoning": "r"}')
    _modern_ready(2, [_pexels(8)], '{"winner_index": 0, "reasoning": "r"}')

    results = batch.apply_modern([1, 2], keep_going=True, envato_profile_dir="env")

    assert [results[1].status, results[2].status] == ["error", "done"]


def test_apply_modern_errors_on_a_missing_response_and_a_malformed_one(run, monkeypatch):
    monkeypatch.setattr(batch, "resolve_combined_winner", _fake_resolve([]))
    _modern_ready(1, [_pexels(7)], None)
    _modern_ready(2, [_pexels(8)], '{"winner_index": 5}')

    results = batch.apply_modern([1, 2], keep_going=True, envato_profile_dir="env")

    assert results[1].status == "error" and "scoring_response_1.txt" in results[1].message
    assert results[2].status == "error" and "winner_index" in results[2].message


def test_apply_modern_by_default_takes_prepped_beats_without_a_clip(run, monkeypatch):
    downloads = []
    monkeypatch.setattr(batch, "resolve_combined_winner", _fake_resolve(downloads))
    _modern_ready(1, [_pexels(7)], '{"winner_index": 0, "reasoning": "r"}')
    _modern_ready(3, [_pexels(9)], '{"winner_index": 0, "reasoning": "r"}')  # beat 2 not prepped

    results = batch.apply_modern(envato_profile_dir="env")

    assert sorted(results) == [1, 3]


# --- archival film / photos ----------------------------------------------------------------------

def test_prep_film_reports_which_beats_have_film_and_clears_stale_responses(run, monkeypatch):
    os.makedirs("archival_work")
    open("archival_work/film_response_10.txt", "w").write("old")
    monkeypatch.setattr(batch, "prepare_film", lambda beat, used: beat["beat_index"] == 10)

    results = batch.prep_film(workers=2)

    assert sorted(results) == [10, 11, 14]
    assert results[10].status == "ok" and results[10].judge
    assert results[11].status == "needs_photos" and not results[11].judge
    assert not os.path.exists("archival_work/film_response_10.txt")


def test_apply_film_uses_film_or_hands_the_beat_to_photos_and_refuses_duplicates(run, monkeypatch):
    finished = []
    monkeypatch.setattr(batch, "finish_film", lambda beat, raw: finished.append(beat["beat_index"]) or
                        json.loads(raw)["winner_index"] is not None)
    for n in (10, 11, 14):
        save_candidates(candidates_path("film", n), [_film(n), _film(99)])
        open(f"archival_work/film_prompt_{n}.txt", "w").write("p")
    open("archival_work/film_response_10.txt", "w").write('{"winner_index": 0, "rejected": [], "reasoning": "r"}')
    open("archival_work/film_response_11.txt", "w").write('{"winner_index": null, "rejected": [], "reasoning": "none"}')
    open("archival_work/film_response_14.txt", "w").write('{"winner_index": 1, "rejected": [], "reasoning": "r"}')
    json.dump([["archive", "ia:film99"]], open("used_footage_ids.json", "w"))

    results = batch.apply_film()

    assert [results[n].status for n in (10, 11, 14)] == ["done", "needs_photos", "duplicate"]
    assert finished == [10, 11]


def test_apply_photos_flags_an_empty_pick_list_and_a_duplicate_pick(run, monkeypatch):
    finished = []
    monkeypatch.setattr(batch, "finish_photos", lambda beat, raw: finished.append(beat["beat_index"]))
    for n in (10, 11, 14):
        save_candidates(candidates_path("photo", n), [_still(1), _still(2), _still(3)])
        open(f"archival_work/photo_prompt_{n}.txt", "w").write("p")
    open("archival_work/photo_response_10.txt", "w").write('{"picks": [], "rejected": [], "reasoning": "all AI"}')
    open("archival_work/photo_response_11.txt", "w").write('{"picks": [0, 2], "rejected": [], "reasoning": "r"}')
    open("archival_work/photo_response_14.txt", "w").write('{"picks": [1], "rejected": [], "reasoning": "r"}')
    json.dump([["archive", "loc:2"]], open("used_footage_ids.json", "w"))

    results = batch.apply_photos([10, 11, 14])

    assert results[10].status == "no_acceptable" and "all AI" in results[10].message
    assert results[11].status == "done"
    assert results[14].status == "duplicate" and "loc:2" in results[14].message
    assert finished == [11]


def test_a_duplicate_check_only_counts_the_photos_that_will_be_shown(run, monkeypatch):
    # A 3-second cut shows only the first pick (2 s minimum each), so only that one is marked used.
    finished = []
    monkeypatch.setattr(batch, "finish_photos", lambda beat, raw: finished.append(beat["beat_index"]))
    beats = json.load(open("archival_beats.json"))
    beats[0]["end"] = 3.0
    json.dump(beats, open("archival_beats.json", "w"))
    save_candidates(candidates_path("photo", 10), [_still(1), _still(2)])
    open("archival_work/photo_prompt_10.txt", "w").write("p")
    open("archival_work/photo_response_10.txt", "w").write('{"picks": [0, 1], "rejected": [], "reasoning": "r"}')
    json.dump([["archive", "loc:2"]], open("used_footage_ids.json", "w"))

    assert batch.apply_photos([10])[10].status == "done"


# --- mixed ---------------------------------------------------------------------------------------

def test_prep_mixed_records_quota_only_for_artwork_or_stock(run, monkeypatch):
    spends = []
    monkeypatch.setattr(batch, "prepare_mixed", lambda *a: {"artwork": 2, "photo": 0, "stock": 3})
    monkeypatch.setattr(batch, "record_spend", lambda units, path: spends.append(units))

    results = batch.prep_mixed(workers=2, pexels_api_key="pk", youtube_api_key="yk", envato_profile_dir="env")

    assert sorted(results) == [12, 13] and spends == [102]


def test_apply_mixed_flags_none_and_refuses_a_duplicate_stock_clip(run, monkeypatch):
    finished = []
    monkeypatch.setattr(batch, "finish_mixed", lambda beat, raw, env: finished.append(beat["beat_index"]) or "stock")
    _save_state(12, [_still(1)], ["photo"], [])
    _save_state(13, [_still(2, "met")], ["artwork"], [_pexels(5)])
    open("archival_work/mixed_prompt_12.txt", "w").write("p")
    open("archival_work/mixed_prompt_13.txt", "w").write("p")
    open("archival_work/mixed_response_12.txt", "w").write('{"picks": [], "rejected": [], "reasoning": "nothing real"}')
    open("archival_work/mixed_response_13.txt", "w").write('{"picks": [1], "rejected": [], "reasoning": "r"}')
    json.dump([["pexels", "5"]], open("used_footage_ids.json", "w"))

    results = batch.apply_mixed(envato_profile_dir="env")

    assert results[12].status == "no_acceptable" and "nothing real" in results[12].message
    assert results[13].status == "duplicate" and finished == []


# --- judge responses -----------------------------------------------------------------------------

def test_extract_verdict_takes_the_last_json_answer_with_the_expected_key():
    prompt_example = '{"winner_index": null, "reasoning": "<one sentence on why none are acceptable>"}'
    transcript = "\n".join(json.dumps(line) for line in [
        {"type": "user", "message": {"content": [{"type": "text", "text": "Instructions...\n" + prompt_example}]}},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "Let me look at the thumbnails."}]}},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": '{"picks": [1]}'}]}},
        {"type": "assistant", "message": {"content": [
            {"type": "text", "text": '```json\n{"winner_index": 2, "reasoning": "the real port"}\n```'}]}},
    ])

    assert json.loads(batch.extract_verdict(transcript, "winner_index")) == {"winner_index": 2, "reasoning": "the real port"}
    assert json.loads(batch.extract_verdict(transcript, "picks")) == {"picks": [1]}
    assert batch.extract_verdict("no json here", "picks") is None


def test_save_response_accepts_plain_text_and_writes_the_kinds_response_file(run):
    path = batch.save_response("photo", 11, 'Here it is:\n{"picks": [0], "rejected": [], "reasoning": "r"}\n')

    assert path == os.path.join("archival_work", "photo_response_11.txt")
    assert json.loads(open(path).read())["picks"] == [0]
    with pytest.raises(ValueError, match="no JSON verdict"):
        batch.save_response("modern", 1, "I could not decide.")


def test_cli_extract_reads_subagent_output_files(run, tmp_path):
    open("scoring_prompt_1.txt", "w").write("p")
    out = tmp_path / "agent.output"
    out.write_text(json.dumps({"prompt": f"Read the file {os.path.abspath('scoring_prompt_1.txt')}"}) + "\n" +
                   json.dumps({"message": {"content": [{"type": "text", "text": '{"winner_index": 0, "reasoning": "r"}'}]}}))

    assert batch.main(["extract", "modern", f"1={out}"]) == 0
    assert json.loads(open("scoring_response_1.txt").read())["winner_index"] == 0


# --- CLI ----------------------------------------------------------------------------------------

def test_cli_exit_codes_are_0_ok_2_flagged_1_error(run, monkeypatch):
    monkeypatch.setattr(batch, "resolve_combined_winner", _fake_resolve([], fail_for="8"))
    _modern_ready(1, [_pexels(7)], '{"winner_index": null, "reasoning": "none"}')
    assert batch.main(["apply-modern", "1"]) == 2
    _modern_ready(2, [_pexels(8)], '{"winner_index": 0, "reasoning": "r"}')
    assert batch.main(["apply-modern", "2"]) == 1
    _modern_ready(3, [_pexels(9)], '{"winner_index": 0, "reasoning": "r"}')
    assert batch.main(["apply-modern", "3"]) == 0


def test_cli_prints_one_judge_line_per_beat_to_judge(run, monkeypatch, capsys):
    monkeypatch.setattr(batch, "prepare_film", lambda beat, used: beat["beat_index"] != 11)

    assert batch.main(["prep-film", "--workers", "2"]) == 0

    out = capsys.readouterr().out
    assert f"JUDGE beat=10 model=opus prompt={os.path.abspath('archival_work/film_prompt_10.txt')} " \
           f"response={os.path.abspath('archival_work/film_response_10.txt')}" in out
    assert "JUDGE beat=11" not in out
    assert "prep-photos 11" in out


def test_status_lists_what_is_left(run, capsys):
    os.makedirs("footage_output")
    open("footage_output/beat_1.mp4", "wb").write(b"x")

    assert batch.main(["status"]) == 0
    out = capsys.readouterr().out
    assert "modern: 2 of 3 left: 2 3" in out and "archival photo: 3 of 3 left: 10 11 14" in out
    assert "mixed: 2 of 2 left: 12 13" in out


# --- review fixes ---------------------------------------------------------------------------------

def _age(path, seconds):
    t = time.time() - seconds
    os.utime(path, (t, t))


def test_default_apply_ignores_files_left_from_an_earlier_video(run, monkeypatch):
    # Step 1 writes footage_beats.json for the new video; prompts older than it belong to the last video.
    downloads = []
    monkeypatch.setattr(batch, "resolve_combined_winner", _fake_resolve(downloads))
    _modern_ready(1, [_pexels(7)], '{"winner_index": 0, "reasoning": "old video"}')
    for path in ("candidates_1.json", "scoring_prompt_1.txt", "scoring_response_1.txt"):
        _age(path, 3600)

    assert batch.apply_modern(envato_profile_dir="env") == {}
    results = batch.apply_modern([1], envato_profile_dir="env")
    assert results[1].status == "error" and "earlier video" in results[1].message and downloads == []


def test_a_response_older_than_its_prompt_is_never_applied(run, monkeypatch):
    downloads = []
    monkeypatch.setattr(batch, "resolve_combined_winner", _fake_resolve(downloads))
    _modern_ready(1, [_pexels(7)], '{"winner_index": 0, "reasoning": "r"}')
    _age("scoring_response_1.txt", 60)

    results = batch.apply_modern([1], envato_profile_dir="env")

    assert results[1].status == "error" and "older than its prompt" in results[1].message and downloads == []


def test_explicit_beat_lists_are_deduplicated_and_put_in_beat_order(run, monkeypatch):
    downloads = []
    monkeypatch.setattr(batch, "resolve_combined_winner", _fake_resolve(downloads))
    _modern_ready(1, [_pexels(7)], '{"winner_index": 0, "reasoning": "r"}')
    _modern_ready(3, [_pexels(9)], '{"winner_index": 0, "reasoning": "r"}')

    results = batch.apply_modern([3, 1, 3], envato_profile_dir="env")

    assert list(results) == [1, 3] and [d[0] for d in downloads] == ["7", "9"]


def test_extract_refuses_an_output_file_for_another_beats_prompt_or_an_older_one(run, tmp_path):
    open("scoring_prompt_1.txt", "w").write("p1")
    open("scoring_prompt_2.txt", "w").write("p2")
    answer = {"message": {"content": [{"type": "text", "text": '{"winner_index": 0, "reasoning": "r"}'}]}}
    other = tmp_path / "other.output"
    other.write_text(json.dumps({"prompt": f"Read {os.path.abspath('scoring_prompt_2.txt')}"}) + "\n" + json.dumps(answer))
    old = tmp_path / "old.output"
    old.write_text(json.dumps({"prompt": f"Read {os.path.abspath('scoring_prompt_1.txt')}"}) + "\n" + json.dumps(answer))
    _age(str(old), 60)

    assert batch.main(["extract", "modern", f"1={other}", f"1={old}"]) == 1
    assert not os.path.exists("scoring_response_1.txt")


def test_a_failing_beat_prints_its_traceback(run, monkeypatch, capsys):
    monkeypatch.setattr(batch, "prepare_combined_scoring", _fake_prepare_combined([], fail_query="q1"))
    monkeypatch.setattr(batch, "record_spend", lambda units, path: None)

    batch.prep_modern([1], workers=1, pexels_api_key="pk", youtube_api_key="yk", envato_profile_dir="env")

    assert "[beat 1] Traceback (most recent call last):" in capsys.readouterr().out


def test_prep_lines_are_printed_while_the_beat_is_still_running(run, monkeypatch, capsys):
    seen_early = []

    def slow(**kw):
        print(f"progress {kw['query']}")
        seen_early.append("[beat 1] progress q1" in capsys.readouterr().out)
        return [_pexels(1)], "p"

    monkeypatch.setattr(batch, "prepare_combined_scoring", slow)
    monkeypatch.setattr(batch, "record_spend", lambda units, path: None)

    batch.prep_modern([1], workers=1, pexels_api_key="pk", youtube_api_key="yk", envato_profile_dir="env")

    assert seen_early == [True]
