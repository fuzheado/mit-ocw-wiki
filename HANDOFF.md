# Handoff: Contribution Impact Matrix (v0.1)

## 1. What we built

- **Contribution Impact Matrix** — D3.js bubble scatterplot for exploring any WikiProject's articles by quality, pageviews, importance, and maintenance templates. Self-contained HTML at `wiki/impact-matrix/standalone.html` (~1.7 MB, works from `file://`).
- **Data pipeline** — 8 WikiProjects × 500-1000 articles = 6,500 articles with pageviews, templates, short descriptions, page metadata, and pre-computed wikitext context. Data in `wiki/impact-matrix/data/live-data.js`.
- **SSH tunnel** — Working connection to `enwiki_p` (MariaDB analytics replica). Credentials in `.env`.
- **Detail panel** — Click a bubble to see section name, template date, sentence context, quality gap indicator, read/edit links. No runtime API calls.
- **v0.1 tagged** as `v0.1-impact-matrix`.

## 2. Key session-specific knowledge (not in other docs)

These are things a new agent would need to know that aren't captured in `DESIGN.md` or `PRD`:

- **Data generation script is inline** — The Python script that fetches Popular pages, runs SQL, and parses wikitext with mwparserfromhell was executed as multiple inline heredocs. There is no standalone `.py` file for it yet. To regenerate data, you must reconstruct the heredoc or extract it into `scripts/generate-impact-matrix-data.py`.
- **`templatelinks` schema changed** — The table no longer has `tl_title`. It uses `tl_target_id` which joins to `linktarget.lt_id` where the actual title lives. This applies to ALL Wikimedia replica queries.
- **`pageview_daily_average` doesn't exist** in `enwiki_p`. Zero rows. The REST API rate-limits improved after we added a compliant User-Agent, but Popular pages are still the preferred source (1 API call vs 1,000+).
- **Popular pages are fetched via `action=parse` with `prop=text`** (rendered HTML), not `prop=wikitext`. Parsed with regex on `<table class="wikitable">`. This works because the bot output is stable but is intentionally not using mwparserfromhell (see DESIGN.md for rationale).
- **Wikitext for individual article context** was fetched via `action=parse&prop=wikitext` during data generation. The client-side JS approaches (`fetch()` with CORS, JSONP) both failed from `file://` — this is why context is pre-computed.
- **mwparserfromhell `ifilter_templates(recursive=True)` returns duplicates** — same template appears in parent and child sections. Must deduplicate by text position.
- **`Overly_technical`, `Needs_diagram`, `Scientific_verification`** don't exist in the `linktarget` table. They're in the query list but never match.
- **The standalone rebuild command** is a 4-line Python script that replaces `<script src="data/live-data.js"></script>` with inline `<script>` containing the data. Not yet a dedicated script.
- **MIT Mode** is a planned feature but no code exists yet. The existing code is Generic Mode only.

## 3. Repository structure (impact-matrix specific)

```
wiki/impact-matrix/
  standalone.html    ← Self-contained tool. Open this.
  index.html         ← Source HTML (loads live-data.js externally)
  data/
    live-data.js     ← Pre-computed data (8 projects, 6,500 articles)
scripts/
  impact-matrix-server.py  ← Live query server (needs SSH tunnel + .env)
notes/
  pageview-data-issues.md  ← Pageview API limitations
  detail-panel-spec.md     ← Detail panel spec
DESIGN.md                   ← Architecture, data flow, key decisions
PRD-CONTRIBUTION-IMPACT-MATRIX.md  ← Product requirements
```

Other relevant scripts:
- `scripts/crossref-wikipedia.py` — Earlier OCW crossref tool. Separate concern (OCW-specific). Not needed for the generic Impact Matrix.
- `.claude/skills/wikimedia-database/SKILL.md` — SSH tunnel setup guide.

## 4. Next actions (recommended order)

| Priority | Action | Details |
|----------|--------|---------|
| P0 | Extract data generation script | The inline heredoc into `scripts/generate-impact-matrix-data.py`. Makes the pipeline reproducible. |
| P0 | Extract standalone build command | The 4-line inline Python into `scripts/build-standalone.sh` or add a `--build` flag to the data generator. |
| P1 | Live query server reliability | The server works but the SSH tunnel is fragile. Consider a systemd service or Docker container if deploying. |
| P2 | MIT Mode toggle | Add OCW match overlay: filter by OCW-aligned projects, show course data on bubbles, add Wikipedia Bridge tab to detail panel. |
| P2 | Add more WikiProjects | Run the data generation for all ~500 projects with Popular pages. Data size scales linearly (~200 KB per project). |
| P3 | Aggregate dashboard | View across all 25 OCW-aligned projects at once (small multiples or list). |
| P3 | Request Popular pages for missing projects | The Community Tech bot can enable Popular pages for any WikiProject on request. |
| P3 | Citation snippet builder | Pre-fill `{{cite web}}` template from OCW course metadata. |

## 5. Known issues and sharp edges

- **SSH tunnel dies unpredictably.** The `enwiki_p` connection can drop. The server logs `[impact-matrix]` prefix. Check with `nc -z 127.0.0.1 3306` and re-establish with the SSH command in the server script.
- **Popular pages only cover ~500 of ~1,500 WikiProjects.** For the rest, there's no pageview data and the project won't appear in the current data set.
- **Some articles have no short description** (~26% coverage via `wikibase-shortdesc`). The detail panel gracefully omits the short_desc line when absent.
- **Article wikitext fetching for context is the bottleneck in data generation.** 859 API calls for 859 templated articles. Each call takes ~1-2 seconds. Total generation time is ~25-35 minutes across 8 projects.
- **Color scale is hardcoded.** The threshold domain `[1, 2, 3, 4]` and color hex values are in `index.html` as `TEMPLATE_COLORS`. Change there and in `renderLegend()`.
- **D3.js is loaded from CDN.** The standalone HTML won't work offline. To make it fully offline, vendor D3.js locally.
- **The `origin=*` CORS parameter on `action=parse` does NOT work from `file://`.** This was the root cause of the "Loading context..." hang. The fix was to pre-compute context during data generation instead. JSONP also failed.
- **`file://` blocks `fetch()` entirely.** No network requests work from `file://` in Chromium-based browsers. The HTML must be served via HTTP for any runtime API calls.

## 6. Testing notes

- **Parthenogenesis** article (in Biology project) is a good test case for template context classification. Has multiple `{{cn}}` tags at end of sentences, none inside `<ref>` tags. Should show 0 footnote, 2 inline.
- **Earth Day** article (in Environment project) has both article-body and talk-page templates. Good for testing the full detail panel.
- **To verify data integrity**: Open the standalone HTML, click a bubble, check that the detail panel shows section name, date, and context without "Loading..." state.
- **To verify template counts match SQL**: Compare bubble colors in the scatterplot with the detail panel's template list. Green bubbles should have 0 templates listed.

## 7. Credentials

- `.env` file in project root contains Toolforge SQL credentials. **Do not commit.**
- SSH tunnel: `ssh -L 3306:enwiki.analytics.db.svc.wikimedia.cloud:3306 alih@login.toolforge.org -N`
- UA string for Wikimedia API calls: `'MIT OCW Bot/1.0 (https://meta.wikimedia.org/wiki/Wiki_MIT; andrew.lih@gmail.com) ContentGapResearch'`
