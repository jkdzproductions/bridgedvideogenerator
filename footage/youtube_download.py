import json
import os
import subprocess

import yt_dlp
from yt_dlp.utils import download_range_func

from footage.download import download_file
from footage.youtube import YouTubeCandidate


class YouTubeDownloadError(Exception):
    pass


class PortraitVideoError(YouTubeDownloadError):
    """A downloaded clip turned out not to be landscape, so it can't be used in a 16:9 video."""


def probe_video_dimensions(path: str) -> tuple[int, int]:
    """Displayed (width, height) of a video file's first video stream, via ffprobe."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=width,height:stream_side_data=rotation:stream_tags=rotate",
                "-of", "json", path,
            ],
            capture_output=True, text=True,
        )
    except OSError as e:
        raise YouTubeDownloadError(f"could not run ffprobe on {path}: {e}") from e
    if result.returncode != 0:
        raise YouTubeDownloadError(f"ffprobe failed on {path}: {result.stderr.strip()}")

    try:
        streams = json.loads(result.stdout).get("streams", [])
        if not streams or "width" not in streams[0] or "height" not in streams[0]:
            raise YouTubeDownloadError(f"ffprobe found no video stream in {path}")
        stream = streams[0]
        width, height = int(stream["width"]), int(stream["height"])

        rotation = stream.get("tags", {}).get("rotate", 0)
        for side_data in stream.get("side_data_list", []):
            rotation = side_data.get("rotation", rotation)
        if int(float(rotation)) % 180 != 0:
            width, height = height, width  # stored sideways, displayed rotated
    except (ValueError, TypeError, AttributeError) as e:
        raise YouTubeDownloadError(f"could not read ffprobe output for {path}: {e}") from e
    return width, height


def download_youtube_thumbnails(
    candidates: list[YouTubeCandidate], out_dir: str
) -> dict[str, str]:
    # Absolute paths: these go into the scoring prompt, and the scoring subagent's Read tool
    # needs absolute paths to open the thumbnails reliably.
    paths: dict[str, str] = {}
    for candidate in candidates:
        dest = os.path.abspath(f"{out_dir}/{candidate.video_id}.jpg")
        download_file(candidate.thumbnail_url, dest)
        paths[candidate.video_id] = dest
    return paths


def _remove_if_exists(path: str) -> None:
    if os.path.exists(path):
        os.remove(path)


def download_youtube_clip(video_id: str, dest_path: str, duration_seconds: float) -> str:
    # Remove any leftover file at dest_path up front (e.g. from an earlier video or an earlier
    # attempt at this beat), so the existence check below can only pass on a file this call
    # actually produced.
    _remove_if_exists(dest_path)

    ydl_opts = {
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "outtmpl": dest_path,
        "download_ranges": download_range_func(None, [(0, duration_seconds)]),
        "force_keyframes_at_cuts": True,
        # yt-dlp's default (overwrites=None) keeps an existing video file at outtmpl and still
        # reports success, which silently passes off stale footage as this video's clip.
        "overwrites": True,
        "quiet": True,
        "no_warnings": True,
        # Without a PO-token provider, yt-dlp's default tv/web_safari clients intermittently
        # get UNPLAYABLE / "The page needs to be reloaded" because YouTube now forces SABR
        # streaming on them (https://github.com/yt-dlp/yt-dlp/issues/12482). The android
        # client isn't subject to that restriction, so force it to avoid the failure.
        "extractor_args": {"youtube": {"player_client": ["android"]}},
    }
    url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except Exception as e:
        _remove_if_exists(dest_path)
        raise YouTubeDownloadError(f"failed to download YouTube video {video_id}: {e}") from e

    if not os.path.exists(dest_path):
        raise YouTubeDownloadError(
            f"yt-dlp reported success for YouTube video {video_id} but no file was produced "
            f"at {dest_path}"
        )
    if os.path.getsize(dest_path) == 0:
        _remove_if_exists(dest_path)
        raise YouTubeDownloadError(
            f"yt-dlp produced an empty file for YouTube video {video_id} at {dest_path}"
        )
    return dest_path
