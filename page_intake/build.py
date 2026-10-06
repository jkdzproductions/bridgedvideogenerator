"""Stage 1 Step 1c: capture every linked page and write `page_readings.json`."""
import json
import os
import shutil

from page_intake.capture import PageCaptureError, capture_page
from page_intake.paths import PAGE_STILLS_DIR

PAGE_LINKS = "page_links.json"
PAGE_READINGS = "page_readings.json"


def prepare_page_readings(page_links: list, out_dir: str = ".") -> dict:
    """Capture each page link in order and write page_readings.json:
    {"<italic_index>": {"italic_text", "url", "passage", "title", "still_path", "plain_path",
    "uncovered"}}. Returns it keyed by int italic_index. The file is written only after every link
    has been captured, so a failed run never leaves readings that look complete."""
    shutil.rmtree(os.path.join(out_dir, PAGE_STILLS_DIR), ignore_errors=True)
    readings_path = os.path.join(out_dir, PAGE_READINGS)
    if os.path.exists(readings_path):
        os.remove(readings_path)
    readings = {}
    for link in page_links:
        try:
            result = capture_page(link["url"], out_dir, link["italic_index"])
        except PageCaptureError as e:
            raise PageCaptureError(f"page highlight for {link['text']!r} ({link['url']}): {e}") from e
        readings[link["italic_index"]] = {
            "italic_text": link["text"], "url": link["url"],
            **{key: result[key] for key in ("passage", "title", "still_path", "plain_path", "uncovered")}}
    os.makedirs(out_dir, exist_ok=True)
    with open(readings_path, "w", encoding="utf-8") as f:
        json.dump({str(k): v for k, v in readings.items()}, f, indent=2)
    return readings


def load_page_readings(readings_path: str = PAGE_READINGS, links_path: str = PAGE_LINKS) -> dict:
    """page_readings.json keyed by int italic_index, checked against page_links.json so stills left
    over from a different script can never reach the director or the assembly."""
    with open(readings_path, encoding="utf-8") as f:
        raw_readings = json.load(f)
    with open(links_path, encoding="utf-8") as f:
        raw_links = json.load(f)
    readings = {int(k): v for k, v in raw_readings.items()}
    links = {link["italic_index"]: link for link in raw_links}
    stale = sorted(set(readings) ^ set(links)) + sorted(
        i for i in set(readings) & set(links) if readings[i]["url"] != links[i]["url"])
    if stale:
        raise ValueError(
            f"{readings_path} does not match {links_path} (graphic spans {stale}) — it is left over "
            "from another script; re-run Stage 1 from Step 1a")
    return readings
