import json
import re
from dataclasses import dataclass
from typing import Literal, Optional

_FENCE_PATTERN = re.compile(r"^```(?:json)?\s*\n(.*)\n```\s*$", re.DOTALL)

_VALID_VERDICTS = {"approve", "correction", "reject"}


class ReviewerOutputError(ValueError):
    pass


@dataclass
class ReviewerVerdict:
    verdict: Literal["approve", "correction", "reject"]
    reasoning: str
    correction_instructions: Optional[str] = None


def _strip_code_fence(raw: str) -> str:
    match = _FENCE_PATTERN.match(raw.strip())
    return match.group(1) if match else raw


def parse_reviewer_output(raw: str) -> ReviewerVerdict:
    cleaned = _strip_code_fence(raw)
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ReviewerOutputError(f"reviewer output is not valid JSON: {e}") from e

    if not isinstance(payload, dict):
        raise ReviewerOutputError(
            f"reviewer output must be a JSON object, got {type(payload).__name__}"
        )

    verdict = payload.get("verdict")
    if verdict not in _VALID_VERDICTS:
        raise ReviewerOutputError(
            f"verdict must be one of {sorted(_VALID_VERDICTS)}, got {verdict!r}"
        )

    reasoning = payload.get("reasoning")
    if not isinstance(reasoning, str) or not reasoning.strip():
        raise ReviewerOutputError("reviewer output missing a non-empty 'reasoning'")

    correction_instructions = payload.get("correction_instructions")
    if verdict == "correction":
        if not isinstance(correction_instructions, str) or not correction_instructions.strip():
            raise ReviewerOutputError(
                "verdict is 'correction' but 'correction_instructions' is missing or empty"
            )
        correction_instructions = correction_instructions.strip()
    else:
        correction_instructions = None

    return ReviewerVerdict(
        verdict=verdict, reasoning=reasoning.strip(),
        correction_instructions=correction_instructions,
    )
