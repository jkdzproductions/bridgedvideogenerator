import json

import pytest

from footage.archival_scoring import MixedVerdict, build_mixed_scoring_prompt, parse_mixed_verdict
from footage.archive_types import ArchiveCandidate
from footage.combined_build import CombinedCandidate
from footage.pexels import PexelsCandidate, VideoFile
from footage.scoring_output import ScoringOutputError


def _still(i, **over):
    base = dict(source="met", item_id=str(i), kind="photo", title=f"Picture {i}", year=1781, creator="Artist",
                rights="Public domain (The Met Open Access)", page_url="p", media_url="m", thumbnail_url="t")
    base.update(over)
    return ArchiveCandidate(**base)


def _stock(i):
    p = PexelsCandidate(i, f"url{i}", f"thumb{i}.jpg", 12, 1920, 1080, [VideoFile("hd", "video/mp4", 1920, 1080, "x.mp4")])
    return CombinedCandidate("pexels", str(i), f"/t/stock{i}.jpg", p)


def _prompt():
    return build_mixed_scoring_prompt(
        "naval battle", 1781, "naval battle 1781", "ship at sea",
        [_still(0), _still(1, year=None, source="loc")], ["artwork", "photo"], ["/t/a0.jpg", "/t/a1.jpg"], [_stock(7)], 4.0)


def test_the_prompt_numbers_stills_then_stock_and_tags_each_type():
    prompt = _prompt()

    assert "[0] type=artwork" in prompt and "[1] type=photo" in prompt and "[2] type=stock" in prompt
    assert "/t/a0.jpg" in prompt and "/t/stock7.jpg" in prompt
    assert "year=unknown" in prompt and "1781" in prompt and "4.0" in prompt


def test_the_prompt_states_the_rules_and_the_json_schema():
    prompt = _prompt()

    assert "real historical" in prompt.lower() and "AI" in prompt and "digital illustration" in prompt
    assert "contradicts the period" in prompt                 # stock only when nothing modern shows
    assert "title card" in prompt and "graphic" in prompt.lower()
    assert '"picks"' in prompt and "empty" in prompt          # empty picks = none acceptable
    assert "1 to 3" in prompt and "exactly one" in prompt and "never a mix" in prompt


def test_the_prompt_works_with_only_stills_or_only_stock():
    only_stock = build_mixed_scoring_prompt("s", 1781, "aq", "sq", [], [], [], [_stock(1)], 4.0)
    only_stills = build_mixed_scoring_prompt("s", 1863, "aq", "sq", [_still(0)], ["photo"], ["/t/a.jpg"], [], 4.0)

    assert "[0] type=stock" in only_stock and "[0] type=photo" in only_stills
    assert "type=stock" not in only_stills
    assert "contradicts the period" not in only_stills


def test_mismatched_still_lists_stop_loudly():
    with pytest.raises(ValueError):
        build_mixed_scoring_prompt("s", 1781, "aq", "sq", [_still(0)], ["artwork"], [], [], 4.0)
    with pytest.raises(ValueError):
        build_mixed_scoring_prompt("s", 1781, "aq", "sq", [_still(0)], [], ["/t/a.jpg"], [], 4.0)
    with pytest.raises(ValueError):
        build_mixed_scoring_prompt("s", 1781, "aq", "sq", [_still(0)], ["drawing"], ["/t/a.jpg"], [], 4.0)


def test_the_prompt_tells_the_judge_to_reject_tiny_blurry_or_cropped_images_and_say_so():
    # The Met payload has no pixel size, so the judge is the only guard against tiny images.
    prompt = _prompt().lower()

    assert "tiny, blurry or heavily cropped" in prompt
    assert "say so in the rejection reason" in prompt


TYPES = ["artwork", "photo", "artwork", "stock", "stock"]


def test_stills_of_both_kinds_can_be_mixed_in_order_with_rejections():
    raw = json.dumps({"picks": [2, 0, 1], "rejected": [{"index": 3, "reason": "modern skyline"}], "reasoning": "best"})

    assert parse_mixed_verdict(raw, TYPES) == MixedVerdict("stills", [2, 0, 1], {3: "modern skyline"}, "best")


def test_a_single_stock_pick():
    assert parse_mixed_verdict(json.dumps({"picks": [4], "reasoning": "calm sea"}), TYPES) == MixedVerdict("stock", [4], {}, "calm sea")


def test_an_empty_pick_list_is_the_none_outcome():
    verdict = parse_mixed_verdict(json.dumps({"picks": [], "reasoning": "everything is modern or graphic"}), TYPES)

    assert verdict.choice == "none" and verdict.picks == [] and "modern" in verdict.reasoning


@pytest.mark.parametrize("picks", [[0, 3], [3, 4], [0, 1, 2, 0], [0, 1, 2, 9], [-1], ["0"], [True], "0", None])
def test_bad_pick_lists_stop_loudly(picks):
    with pytest.raises(ScoringOutputError):
        parse_mixed_verdict(json.dumps({"picks": picks, "reasoning": "x"}), TYPES)


def test_four_stills_are_too_many():
    with pytest.raises(ScoringOutputError):
        parse_mixed_verdict(json.dumps({"picks": [0, 1, 2, 5], "reasoning": "x"}), ["artwork"] * 6)


def test_a_pick_that_is_also_rejected_is_contradictory():
    raw = json.dumps({"picks": [0], "rejected": [{"index": 0, "reason": "r"}], "reasoning": "x"})

    with pytest.raises(ScoringOutputError):
        parse_mixed_verdict(raw, TYPES)


@pytest.mark.parametrize("raw", ["not json", "[1]", json.dumps({"reasoning": "no picks key"}),
                                 json.dumps({"picks": [0], "rejected": "x", "reasoning": "x"})])
def test_malformed_verdicts_stop_loudly(raw):
    with pytest.raises(ScoringOutputError):
        parse_mixed_verdict(raw, TYPES)


def test_the_mixed_prompt_has_the_commons_provenance_rule_even_with_only_stock():
    for prompt in (_prompt(), build_mixed_scoring_prompt("s", 1781, "a", "b", [], [], [], [_stock(1)], 4.0)):
        low = prompt.lower()
        assert "wikimedia commons" in low and "ai-generated" in low and "provenance" in low


def test_the_mixed_artwork_rule_allows_hand_colored_prints_and_clean_scans():
    low = _prompt().lower()

    assert "hand-colored" in low and "cleanly digitized" in low
    assert "only to photographs" in low
    assert "colorized or restored-looking image" in low  # the PHOTO rule still carries it


def test_an_unknown_label_in_the_types_list_fails_loudly():
    with pytest.raises(ScoringOutputError, match="label"):
        parse_mixed_verdict('{"picks": [0], "rejected": [], "reasoning": "x"}', ["still"])


def _yt_stock(i):
    from footage.youtube import YouTubeCandidate
    return CombinedCandidate("youtube", f"v{i}", f"/t/y{i}.jpg", YouTubeCandidate(f"v{i}", "Ship at sea", "ch", "Sea Films", "u", 42.4))


def _env_stock(i):
    from footage.envato import EnvatoCandidate
    return CombinedCandidate("envato", f"e{i}", f"/t/e{i}.jpg", EnvatoCandidate(f"e{i}", "Waves", "u", "Some Author", "d"))


def test_stock_lines_show_per_source_details():
    prompt = build_mixed_scoring_prompt("s", 1781, "aq", "sq", [], [], [], [_stock(1), _yt_stock(2), _env_stock(3)], 4.0)

    assert "[0] type=stock source=pexels duration=12s resolution=1920x1080 thumbnail=/t/stock1.jpg" in prompt
    assert '[1] type=stock source=youtube title="Ship at sea" channel="Sea Films" duration=42s' in prompt
    assert '[2] type=stock source=envato title="Waves" author="Some Author" thumbnail=/t/e3.jpg' in prompt
    assert "duration" not in prompt.split("[2] type=stock")[1].split("\n")[0]
    assert "opening of a youtube video" in prompt.lower() and "0:00" in prompt


def test_the_stock_rule_rejects_ai_cgi_animated_and_reenactment_stock():
    low = build_mixed_scoring_prompt("s", 1781, "aq", "sq", [], [], [], [_stock(1)], 4.0).lower()

    for word in ("ai-generated", "cgi", "animated", "rendered", "game", "reenactment", "re-creation"):
        assert word in low
    assert "thumbnail plus" in low


def test_still_rules_are_source_aware_for_commons_non_photographs():
    low = _prompt().lower()

    assert "source is met or loc may be a genuine historical photograph or genuine historical artwork" in low
    assert "source is commons must be a genuine photograph" in low
    assert "reject any painting, drawing, print, engraving, map or other non-photograph from commons" in low
    assert "hand-colored prints" in low


def test_a_photograph_is_judged_as_a_photograph_whatever_its_label():
    low = _prompt().lower()

    assert ("whatever its type label, judge a still that is a photograph as a photograph: it must be a real "
            "photograph made within about a decade of 1781, and a genuine period photograph labelled artwork is "
            "acceptable; a photograph made much later than the period (for example a later reunion or memorial "
            "photograph) must be rejected") in low
    # the earlier rules are still there
    assert "source is met or loc may be a genuine historical photograph or genuine historical artwork" in low
    assert "hand-colored prints" in low and "provenance" in low and "wrongly labelled public domain" in low
    stock_only = build_mixed_scoring_prompt("s", 1781, "aq", "sq", [], [], [], [_stock(1)], 4.0).lower()
    assert "judge a still that is a photograph" not in stock_only


def test_the_answer_text_asks_for_different_views():
    assert "Choose different views: never pick near-identical pictures." in _prompt()
