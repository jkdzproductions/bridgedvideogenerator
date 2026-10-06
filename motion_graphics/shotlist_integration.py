from shot_list.models import GraphicSpec, ShotList


def graphic_beats(shot_list: ShotList) -> list[tuple[int, GraphicSpec, float]]:
    return [
        (i, beat.graphic, beat.end - beat.start)
        for i, beat in enumerate(shot_list.beats)
        if beat.type == "graphic"
    ]
