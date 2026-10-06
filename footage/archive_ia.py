# footage/archive_ia.py
"""Internet Archive film search. Only two curated collections of old films are searched; the generic
"opensource_movies" collection is mostly unrelated uploads (newspaper scans filed as movies), so it is never
used. A film is kept only when the item's license is public domain."""
import math
import re
from typing import List, Optional
from urllib.parse import quote

from footage.archive_types import MIN_FILM_SECONDS, ArchiveCandidate, ArchiveError, get_json
from shot_list.models import ARCHIVAL_CUTOFF_YEAR

FILM_COLLECTIONS = ("prelinger", "universal_newsreels")
FILM_EARLIEST_YEAR = 1895  # no film before this
_FILM_HALF_WIDTH = 15
_SEARCH_URL = "https://archive.org/advancedsearch.php"
_STOPWORDS = {"the", "and", "for", "with", "from", "that", "this", "into"}
_VIDEO_FORMATS = ("h.264", "MPEG4", "512Kb MPEG4")


def film_year_range(era: int) -> Optional[tuple]:
    low = max(FILM_EARLIEST_YEAR, era - _FILM_HALF_WIDTH)
    high = min(ARCHIVAL_CUTOFF_YEAR - 1, era + _FILM_HALF_WIDTH)
    return (low, high) if low <= high else None


def _terms(query: str) -> List[str]:
    words = re.findall(r"[A-Za-z0-9]+", query)
    keep = [w for w in words if len(w) > 2 and w.lower() not in _STOPWORDS
            and not re.fullmatch(r"\d{4}s?", w)]  # years and decades are matched through the year filter
    return keep[:5]


def build_ia_query(query: str, year_range: tuple) -> str:
    terms = _terms(query)
    if not terms:
        raise ArchiveError(f"film query {query!r} has no searchable words")
    collections = " OR ".join(FILM_COLLECTIONS)
    return (f"({' AND '.join(terms)}) AND collection:({collections}) AND mediatype:movies "
            f"AND year:[{year_range[0]} TO {year_range[1]}]")


def _license_text(doc: dict) -> str:
    value = doc.get("licenseurl")
    return " ".join(value) if isinstance(value, list) else str(value or "")


def parse_ia_search(payload: dict) -> List[dict]:
    docs = (payload.get("response") or {}).get("docs") or []
    return [d for d in docs if "publicdomain" in _license_text(d).lower()]


def _pick_video_file(files: List[dict]) -> Optional[dict]:
    for fmt in _VIDEO_FORMATS:
        for f in files:
            if f.get("format") == fmt and str(f.get("name", "")).lower().endswith(".mp4"):
                return f
    return None


def _dimension(value) -> int:
    """Width/height are informational: a malformed value is 0, never an error."""
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def candidate_from_metadata(doc: dict, metadata: dict) -> Optional[ArchiveCandidate]:
    video = _pick_video_file(metadata.get("files") or [])
    if video is None:
        return None
    try:
        duration = float(video.get("length"))
    except (TypeError, ValueError):
        return None
    if not math.isfinite(duration) or not duration >= MIN_FILM_SECONDS:
        return None
    identifier = doc["identifier"]
    year = doc.get("year")
    creator = doc.get("creator")
    return ArchiveCandidate(
        source="ia", item_id=identifier, kind="film", title=str(doc.get("title", "")),
        year=int(year) if str(year).isdigit() else None,
        creator=" ".join(creator) if isinstance(creator, list) else str(creator or ""),
        rights="Public domain", page_url=f"https://archive.org/details/{identifier}",
        media_url=f"https://archive.org/download/{identifier}/{quote(video['name'])}",
        thumbnail_url=f"https://archive.org/services/img/{identifier}",
        width=_dimension(video.get("width")), height=_dimension(video.get("height")),
        duration_seconds=duration,
    )


def search_ia_film(query: str, era: int, limit: int = 8) -> List[ArchiveCandidate]:
    year_range = film_year_range(era)
    if year_range is None:
        return []
    payload = get_json(_SEARCH_URL, {
        "q": build_ia_query(query, year_range),
        "fl[]": ["identifier", "title", "year", "licenseurl", "creator"],
        "rows": limit, "output": "json",
    })
    films = []
    for doc in parse_ia_search(payload):
        try:
            metadata = get_json(f"https://archive.org/metadata/{doc['identifier']}", {})
        except ArchiveError:
            continue  # one unreadable item must not sink the search
        candidate = candidate_from_metadata(doc, metadata)
        if candidate is not None:
            films.append(candidate)
    return films
