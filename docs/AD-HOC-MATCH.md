# Ad-hoc Match: Find Wikipedia Articles for Any OCW Course

> **Status:** Built and tested (2026-06-03). Five filter layers eliminate noise from broad-field articles, glossary/list pages, named entities, and generic category-word overlap. Three match sources combine pre-computed corpus data with live Wikipedia search. Scoring weights corpus validation, title specificity, maintenance templates, and pageviews.

---

## What it is

Given any MIT OCW course (by slug, URL, or course ID), find the best Wikipedia article matches ranked by relevance. The tool then lets you either:

- **Stdout mode**: print a ranked table with scores, quality, views, and ready-to-paste L1/L2 commands
- **Interactive mode**: select a match → preview the diff → confirm → post to Wikipedia

The match algorithm is designed to be *conservative* — it will return fewer results if it can't find strong signals, rather than flooding the user with noise.

## Why this tool exists

The pre-computed match corpus (`live-matches.json`, 157 articles across 25 WikiProjects) covers only 220 of 2,577 courses. For the other 2,300+ courses, or for finding better matches than the corpus provides, the ad-hoc tool provides live search with quality filtering.

## Match providers (pluggable architecture)

The matching system uses a **provider interface** (`MatchProvider` ABC). Each provider
implements `find_candidates()` which returns candidate articles from its matching strategy.
The pipeline orchestrator handles deduplication, enrichment, filtering, scoring, and ranking
— providers don't need to worry about any of that.

To add a new matching strategy:
```python
class MyProvider(MatchProvider):
    @property
    def name(self):
        return "my-provider"
    def find_candidates(self, course):
        # Return list of candidate dicts with at minimum: title
        return [{"title": "Some Article", ...}]

# Register it
PROVIDER_REGISTRY["my-provider"] = MyProvider
```

Then use it:
```bash
python3 scripts/ad-hoc-match.py "STS.050" --provider "corpus,wikipedia,my-provider"
```

Available providers and the order they run:

| Provider | Flag | Source | Coverage |
|----------|------|--------|----------|
| Corpus | `corpus` | `live-matches.json` | 220 courses, 157 articles |
| Wikipedia search | `wikipedia` | Wikipedia Search API by course title | All 6M+ Wikipedia articles |
| Acronym expansion | `acronym` | Wikipedia Search API with expanded acronyms | Bridges MIT↔Massachusetts Institute of Technology |
| Simplified fallback | `simplified` | Title stripped of qualifiers | Activates only when < 5 candidates |

Default: `--provider corpus,wikipedia,acronym,simplified`

## Match sources (in priority order)

```
                    ┌─────────────────────────────┐
                    │ 1. Pre-computed match       │
                    │    corpus                   │
                    │    (live-matches.json)      │
                    │    220 courses, 157 articles│
                    └──────────┬──────────────────┘
                               │
                    ┌──────────▼──────────────────┐
                    │ 2. Wikipedia search by      │
                    │    course title              │
                    │    e.g. "Machine Learning   │
                    │    for Healthcare"           │
                    └──────────┬──────────────────┘
                               │
              ┌────────────────▼────────────────┐
              │ 3. Simplified fallback search   │
              │    (only if < 5 candidates)     │
              │    Removes trailing qualifiers: │
              │    "ML for Healthcare" → "ML"   │
              └─────────────────────────────────┘
```

### Source 1: Pre-computed match corpus

An inverse index built from `live-matches.json`: `course_id → [{title, wikiproject, templates, quality, views}]`.

This is the highest-quality signal because the corpus was built through keyword matching across WikiProjects. However, some corpus entries are noisy — courses with generic descriptors like "Libertarianism in **History**" matched everything in the History WikiProject. The scoring accounts for this (see below).

**Coverage:** 220 courses mapped to 157 articles.

### Source 2: Wikipedia search by course title

The course title is searched directly via the Wikipedia Search API (`list=search`). This naturally finds the most semantically relevant articles. For example, "Machine Learning for Healthcare" returns articles about machine learning in clinical contexts, not "Computer science" or "Integer."

**Limit:** 30 results per search, deduplicated against the corpus.

### Source 3: Simplified fallback search

If sources 1+2 produce fewer than 5 candidates, the tool strips trailing qualifiers from the course title and searches again. For example:

- "Machine Learning **for Healthcare**" → searches "Machine Learning"
- "Introduction to Nuclear Engineering **and Ionizing Radiation**" → searches "Introduction to Nuclear Engineering"

This only runs when needed — avoids noise when the primary search is sufficient.

## Filters (five layers)

Every candidate passes through all five filters before scoring. A candidate that fails any filter is **removed entirely**.

### 1. Broad-field articles

Single-field names that are too generic to be useful targets:

```
"computer science", "mathematics", "physics", "chemistry", "biology",
"engineering", "science", "technology", "history", "literature",
"philosophy", "economics", "psychology", "sociology",
"artificial intelligence", "machine learning",
... (30 total)
```

These are meta-articles that describe entire fields. Adding a course link to "Computer science" helps nobody — it's too broad to be actionable.

**Before:** Course "Machine Learning for Healthcare" returned "Computer science" (score 30)
**After:** Filtered out.

### 2. Junk page types (API-detected)

Pages detected as disambiguation, glossary, list, or outline via:

- **Title heuristics**: `"Glossary of *"`, `"List of *"`, `"Outline of *"`, `"Timeline of *"`
- **Wikipedia API batch check**: `prop=pageprops|categories` detects `disambiguation` flag and disambiguation/glossary categories

Each candidate is checked in batches of 50 with a single API call.

**Before:** "Glossary of computer science" appeared as a match
**After:** Filtered out.

### 3. Named entities on weak matches

If a candidate has **no title word overlap** with the course and its title contains named-entity keywords, it's removed:

```
"academy", "university", "college", "school", "institute",
"corporation", "inc.", "ltd.", "company", "laboratories",
"foundation", "association", "society", "organization"
```

**Exception:** If the candidate shares content words with the course title, named entities are **allowed** — a research institute focused on machine learning IS relevant even though it's an organization.

**Before:** "Queensland Academy for Science, Mathematics and Technology" matched "Machine Learning for Healthcare" via the broad topic "Computer Science" 
**After:** Filtered out (no title word overlap + named entity).

### 4. Generic category words

Certain words describe the *scope* of a course rather than its *subject matter*. These don't count toward specificity scoring:

```
"history", "introduction", "principles", "fundamentals",
"foundations", "basics", "overview", "survey",
"topics", "concepts", "applications", "theory",
"methods", "techniques", "analysis", "dynamics",
"systems", "processes", "design", "modeling"
```

**Why:** "Libertarianism in **History**" and "**History** of France" share the word "History" but are about completely different things. Without this filter, the specificity score is inflated by a generic word.

**Effect:** The candidate still appears (it's not removed), but the specificity component of its score is calculated from *content words only*. The reason string shows "generic overlap only (weak specificity)" to indicate low confidence.

### 5. No-overlap exclusion

If a candidate has **zero title word overlap** with the course title **and** no maintenance templates, it's removed. This eliminates articles that are tangentially related through a broad topic but have no direct connection.

**Before:** "Integer (computer science)", "Garbage collection (computer science)", "Heuristic (computer science)" for course "Machine Learning for Healthcare"
**After:** Filtered out.

## Scoring formula

Each surviving candidate receives a score from 0-100:

```
score = corpus_match (0-40)
      + title_specificity (0-35)
      + maintenance_templates (0-15)
      + pageviews (0-10)
```

### 1. Corpus match (0-40)

| Condition | Score | Label |
|-----------|-------|-------|
| Corpus match + content-specific title overlap | +40 | `pre-computed match (+40)` |
| Corpus match + only generic overlap | +25 | `pre-computed (generic) (+25)` |
| Not from corpus | +0 | — |

The generic reduction prevents "History of France" from scoring high just because it's in the same WikiProject as "Libertarianism in History."

### 2. Title specificity (0-35)

Calculated from **content words only** (generic category words excluded):

```
specificity = |course_content_words ∩ article_content_words|
            / max(|course_content_words|, 1)

specificity_score = min(specificity × 35, 35)
```

**Examples:**

| Course | Article | Content overlap | Specificity |
|--------|---------|----------------|-------------|
| Machine Learning for Healthcare | Quantum machine learning | `machine`, `learning` (2/3) | 23 |
| Machine Learning for Healthcare | Fast Healthcare Interop. Resources | `healthcare` (1/3) | 12 |
| Libertatarianism in History | Libertarianism | `libertarianism` (1/1) | 35 |
| Libertatarianism in History | History of France | `history` is generic — none | 0 |

### 3. Maintenance templates (0-15)

```
template_score = min(number_of_templates × 5, 15)
```

This is the "community need" signal. An article with `{{citation needed}}` and `{{refimprove}}` gets +10, indicating editors have already flagged it for improvement.

### 4. Pageviews (0-10)

Log-scaled popularity:

```
view_score = min(10 × (views / 100000)^0.3, 10)
```

Scales from ~1 point at 1,000 monthly views to ~10 points at 1M+ views.

## Page type detection

The Wikipedia API batch endpoint checks all candidates in groups of 50 with a single call:

```
action=query&titles=A|B|C|...
&prop=pageprops|categories
&ppprop=disambiguation
&cllimit=10
```

For each page, it checks:

1. **Title prefix**: `"Glossary of"`, `"List of"`, etc. (fast, no API needed)
2. **Disambiguation flag**: `pageprops.disambiguation` exists → "dab"
3. **Category membership**: Any category containing "disambiguation" or "glossary" → "dab"/"glossary"
4. **Fallthrough**: None of the above → "normal"

Pages typed as "dab", "glossary", or "list" are excluded. This catches cases the title heuristic misses (e.g., a page titled "Matrix" that's a disambiguation page).

## Complete algorithm flow

```
Course input (slug/URL/ID)
    │
    ▼
Resolve course metadata from wiki/courses/ YAML frontmatter
    │
    ▼
Source 1: Look up course_id in live-matches.json corpus
    │
    ▼
Source 2: Search Wikipedia by course title (limit 30)
    │
    ▼
If candidates < 5: Source 3: Simplified title search
    │
    ▼
Batch-check all candidates for page type (1 API call per 50)
    │
    ▼
For each candidate:
    ├─ Filter 1: Broad-field article? → remove
    ├─ Filter 2: Junk page type? → remove
    ├─ Filter 3: Named entity with no overlap? → remove
    ├─ Filter 4: (No removal — just compute content vs generic overlap)
    └─ Filter 5: No overlap + no templates? → remove
    │
    ▼
Score each survivor (corpus + specificity + templates + views)
    │
    ▼
Sort by score descending, take top N
    │
    ▼
Output: stdout table or interactive selection
```

## Interactive flow

In `--interactive` mode:

```
  Top 10 matches for 6.S897 — Machine Learning for Healthcare

   1. Quantum machine learning          (Score: 68)  [?, ? views]
   2. Australian Inst. for Machine Lrn  (Score: 23)  [?, ? views]
   3. Machine learning in bioinformatics (Score: 23)  [?, ? views]
   ...
   q. Quit

  Select match [1-10, q]: 1

  Selected: Quantum machine learning
  Action: append
  Section: External links
  Detail: Appended to == External links ==

  [side-by-side diff shown here]

  Post to Wikipedia article? [y/N]:
```

After posting, the tool asks "Find another match for this course?" — letting you apply multiple edits in one session.

## CLI reference

```
usage: scripts/ad-hoc-match.py COURSE [options]

COURSE:
  Course slug:    6-s897-machine-learning-for-healthcare-spring-2019
  Full URL:       https://ocw.mit.edu/courses/6-s897-.../
  Course ID:      6.S897

Options:
  --top N         Show top N matches (default: 10)
  --mode L1|L2    Contribution level (default: L1)
  --interactive   Select match interactively, preview diff, post
  --dry-run       Preview without posting
  --provider S    Comma-separated provider names (default: corpus,wikipedia,acronym,simplified)
                  e.g. --provider wikipedia or --provider corpus,wikipedia
```

## How it feeds into L1 and L2

The tool is designed as a **front door** to the L1 and L2 insert tools:

- **L1 output**: `python3 scripts/apply-l1-refideas.py "Article" --course "slug"`
- **L2 output**: `python3 scripts/apply-l2-external-links.py "Article" --course "slug"`

In interactive mode, it calls these functions directly:

```
ad-hoc-match (select)
    │
    ├── L1: l1_insert_refideas() → diff → confirm → _add.apply_edit()
    │
    └── L2: l2_insert_external_link() → diff → confirm → post_article_edit()
```

## Display features

### Course context

The tool shows a description of the course at the top, extracted from the first paragraph of the course's wiki page body. This gives immediate context — what the course covers, its level, and its clinical application area:

```
Course: 6.S897 — Machine Learning for Healthcare
Description: This course introduces students to machine learning in healthcare,
including the nature of clinical data and the use of machine learning for risk
stratification, disease progression modeling...
Topics: Imaging, Computer Science, Public Health, Health & Medicine, AI
```

### Article short descriptions

Each Wikipedia match shows its Wikidata short description beneath the title, when available. This helps you judge relevance at a glance without clicking through:

```
1. Quantum machine learning
   Interdisciplinary research area
   Quality: ? | Views: 4,143, ⚡ 1 maintenance
   Score: 72/100 — pre-computed match (+40); strong title overlap (+23); ...
```

Descriptions are batched in the same API call as assessments and pageviews (`prop=description`), so there's no additional latency.

## Data enrichment (live API calls)

After collecting candidates, the tool makes batch API calls to enrich each article:

1. **`prop=pageassessments`** — fetches WikiProject quality/importance ratings for ALL candidates in a single call. Picks the highest quality class (FA > GA > B > C > Start > Stub) across all WikiProjects.
2. **`prop=pageviews`** — fetches daily view counts for the last ~60 days. Sums the most recent 30 days for a monthly estimate.
3. **`prop=description`** — fetches Wikidata short descriptions for context in the match list.

**Coverage:** Pageviews and descriptions are available for virtually all articles. Quality assessments are sparser — only articles formally evaluated by a WikiProject (roughly 1 in 10) will have a class rating. Articles without assessments show `?` for quality, which is correct behavior.

## Known limitations

| Limitation | Impact | Workaround |
|-----------|--------|------------|
| Corpus covers only 220 courses | Most courses rely on Wikipedia search | Search quality depends on how descriptive the course title is |
| Quality assessments are sparse | ~90% of articles show `?` quality | This is genuine — most Wikipedia articles aren't formally assessed by any WikiProject |
| Pageviews are 30-day estimates | May not reflect long-term trends | Good enough for scoring (only 10% of total) |
| API rate limits on search | ~50 searches/minute | Tool makes 2-4 API calls per run — well within limits |
| Named entity filter is heuristic | May miss some irrelevant orgs | False negatives (letting bad matches through) are preferred over false positives |

## Quick ingest for new courses

If a course isn't in the local wiki yet, use `scripts/ingest-one.py` to add it from its OCW URL:

```bash
python3 scripts/ingest-one.py "https://ocw.mit.edu/courses/14-12-economic-applications-of-game-theory-fall-2025/"
python3 scripts/regenerate-index.py                     # update course index
python3 scripts/ad-hoc-match.py "14-12-economic-applications-of-game-theory-fall-2025"  # now it works
```

The script scrapes the OCW page for title/description, searches the MIT Learn API for metadata,
and creates a wiki page with YAML frontmatter. It handles both API-published and stub courses.

## References

- `scripts/ad-hoc-match.py` — implementation
- `scripts/contribution-protocol.py` — `l1_insert_refideas()`, `l2_insert_external_link()`
- `scripts/apply-l1-refideas.py` — L1 CLI for individual edits
- `scripts/apply-l2-external-links.py` — L2 CLI for individual edits
- `.wiki_cache/live-matches.json` — pre-computed match corpus
- `docs/L1-REFIDEAS.md` — L1 insertion algorithm
- `docs/L2-EXTERNAL-LINKS.md` — L2 insertion algorithm
- `docs/crossref-strategy.md` — WikiProject-level matching strategy
