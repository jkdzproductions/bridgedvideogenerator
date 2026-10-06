import pytest
from motion_graphics.reviewer_output import ReviewerOutputError, ReviewerVerdict, parse_reviewer_output


def test_parses_approve_verdict():
    raw = '{"verdict": "approve", "reasoning": "matches the spec exactly"}'
    result = parse_reviewer_output(raw)
    assert result == ReviewerVerdict(verdict="approve", reasoning="matches the spec exactly")


def test_parses_correction_verdict_with_instructions():
    raw = (
        '{"verdict": "correction", '
        '"correction_instructions": "make the number larger and centered", '
        '"reasoning": "value is too small to read"}'
    )
    result = parse_reviewer_output(raw)
    assert result.verdict == "correction"
    assert result.correction_instructions == "make the number larger and centered"


def test_parses_reject_verdict():
    raw = '{"verdict": "reject", "reasoning": "wrong archetype entirely, built a chart not a table"}'
    result = parse_reviewer_output(raw)
    assert result.verdict == "reject"
    assert result.correction_instructions is None


def test_strips_json_code_fence():
    raw = '```json\n{"verdict": "approve", "reasoning": "good"}\n```'
    assert parse_reviewer_output(raw).verdict == "approve"


def test_correction_verdict_missing_instructions_raises():
    with pytest.raises(ReviewerOutputError, match="correction_instructions"):
        parse_reviewer_output('{"verdict": "correction", "reasoning": "needs work"}')


def test_correction_verdict_empty_instructions_raises():
    with pytest.raises(ReviewerOutputError, match="correction_instructions"):
        parse_reviewer_output(
            '{"verdict": "correction", "correction_instructions": "  ", "reasoning": "needs work"}'
        )


def test_invalid_verdict_value_raises():
    with pytest.raises(ReviewerOutputError, match="verdict must be one of"):
        parse_reviewer_output('{"verdict": "maybe", "reasoning": "x"}')


def test_missing_reasoning_raises():
    with pytest.raises(ReviewerOutputError, match="reasoning"):
        parse_reviewer_output('{"verdict": "approve"}')


def test_malformed_json_raises():
    with pytest.raises(ReviewerOutputError, match="not valid JSON"):
        parse_reviewer_output("not json")
