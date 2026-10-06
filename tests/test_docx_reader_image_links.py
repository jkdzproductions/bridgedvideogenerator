import pytest

from script_input.docx_reader import DocxScriptError, is_image_url, read_docx_script
from tests.docx_builders import add_field_hyperlink, add_hyperlink, add_run, new_document, save

IMG = "https://example.com/maps/atlanta.jpg"


def _read(tmp_path, build):
    doc = new_document()
    build(doc.add_paragraph())
    return read_docx_script(save(doc, tmp_path))


@pytest.mark.parametrize("url", [
    "https://example.com/a.png", "http://example.com/a.JPG?width=640&s=1", "https://e.com/a.jpeg",
    "https://e.com/a.gif#x", "https://e.com/path/a.WEBP"])
def test_is_image_url_accepts_image_files(url):
    assert is_image_url(url)


@pytest.mark.parametrize("url", [
    "https://e.com/story", "https://e.com/a.html", "ftp://e.com/a.png", "https://e.com/a.pdf",
    "mailto:a@b.com", "https://e.com/png"])
def test_is_image_url_rejects_everything_else(url):
    assert not is_image_url(url)


def test_a_non_italic_image_link_becomes_a_marked_span_and_an_image_link(tmp_path):
    def build(p):
        add_run(p, "Before. ")
        add_hyperlink(p, IMG, [("a stake in the ground", False)])
        add_run(p, " after.")

    result = _read(tmp_path, build)

    assert result.marked_text == "Before. *a stake in the ground* after."
    assert list(result.image_links) == [{"italic_index": 0, "text": "a stake in the ground", "url": IMG}]
    assert result.links == [] and list(result.page_links) == [] and result.ignored_links == []


def test_image_links_share_one_italic_index_space_with_graph_links(tmp_path):
    def build(p):
        add_run(p, "One ")
        add_hyperlink(p, "https://x.com/c.png", [("chart", True)])
        add_run(p, " two ")
        add_hyperlink(p, IMG, [("the map", False)])

    result = _read(tmp_path, build)

    assert [(l["italic_index"], l["text"]) for l in result.links] == [(0, "chart")]
    assert [(l["italic_index"], l["text"]) for l in result.image_links] == [(1, "the map")]


def test_a_field_code_hyperlink_is_read_the_same_way(tmp_path):
    def build(p):
        add_run(p, "See ")
        add_field_hyperlink(p, IMG, [("the map", False)])
        add_run(p, " now.")

    result = _read(tmp_path, build)

    assert result.marked_text == "See *the map* now."
    assert [l["url"] for l in result.image_links] == [IMG]


def test_a_link_to_a_web_page_stays_ignored(tmp_path):
    def build(p):
        add_run(p, "Read ")
        add_hyperlink(p, "https://example.com/story", [("this story", False)])

    result = _read(tmp_path, build)

    assert result.marked_text == "Read this story"
    assert list(result.image_links) == []
    assert result.ignored_links == [{"text": "this story", "url": "https://example.com/story"}]


def test_a_bold_image_link_stays_a_talking_head_and_is_ignored(tmp_path):
    def build(p):
        add_run(p, "Now ")
        add_hyperlink(p, IMG, [("a big claim", False, True)])

    result = _read(tmp_path, build)

    assert result.marked_text == "Now **a big claim**"
    assert list(result.image_links) == []
    assert result.ignored_links == [{"text": "a big claim", "url": IMG}]


def test_an_image_link_on_whitespace_only_is_ignored_and_reported(tmp_path):
    def build(p):
        add_run(p, "Word")
        add_hyperlink(p, IMG, [(" ", False)])
        add_run(p, "more")

    result = _read(tmp_path, build)

    assert result.marked_text == "Word more"
    assert list(result.image_links) == []
    assert result.ignored_links == [{"text": " ", "url": IMG}]


def test_one_phrase_split_over_two_link_elements_with_the_same_url_is_one_span(tmp_path):
    def build(p):
        add_run(p, "Look at ")
        add_hyperlink(p, IMG, [("a ", False)])
        add_hyperlink(p, IMG, [("small map", False)])

    result = _read(tmp_path, build)

    assert result.marked_text == "Look at *a small map*"
    assert [l["text"] for l in result.image_links] == ["a small map"]


def test_the_trailing_space_a_link_swallows_stays_outside_the_markers(tmp_path):
    def build(p):
        add_run(p, "See ")
        add_hyperlink(p, IMG, [("the map ", False)])
        add_run(p, "now.")

    result = _read(tmp_path, build)

    assert result.marked_text == "See *the map* now."
    assert result.image_links[0]["text"] == "the map"


def test_an_image_phrase_touching_an_italic_phrase_is_refused_by_name(tmp_path):
    def build(p):
        add_run(p, "alpha", italic=True)
        add_hyperlink(p, IMG, [("beta", False)])

    with pytest.raises(DocxScriptError, match="beta"):
        _read(tmp_path, build)


def test_an_image_phrase_touching_a_bold_phrase_is_refused_by_name(tmp_path):
    def build(p):
        add_hyperlink(p, IMG, [("beta", False)])
        add_run(p, "gamma", bold=True)

    with pytest.raises(DocxScriptError, match="beta"):
        _read(tmp_path, build)


def test_an_image_phrase_separated_from_an_italic_phrase_by_a_space_is_fine(tmp_path):
    def build(p):
        add_run(p, "alpha", italic=True)
        add_run(p, " ")
        add_hyperlink(p, IMG, [("beta", False)])

    result = _read(tmp_path, build)

    assert result.marked_text == "*alpha* *beta*"
    assert [l["italic_index"] for l in result.image_links] == [1]


def test_a_non_italic_tail_of_an_italic_image_link_is_ignored_not_a_second_image(tmp_path):
    graph = "https://i.redd.it/graph.png"

    def build(p):
        add_hyperlink(p, graph, [("GDP per capita", True), (" in Latin America", False)])

    result = _read(tmp_path, build)

    assert result.marked_text == "*GDP per capita* in Latin America"
    assert result.links == [{"italic_index": 0, "text": "GDP per capita", "url": graph}]
    assert list(result.image_links) == []
    assert result.ignored_links == [{"text": " in Latin America", "url": graph}]


def test_a_possessive_tail_after_an_italic_link_does_not_touch_an_image_phrase(tmp_path):
    graph = "https://i.redd.it/graph.png"

    def build(p):
        add_hyperlink(p, graph, [("Mexico", True), ("'s GDP", False)])

    result = _read(tmp_path, build)

    assert result.marked_text == "*Mexico*'s GDP"
    assert list(result.image_links) == []
    assert result.ignored_links == [{"text": "'s GDP", "url": graph}]


def test_a_non_italic_head_before_an_italic_part_of_one_link_is_ignored(tmp_path):
    graph = "https://i.redd.it/graph.png"

    def build(p):
        add_hyperlink(p, graph, [("Rising ", False), ("GDP per capita", True)])

    result = _read(tmp_path, build)

    assert result.marked_text == "Rising *GDP per capita*"
    assert list(result.image_links) == []
    assert result.ignored_links == [{"text": "Rising ", "url": graph}]


def test_an_image_link_with_a_different_url_next_to_an_italic_link_is_still_an_image(tmp_path):
    graph = "https://i.redd.it/graph.png"

    def build(p):
        add_hyperlink(p, graph, [("the chart", True)])
        add_run(p, " ")
        add_hyperlink(p, IMG, [("the map", False)])

    result = _read(tmp_path, build)

    assert result.marked_text == "*the chart* *the map*"
    assert [(l["italic_index"], l["text"], l["url"]) for l in result.image_links] == [(1, "the map", IMG)]
    assert result.ignored_links == []


def test_a_malformed_url_on_non_italic_text_is_ignored_and_reported(tmp_path):
    bad = "http://[bad/x"

    def build(p):
        add_hyperlink(p, bad, [("odd link", False)])

    result = _read(tmp_path, build)

    assert is_image_url(bad) is False
    assert list(result.image_links) == []
    assert result.ignored_links == [{"text": "odd link", "url": bad}]
