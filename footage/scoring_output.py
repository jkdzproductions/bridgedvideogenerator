import json
import re
from typing import Optional

_FENCE_PATTERN = re.compile(r"^```(?:json)?\s*\n(.*)\n```\s*$", re.DOTALL)


class ScoringOutputError(ValueError):
    """The scorer's response is malformed (not JSON, wrong shape, bad index)."""


class NoAcceptableCandidateError(Exception):
    """The scorer deliberately answered winner_index: null — none of the candidates is an
    acceptable match. A valid verdict, not a parse error, so deliberately NOT a subclass of
    ScoringOutputError: callers must handle it distinctly (stop and flag the beat)."""

    def __init__(self, reasoning: Optional[str]):
        self.reasoning = reasoning
        message = "scorer found no acceptable candidate"
        if reasoning:
            message += f": {reasoning}"
        super().__init__(message)


def _strip_code_fence(raw: str) -> str:
    match = _FENCE_PATTERN.match(raw.strip())
    return match.group(1) if match else raw


def parse_scoring_output(raw_json: str, num_candidates: int) -> int:
    cleaned = _strip_code_fence(raw_json)
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ScoringOutputError(f"scoring output is not valid JSON: {e}") from e

    if not isinstance(payload, dict):
        raise ScoringOutputError(
            f"scoring output must be a JSON object, got {type(payload).__name__}"
        )

    # An explicit null is the scorer saying "none of these"; a missing key is malformed.
    if "winner_index" in payload and payload["winner_index"] is None:
        reasoning = payload.get("reasoning")
        raise NoAcceptableCandidateError(reasoning if isinstance(reasoning, str) else None)

    winner_index = payload.get("winner_index")
    if not isinstance(winner_index, int) or isinstance(winner_index, bool) or not (
        0 <= winner_index < num_candidates
    ):
        raise ScoringOutputError(
            f"winner_index must be an integer between 0 and {num_candidates - 1}, "
            f"got {winner_index!r}"
        )
    return winner_index
