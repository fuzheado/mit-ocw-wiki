# Handoff — Session Context for New Agents

> **Last updated:** 2026-05-26
> **Project state:** L1 (refideas insert, linter, fixer) production-ready. L2-L5 designed but not built.

---

## What this project is

Wiki MIT — connect MIT OpenCourseWare's 2,577 courses with Wikipedia. Three subsystems:

1. **OCW Course Wiki** — 2,577 courses ingested as markdown pages with typed assets
2. **Match Heatmap** — cross-reference OCW departments against WikiProjects
3. **Contribution Impact Matrix** — D3.js scatterplot surfacing high-impact articles

Read `README.md` for the full overview. Read `docs/ROADMAP.md` for the plan.

---

## What we built (L1 — Refideas insert, linter, and fixer)

### Scripts

| Script | Purpose | Key commands |
|--------|---------|-------------|
| `scripts/lint-refideas.py` | Detect 6 error types in `{{refideas}}` templates across 11 aliases | `--fetch "Article"`, `--sample 50`, `--classify 30`, `--fix "Article"` |
| `scripts/apply-refideas-fix.py` | Apply fixes to live Wikipedia with auth | `"Article"`, `--dry-run`, `--yes`, `--survey 50` |
| `scripts/contribution-protocol.py` | L1-L5 data model, factories, validation; `build_refideas_wikitext()` (pure fn), `refideas_add()` (orchestrator), `l1_insert_refideas()` (OCW wrapper) | `--validate`, `--wikitext`, `--l1-test` |
| `scripts/refideas-add.py` | **Generic** CLI — add any reference to `{{refideas}}` (not OCW-specific) | `"Article" --url "..." --label "..." [--source "..."] [--note "..."]` |
| `scripts/apply-l1-refideas.py` | **OCW wrapper** CLI — formats `--course-id` etc. and delegates to generic tools | `"Article" --course-id 6.006 --course-title "..." --course-url "..."` |
| `scripts/test-refideas.py` | 28 regression tests (linter/fixer) | `python3 scripts/test-refideas.py -v` |
| `scripts/test-l1-refideas-insert.py` | 22 tests for `build_refideas_wikitext()` (pure function, no API) | `python3 scripts/test-l1-refideas-insert.py -v` |

### Fix types

| Type | Severity | What it does | Auto-fixed |
|------|----------|-------------|-----------|
| `multi_bullet` | 🔴 error | Split `\|* ref1\n* ref2` into separate numbered params | ✅ |
| `bullet_syntax` | 🔴 error | Strip `*` from `\|1=* url` or `\|* = url` | ✅ |
| `duplicate_url` | 🟡 warning | Remove duplicate URL (keep first) | ✅ |
| `unnumbered_param` | 🟡 warning | Detected, not auto-fixed | ❌ |
| `param_spacing` | 🟡 warning | Detected, not auto-fixed | ❌ |
| `bare_url` | ℹ️ info | Detected, not auto-fixed (needs page scraping for label) | ❌ |

### Live editing

Authentication via bot password in `.env`:
```
WIKIPEDIA_USERNAME=YourUsername@BotName
WIKIPEDIA_BOT_PASSWORD=your_bot_password
```

Workflow: `--survey` to find pages → `--dry-run "Article"` to preview → `"Article"` to apply (with color diff + [y/N]).

8 pages fixed on live Wikipedia. L1 insert editor tested on live Talk pages.

### Architecture: pure function + orchestrator pattern

L1 refactored into three layers (pattern to follow for L2-L5):

- **`build_refideas_wikitext(wikitext, url, label, source, note)`** — pure function. Takes wikitext string in, returns modified wikitext out. No API calls, no side effects. 22 offline tests.
- **`refideas_add(article, url, label, source, note)`** — orchestrator. Fetches Talk page via API, deduplicates by URL, delegates to `build_refideas_wikitext()`.
- **`l1_insert_refideas(article, course_id, course_title, url, note)`** — OCW wrapper. Formats `"[url MIT id: title], MIT OpenCourseWare (note)"` and calls `refideas_add()`.

New features in this refactor:
- **Deduplication** — checks entire Talk page for the URL before inserting; skips with `⏭` message
- **11 template aliases** recognized (refideas, refidea, RI, suggested sources, etc.)
- **Heading at page start** handled (no leading `\n` before `==`)
- **Generic CLI** (`refideas-add.py`) — works for any reference, not just OCW

### Key architectural decisions

- **mwparserfromhell** for all wikitext parsing — never regex on raw wikitext
- **Batch fetching** via `action=query&titles=A|B|C` (50 pages per call, ~1s for survey)
- **Population caching** to `.wiki_cache/` — 29,177 pages loaded in 0.0s after first fetch
- **Direct URL construction** for API calls with percent-encoded titles — never `urlencode` which double-encodes
- **Cookie jar shared across auth steps** — login token, CSRF token, and edit must share the same jar
- **`str(tmpl)` captured before any param modifications** — otherwise string replacement silently fails

---

## How to continue

### Next: L2 — External links

Designed in `docs/CONTRIBUTION-LEVELS.md`. Add OCW course links to `== External links ==` sections.

**Key questions to answer:**
- Find `== External links ==` vs `== Further reading ==` section via `filter_headings()`
- Append bulleted `{{cite web}}` or plain `[url Label]`? (Standard is `{{cite web}}` for external links)
- What if no External links section exists? Create one, positioned before `== References ==` per WP:LAYOUT
- Write tests before implementing

### After L2: L3 — Replace `{{Citation needed}}`

Replace `{{cn}}` tags with `<ref>{{cite web}}</ref>` pointing to OCW resources. Requires:
- Finding the specific `{{cn}}` by section + context text
- Generating a proper citation from OCW course/lecture metadata
- The OCW license (CC BY-NC-SA) note — citing NC works is standard academic practice

### Contribution interface (Phase 3 in ROADMAP)

The work queue: join Impact Matrix data with OCW match data to produce a prioritized list of articles with pre-formatted edit suggestions. Start with L1-L3.

---

## Common workflows

```bash
# ── Linter / fixer ──

# Lint one page
python3 scripts/lint-refideas.py --fetch "Article"

# Find pages with fixable errors
python3 scripts/apply-refideas-fix.py --survey 80

# Preview fix
python3 scripts/apply-refideas-fix.py --dry-run "Article"

# Apply fix (with prompt)
python3 scripts/apply-refideas-fix.py "Article"

# Apply fix (auto-confirm)
python3 scripts/apply-refideas-fix.py --yes "Article"

# Classify reference types
python3 scripts/lint-refideas.py --classify 30

# ── Insert new references ──

# Generic: add any reference to {{refideas}}
python3 scripts/refideas-add.py "Article" \
    --url "https://example.com/ref" \
    --label "Reference Label" \
    --source "Source Name" \
    --note "optional note"

# OCW-specific: add MIT course as refideas suggestion
python3 scripts/apply-l1-refideas.py "Article" \
    --course-id 6.006 \
    --course-title "Introduction to Algorithms" \
    --course-url "https://ocw.mit.edu/courses/6-006-..." \
    --note "video lectures, problem sets"

# Preview either without posting (--dry-run)
python3 scripts/apply-l1-refideas.py --dry-run "Article" --course-id ...

# Quick dry-run from contribution-protocol (no auth needed)
python3 scripts/contribution-protocol.py --l1-test "Article"

# ── Tests ──

# All L1 tests (50 total: 28 linter + 22 insert)
python3 scripts/test-refideas.py -v
python3 scripts/test-l1-refideas-insert.py -v
```

---

## Key docs

| Doc | Covers |
|-----|--------|
| `docs/L1-REFIDEAS.md` | Complete L1 reference: algorithm, flow chart, linter, insert editor, live editing, pure function pattern |
| `docs/CONTRIBUTION-LEVELS.md` | All five L1-L5 levels with processing specs |
| `docs/CONTRIBUTION-PROTOCOL.md` | ContributionRecord data schema |
| `docs/ROADMAP.md` | Project roadmap: Phase 2 (integration) + Phase 3 (contribution interface) |
| `.claude/skills/wikipedia-editing/SKILL.md` | Reusable skill: talk page insertion, mwparserfromhell gotchas, API auth, encoding |
| `HANDOFF.md` | This file |

---

## Sharp edges

- **Duplicate URL fix only removes exact matches** — different URLs for the same content (e.g., `http` vs `https`, or different archive snapshots) are not detected as duplicates
- **Bare URLs** are the most common issue (52% of refs) but not auto-fixed — need page title scraping for meaningful labels
- **`--yes` flag** applies edits without confirmation — use after reviewing diffs
- **Encoding**: always `unquote()` titles from cache before re-encoding or passing to `urlencode`
- **Skills**: `.claude/skills/wikimedia-*` are restored from the Wikipedia-AI-Skills external repo
