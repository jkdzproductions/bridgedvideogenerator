import json
import re

_FENCE_PATTERN = re.compile(r"^```(?:json)?\s*\n(.*)\n```\s*$", re.DOTALL)


class PromptWriterOutputError(ValueError):
    pass


def _strip_code_fence(raw: str) -> str:
    match = _FENCE_PATTERN.match(raw.strip())
    return match.group(1) if match else raw


def parse_prompt_writer_output(raw: str) -> str:
    cleaned = _strip_code_fence(raw)
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise PromptWriterOutputError(f"prompt-writer output is not valid JSON: {e}") from e

    if not isinstance(payload, dict):
        raise PromptWriterOutputError(
            f"prompt-writer output must be a JSON object, got {type(payload).__name__}"
        )

    authoring_prompt = payload.get("authoring_prompt")
    if not isinstance(authoring_prompt, str) or not authoring_prompt.strip():
        raise PromptWriterOutputError(
            "prompt-writer output missing a non-empty 'authoring_prompt'"
        )

    return authoring_prompt.strip()
