#!/usr/bin/env python3
"""
Prioritize OCW→Wikipedia matches for refideas insertion.

Option B scoring: template gate + lecture↔article keyword overlap.
Auto-apply is gated behind an explicit --apply-top N flag.

Usage:
    python3 scripts/prioritize-matches.py                    # Score and rank all matches
    python3 scripts/prioritize-matches.py -v                 # Verbose reasoning for top 5
    python3 scripts/prioritize-matches.py --interactive 5    # Review then confirm each
    python3 scripts/prioritize-matches.py --apply-top 3 --yes # Auto-apply top 3
    python3 scripts/prioritize-matches.py --min-score 50     # Only show score ≥ 50
    python3 scripts/prioritize-matches.py --apply-top 3      # Post top 3 matches (with confirmation)
    python3 scripts/prioritize-matches.py --apply-top 5 --yes # Post top 5 (auto-confirm)
"""

import os
import sys
import json
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

# Import get_auth from refideas-add.py for interactive mode
_add_spec = importlib.util.spec_from_file_location(
    "refideas_add_cli",
    os.path.join(SCRIPTS_DIR, "refideas-add.py")
)
_add = importlib.util.module_from_spec(_add_spec)
_add_spec.loader.exec_module(_add)
get_auth = _add.get_auth


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


# ─── Live template detection ───────────────────────────────────────────────

# Maintenance template patterns to detect in article HTML
MAINTENANCE_TEMPLATES = {
    "citation needed": ["Citation needed", "cn", "fact"],
    "more citations needed": ["More citations needed", "refimprove", "unreferenced",
                               "more references", "additional citations"],
    "missing information": ["Missing information"],
    "update": ["Update", "outdated"],
    "tone": ["Tone", "essay-like", "peacock"],
    "third-party": ["Third-party", "primary sources", "self-published"],
    "cleanup": ["Cleanup", "copy edit"],
    "expand": ["Expand section", "expand language", "stub"],
}

UA = "MIT OCW Bot/1.0 (https://meta.wikimedia.org/wiki/Wiki_MIT; andrew.lih@gmail.com) ContentGapResearch"
TEMPLATE_CACHE = {}  # {article_title: [template_names]}


def detect_templates_for_article(article_title: str) -> list:
    """Fetch article HTML and detect maintenance templates. Results cached."""
    if article_title in TEMPLATE_CACHE:
        return TEMPLATE_CACHE[article_title]

    import urllib.request
    import urllib.parse
    import json

    encoded = urllib.parse.quote(article_title.replace(" ", "_"), safe="")
    url = f"https://en.wikipedia.org/w/api.php?action=parse&page={encoded}&prop=text&format=json&formatversion=2"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            html = data.get("parse", {}).get("text", "")
    except Exception:
        TEMPLATE_CACHE[article_title] = []
        return []

    found = []
    html_lower = html.lower()
    for canonical, patterns in MAINTENANCE_TEMPLATES.items():
        for p in patterns:
            if p.lower() in html_lower:
                found.append(canonical)
                break  # Only count once per canonical type

    TEMPLATE_CACHE[article_title] = found
    return found


def detect_templates_batch(article_titles: list) -> dict:
    """Batch-fetch templates for multiple articles."""
    import urllib.request
    import urllib.parse
    import json

    results = {}
    for i in range(0, len(article_titles), 50):
        batch = article_titles[i:i+50]
        titles = "|".join(
            urllib.parse.quote(t.replace(" ", "_"), safe="")
            for t in batch
        )
        url = (
            f"https://en.wikipedia.org/w/api.php?action=query"
            f"&titles={urllib.parse.quote(titles, safe='|')}"
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
                    revs = page.get("revisions", [])
                    wikitext = revs[0].get("slots", {}).get("main", {}).get("content", "") if revs else ""
                    # Detect templates in wikitext directly
                    found = []
                    wt_lower = wikitext.lower()
                    for canonical, patterns in MAINTENANCE_TEMPLATES.items():
                        for p in patterns:
                            if p.lower() in wt_lower:
                                found.append(canonical)
                                break
                    results[title] = found
                    TEMPLATE_CACHE[title] = found
        except Exception:
            for t in batch:
                results[t] = []
                TEMPLATE_CACHE[t] = []

    return results


# ─── Asset note generation ─────────────────────────────────────────────────

def load_asset_notes():
    """
    Build {course_id_lower: human_readable_note} from asset_counts.
    E.g., '5.111sc' → 'lecture notes, problem sets, and videos'
    """
    courses_dir = os.path.join(os.path.dirname(SCRIPTS_DIR), "wiki", "courses")
    notes = {}
    if not os.path.isdir(courses_dir):
        return notes

    for filename in os.listdir(courses_dir):
        if not filename.endswith(".md"):
            continue
        fpath = os.path.join(courses_dir, filename)
        try:
            with open(fpath) as f:
                content = f.read(4096)

            cid_match = re.search(r'^course_id:\s*"([^"]+)"', content, re.MULTILINE)
            ac_match = re.search(r'^asset_counts:\s*"(.+?)"', content, re.MULTILINE)

            if cid_match and ac_match:
                cid = cid_match.group(1)
                counts = ac_match.group(1)

                # Parse asset types with counts > 0
                # Skip problem sets — not useful for Wikipedia editors
                SKIP_TYPES = {"problem set", "problem sets", "assignment", "assignments"}
                types = []
                for part in counts.split(","):
                    part = part.strip()
                    if ":" in part:
                        k, v = part.split(":", 1)
                        k = k.strip().replace("-", " ").lower()
                        if k in SKIP_TYPES:
                            continue
                        try:
                            if int(v.strip()) > 0:
                                if k in ("reading list", "resource", "syllabus"):
                                    types.append(k + "s" if not k.endswith("s") else k)
                                elif k == "lecture notes":
                                    types.append("lecture notes")
                                elif k == "video transcript":
                                    types.append("video lectures")
                                else:
                                    types.append(k)
                        except ValueError:
                            pass

                if types:
                    if len(types) == 1:
                        notes[cid.lower()] = types[0]
                    elif len(types) == 2:
                        notes[cid.lower()] = f"{types[0]} and {types[1]}"
                    else:
                        notes[cid.lower()] = f"{', '.join(types[:-1])}, and {types[-1]}"
        except Exception:
            continue

    return notes


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

def _build_note(lecture: str, asset_note: str) -> str:
    """Build a descriptive note for the refideas entry."""
    if lecture:
        return f"lecture: {lecture}"
    if asset_note:
        return f"includes {asset_note}"
    return ""


def _is_mit_article(title: str) -> bool:
    """Check if an article is about MIT itself — circular to suggest MIT OCW."""
    lower = title.lower()
    mit_patterns = [
        "massachusetts institute of technology",
        "mit school of", "mit department of", "mit faculty of",
        "mit center for", "mit laboratory", "mit lab",
        "mit program in", "mit office of",
        "history of mit", "campus of mit",
    ]
    for p in mit_patterns:
        if p in lower:
            return True
    # Also check: title starts with "MIT " followed by a non-trivial word
    if lower.startswith("mit ") and len(title) > 10:
        return True
    return False


def _is_low_value_article(title: str) -> bool:
    """
    Filter out articles where OCW references add little value:
    - Navigation pages (lists, glossaries, outlines, indices)
    - Overly broad single-word topics ("Chemistry", "Physics")
    - Articles about education/pedagogy, not the subject itself
    """
    lower = title.lower()

    # Navigation pages
    nav_prefixes = ("list of", "glossary of", "glossary", "outline of",
                    "index of", "timeline of")
    if lower.startswith(nav_prefixes):
        return True

    # Overly broad single-word articles
    if " " not in title and "(" not in title and len(title) > 3:
        return True

    # Education-topic articles (about teaching, not the subject)
    if lower.endswith(" education") and lower != "education":
        return True
    if lower in ("education sciences", "pedagogy"):
        return True

    # Articles about specific named institutions (other universities, schools, institutes)
    # "Kellogg School of Management" is about the school, not management itself
    institution_patterns = (
        " school of ", " college of ", " institute of ",
        " academy of ", " university of ", " university",
        " graduate school", " polytechnic",
    )
    for pat in institution_patterns:
        if pat in lower:
            return True

    # Specific well-known universities (avoid matching on generic words)
    known_universities = (
        "harvard", "stanford", "yale", "princeton", "oxford", "cambridge",
        "columbia university", "berkeley", "caltech",
    )
    for uni in known_universities:
        if uni in lower:
            return True

    # MOOC platforms — circular for OCW
    mooc_patterns = ("edx", "mitx", "coursera", "open courseware", "mooc")
    for pat in mooc_patterns:
        if pat in lower:
            return True

    return False


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

def score_all_matches(demo_data: dict, course_urls: dict, lecture_titles: dict, asset_notes: dict = None, use_live_templates: bool = True) -> list:
    """Score all matches across all WikiProjects. Returns sorted list of match dicts."""
    results = []
    if asset_notes is None:
        asset_notes = {}

    # Collect unique article titles for batch template detection
    all_articles = set()
    for project, data in demo_data.items():
        for article in data.get("articles", []):
            all_articles.add(article["title"])

    # Fetch live templates if requested
    if use_live_templates:
        print(f"  Detecting maintenance templates on {len(all_articles)} articles...", file=sys.stderr)
        detect_templates_batch(list(all_articles))
        print(f"  Found templates on {sum(1 for v in TEMPLATE_CACHE.values() if v)} articles", file=sys.stderr)

    for project, data in demo_data.items():
        for article in data.get("articles", []):
            article_title = article["title"]

            # Skip MIT-internal articles — circular to suggest MIT OCW for MIT departments
            if _is_mit_article(article_title):
                continue
            # Skip low-value articles — navigation pages, overly broad topics, education meta
            if _is_low_value_article(article_title):
                continue
            # Use live template data, fall back to demo estimate
            templates = TEMPLATE_CACHE.get(article_title, article.get("templates", []))
            quality = article.get("quality", "?")
            importance = article.get("importance", "?")
            views = article.get("views", 0)

            for match in article.get("ocw_matches", []):
                course_id = match["course"]
                course_title = match["title"]
                url = course_urls.get(course_id.lower(), "")

                if not url:
                    continue

                # Use REAL lecture titles from scanned data
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
                    scoring = score_match(article_title, templates, best_lecture)
                else:
                    # No scanned lectures — score overlap as 0, don't trust demo data
                    lecture = ""
                    scoring = score_match(article_title, templates, "")

                results.append({
                    "article": article_title,
                    "quality": quality,
                    "importance": importance,
                    "views": views,
                    "templates": templates,
                    "course_id": course_id,
                    "course_title": course_title,
                    "course_url": url,
                    "lecture": lecture if real_lectures else "[no titled lectures]",
                    "note": _build_note(lecture if real_lectures else "", asset_notes.get(course_id.lower(), "")),
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
        if lecture and not lecture.startswith("["):
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
            if lecture.startswith("["):
                print(f"  │     ⚠️  No lecture titles available for overlap scoring")
        elif lecture:
            print(f"  │")
            print(f"  │  🎓 Lecture match: {c('[no titled lectures — course has materials but no lecture breakdown]', Color.YELLOW)}")
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
    """Apply the top N eligible matches (batch mode — requires --yes)."""
    eligible = [r for r in results if r["eligible"]]
    if not eligible:
        print("No eligible matches to apply.")
        return

    to_apply = eligible[:n]
    print(f"\n  Applying top {len(to_apply)} matches...\n")

    script = os.path.join(SCRIPTS_DIR, "apply-l1-refideas.py")

    for i, r in enumerate(to_apply):
        note = r.get("note", "")
        print(f"  [{i+1}/{len(to_apply)}] {r['article']} ← {r['course_id']} (score: {r['score']})")

        cmd = [
            sys.executable, script,
            r["article"],
            "--course-id", r["course_id"],
            "--course-title", r["course_title"],
            "--course-url", r["course_url"],
            "--yes",
        ]
        if note:
            cmd.extend(["--note", note])

        result = subprocess.run(cmd, capture_output=True, text=True)
        stdout = result.stdout + result.stderr

        for line in stdout.splitlines():
            if any(kw in line for kw in ["✅ Refideas posted", "❌ Edit failed", "⏭"]):
                print(f"    {line.strip()}")
                break
        else:
            lines = [l for l in stdout.splitlines() if l.strip() and "Authenticated" not in l]
            if lines:
                print(f"    {lines[-1].strip()[:100]}")

        print()


def apply_interactive(results: list, top_n: int = 5):
    """
    Interactive mode: show verbose reasoning for each match,
    prompt [y/N/q], apply with confirmation.
    """
    eligible = [r for r in results if r["eligible"]]
    if not eligible:
        print("No eligible matches to review.")
        return

    auth = get_auth()
    if not auth:
        print(c("\n  ⚠️  No Wikipedia credentials found. Set WIKIPEDIA_USERNAME + WIKIPEDIA_BOT_PASSWORD in .env", Color.YELLOW))
        return

    to_show = eligible[:top_n]
    script = os.path.join(SCRIPTS_DIR, "apply-l1-refideas.py")

    for i, r in enumerate(to_show):
        # Show verbose reasoning for this single match
        print_verbose_single(r, i + 1)

        # Prompt
        try:
            response = input(c("  Post to Wikipedia? [y/N/q] ", Color.BOLD))
        except (EOFError, KeyboardInterrupt):
            print("\n  Cancelled.")
            return

        if response.lower() == "q":
            print(c("  Quit.", Color.YELLOW))
            return
        elif response.lower() not in ("y", "yes"):
            print(c("  Skipped.", Color.DIM))
            print()
            continue

        # Post it
        note = r.get("note", "")
        print(f"  Posting...")

        cmd = [
            sys.executable, script,
            r["article"],
            "--course-id", r["course_id"],
            "--course-title", r["course_title"],
            "--course-url", r["course_url"],
            "--yes",
        ]
        if note:
            cmd.extend(["--note", note])

        result = subprocess.run(cmd, capture_output=True, text=True)
        stdout = result.stdout + result.stderr

        for line in stdout.splitlines():
            if any(kw in line for kw in ["✅ Refideas posted", "❌ Edit failed", "⏭"]):
                print(f"  {line.strip()}")
                break
        else:
            lines = [l for l in stdout.splitlines() if l.strip() and "Authenticated" not in l]
            if lines:
                print(f"  {lines[-1].strip()[:100]}")
        print()


def print_verbose_single(r: dict, num: int):
    """Print verbose reasoning for a single match."""
    article = r["article"]
    course_id = r["course_id"]
    course_title = r["course_title"]
    lecture = r.get("lecture", "")
    templates = r["templates"]
    score = r["score"]
    t_score = r["template_score"]
    overlap = r["overlap"]
    spec = r["specificity"]
    views = r["views"]

    score_color = Color.GREEN if score >= 60 else Color.YELLOW if score >= 35 else Color.RED

    print(f"\n  {'='*68}")
    print(f"  ┌─ #{num}: {c(article, Color.BOLD)} ← {course_id} ({course_title})")
    print(f"  │  Score: {c(str(score), score_color)} / 100  |  {views:,} views/mo  |  {r['quality']}/{r['importance']}")
    print(f"  │")

    # Template gate
    if templates:
        template_names = ", ".join(f"{{{{{t}}}}}" for t in templates)
        print(f"  │  📋 Template gate: {c('PASS', Color.GREEN)}")
        print(f"  │     Found: {template_names}")
        print(f"  │     Urgency: {t_score}/35")

    # Lecture matching
    if lecture and not lecture.startswith("["):
        a_tokens = tokenize(article)
        l_tokens = tokenize(lecture)
        shared = a_tokens & l_tokens
        print(f"  │")
        print(f"  │  🎓 Best lecture: {c(lecture, Color.CYAN)}")
        print(f"  │     Article: {sorted(a_tokens)}")
        print(f"  │     Lecture: {sorted(l_tokens)}")
        if shared:
            print(f"  │     Shared:  {c(str(sorted(shared)), Color.GREEN)}")
        print(f"  │     Overlap: {overlap:.2f} → {overlap*35:.0f}/35")
    elif lecture:
        print(f"  │")
        print(f"  │  🎓 Lecture: {c('[no titled lectures]', Color.YELLOW)}")

    # Specificity
    words = article.split()
    print(f"  │")
    print(f"  │  📐 Specificity: {spec:.2f} → {spec*30:.0f}/30  (\"{article}\" — {len(words)} word{'s' if len(words) != 1 else ''})")

    # Formula
    print(f"  │")
    print(f"  │  🧮 {t_score:.0f} (templates) + {overlap*35:.0f} (overlap) + {spec*30:.0f} (specificity) = {c(str(score), score_color)}")

    if score >= 60:
        print(f"  │  {c('✅ Strong match', Color.GREEN)}")
    elif score >= 35:
        print(f"  │  {c('🟡 Moderate match', Color.YELLOW)}")
    else:
        print(f"  │  {c('🔴 Weak match', Color.RED)}")

    print(f"  └{'─'*66}")


# ─── CLI ────────────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]
    min_score = 0
    apply_n = 0
    interactive_n = 0
    auto_yes = False
    verbose = False
    data_file = None

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
        elif args[i] == "--interactive":
            i += 1
            if i < len(args) and args[i].isdigit():
                interactive_n = int(args[i])
            else:
                interactive_n = 5
                continue  # don't consume the next arg
        elif args[i] in ("--yes", "-y"):
            auto_yes = True
        elif args[i] in ("--verbose", "-v"):
            verbose = True
        elif args[i] == "--data":
            i += 1
            if i < len(args):
                data_file = args[i]
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

    print("  Loading asset notes from scanned courses...")
    asset_notes = load_asset_notes()
    print(f"  Found asset notes for {len(asset_notes)} courses")

    # Load match data — from --data JSON, or fall back to demo
    if data_file and os.path.exists(data_file):
        with open(data_file) as f:
            demo_data = json.loads(f.read())
        print(f"  Loaded match data from {data_file}")
    else:
        demo_data = _xref.DEMO_DATA

    project_count = len(demo_data)
    article_count = sum(len(v.get("articles", [])) for v in demo_data.values())
    print(f"  {article_count} articles across {project_count} WikiProjects")

    results = score_all_matches(demo_data, course_urls, lecture_titles, asset_notes)

    if interactive_n > 0:
        apply_interactive(results, interactive_n)
    elif apply_n > 0:
        if not auto_yes:
            print(f"\n  {c('ERROR: --apply-top requires --yes for batch mode.', Color.RED)}", file=sys.stderr)
            print(f"  Posts to Wikipedia need explicit confirmation. Add --yes to auto-apply.", file=sys.stderr)
            print(f"  Or use --interactive N to review each match before posting.", file=sys.stderr)
            sys.exit(1)
        apply_top(results, apply_n, auto_yes)
    else:
        print_ranked(results, min_score)
        if verbose:
            print_verbose(results)


if __name__ == "__main__":
    main()
