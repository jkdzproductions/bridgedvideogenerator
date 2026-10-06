"""Read a Word (.docx) script into the markup the rest of the pipeline consumes: italic phrases
mark graphics (`*italic*`, and a hyperlink on an italic phrase points at a graph image) and bold
phrases mark talking heads (`**bold**`).

Walks the raw WordprocessingML instead of python-docx's `paragraph.runs`, because real Word
files put hyperlinked text in places `.runs` does not see: inside `w:hyperlink` elements, inside
`HYPERLINK` field codes (`w:fldSimple`, or `w:fldChar` begin/separate/end runs), inside tracked
insertions (`w:ins`) and content controls (`w:sdt`).
"""
import re
from dataclasses import dataclass
from typing import NamedTuple, Optional
from urllib.parse import parse_qs, urlsplit

from page_intake.fragment import FragmentError, has_text_fragment, parse_text_fragment
from shot_list.markup import parse_markup

_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

# Word's typographic spaces become plain spaces; invisible characters are removed. Otherwise a
# non-breaking space or a zero-width space inside a marked phrase glues two spoken words into one
# script word, which the audio alignment can never match.
_TEXT_FIXES = str.maketrans({
    " ": " ", " ": " ", " ": " ",
    "​": None, "‌": None, "‍": None, "⁠": None, "﻿": None,
    "­": None,
})
_OFF_VALUES = {"0", "false", "off", "none"}
# Children to descend into (their runs are real, visible text). Everything else under a
# paragraph that is not listed here or handled explicitly (w:del, w:moveFrom, w:pPr, bookmarks,
# comments, proofing marks) contributes no text.
_CONTAINERS = {"ins", "moveTo", "smartTag", "customXml", "dir", "bdo", "sdt", "sdtContent"}

_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".webp")


def is_image_url(url: str) -> bool:
    """An http(s) URL whose path ends in an image file extension (a ?query or #fragment is
    ignored). Whether the server really sends an image is checked later, in Step 1d."""
    try:
        parts = urlsplit(url.strip())
    except ValueError:  # e.g. "http://[bad/x": a malformed link is just not an image link
        return False
    return parts.scheme.lower() in ("http", "https") and parts.path.lower().endswith(_IMAGE_EXTENSIONS)


class DocxScriptError(ValueError):
    """The .docx can't be turned into a script safely; the message names the offending text."""


class ScriptInput(NamedTuple):
    marked_text: str  # the script with * around italic and ** around bold spans, paragraphs joined by "\n"
    links: list  # [{"italic_index": int, "text": str, "url": str}], one per linked italic (graphic) span that is not a page highlight
    ignored_links: list  # [{"text": str, "url": str}], links on text that is not italic (bold links included)
    page_links: tuple = ()  # [{"italic_index": int, "text": str, "url": str}], italic links whose URL has a #:~:text= highlight
    image_links: tuple = ()  # [{"italic_index": int, "text": str, "url": str}], non-italic links to an image file: shown as-is


@dataclass
class _Piece:
    text: str
    italic: bool
    bold: bool
    url: Optional[str]


def _w(tag: str) -> str:
    return f"{{{_W}}}{tag}"


def _local(tag) -> str:
    return tag.split("}", 1)[1] if isinstance(tag, str) and "}" in tag else ""


def _is_on(toggle_el) -> bool:
    return toggle_el.get(_w("val"), "true").lower() not in _OFF_VALUES


class _FormatResolver:
    """Whether a run is italic (tag "i") or bold (tag "b"): direct formatting on the run first,
    then the run's character style and that style's basedOn chain. A paragraph style's italic or
    bold (e.g. a Heading) does not count."""

    def __init__(self, styles_element, tag: str):
        self._tag = tag
        self._styles = {}
        if styles_element is not None:
            for style in styles_element.findall(_w("style")):
                self._styles[style.get(_w("styleId"))] = style

    def run_has(self, r) -> bool:
        rpr = r.find(_w("rPr"))
        if rpr is None:
            return False
        direct = rpr.find(_w(self._tag))
        if direct is not None:
            return _is_on(direct)
        rstyle = rpr.find(_w("rStyle"))
        return rstyle is not None and self._style_has(rstyle.get(_w("val")), set())

    def _style_has(self, style_id, seen) -> bool:
        style = self._styles.get(style_id)
        if style is None or style_id in seen:
            return False
        seen.add(style_id)
        rpr = style.find(_w("rPr"))
        if rpr is not None and rpr.find(_w(self._tag)) is not None:
            return _is_on(rpr.find(_w(self._tag)))
        based_on = style.find(_w("basedOn"))
        return based_on is not None and self._style_has(based_on.get(_w("val")), seen)


_GOOGLE_REDIRECT_HOSTS = ("google.com", "www.google.com")


def unwrap_google_redirect(url: str) -> str:
    """Google Docs writes a link as `google.com/url?q=<real address>&sa=D&...`, with the real
    address (and any #:~:text= highlight) percent-encoded inside. Return the real address; any
    other URL, or a redirect with no usable http(s) target, comes back unchanged."""
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return url
    if (parts.hostname or "").lower() not in _GOOGLE_REDIRECT_HOSTS or parts.path != "/url":
        return url
    query = parse_qs(parts.query)
    for key in ("q", "url"):
        target = (query.get(key) or [""])[0]
        if target.lower().startswith(("http://", "https://")):
            return target
    return url


_INSTR_TOKEN = re.compile(r'"([^"]*)"|(\S+)')


def _url_from_field(instr: str) -> Optional[str]:
    """`HYPERLINK "https://x" \\l "anchor" \\o "tip"` -> "https://x#anchor". None if the field
    is not a HYPERLINK (e.g. PAGE, REF): its result text is ordinary text."""
    tokens = [quoted if quoted or bare == "" else bare for quoted, bare in _INSTR_TOKEN.findall(instr)]
    if not tokens or tokens[0].upper() != "HYPERLINK":
        return None
    target, anchor, i = "", "", 1
    while i < len(tokens):
        token = tokens[i]
        if token.lower() == "\\l" and i + 1 < len(tokens):
            anchor, i = tokens[i + 1], i + 2
        elif token.lower() in ("\\o", "\\t") and i + 1 < len(tokens):
            i += 2
        elif token.startswith("\\"):
            i += 1
        else:
            target = target or token
            i += 1
    return unwrap_google_redirect(target + (f"#{anchor}" if anchor else ""))


class _Walker:
    def __init__(self, document):
        self._part = document.part
        self._italic = _FormatResolver(document.styles.element, "i")
        self._bold = _FormatResolver(document.styles.element, "b")
        # Complex fields (w:fldChar begin/separate/end) can wrap several runs and nest, so their
        # state lives across the whole walk: [{"instr": str, "in_result": bool}].
        self._fields: list = []

    def _field_url(self) -> Optional[str]:
        for field in reversed(self._fields):
            if field["in_result"]:
                url = _url_from_field(field["instr"])
                if url is not None:
                    return url
        return None

    def _hyperlink_url(self, el) -> str:
        rel_id = el.get(f"{{{_R}}}id")
        anchor = el.get(_w("anchor"))
        target = ""
        if rel_id:
            if rel_id not in self._part.rels:
                raise DocxScriptError(f"hyperlink relationship {rel_id!r} is missing from the .docx")
            target = self._part.rels[rel_id].target_ref
        return unwrap_google_redirect(target + (f"#{anchor}" if anchor else ""))

    def pieces(self, el, url: Optional[str] = None) -> list:
        out: list = []
        for child in el:
            name = _local(child.tag)
            if name == "r":
                out.extend(self._run(child, url))
            elif name == "hyperlink":
                out.extend(self.pieces(child, self._hyperlink_url(child)))
            elif name == "fldSimple":
                out.extend(self.pieces(child, _url_from_field(child.get(_w("instr"), "")) or url))
            elif name in _CONTAINERS:
                out.extend(self.pieces(child, url))
        return out

    def _run(self, r, url: Optional[str]) -> list:
        italic = self._italic.run_has(r)
        bold = self._bold.run_has(r)
        out: list = []
        for child in r:
            name = _local(child.tag)
            if name == "fldChar":
                kind = child.get(_w("fldCharType"))
                if kind == "begin":
                    self._fields.append({"instr": "", "in_result": False})
                elif kind == "separate" and self._fields:
                    self._fields[-1]["in_result"] = True
                elif kind == "end" and self._fields:
                    self._fields.pop()
                continue
            if name == "instrText":
                if self._fields and not self._fields[-1]["in_result"]:
                    self._fields[-1]["instr"] += child.text or ""
                continue
            if any(not f["in_result"] for f in self._fields):
                continue  # inside a field's instruction part: not visible text
            text = {"t": child.text or "", "tab": "\t", "br": "\n", "cr": "\n",
                    "noBreakHyphen": "-"}.get(name)
            if text:
                text = text.translate(_TEXT_FIXES)
                if italic and bold and text.strip():
                    raise DocxScriptError(
                        f"{text.strip()[:80]!r} is both bold and italic — use italic for a graphic "
                        "or bold for a talking head, not both")
                out.append(_Piece(text, italic, bold, url or self._field_url()))
        return out


def _paragraph_elements(body):
    for child in body:
        name = _local(child.tag)
        if name == "p":
            yield child
        elif name == "sdt":
            content = child.find(_w("sdtContent"))
            if content is not None:
                yield from _paragraph_elements(content)
        elif name == "tbl":
            text = "".join(t.text or "" for t in child.iter(_w("t")))[:80]
            raise DocxScriptError(
                f"the .docx contains a table ({text!r}...) — tables are not read; move the "
                "script text out of the table")


def _check_link(text: str, url: str) -> None:
    if not url.lower().startswith(("http://", "https://")):
        raise DocxScriptError(
            f"italic phrase {text!r} links to {url!r}, which is not an http(s) image address — "
            "a linked italic phrase must link directly to a graph image")


def _check_image_neighbours(groups: list) -> None:
    """A linked image phrase must be separated from any other marked phrase by whitespace: the
    emitted `*` markers of two touching phrases would merge into a `**` marker."""
    for i, (kind, text, _url) in enumerate(groups):
        if kind != "image" or not any(ch.isalnum() for ch in text):
            continue
        for j, left in ((i - 1, True), (i + 1, False)):
            if not 0 <= j < len(groups) or groups[j][0] == "plain":
                continue
            other = groups[j][1]
            if not any(ch.isalnum() for ch in other):
                continue
            touching = (not other[-1:].isspace() and not text[:1].isspace()) if left else (
                not text[-1:].isspace() and not other[:1].isspace())
            if touching:
                raise DocxScriptError(
                    f"the linked image phrase {text.strip()!r} touches another italic, bold or "
                    "linked-image phrase with no space between them — put a space between them")


def _check_link_edges(groups: list) -> None:
    """Two adjacent italic groups exist only because their links differ (a link starts or ends
    there). They must be separated by whitespace: touching, their `*` markers would collide."""
    for (kind, text, _url), (next_kind, next_text, _next_url) in zip(groups, groups[1:]):
        if kind != "graphic" or next_kind != "graphic":
            continue
        if not any(ch.isalnum() for ch in text) or not any(ch.isalnum() for ch in next_text):
            continue
        if not text[-1:].isspace() and not next_text[:1].isspace():
            raise DocxScriptError(
                f"the link on {text.strip()!r} / {next_text.strip()!r} starts or ends in the middle "
                "of a word — start and end the link at a word boundary (a space), so each italic "
                "phrase is either fully linked or fully unlinked")


def _paragraph_markup(pieces: list, links: list, ignored: list, first_italic_index: int, page_links: list,
                      image_links: list):
    """-> (marked text, plain text, graphic spans, talking-head spans as (start, end) in plain text)."""
    groups: list = []  # [kind, text, url]
    previous_ignored = None
    # A hyperlink that runs past its italic text (the rest of it is not italic) is still one link
    # to that graph, not a second, raw image: a non-italic piece is a show-as-is image only when no
    # piece of its run of consecutive same-URL pieces is italic.
    in_italic_link = [False] * len(pieces)
    i = 0
    while i < len(pieces):
        j = i
        while j < len(pieces) and pieces[j].url and pieces[j].url == pieces[i].url:
            j += 1
        if j == i:
            i += 1
            continue
        if any(piece.italic for piece in pieces[i:j]):
            in_italic_link[i:j] = [True] * (j - i)
        i = j
    for index, piece in enumerate(pieces):
        if piece.italic:
            kind = "graphic"
        elif piece.bold:
            kind = "talking_head"
        elif piece.url and not in_italic_link[index] and is_image_url(piece.url):
            kind = "image"
        else:
            kind = "plain"
        if piece.url and kind not in ("graphic", "image"):
            if previous_ignored is not None and previous_ignored["url"] == piece.url:
                previous_ignored["text"] += piece.text
            else:
                previous_ignored = {"text": piece.text, "url": piece.url}
                ignored.append(previous_ignored)
        else:
            previous_ignored = None
        last = groups[-1] if groups else None
        if kind == "plain":
            groups.append(["plain", piece.text, None])
        elif kind == "talking_head" and last and last[0] == "talking_head":
            last[1] += piece.text
        elif kind == "graphic" and last and last[0] == "graphic" and last[2] == piece.url:
            # a hyperlink edge is a span edge: italic pieces merge only when they carry the same
            # URL (both unlinked, or both the identical link)
            last[1] += piece.text
        elif kind == "image" and last and last[0] == "image" and last[2] == piece.url:
            last[1] += piece.text
        else:
            groups.append([kind, piece.text, piece.url if kind in ("graphic", "image") else None])
    _check_image_neighbours(groups)
    _check_link_edges(groups)

    marked, plain, graphic_spans, talking_spans = [], [], [], []
    plain_len = 0
    for kind, text, url in groups:
        core = text.strip()
        if kind == "plain" or not any(ch.isalnum() for ch in core):
            if kind in ("graphic", "image") and url:  # a link on italic or image whitespace/punctuation only: nothing to show
                ignored.append({"text": text, "url": url})
            marked.append(text)
            plain.append(text)
            plain_len += len(text)
            continue
        lead = text[: len(text) - len(text.lstrip())]
        trail = text[len(text.rstrip()):]
        start = plain_len + len(lead)
        if kind == "graphic":
            if url:
                _check_link(core, url)
                entry = {"italic_index": first_italic_index + len(graphic_spans), "text": core, "url": url}
                if has_text_fragment(url):
                    try:
                        parse_text_fragment(url)  # fail now, in Step 1a, not after a browser launch
                    except FragmentError as e:
                        raise DocxScriptError(f"italic phrase {core!r}: {e}") from e
                    page_links.append(entry)
                else:
                    links.append(entry)
            marked.append(f"{lead}*{core}*{trail}")
            graphic_spans.append((start, start + len(core)))
        elif kind == "image":
            image_links.append({"italic_index": first_italic_index + len(graphic_spans), "text": core, "url": url})
            marked.append(f"{lead}*{core}*{trail}")
            graphic_spans.append((start, start + len(core)))
        else:
            marked.append(f"{lead}**{core}**{trail}")
            talking_spans.append((start, start + len(core)))
        plain.append(text)
        plain_len += len(text)
    return "".join(marked), "".join(plain), graphic_spans, talking_spans


def read_docx_script(path: str) -> ScriptInput:
    import docx  # optional extra "docx"; imported here so `import script_input` never needs it

    try:
        document = docx.Document(path)
    except Exception as e:  # python-docx raises several unrelated types for a bad file
        raise DocxScriptError(f"could not open {path!r} as a Word .docx file: {e}") from e

    walker = _Walker(document)
    links: list = []
    page_links: list = []
    image_links: list = []
    ignored: list = []
    marked_paragraphs, plain_paragraphs, all_graphic, all_talking = [], [], [], []
    offset = 0
    for p in _paragraph_elements(document.element.body):
        pieces = walker.pieces(p)
        paragraph_text = "".join(piece.text for piece in pieces)
        if "*" in paragraph_text:
            raise DocxScriptError(
                f"the document already contains a literal '*' in {paragraph_text.strip()[:80]!r} "
                "— remove it; '*' is reserved for marking italic and bold")
        marked, plain, graphic, talking = _paragraph_markup(pieces, links, ignored, len(all_graphic), page_links,
                                                            image_links)
        marked_paragraphs.append(marked)
        plain_paragraphs.append(plain)
        all_graphic.extend((offset + s, offset + e) for s, e in graphic)
        all_talking.extend((offset + s, offset + e) for s, e in talking)
        offset += len(plain) + 1  # the "\n" joining paragraphs

    marked_text = "\n".join(marked_paragraphs)
    plain_text = "\n".join(plain_paragraphs)
    if not plain_text.strip():
        raise DocxScriptError(f"{path!r} contains no text")

    # Self-check: the markup must parse back to exactly the text and spans read from the
    # document. A stray '*' next to a marked phrase would otherwise silently shift a span.
    try:
        parsed = parse_markup(marked_text)
    except ValueError as e:
        raise DocxScriptError(
            f"marked text (italic, bold or a linked image) touches other marked text with no space "
            f"between them, or an asterisk collides with the markers ({e}) — put a space between marked phrases"
        ) from e
    if (parsed.plain_text != plain_text or parsed.graphic_spans != all_graphic
            or parsed.talking_head_spans != all_talking):
        bad = next((plain_text[s:e] for s, e in all_graphic + all_talking
                    if (s, e) not in parsed.graphic_spans + parsed.talking_head_spans), plain_text[:80])
        raise DocxScriptError(f"markers do not round-trip near {bad!r} — check the italic/bold formatting there")
    return ScriptInput(marked_text, links, ignored, page_links, image_links)
