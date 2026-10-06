import re
from dataclasses import dataclass

import requests


@dataclass
class YouTubeCandidate:
    video_id: str
    title: str
    channel_id: str
    channel_title: str
    thumbnail_url: str
    duration_seconds: float


class YouTubeError(Exception):
    pass


_ISO8601_DURATION_PATTERN = re.compile(
    r"^PT(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?$"
)


def _parse_iso8601_duration(duration: str) -> float:
    match = _ISO8601_DURATION_PATTERN.match(duration)
    if not match or not any(match.groups()):
        raise YouTubeError(f"could not parse a usable ISO 8601 duration: {duration!r}")

    hours = int(match.group("hours") or 0)
    minutes = int(match.group("minutes") or 0)
    seconds = int(match.group("seconds") or 0)
    total = hours * 3600 + minutes * 60 + seconds
    if total <= 0:
        raise YouTubeError(f"video has zero or invalid duration: {duration!r}")
    return float(total)


def _fetch_search_json(query: str, api_key: str, max_results: int) -> dict:
    response = requests.get(
        "https://www.googleapis.com/youtube/v3/search",
        params={
            "part": "snippet", "q": query, "type": "video",
            "maxResults": max_results, "safeSearch": "strict", "key": api_key,
        },
        timeout=30,
    )
    if response.status_code != 200:
        raise YouTubeError(
            f"YouTube search API returned status {response.status_code}: {response.text[:200]}"
        )
    return response.json()


# videos.list only returns player.embedWidth/embedHeight when maxWidth (or maxHeight) is set.
# They are the embed size scaled to that width, so their ratio is the video's own aspect ratio
# (a 9:16 Short comes back as 1280x2276). Adding the player part costs no extra quota.
_EMBED_MAX_WIDTH = 1280


@dataclass
class VideoDetails:
    duration_seconds: float
    width: int
    height: int


def _fetch_video_details_json(video_ids: list[str], api_key: str) -> dict:
    response = requests.get(
        "https://www.googleapis.com/youtube/v3/videos",
        params={
            "part": "contentDetails,player", "id": ",".join(video_ids),
            "maxWidth": _EMBED_MAX_WIDTH, "key": api_key,
        },
        timeout=30,
    )
    if response.status_code != 200:
        raise YouTubeError(
            f"YouTube videos API returned status {response.status_code}: {response.text[:200]}"
        )
    return response.json()


def _parse_embed_dimensions(player: dict) -> tuple[int, int]:
    try:
        width, height = int(player["embedWidth"]), int(player["embedHeight"])
    except (KeyError, TypeError, ValueError) as e:
        raise YouTubeError("no usable embed dimensions in player data") from e
    if width <= 0 or height <= 0:
        raise YouTubeError(f"invalid embed dimensions {width}x{height}")
    return width, height


def _parse_video_details_response(payload: dict) -> dict[str, VideoDetails]:
    details: dict[str, VideoDetails] = {}
    for item in payload.get("items", []):
        try:
            duration = _parse_iso8601_duration(item["contentDetails"]["duration"])
            width, height = _parse_embed_dimensions(item.get("player", {}))
        except YouTubeError:
            # unusable duration (e.g. a live stream) or unknown orientation — exclude rather
            # than guess
            continue
        details[item["id"]] = VideoDetails(duration_seconds=duration, width=width, height=height)
    return details


def _is_landscape(details: VideoDetails) -> bool:
    # The final video is 16:9 — portrait (e.g. YouTube Shorts) and square footage don't fit it.
    return details.width > details.height


# Footage from channels bigger than this is never used. A channel that hides its subscriber count
# (or that the API does not return) cannot be shown to be under it, so it is skipped too.
MAX_CHANNEL_SUBSCRIBERS = 1_000_000


def _fetch_channel_stats_json(channel_ids: list[str], api_key: str) -> dict:
    response = requests.get(
        "https://www.googleapis.com/youtube/v3/channels",
        params={
            "part": "statistics", "id": ",".join(channel_ids),
            "maxResults": 50, "key": api_key,
        },
        timeout=30,
    )
    if response.status_code != 200:
        raise YouTubeError(
            f"YouTube channels API returned status {response.status_code}: {response.text[:200]}"
        )
    return response.json()


def _parse_subscriber_counts(payload: dict) -> dict[str, int]:
    """channel id -> subscriber count; channels that hide their count are left out."""
    counts = {}
    for item in payload.get("items", []):
        stats = item.get("statistics", {})
        if stats.get("hiddenSubscriberCount") or "subscriberCount" not in stats:
            continue
        counts[item["id"]] = int(stats["subscriberCount"])
    return counts


@dataclass
class YouTubeSearchResult:
    """Surviving candidates, plus how many raw results each filter removed — so a caller whose
    pool ends up empty can say which filter emptied it instead of guessing."""
    candidates: list[YouTubeCandidate]
    raw_count: int
    excluded_channel_count: int
    non_landscape_count: int
    unusable_count: int  # no usable duration (e.g. live stream) or dimensions


def _parse_search_response(
    payload: dict, details: dict[str, VideoDetails]
) -> list[YouTubeCandidate]:
    candidates = []
    for item in payload.get("items", []):
        video_id = item["id"]["videoId"]
        video = details.get(video_id)
        if video is None:
            continue  # no usable duration/dimensions for this video — skip rather than guess
        if not _is_landscape(video):
            continue  # portrait/square — never let it reach the scorer
        snippet = item["snippet"]
        candidates.append(YouTubeCandidate(
            video_id=video_id, title=snippet["title"], channel_id=snippet["channelId"],
            channel_title=snippet["channelTitle"],
            thumbnail_url=snippet["thumbnails"]["high"]["url"],
            duration_seconds=video.duration_seconds,
        ))
    return candidates


def search_youtube(
    query: str, api_key: str, excluded_channel_ids: frozenset[str], max_results: int = 7
) -> YouTubeSearchResult:
    raw_items = _fetch_search_json(query, api_key, max_results).get("items", [])
    items = [
        item for item in raw_items
        if item["snippet"]["channelId"] not in excluded_channel_ids
    ]
    if items:
        # One channels.list call covers every distinct channel (the search returns at most 50).
        channel_ids = list(dict.fromkeys(item["snippet"]["channelId"] for item in items))
        counts = _parse_subscriber_counts(_fetch_channel_stats_json(channel_ids, api_key))
        items = [
            item for item in items
            if counts.get(item["snippet"]["channelId"], MAX_CHANNEL_SUBSCRIBERS + 1)
            <= MAX_CHANNEL_SUBSCRIBERS
        ]
    # Blacklisted and too-big/unknown-size channels are all "excluded channels".
    excluded_channel_count = len(raw_items) - len(items)
    if not items:
        return YouTubeSearchResult([], len(raw_items), excluded_channel_count, 0, 0)

    video_ids = [item["id"]["videoId"] for item in items]
    details = _parse_video_details_response(_fetch_video_details_json(video_ids, api_key))

    candidates = _parse_search_response({"items": items}, details)
    unusable_count = sum(1 for vid in video_ids if vid not in details)
    non_landscape_count = len(items) - unusable_count - len(candidates)
    return YouTubeSearchResult(
        candidates=candidates, raw_count=len(raw_items),
        excluded_channel_count=excluded_channel_count,
        non_landscape_count=non_landscape_count, unusable_count=unusable_count,
    )
