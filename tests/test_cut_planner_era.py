import json

import pytest

from shot_list.cut_planner import (
    CutPlannerOutputError, FootageCut, apply_cut_plans, build_cut_planner_prompt, parse_cut_planner_output,
)
from shot_list.models import Beat, FootageSpec, ShotList

_CUTS = [
    FootageCut(0, 0.0, 4.0, "Atlanta in 1847 was a railroad stop", "early Atlanta"),
    FootageCut(1, 4.0, 8.0, "today it is a huge city", "modern Atlanta"),
]


def _reply(*entries):
    return json.dumps({"count": len(entries), "entries": list(entries)})


def _old(i, **extra):
    entry = {"index": i, "query": "railroad depot", "subject": "depot", "era": 1847,
             "archival_query": "Atlanta railroad depot 1840s", "archival_broad_query": "Atlanta Georgia 1840s"}
    entry.update(extra)
    return entry


def _modern(i, query="skyline", **extra):
    entry = {"index": i, "query": query, "subject": "skyline", "era": "modern"}
    entry.update(extra)
    return entry


def test_prompt_explains_the_era_tag_and_the_archival_queries():
    prompt = build_cut_planner_prompt(_CUTS)

    assert '"era"' in prompt and '"archival_query"' in prompt and '"archival_broad_query"' in prompt
    assert "modern" in prompt and "1960" in prompt
    assert "period the words are about" in prompt


def test_an_old_cut_carries_its_year_and_both_archival_queries():
    plans = parse_cut_planner_output(_reply(_old(0), _modern(1)), _CUTS)

    assert plans[0]["era"] == 1847
    assert plans[0]["archival_query"] == "Atlanta railroad depot 1840s"
    assert plans[0]["archival_broad_query"] == "Atlanta Georgia 1840s"
    assert plans[1]["era"] is None and plans[1]["archival_query"] == ""


def test_a_year_as_a_digit_string_is_accepted():
    plans = parse_cut_planner_output(_reply(_old(0, era="1847"), _modern(1)), _CUTS)

    assert plans[0]["era"] == 1847


def test_a_year_of_1960_or_later_is_a_valid_modern_tag_that_needs_no_archival_queries():
    plans = parse_cut_planner_output(_reply(_modern(0, era=1985, query="a"), _modern(1, era=1960, query="b")), _CUTS)

    assert [p["era"] for p in plans] == [1985, 1960]
    assert [p["archival_query"] for p in plans] == ["", ""]


def test_modern_cuts_drop_any_archival_queries_the_planner_wrote_anyway():
    plans = parse_cut_planner_output(
        _reply(_modern(0, archival_query="x y", archival_broad_query="x"), _modern(1, query="b")), _CUTS)

    assert plans[0]["archival_query"] == "" and plans[0]["archival_broad_query"] == ""


@pytest.mark.parametrize("bad_era", [None, "", "later", 12, 3000, True, 1847.5, [1847]])
def test_a_missing_or_malformed_era_stops_loudly(bad_era):
    entry = _modern(0)
    if bad_era is None:
        del entry["era"]
    else:
        entry["era"] = bad_era

    with pytest.raises(CutPlannerOutputError, match="era"):
        parse_cut_planner_output(_reply(entry, _modern(1, query="b")), _CUTS)


@pytest.mark.parametrize("field", ["archival_query", "archival_broad_query"])
@pytest.mark.parametrize("value", ["", "   ", None, 5])
def test_an_old_cut_without_a_usable_archival_query_stops_loudly(field, value):
    entry = _old(0)
    entry[field] = value

    with pytest.raises(CutPlannerOutputError, match=field):
        parse_cut_planner_output(_reply(entry, _modern(1)), _CUTS)


def test_consecutive_old_cuts_must_not_share_an_archival_query():
    cuts = [FootageCut(0, 0.0, 4.0, "a", "s"), FootageCut(1, 4.0, 8.0, "b", "s")]
    raw = _reply(_old(0, query="one"), _old(1, query="two", archival_query="ATLANTA railroad depot 1840s"))

    with pytest.raises(CutPlannerOutputError, match="same archival query"):
        parse_cut_planner_output(raw, cuts)


def test_apply_copies_era_and_queries_onto_the_footage_spec():
    shot_list = ShotList([Beat(0.0, 4.0, "footage", footage=FootageSpec("old", "old subject")),
                          Beat(4.0, 8.0, "footage", footage=FootageSpec("old", "old subject"))], 8.0)
    plans = parse_cut_planner_output(_reply(_old(0), _modern(1)), _CUTS)

    result = apply_cut_plans(shot_list, _CUTS, plans)

    assert result.beats[0].footage == FootageSpec(
        "railroad depot", "depot", era=1847,
        archival_query="Atlanta railroad depot 1840s", archival_broad_query="Atlanta Georgia 1840s")
    assert result.beats[1].footage == FootageSpec("skyline", "skyline")


def test_an_era_before_photography_without_archival_queries_is_rejected():
    entry = _modern(0, era=1781, query="a", archival_query="", archival_broad_query="")

    with pytest.raises(CutPlannerOutputError, match="archival_query"):
        parse_cut_planner_output(_reply(entry, _modern(1, query="b")), _CUTS)


def test_an_era_before_photography_with_archival_queries_returns_them():
    entry = _modern(0, era=1781, query="a", archival_query="Yorktown siege 1781", archival_broad_query="American Revolution")
    plans = parse_cut_planner_output(_reply(entry, _modern(1, query="b")), _CUTS)

    assert plans[0]["era"] == 1781
    assert plans[0]["archival_query"] == "Yorktown siege 1781" and plans[0]["archival_broad_query"] == "American Revolution"


def test_a_cut_at_the_first_photography_year_still_needs_archival_queries():
    entry = _old(0, era=1839, archival_query="")

    with pytest.raises(CutPlannerOutputError, match="archival_query"):
        parse_cut_planner_output(_reply(entry, _modern(1)), _CUTS)


def test_the_prompt_says_a_year_before_1900_may_show_real_artwork_and_needs_archival_queries():
    prompt = build_cut_planner_prompt(_CUTS)

    assert "painting" in prompt and "1900" in prompt
    assert "needs no archival queries" not in prompt
    assert "adds medium words" not in prompt  # nothing in the artwork search adds medium words


def test_a_missing_era_error_tells_the_operator_to_rerun_step_6b_ii():
    entry = _modern(0)
    del entry["era"]

    with pytest.raises(CutPlannerOutputError, match=r'cut 0 entry needs "era".*got None.*re-run Step 6b-ii'):
        parse_cut_planner_output(_reply(entry, _modern(1, query="b")), _CUTS)
