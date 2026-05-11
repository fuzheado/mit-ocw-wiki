# Agent Instructions

This is a wiki maintained by an LLM agent. Read `CLAUDE.md` for the full schema, conventions, and workflows.

This file exists so that **any** LLM coding agent — Claude Code, OpenAI Codex, Cursor, Windsurf, Copilot CLI, or others — can operate this wiki. If your agent reads `CLAUDE.md` natively (Claude Code does), great. If not, everything you need is here plus the skill files referenced below.

## Quick reference

- **`raw/`** — immutable source documents. Read-only.
- **`wiki/`** — LLM-maintained markdown pages. All edits here. Source summaries go in `wiki/sources/`.
- **`site/`** — build tooling and compiled output. `site/out/` is auto-generated.
- **`CLAUDE.md`** — the wiki schema. Your source of truth for how this wiki works.

## Key conventions

- Link with `[[wikilinks]]`. Bare filename, no path.
- Cite sources inline: `([[source-slug]])`.
- Wiki pages are short blog posts, not reference dumps. TL;DR first, then the argument.
- After any ingest, update `wiki/index.md` and append to `wiki/log.md`.
- Log entry format: `## [YYYY-MM-DD HH:MM] <op> | <title>`.
- Voice: opinionated, direct, declarative. Most pages under 800 words.

## Tool mapping

Skills reference Claude Code tool names. If you're running a different agent, use the equivalent:

| Claude Code | Codex CLI | Copilot CLI | Generic |
|---|---|---|---|
| `Read` | `read_file` | `read_file` | read a file |
| `Write` | `write_file` | `write_file` | write/create a file |
| `Edit` | `write_file` (partial) | `patch` | edit part of a file |
| `Bash(*)` | `shell` | `run_command` | run a shell command |
| `Glob` | `shell` + `find` | `run_command` + `find` | find files by pattern |
| `Grep` | `shell` + `grep`/`rg` | `run_command` + `grep` | search file contents |
| `Agent` (subagent) | N/A | N/A | do it inline |

When a skill says `allowed-tools: Bash(*) Read Write Edit Glob Grep`, that's Claude Code syntax. In other agents, just use whatever tools let you run shell commands and read/write files.

## Skills

Detailed skill files live in `.claude/skills/<name>/SKILL.md`. **Read the skill file before running a workflow** — it contains step-by-step instructions, shell commands, and rules.

### How to use skills

- **Claude Code**: Skills are auto-discovered from `.claude/skills/`. Invoke with `/ingest`, `/lint`, etc.
- **Codex / other agents**: Read the skill file manually — e.g., read `.claude/skills/ingest/SKILL.md` — then follow its instructions. The skill files are plain markdown with step-by-step workflows.

### Skill catalog

| Skill | Path | Purpose |
|---|---|---|
| **ocw-ingest** | `.claude/skills/ocw-ingest/SKILL.md` | Bulk-ingest OCW courses from the MIT Learn API with pagination, checkpoint resume, and batch commits |
| **ingest** | `.claude/skills/ingest/SKILL.md` | Add a source to the wiki — save raw, create summary page, propagate claims, update index and log |
| **digest** | `.claude/skills/digest/SKILL.md` | Deep-propagate ingested sources across the wiki — update concept/entity pages, flag contradictions, create new pages where warranted |
| **lint** | `.claude/skills/lint/SKILL.md` | Health-check for contradictions, orphan pages, broken links, stale claims, missing cross-links |
| **wikimedia-database** | `.claude/skills/wikimedia-database/SKILL.md` | SSH tunnel to Wikimedia database replicas for direct SQL queries (enwiki_p, wikidata, commons) |
| **wikimedia-page-assessment** | `.claude/skills/wikimedia-page-assessment/SKILL.md` | Query article quality (FA/GA/B/C/Start/Stub) and importance ratings from page_assessments tables |
| **wikimedia-pageviews** | `.claude/skills/wikimedia-pageviews/SKILL.md` | Retrieve cached pageview averages (via SQL page_props) or precise historical data (via REST API) |
| **ingest-tweets** | `.claude/skills/ingest-tweets/SKILL.md` | Search Twitter/X for tweets on a topic using browser automation, extract content, and ingest into the wiki |
| **import-readwise** | `.claude/skills/import-readwise/SKILL.md` | Search and import documents/highlights from Readwise (orchestrator — delegates to fetch skills below) |
| **fetch-readwise-document** | `.claude/skills/fetch-readwise-document/SKILL.md` | Stream a Reader document into `raw/` without loading the body into context |
| **fetch-readwise-highlights** | `.claude/skills/fetch-readwise-highlights/SKILL.md` | Vector-search highlights, grouped by parent doc, write to `raw/` |

### Workflow cheat sheet

These are abbreviated versions. Read the full skill files for details.

**Ingest an OCW course batch:**
1. Read `_checkpoint.json` to determine current offset
2. Fetch `GET /api/v1/courses/?offered_by=ocw&limit=100&offset={N}`
3. For each course: extract YAML frontmatter, write `wiki/courses/{slug}.md`, link from department/topic/instructor pages
4. Use `[[wikilinks]]` by slug only (filename, not path — the build system flattens by filename)
5. Update `wiki/index.md` with new course count
6. Update `_checkpoint.json` with new offset and counts
7. Append to `wiki/log.md` — `## [YYYY-MM-DD HH:MM] ocw-ingest | Batch offset={N} ({count} courses)`
8. Git commit with message `ocw: ingest batch offset={N}`

**Ingest a source (generic):**
1. Save raw source to `raw/<slug>.md`
2. Create source-summary page at `wiki/sources/<slug>.md` with frontmatter (`type`, `date`, `author`, `url`, `raw`)
3. Propagate claims into concept/entity pages with citations `([[slug]])`
4. **Cross-link aggressively** — add `[[wikilinks]]` FROM existing pages TO new pages (edit 2-3 related pages), and FROM new pages TO existing ones. No orphans.
5. Update `wiki/index.md` — add new pages with one-line summaries
6. Update `wiki/home.md` if the source changes the narrative
7. Append to `wiki/log.md` — `## [YYYY-MM-DD HH:MM] ingest | <title>`

**Lint the wiki:**
1. Scan `wiki/` for contradictions, orphan pages, broken `[[wikilinks]]`, stale claims, missing cross-links
2. Check OCW-specific: link rot (dead OCW URLs → suggest Wayback Machine), missing Wikipedia Bridges, inconsistent frontmatter
3. Report findings grouped by category
4. Append to `wiki/log.md` — `## [YYYY-MM-DD HH:MM] lint | <summary>`

**Cross-reference against Wikipedia (Stage 4):**
1. Read `CROSSREF-STRATEGY.md` for the full matching strategy
2. Establish SSH tunnel per `wikimedia-database` skill
3. For each OCW topic, query matching WikiProject via `page_assessments` and `page_assessments_projects` tables
4. Filter by quality gaps (Stub/Start/C-class), importance, pageview averages, and maintenance templates
5. Score candidate articles against OCW course assets and lecture titles
6. Generate Wikipedia Bridge sections and `wiki/crossrefs/` hub pages

**Ingest tweets:**
1. Open Twitter/X search via browser automation
2. Scroll and extract 10-20 tweets (author, date, text, engagement, URL)
3. Present to user for curation
4. Save to `raw/tweets_<topic>_<date>.md`
5. Chain into ingest — source-summary uses `type: tweets` and synthesizes the discourse

## Running your agent

WikiWise includes a built-in terminal in the right sidebar — click the terminal icon in the toolbar. You can also run your agent in any external terminal pointed at this folder.

```bash
# Claude Code
claude

# Codex
codex

# Any agent — just cd to the wiki folder first
cd /path/to/your-wiki
```
