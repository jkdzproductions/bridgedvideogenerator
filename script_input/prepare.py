"""Stage 1 Step 0: turn the user's script file into `script_marked.txt` (the text every later
Stage 1 step reads) plus `graph_links.json`, `page_links.json`, `image_links.json` and `ignored_links.json`."""
import json
import os
import shutil

from image_intake.paths import IMAGE_STILLS_DIR
from page_intake.paths import PAGE_STILLS_DIR
from script_input.docx_reader import ScriptInput, read_docx_script
from shot_list.markup import parse_markup
from shot_list.segments import segment_script

SCRIPT_MARKED = "script_marked.txt"
GRAPH_LINKS = "graph_links.json"
IGNORED_LINKS = "ignored_links.json"
PAGE_LINKS = "page_links.json"
PAGE_READINGS = "page_readings.json"
IMAGE_LINKS = "image_links.json"
IMAGE_READINGS = "image_readings.json"


_DOCX_MARK_HINT = (
    " — in Word, italicize (graphic) or bold (talking head) the WHOLE word, including a leading "
    "quote, $ or bracket, so the formatting starts where the word starts")


def prepare_script_input(script_path: str, out_dir: str = ".") -> ScriptInput:
    # A failing run must never leave the previous script's files behind for later steps.
    for name in (SCRIPT_MARKED, GRAPH_LINKS, IGNORED_LINKS, PAGE_LINKS, PAGE_READINGS, IMAGE_LINKS, IMAGE_READINGS):
        path = os.path.join(out_dir, name)
        if os.path.exists(path):
            os.remove(path)
    shutil.rmtree(os.path.join(out_dir, PAGE_STILLS_DIR), ignore_errors=True)
    shutil.rmtree(os.path.join(out_dir, IMAGE_STILLS_DIR), ignore_errors=True)
    extension = os.path.splitext(script_path)[1].lower()
    if extension == ".docx":
        result = read_docx_script(script_path)
    elif extension in (".txt", ".md"):
        # Unchanged behaviour for marked-text scripts: the file's text, no links.
        with open(script_path, encoding="utf-8") as f:
            result = ScriptInput(f.read(), [], [])
    else:
        raise ValueError(
            f"unsupported script file {script_path!r}: use a Word .docx, or a .txt/.md with "
            "*...* around graphic moments and **...** around talking-head moments")
    parsed = parse_markup(result.marked_text)  # unbalanced ** fails here, before anything is written
    try:
        # The same check Step 3 makes, run now so a bad marked span fails before any download or model spend.
        segment_script(parsed.plain_text, parsed.graphic_spans, parsed.talking_head_spans)
    except ValueError as e:
        if extension == ".docx":
            raise ValueError(f"{e}{_DOCX_MARK_HINT}") from e
        raise

    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, SCRIPT_MARKED), "w", encoding="utf-8") as f:
        f.write(result.marked_text)
    with open(os.path.join(out_dir, GRAPH_LINKS), "w", encoding="utf-8") as f:
        json.dump(result.links, f, indent=2)
    with open(os.path.join(out_dir, IGNORED_LINKS), "w", encoding="utf-8") as f:
        json.dump(result.ignored_links, f, indent=2)
    with open(os.path.join(out_dir, PAGE_LINKS), "w", encoding="utf-8") as f:
        json.dump(list(result.page_links), f, indent=2)
    with open(os.path.join(out_dir, IMAGE_LINKS), "w", encoding="utf-8") as f:
        json.dump(list(result.image_links), f, indent=2)
    return result
