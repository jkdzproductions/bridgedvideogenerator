import os
import subprocess


class ConcatError(Exception):
    pass


def build_concat_list(clip_paths: list[str]) -> str:
    lines = []
    for path in clip_paths:
        abs_path = os.path.abspath(path)
        escaped = abs_path.replace("'", "'\\''")
        lines.append(f"file '{escaped}'")
    return "\n".join(lines) + "\n"


def run_concat(clip_paths: list[str], dest_path: str, list_file_path: str) -> None:
    with open(list_file_path, "w") as f:
        f.write(build_concat_list(clip_paths))

    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", list_file_path, "-c", "copy", dest_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise ConcatError(f"ffmpeg concat failed: {result.stderr.strip()}")
