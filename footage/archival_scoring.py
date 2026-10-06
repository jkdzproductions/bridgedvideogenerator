"""The judge for archival film and photos: the prompt a scoring subagent gets, and the parser for its verdict."""
import json
from dataclasses import dataclass

from footage.archive_types import ArchiveCandidate
from footage.scoring_output import ScoringOutputError, _strip_code_fence

MAX_PHOTO_PICKS = 3

_RULES = """Rules (apply them to every candidate):
- ERA MATCH: the item must show the period of the spoken words, within about a decade of {era}. The right \
place and the right event (a war photo must be that war; a building must be that building). Reject a \
modern photo, a painting or drawing presented as a photograph, a colorized or restored-looking image, and \
anything that looks AI-generated. An item labelled photo that is a painting, drawing, print or other \
non-photograph must be rejected. A photograph of the right place from the closest available decade is fine.
- PROVENANCE: items with source=commons come from Wikimedia Commons, where anyone can upload, so they may \
include AI-generated pictures wrongly labelled public domain. Reject any item that looks AI-generated, that \
looks too clean or too modern for its stated date, or whose provenance (maker, date, collection) is not \
clear from its metadata.
- NOT TOO GRAPHIC: reject images or film showing bodies, severe injuries or close-ups of atrocity. Soldiers, \
ruins, crowds, cities, equipment and everyday scenes are fine.
- NO TEXT SCREENS: always reject a title card or any screen that is mostly text (a book page, a document, a \
newspaper clipping, a caption card), even when it is the closest match.
- REAL IMAGERY ONLY: if you cannot tell that an item is a real archival photograph or film of the period, \
reject it.
- For every candidate you reject, give a short reason in "rejected" (index and reason); the human reviewer \
reads these."""

# Plain strings (single braces): they are inserted as values, never run through str.format.
_PHOTO_TASK = """Pick 1 to 3 photographs for this shot, in the order they should appear while the words are spoken. \
Choose different views (do not pick three near-identical pictures), prefer sharp, well-exposed scans, and \
reject tiny, blurry or heavily cropped ones. Every pick must pass all the rules above. When no photo is \
perfect, relax only quality preferences (sharpness, variety of views, how close the decade is within the \
allowed window); never relax the real-imagery, not-graphic or no-text-screen rules. If every candidate \
breaks those rules, return an empty "picks" list and say why in "reasoning" (a person will then supply \
photos).

Respond with ONLY a JSON object, no other text:
{"picks": [<index>, ...], "rejected": [{"index": <int>, "reason": "<short reason>"}], "reasoning": "<one sentence>"}"""

_FILM_TASK = """Pick the ONE film clip that best shows the subject, or answer null if none is acceptable. The \
clip will be played for TARGET seconds. Each clip is listed with several still frames: view all frames of \
each clip; they come from the part that will be played, so judge graphic content from them. Reject a clip \
whose frames show graphic content, that is mostly titles, credits or leader, or that has heavy damage.

Respond with ONLY a JSON object, no other text. Either:
{"winner_index": <int>, "rejected": [{"index": <int>, "reason": "<short reason>"}], "reasoning": "<one sentence>"}
or, if no clip is acceptable:
{"winner_index": null, "rejected": [{"index": <int>, "reason": "<short reason>"}], "reasoning": "<one sentence on why none are acceptable>"}"""

_TINY_RULE = ("Reject tiny, blurry or heavily cropped images, and say so in the rejection reason (the size of "
              "an image is not listed, so judge it from the thumbnail).")

_ARTWORK_RULES = """Rules (apply them to every candidate):
- ERA MATCH: the artwork must depict the period of the spoken words (within about a decade of {era}) or have \
been made in it. The right place and the right event. Reject a modern photograph and anything that looks \
AI-generated. Hand-colored prints, lithographs, engravings and paintings are fine, and so are cleanly \
digitized museum scans; "colorized" or "restored-looking" applies only to photographs (a photograph that was \
digitally colorized is rejected, a hand-colored print is not).
- PROVENANCE: items with source=commons come from Wikimedia Commons, where anyone can upload, so they may \
include AI-generated pictures wrongly labelled public domain. Reject any item that looks AI-generated, that \
looks too clean or too modern for its stated date, or whose provenance (maker, date, collection) is not \
clear from its metadata.
- NOT TOO GRAPHIC: reject images or film showing bodies, severe injuries or close-ups of atrocity. Soldiers, \
ruins, crowds, cities, equipment and everyday scenes are fine.
- NO TEXT SCREENS: always reject a title card or any screen that is mostly text (a book page, a document, a \
newspaper clipping, a caption card), even when it is the closest match.
- REAL HISTORICAL ARTWORK ONLY: accept paintings, engravings, etchings, lithographs, drawings, prints and maps \
that are real works from a museum or archive collection, made in the period or later depicting it. Reject \
anything that looks AI-generated, any modern digital illustration, and any modern photograph.
- IMAGE QUALITY: """ + _TINY_RULE + """
- For every candidate you reject, give a short reason in "rejected" (index and reason); the human reviewer \
reads these."""

_MIXED_ANSWER = """Respond with ONLY a JSON object: {"picks": [<index>, ...], "rejected": [{"index": <int>, "reason": "<short reason>"}], "reasoning": "<one sentence>"}. Either pick 1 to 3 stills (artwork and/or photos, in the order they should appear), or exactly one stock clip, never a mix of stills and stock. Choose different views: never pick near-identical pictures. If nothing is acceptable return an empty picks list and say why in reasoning; the pipeline will stop and a human will supply an image."""


def _line(i: int, c: ArchiveCandidate, thumbnail_path) -> str:
    year = c.year if c.year is not None else "unknown"
    base = f'[{i}] source={c.source} title="{c.title}" year={year} creator="{c.creator}" rights="{c.rights}"'
    if c.kind == "film":
        if isinstance(thumbnail_path, (list, tuple)):
            return f"{base} duration={c.duration_seconds:.0f}s frames={', '.join(thumbnail_path)}"
        return f"{base} duration={c.duration_seconds:.0f}s thumbnail={thumbnail_path}"
    return f"{base} size={c.width}x{c.height} thumbnail={thumbnail_path}"


def build_archival_scoring_prompt(
    kind: str, subject: str, era: int, query: str, candidates: list[ArchiveCandidate],
    thumbnail_paths: list, target_duration: float,
) -> str:
    if kind not in ("film", "photo", "artwork"):
        raise ValueError(f"kind must be 'film', 'photo' or 'artwork', got {kind!r}")
    if len(candidates) != len(thumbnail_paths):
        raise ValueError(f"{len(candidates)} candidates but {len(thumbnail_paths)} thumbnail paths")
    lines = "\n".join(_line(i, c, p) for i, (c, p) in enumerate(zip(candidates, thumbnail_paths)))
    noun = {"film": "film clips", "photo": "photographs", "artwork": "artworks"}[kind]
    rules = _ARTWORK_RULES if kind == "artwork" else _RULES
    task = _FILM_TASK.replace("TARGET", f"{target_duration:.1f}") if kind == "film" else _PHOTO_TASK
    return f"""You are choosing real archival {noun} for one shot of a documentary video.

Target subject: {subject}
Period the spoken words are about: {era}
Search used to find these candidates: "{query}"
The shot lasts {target_duration:.1f} seconds.

Below are {len(candidates)} candidates. Use your Read tool to view each thumbnail image at its listed path \
(for film, every listed frame) before judging; do not guess from the metadata alone.

Candidates:
{lines}

{rules.format(era=era)}

{task}
"""


@dataclass
class ArchivalVerdict:
    picks: list[int]
    rejected: dict[int, str]
    reasoning: str


def _index_ok(value, num_candidates: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value < num_candidates


def _parse_payload(raw: str, num_candidates: int):
    """Shared JSON/fence/'rejected' parsing: returns (payload, rejected, reasoning)."""
    try:
        payload = json.loads(_strip_code_fence(raw))
    except json.JSONDecodeError as e:
        raise ScoringOutputError(f"archival verdict is not valid JSON: {e}") from e
    if not isinstance(payload, dict):
        raise ScoringOutputError("archival verdict must be a JSON object")

    rejected: dict[int, str] = {}
    raw_rejected = payload.get("rejected", [])
    if not isinstance(raw_rejected, list):
        raise ScoringOutputError("archival verdict 'rejected' must be a list")
    for entry in raw_rejected:
        if (not isinstance(entry, dict) or not _index_ok(entry.get("index"), num_candidates)
                or not isinstance(entry.get("reason"), str)):
            raise ScoringOutputError(f"archival verdict has a malformed 'rejected' entry: {entry!r}")
        rejected[entry["index"]] = entry["reason"]
    reasoning = payload.get("reasoning") if isinstance(payload.get("reasoning"), str) else ""
    return payload, rejected, reasoning


def parse_archival_verdict(raw: str, num_candidates: int, kind: str) -> ArchivalVerdict:
    if kind not in ("film", "photo", "artwork"):
        raise ScoringOutputError(f"kind must be 'film', 'photo' or 'artwork', got {kind!r}")
    payload, rejected, reasoning = _parse_payload(raw, num_candidates)

    if kind == "film":
        if "winner_index" not in payload:
            raise ScoringOutputError("film verdict is missing 'winner_index'")
        winner = payload["winner_index"]
        if winner is None:
            return ArchivalVerdict([], rejected, reasoning)
        if not _index_ok(winner, num_candidates):
            raise ScoringOutputError(f"winner_index must be an integer between 0 and {num_candidates - 1}, got {winner!r}")
        if winner in rejected:
            raise ScoringOutputError(f"candidate {winner} is both the winner and in 'rejected'")
        return ArchivalVerdict([winner], rejected, reasoning)

    picks = payload.get("picks")
    if (not isinstance(picks, list) or not 1 <= len(picks) <= MAX_PHOTO_PICKS
            or not all(_index_ok(p, num_candidates) for p in picks) or len(set(picks)) != len(picks)):
        raise ScoringOutputError(
            f"photo verdict needs 'picks': 1 to {MAX_PHOTO_PICKS} distinct indexes between 0 and "
            f"{num_candidates - 1}, got {picks!r}")
    contradictory = sorted(set(picks) & set(rejected))
    if contradictory:
        raise ScoringOutputError(f"candidates {contradictory} are both picked and in 'rejected'")
    return ArchivalVerdict(picks, rejected, reasoning)


@dataclass
class MixedVerdict:
    choice: str  # "stills", "stock" or "none"
    picks: list[int]
    rejected: dict[int, str]
    reasoning: str


def _stock_detail(c) -> str:
    p = c.payload
    if c.source == "pexels":
        return f"duration={p.duration}s resolution={p.width}x{p.height}"
    if c.source == "youtube":
        return f'title="{p.title}" channel="{p.channel_title}" duration={p.duration_seconds:.0f}s'
    if c.source == "envato":
        return f'title="{p.title}" author="{p.author}"'  # the scraped duration is not stored; none is invented
    raise ValueError(f"unknown stock source {c.source!r}")


def build_mixed_scoring_prompt(
    subject: str, era: int, archival_query: str, stock_query: str, stills: list, still_types: list,
    still_thumbs: list, stock: list, target_duration: float,
) -> str:
    if not len(stills) == len(still_types) == len(still_thumbs):
        raise ValueError(
            f"{len(stills)} stills, {len(still_types)} still types and {len(still_thumbs)} thumbnail paths must be the same length")
    bad = [t for t in still_types if t not in ("artwork", "photo")]
    if bad:
        raise ValueError(f"still types must be 'artwork' or 'photo', got {bad!r}")

    lines = []
    for i, (c, t, path) in enumerate(zip(stills, still_types, still_thumbs)):
        year = c.year if c.year is not None else "unknown"
        lines.append(f'[{i}] type={t} source={c.source} title="{c.title}" year={year} '
                     f'creator="{c.creator}" rights="{c.rights}" thumbnail={path}')
    for j, c in enumerate(stock):
        lines.append(f"[{len(stills) + j}] type=stock source={c.source} {_stock_detail(c)} thumbnail={c.thumbnail_path}")

    rules = ["Rules (apply them to every candidate):"]
    if "artwork" in still_types:
        rules.append(
            f"- ARTWORK: the artwork must depict the period of the spoken words (within about a decade of {era}) or "
            "have been made in it, the right place and the right event. REAL HISTORICAL ARTWORK ONLY: accept "
            "paintings, engravings, etchings, lithographs, drawings, prints and maps that are real works from a "
            "museum or archive collection, made in the period or later depicting it. Hand-colored prints, "
            "lithographs, engravings and paintings are fine, and so are cleanly digitized museum scans; "
            "\"colorized\" or \"restored-looking\" applies only to photographs, never to artwork. Reject anything "
            "that looks AI-generated, any modern digital illustration, and any modern photograph.")
    if "photo" in still_types:
        rules.append(
            f"- PHOTO: the photograph must show the period of the spoken words, within about a decade of {era}, "
            "the right place and the right event. It must be a real archival photograph: reject a modern photo, a "
            "painting or drawing presented as a photograph, a colorized or restored-looking image, and anything "
            "that looks AI-generated.")
    if stills:
        rules.append(
            "- STILL SOURCES: A still whose source is met or loc may be a genuine historical photograph OR genuine "
            "historical artwork (painting, engraving, etching, lithograph, print, drawing, map). A still whose "
            "source is commons must be a genuine photograph: reject any painting, drawing, print, engraving, map "
            "or other non-photograph from commons, whatever its label. "
            f"Whatever its type label, judge a still that is a photograph as a photograph: it must be a real "
            f"photograph made within about a decade of {era}, and a genuine period photograph labelled artwork is "
            "acceptable; a photograph made much later than the period (for example a later reunion or memorial "
            "photograph) must be rejected.")
        rules.append("- IMAGE QUALITY (stills): " + _TINY_RULE)
    if stock:
        rules.append(
            "- STOCK FOOTAGE is acceptable only when nothing in the thumbnail contradicts the period: no modern "
            "buildings, vehicles, clothing, signs, screens or people in modern dress; timeless nature, sea and sky "
            "are fine. Prefer a real still when it shows the subject more specifically; prefer stock only when it "
            "clearly shows the subject without breaking the period. Reject anything that looks AI-generated, CGI, "
            "animated or rendered, and any title or channel that suggests AI, animation, a game, a reenactment or a "
            "documentary re-creation. Stock is judged from the thumbnail plus the listed details only."
            + (" Only the opening of a YouTube video (from 0:00, up to the shot length) is used, so judge its "
               "thumbnail as a proxy for that opening." if any(c.source == "youtube" for c in stock) else ""))
    rules.append(
        "- PROVENANCE: items with source=commons come from Wikimedia Commons, where anyone can upload, so they "
        "may include AI-generated pictures wrongly labelled public domain. Reject any item that looks "
        "AI-generated, that looks too clean or too modern for its stated date, or whose provenance (maker, date, "
        "collection) is not clear from its metadata.")
    rules.append(
        "- NOT TOO GRAPHIC: reject images or film showing bodies, severe injuries or close-ups of atrocity. "
        "Soldiers, ruins, crowds, cities, equipment and everyday scenes are fine.")
    rules.append(
        "- NO TEXT SCREENS: always reject a title card or any screen that is mostly text (a book page, a "
        "document, a newspaper clipping, a caption card), even when it is the closest match.")
    rules.append(
        '- For every candidate you reject, give a short reason in "rejected" (index and reason); the human '
        "reviewer reads these.")

    candidates = "\n".join(lines)
    rules_text = "\n".join(rules)
    return f"""You are choosing imagery for one shot of a documentary video about a period when photographs may be scarce or absent.

Target subject: {subject}
Period the spoken words are about: {era}
Archive search used for the stills: "{archival_query}"
Stock search used for the footage: "{stock_query}"
The shot lasts {target_duration:.1f} seconds.

Candidates (stills first, then stock footage; view every thumbnail with your Read tool at its path):
{candidates}

{rules_text}

{_MIXED_ANSWER}
"""


def parse_mixed_verdict(raw: str, types: list) -> MixedVerdict:
    n = len(types)
    unknown = [t for t in types if t not in ("artwork", "photo", "stock")]
    if unknown:
        raise ScoringOutputError(f"mixed verdict: unknown candidate label(s) {unknown!r}; expected artwork, photo or stock")
    payload, rejected, reasoning = _parse_payload(raw, n)
    picks = payload.get("picks")
    if (not isinstance(picks, list) or not all(_index_ok(p, n) for p in picks)
            or len(set(picks)) != len(picks)):
        raise ScoringOutputError(
            f"mixed verdict needs 'picks': a list of distinct indexes between 0 and {n - 1}, got {picks!r}")
    contradictory = sorted(set(picks) & set(rejected))
    if contradictory:
        raise ScoringOutputError(f"candidates {contradictory} are both picked and in 'rejected'")
    if not picks:
        return MixedVerdict("none", [], rejected, reasoning)
    kinds = {"stock" if types[p] == "stock" else "stills" for p in picks}
    if len(kinds) > 1:
        raise ScoringOutputError(f"mixed verdict picks stills and stock together: {picks!r}")
    if kinds == {"stock"}:
        if len(picks) != 1:
            raise ScoringOutputError(f"mixed verdict needs exactly one stock clip, got {picks!r}")
        return MixedVerdict("stock", picks, rejected, reasoning)
    if len(picks) > MAX_PHOTO_PICKS:
        raise ScoringOutputError(f"mixed verdict needs 1 to {MAX_PHOTO_PICKS} stills, got {picks!r}")
    return MixedVerdict("stills", picks, rejected, reasoning)
