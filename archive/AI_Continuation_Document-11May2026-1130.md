# PROJECT CONTINUATION DOCUMENT
## Session 1 — 11 May 2026

### 1. PROJECT IDENTITY

- **Project Name:** MIT OCW LLM Wiki — Contribution Impact Matrix
- **What This Project Is:** A D3.js bubble scatterplot tool for exploring any Wikipedia WikiProject's articles by quality, pageviews, importance, and maintenance templates. Surfaces "enrichment opportunities" — articles where editor effort has the most impact. Also includes an OCW (MIT OpenCourseWare) cross-referencing wiki of 2,577 courses.
- **Primary Objective:** Build a functioning, self-contained Contribution Impact Matrix (v0.1 tagged) that Wikipedia editors can use to find high-impact articles to improve, without needing any server infrastructure.
- **Strategic Intent:** Two audiences: (1) Wikipedia editors — give them a unified view of the four signals that determine article priority. (2) MIT OCW wiki maintainers — identify where MIT's open-licensed educational materials can fill Wikipedia's maintenance-template gaps.
- **Hard Constraints:**
  - All data must be pre-generated; the tool must work from `file://` with NO runtime API calls (browsers block `file://` CORS/fetch/JSONP).
  - The `enwiki_p` analytics replica has NO pageview data. Do NOT attempt to query `page_props.pageview_daily_average`.
  - The Wikimedia pageview REST API was rate-limiting our early tests (~15 req/min), but this improved after we standardized on a compliant User-Agent string. Popular pages are still preferred (1 API call vs 1,000+), but the REST API is viable for small batches with the proper UA.
  - WikiProject Popular pages (`Wikipedia:WikiProject_{name}/Popular_pages`) is the ONLY reliable pageview source.
  - The `templatelinks` table uses `tl_target_id → linktarget.lt_id`, NOT `tl_title`. This changed from the old schema — any SQL queries against templatelinks must join through linktarget.
  - `.env` file with Toolforge SQL credentials exists in project root. Do NOT commit.
  - User-Agent for all Wikimedia API calls: `'MIT OCW Bot/1.0 (https://meta.wikimedia.org/wiki/Wiki_MIT; andrew.lih@gmail.com) ContentGapResearch'`

### 2. WHAT EXISTS RIGHT NOW

- **What is built and working:**
  - Self-contained standalone HTML at `wiki/impact-matrix/standalone.html` (~1.7 MB). Open in any browser, works from `file://`.
  - 8 WikiProjects with full data: Environment, Chemistry, Biology, Physics, Computer Science, Mathematics, Medicine, Business. 500-1000 articles each, 6,500 total.
  - Bubble scatterplot: Quality (X, log scale), Pageviews (Y, ordinal, dynamically collapses hidden classes), Importance (bubble size), Template count (bubble color: green/yellow/orange/red/maroon).
  - Detail panel with pre-computed wikitext context: section name, date parameter, preceding sentence, context classifier (inline/infobox/table/footnote/blockquote/minimal).
  - Filters: rank slider (inline in header), quality checkboxes, importance checkboxes, template type pills, "Hide 0 templates" toggle, text search.
  - Filters persist as removable chips.
  - Scatter/Table view toggle (table is sortable by clicking column headers).
  - Assessed/Predicted quality toggle (mocked ORES — randomly perturbs quality ±1 class).
  - School group headers (Engineering, Science, Humanities, etc.) in the main table (NOT the scatterplot — the scatterplot shows departments).
  - SSH tunnel to `enwiki_p` — working, credentials in `.env`.
  - Action links in detail panel: "Read article", "Edit page" (direct to Wikipedia source editor).
  
- **What is partially built:**
  - Live query server (`scripts/impact-matrix-server.py`) — works when SSH tunnel is up, but the tunnel process management is unreliable in this environment. The server's `enrich_pageviews()` function uses the REST API which should be more tolerant with the compliant User-Agent, but Popular pages are still preferred.
  - Detail panel spec (`notes/detail-panel-spec.md`) — closely matches implementation. Minor differences: quality gap indicator was added, the "short description" row was simplified.
  
- **What is broken or blocked:**
  - The live query server process keeps dying because the bash tool kills background processes. The server can only be kept alive through a `task` subagent. Not suitable for production use.
  - `origin=*` CORS parameter on `action=parse` does NOT work from `file://`. JSONP via `<script>` tag also fails. This is WHY wikitext context is pre-computed during data generation rather than fetched client-side.
  
- **What has NOT been started yet:**
  - MIT Mode toggle (OCW match overlay on bubbles, "Has OCW match" filter, Wikipedia Bridge tab in detail panel).
  - Aggregate "all 25 OCW projects" dashboard.
  - Data generation script extraction (currently inline heredocs — no standalone `.py` file).
  - Standalone build command extraction (currently a 4-line Python one-liner).
  - Citation snippet builder (pre-fill `{{cite web}}` for OCW courses).
  - Popular pages request tool for missing WikiProjects.

### 3. ARCHITECTURE & TECHNICAL MAP

- **Tech stack / tools / platforms:**
  - Python 3.14 — data generation, SQL queries, wikitext parsing
  - JavaScript (vanilla) + D3.js v7 (CDN) — browser visualization
  - MariaDB (`enwiki_p` via SSH tunnel to Toolforge) — article assessments, templates, page metadata
  - Wikimedia REST API (`action=parse`) — Popular pages fetching, wikitext fetching
  - mwparserfromhell — wikitext AST parsing for template context extraction
  - pymysql — SQL connection to enwiki_p
  - python-dotenv — credential loading from `.env`
  - ssh — tunnel to `login.toolforge.org`

- **Key data structures, tables, files, or repos:**
  - `wiki/impact-matrix/standalone.html` — self-contained tool (~1.7 MB)
  - `wiki/impact-matrix/index.html` — source HTML (loads `live-data.js` externally)
  - `wiki/impact-matrix/data/live-data.js` — pre-computed data as `var LIVE_DATA = {...}`
  - `scripts/impact-matrix-server.py` — live query server (requires SSH tunnel)
  - SQL tables used: `page`, `page_assessments`, `page_assessments_projects`, `page_props`, `templatelinks`, `linktarget`
  - Data per article: `{title, views, quality, importance, templates[], short_desc, touched, page_len, ctx[]}`
  - Context per template: `{name, section, date, context (sentence), contextType}`

- **How the system works end-to-end:**
  1. For each WikiProject, fetch Popular pages via `action=parse&page=Wikipedia:WikiProject_{name}/Popular_pages&prop=text`. Parse the rendered HTML `<table class="wikitable">` with regex to extract Rank, Title, Views, DailyAvg, Assessment (as `[[:Category:X-Class articles|X]]`), Importance (as `[[:Category:X-importance articles|X]]`).
  2. For each article, batch-query templates from SQL via SSH tunnel. Two queries: (a) article-body templates from `templatelinks → linktarget` with 20 known aliases, (b) talk-page templates from `templatelinks → linktarget` via `page` join to namespace 1 with 7 known aliases. Process: `tl_target_id → linktarget.lt_id WHERE lt.lt_namespace=10 AND lt.lt_title IN (...)`. Batch size: 50.
  3. Batch-query short descriptions (`page_props WHERE pp_propname='wikibase-shortdesc'`), last edit date (`page.page_touched`), and article size (`page.page_len`).
  4. For each article that has templates, fetch its raw wikitext via `action=parse&prop=wikitext`. Parse with `mwparserfromhell.parse()`. Use `ifilter_templates(recursive=True)` to find matching templates. IMPORTANT: deduplicate by text position — `ifilter_templates` returns the same template in parent AND child sections. For each unique template, extract: section name (iterate `get_sections(flat=True)`, find which section contains the template), date parameter (`tmpl.get('date')`), preceding sentence (last `\n\n` before template position within 500 chars), context type (classifier below).
  5. Context type classification (in order of precedence): if last unmatched `<ref` before template > last unmatched `</ref>` → "footnote" (checks the FULL wikitext before position, not a 500-char window). If `{{Infobox` in 500 chars before → "infobox". If wikitable markers in 500 chars → "table". If `<blockquote` or `{{Quote` in 500 chars → "blockquote". If extracted context <20 chars → "minimal". Otherwise → "inline".
  6. Merge all data into `var LIVE_DATA = {...}` and write to `wiki/impact-matrix/data/live-data.js`.
  7. Build standalone: Python script reads `live-data.js`, reads `index.html`, replaces `<script src="data/live-data.js"></script>` with inline `<script>var LIVE_DATA = ...</script>`, writes `standalone.html`.
  8. In the browser, the HTML loads D3.js from CDN, reads the embedded LIVE_DATA, renders the scatterplot, and handles all interactions client-side.

- **Naming conventions or standards in use:**
  - Wikitext template names: use underscores in SQL (`Citation_needed`), convert to spaces for display (`Citation needed`).
  - WikiProject names: use underscores in URLs (`Computer_science`), use spaces in the UI (`Computer science`).
  - Context type values: lowercase single words (`inline`, `footnote`, `infobox`, `table`, `blockquote`, `minimal`).
  - User-Agent: single consistent string across all Wikimedia API calls (see Hard Constraints above).

- **External dependencies:**
  - D3.js v7 — loaded from CDN (`d3js.org`). The standalone HTML does NOT work offline.
  - mwparserfromhell — Python library for wikitext parsing. Requires C compiler to install. Already installed.
  - pymysql — Python MySQL driver. Already installed.
  - Toolforge SSH tunnel — requires active SSH key and `.env` credentials.

### 4. RECENT WORK — WHAT JUST HAPPENED (HIGH PRIORITY)

- **What was worked on in this session:**
  - Built the entire Contribution Impact Matrix from scratch: scatterplot, detail panel, filters, table view, slider, color scale.
  - Documented pageview data issues — tried 3 approaches (SQL page_props, REST API monthly, REST API daily), all failed. Resolved with WikiProject Popular pages.
  - Refined the detail panel with pre-computed wikitext context (section name, date, sentence context, 6 context classifiers).
  - Fixed `<ref>` detection bug: was checking 500-char window for `</ref>` (false positives when a `</ref>` happened to be near an inline `{{cn}}`). Fixed by checking last unmatched `<ref` vs `</ref>` in the FULL text before the template.
  - Fixed template name matching: added both space and underscore variants to the matching list.
  - Fixed `ifilter_templates` duplicate issue: deduplicated by text position.
  - Fixed Popular pages fetch URL encoding for projects with spaces (`Computer science` → `Computer_science`).
  - Created template explanations object (25 template aliases with descriptions).
  - Built template filter pills (All, Citation, Refimprove, Technical, Missing, Sources).
  - Added "Hide 0 templates" toggle with removable chip.
  - Moved rank slider from full-width div to inline in header bar.
  - Refined color scale from original yellow/orange/red to green/yellow/orange/red/maroon.
  - Added right margin to X axis to prevent bubble clipping.
  - Documented everything: DESIGN.md, HANDOFF.md, PRD updates, README updates.
  - Tagged v0.1.
  - Established SSH tunnel to enwiki_p and verified queries work.

- **What decisions were made and WHY:**
  
  1. **Popular pages over REST API for pageviews** — The REST API was rate-limiting our initial tests (~15 req/min) before we added a compliant User-Agent. With the proper UA, limits are more lenient. But Popular pages still win: 1 API call returns 500-1000 articles with views, quality, AND importance, vs 1,000+ individual API calls for the same data. Tradeoff: only ~500 of ~1,500 WikiProjects have Popular pages enabled.
  
  2. **Pre-computed wikitext context over client-side fetch** — `fetch()` is blocked from `file://` by CORS. JSONP via `<script>` tags also fails. The ONLY reliable approach is to parse wikitext during data generation with mwparserfromhell and store the results. Tradeoff: data generation is slower (one API call per templated article, ~25-35 min for 8 projects), data size is ~1.7 MB instead of ~1.1 MB.
  
  3. **HTML table parsing (regex) for Popular pages over mwparserfromhell** — The Community Tech bot generates these tables with stable, predictable HTML. MediaWiki's wikitable rendering hasn't changed in over a decade. Using mwparserfromhell would require parsing the wikitext of the Popular pages page, which has additional templates and markup that complicate extraction. The HTML table regex is simpler and more robust for THIS specific machine-generated table.
  
  4. **Standalone HTML over live server** — The bash tool kills background processes when shell commands time out. `nohup`, `disown`, `setsid` all failed. Only a `task` subagent kept the server alive, which is fragile. A self-contained HTML file with all data embedded has zero operational dependency. Tradeoff: no ad-hoc query capability.
  
  5. **Last-unmatched `<ref` check over 500-char window** — The original 500-char window approach flagged `{{cn}}` tags as "footnote" when a `</ref>` happened to be within 500 characters but its matching `<ref` was outside the window. Checking the full wikitext before the template position for the last unmatched opener vs closer correctly determines actual containment inside a `<ref>` block. Verified on Parthenogenesis article (2 inline `{{cn}}`, 0 footnote — was 4 footnote, 2 inline with duplicates).
  
  6. **Deduplicate mwparserfromhell templates by text position** — `ifilter_templates(recursive=True)` walks the parsed tree depth-first, returning the same template node when it's contained in both a parent section and a subsection. Deduplicating by `full.indexOf(str(tmpl))` with a `seen_positions` set eliminates duplicates.

- **What changed in the system:**
  - Extracted and stored: `wiki/impact-matrix/data/live-data.js` (pre-computed data for 8 projects)
  - Built: `wiki/impact-matrix/standalone.html` (self-contained tool, 1.7 MB)
  - Built: `wiki/impact-matrix/index.html` (source HTML)
  - Built: `scripts/impact-matrix-server.py` (live query server)
  - Added: `DESIGN.md`, `HANDOFF.md`, `PRD-CONTRIBUTION-IMPACT-MATRIX.md`
  - Added: `notes/pageview-data-issues.md`, `notes/detail-panel-spec.md`
  - Updated: `README.md`, `_checkpoint.json`, `.gitignore`, `wiki/log.md`
  - Updated: `.claude/skills/wikimedia-pageviews/SKILL.md`, `WIKIMEDIA_PAGEVIEWS.md` (User-Agent string)
  - Removed: ~110 lines of client-side JS (wikitext parser, JSONP fetch) — replaced with pre-computed data
  - Tagged: `v0.1-impact-matrix`

- **What was discussed but NOT yet implemented:**
  - MIT Mode toggle (OCW overlay on bubbles, project restriction, Wikipedia Bridge tab)
  - Aggregate "all 25 OCW projects" dashboard
  - Citation snippet builder
  - Linear pageview scale toggle (currently log-only)
  - "Copy as markdown table" export
  - Popular pages request tool for missing WikiProjects
  - Requesting WikiProjects to be added to the Community Tech bot's Popular pages generation
  - Live query server as a permanent Toolforge tool

- **Open threads or unresolved questions:**
  - The `Rs?` template alias was requested by the user but doesn't match any articles. May need different canonical form (`Rs` without `?`).
  - The `Cite` template alias was queried but never matched — may be a different template entirely.
  - Some context types classified as "table" may actually be list items. The heuristic checks for `{|` in 500 chars, which is a wikitable marker. Lists use `*` or `#` which aren't detected.
  - Article short descriptions only cover ~26% of articles via `wikibase-shortdesc`. The remaining 74% silently omit the line in the detail panel.

### 5. WHAT COULD GO WRONG

- **Known bugs or issues:**
  - The data generation takes 25-35 minutes for 8 projects. The SSH tunnel can drop during this time, causing SQL queries to fail midway. If this happens, check the tunnel with `nc -z 127.0.0.1 3306` and restart the generation from scratch (no incremental resume).
  - `mwparserfromhell` may fail to parse certain articles with malformed wikitext. The generation script catches these with `try/except` and leaves `ctx: null` for that article. Currently ~880 templated articles, ~859 with context (~21 failures). These are silently skipped.
  - The Popular pages API call may fail for WikiProjects with very large pages (Medicine has ~1000 articles, works fine). Error handling catches this and returns None.
  - The "Assessed" vs "Predicted" quality toggle uses a mock that randomly perturbs quality ±1 class. This is NOT connected to real ORES data. The toggle exists for UI prototyping only.

- **Edge cases to watch for:**
  - WikiProjects with spaces in the name: the Popular pages URL path uses underscores (`Computer_science`), but the `fetch_popular_pages` function in the server script must `quote()` the page title. The data generation script does `proj.replace('_',' ')` for the Popular pages API call but `proj` is already the display name.
  - Article titles with special characters (e.g., `El Niño–Southern Oscillation` with `–` en-dash, not `-` hyphen). These work in the Popular pages table but may cause issues in the wikitext fetch URL. The `quote()` function handles encoding correctly.
  - Template names in `lt.lt_title` use underscores (`Citation_needed`). The `.replace('_',' ')` converts to display names. But the matching in the detail panel and the JS `TEMPLATE_EXPLANATIONS` must use the display name format (with spaces). Both the space and underscore variants are checked.
  - The `ifilter_templates(recursive=True)` duplicate issue means the same template can appear multiple times in the context array. The deduplication by text position handles this, but only if the same text position isn't reused across different templates from different sections (which shouldn't happen).

- **Technical debt or shortcuts taken:**
  - The data generation script is an inline heredoc executed in the session, not a standalone `.py` file. Must be extracted for reproducibility.
  - The standalone build is a 4-line Python one-liner, not a script. Must be extracted.
  - The "Predicted" quality toggle uses a mock (random perturbation ±1 class). Real ORES data would require the LiftWing API.
  - Template explanations are hardcoded in `TEMPLATE_EXPLANATIONS` — 25 entries. New templates need manual additions.
  - The color scale thresholds `[1, 2, 3, 4]` and color hex values are hardcoded in two places: `TEMPLATE_COLORS` definition and `renderLegend()`. Both must be updated together.
  - D3.js v7 is loaded from CDN. The standalone HTML is not fully offline.
  - The school group headers are hardcoded in the `processData` function (not present — actually the school grouping only exists in the server script's `WIKIPROJECT_DEPT_MAP`, NOT in the standalone HTML. The standalone HTML shows all departments flat, not grouped by school. Correction: the earlier heatmap has school grouping. The Impact Matrix does NOT have school group headers in its current state.)
  
  ⚠️ CORRECTION: The school group headers are in the CROSSREF HEATMAP (`wiki/reports/crossref-heatmap.html`), NOT in the Contribution Impact Matrix. The Impact Matrix shows departments flat without grouping. Do NOT confuse the two tools.

- **Assumptions being made that could be wrong:**
  - That Popular pages will continue to be generated by the Community Tech bot. If the bot stops running, the primary data source disappears.
  - That the `linktarget` table structure won't change. It was migrated from `templatelinks.tl_title` — a future migration could change it again.
  - That `action=parse&prop=text` with a `wikitable` class selector will continue to produce the same HTML structure. MediaWiki upgrades COULD change CSS class names or table rendering.
  - That the 150-character truncation for sentence context is sufficient. Very long sentences are truncated with `...` which may lose the actual claim that needs citation.

### 6. HOW TO THINK ABOUT THIS PROJECT

1. **What is the core architectural pattern or design philosophy, and why was it chosen?**

   The core pattern is **pre-generate everything, serve statically**. Every piece of data that the tool needs — pageviews, templates, metadata, wikitext context — is fetched and processed during an offline data generation phase. The browser receives a single self-contained HTML file with all data embedded. No runtime API calls. No server. No database connections from the browser.

   This was chosen because the `file://` protocol (which is how users will open the standalone HTML) blocks ALL network requests: `fetch()`, `XMLHttpRequest`, even JSONP `<script>` tags. The Wikimedia API also has rate limits that make live queries unreliable for more than a handful of articles.

   The tradeoff is that adding new data (new WikiProjects, refreshed pageview counts) requires re-running the generation pipeline rather than happening live. For a tool meant to be used periodically (not real-time), this is acceptable.

2. **What is the most common mistake a new person working on this would make?**

   The most common mistake would be to try to make the browser fetch data at runtime — either by querying the Wikipedia API directly from the browser, or by setting up a local server. Both approaches have been tried and failed:
   - `fetch()` from `file://` → CORS blocked
   - JSONP via `<script>` → callback never executed from `file://`
   - Live Python server → process management unreliable in this environment

   The correct approach is ALWAYS: fetch data during the generation step (Python + SSH tunnel + API calls), store it in the HTML, and then the browser just renders.

   A close second: trying to use `page_props.pageview_daily_average` in SQL queries. It has 0 rows in `enwiki_p`. Don't use it.

3. **What looks like it should be refactored or redesigned but intentionally should NOT be? Why?**

   - **The Popular pages HTML parsing** might look like it should use mwparserfromhell on the wikitext instead of regex on HTML. But the Popular pages table is bot-generated, not hand-edited. HTML regex on a bot-generated wikitable is actually MORE stable than wikitext parsing (which would need to handle the `{{FORMATNUM:}}`, `{{Tabbed header}}`, and wiki-magic on the page). The current approach has worked correctly for all 8 projects tested.
   
   - **The client-side JS** might look like it could be modularized into separate files (data loader, renderer, filter, detail panel). But the standalone HTML needs to be a single file for portability. Splitting would require a build step or a server. Not worth it at this scale (~1,500 lines of JS).
   
   - **The color scale** might look like it should be a dynamic range (e.g., d3.interpolateReds) instead of hardcoded thresholds. But the user explicitly wanted distinct, discrete categories (0, 1, 2, 3, 4+) with specific meaning per count. A continuous gradient would lose this semantic precision.

### 7. DO NOT TOUCH LIST

- Do NOT refactor the data pipeline to use client-side API calls. Pre-generation is the correct pattern for this use case.
- Do NOT attempt to query `page_props.pageview_daily_average` — it has 0 rows in `enwiki_p`. Use Popular pages.
- Do NOT remove the template deduplication by text position — `ifilter_templates(recursive=True)` WILL produce duplicates.
- Do NOT use `tl_title` directly from `templatelinks` — it's been migrated to `linktarget`; you must join through `tl_target_id`.
- Do NOT change the User-Agent string — it's the project's compliance mechanism with Wikimedia's API terms.
- Do NOT commit the `.env` file — it contains Toolforge SQL credentials.
- Do NOT change the `DOMAIN = [1, 2, 3, 4]` thresholds or add/remove colors without also updating `renderLegend()` — they must stay in sync.
- Do NOT change `origin=*` to `callback=` for wikitext fetching expecting it to work from `file://` — JSONP was tried and failed.
- Do NOT confuse the Contribution Impact Matrix (this project) with the crossref heatmap (`wiki/reports/crossref-heatmap.html`) — they are separate tools with separate codebases. The heatmap is OCW-specific; the Impact Matrix is generic.
- Ask before introducing new npm packages, Python libraries, or external services.

### 8. CONFIDENCE & FRESHNESS

| Section | Confidence | Notes |
|---------|------------|-------|
| 1. Project Identity | ✅ HIGH | Established at the start of this session, verified throughout |
| 2. What Exists Right Now | ✅ HIGH | Built and tested this session |
| 3. Architecture & Technical Map | ✅ HIGH | All patterns verified this session (except server script — see DESIGN.md) |
| 4. Recent Work | ✅ HIGH | Documented as it happened |
| 5. What Could Go Wrong | ⚠️ MEDIUM | Some edge cases (malformed wikitext, special characters) tested but not exhaustively |
| 6. How to Think About This Project | ✅ HIGH | Core philosophy established through multiple failed alternatives |
| 7. Do Not Touch List | ✅ HIGH | Each rule was learned the hard way this session |
| 8. Confidence & Freshness | ✅ HIGH | Self-assessment |

---

## RESUME PROMPT

Copy and paste this into a brand new AI session to resume the project:

```
You are resuming work on the MIT OCW LLM Wiki — Contribution Impact Matrix project.

FIRST: Read the attached file `AI_Continuation_Document-11May2026-1130.md` in FULL. Do NOT skip it. The document contains critical constraints, decisions, and session-specific knowledge that are NOT in any other project file.

SECOND: Check for a USER DIRECTIVE below. If present, prioritize it over the next actions in the continuation document.

THIRD: After reading, provide:
1. A 3-5 sentence summary of your understanding of the current project state.
2. The single next action you will take, based on the continuation document's priority list and any user directive.
3. Ask clarification questions ONLY if something in the continuation document is contradictory or if the user's directive is ambiguous.

Then begin working.

USER DIRECTIVE:
(Add your instruction here — e.g., "Extract the data generation script from the inline heredoc into scripts/generate-impact-matrix-data.py" or "Continue with the P0 items from section 4.")
```
