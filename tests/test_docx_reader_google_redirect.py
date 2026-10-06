import pytest

from script_input.docx_reader import read_docx_script, unwrap_google_redirect
from tests.docx_builders import add_field_hyperlink, add_hyperlink, add_run, new_document, save

# What Google Docs writes into a downloaded .docx for a link to the page below: the real address
# (with its #:~:text= highlight) sits percent-encoded inside a google.com/url?q=... redirect.
REAL = "https://www.dday-overlord.com/en/d-day/figures?utm_source=chatgpt.com#:~:text=on%20D%2DDay-,156%2C115,-Number%20of%20Allied"
WRAPPED = (
    "http://google.com/url?q=https://www.dday-overlord.com/en/d-day/figures?utm_source%3Dchatgpt.com"
    "%23:~:text%3Don%2520D%252DDay-,156%252C115,-Number%2520of%2520Allied"
    "&sa=D&source=docs&ust=1791163948254200&usg=AOvVaw1RyMpdOuUQTDpYsHL4ocdZ"
)


def test_a_google_redirect_is_unwrapped_to_the_real_address():
    assert unwrap_google_redirect(WRAPPED) == REAL


@pytest.mark.parametrize("url", [
    "https://www.google.com/url?q=https://example.com/a.png&sa=D",
    "http://www.google.com/url?sa=t&q=https://example.com/a.png",
])
def test_both_google_hosts_and_any_parameter_order_are_unwrapped(url):
    assert unwrap_google_redirect(url) == "https://example.com/a.png"


@pytest.mark.parametrize("url", [
    "https://example.com/a.png",
    "https://www.google.com/maps/place/Atlanta",         # a real Google page, not a redirect
    "https://google.com/url?sa=D&source=docs",             # a redirect with no target
    "https://google.com/url?q=mailto:a@b.com",             # target is not http(s)
    "https://notgoogle.com/url?q=https://example.com/x",   # a look-alike host
    "mailto:a@b.com",
])
def test_everything_else_is_left_alone(url):
    assert unwrap_google_redirect(url) == url


def test_an_italic_google_wrapped_highlight_link_becomes_a_page_highlight(tmp_path):
    doc = new_document()
    p = doc.add_paragraph()
    add_run(p, "It took over ")
    add_hyperlink(p, WRAPPED, [("156,000", True)])
    add_run(p, " troops.")

    result = read_docx_script(save(doc, tmp_path))

    assert [(l["text"], l["url"]) for l in result.page_links] == [("156,000", REAL)]
    assert result.links == []


def test_a_field_code_google_wrapped_link_is_unwrapped_too(tmp_path):
    doc = new_document()
    p = doc.add_paragraph()
    add_field_hyperlink(p, WRAPPED, [("156,000", True)])

    result = read_docx_script(save(doc, tmp_path))

    assert [l["url"] for l in result.page_links] == [REAL]
