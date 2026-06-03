# L2 Contribution: External Links Section

> **Status:** Built and tested (2026-06-03). Pure function (26 offline tests) + orchestrator + OCW CLI wrapper. CLI supports auto-resolution from local wiki via `--course` slug/URL, plus legacy `--course-id`/`--course-url`/`--course-title` mode. Two bug fixes applied: (1) smart insertion before trailing navboxes/categories, (2) regex handles `*[url` (no space after `*`).

---

## What it is

An MIT OCW course link added to a Wikipedia article's `== External links ==` section. This is a higher-value edit than `{{refideas}}` (L1) because it modifies the article itself, but it's still low-risk — external links sections are append-only and well-understood by editors.

## What it looks like

Standard Wikipedia convention — a bulleted `{{cite web}}` entry:

```wikitext
== External links ==
* [https://health.ec.europa.eu/... Artificial Intelligence in healthcare] on ''europa.eu''
* {{cite web |url=https://ocw.mit.edu/courses/6-s897-machine-learning-for-healthcare-spring-2019/ |title=Machine Learning for Healthcare |publisher=MIT OpenCourseWare}} — Graduate course exploring machine learning methods for clinical diagnosis, treatment planning, and healthcare delivery.
```

The format follows [WP:EL](https://en.wikipedia.org/wiki/Wikipedia:External_links) conventions:
- Bulleted line starting with `*`
- Typically a `{{cite web}}` template for academic resources
- Optional description after an em-dash (` — `)

## Where it goes

**Section targeting** (in priority order):

1. `== External links ==` — appends after the last `*` bullet, but **before** any trailing navboxes or categories (per WP:LAYOUT)
2. `== Further reading ==` — fallback if no External links section exists
3. Neither exists → creates a new `== External links ==` section, positioned before References/Notes/See also, or at end of page if none of those exist

**Critical placement detail:** When `== External links ==` is the last section on the page, the algorithm does NOT simply append at end-of-file (which would place the link after categories). Instead it finds the last `*` bullet in the section and inserts after it, preserving Wikipedia's standard layout:
```
== External links ==
* Existing link 1
* Existing link 2
* {{cite web |url=... |title=MIT OCW Course |publisher=MIT OpenCourseWare}}   ← NEW

{{Navbox}}                                        ← navboxes stay at bottom
{{Authority control}}

[[Category:Topic]]                                 ← categories at very bottom
```

## The algorithm

```
                    ┌──────────────────────┐
                    │ 1. Fetch article     │
                    │    wikitext via API   │
                    │    action=parse       │
                    │    &prop=wikitext     │
                    └──────────┬───────────┘
                               │
              ┌────────────────▼────────────────┐
              │ 2. Dedup: URL already in page?   │
              │    test: url in wikitext         │
              └────────┬─────────────────────────┘
                       │ YES → skip
                       │ NO
                       ▼
              ┌──────────────────────────────────┐
              │ 3. Parse headings via            │
              │    mwparserfromhell              │
              │    filter_headings()             │
              │    (Level 2 only: == ... ==)     │
              └────────┬─────────────────────────┘
                       │
              ┌────────────────▼────────────────┐
              │ 4. == External links == exists?  │
              └────────┬──────────────┬──────────┘
                       │ YES          │ NO
                       ▼              ▼
           ┌────────────────────┐  ┌──────────────────────────┐
           │ 5a. APPEND to     │  │ 5b. == Further reading   │
           │     existing      │  │     == exists?            │
           │     section       │  └────────┬──────────────────┘
           │                   │           │ YES     │ NO
           │ Find last *       │           ▼         ▼
           │ bullet via regex  │  ┌────────────┐  ┌──────────────────┐
           │ ^\s*\*            │  │ Append to  │  │ Create new       │
           │                   │  │ Further    │  │ == External      │
           │ Insert after it   │  │ reading    │  │ links ==         │
           │ (before nav/cat)  │  │ section    │  │ before References│
           └────────────────────┘  └────────────┘  │ or See also, or │
                                                   │ at end          │
                                                   └──────────────────┘
```

### Step details

**Step 1 — Fetch article wikitext:**
```
GET /w/api.php?action=parse&page=Algorithm&prop=wikitext&format=json&formatversion=2
```
**User-Agent required.** Use: `MIT OCW Bot/1.0 (https://meta.wikimedia.org/wiki/Wiki_MIT; andrew.lih@gmail.com) ContentGapResearch`

**Step 2 — Deduplication:**
```python
if url in wikitext:
    # Skip — already present
    return {"skipped": True, "reason": "duplicate_url"}
```

Dedup is a simple string match. Note: `http` vs `https` variants are not caught — this is a known limitation.

**Step 3 — Parse headings:**
```python
import mwparserfromhell
code = mwparserfromhell.parse(wikitext)
headings = code.filter_headings()
heading_data = []
for h in headings:
    if h.level == 2:
        h_title = str(h.title).strip()
        # Find byte position in original wikitext
        pattern = rf'(?:^|\n)==\s*{re.escape(h_title)}\s*=='
        m = re.search(pattern, wikitext, re.MULTILINE)
        if m:
            heading_data.append((h_title, m.start(), m.end()))
heading_data.sort(key=lambda x: x[1])
```

⚠️ **Why mwparserfromhell + regex instead of pure regex:** Using `re.split(r'\n==', ...)` would match `==` inside template parameters, wikitext tables, or HTML comments. mwparserfromhell provides AST-based heading detection. We then use regex only to find the byte position in the original string (since mwparserfromhell doesn't expose byte positions).

**Step 5a — Append to External links:**
```python
# Find the section content between heading and next heading (or end of page)
h_start, h_end = heading_data[target_idx][1], heading_data[target_idx][2]
end_pos = next heading start, or len(wikitext) if last section
section_raw = wikitext[h_end:end_pos]

# Find the last * bullet in the section
last_bullet_end = -1
for m in re.finditer(r'^\s*\*', section_raw, re.MULTILINE):
    line_end = section_raw.find('\n', m.end())
    if line_end == -1:
        line_end = len(section_raw)
    last_bullet_end = max(last_bullet_end, line_end)

if last_bullet_end > 0:
    actual_end = h_end + last_bullet_end
    before = wikitext[:actual_end].rstrip('\n')
    after = wikitext[actual_end:]
    new_wikitext = before + bullet + "\n" + after.lstrip('\n')
```

**Key regex detail:** `^\s*\*` matches `*` at the start of a line, regardless of whether there's a space after it. This handles both `* [url` and `*[url` syntax found across different Wikipedia articles. Earlier versions used `^\s*\*\s+` which broke on `*[url` (no space after `*`).

**When creating a new section** (Step 5b, no External links or Further reading exists):
```python
# Find References (or Notes/Footnotes) to position before
REFERENCE_NAMES = {'references', 'notes', 'footnotes', 'notes and references'}
# Fall back to == See also ==
# If neither exists, append at end
```

## API calls needed

| # | Endpoint | Purpose |
|---|----------|---------|
| 1 | `action=parse&page={title}&prop=wikitext` | Fetch current article wikitext |
| 2 | `action=query&meta=tokens&type=csrf` | Get edit token |
| 3 | `action=edit&title={title}&text=...&token=...` | Post the edit |

Total: 3 API calls per contribution (same as L1).

## Course resolution

The CLI supports two modes for specifying the course:

### Primary: `--course` (slug or URL)

Accepts either an OCW slug or a full OCW URL. Resolves course metadata from the local wiki at `wiki/courses/{slug}.md`:

```bash
# Slug
--course "6-s897-machine-learning-for-healthcare-spring-2019"

# Full URL
--course "https://ocw.mit.edu/courses/6-s897-machine-learning-for-healthcare-spring-2019/"
```

The local wiki file must exist (ingested during the course ingest phase — 2,573 courses available). The YAML frontmatter provides:

```yaml
course_id: "6.S897"
title: "Machine Learning for Healthcare"
url: "https://ocw.mit.edu/courses/6-s897-machine-learning-for-healthcare-spring-2019/"
```

The resolved `title` and `description` can be overridden:

```bash
--course "6-s897-..." \
--course-title "Custom Title" \
--description "Custom description."
```

### Legacy: `--course-id` + `--course-url` + `--course-title`

All fields must be provided explicitly. Still supported for backward compatibility:

```bash
--course-id 6.006 \
--course-title "Introduction to Algorithms" \
--course-url "https://ocw.mit.edu/courses/6-006-..."
```

## Architecture: pure function + orchestrator + CLI

Same three-layer pattern as L1:

| Function | Layer | Testable? | What it does |
|----------|-------|-----------|-------------|
| `build_external_link_wikitext(wikitext, url, title, publisher, description)` | Pure | ✅ 26 offline tests | Takes wikitext string in, returns modified wikitext out. No API calls. |
| `external_link_add(article, url, title, publisher, description)` | Orchestrator | ⬜ via integration | Fetches article via API, deduplicates by URL, delegates to pure function. |
| `l2_insert_external_link(article, course_id, course_title, course_url, description)` | OCW wrapper | ✅ | Formats publisher as "MIT OpenCourseWare", calls `external_link_add()`. |

All three are in `scripts/contribution-protocol.py`.

The CLI (`scripts/apply-l2-external-links.py`) wraps these with:
- Course resolution from local wiki (`--course` → `resolve_course()`)
- Article title from Wikipedia URL or bare string (`resolve_article()`)
- Authentication via bot password (same as L1)
- Side-by-side diff display (reuses from `refideas-add.py`)
- [y/N] confirmation prompt
- Edit posting via Wikipedia API

## CLI usage

### Primary: `--course` mode

```bash
# Course as slug — resolves title/url from local wiki
python3 scripts/apply-l2-external-links.py "Artificial intelligence in healthcare" \
    --course "6-s897-machine-learning-for-healthcare-spring-2019" \
    --description "Graduate course on ML methods for healthcare."

# Course as full URL
python3 scripts/apply-l2-external-links.py "Algorithm" \
    --course "https://ocw.mit.edu/courses/6-006-introduction-to-algorithms-spring-2020/"

# Article as full Wikipedia URL
python3 scripts/apply-l2-external-links.py \
    "https://en.wikipedia.org/wiki/Artificial_intelligence_in_healthcare" \
    --course "6-s897-..."

# Override course title resolved from wiki
python3 scripts/apply-l2-external-links.py "Algorithm" \
    --course "6-006-..." \
    --course-title "Custom Title" \
    --description "Custom description."

# Preview without posting
python3 scripts/apply-l2-external-links.py --dry-run "Algorithm" --course "6-006-..."

# Skip confirmation prompt
python3 scripts/apply-l2-external-links.py --yes "Algorithm" --course "6-006-..."
```

### Legacy: explicit fields

```bash
python3 scripts/apply-l2-external-links.py "Algorithm" \
    --course-id 6.006 \
    --course-title "Introduction to Algorithms" \
    --course-url "https://ocw.mit.edu/courses/6-006-introduction-to-algorithms-spring-2020/" \
    --description "Full course with video lectures, problem sets, and exams."
```

### Dry-run preview (no auth needed)

```bash
python3 scripts/contribution-protocol.py --l2-test
python3 scripts/contribution-protocol.py --l2-test "Nuclear weapon"
```

## Bug fixes (2026-06-03)

### 1. Insertion before navboxes/categories

**Problem:** When `== External links ==` was the last section on the page, the algorithm set `end_pos = len(wikitext)` (end of file). The new bullet was appended after all categories and navboxes, breaking WP:LAYOUT.

**Fix:** When the section is the last one, find the last `*` bullet via regex and insert after it, before any trailing `{{navbox}}` or `[[Category:...]]` content.

### 2. Regex misses `*[url` (no space after `*`)

**Problem:** The regex `^\s*\*\s+` required at least one whitespace character after `*`. Many Wikipedia articles use `*[url` (no space), causing the regex to miss the last bullet.

**Fix:** Changed to `^\s*\*` — matches `*` at start of line regardless of what follows.

## Tests

```bash
# L2 external links tests (26) — pure function, no API calls
python3 scripts/test-l2-external-links.py -v

# Test coverage includes:
#   - Append to existing External links
#   - Append to Further reading (fallback)
#   - Prefer External links over Further reading when both exist
#   - Insert before navboxes/categories (bug fix)
#   - Create new section before References
#   - Create new section before See also
#   - Append at end when no References or See also
#   - Idempotency (appending twice)
#   - Special characters in titles
#   - Sub-headings within External links (===)
#   - Multiple sections after External links
```

## Output format

```wikitext
* {{cite web |url=https://ocw.mit.edu/courses/6-006-introduction-to-algorithms-spring-2020/ |title=Introduction to Algorithms |publisher=MIT OpenCourseWare}} — Full course with video lectures, problem sets, and exams covering algorithm design and analysis.
```

If no description is provided, the `— description` portion is omitted.

## Known limitations

- **Duplicate URL detection** only catches exact string matches — `http` vs `https`, or different URL-encoded variants, are not detected as duplicates
- **Course resolution** requires the local wiki file to exist (the `--course` mode won't work for courses that weren't ingested)
- **Edit conflict handling** is basic — the script fetches the page once, diffs, and posts. If another editor modifies the page between fetch and post, the edit may fail with a conflict error. The script reports the error but does not retry.
- **Rate limiting** respects standard Wikipedia API limits when using a proper User-Agent string

## Companion tool

`scripts/ad-hoc-match.py` and `docs/AD-HOC-MATCH.md` — finds the best Wikipedia article matches
for any OCW course, then lets you post L2 external links or L1 `{{refideas}}` interactively.
Five filter layers (broad-field articles, glossary/list pages, named entities,
generic category words, no-overlap exclusion) keep the match list focused on genuinely
relevant articles.

```bash
# Find matches for a course, then post L2 external links
python3 scripts/ad-hoc-match.py "6.S897" --mode L2 --interactive

# Preview without posting
python3 scripts/ad-hoc-match.py "6.S897" --mode L2 --interactive --dry-run

# Just see the ranked list with scores
python3 scripts/ad-hoc-match.py "6.S897" --top 5
```

## References

- `scripts/apply-l2-external-links.py` — CLI entry point
- `scripts/contribution-protocol.py` — `build_external_link_wikitext()`, `external_link_add()`, `l2_insert_external_link()`
- `scripts/test-l2-external-links.py` — 26 offline tests
- `scripts/ad-hoc-match.py` — companion match-finding tool
- `docs/L1-REFIDEAS.md` — L1 pattern (same architecture)
- `docs/CONTRIBUTION-LEVELS.md` — L1-L5 overview
