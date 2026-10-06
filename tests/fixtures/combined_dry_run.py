# tests/fixtures/combined_dry_run.py
"""Real end-to-end check against the live Pexels and YouTube Data APIs. Requires both
PEXELS_API_KEY and YOUTUBE_API_KEY in .env. Uses a canned scoring response, since the real
scoring subagent only runs inside a Claude Code session — everything else here is the real code
path, across both sources.

Usage: .venv/bin/python tests/fixtures/combined_dry_run.py [canned_winner_index] (default 0)."""
import hashlib
import json
import os
import sys
import time

from dotenv import load_dotenv

from footage.combined_build import prepare_combined_scoring, resolve_combined_winner
from footage.quota import PER_BEAT_UNITS, record_spend, spent_today
from footage.scoring_output import parse_scoring_output
from footage.youtube_channels import EXCLUDED_CHANNEL_URLS, resolve_channel_ids
from footage.youtube_download import probe_video_dimensions

load_dotenv()
pexels_api_key = os.environ["PEXELS_API_KEY"]
youtube_api_key = os.environ["YOUTUBE_API_KEY"]
envato_profile_dir = os.environ.get("ENVATO_PROFILE_DIR", ".envato_automation_profile")

QUERY = "tokyo subway station"
SUBJECT = "Tokyo's subway system"
TARGET_DURATION = 8.0
TRACKER_PATH = "tests/fixtures/combined_dry_run_quota.json"
canned_winner_index = int(sys.argv[1]) if len(sys.argv) > 1 else 0

excluded_ids = resolve_channel_ids(EXCLUDED_CHANNEL_URLS, youtube_api_key)
print(f"resolved {len(excluded_ids)} excluded channel IDs")

spent_before = spent_today(TRACKER_PATH)

candidates, prompt = prepare_combined_scoring(
    query=QUERY, subject=SUBJECT, pexels_api_key=pexels_api_key, youtube_api_key=youtube_api_key,
    excluded_channel_ids=excluded_ids, thumbnails_dir="tests/fixtures/combined_dry_run_thumbnails",
    envato_profile_dir=envato_profile_dir,
)
record_spend(PER_BEAT_UNITS, TRACKER_PATH)

print(f"{len(candidates)} candidates found for {QUERY!r}")
for i, c in enumerate(candidates):
    print(f"  [{i}] source={c.source} id={c.display_id} thumbnail={c.thumbnail_path}")

assert any(c.source == "pexels" for c in candidates), "expected at least one Pexels candidate"
assert any(c.source == "youtube" for c in candidates), "expected at least one YouTube candidate"
assert any(c.source == "envato" for c in candidates), "expected at least one Envato candidate"

print("\n--- scoring prompt (first 500 chars) ---")
print(prompt[:500])

canned_response = json.dumps(
    {"winner_index": canned_winner_index, "reasoning": "dry run — canned choice"}
)
winner_index = parse_scoring_output(canned_response, num_candidates=len(candidates))
winner = candidates[winner_index]

dest = "tests/fixtures/combined_dry_run_winner.mp4"
started_at = time.time()
path = resolve_combined_winner(
    candidates, winner_index, dest, target_duration=TARGET_DURATION,
    envato_profile_dir=envato_profile_dir,
)

# Check the artifact itself, not just that the call returned: it must be a file written by THIS
# run (not a leftover from an earlier one) and real-video sized.
mtime = os.path.getmtime(path)
size_bytes = os.path.getsize(path)
md5 = hashlib.md5(open(path, "rb").read()).hexdigest()
print(
    f"\ndownloaded winner (candidate [{winner_index}], source={winner.source}, "
    f"id={winner.display_id}) to {path}: {size_bytes} bytes, md5={md5}, "
    f"mtime={time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(mtime))}"
)
assert mtime >= started_at, "output file predates this run — a stale file was kept"
assert size_bytes > 20_000, "downloaded file suspiciously small for a real video clip"

if winner.source == "youtube":
    width, height = probe_video_dimensions(path)
    print(f"probed dimensions: {width}x{height}")
    assert width > height, f"winner is {width}x{height}, not landscape"

spent_after = spent_today(TRACKER_PATH)
print(f"\nquota tracker: {spent_before} -> {spent_after} units spent today")
assert spent_after == spent_before + PER_BEAT_UNITS, "quota tracker did not record this beat's real spend"
print("combined_dry_run: OK")
