#!/usr/bin/env python3
"""
Asset scan for OCW courses.

Visits each course's OCW page, discovers all sidebar links, downloadable
files, and video galleries, and classifies them into typed asset lists.

Usage:
    python3 scripts/scan-assets.py --slug 4-241j-the-making-of-cities-spring-2025
    python3 scripts/scan-assets.py --deep 15-071-the-analytics-edge-spring-2017
    python3 scripts/scan-assets.py --api 5-111sc-principles-of-chemical-science-fall-2014
    python3 scripts/scan-assets.py --hybrid 2-782j-design-of-medical-devices-and-implants-spring-2025
    python3 scripts/scan-assets.py --batch 0 100
    python3 scripts/scan-assets.py --unscanned
"""

import json, re, sys, time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError

API_BASE = "https://api.learn.mit.edu/api/v1"
WIKI_DIR = Path(__file__).resolve().parent.parent / "wiki"
IGNORED_WORDS = {"welcome to", "overview", "introduction", "menu", "course info"}

# Map API content_feature_type to wiki asset types
FEATURE_TYPE_MAP = {
    "Lecture Videos": "Video-Transcript",
    "Other Video": "Video-Transcript",
    "Lecture Notes": "Lecture-Notes",
    "Problem Sets": "Problem-Set",
    "Problem Set Solutions": "Problem-Set",
    "Exams": "Problem-Set",
    "Exam Solutions": "Problem-Set",
    "Projects": "Assignment",
    "Projects with Examples": "Assignment",
    "Assignments": "Problem-Set",
    "Written Assignments": "Problem-Set",
    "Written Assignments with Examples": "Problem-Set",
    "Readings": "Reading-List",
    "Reading Lists": "Reading-List",
    "Instructor Insights": "Resource",
    "Activity Assignments with Examples": "Assignment",
    "Image Gallery": "Image-Gallery",
    "Open Textbooks": "Reading-List",
}

PATTERN_MAP = [
    (r"syllabus|calendar|schedule", "Syllabus"),
    (r"readings?|bibliograph|textbook|references?|reading.?list", "Reading-List"),
    (r"lecture.?note|slide|presentation|lecture.?summary", "Lecture-Notes"),
    (r"video|recording|lecture.?vid|lecture.?sequence|video.?gallery", "Video-Transcript"),
    (r"problem.?set|assignment|homework|pset|exercise", "Problem-Set"),
    (r"exam|quiz|test|midterm|final", "Problem-Set"),
    (r"solution|answer.?key", "Problem-Set"),
    (r"project|paper|essay|report|writing|research.?project", "Assignment"),
    (r"image|photo|gallery|diagram|figure|map", "Image-Gallery"),
    (r"studio|lab|recitation|tutorial|workshop", "Lecture-Notes"),
    (r"unit\s+\d", "Lecture-Notes"),
    (r"download", "Resource"),
]

def timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")

def course_label(slug: str) -> str:
    """Return 'course_id Title' for log entries, e.g. '5.111SC Principles of Chemical Science'."""
    page_path = WIKI_DIR / "courses" / f"{slug}.md"
    if not page_path.exists():
        return slug
    content = page_path.read_text()
    cid = re.search(r'^course_id:\s*"(.+)"', content, re.M)
    title = re.search(r'^title:\s*"(.+)"', content, re.M)
    parts = []
    if cid:
        parts.append(cid.group(1))
    if title:
        parts.append(title.group(1))
    return " ".join(parts) if parts else slug
    return datetime.now().strftime("%Y-%m-%d %H:%M")

def classify_link(text: str) -> str:
    for pattern, atype in PATTERN_MAP:
        if re.search(pattern, text, re.I):
            return atype
    return "Resource"

def fetch(url: str) -> str:
    try:
        resp = urlopen(Request(url, headers={"User-Agent": "OCW-LLM-Wiki/1.0"}), timeout=15)
        return resp.read().decode("utf-8", errors="replace")
    except Exception:
        return ""

def scan_one(slug: str) -> list:
    """Scan a course page and return all discovered assets."""
    html = fetch(f"https://ocw.mit.edu/courses/{slug}/")
    if not html:
        return []

    assets = []
    seen = set()

    # 1. All sidebar navigation links (pages, video_galleries, lists, resources)
    for path in re.findall(r'href="(/courses/' + re.escape(slug) + r'/(?:pages|video_galleries|lists|resources)/[^"]*)"', html):
        m = re.search(r'href="' + re.escape(path) + r'"[^>]*>([^<]+)', html)
        text = m.group(1).strip() if m else path.rstrip("/").split("/")[-1]
        if text.lower() in seen or len(text) < 2:
            continue
        seen.add(text.lower())
        assets.append((classify_link(text), text, f"https://ocw.mit.edu{path}"))

    # 2. Direct file downloads (PDFs, ZIPs, spreadsheets, etc.)
    for path in re.findall(r'href="(/courses/' + re.escape(slug) + r'/resources/[^"]*\.(?:pdf|zip|tar|gz|csv|xlsx?|docx?|pptx?|mp4|mov|png|jpg|jpeg|gif|svg))"', html, re.I):
        fname = path.rstrip("/").split("/")[-1]
        if fname.lower() in seen:
            continue
        seen.add(fname.lower())
        t = "Image-Gallery" if re.search(r"\.(png|jpg|jpeg|gif|svg)$", fname, re.I) else "Resource"
        assets.append((t, fname, f"https://ocw.mit.edu{path}"))

    # 3. External resource links (YouTube, OCW Scholar, etc.)
    for href, text in re.findall(r'href="(https?://[^"]+)"[^>]*>([^<]+)', html):
        text = text.strip()
        if not text or len(text) < 5 or "ocw" in href:
            continue
        if text.lower() in seen:
            continue
        seen.add(text.lower())
        if any(d in href for d in ("youtube", "youtu.be", "video", "podcast")):
            assets.append(("Video-Transcript", text, href))
        elif any(d in href for d in ("pdf", "document", "download")):
            assets.append(("Resource", text, href))

    return assets


def detect_video(html: str) -> list:
    """Check a page for video content and return details."""
    found = []
    if re.search(r"Download video|Download transcript|View video page", html, re.I):
        found.append("OCW player")
    if re.search(r"youtube\.com/embed|youtu\.be|youtube\.com/watch", html, re.I):
        found.append("YouTube")
    if re.search(r"\.mp4|video/mp4|video/ogg|video/webm", html, re.I):
        found.append("MP4 file")
    if re.search(r"class=\"[^\"]*video[^\"]*\"", html, re.I):
        found.append("Video embed")
    return found


def deep_scan_one(slug: str, assets: list, max_pages: int = 100) -> list:
    """
    Visit sub-pages to detect video content and downloadable resources.
    Returns updated assets with video annotations.
    """
    # Collect unique sub-page URLs from assets
    sub_urls = []
    seen_urls = set()
    for atype, text, url in assets:
        if url not in seen_urls and atype != "Syllabus":
            seen_urls.add(url)
            sub_urls.append((atype, text, url))

    print(f"  deep scan: {len(sub_urls)} sub-pages...")
    scanned = 0

    for atype, text, url in sub_urls[:max_pages]:
        html = fetch(url)
        if not html:
            continue

        # --- Extract rich page metadata ---
        # Full page title from <title> tag
        page_title = re.search(r'<title>([^<]+)', html)
        if page_title:
            full_title = page_title.group(1).split(" |")[0].strip()
            # Use the full title if it's more descriptive than the sidebar text
            if len(full_title) > len(text) and not text.startswith("Download "):
                old_text = text
                text = full_title
                # Update the asset entry to use the richer title
                for i, (a, t, u) in enumerate(assets):
                    if u == url and a == atype and t == old_text:
                        assets[i] = (a, text, u)
                        break

        # Description from og:description or meta description
        description = ""
        og_desc = re.search(r'property="og:description" content="([^"]+)', html)
        if og_desc:
            description = og_desc.group(1).strip()
        else:
            meta_desc = re.search(r'<meta name="description" content="([^"]+)', html)
            if meta_desc:
                description = meta_desc.group(1).strip()
        if description:
            description = re.sub(r'\s+', ' ', description).strip()

        videos = detect_video(html)
        slides = re.search(r'slides.*?\.pdf|lecture.*?\.pdf', html, re.I)

        annotations = []
        if videos:
            annotations.extend(videos)
        if slides:
            annotations.append("slides")

        # Extract external video links on this sub-page
        ext_videos = 0
        for href, link_text in re.findall(r'href="(https?://[^"]+)"[^>]*>([^<]+)', html):
            link_text = link_text.strip()
            if not link_text or len(link_text) < 3:
                continue
            is_external = "(external)" in link_text.lower() or "external" in href.lower()
            is_video_host = any(d in href for d in ("dropbox", "youtube", "youtu.be", "vimeo", "wistia", "panopto", "kaltura", "zoom.us", "archive.org"))
            if is_external or is_video_host:
                link_type = "Video-Transcript" if is_video_host else "Resource"
                entry = (link_type, link_text, href)
                if entry not in assets:
                    assets.append(entry)
                    ext_videos += 1

        # Extract "Download video" / "Download transcript" links on sub-pages
        for m in re.finditer(r'href="([^"]+)"[^>]*>(Download\s+(?:video|transcript|the video))</a>', html, re.I):
            dl_href = m.group(1)
            dl_text = m.group(2)
            if dl_href.startswith("/"):
                dl_href = "https://ocw.mit.edu" + dl_href
            entry = ("Video-Transcript", dl_text, dl_href)
            if entry not in assets:
                assets.append(entry)
                ext_videos += 1

        # Extract inline lecture listings from video gallery pages
        # Pattern: "Lecture N: Title" appearing in page content
        for m in re.finditer(r'Lecture\s+(\d+[A-Za-z]?):\s*([^<]{10,100})', html):
            lecture_num = m.group(1)
            lecture_title = m.group(2).strip()
            full = f"Lecture {lecture_num}: {lecture_title}"
            entry = ("Video-Transcript", full, url)
            if entry not in assets:
                assets.append(entry)
                ext_videos += 1

        if annotations or ext_videos or description:
            detail = ", ".join(annotations)
            if description:
                detail += (", " if detail else "") + description[:120]
            if ext_videos:
                detail += (", " if detail else "") + f"{ext_videos} external video links"
            print(f"    [{atype:16s}] {text}")
            # Append video annotation to text for display
            if videos:
                badges = []
                if "YouTube" in videos:
                    badges.append("🎬YouTube")
                if "OCW player" in videos or "MP4 file" in videos or "Video embed" in videos:
                    badges.append("📺Video")
                annotation = " ".join(badges)
                # Update the asset entry to include annotation
                for i, (a, t, u) in enumerate(assets):
                    if u == url and a == atype:
                        assets[i] = (a, f"{t} {annotation}", u)
                        break

        # Also check for direct file links on the sub-page
        for fpath in re.findall(r'href="(/courses/' + re.escape(slug) + r'/resources/[^"]*\.(?:pdf|zip|csv|xlsx?))"', html, re.I):
            fname = fpath.rstrip("/").split("/")[-1]
            if fname.lower() not in [a[1].lower() for a in assets]:
                assets.append(("Resource", fname, f"https://ocw.mit.edu{fpath}"))

        scanned += 1
        time.sleep(0.2)

    print(f"  deep scan: {scanned} pages checked")
    return assets


def api_scan(slug: str) -> list:
    """
    Fetch all content files for a course from the MIT Learn API.
    Returns a complete, authoritative list of assets with rich metadata.
    """
    # Read the course page to get frontmatter
    page_path = WIKI_DIR / "courses" / f"{slug}.md"
    if not page_path.exists():
        print(f"  SKIP {slug} — no wiki page found")
        return []
    frontmatter = page_path.read_text()
    course_id = re.search(r'^course_id:\s*"(.+)"', frontmatter, re.M)
    year = re.search(r'^year_published:\s*(\d+)', frontmatter, re.M)

    # Derive semester from the URL in frontmatter
    url_match = re.search(r'^url:\s*"(.+?)"', frontmatter, re.M)
    semester = "unknown"
    if url_match:
        # Extract semester from URL like "...spring-2025/"
        url = url_match.group(1).rstrip("/")
        parts = url.split("-")
        if len(parts) >= 2:
            semester = parts[-2]  # e.g. "spring" from "...spring-2025"

    if not course_id or not year:
        print(f"  SKIP {slug} — missing course_id or year_published in frontmatter")
        return []

    readable_id = f"{course_id.group(1)}+{semester}_{year.group(1)}"
    encoded_rid = quote(readable_id, safe="")

    # Look up course in API to get the numeric ID
    api_url = f"{API_BASE}/courses/?offered_by=ocw&readable_id={encoded_rid}"
    try:
        raw = urlopen(Request(api_url, headers={"Accept": "application/json"}), timeout=15).read()
        data = json.loads(raw)
        if data["count"] == 0:
            print(f"  SKIP {slug} — course not found in API (readable_id={readable_id})")
            return []
        course_api_id = data["results"][0]["id"]
    except Exception as e:
        print(f"  SKIP {slug} — API lookup failed: {e}")
        return []

    # Fetch ALL content files for this course
    all_files = []
    offset = 0
    limit = 100
    while True:
        cf_url = f"{API_BASE}/courses/{course_api_id}/contentfiles/?limit={limit}&offset={offset}"
        try:
            raw = urlopen(Request(cf_url, headers={"Accept": "application/json"}), timeout=15).read()
            data = json.loads(raw)
            all_files.extend(data["results"])
            if data.get("next"):
                offset += limit
            else:
                break
        except Exception as e:
            print(f"  API error: {e}")
            break

    print(f"  API: {len(all_files)} content files found for course {course_api_id}")

    assets = []
    seen = set()

    for f in all_files:
        title = f.get("content_title") or f.get("title", "")
        if not title or title.lower() in seen:
            continue
        seen.add(title.lower())

        # Determine asset type from content_feature_type
        feature_types = f.get("content_feature_type", [])
        asset_type = "Resource"
        for ft in feature_types:
            if ft in FEATURE_TYPE_MAP:
                asset_type = FEATURE_TYPE_MAP[ft]
                break

        # Build display text with metadata
        display = title
        badges = []

        # YouTube link
        yt_id = f.get("youtube_id")
        yt_url = None
        if yt_id:
            yt_url = f"https://youtu.be/{yt_id}"
            badges.append("🎬YouTube")

        # File extension info
        ext = f.get("file_extension", "")
        content_type = f.get("content_type", "")
        if ext:
            display = f"{display} ({ext})"

        # Mark video content
        if content_type == "video" or ext == ".mp4":
            badges.append("📺Video")

        if badges:
            display = f"{display} {' '.join(badges)}"

        # Primary URL: prefer YouTube if available, otherwise the resource URL
        primary_url = yt_url or f.get("url", "")

        # Add the asset
        assets.append((asset_type, display, primary_url))

        # Also add YouTube link as a separate Video-Transcript entry if it exists
        if yt_url and yt_url != primary_url:
            yt_display = f"{title} 🎬YouTube"
            assets.append(("Video-Transcript", yt_display, yt_url))

    return assets

def update_page(slug: str, assets: list):
    path = WIKI_DIR / "courses" / f"{slug}.md"
    if not path.exists():
        return

    content = path.read_text()

    # Group assets by type
    groups = {}
    for atype, text, url in assets:
        groups.setdefault(atype, []).append((text, url))

    type_order = ["Syllabus", "Lecture-Notes", "Video-Transcript", "Reading-List",
                  "Problem-Set", "Assignment", "Image-Gallery", "Resource"]

    lines = ["## Materials", ""]
    for t in type_order:
        if t not in groups:
            continue
        lines.append(f"### {t}")
        for text, url in groups[t]:
            lines.append(f"- [{text}]({url})")
        lines.append("")

    # Remove trailing blank lines
    while lines and lines[-1] == "":
        lines.pop()

    new_section = "\n".join(lines)

    if "## Materials" in content:
        content = re.sub(r"## Materials\n.*?(?=\n## |\n---|$)", new_section, content, flags=re.DOTALL)
    else:
        content = content.replace("- **License:** CC BY-NC-SA\n",
                                  f"- **License:** CC BY-NC-SA\n\n{new_section}\n")

    path.write_text(content)
    print(f"  updated {slug} ({len(assets)} assets in {len(groups)} categories)")

def append_log(msg: str):
    p = WIKI_DIR / "log.md"
    p.write_text(p.read_text().rstrip() + f"\n\n{msg}\n")

def update_checkpoint(n: int):
    cp = json.loads((Path(__file__).resolve().parent.parent / "_checkpoint.json").read_text())
    cp["stages"]["asset_scan"]["courses_done"] += n
    (Path(__file__).resolve().parent.parent / "_checkpoint.json").write_text(json.dumps(cp, indent=2))

def main():
    args = sys.argv[1:]

    if args[0] == "--hybrid" and len(args) >= 2:
        slug = args[1]
        print(f"Hybrid scan of {slug}...")

        # Phase 1: API scan for authoritative content files
        api_assets = api_scan(slug)
        print(f"  API phase: {len(api_assets)} assets")

        # Phase 2: Deep URL scan for sidebar structure
        url_assets = scan_one(slug)
        url_assets = deep_scan_one(slug, url_assets)
        # From deep scan, keep sidebar pages AND external video links
        sidebar_pages = []
        external_videos = []
        for a in url_assets:
            is_external_video = a[2].startswith(("https://youtu", "https://www.youtube", "https://vimeo", "https://www.dropbox"))
            is_sidebar = not is_external_video and a[2].count("/") < 12 and not a[2].startswith("https://archive.org") and not a[1].startswith("Download ")
            if is_external_video:
                external_videos.append(a)
            elif is_sidebar:
                sidebar_pages.append(a)
        print(f"  Deep scan phase: {len(url_assets)} total ({len(sidebar_pages)} sidebar pages, {len(external_videos)} external videos)")

        # Merge: use API assets as base, add sidebar pages and external videos from URL scan
        if not api_assets:
            merged = url_assets
            print(f"  API empty, using full deep scan ({len(merged)} assets)")
        else:
            merged = list(api_assets)
            merged_urls = {a[2] for a in merged}
            added = 0
            # Add sidebar pages (with type correction)
            for a in sidebar_pages:
                if a[2] not in merged_urls:
                    merged.append(a)
                    merged_urls.add(a[2])
                    added += 1
                else:
                    for i, ma in enumerate(merged):
                        if ma[2] == a[2] and ma[0] == "Resource" and a[0] != "Resource":
                            merged[i] = a
                            break
            # Add external video links not already covered
            for a in external_videos:
                if a[2] not in merged_urls:
                    merged.append(a)
                    merged_urls.add(a[2])
                    added += 1
            print(f"  Merged: {len(api_assets)} API + {added} additions = {len(merged)} total")

        if merged:
            update_page(slug, merged)
            total_api = len(api_assets)
            total_url = len(sidebar_pages) if api_assets else 0
            append_log(f"## [{timestamp()}] asset-scan | Hybrid scanned [[{slug}|{course_label(slug)}]] ({len(merged)} assets: {total_api} API + {total_url} pages)")
            update_checkpoint(0)
            types = {}
            for a, t, u in merged:
                types[a] = types.get(a, 0) + 1
            for t, c in sorted(types.items()):
                print(f"  [{t:20s}] {c} items")
        else:
            print("  No assets found.")

    elif args[0] == "--api" and len(args) >= 2:
        slug = args[1]
        assets = api_scan(slug)
        if assets:
            # Print summary by type
            types = {}
            for a, t, u in assets:
                types[a] = types.get(a, 0) + 1
            for t, c in sorted(types.items()):
                print(f"  [{t:20s}] {c} files")
            update_page(slug, assets)
            append_log(f"## [{timestamp()}] asset-scan | API scanned [[{slug}|{course_label(slug)}]] ({len(assets)} assets via API)")
            update_checkpoint(0)
        else:
            print("  No assets found.")

    elif args[0] == "--deep" and len(args) >= 2:
        slug = args[1]
        assets = scan_one(slug)
        assets = deep_scan_one(slug, assets)
        if assets:
            update_page(slug, assets)
            append_log(f"## [{timestamp()}] asset-scan | Deep scanned [[{slug}|{course_label(slug)}]] ({len(assets)} assets)")
            update_checkpoint(0)

    elif args[0] == "--slug" and len(args) >= 2:
        slug = args[1]
        assets = scan_one(slug)
        for at, t, u in assets:
            print(f"  [{at:20s}] {t}")
        if assets:
            update_page(slug, assets)
            append_log(f"## [{timestamp()}] asset-scan | Scanned [[{slug}|{course_label(slug)}]] ({len(assets)} assets)")
            update_checkpoint(1)

    elif args[0] == "--batch" and len(args) >= 2:
        offset = int(args[1])
        limit = int(args[2]) if len(args) > 2 else 100
        slugs = sorted(f.name.replace(".md", "") for f in (WIKI_DIR / "courses").iterdir() if f.name.endswith(".md"))
        batch = slugs[offset:offset+limit]
        scanned = 0
        for slug in batch:
            a = scan_one(slug)
            if a:
                update_page(slug, a)
                scanned += 1
            time.sleep(0.25)
        append_log(f"## [{timestamp()}] asset-scan | Batch offset={offset} ({scanned} courses, e.g. [[{batch[0] if batch else '?'}]] ... [[{batch[-1] if batch else '?'}]])")
        update_checkpoint(scanned)
        print(f"Scanned {scanned} courses in this batch.")

    elif args[0] == "--unscanned":
        slugs = sorted(f.name.replace(".md", "") for f in (WIKI_DIR / "courses").iterdir() if f.name.endswith(".md"))
        scanned = 0
        remaining = []
        for slug in slugs:
            c = (WIKI_DIR / "courses" / f"{slug}.md").read_text()
            if re.search(r"### (Syllabus|Lecture-Notes|Video-Transcript|Reading-List|Problem-Set|Assignment|Image-Gallery)", c):
                scanned += 1
            else:
                remaining.append(slug)
        print(f"{scanned} scanned, {len(remaining)} remaining")
        if remaining:
            batch = remaining[:100]
            done = 0
            for slug in batch:
                a = scan_one(slug)
                if a:
                    update_page(slug, a)
                    done += 1
                time.sleep(0.25)
            append_log(f"## [{timestamp()}] asset-scan | Unscanned batch ({done} courses, e.g. [[{batch[0] if batch else '?'}]])")
            update_checkpoint(done)

    else:
        print(__doc__)

if __name__ == "__main__":
    main()
