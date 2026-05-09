#!/usr/bin/env python3
"""
Batch OCW course ingester for the MIT LLM Wiki.

Fetches courses from the MIT Learn API, creates wiki pages,
and updates department/topic/instructor pages.

Usage:
    python3 scripts/ingest-batch.py --offset 0 --limit 100
    python3 scripts/ingest-batch.py --offset 100 --limit 100
    python3 scripts/ingest-batch.py --all                # all 2577 courses
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

WIKI_DIR = Path(__file__).resolve().parent.parent / "wiki"
RAW_DIR = Path(__file__).resolve().parent.parent / "raw"
API_BASE = "https://api.learn.mit.edu/api/v1/courses/"


def fetch(offset: int, limit: int = 100) -> dict:
    """Fetch one page of courses from the MIT Learn API."""
    params = urlencode({"offered_by": "ocw", "limit": limit, "offset": offset})
    url = f"{API_BASE}?{params}"
    req = Request(url, headers={"Accept": "application/json"})
    resp = urlopen(req)
    return json.loads(resp.read())


def slugify(text: str) -> str:
    """Convert a string to a wiki filename slug."""
    s = text.lower().strip()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"-+", "-", s)
    return s.strip("-")


def topic_slug(name: str) -> str:
    """Convert a topic name to its wiki slug."""
    return slugify(name)


def instructor_slug(full_name: str) -> str:
    """Convert instructor name to a wiki slug."""
    name = full_name.replace("Prof.", "").replace("Dr.", "").replace("Mr.", "").replace("Ms.", "").strip()
    return slugify(name)


def course_slug(run: dict) -> str:
    """Derive a wiki slug from a course run."""
    if run.get("slug"):
        return run["slug"].replace("courses/", "")
    url = run.get("url", "")
    if url:
        return url.replace("https://ocw.mit.edu/courses/", "").rstrip("/")
    return None

def build_course_page(course: dict, slug: str = None) -> str:
    """Generate the markdown for a single course page."""
    run = course["runs"][0]
    if not slug:
        slug = course_slug(run)
    course_id = course["course"]["course_numbers"][0]["value"]
    title = run["title"]
    description = run.get("description", "") or ""
    description = re.sub(r"<[^>]+>", "", description).strip()
    year = run.get("year", "Unknown")
    semester = run.get("semester", "Unknown")
    level_code = run["level"][0]["code"] if run.get("level") else "unknown"
    level_map = {"undergraduate": "Undergraduate", "graduate": "Graduate", "noncredit": "Non-Credit", "high_school": "High School"}
    level = level_map.get(level_code, level_code.capitalize())
    views = course.get("views", "Unknown")
    completeness = course.get("completeness", "Unknown")
    last_modified = run.get("last_modified", "Unknown")

    depts = course.get("departments", [])
    dept_links = [f"[[{d['department_id'].lower()}|{d['name']}]]" for d in depts]

    topics = course.get("topics", [])
    topic_links = [f"[[{topic_slug(t['name'])}|{t['name']}]]" for t in topics]

    instructors = run.get("instructors", [])
    instructor_names = [i["full_name"] for i in instructors]
    instructor_links = [f"[[{instructor_slug(i['full_name'])}|{i['full_name']}]]" for i in instructors]

    features = course.get("course_feature", [])

    frontmatter = {
        "url": run.get("url", ""),
        "course_id": course_id,
        "title": title,
        "year_published": year,
        "instructors": instructor_names,
        "level": [level_code],
        "department": depts[0]["department_id"] if depts else "Unknown",
        "topics": [t["name"] for t in topics],
        "license": "CC BY-NC-SA",
        "views": views,
        "completeness": completeness,
        "last_modified": last_modified,
        "type": "course",
    }

    yaml_lines = ["---"]
    for k, v in frontmatter.items():
        if isinstance(v, list):
            yaml_lines.append(f"{k}: [{', '.join(json.dumps(x) for x in v)}]")
        elif isinstance(v, str):
            yaml_lines.append(f'{k}: "{v}"')
        else:
            yaml_lines.append(f"{k}: {v}")
    yaml_lines.append("---")

    materials = "\n".join(f"- [{t}] {t}" for t in features) if features else "- [Lecture-Notes] Lecture notes"

    citation = f"""{{{{cite web
 |url={run.get('url', '')}
 |title={title}
 |author={', '.join(instructor_names)}
 |website=MIT OpenCourseWare
 |access-date=2026-05-09
}}}}"""

    return f"""{"\n".join(yaml_lines)}

# {title}

{description}

## Course Info

- **Department:** {', '.join(dept_links)}
- **Course Number:** {course_id}
- **Instructors:** {', '.join(instructor_links)}
- **Year:** {year}
- **Level:** {level}
- **Topics:** {', '.join(topic_links)}
- **License:** CC BY-NC-SA

## Materials

{materials}

## Wikipedia Bridge

### Related Articles

TBD — crossref not yet run.

### Citation Template

```wikitext
{citation}
```
"""


def append_to_list(filepath: Path, line: str, marker: str = "## Courses"):
    """Add a line to the Courses section of a page."""
    if not filepath.exists():
        return
    content = filepath.read_text()
    if marker not in content:
        return
    if line in content:
        return  # already linked
    content = content.replace(f"{marker}\n\n*None yet.*", f"{marker}\n\n{line}")
    if f"{marker}\n\n" in content and "*None yet.*" not in content:
        content = content.replace(f"{marker}\n\n", f"{marker}\n\n{line}\n")
    else:
        content = content.replace(f"{marker}\n\n", f"{marker}\n\n{line}\n", 1)
    filepath.write_text(content)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()

    if args.all:
        offset = 0
        limit = 100
        total = 2577
        while offset < total:
            print(f"Batch offset={offset}...")
            _process_batch(offset, limit)
            offset += limit
            time.sleep(0.5)
    else:
        _process_batch(args.offset, args.limit)


def _process_batch(offset: int, limit: int):
    data = fetch(offset, limit)
    courses = data["results"]

    for course in courses:
        if not course.get("runs") or not course["runs"][0]:
            print(f"  SKIP {course.get('title', 'unknown')} (id={course.get('id')}) — no runs data")
            continue
        run = course["runs"][0]
        slug = course_slug(run)
        if not slug:
            print(f"  SKIP {course.get('title', 'unknown')} (id={course.get('id')}) — no slug")
            continue

        page = build_course_page(course, slug)
        page_path = WIKI_DIR / "courses" / f"{slug}.md"
        page_path.parent.mkdir(parents=True, exist_ok=True)
        page_path.write_text(page)
        print(f"  wrote {slug}")

        # Get course number safely
        course_num = "Unknown"
        if course.get("course") and course["course"].get("course_numbers"):
            course_num = course["course"]["course_numbers"][0]["value"]

        # Link from departments
        for dept in course.get("departments", []):
            dept_path = WIKI_DIR / "departments" / f"{dept['department_id'].lower()}.md"
            line = f"- [[{slug}|{run['title']}]] ({course_num})"
            append_to_list(dept_path, line)

        # Link from topics
        for topic in course.get("topics", []):
            topic_path = WIKI_DIR / "topics" / f"{topic_slug(topic['name'])}.md"
            line = f"- [[{slug}|{run['title']}]] — {course_num}, {run.get('semester', '')} {run.get('year', '')}"
            append_to_list(topic_path, line.strip())

        # Create instructor pages
        for instructor in run.get("instructors", []):
            instr_path = WIKI_DIR / "instructors" / f"{instructor_slug(instructor['full_name'])}.md"
            if not instr_path.exists():
                instr_path.write_text(f"""---
name: "{instructor['full_name']}"
type: instructor
courses_count: 1
---

# {instructor['full_name']}

## Courses Taught at MIT

- [[{slug}|{run['title']}]]
""")
            else:
                content = instr_path.read_text()
                line = f"- [[{slug}|{run['title']}]]"
                if line not in content:
                    content = content.replace("## Courses Taught at MIT\n\n", f"## Courses Taught at MIT\n\n{line}\n")
                    instr_path.write_text(content)

    # Save raw JSON
    raw_path = RAW_DIR / "api" / f"courses-page-{offset:03d}.json"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(json.dumps(data, indent=2))

    print(f"Batch offset={offset}: {len(courses)} courses processed")


if __name__ == "__main__":
    main()
