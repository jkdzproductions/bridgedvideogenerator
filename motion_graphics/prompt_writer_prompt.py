import json

from shot_list.director_prompt import DESIGN_SYSTEM_SNAPSHOT


def build_prompt_writer_prompt(archetype: str, data: dict, target_duration: float) -> str:
    data_json = json.dumps(data, indent=2)

    return f"""You are writing an authoring prompt for Claude Design's Animation template, for \
one motion-graphic beat of a Bridged documentary video.

First, Read {DESIGN_SYSTEM_SNAPSHOT} (the Bridged design system rules). Do not invoke any \
skill. You need its "The 7 frame types" table, "The one rule", "Visual foundations", and \
"Content fundamentals" sections.

This beat's frame archetype: {archetype}
This beat's target duration: {target_duration:.1f} seconds
This beat's data to visualize:
{data_json}

Using the design system's rules for the "{archetype}" frame type, write a single, complete, \
self-contained prompt that a person could paste directly into Claude Design's Animation \
template to have it generate this exact animation. Claude Design's own in-product AI reads \
this prompt conversationally — write it as direct instructions to that AI, not as a \
description written for a human. The Bridged design system is already attached to the canvas, \
so tell the AI to use it rather than re-describing every token. The prompt must specify: the \
archetype's visual structure as the frame-type table describes it (look and ground), the \
exact data values to show, and the design system's rules — its "one rule" from \
"The one rule", its single typeface, and the correct ground/texture for this frame type. \
If the graphic highlights two or more neighboring countries, the prompt must tell the AI to \
give each country its own distinct color (never the same color for all of them, and no blue) \
and to draw the border where the neighboring countries meet as a clearly visible line, so they \
never read as one country. \
If the beat's data (or the fact it states) names a historical year or period (a year such as \
1847, a decade such as "the 1850s", or words like "founded" or "in 1837"), then any photograph, \
map or other imagery in the graphic must match that era: tell the AI to use a public-domain, \
period-appropriate image (an old photograph, engraving, lithograph or historic map of the \
place, for example from the Library of Congress or Wikimedia Commons) from the closest \
available decade. An exact-year match is NOT required (for 1847, an 1850 or 1860 view is \
fine). The AI must NOT use a modern photo, skyline, vehicles or buildings for a historical \
year. For the earliest years no photograph of the place may exist, in which case an \
engraving, lithograph or old map from the nearest decade is correct. This rule applies only to genuinely historical dates (before \
roughly the mid-20th century): ignore it for recent or modern years and figures, for modern or \
satellite maps, and for graphics with no photographic imagery, and never add imagery that the \
archetype would not otherwise have. \
It must also say the animation should last approximately {target_duration:.1f} seconds with no \
audio (the clip is silent — the voiceover is added separately later, at final assembly).

Respond with ONLY a JSON object, no other text:
{{"authoring_prompt": "<the complete prompt text>"}}
"""
