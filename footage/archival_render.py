# footage/archival_render.py
"""Turn picked archival items into the beat's finished clip, footage_output/beat_<n>.mp4.
Stage 4 treats the result like any other footage clip, so assembly needs no changes."""
import os
import subprocess

from assembly.concat import run_concat
from assembly.normalize import build_normalize_command, run_image_clip
from footage.archive_types import ArchiveCandidate

MIN_SECONDS_PER_PHOTO = 2.0
FILM_START_FRACTION = 0.2  # start this far into a film to skip leader, titles and credits


class ArchivalRenderError(Exception):
    pass


def photo_shares(total_duration: float, photo_count: int) -> list[float]:
    """How long each photo is held: equal shares, but never fewer than MIN_SECONDS_PER_PHOTO seconds
    each (so a short cut gets fewer photos), and always at least one photo."""
    usable = max(1, min(photo_count, int(total_duration // MIN_SECONDS_PER_PHOTO)))
    return [total_duration / usable] * usable


def render_photo_beat(photo_paths: list[str], dest_path: str, target_duration: float, work_dir: str) -> str:
    if not photo_paths:
        raise ArchivalRenderError("no photos to render")
    if target_duration <= 0:
        raise ArchivalRenderError(f"target duration must be positive, got {target_duration}s")
    shares = photo_shares(target_duration, len(photo_paths))
    os.makedirs(work_dir, exist_ok=True)
    os.makedirs(os.path.dirname(os.path.abspath(dest_path)), exist_ok=True)
    clips = []
    try:
        for i, (photo, share) in enumerate(zip(photo_paths, shares)):
            clip = os.path.join(work_dir, f"photo_{i}.mp4")
            run_image_clip(photo, clip, share)
            clips.append(clip)
        if os.path.exists(dest_path):
            os.remove(dest_path)
        if len(clips) == 1:
            os.replace(clips[0], dest_path)
        else:
            run_concat(clips, dest_path, os.path.join(work_dir, "concat_list.txt"))
    except Exception:
        if os.path.exists(dest_path):
            os.remove(dest_path)
        raise
    return dest_path


def film_start_offset(duration: float, target_duration: float) -> float:
    return max(0.0, min(duration * FILM_START_FRACTION, duration - target_duration))


def build_film_command(media_url: str, dest_path: str, target_duration: float, duration: float) -> list[str]:
    """The normal footage-normalize command, reading the film straight from its URL after a seek
    (ffmpeg fetches only the part it needs), so a long reel is never downloaded whole."""
    cmd = build_normalize_command(media_url, dest_path, target_duration)
    cmd[2:2] = ["-ss", f"{film_start_offset(duration, target_duration):.2f}"]
    return cmd


def film_frame_times(duration: float, target_duration: float) -> list[float]:
    """Three moments inside the part of the film that will play (start, middle, just before the end),
    clamped so every one lies within the segment and inside the film."""
    start = film_start_offset(duration, target_duration)
    last = min(start + target_duration, duration) - 0.1
    return sorted(max(start, min(t, last)) for t in (start, start + target_duration / 2, start + target_duration - 0.5))


def build_frame_command(media_url: str, t: float, out_path: str) -> list[str]:
    """One still frame at time t, read straight from the URL (ffmpeg fetches only what it needs)."""
    return ["ffmpeg", "-y", "-ss", f"{t:.2f}", "-i", media_url, "-frames:v", "1", "-vf", "scale=640:-2", out_path]


def render_film_beat(candidate: ArchiveCandidate, dest_path: str, target_duration: float) -> str:
    if target_duration <= 0:
        raise ArchivalRenderError(f"target duration must be positive, got {target_duration}s")
    if candidate.duration_seconds < target_duration:
        raise ArchivalRenderError(
            f"film {candidate.display_id} is {candidate.duration_seconds:.1f}s, shorter than the "
            f"{target_duration:.1f}s cut")
    os.makedirs(os.path.dirname(os.path.abspath(dest_path)), exist_ok=True)
    if os.path.exists(dest_path):
        os.remove(dest_path)
    cmd = build_film_command(candidate.media_url, dest_path, target_duration, candidate.duration_seconds)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
    except OSError as e:
        if os.path.exists(dest_path):
            os.remove(dest_path)
        raise ArchivalRenderError(f"could not run ffmpeg for {candidate.display_id}: {e}") from e
    if result.returncode != 0:
        if os.path.exists(dest_path):
            os.remove(dest_path)
        raise ArchivalRenderError(f"ffmpeg film render failed for {candidate.display_id}: {result.stderr.strip()}")
    return dest_path
