from footage.pexels import PexelsCandidate


def build_scoring_prompt(
    query: str,
    subject: str,
    candidates: list[PexelsCandidate],
    thumbnail_paths: dict[int, str],
) -> str:
    candidate_lines = "\n".join(
        f"[{i}] duration={c.duration}s resolution={c.width}x{c.height} "
        f"thumbnail={thumbnail_paths[c.id]}"
        for i, c in enumerate(candidates)
    )

    return f"""You are scoring stock footage candidates for one beat of a documentary video.

Target subject: {subject}
Search query used to find these candidates: "{query}"

Below are {len(candidates)} candidate video thumbnails. Use your Read tool to actually view \
each thumbnail image at its listed path before judging — do not guess from the metadata alone.

Candidates:
{candidate_lines}

Pick the candidate whose thumbnail most specifically and accurately depicts the target subject. \
Prefer a real, specific match over a generic stand-in (e.g. an actual Tokyo subway platform over \
generic transit stock footage). If two are equally good matches, prefer the higher resolution one.

If NONE of the candidates is an acceptable match — every one is irrelevant, wrong, or too \
generic to stand in for the target subject — do not force a pick. Say so with a null winner \
instead; the beat will be flagged for a human rather than filled with a poor clip.

Respond with ONLY a JSON object, no other text. Either:
{{"winner_index": <int>, "reasoning": "<one sentence>"}}
or, if no candidate is acceptable:
{{"winner_index": null, "reasoning": "<one sentence on why none are acceptable>"}}
"""
