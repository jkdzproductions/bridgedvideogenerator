# footage/batch.py
"""Stage 2 in batches: prepare many beats at once, let several judge subagents run in parallel, then apply the
verdicts in beat order. Run as `.venv/bin/python -m footage.batch <command> ...` (CLAUDE.md Stage 2).

Why: one 192-beat video took 13+ hours because every beat went strictly one at a time (search, ONE judge,
save, download) with serial network waits. The searches and judges of different beats are independent; only
"which clip is already used" ties beats together, and that is decided when verdicts are APPLIED, in beat order,
by the same rules as before (a winner that an earlier beat already took is refused, never swapped for another
candidate).

Commands (beats default to every beat of that kind that has no footage_output/beat_<n>.mp4 yet):
  status                         what is left to source
  prep-modern [beats]            Step 2a for many beats (Pexels + YouTube + Envato; records YouTube quota)
  apply-modern [beats]           Step 2d for many beats, in order
  prep-film / apply-film         Step 2A a-b for "photo"-medium archival beats
  prep-photos / apply-photos     Step 2A c-d (prep-photos needs the beat list printed by prep-film/apply-film)
  prep-mixed / apply-mixed       Step 2M
  save-response KIND BEAT        save a judge's answer (stdin or --file) to that beat's response file
  extract KIND BEAT=PATH ...     the same, from subagent output/transcript files
Exit codes: 0 all fine; 2 some beats flagged (no acceptable footage, duplicate winner); 1 an error stopped it.
"""
import argparse
import concurrent.futures
import io
import json
import os
import re
import sys
import threading
import traceback
from collections import Counter
from dataclasses import dataclass
from typing import Callable, Optional

from footage.archival_build import (
    WORK_DIR, candidates_path, finish_film, finish_photos, load_candidates, prepare_film, prepare_photos,
    prompt_path,
)
from footage.archival_render import photo_shares
from footage.archival_scoring import parse_archival_verdict, parse_mixed_verdict
from footage.combined_build import prepare_combined_scoring, resolve_combined_winner
from footage.mixed_build import (
    _load_state, finish_mixed, load_stock_candidates, mixed_prompt_path, prepare_mixed, save_stock_candidates,
)
from footage.quota import PER_BEAT_UNITS, record_spend
from footage.scoring_output import NoAcceptableCandidateError, _strip_code_fence, parse_scoring_output

# Safe defaults, measured against what each step shares:
# - prep: 4 beats at a time. Searches and thumbnail downloads are network waits; the Envato part of each beat
#   is serialized by combined_build.ENVATO_PROFILE_LOCK (one browser per profile); quota recording is locked.
#   More than 4 mostly adds load on Commons/LoC/archive.org (which rate-limit) without finishing sooner.
# - judges: up to 8 subagents in parallel (they only read thumbnails and answer JSON).
DEFAULT_PREP_WORKERS = 4
MAX_PARALLEL_JUDGES = 8

QUOTA_PATH = "youtube_quota_usage.json"
USED_IDS_PATH = "used_footage_ids.json"
OUTPUT_DIR = "footage_output"
MIXED_MEDIA = ("photo_or_artwork", "artwork_or_stock")


@dataclass
class BeatResult:
    status: str  # ok | needs_photos | done | skipped | no_acceptable | duplicate | error | not_started
    message: str = ""
    judge: bool = False  # prep only: a judge subagent must now answer this beat's prompt


FLAGGED = ("no_acceptable", "duplicate")
FAILED = ("error", "not_started")


# --- files ---------------------------------------------------------------------------------------

def output_path(n: int) -> str:
    return os.path.join(OUTPUT_DIR, f"beat_{n}.mp4")


def _modern_prompt(n: int) -> str:
    return f"scoring_prompt_{n}.txt"


def _modern_response(n: int) -> str:
    return f"scoring_response_{n}.txt"


def _archival_response(kind: str, n: int) -> str:
    return os.path.join(WORK_DIR, f"{kind}_response_{n}.txt")


# kind -> (prompt path, response path, key the verdict JSON must have, judge model)
JUDGES = {
    "modern": (_modern_prompt, _modern_response, "winner_index", "default"),
    "film": (lambda n: prompt_path("film", n), lambda n: _archival_response("film", n), "winner_index", "opus"),
    "photo": (lambda n: prompt_path("photo", n), lambda n: _archival_response("photo", n), "picks", "opus"),
    "mixed": (mixed_prompt_path, lambda n: _archival_response("mixed", n), "picks", "opus"),
}


def _load(path: str, default=None):
    if default is not None and not os.path.exists(path):
        return default
    with open(path) as f:
        return json.load(f)


def _write_text_atomic(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w") as f:
        f.write(text)
    os.replace(tmp, path)


def _remove(path: str) -> None:
    if os.path.exists(path):
        os.remove(path)


def _used_pairs() -> list:
    return [list(p) for p in _load(USED_IDS_PATH, [])]


def _modern_beats() -> dict:
    return {int(i): (q, s) for i, q, s in _load("footage_beats.json")}


def _archival_beats(media: tuple) -> dict:
    return {b["beat_index"]: b for b in _load("archival_beats.json") if b["medium"] in media}


def _duration(n: int) -> float:
    return _load("beat_durations.json")[str(n)]


def _video_started() -> float:
    """When Stage 2 Step 1 ran for this video: it writes footage_beats.json. Root-level prompt/response files
    older than that belong to an earlier video (Step 1 does not delete them)."""
    return os.path.getmtime("footage_beats.json") if os.path.exists("footage_beats.json") else 0.0


def _is_current(path: str) -> bool:
    return os.path.exists(path) and os.path.getmtime(path) >= _video_started()


def _select(beats: Optional[list], known: dict, label: str, prompt_of: Optional[Callable] = None) -> list:
    """The beats to work on, in beat order, each once. Given beats must belong to `known`. By default: every
    beat of `known` without a clip (and, for apply, with a prompt written by prep for THIS video)."""
    if beats is None:
        return [n for n in sorted(known) if not os.path.exists(output_path(n))
                and (prompt_of is None or _is_current(prompt_of(n)))]
    for n in beats:
        if n not in known:
            raise ValueError(f"beat {n} is not a {label} beat")
    return sorted(set(beats))


def _read_response(kind: str, n: int) -> str:
    """The judge's saved answer for beat n, only when it answers this video's current prompt."""
    prompt_of, response_of, _, _ = JUDGES[kind]
    prompt, response = prompt_of(n), response_of(n)
    if not os.path.exists(prompt):
        raise FileNotFoundError(f"no judging prompt at {prompt}: run the prep step for beat {n} first")
    if not _is_current(prompt):
        raise ValueError(f"{prompt} is from an earlier video (older than footage_beats.json): run the prep step "
                         f"for beat {n} again and judge it again")
    if not os.path.exists(response):
        raise FileNotFoundError(f"no judge response saved at {response}")
    if os.path.getmtime(response) < os.path.getmtime(prompt):
        raise ValueError(f"{response} is older than its prompt {prompt} (the beat was prepared again after it "
                         "was judged): judge it again")
    with open(response) as f:
        return f.read()


# --- running beats -------------------------------------------------------------------------------

class _ThreadOutput(io.TextIOBase):
    """sys.stdout stand-in for the prep thread pool: each complete line a worker prints goes out at once,
    labelled "[beat n] ", so progress shows while a beat runs and lines of different beats never mix mid-line."""

    def __init__(self, real, lock):
        self.real, self.lock = real, lock
        self.local = threading.local()

    def write(self, text):
        beat = getattr(self.local, "beat", None)
        if beat is None:
            with self.lock:
                self.real.write(text)
            return len(text)
        pending = getattr(self.local, "pending", "") + text
        *lines, self.local.pending = pending.split("\n")
        if lines:
            with self.lock:
                for line in lines:
                    self.real.write(f"[beat {beat}] {line}\n")
                self.real.flush()
        return len(text)

    def start(self, beat):
        self.local.beat, self.local.pending = beat, ""

    def end(self):
        if getattr(self.local, "pending", ""):
            self.write("\n")
        self.local.beat = None

    def flush(self):
        self.real.flush()


def _report(real, lock, n: int, result: BeatResult) -> None:
    with lock:
        real.write(f"beat {n}: {result.status.upper()}{' ' + result.message if result.message else ''}\n")
        real.flush()


def _run_parallel(beats: list, work: Callable[[int], BeatResult], workers: int) -> dict:
    """Run work(n) for each beat on a small thread pool. After the first error no further beat is started
    (beats already running finish); those are reported as not_started."""
    real, lock, stop = sys.stdout, threading.Lock(), threading.Event()
    router = _ThreadOutput(real, lock)

    def task(n):
        if stop.is_set():
            result = BeatResult("not_started", "an earlier beat failed")
            _report(real, lock, n, result)
            return result
        router.start(n)
        try:
            result = work(n)
        except Exception as e:  # noqa: BLE001 - reported per beat, the batch decides what to do
            print(traceback.format_exc(), end="")
            result = BeatResult("error", f"{type(e).__name__}: {e}")
            stop.set()
        finally:
            router.end()
        _report(real, lock, n, result)
        return result

    sys.stdout = router
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            return dict(zip(beats, pool.map(task, beats)))
    finally:
        sys.stdout = real


def _run_in_order(beats: list, work: Callable[[int], BeatResult], keep_going: bool) -> dict:
    """Apply verdicts one beat at a time, in beat order (used ids depend on the order). An error stops the
    rest unless keep_going; flagged beats (no acceptable, duplicate) never stop it."""
    results, stopped = {}, False
    lock = threading.Lock()
    for n in beats:
        if stopped:
            result = BeatResult("not_started", "an earlier beat failed")
        else:
            try:
                result = work(n)
            except Exception as e:  # noqa: BLE001
                for line in traceback.format_exc().splitlines():
                    print(f"[beat {n}] {line}")
                result = BeatResult("error", f"{type(e).__name__}: {e}")
                stopped = not keep_going
        results[n] = result
        _report(sys.stdout, lock, n, result)
    return results


# --- modern beats (Step 2) -----------------------------------------------------------------------

def prep_modern(beats: Optional[list] = None, workers: int = DEFAULT_PREP_WORKERS, *, pexels_api_key: str,
                youtube_api_key: str, envato_profile_dir: str) -> dict:
    known = _modern_beats()
    beats = _select(beats, known, "modern footage")
    excluded = frozenset(_load("excluded_channel_ids.json"))
    # Exactly as in the one-beat flow: exclude what earlier beats have ACTUALLY used (read once; prep never
    # changes it). Two beats may then share a candidate; apply refuses the second winner of the same clip.
    used = frozenset(tuple(p) for p in _used_pairs())

    def work(n: int) -> BeatResult:
        query, subject = known[n]
        _remove(_modern_response(n))  # an old verdict must never be applied to new candidates
        candidates, prompt = prepare_combined_scoring(
            query=query, subject=subject, pexels_api_key=pexels_api_key, youtube_api_key=youtube_api_key,
            excluded_channel_ids=excluded, thumbnails_dir=f"thumbnails/beat_{n}",
            envato_profile_dir=envato_profile_dir, exclude_ids=used,
        )
        record_spend(PER_BEAT_UNITS, QUOTA_PATH)
        save_stock_candidates(f"candidates_{n}.json", candidates)
        _write_text_atomic(_modern_prompt(n), prompt)
        counts = dict(Counter(c.source for c in candidates))
        return BeatResult("ok", f"{len(candidates)} candidates {counts}", judge=True)

    return _run_parallel(beats, work, workers)


def _duplicate(pairs: list) -> list:
    used = _used_pairs()
    return [p for p in pairs if list(p) in used]


def apply_modern(beats: Optional[list] = None, keep_going: bool = False, *, envato_profile_dir: str) -> dict:
    beats = _select(beats, _modern_beats(), "modern footage", _modern_prompt)

    def work(n: int) -> BeatResult:
        if os.path.exists(output_path(n)):
            return BeatResult("skipped", f"{output_path(n)} already exists")
        raw = _read_response("modern", n)
        candidates = load_stock_candidates(f"candidates_{n}.json")
        try:
            winner_index = parse_scoring_output(raw, num_candidates=len(candidates))
        except NoAcceptableCandidateError as e:
            return BeatResult("no_acceptable", f"NO ACCEPTABLE FOOTAGE: {e.reasoning or '(no reason given)'}")
        winner = candidates[winner_index]
        if _duplicate([[winner.source, winner.display_id]]):
            return BeatResult("duplicate", f"winner {winner.source} {winner.display_id} is already used by an "
                              f"earlier beat; re-run `prep-modern {n}` and judge it again")
        path = resolve_combined_winner(candidates, winner_index, output_path(n), _duration(n),
                                       envato_profile_dir=envato_profile_dir)
        used = _used_pairs()
        used.append([winner.source, winner.display_id])
        _write_text_atomic(USED_IDS_PATH, json.dumps(used))
        return BeatResult("done", f"downloaded {path} (source={winner.source})")

    return _run_in_order(beats, work, keep_going)


# --- archival photo-medium beats (Step 2A) -------------------------------------------------------

def prep_film(beats: Optional[list] = None, workers: int = DEFAULT_PREP_WORKERS) -> dict:
    known = _archival_beats(("photo",))
    beats = _select(beats, known, "photo")
    used = _used_pairs()

    def work(n: int) -> BeatResult:
        _remove(_archival_response("film", n))
        if prepare_film(known[n], used):
            return BeatResult("ok", "film candidates: yes", judge=True)
        return BeatResult("needs_photos", "film candidates: no")

    return _run_parallel(beats, work, workers)


def apply_film(beats: Optional[list] = None, keep_going: bool = False) -> dict:
    known = _archival_beats(("photo",))
    beats = _select(beats, known, "photo", JUDGES["film"][0])

    def work(n: int) -> BeatResult:
        if os.path.exists(output_path(n)):
            return BeatResult("skipped", f"{output_path(n)} already exists")
        raw = _read_response("film", n)
        candidates = load_candidates(candidates_path("film", n))
        verdict = parse_archival_verdict(raw, len(candidates), "film")
        if verdict.picks:
            film_id = candidates[verdict.picks[0]].display_id
            if _duplicate([["archive", film_id]]):
                return BeatResult("duplicate", f"film {film_id} is already used by an earlier beat; re-run "
                                  f"`prep-film {n}` and judge it again")
        if finish_film(known[n], raw):
            return BeatResult("done", "film used")
        return BeatResult("needs_photos", f"no acceptable film ({verdict.reasoning or 'no reason given'})")

    return _run_in_order(beats, work, keep_going)


def prep_photos(beats: list, workers: int = DEFAULT_PREP_WORKERS) -> dict:
    known = _archival_beats(("photo",))
    beats = _select(beats, known, "photo")
    used = _used_pairs()

    def work(n: int) -> BeatResult:
        _remove(_archival_response("photo", n))
        prepare_photos(known[n], used)
        return BeatResult("ok", "photo candidates ready", judge=True)

    return _run_parallel(beats, work, workers)


def _empty_picks_reasoning(raw: str) -> Optional[str]:
    """The judge's reasoning when it deliberately picked nothing ({"picks": []}), else None."""
    try:
        payload = json.loads(_strip_code_fence(raw))
    except json.JSONDecodeError:
        return None
    if isinstance(payload, dict) and payload.get("picks") == []:
        reasoning = payload.get("reasoning")
        return reasoning if isinstance(reasoning, str) and reasoning else "(no reason given)"
    return None


def _shown(picks: list, beat: dict) -> list:
    """Only the stills that fit the cut (at least 2 s each) are shown, rendered and marked used (the same rule,
    on the same beat length, as archival_build._render_still_picks)."""
    return picks[:len(photo_shares(beat["end"] - beat["start"], len(picks)))]


def apply_photos(beats: Optional[list] = None, keep_going: bool = False) -> dict:
    known = _archival_beats(("photo",))
    beats = _select(beats, known, "photo", JUDGES["photo"][0])

    def work(n: int) -> BeatResult:
        if os.path.exists(output_path(n)):
            return BeatResult("skipped", f"{output_path(n)} already exists")
        raw = _read_response("photo", n)
        reasoning = _empty_picks_reasoning(raw)
        if reasoning is not None:
            return BeatResult("no_acceptable", f"the judge picked no photo: {reasoning}")
        candidates = load_candidates(candidates_path("photo", n))
        verdict = parse_archival_verdict(raw, len(candidates), "photo")
        taken = _duplicate([["archive", candidates[i].display_id] for i in _shown(verdict.picks, known[n])])
        if taken:
            return BeatResult("duplicate", f"{', '.join(p[1] for p in taken)} already used by an earlier beat; "
                              f"re-run `prep-photos {n}` and judge it again")
        finish_photos(known[n], raw)
        return BeatResult("done", "photos used")

    return _run_in_order(beats, work, keep_going)


# --- mixed beats (Step 2M) -----------------------------------------------------------------------

def prep_mixed(beats: Optional[list] = None, workers: int = DEFAULT_PREP_WORKERS, *, pexels_api_key: str,
               youtube_api_key: str, envato_profile_dir: str) -> dict:
    known = _archival_beats(MIXED_MEDIA)
    beats = _select(beats, known, "mixed")
    excluded = frozenset(_load("excluded_channel_ids.json"))
    used = _used_pairs()

    def work(n: int) -> BeatResult:
        beat = known[n]
        _remove(_archival_response("mixed", n))
        counts = prepare_mixed(beat, used, pexels_api_key, youtube_api_key, excluded, envato_profile_dir)
        if beat["medium"] == "artwork_or_stock":
            record_spend(PER_BEAT_UNITS, QUOTA_PATH)
        return BeatResult("ok", f"candidates: {counts}", judge=True)

    return _run_parallel(beats, work, workers)


def apply_mixed(beats: Optional[list] = None, keep_going: bool = False, *, envato_profile_dir: str) -> dict:
    known = _archival_beats(MIXED_MEDIA)
    beats = _select(beats, known, "mixed", JUDGES["mixed"][0])

    def work(n: int) -> BeatResult:
        if os.path.exists(output_path(n)):
            return BeatResult("skipped", f"{output_path(n)} already exists")
        raw = _read_response("mixed", n)
        stills, still_types, stock = _load_state(n)
        verdict = parse_mixed_verdict(raw, still_types + ["stock"] * len(stock))
        if verdict.choice == "none":
            return BeatResult("no_acceptable", f"the judge picked nothing: {verdict.reasoning or '(no reason given)'}")
        if verdict.choice == "stock":
            winner = stock[verdict.picks[0] - len(stills)]
            pairs = [[winner.source, winner.display_id]]
        else:
            pairs = [["archive", stills[i].display_id] for i in _shown(verdict.picks, known[n])]
        taken = _duplicate(pairs)
        if taken:
            return BeatResult("duplicate", f"{', '.join(' '.join(p) for p in taken)} already used by an earlier "
                              f"beat; re-run `prep-mixed {n}` and judge it again")
        return BeatResult("done", finish_mixed(known[n], raw, envato_profile_dir))

    return _run_in_order(beats, work, keep_going)


# --- judge responses -----------------------------------------------------------------------------

_FENCED = re.compile(r"```(?:json)?\s*\n(.*?)\n```", re.DOTALL)


def _as_verdict(text: str, key: str, loose: bool) -> Optional[str]:
    """`text` as a verdict JSON object string when it is one (optionally inside a ``` fence) with `key`; with
    loose, also the span from its first "{" to its last "}" (an answer with a sentence around it)."""
    tries = [text.strip()]
    tries += _FENCED.findall(text)
    if loose and "{" in text:
        tries.append(text[text.index("{"):text.rindex("}") + 1])
    for candidate in tries:
        try:
            payload = json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(payload, dict) and key in payload:
            return json.dumps(payload)
    return None


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _strings(v)


def extract_verdict(text: str, key: str) -> Optional[str]:
    """The LAST verdict JSON (an object with `key`) in a subagent's output: a JSON-lines transcript (every
    string in every line is checked; the judge's final answer comes last) or its plain answer text."""
    found = None
    for line in text.splitlines():
        try:
            record = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        for s in _strings(record):
            found = _as_verdict(s, key, loose=False) or found
    return found or _as_verdict(text, key, loose=True)


def save_response(kind: str, n: int, text: str) -> str:
    _, response_of, key, _ = JUDGES[kind]
    verdict = extract_verdict(text, key)
    if verdict is None:
        raise ValueError(f"no JSON verdict with {key!r} found in the {kind} judge's answer for beat {n}")
    path = response_of(n)
    _write_text_atomic(path, verdict)
    return path


def extract_response(kind: str, n: int, output_path_: str) -> str:
    """save_response from a judge subagent's output file, but only when that file is this beat's judge: it must
    mention the beat's prompt file (the judge was told to Read it) and be newer than the prompt (a judge that
    ran before the beat was prepared again answered other candidates)."""
    prompt = os.path.abspath(JUDGES[kind][0](n))
    with open(output_path_) as f:
        text = f.read()
    if prompt not in text:
        raise ValueError(f"{output_path_} never mentions {prompt}: it is not beat {n}'s {kind} judge")
    if os.path.exists(prompt) and os.path.getmtime(output_path_) < os.path.getmtime(prompt):
        raise ValueError(f"{output_path_} is older than {prompt}: that judge answered an earlier prep of beat {n}")
    return save_response(kind, n, text)


# --- CLI -----------------------------------------------------------------------------------------

def _env():
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.getcwd(), ".env"))
    return {"pexels_api_key": os.environ["PEXELS_API_KEY"], "youtube_api_key": os.environ["YOUTUBE_API_KEY"],
            "envato_profile_dir": os.environ.get("ENVATO_PROFILE_DIR", ".envato_automation_profile")}


def _envato_dir() -> str:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.getcwd(), ".env"))
    return os.environ.get("ENVATO_PROFILE_DIR", ".envato_automation_profile")


def _summary(command: str, kind: str, results: dict) -> int:
    counts = Counter(r.status for r in results.values())
    print(f"{command}: {len(results)} beats: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    prompt_of, response_of, _, model = JUDGES[kind]
    judges = [n for n, r in results.items() if r.judge]
    for n in judges:
        print(f"JUDGE beat={n} model={model} prompt={os.path.abspath(prompt_of(n))} "
              f"response={os.path.abspath(response_of(n))}")
    if judges:
        apply_cmd = {"modern": "apply-modern", "film": "apply-film", "photo": "apply-photos", "mixed": "apply-mixed"}
        print(f"NEXT: run the {len(judges)} judges (at most {MAX_PARALLEL_JUDGES} at a time), save each answer, then "
              f"`python -m footage.batch {apply_cmd[kind]} {' '.join(map(str, judges))}`")
    photos = [n for n, r in results.items() if r.status == "needs_photos"]
    if photos:
        print(f"NEXT: `python -m footage.batch prep-photos {' '.join(map(str, photos))}`")
    for status in FLAGGED + FAILED:
        for n, r in results.items():
            if r.status == status:
                print(f"{status.upper()}: beat {n}: {r.message}")
    if any(r.status in FAILED for r in results.values()):
        return 1
    return 2 if any(r.status in FLAGGED for r in results.values()) else 0


def _status() -> int:
    groups = [("modern", _modern_beats()), ("archival photo", _archival_beats(("photo",))),
              ("mixed", _archival_beats(MIXED_MEDIA))]
    for label, known in groups:
        left = [n for n in sorted(known) if not os.path.exists(output_path(n))]
        print(f"{label}: {len(left)} of {len(known)} left: {' '.join(map(str, left))}")
    return 0


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m footage.batch", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    for name in ("prep-modern", "prep-film", "prep-photos", "prep-mixed"):
        p = sub.add_parser(name)
        p.add_argument("beats", nargs="*" if name != "prep-photos" else "+", type=int)
        p.add_argument("--workers", type=int, default=DEFAULT_PREP_WORKERS)
    for name in ("apply-modern", "apply-film", "apply-photos", "apply-mixed"):
        p = sub.add_parser(name)
        p.add_argument("beats", nargs="*", type=int)
        p.add_argument("--keep-going", action="store_true", help="continue past an error to the next beat")
    p = sub.add_parser("save-response")
    p.add_argument("kind", choices=sorted(JUDGES))
    p.add_argument("beat", type=int)
    p.add_argument("--file", help="read the answer from this file instead of stdin")
    p = sub.add_parser("extract")
    p.add_argument("kind", choices=sorted(JUDGES))
    p.add_argument("pairs", nargs="+", help="BEAT=PATH of a subagent's output file")
    args = parser.parse_args(argv)

    beats = getattr(args, "beats", None) or None
    if args.command == "status":
        return _status()
    if args.command == "prep-modern":
        return _summary(args.command, "modern", prep_modern(beats, args.workers, **_env()))
    if args.command == "apply-modern":
        return _summary(args.command, "modern", apply_modern(beats, args.keep_going, envato_profile_dir=_envato_dir()))
    if args.command == "prep-film":
        return _summary(args.command, "film", prep_film(beats, args.workers))
    if args.command == "apply-film":
        return _summary(args.command, "film", apply_film(beats, args.keep_going))
    if args.command == "prep-photos":
        return _summary(args.command, "photo", prep_photos(beats, args.workers))
    if args.command == "apply-photos":
        return _summary(args.command, "photo", apply_photos(beats, args.keep_going))
    if args.command == "prep-mixed":
        return _summary(args.command, "mixed", prep_mixed(beats, args.workers, **_env()))
    if args.command == "apply-mixed":
        return _summary(args.command, "mixed", apply_mixed(beats, args.keep_going, envato_profile_dir=_envato_dir()))
    if args.command == "save-response":
        text = open(args.file).read() if args.file else sys.stdin.read()
        print("saved", save_response(args.kind, args.beat, text))
        return 0
    status = 0
    for pair in args.pairs:
        beat, _, path = pair.partition("=")
        try:
            print(f"beat {beat}: saved", extract_response(args.kind, int(beat), path))
        except (OSError, ValueError) as e:
            print(f"beat {beat}: ERROR {e}")
            status = 1
    return status


if __name__ == "__main__":
    sys.exit(main())
