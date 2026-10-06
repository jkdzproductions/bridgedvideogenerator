import json

import pytest

import page_intake.build as build_mod
from page_intake.build import load_page_readings, prepare_page_readings
from page_intake.capture import PageCaptureError

LINKS = [
    {"italic_index": 1, "text": "less than 40 people", "url": "https://example.com/a#:~:text=less"},
    {"italic_index": 3, "text": "a second story", "url": "https://example.com/b#:~:text=second"},
]


@pytest.fixture
def fake_capture(monkeypatch):
    calls = []

    def fake(url, out_dir, italic_index):
        calls.append((url, italic_index))
        return {"passage": f"passage {italic_index}", "title": f"Title {italic_index}",
                "still_path": f"{out_dir}/page_stills/page_{italic_index}.png",
                "plain_path": f"{out_dir}/page_stills/page_{italic_index}_plain.png",
                "uncovered": [], "rects": [[0, 0, 1, 1]]}
    monkeypatch.setattr(build_mod, "capture_page", fake)
    return calls


def test_prepare_captures_each_link_and_writes_readings(tmp_path, fake_capture):
    readings = prepare_page_readings(LINKS, str(tmp_path))

    assert fake_capture == [(LINKS[0]["url"], 1), (LINKS[1]["url"], 3)]
    assert set(readings) == {1, 3}
    assert readings[3]["italic_text"] == "a second story"
    assert readings[3]["passage"] == "passage 3"
    assert "rects" not in readings[3]
    on_disk = json.loads((tmp_path / "page_readings.json").read_text())
    assert set(on_disk) == {"1", "3"}


def test_no_links_writes_empty_readings_and_clears_the_previous_run(tmp_path, fake_capture):
    (tmp_path / "page_stills").mkdir()
    (tmp_path / "page_stills" / "page_9.png").write_bytes(b"stale")
    (tmp_path / "page_readings.json").write_text('{"9": {}}')

    assert prepare_page_readings([], str(tmp_path)) == {}

    assert json.loads((tmp_path / "page_readings.json").read_text()) == {}
    assert not (tmp_path / "page_stills" / "page_9.png").exists()


def test_a_capture_failure_names_the_phrase_and_url_and_writes_no_readings(tmp_path, monkeypatch):
    def failing(url, out_dir, italic_index):
        raise PageCaptureError("the page answered HTTP 403 (blocked, paywalled or missing)")
    monkeypatch.setattr(build_mod, "capture_page", failing)

    with pytest.raises(PageCaptureError, match=r"page highlight for 'less than 40 people' \(https://example.com/a.*HTTP 403"):
        prepare_page_readings(LINKS, str(tmp_path))
    assert not (tmp_path / "page_readings.json").exists()


def test_load_returns_int_keys_when_files_agree(tmp_path, fake_capture):
    prepare_page_readings(LINKS, str(tmp_path))
    (tmp_path / "page_links.json").write_text(json.dumps(LINKS))

    readings = load_page_readings(str(tmp_path / "page_readings.json"), str(tmp_path / "page_links.json"))

    assert sorted(readings) == [1, 3]


def test_load_rejects_readings_left_over_from_another_script(tmp_path, fake_capture):
    prepare_page_readings(LINKS, str(tmp_path))
    (tmp_path / "page_links.json").write_text(json.dumps(LINKS[:1]))

    with pytest.raises(ValueError, match="left over from another script"):
        load_page_readings(str(tmp_path / "page_readings.json"), str(tmp_path / "page_links.json"))


def test_load_rejects_a_changed_url(tmp_path, fake_capture):
    prepare_page_readings(LINKS, str(tmp_path))
    changed = [dict(LINKS[0], url="https://example.com/other#:~:text=x"), LINKS[1]]
    (tmp_path / "page_links.json").write_text(json.dumps(changed))

    with pytest.raises(ValueError, match="left over from another script"):
        load_page_readings(str(tmp_path / "page_readings.json"), str(tmp_path / "page_links.json"))
