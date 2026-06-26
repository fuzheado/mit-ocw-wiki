#!/usr/bin/env python3
"""
generate-ocw-census.py — Sprint 1: OCW Link Census

Queries Wikipedia for all articles containing ocw.mit.edu links,
enriches with quality assessments and pageviews, outputs as
dashboard/ocw-census.js for the static HTML dashboard.

Usage:
    python3 dashboard/generate-ocw-census.py          # Full generation
    python3 dashboard/generate-ocw-census.py --limit 50  # Quick test
"""

import json
import sys
import time
import os
from urllib.parse import quote, urlencode
from collections import defaultdict

import requests

# ─── Config ────────────────────────────────────────────────────────────────

USER_AGENT = "Wiki MIT Dashboard/1.0 (https://meta.wikimedia.org/wiki/Wiki_MIT; andrew.lih@gmail.com)"

API_BASE = "https://en.wikipedia.org/w/api.php"
PAGEVIEWS_BASE = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article"

OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "ocw-census.js")

# WikiProjects aligned with MIT OCW (from docs/crossref-strategy.md)
MIT_WIKIPROJECTS = [
    "Physics", "Chemistry", "Mathematics", "Computer science",
    "Engineering", "Biology", "Economics", "Environment",
    "Electrical engineering", "Mechanical engineering", "Civil engineering",
    "Chemical and Bio engineering", "Materials science", "Nuclear technology",
    "Astronomy", "Earth sciences", "Energy", "Architecture",
    "Linguistics", "Philosophy", "Political science", "History",
    "Media", "Music", "Business",
]

# ─── API Helpers ───────────────────────────────────────────────────────────

session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT})

def api_call(params, retries=3):
    """Make a Wikipedia API call with retry on 429."""
    for attempt in range(retries):
        resp = session.get(API_BASE, params=params, timeout=30)
        if resp.status_code == 429:
            time.sleep(2 ** attempt)
            continue
        resp.raise_for_status()
        return resp.json()
    raise RuntimeError("API rate limit exceeded after retries")

def search_ocw_articles(limit=None):
    """Find all articles with ocw.mit.edu in wikitext using CirrusSearch."""
    articles = []
    sroffset = 0
    batch_size = 50

    while True:
        if limit and sroffset >= limit:
            break

        params = {
            "action": "query",
            "list": "search",
            "srsearch": "insource:ocw.mit.edu",
            "srlimit": min(batch_size, limit - sroffset) if limit else batch_size,
            "sroffset": sroffset,
            "srprop": "size|wordcount|timestamp|snippet",
            "format": "json",
        }

        data = api_call(params)
        results = data.get("query", {}).get("search", [])
        total = data.get("query", {}).get("searchinfo", {}).get("totalhits", 0)

        for r in results:
            articles.append({
                "title": r["title"],
                "size": r.get("size", 0),
                "wordcount": r.get("wordcount", 0),
                "timestamp": r.get("timestamp", ""),
                "snippet": r.get("snippet", ""),
            })

        sroffset += len(results)
        print(f"  Fetched {sroffset}/{total} articles...", file=sys.stderr)

        if len(results) < batch_size:
            break

        time.sleep(0.3)  # Rate limit courtesy

    print(f"  Total articles with OCW links: {len(articles)}", file=sys.stderr)
    return articles

def batch_page_assessments(titles):
    """Fetch quality and WikiProject assessments for a list of articles."""
    # Returns: {title: {"quality": "C", "importance": "High", "projects": ["Physics", ...]}}
    results = {}
    batch_size = 50

    for i in range(0, len(titles), batch_size):
        batch = titles[i:i + batch_size]
        params = {
            "action": "query",
            "prop": "pageassessments",
            "titles": "|".join(batch),
            "format": "json",
        }

        try:
            data = api_call(params)
            pages = data.get("query", {}).get("pages", {})

            for page_id, page_data in pages.items():
                title = page_data.get("title", "")
                if not title:
                    continue

                assessments = page_data.get("pageassessments", {})
                quality = "?"
                importance = "?"
                projects = []

                # pageassessments is a dict: {"ProjectName": {"class": "C", "importance": "Top"}, ...}
                for proj_name, proj_data in assessments.items():
                    if not isinstance(proj_data, dict):
                        continue
                    cls = proj_data.get("class", "")
                    imp = proj_data.get("importance", "")

                    if cls and cls != "?":
                        quality = cls
                    if imp and imp != "?":
                        importance = imp
                    projects.append(proj_name)

                results[title] = {
                    "quality": quality,
                    "importance": importance,
                    "projects": projects,
                }

        except Exception as e:
            print(f"  Assessment fetch error: {e}", file=sys.stderr)

        time.sleep(0.2)

    return results

def batch_pageviews(titles, start="20260501", end="20260601"):
    """Fetch monthly pageviews for a list of articles."""
    results = {}

    for title in titles:
        safe_title = quote(title.replace(" ", "_"), safe="")
        url = f"{PAGEVIEWS_BASE}/en.wikipedia/all-access/all-agents/{safe_title}/monthly/{start}/{end}"

        try:
            resp = session.get(url, timeout=10)
            if resp.status_code == 200:
                items = resp.json().get("items", [])
                total_views = sum(item.get("views", 0) for item in items)
                results[title] = total_views
            elif resp.status_code == 404:
                results[title] = 0
        except Exception:
            results[title] = 0

        # Rate limit: 100 req/s is allowed, but be gentle
        if len(results) % 50 == 0:
            print(f"  Pageviews: {len(results)}/{len(titles)}...", file=sys.stderr)

    return results

def classify_by_project(articles, mit_projects):
    """Group articles by which MIT-aligned WikiProject they belong to."""
    by_project = defaultdict(list)
    unclassified = []

    for article in articles:
        projects = article.get("projects", [])
        matched = False
        for proj in projects:
            for mit_proj in mit_projects:
                if mit_proj.lower() in proj.lower():
                    by_project[proj].append(article)
                    matched = True
                    break
            if matched:
                break
        if not matched:
            unclassified.append(article)

    return dict(by_project), unclassified

# ─── Main ──────────────────────────────────────────────────────────────────

def main():
    limit = None
    if len(sys.argv) > 2 and sys.argv[1] == "--limit":
        limit = int(sys.argv[2])

    print("=== OCW Link Census ===", file=sys.stderr)
    print("Phase 1: Finding articles with ocw.mit.edu links...", file=sys.stderr)

    articles = search_ocw_articles(limit=limit)
    titles = [a["title"] for a in articles]

    print(f"\nPhase 2: Fetching quality assessments for {len(titles)} articles...", file=sys.stderr)
    assessments = batch_page_assessments(titles)

    # Merge assessments into articles
    quality_counts = defaultdict(int)
    for article in articles:
        a = assessments.get(article["title"], {})
        article["quality"] = a.get("quality", "?")
        article["importance"] = a.get("importance", "?")
        article["projects"] = a.get("projects", [])
        quality_counts[article["quality"]] += 1

    print(f"  Quality distribution: {dict(quality_counts)}", file=sys.stderr)

    print(f"\nPhase 3: Fetching pageviews for {len(titles)} articles...", file=sys.stderr)
    pageviews = batch_pageviews(titles)

    for article in articles:
        article["views"] = pageviews.get(article["title"], 0)

    total_views = sum(a["views"] for a in articles)
    print(f"  Total monthly views: {total_views:,}", file=sys.stderr)

    print(f"\nPhase 4: Classifying by WikiProject...", file=sys.stderr)
    by_project, unclassified = classify_by_project(articles, MIT_WIKIPROJECTS)
    print(f"  Classified into {len(by_project)} WikiProjects, {len(unclassified)} unclassified", file=sys.stderr)

    # ─── Build output ──────────────────────────────────────────────────

    # Sort by quality order
    quality_order = {"FA": 0, "GA": 1, "B": 2, "C": 3, "Start": 4, "Stub": 5, "?": 6}

    output = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_articles": len(articles),
        "total_pageviews": total_views,
        "quality_distribution": dict(sorted(quality_counts.items(), key=lambda x: quality_order.get(x[0], 99))),
        "articles": sorted(articles, key=lambda a: (-a.get("views", 0), quality_order.get(a.get("quality", "?"), 99), a["title"])),
        "by_project": {
            proj: {
                "count": len(items),
                "total_views": sum(a.get("views", 0) for a in items),
                "qualities": dict(sorted(
                    defaultdict(int, {a["quality"]: sum(1 for x in items if x["quality"] == a["quality"]) for a in items}).items(),
                    key=lambda x: quality_order.get(x[0], 99)
                )),
            }
            for proj, items in sorted(by_project.items(), key=lambda x: -len(x[1]))
        },
        "unclassified_count": len(unclassified),
        "mit_wikiprojects_used": MIT_WIKIPROJECTS,
    }

    # Write as JS variable assignment
    js_content = f"// OCW Link Census — generated {output['generated']}\n"
    js_content += f"// {output['total_articles']} articles, {output['total_pageviews']:,} monthly views\n"
    js_content += f"var OCW_CENSUS = {json.dumps(output, indent=2, ensure_ascii=False)};\n"

    with open(OUTPUT_FILE, "w") as f:
        f.write(js_content)

    print(f"\n✅ Written to {OUTPUT_FILE}", file=sys.stderr)
    print(f"   {len(output['articles'])} articles, {len(output['by_project'])} WikiProjects", file=sys.stderr)
    print(f"   {output['total_pageviews']:,} monthly pageviews", file=sys.stderr)

    # Print top 10 WikiProjects by article count
    print(f"\n   Top WikiProjects:", file=sys.stderr)
    for proj, data in list(output["by_project"].items())[:10]:
        print(f"     {proj}: {data['count']} articles, {data['total_views']:,} views", file=sys.stderr)


if __name__ == "__main__":
    main()
