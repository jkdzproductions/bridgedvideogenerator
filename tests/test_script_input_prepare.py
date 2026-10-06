import json

import pytest

from script_input.prepare import prepare_script_input
from tests.docx_builders import add_hyperlink, add_run, new_document, save

GRAPH = "https://i.redd.it/mvawcfe7ph5e1.jpeg"


def _read(path):
    return path.read_text(encoding="utf-8")


def test_docx_writes_marked_text_links_and_ignored_links(tmp_path):
    doc = new_document()
    p = doc.add_paragraph()
    add_run(p, "Incomes vary. ")
    add_hyperlink(p, GRAPH, [("GDP per capita", True)])
    add_hyperlink(p, "https://example.com", [(" source", False)])
    out = tmp_path / "run"

    prepare_script_input(save(doc, tmp_path), str(out))

    assert _read(out / "script_marked.txt") == "Incomes vary. *GDP per capita* source"
    assert json.loads(_read(out / "graph_links.json")) == [
        {"italic_index": 0, "text": "GDP per capita", "url": GRAPH}]
    assert json.loads(_read(out / "ignored_links.json")) == [
        {"text": " source", "url": "https://example.com"}]


@pytest.mark.parametrize("name", ["script.txt", "script.md"])
def test_marked_text_file_is_copied_unchanged_with_no_links(tmp_path, name):
    script = tmp_path / name
    script.write_text("The city grew. *Population tripled.* Then it slowed.", encoding="utf-8")
    out = tmp_path / "run"

    prepare_script_input(str(script), str(out))

    assert _read(out / "script_marked.txt") == _read(script)
    assert json.loads(_read(out / "graph_links.json")) == []
    assert json.loads(_read(out / "ignored_links.json")) == []


def test_unbalanced_markers_in_a_text_script_fail_before_writing(tmp_path):
    script = tmp_path / "script.txt"
    script.write_text("The city **grew.", encoding="utf-8")
    out = tmp_path / "run"

    with pytest.raises(ValueError, match="unbalanced"):
        prepare_script_input(str(script), str(out))
    assert not (out / "script_marked.txt").exists()


def test_unsupported_extension_raises(tmp_path):
    script = tmp_path / "script.pdf"
    script.write_bytes(b"%PDF-1.4")

    with pytest.raises(ValueError, match=r"unsupported script file.*\*\.\.\.\* around graphic moments and \*\*\.\.\.\*\* around talking-head"):
        prepare_script_input(str(script), str(tmp_path))


def _docx_with_bold_after_punctuation(tmp_path, before, bold, after=""):
    doc = new_document()
    p = doc.add_paragraph()
    add_run(p, "Latin America is uneven. " + before)
    add_hyperlink(p, GRAPH, [(bold, True)])
    add_run(p, after)
    return save(doc, tmp_path)


@pytest.mark.parametrize("before,bold,after", [('The word "', "Mexico", '" matters.'), ("It costs $", "14K", " each.")])
def test_docx_bold_starting_after_punctuation_fails_in_step_1a_with_a_word_hint(
        tmp_path, before, bold, after):
    path = _docx_with_bold_after_punctuation(tmp_path, before, bold, after)
    out = tmp_path / "run"

    with pytest.raises(ValueError, match="italicize \\(graphic\\) or bold \\(talking head\\) the WHOLE word, including a leading quote, \\$ or bracket"):
        prepare_script_input(path, str(out))
    assert not (out / "script_marked.txt").exists()


def test_text_script_bold_after_punctuation_keeps_the_plain_message(tmp_path):
    script = tmp_path / "script.txt"
    script.write_text('The word "*Mexico*" matters.', encoding="utf-8")

    with pytest.raises(ValueError, match="contains no whole word") as info:
        prepare_script_input(str(script), str(tmp_path / "run"))
    assert "in Word" not in str(info.value)


def test_a_failing_run_removes_the_previous_scripts_files(tmp_path):
    out = tmp_path / "run"
    good = new_document()
    p = good.add_paragraph()
    add_run(p, "Incomes vary. ")
    add_hyperlink(p, GRAPH, [("GDP per capita", True)])
    prepare_script_input(save(good, tmp_path, "good.docx"), str(out))
    assert (out / "script_marked.txt").exists()

    bad = tmp_path / "bad.txt"
    bad.write_text("The city **grew.", encoding="utf-8")
    with pytest.raises(ValueError):
        prepare_script_input(str(bad), str(out))

    for name in ("script_marked.txt", "graph_links.json", "ignored_links.json"):
        assert not (out / name).exists()


def test_bold_docx_text_becomes_a_talking_head_span_in_script_marked(tmp_path):
    from tests.docx_builders import add_run, new_document, save

    doc = new_document()
    p = doc.add_paragraph()
    add_run(p, "Intro. ")
    add_run(p, "Hello it's me.", bold=True)
    path = save(doc, tmp_path)
    out = tmp_path / "out"

    result = prepare_script_input(path, str(out))

    assert result.marked_text == "Intro. **Hello it's me.**"
    assert (out / "script_marked.txt").read_text(encoding="utf-8") == "Intro. **Hello it's me.**"


PAGE = "https://example.com/story#:~:text=population%20of%20less%20than%2040"


def test_italic_link_with_a_text_fragment_is_a_page_link(tmp_path):
    doc = new_document()
    p = doc.add_paragraph()
    add_run(p, "Tiny island. ")
    add_hyperlink(p, PAGE, [("less than 40 people", True)])
    add_run(p, " live there.")
    out = tmp_path / "run"

    result = prepare_script_input(save(doc, tmp_path), str(out))

    assert _read(out / "script_marked.txt") == "Tiny island. *less than 40 people* live there."
    assert json.loads(_read(out / "page_links.json")) == [
        {"italic_index": 0, "text": "less than 40 people", "url": PAGE}]
    assert json.loads(_read(out / "graph_links.json")) == []
    assert list(result.page_links) == json.loads(_read(out / "page_links.json"))


def test_graph_and_page_links_share_one_italic_index_space(tmp_path):
    doc = new_document()
    p = doc.add_paragraph()
    add_hyperlink(p, GRAPH, [("GDP per capita", True)])
    add_run(p, " then ")
    add_hyperlink(p, PAGE, [("a news story", True)])
    out = tmp_path / "run"

    prepare_script_input(save(doc, tmp_path), str(out))

    assert [(l["italic_index"], l["url"]) for l in json.loads(_read(out / "graph_links.json"))] == [(0, GRAPH)]
    assert [(l["italic_index"], l["url"]) for l in json.loads(_read(out / "page_links.json"))] == [(1, PAGE)]


def test_text_script_has_no_page_links_and_stale_file_is_removed(tmp_path):
    script = tmp_path / "script.txt"
    script.write_text("The city grew. *Population tripled.*", encoding="utf-8")
    out = tmp_path / "run"
    out.mkdir()
    (out / "page_links.json").write_text('[{"stale": true}]')

    prepare_script_input(str(script), str(out))

    assert json.loads(_read(out / "page_links.json")) == []


def test_a_new_run_removes_the_previous_videos_page_readings_and_stills(tmp_path):
    script = tmp_path / "script.txt"
    script.write_text("The city grew. *Population tripled.*", encoding="utf-8")
    out = tmp_path / "run"
    (out / "page_stills").mkdir(parents=True)
    (out / "page_readings.json").write_text('{"0": {"stale": true}}')
    (out / "page_stills" / "page_0.png").write_bytes(b"stale")

    prepare_script_input(str(script), str(out))

    assert not (out / "page_readings.json").exists()
    assert not (out / "page_stills").exists()


def test_malformed_text_fragment_on_an_italic_link_fails_naming_the_phrase(tmp_path):
    doc = new_document()
    p = doc.add_paragraph()
    add_hyperlink(p, "https://example.com/story#:~:text=a,b,c", [("a news story", True)])

    with pytest.raises(ValueError, match="a news story"):
        prepare_script_input(save(doc, tmp_path), str(tmp_path / "run"))


def test_text_fragment_link_on_non_italic_text_is_ignored_and_reported(tmp_path):
    doc = new_document()
    p = doc.add_paragraph()
    add_run(p, "See ")
    add_hyperlink(p, PAGE, [("the story", False)])
    out = tmp_path / "run"

    prepare_script_input(save(doc, tmp_path), str(out))

    assert json.loads(_read(out / "page_links.json")) == []
    assert json.loads(_read(out / "ignored_links.json")) == [{"text": "the story", "url": PAGE}]
