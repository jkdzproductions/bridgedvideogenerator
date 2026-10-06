# footage/archive_artwork.py
"""Artwork candidates for cuts about a period before 1900: Met open access + LoC prints only
(catalogued collections: Wikimedia Commons accepts anyone's uploads, including AI images tagged public domain)."""
from footage.archive_loc import search_loc_photos
from footage.archive_met import search_met_artwork
from footage.archive_search import ArchivalSearchError, decade_form, search_photos
from footage.archive_types import ArchiveCandidate

ARTWORK_LATEST_YEAR = 1930  # artwork may be made after the event, but not after this
_BEFORE = (10, 15, 25, 40)  # years before the era the work may have been made
_AFTER = (60, 100, 100, 150)  # years after the era (a later work depicting the period), clamped to ARTWORK_LATEST_YEAR


def artwork_ladder(era: int, query: str, broad: str) -> list:
    """Like broadening_ladder, but the window is asymmetric: a painting made decades after the event still
    depicts it, so the upper bound reaches far later than the lower bound reaches earlier."""
    queries = [query, decade_form(query, era), broad, broad]
    return [(q, (era - before, min(era + after, ARTWORK_LATEST_YEAR)))
            for q, before, after in zip(queries, _BEFORE, _AFTER)]


def search_artwork(era: int, query: str, broad: str, exclude: frozenset = frozenset()) -> list:
    """Artwork for one cut. Finding none is NOT an error here (stock footage may still be chosen by the judge),
    so a failed or empty search is a printed warning and []."""
    try:
        return search_photos(era, query, broad, exclude, [search_met_artwork, search_loc_photos],
                             ladder=artwork_ladder(era, query, broad))
    except ArchivalSearchError as e:
        print(f"WARNING: no archival artwork found ({e})")
        return []
