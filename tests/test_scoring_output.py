import pytest
from footage.scoring_output import (
    NoAcceptableCandidateError,
    ScoringOutputError,
    parse_scoring_output,
)


def test_parses_valid_output():
    assert parse_scoring_output('{"winner_index": 2, "reasoning": "best match"}', num_candidates=5) == 2


def test_strips_json_code_fence():
    raw = '```json\n{"winner_index": 1, "reasoning": "closest match"}\n```'
    assert parse_scoring_output(raw, num_candidates=3) == 1


def test_strips_bare_code_fence():
    raw = '```\n{"winner_index": 0, "reasoning": "only real option"}\n```'
    assert parse_scoring_output(raw, num_candidates=3) == 0


def test_malformed_json_raises():
    with pytest.raises(ScoringOutputError, match="not valid JSON"):
        parse_scoring_output("not json at all", num_candidates=5)


def test_out_of_range_index_raises():
    with pytest.raises(ScoringOutputError, match="between 0 and 4"):
        parse_scoring_output('{"winner_index": 7, "reasoning": "x"}', num_candidates=5)


def test_negative_index_raises():
    with pytest.raises(ScoringOutputError, match="between 0 and 4"):
        parse_scoring_output('{"winner_index": -1, "reasoning": "x"}', num_candidates=5)


def test_non_integer_index_raises():
    with pytest.raises(ScoringOutputError, match="between 0 and 4"):
        parse_scoring_output('{"winner_index": "two", "reasoning": "x"}', num_candidates=5)


def test_missing_index_raises():
    with pytest.raises(ScoringOutputError, match="between 0 and 4"):
        parse_scoring_output('{"reasoning": "x"}', num_candidates=5)


def test_null_winner_raises_no_acceptable_candidate_with_reasoning():
    raw = '{"winner_index": null, "reasoning": "all clips show Osaka, not Tokyo"}'
    with pytest.raises(NoAcceptableCandidateError) as excinfo:
        parse_scoring_output(raw, num_candidates=5)

    assert excinfo.value.reasoning == "all clips show Osaka, not Tokyo"
    assert "all clips show Osaka, not Tokyo" in str(excinfo.value)


def test_null_winner_inside_code_fence_is_still_no_acceptable_candidate():
    raw = '```json\n{"winner_index": null, "reasoning": "none match"}\n```'
    with pytest.raises(NoAcceptableCandidateError):
        parse_scoring_output(raw, num_candidates=3)


def test_null_winner_without_reasoning_still_raises_no_acceptable_candidate():
    with pytest.raises(NoAcceptableCandidateError) as excinfo:
        parse_scoring_output('{"winner_index": null}', num_candidates=3)

    assert excinfo.value.reasoning is None


def test_null_winner_is_distinguishable_from_malformed_output():
    # A deliberate "none acceptable" verdict is a valid response, not a parse error...
    with pytest.raises(NoAcceptableCandidateError) as null_exc:
        parse_scoring_output('{"winner_index": null, "reasoning": "x"}', num_candidates=3)
    assert not isinstance(null_exc.value, ScoringOutputError)

    # ...while a missing index is malformed output, not a "none acceptable" verdict.
    with pytest.raises(ScoringOutputError) as missing_exc:
        parse_scoring_output('{"reasoning": "x"}', num_candidates=3)
    assert not isinstance(missing_exc.value, NoAcceptableCandidateError)


@pytest.mark.parametrize("raw", ['[0, 1]', '"winner is 0"', '3', 'null'])
def test_non_object_top_level_json_raises_scoring_output_error(raw):
    with pytest.raises(ScoringOutputError, match="must be a JSON object"):
        parse_scoring_output(raw, num_candidates=3)
