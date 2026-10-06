import math


def subdivide_footage_range(
    start: float, end: float, min_cut: float = 2.5, max_cut: float = 6.0
) -> list[tuple[float, float]]:
    # max_cut is 6s (Josh, 2026-09-29; was 10s). min_cut must stay <= max_cut / 2 so any range
    # just over max_cut can still be split into two cuts that both respect the minimum.
    duration = end - start
    if duration <= max_cut:
        return [(start, end)]

    n_cuts = math.ceil(duration / max_cut)
    cut_len = duration / n_cuts
    while cut_len < min_cut and n_cuts > 1:
        n_cuts -= 1
        cut_len = duration / n_cuts

    return [(start + i * cut_len, start + (i + 1) * cut_len) for i in range(n_cuts)]
