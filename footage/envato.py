import re
from dataclasses import dataclass
from urllib.parse import quote_plus, urlparse


class EnvatoError(Exception):
    pass


@dataclass
class EnvatoCandidate:
    item_id: str
    title: str
    thumbnail_url: str
    author: str
    detail_url: str


@dataclass
class EnvatoCandidateDetails:
    duration_seconds: float
    width: int
    height: int


_ITEM_ID_PATTERN = re.compile(r"/search/stock-video/([0-9a-f-]{36})")
_DURATION_PATTERN = re.compile(r"(\d+)\s+seconds?")
_RESOLUTION_PATTERN = re.compile(r"(\d+)\s*x\s*(\d+)\s*px")


def _build_search_url(query: str) -> str:
    # Global Constraint: never search without the Stock Footage category filter — this is the
    # only thing standing between real footage and Envato's Motion Graphics / AI-adjacent
    # content, per the spec's "What's verified live" section.
    return (
        "https://app.envato.com/search"
        f"?term={quote_plus(query)}&itemType=stock-video&filter.categories=Stock+Footage"
    )


def _parse_search_results(raw_results: list[dict]) -> list[EnvatoCandidate]:
    candidates = []
    for r in raw_results:
        match = _ITEM_ID_PATTERN.search(r["href"])
        if not match:
            raise EnvatoError(f"could not extract an item id from href: {r['href']!r}")
        detail_url = f"https://app.envato.com{r['href']}" if r["href"].startswith("/") else r["href"]
        candidates.append(EnvatoCandidate(
            item_id=match.group(1), title=r["title"], thumbnail_url=r["thumbnail_src"],
            author=r["author"], detail_url=detail_url,
        ))
    return candidates


def _parse_detail_page_text(text: str) -> EnvatoCandidateDetails:
    duration_match = _DURATION_PATTERN.search(text)
    if not duration_match:
        raise EnvatoError(f"could not find a duration on the detail page: {text[:200]!r}")
    resolution_match = _RESOLUTION_PATTERN.search(text)
    if not resolution_match:
        raise EnvatoError(f"could not find a resolution on the detail page: {text[:200]!r}")
    return EnvatoCandidateDetails(
        duration_seconds=float(duration_match.group(1)),
        width=int(resolution_match.group(1)), height=int(resolution_match.group(2)),
    )


def _extract_raw_search_results(page, max_results: int) -> list[dict]:
    """Talks to a real (or faked) Playwright `page`. Isolated here, alone, so every function
    above it stays unit-testable without a browser.

    Live-verified selectors (checked against the real, logged-in site in BOTH headless=True and
    headless=False — identical results in both modes, at default 1280x720 viewport):
    - Each search result card is an `a[href*="/search/stock-video/"]` anchor. The href already
      contains the item id and is used as-is (relative, e.g. "/search/stock-video/<uuid>?...").
    - That same anchor carries `data-analytics-item_title` and `data-analytics-item_author`
      attributes — Envato's own click-tracking data attached directly to the link element. This
      is what's actually used for title/author: the brief's guess that the `<img alt>` held the
      title did NOT hold up live — the real `alt` text is a fixed i18n placeholder string,
      `"stock-video.item.alt"`, the same on every card, never the item's real title. The
      data-analytics-* attributes were confirmed correct and present on every result card
      checked, in both headless modes.
    - The thumbnail is the `<img>` inside the anchor; its `src` attribute is the thumbnail URL.
    """
    anchors = page.locator('a[href*="/search/stock-video/"]')
    count = anchors.count()
    seen_hrefs = set()
    results = []
    for i in range(count):
        if len(results) >= max_results:
            break
        anchor = anchors.nth(i)
        href = anchor.get_attribute("href")
        if not href or href in seen_hrefs:
            continue  # guards against the same item's anchor appearing more than once in the DOM
        seen_hrefs.add(href)

        title = anchor.get_attribute("data-analytics-item_title") or ""
        author = anchor.get_attribute("data-analytics-item_author") or ""
        img = anchor.locator("img").first
        thumbnail_src = (img.get_attribute("src") or "") if img.count() > 0 else ""

        results.append({
            "href": href, "title": title, "thumbnail_src": thumbnail_src, "author": author,
        })
    return results


def _extract_detail_page_text(page) -> str:
    """Talks to a real (or faked) Playwright `page`, already navigated to an item detail URL.

    Live-verified (checked in both headless=True and headless=False, identical result): the
    brief's guess of a `<main>` element or `dt`/`dd` pairs did NOT hold up live — the real detail
    page has no `<main>` element at all, and no `dt`/`dd` elements either. The duration/
    resolution/fps metadata is instead rendered as a small "icon grid" of label spans (e.g. one
    span with text "30 seconds" sitting near a sibling span with text "1920 x 1080 px"), wrapped
    in Envato's own CSS-module classes (observed live as names like "_iconGrid_r2m42_5") that look
    autogenerated per-build and too fragile to hardcode. Instead, this locates the "NN seconds"
    text node directly (a stable, content-based anchor) and walks up its ancestor chain until it
    finds the smallest container whose text also includes "px" — structurally the same metadata
    block `_parse_detail_page_text` expects, found by content rather than by a fragile class name.
    Confirmed live: this container's `inner_text()` is exactly
    "30 seconds\\n1920 x 1080 px\\n50 fps\\nNo Alpha Channel\\nNot Looped\\nProRes\\nHorizontal"
    for a real item — the same fields the brief's fixture assumes, just a different line order
    (ProRes/Horizontal swapped), which doesn't matter to `_parse_detail_page_text`'s regex search.
    Falls back to the whole page body's text (still contains the same metadata, just with more
    surrounding noise that the regexes tolerate) if that structural walk doesn't find a container.

    Also live-verified (a real bug this caught, not a guess): `page.goto(..., wait_until=
    "domcontentloaded")` returns before this metadata block has actually rendered — it's an SPA;
    calling `.count()` immediately after navigation reliably found 0 matches. An explicit
    `wait_for(state="attached")` on the duration text node before doing anything else fixed this
    every time it was tested live; without it, `fetch_envato_details` intermittently raised on the
    very first candidate.
    """
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

    duration_nodes = page.get_by_text(_DURATION_PATTERN)
    try:
        duration_nodes.first.wait_for(state="attached", timeout=15000)
    except PlaywrightTimeoutError:
        raise EnvatoError("could not find a duration element on the detail page")

    container = duration_nodes.first
    for _ in range(8):
        container = container.locator("xpath=..")
        text = container.inner_text()
        if "px" in text and len(text) < 1000:
            return text
    return page.locator("body").inner_text()


def _is_logged_out_url(url: str) -> bool:
    # The real logged-out redirect observed live in Task 1 is
    # "https://account.envato.com/sign_in?to=envatoapp&state=..." — no "login" in it at all.
    # Every logged-in page this code uses lives on app.envato.com, so ANY landing on the
    # account.envato.com host (sign_in, sign_up, password reset, ...) means no usable session.
    # Only host+path are checked, never the query string — a search term like "login screen"
    # lands in `?term=...` and must not look like a logged-out redirect.
    parsed = urlparse(url.lower())
    return (
        parsed.hostname == "account.envato.com"
        or any(marker in parsed.path for marker in ("sign_in", "signin", "login"))
    )


def search_envato(
    query: str, exclude_ids: frozenset[str], profile_dir: str, max_results: int = 7
) -> list[EnvatoCandidate]:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(profile_dir, headless=True)
        try:
            page = context.new_page()
            page.goto(_build_search_url(query), wait_until="domcontentloaded")
            if _is_logged_out_url(page.url):
                raise EnvatoError(
                    f"landed on Envato's sign-in page ({page.url}) — the Playwright profile's "
                    "Envato session has expired or was never logged in; re-run tests/fixtures/"
                    "envato_automation_spike.py to log in again"
                )
            raw_results = _extract_raw_search_results(page, max_results)
        finally:
            context.close()

    candidates = _parse_search_results(raw_results)
    # Unlike a login/session failure (which DOES raise — see above), a genuinely empty result
    # set is not an error: Envato is an additive, optional source (Global Constraints), so
    # this returns [] rather than raising, matching search_pexels's and search_youtube's own
    # shape exactly (both return a possibly-empty list; the caller decides whether that's
    # fatal). The one place that must still raise on a truly empty *combined* pool across all
    # three sources is prepare_combined_scoring's existing top-level check (Task 4) — untouched
    # by this function.
    return [c for c in candidates if c.item_id not in exclude_ids][:max_results]


def fetch_envato_details(
    candidates: list[EnvatoCandidate], profile_dir: str
) -> dict[str, EnvatoCandidateDetails]:
    from playwright.sync_api import sync_playwright

    details: dict[str, EnvatoCandidateDetails] = {}
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(profile_dir, headless=True)
        try:
            page = context.new_page()
            for c in candidates:
                page.goto(c.detail_url, wait_until="domcontentloaded")
                text = _extract_detail_page_text(page)
                details[c.item_id] = _parse_detail_page_text(text)
        finally:
            context.close()
    return details
