"""Measures the real push-in: zoompan crops at whole pixels, so a too-small pre-zoom upscale makes
the picture jump about a pixel every few frames (seen as shaking on text). Renders real clips and
checks the sub-pixel frame-to-frame shift of a textured region is steady."""
import shutil
import subprocess

import pytest

from assembly.normalize import run_image_clip, run_page_clip

np = pytest.importorskip("numpy")

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")

WIDTH, HEIGHT, FPS = 1920, 1080, 30
CROP = 512                     # textured square around the frame centre used for the measurement
FIRST_FRAME, LAST_FRAME = 30, 90   # 1 s to 3 s: the highlight fade is done, the zoom cap is far off
MAX_STD_PX = 0.25
MAX_WORST_PX = 0.6


def _textured_png(path):
    # blurred noise over a test pattern: sharp, detailed and aperiodic, so phase correlation locks
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
         "-i", f"testsrc2=s={WIDTH}x{HEIGHT},noise=alls=60:allf=t,gblur=sigma=0.8",
         "-frames:v", "1", path], check=True, capture_output=True)


def _gray_frames(video):
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", video, "-vf", "format=gray", "-f", "rawvideo", "-"],
        check=True, capture_output=True).stdout
    frames = np.frombuffer(raw, dtype=np.uint8).reshape(-1, HEIGHT, WIDTH)
    return frames[FIRST_FRAME:LAST_FRAME + 1]


def _crop(frame):
    top, left = (HEIGHT - CROP) // 2, (WIDTH - CROP) // 2
    return frame[top:top + CROP, left:left + CROP].astype(np.float64)


def _shift(a, b):
    """Sub-pixel (dx, dy) of b relative to a: windowed FFT phase correlation, parabolic peak."""
    window = np.outer(np.hanning(CROP), np.hanning(CROP))
    fa, fb = np.fft.fft2((a - a.mean()) * window), np.fft.fft2((b - b.mean()) * window)
    cross = fa.conj() * fb
    corr = np.fft.ifft2(cross / (np.abs(cross) + 1e-9)).real
    py, px = np.unravel_index(np.argmax(corr), corr.shape)

    def refine(minus, centre, plus):
        denom = minus - 2 * centre + plus
        return 0.0 if denom == 0 else 0.5 * (minus - plus) / denom

    dx = px + refine(corr[py, (px - 1) % CROP], corr[py, px], corr[py, (px + 1) % CROP])
    dy = py + refine(corr[(py - 1) % CROP, px], corr[py, px], corr[(py + 1) % CROP, px])
    wrap = lambda v: v - CROP if v > CROP / 2 else v
    return wrap(dx), wrap(dy)


def _shift_stats(video):
    frames = [_crop(f) for f in _gray_frames(video)]
    shifts = np.array([_shift(a, b) for a, b in zip(frames, frames[1:])])
    deviation = np.abs(shifts - np.median(shifts, axis=0))
    return shifts.std(axis=0), deviation.max(axis=0)


def _assert_smooth(video):
    std, worst = _shift_stats(video)
    print(f"shift std x/y = {std[0]:.3f}/{std[1]:.3f} px, worst deviation x/y = {worst[0]:.3f}/{worst[1]:.3f} px")
    assert (std < MAX_STD_PX).all(), f"push-in jitters: per-frame shift std {std} px"
    assert (worst < MAX_WORST_PX).all(), f"push-in jumps: worst deviation from the median shift {worst} px"


@needs_ffmpeg
def test_page_clip_push_in_drifts_smoothly(tmp_path):
    _textured_png(str(tmp_path / "page.png"))
    shutil.copy(tmp_path / "page.png", tmp_path / "plain.png")
    dest = str(tmp_path / "out.mp4")

    run_page_clip(str(tmp_path / "page.png"), str(tmp_path / "plain.png"), dest, 4.0)

    _assert_smooth(dest)


@needs_ffmpeg
def test_image_clip_push_in_drifts_smoothly(tmp_path):
    _textured_png(str(tmp_path / "in.png"))
    dest = str(tmp_path / "out.mp4")

    run_image_clip(str(tmp_path / "in.png"), dest, 4.0)

    _assert_smooth(dest)
