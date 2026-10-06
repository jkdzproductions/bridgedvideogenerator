import pytest

from shot_list.markup import parse_markup


def test_single_asterisk_span_is_a_graphic_span():
    script = "The city grew fast. *Population tripled in a decade.* Then it slowed."
    result = parse_markup(script)

    assert "*" not in result.plain_text
    assert result.plain_text == "The city grew fast. Population tripled in a decade. Then it slowed."
    assert result.talking_head_spans == []
    assert len(result.graphic_spans) == 1
    start, end = result.graphic_spans[0]
    assert result.plain_text[start:end] == "Population tripled in a decade."


def test_double_asterisk_span_is_a_talking_head_span():
    script = "Intro line. **Look straight at the camera now.** Then on."
    result = parse_markup(script)

    assert result.graphic_spans == []
    assert len(result.talking_head_spans) == 1
    start, end = result.talking_head_spans[0]
    assert result.plain_text[start:end] == "Look straight at the camera now."


def test_both_kinds_in_one_script_are_tracked_separately_and_in_order():
    script = "*Tokyo has 37 million people.* It is dense. **Hi, it's me.** Then *Density drives the subway.*"
    result = parse_markup(script)

    text = result.plain_text
    assert [text[s:e] for s, e in result.graphic_spans] == [
        "Tokyo has 37 million people.", "Density drives the subway."]
    assert [text[s:e] for s, e in result.talking_head_spans] == ["Hi, it's me."]


def test_script_with_no_markers_returns_empty_lists():
    script = "This entire script is plain narration with no callouts at all."
    result = parse_markup(script)

    assert result.plain_text == script
    assert result.graphic_spans == []
    assert result.talking_head_spans == []


@pytest.mark.parametrize("script", [
    "An unclosed *graphic marker without a closing one.",
    "An unclosed **talking head marker without a closing one.",
])
def test_unbalanced_markers_raise(script):
    with pytest.raises(ValueError, match="unbalanced markers"):
        parse_markup(script)


@pytest.mark.parametrize("script", [
    "Triple ***nested*** markers.",
    "A *graphic with **talking head** inside* it.",
    "A **talking head with *graphic* inside** it.",
])
def test_overlapping_or_nested_markers_raise(script):
    with pytest.raises(ValueError):
        parse_markup(script)
