import re

from motion_graphics.prompt_writer_prompt import build_prompt_writer_prompt
from motion_graphics.reviewer_prompt import build_reviewer_prompt
from shot_list.cut_planner import FootageCut, build_cut_planner_prompt
from shot_list.director_prompt import build_director_prompt
from shot_list.segments import Segment


def _all_prompts():
    return {
        "director": build_director_prompt([Segment("graphic", "Cargo moved through the port.", 0, 5)]),
        "prompt_writer": build_prompt_writer_prompt(archetype="chart_card", data={}, target_duration=3.0),
        "reviewer": build_reviewer_prompt(
            archetype="territory_map", data={"territory": "Panama"},
            screenshot_path="/tmp/x.png", attempt=1, max_attempts=3,
        ),
        "cut_planner": build_cut_planner_prompt(
            [FootageCut(0, 0.0, 4.0, "Ships queue at the canal", "Panama Canal")]
        ),
    }


def test_no_prompt_mentions_versed_or_a_specific_typeface():
    for name, prompt in _all_prompts().items():
        lowered = prompt.lower()
        assert not re.search(r"(?<![a-z])versed", lowered), f"{name} prompt still says Versed"
        assert "nagel" not in lowered, f"{name} prompt still names the Nagel font"


def test_every_prompt_says_bridged_documentary_video():
    for name, prompt in _all_prompts().items():
        assert "Bridged documentary video" in prompt, f"{name} prompt does not say Bridged"
