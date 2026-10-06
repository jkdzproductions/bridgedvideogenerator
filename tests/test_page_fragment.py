import pytest

from page_intake.fragment import (
    FragmentError, TextFragment, has_text_fragment, parse_text_fragment, strip_fragment_directive)
from page_intake.paths import plain_path_for, plain_still_path, still_path


def test_plain_start_text_is_percent_decoded():
    fragment = parse_text_fragment("https://x.com/a#:~:text=hello%20world")
    assert fragment == TextFragment(start="hello world")


def test_start_and_end():
    fragment = parse_text_fragment("https://x.com/a#:~:text=population%20of,to%20relocate")
    assert fragment == TextFragment(start="population of", end="to relocate")


def test_prefix_and_suffix_are_split_off():
    fragment = parse_text_fragment("https://x.com/a#:~:text=the%20-,island,-nation")
    assert fragment == TextFragment(start="island", prefix="the ", suffix="nation")


def test_prefix_start_end_suffix_together():
    fragment = parse_text_fragment("https://x.com/a#:~:text=pre-,start,end,-suf")
    assert fragment == TextFragment(start="start", end="end", prefix="pre", suffix="suf")


def test_encoded_comma_and_utf8_stay_inside_the_text():
    fragment = parse_text_fragment("https://x.com/a#:~:text=Pitcairn%2C%20it%E2%80%99s")
    assert fragment.start == "Pitcairn, it’s"
    assert fragment.end is None


def test_first_text_directive_wins():
    fragment = parse_text_fragment("https://x.com/a#:~:text=first&text=second")
    assert fragment.start == "first"


def test_ordinary_anchor_before_the_directive_is_allowed():
    url = "https://x.com/a#section:~:text=hello"
    assert has_text_fragment(url)
    assert parse_text_fragment(url).start == "hello"


@pytest.mark.parametrize("url", [
    "https://x.com/a",
    "https://x.com/a#intro",
    "https://x.com/a#:~:selector(x)",
    "https://x.com/a?text=hello",
])
def test_no_highlight_means_no_text_fragment(url):
    assert not has_text_fragment(url)
    with pytest.raises(FragmentError, match="no #:~:text= highlight"):
        parse_text_fragment(url)


@pytest.mark.parametrize("url", [
    "https://x.com/a#:~:text=",
    "https://x.com/a#:~:text=%20",
    "https://x.com/a#:~:text=a,b,c",
    "https://x.com/a#:~:text=a,",
])
def test_malformed_fragment_raises(url):
    with pytest.raises(FragmentError):
        parse_text_fragment(url)


def test_strip_removes_only_the_directive():
    assert strip_fragment_directive("https://x.com/a#:~:text=hi") == "https://x.com/a"
    assert strip_fragment_directive("https://x.com/a#section:~:text=hi") == "https://x.com/a#section"
    assert strip_fragment_directive("https://x.com/a#section") == "https://x.com/a#section"
    assert strip_fragment_directive("https://x.com/a") == "https://x.com/a"


def test_still_paths():
    assert still_path(3) == "page_stills/page_3.png"
    assert plain_still_path(3) == "page_stills/page_3_plain.png"
    assert still_path(3, "run") == "run/page_stills/page_3.png"
    assert plain_path_for("page_stills/page_3.png") == "page_stills/page_3_plain.png"
