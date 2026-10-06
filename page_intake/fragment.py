"""Parse Chrome's "Copy link to highlight" URLs: the `#:~:text=` text-fragment directive.

Syntax: `text=[prefix-,]start[,end][,-suffix]`, every part percent-encoded (a literal comma inside
the text is `%2C`). Several directives may be joined with `&`; only the first `text=` is used.
"""
import urllib.parse
from dataclasses import dataclass
from typing import Optional

DIRECTIVE = ":~:"


class FragmentError(ValueError):
    """The URL has no usable `#:~:text=` highlight; the message says why."""


@dataclass(frozen=True)
class TextFragment:
    start: str
    end: Optional[str] = None
    prefix: Optional[str] = None
    suffix: Optional[str] = None


def _text_values(url: str) -> list:
    fragment = url.partition("#")[2]
    if DIRECTIVE not in fragment:
        return []
    directives = fragment.partition(DIRECTIVE)[2].split("&")
    return [d[len("text="):] for d in directives if d.startswith("text=")]


def has_text_fragment(url: str) -> bool:
    return bool(_text_values(url))


def parse_text_fragment(url: str) -> TextFragment:
    values = _text_values(url)
    if not values:
        raise FragmentError(f"{url!r} has no #:~:text= highlight")
    parts = values[0].split(",")
    prefix = suffix = None
    if len(parts) > 1 and parts[0].endswith("-"):
        prefix = urllib.parse.unquote(parts.pop(0)[:-1])
    if len(parts) > 1 and parts[-1].startswith("-"):
        suffix = urllib.parse.unquote(parts.pop()[1:])
    if len(parts) not in (1, 2):
        raise FragmentError(f"{url!r}: the #:~:text= highlight is malformed (too many comma-separated parts)")
    start = urllib.parse.unquote(parts[0])
    end = urllib.parse.unquote(parts[1]) if len(parts) == 2 else None
    if not start.strip() or (end is not None and not end.strip()):
        raise FragmentError(f"{url!r}: the #:~:text= highlight has an empty start or end")
    return TextFragment(start=start, end=end, prefix=prefix or None, suffix=suffix or None)


def strip_fragment_directive(url: str) -> str:
    """The URL without its `:~:...` directive; an ordinary anchor before it is kept."""
    base, hash_mark, fragment = url.partition("#")
    if not hash_mark:
        return url
    kept = fragment.partition(DIRECTIVE)[0]
    return f"{base}#{kept}" if kept else base
