import json

import pytest

from footage.archival_scoring import (
    MAX_PHOTO_PICKS, ArchivalVerdict, build_archival_scoring_prompt, parse_archival_verdict,
)
from footage.archive_types import ArchiveCandidate
from footage.scoring_output import ScoringOutputError


def _c(kind, i, **over):
    base = dict(source="ia" if kind == "film" else "loc", item_id=str(i), kind=kind, title=f"Title {i}", year=1938,
                creator="Maker", rights="Public domain", page_url="p", media_url="m", thumbnail_url="t",
                width=1600, height=1200, duration_seconds=45.0 if kind == "film" else 0.0)
    base.update(over)
    return ArchiveCandidate(**base)


def test_the_photo_prompt_lists_every_candidate_with_its_thumbnail_and_the_era():
    prompt = build_archival_scoring_prompt(
        "photo", "Atlanta railroad depot", 1847, "Atlanta depot 1840s",
        [_c("photo", 0, year=1864), _c("photo", 1, year=None)], ["/t/0.jpg", "/t/1.jpg"], 4.0)

    assert "[0]" in prompt and "/t/0.jpg" in prompt and "[1]" in prompt and "/t/1.jpg" in prompt
    assert "1847" in prompt and "Atlanta railroad depot" in prompt
    assert "year=1864" in prompt and "year=unknown" in prompt
    assert '"picks"' in prompt and "1 to 3" in prompt


def test_the_film_prompt_states_the_cut_length_and_asks_for_a_winner_or_null():
    prompt = build_archival_scoring_prompt("film", "street scene", 1938, "q", [_c("film", 0)], ["/t/0.jpg"], 5.5)

    assert "duration=45s" in prompt and "5.5" in prompt
    assert '"winner_index"' in prompt and "null" in prompt


@pytest.mark.parametrize("kind", ["film", "photo"])
def test_both_prompts_enforce_the_archival_rules(kind):
    cand = [_c(kind, 0)]
    prompt = build_archival_scoring_prompt(kind, "s", 1938, "q", cand, ["/t/0.jpg"], 4.0)

    assert "within about a decade" in prompt            # era match
    assert "graphic" in prompt.lower()                        # not too graphic
    assert "title card" in prompt                       # no text-only screens
    assert "colorized" in prompt                        # real imagery only
    assert "rejected" in prompt                         # a reason per rejection for the review sheet


def test_a_photo_verdict_gives_ordered_picks_and_rejection_reasons():
    raw = json.dumps({"picks": [2, 0], "rejected": [{"index": 1, "reason": "modern building"}], "reasoning": "best"})

    assert parse_archival_verdict(raw, 4, "photo") == ArchivalVerdict([2, 0], {1: "modern building"}, "best")


def test_a_code_fence_is_stripped():
    raw = "```json\n" + json.dumps({"picks": [0], "reasoning": "ok"}) + "\n```"

    assert parse_archival_verdict(raw, 2, "photo").picks == [0]


@pytest.mark.parametrize("picks", [[], [5], [-1], [0, 0], [0, 1, 2, 3], ["0"], [True], "0", None])
def test_a_bad_photo_pick_list_stops_loudly(picks):
    raw = json.dumps({"picks": picks, "reasoning": "x"})

    with pytest.raises(ScoringOutputError):
        parse_archival_verdict(raw, 4, "photo")


def test_the_most_a_cut_may_take_is_three():
    assert MAX_PHOTO_PICKS == 3


def test_a_film_winner_and_a_null_winner():
    assert parse_archival_verdict(json.dumps({"winner_index": 1, "reasoning": "x"}), 2, "film").picks == [1]
    none = parse_archival_verdict(json.dumps({"winner_index": None, "reasoning": "all graphic"}), 2, "film")
    assert none.picks == [] and none.reasoning == "all graphic"


@pytest.mark.parametrize("raw", [
    json.dumps({"reasoning": "winner key missing"}),
    json.dumps({"winner_index": 9, "reasoning": "x"}),
    json.dumps({"winner_index": True, "reasoning": "x"}),
    "not json", "[1]",
])
def test_a_bad_film_verdict_stops_loudly(raw):
    with pytest.raises(ScoringOutputError):
        parse_archival_verdict(raw, 2, "film")


@pytest.mark.parametrize("rejected", ["x", [{"index": 9, "reason": "r"}], [{"index": 0}], [{"index": 0, "reason": 5}], ["a"]])
def test_a_malformed_rejected_list_stops_loudly(rejected):
    raw = json.dumps({"picks": [0], "rejected": rejected, "reasoning": "x"})

    with pytest.raises(ScoringOutputError, match="rejected"):
        parse_archival_verdict(raw, 2, "photo")


def test_the_photo_prompt_relaxes_only_quality_and_allows_an_empty_pick_list():
    prompt = build_archival_scoring_prompt("photo", "s", 1938, "q", [_c("photo", 0)], ["/t/0.jpg"], 4.0)

    assert "relax only quality" in prompt and "empty" in prompt and '"picks"' in prompt
    assert "MUST pick at least one" not in prompt


def test_a_bad_kind_or_mismatched_lists_stop_loudly():
    with pytest.raises(ValueError):
        build_archival_scoring_prompt("video", "s", 1938, "q", [_c("photo", 0)], ["/t/0.jpg"], 4.0)
    with pytest.raises(ValueError):
        build_archival_scoring_prompt("photo", "s", 1938, "q", [_c("photo", 0)], [], 4.0)
    with pytest.raises(ScoringOutputError):
        parse_archival_verdict(json.dumps({"picks": [0]}), 2, "video")


def test_a_film_candidate_can_list_several_frames_and_the_prompt_says_to_view_them_all():
    prompt = build_archival_scoring_prompt(
        "film", "street scene", 1938, "q", [_c("film", 0), _c("film", 1)],
        [["/f/a_0.jpg", "/f/a_1.jpg", "/f/a_2.jpg"], "/f/b.jpg"], 5.5)

    assert "/f/a_0.jpg" in prompt and "/f/a_1.jpg" in prompt and "/f/a_2.jpg" in prompt and "/f/b.jpg" in prompt
    assert "view all frames of each clip" in prompt
    assert "part that will be played" in prompt and "graphic content" in prompt


def test_frame_lists_keep_the_parallel_length_check():
    with pytest.raises(ValueError):
        build_archival_scoring_prompt("film", "s", 1938, "q", [_c("film", 0), _c("film", 1)], [["/f/a.jpg"]], 4.0)


def test_a_pick_that_is_also_rejected_is_contradictory_and_stops_loudly():
    raw = json.dumps({"picks": [0, 1], "rejected": [{"index": 1, "reason": "modern"}], "reasoning": "r"})

    with pytest.raises(ScoringOutputError, match="rejected"):
        parse_archival_verdict(raw, 3, "photo")
    film = json.dumps({"winner_index": 0, "rejected": [{"index": 0, "reason": "titles"}], "reasoning": "r"})
    with pytest.raises(ScoringOutputError, match="rejected"):
        parse_archival_verdict(film, 3, "film")


def test_the_artwork_prompt_has_artwork_rules_and_the_photo_task():
    prompt = build_archival_scoring_prompt("artwork", "naval battle", 1781, "q", [_c("photo", 0)], ["/t/0.jpg"], 4.0)

    assert "artworks" in prompt
    assert "real historical" in prompt.lower() and "digital illustration" in prompt
    assert "within about a decade of 1781" in prompt
    assert "title card" in prompt and "graphic" in prompt.lower()
    assert '"picks"' in prompt and "1 to 3" in prompt and "empty" in prompt
    assert "MUST pick at least one" not in prompt


def test_the_artwork_prompt_tells_the_judge_to_reject_tiny_blurry_or_cropped_images_and_say_so():
    # The Met payload has no pixel size, so the judge is the only guard against tiny images.
    prompt = build_archival_scoring_prompt("artwork", "s", 1781, "q", [_c("photo", 0)], ["/t/0.jpg"], 4.0).lower()

    assert "tiny, blurry or heavily cropped" in prompt
    assert "say so in the rejection reason" in prompt


def test_an_artwork_verdict_parses_like_a_photo_verdict():
    raw = json.dumps({"picks": [2, 0], "rejected": [{"index": 1, "reason": "modern"}], "reasoning": "best"})

    assert parse_archival_verdict(raw, 4, "artwork") == ArchivalVerdict([2, 0], {1: "modern"}, "best")
    for picks in ([], [0, 1, 2, 3], [9], [0, 0]):
        with pytest.raises(ScoringOutputError):
            parse_archival_verdict(json.dumps({"picks": picks, "reasoning": "x"}), 4, "artwork")
    contradictory = json.dumps({"picks": [0], "rejected": [{"index": 0, "reason": "r"}], "reasoning": "x"})
    with pytest.raises(ScoringOutputError, match="rejected"):
        parse_archival_verdict(contradictory, 4, "artwork")
    with pytest.raises(ScoringOutputError):
        parse_archival_verdict(json.dumps({"picks": [0]}), 2, "drawing")


@pytest.mark.parametrize("kind", ["film", "photo", "artwork"])
def test_every_prompt_kind_has_the_commons_provenance_rule(kind):
    prompt = build_archival_scoring_prompt(kind, "s", 1781, "q", [_c("film" if kind == "film" else "photo", 0)], ["/t/0.jpg"], 4.0).lower()

    assert "wikimedia commons" in prompt and "ai-generated" in prompt and "provenance" in prompt


def test_the_artwork_rules_allow_hand_colored_prints_and_clean_scans_and_restrict_colorized_to_photographs():
    prompt = build_archival_scoring_prompt("artwork", "s", 1781, "q", [_c("photo", 0)], ["/t/0.jpg"], 4.0)
    low = prompt.lower()

    assert "colorized or restored-looking image" not in low
    assert "hand-colored" in low and "cleanly digitized" in low
    assert "only to photographs" in low


def test_the_photo_prompt_still_rejects_a_colorized_image():
    prompt = build_archival_scoring_prompt("photo", "s", 1938, "q", [_c("photo", 0)], ["/t/0.jpg"], 4.0)

    assert "colorized or restored-looking image" in prompt


def test_the_photo_rules_reject_a_non_photograph_labelled_photo():
    prompt = build_archival_scoring_prompt("photo", "s", 1938, "q", [_c("photo", 0)], ["/t/0.jpg"], 4.0).lower()

    assert "labelled photo that is a painting, drawing, print or other non-photograph must be rejected" in prompt
