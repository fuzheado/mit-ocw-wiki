# Handoff — Session Context for New Agents

> **Last updated:** 2026-06-03
> **Project state:** L1 (refideas insert, linter, fixer) production-ready. L2 (external links) built and tested. L3-L5 designed but not built.

---

## What this project is

Wiki MIT — connect MIT OpenCourseWare's 2,577 courses with Wikipedia. Three subsystems:

1. **OCW Course Wiki** — 2,577 courses ingested as markdown pages with typed assets
2. **Match Heatmap** — cross-reference OCW departments against WikiProjects
3. **Contribution Impact Matrix** — D3.js scatterplot surfacing high-impact articles

Read `README.md` for the full overview. Read `docs/ROADMAP.md` for the plan.

---

## What we built

### L1 (Refideas: insert, linter, fixer, match discovery)

Production-ready with 50 tests, 8 live edits.

### Scripts

| Script | Purpose | Key commands |
|--------|---------|-------------|
| `scripts/lint-refideas.py` | Detect 6 error types in `{{refideas}}` templates across 11 aliases | `--fetch "Article"`, `--sample 50`, `--classify 30` |
| `scripts/apply-refideas-fix.py` | Apply fixes to live Wikipedia with auth | `"Article"`, `--dry-run`, `--yes`, `--survey 50` |
| `scripts/contribution-protocol.py` | L1-L5 data model, factories; `build_refideas_wikitext()` (pure fn), `refideas_add()` (orchestrator), `l1_insert_refideas()` (OCW wrapper) | `--validate`, `--wikitext`, `--l1-test` |
| `scripts/refideas-add.py` | **Generic** CLI — add any reference to `{{refideas}}` | `"Article" --url "..." --label "..." [--source "..."]` |
| `scripts/apply-l1-refideas.py` | **OCW wrapper** CLI — formats `--course-id` and delegates to generic tools | `"Article" --course-id 6.006 --course-title "..."` |
| `scripts/ad-hoc-match.py` | **Ad-hoc match** — find best Wikipedia articles for any OCW course, with pluggable providers, interactive L1/L2 posting | `--top 5`, `--mode L2 --interactive`, `--provider wikipedia` |
| `scripts/prioritize-matches.py` | **Match scoring** — template gate + IDF-weighted overlap + specificity | `--data FILE`, `-v` (verbose), `--interactive N`, `--apply-top N --yes` |
| `scripts/review-collaborator-matches.py` | **Collaborator match reviewer** — 185 cross-encoder-scored pairs, interactive y/N/q posting | `--mode L2`, `--min-score 0.90`, `--export file.json` |
| `scripts/generate-matches.py` | **Live match discovery** — searches 25 WikiProjects via Wikipedia API, detects templates with mwparserfromhell, matches against 2,577 OCW courses | `--top 30 --output FILE`, `--project Chemistry` |
| `scripts/scan-batch-parallel.py` | **Parallel asset scanner** — scanned 2,165 courses in 13.5 min (8 workers, 2.7/s) | `--workers 8`, `--limit 50`, `--dry-run` |
| `scripts/test-refideas.py` | 28 regression tests (linter/fixer) | `python3 scripts/test-refideas.py -v` |
| `scripts/test-l1-refideas-insert.py` | 22 tests for `build_refideas_wikitext()` (pure function, no API) | `python3 scripts/test-l1-refideas-insert.py -v` |

### L2 (External links — built 2026-05-27, updated 2026-06-03)

| Script | Purpose | Key commands |
|--------|---------|-------------|
| `scripts/apply-l2-external-links.py` | **OCW CLI** — add MIT course link to article's `== External links ==` section | See below for CLI syntax |
| `scripts/test-l2-external-links.py` | 26 offline tests for `build_external_link_wikitext()` (pure function) | `python3 scripts/test-l2-external-links.py -v` |

**Architecture** (same pure function + orchestrator + OCW wrapper pattern as L1):
- **`build_external_link_wikitext(wikitext, url, title, publisher, description)`** — pure function, 26 offline tests
- **`external_link_add(article, url, title, publisher, description)`** — orchestrator, fetches via API, deduplicates
- **`l2_insert_external_link(article, course_id, course_title, course_url, description)`** — OCW wrapper

**CLI syntax — `--course` mode (primary, resolves from local wiki):**
```bash
# Course as OCW slug
python3 scripts/apply-l2-external-links.py "Article" \
    --course "6-s897-machine-learning-for-healthcare-spring-2019"

# Course as full URL
python3 scripts/apply-l2-external-links.py "Article" \
    --course "https://ocw.mit.edu/courses/6-s897-machine-learning-for-healthcare-spring-2019/"

# Article as full Wikipedia URL
python3 scripts/apply-l2-external-links.py \
    "https://en.wikipedia.org/wiki/Artificial_intelligence_in_healthcare" \
    --course "6-s897-..."

# Override course title or description from wiki
python3 scripts/apply-l2-external-links.py "Article" \
    --course "6-s897-..." \
    --course-title "Custom Title" \
    --description "Custom description."
```

**CLI syntax — legacy mode (all fields explicit, still supported):**
```bash
python3 scripts/apply-l2-external-links.py "Article" \
    --course-id 6.006 \
    --course-title "Introduction to Algorithms" \
    --course-url "https://ocw.mit.edu/courses/6-006-..." \
    --description "Full course."
```

**Course resolution:** The `--course` flag accepts either an OCW slug
(`6-s897-machine-learning-for-healthcare-spring-2019`) or a full OCW URL
(`https://ocw.mit.edu/courses/6-s897-.../`). It resolves the course metadata
(course_id, title, url) from the local wiki at `wiki/courses/{slug}.md`.
The resolved title/description can be overridden with `--course-title` or
`--description`.

**Article resolution:** The positional argument accepts either a bare Wikipedia
article title (`Artificial intelligence in healthcare`) or a full Wikipedia URL
(`https://en.wikipedia.org/wiki/Artificial_intelligence_in_healthcare`).

**Section targeting:**
1. `== External links ==` (preferred) — inserts after the last `*` bullet, before any trailing navboxes/categories
2. `== Further reading ==` (fallback)
3. Neither exists → creates `== External links ==` before References/Notes/See also, or at end

**Output format:** `* {{cite web |url=... |title=... |publisher=MIT OpenCourseWare}} — description`

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

### L2 architecture (built 2026-05-27)

Same pure function + orchestrator + OCW wrapper pattern:

- **`build_external_link_wikitext(wikitext, url, title, publisher, description)`** — pure function. Takes wikitext in, appends `* {{cite web}}` to External links / Further reading section, or creates a new one. 25 offline tests.
- **`external_link_add(article, url, title, publisher, description)`** — orchestrator. Fetches article via API (not Talk page), deduplicates by URL, delegates to pure function.
- **`l2_insert_external_link(article, course_id, course_title, course_url, description)`** — OCW wrapper. Publisher = MIT OpenCourseWare.

### Match discovery and scoring pipeline

```
generate-matches.py          prioritize-matches.py        apply-l1-refideas.py
──────────────────          ─────────────────────        ─────────────────────
1. Search Wikipedia API     4. Template gate            7. Post to Wikipedia
   across 25 WikiProjects      (mwparserfromhell)          (bot auth, diff,
2. Batch-fetch wikitext      5. IDF-weighted overlap        [y/N] confirm)
3. Detect templates via        (rare words > common)
   mwparserfromhell         6. Multiple filter layers:
                               MIT-internal, outlines,
                               single-word, institutions,
                               organizations, geo-locale
```

**Scoring formula:** `template_urgency + overlap×35 + specificity×30` (0-100 scale)

**Filter layers remove false positives:**
- MIT-internal articles (circular)
- Outlines/lists/glossaries (navigation pages)
- Single-word topics (too broad)
- Education meta-articles
- Named institutions (Harvard, Max Planck)
- Organizations (labs, companies, agencies)
- Geo-locale articles (Solar power in the UK)

**Result:** 156 high-quality article↔course matches across 25 WikiProjects, scored and ready for review.

### Collaborator cross-encoder matches (Environment/Climate/Energy)

A collaborator provided 185 high-confidence OCW↔Wikipedia matches from a
rigorous two-stage pipeline (TF-IDF → zerank-2 cross-encoder reranking)
restricted to Environment/Climate/Energy domain.

| Metric | Value |
|--------|-------|
| OCW PDFs scanned | 1,439 (from 1,648 API results, audited) |
| Wikipedia seed articles | 103 (curated, env/climate/energy) |
| Stage-1 TF-IDF candidates | 1,545 |
| Stage-2 cross-encoder reranked | 1,020 (zerank-2, top 10 per article) |
| Kept after ≥ 0.79 threshold | **185 pairs across 62 articles** |
| Score range | 0.790–0.961 (median 0.875) |
| Cross-encoder model | `zeroentropy/zerank-2` |

**What's different from our pipeline:**
- Scores are full-text semantic similarity (not title keyword overlap)
- Matches specific lecture PDFs, not just whole courses
- No template gate — scores every article against OCW content
- Far narrower domain scope (1 topic vs. our 25 WikiProjects)

The reviewer tool (`scripts/review-collaborator-matches.py`) resolves all
course names to our wiki metadata (40/41 matched 1:1) and posts via
our existing L1/L2 editors.

Source files live in `external/`:
- `OVERVIEW.pdf` — pipeline description, filters, department breakdown
- `reranked_p79.pdf` — all 185 matches with scores and lecture PDFs

### Key architectural decisions

- **mwparserfromhell** for all wikitext parsing — never regex on raw wikitext
- **Batch fetching** via `action=query&titles=A|B|C` (50 pages per call, ~1s for survey)
- **Population caching** to `.wiki_cache/` — 29,177 pages loaded in 0.0s after first fetch
- **Direct URL construction** for API calls with percent-encoded titles — never `urlencode` which double-encodes
- **Cookie jar shared across auth steps** — login token, CSRF token, and edit must share the same jar
- **`str(tmpl)` captured before any param modifications** — otherwise string replacement silently fails

---

## How to continue

### L2 ✅ Built

External links insertion is complete: pure function (25 tests), orchestrator, OCW wrapper CLI.

```bash
# Dry-run preview
python3 scripts/contribution-protocol.py --l2-test
python3 scripts/contribution-protocol.py --l2-test "Nuclear weapon"

# Live insertion (auth required)
python3 scripts/apply-l2-external-links.py "Algorithm" \
    --course-id 6.006 \
    --course-title "Introduction to Algorithms" \
    --course-url "https://ocw.mit.edu/courses/6-006-..." \
    --description "Full course with video lectures, problem sets, and exams."

# Preview without posting
python3 scripts/apply-l2-external-links.py --dry-run "Algorithm" --course-id ...

# Run tests
python3 scripts/test-l2-external-links.py -v
```

### Next: L3 — Replace {{{{Citation needed}}}}

Designed in `docs/CONTRIBUTION-LEVELS.md`. Replace `{{cn}}` tags with `<ref>{{cite web}}</ref>` pointing to OCW resources. Requires:
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
    --source "Source Name"

# OCW-specific: add MIT course as refideas suggestion
python3 scripts/apply-l1-refideas.py "Article" \
    --course-id 6.006 \
    --course-title "Introduction to Algorithms" \
    --course-url "https://ocw.mit.edu/courses/6-006-..."

# Preview either without posting (--dry-run)
python3 scripts/apply-l1-refideas.py --dry-run "Article" --course-id ...

# ── Match discovery and scoring ──

# Generate live matches across 25 WikiProjects
python3 scripts/generate-matches.py --top 30 --output .wiki_cache/live-matches.json

# Score and rank all matches
python3 scripts/prioritize-matches.py --data .wiki_cache/live-matches.json

# Verbose reasoning for top 5
python3 scripts/prioritize-matches.py --data .wiki_cache/live-matches.json -v

# Interactive: review each match with [y/N/q]
python3 scripts/prioritize-matches.py --data .wiki_cache/live-matches.json --interactive 5

# Batch apply top N (requires --yes)
python3 scripts/prioritize-matches.py --data .wiki_cache/live-matches.json --apply-top 3 --yes

# ── Ad-hoc match (find best articles for any OCW course) ──

# Ranked matches (stdout)
python3 scripts/ad-hoc-match.py "6.S897" --top 5
python3 scripts/ad-hoc-match.py "https://ocw.mit.edu/courses/6-s897-.../" --top 8

# Provider selection (pluggable matching strategies)
python3 scripts/ad-hoc-match.py "STS.050" --provider corpus          # pre-computed matches only
python3 scripts/ad-hoc-match.py "STS.050" --provider wikipedia        # Wikipedia search only
python3 scripts/ad-hoc-match.py "STS.050" --provider "corpus,wikipedia"  # custom combination

# Interactive mode (select match → preview diff → post)
python3 scripts/ad-hoc-match.py "6.S897" --mode L2 --interactive --dry-run
python3 scripts/ad-hoc-match.py "22.01" --mode L1 --interactive

# ── L2: External links ──

# Dry-run: see what would be posted (no auth needed)
python3 scripts/contribution-protocol.py --l2-test
python3 scripts/contribution-protocol.py --l2-test "Nuclear weapon"

# ── Primary --course mode (resolves from local wiki) ──

# Course as OCW slug (preferred)
python3 scripts/apply-l2-external-links.py "Algorithm" \
    --course "6-006-introduction-to-algorithms-spring-2020" \
    --description "Full course with video lectures, problem sets, and exams."

# Course as full OCW URL
python3 scripts/apply-l2-external-links.py "Algorithm" \
    --course "https://ocw.mit.edu/courses/6-006-introduction-to-algorithms-spring-2020/"

# Article as full Wikipedia URL
python3 scripts/apply-l2-external-links.py \
    "https://en.wikipedia.org/wiki/Algorithm" \
    --course "6-006-..."

# Override course title or description resolved from wiki
python3 scripts/apply-l2-external-links.py "Algorithm" \
    --course "6-006-..." \
    --course-title "Custom Title" \
    --description "Custom description."

# Preview without posting (--dry-run)
python3 scripts/apply-l2-external-links.py --dry-run "Algorithm" --course "6-006-..."

# Skip confirmation (--yes)
python3 scripts/apply-l2-external-links.py --yes "Algorithm" --course "6-006-..."

# ── Legacy mode (all fields explicit, still supported) ──

python3 scripts/apply-l2-external-links.py "Algorithm" \
    --course-id 6.006 \
    --course-title "Introduction to Algorithms" \
    --course-url "https://ocw.mit.edu/courses/6-006-..." \
    --description "Full course with video lectures, problem sets, and exams."

# ── Collaborator cross-encoder matches ──

# Interactive review (L1 refideas mode)
python3 scripts/review-collaborator-matches.py

# L2 external links mode, top tier only
python3 scripts/review-collaborator-matches.py --mode L2 --min-score 0.90

# Export as JSON for prioritize-matches.py --data
python3 scripts/review-collaborator-matches.py --export matches-collab.json

# ── Tests ──

# All tests (75 total: 28 linter + 22 L1 insert + 25 L2 external links)
python3 scripts/test-refideas.py -v
python3 scripts/test-l1-refideas-insert.py -v
python3 scripts/test-l2-external-links.py -v

# Validate all contribution level examples
python3 scripts/contribution-protocol.py --validate
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
