import re

import requests

EXCLUDED_CHANNEL_URLS = [
    "https://www.youtube.com/@wsj",
    "https://www.youtube.com/@CNN",
    "https://www.youtube.com/@BBCNews",
    "https://www.youtube.com/@BBCEarthScience",
    "https://www.youtube.com/@BBC/videos",
    "https://www.youtube.com/@FoxNews",
    "https://www.youtube.com/@Survivethejive",
    "https://www.youtube.com/@business",
    "https://www.youtube.com/@nytimes",
    "https://www.youtube.com/@bbcearth",
]


class ChannelResolutionError(Exception):
    pass


_HANDLE_PATTERN = re.compile(r"@([A-Za-z0-9_.-]+)")


def extract_handle(url: str) -> str:
    match = _HANDLE_PATTERN.search(url)
    if not match:
        raise ChannelResolutionError(f"could not extract a channel handle from: {url!r}")
    return match.group(1)


def _fetch_channel_json(handle: str, api_key: str) -> dict:
    response = requests.get(
        "https://www.googleapis.com/youtube/v3/channels",
        params={"part": "id", "forHandle": f"@{handle}", "key": api_key},
        timeout=30,
    )
    if response.status_code != 200:
        raise ChannelResolutionError(
            f"YouTube channels API returned status {response.status_code} for handle "
            f"{handle!r}: {response.text[:200]}"
        )
    return response.json()


def resolve_channel_ids(urls: list[str], api_key: str) -> frozenset[str]:
    channel_ids = set()
    for url in urls:
        handle = extract_handle(url)
        payload = _fetch_channel_json(handle, api_key)
        items = payload.get("items", [])
        if not items:
            raise ChannelResolutionError(
                f"no YouTube channel found for handle {handle!r} (from {url!r}) — "
                "this channel would NOT be excluded if we silently continued"
            )
        channel_ids.add(items[0]["id"])
    return frozenset(channel_ids)
