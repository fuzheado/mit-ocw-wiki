# Feature Requests — Wiki MIT Contribution Workbench

> Running list of feature ideas for the web interface at `toolforge/`.
> Add new requests at the bottom. Mark as `✅ Done`, `🚧 In Progress`, or `📋 Planned`.

---

## 📋 Manual Wikipedia Article Entry

**Requested:** 2026-06-22

Currently the only way to select a target article is through the match pipeline
(search OCW course → get ranked matches → pick one). There's no way to say
"I already know which article I want to edit — just let me type it in."

**What it would look like:**

Add a toggle or secondary input in Step 1:

```
  [🔍 Match from course]  |  [✏️ Direct entry]
  
  ── Direct entry mode ──
  Article: [Photovoltaics                    ] [🔍 Verify]
  (or paste Wikipedia URL)
  
  Course:  [5.111SC — Principles of Chemical Science] [🔍 Find]
  
  → Preview wikitext → Apply
```

**Implementation notes:**
- Add a "Direct entry" tab in the search panel
- Article input: typeahead against Wikipedia search API (`action=opensearch`)
- Course input: existing course search (reuse)
- Skip the match step entirely — go straight to L1/L2 preview
- `POST /api/preview` and `POST /api/apply` already accept arbitrary `article` parameters
- Validation: warn if article doesn't exist or is a redirect

**Effort:** Small (1 session) — mostly UI work, the API already supports it

---

## 📋 Manual Link Entry (Any URL, Not Just MIT OCW)

**Requested:** 2026-06-22

Currently L1 and L2 previews are hardcoded to MIT OpenCourseWare formatting
(`publisher=MIT OpenCourseWare`, course ID labeling). There's no way to add
an arbitrary external link or refideas suggestion for a non-OCW resource.

**What it would look like:**

Add a "Custom link" mode alongside the course-based flow:

```
  ── Custom link mode ──
  Article: [Photovoltaics                   ]
  URL:     [https://example.org/solar-paper ]
  Label:   [Solar Cell Efficiency Paper     ]
  Source:  [Journal of Applied Physics       ]
  Note:    [Covers latest perovskite research ]
  
  → Generates L1: {{Refideas |1=[url label], source (note)}}
  → Generates L2: * {{cite web |url=... |title=label |publisher=source}} — note
```

**Implementation notes:**
- New `POST /api/preview/custom` endpoint that accepts arbitrary URL/label/source instead of course ID
- Client-side: toggle between "OCW course" mode and "Custom link" mode
- The `contribution-protocol.py` pure functions already support arbitrary URLs — just need to expose them through the API
- Validation: basic URL format check, warn if domain is on Wikipedia's blocklist
- Activity log: mark entries as "custom" vs "ocw"

**Bonus:** This generalizes the Workbench toward the multi-corpus vision in
`docs/CONTRIBUTION-LADDER.md` — "custom link" is essentially a generic
`CorpusConnector` that accepts free-form input.

**Effort:** Small-Medium (1-2 sessions) — new endpoint + UI toggle + validation

---

## 📋 L2 Dry-Run Diff Preview

**Source:** `toolforge/DESIGN.md` v0.2 roadmap

Before applying an L2 edit, show exactly what the External links section
will look like after the edit — the current wikitext, a diff highlighting
the added line, and the new section state.

**Effort:** Medium — requires fetching article wikitext via API and rendering a diff

---

## 📋 Wikipedia Article URL Input in Search

**Source:** `toolforge/DESIGN.md` v0.2 roadmap

Allow pasting a full Wikipedia URL (e.g., `https://en.wikipedia.org/wiki/Photovoltaics`)
in the search box to find matching OCW courses for that article. The reverse of the
current flow (currently: course → articles; want: article → courses).

**Effort:** Small — parse URL, extract title, call match in reverse

---

## 📋 Match Quality Color Coding

**Source:** `toolforge/DESIGN.md` v0.2 roadmap

Color-code match cards by score threshold:
- Green (score ≥ 70): strong match
- Yellow (score ≥ 40): moderate match
- Red (score < 40): weak match

**Effort:** Trivial — CSS class on match cards based on score

---

## 📋 Server-Side Activity Log

**Source:** `toolforge/DESIGN.md` v0.2 roadmap

Replace browser `localStorage` with server-side SQLite database on Toolforge NFS.
Enables shared activity history across browsers, per-editor stats, and persistence
across pod restarts.

**Effort:** Medium — SQLite integration + migration from localStorage

---

## 📋 Rung 3: Replace [Citation Needed]

**Source:** `docs/CONTRIBUTION-LEVELS.md`, Phase 3c roadmap

Add L3 tab to the rung selector. Find `{{citation needed}}` tags on the target
article and offer to replace them with OCW-sourced `<ref>` citations.

**Prerequisite:** The match pipeline needs to detect templates on the article.
Current match data doesn't include template information.

**Effort:** Large (2-3 sessions) — template detection + L3 formatter + UI

---

## 📋 Batch Mode — Apply to Multiple Articles

**Source:** `toolforge/DESIGN.md` v0.3 roadmap

Select multiple matches and apply L1/L2 to all of them in one session.
Shows a confirmation dialog with a summary of all edits.

**Effort:** Medium — UI multi-select + sequential API calls with progress bar

---

## 📋 OAuth 2.0 Multi-User Authentication

**Source:** `toolforge/DESIGN.md` v0.2 roadmap

Replace bot password auth with full OAuth 2.0 Authorization Code Grant.
Edits are attributed to individual editor accounts instead of a bot.

**Prerequisite:** Register OAuth consumer on Meta Wikimedia.

**Effort:** Medium-Large — OAuth flow + session management + consumer registration

---

## 📋 Per-WikiProject Filtering

**Source:** `toolforge/DESIGN.md` v0.3 roadmap

Add a WikiProject filter dropdown to the match results: "Show only
matches in WikiProject Chemistry / Physics / etc."

**Effort:** Small — filter on existing match data

---

## 📋 Diff Preview in Detail Panel

**Source:** `toolforge/DESIGN.md` v0.3 roadmap

When previewing an edit, show a side-by-side or unified diff of the
wikitext before and after the edit. Currently only shows the snippet
to be inserted, not what the page looks like with it.

**Effort:** Medium — requires fetching page wikitext + diff library

---

## Legend

| Icon | Meaning |
|------|---------|
| 📋 | Planned (not yet started) |
| 🚧 | In progress |
| ✅ | Done |
