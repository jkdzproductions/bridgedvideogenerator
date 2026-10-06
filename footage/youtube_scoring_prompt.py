from footage.youtube import YouTubeCandidate


def build_youtube_scoring_prompt(
    query: str,
    subject: str,
    candidates: list[YouTubeCandidate],
    thumbnail_paths: dict[str, str],
) -> str:
    candidate_lines = "\n".join(
        f'[{i}] title="{c.title}" channel="{c.channel_title}" duration={c.duration_seconds:.0f}s '
        f"thumbnail={thumbnail_paths[c.video_id]}"
        for i, c in enumerate(candidates)
    )

    return f"""You are scoring YouTube video candidates for one beat of a documentary video.

Target subject: {subject}
Search query used to find these candidates: "{query}"

Below are {len(candidates)} candidate YouTube videos. Use your Read tool to actually view each \
thumbnail image at its listed path before judging — do not guess from the title alone.

Candidates:
{candidate_lines}

These are whole YouTube videos, not pre-cut stock clips — only the first part of the video \
(from 0:00) will actually be used, up to the beat's needed duration, so judge each thumbnail as \
a proxy for what the opening of that video likely shows, not the video as a whole. Prefer a \
candidate whose title and thumbnail suggest short, purpose-shot b-roll/stock footage over a \
long-form video (news segment, vlog, documentary) where the relevant content might be buried \
deep inside it.

If none of the candidates are an acceptable match, respond with "winner_index": null and \
explain why in "reasoning" — do not force a pick.

Respond with ONLY a JSON object, no other text:
{{"winner_index": <int or null>, "reasoning": "<one sentence>"}}
"""
