#!/usr/bin/env python3
"""
Add MIT OCW course links to a Wikipedia article's External links section.

Full reference: docs/L2-EXTERNAL-LINKS.md — algorithm, architecture, course resolution, known bugs.
Keep that doc in sync when changing this script.

Fetches the article, appends to the == External links == section (or
== Further reading ==), creates one if neither exists, and posts the edit.

Usage — primary (course resolved from local wiki):
    python3 scripts/apply-l2-external-links.py \\
        "Article title" \\
        --course "6-s897-machine-learning-for-healthcare-spring-2019"

    python3 scripts/apply-l2-external-links.py \\
        "Article title" \\
        --course "https://ocw.mit.edu/courses/6-s897-machine-learning-for-healthcare-spring-2019/"

    # Article as full URL works too:
    python3 scripts/apply-l2-external-links.py \\
        "https://en.wikipedia.org/wiki/Artificial_intelligence_in_healthcare" \\
        --course "6-s897-..."

    # Override title/description from wiki:
    python3 scripts/apply-l2-external-links.py "Article" \\
        --course "6-s897-..." \\
        --course-title "Custom Title" \\
        --description "Custom description."

Usage — legacy (all fields explicit, still supported):
    python3 scripts/apply-l2-external-links.py \\
        "Article title" \\
        --course-id 6.006 \\
        --course-title "Introduction to Algorithms" \\
        --course-url "https://ocw.mit.edu/courses/6-006-..." \\
        --description "Full course with video lectures, problem sets, and exams."

Options:
    --dry-run           Preview only (no auth needed)
    --yes, -y           Skip confirmation prompt

Authentication:
    Uses bot password. Set in .env or environment variables:

    WIKIPEDIA_USERNAME=YourUsername@BotName
    WIKIPEDIA_BOT_PASSWORD=your_bot_password

    Create a bot password at Special:BotPasswords with "Edit existing pages" grant.
"""

import os
import sys
import json
import urllib.request
import urllib.parse
import importlib.util

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
WIKI_COURSES_DIR = os.path.abspath(os.path.join(SCRIPTS_DIR, "..", "wiki", "courses"))
sys.path.insert(0, SCRIPTS_DIR)

# Import shared utilities from refideas-add.py (auth, colors, diff)
_add_spec = importlib.util.spec_from_file_location(
    "refideas_add_cli",
    os.path.join(SCRIPTS_DIR, "refideas-add.py")
)
_add = importlib.util.module_from_spec(_add_spec)
_add_spec.loader.exec_module(_add)

# Import core function from contribution-protocol.py
_proto_spec = importlib.util.spec_from_file_location(
    "contribution_protocol",
    os.path.join(SCRIPTS_DIR, "contribution-protocol.py")
)
_proto = importlib.util.module_from_spec(_proto_spec)
_proto_spec.loader.exec_module(_proto)

UA = _add.UA
WIKIPEDIA_API = _add.WIKIPEDIA_API
colorize = _add.colorize
Color = _add.Color


# ─── Course resolution from local wiki ────────────────────────────────────

def _parse_frontmatter(filepath: str) -> dict:
    """Parse YAML frontmatter from a markdown file.
    
    Simple key-value parser for the fields we need (course_id, title, url).
    No external YAML dependency required.
    """
    with open(filepath, encoding="utf-8") as f:
        content = f.read()

    if not content.startswith("---"):
        return {}

    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}

    frontmatter = {}
    for line in parts[1].strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip()
            # Strip surrounding quotes
            if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
                val = val[1:-1]
            frontmatter[key] = val

    return frontmatter


def resolve_course(course_arg: str):
    """Resolve course slug or URL to (course_id, title, url) from local wiki.
    
    Supports:
        - Full URL: https://ocw.mit.edu/courses/6-s897-machine-learning-for-healthcare-spring-2019/
        - Slug:     6-s897-machine-learning-for-healthcare-spring-2019
    """
    slug = course_arg.rstrip("/")

    # Extract slug from full OCW URL
    if slug.startswith("https://ocw.mit.edu/courses/"):
        path = urllib.parse.urlparse(slug).path.rstrip("/")
        prefix = "/courses/"
        if path.startswith(prefix):
            slug = path[len(prefix):]

    # Remove trailing slash from slug if present
    slug = slug.rstrip("/")

    # Look up wiki/courses/{slug}.md
    wiki_path = os.path.join(WIKI_COURSES_DIR, f"{slug}.md")
    if not os.path.exists(wiki_path):
        print(colorize(f"\n  ❌ Course not found in local wiki: {slug}", Color.RED), file=sys.stderr)
        print(f"     Looked in: {wiki_path}", file=sys.stderr)
        sys.exit(1)

    fm = _parse_frontmatter(wiki_path)
    course_id = fm.get("course_id", "")
    title = fm.get("title", "")
    url = fm.get("url", "")

    if not course_id or not title or not url:
        print(colorize(f"\n  ❌ Incomplete metadata in {slug}.md", Color.RED), file=sys.stderr)
        sys.exit(1)

    return course_id, title, url


def resolve_article(article_arg: str) -> str:
    """Extract article title from Wikipedia URL or return as-is."""
    if article_arg.startswith("https://en.wikipedia.org/wiki/"):
        path = urllib.parse.urlparse(article_arg).path
        prefix = "/wiki/"
        if path.startswith(prefix):
            return urllib.parse.unquote(path[len(prefix):]).replace("_", " ")
    return article_arg


# ─── Article edit (not Talk page) ──────────────────────────────────────────

def post_article_edit(article: str, new_wikitext: str, summary: str, opener) -> dict:
    """Post an edit to a Wikipedia article (NOT Talk page)."""
    token_url = f"{WIKIPEDIA_API}?action=query&meta=tokens&type=csrf&format=json&formatversion=2"
    req = urllib.request.Request(token_url, headers={"User-Agent": UA})
    fetcher = opener if opener else urllib.request.build_opener()
    with fetcher.open(req, timeout=15) as resp:
        token_data = json.loads(resp.read())

    if "error" in token_data:
        return token_data

    csrf_token = token_data.get("query", {}).get("tokens", {}).get("csrftoken", "")
    if not csrf_token:
        return {"error": {"code": "no_token", "info": "Could not get CSRF token"}}

    decoded = urllib.parse.unquote(article).replace(" ", "_")
    post_data = urllib.parse.urlencode({
        "action": "edit",
        "title": decoded,
        "text": new_wikitext,
        "summary": summary,
        "token": csrf_token,
        "format": "json", "formatversion": "2",
    }).encode()

    req = urllib.request.Request(
        WIKIPEDIA_API, data=post_data,
        headers={"User-Agent": UA, "Content-Type": "application/x-www-form-urlencoded"}
    )
    try:
        with fetcher.open(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode() if e.fp else str(e)
        return {"error": {"code": str(e.code), "info": error_body[:500]}}
    except Exception as e:
        return {"error": {"code": "exception", "info": str(e)}}


# ─── CLI ────────────────────────────────────────────────────────────────────

def parse_args():
    """Parse command line arguments."""
    args = sys.argv[1:]
    article = None
    course = None        # --course (slug or URL)
    course_id = None     # --course-id (legacy, fallback)
    course_title = None  # --course-title (override or legacy)
    course_url = None    # --course-url (legacy)
    description = ""
    dry_run = False
    auto_yes = False

    i = 0
    while i < len(args):
        if args[i] == "--dry-run":
            dry_run = True
            i += 1
        elif args[i] in ("--yes", "-y"):
            auto_yes = True
            i += 1
        elif args[i] == "--course":
            i += 1
            if i < len(args):
                course = args[i]
                i += 1
        elif args[i] == "--course-id":
            i += 1
            if i < len(args):
                course_id = args[i]
                i += 1
        elif args[i] == "--course-title":
            i += 1
            if i < len(args):
                course_title = args[i]
                i += 1
        elif args[i] == "--course-url":
            i += 1
            if i < len(args):
                course_url = args[i]
                i += 1
        elif args[i] == "--description":
            i += 1
            if i < len(args):
                description = args[i]
                i += 1
        elif not args[i].startswith("--"):
            article = args[i]
            i += 1
        else:
            print(f"Unknown flag: {args[i]}", file=sys.stderr)
            i += 1

    return article, course, course_id, course_title, course_url, description, dry_run, auto_yes


def main():
    article_arg, course, course_id, course_title, course_url, description, dry_run, auto_yes = parse_args()

    if not article_arg:
        print(__doc__)
        sys.exit(1)

    # Resolve article title (accept full Wikipedia URL or bare title)
    article = resolve_article(article_arg)

    # Resolve course: --course (new) or --course-id/--course-title/--course-url (legacy)
    using_course_flag = course is not None
    using_legacy = course_id is not None or course_url is not None

    if using_course_flag:
        # New primary mode: resolve from local wiki
        resolved_id, resolved_title, resolved_url = resolve_course(course)
        # Allow overrides
        if course_title is None:
            course_title = resolved_title
        if course_url is None:
            course_url = resolved_url
        if course_id is None:
            course_id = resolved_id
    elif using_legacy:
        # Legacy mode: all fields must be provided
        if not course_id or not course_title or not course_url:
            print(colorize("\n  ❌ Legacy mode requires --course-id, --course-title, and --course-url",
                          Color.RED), file=sys.stderr)
            print(__doc__)
            sys.exit(1)
    else:
        print(colorize("\n  ❌ Must specify --course (slug/URL) or --course-id/--course-title/--course-url",
                      Color.RED), file=sys.stderr)
        print(__doc__)
        sys.exit(1)

    # Auth
    opener = _add.get_auth()
    if not opener and not dry_run:
        print(colorize("\n  ⚠️  No Wikipedia credentials found.", Color.YELLOW), file=sys.stderr)
        print("  Set WIKIPEDIA_USERNAME + WIKIPEDIA_BOT_PASSWORD in .env", file=sys.stderr)
        print("  Running in dry-run mode.\n", file=sys.stderr)
        dry_run = True

    # Generate new wikitext
    print(f"\n  Fetching article: {article}...", file=sys.stderr)
    print(f"  Course: {colorize(course_id, Color.CYAN)} — {course_title}", file=sys.stderr)
    result = _proto.l2_insert_external_link(
        article_title=article,
        course_id=course_id,
        course_title=course_title,
        course_url=course_url,
        description=description,
    )

    new_wikitext = result["wikitext"]

    if result.get("skipped"):
        print(colorize(f"\n  ⏭  {result['detail']}", Color.YELLOW))
        sys.exit(0)

    action = result["action"]
    detail = result["detail"]
    section = result.get("section", "")
    summary = result["summary"]

    print(f"\n  Action: {colorize(action, Color.CYAN)}")
    if section:
        print(f"  Section: {colorize(section, Color.CYAN)}")
    print(f"  Detail: {detail}")
    print(f"  Summary: {colorize(summary, Color.GREEN)}")

    # Fetch original for diff
    decoded = urllib.parse.unquote(article).replace(" ", "_")
    encoded = urllib.parse.quote(decoded, safe="")
    api_url = f"{WIKIPEDIA_API}?action=parse&page={encoded}&prop=wikitext&format=json&formatversion=2"
    req = urllib.request.Request(api_url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            current_wikitext = data.get("parse", {}).get("wikitext", "")
    except Exception as e:
        print(f"  Error fetching article for diff: {e}", file=sys.stderr)
        sys.exit(1)

    if new_wikitext == current_wikitext:
        print(colorize("\n  ⚠️  Generated wikitext is identical to current page. Nothing to do.", Color.YELLOW))
        sys.exit(0)

    # Show diff
    diff = _add.side_by_side_diff(current_wikitext, new_wikitext, article)
    print(diff)

    if dry_run:
        print(colorize("\n  Dry run — no edit was made.", Color.YELLOW))
        print(f"\n  To apply, run without --dry-run:")
        if using_course_flag:
            # Show --course syntax  (preferred)
            course_repr = course  # the original --course value
            print(f"    python3 scripts/apply-l2-external-links.py \\")
            print(f"        \"{article}\" \\")
            print(f"        --course \"{course_repr}\"" + (" \\" if description else ""))
            if description:
                print(f"        --description \"{description}\"")
        else:
            print(f"    python3 scripts/apply-l2-external-links.py \\")
            print(f"        \"{article}\" \\")
            print(f"        --course-id {course_id} \\")
            print(f"        --course-title \"{course_title}\" \\")
            print(f"        --course-url \"{course_url}\"" + (" \\" if description else ""))
            if description:
                print(f"        --description \"{description}\"")
        sys.exit(0)

    # Confirm
    if auto_yes:
        print(colorize("\n  Auto-applying (--yes)...", Color.YELLOW))
    else:
        print()
        try:
            response = input(colorize("  Post to Wikipedia article? [y/N] ", Color.BOLD))
        except (EOFError, KeyboardInterrupt):
            print("\n  Cancelled.")
            sys.exit(0)
        if response.lower() not in ("y", "yes"):
            print(colorize("  Cancelled.", Color.YELLOW))
            sys.exit(0)

    # Post
    print(f"\n  Posting edit...", file=sys.stderr)
    edit_result = post_article_edit(article, new_wikitext, summary, opener)

    if "error" in edit_result:
        error_info = edit_result["error"]
        print(colorize(f"\n  ❌ Edit failed: {error_info.get('code', 'unknown')}", Color.RED))
        if "info" in error_info:
            print(f"  {error_info['info'][:300]}")
        sys.exit(1)

    edit = edit_result.get("edit", {})
    if edit.get("result") == "Success":
        rev_id = edit.get("newrevid", "?")
        print(colorize(f"\n  ✅ External link added! Revision: {rev_id}", Color.GREEN))
        decoded = urllib.parse.unquote(article).replace(" ", "_")
        enc = urllib.parse.quote(decoded, safe="")
        print(f"  https://en.wikipedia.org/w/index.php?title={enc}&oldid={rev_id}")
    else:
        print(colorize(f"\n  ⚠️  Unexpected response: {json.dumps(edit_result, indent=2)[:300]}", Color.YELLOW))


if __name__ == "__main__":
    main()
