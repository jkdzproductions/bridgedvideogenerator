import json

from script_input.prepare import prepare_script_input
from tests.docx_builders import add_hyperlink, add_run, new_document, save

IMG = "https://example.com/maps/atlanta.jpg"


def _docx(tmp_path):
    doc = new_document()
    p = doc.add_paragraph()
    add_run(p, "See ")
    add_hyperlink(p, IMG, [("the map", False)])
    add_run(p, " now.")
    return save(doc, tmp_path)


def test_a_docx_writes_image_links_json(tmp_path):
    out = tmp_path / "out"

    result = prepare_script_input(_docx(tmp_path), str(out))

    expected = [{"italic_index": 0, "text": "the map", "url": IMG}]
    assert list(result.image_links) == expected
    assert json.loads((out / "image_links.json").read_text()) == expected
    assert (out / "script_marked.txt").read_text() == "See *the map* now."


def test_a_text_script_has_no_image_links_and_a_stale_file_is_removed(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "image_links.json").write_text('[{"stale": true}]')
    script = tmp_path / "script.txt"
    script.write_text("Plain words here.")

    prepare_script_input(str(script), str(out))

    assert json.loads((out / "image_links.json").read_text()) == []


def test_a_new_run_removes_the_previous_videos_image_readings_and_stills(tmp_path):
    out = tmp_path / "out"
    (out / "image_stills").mkdir(parents=True)
    (out / "image_stills" / "image_0.jpg").write_bytes(b"old")
    (out / "image_readings.json").write_text('{"0": {"stale": true}}')

    prepare_script_input(_docx(tmp_path), str(out))

    assert not (out / "image_readings.json").exists()
    assert not (out / "image_stills").exists()
