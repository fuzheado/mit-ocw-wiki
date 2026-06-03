#!/usr/bin/env python3
"""
Ingest a single OCW course from its URL into the local wiki.

Creates a wiki page with YAML frontmatter by scraping the OCW course page
and looking up the MIT Learn API. If the API doesn't have the course yet,
creates a minimal stub with what's available from the page.

Usage:
    python3 scripts/ingest-one.py "https://ocw.mit.edu/courses/14-12-economic-applications-of-game-theory-fall-2025/"
    python3 scripts/ingest-one.py "14-12-economic-applications-of-game-theory-fall-2025"
"""

import sys
import os
import re
import json
import urllib.request
import urllib.parse
from datetime import datetime, timezone

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
WIKI_COURSES_DIR = os.path.abspath(os.path.join(SCRIPTS_DIR, "..", "wiki", "courses"))
RAW_DIR = os.path.abspath(os.path.join(SCRIPTS_DIR, "..", "raw"))
UA = "MIT OCW Bot/1.0 (https://meta.wikimedia.org/wiki/Wiki_MIT; andrew.lih@gmail.com) ContentGapResearch"


def extract_slug(url: str) -> str:
    """Extract course slug from URL or return as-is if already a slug."""
    url = url.rstrip("/")
    if url.startswith("https://ocw.mit.edu/courses/"):
        path = urllib.parse.urlparse(url).path.rstrip("/")
        if path.startswith("/courses/"):
            return path[len("/courses/"):]
    return url


def parse_course_id(slug: str) -> str:
    """Derive MIT course ID from slug. E.g., '14-12-...' → '14.12'."""
    m = re.match(r'^(\d+|[A-Z]+)-(\d+[A-Z0-9]*)', slug)
    if m:
        return f"{m.group(1)}.{m.group(2)}"
    return slug


def scrape_ocw_page(url: str) -> dict:
    """Scrape basic course info from the OCW page HTML."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8")
    except Exception as e:
        print(f"  ⚠️  Could not fetch OCW page: {e}", file=sys.stderr)
        return {}

    info = {}

    # Title from <title> tag
    m = re.search(r'<title>(.*?)</title>', html)
    if m:
        full_title = m.group(1).strip()
        # "Economic Applications of Game Theory | Economics | MIT OpenCourseWare"
        parts = full_title.split("|")
        info["title"] = parts[0].strip()

    # Description from meta tags
    for pat in [
        r'<meta[^>]+name="description"[^>]+content="([^"]*)"',
        r'<meta[^>]+property="og:description"[^>]+content="([^"]*)"',
    ]:
        m = re.search(pat, html)
        if m:
            desc = m.group(1).strip()
            if desc:
                info["description"] = desc
                break

    # Department from breadcrumb or URL
    m = re.search(r'courses/([a-zA-Z0-9]+)-', url)
    if m:
        info["department"] = m.group(1)

    return info


def lookup_api(slug: str, course_id: str, title: str) -> dict:
    """Try to find the course in the MIT Learn API by searching across all pages."""
    api_base = "https://api.learn.mit.edu/api/v1/courses/"
    params = urllib.parse.urlencode({"offered_by": "ocw", "limit": 100})
    offset = 0

    while True:
        url = f"{api_base}?{params}&offset={offset}"
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
        except Exception:
            break

        results = data.get("results", [])
        if not results:
            break

        for c in results:
            c_url = (c.get("url") or "")
            c_slug = (c.get("slug") or "")
            # Best match: slug in URL (most reliable — course_id can collide)
            if slug in c_url:
                return c
            # Fall back to slug field
            if c_slug and c_slug == slug:
                return c

        offset += len(results)
        if offset >= data.get("count", 0):
            break

    return {}


def build_frontmatter(api_data: dict, scraped: dict, slug: str, course_id: str) -> dict:
    """Build YAML frontmatter from API and scraped data."""
    fm = {}

    # Prefer API data, fall back to scraped
    fm["url"] = api_data.get("url") or f"https://ocw.mit.edu/courses/{slug}/"
    fm["course_id"] = api_data.get("course_id") or course_id
    fm["title"] = api_data.get("title") or scraped.get("title") or slug
    fm["year_published"] = api_data.get("year_published") or ""

    # Instructors
    instructors = api_data.get("instructors", [])
    if isinstance(instructors, list):
        fm["instructors"] = [i.get("name", "") if isinstance(i, dict) else str(i) for i in instructors if i]
    else:
        fm["instructors"] = []

    # Level
    level = api_data.get("level", [])
    if isinstance(level, list):
        fm["level"] = [str(l) for l in level if l]
    else:
        fm["level"] = [str(level)] if level else []

    # Department
    fm["department"] = api_data.get("department") or scraped.get("department", "")

    # Topics — API returns dicts like {"id": ..., "name": "Economics"}
    topics = api_data.get("topics", [])
    if isinstance(topics, list):
        names = []
        for t in topics:
            if isinstance(t, dict):
                name = t.get("name", "")
                if name:
                    names.append(name)
            elif isinstance(t, str):
                names.append(t)
        fm["topics"] = names
    else:
        fm["topics"] = [str(topics)] if topics else []

    # License
    licenses = api_data.get("license", [])
    if isinstance(licenses, list) and licenses:
        fm["license"] = str(licenses[0]) if isinstance(licenses[0], str) else licenses[0].get("name", "")
    else:
        fm["license"] = str(licenses) if licenses else "CC BY-NC-SA"

    fm["type"] = "course"

    api_id = api_data.get("id", "")
    if api_id:
        fm["api_id"] = api_id

    return fm


def yaml_value(val):
    """Format a value as YAML."""
    if isinstance(val, list):
        if not val:
            return "[]"
        items = ", ".join(f'"{v}"' for v in val)
        return f"[{items}]"
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, int):
        return str(val)
    if isinstance(val, float):
        return str(val)
    return f'"{val}"'


def write_course_page(fm: dict, slug: str, scraped: dict):
    """Write the course wiki page."""
    filepath = os.path.join(WIKI_COURSES_DIR, f"{slug}.md")

    lines = ["---"]
    for key in ["url", "course_id", "title", "year_published", "instructors", "level", "department", "topics", "license", "type"]:
        val = fm.get(key)
        if val is None or (isinstance(val, list) and not val):
            continue
        lines.append(f"{key}: {yaml_value(val)}")

    if "api_id" in fm:
        lines.append(f'api_id: {fm["api_id"]}')

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines.append(f'last_modified: "{now}"')
    lines.append("---")
    lines.append("")
    lines.append(f"# {fm['title']}")

    desc = scraped.get("description", "")
    if desc:
        lines.append("")
        lines.append(desc)

    lines.append("")
    content = "\n".join(lines) + "\n"

    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    return filepath


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    url = sys.argv[1]
    slug = extract_slug(url)
    course_id = parse_course_id(slug)

    print(f"\n  Slug: {slug}")
    print(f"  course_id: {course_id}")

    # Check if already exists
    existing = os.path.join(WIKI_COURSES_DIR, f"{slug}.md")
    if os.path.exists(existing):
        print(f"  ⚠️  Already exists: {existing}", file=sys.stderr)
        sys.exit(1)

    # Scrape OCW page
    print(f"  Scraping OCW page...", file=sys.stderr)
    scraped = scrape_ocw_page(f"https://ocw.mit.edu/courses/{slug}/")
    if scraped:
        print(f"  Found: {scraped.get('title', '?')}", file=sys.stderr)

    # Look up API
    print(f"  Searching MIT Learn API...", file=sys.stderr)
    api_data = lookup_api(slug, course_id, scraped.get("title", ""))
    if api_data:
        print(f"  Found in API: {api_data.get('title', '?')}", file=sys.stderr)
    else:
        print(f"  Not in API (will create stub)", file=sys.stderr)

    # Build and write page
    fm = build_frontmatter(api_data, scraped, slug, course_id)
    filepath = write_course_page(fm, slug, scraped)

    print(f"\n  ✅ Created: {filepath}", file=sys.stderr)
    print(f"\n  Regenerate index:")
    print(f"    python3 scripts/regenerate-index.py")
    print(f"\n  Now use ad-hoc-match:")
    print(f"    python3 scripts/ad-hoc-match.py \"{slug}\"")


if __name__ == "__main__":
    main()
