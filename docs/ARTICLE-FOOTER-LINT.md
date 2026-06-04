# Article Footer Linter — Design & Requirements

> **Status:** Design proposal  
> **Last updated:** 2026-06-03  
> **See also:** `docs/L2-EXTERNAL-LINKS.md` (downstream consumer), `scripts/lint-refideas.py` (sibling tool, same pattern)

---

## Problem statement

Wikipedia article footers — the region below the last content section, spanning
`== See also ==` through categories — accumulate structural inconsistencies
over time: misplaced bullets, missing whitespace, templates in the wrong order.
These issues are:

1. **Visually jarring** to readers browsing the bottom of an article
2. **Edit-fragile** — our L2 external links tool broke when adding to
   `== Further reading ==` on Photovoltaics because the footer had no `*`
   bullets and the insertion landed after categories
3. **Hard to fix by hand** — each issue is trivial, but there are thousands
   of articles

A linter that detects and auto-fixes the most common footer issues provides
a low-risk, high-value public service while simultaneously making our own
edits more reliable.

---

## Scope

### In scope

The region of the article from the **last content-level heading** (typically
`== See also ==`) through the **end of the article**. Specifically:

- `== See also ==` (if present)
- `== Notes ==` / `== Footnotes ==` (if present)
- `== References ==` (if present)
- `== Further reading ==` (if present)
- `== External links ==` (if present)
- Article-footer templates: `{{Navbox}}`, `{{Authority control}}`,
  `{{Portal bar}}`, `{{DEFAULTSORT}}`
- Categories: `[[Category:...]]`
- Stub templates: `{{...-stub}}`

### Out of scope (explicitly)

- **Adding or removing `== External links ==` sections.** Per community
  discussion, some articles intentionally omit this section. Our tool should
  not create or delete it.
- **Alphabetizing categories.** Category order is sometimes intentional
  (primary category first). We will not reorder them.
- **Reviewing the quality or appropriateness of existing external links.**
  That is a content decision, not a formatting one.
- **Reordering sections** (e.g., moving Further reading before See also).
  Section order is covered by manual review; auto-reordering is too risky.
- **Anything above `== See also ==`.** The article body is out of scope.

---

## Detectable issues

### Issue 1: `*` bullets after categories (`bullet_after_categories`)

**Severity:** Error  

**Detection:** Any line starting with `*` that appears after the first
`[[Category:` line in the article.

**Fix:** Move all `*` bullets found after the first category to the
appropriate section (External links or Further reading, depending on section
position). If no target section exists, move them to right before the first
category.

**Rationale:** Per WP:LAYOUT, categories are always the last element.
External links appearing after categories break the visual structure and
confuse automated tools.

**Confidence:** 100% — clear rule, no ambiguity.

### Issue 2: `*` bullets not inside a section (`orphan_bullets`)

**Severity:** Warning  

**Detection:** `*` bullets that appear in the footer region but are not
inside any `== ... ==` section (they come after the last level-2 heading).

**Fix:** Group orphan bullets under a new `== External links ==` heading.
If only one bullet, consider moving it into the preceding section if that
section makes sense (e.g., Further reading).

**⚠️ Excluded from initial scope** (per decision above — we do not create
`== External links ==` sections). Revisit if orphan bullets are common.

### Issue 3: `{{DEFAULTSORT}}` in wrong position (`defaultsort_position`)

**Severity:** Warning  

**Detection:** `{{DEFAULTSORT:...}}` found **after** the first
`[[Category:` line, or **before** `{{Authority control}}`.

**Correct position:** After all navboxes and `{{Authority control}}`, but
before the first category. (Per WP:FOOTERS.)

**Fix:** Move `{{DEFAULTSORT}}` to immediately before the first category
line.

**Confidence:** 95% — DEFAULTSORT must precede categories to work correctly.
Moving it to the correct position is always safe.

### Issue 4: Missing blank line between sections (`section_spacing`)

**Severity:** Info / Warning  

**Detection:** Two consecutive `== ... ==` headings with no blank line
between them, or a heading immediately followed by content with no blank
line.

**Fix:** Ensure exactly one blank line between the end of one section and
the start of the next. Ensure a blank line between a heading and its
first content line.

**Confidence:** 100% for sections; 95% for heading-to-content (some
articles intentionally omit the blank line).

### Issue 5: `{{Authority control}}` not in standard position (`auth_control_position`)

**Severity:** Info  

**Detection:** `{{Authority control}}` found outside its expected position
(after navboxes, before `{{DEFAULTSORT}}` or categories).

**Fix:** Move `{{Authority control}}` to after all navboxes, before
`{{DEFAULTSORT}}` or the first category.

**Confidence:** 90% — the standard position is well-established. Some
atypical articles place it inside a navbox, which we must detect and skip.

### Issue 6: Stub template not at very end (`stub_position`)

**Severity:** Info  

**Detection:** A `{{...-stub}}` template followed by any non-whitespace
content other than categories.

**Fix:** Move the stub template to after the last category line, on its
own line.

**Confidence:** 95% — per WP:STUB, stub templates go after categories.

### Issue 7: Duplicate or trailing blank lines (`whitespace_cleanup`)

**Severity:** Info  

**Detection:** Three or more consecutive blank lines, or trailing blank
lines at the end of the article.

**Fix:** Collapse consecutive blank lines to at most two. Remove trailing
blank lines.

**Confidence:** 100% — mechanical, no semantic impact.

---

## Architecture

### Files

| Path | Purpose |
|------|---------|
| `scripts/lint-article-footer.py` | Main CLI tool: analyze, fix, survey, batch |
| `docs/ARTICLE-FOOTER-LINT.md` | This document |

### Modules (in `scripts/lint-article-footer.py`)

```
lint_article_footer.py
├── analyze_footer(wikitext)          # Pure function → {issues: [{type, pos, desc}]}
├── fix_footer(wikitext, issues)      # Pure function → fixed wikitext + {fixes_applied}
├── fetch_and_analyze(article)        # Fetch wikitext via API, call analyze_footer
├── fetch_and_fix(article, auto_yes)  # Fetch, analyze, confirm, post via API
├── survey(sample_size)               # Batch analyze random articles → report
├── CLI                               # --fix, --survey, --report-only, --dry-run
```

### Follows the established pattern

Same architecture as L1/L2 tools:

```
Pure function (tests only) → Orchestrator (API calls) → CLI
```

### Fix ordering

Fixes must be applied in a specific order to avoid conflicts:

1. **Whitespace cleanup** (fix 7) — normalizes blank lines first
2. **Section spacing** (fix 4) — ensures blank lines between sections
3. **Bullets after categories** (fix 1) — move bullets into proper position
4. **Stub position** (fix 6) — move stubs to end
5. **Authority control position** (fix 5) — reposition
6. **DEFAULTSORT position** (fix 3) — reposition (after navboxes, before cats)
7. **Trailing whitespace** (fix 7, second pass) — clean up after moves

---

## CLI

```bash
# Analyze one article (read-only)
python3 scripts/lint-article-footer.py "Climate change"

# Analyze and fix one article
python3 scripts/lint-article-footer.py --fix "Photovoltaics"

# Dry-run (show diff, don't post)
python3 scripts/lint-article-footer.py --fix --dry-run "Biology"

# Auto-confirm (skip y/N prompt)
python3 scripts/lint-article-footer.py --fix --yes "Biology"

# Survey N random articles
python3 scripts/lint-article-footer.py --survey 100

# Fix only specific issues
python3 scripts/lint-article-footer.py --fix "Photovoltaics" --only bullet_after_categories,defaultsort_position

# Batch fix top N from survey
python3 scripts/lint-article-footer.py --survey 50 --fix-top 10
```

### Output format

```json
{
  "article": "Photovoltaics",
  "fixes_applied": 3,
  "issues": [
    {
      "type": "bullet_after_categories",
      "severity": "error",
      "description": "1 * bullet found after [[Category:...]]",
      "fixed": true
    },
    {
      "type": "section_spacing",
      "severity": "info",
      "description": "2 sections with no blank line between",
      "fixed": true
    },
    {
      "type": "whitespace_cleanup",
      "severity": "info",
      "description": "Collapsed 3 consecutive blank lines",
      "fixed": true
    }
  ]
}
```

### Survey output

```
Surveying 100 articles...
================  ==========  ======
Issue type        Articles    %     
================  ==========  ======
bullet_after_cats     3       3%    
section_spacing      31      31%    
defaultsort_pos       2       2%    
auth_control_pos      5       5%    
stub_position         1       1%    
whitespace_cleanup   22      22%    
================  ==========  ======
```

---

## Tests

| # | Test | Type | Status |
|---|------|------|--------|
| 1 | `*` bullets after categories → moved before cats | Integration | Planned |
| 2 | DEFAULTSORT after first category → moved before cats | Integration | Planned |
| 3 | DEFAULTSORT before AuthControl → moved after | Integration | Planned |
| 4 | Sections with no blank line → blank line inserted | Integration | Planned |
| 5 | Heading immediately followed by content → blank line | Integration | Planned |
| 6 | AuthControl after categories → moved before cats | Integration | Planned |
| 7 | Stub before last category → moved to end | Integration | Planned |
| 8 | Triple blank lines → collapsed to 2 | Integration | Planned |
| 9 | Trailing blank lines → removed | Integration | Planned |
| 10 | Multiple fixes on one article → applied in order | Integration | Planned |
| 11 | Well-formed article → no changes | Regression | Planned |
| 12 | Empty footer → no changes | Edge case | Planned |
| 13 | No issues → returns empty list | Unit | Planned |

**Target:** 20-25 tests covering all fix types plus edge cases.

---

## Risk analysis

| Fix | Risk | Mitigation |
|-----|------|------------|
| `bullet_after_categories` | None — bullets after cats are always wrong | — |
| `section_spacing` | None — mechanical | — |
| `auth_control_position` | Low — some articles embed AC in navboxes | Skip if inside `{{...}}` |
| `defaultsort_position` | None — DEFAULTSORT must be before cats to work | — |
| `stub_position` | None — stubs at end is universal convention | — |
| `whitespace_cleanup` | None — mechanical | — |

**All fixes are composable** — they operate on independent regions of the
wikitext and apply in a fixed order that avoids conflicts.

---

## Phase 2: Dead link detection (`--check-links`)

External links sections accumulate broken URLs over time as sites move,
restructure, or shut down. A `--check-links` mode (separate from `--fix`)
probes each HTTP(S) URL found in the footer and reports or tags dead ones.

### Policy

- **Never remove links.** Per Wikipedia convention, broken external links
  are tagged with `{{dead link|date=June 2026}}`, not removed. Removal is
  a content decision best left to human editors.
- **Two-strike rule.** A single 404 may be a temporary outage. Retry once
  after a 5-second delay before flagging.
- **Archive.org fallback.** Before tagging as dead, check the Wayback
  Machine for an archived copy. If found, note it in the tag or log.
- **Rate-limited.** Max 1 HTTP request per second to avoid rate limiting.
  Survey mode respects this with a progress bar.

### Which links are checkable

| Format | Example | Checkable? | URL extraction |
|--------|---------|------------|----------------|
| `* [https://... Title]` | Most common | Yes | Extract from `[...]` |
| `* {{cite web \|url=...}}` | Rare in EL sections | Yes | Extract `\|url=` param |
| `* {{curlie\|...}}` | Common (~13%) | No | Directory link, not HTTP |
| `* {{dmoz\|...}}` | Deprecated | No | Directory link |
| `* {{Library resources box}}` | Occasional | No | Meta-template |
| `* {{Sister project links}}` | Occasional | No | Meta-template |

### Detection strategies

1. **HEAD request first.** Fast, low bandwidth. If the server returns a
   405/501 (method not allowed), retry with GET.
2. **Status code interpretation:**
   - 2xx → alive
   - 3xx → follow redirect, check final destination (redirects are not dead)
   - 4xx → retry once, then flag
   - 5xx → retry once (server error may be transient)
   - Connection refused / timeout → retry once, then flag
3. **HTTPS upgrade.** If an `http://` URL returns a redirect to `https://`,
   that's fine — the link works. Optionally suggest upgrading the URL.
4. **Archive.org check.** For links confirmed dead after two strikes,
   query `https://web.archive.org/web/YYYYMMDDhhmmss/URL` (the Wayback
   availability API) to see if a snapshot exists.

### Tagging format

```wikitext
* [https://example.com/broken-link Title]{{dead link|date=June 2026}}
* {{cite web |url=https://example.com/broken-link |title=Title |publisher=Foo}}{{dead link|date=June 2026}}
```

If an archive URL is found, an alternative is to replace the link with
an archive link (controversial — opt-in only):

```wikitext
* {{webarchive |url=https://web.archive.org/web/20250101000000/https://example.com/broken-link |title=Title |date=2025-01-01}}
```

### CLI

```bash
# Check all external links on one article (read-only report)
python3 scripts/lint-article-footer.py --check-links "Climate change"

# Tag dead links with {{dead link}}
python3 scripts/lint-article-footer.py --check-links --tag-dead "DNA"

# Survey: how many articles have dead links?
python3 scripts/lint-article-footer.py --check-links --survey 50

# Replace dead links with archived versions (opt-in)
python3 scripts/lint-article-footer.py --check-links --use-archive "Biology"

# Check only our own recently-added OCW links
python3 scripts/lint-article-footer.py --check-links --since "2026-01-01"
```

### Tests

| # | Test | Type |
|---|------|------|
| 1 | 200 response → not flagged | Unit |
| 2 | 404 response → flagged after retry | Integration |
| 3 | 404 then 200 on retry → not flagged | Integration |
| 4 | http redirect to https → followed, not flagged | Integration |
| 5 | Connection refused → flagged after retry | Integration |
| 6 | Curlie link → skipped (no HTTP check) | Unit |
| 7 | {{cite web}} link → URL extracted and checked | Unit |
| 8 | Bare `[url title]` link → URL extracted and checked | Unit |
| 9 | Dead link with archive.org copy → archive URL noted | Integration |
| 10 | `--tag-dead` adds `{{dead link}}` after the link | Unit |

**Target:** 12-15 tests.

### Integration with structural fixes

`--check-links` and `--fix` can be combined:

```bash
# Fix structure, then check links
python3 scripts/lint-article-footer.py --fix --check-links "Photovoltaics"
```

When combined, structural fixes run first (normalizing the footer), then
link checking runs on the cleaned wikitext. This ensures misplaced bullets
are moved back into the External links section before being checked.

---

## Relationship to L2 external links

The footer linter directly improves L2 edit reliability:

- **`bullet_after_categories` fix** prevents the exact bug we hit on
  Photovoltaics. Running the linter as a pre-flight check before L2
  insertion ensures the `== External links ==` section is clean.
- **`section_spacing` fix** ensures our insertion logic doesn't break
  on unusual spacing.
- **`auth_control_position` / `defaultsort_position` fixes** ensure
  our section-end detection doesn't trigger on misplaced templates.

The linter can be called as a pre-flight step within the L2 pipeline:

```python
# In apply-l2-external-links.py (future):
result = lint_article_footer(article_wikitext)
if result["fixes_applied"]:
    # Post the lint fix first, then retry the L2 edit
    post_lint_fix(article, result["wikitext"])
    article_wikitext = result["wikitext"]
```

Or provided as a separate public-service tool that editors run
independently of the Wiki MIT pipeline.

---

## Next steps

1. ✅ Design doc reviewed and approved
2. Implement `analyze_footer()` — detect all 6 issue types
3. Implement `fix_footer()` — apply fixes in order
4. Add CLI (`--fix`, `--survey`, `--dry-run`)
5. Write 20+ tests
6. Deploy: survey 200 random articles to measure prevalence
7. Optionally: integrate as pre-flight in L2 pipeline
