import os
import pytest
from footage.download import DownloadError, download_file, download_thumbnails, download_winning_video
from footage.pexels import PexelsCandidate, VideoFile


class FakeStreamResponse:
    def __init__(self, status_code: int, chunks: list[bytes]):
        self.status_code = status_code
        self._chunks = chunks

    def iter_content(self, chunk_size):
        yield from self._chunks


def test_download_file_writes_streamed_content(tmp_path, monkeypatch):
    import footage.download as download_mod

    monkeypatch.setattr(
        download_mod.requests, "get",
        lambda *a, **kw: FakeStreamResponse(200, [b"hello ", b"world"]),
    )

    dest = tmp_path / "sub" / "out.bin"
    download_file("https://example.com/f.bin", str(dest))

    assert dest.read_bytes() == b"hello world"


def test_download_file_raises_on_non_200(monkeypatch):
    import footage.download as download_mod

    monkeypatch.setattr(
        download_mod.requests, "get",
        lambda *a, **kw: FakeStreamResponse(404, []),
    )

    with pytest.raises(DownloadError, match="404"):
        download_file("https://example.com/missing.bin", "/tmp/whatever.bin")


def test_download_thumbnails_maps_candidate_id_to_local_path(tmp_path, monkeypatch):
    import footage.download as download_mod

    monkeypatch.setattr(
        download_mod, "download_file",
        lambda url, dest: open(dest, "wb").write(b"fake-jpg"),
    )

    candidates = [
        PexelsCandidate(1, "url1", "https://img/1.jpg", 10, 100, 100, []),
        PexelsCandidate(2, "url2", "https://img/2.jpg", 10, 100, 100, []),
    ]

    paths = download_thumbnails(candidates, str(tmp_path))

    assert set(paths.keys()) == {1, 2}
    assert os.path.exists(paths[1])
    assert os.path.exists(paths[2])


def test_download_thumbnails_returns_absolute_paths_for_relative_out_dir(tmp_path, monkeypatch):
    import footage.download as download_mod

    written = []
    monkeypatch.setattr(download_mod, "download_file", lambda url, dest: written.append(dest))
    monkeypatch.chdir(tmp_path)

    candidates = [PexelsCandidate(7, "url7", "https://img/7.jpg", 10, 100, 100, [])]
    paths = download_thumbnails(candidates, "thumbnails/beat_3")

    # The scoring subagent's Read tool needs absolute paths to open these reliably.
    assert os.path.isabs(paths[7])
    assert paths[7] == str(tmp_path / "thumbnails" / "beat_3" / "7.jpg")
    assert written == [paths[7]]


def test_download_winning_video_picks_best_file_and_downloads_it(tmp_path, monkeypatch):
    import footage.download as download_mod

    calls = []
    monkeypatch.setattr(
        download_mod, "download_file",
        lambda url, dest: calls.append((url, dest)) or open(dest, "wb").write(b"fake-mp4"),
    )

    candidate = PexelsCandidate(
        1, "url1", "thumb.jpg", 10, 1920, 1080,
        video_files=[
            VideoFile("sd", "video/mp4", 640, 360, "sd.mp4"),
            VideoFile("hd", "video/mp4", 1920, 1080, "hd.mp4"),
        ],
    )

    dest = str(tmp_path / "beat_0.mp4")
    result = download_winning_video(candidate, dest)

    assert result == dest
    assert calls == [("hd.mp4", dest)]
