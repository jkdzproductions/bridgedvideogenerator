import os

from footage.youtube import YouTubeCandidate, YouTubeSearchResult, search_youtube
from footage.youtube_download import (
    PortraitVideoError,
    YouTubeDownloadError,
    download_youtube_clip,
    download_youtube_thumbnails,
    probe_video_dimensions,
)
from footage.youtube_scoring_prompt import build_youtube_scoring_prompt

YOUTUBE_MAX_PER_PAGE = 50


def _empty_pool_message(query: str, result: YouTubeSearchResult, used_count: int) -> str:
    """Name the filter that actually emptied the pool, with every filter's count for context."""
    after_channels = result.raw_count - result.excluded_channel_count
    if result.raw_count == 0:
        cause = "the search returned zero results"
    elif after_channels == 0:
        cause = f"all {result.raw_count} result(s) were from excluded channels"
    elif not result.candidates:
        cause = (
            f"all {after_channels} result(s) not from excluded channels were portrait/square "
            "or had no usable duration/dimensions"
        )
    else:
        cause = f"all {used_count} remaining result(s) were already used by earlier beats"
    breakdown = (
        f"{result.raw_count} raw result(s): {result.excluded_channel_count} from excluded "
        f"channels, {result.non_landscape_count} portrait/square, {result.unusable_count} with "
        f"no usable duration/dimensions, {used_count} already used"
    )
    return f"no YouTube candidates found for query: {query!r} — {cause} ({breakdown})"


def prepare_youtube_scoring(
    query: str,
    subject: str,
    api_key: str,
    excluded_channel_ids: frozenset[str],
    thumbnails_dir: str,
    exclude_video_ids: frozenset[str] = frozenset(),
    max_results: int = 7,
) -> tuple[list[YouTubeCandidate], str]:
    # search.list costs the same 100 quota units whatever maxResults is, so always take a full
    # page: it leaves room for the channel/orientation/used-video filters to discard results.
    result = search_youtube(
        query, api_key, excluded_channel_ids, max_results=YOUTUBE_MAX_PER_PAGE
    )
    fresh = [c for c in result.candidates if c.video_id not in exclude_video_ids]

    if not fresh:
        raise ValueError(_empty_pool_message(query, result, len(result.candidates) - len(fresh)))

    candidates = fresh[:max_results]
    thumbnail_paths = download_youtube_thumbnails(candidates, thumbnails_dir)
    prompt = build_youtube_scoring_prompt(query, subject, candidates, thumbnail_paths)
    return candidates, prompt


def resolve_youtube_winner(
    candidates: list[YouTubeCandidate], winner_index: int, dest_path: str, target_duration: float
) -> str:
    winner = candidates[winner_index]
    clip_duration = min(target_duration, winner.duration_seconds)
    path = download_youtube_clip(winner.video_id, dest_path, clip_duration)

    # Backstop for search_youtube's metadata-based landscape filter: check the real file. Any
    # clip that fails this check is deleted, so a resumed run never counts the beat as sourced.
    try:
        width, height = probe_video_dimensions(path)
    except YouTubeDownloadError:
        os.remove(path)
        raise
    if width <= height:
        os.remove(path)
        raise PortraitVideoError(
            f"downloaded YouTube video {winner.video_id} is {width}x{height} (not landscape), "
            "so it can't be used in a 16:9 video — deleted it"
        )
    return path
