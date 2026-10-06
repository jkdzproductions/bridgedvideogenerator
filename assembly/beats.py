import os
from dataclasses import dataclass

from image_intake.paths import IMAGE_STILLS_DIR, find_image_still
from page_intake.paths import plain_still_path, still_path
from shot_list.models import ShotList


@dataclass
class BeatClip:
    index: int
    start: float
    end: float
    type: str
    source_path: str


class MissingClipsError(Exception):
    pass


def resolve_beat_clips(shot_list: ShotList) -> list[BeatClip]:
    clips: list[BeatClip] = []
    missing: list[tuple[int, str, str]] = []

    for i, beat in enumerate(shot_list.beats):
        if beat.type == "talking_head":
            clips.append(BeatClip(
                index=i, start=beat.start, end=beat.end, type="talking_head", source_path="",
            ))
            continue
        if beat.type == "page_highlight":
            final = still_path(beat.page.italic_index)
            absent = [p for p in (final, plain_still_path(beat.page.italic_index)) if not os.path.exists(p)]
            if absent:
                missing.append((i, "page_highlight", " and ".join(absent)))
                continue
            clips.append(BeatClip(
                index=i, start=beat.start, end=beat.end, type="page_highlight", source_path=final,
            ))
            continue
        if beat.type == "image":
            still = find_image_still(beat.image.italic_index)
            if still is None:
                missing.append((i, "image", f"{IMAGE_STILLS_DIR}/image_{beat.image.italic_index}.*"))
                continue
            clips.append(BeatClip(
                index=i, start=beat.start, end=beat.end, type="image", source_path=still,
            ))
            continue
        source_dir = "footage_output" if beat.type == "footage" else "graphics_output"
        path = f"{source_dir}/beat_{i}.mp4"
        if not os.path.exists(path):
            missing.append((i, beat.type, path))
            continue
        clips.append(BeatClip(
            index=i, start=beat.start, end=beat.end, type=beat.type, source_path=path,
        ))

    if missing:
        detail = "; ".join(f"beat {i} ({t}): expected {p}" for i, t, p in missing)
        raise MissingClipsError(f"{len(missing)} beat clip(s) missing: {detail}")

    return clips
