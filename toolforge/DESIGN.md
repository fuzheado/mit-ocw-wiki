# Wiki MIT Workbench — Design & User Manual

> **Status:** Prototype (v0.1). Local dev working. Toolforge deployment ready.
> **Depends on:** `scripts/ad-hoc-match.py`, `scripts/contribution-protocol.py`, `scripts/apply-l1-refideas.py`, `scripts/apply-l2-external-links.py`
> **Design docs:** `docs/CONTRIBUTION-LADDER.md` (framework), `docs/CONTRIBUTION-UI.md` (interface options), `docs/ROADMAP.md` (Phase 3-4)

---

## Table of Contents

1. [Architecture](#architecture)
2. [Design Decisions](#design-decisions)
3. [Data Flow](#data-flow)
4. [Component Breakdown](#component-breakdown)
5. [API Reference](#api-reference)
6. [Auth Modes](#auth-modes)
7. [User Manual](#user-manual)
8. [Deployment](#deployment)
9. [Error Handling & Edge Cases](#error-handling--edge-cases)
10. [Future Roadmap](#future-roadmap)

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                         User's Browser                           │
│                                                                  │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐ │
│  │ Course     │  │ Match      │  │ Preview    │  │ Apply      │ │
│  │ Search     │→ │ List       │→ │ Panel      │→ │ + Activity │ │
│  │ (autocomplete)│ (ranked)   │  │ (L1/L2 rungs)│ │ Log        │ │
│  └─────┬──────┘  └─────┬──────┘  └─────┬──────┘  └─────┬──────┘ │
│        │               │               │               │        │
└────────┼───────────────┼───────────────┼───────────────┼────────┘
         │               │               │               │
         ▼               ▼               ▼               ▼
┌──────────────────────────────────────────────────────────────────┐
│                   Node.js Server (server.mjs)                    │
│                   Zero dependencies, ~480 lines                  │
│                                                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐        │
│  │ Course   │  │ Match    │  │ Preview  │  │ Apply    │        │
│  │ Index    │  │ Engine   │  │ Engine   │  │ Engine   │        │
│  │ (memory) │  │ (Python) │  │ (JS)     │  │ (Python) │        │
│  └────┬─────┘  └────┬─────┘  └──────────┘  └────┬─────┘        │
│       │             │                            │              │
│       │      ┌──────┴──────┐            ┌───────┴───────┐       │
│       │      │ ad-hoc-     │            │ apply-l1-     │       │
│       │      │ match.py    │            │ refideas.py   │       │
│       │      └─────────────┘            │ apply-l2-     │       │
│       │                                 │ external-     │       │
│       │                                 │ links.py      │       │
│       │                                 └───────────────┘       │
└───────┼──────────────────────────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────────────────────────────────┐
│                   Course Wiki (wiki/courses/)                    │
│                   2,577 YAML-frontmatter .md files               │
│                   Indexed into memory on startup                 │
└──────────────────────────────────────────────────────────────────┘
```

### Key Design Principle: Python Subprocess Proxy

The Node.js server does not reimplement any of the existing Python logic. Instead, it acts as a thin proxy that:

1. **Spawns Python subprocesses** for matching and editing
2. **Parses stdout** into JSON for the frontend
3. **Serves static files** for the UI

This preserves the 150+ existing tests and mature algorithms in the Python codebase. The server is just an HTTP wrapper around the CLI tools.

---

## Design Decisions

### Decision 1: Zero npm dependencies

**Choice:** Use only Node.js built-in modules (`http`, `fs`, `path`, `child_process`, `crypto`).

**Why:**
- Toolforge NFS has slow metadata operations — `npm install` can take minutes
- The app is simple enough that no framework is needed
- `createServer` + manual routing is ~50 lines and fully transparent
- Eliminates supply chain risk for a tool that handles Wikipedia credentials

**Trade-off:** No Express-style middleware, no template engine, no hot reload. Acceptable for a 500-line server.

### Decision 2: Python subprocess rather than porting to JS

**Choice:** Call the existing Python scripts via `child_process.spawn()`.

**Why:**
- `ad-hoc-match.py` is 1,100+ lines with complex wikitext parsing, API calls, and scoring
- `contribution-protocol.py` has 50+ validated tests
- Porting to JS would require reimplementing `mwparserfromhell`, Wikipedia API auth, and all scoring logic
- The Python scripts are battle-tested with live Wikipedia edits

**Trade-off:** Subprocess overhead (~1-2s per match call). Acceptable for an interactive tool where the user expects a brief wait.

### Decision 3: Bot password as primary auth (OAuth deferred)

**Choice:** Authenticate edits using a Wikipedia bot password rather than OAuth 2.0.

**Why:**
- Bot passwords work immediately — no consumer registration or admin approval
- The prototype needs to demonstrate the editing pipeline now
- OAuth 2.0 is architecturally supported (stubs exist in `server.mjs`) but requires:
  - Registering an OAuth consumer on Meta
  - Administrator approval for public use
  - Callback URL setup on Toolforge

**Trade-off:** Edits are attributed to a bot account rather than individual editors. This is fine for the prototype phase but should be upgraded to OAuth 2.0 (multi-user) for production use. See `docs/CONTRIBUTION-UI.md` → OAuth upgrade path.

### Decision 4: In-memory course index

**Choice:** Parse all `wiki/courses/*.md` files on startup into an in-memory array.

**Why:**
- 2,577 courses × ~200 bytes = ~500 KB — fits easily in memory
- Substring search is instant (no database round-trips)
- No persistence needed — the course files are the source of truth
- Startup time is < 1 second even on Toolforge NFS

**Trade-off:** If the course wiki grows significantly (10,000+ courses), a database or trie-based search index would be needed. Not a concern for the foreseeable future.

### Decision 5: Client-side `localStorage` for activity log

**Choice:** Store recent edit history in the browser's `localStorage` rather than on the server.

**Why:**
- No database needed
- Survives page reloads and browser restarts
- Private to each editor's browser
- The activity log is just a convenience feature, not mission-critical data

**Trade-off:** Activity is not shared between browsers or users. A server-side log (SQLite on NFS) would be a natural upgrade.

---

## Data Flow

### Match Flow

```
User types "6.006" in search box
  │
  ▼
GET /api/courses?q=6.006
  → server searches in-memory courseIndex[]
  → returns [{slug, id, title, department, topics}, ...]
  │
  ▼
User selects "6.006 — Introduction to Algorithms"
  → state.courseSlug = "6-006-introduction-to-algorithms-fall-2011"
  → state.courseId   = "6.006"
  → state.courseTitle = "Introduction to Algorithms"
  → state.courseUrl  = "https://ocw.mit.edu/courses/.../"
  │
  ▼
User clicks "Find matches"
  │
  ▼
GET /api/match?course=6.006
  → server.mjs: spawn('python3', ['ad-hoc-match.py', '6.006', '--top', '10', ...])
  → ad-hoc-match.py:
      1. resolve_course("6.006") → reads wiki/courses/*.md YAML
      2. MatchProvider.find_candidates() → corpus + Wikipedia API search
      3. Pipeline: deduplicate → enrich (quality/views) → filter → score → rank
      4. Prints ANSI-styled table to stdout
  → server.mjs: parseAdHocOutput(stdout) → [{rank, title, score, quality, views, ...}]
  → returns JSON to client
  │
  ▼
Client renders match cards
```

### Preview Flow

```
User clicks L1 or L2 rung tab on a selected match
  │
  ▼
POST /api/preview {level: "L1", courseId: "6.006", courseTitle: "...", courseUrl: "..."}
  → server.mjs: previewL1() generates wikitext string
  → returns {wikitext: "{{Refideas\n|1=..."}
  │
  ▼
Client displays in <pre> with syntax preview
  → Copy button: navigator.clipboard.writeText()
```

### Apply Flow

```
User clicks "Apply to Wikipedia"
  │
  ▼
POST /api/apply {level: "L1", article: "Introduction to Algorithms", courseId: "6.006", ...}
  → server.mjs: checks WIKI_BOT_USER is set
  → spawn('python3', ['apply-l1-refideas.py', '--yes', article, '--course-id', courseId, ...])
  → apply-l1-refideas.py:
      1. Logs in with bot password (WIKIPEDIA_USERNAME / WIKIPEDIA_BOT_PASSWORD)
      2. Fetches Talk page wikitext via action=parse
      3. Parses with mwparserfromhell
      4. Inserts or appends {{Refideas}} block
      5. Posts via action=edit with CSRF token
      6. Prints success/error to stdout
  → server.mjs: returns {success: true/false, detail: "..."}
  │
  ▼
Client updates activity log in localStorage
  → ✅ success → green "Applied!" message
  → ⚠️ failure → red error with link to manual Wikipedia edit
```

---

## Component Breakdown

### `server.mjs` (~480 lines)

| Section | Lines | Purpose |
|---------|-------|---------|
| Config | 10-25 | PORT, script paths, auth env vars |
| Helpers | 27-70 | `json()`, `parseBody()`, session management |
| Python runner | 72-95 | `runPython()` — spawn subprocess, collect stdout |
| Course index | 97-135 | `loadCourseIndex()`, `searchCourses()` — parse YAML, substring match |
| Match engine | 137-210 | `matchCourse()`, `parseAdHocOutput()` — proxy to ad-hoc-match.py, parse ANSI output |
| L1/L2 engines | 212-260 | `applyL1()`, `applyL2()`, `previewL1()`, `previewL2()` |
| HTTP server | 262-460 | Route handler: `/api/courses`, `/api/match`, `/api/preview`, `/api/apply`, `/api/auth`, `/api/oauth/*`, static files |
| Startup | 462-477 | `loadCourseIndex()`, `server.listen(PORT)` |

### `public/index.html` (~115 lines)

Semantic HTML5. Three `<section>` panels:

1. **Search panel** — text input with dropdown, "Find matches" button
2. **Matches section** — match cards list + detail panel with rung tabs, preview, apply button
3. **Activity section** — recent edit log (hidden when empty)

Accessibility: proper heading hierarchy, form labels, button semantics, keyboard-navigable dropdown.

### `public/style.css` (~575 lines)

Design system:
- **Colors:** MIT red (`#a31f34`) as primary, green (`#28a745`) for L1/apply, teal (`#17a2b8`) for L2
- **Layout:** CSS Grid for rung tabs, flexbox for cards and rows
- **Components:** Cards with hover/selected states, rung tabs with active highlight, score bars, dropdown, status messages
- **Responsive:** Single-column layout below 640px
- **Caching-friendly:** All CSS is a single file with no external dependencies

### `public/app.js` (~450 lines)

Single-page application (no framework):

| Section | Lines | Purpose |
|---------|-------|---------|
| State | 10-25 | Course data, matches, selected match, rung, activity log |
| API helpers | 27-40 | `apiFetch()` — thin wrapper around `fetch()` |
| Auth status | 42-55 | `checkAuth()` — polls `/api/auth/status` |
| Course search | 57-110 | Debounced autocomplete, keyboard navigation (↑↓Enter) |
| Match rendering | 112-145 | `renderMatches()` — creates cards with score bars and Wikipedia links |
| Detail panel | 147-190 | `showDetail()`, `updateRungDescription()`, `updatePreview()` |
| Wikitext preview | 192-225 | `generateWikitextLocal()` — fallback if server preview unavailable |
| Copy button | 227-240 | `navigator.clipboard.writeText()` with fallback |
| Apply button | 242-290 | `applyEdit()` — calls `/api/apply`, handles success/error, logs activity |
| Activity log | 292-310 | `logActivity()`, `renderActivity()` — localStorage persistence |
| Init | 312-340 | Check auth, render activity, focus search, handle URL hash |

---

## API Reference

### `GET /api/health`

Health check. Returns server status, course count, and auth state.

**Response:**
```json
{
  "status": "ok",
  "courses": 2573,
  "auth": false,
  "time": "2026-06-22T14:19:24.068Z"
}
```

### `GET /api/courses?q=<query>`

Search the course index. Returns up to 30 matches.

**Parameters:**
- `q` (string) — search query (case-insensitive substring match against course ID, title, department, topics)

**Response:**
```json
{
  "results": [
    {
      "slug": "6-006-introduction-to-algorithms-fall-2011",
      "id": "6.006",
      "title": "Introduction to Algorithms",
      "department": "6",
      "topics": ["Engineering", "Algorithms and Data Structures", ...]
    }
  ]
}
```

### `GET /api/match?course=<course-id-or-slug>`

Match a course to Wikipedia articles. Spawns `ad-hoc-match.py` as a subprocess.

**Parameters:**
- `course` (string, required) — OCW course ID (e.g., `6.006`), slug, or URL

**Response:**
```json
{
  "course": "6.006",
  "matches": [
    {
      "rank": 1,
      "title": "Introduction to Algorithms",
      "score": 39,
      "quality": "C",
      "views": 3588,
      "importance": "?",
      "templates": "",
      "match_source": "Wikipedia search",
      "refideas": false,
      "course_slug": "6-006-introduction-to-algorithms-spring-2008",
      "description": "Book on computer programming, used as textbook for algorithms courses"
    }
  ]
}
```

**Latency:** 2-5 seconds (Wikipedia API calls in the Python subprocess).

### `POST /api/preview`

Generate wikitext without posting to Wikipedia.

**Request body:**
```json
{
  "level": "L1",
  "courseId": "6.006",
  "courseTitle": "Introduction to Algorithms",
  "courseUrl": "https://ocw.mit.edu/courses/6-006-.../",
  "description": "Full course with video lectures."
}
```

**Response:**
```json
{
  "wikitext": "{{Refideas\n|1=[https://ocw.mit.edu/courses/6-006-.../ 6.006: Introduction to Algorithms], MIT OpenCourseWare\n|comment=6.006 covers topics relevant to this article.\n}}"
}
```

### `POST /api/apply`

Apply an edit to Wikipedia. Requires bot credentials.

**Request body:**
```json
{
  "level": "L1",
  "article": "Introduction to Algorithms",
  "courseId": "6.006",
  "courseTitle": "Introduction to Algorithms",
  "courseUrl": "https://ocw.mit.edu/courses/6-006-.../",
  "description": "Full course with video lectures."
}
```

**Response (success):**
```json
{ "success": true, "detail": "Edit applied" }
```

**Response (failure):**
```json
{ "success": false, "error": "Login failed: ..." }
```

**Response (no auth):** HTTP 503
```json
{ "error": "Bot credentials not configured" }
```

### `GET /api/auth/status`

Current authentication state.

**Response:**
```json
{
  "authenticated": false,
  "username": null,
  "method": "none"
}
```

### `GET /api/oauth/login`

Start OAuth 2.0 flow. Redirects to Meta Wikimedia authorization page. Only available when `OAUTH_CLIENT_ID` is configured.

### `GET /api/oauth/callback`

OAuth 2.0 callback. Exchanges authorization code for access token, fetches user profile, stores session.

---

## Auth Modes

| Mode | Env vars required | Edits attributed to | Status |
|------|------------------|---------------------|--------|
| **Read-only** | None | N/A (browse only) | ✅ Working |
| **Bot password** | `WIKI_BOT_USER`, `WIKI_BOT_PASS` | Bot account (e.g., `YourName@ocw-workbench`) | ✅ Working |
| **OAuth 2.0** | `OAUTH_CLIENT_ID`, `OAUTH_CLIENT_SECRET`, `OAUTH_CALLBACK` | Individual editor's Wikipedia account | 🔧 Stubbed — requires OAuth consumer registration |

### Setting up bot password auth

1. Create a bot password at `https://en.wikipedia.org/wiki/Special:BotPasswords`
   - Bot name: `ocw-workbench`
   - Grants: `Edit existing pages`, `Create, edit, and move pages`, `High-volume text querying`
2. Set environment variables:
   ```bash
   export WIKI_BOT_USER="YourWikiUsername@ocw-workbench"
   export WIKI_BOT_PASS="generated_bot_password_here"
   ```
3. Restart the server

---

## User Manual

### Getting Started

1. Open **http://localhost:8765** (local dev) or **https://wiki-mit.toolforge.org** (deployed)
2. Check the header — it shows your auth status:
   - **Not authenticated (read-only):** You can browse and preview, but not apply edits
   - **Logged in as YourName:** Bot credentials are active — you can apply edits

### Step 1: Find a Match

1. Type a course ID or title in the search box (e.g., `6.006`, `algorithms`, `photovoltaics`)
2. A dropdown appears with matching OCW courses — use **↑↓ arrow keys** or click to select
3. The search box fills with the selected course (e.g., `6.006 — Introduction to Algorithms`)
4. Click **🔍 Find matches** (or press **Enter**)

The app will search Wikipedia for articles that match your course content. This takes 2-5 seconds.

### Step 2: Review Matches

Matches appear as ranked cards, each showing:
- **Rank** (1, 2, 3...) and **title** (clickable link to Wikipedia)
- **Quality** (FA, GA, B, C, Start, Stub, or ?)
- **Pageviews** (monthly)
- **Score** (0-100 bar, higher = better match)

Click any match card to expand the detail panel.

### Step 3: Choose a Contribution Level

The detail panel shows two rung tabs:

| Rung | What it does | Risk | Where |
|------|-------------|------|-------|
| **💬 L1 — Refideas** | Suggests the course as a reference | Safe | Article Talk page |
| **🔗 L2 — External link** | Adds the course link to External links | Low risk | Article footer |

Click the tab for the contribution type you want.

### Step 4: Preview and Apply

1. The **wikitext preview** shows exactly what will be posted to Wikipedia
2. Click **📋 Copy** to copy the wikitext to your clipboard (for manual pasting)
3. Click **📝 Apply to Wikipedia** to post the edit automatically (requires auth)

### Step 5: Track Activity

The **Recent activity** section at the bottom shows your last 10 actions:
- ✅ Green = successful edit
- ⚠️ Yellow = failed (click for a link to edit manually on Wikipedia)
- Each entry shows: level, article name, course ID, and time

Activity persists across browser sessions via `localStorage`. It's private to your browser.

### Keyboard Shortcuts

| Key | Context | Action |
|-----|---------|--------|
| `↑` / `↓` | Search dropdown open | Navigate results |
| `Enter` | Search dropdown open | Select highlighted result |
| `Enter` | Search box, course selected | Trigger "Find matches" |

### Tips

- **Course IDs work best** — `6.006`, `18.06`, `5.111SC` are unique and fast
- **Partial titles work too** — `algorithms`, `quantum`, `climate` search across all 2,577 courses
- **Paste a Wikipedia URL** in the search box — not yet supported but designed for
- **The preview is always available**, even without auth — you can copy wikitext and paste manually
- **L1 (Refideas) is the safest choice** — it only posts to the Talk page, never modifies the article

---

## Deployment

### Local Development

```bash
cd toolforge
node server.mjs
# Open http://localhost:8765
```

Course search and match preview work without any configuration. Applying edits requires bot credentials.

### Toolforge Deployment

```bash
# One-time setup: create the tool
python3 ~/.pi/agent/skills/toolforge/scripts/login-toolsadmin.py \
  --create wiki-mit "Wiki MIT Workbench" \
  "Contribution interface connecting MIT OCW to Wikipedia"

# Set credentials
ssh <user>@login.toolforge.org
become wiki-mit toolforge env set WIKI_BOT_USER "YourName@ocw-workbench"
become wiki-mit toolforge env set WIKI_BOT_PASS "your_bot_password"

# Deploy
cd toolforge
./deploy.sh
```

The app will be available at `https://wiki-mit.toolforge.org`.

### Monitoring

```bash
# Check status
ssh <user>@login.toolforge.org "become wiki-mit webservice --backend=kubernetes node22 status"

# View logs
ssh <user>@login.toolforge.org "become wiki-mit kubectl logs -f deployment/wiki-mit"

# Restart
ssh <user>@login.toolforge.org "become wiki-mit webservice --backend=kubernetes node22 restart"
```

---

## Error Handling & Edge Cases

### Server-Side

| Scenario | Handling |
|----------|----------|
| **Python script fails** | Caught in `runPython()`, returns `{error: "..."}` with stderr message |
| **Match returns 0 results** | Returns empty `matches[]` — UI shows "No strong matches found" with suggestion |
| **Auth not configured** | `/api/apply` returns HTTP 503 with clear message |
| **Course files missing** | `loadCourseIndex()` logs warning, server starts with empty index — search falls back to free-text mode |
| **ANSI parsing fails** | `parseAdHocOutput()` returns empty array — no crash |
| **Path traversal** | Static file resolver checks `startsWith(safeDir)` — returns 403 |
| **Course index directory missing** | Caught in try/catch, server starts with empty index |

### Client-Side

| Scenario | Handling |
|----------|----------|
| **API unavailable** | Course search falls back to free-text entry (user can still type course IDs manually) |
| **Preview API fails** | Falls back to `generateWikitextLocal()` — client-side wikitext generation |
| **Apply API fails** | Shows error with link to manual Wikipedia edit page |
| **Copy fails** | Falls back to `document.execCommand('copy')` via hidden textarea |
| **localStorage full** | Activity log silently truncated to 20 entries |
| **Search with no results** | Dropdown shows "No courses found" |
| **Double-click apply** | Button disabled immediately, prevents duplicate submissions |

---

## Future Roadmap

### Short-term (v0.2)

- [ ] **OAuth 2.0 integration** — register consumer on Meta, implement full Authorization Code Grant
- [ ] **L2 dry-run preview** — show the exact wikitext diff before applying
- [ ] **Wikipedia article URL input** — paste an article URL to find matching OCW courses for it
- [ ] **Match quality indicators** — color-code matches by score (green > 70, yellow > 40, red < 40)
- [ ] **Server-side activity log** — SQLite on NFS for persistent, shared activity history

### Medium-term (v0.3)

- [ ] **L3 support** — replace `{{citation needed}}` tags (requires `ad-hoc-match.py` to detect templates)
- [ ] **Batch mode** — select multiple articles and apply L1/L2 to all
- [ ] **Per-WikiProject filtering** — filter matches by WikiProject (Chemistry, Physics, etc.)
- [ ] **Edit diff preview** — show side-by-side wikitext diff in the preview panel

### Long-term (v1.0)

- [ ] **Multi-corpus support** — arXiv, JSTOR, PubMed Central as additional corpora (see `docs/CONTRIBUTION-LADDER.md`)
- [ ] **Per-editor stats dashboard** — acceptance rates, edit counts, rung progress
- [ ] **Wikipedia gadget integration** — "Match-as-you-browse" sidebar on Wikipedia articles
- [ ] **On-wiki review queue** — post suggestions to Meta wiki page for community review

---

## Reference

| Document | Covers |
|----------|--------|
| `toolforge/README.md` | Quick start and deployment guide |
| `docs/CONTRIBUTION-LADDER.md` | Generalized corpus-agnostic framework design |
| `docs/CONTRIBUTION-UI.md` | Five deployment approaches and UI architecture decisions |
| `docs/CONTRIBUTION-LEVELS.md` | Full L1-L5 specification |
| `docs/CONTRIBUTION-PROTOCOL.md` | ContributionRecord data schema |
| `docs/ROADMAP.md` | Project roadmap — Phase 3 (contribution interface) |
| `scripts/ad-hoc-match.py` | Match provider architecture (called as subprocess) |
| `scripts/contribution-protocol.py` | Wikitext generation (called as subprocess) |
