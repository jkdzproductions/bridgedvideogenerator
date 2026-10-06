from footage.pexels import PexelsCandidate
from footage.scoring_prompt import build_scoring_prompt

CANDIDATES = [
    PexelsCandidate(3129957, "url1", "thumb1.jpg", 20, 1920, 1080, []),
    PexelsCandidate(4242424, "url2", "thumb2.jpg", 12, 1280, 720, []),
]
THUMBNAIL_PATHS = {3129957: "/tmp/thumbs/3129957.jpg", 4242424: "/tmp/thumbs/4242424.jpg"}


def test_prompt_includes_query_subject_and_every_thumbnail_path():
    prompt = build_scoring_prompt(
        query="tokyo subway platform", subject="Tokyo's subway system",
        candidates=CANDIDATES, thumbnail_paths=THUMBNAIL_PATHS,
    )

    assert "tokyo subway platform" in prompt
    assert "Tokyo's subway system" in prompt
    assert "/tmp/thumbs/3129957.jpg" in prompt
    assert "/tmp/thumbs/4242424.jpg" in prompt
    assert "[0]" in prompt
    assert "[1]" in prompt


def test_prompt_instructs_using_the_read_tool_and_json_response():
    prompt = build_scoring_prompt(
        query="q", subject="s", candidates=CANDIDATES, thumbnail_paths=THUMBNAIL_PATHS,
    )

    assert "Read tool" in prompt
    assert "winner_index" in prompt


def test_prompt_allows_a_null_winner_when_no_candidate_is_acceptable():
    prompt = build_scoring_prompt(
        query="q", subject="s", candidates=CANDIDATES, thumbnail_paths=THUMBNAIL_PATHS,
    )

    assert '{"winner_index": null' in prompt
    assert "none" in prompt.lower()
