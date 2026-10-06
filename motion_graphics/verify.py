import json
import os
import subprocess


class ClipVerificationError(Exception):
    pass


def _probe_duration_seconds(path: str) -> float:
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", path],
            capture_output=True, text=True,
        )
    except OSError as e:
        raise ClipVerificationError(f"could not run ffprobe on {path}: {e}") from e
    if result.returncode != 0:
        raise ClipVerificationError(f"ffprobe failed on {path}: {result.stderr.strip()}")

    try:
        duration = float(json.loads(result.stdout)["format"]["duration"])
    except (KeyError, ValueError, json.JSONDecodeError) as e:
        raise ClipVerificationError(
            f"could not read a duration from ffprobe output for {path}: {e}"
        ) from e
    return duration


def verify_exported_clip(
    path: str,
    target_duration: float,
    duration_tolerance: float = 1.0,
    min_size_bytes: int = 5_000,
) -> None:
    if not os.path.exists(path):
        raise ClipVerificationError(f"no file at {path}")

    size_bytes = os.path.getsize(path)
    if size_bytes < min_size_bytes:
        raise ClipVerificationError(
            f"{path} is only {size_bytes} bytes — too small to be a real exported clip"
        )

    duration = _probe_duration_seconds(path)
    if abs(duration - target_duration) > duration_tolerance:
        raise ClipVerificationError(
            f"{path} is {duration:.1f}s, expected close to {target_duration:.1f}s "
            f"(tolerance {duration_tolerance:.1f}s)"
        )
