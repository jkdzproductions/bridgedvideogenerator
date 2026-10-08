import json
import re
from dataclasses import dataclass, field
from typing import Optional

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
    # (word, start time) of every word spoken during this cut, in order: a split cut's piece
    # boundaries must fall on one of these start times.
    word_times: tuple = field(default=())


MIN_PIECE_SECONDS = 1.3  # a split piece shorter than this flashes by too fast to read
MAX_PIECES = 4
# Boundaries are printed to the planner at 3 decimals; a boundary within this of a word start (or of
# the cut's start/end) is snapped to the exact value.
BOUNDARY_TOLERANCE = 0.005


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
        spoken = [w for w in word_timings if beat.start <= w.start < beat.end]
        if not spoken:
            continue
        cuts.append(FootageCut(
            beat_index=i, start=beat.start, end=beat.end,
            words=" ".join(w.word for w in spoken), director_subject=beat.footage.subject,
            word_times=tuple((w.word, w.start) for w in spoken),
        ))
    return cuts


def build_cut_planner_prompt(cuts: list[FootageCut]) -> str:
    lines = []
    for i, cut in enumerate(cuts):
        prev_words = cuts[i - 1].words if i > 0 else "(none)"
        next_words = cuts[i + 1].words if i + 1 < len(cuts) else "(none)"
        word_starts = " ".join(f"{word}@{start:.3f}" for word, start in cut.word_times)
        lines.append(
            f'[{i}] {cut.start:.1f}s-{cut.end:.1f}s (exact start {cut.start:.3f}, exact end {cut.end:.3f})\n'
            f'    spoken during this cut: "{cut.words}"\n'
            f'    word start times: {word_starts}\n'
            f'    previous: {prev_words}\n'
            f'    next: {next_words}\n'
            f'    the director\'s overall subject for this stretch: {cut.director_subject}'
        )
    cut_lines = "\n".join(lines)

    return f"""You are the footage planner for a Bridged documentary video. The narration has \
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

Splitting a shot into pieces:
- Most shots get ONE plan. Split a shot into 2 or 3 pieces (never more than {MAX_PIECES} pieces) \
ONLY when its words name several distinct things a camera could show, one after another: a list \
of nouns, places or people, "from A to B", "X versus Y", or a run of distinct events. Each piece \
then shows its own thing while its own words are spoken. Example: "Oil has tank farms, grain has \
silos, water has towers" is three pieces (an oil tank farm, then grain silos, then a water tower), \
not one oil shot.
- Do not split abstract phrasing or filler, and do not split one continuous subject described at \
length: one subject stays one shot even when the sentence is long.
- Piece times: the first piece starts at the shot's exact start and the last piece ends at its \
exact end (copy both from the shot's line above). Every other boundary is the word start time of \
the word that begins the next piece, copied exactly from that shot's "word start times" (the \
piece appears as its first word is spoken). Pieces follow each other with no gap or overlap \
(each piece's "start" is the previous piece's "end").
- Every piece lasts at least {MIN_PIECE_SECONDS} seconds ("end" minus "start"). If one subject's \
words are shorter than that, move the boundary to a nearby word start, merge that piece with its \
neighbour, or do not split.
- Every piece follows all the rules above on its own: a literal, specific, searchable "query", a \
"subject", an "era", and "archival_query" and "archival_broad_query" when its era is before \
{ARCHIVAL_CUTOFF_YEAR}. Consecutive pieces, and a piece and the shot next to it, must not have \
the same query.

Respond with ONLY a JSON object, no other text, with exactly one entry per shot in the same \
order, where "index" is the number in square brackets above. An entry is either one plan, or \
"pieces" (an ordered list of piece plans) for a split shot, never both:

{{
  "count": {len(cuts)},
  "entries": [
    {{"index": 0, "query": "...", "subject": "<one line: what this shot shows and why it fits the words>", "era": "modern", "archival_query": "", "archival_broad_query": ""}},
    {{"index": 1, "pieces": [
      {{"start": <the shot's exact start>, "end": <a word start time>, "words": "<the words spoken in this piece>", "query": "...", "subject": "...", "era": "modern", "archival_query": "", "archival_broad_query": ""}},
      {{"start": <that same word start time>, "end": <the shot's exact end>, "words": "...", "query": "...", "subject": "...", "era": "modern", "archival_query": "", "archival_broad_query": ""}}
    ]}}
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


def _parse_era(value, label: str):
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
            f'{label} needs "era" to be "modern" or a four-digit year, got None. The planner prompt now '
            "requires an era on every shot; re-run Step 6b-ii (spawn the planner again with a freshly built "
            "cut_planner_prompt.txt)")
    if isinstance(value, bool) or not isinstance(value, int) or not (MIN_ERA_YEAR <= value <= MAX_ERA_YEAR):
        raise CutPlannerOutputError(
            f'{label} needs "era" to be "modern" or a four-digit year, got {value!r}')
    return value


def _parse_plan_fields(obj: dict, label: str) -> dict:
    """query, subject, era and the archival queries of one plan (a whole cut or one piece)."""
    query, subject = obj.get("query"), obj.get("subject")
    if not isinstance(query, str) or not query.strip():
        raise CutPlannerOutputError(f"{label} has a missing or blank query")
    if not isinstance(subject, str) or not subject.strip():
        raise CutPlannerOutputError(f"{label} has a missing or blank subject")
    era = _parse_era(obj.get("era"), label)
    archival_query = archival_broad_query = ""
    if needs_archival(era):
        archival_query, archival_broad_query = obj.get("archival_query"), obj.get("archival_broad_query")
        for name, value in (("archival_query", archival_query), ("archival_broad_query", archival_broad_query)):
            if not isinstance(value, str) or not value.strip():
                raise CutPlannerOutputError(
                    f"{label} is about {era} (before {ARCHIVAL_CUTOFF_YEAR}) but has a missing or blank {name}")
        archival_query, archival_broad_query = archival_query.strip(), archival_broad_query.strip()
    return {"query": query.strip(), "subject": subject.strip(), "era": era,
            "archival_query": archival_query, "archival_broad_query": archival_broad_query}


def _time(value, name: str, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CutPlannerOutputError(f"{label} needs a numeric {name!r} (seconds), got {value!r}")
    return float(value)


def _snap(value: float, targets: list) -> Optional[float]:
    """The target nearest `value` when it is within BOUNDARY_TOLERANCE, else None."""
    best = min(targets, key=lambda t: abs(t - value), default=None)
    return best if best is not None and abs(best - value) <= BOUNDARY_TOLERANCE else None


def _parse_pieces(raw_pieces, cut: FootageCut, i: int) -> list[dict]:
    """Validated pieces of a split cut: they tile [cut.start, cut.end] exactly, every inner boundary is
    a word start of the cut, each lasts at least MIN_PIECE_SECONDS, 2 to MAX_PIECES of them. Times are
    snapped to the exact cut bounds and word starts; "words" is recomputed from the word timings."""
    if not isinstance(raw_pieces, list):
        raise CutPlannerOutputError(f'cut {i} entry "pieces" must be a list of piece objects')
    if len(raw_pieces) > MAX_PIECES:
        raise CutPlannerOutputError(f"cut {i} has {len(raw_pieces)} pieces; at most {MAX_PIECES} are allowed")
    if len(raw_pieces) < 2:
        raise CutPlannerOutputError(
            f"cut {i} has {len(raw_pieces)} piece; a split needs 2 to {MAX_PIECES} pieces "
            "(give one plan without \"pieces\" for an unsplit cut)")

    word_starts = [start for _, start in cut.word_times if cut.start < start < cut.end]
    pieces = []
    for k, raw in enumerate(raw_pieces):
        label = f"cut {i} piece {k}"
        if not isinstance(raw, dict):
            raise CutPlannerOutputError(f"{label} is not an object: {raw!r}")
        start, end = _time(raw.get("start"), "start", label), _time(raw.get("end"), "end", label)
        words = raw.get("words")
        if not isinstance(words, str) or not words.strip():
            raise CutPlannerOutputError(f"{label} has missing or blank words")
        plan = _parse_plan_fields(raw, label)

        if k == 0:
            if abs(start - cut.start) > BOUNDARY_TOLERANCE:
                raise CutPlannerOutputError(
                    f"{label} must start at the cut's start {cut.start:.3f}, got {start:.3f}")
            start = cut.start
        else:
            previous_end = pieces[-1]["end"]
            if abs(start - previous_end) > BOUNDARY_TOLERANCE:
                raise CutPlannerOutputError(
                    f"{label} starts at {start:.3f} but piece {k - 1} ends at {previous_end:.3f}; pieces "
                    "must tile the cut with no gap or overlap")
            start = previous_end
        if k == len(raw_pieces) - 1:
            if abs(end - cut.end) > BOUNDARY_TOLERANCE:
                raise CutPlannerOutputError(f"{label} must end at the cut's end {cut.end:.3f}, got {end:.3f}")
            end = cut.end
        else:
            snapped = _snap(end, word_starts)
            if snapped is None:
                raise CutPlannerOutputError(
                    f"cut {i} piece {k + 1} starts at {end:.3f}, which is not the start of a word in this cut "
                    f"(word starts: {', '.join(f'{t:.3f}' for t in word_starts) or 'none'})")
            end = snapped
        if end - start < MIN_PIECE_SECONDS - 1e-9:
            raise CutPlannerOutputError(
                f"{label} lasts {end - start:.2f} s ({start:.3f}-{end:.3f}); every piece must last at least "
                f"{MIN_PIECE_SECONDS} s")
        spoken = " ".join(word for word, t in cut.word_times if start <= t < end)
        if not spoken:
            raise CutPlannerOutputError(f"{label} ({start:.3f}-{end:.3f}) has no spoken words")
        pieces.append({"start": start, "end": end, "words": spoken, **plan})
    return pieces


def _units(plans: list[dict]):
    """(label, plan) for every planned shot in timeline order: each piece of a split cut, else the cut."""
    for i, plan in enumerate(plans):
        if "pieces" in plan:
            for k, piece in enumerate(plan["pieces"]):
                yield f"cut {i} piece {k}", piece
        else:
            yield f"cut {i}", plan


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
    for i, cut in enumerate(cuts):
        entry = by_index.get(i)
        if entry is None:
            raise CutPlannerOutputError(f"missing entry for cut {i}")
        if "pieces" in entry:
            if "query" in entry:
                raise CutPlannerOutputError(
                    f'cut {i} entry has both "pieces" and a "query"; give one plan or pieces, not both')
            plans.append({"pieces": _parse_pieces(entry["pieces"], cut, i)})
        else:
            plans.append(_parse_plan_fields(entry, f"cut {i} entry"))

    # Consecutive shots (a piece counts as a shot) must differ, across cut boundaries too.
    units = list(_units(plans))
    for (prev_label, prev), (label, cur) in zip(units, units[1:]):
        if cur["query"].lower() == prev["query"].lower():
            raise CutPlannerOutputError(
                f"{prev_label} and {label} have the same query {cur['query']!r}; consecutive cuts must differ")
    for (prev_label, prev), (label, cur) in zip(units, units[1:]):
        if cur["archival_query"] and cur["archival_query"].lower() == prev["archival_query"].lower():
            raise CutPlannerOutputError(
                f"{prev_label} and {label} have the same archival query {cur['archival_query']!r}; "
                "consecutive cuts must differ")
    return plans


def _footage_beat(start: float, end: float, plan: dict) -> Beat:
    return Beat(
        start=start, end=end, type="footage",
        footage=FootageSpec(
            query=plan["query"], subject=plan["subject"], era=plan.get("era"),
            archival_query=plan.get("archival_query", ""),
            archival_broad_query=plan.get("archival_broad_query", ""),
        ),
    )


def apply_cut_plans(shot_list: ShotList, cuts: list[FootageCut], plans: list[dict]) -> ShotList:
    """A new ShotList with each planned footage beat's FootageSpec replaced, and each split cut replaced
    by one footage beat per piece (later beats move up, so beat numbers stay sequential). Beats not in
    `cuts` (graphics, and footage beats with no spoken words) are kept as they are. Runs before Stage 2,
    so no clip ever needs renumbering."""
    if len(cuts) != len(plans):
        raise ValueError(f"{len(cuts)} cuts but {len(plans)} plans")
    plan_by_beat = {}
    for cut, plan in zip(cuts, plans):
        old = shot_list.beats[cut.beat_index]
        if old.type != "footage":
            raise ValueError(f"cut points at beat {cut.beat_index}, which is a {old.type} beat")
        plan_by_beat[cut.beat_index] = plan

    beats = []
    for index, old in enumerate(shot_list.beats):
        plan = plan_by_beat.get(index)
        if plan is None:
            beats.append(old)
        elif "pieces" not in plan:
            beats.append(_footage_beat(old.start, old.end, plan))
        else:
            pieces = plan["pieces"]
            if abs(pieces[0]["start"] - old.start) > 1e-6 or abs(pieces[-1]["end"] - old.end) > 1e-6:
                raise ValueError(
                    f"beat {index}'s pieces run {pieces[0]['start']}-{pieces[-1]['end']}, "
                    f"not the beat's {old.start}-{old.end}")
            for k, piece in enumerate(pieces):
                start = old.start if k == 0 else piece["start"]
                end = old.end if k == len(pieces) - 1 else piece["end"]
                beats.append(_footage_beat(start, end, piece))
    result = ShotList(beats=beats, duration=shot_list.duration)
    validate_shot_list(result)
    return result


def _plan_text(plan: dict) -> str:
    era = plan["era"] if plan["era"] is not None else "modern"
    archival = f' | archival: {plan["archival_query"]!r}' if plan["archival_query"] else ""
    return f"{plan['query']!r} | era: {era}{archival}"


def format_cut_plan_report(cuts: list[FootageCut], plans: list[dict]) -> str:
    """The cut-by-cut plan for the Step 6b / Step 7 report: one line per cut, one indented line per
    piece of a split cut, and a summary line."""
    lines = []
    split_cuts = pieces_total = 0
    for cut, plan in zip(cuts, plans):
        head = f'{cut.start:.1f}-{cut.end:.1f}s "{cut.words}" -> '
        if "pieces" not in plan:
            lines.append(head + _plan_text(plan))
            continue
        split_cuts += 1
        pieces_total += len(plan["pieces"])
        lines.append(head + f"split into {len(plan['pieces'])} pieces:")
        for piece in plan["pieces"]:
            lines.append(f'    {piece["start"]:.2f}-{piece["end"]:.2f}s "{piece["words"]}" -> {_plan_text(piece)}')
    beats_total = len(cuts) - split_cuts + pieces_total
    lines.append(
        f"{len(cuts)} footage cuts planned; {split_cuts} cut{'' if split_cuts == 1 else 's'} split into "
        f"{pieces_total} pieces; {beats_total} footage beats")
    return "\n".join(lines)
