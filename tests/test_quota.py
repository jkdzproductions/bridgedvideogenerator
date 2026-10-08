# tests/test_quota.py
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from footage.quota import (
    CHANNEL_RESOLUTION_UNITS,
    PER_BEAT_UNITS,
    QuotaExceededError,
    check_preflight,
    mark_exhausted_today,
    record_spend,
    spent_today,
)

_PACIFIC = ZoneInfo("America/Los_Angeles")


def _pacific_time(year, month, day, hour, minute=0, second=0) -> float:
    return datetime(year, month, day, hour, minute, second, tzinfo=_PACIFIC).timestamp()


def test_spent_today_is_zero_when_tracker_file_does_not_exist_yet(tmp_path):
    tracker_path = str(tmp_path / "does_not_exist.json")
    assert spent_today(tracker_path, now=_pacific_time(2026, 6, 15, 12)) == 0


def test_spent_today_counts_only_entries_after_the_most_recent_pacific_midnight(tmp_path):
    tracker_path = str(tmp_path / "quota.json")
    yesterday_end = _pacific_time(2026, 6, 14, 23, 59, 59)
    today_start = _pacific_time(2026, 6, 15, 0, 0, 1)

    record_spend(50, tracker_path, now=yesterday_end)
    record_spend(30, tracker_path, now=today_start)

    assert spent_today(tracker_path, now=_pacific_time(2026, 6, 15, 12)) == 30


def test_record_spend_persists_and_accumulates_across_multiple_calls(tmp_path):
    tracker_path = str(tmp_path / "quota.json")
    now = _pacific_time(2026, 6, 15, 10)

    record_spend(101, tracker_path, now=now)
    record_spend(101, tracker_path, now=now + 60)

    assert spent_today(tracker_path, now=now + 120) == 202


def test_check_preflight_passes_when_video_fits_in_remaining_quota(tmp_path):
    tracker_path = str(tmp_path / "quota.json")
    check_preflight(beat_count=10, tracker_path=tracker_path, daily_quota=10_000,
                     now=_pacific_time(2026, 6, 15, 10))


def test_check_preflight_raises_with_shortfall_details_when_video_does_not_fit(tmp_path):
    tracker_path = str(tmp_path / "quota.json")
    now = _pacific_time(2026, 6, 15, 10)
    record_spend(9000, tracker_path, now=now)  # only 1000 left today

    with pytest.raises(QuotaExceededError) as exc_info:
        check_preflight(beat_count=20, tracker_path=tracker_path, daily_quota=10_000, now=now)

    message = str(exc_info.value)
    assert "9000" in message  # already spent
    assert "1000" in message  # remaining
    assert "2048" in message  # projected need: 8 + 20*102


def test_check_preflight_accounts_for_channel_resolution_overhead(tmp_path):
    tracker_path = str(tmp_path / "quota.json")
    exact_fit = CHANNEL_RESOLUTION_UNITS + PER_BEAT_UNITS
    check_preflight(beat_count=1, tracker_path=tracker_path, daily_quota=exact_fit,
                     now=_pacific_time(2026, 6, 15, 10))

    with pytest.raises(QuotaExceededError):
        check_preflight(beat_count=1, tracker_path=tracker_path, daily_quota=exact_fit - 1,
                         now=_pacific_time(2026, 6, 15, 10))


def test_mark_exhausted_today_makes_next_preflight_check_see_zero_headroom(tmp_path):
    tracker_path = str(tmp_path / "quota.json")
    now = _pacific_time(2026, 6, 15, 10)
    record_spend(50, tracker_path, now=now)

    mark_exhausted_today(tracker_path, daily_quota=10_000, now=now)

    assert spent_today(tracker_path, now=now) == 10_000
    with pytest.raises(QuotaExceededError):
        check_preflight(beat_count=1, tracker_path=tracker_path, daily_quota=10_000, now=now)


def test_mark_exhausted_today_is_a_no_op_when_already_spent_exceeds_quota(tmp_path):
    tracker_path = str(tmp_path / "quota.json")
    now = _pacific_time(2026, 6, 15, 10)
    record_spend(12_000, tracker_path, now=now)  # e.g. daily_quota lowered after spending

    mark_exhausted_today(tracker_path, daily_quota=10_000, now=now)

    assert spent_today(tracker_path, now=now) == 12_000  # unchanged, no negative-units entry


def test_tracker_file_is_never_left_corrupt_after_rapid_writes(tmp_path):
    """Verify atomic writes: tracker file is always valid JSON after writes."""
    tracker_path = str(tmp_path / "quota.json")
    now = _pacific_time(2026, 6, 15, 10)

    # Perform multiple rapid writes
    for i in range(10):
        record_spend(100, tracker_path, now=now + i)

    # Verify file is valid JSON and readable
    with open(tracker_path) as f:
        entries = json.load(f)
    assert len(entries) == 10
    assert all("units" in e and "timestamp" in e for e in entries)

    # Verify spent_today can still read it correctly
    assert spent_today(tracker_path, now=now + 100) == 1000


def _spend_many(tracker_path, count, units):
    for _ in range(count):
        record_spend(units, tracker_path)


def test_record_spend_from_many_threads_loses_no_spend(tmp_path):
    """Batch prep (footage/batch.py) records quota from worker threads at once."""
    import threading

    tracker_path = str(tmp_path / "quota.json")
    threads = [threading.Thread(target=_spend_many, args=(tracker_path, 40, 102)) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    with open(tracker_path) as f:
        assert len(json.load(f)) == 320
    assert spent_today(tracker_path) == 320 * 102


def test_record_spend_from_several_processes_loses_no_spend(tmp_path):
    import multiprocessing

    tracker_path = str(tmp_path / "quota.json")
    ctx = multiprocessing.get_context("spawn")
    procs = [ctx.Process(target=_spend_many, args=(tracker_path, 25, 102)) for _ in range(4)]
    for p in procs:
        p.start()
    for p in procs:
        p.join(60)
    assert all(p.exitcode == 0 for p in procs)

    with open(tracker_path) as f:
        assert len(json.load(f)) == 100
