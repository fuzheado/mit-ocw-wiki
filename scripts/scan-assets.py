#!/usr/bin/env python3
"""
Asset scan for OCW courses.

Visits each course's OCW page, extracts sidebar navigation links,
and classifies them into asset types per Rule 1.2.

Usage:
    python3 scripts/scan-assets.py --slug 4-241j-the-making-of-cities-spring-2025
    python3 scripts/scan-assets.py --batch 0 100
    python3 scripts/scan-assets.py --remaining     # all unscanned courses
"""

import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

WIKI_DIR = Path(__file__).resolve().parent.parent / "wiki"

# Map sidebar link text patterns to asset types
PATTERN_MAP = [
    (r"(?i)syllabus|calendar", "Lecture-Notes"),
    (r"(?i)readings?|bibliograph|textbook|references?|reading.?list", "Reading-List"),
    (r"(?i)lecture.?note|slide|presentation", "Lecture-Notes"),
    (r"(?i)video|recording|lecture.?vid|lecture.?sequence", "Video-Transcript"),
    (r"(?i)problem.?set|assignment|homework|pset|exercise", "Problem-Set"),
    (r"(?i)exam|quiz|test|midterm|final", "Problem-Set"),
    (r"(?i)solution|answer.?key", "Problem-Set"),
    (r"(?i)project|paper|essay|report|writing", "Problem-Set"),
    (r"(?i)image|photo|gallery|diagram|figure", "Image-Gallery"),
    (r"(?i)studio|lab|recitation|tutorial", "Lecture-Notes"),
    (r"(?i)unit\s+\d", "Lecture-Notes"),
    (r"(?i)download", "Resource"),
]


def classify_link(text: str) -> str:
    """Classify a sidebar link into an asset type based on its text."""
    for pattern, asset_type in PATTERN_MAP:
        if re.search(pattern, text):
            return asset_type
    return "Resource"


def fetch_page(url: str) -> str:
    """Fetch a URL and return the text content."""
    req = Request(url, headers={"User-Agent": "OCW-LLM-Wiki/1.0"})
    try:
        resp = urlopen(req, timeout=15)
        return resp.read().decode("utf-8", errors="replace")
    except HTTPError as e:
        print(f"  HTTP {e.code} for {url}")
        return ""
    except Exception as e:
        print(f"  Error: {e}")
        return ""


def scan_course(slug: str) -> list:
    """Scan a single course page and return categorized assets."""
    url = f"https://ocw.mit.edu/courses/{slug}/"
    html = fetch_page(url)
    if not html:
        return []

    # Find sidebar links: look for href patterns under Browse Course Material
    # OCW sidebar links look like: href="/courses/{slug}/pages/..."
    # or href="/courses/{slug}/video_galleries/..."
    # or href="/courses/{slug}/lists/..."
    # or href="/courses/{slug}/resources/..."
    pattern = re.compile(
        r'href="(/courses/' + re.escape(slug) + r'/(?:pages|video_galleries|lists|resources)/[^"]*)"'
    )
    matches = pattern.findall(html)

    # Filter to only top-level sidebar pages (one segment after /pages/ or /lists/)
    # Nested pages have two+ segments: /pages/unit/welcome-to-unit-1/
    top_level = []
    for path in matches:
        # Extract the path segment after /pages/, /video_galleries/, /lists/, /resources/
        parts = path.split("/")
        # Find the index of the type segment (pages, video_galleries, lists, resources)
        for i, part in enumerate(parts):
            if part in ("pages", "video_galleries", "lists", "resources"):
                remaining = [p for p in parts[i + 1:] if p]  # strip empty strings
                # Top-level: only one segment (e.g., "syllabus")
                # Nested: two or more segments (e.g., "linear-regression/welcome-to-unit-2")
                if len(remaining) <= 1:
                    top_level.append(path)
                break

    matches = top_level
    # Also look for video gallery links specifically
    video_pattern = re.compile(
        r'href="(/courses/' + re.escape(slug) + r'/video_galleries/[^"]*)"'
    )
    matches.extend(video_pattern.findall(html))

    # Also find direct resource links (PDFs, etc.)
    resource_pattern = re.compile(
        r'href="(/courses/' + re.escape(slug) + r'/resources/[^"]*\.(?:pdf|zip|mp4|mov|png|jpg))"',
        re.IGNORECASE
    )
    resource_matches = resource_pattern.findall(html)

    assets = []
    seen = set()

    for path in matches:
        # Extract the display text near the link
        # Look for the link text in the HTML
        text_match = re.search(
            r'href="' + re.escape(path) + r'"[^>]*>([^<]+)',
            html
        )
        text = text_match.group(1).strip() if text_match else path.split("/")[-1]
        if text in seen:
            continue
        seen.add(text)
        asset_type = classify_link(text)
        assets.append((asset_type, text, f"https://ocw.mit.edu{path}"))

    for path in resource_matches:
        filename = path.split("/")[-1]
        if filename in seen:
            continue
        seen.add(filename)
        asset_type = "Image-Gallery" if re.search(r"\.(png|jpg|jpeg|gif|svg)$", filename, re.I) else "Resource"
        assets.append((asset_type, filename, f"https://ocw.mit.edu{path}"))

    # De-duplicate by type+text
    seen_dedup = set()
    unique = []
    for asset in assets:
        key = (asset[0], asset[1])
        if key not in seen_dedup:
            seen_dedup.add(key)
            unique.append(asset)

    # Cap at 20 assets to keep pages readable
    return unique[:20]


def update_course_page(slug: str, assets: list):
    """Update the Materials section of a course page with scanned assets."""
    page_path = WIKI_DIR / "courses" / f"{slug}.md"
    if not page_path.exists():
        print(f"  SKIP {slug} — no page found")
        return

    content = page_path.read_text()

    # Build the new Materials section
    material_lines = ["## Materials", ""]
    if assets:
        for asset_type, text, url in assets:
            material_lines.append(f"- [{asset_type}] [{text}]({url})")
    else:
        material_lines.append("*No assets found.*")

    material_lines.append("")

    new_material_section = "\n".join(material_lines)

    # Replace existing Materials section or add after Course Info
    if "## Materials" in content:
        content = re.sub(
            r"## Materials\n.*?(?=\n## |\n---|$)",
            new_material_section,
            content,
            flags=re.DOTALL
        )
    else:
        # Add after the License line in Course Info
        content = content.replace(
            "- **License:** CC BY-NC-SA\n",
            f"- **License:** CC BY-NC-SA\n\n{new_material_section}"
        )

    page_path.write_text(content)
    print(f"  updated {slug} ({len(assets)} assets)")


def main():
    args = sys.argv[1:]

    if len(args) >= 2 and args[0] == "--batch":
        offset = int(args[1])
        limit = int(args[2]) if len(args) > 2 else 100
        slugs = sorted(f.name.replace(".md", "") for f in (WIKI_DIR / "courses").iterdir() if f.name.endswith(".md"))
        batch = slugs[offset:offset + limit]
        print(f"Scanning batch {offset}-{offset + len(batch)} ({len(batch)} courses)...")
        for slug in batch:
            assets = scan_course(slug)
            if assets:
                update_course_page(slug, assets)
            time.sleep(0.3)  # rate limit
        print(f"Done. Scanned {len(batch)} courses.")

    elif len(args) >= 1 and args[0] == "--slug":
        slug = args[1]
        print(f"Scanning {slug}...")
        assets = scan_course(slug)
        for at, text, url in assets:
            print(f"  [{at}] {text} -> {url}")
        if assets:
            update_course_page(slug, assets)

    elif len(args) >= 1 and args[0] == "--remaining":
        # Find courses without proper asset scans
        slugs = sorted(f.name.replace(".md", "") for f in (WIKI_DIR / "courses").iterdir() if f.name.endswith(".md"))
        # Count how many have been scanned
        scanned = 0
        remaining = []
        for slug in slugs:
            content = (WIKI_DIR / "courses" / f"{slug}.md").read_text()
            # A scanned page has typed tags like [Lecture-Notes] or [Reading-List]
            # An unscanned one has generic tags like [Lecture Notes]
            if re.search(r"\[(Lecture-Notes|Video-Transcript|Problem-Set|Reading-List|Image-Gallery)\]", content):
                scanned += 1
            else:
                remaining.append(slug)
        print(f"{scanned} scanned, {len(remaining)} remaining")
        if remaining:
            batch = remaining[:100]
            print(f"Scanning next 100...")
            for slug in batch:
                assets = scan_course(slug)
                if assets:
                    update_course_page(slug, assets)
                time.sleep(0.3)

    else:
        print(__doc__)


if __name__ == "__main__":
    main()
