# tests/fixtures/youtube_dry_run.py
"""Real end-to-end check against the live YouTube Data API and yt-dlp. Requires
YOUTUBE_API_KEY in .env. Uses a canned scoring response, since the real scoring subagent only
runs inside a Claude Code session — everything else here is the real code path.

Usage: .venv/bin/python tests/fixtures/youtube_dry_run.py [canned_winner_index]
(default 0). Running it twice with different indices downloads two different videos to the same
path — a real check that a rerun replaces the old file instead of silently keeping it."""
import hashlib
import json
import os
import sys
import time

from dotenv import load_dotenv

from footage.youtube_build import prepare_youtube_scoring, resolve_youtube_winner
from footage.youtube_channels import EXCLUDED_CHANNEL_URLS, resolve_channel_ids
from footage.youtube_download import probe_video_dimensions
from footage.scoring_output import parse_scoring_output

load_dotenv()
api_key = os.environ["YOUTUBE_API_KEY"]

QUERY = "tokyo subway b-roll stock footage"
SUBJECT = "Tokyo's subway system"
TARGET_DURATION = 8.0
canned_winner_index = int(sys.argv[1]) if len(sys.argv) > 1 else 0

excluded_ids = resolve_channel_ids(EXCLUDED_CHANNEL_URLS, api_key)
print(f"resolved {len(excluded_ids)} excluded channel IDs")

candidates, prompt = prepare_youtube_scoring(
    query=QUERY, subject=SUBJECT, api_key=api_key, excluded_channel_ids=excluded_ids,
    thumbnails_dir="tests/fixtures/youtube_dry_run_thumbnails",
)

print(f"{len(candidates)} candidates found for {QUERY!r}")
for i, c in enumerate(candidates):
    print(f"  [{i}] {c.video_id} {c.duration_seconds:.0f}s channel={c.channel_title!r} -> {c.title!r}")

assert all(c.channel_id not in excluded_ids for c in candidates), "an excluded channel slipped through"

print("\n--- scoring prompt (first 500 chars) ---")
print(prompt[:500])

canned_response = json.dumps({"winner_index": canned_winner_index, "reasoning": "dry run — canned choice"})
winner_index = parse_scoring_output(canned_response, num_candidates=len(candidates))

dest = "tests/fixtures/youtube_dry_run_winner.mp4"
started_at = time.time()
path = resolve_youtube_winner(candidates, winner_index, dest, target_duration=TARGET_DURATION)

# Check the artifact itself, not just that the call returned: it must be a file written by THIS
# run (not a leftover from an earlier one), real-video sized, and landscape.
mtime = os.path.getmtime(path)
size_bytes = os.path.getsize(path)
width, height = probe_video_dimensions(path)
md5 = hashlib.md5(open(path, "rb").read()).hexdigest()
print(
    f"\ndownloaded winner (candidate [{winner_index}] = {candidates[winner_index].video_id}) to "
    f"{path}: {size_bytes} bytes, {width}x{height}, md5={md5}, "
    f"mtime={time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(mtime))}"
)
assert mtime >= started_at, "output file predates this run — a stale file was kept"
assert size_bytes > 20_000, "downloaded file suspiciously small for a real video clip"
assert width > height, f"winner is {width}x{height}, not landscape"
print("youtube_dry_run: OK")
