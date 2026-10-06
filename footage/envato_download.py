import glob
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time

from footage.envato import EnvatoCandidate

logger = logging.getLogger(__name__)


class EnvatoDownloadError(Exception):
    pass


def find_completed_download(
    downloads_dir: str, started_at: float, deadline_seconds: float = 60
) -> str:
    # Chrome's naming for these downloads is not predictable from the item title while in
    # progress ("Unconfirmed <id>.crdownload") — match by mtime-since-start and "nothing still
    # pending," exactly Stage 3's Step 2f pattern, extracted here as a real tested function.
    #
    # LIVE FINDING (Task 3): this folder-polling approach is NOT what `download_envato_clip`
    # actually uses. Live-verified against a real detail page: clicking the Download button
    # under Playwright fires a Playwright-managed `download` event (caught by
    # `page.expect_download()`), and the file does NOT land in the OS-level `~/Downloads`
    # folder at all — Playwright intercepts Chromium's download via CDP and keeps it in its own
    # internal temp file (reachable via `download.path()`), never in the real filesystem location
    # a human would see. Confirmed directly: after a real 214MB download completed via
    # `expect_download()`, `~/Downloads` had zero new files. So this function, exactly as given
    # in the brief, remains correct pure logic and is kept (and tested) as specified, but
    # `download_envato_clip` no longer calls it — see that function's docstring for the real
    # orchestration.
    deadline = time.time() + deadline_seconds
    while True:
        new = [
            p for p in glob.glob(os.path.join(downloads_dir, "*.mov"))
            if os.path.getmtime(p) >= started_at
        ]
        pending = [
            p for p in glob.glob(os.path.join(downloads_dir, "*.crdownload"))
            if os.path.getmtime(p) >= started_at
        ]
        if new and not pending:
            break
        if time.time() > deadline:
            raise EnvatoDownloadError(
                f"no finished .mov download appeared in {downloads_dir} since {started_at}"
            )
        time.sleep(0.5)
    if len(new) != 1:
        raise EnvatoDownloadError(
            f"expected exactly one new .mov in {downloads_dir}, found {new} — "
            "picking one would risk grabbing the wrong file"
        )
    return new[0]


def trim_envato_clip(source_path: str, dest_path: str, duration_seconds: float) -> str:
    # Re-encodes (never stream-copies). Envato masters arrive as either ProRes (.mov) or
    # in-camera h264 (Task 3's live DJI_0416.MOV), and the production destination is
    # footage_output/beat_<n>.mp4 — a `-c copy` of ProRes into an .mp4 container fails outright
    # (ffmpeg rc=234 "Could not write header", reproduced in the final branch review), which
    # would STOP Stage 2 on every ProRes winner. Re-encoding to h264/yuv420p also retires the
    # Task 3-deferred "safe only because the source has no B-frames" stream-copy fragility.
    # `-an` matches assembly/normalize.py's run_normalize, which strips audio from every
    # footage clip anyway (the voiceover is muxed separately).
    result = subprocess.run(
        ["ffmpeg", "-y", "-i", source_path, "-t", f"{duration_seconds}",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
         "-an", dest_path],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise EnvatoDownloadError(f"ffmpeg trim failed for {source_path}: {result.stderr.strip()}")
    return dest_path


_MAX_DOWNLOAD_ATTEMPTS = 3
_RETRY_SLEEP_SECONDS = 2


def download_envato_clip(
    candidate: EnvatoCandidate,
    dest_path: str,
    target_duration_seconds: float,
    profile_dir: str,
) -> str:
    # REAL, JUSTIFIED DEVIATION FROM THE BRIEF (live-verified, not assumed — see
    # `_click_download_button` and `find_completed_download` for the full finding): clicking
    # Envato's Download button does not produce an OS-level file that `find_completed_download`
    # could ever poll for. Playwright intercepts the browser's download via CDP as its own
    # `download` event, held in Playwright's own internal temp file (`download.path()`) that we
    # move out ourselves. So this orchestration uses `page.expect_download()` directly instead of
    # folder-polling.
    #
    # The raw master is saved into a private, fresh temporary directory — never the user's real
    # ~/Downloads. Envato's suggested filenames are generic camera names (e.g. DJI_0416.MOV), so
    # saving there could overwrite, and then delete, an unrelated file of the user's with the same
    # name. (The former `downloads_dir` parameter only existed for the abandoned folder-polling
    # design and has been removed.)
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright

    with tempfile.TemporaryDirectory(prefix="envato_download_") as raw_dir:
        with sync_playwright() as p:
            for attempt in range(1, _MAX_DOWNLOAD_ATTEMPTS + 1):
                try:
                    raw_path = _attempt_download(p, candidate, profile_dir, raw_dir)
                    break
                except PlaywrightError as exc:
                    if "canceled" not in str(exc):
                        raise
                    if attempt == _MAX_DOWNLOAD_ATTEMPTS:
                        raise EnvatoDownloadError(
                            f"Envato download failed after {attempt} attempts; "
                            f"last error: {exc}"
                        ) from exc
                    time.sleep(_RETRY_SLEEP_SECONDS)

        # The full downloaded master (often 1GB+) has no further use once trimmed; the
        # TemporaryDirectory removes it (and anything else in raw_dir) on exit, success or not.
        return trim_envato_clip(raw_path, dest_path, target_duration_seconds)


def _attempt_download(p, candidate: EnvatoCandidate, profile_dir: str, raw_dir: str) -> str:
    """One full download attempt with a fresh browser context; returns the raw master's path."""
    context = p.chromium.launch_persistent_context(
        profile_dir, headless=True, accept_downloads=True
    )
    raw_path = None
    try:
        page = context.new_page()
        page.goto(candidate.detail_url, wait_until="domcontentloaded")
        with page.expect_download(timeout=60000) as download_info:
            _click_download_button(page)
        download = download_info.value
        raw_path = os.path.join(raw_dir, download.suggested_filename)

        # LIVE-DIAGNOSED (post-merge, real production failure): `download.save_as(raw_path)`
        # raised `playwright._impl._errors.Error: Download.save_as: canceled` on every
        # attempt for a specific very large (1.4GB ProRes) Envato master, while a 145MB
        # h264 item downloaded fine via the exact same save_as() code. `download.path()`
        # (Playwright's own already-completed internal download file) reads the same
        # 1.4GB item correctly at its full, real byte count, so we read the file from
        # there and move it out ourselves instead of using save_as(). This must happen
        # before `context.close()` below: Playwright owns that internal temp file's
        # lifecycle and cleans it up when the browser context closes, so `shutil.move` has
        # to run first (confirmed live: moving before close is safe).
        #
        # download.path() is NOT a total fix on its own: live testing on 1GB+ items showed
        # intermittent `Download.path: canceled` (observed in live testing on 1GB+ items, roughly 40%
        # of attempts, at varying points in the transfer, with no code-visible cause; clean 200 responses with correct
        # content-length). Successful attempts were byte-identical at full size. This looks
        # like genuine flakiness at the Chromium/network layer, so `download_envato_clip` now
        # retries the whole attempt (fresh context -> click -> expect_download -> path() ->
        # move) up to _MAX_DOWNLOAD_ATTEMPTS times when the error is a Playwright "canceled".
        shutil.move(download.path(), raw_path)
        return raw_path
    except BaseException:
        # Never leave a partial file behind for the next attempt. A secondary failure here must
        # not replace the original error.
        try:
            if raw_path and os.path.exists(raw_path):
                os.remove(raw_path)
        except OSError:
            logger.warning("could not remove partial download %s", raw_path, exc_info=True)
        raise
    finally:
        try:
            context.close()
        except Exception:  # noqa: BLE001 - must not mask the original error / a success
            logger.warning("error closing browser context", exc_info=True)


_DOWNLOAD_BUTTON_TEXT_PATTERN = re.compile(r"^Download\b")


def _click_download_button(page) -> None:
    """Live-verified against a real, logged-in item detail page (Task 3), not guessed:

    - The visible "Download <size>" text (e.g. "Download 4K") lives on a plain `<div>` with no
      semantic role, href, or data attributes of its own — matching Task 2's finding that this
      site's UI has no stable semantic structure. The actual clickable element, several
      ancestors up, is a `<button>` with an `onclick` handler and Envato's own
      `data-analytics-*` tracking attributes (item_id, item_title, format_label, asset_uuid,
      etc.) — but Playwright's `.click()` on the inner text element works correctly (confirmed
      live) because a real click at that screen position is delivered by the browser to
      whichever element is actually there, which bubbles up through the ancestor chain to the
      button's handler exactly as a real user's click would. Content-based lookup
      (`get_by_text` on a "Download" prefix) was used rather than hardcoding any of the
      `ds-b1394h...`-style generated class names on those ancestors, which look exactly as
      build-specific/fragile as the `_iconGrid_*` classes Task 2 already ruled out.
    - No license-picker dialog or further confirmation appears — confirmed live, matching the
      spike's original observation of an instant "Automatically licensed" toast with nothing
      further to click.
    - Confirmed live with a real ~214MB download of a real item: clicking this element does
      NOT produce a file in the OS-level `~/Downloads` folder that a human would see (checked:
      zero new files appeared there). It instead fires a genuine Playwright `download` event
      (caught via `page.expect_download()` in the caller) — a real network transfer of a real
      Envato-hosted URL (`video-downloads.elements.envatousercontent.com/.../DJI_0416.MOV`),
      not a same-page JS fetch that stays invisible to Playwright. So `page.expect_download()`
      is the correct, real mechanism — `find_completed_download`'s folder-polling approach,
      while correctly implemented as pure logic, is not reachable from this browser-driven path
      and is not used by `download_envato_clip`.
    """
    button = page.get_by_text(_DOWNLOAD_BUTTON_TEXT_PATTERN).first
    button.wait_for(state="visible", timeout=15000)
    button.click()
