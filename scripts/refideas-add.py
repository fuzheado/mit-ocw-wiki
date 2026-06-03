#!/usr/bin/env python3
"""
Add a reference to a Wikipedia Talk page's {{refideas}} template.

Full reference: docs/L1-REFIDEAS.md — algorithm, CLI, dedup, auth flow.
Keep that doc in sync when changing this script.

Generic tool — works for any reference, not just OCW. Fetches the Talk page,
generates the new wikitext, shows a color-coded side-by-side diff, prompts
for confirmation, then posts the edit via the Wikipedia API.

Authentication:
    Uses bot password. Set in .env or environment variables:

    WIKIPEDIA_USERNAME=your_username
    WIKIPEDIA_BOT_PASSWORD=your_bot_password

    Create a bot password at Special:BotPasswords with "Edit existing pages" grant.

Usage:
    python3 scripts/refideas-add.py \\
        "Article title" \\
        --url "https://example.com/reference" \\
        --label "Reference Label" \\
        --source "Source Name" \\
        --note "optional note"

    python3 scripts/refideas-add.py --dry-run "Article" --url ... --label ...  # Preview only
    python3 scripts/refideas-add.py --yes "Article" --url ... --label ...      # Skip confirmation
"""

import os
import sys
import json
import re
import urllib.request
import urllib.parse
import http.cookiejar

# Add scripts to path for contribution-protocol import
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

UA = "MIT OCW Bot/1.0 (https://meta.wikimedia.org/wiki/Wiki_MIT; andrew.lih@gmail.com) ContentGapResearch"
WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"

# Load .env if present
ENV_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
if os.path.exists(ENV_FILE):
    with open(ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                os.environ.setdefault(k, v)


# ─── Color helpers ─────────────────────────────────────────────────────────

class Color:
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"
    BG_BLUE = "\033[44m"
    RESET = "\033[0m"

def colorize(text: str, color: str) -> str:
    return f"{color}{text}{Color.RESET}"


# ─── Authentication ────────────────────────────────────────────────────────

def get_auth():
    """Authenticate with Wikipedia using bot password. Returns opener or None."""
    username = os.environ.get("WIKIPEDIA_USERNAME", "").strip().strip('"').strip("'")
    bot_password = os.environ.get("WIKIPEDIA_BOT_PASSWORD", "").strip().strip('"').strip("'")

    if not username or not bot_password:
        return None

    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    token_url = WIKIPEDIA_API + "?action=query&meta=tokens&type=login&format=json&formatversion=2"
    req = urllib.request.Request(token_url, headers={"User-Agent": UA})
    with opener.open(req, timeout=15) as resp:
        data = json.loads(resp.read())
        login_token = data["query"]["tokens"]["logintoken"]

    post_data = urllib.parse.urlencode({
        "action": "login",
        "lgname": username,
        "lgpassword": bot_password,
        "lgtoken": login_token,
        "format": "json",
    }).encode()
    req = urllib.request.Request(
        WIKIPEDIA_API, data=post_data,
        headers={"User-Agent": UA, "Content-Type": "application/x-www-form-urlencoded"}
    )
    with opener.open(req, timeout=15) as resp:
        data = json.loads(resp.read())
        result = data.get("login", {})
        if result.get("result") != "Success":
            print(f"  Login failed: {result.get('reason', 'unknown')}", file=sys.stderr)
            return None

    print(f"  Authenticated as: {result.get('lgusername', username)}", file=sys.stderr)
    return opener


# ─── Side-by-side diff ─────────────────────────────────────────────────────

def side_by_side_diff(original: str, fixed: str, title: str, col_width: int = 38) -> str:
    """Render a color-coded side-by-side diff with collapsed unchanged sections."""
    from difflib import SequenceMatcher

    def trunc(s, w=col_width):
        s = s.rstrip()
        return (s[:w-3] + "...") if len(s) > w else s.ljust(w)

    orig_lines = original.splitlines()
    fixed_lines = fixed.splitlines()
    sm = SequenceMatcher(None, orig_lines, fixed_lines)

    output = []
    divider = "─" * col_width + "─┼─" + "─" * col_width

    output.append(colorize(f"\n  Edit: {title}", Color.BOLD))
    output.append(colorize(divider, Color.DIM))
    output.append(
        colorize("Original".center(col_width), Color.BOLD + Color.BG_RED) +
        colorize(" │ ", Color.DIM) +
        colorize("Fixed".center(col_width), Color.BOLD + Color.BG_GREEN)
    )
    output.append(colorize(divider, Color.DIM))

    context = 3
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            run_len = i2 - i1
            if run_len > context * 2 + 2:
                for k in range(min(context, run_len)):
                    output.append(f"{trunc(orig_lines[i1 + k])} │ {trunc(fixed_lines[j1 + k])}")
                output.append(colorize(
                    f"  ... {run_len - 2*context} unchanged lines ...".center(col_width*2+3), Color.DIM))
                for k in range(run_len - context, run_len):
                    output.append(f"{trunc(orig_lines[i1 + k])} │ {trunc(fixed_lines[j1 + k])}")
            else:
                for k in range(run_len):
                    output.append(f"{trunc(orig_lines[i1 + k])} │ {trunc(fixed_lines[j1 + k])}")
        elif tag == "replace":
            max_lines = max(i2 - i1, j2 - j1)
            for k in range(max_lines):
                left = trunc(orig_lines[i1 + k]) if i1 + k < i2 else " " * col_width
                right = trunc(fixed_lines[j1 + k]) if j1 + k < j2 else " " * col_width
                if i1 + k < i2 and j1 + k < j2:
                    output.append(colorize(left, Color.RED) + " │ " + colorize(right, Color.GREEN))
                elif i1 + k < i2:
                    output.append(colorize(left, Color.BG_RED + Color.WHITE) + " │ " + " " * col_width)
                else:
                    output.append(" " * col_width + " │ " + colorize(right, Color.BG_GREEN + Color.WHITE))
        elif tag == "delete":
            for k in range(i1, i2):
                output.append(colorize(trunc(orig_lines[k]), Color.BG_RED + Color.WHITE) + " │ " + " " * col_width)
        elif tag == "insert":
            for k in range(j1, j2):
                output.append(" " * col_width + " │ " + colorize(trunc(fixed_lines[k]), Color.BG_GREEN + Color.WHITE))

    output.append(colorize(divider, Color.DIM))
    return "\n".join(output)


# ─── Post the edit ─────────────────────────────────────────────────────────

def apply_edit(article: str, new_wikitext: str, summary: str, opener) -> dict:
    """Post an edit to a Wikipedia Talk page using authenticated session."""
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
        "title": f"Talk:{decoded}",
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


# ─── Import the core function ──────────────────────────────────────────────

def _import_proto():
    """Import refideas_add from contribution-protocol.py."""
    import importlib.util
    proto_path = os.path.join(os.path.dirname(__file__), "contribution-protocol.py")
    spec = importlib.util.spec_from_file_location("contribution_protocol", proto_path)
    proto = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(proto)
    return proto.refideas_add


# ─── CLI ────────────────────────────────────────────────────────────────────

def parse_args():
    """Parse command line arguments."""
    args = sys.argv[1:]
    article = None
    url = None
    label = None
    source = ""
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
        elif args[i] == "--url":
            i += 1
            if i < len(args):
                url = args[i]
                i += 1
        elif args[i] == "--label":
            i += 1
            if i < len(args):
                label = args[i]
                i += 1
        elif args[i] == "--source":
            i += 1
            if i < len(args):
                source = args[i]
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

    return article, url, label, source, note, dry_run, auto_yes


def main():
    article, url, label, source, note, dry_run, auto_yes = parse_args()

    if not article or not url or not label:
        print(__doc__)
        sys.exit(1)

    refideas_add = _import_proto()

    # Auth
    opener = get_auth()
    if not opener and not dry_run:
        print(colorize("\n  ⚠️  No Wikipedia credentials found.", Color.YELLOW), file=sys.stderr)
        print("  Set WIKIPEDIA_USERNAME + WIKIPEDIA_BOT_PASSWORD in .env", file=sys.stderr)
        print("  Running in dry-run mode.\n", file=sys.stderr)
        dry_run = True

    # Generate new wikitext
    print(f"\n  Fetching Talk:{article}...", file=sys.stderr)
    result = refideas_add(
        article_title=article,
        url=url,
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

    # Fetch original again for diff (since refideas_add already fetched and returned new wikitext,
    # but we need the original for diff display). Parse it back out.
    # The refideas_add function fetched wikitext internally - we need the original.
    # Re-fetch for diff display.
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

    # Show side-by-side diff
    diff = side_by_side_diff(current_wikitext, new_wikitext, f"Talk:{article}")
    print(diff)

    if dry_run:
        print(colorize("\n  Dry run — no edit was made.", Color.YELLOW))
        if source or note:
            print(f"\n  To apply, run without --dry-run:")
            print(f"  python3 scripts/refideas-add.py \"{article}\" \\")
            print(f"      --url \"{url}\" \\")
            print(f"      --label \"{label}\" \\")
            print(f"      --source \"{source}\"" + (" \\" if note else ""))
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

    # Post
    print(f"\n  Posting edit...", file=sys.stderr)
    edit_result = apply_edit(article, new_wikitext, summary, opener)

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
