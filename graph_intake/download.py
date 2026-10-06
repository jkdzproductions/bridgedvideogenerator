"""Download the graph image an italic phrase links to (stdlib only), refusing anything that is not
really a raster image the reading subagent can view."""
import glob
import http.client
import os
import struct
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

# Image hosts (i.redd.it included) refuse or rate-limit Python's default "Python-urllib" agent.
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
TIMEOUT_SECONDS = 30  # per socket operation
# TIMEOUT_SECONDS alone lets a server that drips one byte at a time hold the download open
# forever, so the whole transfer also gets a wall-clock budget.
TOTAL_DEADLINE_SECONDS = 120
CHUNK_BYTES = 64 * 1024
MAX_BYTES = 15 * 1024 * 1024
# The image reader downsizes or refuses very large images; a graph taller or wider than this
# would have its labels shrunk past legibility, so it is refused instead of misread.
MAX_SIDE_PIXELS = 8000


class GraphDownloadError(Exception):
    """The linked graph could not be downloaded as an image; the message names phrase and URL."""


class NotAnImageError(GraphDownloadError):
    """The link points at a web page, not an image file. Stage 1 skips such a link (reporting it)
    instead of stopping, because a page link without a #:~:text= highlight is not a graph."""


def sniff_image_type(data: bytes) -> Optional[str]:
    """File extension from the bytes themselves (never from the URL, which may carry a query
    string or no extension at all). None if not a PNG/JPEG/GIF/WebP."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def _jpeg_size(data: bytes) -> Optional[tuple]:
    i = 2
    while i + 9 < len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7 or marker == 0xFF:
            i += 1 if marker == 0xFF else 2
            continue
        (length,) = struct.unpack(">H", data[i + 2:i + 4])
        # SOF0-SOF15 carry the frame size, except DHT (C4), JPG (C8) and DAC (CC).
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            height, width = struct.unpack(">HH", data[i + 5:i + 9])
            return width, height
        i += 2 + length
    return None


def image_is_complete(data: bytes, image_type: str) -> bool:
    """True if the bytes end the way a whole file of this type ends, so a body cut short by a
    dropped connection is refused instead of saved as a corrupt image."""
    if image_type == "png":  # last chunk is IEND: length 0, type, fixed CRC
        return data.endswith(b"\x00\x00\x00\x00IEND\xaeB`\x82")
    if image_type == "jpg":  # End Of Image marker (encoders may pad with zero bytes after it)
        return data.rstrip(b"\x00").endswith(b"\xff\xd9")
    if image_type == "gif":  # trailer byte
        return data.endswith(b"\x3b")
    if image_type == "webp":  # RIFF size field counts everything after the first 8 bytes
        return len(data) >= 12 and len(data) == 8 + int.from_bytes(data[4:8], "little")
    return False


def image_size(data: bytes, image_type: str) -> Optional[tuple]:
    """(width, height) read from the header, or None if the header can't be parsed."""
    if image_type == "png" and len(data) >= 24:
        return struct.unpack(">II", data[16:24])
    if image_type == "gif" and len(data) >= 10:
        return struct.unpack("<HH", data[6:10])
    if image_type == "jpg":
        return _jpeg_size(data)
    if image_type == "webp" and len(data) >= 30:
        chunk = data[12:16]
        if chunk == b"VP8X":
            return (int.from_bytes(data[24:27], "little") + 1,
                    int.from_bytes(data[27:30], "little") + 1)
        if chunk == b"VP8L":
            bits = int.from_bytes(data[21:25], "little")
            return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
        if chunk == b"VP8 ":
            width, height = struct.unpack("<HH", data[26:30])
            return width & 0x3FFF, height & 0x3FFF
    return None


class _BadRedirect(Exception):
    pass


class _HttpOnlyRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        scheme = urllib.parse.urlsplit(newurl).scheme.lower()
        if scheme not in ("http", "https"):
            raise _BadRedirect(
                f"redirected to a {scheme or 'non-http'!r} URL ({newurl}); only http and https "
                "are followed")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _safe_url(url: str) -> str:
    """Percent-quote spaces / non-ASCII in path and query, leaving existing %XX escapes and URL
    delimiters alone so an already-encoded URL is not double-encoded."""
    parts = urllib.parse.urlsplit(url.strip())
    safe = "/%:@!$&'()*+,;=~-._"
    return urllib.parse.urlunsplit((
        parts.scheme, parts.netloc, urllib.parse.quote(parts.path, safe=safe),
        urllib.parse.quote(parts.query, safe=safe + "?"), ""))


def _remove_graph_files(out_dir: str, italic_index: int) -> None:
    for path in glob.glob(os.path.join(glob.escape(out_dir), f"graph_{italic_index}.*")):
        os.remove(path)


def download_graph_image(url: str, italic_text: str, italic_index: int, out_dir: str) -> dict:
    """-> {"image_path": absolute path, "width": int, "height": int}. Raises GraphDownloadError.
    On any failure no graph_<italic_index>.* file is left behind (a stale image from an earlier
    run must never be mistaken for this download)."""
    where = f"linked graph for {italic_text!r} ({url})"
    _remove_graph_files(out_dir, italic_index)
    try:
        request = urllib.request.Request(
            _safe_url(url), headers={"User-Agent": USER_AGENT, "Accept": "image/*,*/*;q=0.8"})
    except ValueError as e:
        raise GraphDownloadError(f"{where}: not a usable URL: {e}") from e
    opener = urllib.request.build_opener(_HttpOnlyRedirects)
    started = time.monotonic()
    try:
        # The opener follows redirects itself; HTTPError covers every 4xx/5xx.
        with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
            status = response.status
            content_type = response.headers.get("Content-Type", "")
            declared = response.headers.get("Content-Length")
            declared = int(declared) if declared and declared.isdigit() else None
            if declared is not None and declared > MAX_BYTES:
                raise GraphDownloadError(
                    f"{where}: file is {declared} bytes, over the {MAX_BYTES}-byte limit")
            chunks, total = [], 0
            while True:
                if time.monotonic() - started > TOTAL_DEADLINE_SECONDS:
                    raise GraphDownloadError(
                        f"{where}: download passed the {TOTAL_DEADLINE_SECONDS}-second deadline")
                chunk = response.read1(CHUNK_BYTES)
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
                if total > MAX_BYTES:
                    raise GraphDownloadError(
                        f"{where}: file is over the {MAX_BYTES}-byte limit")
            data = b"".join(chunks)
            if declared is not None and len(data) < declared:
                raise GraphDownloadError(
                    f"{where}: download truncated, got {len(data)} of {declared} bytes")
    except _BadRedirect as e:
        raise GraphDownloadError(f"{where}: {e}") from e
    except urllib.error.HTTPError as e:
        raise GraphDownloadError(f"{where}: HTTP {e.code} {e.reason}") from e
    except http.client.IncompleteRead as e:
        raise GraphDownloadError(f"{where}: download truncated ({e})") from e
    except (urllib.error.URLError, http.client.HTTPException, OSError, ValueError) as e:
        # DNS, refused, TLS, timeout, invalid URL
        raise GraphDownloadError(f"{where}: download failed: {e}") from e

    if status != 200:
        raise GraphDownloadError(f"{where}: HTTP {status}, expected 200")
    base_type = content_type.split(";")[0].strip().lower()
    if base_type in ("text/html", "application/xhtml+xml"):
        raise NotAnImageError(
            f"{where}: server sent {content_type!r}, not an image — the link points at a web page")
    if not base_type.startswith("image/"):
        raise GraphDownloadError(
            f"{where}: server sent {content_type or 'no Content-Type'!r}, not an image — the "
            "link must point directly at the image file, not a web page")
    image_type = sniff_image_type(data)
    if image_type is None:
        raise GraphDownloadError(
            f"{where}: the bytes are not a PNG, JPEG, GIF or WebP image "
            f"(Content-Type claimed {content_type!r})")
    if not image_is_complete(data, image_type):
        raise GraphDownloadError(
            f"{where}: the {image_type} image is incomplete (the file ends early)")
    size = image_size(data, image_type)
    if size is None:
        raise GraphDownloadError(f"{where}: could not read the {image_type} image's dimensions")
    width, height = size
    if max(width, height) > MAX_SIDE_PIXELS:
        raise GraphDownloadError(
            f"{where}: image is {width}x{height} pixels, over the {MAX_SIDE_PIXELS}-pixel limit "
            "per side — its labels would be shrunk past legibility; link a smaller copy")

    os.makedirs(out_dir, exist_ok=True)
    image_path = os.path.abspath(os.path.join(out_dir, f"graph_{italic_index}.{image_type}"))
    # Temp file in the same directory, renamed only now that every check has passed.
    fd, temp_path = tempfile.mkstemp(dir=out_dir, prefix=f".graph_{italic_index}_", suffix=".part")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(temp_path, image_path)
    except BaseException:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise
    return {"image_path": image_path, "width": width, "height": height}
