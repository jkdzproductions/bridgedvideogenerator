import os
import struct
import threading
import time
import zlib
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

import graph_intake.download as download_mod
from graph_intake.download import (
    GraphDownloadError, download_graph_image, image_is_complete, image_size, sniff_image_type)


def _png(width=4, height=3):
    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + b"\x00\x00\x00" * width for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw))
            + chunk(b"IEND", b""))


def _jpeg_header(width, height):
    # SOI, an APP0 segment, then a baseline SOF0 frame header carrying the size.
    app0 = b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    sof0 = b"\xff\xc0" + struct.pack(">HBHHB", 11, 8, height, width, 1) + b"\x01\x11\x00"
    return b"\xff\xd8" + app0 + sof0 + b"\xff\xd9"


@pytest.fixture
def server():
    """A local HTTP server: routes[path] = (status, headers, body). Records request headers."""
    routes, seen = {}, []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append(dict(self.headers))
            if self.path not in routes:
                self.send_error(404, "Not Found")
                return
            status, headers, body = routes[self.path]
            self.send_response(status)
            for key, value in headers.items():
                self.send_header(key, value)
            self.end_headers()
            try:
                if callable(body):
                    body(self.wfile)
                else:
                    self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, *args):
            pass

    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", routes, seen
    httpd.shutdown()
    httpd.server_close()


def test_downloads_an_image_named_by_its_real_type(server, tmp_path):
    base, routes, seen = server
    routes["/chart.jpeg"] = (200, {"Content-Type": "image/png"}, _png())

    result = download_graph_image(f"{base}/chart.jpeg", "GDP per capita", 2, str(tmp_path / "graph_inputs"))

    assert result == {"image_path": str(tmp_path / "graph_inputs" / "graph_2.png"), "width": 4, "height": 3}
    assert os.path.isabs(result["image_path"])
    assert open(result["image_path"], "rb").read() == _png()
    assert seen[0]["User-Agent"] == download_mod.USER_AGENT


def test_web_page_instead_of_image_raises_naming_phrase_and_url(server, tmp_path):
    base, routes, _ = server
    routes["/post"] = (200, {"Content-Type": "text/html; charset=utf-8"}, b"<html>chart</html>")

    with pytest.raises(GraphDownloadError, match=r"'GDP per capita'.*/post.*not an image"):
        download_graph_image(f"{base}/post", "GDP per capita", 0, str(tmp_path))
    assert os.listdir(tmp_path) == []


def test_image_content_type_with_non_image_bytes_raises(server, tmp_path):
    base, routes, _ = server
    routes["/fake.png"] = (200, {"Content-Type": "image/png"}, b"<html>not really</html>")

    with pytest.raises(GraphDownloadError, match="not a PNG, JPEG, GIF or WebP"):
        download_graph_image(f"{base}/fake.png", "GDP", 0, str(tmp_path))


def test_404_raises(server, tmp_path):
    base, _, _ = server

    with pytest.raises(GraphDownloadError, match=r"'GDP'.*HTTP 404"):
        download_graph_image(f"{base}/missing.png", "GDP", 0, str(tmp_path))


def test_oversize_by_content_length_raises(server, tmp_path, monkeypatch):
    base, routes, _ = server
    monkeypatch.setattr(download_mod, "MAX_BYTES", 100)
    routes["/big.png"] = (200, {"Content-Type": "image/png", "Content-Length": "5000"}, _png() + b"\x00" * 4900)

    with pytest.raises(GraphDownloadError, match="over the 100-byte limit"):
        download_graph_image(f"{base}/big.png", "GDP", 0, str(tmp_path))


def test_oversize_without_content_length_raises(server, tmp_path, monkeypatch):
    base, routes, _ = server
    monkeypatch.setattr(download_mod, "MAX_BYTES", 100)
    routes["/big.png"] = (200, {"Content-Type": "image/png"}, _png() + b"\x00" * 4900)

    with pytest.raises(GraphDownloadError, match="over the 100-byte limit"):
        download_graph_image(f"{base}/big.png", "GDP", 0, str(tmp_path))


def test_unreachable_host_raises(tmp_path):
    with pytest.raises(GraphDownloadError, match="download failed"):
        download_graph_image("http://127.0.0.1:9/x.png", "GDP", 0, str(tmp_path))


# --- Review Focus pins ---------------------------------------------------------------------


def test_redirect_and_query_string_are_followed(server, tmp_path):
    base, routes, _ = server
    routes["/i/chart?width=1080&s=abc"] = (302, {"Location": "/real/chart.png?sig=1"}, b"")
    routes["/real/chart.png?sig=1"] = (200, {"Content-Type": "image/png"}, _png())

    result = download_graph_image(f"{base}/i/chart?width=1080&s=abc", "GDP", 1, str(tmp_path))

    assert result["image_path"].endswith("graph_1.png")


def test_huge_image_dimensions_raise(server, tmp_path):
    base, routes, _ = server
    routes["/tall.jpg"] = (200, {"Content-Type": "image/jpeg"}, _jpeg_header(1200, 9000))

    with pytest.raises(GraphDownloadError, match="1200x9000 pixels"):
        download_graph_image(f"{base}/tall.jpg", "GDP", 0, str(tmp_path))


def test_sniff_and_size_helpers():
    assert sniff_image_type(_png()) == "png"
    assert sniff_image_type(_jpeg_header(10, 20)) == "jpg"
    assert sniff_image_type(b"GIF89a" + struct.pack("<HH", 7, 5)) == "gif"
    assert sniff_image_type(b"<svg xmlns=...>") is None
    assert image_size(_png(4, 3), "png") == (4, 3)
    assert image_size(_jpeg_header(10, 20), "jpg") == (10, 20)
    assert image_size(b"GIF89a" + struct.pack("<HH", 7, 5), "gif") == (7, 5)


# --- Fix round 1 ---------------------------------------------------------------------------


def test_body_shorter_than_declared_content_length_raises(server, tmp_path):
    base, routes, _ = server
    routes["/short.png"] = (200, {"Content-Type": "image/png", "Content-Length": "100000"}, _png())

    with pytest.raises(GraphDownloadError, match=r"'GDP'.*/short.png.*(truncated|incomplete)"):
        download_graph_image(f"{base}/short.png", "GDP", 0, str(tmp_path))
    assert os.listdir(tmp_path) == []


@pytest.mark.parametrize("keep", [60, 33])
def test_truncated_png_without_content_length_raises(server, tmp_path, keep):
    base, routes, _ = server
    routes["/cut.png"] = (200, {"Content-Type": "image/png"}, _png(50, 50)[:keep])

    with pytest.raises(GraphDownloadError, match=r"'GDP'.*/cut.png.*incomplete"):
        download_graph_image(f"{base}/cut.png", "GDP", 0, str(tmp_path))
    assert os.listdir(tmp_path) == []


def test_image_is_complete_per_type():
    assert image_is_complete(_png(), "png")
    assert not image_is_complete(_png()[:-1], "png")
    assert image_is_complete(_jpeg_header(10, 20), "jpg")
    assert not image_is_complete(_jpeg_header(10, 20)[:-2], "jpg")
    gif = b"GIF89a" + struct.pack("<HH", 7, 5) + b"\x00\x00\x00"
    assert image_is_complete(gif + b";", "gif")
    assert not image_is_complete(gif, "gif")
    webp = b"RIFF" + struct.pack("<I", 4 + 6) + b"WEBP" + b"abcdef"
    assert image_is_complete(webp, "webp")
    assert not image_is_complete(webp[:-2], "webp")
    assert not image_is_complete(webp + b"zz", "webp")


def test_failure_removes_stale_file_from_earlier_success(server, tmp_path):
    base, routes, _ = server
    routes["/ok.png"] = (200, {"Content-Type": "image/png"}, _png())
    download_graph_image(f"{base}/ok.png", "GDP", 0, str(tmp_path))
    assert os.listdir(tmp_path) == ["graph_0.png"]

    with pytest.raises(GraphDownloadError, match="HTTP 404"):
        download_graph_image(f"{base}/missing.png", "GDP", 0, str(tmp_path))
    assert os.listdir(tmp_path) == []


def test_new_type_replaces_old_type_for_same_index(server, tmp_path):
    base, routes, _ = server
    routes["/a.jpg"] = (200, {"Content-Type": "image/jpeg"}, _jpeg_header(10, 20))
    routes["/b.png"] = (200, {"Content-Type": "image/png"}, _png())
    download_graph_image(f"{base}/a.jpg", "GDP", 1, str(tmp_path))
    download_graph_image(f"{base}/b.png", "GDP", 1, str(tmp_path))

    assert os.listdir(tmp_path) == ["graph_1.png"]


def test_other_indexes_are_left_alone(server, tmp_path):
    base, routes, _ = server
    routes["/ok.png"] = (200, {"Content-Type": "image/png"}, _png())
    download_graph_image(f"{base}/ok.png", "GDP", 10, str(tmp_path))
    download_graph_image(f"{base}/ok.png", "GDP", 1, str(tmp_path))

    assert sorted(os.listdir(tmp_path)) == ["graph_1.png", "graph_10.png"]


def test_slow_drip_hits_total_deadline(server, tmp_path, monkeypatch):
    base, routes, _ = server
    monkeypatch.setattr(download_mod, "TIMEOUT_SECONDS", 5)
    monkeypatch.setattr(download_mod, "TOTAL_DEADLINE_SECONDS", 1)

    def drip(wfile):
        for _ in range(100):
            wfile.write(b"\x00")
            wfile.flush()
            time.sleep(0.2)

    routes["/slow.png"] = (200, {"Content-Type": "image/png", "Content-Length": "100"}, drip)

    start = time.monotonic()
    with pytest.raises(GraphDownloadError, match=r"'GDP'.*/slow.png.*deadline"):
        download_graph_image(f"{base}/slow.png", "GDP", 0, str(tmp_path))
    assert time.monotonic() - start < 4
    assert os.listdir(tmp_path) == []


def test_url_with_space_and_unicode_is_quoted(server, tmp_path):
    base, routes, _ = server
    routes["/my%20charts/caf%C3%A9.png?a=b%20c"] = (200, {"Content-Type": "image/png"}, _png())

    result = download_graph_image(f"{base}/my charts/café.png?a=b c", "GDP", 0, str(tmp_path))

    assert result["image_path"].endswith("graph_0.png")


def test_already_encoded_url_is_not_double_encoded(server, tmp_path):
    base, routes, _ = server
    routes["/my%20chart.png?sig=a%2Fb"] = (200, {"Content-Type": "image/png"}, _png())

    result = download_graph_image(f"{base}/my%20chart.png?sig=a%2Fb", "GDP", 0, str(tmp_path))

    assert result["image_path"].endswith("graph_0.png")


def test_malformed_url_raises_graph_download_error(tmp_path):
    with pytest.raises(GraphDownloadError, match=r"'GDP'.*http://\[bad"):
        download_graph_image("http://[bad/x.png", "GDP", 0, str(tmp_path))


def test_redirect_to_non_http_scheme_is_refused(server, tmp_path):
    base, routes, _ = server
    routes["/go"] = (302, {"Location": "ftp://127.0.0.1/x.png"}, b"")

    with pytest.raises(GraphDownloadError, match=r"'GDP'.*/go.*ftp"):
        download_graph_image(f"{base}/go", "GDP", 0, str(tmp_path))


def test_web_page_raises_the_not_an_image_subclass(server, tmp_path):
    base, routes, _ = server
    routes["/post"] = (200, {"Content-Type": "text/html; charset=utf-8"}, b"<html>chart</html>")

    with pytest.raises(download_mod.NotAnImageError):
        download_graph_image(f"{base}/post", "GDP per capita", 0, str(tmp_path))


def test_a_pdf_is_still_a_plain_download_error(server, tmp_path):
    base, routes, _ = server
    routes["/doc.pdf"] = (200, {"Content-Type": "application/pdf"}, b"%PDF-1.4")

    with pytest.raises(GraphDownloadError) as exc_info:
        download_graph_image(f"{base}/doc.pdf", "GDP", 0, str(tmp_path))
    assert not isinstance(exc_info.value, download_mod.NotAnImageError)
