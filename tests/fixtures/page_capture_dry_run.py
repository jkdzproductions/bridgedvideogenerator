"""Live check for page capture: .venv/bin/python tests/fixtures/page_capture_dry_run.py "<url>" <out_dir>

Runs the real browser against a real page and prints where the stills are. Open them and look."""
import json
import sys

from page_intake.capture import PageCaptureError, capture_page

url, out_dir = sys.argv[1], sys.argv[2]
try:
    result = capture_page(url, out_dir, 0)
except PageCaptureError as e:
    print(f"CAPTURE FAILED: {e}")
    sys.exit(2)
print(json.dumps({k: v for k, v in result.items() if k != "rects"}, indent=2))
print(f"{len(result['rects'])} highlight rectangles")
