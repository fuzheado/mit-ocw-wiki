# Project Roadmap

> **Current state:** v0.1 across all three subsystems.
> **L1 production-ready:** linter, fixer, live editor, and 24-test suite. 7 pages fixed on Wikipedia.

---

## Phase 2: Subsystem Integration

**Goal:** Wire OCW course data into the Impact Matrix so the three subsystems form a single pipeline.

**Why:** Currently the Impact Matrix is a generic Wikipedia tool — it shows which articles need work, but doesn't connect them to OCW resources. The Match Heatmap shows department-level overlap but not per-article matches. These need to be joined.

### 2a. Per-article match lookup (Matchmaker Phase 1)

Build a static lookup table that maps Wikipedia articles to specific OCW courses and resources.

**What to build:**
1. Extend `scripts/generate-impact-matrix-data.py` to accept OCW match data from `scripts/crossref-wikipedia.py` output
2. For each article in LIVE_DATA, add an `ocw_matches[]` field with:
   - `course_id` (e.g., "5.111SC")
   - `course_title` (e.g., "Principles of Chemical Science")
   - `lecture_title` (e.g., "Lecture 12: VSEPR Theory")
   - `match_score` (0-100)
   - `resource_url` (direct link to the relevant course page or lecture)
   - `resource_type` (video, lecture-notes, problem-set, reading-list)
3. Output: `wiki/impact-matrix/data/ocw-matches.js` — a separate JS file keyed by article title
4. Update `standalone.html` build to embed this data alongside `live-data.js`

**Starting point:** `scripts/crossref-wikipedia.py` already has a `--demo` mode that generates 57 matches across 9 WikiProjects. Read that script's scoring logic and extend it to produce the per-article match file.

**Reference docs:**
- `docs/crossref-strategy.md` — matching strategy, unified SQL query, scoring model
- `notes/matchmaker-api-design.md` — Phase 1 details, data format specification
- `HANDOFF.md` — SSH tunnel setup, session-specific knowledge

**Success criteria:**
- `wiki/impact-matrix/data/ocw-matches.js` exists with matches for articles in at least one WikiProject
- The file is included in the standalone.html build (no runtime API calls)
- Can be loaded client-side for MIT Mode

### 2b. MIT Mode in the Impact Matrix

Add the OCW overlay to the existing scatterplot.

**What to build:**
1. Add an "MIT Mode" toggle in the header of `wiki/impact-matrix/index.html`
2. When enabled:
   - Load `ocw-matches.js` (or access embedded data)
   - Filter the project picker to OCW-aligned WikiProjects (use the mapping from `docs/crossref-strategy.md` — currently 25 projects identified)
   - Bubbles with OCW matches get a colored ring or icon overlay
   - Detail panel gains a "Wikipedia Bridge" tab showing matched courses
3. New filter: "Has OCW match" toggle (show all / matched only / unmatched only)
4. Summary bar: "X of Y articles in this project have OCW matches"

**Starting point:** The existing heatmap (`wiki/reports/crossref-heatmap.html`) already has a detail panel pattern — reuse that for the Wikipedia Bridge tab. The OCW ↔ WikiProject mapping is in `docs/crossref-strategy.md`.

**Reference docs:**
- `docs/impact-matrix/prd.md` — MIT Mode feature spec (section 3)
- `docs/impact-matrix/design.md` — architecture, data flow
- `wiki/reports/crossref-heatmap.html` — detail panel pattern to reuse

### 2c. Update checkpoint and overview

1. Update `_checkpoint.json` to reflect actual scan state (courses_done: 12, not "complete")
2. Update `wiki/overview.md` — already done in this session
3. Verify `wiki/index.md` and `wiki/instructors-index.md` are current (run `python3 scripts/regenerate-index.py` if needed)

**Order of execution:** 2c → 2a → 2b

**Estimated effort:** 3-5 sessions

---

## Phase 3: Contribution Interface

**Goal:** Build a work queue that lets editors apply OCW-based improvements to Wikipedia articles — starting with low-risk talk page annotations and scaling to semi-automated edits.

### Design principles

1. **Start advisory, not automated.** First version should generate suggestions that a human copies into the Wikipedia editor. Add authentication later.
2. **Pre-fill everything.** Every suggestion includes a complete, ready-to-paste wikitext snippet.
3. **Respect the `file://` constraint.** Phase 1 should work as static HTML, like the Impact Matrix.
4. **Use existing data.** The work queue reads from the same pre-computed data as the Impact Matrix — no new data pipeline needed initially.

### 3a. Talk page `{{Refideas}}` generator

**Lowest risk, highest safety.** `{{Refideas}}` is a template that Wikipedia editors place on article Talk pages to suggest references. It doesn't touch the article itself — it's just a helpful note for other editors.

**Prerequisite:** Read `docs/CONTRIBUTION-PROTOCOL.md` first — it defines the ContributionRecord data structure. The reference implementation is in `scripts/contribution-protocol.py`.

**What to build:**
1. A new HTML page at `wiki/editor/index.html`
2. Reads `live-data.js` and `ocw-matches.js` (from Phase 2a)
3. Shows a filterable list of articles that have maintenance templates AND OCW matches
4. For each article, generates a `{{Refideas}}` snippet:

```wikitext
{{Refideas
|1={{cite web |url=https://ocw.mit.edu/courses/5-111sc-principles-of-chemical-science-fall-2014/ |title=Principles of Chemical Science (Lecture 12: VSEPR Theory) |publisher=MIT OpenCourseWare}}
|comment=MIT 5.111SC covers VSEPR theory in detail with video lectures, problem sets, and lecture notes.
}}
```

5. Each item has a "Copy to clipboard" button
6. Filter by WikiProject, template type, quality class

**The snippet format** should be self-contained — the editor can paste it directly into a Wikipedia Talk page without modification.

**Success criteria:**
- Opens as `file://` — no server required
- Shows articles with templates + OCW matches from at least one WikiProject
- Generates correctly formatted `{{Refideas}}` wikitext
- "Copy" button works

### 3b. Work queue with OAuth authentication

Once the advisory version works, add authentication to enable one-click edits.

**What to build:**
1. Wikipedia OAuth integration (requires a registered OAuth consumer on Wikipedia)
2. Authentication flow: "Log in with Wikipedia" → OAuth redirect → token stored
3. "Apply to Talk page" button — uses the Wikipedia API (`action=edit`) to post the `{{Refideas}}` snippet
4. Rate limiting: queue processes one edit at a time with configurable delay
5. Edit summary is always descriptive: `/* Suggested OCW reference */ via Wiki MIT`

**Reference docs:**
- Wikipedia OAuth: https://www.mediawiki.org/wiki/OAuth/For_Developers
- Edit API: `action=edit`, requires `csrf` token

**Note about hosting:** OAuth requires an HTTP callback URL. The tool can't work from `file://` at this stage — it needs to be served from a Toolforge instance or similar. See `notes/matchmaker-api-design.md` for hosting options.

### 3c. Expanded edit types

After Talk page edits are working, extend to higher-value edit types:

| Level | Edit type | Risk | Automation potential |
|-------|-----------|------|---------------------|
| L1 | Talk page `{{Refideas}}` | Near-zero | Fully automated |
| L2 | External links section | Very low | One-click with review |
| L3 | Replace `{{Citation needed}}` | Low | Pre-filled edit window |
| L4 | Fill `{{Missing information}}` | Medium | Pre-filled with OCW content |
| L5 | New content creation | High | Draft only, human posts |

Start with L1-L2 and gather data on editor acceptance rates before moving to L3+.

### 3d. Scale to 942 WikiProjects

Apply the per-project JS + manifest architecture designed in `notes/scalability-and-domain-classification.md`:

1. Update `generate-impact-matrix-data.py` to emit per-project JS files
2. Add `manifest.js` with grouped, searchable project picker
3. Use the 15-category Vital Articles taxonomy
4. Implement lazy loading — load project JS on selection

The 15-category taxonomy is already implemented in `scripts/classify_projects.py`.

**Reference docs:**
- `notes/scalability-and-domain-classification.md` — full analysis, Option 2 selected, manifest structure
- `scripts/classify_projects.py` — domain classification with Vital Articles taxonomy

### Phase 3 execution order

1. **3a first** — `{{Refideas}}` generator (advisory, static HTML)
2. **3d** can be done in parallel with 3a (different part of the system)
3. **3b** after 3a is working — OAuth + one-click edits
4. **3c** incrementally — start with L2, watch adoption, then L3+

**Estimated effort:** 4-6 sessions for Phase 3a-c; 2-3 sessions for Phase 3d

---

## Phase 4: Generalize Beyond MIT OCW

**Goal:** Extract the Contribution Ladder into a corpus-agnostic framework so any citable
knowledge corpus (arXiv, JSTOR, PubMed Central, government data, library collections)
can use the same pipeline — ingest → match → format → contribute.

**Why:** The mechanics of the ladder (match corpus items to Wikipedia articles, format
citations, present a work queue) are identical regardless of what corpus is being cited.
What changes per corpus is the citation template (`{{cite web}}` vs `{{cite arXiv}}` vs
`{{cite journal}}`), the matching strategy (course titles vs paper abstracts vs journal
subjects), and the ingest API. The framework should make adding a corpus a ~70-line plugin.

**Reference doc:** `docs/CONTRIBUTION-LADDER.md` — full design, architecture diagram,
pluggable abstractions, arXiv walkthrough, corpus candidates.

### 4a. Generalize ContributionRecord (1 session)

- Rename OCW-specific fields (`course_id` → `id`, `course_title` → `title`, etc.)
- Backward-compatible: old records continue to work
- Update `scripts/contribution-protocol.py` validation
- Update `docs/CONTRIBUTION-PROTOCOL.md`

### 4b. Extract ActionFormatter ABC (1 session)

- Extract wikitext generation from `contribution-protocol.py` into `OcwFormatter`
- Define `ActionFormatter` ABC: `format_l1()`, `format_l2()`, `format_l3()`, `edit_summary()`
- Refactor existing pure functions to accept an `ActionFormatter` parameter
- All 22 L1 + 26 L2 tests should pass unchanged

### 4c. Add arXiv as a second corpus (1-2 sessions)

- `ArxivConnector` — ingests from arXiv API by category
- `ArxivMatchProvider` — searches Wikipedia by paper title keywords
- `ArxivFormatter` — uses `{{cite arXiv}}` template
- Generate a mixed work queue (OCW + arXiv)

### 4d. Build the static ladder UI (1-2 sessions)

- `wiki/editor/index.html` — corpus selector, filterable work queue, rung selector
- "Copy to clipboard" for each pre-formatted wikitext snippet
- Works from `file://`

### Phase 4 execution order

1. **4a** first — the data model generalization unlocks everything else
2. **4b** — the formatter abstraction makes new corpora possible
3. **4c** — arXiv validates the framework with a real second corpus
4. **4d** — the UI surfaces multi-corpus contributions

**Estimated effort:** 4-6 sessions

---

## Reference map

Where to find things in the reorganized project:

| What | Where |
|------|-------|
| Human overview | `README.md` |
| Agent instructions | `CLAUDE.md` (primary), `AGENTS.md` (thin shim) |
| Schema & normalization | `OCW-LLM-WIKI.md` |
| Technical architecture | `TECHNICAL.md` |
| Session handoff | `HANDOFF.md` |
| Crossref strategy | `docs/crossref-strategy.md` |
| Impact Matrix design | `docs/impact-matrix/design.md` |
| Impact Matrix PRD | `docs/impact-matrix/prd.md` |
| Git strategy | `docs/git-strategy.md` |
| Execution plan (historical) | `archive/ocw-llm-wiki-execution.md` |
| Matchmaker API design | `notes/matchmaker-api-design.md` |
| Scalability analysis | `notes/scalability-and-domain-classification.md` |
| Pageview data issues | `notes/pageview-data-issues.md` |
| Domain classifier | `scripts/classify_projects.py` |
| L1 Refideas reference | `docs/L1-REFIDEAS.md` |
| L2 External links reference | `docs/L2-EXTERNAL-LINKS.md` |
| Contribution levels (L1-L5) | `docs/CONTRIBUTION-LEVELS.md` |
| Contribution Protocol schema | `docs/CONTRIBUTION-PROTOCOL.md` |
| Ad-hoc match tool | `docs/AD-HOC-MATCH.md` — full algorithm: match sources, provider interface, filter layers, scoring formula, page type detection, interactive flow |
| How to add a provider | `docs/HOWTO-NEW-PROVIDER.md` — step-by-step guide for writing a new `MatchProvider` |
| Contribution Ladder framework | `docs/CONTRIBUTION-LADDER.md` — generalized corpus-agnostic design, pluggable abstractions, arXiv walkthrough, corpus candidates |
| Contribution UI options | `docs/CONTRIBUTION-UI.md` — five deployment approaches, composite strategy, architecture decisions, static UI layout sketch, OAuth upgrade path |
| Toolforge Workbench app | `toolforge/` — Node.js web app implementing the Contribution Ladder (search → match → preview → apply). Zero-dependency server, responsive UI, bot password auth. See `toolforge/DESIGN.md` for full design + user manual |
| This roadmap | `docs/ROADMAP.md` |
