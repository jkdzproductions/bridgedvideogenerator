"""Stage 1 Step 1d: fetch every show-as-is image and write `image_readings.json`."""
import json
import os
import shutil

from graph_intake.download import GraphDownloadError, download_graph_image
from image_intake.paths import IMAGE_STILLS_DIR

IMAGE_LINKS = "image_links.json"
IMAGE_READINGS = "image_readings.json"


class ImageIntakeError(Exception):
    """A show-as-is image could not be fetched; the message names the phrase and URL."""


def prepare_image_readings(image_links: list, out_dir: str = ".") -> dict:
    """Download each image link in order, saving the original bytes unchanged as
    image_stills/image_<italic_index>.<ext>, and write image_readings.json:
    {"<italic_index>": {"italic_text", "url", "still_path", "width", "height"}}. Returns it keyed
    by int italic_index. The file is written only after every image arrived, so a failed run never
    leaves readings that look complete."""
    stills_dir = os.path.join(out_dir, IMAGE_STILLS_DIR)
    shutil.rmtree(stills_dir, ignore_errors=True)
    readings_path = os.path.join(out_dir, IMAGE_READINGS)
    if os.path.exists(readings_path):
        os.remove(readings_path)
    readings = {}
    if image_links:
        os.makedirs(stills_dir, exist_ok=True)
    for link in image_links:
        try:
            image = download_graph_image(link["url"], link["text"], link["italic_index"], stills_dir)
        except GraphDownloadError as e:
            raise ImageIntakeError(f"show-as-is image: {e}") from e
        extension = os.path.splitext(image["image_path"])[1]
        still = os.path.abspath(os.path.join(stills_dir, f"image_{link['italic_index']}{extension}"))
        os.replace(image["image_path"], still)  # the downloader names it graph_<n>.<ext>
        readings[link["italic_index"]] = {
            "italic_text": link["text"], "url": link["url"], "still_path": still,
            "width": image["width"], "height": image["height"]}
    os.makedirs(out_dir, exist_ok=True)
    with open(readings_path, "w", encoding="utf-8") as f:
        json.dump({str(k): v for k, v in readings.items()}, f, indent=2)
    return readings


def load_image_readings(readings_path: str = IMAGE_READINGS, links_path: str = IMAGE_LINKS) -> dict:
    """image_readings.json keyed by int italic_index, checked against image_links.json so images
    left over from a different script can never reach the director or the assembly."""
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
