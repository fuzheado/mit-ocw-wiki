# PRD: Wiki Contribution Impact Matrix

> **v0.1 released** — see `wiki/impact-matrix/standalone.html` for the current prototype.
> Implementation status is marked below with ✅ (done), 🔄 (partial), or ⬜ (not yet).

A bubble-scatterplot visualization that surfaces "enrichment opportunities" (articles where OCW materials — or any editor's efforts — can fill Wikipedia's known gaps) using pageviews, quality assessment, importance ratings, and maintenance templates.

## Problem

Wikipedia editors have no unified view of the four signals for a Wikipedia article that determine where effort might be most impactful: 
- **Pageviews** (audience reach)
- **Assessment/quality class** (determined by human effort or via machine learning model prediction via ORES)
- **Importance** (as hand-categorized in a WikiProject)
- **Maintenance templates** (citation needed, and other requests for improvement)

These live in separate database tables and are not easily shown together. A volunteer looking to adopt articles has to jump between tools — XTools for pageviews, the assessment table for quality, category pages for templates — to piece together a priority list.

## Dual-mode design

The tool has two modes, with **Generic Mode as the default**:

### Generic Mode (default)

Opens to a WikiProject picker — any of Wikipedia's ~1,500 WikiProjects. The user selects one and sees the scatterplot for that project's articles. No OCW data visible. This is a general-purpose Wikipedia editor tool: "show me the high-value articles to improve in WikiProject Chemistry."

Target user: any Wikipedia editor who wants to prioritize their contribution within a project they care about.

### MIT Mode (future development)

A toggle in the header switches to MIT Mode, which:
1. Restricts the project picker to the ~25 WikiProjects that align with MIT OCW departments (Chemistry, Physics, Biology, Environment, Computer science, etc.)
2. Runs the scatterplot across **all 25 projects** in parallel
3. Overlays OCW match data on each bubble — asset icons (🎬📄📝), course code, lecture title, direct link
4. Filters and facets gain an additional dimension: "Has OCW match" toggle
5. Detail panel adds a "Wikipedia Bridge" tab showing citation snippets

Target user: OCW wiki maintainers assessing cross-project coverage.

The split ensures the tool is useful beyond OCW from day one, while MIT Mode provides the project-specific value we need for OCW cross-referencing. It also makes prototyping easier — we can develop and refine Generic Mode with a single WikiProject before adding the OCW overlay complexity.

## Problem

Wikipedia articles carry multiple signals — pageviews, quality class, importance rating, and maintenance templates — but these live in separate database tables and are never shown together in one view. An editor trying to prioritize where to contribute has no way to see across all four dimensions at once.

## Terminology

| Term | Meaning |
|---|---|
| **Enrichment opportunity** | An article that scores high across all four dimensions (high views, low quality, high importance, active maintenance templates). Borrowed from environmental remediation — a "contamination" (knowledge gap) with high "exposure" (reader traffic). |
| **Contribution Impact Matrix** | The visualization: a bubble scatterplot with Quality on the X axis, Pageviews on the Y axis, bubble size = Importance, bubble color = maintenance template count. |
| **Generic Mode** | Default mode. User picks any WikiProject and sees the scatterplot with Wikipedia data only. No OCW involvement. |
| **MIT Mode** | Toggle mode. Filters to OCW-aligned projects, runs all 25 at once, overlays course match data on bubbles. |
| **Assessed quality** | The quality class (Stub→FA) assigned by WikiProject editors on the article's Talk page, stored in `page_assessments`. Can be stale — reflects the article at the time of last assessment. |
| **Predicted quality** | A machine-learned quality score from ORES/LiftWing, computed on demand against the article's current revision. Fresher, but only predicts quality (not importance), and has known biases. |
| **Sweet spot** | The top-left zone: high views + low quality. Primary target for enrichment. |
| **Stars** | Top-right: high views + high quality. Already well-covered but maintenance templates may signal decay. |
| **Sleepers** | Bottom-right: low views + high quality. Good articles that deserve more readers. |
| **Tail** | Bottom-left: low views + low quality. Lowest priority for intervention. |

## Data model

### Base query (both modes)

A single query against the `enwiki_p` replica returns core dimensions in under 500ms:

```
page_title       | VARCHAR  — article title
wikiproject      | VARCHAR  — WikiProject name
quality_class    | ENUM    — Stub / Start / C / B / GA / FA  (assessed)
importance       | ENUM    — Low / Mid / High / Top
avg_daily_views  | INT     — cached pageview average
template_count   | INT     — count of maintenance templates
template_list    | TEXT    — comma-separated template names
revision_id      | INT     — current revision ID (needed for ORES lookup)
```

### ORES override (quality source = Predicted)

When the user switches to Predicted quality:

1. Base query runs as above (still fetches assessed quality, importance, project membership).
2. A batch POST to the LiftWing API sends all revision IDs for the result set.
3. The API returns predicted quality classes, which override `quality_class` in memory.
4. Bubbles where assessed ≠ predicted get a visual indicator (e.g., a small triangle or glow ring).

The LiftWing API endpoint: `POST https://api.wikimedia.org/service/lw/inference/v1/models/enwiki-articlequality:predict`  
Body: `{"revs": [12345, 12346, ...]}`  
Response: `{"12345": {"prediction": "C", "probabilities": {"FA": 0.02, "GA": 0.05, "B": 0.15, "C": 0.60, "Start": 0.15, "Stub": 0.03}}, ...}`

Latency: ~200ms for 50 revision IDs, ~1s for 500. Acceptable for a toggle action.

### MIT Mode overlay

When MIT Mode is active, an additional join enriches each article with OCW match data:

```
course_code      | VARCHAR  — e.g., "5.111SC"
course_title     | VARCHAR  — e.g., "Principles of Chemical Science"
lecture          | VARCHAR  — matched lecture title
assets           | VARCHAR  — "video+transcript", "lecture-notes", etc.
match_score      | INT      — 0-100
article_url      | VARCHAR  — OCW course URL
```

This data is pre-computed by `crossref-wikipedia.py` and stored as a JSON sidecar, then joined client-side against the live query results.

## Feature requirements ✅ (v0.1)

### 0. Entry point: Project picker ✅

The tool opens to a project picker — a searchable dropdown or typeahead listing all WikiProjects with qualifying articles (those with assessments + pageview data). Each entry shows the project name and article count. "All Projects" is an option (runs a sweep across all projects). Below the picker, a toggle labeled "MIT Mode" switches to the restricted project list and OCW overlay.

### 1. Bubble scatterplot (primary view) ✅

- **X axis**: Quality (ordered Stub ← Start ← C ← B ← GA ← FA). Treated as ordinal — spacing reflects judgment, not a linear scale.
- **X axis dynamic collapse**: Hidden quality classes removed from scale ✅
- **Y axis**: Pageviews (log scale by default, toggle to linear). ✅
- **Each bubble** = one article.
- **Bubble size**: Importance (Top > High > Mid > Low).
- **Bubble color**: Template count (green = 0, yellow = 1-2, orange = 3-5, red = 6+).
- **In MIT Mode only**: bubbles with OCW matches get a colored ring or glyph overlay distinguishing them from unmatched articles.
- **Quadrant overlays**: Faint shaded zones labeled "Sweet Spots", "Stars", "Sleepers", "Tail".
- **Axis labels**: article count per quality class on X, view thresholds on Y.

### 2. Quality source toggle

Users can switch between two quality signals:

| Source | Data origin | Freshness | Covers importance? | Latency |
|---|---|---|---|---|
| **Assessed** | `page_assessments` table (Talk page WikiProject ratings) | May be months old | Yes — Top/High/Mid/Low | Zero (already in query result) |
| **Predicted** | ORES/LiftWing ML model (`enwiki-articlequality`) | Current revision | No — importance still falls back to assessed | ~200ms per 50-article batch via API |

When **Predicted** is selected:
- The killer query still runs against `page_assessments` for **project membership** and **importance** (ORES doesn't predict importance)
- Quality class is overridden with the ORES prediction
- Bubbles show a small indicator (e.g., a dot or asterisk) when assessed and predicted differ by more than one class — signaling that the article has changed significantly since its last assessment
- A batch ORES call is made after the SQL query returns (POST to the LiftWing API with a list of revision IDs)

The toggle has three states: Assessed (default), Predicted, and Side-by-side (bubble interior shows assessed, a small outer ring shows predicted — for comparison).

### 3. MIT Mode toggle

- When enabled, the project picker restricts to the ~25 OCW-aligned WikiProjects.
- A "Run All" button triggers parallel queries across all 25.
- Each bubble now carries OCW match data: course code, lecture title, asset badges.
- A new filter appears: "Has OCW match" (show only matched / only unmatched / both).
- The detail panel gains a "Wikipedia Bridge" tab with pre-formatted `{{cite web}}` citation templates.
- A summary bar at the top shows: "X of Y articles in this project have OCW matches."

### 4. Interaction

- **Hover**: tooltip with article title, quality (assessed / predicted), importance, views, template list. In MIT Mode, also shows matched course code + lecture title.
- **Click**: opens a detail panel (slide-out sidebar, reusing the existing heatmap pattern). Shows article metadata, maintenance templates as pills, OCW match details (MIT Mode only), and citation snippets.
- **Brush/select**: drag to select a region. Shows aggregate stats: N articles, avg views, template breakdown.

### 5. Filtering & faceting

*(Primary mechanism for scaling beyond 200 items.)*

- **By WikiProject**: dropdown / typeahead (Generic Mode) or project picker (MIT Mode).
- **By quality**: checkboxes for Stub/Start/C/B/GA/FA (default: all except FA in Generic Mode; Stub/Start/C in MIT Mode).
- **By importance**: checkboxes for Low/Mid/High/Top (default: all except Low).
- **By template count**: slider, 0-10+ (default: 0+).
- **By pageviews**: range slider (default: all).
- **By template type**: multi-select pills for specific templates ("Citation needed only").
- **Has OCW match** (MIT Mode only): toggle — matched / unmatched / both.
- **Search**: text input to find a specific article by title.
- **Filter chips**: active filters shown as removable chips above the scatterplot.

On filter change, re-query if the project changed; otherwise filter client-side (the full data is already in memory).

### 6. Table view (alternate mode)

Toggleable below the scatterplot. A sortable, filterable data table showing the same set of articles as rows. Columns: Title, Quality, Importance, Views (compact: 10k), Templates (as pills), and in MIT Mode: OCW match (course code + icon). Synced with the scatterplot — selecting a row highlights its bubble and vice versa.

### 7. Export / share

- "Copy as markdown table" (respects current filter state).
- "Share as link" (URL-encoded filter + mode state). In Generic Mode, links are portable to any editor.
- "Save as PNG" (requires canvas rendering).
- "Export CSV" for further analysis.

## Technical design

### Rendering

**Recommendation: D3.js with SVG.** Canvas would be faster for 5,000+ points, but SVG handles 200-500 points smoothly and gives us free tooltip support (CSS hover on `<circle>` elements), accessibility (SVG title elements), and easy export.

### Performance

The "killer query" (from `CROSSREF-STRATEGY.md`) completes in under 500ms for a single WikiProject:

```sql
SELECT p.page_title, pap.pap_project_title AS wikiproject,
       pa.pa_class, pa.pa_importance,
       CAST(pp.pp_value AS UNSIGNED) AS avg_daily_views,
       COUNT(DISTINCT tlt.tl_title) AS template_count,
       GROUP_CONCAT(DISTINCT tlt.tl_title) AS template_list
FROM page p
JOIN page_assessments pa ON pa.pa_page_id = p.page_id
JOIN page_assessments_projects pap ON pa.pa_project_id = pap.pap_project_id
LEFT JOIN page_props pp ON p.page_id = pp.pp_page
    AND pp.pp_propname = 'pageview_daily_average'
LEFT JOIN templatelinks tlt ON tlt.tl_from = p.page_id
    AND tlt.tl_title IN ('Citation_needed','More_citations_needed',
                         'Refimprove','Missing_information','Technical')
WHERE p.page_namespace = 0
  AND pap.pap_project_title = %s
  AND pa.pa_class IN ('Stub','Start','C','B','GA')
GROUP BY p.page_id
ORDER BY CAST(pp.pp_value AS UNSIGNED) DESC
LIMIT 500;
```

Key facts:
- `enwiki_p` is a **read-only replica** — no lock contention, no write load.
- The tables are **MySQL with InnoDB** and indexes on `page_id`, `pa_page_id`, `pap_project_id`, `tl_from`.
- Typical WikiProject has 200-1,500 qualifying articles. Query returns in 200-800ms.
- **Yes, this is live-queryable** for any WikiProject. No precomputation needed.
- For the OCW use case (37 departments, ~25 WikiProjects), a full run across all projects takes ~20 seconds if queried sequentially. Parallel queries bring that under 3 seconds.

### Architecture

#### Generic Mode request flow

```
Browser (scatterplot.html)
  │
  ├── 1. Page load: fetch WikiProject list
  │     └── GET /api/projects → SQL (SELECT DISTINCT pap_project_title FROM page_assessments_projects)
  │
  ├── 2. User picks "Chemistry"
  │     └── GET /api/query?project=Chemistry&quality_source=assessed
  │           └── SSH tunnel → enwiki_p → killer query → JSON response
  │
  ├── 3. User toggles quality source → Predicted
  │     └── GET /api/query?project=Chemistry&quality_source=ores
  │           ├── SSH tunnel → enwiki_p → killer query (fetches revision IDs)
  │           └── POST LiftWing API with revision IDs → predicted qualities
  │           └── Merge + return JSON
  │
  └── Render scatterplot via D3.js
```

#### MIT Mode request flow

```
Browser (scatterplot.html in MIT Mode)
  │
  ├── 1. Fetch OCW match data (pre-computed JSON sidecar)
  │     └── GET /data/ocw-crossrefs.json
  │
  ├── 2. For each of 25 WikiProjects:
  │     └── GET /api/query?project=Chemistry → killer query (parallel)
  │
  ├── 3. Client-side: join OCW matches onto article data
  │
  └── Render with overlay indicators
```

#### Implementation strategy

| Tier | Approach | When to use |
|---|---|---|
| **v1** | Static HTML + JS + pre-generated JSON data files. No backend required. Open the HTML file directly in a browser. | Prototyping, demo, offline use |
| **v2** | Same HTML/JS, but fetches data from a local Python server that has the SSH tunnel. User runs `python3 scripts/impact-matrix-server.py` | Live exploration, Generic Mode |
| **v3** | Hosted as a Toolforge tool with persistent tunnel. Public URL. | Production |
| **ORES** | Can be added at any tier. v1 can mock ORES by randomly perturbing assessed quality. v2+ calls the LiftWing API directly from the Python server. | v2+ |

For the initial prototype (v1 + a single WikiProject): we pre-generate a JSON file with the killer query results for WikiProject Chemistry (or another well-sized project), embed it in a self-contained HTML page with D3.js, and build the scatterplot, filters, and table against that single file. This gives us a functional demo without any backend. ORES can be mocked by adding a "randomize" button that shuffles qualities.

## Pages / routes

| Page | URL | Description |
|---|---|---|
| Impact matrix | `wiki/impact-matrix/index.html` | Self-contained HTML page. Opens to project picker. MIT Mode toggle in header. |
| Data (v1 static) | `wiki/impact-matrix/data/{project}.json` | Pre-generated killer query results per project. |
| OCW sidecar (MIT) | `wiki/impact-matrix/data/ocw-crossrefs.json` | Pre-computed OCW match data for the 25 aligned projects. |
| Project detail (MIT) | `wiki/crossrefs/{project}/{article}.md` | Per-article detail with OCW matches (existing pattern). |

The HTML page is self-contained (D3.js loaded from CDN). Data loaded via `fetch()` from the local `data/` directory in v1, switching to `/api/` in v2.

## Success criteria

1. A new user opens the tool, sees a project picker, types "Chem", selects WikiProject Chemistry, and sees the scatterplot in < 3 seconds.
2. The top-5 sweet-spot articles for any well-known WikiProject match what an experienced editor would identify as high-priority targets.
3. Toggling quality source (Assessed → Predicted) re-renders in < 2 seconds and shows visible differences for articles that have changed since their last assessment.
4. Switching to MIT Mode, running all 25 projects, and seeing OCW overlays completes in < 10 seconds.
5. Filtering (by quality, importance, template count) re-renders in < 200ms (client-side, no re-query).
6. The largest WikiProject (Medicine, ~1,200 articles) renders in < 2 seconds.
7. A shareable URL preserves project, mode, and filter state.

## Ethical considerations (ORES)

The ORES/LiftWing quality model has known biases. It tends to:
- Underrate articles in less-edited topic areas (e.g., niche sciences vs. pop culture)
- Overrate articles with many edits regardless of structural quality
- Confuse "well-referenced" with "well-written"

The tool mitigates this by:
- Defaulting to **Assessed** quality (human judgment) and requiring an explicit toggle to Predicted
- Showing a visual indicator when assessed and predicted diverge — this is itself useful data (articles whose quality has changed recently)
- Not using ORES importance (which doesn't exist) — importance always comes from WikiProject editors
- Including a note in the tooltip when quality is from ORES: "Predicted (ORES) — may differ from manual assessment"

## Open questions (resolved)

These were discussed and resolved before and during prototyping:

1. **Y axis scale: log or sqrt?** → **Log with a "Linear" toggle**. Log handles the 10-100× spread naturally (articles range from 10 to 250K+ views); sqrt over-compresses the high end. A one-click toggle lets power users switch to linear for specific comparisons. *(Not yet implemented — v0.1 uses log only.)*

2. **Jitter overlapping bubbles?** → **Deterministic jitter by article title hash**. When many articles share the same quality × views coordinates, apply a small random offset. The offset is deterministic by article ID so hover/click targets remain consistent across re-renders. ✅

3. **Show all articles vs. only OCW-matched in MIT Mode?** → **Both, with a filter toggle** (all / matched only / unmatched only). Default: all, with matched articles visually distinguished. *(MIT Mode not yet implemented — v0.1 is Generic Mode only.)*

4. **Individual project vs. aggregate "all 25" in MIT Mode?** → **Start with individual project views**. The picker restricts to the 25 projects but you explore one at a time. An aggregate dashboard ("all 25 at once") is v2.

5. **WikiProjects without Popular pages?** → **They still appear in the picker**. The killer query works for any project regardless (it queries `page_assessments_projects`, not Popular pages). Articles from these projects show the note "no pageview data" and sort by importance + quality gap instead. *(Not yet implemented — v0.1 covers 8 Popular pages projects.)*

6. **Static v1 prototype scope:** → A single-project data file (WikiProject Environment), scatterplot with all four dimensions, quality source toggle (with mocked ORES), table view, filters (quality, importance, template count, search), and a project picker that shows the selected project. No MIT Mode in v1. **This was the starting point — v0.1 far exceeds this scope with 8 projects, 6,500 articles, pre-computed context, and 1.7 MB standalone.**

## What's next (v0.2+)

| Feature | Priority |
|---------|----------|
| MIT Mode: OCW overlay on bubbles, match indicators | High |
| Aggregate "all 25" dashboard for MIT Mode | Medium |
| Live SQL query server for any WikiProject | Medium |
| Popular pages request tool for missing projects | Low |
| "Edit in Wikipedia" with pre-filled citation snippet | Low |
| License/copyright notes for OCW asset reuse | Low |
