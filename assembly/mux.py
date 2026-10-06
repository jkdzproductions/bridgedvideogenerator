import json
import subprocess


class MuxError(Exception):
    pass


def _probe_duration_seconds(path: str) -> float:
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", path],
            capture_output=True, text=True,
        )
    except OSError as e:
        raise MuxError(f"could not run ffprobe on {path}: {e}") from e
    if result.returncode != 0:
        raise MuxError(f"ffprobe failed on {path}: {result.stderr.strip()}")

    try:
        return float(json.loads(result.stdout)["format"]["duration"])
    except (KeyError, ValueError, json.JSONDecodeError) as e:
        raise MuxError(f"could not read a duration from ffprobe output for {path}: {e}") from e


def check_durations_match(video_path: str, audio_path: str, tolerance: float = 0.1) -> None:
    video_duration = _probe_duration_seconds(video_path)
    audio_duration = _probe_duration_seconds(audio_path)
    if abs(video_duration - audio_duration) > tolerance:
        raise MuxError(
            f"video duration {video_duration:.3f}s and audio duration {audio_duration:.3f}s "
            f"differ by more than {tolerance}s tolerance — refusing to mux"
        )


def run_mux(video_path: str, audio_path: str, dest_path: str) -> None:
    check_durations_match(video_path, audio_path)

    cmd = [
        "ffmpeg", "-y", "-i", video_path, "-i", audio_path,
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "copy", "-c:a", "aac",
        dest_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise MuxError(f"ffmpeg mux failed: {result.stderr.strip()}")
