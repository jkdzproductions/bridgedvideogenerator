import json
import os
import subprocess


class FinalOutputVerificationError(Exception):
    pass


def _probe_output(path: str) -> dict:
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "stream=codec_type,width,height:format=duration", "-of", "json", path],
            capture_output=True, text=True,
        )
    except OSError as e:
        raise FinalOutputVerificationError(f"could not run ffprobe on {path}: {e}") from e
    if result.returncode != 0:
        raise FinalOutputVerificationError(f"ffprobe failed on {path}: {result.stderr.strip()}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise FinalOutputVerificationError(
            f"could not parse ffprobe output for {path}: {e}"
        ) from e


def verify_final_output(
    path: str,
    expected_duration: float,
    expected_width: int = 1920,
    expected_height: int = 1080,
    duration_tolerance: float = 0.1,
) -> None:
    if not os.path.exists(path):
        raise FinalOutputVerificationError(f"no file at {path}")

    payload = _probe_output(path)
    streams = payload.get("streams", [])

    video_streams = [s for s in streams if s.get("codec_type") == "video"]
    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
    if not video_streams or not audio_streams:
        raise FinalOutputVerificationError(
            f"{path} missing required stream(s): video={bool(video_streams)}, "
            f"audio={bool(audio_streams)}"
        )

    width, height = video_streams[0].get("width"), video_streams[0].get("height")
    if width != expected_width or height != expected_height:
        raise FinalOutputVerificationError(
            f"{path} is {width}x{height}, expected {expected_width}x{expected_height}"
        )

    try:
        duration = float(payload["format"]["duration"])
    except (KeyError, ValueError) as e:
        raise FinalOutputVerificationError(
            f"could not read duration from ffprobe output for {path}: {e}"
        ) from e
    if abs(duration - expected_duration) > duration_tolerance:
        raise FinalOutputVerificationError(
            f"{path} is {duration:.3f}s, expected close to {expected_duration:.3f}s "
            f"(tolerance {duration_tolerance}s)"
        )
