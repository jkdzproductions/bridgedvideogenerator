"""Stage 1 Step 1c: load a linked page in a real browser, find the highlighted passage, and make
the video stills. Needs the `page` extra (playwright + Pillow). Never solves or bypasses a bot
check: a page the browser cannot load is reported, not worked around."""
import dataclasses
import io
import os
import tempfile

from graph_intake.download import USER_AGENT
from page_intake.fragment import FragmentError, TextFragment, parse_text_fragment, strip_fragment_directive
from page_intake.paths import PAGE_STILLS_DIR, plain_still_path, still_path

try:  # optional extra "page"; imported here so `import page_intake` never needs it
    from playwright.sync_api import Error as PlaywrightError, sync_playwright
except ModuleNotFoundError:
    PlaywrightError = sync_playwright = None

VIEWPORT = {"width": 1920, "height": 1080}
LOAD_TIMEOUT_MS = 30000
IDLE_WAIT_MS = 5000  # busy pages never go network-idle; this only bounds the wait
SETTLE_MS = 500  # late popups and lazy content


class PageCaptureError(Exception):
    """The page could not be turned into a still; the message says why (callers add phrase + URL)."""


# Finds the highlighted words in the page's visible text and keeps them as window.__versedRange.
# Text is lower-cased and whitespace-collapsed for matching; text nodes in different blocks are
# separated by one space so "<h1>A</h1><p>B</p>" reads "a b". Returns null when not found.
FIND_JS = r"""
(frag) => {
  const SKIP = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE']);
  const blockOf = (el) => { while (el && /^inline/.test(getComputedStyle(el).display)) el = el.parentElement; return el; };
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, { acceptNode(n) {
    const p = n.parentElement;
    if (!p || SKIP.has(p.tagName)) return NodeFilter.FILTER_REJECT;
    // display:none on the parent or any ancestor hides the text; visibility inherits, so the
    // parent's computed value is enough. (checkVisibility() would also reject display:contents.)
    for (let e = p; e; e = e.parentElement) {
      if (getComputedStyle(e).display === 'none') return NodeFilter.FILTER_REJECT;
    }
    const vis = getComputedStyle(p).visibility;
    if (vis === 'hidden' || vis === 'collapse') return NodeFilter.FILTER_REJECT;
    return NodeFilter.FILTER_ACCEPT;
  }});
  let text = '';
  let orig = '';  // same characters as `text` but in the page's own case, for the returned passage
  const map = [];
  let node, previousBlock = null;
  while ((node = walker.nextNode())) {
    const block = blockOf(node.parentElement);
    if (previousBlock && block !== previousBlock && text.length && !text.endsWith(' ')) {
      text += ' ';
      orig += ' ';
      map.push([node, 0]);
    }
    previousBlock = block;
    for (let i = 0; i < node.data.length; i++) {
      const ch = node.data[i];
      if (/\s/.test(ch)) {
        if (!text.length || text.endsWith(' ')) continue;
        text += ' ';
        orig += ' ';
      } else {
        const lower = ch.toLowerCase();
        text += lower.length === 1 ? lower : ch;
        orig += ch;
      }
      map.push([node, i]);
    }
  }
  const norm = (s) => s.toLowerCase().replace(/\s+/g, ' ').trim();
  const start = norm(frag.start);
  const end = frag.end ? norm(frag.end) : null;
  const prefix = frag.prefix ? norm(frag.prefix) : null;
  const suffix = frag.suffix ? norm(frag.suffix) : null;
  const prefixOk = (s) => !prefix || text.slice(0, s).trimEnd().endsWith(prefix);
  const suffixOk = (e) => !suffix || text.slice(e).trimStart().startsWith(suffix);
  let found = null;
  for (let from = 0; from <= text.length && !found; ) {
    const s = text.indexOf(start, from);
    if (s < 0) break;
    from = s + 1;
    if (!prefixOk(s)) continue;
    let e = s + start.length;
    if (end) {
      let j = text.indexOf(end, e);
      while (j >= 0 && !suffixOk(j + end.length)) j = text.indexOf(end, j + 1);
      if (j < 0) continue;
      e = j + end.length;
    } else if (!suffixOk(e)) {
      continue;
    }
    found = [s, e];
  }
  if (!found) return null;
  const a = map[found[0]];
  const b = map[found[1] - 1];
  const range = document.createRange();
  range.setStart(a[0], a[1]);
  range.setEnd(b[0], b[1] + 1);
  window.__versedRange = range;
  return { passage: orig.slice(found[0], found[1]) };
}
"""


def load_page(page, url: str) -> None:
    try:
        response = page.goto(url, wait_until="load", timeout=LOAD_TIMEOUT_MS)
    except PlaywrightError as e:
        raise PageCaptureError(f"the page could not be loaded: {e}") from e
    if response is not None and response.status >= 400:
        raise PageCaptureError(
            f"the page answered HTTP {response.status} (blocked, paywalled or missing)")
    try:
        page.wait_for_load_state("networkidle", timeout=IDLE_WAIT_MS)
    except PlaywrightError:
        pass
    page.wait_for_timeout(SETTLE_MS)


def find_passage(page, fragment: TextFragment) -> str:
    result = page.evaluate(FIND_JS, dataclasses.asdict(fragment))
    if result is None:
        raise PageCaptureError(
            f"the highlighted words {fragment.start!r} were not found in the page's visible text "
            "(the page may be paywalled, load its text with JavaScript, or have changed)")
    return result["passage"]


HIGHLIGHT_GREEN = "#30fe3e"  # sampled from Josh's frame design-assets/frames/Screenshot 2026-10-03 at 1.07.30 PM.png
TEXT_BLUR_RADIUS = 2  # Pillow GaussianBlur radius for everything outside the passage
IMAGE_BLUR_PX = 28  # CSS blur on every image/video/background so nothing graphic is recognizable
MASK_PADDING_PX = 2  # the sharp patch around each passage rectangle is this much bigger

# Hides cookie/consent/newsletter popups and every fixed or sticky element that does not hold the
# passage. Runs after find_passage, because the passage's own ancestors must never be hidden.
POPUPS_JS = r"""
() => {
  const range = window.__versedRange;
  const holdsPassage = (el) => el.contains(range.commonAncestorContainer);
  let hidden = 0;
  const hide = (el) => { el.style.setProperty('display', 'none', 'important'); hidden++; };
  const SELECTORS = ['#onetrust-consent-sdk', '#CybotCookiebotDialog', '[id*="cookie" i]', '[class*="cookie" i]',
    '[id*="consent" i]', '[class*="consent" i]', '[id*="gdpr" i]', '[class*="gdpr" i]', '[role="dialog"]',
    '[aria-modal="true"]', '[class*="modal" i]', '[class*="popup" i]', '[id*="newsletter" i]',
    '[class*="newsletter" i]', '[class*="overlay" i]'];
  for (const el of document.querySelectorAll(SELECTORS.join(','))) if (!holdsPassage(el)) hide(el);
  for (const el of document.querySelectorAll('body *')) {
    const position = getComputedStyle(el).position;
    if ((position === 'fixed' || position === 'sticky') && !holdsPassage(el)) hide(el);
  }
  for (const el of [document.documentElement, document.body]) {
    if (getComputedStyle(el).overflow === 'hidden') el.style.setProperty('overflow', 'auto', 'important');
  }
  return hidden;
}
"""

# Scrolls so the whole passage is on screen when it can be: centred vertically if it fits the
# frame, else its top a quarter of the way down. Scrolls by the range's own bounding box, never by
# one element, so a passage that starts in a tall container or spans many paragraphs is placed as
# a whole. (The first scrollIntoView only reaches nested scroll containers.)
RECTS_JS = r"""
() => {
  const range = window.__versedRange;
  range.startContainer.parentElement.scrollIntoView({ block: 'nearest', inline: 'nearest', behavior: 'instant' });
  const box = range.getBoundingClientRect();
  const wanted = box.height <= innerHeight ? (innerHeight - box.height) / 2 : innerHeight / 4;
  window.scrollBy({ top: box.top - wanted, left: 0, behavior: 'instant' });
  return [...range.getClientRects()].filter(q => q.width > 0 && q.height > 0)
    .map(q => [q.left, q.top, q.width, q.height]);
}
"""

# Ancestors of the passage that carry a url() background image. They are not blurred (blurring
# them would blur the passage), so a hero photo behind a headline must be reported for review.
ANCESTOR_BG_JS = r"""
() => {
  const bad = [];
  let el = window.__versedRange.commonAncestorContainer;
  if (el.nodeType !== 1) el = el.parentElement;
  for (; el; el = el.parentElement) {
    if (/url\(/.test(getComputedStyle(el).backgroundImage)) {
      const cls = typeof el.className === 'string' && el.className.trim() ? '.' + el.className.trim().split(/\s+/).join('.') : '';
      bad.push(el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + cls);
    }
    if (el === document.body) break;
  }
  return bad;
}
"""

BLUR_IMAGES_JS = r"""
(px) => {
  const range = window.__versedRange;
  let blurred = 0;
  const blur = (el) => { el.style.setProperty('filter', `blur(${px}px)`, 'important'); blurred++; };
  for (const el of document.querySelectorAll('img, picture, video, canvas, svg, iframe, embed, object')) {
    if (!el.contains(range.commonAncestorContainer)) blur(el);
  }
  for (const el of document.querySelectorAll('body *')) {
    if (el.contains(range.commonAncestorContainer)) continue;
    const bg = getComputedStyle(el).backgroundImage;
    if (bg && bg !== 'none') blur(el);
  }
  return blurred;
}
"""

COVER_JS = r"""
(rects) => {
  const common = window.__versedRange.commonAncestorContainer;
  const bad = [];
  for (const [x, y, w, h] of rects) {
    const cx = x + w / 2, cy = y + h / 2;
    if (cx < 0 || cy < 0 || cx > innerWidth || cy > innerHeight) continue;
    const top = document.elementFromPoint(cx, cy);
    if (top && !common.contains(top) && !top.contains(common)) {
      const cls = typeof top.className === 'string' && top.className.trim() ? '.' + top.className.trim().split(/\s+/).join('.') : '';
      bad.push(top.tagName.toLowerCase() + (top.id ? '#' + top.id : '') + cls);
    }
  }
  return [...new Set(bad)];
}
"""

HIGHLIGHT_JS = r"""
(color) => {
  const style = document.createElement('style');
  style.textContent = `::highlight(versed) { background-color: ${color}; color: inherit; }`;
  document.head.appendChild(style);
  CSS.highlights.set('versed', new Highlight(window.__versedRange));
}
"""


CLEAR_HIGHLIGHT_JS = "() => { CSS.highlights.delete('versed'); }"


def hide_popups(page) -> int:
    return page.evaluate(POPUPS_JS)


def bring_into_view(page) -> list:
    """Scroll the passage into the frame and return every one of its rectangles. Fails loudly when
    any of it is outside the frame: a truncated highlight must never pass as a success."""
    page.evaluate(RECTS_JS)
    page.wait_for_timeout(200)
    rects = page.evaluate(RECTS_JS)
    width, height = VIEWPORT["width"], VIEWPORT["height"]
    tolerance = 2
    if not rects or any(
            r[0] < -tolerance or r[1] < -tolerance
            or r[0] + r[2] > width + tolerance or r[1] + r[3] > height + tolerance for r in rects):
        raise PageCaptureError(
            f"the highlighted passage is taller than the {width}x{height} frame (or runs off-screen); "
            "link a shorter highlight")
    return rects


def blur_images(page) -> int:
    return page.evaluate(BLUR_IMAGES_JS, IMAGE_BLUR_PX)


def background_image_ancestors(page) -> list:
    """Ancestors of the passage with a url() background image (they cannot be blurred)."""
    return [f"background image behind the passage (not blurred): {name}"
            for name in page.evaluate(ANCESTOR_BG_JS)]


def uncovered_overlays(page, rects: list) -> list:
    """Elements still sitting on top of the passage after popup hiding (empty = clear)."""
    return page.evaluate(COVER_JS, rects)


def highlight_passage(page) -> None:
    page.evaluate(HIGHLIGHT_JS, HIGHLIGHT_GREEN)


def clear_highlight(page) -> None:
    page.evaluate(CLEAR_HIGHLIGHT_JS)


def _write_png_atomically(image, path: str) -> None:
    directory = os.path.dirname(path)
    fd, temp_path = tempfile.mkstemp(dir=directory, prefix=".page_", suffix=".part")
    try:
        with os.fdopen(fd, "wb") as f:
            image.save(f, format="PNG")
        os.replace(temp_path, path)
    except BaseException:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise


def capture_page(url: str, out_dir: str, italic_index: int, headless: bool = True) -> dict:
    """Load `url` (a link with a #:~:text= highlight), and write the two stills for italic span
    `italic_index`. See the module docstring; raises PageCaptureError on every failure."""
    if sync_playwright is None:
        raise ModuleNotFoundError(
            "No module named 'playwright' — install the page extra: "
            ".venv/bin/pip install -e \".[dev,align,youtube,envato,docx,page]\" "
            "and .venv/bin/playwright install chromium")
    from PIL import Image, ImageFilter

    try:
        fragment = parse_text_fragment(url)
    except FragmentError as e:
        raise PageCaptureError(str(e)) from e

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        try:
            context = browser.new_context(viewport=VIEWPORT, user_agent=USER_AGENT)
            page = context.new_page()
            load_page(page, strip_fragment_directive(url))
            passage = find_passage(page, fragment)
            hide_popups(page)
            rects = bring_into_view(page)
            uncovered = uncovered_overlays(page, rects) + background_image_ancestors(page)
            highlight_passage(page)
            sharp_png = page.screenshot()  # before any blur: an image's blur halo must not tint the passage
            clear_highlight(page)
            blur_images(page)
            page.wait_for_timeout(200)
            plain_png = page.screenshot()
            title = page.title()
        except PlaywrightError as e:
            raise PageCaptureError(f"browser error: {e}") from e
        finally:
            browser.close()

    base = Image.open(io.BytesIO(plain_png)).convert("RGB").filter(ImageFilter.GaussianBlur(TEXT_BLUR_RADIUS))
    sharp = Image.open(io.BytesIO(sharp_png)).convert("RGB")
    final = base.copy()
    for left, top, width, height in rects:
        box = (max(0, int(left) - MASK_PADDING_PX), max(0, int(top) - MASK_PADDING_PX),
               min(base.width, int(left + width) + MASK_PADDING_PX + 1),
               min(base.height, int(top + height) + MASK_PADDING_PX + 1))
        final.paste(sharp.crop(box), box[:2])

    os.makedirs(os.path.join(out_dir, PAGE_STILLS_DIR), exist_ok=True)
    final_path = os.path.abspath(still_path(italic_index, out_dir))
    plain_path = os.path.abspath(plain_still_path(italic_index, out_dir))
    _write_png_atomically(base, plain_path)
    _write_png_atomically(final, final_path)
    return {"passage": passage, "title": title, "still_path": final_path, "plain_path": plain_path,
            "uncovered": uncovered, "rects": rects}
