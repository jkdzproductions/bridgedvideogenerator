"""A hyperlink edge is a span edge: italic text with a link and italic text without one (or with a
different link) are separate graphic spans."""
import pytest

from script_input.docx_reader import DocxScriptError, read_docx_script
from shot_list.markup import parse_markup
from shot_list.segments import segment_script
from tests.docx_builders import add_hyperlink, add_run, new_document, save

PAGE = "https://example.com/history#:~:text=And%20by%20the%201850s"
GRAPH = "https://i.redd.it/mvawcfe7ph5e1.jpeg"
OTHER = "https://i.redd.it/other.png"
FIRST = "But Atlanta faced inland, a connector."
SECOND = "And by the 1850s, rails converged here,"


def _read(tmp_path, build):
    doc = new_document()
    build(doc.add_paragraph())
    return read_docx_script(save(doc, tmp_path))


def _motivating(italic_space):
    def build(p):
        add_run(p, FIRST, italic=True)
        add_run(p, " ", italic=italic_space)
        add_hyperlink(p, PAGE, [(SECOND, True)])
    return build


@pytest.mark.parametrize("italic_space", [True, False])
def test_unlinked_then_linked_italic_are_two_spans_only_the_second_linked(tmp_path, italic_space):
    result = _read(tmp_path, _motivating(italic_space))

    assert result.marked_text == f"*{FIRST}* *{SECOND}*"
    assert result.page_links == [{"italic_index": 1, "text": SECOND, "url": PAGE}]
    assert result.links == []


def test_linked_italic_first_then_unlinked_italic(tmp_path):
    def build(p):
        add_hyperlink(p, GRAPH, [("GDP rose ", True)])
        add_run(p, "Then it fell.", italic=True)

    result = _read(tmp_path, build)

    assert result.marked_text == "*GDP rose* *Then it fell.*"
    assert result.links == [{"italic_index": 0, "text": "GDP rose", "url": GRAPH}]


def test_unlinked_linked_unlinked_are_three_spans(tmp_path):
    def build(p):
        add_run(p, "Before it. ", italic=True)
        add_hyperlink(p, PAGE, [("The middle bit. ", True)])
        add_run(p, "After it.", italic=True)

    result = _read(tmp_path, build)

    assert result.marked_text == "*Before it.* *The middle bit.* *After it.*"
    assert result.page_links == [{"italic_index": 1, "text": "The middle bit.", "url": PAGE}]


def test_two_different_links_on_adjacent_italic_phrases_are_two_spans(tmp_path):
    def build(p):
        add_hyperlink(p, GRAPH, [("GDP ", True)])
        add_hyperlink(p, OTHER, [("growth", True)])

    result = _read(tmp_path, build)

    assert result.marked_text == "*GDP* *growth*"
    assert result.links == [{"italic_index": 0, "text": "GDP", "url": GRAPH},
                            {"italic_index": 1, "text": "growth", "url": OTHER}]


def test_touching_unlinked_and_linked_italic_raise_naming_the_text(tmp_path):
    def build(p):
        add_run(p, "foo", italic=True)
        add_hyperlink(p, GRAPH, [("bar", True)])

    with pytest.raises(DocxScriptError, match=r"'foo'.*'bar'.*middle of a word.*word boundary"):
        _read(tmp_path, build)


def test_linked_then_touching_unlinked_italic_raise(tmp_path):
    def build(p):
        add_hyperlink(p, GRAPH, [("foo", True)])
        add_run(p, "bar", italic=True)

    with pytest.raises(DocxScriptError, match="middle of a word"):
        _read(tmp_path, build)


def test_fully_linked_and_fully_unlinked_phrases_behave_as_before(tmp_path):
    def build(p):
        add_run(p, "See ")
        add_hyperlink(p, GRAPH, [("GDP per ", True), ("capita", True)])
        add_run(p, " and ")
        add_run(p, "Population ", italic=True)
        add_run(p, "grew", italic=True)

    result = _read(tmp_path, build)

    assert result.marked_text == "See *GDP per capita* and *Population grew*"
    assert result.links == [{"italic_index": 0, "text": "GDP per capita", "url": GRAPH}]


def test_the_two_spans_stay_two_adjacent_graphic_segments(tmp_path):
    result = _read(tmp_path, _motivating(True))
    parsed = parse_markup(result.marked_text)

    segments = segment_script(parsed.plain_text, parsed.graphic_spans, parsed.talking_head_spans)

    assert [s.kind for s in segments] == ["graphic", "graphic"]
    assert [s.text for s in segments] == [FIRST, SECOND]
