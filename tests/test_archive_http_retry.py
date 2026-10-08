# tests/test_archive_http_retry.py
"""Bounded retry with exponential backoff for the archive HTTP helpers (get_json and fetch_to_file).

Live finding (2026-10-07/08): Wikimedia Commons answered 429 on 27 thumbnail downloads and the Library of
Congress gave 520s and IncompleteRead broken downloads; every one was dropped on the first failure."""
import http.client

import pytest
import requests

import footage.archive_types as types_mod
from footage.archive_types import ArchiveError, MAX_ATTEMPTS, fetch_to_file, get_json


class _Resp:
    def __init__(self, status=200, headers=None, body=(b"ab", b"cd"), json_value=None, text=""):
        self.status_code = status
        self.headers = headers or {}
        self._body = body
        self._json = {"ok": 1} if json_value is None else json_value
        self.text = text
        self.closed = False

    def json(self):
        return self._json

    def iter_content(self, chunk_size):
        for chunk in self._body:
            if isinstance(chunk, Exception):
                raise chunk
            yield chunk

    def close(self):
        self.closed = True


def _script(monkeypatch, outcomes):
    """requests.get returns (or raises) each outcome in turn; sleeps are recorded, never slept."""
    calls, sleeps = [], []

    def fake_get(*a, **k):
        calls.append(a[0] if a else k.get("url"))
        outcome = outcomes[len(calls) - 1]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(types_mod.requests, "get", fake_get)
    monkeypatch.setattr(types_mod.time, "sleep", sleeps.append)
    return calls, sleeps


def test_there_are_four_attempts_in_all():
    assert MAX_ATTEMPTS == 4


# --- get_json -----------------------------------------------------------------------------------

def test_get_json_retries_a_429_and_honors_retry_after(monkeypatch):
    calls, sleeps = _script(monkeypatch, [_Resp(429, {"Retry-After": "7"}), _Resp(200)])

    assert get_json("https://commons.example/api", {}) == {"ok": 1}
    assert len(calls) == 2 and sleeps == [7.0]


def test_get_json_backs_off_exponentially_without_retry_after(monkeypatch):
    calls, sleeps = _script(monkeypatch, [_Resp(520), _Resp(503), _Resp(502), _Resp(200)])

    assert get_json("https://loc.example/photos/", {}) == {"ok": 1}
    assert sleeps == [2.0, 4.0, 8.0]


def test_get_json_caps_a_huge_retry_after(monkeypatch):
    _, sleeps = _script(monkeypatch, [_Resp(429, {"Retry-After": "3600"}), _Resp(200)])

    get_json("https://commons.example/api", {})
    assert sleeps == [types_mod.MAX_BACKOFF_SECONDS]


def test_get_json_gives_up_after_the_last_attempt_and_names_status_and_rate_limit_headers(monkeypatch):
    headers = {"Retry-After": "1", "x-ratelimit-limit": "600000;w=60", "Content-Type": "text/html"}
    calls, sleeps = _script(monkeypatch, [_Resp(429, headers, text="slow down")] * MAX_ATTEMPTS)

    with pytest.raises(ArchiveError) as info:
        get_json("https://commons.example/api", {})

    message = str(info.value)
    assert len(calls) == MAX_ATTEMPTS and len(sleeps) == MAX_ATTEMPTS - 1
    assert "429" in message and "Retry-After: 1" in message and "x-ratelimit-limit: 600000;w=60" in message
    assert "Content-Type" not in message  # only the rate-limit headers are logged
    assert f"{MAX_ATTEMPTS} attempts" in message


def test_get_json_never_retries_a_404(monkeypatch):
    calls, sleeps = _script(monkeypatch, [_Resp(404), _Resp(200)])

    with pytest.raises(ArchiveError, match="404"):
        get_json("https://x.example/api", {})
    assert len(calls) == 1 and sleeps == []


def test_get_json_retries_timeouts_and_connection_errors(monkeypatch):
    calls, sleeps = _script(monkeypatch, [requests.Timeout("slow"), requests.ConnectionError("reset"), _Resp(200)])

    assert get_json("https://x.example/api", {}) == {"ok": 1}
    assert sleeps == [2.0, 4.0]


def test_get_json_retry_warnings_are_printed(monkeypatch, capsys):
    _script(monkeypatch, [_Resp(429, {"x-ratelimit-reset": "7"}), _Resp(200)])

    get_json("https://commons.example/api", {})
    out = capsys.readouterr().out
    assert "WARNING" in out and "429" in out and "x-ratelimit-reset: 7" in out and "retrying in 2" in out


# --- fetch_to_file ------------------------------------------------------------------------------

def test_fetch_to_file_retries_a_429_then_writes_the_file(monkeypatch, tmp_path):
    calls, sleeps = _script(monkeypatch, [_Resp(429, {"Retry-After": "3"}), _Resp(200)])
    dest = tmp_path / "t.jpg"

    assert fetch_to_file("https://upload.example/x.jpg", str(dest)) == str(dest)
    assert dest.read_bytes() == b"abcd" and sleeps == [3.0] and len(calls) == 2


def test_fetch_to_file_retries_an_incomplete_read_mid_download_and_leaves_no_partial_file(monkeypatch, tmp_path):
    broken = requests.exceptions.ChunkedEncodingError(http.client.IncompleteRead(b"ab", 10))
    calls, sleeps = _script(monkeypatch, [_Resp(200, body=(b"ab", broken)), _Resp(200, body=(b"whole",))])
    dest = tmp_path / "t.jpg"

    fetch_to_file("https://tile.example/x.jpg", str(dest))
    assert dest.read_bytes() == b"whole" and sleeps == [2.0]


def test_fetch_to_file_retries_a_raw_incomplete_read(monkeypatch, tmp_path):
    _, sleeps = _script(monkeypatch, [_Resp(200, body=(http.client.IncompleteRead(b"a", 5),)), _Resp(200)])

    fetch_to_file("https://tile.example/x.jpg", str(tmp_path / "t.jpg"))
    assert sleeps == [2.0]


def test_fetch_to_file_treats_a_short_body_as_incomplete(monkeypatch, tmp_path):
    short = _Resp(200, headers={"Content-Length": "10"}, body=(b"abc",))
    _, sleeps = _script(monkeypatch, [short, _Resp(200, headers={"Content-Length": "4"})])
    dest = tmp_path / "t.jpg"

    fetch_to_file("https://tile.example/x.jpg", str(dest))
    assert dest.read_bytes() == b"abcd" and sleeps == [2.0]


def test_fetch_to_file_gives_up_after_the_last_attempt_and_removes_the_partial_file(monkeypatch, tmp_path):
    _script(monkeypatch, [_Resp(520, {"Retry-After": "0"})] * MAX_ATTEMPTS)
    dest = tmp_path / "t.jpg"

    with pytest.raises(ArchiveError, match="520"):
        fetch_to_file("https://tile.example/x.jpg", str(dest))
    assert not dest.exists()


def test_fetch_to_file_never_retries_a_404(monkeypatch, tmp_path):
    calls, sleeps = _script(monkeypatch, [_Resp(404), _Resp(200)])

    with pytest.raises(ArchiveError, match="404"):
        fetch_to_file("https://x.example/x.jpg", str(tmp_path / "t.jpg"))
    assert len(calls) == 1 and sleeps == []


def test_fetch_to_file_closes_every_response(monkeypatch, tmp_path):
    first, second = _Resp(503), _Resp(200)
    _script(monkeypatch, [first, second])

    fetch_to_file("https://x.example/x.jpg", str(tmp_path / "t.jpg"))
    assert first.closed and second.closed


def test_fetch_to_file_closes_a_failed_response_before_waiting(monkeypatch, tmp_path):
    first = _Resp(503, {"Retry-After": "5"})
    _script(monkeypatch, [first, _Resp(200)])
    closed_while_waiting = []
    monkeypatch.setattr(types_mod.time, "sleep", lambda s: closed_while_waiting.append(first.closed))

    fetch_to_file("https://x.example/x.jpg", str(tmp_path / "t.jpg"))
    assert closed_while_waiting == [True]


def test_retry_after_as_an_http_date_is_understood(monkeypatch):
    monkeypatch.setattr(types_mod.time, "time", lambda: 1_000_000_000.0)  # 2001-09-09T01:46:40Z
    resp = _Resp(429, {"Retry-After": "Sun, 09 Sep 2001 01:46:50 GMT"})

    assert types_mod._retry_delay(1, resp) == 10.0
