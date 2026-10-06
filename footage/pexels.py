from dataclasses import dataclass

import requests


@dataclass
class VideoFile:
    quality: str
    file_type: str
    width: int
    height: int
    link: str


@dataclass
class PexelsCandidate:
    id: int
    url: str
    thumbnail_url: str
    duration: int
    width: int
    height: int
    video_files: list[VideoFile]


class PexelsError(Exception):
    pass


def _parse_search_response(payload: dict) -> list[PexelsCandidate]:
    candidates = []
    for v in payload.get("videos", []):
        video_files = [
            VideoFile(
                quality=vf.get("quality", ""),
                file_type=vf.get("file_type", ""),
                width=vf.get("width", 0),
                height=vf.get("height", 0),
                link=vf["link"],
            )
            for vf in v.get("video_files", [])
        ]
        candidates.append(PexelsCandidate(
            id=v["id"], url=v["url"], thumbnail_url=v["image"],
            duration=v["duration"], width=v["width"], height=v["height"],
            video_files=video_files,
        ))
    return candidates


def _fetch_pexels_json(query: str, api_key: str, per_page: int) -> dict:
    response = requests.get(
        "https://api.pexels.com/videos/search",
        headers={"Authorization": api_key},
        # The final video is 16:9 — portrait/square clips are never usable b-roll.
        params={"query": query, "per_page": per_page, "orientation": "landscape"},
        timeout=30,
    )
    if response.status_code != 200:
        raise PexelsError(
            f"Pexels API returned status {response.status_code}: {response.text[:200]}"
        )
    return response.json()


def search_pexels(query: str, api_key: str, per_page: int = 7) -> list[PexelsCandidate]:
    payload = _fetch_pexels_json(query, api_key, per_page)
    return _parse_search_response(payload)


def select_best_video_file(video_files: list[VideoFile], target_width: int = 1920) -> VideoFile:
    mp4_files = [vf for vf in video_files if vf.file_type == "video/mp4"]
    if not mp4_files:
        raise PexelsError("no mp4 video files available for this candidate")

    at_or_above_target = [vf for vf in mp4_files if vf.width >= target_width]
    if at_or_above_target:
        return min(at_or_above_target, key=lambda vf: vf.width)
    return max(mp4_files, key=lambda vf: vf.width)
