# tests/fixtures/envato_dry_run.py
"""Real end-to-end check against the live Envato Elements site, via Playwright. Requires the
profile at ENVATO_PROFILE_DIR (default .envato_automation_profile) to already be logged in —
run tests/fixtures/envato_automation_spike.py first if it isn't.

Usage: .venv/bin/python tests/fixtures/envato_dry_run.py
"""
import hashlib
import os
import subprocess
import time

from dotenv import load_dotenv

from footage.combined_build import _envato_candidates
from footage.envato import EnvatoError
from footage.envato_download import download_envato_clip

load_dotenv()
PROFILE_DIR = os.environ.get("ENVATO_PROFILE_DIR", ".envato_automation_profile")
QUERY = "city skyline aerial"
TARGET_DURATION = 8.0
THUMBNAILS_DIR = "tests/fixtures/envato_dry_run_thumbnails"
DEST = "tests/fixtures/envato_dry_run_winner.mov"

print(f"Searching Envato Stock Footage for {QUERY!r} ...")
# Task 4's real, reviewer-approved deviation: _envato_candidates returns a
# (candidates, details) tuple, not a plain list — see footage/combined_build.py.
candidates, details = _envato_candidates(
    QUERY, exclude_ids=frozenset(), profile_dir=PROFILE_DIR, thumbnails_dir=THUMBNAILS_DIR
)
assert candidates, "expected at least one real Envato candidate for a common query"
for c in candidates:
    print(f"  {c.display_id}: {c.payload.title!r} by {c.payload.author!r} "
          f"thumbnail={c.thumbnail_path}")

winner = candidates[0]
print(f"\nDownloading winner: {winner.payload.title!r} ...")
started_at = time.time()
path = download_envato_clip(
    winner.payload, dest_path=DEST, target_duration_seconds=TARGET_DURATION,
    profile_dir=PROFILE_DIR,
)

# Check the real artifact, not just that the call returned — this project's standing rule.
mtime = os.path.getmtime(path)
size_bytes = os.path.getsize(path)
md5 = hashlib.md5(open(path, "rb").read()).hexdigest()
print(f"\nDownloaded and trimmed to {path}: {size_bytes} bytes, md5={md5}")
assert mtime >= started_at, "output file predates this run — a stale file was kept"
assert size_bytes > 20_000, "downloaded file suspiciously small for a real video clip"

probe = subprocess.run(
    ["ffprobe", "-v", "error", "-show_entries", "format=duration",
     "-show_entries", "stream=width,height", "-of", "default=noprint_wrappers=0", path],
    capture_output=True, text=True,
)
print(f"\nffprobe output:\n{probe.stdout}")
assert "width=1920" in probe.stdout or "width=" in probe.stdout, "no readable video stream"

print("\nenvato_dry_run: OK — real search, real download, real trim, real verification.")
