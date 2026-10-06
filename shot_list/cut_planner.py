import json
import re
from dataclasses import dataclass

from shot_list.align import WordTiming
from shot_list.models import (
    ARCHIVAL_CUTOFF_YEAR, Beat, FootageSpec, ShotList, beat_from_dict, needs_archival,
    validate_shot_list,
)


class CutPlannerOutputError(ValueError):
    pass


@dataclass
class FootageCut:
    beat_index: int  # index into ShotList.beats
    start: float
    end: float
    words: str  # the words spoken during this cut, in order
    director_subject: str  # the director's existing subject for this segment (context/fallback)


def load_shot_list(path: str) -> ShotList:
    with open(path) as f:
        raw = json.load(f)
    return ShotList(beats=[beat_from_dict(b) for b in raw["beats"]], duration=raw["duration"])


def words_in_range(word_timings: list[WordTiming], start: float, end: float) -> str:
    """Words whose start time is in [start, end), in spoken order, joined by spaces. A word that
    starts exactly on a boundary belongs to the later range only."""
    return " ".join(w.word for w in word_timings if start <= w.start < end)


def footage_cuts(shot_list: ShotList, word_timings: list[WordTiming]) -> list[FootageCut]:
    """One FootageCut per footage beat that has at least one spoken word. Footage beats with no
    spoken words are omitted (they keep the director's spec)."""
    cuts = []
    for i, beat in enumerate(shot_list.beats):
        if beat.type != "footage":
            continue
        words = words_in_range(word_timings, beat.start, beat.end)
        if not words:
            continue
        cuts.append(FootageCut(
            beat_index=i, start=beat.start, end=beat.end,
            words=words, director_subject=beat.footage.subject,
        ))
    return cuts


def build_cut_planner_prompt(cuts: list[FootageCut]) -> str:
    lines = []
    for i, cut in enumerate(cuts):
        prev_words = cuts[i - 1].words if i > 0 else "(none)"
        next_words = cuts[i + 1].words if i + 1 < len(cuts) else "(none)"
        lines.append(
            f'[{i}] {cut.start:.1f}s-{cut.end:.1f}s\n'
            f'    spoken during this cut: "{cut.words}"\n'
            f'    previous: {prev_words}\n'
            f'    next: {next_words}\n'
            f'    the director\'s overall subject for this stretch: {cut.director_subject}'
        )
    cut_lines = "\n".join(lines)

    return f"""You are the footage planner for a Versed documentary video. The narration has \
already been cut into {len(cuts)} footage shots, each shown for a few seconds. For each shot, \
choose what real stock footage should be on screen while those exact words are spoken.

The shots, in timeline order:
{cut_lines}

Rules:
- Show literally what is being said. If the words say "same tropical climate", plan tropical \
footage such as a beach with palm trees; if they name a language, a market, a border, a crop, \
show that.
- Name a specific place for every shot (a city, town, landmark or natural feature), never only \
a region or a group of countries. If the words or the director's subject name a country, the \
place must be inside that country.
- Two consecutive shots must never have the same idea or the same query. Vary the place, the \
subject and the kind of shot across the timeline.
- If the words in a shot are abstract or filler ("it's crazy because", "on paper, they should \
be similar"), fall back to the director's subject for that stretch, but still vary it from the \
neighbouring shots.
- Each query must describe what a camera would actually see and be searchable on a stock \
footage site (3 to 8 words). Never plan a title card, a text-only screen, a slideshow or a \
graphic.
- For every shot also give "era": the four-digit year of the period the spoken words are about \
(1847 for "Atlanta in 1847", 1863 for "the Civil War", 1917 for "the First World War"), or the \
word "modern" when the words are about the present day or any time from {ARCHIVAL_CUTOFF_YEAR} \
onward. Tag by the period the words are about, not by the place or the time of telling: "Atlanta \
today" is "modern". When the words are abstract, use the director's subject and the neighbouring \
shots to decide.
- When "era" is a year before {ARCHIVAL_CUTOFF_YEAR}, the shot will show real archival photos or \
film, so also give "archival_query" (a search for archive sites naming the place, the event and \
the year or decade, 3 to 8 words, for example "Atlanta railroad depot 1860s") and \
"archival_broad_query" (a broader search naming only the city or region and the era, 2 to 5 \
words, for example "Atlanta Georgia 1860s"). For a "modern" shot give "" for both. For a year before 1900 \
(1781 for "the American Revolution") the shot may show a real historical painting, engraving, \
lithograph, print or map instead of a photograph (photographs are scarce), so "archival_query" and \
"archival_broad_query" should describe the scene itself (the event, the place, the people), not the \
medium. "query" is still the ordinary stock search.

Respond with ONLY a JSON object, no other text, with exactly one entry per shot in the same \
order, where "index" is the number in square brackets above:

{{
  "count": {len(cuts)},
  "entries": [
    {{"index": 0, "query": "...", "subject": "<one line: what this shot shows and why it fits the words>", "era": "modern", "archival_query": "", "archival_broad_query": ""}}
  ]
}}
"""


# Opus often wraps a JSON-only answer in a ```json ... ``` fence despite being told not to.
_CODE_FENCE = re.compile(r"\A\s*```[A-Za-z]*[ \t]*\n(.*?)\n\s*```\s*\Z", re.DOTALL)


def _strip_code_fence(raw: str) -> str:
    match = _CODE_FENCE.match(raw)
    return match.group(1) if match else raw


MIN_ERA_YEAR = 1000
MAX_ERA_YEAR = 2100


def _parse_era(value, i: int):
    """None for "modern", otherwise the year. A year of ARCHIVAL_CUTOFF_YEAR or later is kept as a year
    but is still modern for routing (see shot_list.models.needs_archival)."""
    if isinstance(value, str):
        text = value.strip().lower()
        if text == "modern":
            return None
        if text.isdigit():
            value = int(text)
    if value is None:
        raise CutPlannerOutputError(
            f'cut {i} entry needs "era" to be "modern" or a four-digit year, got None. The planner prompt now '
            "requires an era on every shot; re-run Step 6b-ii (spawn the planner again with a freshly built "
            "cut_planner_prompt.txt)")
    if isinstance(value, bool) or not isinstance(value, int) or not (MIN_ERA_YEAR <= value <= MAX_ERA_YEAR):
        raise CutPlannerOutputError(
            f'cut {i} entry needs "era" to be "modern" or a four-digit year, got {value!r}')
    return value


def parse_cut_planner_output(raw_json: str, cuts: list[FootageCut]) -> list[dict]:
    try:
        payload = json.loads(_strip_code_fence(raw_json))
    except json.JSONDecodeError as e:
        raise CutPlannerOutputError(f"cut planner output is not valid JSON: {e}") from e
    if not isinstance(payload, dict):
        raise CutPlannerOutputError("cut planner output must be a JSON object")

    entries = payload.get("entries")
    if not isinstance(entries, list) or len(entries) != len(cuts):
        got = len(entries) if isinstance(entries, list) else "no"
        raise CutPlannerOutputError(f"expected {len(cuts)} entries, got {got}")

    by_index = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise CutPlannerOutputError(f"entry is not an object: {entry!r}")
        index = entry.get("index")
        if not isinstance(index, int) or isinstance(index, bool):
            raise CutPlannerOutputError(f"entry index must be an integer, got {type(index).__name__}: {index!r}")
        by_index[index] = entry

    plans = []
    for i in range(len(cuts)):
        entry = by_index.get(i)
        if entry is None:
            raise CutPlannerOutputError(f"missing entry for cut {i}")
        query, subject = entry.get("query"), entry.get("subject")
        if not isinstance(query, str) or not query.strip():
            raise CutPlannerOutputError(f"cut {i} entry has a missing or blank query")
        if not isinstance(subject, str) or not subject.strip():
            raise CutPlannerOutputError(f"cut {i} entry has a missing or blank subject")
        era = _parse_era(entry.get("era"), i)
        archival_query = archival_broad_query = ""
        if needs_archival(era):
            archival_query, archival_broad_query = entry.get("archival_query"), entry.get("archival_broad_query")
            for name, value in (("archival_query", archival_query), ("archival_broad_query", archival_broad_query)):
                if not isinstance(value, str) or not value.strip():
                    raise CutPlannerOutputError(
                        f"cut {i} is about {era} (before {ARCHIVAL_CUTOFF_YEAR}) but has a missing or blank {name}")
            archival_query, archival_broad_query = archival_query.strip(), archival_broad_query.strip()
        plans.append({"query": query.strip(), "subject": subject.strip(), "era": era,
                      "archival_query": archival_query, "archival_broad_query": archival_broad_query})

    for i in range(1, len(plans)):
        if plans[i]["query"].lower() == plans[i - 1]["query"].lower():
            raise CutPlannerOutputError(
                f"cuts {i - 1} and {i} have the same query {plans[i]['query']!r}; "
                "consecutive cuts must differ"
            )
    for i in range(1, len(plans)):
        if plans[i]["archival_query"] and plans[i]["archival_query"].lower() == plans[i - 1]["archival_query"].lower():
            raise CutPlannerOutputError(
                f"cuts {i - 1} and {i} have the same archival query {plans[i]['archival_query']!r}; "
                "consecutive cuts must differ"
            )
    return plans


def apply_cut_plans(shot_list: ShotList, cuts: list[FootageCut], plans: list[dict]) -> ShotList:
    """A new ShotList with each planned footage beat's FootageSpec replaced. Beats not in `cuts`
    (graphics, and footage beats with no spoken words) are kept as they are."""
    if len(cuts) != len(plans):
        raise ValueError(f"{len(cuts)} cuts but {len(plans)} plans")
    beats = list(shot_list.beats)
    for cut, plan in zip(cuts, plans):
        old = beats[cut.beat_index]
        if old.type != "footage":
            raise ValueError(f"cut points at beat {cut.beat_index}, which is a {old.type} beat")
        beats[cut.beat_index] = Beat(
            start=old.start, end=old.end, type="footage",
            footage=FootageSpec(
                query=plan["query"], subject=plan["subject"], era=plan.get("era"),
                archival_query=plan.get("archival_query", ""),
                archival_broad_query=plan.get("archival_broad_query", ""),
            ),
        )
    result = ShotList(beats=beats, duration=shot_list.duration)
    validate_shot_list(result)
    return result
