import json
import os

import pytest

import image_intake.build as build_mod
from graph_intake.download import GraphDownloadError, NotAnImageError
from image_intake.build import ImageIntakeError, load_image_readings, prepare_image_readings
from image_intake.paths import find_image_still

LINKS = [
    {"italic_index": 1, "text": "the old map", "url": "https://example.com/map.jpg"},
    {"italic_index": 4, "text": "a second picture", "url": "https://example.com/two.png"},
]


@pytest.fixture
def fake_download(monkeypatch):
    calls = []

    def fake(url, italic_text, italic_index, out_dir):
        calls.append((url, italic_text, italic_index))
        ext = "png" if url.endswith(".png") else "jpg"
        path = os.path.join(out_dir, f"graph_{italic_index}.{ext}")
        with open(path, "wb") as f:
            f.write(b"image-bytes")
        return {"image_path": os.path.abspath(path), "width": 570, "height": 631}
    monkeypatch.setattr(build_mod, "download_graph_image", fake)
    return calls


def test_prepare_fetches_each_link_and_writes_readings(tmp_path, fake_download):
    readings = prepare_image_readings(LINKS, str(tmp_path))

    assert fake_download == [("https://example.com/map.jpg", "the old map", 1),
                             ("https://example.com/two.png", "a second picture", 4)]
    assert sorted(readings) == [1, 4]
    assert readings[1]["still_path"] == str(tmp_path / "image_stills" / "image_1.jpg")
    assert readings[4]["still_path"] == str(tmp_path / "image_stills" / "image_4.png")
    assert readings[1]["italic_text"] == "the old map" and readings[1]["width"] == 570
    assert (tmp_path / "image_stills" / "image_1.jpg").read_bytes() == b"image-bytes"  # original bytes, untouched
    assert not (tmp_path / "image_stills" / "graph_1.jpg").exists()  # renamed, not copied
    on_disk = json.loads((tmp_path / "image_readings.json").read_text())
    assert sorted(on_disk) == ["1", "4"] and on_disk["4"]["url"] == "https://example.com/two.png"


def test_no_links_writes_an_empty_readings_file_and_clears_the_previous_video(tmp_path, fake_download):
    (tmp_path / "image_stills").mkdir()
    (tmp_path / "image_stills" / "image_9.jpg").write_bytes(b"old")
    (tmp_path / "image_readings.json").write_text('{"9": {}}')

    assert prepare_image_readings([], str(tmp_path)) == {}

    assert json.loads((tmp_path / "image_readings.json").read_text()) == {}
    assert not (tmp_path / "image_stills" / "image_9.jpg").exists()


def test_a_failed_download_names_the_phrase_and_url_and_leaves_no_readings(tmp_path, monkeypatch):
    def refuse(url, italic_text, italic_index, out_dir):
        raise GraphDownloadError(f"linked graph for {italic_text!r} ({url}): HTTP 403 Forbidden")
    monkeypatch.setattr(build_mod, "download_graph_image", refuse)

    with pytest.raises(ImageIntakeError) as exc_info:
        prepare_image_readings(LINKS, str(tmp_path))

    message = str(exc_info.value)
    assert "'the old map'" in message and "https://example.com/map.jpg" in message and "403" in message
    assert not (tmp_path / "image_readings.json").exists()


def test_a_link_that_turns_out_to_be_a_web_page_stops_the_run(tmp_path, monkeypatch):
    def html(url, italic_text, italic_index, out_dir):
        raise NotAnImageError(f"linked graph for {italic_text!r} ({url}): server sent 'text/html'")
    monkeypatch.setattr(build_mod, "download_graph_image", html)

    with pytest.raises(ImageIntakeError, match="text/html"):
        prepare_image_readings(LINKS, str(tmp_path))


def test_load_matches_readings_to_links(tmp_path, fake_download):
    prepare_image_readings(LINKS, str(tmp_path))
    (tmp_path / "image_links.json").write_text(json.dumps(LINKS))

    readings = load_image_readings(str(tmp_path / "image_readings.json"), str(tmp_path / "image_links.json"))

    assert sorted(readings) == [1, 4]


def test_load_refuses_readings_left_over_from_another_script(tmp_path, fake_download):
    prepare_image_readings(LINKS, str(tmp_path))
    (tmp_path / "image_links.json").write_text(json.dumps(LINKS[:1]))  # this script has only one image

    with pytest.raises(ValueError, match="left over from another script"):
        load_image_readings(str(tmp_path / "image_readings.json"), str(tmp_path / "image_links.json"))


def test_load_refuses_a_reading_whose_url_changed(tmp_path, fake_download):
    prepare_image_readings(LINKS, str(tmp_path))
    changed = [dict(LINKS[0], url="https://example.com/other.jpg"), LINKS[1]]
    (tmp_path / "image_links.json").write_text(json.dumps(changed))

    with pytest.raises(ValueError, match="left over from another script"):
        load_image_readings(str(tmp_path / "image_readings.json"), str(tmp_path / "image_links.json"))


def test_find_image_still_returns_none_when_missing_and_the_path_when_present(tmp_path):
    assert find_image_still(2, str(tmp_path)) is None
    (tmp_path / "image_stills").mkdir()
    (tmp_path / "image_stills" / "image_2.webp").write_bytes(b"x")

    assert find_image_still(2, str(tmp_path)) == os.path.join(str(tmp_path), "image_stills", "image_2.webp")
    assert find_image_still(3, str(tmp_path)) is None
