import os
import subprocess

from footage.youtube_download import probe_video_dimensions

# Every YouTube clip that wins a beat is mirrored, zoomed in a hair, given a light film grain and a
# slight vignette# before it is saved as footage_output/beat_<n>.mp4. Pexels and Envato clips are left alone.
ZOOM = 1.03  # fixed 3% crop-in, the same for the whole clip
GRAIN_STRENGTH = 6  # ffmpeg noise strength; ~6 is faintly visible, 20+ is heavy
VIGNETTE_ANGLE = "PI/5"  # ffmpeg's default vignette (corners clearly darker)
VIGNETTE_STRENGTH = 0.5  # that vignette blended in at half strength; 1.0 = the full default


class YouTubeLookError(Exception):
    pass


def _even(value: float) -> int:
    return int(value / 2) * 2  # yuv420p needs even sizes


def build_look_command(source_path: str, dest_path: str, width: int, height: int) -> list[str]:
    # Crop the centre window that is ZOOM times smaller, then scale it back up to the clip's own
    # width and height, so the resolution never changes.
    chain = (
        "hflip,"
        f"crop={_even(width / ZOOM)}:{_even(height / ZOOM)},"
        f"scale={width}:{height}:flags=lanczos,"
        f"noise=alls={GRAIN_STRENGTH}:allf=t,"
        # Half-strength vignette: blend the vignetted copy over the plain one at 50% opacity.
        f"split[plain][edge];[edge]vignette={VIGNETTE_ANGLE}[dark];"
        f"[plain][dark]blend=all_opacity={VIGNETTE_STRENGTH}"
    )
    return [
        "ffmpeg", "-y", "-i", source_path, "-vf", chain,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
        "-an", dest_path,
    ]


def _remove_if_exists(path: str) -> None:
    if os.path.exists(path):
        os.remove(path)


def apply_youtube_look(path: str) -> str:
    """Replace the clip at `path` with its mirrored, zoomed, grained version, in place.

    Written to a work file first and swapped in only on success. On failure both files are
    deleted, because Stage 2 treats any existing footage_output/beat_<n>.mp4 as a finished beat.
    """
    work_path = os.path.splitext(path)[0] + ".look.mp4"
    _remove_if_exists(work_path)
    try:
        width, height = probe_video_dimensions(path)
    except Exception as e:
        _remove_if_exists(path)
        raise YouTubeLookError(f"could not read the size of {path}: {e}") from e
    result = subprocess.run(
        build_look_command(path, work_path, width, height), capture_output=True, text=True
    )
    if result.returncode != 0 or not os.path.exists(work_path) or os.path.getsize(work_path) == 0:
        _remove_if_exists(work_path)
        _remove_if_exists(path)
        raise YouTubeLookError(
            f"ffmpeg could not apply the YouTube look to {path}: {result.stderr.strip()[-300:]}"
        )
    os.replace(work_path, path)
    return path
