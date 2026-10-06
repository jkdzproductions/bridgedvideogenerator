import json

from shot_list.director_prompt import DESIGN_SYSTEM_SNAPSHOT


def build_reviewer_prompt(
    archetype: str,
    data: dict,
    screenshot_path: str,
    attempt: int,
    max_attempts: int,
) -> str:
    data_json = json.dumps(data, indent=2)

    return f"""You are reviewing a rendered motion-graphic beat for a Versed documentary video, \
attempt {attempt} of {max_attempts}.

First, Read {DESIGN_SYSTEM_SNAPSHOT} (the Versed design system rules). Do not invoke any \
skill. You will judge against its "Pre-ship checklist" section.

Target archetype: {archetype}
Data that should be visualized:
{data_json}

Use your Read tool to actually view the screenshot at this path before judging — do not guess: \
{screenshot_path}

Judge against the design system's "Pre-ship checklist" (every item): exactly the target frame \
type with the data above and no wrong, missing, or fabricated values; red only marking the \
subject; one clear focal point; a single typeface (Nagel), no serif; the right ground/texture \
for this frame type and no drop shadows on shapes; comma-formatted numbers and short labels; \
and legibility at phone size (480p). Also judge era: if the data names a historical year or \
period, the imagery matches that era (no modern buildings, skylines, vehicles or photography \
for a historical year; the closest available older view is acceptable, an exact-year match is \
not required). If a modern image is shown for a historical fact the verdict is a `correction` \
(or `reject` only if no correction could fix it), with concrete instructions to use a \
period-appropriate public-domain image (an old photograph, engraving, lithograph or historic \
map from the closest available decade). This check applies only to genuinely historical dates \
(before roughly the mid-20th century); a modern fact, modern or satellite maps, or a frame with \
no photographic imagery is not affected, so do not ask for old imagery there.

Respond with ONLY a JSON object, no other text, in exactly one of these three shapes:

Approved — the beat is ready to export as-is:
{{"verdict": "approve", "reasoning": "<one sentence>"}}

Needs a specific correction — close, but something needs fixing (write concrete, actionable \
instructions the same in-product AI that made it can follow directly):
{{"verdict": "correction", "correction_instructions": "<specific instructions>", "reasoning": "<one sentence>"}}

Reject entirely — no amount of correction would fix this (e.g. the wrong archetype was built \
from the start):
{{"verdict": "reject", "reasoning": "<one sentence explaining why no correction would help>"}}
"""
