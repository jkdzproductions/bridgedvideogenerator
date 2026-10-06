"""Where a show-as-is image lives. Shared by Stage 1 (writes it) and Stage 4 (reads it)."""
import glob
import os
from typing import Optional

IMAGE_STILLS_DIR = "image_stills"


def find_image_still(italic_index: int, out_dir: str = "") -> Optional[str]:
    """The saved original for this italic span (its extension depends on the image's real type),
    or None if it is not there."""
    pattern = os.path.join(glob.escape(out_dir), IMAGE_STILLS_DIR, f"image_{italic_index}.*")
    matches = sorted(glob.glob(pattern))
    return matches[0] if matches else None
