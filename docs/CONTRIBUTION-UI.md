# Contribution UI — Interface Options

> **Status:** Design phase. Evaluating deployment options for the contribution interface that bridges the OCW match pipeline to Wikipedia editing.
> **Depends on:** `docs/CONTRIBUTION-LEVELS.md`, `docs/CONTRIBUTION-PROTOCOL.md`, `docs/CONTRIBUTION-LADDER.md`, `docs/ROADMAP.md`

---

## What we're wiring together

Three existing subsystems need to become one editing pipeline:

```
OCW Course Wiki (2,577 courses)
        │
        ▼
Match Engine (ad-hoc-match + crossref scoring)
        │
        ▼
Impact Matrix (which articles need work?)
        │
        ▼
Contribution Editor (L1→L2→L3 actions)
        │
        ▼
Wikipedia (live edits via OAuth/bot password)
```

The interface needs to bridge the gap between "here's a match" and "here's a posted edit" — with varying degrees of human involvement.

---

## The Contribution Ladder as UX

The defining UX concept is a **ladder** that editors climb. Each rung requires progressively more trust and skill:

```
Rung 5: Write new content           ─┐
Rung 4: Fill [missing information]    ├─ Content creation (needs corpus-specific prose)
Rung 3: Replace [citation needed]    ─┘
Rung 2: Add external link            ─┐
Rung 1: Suggest as {{refideas}}       └─ Mechanical (pure formatting)
```

An editor's journey through a session:

1. **Browse:** Open the Impact Matrix, select a WikiProject, see which articles need work
2. **Match:** Click an article with maintenance templates, see matching OCW courses
3. **Climb:** Choose a rung — L1 for a safe talk page suggestion, L2 for an external link, L3 to replace a `[citation needed]` tag
4. **Review:** See the pre-formatted wikitext with a diff preview
5. **Apply:** One click (or copy-paste in the advisory phase)

The ladder is the same regardless of corpus — whether citing MIT OCW or arXiv, the flow from browse to apply is identical. What changes is the citation format.

---

## Five approach options

### Approach 1: On-Wiki Interface (Wiki-Native, Lowest Friction)

**Concept:** Host the contribution interface directly on a wiki page. Wikipedia editors already live on-wiki. Meet them there.

**What it looks like:** A rich subpage at `meta.wikimedia.org/wiki/Wiki_MIT/Workbench` that loads match data and presents a filterable review queue. Editors visit this page like any other, click through suggestions, and apply edits.

**How it's built:**
- **TemplateStyles** — full CSS Grid layout, cards, color themes, responsive breakpoints. No external CSS needed.
- **Static JSON data** — pre-computed match data uploaded as wiki JSON subpages (or embedded in a `<templatestyles>` block).
- **Wikipedia JS** — gadget-style script on the page that renders the queue, handles filtering, and calls the MediaWiki API.
- **OAuth 2.0** — registered as an owner-only consumer on Meta. The JS obtains a token and makes `action=edit` calls.

**Pros:**
- Zero hosting cost — the wiki is the host
- No separate domain to remember or trust
- Editors stay in their native environment
- Uses Wikipedia's existing auth, abuse filters, and rate limiting
- Can be linked from WikiProject pages, talk page templates, existing heatmap

**Cons:**
- Limited JS ecosystem (no npm dependencies, must work within MediaWiki JS constraints)
- Large data files (match data) need creative loading on-wiki
- OAuth redirect URI requires a separate callback (Toolforge or `oob` flow)

**Effort:** Medium (2-3 sessions)

---

### Approach 2: Toolforge Web App (Full Control, Multi-User)

**Concept:** A proper web application at `https://wiki-mit.toolforge.org` that provides the complete pipeline from match discovery to edit application.

**What it looks like:** A three-panel layout — left: WikiProject/article browser (like the Impact Matrix), center: match details + wikitext preview, right: contribution queue. OAuth login in the header. Stats dashboard showing edits made, acceptance rates, editor activity.

**How it's built:**
- **Toolforge Node.js** — zero-dependency HTTP server in a single `.mjs` file. Serves static HTML/JS and a thin API.
- **OAuth 2.0** — full Authorization Code Grant with PKCE. Multi-user. Each editor logs in with their Wikipedia account, the tool gets a token, and edits are attributed to them personally.
- **Python API proxy** — existing Python match/lint/edit scripts become API endpoints behind the Node.js server.
- **SQLite or JSON files on NFS** for persistence — track which suggestions have been shown, accepted, rejected.

**Architecture sketch:**
```
Browser (wiki-mit.toolforge.org)
  │
  ├─ GET / → static SPA (HTML/JS/CSS on NFS)
  ├─ GET /api/matches?project=Chemistry&quality=C → Python subprocess → JSON
  ├─ POST /api/apply-l1 → Python subprocess → action=edit (with user's OAuth token)
  └─ OAuth 2.0 flow → Special:OAuth/authorize → /oauth/callback → store token
```

**Pros:**
- Full UX control — no wiki-imposed limitations
- Proper OAuth means edits carry the editor's name and reputation (not a bot)
- Can track acceptance rates and improve matching over time
- Serves as the central hub linking all tools (Impact Matrix, Heatmap, Workbench)

**Cons:**
- More infrastructure to maintain (Toolforge webservice, OAuth consumer registration)
- Separate domain from Wikipedia — editors need to discover it
- Needs ongoing webservice uptime

**Effort:** Medium-High (3-5 sessions)

---

### Approach 3: Static HTML + Lightweight API Proxy (Incremental)

**Concept:** Start with static HTML (like the Impact Matrix) for browsing, and add a thin Toolforge proxy only for the bits that need a server (OAuth callback, edit actions).

**What it looks like:** A single HTML file (`wiki/editor/standalone.html`) that works from `file://` for browsing matches. When the user clicks "Apply to Wikipedia," they're redirected to a minimal Toolforge endpoint that handles OAuth and proxies the edit.

**How it's built:**
- **Phase 1 (no server):** A `wiki/editor/standalone.html` that loads match data, shows the filterable queue, generates wikitext snippets with "Copy to clipboard." Exactly as Phase 3a of the roadmap. Zero infrastructure.
- **Phase 2 (minimal server):** A 50-line Node.js server on Toolforge that does exactly two things: OAuth callback handling, and `action=edit` proxy. The static page posts to it with the user's OAuth token.

**Pros:**
- Advisory-only version works with zero infrastructure
- Graduated deployment — each phase delivers value independently
- Preserves `file://` constraint for browse/explore
- Static HTML can be reused in the Toolforge and on-wiki approaches

**Cons:**
- Two codebases (static HTML + server API) to keep in sync
- Cross-origin requests from `file://` to Toolforge API need CORS headers
- OAuth flow from a `file://` page is awkward (no proper redirect URI)

**Effort:** Low for Phase 1 (1-2 sessions), Medium for Phase 2 (1-2 sessions)

---

### Approach 4: Wikipedia Gadget — "Match-As-You-Browse"

**Concept:** A Wikipedia user script or gadget that adds an OCW match panel to any Wikipedia article you're viewing. When you land on "Photovoltaics," a sidebar shows: "3 MIT OCW courses cover this topic → [Suggest reference] [Add external link]."

**What it looks like:** A collapsible panel injected into the Wikipedia sidebar (or as a floating button). Clicking expands a compact card with matching courses and one-click action buttons.

**How it's built:**
- A single JS file registered as a Wikipedia gadget (or loaded as a user script)
- Bundles a compact match lookup table (article → courses) or queries a Toolforge API
- Uses the MediaWiki JS API (`mw.Api`) to fetch page wikitext and make edits
- OAuth for attribution — the gadget gets a token stored in `localStorage`

**Pros:**
- **Zero context-switching** — the editor is already on the article
- Discovery happens naturally during normal browsing
- Low commitment — try as a user script, graduate to a gadget if popular
- The suggestion appears exactly where and when it's most relevant

**Cons:**
- Bundling match data into a gadget is challenging (the data is large)
- Solution: a bloom-filter-like structure saying "this article has a match" + Toolforge API for details
- Gadget approval process on Wikipedia requires community consensus
- More complex client-side logic than the other approaches

**Effort:** Medium (2-3 sessions)

---

### Approach 5: Bot-Generated Suggestions → Human Review Queue

**Concept:** A scheduled bot runs the match pipeline nightly, generates L1 refideas wikitext for all new matches, and posts them to a centralized review page. Human editors review and apply. The simplest possible "interface."

**What it looks like:** A wiki page at `Wikipedia:WikiProject MIT/OCW suggestions` (or on Meta) listing pre-formatted `{{refideas}}` snippets, grouped by WikiProject. Each entry has a "Publish to Talk page" link.

**How it's built:**
- **Cron job on Toolforge** — runs `generate-matches.py` → `prioritize-matches.py` → formats output as a wikitext table
- Posts the table to a wiki page via bot password
- Human editors review and copy-paste (or a gadget auto-posts)

**Pros:**
- Truly minimal interface — the "interface" is just a wiki page
- No OAuth needed for the bot
- Editors already know how to review wiki pages
- Can be running tomorrow

**Cons:**
- No interactive filtering or scoring exploration
- Human copy-paste is error-prone
- Doesn't scale to L2/L3 without additional tooling
- The review page becomes stale between bot runs

**Effort:** Very Low (1 session)

---

## Recommended path: Composite strategy

Layer these approaches in order of increasing complexity, with each building on the last:

```
               NOW ──────────────────────────────► FUTURE
                │                                     │
Approach 5      │  Bot-generated review page          │
(Week 1)        │  on Meta — running tomorrow         │
                │                                     │
Approach 3      │     Static advisory HTML            │
Phase 1         │     (Phase 3a from roadmap)         │
(Week 1-2)      │                                     │
                │                                     │
Approach 1      │        On-Wiki Workbench page       │
(Week 2-3)      │        with TemplateStyles UI       │
                │        + OAuth one-click editing     │
                │                                     │
Approach 4      │           Wikipedia Gadget —        │
(Week 3-4)      │           "Match As You Browse"     │
                │                                     │
Approach 2      │              Toolforge Web App      │
(Week 4-6)      │              Full dashboard         │
                │                                     │
```

Each layer builds on the data and auth plumbing of the previous one. The on-wiki and gadget approaches share the same OAuth consumer and API endpoints.

---

## Architecture decision matrix

Decisions to make before building:

| Decision | Options | Recommendation |
|----------|---------|----------------|
| **Auth model** | Bot password vs. OAuth 2.0 owner-only vs. OAuth 2.0 multi-user | Start with bot for the scheduled review page (Approach 5), then add OAuth 2.0 multi-user for interactive tools |
| **Data delivery** | Static JSON files vs. REST API vs. embedded in gadget | Static JSON for Phase 1, thin Toolforge API as needs grow |
| **Hosting** | Toolforge vs. Meta wiki page vs. both | Both: on-wiki for the review queue, Toolforge for the OAuth callback and heavier compute |
| **Edit attribution** | Bot account vs. individual editor accounts | **Individual editor accounts via OAuth** — crucial for community acceptance. Edits from real editors are far less likely to be reverted than bot edits |
| **Match freshness** | Pre-computed batch vs. on-demand matching | Pre-computed batch with daily refresh. Most course-article matches don't change rapidly |

---

## Static advisory UI — Phase 1 layout sketch

The first deliverable: a single HTML file at `wiki/editor/index.html` that works from `file://`.

```
┌──────────────────────────────────────────────────────────────┐
│  Wiki MIT — Contribution Workbench                           │
│                                                              │
│  [Corpus: OCW ▾]  [WikiProject: All ▾]  [Rung: L1 ▾]        │
│  [Quality: All ▾]  [Score ≥ 70]  [Search...]                 │
│                                                              │
│  Active filters: ✕ Chemistry  ✕ L1  ✕ Score ≥ 70            │
│                                                              │
│  ┌──────────────────────────────────────────────────────────┐│
│  │ ▸ Photovoltaics (C, High, 42K views)  ← 5.111SC (92)    ││
│  │   WikiProject Energy                                     ││
│  │                                                          ││
│  │   L1 ▼  {{Refideas}} to Talk page                        ││
│  │   ┌────────────────────────────────────────────────────┐ ││
│  │   │ {{Refideas                                         │ ││
│  │   │ |1={{cite web |url=https://ocw.mit.edu/...         │ ││
│  │   │   |title=Principles of Chemical Science            │ ││
│  │   │   |publisher=MIT OpenCourseWare}}                  │ ││
│  │   │ |comment=MIT 5.111SC covers solar cell physics...  │ ││
│  │   │ }}                                                 │ ││
│  │   └────────────────────────────────────────────────────┘ ││
│  │   [📋 Copy to clipboard]  [🔗 Open Talk page]            ││
│  │                                                          ││
│  │   L2    External link to == External links ==            ││
│  │                                                          ││
│  │   L3    Replace [citation needed] in §Photovoltaics      ││
│  └──────────────────────────────────────────────────────────┘│
│                                                              │
│  ┌──────────────────────────────────────────────────────────┐│
│  │ ▸ Solar cell (Start, Mid, 28K views)  ← 3.024 (76)      ││
│  │   ...                                                    ││
│  └──────────────────────────────────────────────────────────┘│
│                                                              │
│  Showing 12 of 156 matches  ·  [Load more]                   │
└──────────────────────────────────────────────────────────────┘
```

### Key behaviors

- **Corpus selector** — single-corpus for now (OCW), but designed for multi-corpus from the start
- **Rung selector** — per-article dropdown: L1 (refideas), L2 (external link), L3 (citation) where applicable. Only show rungs that apply to this match
- **Wikitext preview** — rendered in a `<pre>` block with syntax-highlighted citation template
- **Copy to clipboard** — one click copies the exact wikitext to paste into the Wikipedia editor
- **Open Talk page** — opens the Wikipedia Talk page in a new tab, pre-positioned for pasting
- **Filters** — WikiProject, quality class, score threshold, rung level, text search on article title
- **Active filter chips** — removable, like the Impact Matrix

### Data format

Reads from the same static data files as the Impact Matrix:

```javascript
// wiki/impact-matrix/data/live-data.js — existing, article metadata
// wiki/impact-matrix/data/ocw-matches.js — Phase 2a deliverable, per-article OCW matches
```

Each match entry:
```json
{
  "article": "Photovoltaics",
  "quality": "C",
  "importance": "High",
  "views": 42000,
  "wikiproject": "Energy",
  "templates": ["citation needed", "refimprove"],
  "matches": [
    {
      "course_id": "5.111SC",
      "course_title": "Principles of Chemical Science",
      "course_url": "https://ocw.mit.edu/courses/5-111sc-.../",
      "lecture_title": "Lecture 12: VSEPR Theory",
      "match_score": 92,
      "resource_type": "video",
      "applicable_rungs": ["L1", "L2", "L3"]
    }
  ]
}
```

---

## OAuth upgrade path — Phase 2

Once the advisory UI is working, add one-click editing:

### OAuth 2.0 flow (for the Toolforge web app)

```
User clicks "Log in with Wikipedia"
  │
  ▼
Redirect to: https://en.wikipedia.org/wiki/Special:OAuth/authorize
  ?oauth_callback=https://wiki-mit.toolforge.org/oauth/callback
  &consumer_key=<registered consumer key>
  │
  ▼
User authorizes the app on Wikipedia
  │
  ▼
Redirect back to Toolforge with ?code=...
  │
  ▼
POST to /rest.php/oauth2/access_token
  { grant_type: "authorization_code", code: "..." }
  │
  ▼
Store { access_token, refresh_token, expires_at }
  │
  ▼
EDIT: POST to /w/api.php?action=edit
  Authorization: Bearer <access_token>
```

### OAuth 2.0 flow (for on-wiki JS — out-of-band)

```
JS opens popup to Special:OAuth/authorize?oauth_callback=oob
  │
  ▼
User authorizes, sees a code on screen
  │
  ▼
User pastes code into the widget
  │
  ▼
JS exchanges code for token via Toolforge proxy (CORS-safe)
  │
  ▼
Token stored in localStorage
```

### What changes in the UI

| Advisory (Phase 1) | Authenticated (Phase 2) |
|--------------------|------------------------|
| "Copy to clipboard" | "Apply to Talk page" |
| "Open Talk page" link | Inline diff preview |
| No edit history | "Recently applied" section |
| No user state | OAuth login in header, editor name shown |
| Manual paste | One-click apply with edit summary |

---

## Per-corpus metrics dashboard (Phase 3+)

Once multiple corpora are active, the UI should show:

- **Per-corpus stats:** edits attempted, edits accepted, revert rate, editor count
- **Per-WikiProject stats:** which projects are most active, which need attention
- **Per-rung stats:** L1 vs L2 vs L3 usage, average time from suggestion to apply
- **Editor leaderboard:** gamification — "WikiProject MIT" stats per editor (rung reached, edits made)

This data feeds back into the match scoring: if a corpus has high revert rates, its matches get down-weighted or restricted to L1-only.

---

## Reference

| Document | Covers |
|----------|--------|
| `docs/CONTRIBUTION-LEVELS.md` | Full L1-L5 specification and processing details |
| `docs/CONTRIBUTION-PROTOCOL.md` | `ContributionRecord` schema, validation rules, work queue structure |
| `docs/CONTRIBUTION-LADDER.md` | Generalized corpus-agnostic framework, pluggable abstractions |
| `docs/ROADMAP.md` | Project roadmap — Phase 2 (integration), Phase 3 (contribution interface), Phase 4 (generalization) |
| `docs/AD-HOC-MATCH.md` | Match provider architecture, 5 filter layers, scoring formula |
| `docs/impact-matrix/design.md` | Impact Matrix architecture — data flow pattern to reuse |
| `docs/impact-matrix/prd.md` | MIT Mode feature spec (Phase 2b) |
