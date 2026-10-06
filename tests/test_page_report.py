from page_intake.report import build_page_highlights_report

READING = {"italic_text": "less than 40 people", "url": "https://example.com/a#:~:text=less",
           "passage": "fewer than 40 people", "title": "Pitcairn, Free Land",
           "still_path": "/run/page_stills/page_1.png", "plain_path": "/run/page_stills/page_1_plain.png",
           "uncovered": []}


def test_report_lists_each_highlight_with_its_still_to_open():
    text = build_page_highlights_report({1: READING}, [])

    assert "Page highlights (1):" in text
    assert "- Italic phrase: 'less than 40 people' (graphic span 1)" in text
    assert "URL: https://example.com/a#:~:text=less" in text
    assert "Passage: fewer than 40 people" in text
    assert "Page title: Pitcairn, Free Land" in text
    assert "Still (open and check it): /run/page_stills/page_1.png" in text
    assert "verify" not in text.lower()
    assert "Page links with no highlight: none." in text


def test_report_flags_overlays_that_could_not_be_cleared():
    text = build_page_highlights_report({1: dict(READING, uncovered=["div#paywall.gate"])}, [])

    assert "Could not clear (check the still): div#paywall.gate" in text


def test_report_lists_skipped_page_links_with_the_recopy_instruction():
    skipped = [{"italic_index": 2, "text": "a news story", "url": "https://example.com/story"}]

    text = build_page_highlights_report({}, skipped)

    assert "Page highlights: none." in text
    assert 'Copy link to highlight' in text
    assert "ordinary graphic from its own text" in text
    assert "- 'a news story' -> https://example.com/story" in text
