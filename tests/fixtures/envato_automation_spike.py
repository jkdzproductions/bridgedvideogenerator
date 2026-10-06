"""Live spike: does a Python-launched (Playwright) browser get blocked by bot-detection on
Envato Elements, the way motion graphics found Playwright gets blocked on claude.ai by
Cloudflare? Run this manually, not as part of the test suite — it needs a real, visible browser
and (on the first run) a human to log in.

Usage: .venv/bin/python tests/fixtures/envato_automation_spike.py
"""
import os
import sys
import time

from playwright.sync_api import sync_playwright

PROFILE_DIR = os.path.abspath(".envato_automation_profile")
SEARCH_URL = (
    "https://app.envato.com/search"
    "?term=city+skyline+aerial&itemType=stock-video&filter.categories=Stock+Footage"
)

with sync_playwright() as p:
    context = p.chromium.launch_persistent_context(
        PROFILE_DIR, headless=False, viewport={"width": 1440, "height": 900},
    )
    page = context.new_page()

    print(f"Navigating to {SEARCH_URL} ...")
    page.goto(SEARCH_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(3000)

    title = page.title()
    url = page.url
    print(f"Landed on: {url!r}, title={title!r}")

    # A real login page or a bot-detection interstitial will not look like the real search
    # results page — check for the specific "What should we create?"-equivalent search UI
    # element instead of assuming success from a 200 status.
    has_search_results = page.locator("text=Filters").count() > 0
    looks_like_login = "login" in url.lower() or "sign" in url.lower()
    print(f"has_search_results={has_search_results}, looks_like_login={looks_like_login}")

    if looks_like_login:
        print(
            "\nLooks like a login page. If this is the FIRST run, log in manually in the real "
            "browser window now — you have 3 minutes. This spike will keep polling."
        )
        deadline = time.time() + 180
        while time.time() < deadline:
            if page.locator("text=Filters").count() > 0:
                print("Logged in — search results now visible.")
                break
            page.wait_for_timeout(2000)
        else:
            print("SPIKE RESULT: could not confirm login within 3 minutes. Re-run this script.")
            context.close()
            sys.exit(1)

    # Take a screenshot either way — this is the real evidence, not a printed claim.
    screenshot_path = os.path.abspath("tests/fixtures/envato_spike_screenshot.png")
    page.screenshot(path=screenshot_path)
    print(f"Screenshot saved to {screenshot_path} — open it and look for yourself.")

    body_text = page.locator("body").inner_text()
    blocked_signals = ["Cloudflare", "captcha", "CAPTCHA", "verify you are human", "Access denied"]
    hit_signals = [s for s in blocked_signals if s.lower() in body_text.lower()]
    if hit_signals:
        print(f"SPIKE RESULT: BLOCKED — page body contains: {hit_signals}")
        context.close()
        sys.exit(1)

    if not has_search_results:
        print(
            "SPIKE RESULT: UNCLEAR — no obvious block signal, but the expected search UI "
            "wasn't found either. Inspect the screenshot before concluding anything."
        )
        context.close()
        sys.exit(1)

    print("SPIKE RESULT: real search results loaded, no block signal found.")

    # Now the real second half: open one real item and confirm the Download button is present
    # and clickable (do NOT actually click it here — Task 3 covers real download verification
    # with proper cleanup; this spike only needs to prove the mechanics reach that point).
    first_result = page.locator("a[href*='/search/stock-video/']").first
    if first_result.count() == 0:
        print("SPIKE RESULT: search results loaded but no item links found — inspect manually.")
        context.close()
        sys.exit(1)
    first_result.click()
    page.wait_for_timeout(2000)
    download_button = page.locator("text=Download").first
    print(f"Item detail page reached: {page.url!r}, Download button present: "
          f"{download_button.count() > 0}")

    context.close()
    print("\nSpike complete. If everything above says OK with no block signals, Task 1 concludes "
          "'Python-driven automation works' and Tasks 2+ proceed as written.")
