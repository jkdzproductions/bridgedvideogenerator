import os

from assembly.beats import BeatClip
from assembly.concat import run_concat
from assembly.mux import run_mux
from assembly.normalize import TARGET_FPS, run_black_clip, run_image_clip, run_normalize, run_page_clip
from assembly.verify import verify_final_output
from page_intake.paths import plain_path_for


def normalize_all(clips: list[BeatClip], staging_dir: str) -> list[str]:
    os.makedirs(staging_dir, exist_ok=True)
    normalized_paths = []
    frames_so_far = 0
    for clip in clips:
        dest = os.path.join(staging_dir, f"beat_{clip.index}.mp4")
        # Each clip is cut to whole frames. Rounding every clip on its own lost up to a frame per
        # clip (0.4 s over 30 beats), so work from the cumulative end time: the rounding error
        # never builds up and the total stays within one frame of the voiceover.
        clip_frames = max(1, round(clip.end * TARGET_FPS) - frames_so_far)
        frames_so_far += clip_frames
        duration = clip_frames / TARGET_FPS
        if clip.type == "talking_head":
            run_black_clip(dest, duration)
        elif clip.type == "page_highlight":
            run_page_clip(clip.source_path, plain_path_for(clip.source_path), dest, duration)
        elif clip.type == "image":
            run_image_clip(clip.source_path, dest, duration)
        else:
            run_normalize(clip.source_path, dest, duration)
        normalized_paths.append(dest)
    return normalized_paths


def assemble(
    clips: list[BeatClip],
    audio_path: str,
    staging_dir: str,
    final_path: str,
    total_duration: float,
) -> str:
    normalized_paths = normalize_all(clips, staging_dir)

    concat_video_path = os.path.join(staging_dir, "concat.mp4")
    list_file_path = os.path.join(staging_dir, "concat_list.txt")
    run_concat(normalized_paths, concat_video_path, list_file_path)

    os.makedirs(os.path.dirname(final_path) or ".", exist_ok=True)
    candidate_path = os.path.join(staging_dir, "final_candidate.mp4")
    run_mux(concat_video_path, audio_path, candidate_path)

    verify_final_output(candidate_path, total_duration)
    os.replace(candidate_path, final_path)
    return final_path
