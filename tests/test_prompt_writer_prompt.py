from motion_graphics.prompt_writer_prompt import build_prompt_writer_prompt
from shot_list.director_prompt import DESIGN_SYSTEM_SNAPSHOT


def test_prompt_includes_archetype_duration_and_all_data():
    prompt = build_prompt_writer_prompt(
        archetype="chart_card",
        data={"title": "Berlin's Population", "range": "1750-1880", "peak": "220,000"},
        target_duration=5.5,
    )

    assert "chart_card" in prompt
    assert "5.5" in prompt
    assert "Berlin's Population" in prompt
    assert "1750-1880" in prompt
    assert "220,000" in prompt


def test_prompt_reads_snapshot_by_absolute_path_and_asks_for_json():
    prompt = build_prompt_writer_prompt(archetype="fan_out", data={}, target_duration=3.0)

    assert DESIGN_SYSTEM_SNAPSHOT in prompt
    assert "Do not invoke any skill" in prompt
    assert "authoring_prompt" in prompt
    assert "already attached" in prompt
    assert "The one rule" in prompt
    assert "Nagel" not in prompt


def test_prompt_notes_the_clip_is_silent():
    prompt = build_prompt_writer_prompt(archetype="year_range", data={}, target_duration=4.0)

    assert "no audio" in prompt or "silent" in prompt


def test_prompt_writer_prompt_requires_distinct_colors_and_border_for_neighboring_countries():
    from motion_graphics.prompt_writer_prompt import build_prompt_writer_prompt

    prompt = build_prompt_writer_prompt("territory_map", {"territories": ["Costa Rica", "Panama"]}, 10.0)
    assert "two or more neighboring countries" in prompt
    assert "distinct color" in prompt
    assert "border" in prompt


def test_prompt_writer_prompt_has_era_rule_for_every_archetype():
    for archetype in ("network_map", "chart_card", "territory_map"):
        prompt = build_prompt_writer_prompt(archetype, {"year": "1847", "place": "Atlanta"}, 5.0)
        assert "historical year or period" in prompt
        assert "public-domain" in prompt
        assert "closest available decade" in prompt
        assert "exact-year match is NOT required" in prompt
        assert "must NOT use a modern photo" in prompt
        assert "engraving, lithograph or old map" in prompt


def test_prompt_writer_prompt_keeps_existing_contracts_with_era_rule():
    prompt = build_prompt_writer_prompt("network_map", {}, 4.0)
    assert '{"authoring_prompt": "<the complete prompt text>"}' in prompt
    assert "Respond with ONLY a JSON object" in prompt
    assert "approximately 4.0 seconds with no audio" in prompt
    assert "distinct color" in prompt


def test_prompt_writer_era_rule_has_modern_carve_out():
    prompt = build_prompt_writer_prompt("chart_card", {"year": "2022"}, 5.0)
    assert "applies only to genuinely historical dates" in prompt
    assert "mid-20th century" in prompt
    assert "modern or satellite maps" in prompt
    assert "never add imagery" in prompt
