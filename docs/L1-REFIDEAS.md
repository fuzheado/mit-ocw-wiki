# L1 Contribution: Talk Page `{{refideas}}`

> **Status:** Algorithm validated on real Wikipedia Talk pages. Refactored into pure-function + orchestrator pattern for testability. Reference implementation in `scripts/contribution-protocol.py`. Generic and OCW-specific CLI tools available.

---

## What it is

A `{{refideas}}` template posted to an article's Talk page that suggests OCW resources as potential references. It does **not** modify the article itself — it's a non-invasive suggestion for editors. Used on ~29,000 Wikipedia pages.

## What it looks like

Standard Wikipedia convention — plain external links with a source attribution:

```wikitext
{{refideas
| 1 = [https://ocw.mit.edu/courses/5-111sc-principles-of-chemical-science-fall-2014/ MIT 5.111SC: Principles of Chemical Science], MIT OpenCourseWare (video lecture, lecture notes, and problem set with solutions)
| 2 = [https://ocw.mit.edu/courses/2-60j-fundamentals-of-advanced-energy-conversion-spring-2020/resources/mit2_60s20_lec18/ 2.60 S2020 Lecture 18: Geothermal Energy], MIT OpenCourseWare (general info)
}}
```

**Do NOT use `{{cite web}}` templates inside `{{refideas}}`.** Wikipedia editors use plain `[url Label]` format. Using `{{cite web}}` works syntactically but is visually heavier and non-standard.

The template also supports:
- `|comment=` — a note at the bottom of the reference list
- `|state=collapsed` — collapse the box when there are many references
- Up to 21 numbered parameters (`|1=` through `|21=`)

When a `{{refideas}}` template is added to a Talk page, it automatically triggers `{{Refideas editnotice}}` on the article page — editors visiting the article see a banner reminding them about the suggested references.

## Where it goes

**Top of the Talk page, after the last metadata banner, before the first `== Discussion section ==`.**

Example placement (from multiple real Talk pages, including Boeing, Geothermal energy):

```wikitext
{{Talk header}}
{{WikiProject banner shell|class=B|...}}
{{User:MiszaBot/config|...}}
}}                                          ← last banner closes here
{{refideas                                   ← INSERTED HERE
| 1 = [url Label], Source
}}
                                             ← blank line
== First discussion topic ==                 ← first heading
...
```

This placement is the Wikipedia convention because:
- It groups `{{refideas}}` with other metadata banners, not with discussion threads
- It ensures the editnotice fires (which only triggers when the template is in the banner area)
- It's immediately visible to editors visiting the Talk page

## The algorithm

```
                    ┌──────────────────────┐
                    │ 1. Fetch Talk page   │
                    │    wikitext via API   │
                    │    action=parse       │
                    │    &prop=wikitext     │
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │ 2. Parse with        │
                    │    mwparserfromhell  │
                    └──────────┬───────────┘
                               │
              ┌────────────────▼────────────────┐
              │ 3. Existing {{refideas}}?        │
              │                                    │
              │  code.filter_templates(           │
              │    matches=lambda t:              │
              │      str(t.name).lower().strip()  │
              │      == "refideas"                │
              │  )                                │
              └────────┬──────────────┬───────────┘
                       │ YES          │ NO
                       ▼              ▼
           ┌────────────────┐  ┌──────────────────────┐
           │ 4a. APPEND     │  │ 4b. Find first       │
           │                │  │     == Heading ==     │
           │ Find highest   │  │     via               │
           │ numbered param │  │     filter_headings() │
           │ (int(name))    │  └──────────┬───────────┘
           │                │             │
           │ tmpl.add(      │  ┌──────────▼───────────┐
           │   str(n+1),    │  │ 5. Heading found?    │
           │   ref          │  └──┬──────────────┬────┘
           │ )              │     │ YES          │ NO
           │                │     ▼              ▼
           │ str(code)      │  ┌───────────┐  ┌──────────┐
           └────────────────┘  │ INSERT    │  │ APPEND   │
                               │ before    │  │ at end   │
                               │ heading   │  │ of page  │
                               └───────────┘  └──────────┘
```

### Step details

**Step 1 — Fetch Talk page wikitext:**
```
GET /w/api.php?action=parse&page=Talk:Nuclear_weapon&prop=wikitext&format=json&formatversion=2
```
**User-Agent required.** Use: `MIT OCW Bot/1.0 (https://meta.wikimedia.org/wiki/Wiki_MIT; andrew.lih@gmail.com) ContentGapResearch`

**Step 3 — Check for existing Refideas:**
```python
code = mwparserfromhell.parse(wikitext)
existing = code.filter_templates(
    matches=lambda t: str(t.name).lower().strip() == "refideas"
)
```

⚠️ **Critical:** `filter_templates(matches=...)` passes the **Template node**, not the name string. Use `t.name` to get the name. `str(t)` returns the full wikitext including `{{` and `}}`, which will never match `"refideas"`.

**Step 4a — Append to existing:**
```python
tmpl = existing[0]
max_num = max(
    int(str(p.name).strip()) 
    for p in tmpl.params 
    if str(p.name).strip().isdigit()
)
tmpl.add(str(max_num + 1), "[url Label], Source (note)")
new_wikitext = str(code)  # mwparserfromhell serializes the modified AST
```

**Step 4b — Find insertion point:**
```python
headings = code.filter_headings()
if headings:
    first_text = str(headings[0].title).strip()
    # Find in original wikitext (not parsed code — we need byte position)
    import re
    pattern = rf'\n==\s*{re.escape(first_text)}\s*=='
    m = re.search(pattern, wikitext)
    if m:
        new_wikitext = wikitext[:m.start()] + refideas_block + wikitext[m.start():]
```

⚠️ **Do not use `re.split(r'\n==', ...)` to find the first heading.** Regex `==` can match inside template parameters, wikitext tables, or HTML comments. Use mwparserfromhell's AST-based `filter_headings()` to find real headings, then locate them in the original wikitext string.

## API calls needed

| # | Endpoint | Purpose |
|---|----------|---------|
| 1 | `action=parse&page=Talk:{title}&prop=wikitext` | Fetch current Talk page wikitext |
| 2 | `action=query&meta=tokens&type=csrf` | Get edit token |
| 3 | `action=edit&title=Talk:{title}&text=...&token=...` | Post the edit |

Total: 3 API calls per contribution.

## Deduplication

Before posting, check the Talk page for:
1. The exact OCW course URL already present in any `{{refideas}}` parameter
2. If found, skip (already suggested)

After posting, log to a local JSON file:
```json
{
  "article": "Nuclear weapon",
  "course_id": "22.01",
  "level": "L1",
  "timestamp": "2026-05-25T12:00:00Z",
  "revision_id": 12345678
}
```

## Empirical findings (from sampling 25 crossref-matched articles)

| Pattern | Count | % | Handled by |
|---------|-------|---|-----------|
| Banner Shell (`{{WikiProject banner shell\|...}}`) then discussion | 22 | 88% | Insert before first heading |
| Complex (banner shell + tables, todo lists, extra banners) | 2 | 8% | Insert before first heading (same) |
| Templates only, no discussion sections | 1 | 4% | Append at end |
| Sections only, no templates | 0 | 0% | Insert before first heading |
| Existing Refideas already present | 0 | 0% | Append to existing |

**Takeaway:** A single insertion strategy (before first heading) handles 96% of cases. The remaining 4% (no sections) append at end.

## Common pitfalls

| Pitfall | Why it happens | Correct approach |
|---------|---------------|-----------------|
| `filter_templates(matches=lambda t: str(t) == 'refideas')` | `str(template)` returns the full wikitext with braces | Use `str(t.name)` to get just the name |
| `re.split(r'\n==', wikitext)` | `==` appears inside template params, table cells, comments | Use mwparserfromhell `filter_headings()` first, then locate in wikitext |
| `{{cite web}}` inside `{{refideas}}` | `{{cite web}}` works but is non-standard | Use plain `[url Label], Source` format |
| Bottom-of-page placement | Refideas is metadata, not a discussion | Insert before first `==` heading |
| Creating duplicate Refideas blocks | Easier to implement but looks sloppy | Append to existing block (find max param, add n+1) |

## Reference implementation

### Architecture: pure function + orchestrator

The L1 insert logic is split into three layers — the pattern to follow for L2-L5:

| Function | Layer | Testable? |
|----------|-------|-----------|
| `build_refideas_wikitext(wikitext, url, label, source, note)` | Pure — takes wikitext string, returns modified wikitext. No API calls. | ✅ 22 offline tests |
| `refideas_add(article, url, label, source, note)` | Orchestrator — fetches Talk page via API, deduplicates by URL, delegates to `build_refideas_wikitext()` | ⬜ via integration |
| `l1_insert_refideas(article, course_id, course_title, url, note)` | OCW wrapper — formats `[url MIT id: title], MIT OpenCourseWare (note)` and calls `refideas_add()` | ✅ via wrapper tests |

### Deduplication

Before inserting, `refideas_add()` checks whether the URL already appears anywhere on the Talk page. If found, it skips with a `⏭` message. This prevents duplicate suggestions.

### Template aliases

The function recognizes all 11 `{{refideas}}` template aliases: `refideas`, `refidea`, `RI`, `ref ideas`, `suggested sources`, `suggested refs`, `source ideas`, `potential sources`, `possible sources`, `refideas-nonotice`, `refsuggestion`.

### Usage

```bash
# Quick dry-run preview (no auth needed)
python3 scripts/contribution-protocol.py --l1-test "Geothermal energy"
python3 scripts/contribution-protocol.py --l1-test Boeing

# Validate all example records
python3 scripts/contribution-protocol.py --validate

# See the wikitext output for all levels
python3 scripts/contribution-protocol.py --wikitext
```

### CLI tools

```bash
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

# Preview either without posting
python3 scripts/apply-l1-refideas.py --dry-run "Article" --course-id ...
```

Both CLIs share the same auth (bot password from `.env`), side-by-side diff, and [y/N] confirmation prompt. The OCW wrapper (`apply-l1-refideas.py`) imports utilities from the generic tool (`refideas-add.py`) rather than duplicating them.

### Tests

```bash
# Linter/fixer tests (26)
python3 scripts/test-refideas.py -v

# Insert tests (22) — pure function, no API calls
python3 scripts/test-l1-refideas-insert.py -v
```

48 tests total, all passing.

## Linter / Cleaner mode

A companion linter (`scripts/lint-refideas.py`) detects and fixes common formatting errors in existing `{{refideas}}` templates. Based on [analysis of ~380 randomly sampled pages](https://meta.wikimedia.org/wiki/Wiki_MIT/RefIdeas) that found 54 instances of bullet syntax errors.

First run paginates through all ~29,000 Refideas pages (~30s) and caches to `.wiki_cache/`. Subsequent runs load from cache instantly.

### Detected error types

| Type | Severity | Description |
|------|----------|-------------|
| `multi_bullet` | 🔴 error | Multiple references crammed into one parameter with `* ` separators |
| `bullet_syntax` | 🔴 error | Parameter uses `\|* url` or has `*` as parameter name |
| `duplicate_url` | 🟡 warning | Same URL appears in multiple parameters |
| `unnumbered_param` | 🟡 warning | Positional parameter that should be numbered |
| `param_spacing` | 🟡 warning | Extra whitespace in parameter names |
| `bare_url` | ℹ️ info | URL without `[url Label]` format — valid but less readable |

### Handles all 11 template aliases

Refideas, Refidea, RI, Ref ideas, Suggested sources, Suggested refs, Source ideas, Potential sources, Possible sources, Refideas-nonotice, Refsuggestion

All redirects resolve to `Template:Refideas` in the database, so only the canonical name is needed for population queries.

### Usage

```bash
# Lint one page with full report
python3 scripts/lint-refideas.py --fetch "Cult film"

# Show fix diff (side-by-side unified diff)
python3 scripts/lint-refideas.py --fix "Cult film"

# Lint a random sample (population from cache, instant after first run)
python3 scripts/lint-refideas.py --sample 50

# Classify reference types on one page
python3 scripts/lint-refideas.py --classify Boeing

# Classify reference types across a random sample
python3 scripts/lint-refideas.py --classify 30
```

### Sample output

```
Linting 10 pages...
  ✅ Geothermal energy: OK — refideas
  ℹ️  Jacob Arabo: 3 notice(s) — refideas
     Bare URL in param '1' — should use [url Label] format for readability
  ❌ Cult film: 1 issue(s) — refideas
     [multi_bullet] 5 references crammed into param '1' using bullet syntax

  Sample Results: 7 clean, 1 with issues, 2 with notices
```

Three result tiers: **✅ OK** (proof of processing), **ℹ️ notices** (info only), **❌ issues** (actionable errors).

### Reference type classification

The `--classify` mode categorizes each reference by domain type, matching the [Meta-Wiki analysis](https://meta.wikimedia.org/wiki/Wiki_MIT/RefIdeas):

```
=== Reference Type Distribution (30 pages, 91 references) ===
  url                   :    49 ( 53.8%)  ← matches Meta report 52%
  citation_template     :    19 ( 20.9%)  ← matches Meta report 16%
  archive               :    17 ( 18.7%)  ← matches Meta report 26%
  academic_journal      :     2 (  2.2%)
```

### Example fix: multi-bullet on "Cult film"

**Before:** 5 references crammed into one parameter with bullet syntax
```wikitext
{{refideas|
* {{cite journal|...}}
* {{cite book|...}}
* {{cite web|...}}
}}
```
**After:** split into properly numbered parameters
```wikitext
{{refideas
|{{cite journal|...}}
|{{cite book|...}}
|{{cite web|...}}
}}
```

## Live editing

`scripts/apply-refideas-fix.py` applies fixes to live Wikipedia Talk pages using bot password authentication.

### Setup

Add to `.env`:
```
WIKIPEDIA_USERNAME=YourUsername@BotName
WIKIPEDIA_BOT_PASSWORD=your_bot_password
```

Create a bot password at `https://en.wikipedia.org/wiki/Special:BotPasswords` with "Edit existing pages" grant.

### Workflow

```bash
# Survey — find pages with actionable errors
python3 scripts/apply-refideas-fix.py --survey 50

  Survey: 2 of 50 pages have actionable errors
  Kinesoft
    1 issue(s) — [bullet_syntax] — Refideas
    Fix: python3 scripts/apply-refideas-fix.py "Kinesoft"

# Fix — shows color-coded side-by-side diff, prompts [y/N], then posts
python3 scripts/apply-refideas-fix.py "Kinesoft"

  Authenticated as: YourUsername
  Found 1 fixable issue(s):
  🔴 [bullet_syntax] Fixed: reformatted template with proper newlines

         Original        │         Fixed
  ───────────────────────┼───────────────────────
  {{Refideas|            │ {{refideas
  * GA Strategy, [url]   │ |GA Strategy, [url]
  }}                     │ }}

  Apply this fix? [y/N] y
  ✅ Fix applied! Revision: 1356174086

# Dry-run — show diff without editing
python3 scripts/apply-refideas-fix.py --dry-run "Kinesoft"
```

### Formatting

All fixes produce clean, readable wikitext with each reference on its own line:

```wikitext
{{refideas
|{{cite journal|title=...}}
|{{cite book|title=...}}
|{{cite web|url=...}}
}}
```

Pages fixed so far: Cult film (multi_bullet, 5 refs split), Kinesoft (bullet_syntax), Toshakhana (bullet_syntax).

### Insert tools

Two CLIs for adding new references to `{{refideas}}` — a generic one for any reference, and an OCW-specific wrapper:

```bash
# Generic: add any reference to {{refideas}}
python3 scripts/refideas-add.py "Algorithm" \
    --url "https://example.com/algo-ref" \
    --label "Algorithm Reference" \
    --source "Example Press" \
    --note "chapter 3"

# OCW-specific: add MIT course suggestion
python3 scripts/apply-l1-refideas.py "Algorithm" \
    --course-id 6.006 \
    --course-title "Introduction to Algorithms" \
    --course-url "https://ocw.mit.edu/courses/6-006-..." \
    --note "video lectures, problem sets"

# Preview without posting (--dry-run)
python3 scripts/refideas-add.py --dry-run "Algorithm" --url ... --label ...

# Skip confirmation (--yes)
python3 scripts/apply-l1-refideas.py --yes "Algorithm" --course-id ...
```

Both show a color-coded side-by-side diff, prompt [y/N] before posting, and use bot password auth from `.env`. The OCW wrapper imports auth/diff/post utilities from the generic tool — no code duplication.

Deduplication: if the URL already appears anywhere on the Talk page, the insert is skipped with a `⏭` message.

## Next

- **Tests:** `python3 scripts/test-l1-refideas-insert.py -v` — 22 tests for the pure function
- **L2:** See `docs/CONTRIBUTION-LEVELS.md` — External links insertion (next priority)
- **All levels:** `docs/CONTRIBUTION-LEVELS.md` for L1-L5 specs
