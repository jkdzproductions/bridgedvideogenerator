from dataclasses import dataclass
from typing import Literal, Optional

ARCHETYPES = {
    "diamond_flow",
    "fan_out",
    "year_range",
    "then_vs_now",
    "chart_card",
    "territory_map",
    "network_map",
}


@dataclass
class GraphicSpec:
    archetype: str
    data: dict


ARCHIVAL_CUTOFF_YEAR = 1960  # a cut about a period before this year uses real archival film/photos
PHOTO_EARLIEST_YEAR = 1839  # before this year there are no photographs
ARTWORK_BEFORE_YEAR = 1900  # before this year (photographs are scarce) the judge may also choose real historical artwork


@dataclass
class FootageSpec:
    query: str
    subject: str
    era: Optional[int] = None  # None = modern; otherwise the year the spoken words are about
    archival_query: str = ""  # pre-cutoff cuts only: a specific search for archive sites
    archival_broad_query: str = ""  # pre-cutoff cuts only: city/region + era, used when the specific one finds too few


def needs_archival(era: Optional[int]) -> bool:
    """True for every year before ARCHIVAL_CUTOFF_YEAR. The one place this comparison lives."""
    return era is not None and era < ARCHIVAL_CUTOFF_YEAR


def archival_medium(era: int) -> str:
    """Which candidates the judge sees for an archival cut: stock or artwork before photography existed,
    photographs or artwork up to 1900, photographs and film after that."""
    if era < PHOTO_EARLIEST_YEAR:
        return "artwork_or_stock"
    if era < ARTWORK_BEFORE_YEAR:
        return "photo_or_artwork"
    return "photo"


def is_archival(spec: FootageSpec) -> bool:
    return needs_archival(spec.era)


@dataclass
class PageSpec:
    italic_index: int  # which italic (graphic) span of the script this page link is; names its stills


@dataclass
class ImageSpec:
    italic_index: int  # which italic (graphic) span of the script this image link is; names its file in image_stills/


@dataclass
class Beat:
    start: float
    end: float
    type: Literal["footage", "graphic", "talking_head", "page_highlight", "image"]
    footage: Optional[FootageSpec] = None
    graphic: Optional[GraphicSpec] = None
    page: Optional[PageSpec] = None
    image: Optional[ImageSpec] = None


def beat_from_dict(b: dict) -> Beat:
    """A Beat from its dataclasses.asdict form (shot_list.json). `.get` for page and image so files written
    before page_highlight existed still load."""
    return Beat(
        start=b["start"], end=b["end"], type=b["type"],
        footage=FootageSpec(**b["footage"]) if b.get("footage") else None,
        graphic=GraphicSpec(**b["graphic"]) if b.get("graphic") else None,
        page=PageSpec(**b["page"]) if b.get("page") else None,
        image=ImageSpec(**b["image"]) if b.get("image") else None,
    )


@dataclass
class ShotList:
    beats: list[Beat]
    duration: float


class ShotListValidationError(ValueError):
    pass


def validate_shot_list(shot_list: "ShotList") -> None:
    if not shot_list.beats:
        raise ShotListValidationError("shot list has no beats")

    beats = sorted(shot_list.beats, key=lambda b: b.start)

    for beat in beats:
        if not beat.start < beat.end:
            raise ShotListValidationError(
                f"beat {beat.start}-{beat.end} has a non-positive duration"
            )

    if abs(beats[0].start - 0.0) > 1e-6:
        raise ShotListValidationError(f"first beat starts at {beats[0].start}, expected 0.0")

    for prev, cur in zip(beats, beats[1:]):
        if abs(prev.end - cur.start) > 1e-6:
            raise ShotListValidationError(
                f"gap or overlap between beat ending at {prev.end} and beat starting at {cur.start}"
            )

    if abs(beats[-1].end - shot_list.duration) > 1e-6:
        raise ShotListValidationError(
            f"last beat ends at {beats[-1].end}, expected duration {shot_list.duration}"
        )

    for beat in beats:
        if beat.type == "graphic":
            if beat.graphic is None:
                raise ShotListValidationError(f"graphic beat at {beat.start} missing graphic spec")
            if beat.graphic.archetype not in ARCHETYPES:
                raise ShotListValidationError(f"unknown archetype: {beat.graphic.archetype}")
        elif beat.type == "footage":
            if beat.footage is None:
                raise ShotListValidationError(f"footage beat at {beat.start} missing footage spec")
            if is_archival(beat.footage) and not (
                    beat.footage.archival_query.strip() and beat.footage.archival_broad_query.strip()):
                raise ShotListValidationError(
                    f"archival footage beat at {beat.start} (era {beat.footage.era}) needs both an "
                    "archival_query and an archival_broad_query")
        elif beat.type == "talking_head":
            if beat.footage is not None or beat.graphic is not None:
                raise ShotListValidationError(
                    f"talking_head beat at {beat.start} must not carry a footage or graphic spec")
        elif beat.type == "page_highlight":
            if beat.page is None:
                raise ShotListValidationError(f"page_highlight beat at {beat.start} missing page spec")
            if beat.footage is not None or beat.graphic is not None:
                raise ShotListValidationError(
                    f"page_highlight beat at {beat.start} must not carry a footage or graphic spec")
        elif beat.type == "image":
            if beat.image is None:
                raise ShotListValidationError(f"image beat at {beat.start} missing image spec")
            if beat.footage is not None or beat.graphic is not None or beat.page is not None:
                raise ShotListValidationError(
                    f"image beat at {beat.start} must not carry a footage, graphic or page spec")
        else:
            raise ShotListValidationError(f"unknown beat type: {beat.type}")
