# footage/archive_types.py
"""Shared pieces of the archival-imagery sources: one candidate shape and the HTTP helpers."""
import html
import os
import re
import time
from dataclasses import dataclass
from typing import Optional

import requests

# No contact details in here on purpose: this header goes to third-party archive servers.
USER_AGENT = "VersedVideoGenerator/0.1"
MIN_PHOTO_LONG_SIDE = 1000  # a full-frame photo much smaller than this looks soft; the judge also checks
MIN_FILM_SECONDS = 3.0
_TIMEOUT = 30


class ArchiveError(Exception):
    """An archive could not be searched or downloaded (HTTP error, not JSON, ...)."""


@dataclass
class ArchiveCandidate:
    source: str  # "commons" | "loc" | "ia"
    item_id: str
    kind: str  # "photo" | "film"
    title: str
    year: Optional[int]
    creator: str
    rights: str  # the archive's own short rights statement, shown on the review sheet
    page_url: str  # human page for the item
    media_url: str  # photo: the image to download; film: the direct video file URL
    thumbnail_url: str  # what the judge looks at
    width: int = 0
    height: int = 0
    duration_seconds: float = 0.0  # film only

    @property
    def display_id(self) -> str:
        return f"{self.source}:{self.item_id}"

    @property
    def safe_id(self) -> str:
        return re.sub(r"[^A-Za-z0-9_-]", "_", self.display_id)


def get_json(url: str, params: dict) -> dict:
    try:
        try:
            response = requests.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=_TIMEOUT)
        except (requests.Timeout, requests.ConnectionError):
            time.sleep(1.0)  # one transient network blip is retried once; HTTP/API errors never are
            response = requests.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=_TIMEOUT)
    except requests.RequestException as e:
        raise ArchiveError(f"{url}: {e}") from e
    if response.status_code != 200:
        raise ArchiveError(f"{url} returned status {response.status_code}: {response.text[:200]}")
    try:
        payload = response.json()
    except ValueError as e:
        raise ArchiveError(f"{url} response is not JSON ({e})") from e
    if not isinstance(payload, dict):
        raise ArchiveError(f"{url} returned an unexpected JSON shape ({type(payload).__name__}, expected an object)")
    if "error" in payload:
        raise ArchiveError(f"{url} returned an API error: {str(payload['error'])[:200]}")
    return payload


def fetch_to_file(url: str, dest_path: str) -> str:
    try:
        response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=60, stream=True)
    except requests.RequestException as e:
        raise ArchiveError(f"{url}: {e}") from e
    try:
        if response.status_code != 200:
            raise ArchiveError(f"download of {url} returned status {response.status_code}")
        os.makedirs(os.path.dirname(os.path.abspath(dest_path)), exist_ok=True)
        try:
            with open(dest_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=65536):
                    f.write(chunk)
        except requests.RequestException as e:
            if os.path.exists(dest_path):
                os.remove(dest_path)
            raise ArchiveError(f"{url}: {e}") from e
        except Exception:
            if os.path.exists(dest_path):
                os.remove(dest_path)
            raise
    finally:
        response.close()
    return dest_path


def strip_html(text: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", "", text or "")).split())


_YEAR_RE = r"(?<!\d)(1[0-9]{3}|20[0-9]{2})"


def year_from(text) -> Optional[int]:
    # Not-preceded-by-a-digit (not \b) so "c1888." still gives 1888.
    match = re.search(_YEAR_RE, str(text or ""))
    return int(match.group(1)) if match else None


def all_years(text) -> list:
    """Every 4-digit year (1000-2099) in the text, in order."""
    return [int(y) for y in re.findall(_YEAR_RE, str(text or ""))]
