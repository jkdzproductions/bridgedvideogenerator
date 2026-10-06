from motion_graphics.reviewer_prompt import build_reviewer_prompt
from shot_list.director_prompt import DESIGN_SYSTEM_SNAPSHOT


def _prompt(**kw):
    args = dict(archetype="territory_map", data={"territory": "Armenia"},
                screenshot_path="/tmp/x.png", attempt=1, max_attempts=3)
    args.update(kw)
    return build_reviewer_prompt(**args)


def test_prompt_includes_archetype_data_and_screenshot_path():
    prompt = _prompt(archetype="then_vs_now", data={"then": "400 Ships", "now": "100 Ships"},
                     screenshot_path="/tmp/beat_1_attempt_1.png")

    assert "then_vs_now" in prompt
    assert "400 Ships" in prompt
    assert "100 Ships" in prompt
    assert "/tmp/beat_1_attempt_1.png" in prompt
    assert "1 of 3" in prompt


def test_prompt_reads_snapshot_by_absolute_path_and_read_tool():
    prompt = _prompt()

    assert "Read tool" in prompt
    assert DESIGN_SYSTEM_SNAPSHOT in prompt
    assert "Pre-ship checklist" in prompt
    assert "Do not invoke any skill" in prompt


def test_prompt_has_no_grayscale_wording():
    prompt = _prompt().lower()

    assert "grayscale" not in prompt


def test_prompt_describes_all_three_verdict_shapes():
    prompt = _prompt()

    assert '"verdict": "approve"' in prompt
    assert '"verdict": "correction"' in prompt
    assert '"verdict": "reject"' in prompt
    assert "correction_instructions" in prompt


def test_prompt_has_era_check_with_correction_verdict():
    prompt = _prompt(data={"year": "1847", "place": "Atlanta"})

    assert "historical year or period" in prompt
    assert "matches that era" in prompt
    assert "closest available older view is acceptable" in prompt
    assert "exact-year match is not required" in prompt
    assert "no modern buildings, skylines, vehicles or photography" in prompt
    assert "public-domain" in prompt
    assert "`correction`" in prompt


def test_prompt_keeps_json_only_contract_with_era_check():
    prompt = _prompt()

    assert "Respond with ONLY a JSON object" in prompt
    assert "Pre-ship checklist" in prompt
    assert '"verdict": "approve"' in prompt


def test_prompt_era_check_has_modern_carve_out():
    prompt = _prompt(data={"year": "2022"})

    assert "applies only to genuinely historical dates" in prompt
    assert "mid-20th century" in prompt
    assert "modern or satellite maps" in prompt
    assert "no photographic imagery" in prompt
