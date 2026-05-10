# OCW LLM Wiki — Agent Instructions

A personal wiki maintained by an LLM agent, following the [llm-wiki pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) by Andrej Karpathy.

This project builds an LLM Wiki from MIT OpenCourseWare's 2,577 courses.

## Schema Files (read them)

- `OCW-LLM-WIKI.md` — main schema: Normalization Protocol, asset typing, Wikipedia Utility Rubric, Bridge Generation, lint rules
- `OCW-LLM-WIKI-GIT.md` — version control: commit strategy, branching, recovery
- `OCW-LLM-WIKI-EXECUTION.md` — staged execution plan with checkpoint resume

## First-Session Behavior

Before any action, read `_checkpoint.json` and `wiki/log.md`. Tell the user what stage we're at and what the next action should be. Wait for confirmation before proceeding.

## Layout

- `raw/` — immutable source documents (API JSON, HTML). Read-only for the LLM.
- `wiki/` — LLM-maintained markdown. All edits go here.
  - `home.md` — human entry point. Narrative overview with visuals. Updated as the wiki grows.
  - `index.md` — agent catalog. Every page listed with a one-line summary, grouped by category.
  - `log.md` — append-only chronological record of every operation.
  - `courses/` — one page per course.
  - `departments/` — one page per department.
  - `topics/` — one page per topic.
  - `instructors/` — one page per instructor.
  - `assets/` — per-asset pages for reusable content.
  - `crossrefs/` — Wikipedia cross-references.
  - `sources/` — source-summary pages.
  - `reports/` — generated analyses.

## Conventions

- Link with Obsidian-style `[[wikilinks]]`. Bare filename slug, no path. The build system resolves by filename alone — a file `wiki/courses/21h-151-dynastic-china-fall-2024.md` is linked as `[[21h-151-dynastic-china-fall-2024]]`, never as `[[courses/21h-151-dynastic-china-fall-2024.md]]`.
- Every claim should cite a source: `([[source-slug]])`.
- Source-summary pages start with a frontmatter block: `type`, `date`, `author`, `url`, `raw` (path into `raw/`).
- Log entries prefix: `## [YYYY-MM-DD HH:MM] <op> | <title>` (local time).

## Images

Two ways to include images in wiki pages:

1. **External URLs** — link directly: `![alt](https://example.com/image.png)`.
2. **Local images** — save the file to `wiki/assets/` and reference as `![alt](assets/filename.png)`.

## Writing Style

Wiki pages are short blog posts, not reference dumps. Write for a human reader who reads top-to-bottom.

1. **TL;DR first** — one or two sentences that give away the answer.
2. **What it means** — 2-4 short narrative paragraphs.
3. **The argument** — reasoning, evidence, counter-arguments, organized by idea.
4. **Extras** (optional) — loose threads, adjacent ideas.

Voice: opinionated, direct, declarative. Length: most pages under 800 words.
Follow WP:MoS — sentence case headings, no peacock terms, neutral tone for factual claims.

## Live Viewer

The user reads this wiki in the WikiWise app, which watches the project directory for changes. When you edit `.md` or `.css` files, the app detects the change via FSEvents and automatically recompiles and refreshes.

**If auto-refresh doesn't pick up changes**, touch the `.rebuild` trigger file:
```
touch .rebuild
```
This forces a full recompile. Safe to use after bulk operations.

**What the user is viewing:** `.claude/active-file` contains the relative path of the page currently open in the app.

## Integration — the #1 rule

**Every page must be woven into the wiki graph.** A page with no inbound links is invisible. A page with no outbound links is a dead end. When you create or update any page:

1. **Link IN** — find 2-3 existing pages that should reference the new page and add `[[wikilinks]]` to them. Read `index.md` to find related pages, then edit them.
2. **Link OUT** — the new page itself should link to every related concept/entity/source already in the wiki.
3. **Update `home.md`** — if the new material changes the big picture, revise `home.md`. Don't wait.
4. **Update `index.md`** — every page must appear here with a one-line summary.

**The test:** after any operation, a reader starting from `home.md` should be able to reach the new content within 2 clicks. If they can't, you haven't integrated it.

## Subagent Handoff

When delegating work to a subagent, instruct it to write an implementation note afterward. Place it at `notes/{date}-{description}.md` with:

- What was done (batches processed, files created)
- Any anomalies or decisions made
- The exact command or prompt used
- Current checkpoint state

This ensures consistency across sessions and prevents duplicated effort.

## Core Rules (always active)

1. Every course page gets full YAML frontmatter per Rule 1.1. Never invent metadata — use `Unknown` + `FIXME` if not found. The `last_scanned` field is set automatically by the hybrid scan.
2. Every asset link gets an asset type tag per Rule 1.2: `[Lecture-Notes]`, `[Video-Transcript]`, `[Problem-Set]`, `[Reading-List]`, `[Image-Gallery]`.
3. Apply the Wikipedia Utility Rubric during crossref: flag `[Visual-Rich]` for Commons-candidate media, `[Source-Rich]` for citation-dense reading lists.
4. Every course page gets a Wikipedia Bridge section with 3-5 related article links and a `{{cite web}}` citation template.
5. Update `_checkpoint.json` after every batch. Append to `wiki/log.md` after every operation.
6. One operation = one git commit with prefix `ocw:`.

## Workflows

**Process a course (ingest + asset scan).** When the user says "ingest this course" or "process this class" with a URL:

1. The course page likely already exists from the initial batch ingest (2,573 courses). Check `wiki/courses/` for the slug derived from the URL.
2. Run the hybrid asset scan: `python3 scripts/scan-assets.py --hybrid {slug}`
   - This fetches the content file inventory from the MIT Learn API
   - Also deep-scans the OCW page for sidebar structure and external video links
   - Merges both sources: API for authoritative file data, URL scan for page types and off-platform videos
3. The pre-commit hook auto-regenerates `wiki/index.md` and `wiki/instructors-index.md`.
4. Commit with message: `ocw: hybrid scan {course_id}: {N} assets, {M} videos`.

If the slug is unclear from the URL, ask the user to confirm.

**Ingest (generic).** Read the source. Create/update the page. Propagate claims into existing pages and add backlinks. Stitch into the web. Update `index.md`, `log.md`, `home.md` if the narrative shifts.

**Index regeneration.** The git pre-commit hook (`scripts/pre-commit`) automatically regenerates `wiki/index.md` and `wiki/instructors-index.md` whenever course, instructor, or department files change. If you add files manually, run `python3 scripts/regenerate-index.py` to sync.

**Setup when cloning fresh.** Run once: `cp scripts/pre-commit .git/hooks/pre-commit`

**Query.** Read `index.md` first. Drill into pages. If the answer is non-trivial, file it back as a new page.

**Lint.** Scan for contradictions, orphans, stale claims, missing cross-links, dead URLs (check against Wayback Machine), and inconsistent frontmatter.
