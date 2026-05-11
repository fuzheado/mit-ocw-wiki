# MIT OCW LLM Wiki

A living, interlinked knowledge base of MIT OpenCourseWare's 2,500+ courses, built incrementally by an LLM agent following the [LLM Wiki pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f).

Courses are ingested from the [MIT Learn API](https://api.learn.mit.edu) and cross-referenced against Wikipedia to identify where MIT's open-licensed educational materials can improve articles. The wiki is maintained as markdown files, compiled into a browsable site by the WikiWise app.

## Status

- **Courses discovered:** 2,577 (all ingested)
- **Courses asset-scanned:** ~2,500+ (hybrid scan)
- **Departments:** 37 | **Topics:** 110 | **Instructors:** 2,142
- **Stages:** Bootstrap (0-2) ✅ | Asset scan (3) ✅ | Wikipedia crossref (4) — crossref tool built, heatmap demo live, Contribution Impact Matrix prototype live

## What's built

| Layer | Status | Details |
|-------|--------|---------|
| Course ingest | ✅ | All 2,577 courses via batch API |
| Course pages | ✅ | YAML frontmatter with canonical metadata |
| Department/topic pages | ✅ | 37 depts, 110 topics with cross-links |
| Instructor index | ✅ | 2,142 instructors, A-Z grouped |
| Hybrid asset scan | ✅ | API + URL deep scan, merged with type correction |
| Video detection | ✅ | YouTube, OCW player, MP4, Dropbox, thumbnails |
| Grouped lecture format | ✅ | One line per lecture with inline format badges |
| Pre-commit hook | ✅ | Auto-rebuilds index on wiki changes |
| Wikipedia crossref strategy | ✅ | Three-tier matching, unified SQL query, scoring model |
| Interactive crossref heatmap | ✅ | 9 WikiProjects × 18 OCW departments, live demo |
| **Contribution Impact Matrix** | ✅ **Prototype** | Bubble scatterplot visualization for any WikiProject |
| **Standalone HTML** | ✅ | Self-contained, works from `file://`, no server needed |

## Key features

### Contribution Impact Matrix

A D3.js bubble scatterplot for exploring any WikiProject's articles by quality, pageviews, importance, and maintenance templates. Located at `wiki/impact-matrix/standalone.html`.

- **Generic mode** (default): pick any WikiProject with Popular pages, see all articles
- **Live data pipeline**: Popular pages (pageviews + quality + importance) + SQL (maintenance templates)
- **Four dimensions**: Quality (X), Pageviews (Y, log scale), Importance (bubble size), Template count (color)
- **Interactions**: Hover tooltips, click for detail panel, sortable table view
- **Filters**: Quality, importance, template type, text search
- **Quality toggle**: Assessed (SQL) ↔ Predicted (mocked ORES)
- **Quadrant overlay**: Sweet Spots, Stars, Sleepers, Tail

### Pageview data: key finding

The `enwiki_p` analytics replica does not contain pageview data (`page_props.pageview_daily_average` has 0 rows). The Wikimedia REST API rate-limits aggressively (~15 req/min on the monthly endpoint). **Resolution:** use WikiProject Popular pages — pre-compiled tables maintained by the Community Tech bot — which include accurate monthly view counts for the top 1,000 articles per project. See `notes/pageview-data-issues.md` for details.

## Quick start

```bash
# Open in your LLM agent (Claude Code, Codex, etc.)
cd /path/to/mit-ocw-wiki
claude

# The agent reads CLAUDE.md and knows the project state
```

## Key commands

```bash
# Ingest a single course + asset scan
python3 scripts/scan-assets.py --hybrid {slug}

# With skip-scanned flag (for batch reprocessing)
python3 scripts/scan-assets.py --hybrid --skip-scanned {slug}

# Generate crossref demo reports
python3 scripts/crossref-wikipedia.py --report --demo

# Regenerate index
python3 scripts/regenerate-index.py
```

## Structure

- `CLAUDE.md` — agent instructions and project schema
- `CROSSREF-STRATEGY.md` — Wikipedia matching strategy with unified SQL query
- `TECHNICAL.md` — architecture, data sources, scan modes, video detection patterns
- `raw/` — immutable API source data
- `wiki/` — LLM-maintained markdown pages (courses, departments, topics, instructors, crossrefs, reports)
- `site/` — WikiWise build tooling
- `scripts/` — ingest-batch.py, scan-assets.py, regenerate-index.py, crossref-wikipedia.py
- `.claude/skills/` — skill files for Wikimedia database access, page assessments, pageviews

## Project files

| File | Purpose |
|------|---------|
| `OCW-LLM-WIKI.md` | Main schema: Normalization Protocol, asset typing, lint rules |
| `OCW-LLM-WIKI-GIT.md` | Version control best practices |
| `OCW-LLM-WIKI-EXECUTION.md` | Staged execution plan with checkpoint resume |
| `CROSSREF-STRATEGY.md` | Wikipedia cross-reference strategy and unified SQL query design |
| `TECHNICAL.md` | Technical architecture and scan mode comparison |

## License

The wiki metadata and structure are MIT. Course content referenced is CC BY-NC-SA 4.0.
