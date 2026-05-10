#!/usr/bin/env python3
"""
Asset scan for OCW courses.

Visits each course's OCW page, discovers all sidebar links, downloadable
files, and video galleries, and classifies them into typed asset lists.

Usage:
    python3 scripts/scan-assets.py --slug 4-241j-the-making-of-cities-spring-2025
    python3 scripts/scan-assets.py --deep 15-071-the-analytics-edge-spring-2017
    python3 scripts/scan-assets.py --batch 0 100
    python3 scripts/scan-assets.py --unscanned
"""

import json, re, sys, time
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

WIKI_DIR = Path(__file__).resolve().parent.parent / "wiki"
IGNORED_WORDS = {"welcome to", "overview", "introduction", "menu", "course info"}

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

    if args[0] == "--deep" and len(args) >= 2:
        slug = args[1]
        assets = scan_one(slug)
        assets = deep_scan_one(slug, assets)
        if assets:
            update_page(slug, assets)
            # Get course title for richer log entry
            title = slug
            page_path = WIKI_DIR / "courses" / f"{slug}.md"
            if page_path.exists():
                m = re.search(r'^title: "(.+)"', page_path.read_text(), re.M)
                if m:
                    title = m.group(1)
            append_log(f"## [{timestamp()}] asset-scan | Deep scanned [[{slug}|{title}]] ({len(assets)} assets)")
            update_checkpoint(0)

    elif args[0] == "--slug" and len(args) >= 2:
        slug = args[1]
        assets = scan_one(slug)
        for at, t, u in assets:
            print(f"  [{at:20s}] {t}")
        if assets:
            update_page(slug, assets)
            title = slug
            page_path = WIKI_DIR / "courses" / f"{slug}.md"
            if page_path.exists():
                m = re.search(r'^title: "(.+)"', page_path.read_text(), re.M)
                if m:
                    title = m.group(1)
            append_log(f"## [{timestamp()}] asset-scan | Scanned [[{slug}|{title}]] ({len(assets)} assets)")
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
