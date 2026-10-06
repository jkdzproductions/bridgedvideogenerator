import json

import pytest

import graph_intake.build as build_mod
from graph_intake.build import collect_graph_readings, load_graph_readings, prepare_graph_readings
from graph_intake.reading_output import GraphReadingError

LINK = {"italic_index": 1, "text": "GDP per capita", "url": "https://i.redd.it/x.jpeg"}
READING = {
    "title": "GDP Per Capita", "subtitle": None, "graph_kind": "choropleth map",
    "unit": "US dollars", "source_line": "Source: IMF", "notes": None,
    "values": [{"label": "Guyana", "display": "$29K", "value": 29000, "readable": True}],
}


@pytest.fixture
def fake_download(monkeypatch):
    def fake(url, italic_text, italic_index, out_dir):
        path = f"{out_dir}/graph_{italic_index}.jpg"
        open(path, "wb").write(b"\xff\xd8\xff")
        return {"image_path": path, "width": 1080, "height": 1350}
    monkeypatch.setattr(build_mod, "download_graph_image", fake)


def test_prepare_downloads_and_writes_one_prompt_per_link(tmp_path, fake_download):
    manifest = prepare_graph_readings([LINK], str(tmp_path))

    assert manifest == [{"italic_index": 1, "italic_text": "GDP per capita", "url": LINK["url"],
                         "image_path": f"{tmp_path}/graph_inputs/graph_1.jpg",
                         "width": 1080, "height": 1350}]
    prompt = (tmp_path / "graph_reading_prompt_1.txt").read_text()
    assert f"{tmp_path}/graph_inputs/graph_1.jpg" in prompt
    assert not (tmp_path / "graph_readings.json").exists()


def test_prepare_with_no_links_writes_empty_readings(tmp_path):
    assert prepare_graph_readings([], str(tmp_path)) == []
    assert json.loads((tmp_path / "graph_readings.json").read_text()) == {}


def test_prepare_clears_a_previous_run(tmp_path, fake_download):
    (tmp_path / "graph_reading_response_1.txt").write_text("stale")
    (tmp_path / "graph_readings.json").write_text("{}")

    prepare_graph_readings([LINK], str(tmp_path))

    assert not (tmp_path / "graph_reading_response_1.txt").exists()
    assert not (tmp_path / "graph_readings.json").exists()


def test_collect_validates_responses_and_writes_readings(tmp_path, fake_download):
    prepare_graph_readings([LINK], str(tmp_path))
    (tmp_path / "graph_reading_response_1.txt").write_text("```json\n" + json.dumps(READING) + "\n```")

    readings = collect_graph_readings(str(tmp_path))

    assert readings[1]["reading"] == READING
    assert readings[1]["italic_text"] == "GDP per capita"
    on_disk = json.loads((tmp_path / "graph_readings.json").read_text())
    assert on_disk["1"]["image_path"] == f"{tmp_path}/graph_inputs/graph_1.jpg"


def test_collect_without_a_saved_response_raises(tmp_path, fake_download):
    prepare_graph_readings([LINK], str(tmp_path))

    with pytest.raises(GraphReadingError, match="'GDP per capita'.*no saved response"):
        collect_graph_readings(str(tmp_path))


def test_load_rejects_readings_from_another_script(tmp_path):
    (tmp_path / "graph_readings.json").write_text(json.dumps(
        {"0": {"italic_text": "x", "url": "https://a/x.png", "reading": READING}}))
    (tmp_path / "graph_links.json").write_text(json.dumps([LINK]))

    with pytest.raises(ValueError, match=r"left over from another script"):
        load_graph_readings(str(tmp_path / "graph_readings.json"), str(tmp_path / "graph_links.json"))


def test_load_returns_int_keys(tmp_path):
    (tmp_path / "graph_readings.json").write_text(json.dumps(
        {"1": {"italic_text": "GDP per capita", "url": LINK["url"], "reading": READING}}))
    (tmp_path / "graph_links.json").write_text(json.dumps([LINK]))

    readings = load_graph_readings(str(tmp_path / "graph_readings.json"), str(tmp_path / "graph_links.json"))

    assert list(readings) == [1]


def _old_key_link():
    return {"bold_index": 1, "text": "GDP per capita", "url": LINK["url"]}


def test_load_rejects_graph_links_with_pre_rename_keys(tmp_path):
    (tmp_path / "graph_readings.json").write_text(json.dumps(
        {"1": {"italic_text": "GDP per capita", "url": LINK["url"], "reading": READING}}))
    (tmp_path / "graph_links.json").write_text(json.dumps([_old_key_link()]))

    with pytest.raises(ValueError, match=r"italic_index.*re-run Stage 1 from Step 1a"):
        load_graph_readings(str(tmp_path / "graph_readings.json"), str(tmp_path / "graph_links.json"))


def test_load_rejects_graph_readings_with_pre_rename_keys(tmp_path):
    (tmp_path / "graph_readings.json").write_text(json.dumps(
        {"1": {"bold_text": "GDP per capita", "url": LINK["url"], "reading": READING}}))
    (tmp_path / "graph_links.json").write_text(json.dumps([LINK]))

    with pytest.raises(ValueError, match=r"italic_text.*re-run Stage 1 from Step 1a"):
        load_graph_readings(str(tmp_path / "graph_readings.json"), str(tmp_path / "graph_links.json"))


def test_collect_rejects_a_manifest_with_pre_rename_keys(tmp_path):
    inputs = tmp_path / "graph_inputs"
    inputs.mkdir()
    (inputs / "manifest.json").write_text(json.dumps([
        {"bold_index": 1, "bold_text": "GDP per capita", "url": LINK["url"]}]))

    with pytest.raises(ValueError, match=r"re-run Stage 1 from Step 1a"):
        collect_graph_readings(str(tmp_path))


def test_prepare_rejects_graph_links_with_pre_rename_keys_before_downloading(tmp_path, monkeypatch):
    def no_download(*a, **k):
        raise AssertionError("must not download")
    monkeypatch.setattr(build_mod, "download_graph_image", no_download)

    with pytest.raises(ValueError, match=r"re-run Stage 1 from Step 1a"):
        prepare_graph_readings([{"bold_index": 0, "text": "x", "url": "https://example.com/a.png"}],
                               out_dir=str(tmp_path))


from graph_intake.download import NotAnImageError

PAGE_LINK = {"italic_index": 2, "text": "a news story", "url": "https://example.com/story"}


@pytest.fixture
def fake_download_skipping_pages(monkeypatch):
    def fake(url, italic_text, italic_index, out_dir):
        if url == PAGE_LINK["url"]:
            raise NotAnImageError(f"linked graph for {italic_text!r} ({url}): server sent 'text/html', not an image")
        path = f"{out_dir}/graph_{italic_index}.jpg"
        open(path, "wb").write(b"\xff\xd8\xff")
        return {"image_path": path, "width": 10, "height": 10}
    monkeypatch.setattr(build_mod, "download_graph_image", fake)


def test_a_web_page_link_is_skipped_and_removed_from_graph_links(tmp_path, fake_download_skipping_pages):
    links = [LINK, PAGE_LINK]
    (tmp_path / "graph_links.json").write_text(json.dumps(links))

    manifest = prepare_graph_readings(links, str(tmp_path))

    assert [m["italic_index"] for m in manifest] == [1]
    assert json.loads((tmp_path / "skipped_page_links.json").read_text()) == [PAGE_LINK]
    assert json.loads((tmp_path / "graph_links.json").read_text()) == [LINK]
    assert not (tmp_path / "graph_reading_prompt_2.txt").exists()


def test_skipped_file_is_always_written_and_graph_links_untouched_when_nothing_skipped(tmp_path, fake_download):
    prepare_graph_readings([LINK], str(tmp_path))

    assert json.loads((tmp_path / "skipped_page_links.json").read_text()) == []
    assert not (tmp_path / "graph_links.json").exists()


def test_every_link_skipped_still_writes_empty_readings_and_empty_graph_links(tmp_path, fake_download_skipping_pages):
    (tmp_path / "graph_links.json").write_text(json.dumps([PAGE_LINK]))

    assert prepare_graph_readings([PAGE_LINK], str(tmp_path)) == []

    assert json.loads((tmp_path / "graph_readings.json").read_text()) == {}
    assert json.loads((tmp_path / "graph_links.json").read_text()) == []


def test_a_previous_runs_skipped_file_is_cleared(tmp_path, fake_download):
    (tmp_path / "skipped_page_links.json").write_text('[{"stale": 1}]')

    prepare_graph_readings([], str(tmp_path))

    assert json.loads((tmp_path / "skipped_page_links.json").read_text()) == []
