"""Where a page link's stills live. Shared by Stage 1 (writes them) and Stage 4 (reads them)."""
import os

PAGE_STILLS_DIR = "page_stills"


def still_path(italic_index: int, out_dir: str = "") -> str:
    """The finished frame: passage sharp and highlighted, the rest of the page blurred."""
    return os.path.join(out_dir, PAGE_STILLS_DIR, f"page_{italic_index}.png")


def plain_path_for(still: str) -> str:
    """The blurred page without the highlight, next to a finished frame."""
    root, ext = os.path.splitext(still)
    return f"{root}_plain{ext}"


def plain_still_path(italic_index: int, out_dir: str = "") -> str:
    return plain_path_for(still_path(italic_index, out_dir))
