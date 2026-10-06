# footage/archive_search.py
"""Find archival film (one search) or photos (a broadening ladder) for one pre-1960 cut."""
import re
from typing import Callable, Optional

from footage.archive_commons import search_commons_photos
from footage.archive_ia import search_ia_film
from footage.archive_loc import search_loc_photos
from footage.archive_types import MIN_PHOTO_LONG_SIDE, ArchiveCandidate, ArchiveError

PHOTO_TARGET = 6  # stop broadening once this many usable photos were found
PHOTO_MAX_CANDIDATES = 12  # what the judge gets to look at
LADDER_HALF_WIDTHS = (10, 15, 25, 40)  # years either side of the era, widening each step
_YEAR = re.compile(r"\b(1[0-9]{3}|20[0-9]{2})(s?)\b")  # a year ("1847") or a decade ("1840s")


class ArchivalSearchError(Exception):
    pass


def decade_form(query: str, era: int) -> str:
    """The query with each exact year turned into its decade ("1847" -> "1840s"; a decade already in the
    query is left alone); if it names no year or decade, the era's decade is appended."""
    replaced, count = _YEAR.subn(lambda m: m.group(0) if m.group(2) else f"{int(m.group(1)) // 10 * 10}s", query)
    return replaced if count else f"{query} {era // 10 * 10}s"


def broadening_ladder(era: int, query: str, broad: str) -> list[tuple[str, tuple[int, int]]]:
    half = LADDER_HALF_WIDTHS
    return [
        (query, (era - half[0], era + half[0])),
        (decade_form(query, era), (era - half[1], era + half[1])),
        (broad, (era - half[2], era + half[2])),
        (broad, (era - half[3], era + half[3])),
    ]


def search_film(query: str, era: int, exclude: frozenset = frozenset()) -> list[ArchiveCandidate]:
    """One film search on the specific query. A failing archive means "no film", which falls to photos."""
    try:
        films = search_ia_film(query, era)
    except ArchiveError as e:
        print(f"WARNING: archival film search failed ({e}); falling back to photos")
        return []
    return [f for f in films if f.display_id not in exclude]


def search_photos(
    era: int, query: str, broad: str, exclude: frozenset = frozenset(),
    sources: Optional[list[Callable]] = None, ladder: Optional[list] = None,
) -> list[ArchiveCandidate]:
    sources = sources if sources is not None else [search_loc_photos, search_commons_photos]
    ladder = ladder if ladder is not None else broadening_ladder(era, query, broad)
    found: dict[str, ArchiveCandidate] = {}
    errors: list[str] = []
    tried: list[str] = []
    for step_query, year_range in ladder:
        tried.append(f"{step_query!r} {year_range[0]}-{year_range[1]}")
        per_source: list[list[ArchiveCandidate]] = []
        for source in sources:
            try:
                results = source(step_query, year_range)
            except ArchiveError as e:
                print(f"WARNING: archival photo source failed for {step_query!r}: {e}")
                errors.append(str(e))
                continue
            per_source.append([c for c in results
                               if c.display_id not in exclude
                               and ((not c.width and not c.height) or max(c.width, c.height) >= MIN_PHOTO_LONG_SIDE)])
        # Round-robin across the sources, so one source's long result list cannot fill the cap.
        for rank in range(max((len(r) for r in per_source), default=0)):
            for results in per_source:
                if rank < len(results) and results[rank].display_id not in found:
                    found[results[rank].display_id] = results[rank]
        if len(found) >= PHOTO_TARGET:
            break
    if not found:
        detail = f"; errors: {'; '.join(errors)}" if errors else ""
        raise ArchivalSearchError(
            f"no archival photos found for era {era} after trying {', '.join(tried)}{detail}")
    return list(found.values())[:PHOTO_MAX_CANDIDATES]
