#!/usr/bin/env python3
"""
Wikipedia cross-reference tool for OCW courses.

Two modes:
  --report --demo    Generate demo reports from hardcoded WikiProject data
  --report           Generate reports from live SQL (requires SSH tunnel + credentials)
  --apply            Apply approved matches to individual course pages

Usage:
    python3 scripts/crossref-wikipedia.py --report --demo
    python3 scripts/crossref-wikipedia.py --report --demo --top 50
    python3 scripts/crossref-wikipedia.py --report --project Chemistry
    python3 scripts/crossref-wikipedia.py --apply --project Chemistry
"""

import json, re, sys, os
from datetime import datetime
from pathlib import Path

WIKI_DIR = Path(__file__).resolve().parent.parent / "wiki"
REPORT_DIR = WIKI_DIR / "reports"
CROSSREF_DIR = WIKI_DIR / "crossrefs"

# Department code to name lookup
DEPT_NAMES = {
    "1": "Civil & Env. Eng.", "2": "Mechanical Eng.", "3": "Materials Sci.",
    "4": "Architecture", "5": "Chemistry", "6": "EECS",
    "7": "Biology", "8": "Physics", "9": "Brain & Cog. Sci.",
    "10": "Chemical Eng.", "11": "Urban Studies", "12": "Earth, Atmos. & Planetary Sci.",
    "14": "Economics", "15": "Management", "16": "Aero/Astro",
    "17": "Political Sci.", "18": "Mathematics", "20": "Biological Eng.",
    "21H": "History", "21L": "Literature", "21M": "Music",
    "22": "Nuclear Sci. & Eng.", "24": "Linguistics & Philosophy",
    "STS": "STS", "HST": "Health Sci. & Tech.", "CC": "Concourse",
    "ES": "Experimental Study", "CMS": "CMS", "WGS": "Women's Studies",
    "EC": "Edgerton Center", "MAS": "Media Arts & Sci.",
    "IDS": "Data, Systems & Society", "PE": "Athletics",
    "RES": "Supplemental Resources", "ESD": "Eng. Systems Division",
    "SP": "Special Programs",
}

# WikiProject name → OCW departments that align with it
WIKIPROJECT_DEPT_MAP = {
    "Environment": ["1", "2", "5", "7", "10", "11", "12", "22", "STS", "EC", "ESD"],
    "Chemistry": ["5", "3", "7", "10", "20"],
    "Physics": ["8", "6", "22"],
    "Biology": ["7", "20", "9", "HST"],
    "History": ["21H", "21L", "STS", "17"],
    "Nuclear technology": ["22", "STS"],
    "Energy": ["2", "22", "10", "5", "ESD", "IDS"],
    "Architecture": ["4", "11"],
    "Music": ["21M"],
    "Earth Science": ["12", "1", "ESD"],
}
# Source: Wikipedia WikiProject Environment Popular pages (April 2026)
# OCW course data from hybrid scans

DEMO_DATA = {
    "Environment": {
        "articles": [
            {
                "title": "Earth Day",
                "views": 291552,
                "quality": "C",
                "importance": "High",
                "templates": ["More citations needed"],
                "ocw_matches": [
                    {"course": "11.165", "title": "Infrastructure and Energy Technology Challenges", "lecture": "Energy policy discussions", "assets": "reading-list"},
                    {"course": "11.941", "title": "Urban Climate Adaptation", "lecture": "Climate adaptation policy", "assets": "lecture-notes"},
                ]
            },
            {
                "title": "Nuclear weapon",
                "views": 95651,
                "quality": "C",
                "importance": "High",
                "templates": ["Citation needed", "More citations needed"],
                "ocw_matches": [
                    {"course": "22.01", "title": "Introduction to Nuclear Engineering", "lecture": "Nuclear weapons overview", "assets": "video+transcript"},
                    {"course": "22.033", "title": "Nuclear Systems Design Project", "lecture": "Nuclear fuel cycle", "assets": "lecture-notes"},
                    {"course": "STS.038", "title": "Energy and Environment in American History", "lecture": "Manhattan Project history", "assets": "reading-list"},
                ]
            },
            {
                "title": "Petroleum",
                "views": 75490,
                "quality": "C",
                "importance": "High",
                "templates": ["Refimprove"],
                "ocw_matches": [
                    {"course": "22.081J", "title": "Introduction to Sustainable Energy", "lecture": "Fossil fuels", "assets": "video+transcript"},
                    {"course": "2.61", "title": "Internal Combustion Engines", "lecture": "Petroleum fuels", "assets": "lecture-notes"},
                    {"course": "12.340", "title": "Global Warming Science", "lecture": "Carbon cycle", "assets": "video+transcript"},
                ]
            },
            {
                "title": "El Niño–Southern Oscillation",
                "views": 74966,
                "quality": "C",
                "importance": "High",
                "templates": ["Missing information"],
                "ocw_matches": [
                    {"course": "12.800", "title": "Fluid Dynamics of the Atmosphere and Ocean", "lecture": "ENSO dynamics", "assets": "lecture-notes"},
                    {"course": "12.307", "title": "Weather and Climate Laboratory", "lecture": "Climate oscillations", "assets": "video+transcript"},
                ]
            },
            {
                "title": "Deepwater Horizon oil spill",
                "views": 65507,
                "quality": "C",
                "importance": "High",
                "templates": ["Missing information"],
                "ocw_matches": [
                    {"course": "1.74", "title": "Land, Water, Food, and Climate", "lecture": "Environmental disasters", "assets": "lecture-notes"},
                    {"course": "1.85", "title": "Water and Wastewater Treatment Engineering", "lecture": "Water contamination", "assets": "lecture-notes"},
                ]
            },
            {
                "title": "Carbon dioxide",
                "views": 37300,
                "quality": "C",
                "importance": "High",
                "templates": ["Refimprove"],
                "ocw_matches": [
                    {"course": "5.111SC", "title": "Principles of Chemical Science", "lecture": "Greenhouse gases", "assets": "video+transcript"},
                    {"course": "12.340", "title": "Global Warming Science", "lecture": "CO2 and climate", "assets": "video+transcript"},
                    {"course": "1.74", "title": "Land, Water, Food, and Climate", "lecture": "Carbon cycle", "assets": "lecture-notes"},
                ]
            },
            {
                "title": "Breeder reactor",
                "views": 36482,
                "quality": "C",
                "importance": "Low",
                "templates": ["Refimprove"],
                "ocw_matches": [
                    {"course": "22.01", "title": "Introduction to Nuclear Engineering", "lecture": "Reactor types", "assets": "video+transcript"},
                    {"course": "22.033", "title": "Nuclear Systems Design Project", "lecture": "Advanced reactors", "assets": "lecture-notes"},
                ]
            },
            {
                "title": "Chernobyl exclusion zone",
                "views": 48144,
                "quality": "C",
                "importance": "High",
                "templates": ["Citation needed"],
                "ocw_matches": [
                    {"course": "22.091", "title": "Nuclear Reactor Safety", "lecture": "Chernobyl case study", "assets": "video+transcript"},
                    {"course": "22.033", "title": "Nuclear Systems Design Project", "lecture": "Containment", "assets": "lecture-notes"},
                ]
            },
            {
                "title": "Extinction",
                "views": 39794,
                "quality": "C",
                "importance": "High",
                "templates": ["Refimprove"],
                "ocw_matches": [
                    {"course": "1.018J", "title": "Ecology I: The Earth System", "lecture": "Biodiversity", "assets": "lecture-notes"},
                    {"course": "7.016", "title": "Introductory Biology", "lecture": "Evolution", "assets": "video+transcript"},
                ]
            },
            {
                "title": "Prisoner's dilemma",
                "views": 39225,
                "quality": "C",
                "importance": "High",
                "templates": ["Refimprove"],
                "ocw_matches": [
                    {"course": "14.12", "title": "Economic Applications of Game Theory", "lecture": "Prisoner's dilemma", "assets": "video+transcript"},
                ]
            },
            {
                "title": "Atmosphere of Earth",
                "views": 58418,
                "quality": "B",
                "importance": "High",
                "templates": [],
                "ocw_matches": [
                    {"course": "12.810", "title": "Dynamics of the Atmosphere", "lecture": "Atmospheric structure", "assets": "video+transcript"},
                ]
            },
            {
                "title": "Climate change",
                "views": 70965,
                "quality": "FA",
                "importance": "Top",
                "templates": [],
                "ocw_matches": []
            },
        ],
        "total_views": 21793841,
        "period": "2026-04-01 to 2026-04-30"
    },
    "Chemistry": {
        "articles": [
            {
                "title": "Chemical bond",
                "views": 85000,
                "quality": "C",
                "importance": "High",
                "templates": ["Refimprove"],
                "ocw_matches": [
                    {"course": "5.111SC", "title": "Principles of Chemical Science", "lecture": "Chemical bonding overview", "assets": "video+transcript"},
                    {"course": "5.112", "title": "Principles of Chemical Science", "lecture": "Ionic and covalent bonds", "assets": "lecture-notes"},
                ]
            },
            {
                "title": "Electron configuration",
                "views": 42000,
                "quality": "Start",
                "importance": "High",
                "templates": ["Missing information"],
                "ocw_matches": [
                    {"course": "5.111SC", "title": "Principles of Chemical Science", "lecture": "Electron configurations", "assets": "video+transcript"},
                ]
            },
            {
                "title": "VSEPR theory",
                "views": 32000,
                "quality": "C",
                "importance": "Mid",
                "templates": ["Image requested"],
                "ocw_matches": [
                    {"course": "5.111SC", "title": "Principles of Chemical Science", "lecture": "Molecular shapes", "assets": "video+transcript"},
                ]
            },
        ],
        "total_views": 2100000,
        "period": "2026-04-01 to 2026-04-30"
    },
    "Biology": {
        "articles": [
            {
                "title": "Evolution",
                "views": 120000,
                "quality": "GA",
                "importance": "Top",
                "templates": [],
                "ocw_matches": []
            },
            {
                "title": "Cell (biology)",
                "views": 95000,
                "quality": "C",
                "importance": "High",
                "templates": ["Refimprove"],
                "ocw_matches": [
                    {"course": "7.016", "title": "Introductory Biology", "lecture": "Cell structure", "assets": "video+transcript"},
                    {"course": "7.012", "title": "Introductory Biology", "lecture": "Cell biology", "assets": "lecture-notes"},
                ]
            },
            {
                "title": "DNA replication",
                "views": 55000,
                "quality": "B",
                "importance": "High",
                "templates": ["Refimprove"],
                "ocw_matches": [
                    {"course": "7.016", "title": "Introductory Biology", "lecture": "DNA replication", "assets": "video+transcript"},
                ]
            },
        ],
        "total_views": 8700000,
        "period": "2026-04-01 to 2026-04-30"
    }
}


def timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def score_match(article: dict, match: dict) -> int:
    """Score a candidate match 0-100."""
    score = 0
    # Quality gap: C or below = good target
    quality_scores = {"Stub": 30, "Start": 25, "C": 20, "B": 10, "GA": 5, "FA": 0}
    score += quality_scores.get(article["quality"], 0)
    # Importance
    importance_scores = {"Top": 25, "High": 20, "Mid": 10, "Low": 5}
    score += importance_scores.get(article["importance"], 0)
    # Templates present
    if article.get("templates"):
        score += min(len(article["templates"]) * 10, 25)
    # Asset richness
    asset_scores = {"video+transcript": 20, "lecture-notes": 10, "reading-list": 5}
    score += asset_scores.get(match.get("assets", ""), 5)
    # Views (log-scaled)
    views = article.get("views", 0)
    if views > 100000:
        score += 10
    elif views > 50000:
        score += 7
    elif views > 20000:
        score += 4
    else:
        score += 1
    return min(score, 100)


def generate_summary(top_n=10):
    """Layer 1: Executive summary report."""
    total_courses = set()
    total_matches = 0
    high_priority = 0
    all_matches = []

    for project, data in DEMO_DATA.items():
        for article in data["articles"]:
            if not article["ocw_matches"]:
                continue
            total_matches += len(article["ocw_matches"])
            for match in article["ocw_matches"]:
                total_courses.add(match["course"])
                s = score_match(article, match)
                if s >= 60:
                    high_priority += 1
                all_matches.append((s, project, article, match))

    all_matches.sort(key=lambda x: -x[0])

    lines = []
    lines.append("> Generated by `scripts/crossref-wikipedia.py --report --demo`")
    lines.append("")
    lines.append("# Wikipedia CrossRef: Summary Report")
    lines.append("")
    lines.append(f"Demo based on WikiProject Environment Popular pages data (April 2026).")
    lines.append(f"**{total_matches} candidate matches** across **{len(total_courses)} OCW courses**.")
    lines.append("")
    lines.append(f"## Top {min(top_n, len(all_matches))} highest-impact matches")
    lines.append("")
    lines.append("| # | OCW Course | Wikipedia Article | Views | Quality | Importance | Templates | Score")
    lines.append("|---|------------|-------------------|-------|---------|------------|-----------|-------")
    for i, (s, proj, article, match) in enumerate(all_matches[:top_n]):
        tmpl = ", ".join(article.get("templates", [])) or "—"
        lines.append(f"| {i+1} | **{match['course']}** | [[en:{article['title'].replace(' ', '_')}]] | {article['views']:,} | {article['quality']} | {article['importance']} | {tmpl} | **{s}**")

    lines.append("")
    lines.append("## By OCW Department")
    lines.append("")
    dept_map = {}
    for s, proj, article, match in all_matches:
        dept = match["course"].split(".")[0]
        dept_map.setdefault(dept, {"matches": 0, "high": 0})
        dept_map[dept]["matches"] += 1
        if s >= 60:
            dept_map[dept]["high"] += 1

    lines.append("| Department | Matches | High-priority |")
    lines.append("|------------|---------|---------------|")
    for dept in sorted(dept_map.keys()):
        name = DEPT_NAMES.get(dept, dept)
        lines.append(f"| **{dept}** {name} | {dept_map[dept]['matches']} | {dept_map[dept]['high']} |")

    lines.append("")
    lines.append("## By Quality Class")
    lines.append("")
    q_counts = {}
    for s, proj, article, match in all_matches:
        q = article["quality"]
        q_counts[q] = q_counts.get(q, 0) + 1
    lines.append("| Quality | Matches |")
    lines.append("|---------|---------|")
    for q in ["Stub", "Start", "C", "B", "GA", "FA"]:
        if q in q_counts:
            lines.append(f"| {q} | {q_counts[q]} |")

    lines.append("")
    lines.append("---")
    lines.append(f"_Report generated {timestamp()}._")

    return "\n".join(lines)


def generate_project_summary(project: str):
    """Layer 2: Detail page for a single WikiProject."""
    data = DEMO_DATA.get(project)
    if not data:
        return "# No data"

    # Separate by priority quadrant
    primary = []   # High importance, C or below
    secondary = [] # Low importance, C or below
    done = []      # B/GA/FA
    templates_by_type = {}

    for article in data["articles"]:
        for tmpl in article.get("templates", []):
            templates_by_type.setdefault(tmpl, []).append(article)
        if article["quality"] in ("Stub", "Start", "C") and article["importance"] in ("Top", "High"):
            primary.append(article)
        elif article["quality"] in ("Stub", "Start", "C"):
            secondary.append(article)
        else:
            done.append(article)

    lines = []
    lines.append(f"> Generated by `scripts/crossref-wikipedia.py --report --demo`")
    lines.append("")
    lines.append(f"# WikiProject: {project}")
    lines.append("")
    lines.append(f"Period: {data['period']}  ·  Total views: {data['total_views']:,}")
    lines.append(f"Articles in scope: {len(data['articles'])}")
    lines.append("")

    # Primary targets
    lines.append("## Primary targets (High importance, needs work)")
    lines.append("")
    lines.append("| Article | Views | Quality | Templates | OCW match | Score")
    lines.append("|---------|-------|---------|-----------|-----------|-------")
    for article in primary:
        tmpl = ", ".join(article.get("templates", [])) or "—"
        if article["ocw_matches"]:
            for match in article["ocw_matches"]:
                s = score_match(article, match)
                lines.append(f"| [[en:{article['title'].replace(' ', '_')}]] | {article['views']:,} | {article['quality']} | {tmpl} | {match['course']} ({match['lecture']}) | **{s}**")
            else:
                lines.append(f"| [[en:{article['title'].replace(' ', '_')}]] | {article['views']:,} | {article['quality']} | {tmpl} | — | —")

    # Templates breakdown
    lines.append("")
    lines.append("## Maintenance templates found")
    lines.append("")
    lines.append("| Template | Articles |")
    lines.append("|----------|----------|")
    for tmpl, articles in sorted(templates_by_type.items()):
        names = ", ".join(a["title"] for a in articles[:5])
        if len(articles) > 5:
            names += f" … and {len(articles)-5} more"
        lines.append(f"| `{{{{{tmpl}}}}}` | {names}")

    lines.append("")
    lines.append("## Score distribution")
    lines.append("")
    all_scores = []
    for article in data["articles"]:
        for match in article.get("ocw_matches", []):
            all_scores.append(score_match(article, match))
    if all_scores:
        buckets = {"0-19": 0, "20-39": 0, "40-59": 0, "60-79": 0, "80-100": 0}
        for s in all_scores:
            if s < 20: buckets["0-19"] += 1
            elif s < 40: buckets["20-39"] += 1
            elif s < 60: buckets["40-59"] += 1
            elif s < 80: buckets["60-79"] += 1
            else: buckets["80-100"] += 1
        
        max_count = max(buckets.values()) or 1
        lines.append("| Score | Count | Distribution |")
        lines.append("|-------|-------|--------------|")
        for bucket, count in buckets.items():
            bar = "█" * int(count / max_count * 30) if max_count else ""
            lines.append(f"| {bucket} | {count} | {bar}")

    lines.append("")
    lines.append("---")
    lines.append(f"_Generated {timestamp()} from demo data._")

    return "\n".join(lines)


def generate_heatmap():
    """Generate an HTML heatmap page using a table layout for guaranteed column alignment."""
    projects = list(DEMO_DATA.keys())
    depts = sorted(set(
        match["course"].split(".")[0]
        for data in DEMO_DATA.values()
        for article in data["articles"]
        for match in article.get("ocw_matches", [])
    ))

    # Build match matrix
    matrix = {}
    for dept in depts:
        matrix[dept] = {}
        for proj in projects:
            matrix[dept][proj] = 0
    for proj, data in DEMO_DATA.items():
        for article in data["articles"]:
            for match in article.get("ocw_matches", []):
                dept = match["course"].split(".")[0]
                matrix.setdefault(dept, {})
                matrix[dept].setdefault(proj, 0)
                matrix[dept][proj] += 1

    max_val = max(matrix[d][p] for d in depts for p in projects) or 1

    def heat_color(t):
        if t <= 0: return "#f5f5f5"
        r = min(255, int(255 * (1 - t * 0.85)))
        g = min(255, int(255 * (1 - t * 0.45)))
        b = min(255, int(255 * (1 - t * 0.15)))
        return f"rgb({r},{g},{b})"

    rows_html = ""

    # Header row
    rows_html += "  <tr>\n    <th class='hl'>Department</th>\n"
    for p in projects:
        rows_html += f"    <th class='hc'>{p}</th>\n"
    rows_html += "  </tr>\n"

    # Data rows
    for d in depts:
        name = DEPT_NAMES.get(d, d)
        rows_html += f"  <tr>\n    <td class='ll'><strong>{d}</strong> <span class='dn'>{name}</span></td>\n"
        for p in projects:
            val = matrix.get(d, {}).get(p, 0)
            if val == 0:
                rows_html += "    <td class='nc'>—</td>\n"
            else:
                bg = heat_color(val / max_val)
                rows_html += f"    <td class='mc'><span class='bc' style='background:{bg}'>{val}<span class='tip'>{d} → {p}: {val} match{'es' if val != 1 else ''}</span></span></td>\n"
        rows_html += "  </tr>\n"

    # Legend bar
    legend_parts = "".join(f'<div style="background:{heat_color(i/max_val)}"></div>' for i in range(max_val + 1))

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>CrossRef Match Heatmap — OCW ↔ Wikipedia</title>
<style>
body{{font-family:'Inter','Segoe UI',sans-serif;background:#fafafa;margin:0;padding:2rem}}
h1{{font-size:1.6rem;font-weight:600;margin-bottom:0.3rem}}
.s{{color:#888;font-size:0.9rem;margin-bottom:2rem}}
table{{border-collapse:collapse;width:100%}}
th,td{{padding:7px 12px;font-size:0.82rem;text-align:center;border-bottom:1px solid #eee}}
.hl{{text-align:right;font-weight:600;color:#555;font-size:0.72rem;letter-spacing:0.05em;border-bottom:2px solid #ddd;padding-right:16px}}
.hc{{font-weight:600;color:#555;font-size:0.72rem;letter-spacing:0.05em;border-bottom:2px solid #ddd}}
.ll{{text-align:right;font-weight:500;color:#333;padding-right:16px;white-space:nowrap}}
.dn{{font-weight:400;color:#999;font-size:0.75rem}}
.nc{{color:#ddd}}
.mc{{text-align:center}}
.bc{{display:inline-block;height:26px;border-radius:3px;line-height:26px;padding:0 8px;font-size:0.75rem;font-weight:600;color:#fff;position:relative;cursor:default;transition:transform 0.1s,box-shadow 0.1s}}
.bc:hover{{transform:scale(1.15);box-shadow:0 2px 10px rgba(0,0,0,0.2);z-index:10}}
.tip{{position:absolute;bottom:100%;left:50%;transform:translateX(-50%);background:#333;color:#fff;padding:3px 8px;border-radius:3px;font-size:0.65rem;white-space:nowrap;opacity:0;pointer-events:none;transition:opacity 0.15s;margin-bottom:5px}}
.bc:hover .tip{{opacity:1}}
.lg{{display:flex;align-items:center;gap:10px;margin-top:2rem;font-size:0.8rem;color:#666}}
.lb{{display:flex;height:14px;border-radius:3px;overflow:hidden}}
.lb div{{width:22px}}
</style>
</head>
<body>
<h1>OCW ↔ Wikipedia Match Heatmap</h1>
<p class="s">{len(depts)} OCW departments × {len(projects)} WikiProjects — darker cells = more OCW courses matching that WikiProject. Hover for details.</p>
<table>
{rows_html}
</table>
<div class="lg"><span>Match density:</span><div class="lb">{legend_parts}</div><span>0 → {max_val}</span></div>
<p style="margin-top:2rem;color:#888;font-size:0.8rem">Generated {timestamp()}</p>
</body>
</html>"""


def main():
    args = sys.argv[1:]
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    if "--report" in args and "--demo" in args:
        top_n = 10
        for i, a in enumerate(args):
            if a == "--top" and i + 1 < len(args):
                top_n = int(args[i + 1])
                break

        print(f"Generating crossref demo reports (top {top_n} matches)...")

        # Layer 1: Executive summary
        summary = generate_summary(top_n)
        (REPORT_DIR / "crossref-summary.md").write_text(summary)
        print(f"  wrote {REPORT_DIR / 'crossref-summary.md'}")

        # Layer 2: Project detail pages
        for project in DEMO_DATA:
            detail = generate_project_summary(project)
            path = REPORT_DIR / f"crossref-{project.lower().replace(' ', '-')}.md"
            path.write_text(detail)
            print(f"  wrote {path}")

        # Layer 3: Heatmap
        heatmap = generate_heatmap()
        (REPORT_DIR / "crossref-heatmap.html").write_text(heatmap)
        print(f"  wrote {REPORT_DIR / 'crossref-heatmap.html'}")

        print(f"\nDone. Open wiki/reports/ in WikiWise to browse.")

    elif "--report" in args:
        print("Live report mode requires SSH tunnel. Use --demo for now, or set up .env credentials.")
        print("  python3 scripts/crossref-wikipedia.py --report --demo")

    elif "--apply" in args:
        print("Apply mode not yet implemented. Review reports first, then run --apply.")
        print("  python3 scripts/crossref-wikipedia.py --report --demo")

    else:
        print(__doc__)


if __name__ == "__main__":
    main()
