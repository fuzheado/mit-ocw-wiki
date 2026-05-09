# OCW LLM Wiki — Technical Overview

## Architecture

Three layers following the [LLM Wiki pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f):

```
raw/          Immutable source data from the MIT Learn API (JSON)
wiki/         LLM-generated markdown pages (the living artifact)
CLAUDE.md     Schema file telling the LLM how to maintain the wiki
```

## Data Source

**MIT Learn API** — `https://api.learn.mit.edu/api/v1/`

- Public, no auth required
- 2,577 OCW courses (filtered by `offered_by=ocw`)
- Paginated: 100 per page, 26 pages total
- Returns structured JSON with topics, departments, instructors, runs, course numbers
- Key insight: course readable IDs use format `{number}+{semester}_{year}` (e.g., `1.018J+fall_2009`)

**Known limitation:** Very new courses (e.g., RES.ENV-007 from Jan 2025) may not be indexed. Fall back to HTML scraping from `https://ocw.mit.edu/courses/{slug}/`.

## Wiki File Structure

| Directory | Purpose | Count |
|-----------|---------|-------|
| `wiki/courses/` | One page per course | ~2,577 when complete |
| `wiki/departments/` | 37 MIT departments | 37 |
| `wiki/topics/` | 110 topics (hierarchical) | 110 |
| `wiki/instructors/` | One page per instructor | grows with courses |
| `wiki/index.md` | Agent catalog of all pages | 1 |
| `wiki/log.md` | Append-only chronological log | 1 |
| `wiki/overview.md` | Top-level synthesis | 1 |

## Page Schema

Every course page has YAML frontmatter per the Normalization Protocol (Rule 1.1):
- `url`, `course_id`, `title`, `year_published`, `instructors`, `level`, `department`, `topics`, `license`, `views`, `completeness`, `last_modified`, `type`

All fields required. Missing values → `Unknown` + `FIXME` tag. Never invent metadata.

## Wikilink Convention

The WikiWise build system resolves links by **filename slug only** — path is ignored.
- File at `wiki/courses/15-071-the-analytics-edge-spring-2017.md` → slug `15-071-the-analytics-edge-spring-2017`
- Link as `[[15-071-the-analytics-edge-spring-2017|The Analytics Edge]]`, never as `[[courses/15-071.md]]`

## Ingestion Workflow

### Batch script
```bash
python3 scripts/ingest-batch.py --offset 0 --limit 100
```

The script:
1. Fetches one API page (100 courses)
2. For each course: extracts Canonical Course Object, writes `wiki/courses/{slug}.md`
3. Appends course links to department pages (creates if new)
4. Appends course links to topic pages (creates if new)  
5. Creates instructor pages (appends to existing if already known)
6. Saves raw JSON to `raw/api/courses-page-{offset}.json`
7. Commits locally with message `ocw: ingest batch offset={N}`

### Checkpoint system
`_checkpoint.json` tracks progress across sessions:
- `stages.courses_bootstrap.last_offset` — resume point
- `stages.courses_bootstrap.batches_done` — progress counter
- `stats.courses_in_wiki` — total pages created

### Ad-hoc single course
For individual courses (not in batch), fetch by readable_id:
```
GET /api/v1/courses/?offered_by=ocw&readable_id={id}%2B{semester}_{year}
```

## Wikipedia Cross-Reference (Stage 4, not yet run)

Planned approach:
- Match courses to Wikipedia articles by topic name, course title keywords, department
- Generate `{{cite web}}` citation templates for each match
- Flag `[Visual-Rich]` assets for Wikimedia Commons eligibility
- Flag `[Source-Rich]` reading lists for Wikipedia "Further reading" sections

## Tools

| Tool | Purpose |
|------|---------|
| WikiWise app | Local viewer, auto-recompiles on file changes |
| `scripts/ingest-batch.py` | Batch course ingestion |
| `touch .rebuild` | Force WikiWise full recompile |
| `.claude/active-file` | Tracks which page user is viewing |

## Git Strategy

- Commits after each batch with prefix `ocw:`
- No auto-push (slow)
- Push manually when convenient
- Branch for experiments (alternate topic hierarchies, crossref strategies)
