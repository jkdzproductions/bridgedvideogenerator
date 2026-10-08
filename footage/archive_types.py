# footage/archive_types.py
"""Shared pieces of the archival-imagery sources: one candidate shape and the HTTP helpers."""
import email.utils
import html
import http.client
import os
import re
import time
from dataclasses import dataclass
from typing import Optional

import requests
import urllib3

# No contact details in here on purpose: this header goes to third-party archive servers.
USER_AGENT = "BridgedVideoGenerator/0.1"
MIN_PHOTO_LONG_SIDE = 1000  # a full-frame photo much smaller than this looks soft; the judge also checks
MIN_FILM_SECONDS = 3.0
_TIMEOUT = 30

# Bounded retry (live finding 2026-10-07/08: Commons 429s and LoC 520s / IncompleteRead broken downloads were
# dropped on the first failure). A 429, any 5xx, a timeout, a dropped connection or a truncated body is retried
# with exponential backoff (2, 4, 8 s), honoring Retry-After (capped), at most MAX_ATTEMPTS tries in all.
# Anything else (404, 403, ...) fails at once. Only after the last attempt does the caller see an ArchiveError,
# so a candidate is dropped only once its retries are used up.
MAX_ATTEMPTS = 4
BACKOFF_BASE_SECONDS = 2.0
MAX_BACKOFF_SECONDS = 60.0
_TRANSIENT_ERRORS = (
    requests.Timeout, requests.ConnectionError, requests.exceptions.ChunkedEncodingError,
    http.client.IncompleteRead, urllib3.exceptions.ProtocolError,
)
_RATE_LIMIT_HEADERS = ("retry-after", "x-ratelimit-limit", "x-ratelimit-remaining", "x-ratelimit-reset",
                       "ratelimit-limit", "ratelimit-remaining", "ratelimit-reset", "ratelimit-policy")


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


class _Incomplete(Exception):
    """The body was shorter than its Content-Length."""


def _retryable_status(status: int) -> bool:
    return status == 429 or 500 <= status <= 599


def _headers(response) -> dict:
    return dict(getattr(response, "headers", None) or {})


def _header(response, name: str):
    return next((v for k, v in _headers(response).items() if k.lower() == name), None)


def _rate_limit_note(response) -> str:
    """' (Retry-After: 7, x-ratelimit-limit: ...)' for the rate-limit headers a response carried, else ''."""
    found = [f"{k}: {v}" for k, v in _headers(response).items() if k.lower() in _RATE_LIMIT_HEADERS]
    return f" ({', '.join(found)})" if found else ""


def _retry_delay(attempt: int, response=None) -> float:
    """Seconds to wait after failed attempt number `attempt` (1-based): the server's Retry-After (seconds or an
    HTTP date) when it sent one, else exponential backoff; never more than MAX_BACKOFF_SECONDS."""
    value = _header(response, "retry-after")
    if value is not None:
        seconds = None
        try:
            seconds = float(value)
        except (TypeError, ValueError):
            try:
                seconds = email.utils.parsedate_to_datetime(str(value)).timestamp() - time.time()
            except (TypeError, ValueError, IndexError):
                seconds = None
        if seconds is not None:
            return min(max(seconds, 0.0), MAX_BACKOFF_SECONDS)
    return min(BACKOFF_BASE_SECONDS * 2 ** (attempt - 1), MAX_BACKOFF_SECONDS)


def _wait_before_retry(url: str, attempt: int, problem: str, response=None) -> None:
    delay = _retry_delay(attempt, response)
    print(f"WARNING: {url}: {problem}{_rate_limit_note(response)}; retrying in {delay:g}s "
          f"(attempt {attempt + 1} of {MAX_ATTEMPTS})", flush=True)
    time.sleep(delay)


def _gave_up(attempt: int) -> str:
    return f" (gave up after {attempt} attempts)" if attempt > 1 else ""


def get_json(url: str, params: dict) -> dict:
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = requests.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=_TIMEOUT)
        except _TRANSIENT_ERRORS as e:
            if attempt == MAX_ATTEMPTS:
                raise ArchiveError(f"{url}: {e}{_gave_up(attempt)}") from e
            _wait_before_retry(url, attempt, f"{type(e).__name__}: {e}")
            continue
        except requests.RequestException as e:
            raise ArchiveError(f"{url}: {e}") from e
        if response.status_code == 200:
            break
        if _retryable_status(response.status_code) and attempt < MAX_ATTEMPTS:
            _wait_before_retry(url, attempt, f"status {response.status_code}", response)
            continue
        raise ArchiveError(f"{url} returned status {response.status_code}{_rate_limit_note(response)}"
                           f"{_gave_up(attempt)}: {str(getattr(response, 'text', ''))[:200]}")
    try:
        payload = response.json()
    except ValueError as e:
        raise ArchiveError(f"{url} response is not JSON ({e})") from e
    if not isinstance(payload, dict):
        raise ArchiveError(f"{url} returned an unexpected JSON shape ({type(payload).__name__}, expected an object)")
    if "error" in payload:
        raise ArchiveError(f"{url} returned an API error: {str(payload['error'])[:200]}")
    return payload


def _remove(path: str) -> None:
    if os.path.exists(path):
        os.remove(path)


def _write_body(response, dest_path: str) -> None:
    """Stream the body to dest_path; raise _Incomplete when fewer bytes arrived than Content-Length promised."""
    written = 0
    with open(dest_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=65536):
            f.write(chunk)
            written += len(chunk)
    expected = _header(response, "content-length")
    if expected is not None and str(expected).isdigit() and written < int(expected):
        raise _Incomplete(f"IncompleteRead: got {written} of {expected} bytes")


def fetch_to_file(url: str, dest_path: str) -> str:
    os.makedirs(os.path.dirname(os.path.abspath(dest_path)), exist_ok=True)
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=60, stream=True)
        except _TRANSIENT_ERRORS as e:
            if attempt == MAX_ATTEMPTS:
                raise ArchiveError(f"{url}: {e}{_gave_up(attempt)}") from e
            _wait_before_retry(url, attempt, f"{type(e).__name__}: {e}")
            continue
        except requests.RequestException as e:
            raise ArchiveError(f"{url}: {e}") from e
        try:
            if response.status_code != 200:
                if _retryable_status(response.status_code) and attempt < MAX_ATTEMPTS:
                    _wait_before_retry(url, attempt, f"status {response.status_code}", response)
                    continue
                raise ArchiveError(f"download of {url} returned status {response.status_code}"
                                   f"{_rate_limit_note(response)}{_gave_up(attempt)}")
            try:
                _write_body(response, dest_path)
                return dest_path
            except (_Incomplete,) + _TRANSIENT_ERRORS as e:
                _remove(dest_path)
                if attempt == MAX_ATTEMPTS:
                    raise ArchiveError(f"{url}: broken download ({e}){_gave_up(attempt)}") from e
                _wait_before_retry(url, attempt, f"broken download ({type(e).__name__}: {e})", response)
            except requests.RequestException as e:
                _remove(dest_path)
                raise ArchiveError(f"{url}: {e}") from e
            except BaseException:
                _remove(dest_path)
                raise
        finally:
            close = getattr(response, "close", None)
            if close:
                close()
    raise AssertionError("unreachable")  # pragma: no cover


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
