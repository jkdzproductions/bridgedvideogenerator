# footage/combined_build.py
import os
import threading
from dataclasses import dataclass
from typing import Literal, Optional, Union

from footage.build import PEXELS_MAX_PER_PAGE
from footage.download import download_thumbnails, download_thumbnails_from_urls, download_winning_video
from footage.envato import EnvatoCandidate, EnvatoCandidateDetails, EnvatoError, fetch_envato_details, search_envato
from footage.envato_download import download_envato_clip
from footage.pexels import PexelsCandidate, search_pexels
from footage.youtube import YouTubeCandidate, search_youtube
from footage.youtube_download import (
    PortraitVideoError,
    YouTubeDownloadError,
    download_youtube_clip,
    download_youtube_thumbnails,
    probe_video_dimensions,
)
from footage.youtube_look import apply_youtube_look

# Fixed pool of 10 candidates per beat across three sources (was 7 = 3 + 2 + 2). Raised so the
# judge has more to choose from and is less often stuck with a wrong-country near miss.
PEXELS_SPLIT = 4
YOUTUBE_SPLIT = 3
ENVATO_SPLIT = 3
YOUTUBE_MAX_PER_PAGE = 50  # matches footage/youtube_build.py — a full page so filters have room

# Every Envato call launches Chromium on the same persistent profile directory, and Chromium refuses to open a
# profile another browser already holds. Batch prep (footage/batch.py) prepares beats in worker threads, so the
# Envato part of each beat holds this lock; Pexels/YouTube work still overlaps with it.
ENVATO_PROFILE_LOCK = threading.Lock()


@dataclass
class CombinedCandidate:
    source: Literal["pexels", "youtube", "envato"]
    display_id: str
    thumbnail_path: str
    payload: Union[PexelsCandidate, YouTubeCandidate, EnvatoCandidate]


def _pexels_candidates(
    query: str, api_key: str, exclude_ids: frozenset[tuple[str, str]], thumbnails_dir: str
) -> list[CombinedCandidate]:
    # Pexels has no server-side "exclude these IDs" parameter, so over-fetch and filter
    # client-side when anything is excluded — same approach as footage/build.py.
    search_size = max(PEXELS_SPLIT, PEXELS_MAX_PER_PAGE) if exclude_ids else PEXELS_SPLIT
    results = search_pexels(query, api_key, search_size)
    fresh = [c for c in results if ("pexels", str(c.id)) not in exclude_ids][:PEXELS_SPLIT]
    if not fresh:
        return []
    thumbnail_paths = download_thumbnails(fresh, thumbnails_dir)
    return [CombinedCandidate("pexels", str(c.id), thumbnail_paths[c.id], c) for c in fresh]


def _youtube_candidates(
    query: str,
    api_key: str,
    excluded_channel_ids: frozenset[str],
    exclude_ids: frozenset[tuple[str, str]],
    thumbnails_dir: str,
) -> list[CombinedCandidate]:
    result = search_youtube(query, api_key, excluded_channel_ids, max_results=YOUTUBE_MAX_PER_PAGE)
    fresh = [c for c in result.candidates if ("youtube", c.video_id) not in exclude_ids][:YOUTUBE_SPLIT]
    if not fresh:
        return []
    thumbnail_paths = download_youtube_thumbnails(fresh, thumbnails_dir)
    return [CombinedCandidate("youtube", c.video_id, thumbnail_paths[c.video_id], c) for c in fresh]


def _envato_candidates(
    query: str, exclude_ids: frozenset[tuple[str, str]], profile_dir: str, thumbnails_dir: str
) -> tuple[list[CombinedCandidate], dict[str, EnvatoCandidateDetails]]:
    # Imported here, not at module top, to match footage/envato.py's lazy-import convention. If
    # the `envato` extra isn't installed this raises ModuleNotFoundError and STOPs loudly on
    # purpose — a missing dependency is a setup bug, not "0 Envato candidates this beat."
    from playwright.sync_api import Error as PlaywrightError

    envato_exclude_ids = frozenset(
        item_id for source, item_id in exclude_ids if source == "envato"
    )
    try:
        # One browser at a time on the shared persistent profile (batch prep runs beats in threads).
        with ENVATO_PROFILE_LOCK:
            results = search_envato(query, envato_exclude_ids, profile_dir, max_results=ENVATO_SPLIT)
            details = fetch_envato_details(results, profile_dir) if results else {}
    except (EnvatoError, PlaywrightError) as e:
        # Additive source, never a hard requirement — a login/session problem, a Playwright
        # timeout, or a locked profile must not block Pexels/YouTube candidates from reaching
        # the scorer. But it must never be SILENT either: an expired session would otherwise
        # quietly zero out Envato for an entire run. (A genuinely empty-but-successful search
        # already returns [] on its own and is not a warning.)
        print(
            f"WARNING: Envato contributed 0 candidates for query {query!r} because it failed "
            f"({type(e).__name__}: {e}). Pexels/YouTube continue for this beat. If this repeats "
            "every beat, the Envato Playwright session has likely expired — re-run "
            "tests/fixtures/envato_automation_spike.py to log in again."
        )
        return [], {}
    if not results:
        return [], {}
    # Envato's search URL has no orientation filter, so drop portrait/square items here, using
    # the width/height fetch_envato_details already scraped — before scoring, instead of only
    # catching them after a full multi-GB download via resolve_combined_winner's ffprobe backstop.
    results = [
        c for c in results
        if c.item_id in details and details[c.item_id].width > details[c.item_id].height
    ]
    if not results:
        return [], {}
    thumbnail_paths = download_thumbnails_from_urls(
        {c.item_id: c.thumbnail_url for c in results}, thumbnails_dir
    )
    candidates = [
        CombinedCandidate("envato", c.item_id, thumbnail_paths[c.item_id], c) for c in results
    ]
    return candidates, details


def build_combined_scoring_prompt(
    query: str,
    subject: str,
    candidates: list[CombinedCandidate],
    envato_details: Optional[dict[str, EnvatoCandidateDetails]] = None,
) -> str:
    envato_details = envato_details or {}
    lines = []
    for i, c in enumerate(candidates):
        if c.source == "pexels":
            p = c.payload
            lines.append(
                f"[{i}] source=pexels duration={p.duration}s resolution={p.width}x{p.height} "
                f"thumbnail={c.thumbnail_path}"
            )
        elif c.source == "youtube":
            y = c.payload
            lines.append(
                f'[{i}] source=youtube title="{y.title}" channel="{y.channel_title}" '
                f"duration={y.duration_seconds:.0f}s thumbnail={c.thumbnail_path}"
            )
        elif c.source == "envato":
            e = c.payload
            lines.append(
                f'[{i}] source=envato title="{e.title}" author="{e.author}" '
                f"duration={envato_details[e.item_id].duration_seconds:.0f}s "
                f"thumbnail={c.thumbnail_path}"
            )
    candidate_lines = "\n".join(lines)

    return f"""You are scoring stock footage candidates for one beat of a documentary video, \
drawn from up to three different sources: Pexels (pre-cut stock clips), YouTube (whole videos — \
only the opening portion, from 0:00, will actually be used, up to the beat's needed duration), \
and Envato Elements (pre-cut, professionally shot licensed stock clips).

Target subject: {subject}
Search query used to find these candidates: "{query}"

Below are {len(candidates)} candidates. Use your Read tool to actually view each thumbnail \
image at its listed path before judging — do not guess from the metadata alone.

Candidates:
{candidate_lines}

Pick the candidate whose thumbnail most specifically and accurately depicts the target subject. \
Prefer a real, specific match over a generic stand-in. For a "source=youtube" candidate, judge \
its thumbnail as a proxy for what the opening of that video likely shows, and prefer one whose \
title/thumbnail suggests short, purpose-shot b-roll over a long-form video where the relevant \
content might be buried deep inside it.

ALWAYS REJECT any candidate whose thumbnail is a title card: a screen that is mostly or only \
text (a video title, channel name or caption on a plain or blurred background), because that \
video most likely opens on that same text screen instead of real footage. Do this even when \
the subject matches and even when it is the closest match; never pick a title card.

ALWAYS REJECT any candidate whose thumbnail shows text or branding burned into the picture: a \
news broadcast or news-channel banner or lower-third ("Breaking", "Exclusive", a headline bar), \
a TV or channel logo, a watermark or credit, captions or subtitles, a vlogger's title overlay, \
or a sign, billboard or placard that is the main thing in the shot (for example a "Welcome to ..." \
sign instead of the place itself). Footage must be clean picture of the subject. Do this even \
when the subject matches, unless the subject itself is a sign or a written text. A small \
incidental sign or street name far in the background is fine.

For a "source=youtube" candidate the rule above is stricter: every YouTube clip is mirrored \
left-to-right before use, so ANY readable text in the thumbnail, even small or in the \
background (a shop name, a street sign, a number plate, a screen, a map label, a ship's name \
on its hull), means REJECT it. Mirrored text gives the edit away.

ALWAYS REJECT any candidate that shows a different country than the one the target subject \
names (for example Mexico or Guatemala when the subject is Costa Rica), even when it looks \
similar or is a near neighbour. If the subject names only a region, reject candidates that \
clearly show a place outside that region. If you cannot tell which country a candidate shows, \
treat that as a weaker match than one you can identify.

If NONE of the candidates is an acceptable match, do not force a pick — respond with a null \
winner instead; the beat will be flagged for a human rather than filled with a poor clip.

Respond with ONLY a JSON object, no other text. Either:
{{"winner_index": <int>, "reasoning": "<one sentence>"}}
or, if no candidate is acceptable:
{{"winner_index": null, "reasoning": "<one sentence on why none are acceptable>"}}
"""


def prepare_combined_scoring(
    query: str,
    subject: str,
    pexels_api_key: str,
    youtube_api_key: str,
    excluded_channel_ids: frozenset[str],
    thumbnails_dir: str,
    envato_profile_dir: str,
    exclude_ids: frozenset[tuple[str, str]] = frozenset(),
) -> tuple[list[CombinedCandidate], str]:
    pexels_candidates = _pexels_candidates(query, pexels_api_key, exclude_ids, thumbnails_dir)
    youtube_candidates = _youtube_candidates(
        query, youtube_api_key, excluded_channel_ids, exclude_ids, thumbnails_dir
    )
    envato_candidates, envato_details = _envato_candidates(
        query, exclude_ids, envato_profile_dir, thumbnails_dir
    )
    candidates = pexels_candidates + youtube_candidates + envato_candidates
    if not candidates:
        raise ValueError(
            f"no candidates found for query: {query!r} from Pexels, YouTube, or Envato "
            "(after exclusions/orientation filters)"
        )
    prompt = build_combined_scoring_prompt(query, subject, candidates, envato_details)
    return candidates, prompt


def resolve_combined_winner(
    candidates: list[CombinedCandidate],
    winner_index: int,
    dest_path: str,
    target_duration: float,
    envato_profile_dir: str,
) -> str:
    winner = candidates[winner_index]
    if winner.source == "pexels":
        if os.path.exists(dest_path):
            os.remove(dest_path)
        try:
            return download_winning_video(winner.payload, dest_path)
        except Exception:
            if os.path.exists(dest_path):
                os.remove(dest_path)
            raise

    if winner.source == "envato":
        # Same remove-before/remove-on-failure pattern as the Pexels branch: a failed trim can
        # leave a 0-byte dest_path, and Stage 2's resume logic treats any existing
        # footage_output/beat_<n>.mp4 as a finished beat.
        if os.path.exists(dest_path):
            os.remove(dest_path)
        try:
            path = download_envato_clip(
                winner.payload, dest_path=dest_path, target_duration_seconds=target_duration,
                profile_dir=envato_profile_dir,
            )
        except Exception:
            if os.path.exists(dest_path):
                os.remove(dest_path)
            raise
        # Same landscape backstop the YouTube branch already applies — Global Constraint: a UI
        # orientation filter alone is never trusted for this.
        try:
            width, height = probe_video_dimensions(path)
        except YouTubeDownloadError:
            os.remove(path)
            raise
        if width <= height:
            os.remove(path)
            raise PortraitVideoError(
                f"downloaded Envato video {winner.payload.item_id} is {width}x{height} (not "
                "landscape) — deleted it"
            )
        return path

    clip_duration = min(target_duration, winner.payload.duration_seconds)
    path = download_youtube_clip(winner.payload.video_id, dest_path, clip_duration)

    # Backstop for search_youtube's metadata-based landscape filter, same as
    # footage/youtube_build.py's resolve_youtube_winner — must not be lost in the merge.
    try:
        width, height = probe_video_dimensions(path)
    except YouTubeDownloadError:
        os.remove(path)
        raise
    if width <= height:
        os.remove(path)
        raise PortraitVideoError(
            f"downloaded YouTube video {winner.payload.video_id} is {width}x{height} (not "
            "landscape), so it can't be used in a 16:9 video — deleted it"
        )
    # YouTube footage only: mirror it, zoom in a hair and add light film grain (Pexels and Envato
    # clips are used as they are).
    return apply_youtube_look(path)
