# footage/archive_loc.py
"""Library of Congress photo search (loc.gov /photos/). Only items whose rights statement says
"no known restrictions" or "public domain" are kept."""
import re
from typing import Optional

from footage.archive_types import (
    MIN_PHOTO_LONG_SIDE, ArchiveCandidate, ArchiveError, get_json, strip_html, year_from,
)

LOC_PHOTOS_URL = "https://www.loc.gov/photos/"
_FRAGMENT = re.compile(r"#.*$")
_DIMS = re.compile(r"[#&](h|w)=(\d+)")
_YEAR_WORD = re.compile(r"\b(1[0-9]{3}|20[0-9]{2})s?\b")
_IMAGE_EXT = (".jpg", ".jpeg", ".png")
_THUMB_MIN_WIDTH = 400  # the judge needs enough pixels to tell what a photo shows


def _text(value) -> str:
    if isinstance(value, list):
        return " ".join(str(v) for v in value)
    return str(value or "")


_DENY_MARKERS = (
    "not evaluated", "not in the public domain", "not determined", "restricted",
    "restrictions may", "protected", "permission",
)
_ALLOW_STARTS = ("no known restrictions", "public domain")


def _statements(raw) -> list[str]:
    items = raw if isinstance(raw, list) else [raw]
    return [strip_html(str(v)) for v in items if v]


def _is_open(statements: list[str]) -> bool:
    """A start-anchored allow-list plus a deny list. The FIRST statement must begin with an open
    wording (a bare substring match would accept "Not in the public domain"), and no statement
    anywhere may carry a deny marker (so one open line cannot launder a restricted one)."""
    normalized = [" ".join(s.lower().split()) for s in statements]
    if not normalized or not normalized[0].startswith(_ALLOW_STARTS):
        return False
    return not any(marker in n for n in normalized for marker in _DENY_MARKERS)


def _images(raw) -> list[tuple[str, int, int]]:
    """(url without fragment, width, height) for each jpg/png in a result's image_url."""
    urls = raw if isinstance(raw, list) else ([raw] if raw else [])
    out = []
    for url in urls:
        clean = _FRAGMENT.sub("", str(url))
        if not clean.lower().endswith(_IMAGE_EXT):
            continue
        dims = {k: int(v) for k, v in _DIMS.findall(str(url))}
        out.append((clean, dims.get("w", 0), dims.get("h", 0)))
    return out


def parse_loc_photos_response(payload: dict, year_range: Optional[tuple] = None) -> list[ArchiveCandidate]:
    candidates = []
    for r in payload.get("results") or []:
        if not isinstance(r, dict) or r.get("access_restricted"):
            continue
        if "image" not in (r.get("online_format") or []):
            continue
        item = r.get("item") or {}
        statements = _statements(item.get("rights_advisory") or item.get("rights"))
        if not _is_open(statements):
            continue
        rights = " ".join(statements)
        images = _images(r.get("image_url"))
        if not images:
            continue
        best = max(images, key=lambda im: max(im[1], im[2]))
        if max(best[1], best[2]) < MIN_PHOTO_LONG_SIDE:
            continue
        medium = next((im for im in images if im[1] >= _THUMB_MIN_WIDTH), best)
        year = year_from(r.get("date"))
        if year_range and year is not None and not (year_range[0] <= year <= year_range[1]):
            continue
        link = str(r.get("url") or r.get("id") or "")
        item_id = [p for p in str(r.get("id", "")).split("/") if p][-1] if r.get("id") else ""
        if not item_id:
            continue
        contributors = r.get("contributor") or []
        candidates.append(ArchiveCandidate(
            source="loc", item_id=item_id, kind="photo", title=strip_html(_text(r.get("title"))), year=year,
            creator=strip_html(_text(contributors[0] if contributors else "")), rights=rights, page_url=link,
            media_url=best[0], thumbnail_url=medium[0], width=best[1], height=best[2],
        ))
    return candidates


def strip_year_words(query: str) -> str:
    """loc.gov ANDs every query word, so a year/decade word in q returns nothing even with a dates
    filter; the dates parameter already carries the year."""
    return " ".join(_YEAR_WORD.sub(" ", query).split())


def search_loc_photos(query: str, year_range: Optional[tuple] = None, limit: int = 15) -> list[ArchiveCandidate]:
    text = strip_year_words(query)
    if not text:
        raise ArchiveError(f"nothing searchable left in LoC query {query!r} after removing year words")
    params = {"q": text, "fo": "json", "c": limit, "fa": "online-format:image"}
    if year_range:
        params["dates"] = f"{year_range[0]}/{year_range[1]}"
    return parse_loc_photos_response(get_json(LOC_PHOTOS_URL, params), year_range)
