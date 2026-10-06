# tests/test_archive_artwork.py
import footage.archive_artwork as art
from footage.archive_artwork import ARTWORK_LATEST_YEAR, artwork_ladder, search_artwork
from footage.archive_search import ArchivalSearchError
from footage.archive_types import ArchiveCandidate


def _c(source, item_id):
    return ArchiveCandidate(source, item_id, "photo", f"t{item_id}", 1781, "", "Public domain", "p", "m", "t", 2000, 1500)


def test_search_artwork_uses_only_met_and_loc_through_the_photo_ladder(monkeypatch):
    seen = {}

    def fake_search_photos(era, query, broad, exclude, sources, ladder=None):
        seen.update(era=era, query=query, broad=broad, exclude=exclude,
                    names=[getattr(s, "__name__", "") for s in sources], ladder=ladder)
        return [_c("met", "1")]

    monkeypatch.setattr(art, "search_photos", fake_search_photos)

    assert [c.display_id for c in search_artwork(1781, "q", "b", frozenset({"met:9"}))] == ["met:1"]
    assert seen["era"] == 1781 and seen["exclude"] == frozenset({"met:9"})
    assert seen["names"] == ["search_met_artwork", "search_loc_photos"]
    assert not hasattr(art, "search_commons_artwork")
    assert seen["ladder"] == artwork_ladder(1781, "q", "b")


def test_search_artwork_returns_empty_with_a_warning_instead_of_raising(monkeypatch, capsys):
    def boom(*a, **k): raise ArchivalSearchError("no archival photos found")
    monkeypatch.setattr(art, "search_photos", boom)

    assert search_artwork(1781, "q", "b") == []
    assert "WARNING" in capsys.readouterr().out


def test_artwork_ladder_allows_work_made_later_than_the_event():
    ladder = artwork_ladder(1776, "Declaration 1776", "Philadelphia 1770s")

    assert [r for _, r in ladder] == [(1766, 1836), (1761, 1876), (1751, 1876), (1736, 1926)]
    assert [q for q, _ in ladder] == ["Declaration 1776", "Declaration 1770s", "Philadelphia 1770s", "Philadelphia 1770s"]


def test_artwork_ladder_clamps_the_upper_bound_to_1930():
    assert ARTWORK_LATEST_YEAR == 1930
    assert [r for _, r in artwork_ladder(1899, "q", "b")] == [(1889, 1930), (1884, 1930), (1874, 1930), (1859, 1930)]
