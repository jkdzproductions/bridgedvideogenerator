import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

pytest.importorskip("playwright.sync_api")
pytest.importorskip("PIL")

from playwright.sync_api import sync_playwright  # noqa: E402

from page_intake.capture import PageCaptureError, find_passage, load_page  # noqa: E402
from page_intake.fragment import TextFragment  # noqa: E402


@pytest.fixture
def browser():
    with sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as e:  # browser binaries not installed
            pytest.skip(f"Playwright Chromium is not installed: {e}")
        yield b
        b.close()


@pytest.fixture
def page(browser):
    pg = browser.new_page(viewport={"width": 1920, "height": 1080})
    yield pg
    pg.close()


def _html(tmp_path, body, name="page.html"):
    path = tmp_path / name
    path.write_text(f"<html><body style='font-family:Georgia;margin:60px;width:900px'>{body}</body></html>",
                    encoding="utf-8")
    return f"file://{path}"


def test_finds_a_passage_inside_one_element(page, tmp_path):
    url = _html(tmp_path, "<p>Pitcairn is tiny. It has fewer than 40 people. Visit soon.</p>")
    load_page(page, url)

    assert find_passage(page, TextFragment(start="fewer than 40 people")) == "fewer than 40 people"


def test_finds_a_passage_split_across_elements_and_keeps_page_case(page, tmp_path):
    url = _html(tmp_path, "<p>Free land for every <em>Migrant</em> who <b>relocates</b> today.</p>")
    load_page(page, url)

    passage = find_passage(page, TextFragment(start="every migrant", end="relocates"))

    assert passage == "every Migrant who relocates"


def test_text_in_different_blocks_is_joined_by_a_space(page, tmp_path):
    url = _html(tmp_path, "<h1>Pitcairn</h1><p>Free land</p>")
    load_page(page, url)

    assert find_passage(page, TextFragment(start="pitcairn free land")) == "Pitcairn Free land"


def test_prefix_and_suffix_pick_the_right_repeat(page, tmp_path):
    url = _html(tmp_path, "<p>The island is small.</p><p>An island nation offers residency.</p>")
    load_page(page, url)

    passage = find_passage(page, TextFragment(start="island", prefix="an", suffix="nation"))

    assert passage == "island"
    rect = page.evaluate("() => { const r = window.__versedRange.getBoundingClientRect(); return r.top; }")
    first_paragraph_top = page.evaluate("() => document.querySelector('p').getBoundingClientRect().top")
    assert rect > first_paragraph_top + 20  # the highlight is in the second paragraph, not the first


def test_hidden_text_is_not_found(page, tmp_path):
    url = _html(tmp_path, "<p style='display:none'>secret passage</p><p>visible text</p>")
    load_page(page, url)

    with pytest.raises(PageCaptureError, match="not found"):
        find_passage(page, TextFragment(start="secret passage"))


def test_missing_passage_raises(page, tmp_path):
    url = _html(tmp_path, "<p>hello world</p>")
    load_page(page, url)

    with pytest.raises(PageCaptureError, match="not found"):
        find_passage(page, TextFragment(start="goodbye"))


def test_an_ordinary_anchor_in_the_url_still_loads(page, tmp_path):
    url = _html(tmp_path, "<h2 id='intro'>Intro</h2><p>some text here</p>") + "#intro"
    load_page(page, url)

    assert find_passage(page, TextFragment(start="some text")) == "some text"


def test_a_missing_page_raises_a_capture_error(page, tmp_path):
    with pytest.raises(PageCaptureError, match="could not be loaded"):
        load_page(page, f"file://{tmp_path}/nope.html")


@pytest.fixture
def http_status_server():
    status = {"code": 403}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(status["code"])
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html><body>Access denied</body></html>")

        def log_message(self, *args):
            pass

    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def test_http_error_status_is_reported_as_blocked(page, http_status_server):
    with pytest.raises(PageCaptureError, match="HTTP 403"):
        load_page(page, http_status_server + "/story")


def test_text_under_a_hidden_ancestor_is_not_found(page, tmp_path):
    url = _html(tmp_path, "<div style='display:none'><p>secret passage</p></div><p>visible text</p>")
    load_page(page, url)

    with pytest.raises(PageCaptureError, match="not found"):
        find_passage(page, TextFragment(start="secret passage"))


def test_a_hidden_duplicate_does_not_beat_the_visible_occurrence(page, tmp_path):
    url = _html(tmp_path, "<div style='display:none'><p>the quick fox</p></div>"
                          "<p>intro line</p><p>the quick fox</p>")
    load_page(page, url)

    assert find_passage(page, TextFragment(start="the quick fox")) == "the quick fox"
    rect = page.evaluate("() => { const r = window.__versedRange.getBoundingClientRect(); "
                         "return [r.width, r.height]; }")
    assert rect[0] > 0 and rect[1] > 0
    in_last_p = page.evaluate("() => { const ps = document.querySelectorAll('p'); "
                              "return ps[ps.length - 1].contains(window.__versedRange.startContainer); }")
    assert in_last_p


def test_text_under_a_display_contents_wrapper_is_found(page, tmp_path):
    url = _html(tmp_path, "<p><span style='display:contents'>wrapped words here</span></p>")
    load_page(page, url)

    assert find_passage(page, TextFragment(start="wrapped words")) == "wrapped words"


import os
from collections import Counter

from PIL import Image

from page_intake.capture import capture_page

GREEN = (0x30, 0xFE, 0x3E)
STRIPES = ("background-image:repeating-linear-gradient(90deg,#000 0,#000 10px,#fff 10px,#fff 20px);"
           "width:400px;height:200px")


def _pixel_near(img, box, color, tolerance=12):
    left, top, width, height = box
    for x in range(int(left), int(left + width), 3):
        for y in range(int(top), int(top + height), 3):
            if all(abs(a - b) <= tolerance for a, b in zip(img.getpixel((x, y)), color)):
                return True
    return False


def _max_row_jump(img, y, x0, x1):
    luma = [img.convert("L").getpixel((x, y)) for x in range(x0, x1)]
    return max(abs(a - b) for a, b in zip(luma, luma[1:]))


def test_capture_writes_two_stills_with_a_green_highlight_and_blurred_rest(tmp_path):
    url = _html(
        tmp_path,
        "<h1>Pitcairn</h1><p>Pitcairn is tiny. It has fewer than 40 people. Visit soon.</p>"
        f"<div id='stripes' style=\"{STRIPES}\"></div>"
        "<div id='banner' style='position:fixed;bottom:0;left:0;right:0;height:120px;background:#222'>cookies</div>",
    ) + "#:~:text=fewer%20than%2040%20people"
    out = tmp_path / "run"

    result = capture_page(url, str(out), 4)

    assert result["passage"] == "fewer than 40 people"
    assert result["still_path"] == str(out / "page_stills" / "page_4.png")
    assert result["plain_path"] == str(out / "page_stills" / "page_4_plain.png")
    final = Image.open(result["still_path"])
    plain = Image.open(result["plain_path"])
    assert final.size == plain.size == (1920, 1080)
    assert any(_pixel_near(final, rect, GREEN) for rect in result["rects"])  # highlight is painted
    assert not any(_pixel_near(plain, rect, GREEN) for rect in result["rects"])  # plain has none
    # the stripes block is heavily blurred in both stills
    assert _max_row_jump(final, 330, 70, 440) < 60
    assert _max_row_jump(plain, 330, 70, 440) < 60
    assert plain.getpixel((100, 1000))[0] > 200  # the fixed cookie banner (#222) was hidden
    assert result["uncovered"] == []


def test_passage_text_stays_sharp_while_the_rest_of_the_page_is_blurred(tmp_path):
    url = _html(tmp_path, "<p style='font-size:40px'>Alpha beta gamma delta</p>"
                          "<p style='font-size:40px'>Epsilon zeta eta theta</p>") + "#:~:text=alpha%20beta"
    result = capture_page(url, str(tmp_path / "run"), 0)

    final = Image.open(result["still_path"]).convert("L")
    left, top, width, height = result["rects"][0]
    sharp_jump = _max_row_jump(final, int(top + height / 2), int(left), int(left + width))
    second_line_middle = int(top + height + 40 + height / 2)  # p margins are 1em = 40px here
    blurred_jump = _max_row_jump(final, second_line_middle, 60, 500)
    assert sharp_jump > 80 > blurred_jump


def test_passage_inside_a_sticky_wrapper_is_not_hidden(tmp_path):
    url = _html(tmp_path, "<div style='position:sticky;top:0'><article><p>The key sentence is here.</p></article></div>"
                          "<div style='position:fixed;top:0;left:0;right:0;height:50px;background:#c00'>ad</div>"
                ) + "#:~:text=key%20sentence"
    result = capture_page(url, str(tmp_path / "run"), 0)

    assert result["passage"] == "key sentence"
    assert any(_pixel_near(Image.open(result["still_path"]), rect, GREEN) for rect in result["rects"])


def test_an_overlay_that_survives_hiding_is_reported(tmp_path):
    # A transparent full-page layer that is not fixed/sticky and has an innocent name.
    url = _html(tmp_path, "<p>Cover me up please.</p>"
                          "<div style='position:absolute;top:0;left:0;width:1900px;height:1000px'></div>"
                ) + "#:~:text=cover%20me%20up"
    result = capture_page(url, str(tmp_path / "run"), 0)

    assert result["uncovered"] and result["uncovered"][0].startswith("div")


def test_capture_page_missing_passage_raises_and_leaves_no_stills(tmp_path):
    out = tmp_path / "run"
    url = _html(tmp_path, "<p>hello</p>") + "#:~:text=goodbye"

    with pytest.raises(PageCaptureError, match="not found"):
        capture_page(url, str(out), 0)
    assert not (out / "page_stills" / "page_0.png").exists()


def test_capture_page_without_a_highlight_in_the_url_raises(tmp_path):
    url = _html(tmp_path, "<p>hello</p>")

    with pytest.raises(PageCaptureError, match="no #:~:text="):
        capture_page(url, str(tmp_path / "run"), 0)


def test_capture_page_replaces_an_earlier_still_atomically(tmp_path):
    out = tmp_path / "run"
    url = _html(tmp_path, "<p>hello world</p>") + "#:~:text=hello"
    capture_page(url, str(out), 0)
    final = out / "page_stills" / "page_0.png"
    final.write_bytes(b"stale")

    capture_page(url, str(out), 0)

    assert final.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    Image.open(final).verify()
    assert sorted(os.listdir(out / "page_stills")) == ["page_0.png", "page_0_plain.png"]


def test_blur_halo_of_an_adjacent_image_does_not_tint_the_passage(tmp_path):
    # stripes start ~6px under the passage line, so an un-clipped blur halo would wash over it
    url = _html(tmp_path, "<p>Alpha beta gamma delta</p>"
                          f"<div style=\"margin-top:-10px;{STRIPES}\"></div>") + "#:~:text=beta%20gamma"
    result = capture_page(url, str(tmp_path / "run"), 0)

    final = Image.open(result["still_path"]).convert("RGB")
    left, top, width, height = result["rects"][0]
    crop = final.crop((int(left), int(top), int(left + width), int(top + height)))
    dominant = Counter(crop.getdata()).most_common(1)[0][0]  # the highlight background
    assert all(abs(a - b) <= 12 for a, b in zip(dominant, GREEN)), dominant
    assert _max_row_jump(final.convert("L"), int(top + height / 2), int(left), int(left + width)) > 80


def _all_rects_inside_the_frame(rects):
    return all(r[0] >= -2 and r[1] >= -2 and r[0] + r[2] <= 1922 and r[1] + r[3] <= 1082 for r in rects)


def test_a_passage_taller_than_the_frame_fails_instead_of_being_truncated(tmp_path):
    paragraphs = "".join(f"<p style='height:200px'>Paragraph {i} filler text.</p>" for i in range(1, 9))
    url = _html(tmp_path, f"<p>First marker begins here.</p>{paragraphs}<p>The last marker ends here.</p>"
                ) + "#:~:text=first%20marker,last%20marker"

    with pytest.raises(PageCaptureError, match="taller than the 1920x1080 frame"):
        capture_page(url, str(tmp_path / "run"), 0)


def test_a_multi_paragraph_passage_that_fits_is_fully_visible_and_highlighted(tmp_path):
    url = _html(tmp_path, "<div style='height:3000px'>spacer</div>"
                          "<p>First marker begins here.</p><p>Middle paragraph text.</p>"
                          "<p>The last marker ends here.</p><div style='height:3000px'>more</div>"
                ) + "#:~:text=first%20marker,last%20marker"
    result = capture_page(url, str(tmp_path / "run"), 0)

    final = Image.open(result["still_path"])
    assert _all_rects_inside_the_frame(result["rects"])
    assert len(result["rects"]) >= 3
    assert all(_pixel_near(final, rect, GREEN) for rect in result["rects"])


def test_a_passage_in_a_tall_container_is_scrolled_by_the_passage_not_the_container(tmp_path):
    url = _html(tmp_path, "<div style='height:2000px'>spacer</div>"
                          "<div style='height:3000px'>Alpha line<br>Beta line<br>Gamma line</div>"
                ) + "#:~:text=alpha%20line,gamma%20line"
    result = capture_page(url, str(tmp_path / "run"), 0)

    final = Image.open(result["still_path"])
    assert _all_rects_inside_the_frame(result["rects"])
    assert all(_pixel_near(final, rect, GREEN) for rect in result["rects"])


def test_a_background_image_behind_the_passage_is_reported(tmp_path):
    png = ("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
    url = _html(tmp_path, f"<header class='hero' style=\"background-image:url({png});padding:40px\">"
                          "<h1>Headline over a photo</h1></header>") + "#:~:text=headline%20over"
    result = capture_page(url, str(tmp_path / "run"), 0)

    assert result["uncovered"] == ["background image behind the passage (not blurred): header.hero"]
