#!/usr/bin/env python3
"""
OCW-specific wrapper around refideas-add for MIT OpenCourseWare references.

Formats OCW course details into the standard Refideas format and delegates
to the generic refideas-add workflow for auth, diff, confirmation, and posting.

Usage:
    python3 scripts/apply-l1-refideas.py \\
        "Article title" \\
        --course-id 5.111SC \\
        --course-title "Principles of Chemical Science" \\
        --course-url "https://ocw.mit.edu/courses/5-111sc-..." \\
        --note "video lectures, problem sets"

    python3 scripts/apply-l1-refideas.py --dry-run "Article" --course-id ...  # Preview only
    python3 scripts/apply-l1-refideas.py --yes "Article" --course-id ...      # Skip confirmation
"""

import os
import sys
import json
import urllib.request
import urllib.parse
import importlib.util

# Add scripts to path
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPTS_DIR)

# Import shared utilities from refideas-add.py
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


def parse_args():
    """Parse OCW-specific command line arguments."""
    args = sys.argv[1:]
    article = None
    course_id = None
    course_title = None
    course_url = None
    note = ""
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
        elif args[i] == "--note":
            i += 1
            if i < len(args):
                note = args[i]
                i += 1
        elif not args[i].startswith("--"):
            article = args[i]
            i += 1
        else:
            print(f"Unknown flag: {args[i]}", file=sys.stderr)
            i += 1

    return article, course_id, course_title, course_url, note, dry_run, auto_yes


def main():
    article, course_id, course_title, course_url, note, dry_run, auto_yes = parse_args()

    if not article or not course_id or not course_title or not course_url:
        print(__doc__)
        sys.exit(1)

    # Format OCW args into generic form
    label = f"MIT {course_id}: {course_title}"
    source = "MIT OpenCourseWare"

    # Auth (same as refideas-add)
    opener = _add.get_auth()
    if not opener and not dry_run:
        print(colorize("\n  ⚠️  No Wikipedia credentials found.", Color.YELLOW), file=sys.stderr)
        print("  Set WIKIPEDIA_USERNAME + WIKIPEDIA_BOT_PASSWORD in .env", file=sys.stderr)
        print("  Running in dry-run mode.\n", file=sys.stderr)
        dry_run = True

    # Generate new wikitext via the generic function
    print(f"\n  Fetching Talk:{article}...", file=sys.stderr)
    result = _proto.refideas_add(
        article_title=article,
        url=course_url,
        label=label,
        source=source,
        note=note,
    )

    new_wikitext = result["wikitext"]

    # Handle dedup skip
    if result.get("skipped"):
        print(colorize(f"\n  ⏭  {result['detail']}", Color.YELLOW))
        sys.exit(0)

    action = result["action"]
    detail = result["detail"]
    summary = result["summary"]

    print(f"\n  Action: {colorize(action, Color.CYAN)}")
    print(f"  Detail: {detail}")
    print(f"  Summary: {colorize(summary, Color.GREEN)}")

    # Fetch original for diff
    decoded = urllib.parse.unquote(article).replace(" ", "_")
    encoded = urllib.parse.quote(decoded, safe="")
    api_url = f"{WIKIPEDIA_API}?action=parse&page=Talk:{encoded}&prop=wikitext&format=json&formatversion=2"
    req = urllib.request.Request(api_url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            current_wikitext = data.get("parse", {}).get("wikitext", "")
    except Exception as e:
        print(f"  Error fetching Talk page for diff: {e}", file=sys.stderr)
        sys.exit(1)

    if new_wikitext == current_wikitext:
        print(colorize("\n  ⚠️  Generated wikitext is identical to current page. Nothing to do.", Color.YELLOW))
        sys.exit(0)

    # Show diff (same renderer)
    diff = _add.side_by_side_diff(current_wikitext, new_wikitext, f"Talk:{article}")
    print(diff)

    if dry_run:
        print(colorize("\n  Dry run — no edit was made.", Color.YELLOW))
        print(f"\n  To apply, run without --dry-run:")
        print(f"  python3 scripts/apply-l1-refideas.py \\")
        print(f"      \"{article}\" \\")
        print(f"      --course-id {course_id} \\")
        print(f"      --course-title \"{course_title}\" \\")
        print(f"      --course-url \"{course_url}\"" + (" \\" if note else ""))
        if note:
            print(f"      --note \"{note}\"")
        sys.exit(0)

    # Confirm
    if auto_yes:
        print(colorize("\n  Auto-applying (--yes)...", Color.YELLOW))
    else:
        print()
        try:
            response = input(colorize("  Post to Wikipedia? [y/N] ", Color.BOLD))
        except (EOFError, KeyboardInterrupt):
            print("\n  Cancelled.")
            sys.exit(0)
        if response.lower() not in ("y", "yes"):
            print(colorize("  Cancelled.", Color.YELLOW))
            sys.exit(0)

    # Post (same edit function)
    print(f"\n  Posting edit...", file=sys.stderr)
    edit_result = _add.apply_edit(article, new_wikitext, summary, opener)

    if "error" in edit_result:
        error_info = edit_result["error"]
        print(colorize(f"\n  ❌ Edit failed: {error_info.get('code', 'unknown')}", Color.RED))
        if "info" in error_info:
            print(f"  {error_info['info'][:300]}")
        sys.exit(1)

    edit = edit_result.get("edit", {})
    if edit.get("result") == "Success":
        rev_id = edit.get("newrevid", "?")
        print(colorize(f"\n  ✅ Refideas posted! Revision: {rev_id}", Color.GREEN))
        decoded = urllib.parse.unquote(article).replace(" ", "_")
        enc = urllib.parse.quote(decoded, safe="")
        print(f"  https://en.wikipedia.org/w/index.php?title=Talk:{enc}&oldid={rev_id}")
    else:
        print(colorize(f"\n  ⚠️  Unexpected response: {json.dumps(edit_result, indent=2)[:300]}", Color.YELLOW))


if __name__ == "__main__":
    main()
