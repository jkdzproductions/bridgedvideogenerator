import json
import os

from footage.archival_review import build_review_html, write_review

PICK = {
    "beat_index": 4, "start": 10.0, "end": 14.0, "era": 1847, "subject": "Atlanta <depot>", "kind": "photo",
    "reasoning": "closest era match",
    "items": [{"source": "loc", "item_id": "1", "display_id": "loc:1", "title": "Depot & yard", "year": 1864,
               "creator": "Barnard", "rights": "No known restrictions on publication.", "page_url": "https://loc.gov/1",
               "local_path": "/tmp/p1.jpg"}],
    "rejected": [{"display_id": "commons:9", "title": "Modern tower", "page_url": "https://c.org/9", "reason": "modern building"}],
}


def test_each_pick_shows_its_image_source_link_year_license_and_the_judges_reason():
    html = build_review_html([PICK])

    assert "file:///tmp/p1.jpg" in html
    assert 'href="https://loc.gov/1"' in html
    assert "1864" in html and "No known restrictions on publication." in html and "Barnard" in html
    assert "closest era match" in html
    assert "10.0" in html and "14.0" in html and "1847" in html


def test_rejected_candidates_are_listed_with_their_reasons():
    html = build_review_html([PICK])

    assert "Modern tower" in html and "modern building" in html and 'href="https://c.org/9"' in html


def test_text_from_archives_is_escaped():
    html = build_review_html([PICK])

    assert "Atlanta &lt;depot&gt;" in html and "Depot &amp; yard" in html
    assert "<depot>" not in html


def test_a_film_pick_links_to_the_film_page_instead_of_embedding_a_local_image():
    film = dict(PICK, kind="film", items=[dict(PICK["items"][0], local_path="", page_url="https://archive.org/details/r",
                                                source="ia", display_id="ia:r", title="Reel")])

    html = build_review_html([film])

    assert 'href="https://archive.org/details/r"' in html and "<img" not in html


def test_no_picks_gives_a_page_that_says_so():
    assert "No archival cuts" in build_review_html([])


def test_write_review_reads_the_picks_file_and_returns_the_absolute_html_path(tmp_path):
    picks = tmp_path / "picks.json"
    picks.write_text(json.dumps([PICK]))
    out = tmp_path / "review.html"

    path = write_review(str(picks), str(out))

    assert path == os.path.abspath(str(out)) and "Depot &amp; yard" in out.read_text()


def test_write_review_without_a_picks_file_writes_the_empty_page(tmp_path):
    out = tmp_path / "review.html"

    write_review(str(tmp_path / "missing.json"), str(out))

    assert "No archival cuts" in out.read_text()


def _with_url(url):
    return dict(PICK, items=[dict(PICK["items"][0], page_url=url)],
                rejected=[dict(PICK["rejected"][0], page_url=url)])


def test_non_http_urls_are_never_rendered_as_links():
    for bad in ("javascript:alert(1)", "data:text/html,<b>x</b>", "  JAVASCRIPT:alert(1)"):
        html = build_review_html([_with_url(bad)])
        assert "href=" not in html
        assert "Depot &amp; yard" in html and "Modern tower" in html


def test_http_and_https_urls_still_become_links():
    assert 'href="http://a.org/x"' in build_review_html([_with_url("http://a.org/x")])
    assert 'href="HTTPS://a.org/x"' in build_review_html([_with_url("HTTPS://a.org/x")])


def test_a_malformed_pick_degrades_and_other_picks_still_appear():
    broken = {"beat_index": 1, "start": None, "items": [{"title": "Lone"}, "junk"], "rejected": [{}]}

    html = build_review_html([broken, PICK])

    assert "Lone" in html and "?s" in html and "unknown" in html
    assert "closest era match" in html and "Depot &amp; yard" in html


def test_local_path_with_a_space_is_percent_encoded_and_relative_paths_get_no_image():
    spaced = dict(PICK, items=[dict(PICK["items"][0], local_path="/tmp/a b#1.jpg")])
    relative = dict(PICK, items=[dict(PICK["items"][0], local_path="rel/p.jpg")])

    assert "file:///tmp/a%20b%231.jpg" in build_review_html([spaced])
    assert "<img" not in build_review_html([relative])


def test_zero_byte_picks_file_gives_the_empty_page(tmp_path):
    picks = tmp_path / "picks.json"
    picks.write_text("")
    out = tmp_path / "review.html"

    write_review(str(picks), str(out))

    assert "No archival cuts" in out.read_text()


def test_missing_year_shows_year_unknown():
    pick = dict(PICK, items=[dict(PICK["items"][0], year=None)])

    assert "year unknown" in build_review_html([pick])


def test_artwork_mixed_and_stock_picks_render_and_show_their_kind():
    art = dict(PICK["items"][0], kind="artwork", title="Battle lithograph")
    photo = dict(PICK["items"][0], kind="photo", title="Camp photo")
    stock = dict(PICK["items"][0], source="pexels", title="Stock clip")
    picks = [dict(PICK, beat_index=1, kind="artwork", items=[art]),
             dict(PICK, beat_index=2, kind="mixed", items=[art, photo]),
             dict(PICK, beat_index=3, kind="stock", items=[stock])]

    html = build_review_html(picks)

    assert "· artwork · era" in html and "· mixed · era" in html and "· stock · era" in html
    assert "<b>artwork</b>" in html and "<b>photo</b>" in html
    assert "Stock clip" in html
