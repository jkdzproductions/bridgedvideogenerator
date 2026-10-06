# footage/archival_build.py
"""Stage 2 for cuts about a period before 1960: search, judge, render and record.
Each function is one step of the agent-driven Stage 2 loop in CLAUDE.md; they share state through files
in WORK_DIR because every step runs as its own process, like the modern footage loop."""
import dataclasses
import json
import os
import shutil
import subprocess
from typing import Optional
from urllib.parse import urlparse

from footage.archival_render import (
    ArchivalRenderError, build_frame_command, film_frame_times, photo_shares, render_film_beat, render_photo_beat,
)
from footage.archival_scoring import MAX_PHOTO_PICKS, ArchivalVerdict, build_archival_scoring_prompt, parse_archival_verdict
from footage.archive_search import ArchivalSearchError, search_film, search_photos
from footage.archive_types import ArchiveCandidate, ArchiveError, fetch_to_file

WORK_DIR = "archival_work"
PICKS_PATH = "archival_picks.json"
USED_IDS_PATH = "used_footage_ids.json"
REVIEW_PATH = "archival_review.html"
FRAME_TIMEOUT_SECONDS = 30  # per remote ffmpeg frame read
MAX_FILM_CANDIDATES_FOR_FRAMES = 5  # frames are read from archive.org over the network; keep the step short


class FrameTimeout(Exception):
    """A remote frame read timed out: the candidate is dropped and its remaining frames are not tried."""


def reset_archival_state() -> None:
    shutil.rmtree(WORK_DIR, ignore_errors=True)
    for path in (PICKS_PATH, REVIEW_PATH):
        if os.path.exists(path):
            os.remove(path)


def prompt_path(kind: str, beat_index: int) -> str:
    return os.path.join(WORK_DIR, f"{kind}_prompt_{beat_index}.txt")


def candidates_path(kind: str, beat_index: int) -> str:
    return os.path.join(WORK_DIR, f"{kind}_candidates_{beat_index}.json")


def save_candidates(path: str, candidates: list[ArchiveCandidate]) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w") as f:
        json.dump([dataclasses.asdict(c) for c in candidates], f, indent=2)


def load_candidates(path: str) -> list[ArchiveCandidate]:
    with open(path) as f:
        return [ArchiveCandidate(**d) for d in json.load(f)]


def _used_archive_ids(used_pairs: list) -> frozenset:
    return frozenset(display_id for source, display_id in used_pairs if source == "archive")


def frames_path(beat_index: int) -> str:
    return os.path.join(WORK_DIR, f"film_frames_{beat_index}.json")


def _download_thumbnails(candidates: list[ArchiveCandidate], kind: str, beat_index: int) -> tuple:
    """(kept candidates, their thumbnail paths). A candidate whose thumbnail fails to download is dropped
    with a warning, so one 404 never sinks the beat. Paths are absolute: the judge's Read tool needs them."""
    directory = os.path.abspath(os.path.join(WORK_DIR, f"{kind}_thumbs_{beat_index}"))
    kept, paths = [], []
    for c in candidates:
        try:
            paths.append(fetch_to_file(c.thumbnail_url, os.path.join(directory, f"{c.safe_id}.jpg")))
        except ArchiveError as e:
            print(f"WARNING: dropped {c.display_id}: thumbnail download failed ({e})")
            continue
        kept.append(c)
    return kept, paths


def _extract_frames(candidate: ArchiveCandidate, target: float, directory: str) -> list[str]:
    """Still frames from the part of the film that will actually play (absolute paths). A frame that
    ffmpeg cannot read is skipped; a missing ffmpeg is an error."""
    directory = os.path.abspath(directory)
    os.makedirs(directory, exist_ok=True)
    frames = []
    for k, t in enumerate(film_frame_times(candidate.duration_seconds, target)):
        out = os.path.join(directory, f"{candidate.safe_id}_{k}.jpg")
        if os.path.exists(out):
            os.remove(out)
        try:
            result = subprocess.run(build_frame_command(candidate.media_url, t, out),
                                    capture_output=True, text=True, timeout=FRAME_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired as e:
            raise FrameTimeout(f"frame read timed out after {FRAME_TIMEOUT_SECONDS}s") from e
        except OSError as e:
            raise ArchivalRenderError(f"could not run ffmpeg for {candidate.display_id}: {e}") from e
        if result.returncode == 0 and os.path.exists(out) and os.path.getsize(out) > 0:
            frames.append(out)
    return frames


def _write_prompt(kind: str, beat: dict, query: str, candidates: list[ArchiveCandidate], thumbs: list) -> None:
    prompt = build_archival_scoring_prompt(
        kind, beat["subject"], beat["era"], query, candidates, thumbs, beat["end"] - beat["start"])
    save_candidates(candidates_path(kind, beat["beat_index"]), candidates)
    with open(prompt_path(kind, beat["beat_index"]), "w") as f:
        f.write(prompt)


def prepare_film(beat: dict, used_pairs: list) -> bool:
    """Search once for film on the specific query and extract still frames from the part of each film that
    would play. True when at least one film at least as long as the cut has frames and its judging prompt was
    written; False means: go straight to photos. A candidate with no extractable frame is dropped."""
    target = beat["end"] - beat["start"]
    films = [f for f in search_film(beat["archival_query"], beat["era"], _used_archive_ids(used_pairs))
             if f.duration_seconds >= target]
    directory = os.path.join(WORK_DIR, f"film_thumbs_{beat['beat_index']}")
    kept, frames = [], {}
    for film in films[:MAX_FILM_CANDIDATES_FOR_FRAMES]:
        try:
            got = _extract_frames(film, target, directory)
        except FrameTimeout as e:
            print(f"WARNING: dropped {film.display_id}: {e} (timed out)")
            continue
        print(f"film candidate {film.display_id}: {len(got)} frames")
        if not got:
            print(f"WARNING: dropped {film.display_id}: could not extract any frame from the film")
            continue
        kept.append(film)
        frames[film.display_id] = got
    if not kept:
        return False
    os.makedirs(WORK_DIR, exist_ok=True)
    with open(frames_path(beat["beat_index"]), "w") as f:
        json.dump(frames, f, indent=2)
    _write_prompt("film", beat, beat["archival_query"], kept, [frames[c.display_id] for c in kept])
    return True


def prepare_photos(beat: dict, used_pairs: list) -> None:
    """Search photos (with the broadening ladder) and write the judging prompt. Raises
    ArchivalSearchError when nothing at all was found, or no found photo's thumbnail could be downloaded,
    which stops the stage."""
    photos = search_photos(beat["era"], beat["archival_query"], beat["archival_broad_query"],
                           _used_archive_ids(used_pairs))
    kept, thumbs = _download_thumbnails(photos, "photo", beat["beat_index"])
    if not kept:
        raise ArchivalSearchError(
            f"beat {beat['beat_index']}: every candidate's thumbnail failed to download "
            f"({len(photos)} photos found for era {beat['era']}); re-run this step once, and if it repeats "
            "the archive is down")
    _write_prompt("photo", beat, beat["archival_query"], kept, thumbs)


def _record(beat: dict, kind: str, verdict, candidates: list[ArchiveCandidate], local_paths: dict) -> dict:
    def item(i: int) -> dict:
        c = candidates[i]
        return {"source": c.source, "item_id": c.item_id, "display_id": c.display_id, "title": c.title,
                "year": c.year, "creator": c.creator, "rights": c.rights, "page_url": c.page_url,
                "local_path": local_paths.get(i, "")}

    return {
        "beat_index": beat["beat_index"], "start": beat["start"], "end": beat["end"], "era": beat["era"],
        "subject": beat["subject"], "kind": kind, "reasoning": verdict.reasoning,
        "items": [item(i) for i in verdict.picks],
        "rejected": [{"display_id": candidates[i].display_id, "title": candidates[i].title,
                      "page_url": candidates[i].page_url, "reason": reason}
                     for i, reason in sorted(verdict.rejected.items())],
    }


def _write_json_atomic(path: str, data, indent=None) -> None:
    """Write via a temp file in the same directory, then os.replace, so a crash never leaves half a file."""
    tmp = f"{path}.tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=indent)
    os.replace(tmp, path)


def append_pick(record: dict, picks_path: str = PICKS_PATH, used_path: str = USED_IDS_PATH,
                used_pairs: Optional[list] = None) -> None:
    """Record a pick and mark its items used. used_pairs, when given, are the exact pairs to add; by default
    each item is marked ["archive", display_id]. The used ids are written first: a crash between the two files
    then only over-excludes an item, it never lets one be reused."""
    if used_pairs is None:
        used_pairs = [["archive", item["display_id"]] for item in record["items"]]
    used = json.load(open(used_path)) if os.path.exists(used_path) else []
    for pair in used_pairs:
        if list(pair) not in used:
            used.append(list(pair))
    _write_json_atomic(used_path, used)

    picks = json.load(open(picks_path)) if os.path.exists(picks_path) else []
    picks = [p for p in picks if p["beat_index"] != record["beat_index"]] + [record]
    picks.sort(key=lambda p: p["beat_index"])
    _write_json_atomic(picks_path, picks, indent=2)


def finish_film(beat: dict, raw_verdict: str, dest_dir: str = "footage_output") -> bool:
    candidates = load_candidates(candidates_path("film", beat["beat_index"]))
    verdict = parse_archival_verdict(raw_verdict, len(candidates), "film")
    if not verdict.picks:
        return False
    dest = os.path.join(dest_dir, f"beat_{beat['beat_index']}.mp4")
    winner = candidates[verdict.picks[0]]
    render_film_beat(winner, dest, beat["end"] - beat["start"])
    # The first extracted frame stands in for the clip on the review sheet.
    frames = {}
    if os.path.exists(frames_path(beat["beat_index"])):
        with open(frames_path(beat["beat_index"])) as f:
            frames = json.load(f)
    winner_frames = frames.get(winner.display_id) or []
    local = {verdict.picks[0]: os.path.abspath(winner_frames[0])} if winner_frames else {}
    append_pick(_record(beat, "film", verdict, candidates, local))
    return True


def _extension(url: str) -> str:
    ext = os.path.splitext(urlparse(url).path)[1].lower()
    return ext if ext in (".jpg", ".jpeg", ".png") else ".jpg"


def _render_still_picks(beat: dict, kind: str, candidates: list, verdict: ArchivalVerdict, dest_dir: str,
                        item_kinds: Optional[dict] = None, fetch=None, render=None) -> None:
    """Download the picked stills in order, render them as one beat, record the pick and mark it used.
    Only the stills that fit the cut (at least 2 s each) are shown, so only those are rendered, recorded and
    marked used. item_kinds (candidate index -> "artwork"/"photo"), when given, adds a per-item "kind".
    fetch/render default to this module's fetch_to_file/render_photo_beat; callers in other modules pass theirs
    so their own names stay patchable."""
    fetch = fetch or fetch_to_file
    render = render or render_photo_beat
    shown = len(photo_shares(beat["end"] - beat["start"], len(verdict.picks)))
    verdict = ArchivalVerdict(verdict.picks[:shown], verdict.rejected, verdict.reasoning)
    local_paths = {}
    for i in verdict.picks:
        c = candidates[i]
        local_paths[i] = os.path.abspath(fetch(
            c.media_url, os.path.join(WORK_DIR, "photos", f"{c.safe_id}{_extension(c.media_url)}")))
    dest = os.path.join(dest_dir, f"beat_{beat['beat_index']}.mp4")
    render([local_paths[i] for i in verdict.picks], dest, beat["end"] - beat["start"],
           os.path.join(WORK_DIR, f"render_{beat['beat_index']}"))
    record = _record(beat, kind, verdict, candidates, local_paths)
    if item_kinds is not None:
        for item, i in zip(record["items"], verdict.picks):
            item["kind"] = item_kinds[i]
    append_pick(record)


def finish_photos(beat: dict, raw_verdict: str, dest_dir: str = "footage_output") -> None:
    candidates = load_candidates(candidates_path("photo", beat["beat_index"]))
    verdict = parse_archival_verdict(raw_verdict, len(candidates), "photo")
    _render_still_picks(beat, "photo", candidates, verdict, dest_dir)


def render_manual_photos(beat: dict, photo_paths: list, source_note: str, dest_dir: str = "footage_output") -> None:
    """Render one beat from photos Josh supplied (real archival photos only) and record them like any pick.
    source_note is required: every picture needs a recorded source or license."""
    if not isinstance(source_note, str) or not source_note.strip():
        raise ValueError("source_note is required: say where each photo came from and its license")
    if not photo_paths:
        raise ValueError("no photo paths given")
    if len(photo_paths) > MAX_PHOTO_PICKS:
        raise ValueError(f"at most {MAX_PHOTO_PICKS} photos per beat, got {len(photo_paths)}")
    for path in photo_paths:
        if not os.path.isfile(path):
            raise ValueError(f"photo file not found: {path}")
    # Only the photos that fit the cut (at least 2 s each) are shown, so only those are rendered and recorded.
    photo_paths = list(photo_paths)[:len(photo_shares(beat["end"] - beat["start"], len(photo_paths)))]
    dest = os.path.join(dest_dir, f"beat_{beat['beat_index']}.mp4")
    render_photo_beat(list(photo_paths), dest, beat["end"] - beat["start"],
                      os.path.join(WORK_DIR, f"render_{beat['beat_index']}"))
    items = []
    for path in photo_paths:
        name = os.path.basename(path)
        items.append({"source": "manual", "item_id": f"manual:{name}", "display_id": f"manual:{name}",
                      "title": name, "year": None, "creator": "", "rights": source_note.strip(), "page_url": "",
                      "local_path": os.path.abspath(path)})
    append_pick({
        "beat_index": beat["beat_index"], "start": beat["start"], "end": beat["end"], "era": beat["era"],
        "subject": beat["subject"], "kind": "photo", "reasoning": "supplied by Josh", "items": items,
        "rejected": [],
    })
