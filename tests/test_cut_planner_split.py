"""Step 6b split cuts: a footage cut whose words name several visualizable things becomes several
footage beats, one per piece, each starting as its words are spoken.

The fixture is a real cut from the 2026-10-08 power-grid video (word times from its
word_timings.json): 'Oil has tank farms, grain has silos, water has towers.' (30.65 to 35.98 s)
was planned as one oil clip; it must show oil, then grain silos, then water towers."""
import dataclasses
import json

import pytest

from assembly.beats import resolve_beat_clips
from footage.shotlist_integration import archival_beats, footage_beats
from motion_graphics.shotlist_integration import graphic_beats
from shot_list.align import WordTiming
from shot_list.cut_planner import (
    MAX_PIECES, MIN_PIECE_SECONDS, CutPlannerOutputError, FootageCut, apply_cut_plans,
    build_cut_planner_prompt, footage_cuts, format_cut_plan_report, parse_cut_planner_output,
)
from shot_list.models import Beat, FootageSpec, GraphicSpec, ShotList, beat_from_dict, validate_shot_list

CUT_END = 35.97833333333333
NEXT_END = 41.306666666666665

# Real word times around the cut (word_timings.json of the 2026-10-08 run).
REAL_WORDS = [
    ("a", 29.84, 30.0), ("buffer.", 30.0, 30.36),
    ("Oil", 30.94, 31.14), ("has", 31.14, 31.44), ("tank", 31.44, 31.68), ("farms,", 31.68, 32.14),
    ("grain", 32.54, 32.74), ("has", 32.74, 33.1), ("silos,", 33.1, 33.48),
    ("water", 34.12, 34.34), ("has", 34.34, 34.78), ("towers.", 34.78, 35.14),
    ("Electricity", 35.74, 36.1), ("has", 36.1, 36.62), ("no", 36.7, 36.9), ("warehouse.", 36.9, 37.6),
]


def _timings():
    return [WordTiming(word=w, start=s, end=e) for w, s, e in REAL_WORDS]


def _shot_list():
    return ShotList(beats=[
        Beat(0.0, 30.65, "talking_head"),
        Beat(30.65, CUT_END, "footage", footage=FootageSpec(
            "oil storage tanks Cushing Oklahoma aerial",
            "The oil tank farm at Cushing, Oklahoma, the literal storage the words name")),
        Beat(CUT_END, NEXT_END, "footage", footage=FootageSpec(
            "power plant cooling towers Ohio River", "A power plant on the Ohio River")),
        Beat(NEXT_END, 45.0, "graphic", graphic=GraphicSpec("chart_card", {"title": "x"})),
    ], duration=45.0)


def _piece(start, end, words, query, subject="s", era="modern", **extra):
    piece = {"start": start, "end": end, "words": words, "query": query, "subject": subject, "era": era}
    piece.update(extra)
    return piece


OIL_GRAIN_WATER = [
    _piece(30.65, 32.54, "Oil has tank farms,", "oil storage tanks Cushing Oklahoma aerial", "oil tank farm"),
    _piece(32.54, 34.12, "grain has silos,", "grain silos elevator Kansas prairie", "grain silos"),
    _piece(34.12, 35.978, "water has towers. Electricity", "water tower small town Iowa", "water tower"),
]


def _reply(*entries):
    return json.dumps({"count": len(entries), "entries": list(entries)})


def _single(i, query="power plant cooling towers Ohio River", **extra):
    entry = {"index": i, "query": query, "subject": "power plant", "era": "modern"}
    entry.update(extra)
    return entry


def _cuts():
    return footage_cuts(_shot_list(), _timings())


# ---- footage_cuts and the prompt ----

def test_footage_cuts_carry_the_word_start_times_of_their_words():
    cuts = _cuts()

    assert cuts[0].word_times == (
        ("Oil", 30.94), ("has", 31.14), ("tank", 31.44), ("farms,", 31.68), ("grain", 32.54),
        ("has", 32.74), ("silos,", 33.1), ("water", 34.12), ("has", 34.34), ("towers.", 34.78),
        ("Electricity", 35.74))
    assert cuts[0].words == "Oil has tank farms, grain has silos, water has towers. Electricity"


def test_prompt_shows_exact_cut_bounds_and_each_word_start_time():
    prompt = build_cut_planner_prompt(_cuts())

    assert "exact start 30.650" in prompt and "exact end 35.978" in prompt
    assert "grain@32.540" in prompt and "water@34.120" in prompt and "Oil@30.940" in prompt


def test_prompt_explains_when_and_how_to_split():
    prompt = build_cut_planner_prompt(_cuts())

    assert '"pieces"' in prompt
    assert "1.3 seconds" in prompt and "4 pieces" in prompt
    assert "word start" in prompt
    assert "from A to B" in prompt and "versus" in prompt
    assert "one continuous subject" in prompt  # do not split
    assert "Oil has tank farms, grain has silos, water has towers" in prompt  # the worked example


# ---- parsing ----

def test_the_oil_grain_water_cut_parses_into_three_pieces_on_real_word_starts():
    plans = parse_cut_planner_output(_reply({"index": 0, "pieces": OIL_GRAIN_WATER}, _single(1)), _cuts())

    pieces = plans[0]["pieces"]
    assert [(p["start"], p["end"]) for p in pieces] == [(30.65, 32.54), (32.54, 34.12), (34.12, CUT_END)]
    assert [p["words"] for p in pieces] == [
        "Oil has tank farms,", "grain has silos,", "water has towers. Electricity"]
    assert [p["query"] for p in pieces] == [
        "oil storage tanks Cushing Oklahoma aerial", "grain silos elevator Kansas prairie",
        "water tower small town Iowa"]
    assert all(p["era"] is None and p["archival_query"] == "" for p in pieces)
    assert plans[1]["query"] == "power plant cooling towers Ohio River" and "pieces" not in plans[1]


def test_rounded_boundaries_snap_to_the_exact_cut_bounds_and_word_starts():
    pieces = [dict(p) for p in OIL_GRAIN_WATER]
    pieces[2]["end"] = 35.98  # the cut ends at 35.97833...
    pieces[1]["end"] = pieces[2]["start"] = 34.1203

    plans = parse_cut_planner_output(_reply({"index": 0, "pieces": pieces}, _single(1)), _cuts())

    assert plans[0]["pieces"][2]["end"] == CUT_END
    assert plans[0]["pieces"][1]["end"] == plans[0]["pieces"][2]["start"] == 34.12


def test_a_boundary_written_slightly_differently_in_end_and_start_still_snaps_to_one_word_start():
    pieces = [dict(p) for p in OIL_GRAIN_WATER]
    pieces[0]["end"], pieces[1]["start"] = 32.544, 32.5355  # both within 5 ms of "grain" (32.54)

    plans = parse_cut_planner_output(_reply({"index": 0, "pieces": pieces}, _single(1)), _cuts())

    assert plans[0]["pieces"][0]["end"] == plans[0]["pieces"][1]["start"] == 32.54


def test_an_inner_boundary_at_the_cut_end_explains_the_next_piece_would_be_empty():
    pieces = [dict(p) for p in OIL_GRAIN_WATER[:2]]
    pieces[1]["end"] = 35.978
    pieces.append(_piece(35.978, 35.978, "x", "water tower small town Iowa"))

    with pytest.raises(CutPlannerOutputError, match=r"cut 0 piece 1 ends at the cut's end.*piece 2"):
        parse_cut_planner_output(_reply({"index": 0, "pieces": pieces}, _single(1)), _cuts())


def test_a_boundary_that_is_not_a_word_start_is_rejected():
    pieces = [dict(p) for p in OIL_GRAIN_WATER]
    pieces[0]["end"] = pieces[1]["start"] = 32.3  # between "farms," and "grain"

    with pytest.raises(CutPlannerOutputError, match=r"cut 0 piece 1 starts at 32.3.*not the start of a word"):
        parse_cut_planner_output(_reply({"index": 0, "pieces": pieces}, _single(1)), _cuts())


def test_pieces_that_overlap_are_a_tiling_violation():
    pieces = [dict(p) for p in OIL_GRAIN_WATER]
    pieces[1]["start"] = 32.14 + 0.0  # piece 0 still ends at 32.54: overlap

    with pytest.raises(CutPlannerOutputError, match=r"cut 0 piece 1 starts at 32.140 but piece 0 ends at 32.540"):
        parse_cut_planner_output(_reply({"index": 0, "pieces": pieces}, _single(1)), _cuts())


@pytest.mark.parametrize("field,value,message", [
    ("first_start", 30.94, r"cut 0 piece 0 must start at the cut's start 30.650"),
    ("last_end", 35.74, r"cut 0 piece 2 must end at the cut's end 35.978"),
])
def test_pieces_must_cover_the_whole_cut(field, value, message):
    pieces = [dict(p) for p in OIL_GRAIN_WATER]
    if field == "first_start":
        pieces[0]["start"] = value
    else:
        pieces[2]["end"] = value

    with pytest.raises(CutPlannerOutputError, match=message):
        parse_cut_planner_output(_reply({"index": 0, "pieces": pieces}, _single(1)), _cuts())


def test_a_piece_shorter_than_the_minimum_is_rejected():
    # "Oil has tank" (30.65-31.68 = 1.03 s) then "farms, grain has silos," ...
    pieces = [
        _piece(30.65, 31.68, "Oil has tank", "oil storage tanks Cushing Oklahoma aerial"),
        _piece(31.68, 34.12, "farms, grain has silos,", "grain silos elevator Kansas prairie"),
        _piece(34.12, 35.978, "water has towers. Electricity", "water tower small town Iowa"),
    ]

    with pytest.raises(CutPlannerOutputError, match=r"cut 0 piece 0 .*1.03 s.*at least 1.3 s"):
        parse_cut_planner_output(_reply({"index": 0, "pieces": pieces}, _single(1)), _cuts())
    assert MIN_PIECE_SECONDS == 1.3


def test_more_than_four_pieces_is_rejected():
    cut = FootageCut(0, 0.0, 6.0, "a b c d e", "s",
                     word_times=(("a", 0.0), ("b", 1.2), ("c", 2.4), ("d", 3.6), ("e", 4.8)))
    pieces = [_piece(1.2 * k, 1.2 * (k + 1) if k < 4 else 6.0, "w", f"query {k}") for k in range(5)]
    # 1.2 s pieces would also be too short; the count check comes first
    assert MAX_PIECES == 4

    with pytest.raises(CutPlannerOutputError, match=r"cut 0 has 5 pieces; at most 4"):
        parse_cut_planner_output(_reply({"index": 0, "pieces": pieces}), [cut])


def test_a_single_piece_is_rejected_as_not_a_split():
    pieces = [_piece(30.65, CUT_END, "all", "oil storage tanks Cushing Oklahoma aerial")]

    with pytest.raises(CutPlannerOutputError, match=r"cut 0 has 1 piece"):
        parse_cut_planner_output(_reply({"index": 0, "pieces": pieces}, _single(1)), _cuts())


def test_an_entry_with_both_pieces_and_a_query_is_ambiguous():
    entry = {"index": 0, "pieces": OIL_GRAIN_WATER, "query": "x y", "subject": "s", "era": "modern"}

    with pytest.raises(CutPlannerOutputError, match=r"cut 0 entry has both"):
        parse_cut_planner_output(_reply(entry, _single(1)), _cuts())


@pytest.mark.parametrize("bad", [
    {"query": ""}, {"subject": "  "}, {"era": "later"}, {"start": "30.65"}, {"words": None},
])
def test_a_piece_with_a_bad_field_is_rejected(bad):
    pieces = [dict(p) for p in OIL_GRAIN_WATER]
    pieces[0].update(bad)

    with pytest.raises(CutPlannerOutputError, match=r"cut 0 piece 0"):
        parse_cut_planner_output(_reply({"index": 0, "pieces": pieces}, _single(1)), _cuts())


def test_pieces_must_be_a_list_of_objects():
    with pytest.raises(CutPlannerOutputError, match=r"cut 0"):
        parse_cut_planner_output(_reply({"index": 0, "pieces": "oil, grain"}, _single(1)), _cuts())
    with pytest.raises(CutPlannerOutputError, match=r"cut 0 piece 1"):
        parse_cut_planner_output(_reply({"index": 0, "pieces": [OIL_GRAIN_WATER[0], 5]}, _single(1)), _cuts())


def test_an_archival_piece_needs_both_archival_queries():
    cut = FootageCut(0, 161.0, 166.4, "physicist William Stanley - backed by industrialist George Westinghouse",
                     "AC history", word_times=(("physicist", 161.1), ("William", 161.6), ("Stanley", 162.0),
                                               ("-", 162.6), ("backed", 162.7), ("by", 163.0),
                                               ("industrialist", 163.3), ("George", 164.0), ("Westinghouse", 164.4)))
    good = [
        _piece(161.0, 163.3, "physicist William Stanley - backed by", "old industrial town Massachusetts 1880s",
               era=1886, archival_query="William Stanley Jr. inventor portrait 1880s",
               archival_broad_query="Massachusetts 1880s"),
        _piece(163.3, 166.4, "industrialist George Westinghouse", "historic industrial buildings Pittsburgh",
               era=1886, archival_query="George Westinghouse portrait Pittsburgh 1880s",
               archival_broad_query="Pittsburgh 1880s"),
    ]
    plans = parse_cut_planner_output(_reply({"index": 0, "pieces": good}), [cut])
    assert [p["era"] for p in plans[0]["pieces"]] == [1886, 1886]
    assert plans[0]["pieces"][1]["archival_broad_query"] == "Pittsburgh 1880s"

    bad = [dict(p) for p in good]
    bad[1]["archival_query"] = ""
    with pytest.raises(CutPlannerOutputError, match=r"cut 0 piece 1 .*archival_query"):
        parse_cut_planner_output(_reply({"index": 0, "pieces": bad}), [cut])


def test_consecutive_pieces_must_not_share_a_query():
    pieces = [dict(p) for p in OIL_GRAIN_WATER]
    pieces[1]["query"] = pieces[0]["query"].upper()

    with pytest.raises(CutPlannerOutputError, match="same query"):
        parse_cut_planner_output(_reply({"index": 0, "pieces": pieces}, _single(1)), _cuts())


def test_the_last_piece_and_the_next_cut_must_not_share_a_query():
    raw = _reply({"index": 0, "pieces": OIL_GRAIN_WATER}, _single(1, query="Water Tower small town Iowa"))

    with pytest.raises(CutPlannerOutputError, match="same query"):
        parse_cut_planner_output(raw, _cuts())


# ---- applying ----

def test_apply_replaces_the_cut_by_one_footage_beat_per_piece_numbered_in_order():
    shot_list, cuts = _shot_list(), _cuts()
    plans = parse_cut_planner_output(_reply({"index": 0, "pieces": OIL_GRAIN_WATER}, _single(1)), cuts)

    result = apply_cut_plans(shot_list, cuts, plans)

    assert [(b.start, b.end, b.type) for b in result.beats] == [
        (0.0, 30.65, "talking_head"),
        (30.65, 32.54, "footage"), (32.54, 34.12, "footage"), (34.12, CUT_END, "footage"),
        (CUT_END, NEXT_END, "footage"), (NEXT_END, 45.0, "graphic"),
    ]
    assert result.beats[2].footage == FootageSpec("grain silos elevator Kansas prairie", "grain silos")
    assert result.beats[4].footage.query == "power plant cooling towers Ohio River"
    assert result.beats[5] == shot_list.beats[3]
    assert result.duration == 45.0


def test_apply_copies_era_and_archival_queries_onto_each_piece_beat():
    shot_list = ShotList([Beat(0.0, 5.0, "footage", footage=FootageSpec("q", "s"))], 5.0)
    cut = FootageCut(0, 0.0, 5.0, "Stanley Westinghouse", "s", word_times=(("Stanley", 0.2), ("Westinghouse", 2.5)))
    plans = [{"pieces": [
        {"start": 0.0, "end": 2.5, "words": "Stanley", "query": "a", "subject": "sa", "era": 1886,
         "archival_query": "Stanley 1880s", "archival_broad_query": "Massachusetts 1880s"},
        {"start": 2.5, "end": 5.0, "words": "Westinghouse", "query": "b", "subject": "sb", "era": None,
         "archival_query": "", "archival_broad_query": ""},
    ]}]

    result = apply_cut_plans(shot_list, [cut], plans)

    assert result.beats[0].footage == FootageSpec("a", "sa", era=1886, archival_query="Stanley 1880s",
                                                   archival_broad_query="Massachusetts 1880s")
    assert result.beats[1].footage == FootageSpec("b", "sb")


def test_apply_rejects_pieces_that_do_not_tile_the_beat():
    shot_list = ShotList([Beat(0.0, 5.0, "footage", footage=FootageSpec("q", "s"))], 5.0)
    cut = FootageCut(0, 0.0, 5.0, "x y", "s", word_times=(("x", 0.2), ("y", 2.5)))
    plans = [{"pieces": [
        {"start": 0.0, "end": 2.5, "words": "x", "query": "a", "subject": "s", "era": None,
         "archival_query": "", "archival_broad_query": ""},
        {"start": 2.6, "end": 5.0, "words": "y", "query": "b", "subject": "s", "era": None,
         "archival_query": "", "archival_broad_query": ""},
    ]}]

    with pytest.raises(ValueError):
        apply_cut_plans(shot_list, [cut], plans)


def test_report_prints_each_cut_and_its_pieces():
    cuts = _cuts()
    plans = parse_cut_planner_output(_reply({"index": 0, "pieces": OIL_GRAIN_WATER}, _single(1)), cuts)

    report = format_cut_plan_report(cuts, plans)

    lines = report.splitlines()
    assert lines[0].startswith('30.6-36.0s "Oil has tank farms, grain has silos, water has towers. Electricity"')
    assert "split into 3 pieces" in lines[0]
    assert lines[1].strip().startswith('30.65-32.54s "Oil has tank farms," -> ')
    assert "'grain silos elevator Kansas prairie'" in lines[2] and "era: modern" in lines[2]
    assert lines[3].strip().startswith('34.12-35.98s "water has towers. Electricity"')
    assert lines[4].startswith('36.0-41.3s "has no warehouse." -> ')
    assert "1 cut split into 3 pieces" in lines[-1] and "4 footage beats" in lines[-1]


# ---- end to end through every later stage's readers ----

def test_end_to_end_split_shot_list_feeds_stage_2_3_and_4_unchanged(tmp_path, monkeypatch):
    shot_list = _shot_list()
    cuts = footage_cuts(shot_list, _timings())
    prompt = build_cut_planner_prompt(cuts)
    assert "grain@32.540" in prompt
    plans = parse_cut_planner_output(_reply({"index": 0, "pieces": OIL_GRAIN_WATER}, _single(1)), cuts)
    updated = apply_cut_plans(shot_list, cuts, plans)

    # shot_list.json round trip, as Stage 2/3/4 read it
    path = tmp_path / "shot_list.json"
    path.write_text(json.dumps(dataclasses.asdict(updated), indent=2))
    raw = json.loads(path.read_text())
    reloaded = ShotList(beats=[beat_from_dict(b) for b in raw["beats"]], duration=raw["duration"])
    validate_shot_list(reloaded)
    assert reloaded == updated

    # Stage 2: sequential beat numbers, one beat per piece
    assert footage_beats(reloaded) == [
        (1, "oil storage tanks Cushing Oklahoma aerial", "oil tank farm"),
        (2, "grain silos elevator Kansas prairie", "grain silos"),
        (3, "water tower small town Iowa", "water tower"),
        (4, "power plant cooling towers Ohio River", "power plant"),
    ]
    assert archival_beats(reloaded) == []

    # Stage 3: the graphic beat moved from index 3 to 5 and keeps its duration
    assert [(i, spec.archetype, round(d, 6)) for i, spec, d in graphic_beats(reloaded)] == [
        (5, "chart_card", round(45.0 - NEXT_END, 6))]

    # Stage 4: clips are looked up by the new sequential numbers
    monkeypatch.chdir(tmp_path)
    (tmp_path / "footage_output").mkdir()
    (tmp_path / "graphics_output").mkdir()
    for i in (1, 2, 3, 4):
        (tmp_path / "footage_output" / f"beat_{i}.mp4").write_bytes(b"x")
    (tmp_path / "graphics_output" / "beat_5.mp4").write_bytes(b"x")
    clips = resolve_beat_clips(reloaded)
    assert [(c.index, c.type, c.source_path) for c in clips] == [
        (0, "talking_head", ""),
        (1, "footage", "footage_output/beat_1.mp4"), (2, "footage", "footage_output/beat_2.mp4"),
        (3, "footage", "footage_output/beat_3.mp4"), (4, "footage", "footage_output/beat_4.mp4"),
        (5, "graphic", "graphics_output/beat_5.mp4"),
    ]
    assert [(c.start, c.end) for c in clips][1:4] == [(30.65, 32.54), (32.54, 34.12), (34.12, CUT_END)]
