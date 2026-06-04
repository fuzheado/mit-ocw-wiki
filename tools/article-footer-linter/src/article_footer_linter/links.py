"""
HTTP link checking for External links sections. (Phase 2 — scaffold.)

This module will be implemented when Phase 2 begins. It checks each
HTTP(S) URL found in the article footer for liveness, with two-strike
retry, archive.org fallback, and {{dead link}} tagging.

See docs/ARTICLE-FOOTER-LINT.md for the full spec.
"""

from typing import Optional


def check_link(url: str, timeout: int = 10, retries: int = 1) -> dict:
    """
    Check whether a URL is alive. (Stub — always returns 'unknown'.)

    Phase 2 will implement:
    1. HEAD request first, GET fallback on 405/501
    2. Two-strike retry with 5s delay
    3. Status code interpretation (2xx=alive, 3xx=follow, 4xx/5xx=dead)
    4. Wayback Machine availability check on dead links

    Returns:
        {"url": str, "status": "alive"|"dead"|"redirect"|"unknown",
         "status_code": int|None, "final_url": str|None,
         "archive_url": str|None}
    """
    return {"url": url, "status": "unknown", "status_code": None, "final_url": None, "archive_url": None}


def extract_urls_from_footer(wikitext: str) -> list[dict]:
    """
    Extract all HTTP(S) URLs from the article footer.
    (Stub — Phase 2 will handle both * [url title] and {{cite web |url=...}} formats.)

    Returns:
        [{"url": str, "format": "bare"|"cite_web", "position": int,
          "context": str, "line": str}]
    """
    return []


def tag_dead_link(wikitext: str, url_info: dict) -> str:
    """
    Append {{dead link}} after a broken external link.
    (Stub — Phase 2 implementation.)

    Args:
        wikitext: The full wikitext.
        url_info: Dict from extract_urls_from_footer identifying the link.

    Returns:
        Modified wikitext with {{dead link|date=...}} inserted.
    """
    return wikitext
