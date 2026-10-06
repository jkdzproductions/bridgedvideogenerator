import os
import subprocess

TARGET_WIDTH = 1920
TARGET_HEIGHT = 1080
TARGET_FPS = 30


class NormalizeError(Exception):
    pass


def build_normalize_command(source_path: str, dest_path: str, target_duration: float) -> list[str]:
    filter_chain = (
        f"scale={TARGET_WIDTH}:{TARGET_HEIGHT}:force_original_aspect_ratio=decrease,"
        f"pad={TARGET_WIDTH}:{TARGET_HEIGHT}:(ow-iw)/2:(oh-ih)/2,"
        f"fps={TARGET_FPS},"
        f"tpad=stop_mode=clone:stop_duration={target_duration},"
        f"setsar=1"
    )
    return [
        "ffmpeg", "-y", "-i", source_path,
        "-vf", filter_chain,
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-an",
        "-t", f"{target_duration}",
        dest_path,
    ]


def run_normalize(source_path: str, dest_path: str, target_duration: float) -> None:
    cmd = build_normalize_command(source_path, dest_path, target_duration)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise NormalizeError(
            f"ffmpeg normalize failed for {source_path}: {result.stderr.strip()}"
        )


def build_black_clip_command(dest_path: str, duration: float) -> list[str]:
    return [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"color=c=black:s={TARGET_WIDTH}x{TARGET_HEIGHT}:r={TARGET_FPS}",
        "-vf", "setsar=1",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-an",
        "-t", f"{duration}",
        dest_path,
    ]


def run_black_clip(dest_path: str, duration: float) -> None:
    cmd = build_black_clip_command(dest_path, duration)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise NormalizeError(
            f"ffmpeg black clip failed for {dest_path}: {result.stderr.strip()}"
        )


# zoompan crops at whole-pixel positions, so the push-in only drifts smoothly if the picture has far
# more pixels than the output: at 3840x2160 it sat still and then jumped about a pixel every few
# frames (visible as shaking on text). 7680x4320 measured to cut that jitter to about a third.
PUSH_IN_PRESCALE_WIDTH = 7680
PUSH_IN_PRESCALE_HEIGHT = 4320

PAGE_FADE_START = 0.3  # seconds before the highlight starts appearing
PAGE_FADE_SECONDS = 0.5
PAGE_ZOOM_STEP = 0.00035  # per output frame: about +6% over 6 seconds at 30 fps
PAGE_ZOOM_MAX = 1.06


def build_page_clip_command(still_path: str, plain_path: str, dest_path: str, duration: float) -> list[str]:
    """The blurred plain page with the finished still (highlight on) fading in over it, then a
    slow push-in. The finished still is the second input so it sits on top."""
    graph = (
        f"[1:v]format=rgba,fade=t=in:st={PAGE_FADE_START}:d={PAGE_FADE_SECONDS}:alpha=1[hl];"
        f"[0:v][hl]overlay=format=auto,format=yuv420p,"
        f"scale={PUSH_IN_PRESCALE_WIDTH}:{PUSH_IN_PRESCALE_HEIGHT}:flags=bicubic,"  # more pixels: sub-pixel zoompan steps
        f"zoompan=z='min(1+{PAGE_ZOOM_STEP}*on,{PAGE_ZOOM_MAX})':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        f":d=1:s={TARGET_WIDTH}x{TARGET_HEIGHT}:fps={TARGET_FPS},setsar=1[v]"
    )
    return [
        "ffmpeg", "-y",
        "-loop", "1", "-framerate", str(TARGET_FPS), "-i", plain_path,
        "-loop", "1", "-framerate", str(TARGET_FPS), "-i", still_path,
        "-filter_complex", graph,
        "-map", "[v]",
        "-an",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-t", f"{duration}",
        dest_path,
    ]


def run_page_clip(still_path: str, plain_path: str, dest_path: str, duration: float) -> None:
    cmd = build_page_clip_command(still_path, plain_path, dest_path, duration)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise NormalizeError(
            f"ffmpeg page clip failed for {still_path}: {result.stderr.strip()}"
        )


IMAGE_ZOOM_STEP = PAGE_ZOOM_STEP  # the same slow push-in as a page clip
IMAGE_ZOOM_MAX = PAGE_ZOOM_MAX
IMAGE_BACKGROUND_DARKEN = -0.4  # brightness offset of the blurred copy behind the image (-1.0 is black; -0.25 left bars too bright)
# The background is blurred at 1/4 size and scaled back up: a 1920x1080 blur of one still is wasted work.
IMAGE_BLUR_WIDTH = TARGET_WIDTH // 4
IMAGE_BLUR_HEIGHT = TARGET_HEIGHT // 4


def build_image_frame_command(source_path: str, frame_path: str) -> list[str]:
    """One 1920x1080 PNG: a blurred, darkened copy of the image fills the frame; the sharp
    original is scaled to fit inside it and centered on top. Transparent areas are flattened onto
    white first. Only the first frame of a GIF or
    WebP is used."""
    graph = (
        # Flatten onto white first (a copy of the image painted solid white, the image over it), so
        # transparent pixels are white in both layers instead of whatever colour hides under them.
        f"[0:v]format=rgba,split=2[img][blank];"
        f"[blank]drawbox=x=0:y=0:w=iw:h=ih:color=white:t=fill[white];"
        f"[white][img]overlay=format=auto,format=rgb24,split=2[bg][fg];"
        f"[bg]scale={IMAGE_BLUR_WIDTH}:{IMAGE_BLUR_HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={IMAGE_BLUR_WIDTH}:{IMAGE_BLUR_HEIGHT},boxblur=12:3,"
        f"scale={TARGET_WIDTH}:{TARGET_HEIGHT}:flags=bicubic,eq=brightness={IMAGE_BACKGROUND_DARKEN}[back];"
        f"[fg]scale={TARGET_WIDTH}:{TARGET_HEIGHT}:force_original_aspect_ratio=decrease:flags=lanczos[front];"
        f"[back][front]overlay=(W-w)/2:(H-h)/2,format=rgb24[v]"
    )
    return [
        "ffmpeg", "-y", "-i", source_path,
        "-filter_complex", graph,
        "-map", "[v]",
        "-frames:v", "1",
        frame_path,
    ]


def build_image_clip_command(frame_path: str, dest_path: str, duration: float) -> list[str]:
    """The finished frame held for `duration`, with the page clips' slow push-in."""
    video_filter = (
        f"format=yuv420p,"
        f"scale={PUSH_IN_PRESCALE_WIDTH}:{PUSH_IN_PRESCALE_HEIGHT}:flags=bicubic,"  # more pixels: sub-pixel zoompan steps
        f"zoompan=z='min(1+{IMAGE_ZOOM_STEP}*on,{IMAGE_ZOOM_MAX})':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        f":d=1:s={TARGET_WIDTH}x{TARGET_HEIGHT}:fps={TARGET_FPS},setsar=1"
    )
    return [
        "ffmpeg", "-y",
        "-loop", "1", "-framerate", str(TARGET_FPS), "-i", frame_path,
        "-vf", video_filter,
        "-an",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-t", f"{duration}",
        dest_path,
    ]


def run_image_clip(source_path: str, dest_path: str, duration: float) -> None:
    frame_path = f"{os.path.splitext(dest_path)[0]}_frame.png"
    for cmd in (build_image_frame_command(source_path, frame_path),
                build_image_clip_command(frame_path, dest_path, duration)):
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise NormalizeError(
                f"ffmpeg image clip failed for {source_path}: {result.stderr.strip()}"
            )
