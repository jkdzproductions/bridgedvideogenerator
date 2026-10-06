"""Stage 1 Step 1b: download every linked graph, write one reading prompt per graph, then (after
the reading subagents have answered) validate their answers into `graph_readings.json`."""
import glob
import json
import os
import shutil

from graph_intake.download import NotAnImageError, download_graph_image
from graph_intake.reading_output import GraphReadingError, parse_reading_output
from graph_intake.reading_prompt import build_reading_prompt

GRAPH_INPUTS_DIR = "graph_inputs"
MANIFEST = "manifest.json"
GRAPH_READINGS = "graph_readings.json"
GRAPH_LINKS = "graph_links.json"
SKIPPED_PAGE_LINKS = "skipped_page_links.json"


def reading_prompt_path(out_dir: str, italic_index: int) -> str:
    return os.path.join(out_dir, f"graph_reading_prompt_{italic_index}.txt")


def reading_response_path(out_dir: str, italic_index: int) -> str:
    return os.path.join(out_dir, f"graph_reading_response_{italic_index}.txt")


def _clear_previous_run(out_dir: str) -> None:
    # A stale response file from an earlier script would otherwise be read as this run's answer.
    shutil.rmtree(os.path.join(out_dir, GRAPH_INPUTS_DIR), ignore_errors=True)
    for pattern in ("graph_reading_prompt_*.txt", "graph_reading_response_*.txt", GRAPH_READINGS, SKIPPED_PAGE_LINKS):
        for path in glob.glob(os.path.join(glob.escape(out_dir), pattern)):
            os.remove(path)


_OLD_KEYS = ("bold_index", "bold_text")


def _reject_pre_rename_keys(data, path: str) -> None:
    """Files written before bold_index/bold_text became italic_index/italic_text fail clearly."""
    entries = data.values() if isinstance(data, dict) else data
    if any(isinstance(e, dict) and any(k in e for k in _OLD_KEYS) for e in entries):
        raise ValueError(
            f"{path} was written before the rename of bold_index/bold_text to italic_index/"
            "italic_text — re-run Stage 1 from Step 1a")


def prepare_graph_readings(links: list, out_dir: str = ".") -> list:
    """Download each linked graph and write its reading prompt. A link whose URL is a web page is
    skipped (written to skipped_page_links.json and dropped from graph_links.json). Returns the manifest:
    [{"italic_index", "italic_text", "url", "image_path", "width", "height"}]. With no links it
    writes an empty graph_readings.json at once (there is nothing for a subagent to read)."""
    _reject_pre_rename_keys(links, "graph_links.json")
    _clear_previous_run(out_dir)
    inputs_dir = os.path.join(out_dir, GRAPH_INPUTS_DIR)
    os.makedirs(inputs_dir, exist_ok=True)
    manifest, skipped = [], []
    for link in links:
        try:
            image = download_graph_image(link["url"], link["text"], link["italic_index"], inputs_dir)
        except NotAnImageError:
            # A web page without a #:~:text= highlight is not a graph: skip it, report it (Step 7).
            skipped.append({"italic_index": link["italic_index"], "text": link["text"], "url": link["url"]})
            continue
        entry = {"italic_index": link["italic_index"], "italic_text": link["text"], "url": link["url"], **image}
        with open(reading_prompt_path(out_dir, link["italic_index"]), "w", encoding="utf-8") as f:
            f.write(build_reading_prompt(entry["image_path"], entry["italic_text"]))
        manifest.append(entry)
    with open(os.path.join(inputs_dir, MANIFEST), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    with open(os.path.join(out_dir, SKIPPED_PAGE_LINKS), "w", encoding="utf-8") as f:
        json.dump(skipped, f, indent=2)
    if skipped:
        # load_graph_readings compares readings against graph_links.json; a skipped link has no reading.
        skipped_indexes = {s["italic_index"] for s in skipped}
        with open(os.path.join(out_dir, GRAPH_LINKS), "w", encoding="utf-8") as f:
            json.dump([l for l in links if l["italic_index"] not in skipped_indexes], f, indent=2)
    if not manifest:
        with open(os.path.join(out_dir, GRAPH_READINGS), "w", encoding="utf-8") as f:
            json.dump({}, f)
    return manifest


def collect_graph_readings(out_dir: str = ".") -> dict:
    """Validate every saved reading response and write graph_readings.json:
    {"<italic_index>": {"italic_text", "url", "image_path", "width", "height", "reading"}}."""
    with open(os.path.join(out_dir, GRAPH_INPUTS_DIR, MANIFEST), encoding="utf-8") as f:
        manifest = json.load(f)
    _reject_pre_rename_keys(manifest, os.path.join(out_dir, GRAPH_INPUTS_DIR, MANIFEST))
    readings = {}
    for entry in manifest:
        response_path = reading_response_path(out_dir, entry["italic_index"])
        if not os.path.exists(response_path):
            raise GraphReadingError(
                f"graph reading for {entry['italic_text']!r}: no saved response at {response_path} "
                "— run the reading subagent for it first")
        with open(response_path, encoding="utf-8") as f:
            reading = parse_reading_output(f.read(), entry["italic_text"])
        readings[str(entry["italic_index"])] = {
            key: entry[key] for key in ("italic_text", "url", "image_path", "width", "height")}
        readings[str(entry["italic_index"])]["reading"] = reading
    with open(os.path.join(out_dir, GRAPH_READINGS), "w", encoding="utf-8") as f:
        json.dump(readings, f, indent=2)
    return {int(k): v for k, v in readings.items()}


def load_graph_readings(readings_path: str = GRAPH_READINGS, links_path: str = "graph_links.json") -> dict:
    """graph_readings.json keyed by int italic_index, checked against graph_links.json so a
    reading left over from a different script can never reach the director."""
    with open(readings_path, encoding="utf-8") as f:
        raw_readings = json.load(f)
    with open(links_path, encoding="utf-8") as f:
        raw_links = json.load(f)
    _reject_pre_rename_keys(raw_readings, readings_path)
    _reject_pre_rename_keys(raw_links, links_path)
    readings = {int(k): v for k, v in raw_readings.items()}
    links = {link["italic_index"]: link for link in raw_links}
    stale = sorted(set(readings) ^ set(links)) + sorted(
        i for i in set(readings) & set(links) if readings[i]["url"] != links[i]["url"])
    if stale:
        raise ValueError(
            f"{readings_path} does not match {links_path} (graphic spans {stale}) — it is left over "
            "from another script; re-run Stage 1 from Step 1a")
    return readings
