#!/usr/bin/env python3
"""
Apply Refideas fixes to Wikipedia Talk pages.

Full reference: docs/L1-REFIDEAS.md — algorithm, error types, CLI, live editing workflow.
Keep that doc in sync when changing this script.

Shows a color-coded side-by-side diff, prompts for confirmation, then posts
the fix via the Wikipedia API.

Authentication:
    Uses OAuth 2.0 owner-only consumer tokens or bot password.
    Set in .env or environment variables:

    # Bot password (simplest — create at Special:BotPasswords)
    WIKIPEDIA_USERNAME=your_username
    WIKIPEDIA_BOT_PASSWORD=your_bot_password

    # OAuth 1.0a (owner-only consumer from Special:OAuthConsumerRegistration)
    WIKIPEDIA_CONSUMER_TOKEN=your_consumer_token
    WIKIPEDIA_CONSUMER_SECRET=your_consumer_secret
    WIKIPEDIA_ACCESS_TOKEN=your_access_token
    WIKIPEDIA_ACCESS_SECRET=your_access_secret

Usage:
    python3 scripts/apply-refideas-fix.py "Article title"         # Fix one page
    python3 scripts/apply-refideas-fix.py --dry-run "Article"      # Show diff only
    python3 scripts/apply-refideas-fix.py --yes "Article"          # Skip confirmation
    python3 scripts/apply-refideas-fix.py --survey 50              # Find pages with errors
"""

import os
import sys
import json
import re
import time
import urllib.request
import urllib.parse
import hashlib
import hmac
import base64
import random
from typing import Optional, Tuple

try:
    import mwparserfromhell
    HAS_MWPARSER = True
except ImportError:
    HAS_MWPARSER = False

# Add parent scripts to path for lint_refideas import
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
    """
    Authenticate with Wikipedia using bot password (action=login).
    Returns an opener with cookies set if successful, None if no credentials.
    """
    import http.cookiejar
    
    username = os.environ.get("WIKIPEDIA_USERNAME", "").strip().strip('"').strip("'")
    bot_password = os.environ.get("WIKIPEDIA_BOT_PASSWORD", "").strip().strip('"').strip("'")
    
    if not username or not bot_password:
        return None
    
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    
    # Step 1: Get login token
    token_url = WIKIPEDIA_API + "?action=query&meta=tokens&type=login&format=json&formatversion=2"
    req = urllib.request.Request(token_url, headers={"User-Agent": UA})
    with opener.open(req, timeout=15) as resp:
        data = json.loads(resp.read())
        login_token = data["query"]["tokens"]["logintoken"]
    
    # Step 2: Login
    post_data = urllib.parse.urlencode({
        "action": "login",
        "lgname": username,
        "lgpassword": bot_password,
        "lgtoken": login_token,
        "format": "json",
    }).encode()
    
    req = urllib.request.Request(
        WIKIPEDIA_API,
        data=post_data,
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


def api_request(params: dict, opener=None, method="GET") -> dict:
    """Make a request to the Wikipedia API, optionally authenticated."""
    url = WIKIPEDIA_API + "?" + urllib.parse.urlencode(params)
    headers = {"User-Agent": UA}
    
    if method == "POST":
        data = urllib.parse.urlencode(params).encode()
        req = urllib.request.Request(WIKIPEDIA_API, data=data, headers=headers)
    else:
        req = urllib.request.Request(url, headers=headers)
    
    fetcher = opener if opener else urllib.request.build_opener()
    
    try:
        with fetcher.open(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode() if e.fp else str(e)
        return {"error": {"code": str(e.code), "info": error_body[:500]}}
    except Exception as e:
        return {"error": {"code": "exception", "info": str(e)}}


# ─── Side-by-side diff ─────────────────────────────────────────────────────

def side_by_side_diff(original: str, fixed: str, title: str, col_width: int = 38) -> str:
    """
    Render a color-coded side-by-side diff with long unchanged sections collapsed.
    """
    from difflib import SequenceMatcher
    
    def trunc(s, w=col_width):
        s = s.rstrip()
        return (s[:w-3] + "...") if len(s) > w else s.ljust(w)
    
    orig_lines = original.splitlines()
    fixed_lines = fixed.splitlines()
    sm = SequenceMatcher(None, orig_lines, fixed_lines)
    
    output = []
    divider = "─" * col_width + "─┼─" + "─" * col_width
    
    output.append(colorize(f"\n  Fix: {title}", Color.BOLD))
    output.append(colorize(divider, Color.DIM))
    
    # Headers
    output.append(
        colorize("Original".center(col_width), Color.BOLD + Color.BG_RED) +
        colorize(" │ ", Color.DIM) +
        colorize("Fixed".center(col_width), Color.BOLD + Color.BG_GREEN)
    )
    output.append(colorize(divider, Color.DIM))
    
    context = 3
    for idx, (tag, i1, i2, j1, j2) in enumerate(sm.get_opcodes()):
        if tag == "equal":
            run_len = i2 - i1
            if run_len > context * 2 + 2:
                # Show first context lines
                for k in range(min(context, run_len)):
                    output.append(f"{trunc(orig_lines[i1 + k])} │ {trunc(fixed_lines[j1 + k])}")
                output.append(colorize(f"  ... {run_len - 2*context} unchanged lines ...".center(col_width*2+3), Color.DIM))
                # Show last context lines
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


# ─── Core logic ────────────────────────────────────────────────────────────

def fetch_talk_wikitext(article: str) -> str:
    """Fetch Talk page wikitext."""
    decoded = urllib.parse.unquote(article).replace(" ", "_")
    encoded = urllib.parse.quote(decoded, safe="")
    url = f"{WIKIPEDIA_API}?action=parse&page=Talk:{encoded}&prop=wikitext&format=json&formatversion=2"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            return data.get("parse", {}).get("wikitext", "")
    except Exception as e:
        return f"__ERROR__: {e}"


def fetch_talk_wikitext_batch(articles: list) -> dict:
    """
    Fetch Talk page wikitext for multiple articles in bulk (up to 50 per call).
    Returns {article_title: wikitext} dict.
    """
    results = {}
    for i in range(0, len(articles), 50):
        batch = articles[i:i+50]
        titles = "|".join(
            f"Talk:{urllib.parse.quote(urllib.parse.unquote(a).replace(' ', '_'), safe='')}"
            for a in batch
        )
        url = (
            f"{WIKIPEDIA_API}?action=query"
            f"&titles={urllib.parse.quote(titles, safe='|:')}"
            f"&prop=revisions&rvprop=content&rvslots=*"
            f"&format=json&formatversion=2"
        )
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
                pages = data.get("query", {}).get("pages", [])
                for page in pages:
                    title = page.get("title", "")
                    at = title[5:] if title.startswith("Talk:") else title
                    revs = page.get("revisions", [])
                    results[at] = revs[0].get("slots", {}).get("main", {}).get("content", "") if revs else ""
        except Exception as e:
            for a in batch:
                results[a] = f"__ERROR__: {e}"
        time.sleep(0.3)
    return results


def get_refideas_fixes(wikitext: str, article: str) -> Tuple[Optional[str], list]:
    """
    Analyze a Talk page and return (fixed_wikitext_or_None, errors_list).
    Imports and reuses the linter's generate_fix logic.
    """
    import importlib.util
    
    if not HAS_MWPARSER:
        return None, [{"type": "error", "message": "mwparserfromhell not installed"}]
    
    # Import lint-refideas.py (hyphen in filename requires importlib)
    lint_path = os.path.join(os.path.dirname(__file__), "lint-refideas.py")
    spec = importlib.util.spec_from_file_location("lint_refideas", lint_path)
    lint = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lint)
    
    # Lint first
    result = lint.lint_refideas_templates(wikitext, article)
    if not result.has_actionable_errors:
        return None, []
    
    # Generate fix
    fixed_wikitext, errors, summary = lint.generate_fix(wikitext, article)
    
    if fixed_wikitext == wikitext:
        return None, []
    
    # Map errors to simple dicts for display
    error_dicts = [
        {"type": e.type, "severity": e.severity, "message": e.message,
         "original": e.original, "fixed": e.fixed}
        for e in errors
    ]
    
    return fixed_wikitext, error_dicts


def apply_edit(article: str, new_wikitext: str, summary: str, opener) -> dict:
    """Post an edit to a Wikipedia Talk page using authenticated session."""
    # Step 1: Get CSRF token
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
    
    # Step 2: Post the edit — build URL manually to avoid urlencode double-encoding
    decoded = urllib.parse.unquote(article).replace(" ", "_")
    encoded = urllib.parse.quote(decoded, safe="")
    post_data = urllib.parse.urlencode({
        "action": "edit",
        "title": f"Talk:{decoded}",  # urlencode handles encoding here
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


# ─── Survey mode ────────────────────────────────────────────────────────────

def do_survey(sample_size: int = 50):
    """Sample pages and list ones with actionable errors."""
    import importlib.util
    lint_path = os.path.join(os.path.dirname(__file__), "lint-refideas.py")
    spec = importlib.util.spec_from_file_location("lint_refideas", lint_path)
    lint = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lint)
    
    print(f"\n  Surveying {sample_size} random Refideas pages...\n", file=sys.stderr)
    articles = lint.fetch_random_refideas_sample(sample_size)
    
    # Batch fetch all page wikitext
    print(f"  Fetching {len(articles)} Talk pages (batch)...", file=sys.stderr)
    wikitexts = fetch_talk_wikitext_batch(articles)
    print(f"  Fetched {len(wikitexts)} pages", file=sys.stderr)
    
    candidates = []
    for i, article in enumerate(articles):
        wikitext = wikitexts.get(article, "")
        if wikitext.startswith("__ERROR__") or not wikitext:
            continue
        result = lint.lint_refideas_templates(wikitext, article)
        if result.has_actionable_errors:
            error_types = set(e.type for e in result.errors if e.severity in ("error", "warning"))
            candidates.append((article, result.actionable_count, error_types, result.template_alias_used))
        if (i + 1) % 20 == 0:
            print(f"  {i+1}/{sample_size}...", file=sys.stderr)
    
    print(f"\n{'='*70}")
    print(f"  Survey: {len(candidates)} of {sample_size} pages have actionable errors\n")
    
    if not candidates:
        print("  No pages with errors found in this sample. Try a larger sample.")
        return
    
    for article, count, types, alias in candidates:
        type_str = ", ".join(sorted(types))
        print(f"  {article}")
        print(f"    {count} issue(s) — [{type_str}] — {alias}")
        print(f"    Fix: python3 scripts/apply-refideas-fix.py \"{article}\"")
        print()
    
    print(f"  Run any of the above commands to apply fixes.")


# ─── CLI ────────────────────────────────────────────────────────────────────

def main():
    article = None
    dry_run = False
    auto_yes = False
    
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--dry-run":
            dry_run = True
            i += 1
        elif args[i] in ("--yes", "-y"):
            auto_yes = True
            i += 1
        elif args[i] == "--batch":
            print("Batch mode not yet implemented.", file=sys.stderr)
            sys.exit(1)
        elif args[i] == "--survey":
            i += 1
            sample_size = int(args[i]) if i < len(args) else 50
            do_survey(sample_size)
            sys.exit(0)
        else:
            article = args[i]
            i += 1
    
    if not article:
        print(__doc__)
        sys.exit(1)
    
    # Auth
    opener = get_auth()
    if not opener and not dry_run:
        print(colorize("\n  ⚠️  No Wikipedia credentials found.", Color.YELLOW), file=sys.stderr)
        print("  Set WIKIPEDIA_USERNAME + WIKIPEDIA_BOT_PASSWORD in .env", file=sys.stderr)
        print("  Running in dry-run mode.\n", file=sys.stderr)
        dry_run = True
    
    if not HAS_MWPARSER:
        print("Error: mwparserfromhell is required. Install with: pip install mwparserfromhell", file=sys.stderr)
        sys.exit(1)
    
    # Fetch and analyze
    print(f"\n  Fetching Talk:{article}...", file=sys.stderr)
    wikitext = fetch_talk_wikitext(article)
    if not wikitext:
        print(f"  Error: could not fetch Talk page for '{article}'", file=sys.stderr)
        sys.exit(1)
    
    print(f"  Analyzing...", file=sys.stderr)
    fixed_wikitext, errors = get_refideas_fixes(wikitext, article)
    
    if not errors and not fixed_wikitext:
        print(colorize(f"\n  ✅ No issues found on Talk:{article}. Nothing to fix.", Color.GREEN))
        sys.exit(0)
    
    if not fixed_wikitext or fixed_wikitext == wikitext:
        print(colorize(f"\n  ℹ️  Issues found but no automatic fixes available.", Color.YELLOW))
        for e in errors:
            print(f"  [{e['type']}] {e['message']}")
        sys.exit(0)
    
    # Show error summary
    error_count = sum(1 for e in errors if e.get("severity") in ("error", "warning"))
    print(f"\n  Found {error_count} fixable issue(s):")
    for e in errors:
        icon = "🔴" if e.get("severity") == "error" else "🟡"
        print(f"  {icon} [{e['type']}] {e['message']}")
    
    # Show side-by-side diff
    diff = side_by_side_diff(wikitext, fixed_wikitext, f"Talk:{article}")
    print(diff)
    
    if dry_run:
        print(colorize("\n  Dry run — no edit was made.", Color.YELLOW))
        sys.exit(0)
    
    # Confirm (skip if --yes)
    if auto_yes:
        print(colorize("\n  Auto-applying (--yes)...", Color.YELLOW))
    else:
        print()
        try:
            response = input(colorize("  Apply this fix? [y/N] ", Color.BOLD))
        except (EOFError, KeyboardInterrupt):
            print("\n  Cancelled.")
            sys.exit(0)
        
        if response.lower() not in ("y", "yes"):
            print(colorize("  Cancelled.", Color.YELLOW))
            sys.exit(0)
    
    # Build descriptive edit summary from error types
    error_types = list(set(e["type"] for e in errors if e.get("severity") in ("error", "warning")))
    
    type_labels = {
        "multi_bullet": "split bullet list into proper refideas parameters",
        "bullet_syntax": "fixed malformed bullet syntax in refideas template",
        "duplicate_url": "removed duplicate URL from refideas template",
    }
    
    descriptions = [type_labels.get(t, f"fixed {t}") for t in error_types]
    
    if len(descriptions) == 1:
        action = descriptions[0]
    elif len(descriptions) == 2:
        action = f"{descriptions[0]} and {descriptions[1]}"
    else:
        action = ", ".join(descriptions[:-1]) + f", and {descriptions[-1]}"
    
    summary = f"Refideas: {action} via Wiki MIT"
    print(f"\n  Posting edit...", file=sys.stderr)
    
    result = apply_edit(article, fixed_wikitext, summary, opener)
    
    if "error" in result:
        error_info = result["error"]
        print(colorize(f"\n  ❌ Edit failed: {error_info.get('code', 'unknown')}", Color.RED))
        if "info" in error_info:
            print(f"  {error_info['info'][:300]}")
        sys.exit(1)
    
    # Success
    edit_result = result.get("edit", {})
    if edit_result.get("result") == "Success":
        rev_id = edit_result.get("newrevid", "?")
        print(colorize(f"\n  ✅ Fix applied! Revision: {rev_id}", Color.GREEN))
        print(f"  https://en.wikipedia.org/w/index.php?title=Talk:{urllib.parse.quote(urllib.parse.unquote(article).replace(' ', '_'), safe='')}&oldid={rev_id}")
    else:
        print(colorize(f"\n  ⚠️  Unexpected response: {json.dumps(result, indent=2)[:300]}", Color.YELLOW))


if __name__ == "__main__":
    main()
