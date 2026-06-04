"""
CLI entry point for the Article Footer Linter.

Usage:
    article-footer-lint "Article"                    # Analyze only
    article-footer-lint "Article" --fix              # Analyze + fix
    article-footer-lint "Article" --fix --dry-run    # Preview fix
    article-footer-lint --survey 50                  # Batch survey
"""

import os, sys, json, urllib.request, urllib.parse, re
from typing import Optional

from . import analyze_footer, apply_fixes


# ─── Wikipedia API helpers ─────────────────────────────────────────────────

UA = "MIT OCW Bot/1.0 (https://meta.wikimedia.org/wiki/Wiki_MIT; andrew.lih@gmail.com) ContentGapResearch"
API = "https://en.wikipedia.org/w/api.php"


def fetch_wikitext(title: str) -> str:
    """Fetch the full wikitext of a Wikipedia article."""
    encoded = urllib.parse.quote(title.replace(" ", "_"), safe="")
    url = f"{API}?action=query&titles={encoded}&prop=revisions&rvprop=content&rvslots=*&format=json&formatversion=2"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())
        pages = data["query"]["pages"]
        wikitext = pages[0].get("revisions", [{}])[0].get("slots", {}).get("main", {}).get("content", "")
        if not wikitext:
            raise ValueError(f"Could not fetch wikitext for '{title}' (missing, protected, or API error)")
        return wikitext


def post_edit(title: str, wikitext: str, summary: str, auth: Optional[dict] = None):
    """Post an edit to Wikipedia. Requires authentication.

    Uses the same cookie-jar-based login flow as refideas-add.py.
    """
    if not auth:
        print("  No authentication provided. Use --dry-run to preview.", file=sys.stderr)
        return False

    import http.cookiejar

    # Cookie jar is essential — it carries the login session to subsequent requests
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    # Step 1: Get login token
    token_url = f"{API}?action=query&meta=tokens&type=login&format=json&formatversion=2"
    req = urllib.request.Request(token_url, headers={"User-Agent": UA})
    with opener.open(req, timeout=15) as resp:
        data = json.loads(resp.read())
        login_token = data["query"]["tokens"]["logintoken"]

    # Step 2: Login (POST to base API, not the token URL)
    login_data = urllib.parse.urlencode({
        "action": "login",
        "lgname": auth["username"],
        "lgpassword": auth["password"],
        "lgtoken": login_token,
        "format": "json",
    }).encode()
    req = urllib.request.Request(
        API, data=login_data,
        headers={"User-Agent": UA, "Content-Type": "application/x-www-form-urlencoded"}
    )
    with opener.open(req, timeout=15) as resp:
        data = json.loads(resp.read())
        result = data.get("login", {})
        if result.get("result") != "Success":
            print(f"  \u274c Login failed: {result.get('reason', 'unknown')}", file=sys.stderr)
            return False

    print(f"  Authenticated as: {result.get('lgusername', auth['username'])}", file=sys.stderr)

    # Step 3: Get CSRF token
    token_url = f"{API}?action=query&meta=tokens&type=csrf&format=json&formatversion=2"
    req = urllib.request.Request(token_url, headers={"User-Agent": UA})
    with opener.open(req, timeout=15) as resp:
        data = json.loads(resp.read())
        csrf_token = data["query"]["tokens"]["csrftoken"]

    # Step 4: Post edit (POST to base API)
    edit_data = urllib.parse.urlencode({
        "action": "edit",
        "title": title,
        "text": wikitext,
        "summary": summary,
        "token": csrf_token,
        "format": "json",
    }).encode()
    req = urllib.request.Request(
        API, data=edit_data,
        headers={"User-Agent": UA, "Content-Type": "application/x-www-form-urlencoded"}
    )
    with opener.open(req, timeout=30) as resp:
        result = json.loads(resp.read())
        if "error" in result:
            print(f"  \u274c Edit failed: {result['error']}", file=sys.stderr)
            return False
        print(f"  \u2705 Edit posted: {result.get('edit', {}).get('newrevid', 'unknown')}", file=sys.stderr)
        return True


def load_auth():
    """Load Wikipedia bot credentials from environment variables or .env file."""
    # 1. Check actual environment variables first (fastest, most portable)
    username = os.environ.get("WIKIPEDIA_USERNAME")
    password = os.environ.get("WIKIPEDIA_BOT_PASSWORD")
    if username and password:
        return {"username": username, "password": password}

    # 2. Walk up from the package location to find project root .env
    #    cli.py lives at tools/article-footer-linter/src/article_footer_linter/cli.py
    #    We need to go up 4 levels to reach the project root.
    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(script_dir, "..", "..", "..", "..", ".env"),   # project root
        os.path.join(os.path.expanduser("~"), ".pi", "agent", ".env"),  # pi agent
    ]
    for path in candidates:
        candidate = os.path.normpath(path)
        if not os.path.exists(candidate):
            continue
        found_username = None
        found_password = None
        with open(candidate) as f:
            for line in f:
                line = line.strip()
                if line.startswith("WIKIPEDIA_USERNAME="):
                    found_username = line.split("=", 1)[1].strip().strip('"').strip("'")
                elif line.startswith("WIKIPEDIA_BOT_PASSWORD="):
                    found_password = line.split("=", 1)[1].strip().strip('"').strip("'")
        if found_username and found_password:
            return {"username": found_username, "password": found_password}

    return None


# ─── Output formatting ────────────────────────────────────────────────────

class Color:
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"

def c(text, color):
    return f"{color}{text}{Color.RESET}"

SEVERITY_COLORS = {
    "error": Color.RED,
    "warning": Color.YELLOW,
    "info": Color.DIM,
}

SEVERITY_LABELS = {
    "error": "🔴",
    "warning": "🟡",
    "info": "ℹ️",
}


def print_report(title: str, issues: list, fixes: list = None):
    """Print a human-readable report."""
    print(f"\n{'='*70}")
    print(f"  {c(title, Color.BOLD)}")
    print(f"{'='*70}")

    if not issues:
        print(f"\n  {c('✅ No issues found.', Color.GREEN)}")
        return

    print(f"\n  {c(f'{len(issues)} issue(s) detected:', Color.BOLD)}")
    for issue in issues:
        icon = SEVERITY_LABELS.get(issue.severity, "•")
        color = SEVERITY_COLORS.get(issue.severity, Color.RESET)
        print(f"  {icon} {c(f'[{issue.type}]', color)} {issue.description}")

    if fixes:
        applied = [f for f in fixes if f.applied]
        if applied:
            print(f"\n  {c(f'{len(applied)} fix(es) applied:', Color.GREEN)}")
            for fix in applied:
                print(f"  ✅ {fix.description}")

    print()


# ─── CLI ────────────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]

    if not args:
        print(__doc__)
        return

    article = None
    do_fix = False
    dry_run = False
    auto_yes = False
    survey_n = 0
    only_types = None

    i = 0
    while i < len(args):
        if args[i] == "--fix":
            do_fix = True
        elif args[i] == "--dry-run":
            dry_run = True
        elif args[i] == "--yes":
            auto_yes = True
        elif args[i] == "--survey":
            i += 1
            if i < len(args):
                survey_n = int(args[i])
        elif args[i] == "--only":
            i += 1
            if i < len(args):
                only_types = set(args[i].split(","))
        elif args[i] in ("-h", "--help"):
            print(__doc__)
            return
        else:
            article = args[i]
        i += 1

    # Survey mode
    if survey_n > 0:
        survey(survey_n, do_fix, dry_run, auto_yes)
        return

    # Single article mode
    if not article:
        print("Error: no article specified.", file=sys.stderr)
        sys.exit(1)

    print(f"  Fetching {c(article, Color.CYAN)}...", file=sys.stderr)
    try:
        wikitext = fetch_wikitext(article)
    except Exception as e:
        print(f"  ❌ {e}", file=sys.stderr)
        sys.exit(1)

    print(f"  Analyzing footer...", file=sys.stderr)
    issues = analyze_footer(wikitext)

    if only_types:
        issues = [i for i in issues if i.type in only_types]

    if not do_fix or dry_run:
        print_report(article, issues)
        if dry_run and issues:
            fixed, fixes = apply_fixes(wikitext, issues)
            applied = [f for f in fixes if f.applied]
            if applied:
                print(f"  {c('Dry-run: would apply', Color.YELLOW)} {len(applied)} fix(es):")
                for fix in applied:
                    print(f"    ✅ {fix.description}")
                print()
        return

    # Apply fixes
    fixed, fixes = apply_fixes(wikitext, issues)
    applied = [f for f in fixes if f.applied]

    if not applied:
        print(f"\n  {c('✅ No fixes needed.', Color.GREEN)}")
        return

    print_report(article, issues, applied)

    # Confirm
    if not auto_yes:
        try:
            response = input(f"  {c('Post to Wikipedia? [y/N] ', Color.BOLD)}")
        except (EOFError, KeyboardInterrupt):
            print("\n  Cancelled.")
            return
        if response.lower() not in ("y", "yes"):
            print(f"  {c('Cancelled.', Color.YELLOW)}")
            return

    # Post
    summary = "Article footer cleanup: "
    summary += ", ".join(f"{f.type}" for f in applied)

    auth = load_auth()
    if not auth:
        print(f"  {c('No Wikipedia credentials found. Set WIKIPEDIA_USERNAME + WIKIPEDIA_BOT_PASSWORD in .env', Color.YELLOW)}")
        return

    print(f"  Posting edit ({len(applied)} fix(es))...", file=sys.stderr)
    success = post_edit(article, fixed, summary, auth)
    if success:
        print(f"  {c('✅ Footer lint posted.', Color.GREEN)}")
    else:
        print(f"  {c('❌ Failed to post edit.', Color.RED)}")


def survey(n: int, do_fix: bool = False, dry_run: bool = False, auto_yes: bool = False):
    """Survey N random articles for footer issues."""
    import random, time

    # Get a list of random article titles
    url = f"{API}?action=query&list=random&rnlimit={min(n, 50)}&rnnamespace=0&format=json&formatversion=2"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())
        pages = data.get("query", {}).get("random", [])

    if not pages:
        print("  No random pages returned.", file=sys.stderr)
        return

    titles = [p["title"] for p in pages]
    issue_counts = {}
    total_with_issues = 0

    print(f"\n  Surveying {len(titles)} random articles...\n")
    print(f"  {'Article':<40} {'Issues':>6}  {'Types'}")
    print(f"  {'-'*40} {'-'*6}  {'-'*30}")

    for title in titles:
        try:
            wikitext = fetch_wikitext(title)
            issues = analyze_footer(wikitext)
            if issues:
                total_with_issues += 1
                types = ", ".join(i.type for i in issues)
                print(f"  {title:<40} {len(issues):>6}  {types}")
                for issue in issues:
                    issue_counts[issue.type] = issue_counts.get(issue.type, 0) + 1
            else:
                print(f"  {title:<40}  {c('clean', Color.GREEN)}")
        except Exception as e:
            print(f"  {title:<40}  {c(f'error: {e}', Color.RED)}")
        time.sleep(0.5)

    # Summary
    print(f"\n  {'='*60}")
    print(f"  Survey complete: {total_with_issues}/{len(titles)} articles have footer issues")
    print(f"  {'='*60}")
    if issue_counts:
        print(f"  {'Issue type':<35} {'Count':>6} {'%':>6}")
        print(f"  {'-'*35} {'-'*6} {'-'*6}")
        for itype, count in sorted(issue_counts.items(), key=lambda x: -x[1]):
            pct = count / len(titles) * 100
            bar = "█" * int(pct / 5) + "░" * max(0, 20 - int(pct / 5))
            print(f"  {itype:<35} {count:>6} {pct:>5.1f}%  {bar}")
        print()


if __name__ == "__main__":
    main()
