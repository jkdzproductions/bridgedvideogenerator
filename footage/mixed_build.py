# footage/mixed_build.py
"""Stage 2 for a cut about a period before 1900 whose judge chooses between real stills (artwork and, for
photo_or_artwork, photos) and, for artwork_or_stock, stock footage. Same agent-driven two-step shape as
archival_build: prepare_mixed writes the prompt and state, finish_mixed reads the judge's verdict."""
import dataclasses
import json
import os

from footage.archival_build import (
    WORK_DIR, ArchivalVerdict, _download_thumbnails, _render_still_picks, _used_archive_ids, append_pick,
)
from footage.archival_scoring import build_mixed_scoring_prompt, parse_mixed_verdict
from footage.archive_artwork import search_artwork
from footage.archive_search import ArchivalSearchError, search_photos
# fetch_to_file and render_photo_beat are imported here so tests can patch them in this module;
# finish_mixed hands them to _render_still_picks.
from footage.archive_types import ArchiveCandidate, fetch_to_file
from footage.archival_render import photo_shares, render_photo_beat
from footage.combined_build import CombinedCandidate, prepare_combined_scoring, resolve_combined_winner
from footage.envato import EnvatoCandidate
from footage.pexels import PexelsCandidate, VideoFile
from footage.youtube import YouTubeCandidate


def mixed_prompt_path(beat_index: int) -> str:
    return os.path.join(WORK_DIR, f"mixed_prompt_{beat_index}.txt")


def mixed_state_path(beat_index: int) -> str:
    return os.path.join(WORK_DIR, f"mixed_state_{beat_index}.json")


def _stock_to_dict(c: CombinedCandidate) -> dict:
    return {"source": c.source, "display_id": c.display_id, "thumbnail_path": c.thumbnail_path,
            "payload": dataclasses.asdict(c.payload)}


def _stock_from_dict(c: dict) -> CombinedCandidate:
    p = c["payload"]
    if c["source"] == "pexels":
        payload = PexelsCandidate(
            id=p["id"], url=p["url"], thumbnail_url=p["thumbnail_url"], duration=p["duration"],
            width=p["width"], height=p["height"], video_files=[VideoFile(**vf) for vf in p["video_files"]])
    elif c["source"] == "envato":
        payload = EnvatoCandidate(**p)
    else:
        payload = YouTubeCandidate(**p)
    return CombinedCandidate(c["source"], c["display_id"], c["thumbnail_path"], payload)


def save_stock_candidates(path: str, candidates: list) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w") as f:
        json.dump([_stock_to_dict(c) for c in candidates], f, indent=2)


def load_stock_candidates(path: str) -> list:
    with open(path) as f:
        return [_stock_from_dict(c) for c in json.load(f)]


def _save_state(beat_index: int, stills: list, still_types: list, stock: list) -> None:
    os.makedirs(WORK_DIR, exist_ok=True)
    with open(mixed_state_path(beat_index), "w") as f:
        json.dump({"stills": [dataclasses.asdict(c) for c in stills], "still_types": still_types,
                   "stock": [_stock_to_dict(c) for c in stock]}, f, indent=2)


def _load_state(beat_index: int) -> tuple:
    with open(mixed_state_path(beat_index)) as f:
        state = json.load(f)
    return ([ArchiveCandidate(**d) for d in state["stills"]], state["still_types"],
            [_stock_from_dict(c) for c in state["stock"]])


def prepare_mixed(beat: dict, used_pairs: list, pexels_api_key: str, youtube_api_key: str,
                  excluded_channel_ids: frozenset, envato_profile_dir: str) -> dict:
    """Search the stills (and stock for artwork_or_stock), download the still thumbnails and write the judging
    prompt and state. Returns the candidate counts. Raises ArchivalSearchError when nothing at all was found."""
    n = beat["beat_index"]
    if beat["medium"] not in ("photo_or_artwork", "artwork_or_stock"):
        raise ValueError(f"beat {n}: mixed beats need medium 'photo_or_artwork' or 'artwork_or_stock', got {beat['medium']!r}")
    exclude = _used_archive_ids(used_pairs)
    artwork = search_artwork(beat["era"], beat["archival_query"], beat["archival_broad_query"], exclude)
    photos = []
    if beat["medium"] == "photo_or_artwork":
        try:
            photos = search_photos(beat["era"], beat["archival_query"], beat["archival_broad_query"], exclude)
        except ArchivalSearchError as e:
            print(f"WARNING: no archival photos found for beat {n} ({e})")
    # Explicit (candidate, type) pairs, artwork first. The same picture can come back from both searches (LoC is
    # in both), so keep only the first occurrence of each display_id: a LoC item keeps its artwork label.
    pairs, seen = [], set()
    for c, t in [(c, "artwork") for c in artwork] + [(c, "photo") for c in photos]:
        if c.display_id not in seen:
            seen.add(c.display_id)
            pairs.append((c, t))
    stills, still_types, thumbs = [], [], []
    for c, t in pairs:
        kept, paths = _download_thumbnails([c], "mixed", n)  # one at a time: types can never misalign
        if kept:
            stills.append(c)
            still_types.append(t)
            thumbs.extend(paths)

    stock = []
    if beat["medium"] == "artwork_or_stock":
        try:
            stock, _ = prepare_combined_scoring(
                query=beat["query"], subject=beat["subject"], pexels_api_key=pexels_api_key,
                youtube_api_key=youtube_api_key, excluded_channel_ids=excluded_channel_ids,
                thumbnails_dir=f"thumbnails/beat_{n}", envato_profile_dir=envato_profile_dir,
                exclude_ids=frozenset(tuple(p) for p in used_pairs))
        except ValueError as e:
            if "no candidates found" not in str(e):
                raise  # only the "nothing found" case is a soft failure
            print(f"WARNING: no stock footage candidates for beat {n} ({e})")
            stock = []

    if not stills and not stock:
        raise ArchivalSearchError(
            f"beat {n}: no artwork, photos or stock footage found for era {beat['era']} "
            f"(archive queries {beat['archival_query']!r} / {beat['archival_broad_query']!r}, "
            f"stock query {beat.get('query', '')!r}); re-run this step once, and if it repeats the sources are down")

    prompt = build_mixed_scoring_prompt(
        beat["subject"], beat["era"], beat["archival_query"], beat.get("query", ""), stills, still_types, thumbs,
        stock, beat["end"] - beat["start"])
    _save_state(n, stills, still_types, stock)
    with open(mixed_prompt_path(n), "w") as f:
        f.write(prompt)
    return {"artwork": still_types.count("artwork"), "photo": still_types.count("photo"), "stock": len(stock)}


def _finish_stock(beat: dict, verdict, stills: list, stock: list, envato_profile_dir: str, dest_dir: str) -> None:
    index = verdict.picks[0] - len(stills)  # the judge numbers stock after the stills
    winner = stock[index]
    dest = os.path.join(dest_dir, f"beat_{beat['beat_index']}.mp4")
    resolve_combined_winner(stock, index, dest, beat["end"] - beat["start"], envato_profile_dir)

    rejected = []
    for i, reason in sorted(verdict.rejected.items()):
        if i < len(stills):
            c = stills[i]
            rejected.append({"display_id": c.display_id, "title": c.title, "page_url": c.page_url, "reason": reason})
        else:
            s = stock[i - len(stills)]
            rejected.append({"display_id": s.display_id, "title": f"stock footage ({s.source})",
                             "page_url": "", "reason": reason})
    record = {
        "beat_index": beat["beat_index"], "start": beat["start"], "end": beat["end"], "era": beat["era"],
        "subject": beat["subject"], "kind": "stock", "reasoning": verdict.reasoning,
        "items": [{"source": winner.source, "item_id": winner.display_id, "display_id": winner.display_id,
                   "title": f"stock footage ({winner.source})", "year": None, "creator": "",
                   "rights": f"stock license ({winner.source})", "page_url": "",
                   "local_path": os.path.abspath(winner.thumbnail_path)}],
        "rejected": rejected,
    }
    append_pick(record, used_pairs=[[winner.source, winner.display_id]])


def finish_mixed(beat: dict, raw_verdict: str, envato_profile_dir: str, dest_dir: str = "footage_output") -> str:
    """Apply the judge's verdict: returns "stills", "stock" or "none" (nothing written for "none")."""
    stills, still_types, stock = _load_state(beat["beat_index"])
    verdict = parse_mixed_verdict(raw_verdict, still_types + ["stock"] * len(stock))
    if verdict.choice == "none":
        return "none"
    if verdict.choice == "stock":
        _finish_stock(beat, verdict, stills, stock, envato_profile_dir, dest_dir)
        return "stock"
    # Only the stills that fit the cut are rendered and recorded, so the pick-level kind comes from those.
    shown = verdict.picks[:len(photo_shares(beat["end"] - beat["start"], len(verdict.picks)))]
    kinds = {still_types[i] for i in shown}
    kind = kinds.pop() if len(kinds) == 1 else "mixed"
    still_verdict = ArchivalVerdict(
        verdict.picks, {i: r for i, r in verdict.rejected.items() if i < len(stills)}, verdict.reasoning)
    _render_still_picks(beat, kind, stills, still_verdict, dest_dir, dict(enumerate(still_types)),
                        fetch=fetch_to_file, render=render_photo_beat)
    return "stills"
