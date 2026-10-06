from footage.download import download_thumbnails, download_winning_video
from footage.pexels import PexelsCandidate, search_pexels
from footage.scoring_prompt import build_scoring_prompt

# Pexels' documented maximum page size for /videos/search.
PEXELS_MAX_PER_PAGE = 80


def prepare_footage_scoring(
    query: str,
    subject: str,
    api_key: str,
    thumbnails_dir: str,
    per_page: int = 7,
    exclude_ids: frozenset[int] = frozenset(),
) -> tuple[list[PexelsCandidate], str]:
    # Pexels has no server-side "exclude these IDs" parameter, so when earlier beats in
    # this run already used some clips, over-fetch and filter them out client-side. That
    # way repeated cuts of the same query get different real clips where Pexels has them.
    search_size = max(per_page, PEXELS_MAX_PER_PAGE) if exclude_ids else per_page
    results = search_pexels(query, api_key, search_size)
    candidates = [c for c in results if c.id not in exclude_ids][:per_page]
    if not candidates:
        detail = (
            f" after excluding {len(results)} already-used clip(s)" if results else ""
        )
        raise ValueError(f"no Pexels candidates found for query: {query!r}{detail}")

    thumbnail_paths = download_thumbnails(candidates, thumbnails_dir)
    prompt = build_scoring_prompt(query, subject, candidates, thumbnail_paths)
    return candidates, prompt


def resolve_footage_winner(
    candidates: list[PexelsCandidate], winner_index: int, dest_path: str
) -> str:
    winner = candidates[winner_index]
    return download_winning_video(winner, dest_path)
