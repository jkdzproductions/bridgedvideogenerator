import json
import os
import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

pytest.importorskip("docx")

from assembly.beats import resolve_beat_clips  # noqa: E402
from assembly.build import assemble  # noqa: E402
from graph_intake.build import prepare_graph_readings  # noqa: E402
from image_intake.build import load_image_readings, prepare_image_readings  # noqa: E402
from script_input.prepare import prepare_script_input  # noqa: E402
from shot_list.align import WordTiming  # noqa: E402
from shot_list.build import assemble_shot_list, prepare_director_input  # noqa: E402
from shot_list.director_output import parse_director_output  # noqa: E402
from shot_list.markup import parse_markup  # noqa: E402
from shot_list.models import ImageSpec, validate_shot_list  # noqa: E402
from tests.docx_builders import add_hyperlink, add_run, new_document, save  # noqa: E402

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


@pytest.fixture
def site(tmp_path):
    png = tmp_path / "served.png"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=orange:s=570x631",
                    "-frames:v", "1", str(png)], check=True)
    body = png.read_bytes()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", body
    httpd.shutdown()
    httpd.server_close()


def test_an_image_link_in_a_docx_script_becomes_the_original_image_in_the_final_video(tmp_path, monkeypatch, site):
    base_url, served = site
    monkeypatch.chdir(tmp_path)
    doc = new_document()
    p = doc.add_paragraph()
    add_run(p, "Tiny island here. ")
    add_run(p, "Hold on.", bold=True)  # a talking-head span before the image phrase must not shift its index
    add_run(p, " ")
    add_hyperlink(p, f"{base_url}/maps/atlanta.png", [("a very old map", False)])
    add_run(p, " shows it now.")
    script = save(doc, tmp_path)

    # Steps 1a, 1b-i (no graphs), 1d
    result = prepare_script_input(script)
    assert [l["text"] for l in result.image_links] == ["a very old map"]
    assert result.links == [] and list(result.page_links) == []
    assert prepare_graph_readings(json.load(open("graph_links.json"))) == []
    prepare_image_readings(json.load(open("image_links.json")))
    image_readings = load_image_readings("image_readings.json", "image_links.json")
    assert open("image_stills/image_0.png", "rb").read() == served  # the original bytes, untouched

    # Steps 2-6 with synthetic timings and a canned director answer
    parsed = parse_markup(open("script_marked.txt").read())
    segments, prompt = prepare_director_input(
        parsed.plain_text, parsed.graphic_spans, {}, parsed.talking_head_spans, None, image_readings)
    assert [s.kind for s in segments] == ["plain", "talking_head", "image", "plain"]
    timings = [WordTiming(w, i * 0.5, i * 0.5 + 0.4, matched=True) for i, w in enumerate(parsed.plain_text.split())]
    total = round(timings[-1].end + 0.3, 3)
    raw = json.dumps({"count": 4, "entries": [
        {"index": 0, "type": "footage", "query": "island", "subject": "an island"},
        {"index": 1, "type": "talking_head"},
        {"index": 2, "type": "image"},
        {"index": 3, "type": "footage", "query": "ocean", "subject": "the ocean"}]})
    specs = parse_director_output(raw, segments)
    shot_list = assemble_shot_list(segments, parsed.plain_text, timings, specs, total)
    validate_shot_list(shot_list)
    assert [b.image for b in shot_list.beats if b.type == "image"] == [ImageSpec(italic_index=0)]

    # Stage 4: stand-in footage clips; talking-head and image beats need nothing else
    os.makedirs("footage_output")
    for i, beat in enumerate(shot_list.beats):
        if beat.type == "footage":
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=white:s=640x360:r=30",
                            "-t", str(beat.end - beat.start + 1), "-c:v", "libx264", "-pix_fmt", "yuv420p",
                            f"footage_output/beat_{i}.mp4"], check=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
                    "-t", str(total), "voice.wav"], check=True)
    clips = resolve_beat_clips(shot_list)
    assert {c.type for c in clips} == {"footage", "talking_head", "image"}
    final = assemble(clips=clips, audio_path="voice.wav", staging_dir="assembly_staging",
                     final_path="final_output/assembled.mp4", total_duration=shot_list.duration)

    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", final],
                           capture_output=True, text=True, check=True).stdout.strip()
    assert abs(float(probe) - total) < 0.1
