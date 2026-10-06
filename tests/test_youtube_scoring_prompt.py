from footage.youtube import YouTubeCandidate
from footage.youtube_scoring_prompt import build_youtube_scoring_prompt

CANDIDATES = [
    YouTubeCandidate("abc123", "Tokyo Subway B-Roll 4K", "UC1", "Free Stock Footage Co",
                      "thumb1.jpg", 253.0),
    YouTubeCandidate("def456", "A Day in Tokyo (Vlog)", "UC2", "Some Traveler",
                      "thumb2.jpg", 900.0),
]
THUMBNAIL_PATHS = {"abc123": "/tmp/thumbs/abc123.jpg", "def456": "/tmp/thumbs/def456.jpg"}


def test_prompt_includes_titles_channels_durations_and_thumbnail_paths():
    prompt = build_youtube_scoring_prompt(
        query="tokyo subway b-roll", subject="Tokyo's subway system",
        candidates=CANDIDATES, thumbnail_paths=THUMBNAIL_PATHS,
    )

    assert "Tokyo Subway B-Roll 4K" in prompt
    assert "Free Stock Footage Co" in prompt
    assert "253" in prompt
    assert "/tmp/thumbs/abc123.jpg" in prompt
    assert "A Day in Tokyo (Vlog)" in prompt


def test_prompt_explains_only_the_start_of_the_video_is_used():
    prompt = build_youtube_scoring_prompt(
        query="q", subject="s", candidates=CANDIDATES, thumbnail_paths=THUMBNAIL_PATHS,
    )

    assert "Read tool" in prompt
    assert "winner_index" in prompt
    assert "only the first part" in prompt.lower() or "opening" in prompt.lower()
    assert "null" in prompt
