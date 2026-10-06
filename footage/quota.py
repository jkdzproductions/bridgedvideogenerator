# footage/quota.py
import json
import os
import tempfile
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

_PACIFIC = ZoneInfo("America/Los_Angeles")

CHANNEL_RESOLUTION_UNITS = 8
PER_BEAT_UNITS = 102  # 100 search + 1 channel sizes + 1 video details
DEFAULT_DAILY_QUOTA_UNITS = 10_000


class QuotaExceededError(Exception):
    pass


@dataclass
class _QuotaEntry:
    units: int
    timestamp: float


def _most_recent_midnight_pacific(now: float) -> float:
    local = datetime.fromtimestamp(now, tz=_PACIFIC)
    midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight.timestamp()


def _load_entries(tracker_path: str) -> list[_QuotaEntry]:
    if not os.path.exists(tracker_path):
        return []
    with open(tracker_path) as f:
        raw = json.load(f)
    return [_QuotaEntry(**e) for e in raw]


def _save_entries(tracker_path: str, entries: list[_QuotaEntry]) -> None:
    tracker_dir = os.path.dirname(tracker_path) or "."
    with tempfile.NamedTemporaryFile(
        mode="w", dir=tracker_dir, delete=False, suffix=".tmp"
    ) as tmp_file:
        json.dump([asdict(e) for e in entries], tmp_file)
        tmp_path = tmp_file.name
    os.replace(tmp_path, tracker_path)


def spent_today(tracker_path: str, now: float = None) -> int:
    now = time.time() if now is None else now
    boundary = _most_recent_midnight_pacific(now)
    entries = _load_entries(tracker_path)
    return sum(e.units for e in entries if e.timestamp >= boundary)


def record_spend(units: int, tracker_path: str, now: float = None) -> None:
    now = time.time() if now is None else now
    entries = _load_entries(tracker_path)
    entries.append(_QuotaEntry(units=units, timestamp=now))
    _save_entries(tracker_path, entries)


def check_preflight(
    beat_count: int,
    tracker_path: str,
    daily_quota: int = DEFAULT_DAILY_QUOTA_UNITS,
    now: float = None,
) -> None:
    now = time.time() if now is None else now
    already_spent = spent_today(tracker_path, now)
    projected_need = CHANNEL_RESOLUTION_UNITS + beat_count * PER_BEAT_UNITS
    remaining = daily_quota - already_spent
    if projected_need > remaining:
        beats_that_fit = max(0, remaining - CHANNEL_RESOLUTION_UNITS) // PER_BEAT_UNITS
        raise QuotaExceededError(
            f"today's YouTube quota already has {already_spent} unit(s) spent, {remaining} "
            f"unit(s) remaining out of {daily_quota}; this video needs {projected_need} unit(s) "
            f"for {beat_count} beat(s) (about {beats_that_fit} beat(s) would fit in what's left)"
        )


def mark_exhausted_today(
    tracker_path: str, daily_quota: int = DEFAULT_DAILY_QUOTA_UNITS, now: float = None
) -> None:
    now = time.time() if now is None else now
    already_spent = spent_today(tracker_path, now)
    shortfall = daily_quota - already_spent
    if shortfall > 0:
        record_spend(shortfall, tracker_path, now)
