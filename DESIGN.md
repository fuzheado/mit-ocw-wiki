# Design: Contribution Impact Matrix

## Overview

A D3.js bubble scatterplot for exploring any Wikipedia WikiProject's articles by four dimensions: quality, pageviews, importance, and maintenance templates. Designed to surface "enrichment opportunities" — articles where editor effort has the most impact.

The tool has two modes:
- **Generic Mode** (default): pick any WikiProject with a Popular pages page, explore its articles
- **MIT Mode** (planned, v0.2): restricts to OCW-aligned WikiProjects, overlays course match data

Current state: **v0.1** — Generic Mode with 8 WikiProjects, 6,500 articles, pre-computed wikitext context.

---

## Data flow

```
┌─────────────────────────────────────────────────────────────────┐
│  DATA GENERATION (Python, offline, run on demand)                │
│                                                                  │
│  1. Popular pages API                                            │
│     action=parse&page=Wikipedia:WikiProject_{name}/Popular_pages │
│     → HTML table with 6 columns (Rank, Title, Views,            │
│       DailyAvg, Assessment, Importance)                          │
│     → Parsed with regex on rendered HTML                         │
│     → 1 API call per project (not per article)                   │
│       (Rationale: bot output, stable MediaWiki table rendering)  │
│                                                                  │
│  2. SQL template enrichment                                      │
│     Tunnel: ssh → enwiki_p (MariaDB replica)                     │
│     Query: templatelinks → linktarget for 27 template aliases    │
│     + talk-page templates via page_title join to namespace 1     │
│     → Article-body + talk-page template list per article         │
│     → Batch of 50 titles per query                               │
│                                                                  │
│  3. SQL article metadata                                         │
│     Query: page_props (wikibase-shortdesc)                       │
│     + page.page_touched, page.page_len                           │
│     → Short description, last edit date, article size            │
│                                                                  │
│  4. Wikitext context (mwparserfromhell)                          │
│     API: action=parse&prop=wikitext (1 call per article)         │
│     Parse: mwparserfromhell.ifilter_templates()                  │
│     Extract per template:                                        │
│       - Section name (walk sections, find containment)           │
│       - |date= parameter value                                   │
│       - Preceding sentence (last \n\n or 500-char window)        │
│       - Context type: inline/infobox/table/footnote/             │
│         blockquote/minimal (see classification logic below)      │
│     Deduplication: skip templates at same text position          │
│     → ~859/880 templated articles get context                    │
│                                                                  │
│  5. Assembly                                                     │
│     All data merged into: wiki/impact-matrix/data/live-data.js   │
│     Format: var LIVE_DATA = { "Project": { articles: [...] } }   │
│     Each article: { title, views, quality, importance,           │
│       templates[], short_desc, touched, page_len, ctx[] }        │
│                                                                  │
│  6. Standalone build                                             │
│     python3 script replaces <script src="..."> with inline JS    │
│     Output: wiki/impact-matrix/standalone.html (~1.7 MB)         │
│     Self-contained — D3.js loaded from CDN, data embedded        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  BROWSER (file:// or http:// — no server needed)                 │
│                                                                  │
│  wiki/impact-matrix/standalone.html                              │
│    │                                                             │
│    ├── D3.js (CDN) → scatterplot rendering                       │
│    ├── LIVE_DATA (embedded) → all article data                   │
│    │                                                             │
│    └── User interactions:                                        │
│         ├── Pick project → filter articles, render scatterplot   │
│         ├── Hover bubble → tooltip with metadata                 │
│         ├── Click bubble → detail panel with context             │
│         ├── Toggle Scatter/Table → switch view                   │
│         ├── Filters → re-filter + re-render                      │
│         └── Slider → truncate to top N articles                  │
└─────────────────────────────────────────────────────────────────┘
```

## Key architectural decisions

### 1. Popular pages over REST API for pageviews

**Problem:** The `enwiki_p` analytics replica has no pageview data (`page_props.pageview_daily_average` = 0 rows). The Wikimedia pageview REST API was initially rate-limiting our early tests (~15 req/min), though this improved after standardizing on a compliant User-Agent string. Even with better rate limits, Popular pages remain the clear winner — 1 API call per project vs. 1,000+ individual calls for the same data.

**Decision:** Use WikiProject Popular pages — bot-maintained monthly tables at `Wikipedia:WikiProject_{name}/Popular_pages`. These pre-compile the top 1,000 articles by pageviews with quality and importance ratings. Available via a single `action=parse` API call per project.

**Tradeoff:** Only ~500 of the ~1,500 WikiProjects have Popular pages enabled. For the remaining 1,000, no pageview data is available (fallback: sort by importance + quality).

**Verification:** Tested across 8 projects (Environment, Chemistry, Biology, Physics, Computer Science, Mathematics, Medicine, Business) — all return 500-1000 articles with 100% pageview coverage.

### 2. Pre-computed context over client-side wikitext parsing

**Problem:** Client-side `fetch()` is blocked from `file://` origins by CORS. JSONP via `<script>` tags also failed (the browser refused to execute the callback).

**Decision:** Pre-compute wikitext context during data generation using Python's `mwparserfromhell`. Each article with templates gets its wikitext fetched and parsed once. Results are stored in `live-data.js`.

**Tradeoff:** Data generation takes longer (one API call per templated article). Total data size is ~1.7 MB instead of ~1.1 MB. But the standalone HTML works from `file://` with zero runtime API calls.

**Impact:** Detail panel renders instantly — no "Loading context..." state.

### 3. HTML table parsing over mwparserfromhell for Popular pages

**Problem:** Popular pages are wikitext tables. Using mwparserfromhell to parse them would mean two wikitext parsers in the pipeline.

**Decision:** Parse the rendered HTML (`prop=text`), not the wikitext. The Community Tech bot generates these tables with stable, predictable HTML (standard `<table class="wikitable">`). The 6-column structure (Rank, Title, Views, DailyAvg, Assessment as `[[:Category:X-Class articles|X]]`, Importance as `[[:Category:X-importance articles|X]]`) has been consistent since the bot's inception.

**Tradeoff:** HTML regex is less principled than AST parsing, but the input is machine-generated, not hand-edited. MediaWiki's wikitable rendering hasn't changed in over a decade.

### 4. Standalone HTML over live server

**Problem:** Running a persistent Python server within the agent/bash tool environment is unreliable — processes are killed when the shell times out.

**Decision:** Pre-generate ALL data including wikitext context into a self-contained HTML file. No server needed.

**Tradeoff:** No ad-hoc query capability (cannot dynamically query a project not in the pre-generated set). The server script (`scripts/impact-matrix-server.py`) exists for future use when a stable hosting environment is available.

### 5. `<ref>` context detection: last-unmatched check

**Problem:** The context classifier was incorrectly flagging inline `{{citation needed}}` tags as "footnote" because a `</ref>` happened to be within 500 characters before the template, while its matching `<ref` was outside that window.

**Decision:** Walk back from the template position through the FULL wikitext before it. Compare the last occurrence of `<ref` (opening tag) and `</ref>` (closing tag). If the opening tag is more recent, the template is inside a `<ref>` block. Otherwise it's inline.

**Verification:** Article Parthenogenesis — 2 `{{cn}}` templates, both now correctly classified as "inline" (was 4 "footnote" + 2 "inline" due to duplicates).

## Template context classification

When a maintenance template is found in the wikitext, its surrounding context is classified into one of these types:

| Type | Detection rule | Display in panel |
|---|---|---|
| **inline** | Default. ≥20 characters of preceding text, not in a special construct. | Shows the preceding sentence as "Possible context", with "⚠ Best guess" disclaimer. |
| **infobox** | `{{Infobox` appears within 500 chars before the template. | "This tag is in an infobox — edit the infobox directly." |
| **table** | Wikitext table markers (`{|`) within 500 chars before. | "This tag is in a table cell — view the article source to locate it." |
| **footnote** | Last unmatched `<ref` before the template comes after the last `</ref>`. | "This tag was placed inside a reference — check the article." |
| **blockquote** | `<blockquote` or `{{Quote` within 500 chars before. | "This tag is inside a quotation — verify against the original source." |
| **minimal** | Extracted context is <20 characters. | "Little surrounding text — the tag may be in a list or nav element." |

## Template aliases queried

27 template aliases split into two categories:

**Article-body (20):** Citation_needed, Cn, Fact, Cite, Refimprove, Sources, Cites, Primary_sources, Primarysources, Better_source_needed, Bsn, Technical, Too_technical, Overly_technical, Missing_information, Expand_section, Gap, Unreferenced_section, Urs, Scientific_verification, Verify

**Talk-page (7):** Image_requested, Needs_image, Imagerequest, Diagram_needed, Needs_diagram, Video_requested, Needs_video

(Note: `Overly_technical`, `Needs_diagram`, `Scientific_verification` don't exist in the linktarget table — queried for completeness but never match.)

## Color scale

Template count → bubble color (d3.scaleThreshold):

| Count | Color | Hex |
|-------|-------|-----|
| 0 | Green | `#27ae60` |
| 1 | Yellow | `#f1c40f` |
| 2 | Orange | `#e67e22` |
| 3 | Red | `#e74c3c` |
| 4+ | Maroon | `#8b0000` |

## Component map

| File | Purpose |
|------|---------|
| `wiki/impact-matrix/standalone.html` | Self-contained tool (~1.7 MB). Open anywhere. |
| `wiki/impact-matrix/index.html` | Prototype source. Same as standalone but loads data from `data/live-data.js`. |
| `wiki/impact-matrix/data/live-data.js` | Pre-computed data for 8 projects, 6,500 articles. Embedding target. |
| `scripts/impact-matrix-server.py` | Live query server. Requires SSH tunnel + .env credentials. |
| `notes/pageview-data-issues.md` | Documentation of pageview data research (3 failed approaches). |
| `notes/detail-panel-spec.md` | Detail panel content spec and mockup. |
| `PRD-CONTRIBUTION-IMPACT-MATRIX.md` | Full product requirements document. |

## Rebuild workflow

```bash
# 1. Regenerate data (Popular pages + SQL templates + wikitext context)
# Edit the inline Python in the session, or run the pipeline manually:
# (The data generation script is not a standalone .py file — it's assembled
#  as an inline heredoc. Extract to scripts/ if run becomes routine.)
python3 << 'HEREDOC'
# See .claude/active-file or session history for the full data generation script
HEREDOC

# 2. Rebuild standalone HTML
python3 -c "
with open('wiki/impact-matrix/data/live-data.js') as f:
    js = f.read()
with open('wiki/impact-matrix/index.html') as f:
    html = f.read()
html = html.replace('<script src=\"data/live-data.js\"></script>',
                    '<script>\n' + js + '\n</script>')
with open('wiki/impact-matrix/standalone.html', 'w') as f:
    f.write(html)
"

# 3. To add a new WikiProject:
#    - Add its name to the `projects` list in the data generation script
#    - Re-run steps 1-2
#    - Verify the project has a Popular pages page at
#      https://en.wikipedia.org/wiki/Wikipedia:WikiProject_{name}/Popular_pages

# 4. To run the live query server (requires SSH tunnel + .env):
python3 scripts/impact-matrix-server.py
# Then open http://localhost:8899/wiki/impact-matrix/index.html
```

## Dependencies

| Dependency | Where | Purpose |
|---|---|---|
| D3.js v7 | CDN (browser) | Scatterplot rendering |
| pymysql | Python (server + data gen) | SQL queries to enwiki_p |
| python-dotenv | Python (server + data gen) | Credential loading |
| mwparserfromhell | Python (data gen) | Wikitext AST parsing for template context |
| ssh (Toolforge) | Python (server + data gen) | Tunnel to enwiki_p |

## Git tags

- `v0.1-impact-matrix` — Current checkpoint. Generic Mode, 8 projects, 6,500 articles, pre-computed context.
