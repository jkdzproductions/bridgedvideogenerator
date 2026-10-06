import pytest
from motion_graphics.prompt_writer_output import PromptWriterOutputError, parse_prompt_writer_output


def test_parses_valid_output():
    raw = '{"authoring_prompt": "Create a chart card showing 14M riders per day..."}'
    assert parse_prompt_writer_output(raw) == "Create a chart card showing 14M riders per day..."


def test_strips_json_code_fence():
    raw = '```json\n{"authoring_prompt": "some prompt text"}\n```'
    assert parse_prompt_writer_output(raw) == "some prompt text"


def test_strips_surrounding_whitespace():
    raw = '{"authoring_prompt": "  some prompt text  "}'
    assert parse_prompt_writer_output(raw) == "some prompt text"


def test_malformed_json_raises():
    with pytest.raises(PromptWriterOutputError, match="not valid JSON"):
        parse_prompt_writer_output("not json at all")


def test_missing_authoring_prompt_raises():
    with pytest.raises(PromptWriterOutputError, match="authoring_prompt"):
        parse_prompt_writer_output('{"something_else": "x"}')


def test_empty_authoring_prompt_raises():
    with pytest.raises(PromptWriterOutputError, match="authoring_prompt"):
        parse_prompt_writer_output('{"authoring_prompt": "   "}')


def test_non_object_json_raises():
    with pytest.raises(PromptWriterOutputError, match="JSON object"):
        parse_prompt_writer_output('["a", "b"]')
