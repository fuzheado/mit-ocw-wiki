#!/usr/bin/env python3
"""
Prioritize OCW→Wikipedia matches for refideas insertion.

Option B scoring: template gate + lecture↔article keyword overlap.
Auto-apply is gated behind an explicit --apply-top N flag.

Usage:
    python3 scripts/prioritize-matches.py                    # Score and rank all matches
    python3 scripts/prioritize-matches.py --min-score 50     # Only show score ≥ 50
    python3 scripts/prioritize-matches.py --apply-top 3      # Post top 3 matches (with confirmation)
    python3 scripts/prioritize-matches.py --apply-top 5 --yes # Post top 5 (auto-confirm)
"""

import os
import sys
import re
import subprocess
import importlib.util

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPTS_DIR)

# Import DEMO_DATA from crossref-wikipedia.py
_xref_spec = importlib.util.spec_from_file_location(
    "crossref_wikipedia",
    os.path.join(SCRIPTS_DIR, "crossref-wikipedia.py")
)
_xref = importlib.util.module_from_spec(_xref_spec)
_xref_spec.loader.exec_module(_xref)


# ─── Stop words ────────────────────────────────────────────────────────────

STOP_WORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "as", "is", "was", "are", "be", "been",
    "its", "it", "this", "that", "these", "those", "has", "have", "had",
    "not", "no", "nor", "so", "if", "then", "than", "too", "very", "just",
    "about", "into", "over", "also", "can", "may", "will", "would",
    "such", "each", "all", "some", "any", "both", "more", "most",
    "other", "only", "new", "use", "used", "using", "one", "two",
}


# ─── Course URL lookup ─────────────────────────────────────────────────────

def load_course_urls():
    """Build {course_id: url} from wiki/courses/ frontmatter."""
    courses_dir = os.path.join(os.path.dirname(SCRIPTS_DIR), "wiki", "courses")
    urls = {}
    if not os.path.isdir(courses_dir):
        return urls

    for filename in os.listdir(courses_dir):
        if not filename.endswith(".md"):
            continue
        fpath = os.path.join(courses_dir, filename)
        try:
            with open(fpath) as f:
                cid = None
                url = None
                in_frontmatter = False
                for line in f:
                    line = line.rstrip("\n")
                    if line == "---":
                        if not in_frontmatter:
                            in_frontmatter = True
                            continue
                        else:
                            break
                    if in_frontmatter:
                        if line.startswith("course_id:"):
                            cid = line.split(":", 1)[1].strip().strip('"')
                        elif line.startswith("url:"):
                            url = line.split(":", 1)[1].strip().strip('"')
                if cid and url:
                    # Normalize: lowercase for case-insensitive lookup
                    urls[cid.lower()] = url
        except Exception:
            continue
    return urls


def load_lecture_titles():
    """
    Build {course_id_lower: [lecture_title, ...]} from scanned wiki/courses/.
    Extracts titles from the ### Lectures section.
    """
    courses_dir = os.path.join(os.path.dirname(SCRIPTS_DIR), "wiki", "courses")
    lectures = {}
    if not os.path.isdir(courses_dir):
        return lectures

    for filename in os.listdir(courses_dir):
        if not filename.endswith(".md"):
            continue
        fpath = os.path.join(courses_dir, filename)
        try:
            with open(fpath) as f:
                content = f.read()

            cid_match = re.search(r'^course_id:\s*"([^"]+)"', content, re.MULTILINE)
            if not cid_match:
                continue
            cid = cid_match.group(1)

            in_lectures = False
            titles = []
            for line in content.splitlines():
                if line.strip().startswith("### Lectures"):
                    in_lectures = True
                    continue
                if in_lectures:
                    if line.strip().startswith("###") or line.strip().startswith("##"):
                        break
                    m = re.search(r'\*\*Lecture\s+\d+:\s*(.+?)\*\*', line)
                    if m:
                        titles.append(m.group(1).strip())

            if titles:
                lectures[cid.lower()] = titles
        except Exception:
            continue

    return lectures


# ─── Tokenization ──────────────────────────────────────────────────────────

def tokenize(text: str) -> set:
    """Tokenize text into lowercase keywords, removing stop words and short tokens."""
    tokens = re.findall(r"[a-zA-Z0-9]{2,}", text.lower())
    return {t for t in tokens if t not in STOP_WORDS}


def overlap_score(article_title: str, lecture_title: str) -> float:
    """
    Compute keyword overlap between article and lecture.
    Returns 0.0–1.0 (Jaccard similarity of token sets).
    """
    a_tokens = tokenize(article_title)
    l_tokens = tokenize(lecture_title)
    if not a_tokens or not l_tokens:
        return 0.0
    intersection = a_tokens & l_tokens
    union = a_tokens | l_tokens
    return len(intersection) / len(union)


# ─── Template scoring ──────────────────────────────────────────────────────

TEMPLATE_WEIGHTS = {
    "citation needed": 35,
    "cn": 35,
    "fact": 35,
    "missing information": 30,
    "more citations needed": 25,
    "refimprove": 20,
    "more references": 20,
    "unreferenced": 20,
    "primary sources": 15,
    "third-party": 15,
}


def template_score(templates: list) -> float:
    """
    Score template urgency. 0 = no templates.
    Multiple templates stack (e.g., Citation needed + Refimprove = 35 + 20 = 55,
    but capped at 35 max — we take the highest urgency template).
    """
    if not templates:
        return 0.0
    best = 0.0
    for t in templates:
        key = t.strip().lower()
        best = max(best, TEMPLATE_WEIGHTS.get(key, 10.0))
    return best


# ─── Specificity scoring ───────────────────────────────────────────────────

def specificity_score(article_title: str) -> float:
    """
    Score article specificity. More words in title = more specific.
    1 word → 0, 5+ words → 1.0. Scaled linearly.
    """
    words = article_title.split()
    n = len(words)
    if n <= 1:
        return 0.0
    if n >= 5:
        return 1.0
    return (n - 1) / 4.0


# ─── Composite score ───────────────────────────────────────────────────────

def score_match(article_title: str, templates: list, lecture_title: str) -> dict:
    """
    Score a single article↔lecture match.
    Returns {score, template_score, overlap, specificity, eligible}.
    """
    t_score = template_score(templates)
    overlap = overlap_score(article_title, lecture_title)
    spec = specificity_score(article_title)

    if t_score == 0:
        # Template gate: no maintenance template → skip
        return {
            "score": 0,
            "template_score": 0,
            "overlap": round(overlap, 2),
            "specificity": round(spec, 2),
            "eligible": False,
            "reason": "no maintenance template",
        }

    # Weighted composite — 0–100 scale
    # template_urgency: up to 35, overlap: up to 35, specificity: up to 30
    composite = min(100,
        t_score * 1.0 +       # raw template score (0–35)
        overlap * 35 +         # keyword overlap (0–35)
        spec * 30              # title word count (0–30)
    )
    composite = round(composite, 1)

    return {
        "score": round(composite, 1),
        "template_score": round(t_score, 1),
        "overlap": round(overlap, 2),
        "specificity": round(spec, 2),
        "eligible": True,
        "reason": "",
    }


# ─── Main scoring loop ─────────────────────────────────────────────────────

def score_all_matches(demo_data: dict, course_urls: dict, lecture_titles: dict) -> list:
    """Score all matches across all WikiProjects. Returns sorted list of match dicts."""
    results = []

    for project, data in demo_data.items():
        for article in data.get("articles", []):
            article_title = article["title"]
            templates = article.get("templates", [])
            quality = article.get("quality", "?")
            importance = article.get("importance", "?")
            views = article.get("views", 0)

            for match in article.get("ocw_matches", []):
                course_id = match["course"]
                course_title = match["title"]
                url = course_urls.get(course_id.lower(), "")

                if not url:
                    continue

                # Use REAL lecture titles from scanned data, fall back to demo estimate
                real_lectures = lecture_titles.get(course_id.lower(), [])
                if real_lectures:
                    # Find best-matching lecture for this article
                    best_overlap = 0.0
                    best_lecture = ""
                    for lt in real_lectures:
                        ov = overlap_score(article_title, lt)
                        if ov > best_overlap:
                            best_overlap = ov
                            best_lecture = lt
                    lecture = best_lecture
                else:
                    # No scanned data — fall back to demo estimate (with warning)
                    lecture = match.get("lecture", "") + " [demo]"

                scoring = score_match(article_title, templates, lecture)
                # Re-score with actual best overlap
                if real_lectures:
                    scoring = score_match(article_title, templates, best_lecture)

                results.append({
                    "article": article_title,
                    "quality": quality,
                    "importance": importance,
                    "views": views,
                    "templates": templates,
                    "course_id": course_id,
                    "course_title": course_title,
                    "course_url": url,
                    "lecture": lecture if real_lectures else match.get("lecture", "") + " [demo]",
                    "project": project,
                    **scoring,
                })

    # Sort by score descending
    results.sort(key=lambda r: r["score"], reverse=True)
    return results


# ─── Output ─────────────────────────────────────────────────────────────────

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


def print_ranked(results: list, min_score: float = 0):
    """Print ranked match list."""
    eligible = [r for r in results if r["eligible"] and r["score"] >= min_score]
    skipped = [r for r in results if not r["eligible"]]

    print(f"\n{'='*72}")
    print(f"  Match Rankings — {len(eligible)} eligible, {len(skipped)} gated")
    print(f"{'='*72}\n")

    if not eligible:
        print("  No eligible matches found.")
        return

    # Header
    print(f"  {'#':<3} {'Score':>5}  {'Article':<35} {'Course':<12} {'Templ':>5} {'Overlap':>7} {'Spec':>5}  {'Views':>8}")
    print(f"  {'-'*3} {'-'*5}  {'-'*35} {'-'*12} {'-'*5} {'-'*7} {'-'*5}  {'-'*8}")

    for i, r in enumerate(eligible):
        score_color = Color.GREEN if r["score"] >= 60 else Color.YELLOW if r["score"] >= 35 else Color.RED
        art = r["article"][:33] + (".." if len(r["article"]) > 33 else "")

        score_str = c(str(round(r["score"], 1)).rjust(5), score_color)
        templ_str = str(round(r["template_score"], 1)).rjust(5)
        overl_str = str(round(r["overlap"], 2)).rjust(7)
        spec_str = str(round(r["specificity"], 2)).rjust(5)
        views_str = f"{r['views']:>8,}"

        print(
            f"  {i+1:<3} "
            f"{score_str}  "
            f"{art:<35} "
            f"{r['course_id']:<12} "
            f"{templ_str} "
            f"{overl_str} "
            f"{spec_str}  "
            f"{views_str}"
        )

    print(f"\n  Score = template_urgency (0-35) + overlap × 35 + specificity × 30")
    print(f"  Template gate: no maintenance template → score = 0 (skipped)\n")

    if skipped:
        print(f"  {c(f'{len(skipped)} matches skipped (no maintenance template):', Color.DIM)}")
        for r in skipped[:5]:
            print(f"    - {r['article']} ← {r['course_id']}")
        if len(skipped) > 5:
            print(f"    ... and {len(skipped) - 5} more")

    # Show apply command
    print(f"\n  {c('To apply top N matches:', Color.BOLD)}")
    print(f"  python3 scripts/prioritize-matches.py --apply-top 3")
    print(f"  python3 scripts/prioritize-matches.py --apply-top 5 --yes")
    print(f"\n  {c('For detailed reasoning:', Color.DIM)}")
    print(f"  python3 scripts/prioritize-matches.py -v")
    print()


def print_verbose(results: list, top_n: int = 5):
    """Print detailed reasoning for the top N matches."""
    eligible = [r for r in results if r["eligible"]]
    to_show = eligible[:top_n]

    print(f"\n{'='*72}")
    print(f"  Verbose Reasoning — Top {min(top_n, len(to_show))} Matches")
    print(f"{'='*72}")

    for i, r in enumerate(to_show):
        article = r["article"]
        course_id = r["course_id"]
        course_title = r["course_title"]
        lecture = r.get("lecture", "")
        templates = r["templates"]
        score = r["score"]
        t_score = r["template_score"]
        overlap = r["overlap"]
        spec = r["specificity"]

        score_color = Color.GREEN if score >= 60 else Color.YELLOW if score >= 35 else Color.RED

        print(f"\n  ┌─ #{i+1}: {c(article, Color.BOLD)} ← {course_id} ({course_title})")
        print(f"  │  Score: {c(str(score), score_color)} / 100")
        print(f"  │")

        # Template gate
        if templates:
            template_names = ", ".join(f"{{{{{t}}}}}" for t in templates)
            print(f"  │  📋 Template gate: {c('PASS', Color.GREEN)}")
            print(f"  │     Found: {template_names}")
            print(f"  │     Urgency: {t_score}/35")
        else:
            print(f"  │  📋 Template gate: {c('FAIL', Color.RED)} (no maintenance templates)")

        # Lecture matching
        if lecture and "[demo]" not in lecture:
            a_tokens = tokenize(article)
            l_tokens = tokenize(lecture)
            shared = a_tokens & l_tokens
            article_only = a_tokens - l_tokens
            lecture_only = l_tokens - a_tokens

            print(f"  │")
            print(f"  │  🎓 Lecture match: {c(lecture, Color.CYAN)}")
            print(f"  │     Article tokens:  {sorted(a_tokens)}")
            print(f"  │     Lecture tokens:  {sorted(l_tokens)}")
            if shared:
                print(f"  │     Shared:          {c(str(sorted(shared)), Color.GREEN)}")
            if article_only:
                print(f"  │     Article only:    {c(str(sorted(article_only)), Color.DIM)}")
            if lecture_only:
                print(f"  │     Lecture only:    {c(str(sorted(lecture_only)), Color.DIM)}")
            print(f"  │     Overlap: {len(shared)}/{len(a_tokens | l_tokens)} = {overlap:.2f} → {overlap*35:.0f}/35")
            if "[demo]" in lecture:
                print(f"  │     ⚠️  Using demo estimate (no real lectures scanned)")
        elif lecture:
            print(f"  │")
            print(f"  │  🎓 Lecture match: {c('[demo data — no real lectures available]', Color.YELLOW)}")
            print(f"  │     ⚠️  Course has no extractable lecture titles")
        else:
            print(f"  │")
            print(f"  │  🎓 Lecture match: {c('[none]', Color.RED)}")

        # Specificity
        words = article.split()
        print(f"  │")
        print(f"  │  📐 Article specificity: {spec:.2f} → {spec*30:.0f}/30")
        print(f"  │     Title: \"{article}\" ({len(words)} word{'s' if len(words) != 1 else ''})")

        # Formula
        print(f"  │")
        print(f"  │  🧮 Score = {t_score:.0f} (templates) + {overlap*35:.0f} (overlap) + {spec*30:.0f} (specificity)")
        print(f"  │       = {c(str(score), score_color)} / 100")

        # Recommendation
        if score >= 60:
            print(f"  │")
            print(f"  │  {c('✅ Strong match — recommend applying', Color.GREEN)}")
        elif score >= 35:
            print(f"  │")
            print(f"  │  {c('🟡 Moderate match — review before applying', Color.YELLOW)}")
        else:
            print(f"  │")
            print(f"  │  {c('🔴 Weak match — likely not worth applying', Color.RED)}")

        print(f"  └{'─'*70}")

    print()


def apply_top(results: list, n: int, auto_yes: bool = False):
    """Apply the top N eligible matches."""
    eligible = [r for r in results if r["eligible"]]
    if not eligible:
        print("No eligible matches to apply.")
        return

    to_apply = eligible[:n]
    print(f"\n  Applying top {len(to_apply)} matches...\n")

    script = os.path.join(SCRIPTS_DIR, "apply-l1-refideas.py")
    yes_flag = ["--yes"] if auto_yes else []

    for i, r in enumerate(to_apply):
        note = f"lecture: {r['lecture']}" if r["lecture"] else ""
        print(f"  [{i+1}/{len(to_apply)}] {r['article']} ← {r['course_id']} (score: {r['score']})")

        cmd = [
            sys.executable, script,
            r["article"],
            "--course-id", r["course_id"],
            "--course-title", r["course_title"],
            "--course-url", r["course_url"],
        ] + yes_flag
        if note:
            cmd.extend(["--note", note])

        result = subprocess.run(cmd, capture_output=True, text=True)
        stdout = result.stdout + result.stderr

        # Extract key lines
        for line in stdout.splitlines():
            if any(kw in line for kw in ["✅ Refideas posted", "❌ Edit failed", "⏭"]):
                print(f"    {line.strip()}")
                break
        else:
            # Fallback: print last meaningful line
            lines = [l for l in stdout.splitlines() if l.strip() and "Authenticated" not in l]
            if lines:
                print(f"    {lines[-1].strip()[:100]}")

        print()


# ─── CLI ────────────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]
    min_score = 0
    apply_n = 0
    auto_yes = False
    verbose = False

    i = 0
    while i < len(args):
        if args[i] == "--min-score":
            i += 1
            if i < len(args):
                min_score = float(args[i])
        elif args[i] == "--apply-top":
            i += 1
            if i < len(args):
                apply_n = int(args[i])
        elif args[i] in ("--yes", "-y"):
            auto_yes = True
        elif args[i] in ("--verbose", "-v"):
            verbose = True
        else:
            print(f"Unknown flag: {args[i]}", file=sys.stderr)
        i += 1

    print("  Loading course URLs from wiki/courses/...")
    course_urls = load_course_urls()
    print(f"  Found {len(course_urls)} course URLs")

    print("  Loading real lecture titles from scanned courses...")
    lecture_titles = load_lecture_titles()
    course_count = len(lecture_titles)
    total_lectures = sum(len(v) for v in lecture_titles.values())
    print(f"  Found {total_lectures} lecture titles across {course_count} courses")

    demo_data = _xref.DEMO_DATA
    project_count = len(demo_data)
    article_count = sum(len(v.get("articles", [])) for v in demo_data.values())
    print(f"  Loaded {article_count} articles across {project_count} WikiProjects")

    results = score_all_matches(demo_data, course_urls, lecture_titles)

    if apply_n > 0:
        apply_top(results, apply_n, auto_yes)
    else:
        print_ranked(results, min_score)
        if verbose:
            print_verbose(results)


if __name__ == "__main__":
    main()
