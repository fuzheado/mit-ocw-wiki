# MIT OCW LLM Wiki

A living, interlinked knowledge base of MIT OpenCourseWare's 2,500+ courses, built incrementally by an LLM agent following the [LLM Wiki pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f).

Courses are ingested from the [MIT Learn API](https://api.learn.mit.edu) and cross-referenced against Wikipedia to identify where MIT's open-licensed educational materials can improve articles. The wiki is maintained as markdown files, compiled into a browsable site by the WikiWise app.

## Status

- **Courses discovered:** 2,577 (all ingested from batch)
- **Courses asset-scanned:** ~2,500+ with hybrid (API + URL deep scan)
- **Asset types cataloged:** Video-Transcript, Lecture-Notes, Problem-Set, Reading-List, Syllabus, Assignment, Image-Gallery, Resource
- **Departments:** 37
- **Topics:** 110
- **Instructors tracked:** 2,142
- **Stages completed:** Bootstrap (0-2 complete), Asset scan (3 in progress), Wikipedia crossref (4 — strategy designed, demo built)

## What's built

| Layer | Status | Details |
|-------|--------|---------|
| Course ingest | ✅ Done | All 2,577 courses ingested via batch API pagination |
| Course pages | ✅ Done | YAML frontmatter with canonical metadata per course |
| Department/topic pages | ✅ Done | 37 departments, 110 topics with course cross-links |
| Instructor index | ✅ Done | 2,142 instructors in A-Z grouped index |
| Hybrid asset scan | ✅ Done | `--hybrid` mode merges API content files with URL deep scan |
| Video detection | ✅ Done | YouTube, OCW player, MP4, Dropbox, thumbnail extraction |
| Grouped lecture format | ✅ Done | One line per lecture with inline format badges (🎬⬇📄) |
| Log with wikilinks | ✅ Done | Clickable `[[slug|Title]]` entries in log |
| Pre-commit hook | ✅ Done | Auto-regenerates index on wiki changes |
| Wikipedia crossref strategy | 📋 Designed | Three-tier matching, SQL via Wikimedia replicas, scoring model |
| Demo crossref reports | ✅ Done | Summary, per-WikiProject detail, interactive heatmap |

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
