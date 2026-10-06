"""archival_review.html: one page listing every archival pick with its source and license so Josh can
check them after Stage 2. Nothing in the pipeline waits for it."""
import html
import json
import os
import pathlib

_STYLE = """body{font-family:system-ui,sans-serif;max-width:960px;margin:24px auto;padding:0 16px;color:#1b1b1b}
section{border:1px solid #ccc;border-radius:8px;padding:12px 16px;margin:16px 0}
.items{display:flex;flex-wrap:wrap;gap:12px}.item{width:280px}.item img{width:100%;border-radius:4px}
.meta{color:#555;font-size:13px}.rejected{color:#7a2d2d;font-size:13px}"""


def _e(value) -> str:
    return html.escape(str(value if value is not None else ""))


def _link(url, text) -> str:
    """An anchor only for http(s) URLs; anything else (javascript:, data:, ...) is shown as plain escaped text."""
    if isinstance(url, str) and url.strip().lower().startswith(("http://", "https://")):
        return f'<a href="{_e(url)}">{_e(text)}</a>'
    return _e(text)


def _image(local_path) -> str:
    if not isinstance(local_path, str) or not local_path or not os.path.isabs(local_path):
        return ""
    return f'<img src="{_e(pathlib.Path(local_path).as_uri())}" alt="">'


def _dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def _list(value) -> list:
    return value if isinstance(value, list) else []


def _seconds(value) -> str:
    return f"{value:.1f}s" if isinstance(value, (int, float)) and not isinstance(value, bool) else "?s"


def _item(item: dict) -> str:
    item = _dict(item)
    year = _e(item["year"]) if item.get("year") is not None else "year unknown"
    kind = f'<b>{_e(item["kind"])}</b> · ' if item.get("kind") else ""
    return (f'<div class="item">{_image(item.get("local_path"))}'
            f'<div>{_link(item.get("page_url"), item.get("title", "unknown"))}</div>'
            f'<div class="meta">{kind}{_e(item.get("source", "unknown"))} · {year} · {_e(item.get("creator", ""))}<br>'
            f'License: {_e(item.get("rights", "unknown"))}</div></div>')


def _pick(pick: dict) -> str:
    pick = _dict(pick)
    rejected_list = [_dict(r) for r in _list(pick.get("rejected"))]
    rejected = "".join(
        f'<li>{_link(r.get("page_url"), r.get("title", "unknown"))}: {_e(r.get("reason", "unknown"))}</li>'
        for r in rejected_list)
    rejected_block = f'<details class="rejected"><summary>Rejected ({len(rejected_list)})</summary><ul>{rejected}</ul></details>' \
        if rejected_list else ""
    return (f'<section><h2>Beat {_e(pick.get("beat_index", "?"))} · {_seconds(pick.get("start"))} to '
            f'{_seconds(pick.get("end"))} · {_e(pick.get("kind", "?"))} · era {_e(pick.get("era", "?"))}</h2>'
            f'<div>{_e(pick.get("subject", ""))}</div>'
            f'<div class="meta">Judge: {_e(pick.get("reasoning", "unknown"))}</div>'
            f'<div class="items">{"".join(_item(i) for i in _list(pick.get("items")))}</div>{rejected_block}</section>')


def build_review_html(picks: list[dict]) -> str:
    body = "".join(_pick(p) for p in picks) if picks else "<p>No archival cuts in this video.</p>"
    return (f'<!doctype html><html><head><meta charset="utf-8"><title>Archival picks</title>'
            f'<style>{_STYLE}</style></head><body><h1>Archival picks</h1>{body}</body></html>')


def write_review(picks_path: str = "archival_picks.json", html_path: str = "archival_review.html") -> str:
    picks = []
    if os.path.exists(picks_path):
        with open(picks_path, encoding="utf-8") as f:
            text = f.read()
        picks = json.loads(text) if text.strip() else []
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(build_review_html(picks))
    return os.path.abspath(html_path)
