# tests/fixtures/footage_dry_run.py
"""Real end-to-end check against the live Pexels API. Requires PEXELS_API_KEY in .env.
Uses a canned scoring response, since the real scoring subagent only runs inside a
Claude Code session — everything else here is the real code path."""
import json
import os

from dotenv import load_dotenv

from footage.build import prepare_footage_scoring, resolve_footage_winner
from footage.scoring_output import parse_scoring_output

load_dotenv()
api_key = os.environ["PEXELS_API_KEY"]

QUERY = "tokyo subway station"
SUBJECT = "Tokyo's subway system"

candidates, prompt = prepare_footage_scoring(
    query=QUERY, subject=SUBJECT, api_key=api_key,
    thumbnails_dir="tests/fixtures/dry_run_thumbnails",
)

print(f"{len(candidates)} candidates found for {QUERY!r}")
for i, c in enumerate(candidates):
    print(f"  [{i}] id={c.id} {c.width}x{c.height} {c.duration}s -> {c.url}")

print("\n--- scoring prompt (first 500 chars) ---")
print(prompt[:500])

# Canned response standing in for the real subagent — always picks candidate 0.
canned_response = json.dumps({"winner_index": 0, "reasoning": "dry run — canned choice"})
winner_index = parse_scoring_output(canned_response, num_candidates=len(candidates))

dest = "tests/fixtures/dry_run_winner.mp4"
path = resolve_footage_winner(candidates, winner_index, dest)

size_bytes = os.path.getsize(path)
print(f"\ndownloaded winner (candidate [{winner_index}]) to {path}: {size_bytes} bytes")
assert size_bytes > 100_000, "downloaded file suspiciously small for a real stock video clip"
print("footage_dry_run: OK")
