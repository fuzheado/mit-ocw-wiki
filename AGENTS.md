# Agent Instructions

This is a wiki maintained by an LLM agent for the [Wiki MIT](https://meta.wikimedia.org/wiki/Wiki_MIT) project — connecting MIT OpenCourseWare with Wikipedia and Wikimedia Commons. Read these files first:

- **`CLAUDE.md`** — agent instructions, project schema, workflows, conventions. Your primary instruction file.
- **`README.md`** — human-facing overview, status, quick start, project structure.
- **`docs/`** — reference docs (crossref strategy, impact matrix design, git strategy, L1/L2 contribution).
  - **`docs/L1-REFIDEAS.md`** — L1 algorithm: Talk page `{{refideas}}`, linter, fixer, insert tools. **50 tests, 15 live edits.** Keep in sync with `scripts/lint-refideas.py`, `scripts/apply-refideas-fix.py`, `scripts/refideas-add.py`, `scripts/apply-l1-refideas.py`.
  - **`docs/L2-EXTERNAL-LINKS.md`** — L2 algorithm: External links insertion, course resolution, CLI reference, known bugs. **26 tests.** Keep in sync with `scripts/apply-l2-external-links.py`, `scripts/contribution-protocol.py` (L2 functions), `scripts/test-l2-external-links.py`.
  - **`docs/AD-HOC-MATCH.md`** — Ad-hoc match algorithm: match sources, filter layers, scoring, page type detection, interactive flow. Keep in sync with `scripts/ad-hoc-match.py`.
  - **`docs/HOWTO-NEW-PROVIDER.md`** — How to add a new `MatchProvider` to the pluggable matching system.
- **`_checkpoint.json`** — current project state. Read this at the start of every session.

## Quick reference

- **`raw/`** — immutable source documents. Read-only.
- **`wiki/`** — LLM-maintained markdown pages. All edits here. Source summaries go in `wiki/sources/`.
- **`site/`** — build tooling and compiled output. `site/out/` is auto-generated.

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

Skill files live in `.claude/skills/<name>/SKILL.md`. **Read the skill file before running a workflow** — it contains step-by-step instructions, shell commands, and rules.

Wikimedia API / SQL skills are provided by the external [Wikipedia-AI-Skills](https://github.com/fuzheado/Wikipedia-AI-Skills) repo. Clone it and load its `.claude/skills/` directory to access them.

### Skill catalog

| Skill | Path | Purpose |
|---|---|---|
| **ocw-ingest** | `.claude/skills/ocw-ingest/SKILL.md` | Bulk-ingest OCW courses from the MIT Learn API with pagination, checkpoint resume, and batch commits |
| **ingest** | `.claude/skills/ingest/SKILL.md` | Add a source to the wiki — save raw, create summary page, propagate claims, update index and log |
| **digest** | `.claude/skills/digest/SKILL.md` | Deep-propagate ingested sources across the wiki — update concept/entity pages, flag contradictions, create new pages where warranted |
| **lint** | `.claude/skills/lint/SKILL.md` | Health-check for contradictions, orphan pages, broken links, stale claims, missing cross-links |
| **ingest-tweets** | `.claude/skills/ingest-tweets/SKILL.md` | Search Twitter/X for tweets on a topic using browser automation, extract content, and ingest into the wiki |
| **import-readwise** | `.claude/skills/import-readwise/SKILL.md` | Search and import documents/highlights from Readwise |
| **fetch-readwise-document** | `.claude/skills/fetch-readwise-document/SKILL.md` | Stream a Reader document into `raw/` |
| **fetch-readwise-highlights** | `.claude/skills/fetch-readwise-highlights/SKILL.md` | Vector-search highlights, grouped by parent doc, write to `raw/` |

### Ad-hoc match tool (`scripts/ad-hoc-match.py`)

Quick way to find the best Wikipedia articles for any MIT OCW course.
Uses a pluggable provider architecture — add new matching strategies via `MatchProvider`:
```bash
python3 scripts/ad-hoc-match.py "6.S897" --top 5           # Ranked matches
python3 scripts/ad-hoc-match.py "STS.050" --provider wikipedia  # Only Wikipedia search
python3 scripts/ad-hoc-match.py "6.S897" --mode L2 --interactive  # Interactive + post
```

Filters out: broad-field articles ("Computer science"), glossary/list pages,
named entities on weak matches, and generic category word overlap.
Scores by: pre-computed corpus matches, title specificity, maintenance templates, pageviews.
See `docs/HOWTO-NEW-PROVIDER.md` to add a new provider.

## OCW ingest workflow

1. Read `_checkpoint.json` to determine current offset
2. Fetch `GET /api/v1/courses/?offered_by=ocw&limit=100&offset={N}`
3. For each course: extract YAML frontmatter, write `wiki/courses/{slug}.md`, link from department/topic/instructor pages
4. Use `[[wikilinks]]` by slug only
5. Update `wiki/index.md` with new course count
6. Update `_checkpoint.json` with new offset and counts
7. Append to `wiki/log.md`
8. Git commit with message `ocw: ingest batch offset={N}`

### Wikipedia cross-reference workflow

1. Read `docs/crossref-strategy.md` for the full matching strategy
2. Establish SSH tunnel per `wikimedia-database` skill
3. For each OCW topic, query matching WikiProject via `page_assessments`
4. Score candidate articles against OCW course assets and lecture titles
5. Generate Wikipedia Bridge sections and `wiki/crossrefs/` hub pages
