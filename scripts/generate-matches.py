#!/usr/bin/env python3
"""
Generate live match data for all 25 WikiProjects in the crossref strategy.

For each WikiProject:
1. Search Wikipedia for articles in that topic area
2. Batch-check for maintenance templates
3. Cross-reference with OCW courses in matching departments
4. Output match data for prioritize-matches.py

Usage:
    python3 scripts/generate-matches.py                    # Generate for all 25 projects
    python3 scripts/generate-matches.py --top 30           # 30 articles per project
    python3 scripts/generate-matches.py --output matches.json
    python3 scripts/generate-matches.py --project Chemistry  # Single project
"""

import os
import sys
import json
import re
import time
import urllib.request
import urllib.parse

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPTS_DIR)

import importlib.util
_xref_spec = importlib.util.spec_from_file_location(
    "xref", os.path.join(SCRIPTS_DIR, "crossref-wikipedia.py")
)
_xref = importlib.util.module_from_spec(_xref_spec)
_xref_spec.loader.exec_module(_xref)

UA = "MIT OCW Bot/1.0 (https://meta.wikimedia.org/wiki/Wiki_MIT; andrew.lih@gmail.com) ContentGapResearch"
API = "https://en.wikipedia.org/w/api.php"

TEMPLATE_PATTERNS = [
    "citation needed", "cn|", "more citations needed", "refimprove",
    "unreferenced", "missing information", "update", "primary sources",
    "third-party", "expand section", "tone",
]

STOP_WORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "was", "are", "be", "been",
    "its", "it", "this", "that", "these", "those",
}

# WikiProject → search query (more specific than just the project name)
PROJECT_SEARCH = {
    "Environment": "environmental science OR climate change OR ecology OR conservation",
    "Chemistry": "chemistry OR chemical compound OR chemical reaction",
    "Physics": "physics OR quantum mechanics OR thermodynamics",
    "Biology": "biology OR genetics OR cell biology OR molecular biology",
    "History": "history",
    "Nuclear technology": "nuclear reactor OR nuclear weapon OR nuclear power",
    "Energy": "energy OR renewable energy OR power generation",
    "Architecture": "architecture OR building design OR urban planning",
    "Music": "music theory OR musical composition OR musicology",
    "Earth Science": "geology OR oceanography OR meteorology OR earth science",
    "Computer science": "algorithm OR programming OR computer science OR machine learning",
    "Business": "management OR marketing OR finance OR business",
    "Aviation": "aviation OR aircraft OR aeronautics",
    "Aerospace": "aerospace OR spacecraft OR rocketry",
    "Anthropology": "anthropology OR archaeology OR cultural studies",
    "Philosophy": "philosophy OR ethics OR metaphysics",
    "Education": "education OR pedagogy OR learning theory",
    "Media": "mass media OR journalism OR broadcasting",
    "Gender studies": "gender studies OR feminism OR queer theory",
    "Linguistics": "linguistics OR language OR syntax OR phonology",
    "Engineering": "engineering OR mechanical engineering OR electrical engineering",
    "Mathematics": "mathematics OR algebra OR calculus OR geometry",
    "Economics": "economics OR economic theory OR macroeconomics",
    "Political science": "political science OR international relations OR government",
    "Medicine": "medicine OR disease OR anatomy OR pharmacology",
}


def tokenize(text):
    tokens = re.findall(r"[a-zA-Z0-9]{2,}", text.lower())
    return {t for t in tokens if t not in STOP_WORDS}


def _is_mit_article(title: str) -> bool:
    """Check if an article is about MIT itself — circular to suggest MIT OCW."""
    lower = title.lower()
    patterns = [
        "massachusetts institute of technology",
        "mit school of", "mit department of", "mit faculty of",
        "mit center for", "mit laboratory", "mit lab",
        "mit program in", "mit office of",
        "history of mit", "campus of mit",
    ]
    for p in patterns:
        if p in lower:
            return True
    if lower.startswith("mit ") and len(title) > 10:
        return True
    return False


def _is_low_value_article(title: str) -> bool:
    """Filter navigation pages, overly broad topics, education meta-articles."""
    lower = title.lower()
    nav_prefixes = ("list of", "glossary of", "glossary", "outline of",
                    "index of", "timeline of")
    if lower.startswith(nav_prefixes):
        return True
    if " " not in title and "(" not in title and len(title) > 3:
        return True
    if lower.endswith(" education") and lower != "education":
        return True
    return False


def search_articles(query: str, limit: int = 50) -> list:
    """Search Wikipedia for articles matching a topic query."""
    encoded = urllib.parse.quote(query)
    url = f"{API}?action=query&list=search&srsearch={encoded}&srlimit={min(limit, 50)}&format=json&formatversion=2"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            return [r["title"] for r in data.get("query", {}).get("search", [])]
    except Exception as e:
        print(f"  ⚠️  Search error: {e}", file=sys.stderr)
        return []


def detect_templates_batch(articles: list) -> dict:
    """Batch check articles for maintenance templates. Returns {title: [template_names]}."""
    results = {}
    for i in range(0, len(articles), 50):
        batch = articles[i:i+50]
        titles = "|".join(
            urllib.parse.quote(t.replace(" ", "_"), safe="")
            for t in batch
        )
        url = (
            f"{API}?action=query"
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
                    wt_lower = wikitext.lower()
                    found = []
                    for tmpl in TEMPLATE_PATTERNS:
                        if tmpl in wt_lower:
                            clean = tmpl.replace("|", "")
                            if clean not in found:
                                found.append(clean)
                    results[title] = found
        except Exception as e:
            for t in batch:
                results[t] = []
        time.sleep(0.3)
    return results


def load_course_data() -> dict:
    """
    Build {department_code: [(course_id, title, url, keywords), ...]}
    from wiki/courses/.
    """
    courses_dir = os.path.join(os.path.dirname(SCRIPTS_DIR), "wiki", "courses")
    dept_courses = {}

    for fname in os.listdir(courses_dir):
        if not fname.endswith(".md"):
            continue
        fpath = os.path.join(courses_dir, fname)
        try:
            with open(fpath) as f:
                content = f.read()

            cid = title = url = dept = None
            in_fm = False
            body = ""

            for line in content.splitlines():
                if line == "---":
                    if not in_fm:
                        in_fm = True
                        continue
                    else:
                        break
                if in_fm:
                    if line.startswith("course_id:"):
                        cid = line.split(":", 1)[1].strip().strip('"')
                    elif line.startswith("title:"):
                        title = line.split(":", 1)[1].strip().strip('"')
                    elif line.startswith("url:"):
                        url = line.split(":", 1)[1].strip().strip('"')
                    elif line.startswith("department:"):
                        dept = line.split(":", 1)[1].strip().strip('"')
                else:
                    body += line + " "

            if not (cid and title and url and dept):
                continue

            keywords = tokenize(title + " " + body)
            dept_courses.setdefault(dept, []).append((cid, title, url, keywords))
        except Exception:
            continue

    return dept_courses


def match_article(article_title: str, dept_courses: dict, dept_codes: list) -> list:
    """Find best-matching OCW courses for an article."""
    article_tokens = tokenize(article_title)
    matches = []

    for dept in dept_codes:
        if dept not in dept_courses:
            continue
        for cid, ctitle, curl, keywords in dept_courses[dept]:
            overlap = article_tokens & keywords
            if overlap:
                score = len(overlap) / max(len(article_tokens | keywords), 1)
                if score > 0.05:  # Minimum threshold
                    matches.append({
                        "course": cid,
                        "title": ctitle,
                        "url": curl,
                        "score": round(score, 3),
                    })

    matches.sort(key=lambda m: m["score"], reverse=True)
    # Deduplicate by course_id
    seen = set()
    unique = []
    for m in matches:
        if m["course"] not in seen:
            seen.add(m["course"])
            unique.append(m)
    return unique[:3]


def generate(projects: list = None, articles_per_project: int = 50) -> dict:
    """Generate match data for specified WikiProjects (or all 25)."""
    project_map = _xref.WIKIPROJECT_DEPT_MAP
    dept_courses = load_course_data()
    print(f"  Loaded courses across {len(dept_courses)} departments", file=sys.stderr)

    to_process = projects if projects else sorted(project_map.keys())
    output = {}

    for i, project in enumerate(to_process):
        if project not in project_map:
            print(f"  ⚠️  Unknown project: {project}", file=sys.stderr)
            continue

        dept_codes = project_map[project]
        query = PROJECT_SEARCH.get(project, project)
        print(f"  [{i+1}/{len(to_process)}] {project} — searching...", file=sys.stderr)

        articles = search_articles(query, articles_per_project)
        if not articles:
            continue
        print(f"    {len(articles)} search results", file=sys.stderr)

        templates = detect_templates_batch(articles)
        with_t = {t: tm for t, tm in templates.items() if tm}
        print(f"    {len(with_t)} have templates", file=sys.stderr)

        if not with_t:
            continue

        article_matches = []
        for article, tmpls in sorted(with_t.items()):
            # Skip MIT-internal articles
            if _is_mit_article(article):
                continue
            # Skip low-value articles
            if _is_low_value_article(article):
                continue
            matches = match_article(article, dept_courses, dept_codes)
            if matches:
                article_matches.append({
                    "title": article,
                    "templates": tmpls,
                    "ocw_matches": [
                        {"course": m["course"], "title": m["title"],
                         "lecture": "", "assets": ""}
                        for m in matches
                    ],
                    "quality": "?",
                    "importance": "?",
                    "views": 0,
                })

        print(f"    {len(article_matches)} matched to OCW courses", file=sys.stderr)
        if article_matches:
            output[project] = {"articles": article_matches}

        time.sleep(0.5)

    return output


def main():
    top_n = 50
    output_file = None
    single_project = None

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--top":
            i += 1
            if i < len(args):
                top_n = int(args[i])
        elif args[i] == "--output":
            i += 1
            if i < len(args):
                output_file = args[i]
        elif args[i] == "--project":
            i += 1
            if i < len(args):
                single_project = args[i]
        i += 1

    projects = [single_project] if single_project else None
    print(f"  Generating matches (top {top_n} per project)...")
    data = generate(projects, top_n)

    total = sum(len(v["articles"]) for v in data.values())
    print(f"\n  Done: {total} articles across {len(data)} WikiProjects")

    if output_file:
        with open(output_file, "w") as f:
            json.dump(data, f, indent=2)
        print(f"  Saved to {output_file}")
    else:
        # Print compact summary
        for proj in sorted(data):
            arts = data[proj]["articles"]
            print(f"\n  {proj} ({len(arts)}):")
            for a in arts[:5]:
                courses = ", ".join(m["course"] for m in a["ocw_matches"])
                print(f"    {a['title'][:50]:<50} [{', '.join(a['templates'][:2])}] → {courses}")
            if len(arts) > 5:
                print(f"    ... and {len(arts) - 5} more")


if __name__ == "__main__":
    main()
