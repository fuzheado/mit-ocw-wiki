# MIT on Wikipedia — Dashboard Design

> **Status:** Design phase. Tracks all MIT-related contributions and assets across Wikipedia and Wikimedia Commons.
> **Depends on:** `docs/CONTRIBUTION-LADDER.md`, `toolforge/DESIGN.md`, existing SQL/cache infrastructure

---

## What it is

A monitoring and visibility dashboard that answers one question: **"What is MIT's footprint on Wikipedia?"** Unlike the Contribution Workbench (which helps editors *make* edits), this dashboard tracks what *already exists* and what *has been done* — OCW links, Commons media, WikiProject coverage, contribution impact, and editor activity.

---

## Metrics & Data Sources

### 1. OCW Links on Wikipedia

**Question:** How many Wikipedia articles link to `ocw.mit.edu`, and where?

**Data source:** CirrusSearch `insource:` or SQL `externallinks` table

```bash
# CirrusSearch: find all articles with ocw.mit.edu in wikitext
curl "https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch=insource:ocw.mit.edu&srlimit=500&format=json"

# SQL (faster for bulk, via SSH tunnel to Toolforge):
SELECT el_from, el_to_domain_index, el_to
FROM externallinks
WHERE el_to_domain_index = 'https://ocw.mit.edu'
  OR el_to LIKE 'https://ocw.mit.edu/%'
```

**Metrics to show:**
| Metric | Source | Refresh |
|--------|--------|---------|
| Total articles with OCW links | SQL `externallinks` | Daily |
| Total unique OCW URLs cited | SQL aggregation | Daily |
| Articles with OCW links by WikiProject | SQL + PageAssessments | Daily |
| Articles with OCW links by quality class | SQL + PageAssessments | Daily |
| New OCW links this month | CirrusSearch + timestamp filter | Weekly |
| Top 10 most-linked OCW courses | SQL aggregation | Daily |
| Articles with OCW links but low quality (Stub/Start) | SQL + PageAssessments | Weekly |

### 2. Wikimedia Commons — MIT Assets

**Question:** What MIT-related media is on Commons, and where is it used?

**Data source:** Commons API + SPARQL

```sparql
# Commons SPARQL (via WCQS or QLever): MIT-related files with usage
SELECT ?file ?title ?usage_count WHERE {
  ?file wdt:P180 ?depicts .
  ?depicts wdt:P31 wd:Q49108 .  # instance of: MIT
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
}
```

Alternative: Category-based approach
```bash
# Commons API: files in MIT-related categories
curl "https://commons.wikimedia.org/w/api.php?action=query&list=categorymembers&cmtitle=Category:Massachusetts_Institute_of_Technology&cmtype=file&cmlimit=100&format=json"
```

**Metrics to show:**
| Metric | Source | Refresh |
|--------|--------|---------|
| Total MIT files on Commons | Commons API category count | Weekly |
| Files by type (image/video/audio/PDF) | Commons API | Weekly |
| Most-used MIT files (global usage) | Commons API `globalusage` | Weekly |
| Files not yet used in any Wikipedia article | Commons API minus usage check | Weekly |
| New uploads this month | Commons API + date filter | Weekly |
| Files by license | Commons API metadata | Monthly |

### 3. WikiProject MIT — Article Scope

**Question:** Which Wikipedia articles are "in scope" for MIT content (by WikiProject, category, or topic)?

**Data source:** PageAssessments SQL + Category API

```sql
-- Articles assessed by WikiProjects relevant to MIT (already in crossref strategy)
SELECT p.page_title, pa.pa_class, pa.pa_importance, pap.project_name
FROM page p
JOIN page_assessments pa ON p.page_id = pa.pa_page
JOIN page_assessments_projects pap ON pa.pa_project = pap.pap_project
WHERE pap.project_name IN ('Physics', 'Chemistry', 'Mathematics', 'Computer Science',
                           'Engineering', 'Biology', 'Economics', 'Environment', ...)
  AND p.page_namespace = 0
```

**Metrics to show:**
| Metric | Source | Refresh |
|--------|--------|---------|
| Articles in MIT-aligned WikiProjects | PageAssessments SQL | Daily |
| Quality distribution (FA/GA/B/C/Start/Stub) | PageAssessments SQL | Daily |
| Articles in scope WITHOUT OCW links (coverage gap) | SQL join with externallinks | Weekly |
| Articles with maintenance templates (cn, refimprove, etc.) | SQL + PageAssessments | Weekly |
| High-importance/low-quality articles (priority targets) | PageAssessments SQL | Daily |

### 4. Wiki MIT — Our Contributions

**Question:** What has the Wiki MIT project contributed to Wikipedia?

**Data source:** Our own activity log (from Workbench `localStorage` or server-side SQLite) + Wikipedia API

| Metric | Source | Refresh |
|--------|--------|---------|
| Total edits made (L1/L2/L3) | Activity log aggregation | Real-time |
| Edits by type (L1 refideas, L2 external links) | Activity log | Real-time |
| Edits by WikiProject | Activity log + PageAssessments | Daily |
| Edits by editor (if OAuth multi-user) | Activity log | Real-time |
| Acceptance rate (edits not reverted) | Wikipedia API `action=query&list=usercontribs` + revert check | Weekly |
| Articles improved (quality upgrade after our edit) | Compare PageAssessments over time | Monthly |

### 5. Impact Metrics

**Question:** What effect are OCW links having on article quality and readership?

| Metric | Source | Refresh |
|--------|--------|---------|
| Total monthly pageviews of articles with OCW links | Pageviews REST API (batch) | Monthly |
| Average pageviews by quality class | Pageviews REST API | Monthly |
| Articles where quality improved after OCW link added | PageAssessments history | Quarterly |
| Top 10 most-viewed articles with OCW links | Pageviews REST API | Weekly |

---

## Dashboard Layout (Static HTML)

Same architecture as the Impact Matrix — a single self-contained HTML file that works from `file://`.

```
┌─────────────────────────────────────────────────────────────────────┐
│  MIT on Wikipedia — Dashboard                           [Refresh]   │
│                                                                     │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ │
│  │  OCW     │ │ Commons  │ │  In      │ │  Our     │ │  Impact  │ │
│  │  LINKS   │ │  ASSETS  │ │  SCOPE   │ │  EDITS   │ │  METRICS │ │
│  │          │ │          │ │          │ │          │ │          │ │
│  │   247    │ │   1,203  │ │  14,582  │ │    156   │ │  2.3M    │ │
│  │ articles │ │  files   │ │ articles │ │  edits   │ │ views/mo │ │
│  │          │ │          │ │ in scope │ │  made    │ │          │ │
│  │  ↑12    │ │  ↑34    │ │          │ │  ↑8     │ │  ↑142K  │ │
│  │ vs last │ │ vs last │ │  6,891   │ │ vs last │ │ vs last │ │
│  │ month   │ │ month   │ │  gaps    │ │ month   │ │ month   │ │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘ │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  OCW Links by WikiProject                    [Bar Chart ▾]   │   │
│  │                                                             │   │
│  │  Physics          ████████████████████  68                  │   │
│  │  Computer Science ████████████████     52                  │   │
│  │  Chemistry        ████████████         38                  │   │
│  │  Mathematics      ██████████           31                  │   │
│  │  Engineering      ████████             24                  │   │
│  │  Biology          ██████               19                  │   │
│  │  Environment      ████                 12                  │   │
│  │  Economics        ███                   9                  │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  Coverage Gap: Articles in scope without OCW links            │   │
│  │  [Table view ▾]  [By WikiProject ▾]  [By Quality ▾]         │   │
│  │                                                             │   │
│  │  Article              │ Project    │ Quality │ Importance  │ │
│  │  ──────────────────── │ ─────────  │ ─────── │ ─────────── │ │
│  │  Quantum computing    │ Physics    │ Start   │ High        │ │
│  │  Machine learning     │ CS         │ C       │ Top         │ │
│  │  Genetic algorithm    │ CS         │ Start   │ Mid         │ │
│  │  ...                                                [more] │ │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌────────────────────────────┐ ┌────────────────────────────┐    │
│  │  Most-Used Commons Assets   │ │  Recent Contributions      │    │
│  │                            │ │                            │    │
│  │  🖼️ MIT Dome.jpg  (142)   │ │  ✅ L2 — Algorithm ← 6.006 │    │
│  │  🖼️ MIT Seal.svg  (98)    │ │  ✅ L1 — Photovoltaics ... │    │
│  │  📹 OCW Lecture (45)      │ │  ✅ L2 — Linear algebra... │    │
│  │  🖼️ Building 10 (38)     │ │  ⚠️ L1 — Climate change...│    │
│  └────────────────────────────┘ └────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Data Pipeline

### Phase 1: Static pre-computed data (like Impact Matrix)

All data pre-generated by Python scripts, saved as JS files, loaded by static HTML:

```
generate-dashboard-data.py
  │
  ├── Step 1: Query SQL for OCW externallinks
  │     → dashboard/ocw-links.js
  │
  ├── Step 2: Query Commons API for MIT files
  │     → dashboard/commons-assets.js
  │
  ├── Step 3: Query PageAssessments for in-scope articles
  │     → dashboard/in-scope.js
  │
  ├── Step 4: Query Pageviews for article traffic
  │     → merges into above files
  │
  └── Step 5: Read activity log + Wikipedia user contributions
        → dashboard/our-edits.js

dashboard/standalone.html
  ← loads all .js files
  ← renders KPI cards, bar charts, tables
  ← works from file://
```

### Phase 2: Toolforge-hosted with live data

Upgrade key metrics to live queries:

```
Toolforge cron job (daily):
  → Regenerates JS data files
  → Posts summary to Meta wiki page

Optional: Live API endpoints in server.mjs:
  GET /api/dashboard/links     → live OCW link count
  GET /api/dashboard/commons   → live Commons asset count
  GET /api/dashboard/coverage  → live coverage gap analysis
```

---

## Key Queries to Build

### 1. Find all OCW links on Wikipedia (SQL, most efficient)

```sql
-- Requires SSH tunnel to Toolforge (wikimedia-database skill)
USE enwiki_p;

-- Count articles with ocw.mit.edu links
SELECT COUNT(DISTINCT el_from) AS article_count
FROM externallinks
WHERE el_to_domain_index = 'https://ocw.mit.edu'
   OR el_to LIKE 'https://ocw.mit.edu/%';

-- List articles with OCW links + quality assessment
SELECT
    p.page_title,
    pa.pa_class AS quality,
    el.el_to AS ocw_url
FROM externallinks el
JOIN page p ON el.el_from = p.page_id
LEFT JOIN page_assessments pa ON p.page_id = pa.pa_page
WHERE (el_to_domain_index = 'https://ocw.mit.edu'
       OR el_to LIKE 'https://ocw.mit.edu/%')
  AND p.page_namespace = 0;
```

### 2. Find OCW links by WikiProject

```sql
-- Articles with OCW links, grouped by WikiProject
SELECT
    pap.project_name,
    COUNT(DISTINCT p.page_id) AS article_count,
    GROUP_CONCAT(DISTINCT pa.pa_class) AS qualities
FROM externallinks el
JOIN page p ON el.el_from = p.page_id
JOIN page_assessments pa ON p.page_id = pa.pa_page
JOIN page_assessments_projects pap ON pa.pa_project = pap.pap_project
WHERE (el_to_domain_index = 'https://ocw.mit.edu'
       OR el_to LIKE 'https://ocw.mit.edu/%')
  AND p.page_namespace = 0
GROUP BY pap.project_name
ORDER BY article_count DESC;
```

### 3. Find coverage gaps (articles in scope without OCW links)

```sql
-- High-importance articles in MIT-aligned WikiProjects that lack OCW links
SELECT
    p.page_title,
    pap.project_name,
    pa.pa_class AS quality,
    pa.pa_importance AS importance
FROM page p
JOIN page_assessments pa ON p.page_id = pa.pa_page
JOIN page_assessments_projects pap ON pa.pa_project = pap.pap_project
WHERE pap.project_name IN ('Physics', 'Chemistry', 'Mathematics',
                           'Computer Science', 'Engineering',
                           'Biology', 'Economics', 'Environment')
  AND pa.pa_importance IN ('Top', 'High')
  AND p.page_namespace = 0
  AND p.page_id NOT IN (
      SELECT el_from FROM externallinks
      WHERE el_to_domain_index = 'https://ocw.mit.edu'
         OR el_to LIKE 'https://ocw.mit.edu/%'
  )
ORDER BY FIELD(pa.pa_importance, 'Top', 'High'),
         FIELD(pa.pa_class, 'Stub', 'Start', 'C', 'B', 'GA', 'FA');
```

### 4. Commons: MIT files with usage count

```bash
# Commons API: category members with global usage
curl "https://commons.wikimedia.org/w/api.php?\
action=query&\
list=categorymembers&\
cmtitle=Category:Massachusetts_Institute_of_Technology&\
cmtype=file&\
cmlimit=100&\
prop=globalusage&\
format=json"
```

### 5. Our edit history (from Wiki MIT)

```bash
# Wikipedia API: edits by our bot account
curl "https://en.wikipedia.org/w/api.php?\
action=query&\
list=usercontribs&\
ucuser=YourName@ocw-workbench&\
uclimit=50&\
format=json"
```

### 6. Pageviews for articles with OCW links

```python
# Batch pageview lookup using REST API
import requests
headers = {'User-Agent': 'Wiki MIT Dashboard/1.0 (https://meta.wikimedia.org/wiki/Wiki_MIT; your-email@example.com)'}

for article in articles_with_ocw:
    url = f"https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/all-agents/{article}/monthly/20260101/20260601"
    resp = requests.get(url, headers=headers)
    views = sum(item['views'] for item in resp.json().get('items', []))
```

---

## Integration Points

### With the Contribution Workbench

- Dashboard's "Coverage Gap" table → each row has a "Match" button that pre-fills the Workbench search
- Dashboard's "Recent Contributions" card → links to the Workbench activity log
- Dashboard KPI cards → live in the Workbench header as "at a glance" stats

### With the Impact Matrix

- Dashboard shares the same WikiProject filter list
- "Articles in scope" count mirrors the Impact Matrix article counts
- Link from Impact Matrix detail panel → Dashboard coverage stats for that article

### With Meta Wiki

- Daily summary posted to `meta.wikimedia.org/wiki/Wiki_MIT/Dashboard`
- Bot-updated wikitext table with key metrics
- Serves as a public-facing report for the project

---

## Build Order

### Sprint 1: OCW Link Census (1 session)

- Python script: query `externallinks` SQL for all `ocw.mit.edu` links
- Output: `dashboard/ocw-links.js`
- Simple HTML table: articles with OCW links, by WikiProject, by quality
- **Deliverable:** Know exactly how many OCW links exist on Wikipedia today

### Sprint 2: Coverage Gap Analysis (1 session)

- Python script: join in-scope articles (PageAssessments) against OCW links
- Output: `dashboard/coverage-gaps.js`
- Highlight: high-importance articles in scope that lack OCW links
- **Deliverable:** Prioritized list of articles to target

### Sprint 3: Commons Asset Census (1 session)

- Python script: query Commons API for MIT-related files + usage counts
- Output: `dashboard/commons-assets.js`
- Cards: most-used files, unused gems, upload activity
- **Deliverable:** Know what MIT media is on Commons and where it's used

### Sprint 4: KPI Dashboard (1-2 sessions)

- Static HTML (`dashboard/standalone.html`) with KPI cards, bar charts, tables
- Loads all pre-computed JS files
- Links to Workbench for gap articles
- **Deliverable:** Complete dashboard, works from `file://`

### Sprint 5: Activity + Impact Tracking (1-2 sessions)

- Integrate Workbench activity log
- Add pageview tracking for improved articles
- Add quality-change tracking over time
- **Deliverable:** Impact metrics showing the project's effect

---

## Reference

| Document | Covers |
|----------|--------|
| `toolforge/DESIGN.md` | Workbench architecture — data pipeline pattern to reuse |
| `docs/CONTRIBUTION-LADDER.md` | Generalized framework — dashboard adds monitoring to the editing pipeline |
| `docs/crossref-strategy.md` | WikiProject↔OCW department mappings (reuse for scope definition) |
| `docs/impact-matrix/design.md` | Static HTML + pre-computed JS data pattern to follow |
| `notes/scalability-and-domain-classification.md` | Per-project data architecture |
