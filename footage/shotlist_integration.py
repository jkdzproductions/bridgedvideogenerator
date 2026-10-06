from shot_list.models import ShotList, archival_medium, is_archival


def footage_beats(shot_list: ShotList) -> list[tuple[int, str, str]]:
    """Modern footage beats only: the ones searched on Pexels, YouTube and Envato."""
    return [
        (i, beat.footage.query, beat.footage.subject)
        for i, beat in enumerate(shot_list.beats)
        if beat.type == "footage" and not is_archival(beat.footage)
    ]


def archival_beats(shot_list: ShotList) -> list[dict]:
    """Footage beats about a period before the cutoff: the ones that get archival film or photos."""
    return [
        {
            "beat_index": i, "start": beat.start, "end": beat.end, "era": beat.footage.era,
            "subject": beat.footage.subject, "archival_query": beat.footage.archival_query,
            "archival_broad_query": beat.footage.archival_broad_query,
            "medium": archival_medium(beat.footage.era), "query": beat.footage.query,
        }
        for i, beat in enumerate(shot_list.beats)
        if beat.type == "footage" and is_archival(beat.footage)
    ]
