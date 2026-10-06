import pytest

from script_input.docx_reader import DocxScriptError, read_docx_script
from shot_list.markup import parse_markup
from tests.docx_builders import (
    add_field_hyperlink,
    add_hyperlink,
    add_run,
    bold_character_style,
    italic_character_style,
    new_document,
    save,
)

GRAPH = "https://i.redd.it/mvawcfe7ph5e1.jpeg"


def _graphic_texts(marked_text):
    parsed = parse_markup(marked_text)
    return [parsed.plain_text[s:e] for s, e in parsed.graphic_spans]


def test_plain_and_italic_paragraphs_become_marked_text(tmp_path):
    doc = new_document()
    p = doc.add_paragraph()
    add_run(p, "The city grew fast. ")
    add_run(p, "Population tripled in a decade.", italic=True)
    doc.add_paragraph("Then it slowed.")

    result = read_docx_script(save(doc, tmp_path))

    assert result.marked_text == (
        "The city grew fast. *Population tripled in a decade.*\nThen it slowed."
    )
    assert result.links == []
    assert result.ignored_links == []


def test_italic_hyperlink_is_a_linked_italic_span(tmp_path):
    doc = new_document()
    p = doc.add_paragraph()
    add_run(p, "Latin America is uneven. ")
    add_hyperlink(p, GRAPH, [("GDP per capita ranges widely", True)])
    add_run(p, " across the region.")

    result = read_docx_script(save(doc, tmp_path))

    assert result.marked_text == (
        "Latin America is uneven. *GDP per capita ranges widely* across the region."
    )
    assert result.links == [{"italic_index": 0, "text": "GDP per capita ranges widely", "url": GRAPH}]


def test_italic_index_counts_every_graphic_span_linked_or_not(tmp_path):
    doc = new_document()
    p = doc.add_paragraph()
    add_run(p, "First ", italic=True)
    add_run(p, "then ")
    add_hyperlink(p, GRAPH, [("second", True)])

    result = read_docx_script(save(doc, tmp_path))

    assert _graphic_texts(result.marked_text) == ["First", "second"]
    assert result.links == [{"italic_index": 1, "text": "second", "url": GRAPH}]


def test_link_covering_only_part_of_an_italic_phrase_splits_it_at_the_link_edge(tmp_path):
    doc = new_document()
    p = doc.add_paragraph()
    add_run(p, "Incomes: ")
    add_run(p, "GDP per capita ", italic=True)
    add_hyperlink(p, GRAPH, [("in 2024", True)])
    add_run(p, " varied.")

    result = read_docx_script(save(doc, tmp_path))

    assert result.marked_text == "Incomes: *GDP per capita* *in 2024* varied."
    assert result.links == [{"italic_index": 1, "text": "in 2024", "url": GRAPH}]


def test_link_on_plain_text_is_ignored_but_reported(tmp_path):
    doc = new_document()
    p = doc.add_paragraph()
    add_run(p, "See ")
    add_hyperlink(p, "https://example.com/article", [("this article", False)])
    add_run(p, " for more.")

    result = read_docx_script(save(doc, tmp_path))

    assert result.marked_text == "See this article for more."
    assert result.links == []
    assert result.ignored_links == [{"text": "this article", "url": "https://example.com/article"}]


def test_plain_linked_run_never_joins_the_italic_span_next_to_it(tmp_path):
    doc = new_document()
    p = doc.add_paragraph()
    add_hyperlink(p, GRAPH, [("GDP per capita", True), (" in Latin America", False)])

    result = read_docx_script(save(doc, tmp_path))

    assert result.marked_text == "*GDP per capita* in Latin America"
    assert result.links == [{"italic_index": 0, "text": "GDP per capita", "url": GRAPH}]
    assert result.ignored_links == [{"text": " in Latin America", "url": GRAPH}]


def test_adjacent_italic_runs_merge_into_one_span(tmp_path):
    doc = new_document()
    p = doc.add_paragraph()
    add_run(p, "Population ", italic=True)
    add_run(p, "tripled", italic=True)
    add_run(p, " fast.")

    result = read_docx_script(save(doc, tmp_path))

    assert result.marked_text == "*Population tripled* fast."


def test_adjacent_italic_runs_with_different_links_split_at_the_space(tmp_path):
    other = "https://i.redd.it/other.png"
    doc = new_document()
    p = doc.add_paragraph()
    add_hyperlink(p, GRAPH, [("Guyana leads ", True)])
    add_hyperlink(p, other, [("Haiti trails", True)])

    result = read_docx_script(save(doc, tmp_path))

    assert result.marked_text == "*Guyana leads* *Haiti trails*"
    assert result.links == [
        {"italic_index": 0, "text": "Guyana leads", "url": GRAPH},
        {"italic_index": 1, "text": "Haiti trails", "url": other},
    ]


def test_two_links_touching_inside_one_italic_word_raise(tmp_path):
    doc = new_document()
    p = doc.add_paragraph()
    add_hyperlink(p, GRAPH, [("GDP", True)])
    add_hyperlink(p, "https://i.redd.it/other.png", [("growth", True)])

    with pytest.raises(DocxScriptError, match="GDP.*growth.*middle of a word"):
        read_docx_script(save(doc, tmp_path))


def test_literal_double_asterisk_raises(tmp_path):
    doc = new_document()
    doc.add_paragraph("Footnote **marker here.")

    with pytest.raises(DocxScriptError, match=r"literal '\*'.*Footnote"):
        read_docx_script(save(doc, tmp_path))


def test_single_asterisk_next_to_italic_raises_instead_of_shifting_the_span(tmp_path):
    doc = new_document()
    p = doc.add_paragraph()
    add_run(p, "Rate*")
    add_run(p, "rose", italic=True)

    with pytest.raises(DocxScriptError, match="literal '\\*'"):
        read_docx_script(save(doc, tmp_path))


def test_mailto_link_on_italic_raises(tmp_path):
    doc = new_document()
    p = doc.add_paragraph()
    add_hyperlink(p, "mailto:josh@example.com", [("Email me", True)])

    with pytest.raises(DocxScriptError, match="'Email me'.*mailto:josh@example.com"):
        read_docx_script(save(doc, tmp_path))


def test_empty_document_raises(tmp_path):
    doc = new_document()
    doc.add_paragraph("   ")

    with pytest.raises(DocxScriptError, match="contains no text"):
        read_docx_script(save(doc, tmp_path))


def test_not_a_docx_raises(tmp_path):
    path = tmp_path / "script.docx"
    path.write_text("plain text pretending to be Word")

    with pytest.raises(DocxScriptError, match="could not open"):
        read_docx_script(str(path))


# --- Review Focus pins ---------------------------------------------------------------------


def test_italic_from_a_character_style_counts_as_italic(tmp_path):
    doc = new_document()
    style = italic_character_style(doc)
    p = doc.add_paragraph()
    add_run(p, "Output ")
    add_run(p, "doubled by 2020", style=style)

    result = read_docx_script(save(doc, tmp_path))

    assert result.marked_text == "Output *doubled by 2020*"


def test_direct_not_italic_overrides_an_italic_character_style(tmp_path):
    doc = new_document()
    style = italic_character_style(doc)
    p = doc.add_paragraph()
    run = add_run(p, "not italic", style=style)
    run.italic = False

    result = read_docx_script(save(doc, tmp_path))

    assert result.marked_text == "not italic"


def test_hyperlink_field_code_split_across_runs_is_read(tmp_path):
    doc = new_document()
    p = doc.add_paragraph()
    add_run(p, "Look: ")
    add_field_hyperlink(p, GRAPH, [("GDP per ", True), ("capita", True)])
    add_run(p, " varies.")

    result = read_docx_script(save(doc, tmp_path))

    assert result.marked_text == "Look: *GDP per capita* varies."
    assert result.links == [{"italic_index": 0, "text": "GDP per capita", "url": GRAPH}]


def test_hyperlink_split_into_two_elements_with_the_same_url_is_one_span(tmp_path):
    doc = new_document()
    p = doc.add_paragraph()
    add_hyperlink(p, GRAPH, [("GDP per ", True)])
    add_hyperlink(p, GRAPH, [("capita", True)])

    result = read_docx_script(save(doc, tmp_path))

    assert result.marked_text == "*GDP per capita*"
    assert result.links == [{"italic_index": 0, "text": "GDP per capita", "url": GRAPH}]


def test_non_breaking_and_zero_width_spaces_become_normal_word_breaks(tmp_path):
    doc = new_document()
    p = doc.add_paragraph()
    add_run(p, "It reached ")
    add_run(p, "$29K per person​", italic=True)

    result = read_docx_script(save(doc, tmp_path))

    assert result.marked_text == "It reached *$29K per person*"
    assert parse_markup(result.marked_text).plain_text.split() == [
        "It", "reached", "$29K", "per", "person"]


def test_whitespace_only_italic_is_not_a_span(tmp_path):
    doc = new_document()
    p = doc.add_paragraph()
    add_run(p, "Two")
    add_run(p, " ", italic=True)
    add_run(p, "words.")

    result = read_docx_script(save(doc, tmp_path))

    assert result.marked_text == "Two words."
    assert parse_markup(result.marked_text).graphic_spans == []


def test_link_query_string_is_kept_verbatim(tmp_path):
    url = "https://preview.redd.it/x.jpeg?width=1080&format=pjpg&s=abc"
    doc = new_document()
    p = doc.add_paragraph()
    add_hyperlink(p, url, [("the chart", True)])

    result = read_docx_script(save(doc, tmp_path))

    assert result.links == [{"italic_index": 0, "text": "the chart", "url": url}]


def test_table_in_the_document_raises(tmp_path):
    doc = new_document()
    doc.add_paragraph("Intro.")
    doc.add_table(rows=1, cols=1).cell(0, 0).text = "Script inside a table"

    with pytest.raises(DocxScriptError, match="contains a table.*Script inside a table"):
        read_docx_script(save(doc, tmp_path))


def test_bold_becomes_a_talking_head_span(tmp_path):
    doc = new_document()
    p = doc.add_paragraph()
    add_run(p, "Intro. ")
    add_run(p, "Hi, it's me talking.", bold=True)
    add_run(p, " Then on.")

    result = read_docx_script(save(doc, tmp_path))

    assert result.marked_text == "Intro. **Hi, it's me talking.** Then on."
    assert result.links == []
    assert result.ignored_links == []


def test_italic_and_bold_in_one_paragraph_give_both_span_kinds(tmp_path):
    doc = new_document()
    p = doc.add_paragraph()
    add_run(p, "Graph line.", italic=True)
    add_run(p, " Middle. ")
    add_run(p, "Talk line.", bold=True)

    result = read_docx_script(save(doc, tmp_path))
    parsed = parse_markup(result.marked_text)

    assert [parsed.plain_text[s:e] for s, e in parsed.graphic_spans] == ["Graph line."]
    assert [parsed.plain_text[s:e] for s, e in parsed.talking_head_spans] == ["Talk line."]


def test_bold_hyperlink_is_ignored_and_reported_not_a_graph(tmp_path):
    doc = new_document()
    p = doc.add_paragraph()
    add_run(p, "Intro ")
    add_hyperlink(p, GRAPH, [("not a graph", False, True)])

    result = read_docx_script(save(doc, tmp_path))

    assert result.marked_text == "Intro **not a graph**"
    assert result.links == []
    assert result.ignored_links == [{"text": "not a graph", "url": GRAPH}]


def test_text_that_is_both_bold_and_italic_raises_naming_the_text(tmp_path):
    doc = new_document()
    p = doc.add_paragraph()
    add_run(p, "Plain start. ")
    run = add_run(p, "Ambiguous phrase", bold=True, italic=True)

    with pytest.raises(DocxScriptError, match="Ambiguous phrase.*both bold and italic"):
        read_docx_script(save(doc, tmp_path))


def test_bold_from_a_character_style_is_a_talking_head(tmp_path):
    doc = new_document()
    style = bold_character_style(doc)
    p = doc.add_paragraph()
    add_run(p, "Intro. ")
    add_run(p, "Styled bold.", style=style)

    result = read_docx_script(save(doc, tmp_path))

    assert result.marked_text == "Intro. **Styled bold.**"


def test_explicit_not_italic_overrides_an_italic_character_style(tmp_path):
    doc = new_document()
    style = italic_character_style(doc)
    p = doc.add_paragraph()
    run = add_run(p, "Not really italic.", style=style)
    run.italic = False

    result = read_docx_script(save(doc, tmp_path))

    assert result.marked_text == "Not really italic."


def test_italic_heading_paragraph_style_does_not_count(tmp_path):
    doc = new_document()
    heading = doc.add_paragraph("Big title", style="Heading 1")
    heading.style.font.italic = True
    doc.add_paragraph("Body text.")

    result = read_docx_script(save(doc, tmp_path))

    assert result.marked_text == "Big title\nBody text."


def test_italic_touching_bold_with_no_space_raises(tmp_path):
    doc = new_document()
    p = doc.add_paragraph()
    add_run(p, "word", italic=True)
    add_run(p, "glued", bold=True)

    with pytest.raises(DocxScriptError):
        read_docx_script(save(doc, tmp_path))


def test_literal_single_asterisk_raises(tmp_path):
    doc = new_document()
    doc.add_paragraph("A footnote marker* in the text.")

    with pytest.raises(DocxScriptError, match="literal '\\*'"):
        read_docx_script(save(doc, tmp_path))


def test_lone_italic_punctuation_stays_plain(tmp_path):
    doc = new_document()
    p = doc.add_paragraph()
    add_run(p, "early on")
    add_run(p, ",", italic=True)
    add_run(p, " then more.")

    result = read_docx_script(save(doc, tmp_path))

    assert result.marked_text == "early on, then more."
    assert "*" not in result.marked_text


def test_lone_bold_punctuation_stays_plain(tmp_path):
    doc = new_document()
    p = doc.add_paragraph()
    add_run(p, "the end")
    add_run(p, ".", bold=True)

    result = read_docx_script(save(doc, tmp_path))

    assert result.marked_text == "the end."


def test_italic_phrase_with_digits_or_letters_is_still_a_graphic_span(tmp_path):
    doc = new_document()
    p = doc.add_paragraph()
    add_run(p, "Costs ")
    add_run(p, "$14K", italic=True)
    add_run(p, " a year.")

    result = read_docx_script(save(doc, tmp_path))

    assert _graphic_texts(result.marked_text) == ["$14K"]
