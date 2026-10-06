# footage/archive_met.py
"""The Metropolitan Museum of Art open-access collection: real historical artwork, public domain only.
The old /v1/search endpoint was retired on 2026-10-01; /v1.1/search returns object IDs, each object is fetched separately."""
import time
from typing import Optional

from footage.archive_loc import strip_year_words
from footage.archive_types import MIN_PHOTO_LONG_SIDE, ArchiveCandidate, ArchiveError, get_json  # noqa: F401

MET_SEARCH_URL = "https://collectionapi.metmuseum.org/public/collection/v1.1/search"
MET_OBJECT_URL = "https://collectionapi.metmuseum.org/public/collection/v1/objects/{id}"

MET_STEP_BUDGET_SECONDS = 45  # one search call stops fetching objects after this long (a degraded API is slow)
MAX_CONSECUTIVE_FAILURES = 2


def _truthy(value) -> bool:
    return value is True or str(value).strip().lower() == "true"


def _year(obj: dict) -> Optional[int]:
    try:
        begin, end = int(obj.get("objectBeginDate") or 0), int(obj.get("objectEndDate") or 0)
    except (TypeError, ValueError):
        return None
    if not begin and not end:
        return None
    return (begin + end) // 2 if begin and end else (begin or end)


def parse_met_object(obj: dict) -> Optional[ArchiveCandidate]:
    if not _truthy(obj.get("isPublicDomain")):
        return None
    image = obj.get("primaryImage")
    title = str(obj.get("title") or "").strip()
    if not image or not title:
        return None
    object_id = obj.get("objectID")
    if object_id is None or str(object_id).strip() == "":
        return None
    return ArchiveCandidate(
        source="met", item_id=str(object_id), kind="photo", title=title, year=_year(obj),
        creator=str(obj.get("artistDisplayName") or ""), rights="Public domain (The Met Open Access)",
        page_url=str(obj.get("objectURL") or ""), media_url=str(image),
        thumbnail_url=str(obj.get("primaryImageSmall") or image), width=0, height=0,
    )


def _overlaps(obj: dict, year_range: Optional[tuple]) -> bool:
    """False only when both dates are known (non-zero) and the span lies wholly outside the requested range."""
    if not year_range:
        return True
    try:
        begin, end = int(obj.get("objectBeginDate") or 0), int(obj.get("objectEndDate") or 0)
    except (TypeError, ValueError):
        return True
    if not begin or not end:
        return True
    return end >= year_range[0] and begin <= year_range[1]


def search_met_artwork(query: str, year_range: Optional[tuple] = None, limit: int = 8) -> list:
    text = strip_year_words(query)
    if not text:
        raise ArchiveError(f"nothing searchable left in Met query {query!r} after removing year words")
    started = time.monotonic()
    params = {"q": text, "hasImages": "true", "isPublicDomain": "true", "limit": limit, "offset": 0}
    if year_range:
        params["dateBegin"], params["dateEnd"] = year_range
    ids = get_json(MET_SEARCH_URL, params).get("objectIDs")
    if not isinstance(ids, list):
        return []
    candidates = []
    fetched = failures = 0
    for object_id in ids[:limit]:
        if object_id is None:
            continue
        if time.monotonic() - started >= MET_STEP_BUDGET_SECONDS:
            print(f"WARNING: Met object fetch budget used up after {fetched} objects")
            break
        fetched += 1
        try:
            obj = get_json(MET_OBJECT_URL.format(id=object_id), {})
        except ArchiveError as e:
            failures += 1
            if failures >= MAX_CONSECUTIVE_FAILURES:
                print(f"WARNING: Met object fetch stopped after {failures} consecutive failures ({e})")
                break
            continue  # one unreadable object must not sink the search
        failures = 0
        if not _overlaps(obj, year_range):
            continue
        candidate = parse_met_object(obj)
        if candidate is not None:
            candidates.append(candidate)
    return candidates
