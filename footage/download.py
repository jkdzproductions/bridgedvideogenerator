import os
import pathlib

import requests

from footage.pexels import PexelsCandidate, select_best_video_file


class DownloadError(Exception):
    pass


def download_file(url: str, dest_path: str) -> None:
    response = requests.get(url, timeout=60, stream=True)
    if response.status_code != 200:
        raise DownloadError(f"failed to download {url}: status {response.status_code}")

    dest = pathlib.Path(dest_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)


def download_thumbnails(candidates: list[PexelsCandidate], out_dir: str) -> dict[int, str]:
    # Absolute paths: these go into the scoring prompt, and the scoring subagent's Read tool
    # needs absolute paths to open the thumbnails reliably.
    paths: dict[int, str] = {}
    for candidate in candidates:
        dest = os.path.abspath(f"{out_dir}/{candidate.id}.jpg")
        download_file(candidate.thumbnail_url, dest)
        paths[candidate.id] = dest
    return paths


def download_thumbnails_from_urls(urls_by_id: dict, out_dir: str) -> dict:
    # Generalizes download_thumbnails/download_youtube_thumbnails above (both candidate-object
    # shaped) for sources — like Envato — where a plain {id: url} mapping is all that's needed.
    paths = {}
    for item_id, url in urls_by_id.items():
        dest = os.path.abspath(f"{out_dir}/{item_id}.jpg")
        download_file(url, dest)
        paths[item_id] = dest
    return paths


def download_winning_video(
    candidate: PexelsCandidate, dest_path: str, target_width: int = 1920
) -> str:
    video_file = select_best_video_file(candidate.video_files, target_width)
    download_file(video_file.link, dest_path)
    return dest_path
