import json

from shot_list.align import WordTiming
from shot_list.cut_planner import (
    FootageCut,
    build_cut_planner_prompt,
    footage_cuts,
    load_shot_list,
    words_in_range,
)
from shot_list.models import Beat, FootageSpec, GraphicSpec, ShotList


def _words(*triples):
    return [WordTiming(word=w, start=s, end=e) for w, s, e in triples]


def test_words_in_range_returns_words_starting_inside_range_in_order():
    timings = _words(("a", 0.0, 0.4), ("b", 1.0, 1.4), ("c", 2.0, 2.4), ("d", 3.0, 3.4))

    assert words_in_range(timings, 1.0, 3.0) == "b c"


def test_word_starting_exactly_on_boundary_belongs_to_later_range_only():
    timings = _words(("a", 0.0, 0.4), ("b", 2.0, 2.4))

    assert words_in_range(timings, 0.0, 2.0) == "a"
    assert words_in_range(timings, 2.0, 4.0) == "b"


def test_words_in_range_empty_when_no_word_starts_inside():
    timings = _words(("a", 0.0, 0.4), ("b", 5.0, 5.4))

    assert words_in_range(timings, 1.0, 4.0) == ""


def _shot_list():
    return ShotList(
        beats=[
            Beat(0.0, 4.0, "graphic", graphic=GraphicSpec("territory_map", {"x": 1})),
            Beat(4.0, 8.0, "footage", footage=FootageSpec("old q", "old subject")),
            Beat(8.0, 12.0, "footage", footage=FootageSpec("old q", "old subject")),
        ],
        duration=12.0,
    )


def test_footage_cuts_skips_graphic_beats_and_records_beat_index():
    timings = _words(("hello", 1.0, 1.4), ("same", 4.5, 4.9), ("tropical", 5.0, 5.4), ("climate", 9.0, 9.4))

    cuts = footage_cuts(_shot_list(), timings)

    assert cuts == [
        FootageCut(beat_index=1, start=4.0, end=8.0, words="same tropical", director_subject="old subject"),
        FootageCut(beat_index=2, start=8.0, end=12.0, words="climate", director_subject="old subject"),
    ]


def test_footage_cuts_omits_a_footage_beat_with_no_spoken_words():
    timings = _words(("hello", 1.0, 1.4), ("climate", 9.0, 9.4))  # nothing starts in 4.0-8.0

    cuts = footage_cuts(_shot_list(), timings)

    assert [c.beat_index for c in cuts] == [2]


def test_load_shot_list_round_trips_a_saved_shot_list(tmp_path):
    import dataclasses

    original = _shot_list()
    path = tmp_path / "shot_list.json"
    path.write_text(json.dumps(dataclasses.asdict(original)))

    assert load_shot_list(str(path)) == original


_CUTS = [
    FootageCut(beat_index=1, start=4.0, end=8.0, words="same language same tropical climate",
               director_subject="Central America colonial towns"),
    FootageCut(beat_index=2, start=8.0, end=12.0, words="and mostly the same independence from Spain",
               director_subject="Central America colonial towns"),
]


def test_prompt_lists_every_cut_with_index_time_words_and_director_subject():
    prompt = build_cut_planner_prompt(_CUTS)

    assert "[0]" in prompt and "[1]" in prompt
    assert "4.0s-8.0s" in prompt and "8.0s-12.0s" in prompt
    assert "same language same tropical climate" in prompt
    assert "and mostly the same independence from Spain" in prompt
    assert "Central America colonial towns" in prompt


def test_prompt_includes_neighbour_words_for_context():
    prompt = build_cut_planner_prompt(_CUTS)

    # cut 1 shows the previous cut's words as "previous", cut 0 shows the next cut's words
    assert "previous: same language same tropical climate" in prompt
    assert "next: and mostly the same independence from Spain" in prompt


def test_prompt_states_the_planning_rules():
    prompt = build_cut_planner_prompt(_CUTS)

    assert "literally" in prompt  # show what is said
    assert "specific place" in prompt  # name a place, not just a region
    assert "never have the same idea" in prompt  # consecutive cuts differ
    assert "filler" in prompt  # abstract-words fallback
    assert "title card" in prompt  # visual, no title cards / text screens


def test_prompt_demands_json_with_count_and_one_entry_per_cut():
    prompt = build_cut_planner_prompt(_CUTS)

    assert '"count": 2' in prompt
    assert '"query"' in prompt and '"subject"' in prompt


import pytest

from shot_list.cut_planner import CutPlannerOutputError, apply_cut_plans, parse_cut_planner_output


def _reply(*entries, count=None):
    return json.dumps({"count": count if count is not None else len(entries), "entries": list(entries)})


def _entry(i, query="tropical beach palm trees", subject="a beach"):
    return {"index": i, "query": query, "subject": subject, "era": "modern"}


def test_parse_returns_plans_in_cut_order():
    raw = _reply(_entry(0, "colonial plaza Antigua Guatemala", "Antigua plaza"),
                 _entry(1, "tropical beach palm trees Costa Rica", "Costa Rica beach"))

    assert parse_cut_planner_output(raw, _CUTS) == [
        {"query": "colonial plaza Antigua Guatemala", "subject": "Antigua plaza",
         "era": None, "archival_query": "", "archival_broad_query": ""},
        {"query": "tropical beach palm trees Costa Rica", "subject": "Costa Rica beach",
         "era": None, "archival_query": "", "archival_broad_query": ""},
    ]


def test_parse_strips_a_json_code_fence():
    raw = "```json\n" + _reply(_entry(0, "a b c"), _entry(1, "d e f")) + "\n```"

    assert len(parse_cut_planner_output(raw, _CUTS)) == 2


@pytest.mark.parametrize("raw", [
    "not json at all",
    "[1, 2]",
    json.dumps({"count": 2}),
    _reply(_entry(0)),  # too few entries
    _reply(_entry(0), _entry(1), _entry(2)),  # too many entries
    _reply(_entry(0), _entry(5)),  # index 1 missing
    _reply(_entry(0), {"index": 1, "query": "", "subject": "x"}),  # blank query
    _reply(_entry(0), {"index": 1, "query": "a b", "subject": "   "}),  # blank subject
    _reply(_entry(0), {"index": 1, "query": 5, "subject": "x"}),  # non-string query
    _reply(_entry(0), {"index": 1, "query": "a b"}),  # subject missing
    _reply(_entry(0), "just a string"),  # entry not an object
    _reply(_entry(0), {"index": [0], "query": "a b", "subject": "x"}),  # unhashable index (list)
    _reply(_entry(0), {"index": {}, "query": "a b", "subject": "x"}),  # unhashable index (dict)
    _reply(_entry(0), {"index": True, "query": "a b", "subject": "x"}),  # bool index (not int)
    _reply(_entry(0), {"index": 1.0, "query": "a b", "subject": "x"}),  # float index (not int)
])
def test_parse_raises_cut_planner_error_on_bad_output(raw):
    with pytest.raises(CutPlannerOutputError):
        parse_cut_planner_output(raw, _CUTS)


def test_parse_rejects_the_same_query_on_consecutive_cuts_case_insensitively():
    raw = _reply(_entry(0, "Tropical Beach"), _entry(1, "tropical beach"))

    with pytest.raises(CutPlannerOutputError, match="same query"):
        parse_cut_planner_output(raw, _CUTS)


def _mixed_shot_list():
    return ShotList(
        beats=[
            Beat(0.0, 4.0, "graphic", graphic=GraphicSpec("territory_map", {"x": 1})),
            Beat(4.0, 8.0, "footage", footage=FootageSpec("old q", "old subject")),
            Beat(8.0, 10.0, "footage", footage=FootageSpec("silent q", "silent subject")),
            Beat(10.0, 14.0, "footage", footage=FootageSpec("old q", "old subject")),
        ],
        duration=14.0,
    )


def test_apply_replaces_only_planned_footage_beats_and_keeps_everything_else():
    shot_list = _mixed_shot_list()
    cuts = [
        FootageCut(beat_index=1, start=4.0, end=8.0, words="w1", director_subject="old subject"),
        FootageCut(beat_index=3, start=10.0, end=14.0, words="w2", director_subject="old subject"),
    ]  # beat 2 (no spoken words) is not a planned cut
    plans = [{"query": "q one", "subject": "s one"}, {"query": "q two", "subject": "s two"}]

    result = apply_cut_plans(shot_list, cuts, plans)

    assert result.beats[0] == shot_list.beats[0]  # graphic untouched
    assert result.beats[1].footage == FootageSpec("q one", "s one")
    assert result.beats[2].footage == FootageSpec("silent q", "silent subject")  # fallback kept
    assert result.beats[3].footage == FootageSpec("q two", "s two")
    assert [(b.start, b.end, b.type) for b in result.beats] == [(b.start, b.end, b.type) for b in shot_list.beats]
    assert result.duration == 14.0


def test_apply_does_not_mutate_the_input_shot_list():
    shot_list = _mixed_shot_list()
    cuts = [FootageCut(beat_index=1, start=4.0, end=8.0, words="w1", director_subject="old subject")]

    apply_cut_plans(shot_list, cuts, [{"query": "q one", "subject": "s one"}])

    assert shot_list.beats[1].footage == FootageSpec("old q", "old subject")


def test_apply_raises_when_plan_count_does_not_match_cut_count():
    cuts = [FootageCut(beat_index=1, start=4.0, end=8.0, words="w1", director_subject="s")]

    with pytest.raises(ValueError):
        apply_cut_plans(_mixed_shot_list(), cuts, [])


def test_apply_raises_when_a_cut_points_at_a_non_footage_beat():
    cuts = [FootageCut(beat_index=0, start=0.0, end=4.0, words="w", director_subject="s")]

    with pytest.raises(ValueError):
        apply_cut_plans(_mixed_shot_list(), cuts, [{"query": "q", "subject": "s"}])
