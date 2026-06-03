# How to Add a New Match Provider

The ad-hoc match tool (`scripts/ad-hoc-match.py`) uses a **pluggable provider architecture**
for finding Wikipedia article matches. Each matching strategy is a separate class that
implements the `MatchProvider` interface. The pipeline orchestrator handles everything else
— deduplication, enrichment, filtering, scoring, and ranking.

This guide walks through adding a new provider step by step.

---

## Quick start: the interface

```python
from abc import ABC, abstractmethod

class MatchProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier. Used in --provider flag."""
        ...

    @abstractmethod
    def find_candidates(self, course: dict) -> list[dict]:
        """Return candidate articles for this course.
        
        Each candidate dict must have at minimum:
          - title: str  (Wikipedia article title)
        
        Optional fields the pipeline will use:
          - templates: list[str]  (maintenance templates like ['cn'])
          - quality: str          ('FA', 'GA', 'B', 'C', 'Start', 'Stub')
          - views: int            (monthly pageview estimate)
          - match_source: str     (shown as "Source:" in output)
          - wikiproject: str      (WikiProject name, for display)
        """
        ...
```

## Step 1: Write the provider class

Providers go in `scripts/ad-hoc-match.py`, in the section marked `# MATCH PROVIDER INTERFACE`.
Add your class alongside the existing ones (`CorpusProvider`, `WikipediaSearchProvider`, etc.).

Here's a template:

```python
class MyCustomProvider(MatchProvider):
    """Description of what this provider does and when to use it."""

    @property
    def name(self) -> str:
        return "my-custom"  # used in --provider my-custom

    def find_candidates(self, course: dict) -> list[dict]:
        # course has: course_id, title, url, slug, topics, department,
        #             instructors, description
        course_title = course["title"]
        course_id = course["course_id"]
        topics = course["topics"]
        
        candidates = []
        
        # ... your matching logic here ...
        # For each match, append a dict:
        candidates.append({
            "title": "Some Wikipedia Article",  # required
            "templates": ["citation needed"],    # optional — helps scoring
            "match_source": "my custom source",  # optional — shown in output
        })
        
        return candidates
```

## Step 2: Register it

Find the `PROVIDER_REGISTRY` dict in `scripts/ad-hoc-match.py` and add your provider:

```python
PROVIDER_REGISTRY: dict[str, type[MatchProvider]] = {
    "corpus": CorpusProvider,
    "wikipedia": WikipediaSearchProvider,
    "acronym": AcronymExpansionProvider,
    "simplified": SimplifiedSearchProvider,
    "my-custom": MyCustomProvider,  # ← add yours here
}
```

## Step 3: Use it

```bash
# Use your provider alone
python3 scripts/ad-hoc-match.py "6.S897" --provider my-custom

# Combine with existing providers
python3 scripts/ad-hoc-match.py "6.S897" --provider "corpus,wikipedia,my-custom"
```

---

## What the pipeline does for you

After your provider returns candidates, the pipeline automatically:

| Step | What it does | Why |
|------|-------------|-----|
| **Deduplication** | Removes articles with the same title from multiple providers | Your provider doesn't need to check for duplicates with other providers |
| **Enrichment** | Batch-fetches quality (`prop=pageassessments`), pageviews (`prop=pageviews`), and short descriptions (`prop=description`) from Wikipedia API | Your provider can return just `{"title": "..."}` — the pipeline fills in the rest |
| **Page type check** | Batch-checks for disambiguation, glossary, and list pages | Your provider doesn't need to filter these |
| **Named entity filter** | Removes organizations/schools on weak matches | Filters out false positives from broad keyword searches |
| **No-overlap filter** | Removes articles with zero title word overlap and no maintenance templates | Filters out noise from broad topic searches |
| **Scoring** | Applies the scoring formula (corpus bonus, title specificity, expanded acronyms, templates, views) | Your provider doesn't need to implement scoring — it gets scored the same way as all other candidates |
| **Ranking** | Sorts by score descending, returns top N | Consistent ranking across all providers |

**Your provider only needs to find candidates.** Everything else is shared infrastructure.

---

## What you get for free

### Data enrichment

The pipeline makes one API call per 50 candidates that fetches:

```python
# All three in a single query:
prop=pageassessments|pageviews|description
```

Your candidates get quality ratings (FA/GA/B/C/Start/Stub), monthly pageview estimates, and Wikidata short descriptions — all without your provider doing anything.

### Filtering

Five automatic filters apply to every candidate from every provider:

| Filter | What it removes | How it works |
|--------|----------------|-------------|
| Broad-field articles | "Computer science", "Physics", "Mathematics" | Title checked against a blocklist |
| Junk page types | Disambiguation, glossary, list pages | API batch-check via `prop=pageprops\|categories` |
| Named entities | Schools, companies, orgs with no title overlap | Title checked against keyword list |
| Generic category words | "History" doesn't count as content overlap | Word excluded from specificity scoring |
| No-overlap exclusion | Articles with zero title word overlap and no templates | Removes coincidental matches |

### Scoring

The same scoring formula applies to all candidates:

```
score = corpus_bonus (0-40)
      + title_specificity (0-35)
      + expanded_acronym_overlap (0-20)
      + maintenance_templates (0-15)
      + pageviews (0-10)
```

See `docs/AD-HOC-MATCH.md` for the full scoring details.

---

## Example: A provider using the Wikipedia API

Here's a provider that searches Wikipedia by course topics instead of title:

```python
class TopicSearchProvider(MatchProvider):
    """Search Wikipedia by course topics (from YAML frontmatter)."""

    @property
    def name(self) -> str:
        return "topics"

    def find_candidates(self, course: dict) -> list[dict]:
        candidates = []
        for topic in course.get("topics", []):
            if not topic or len(topic) < 3:
                continue
            results = search_wikipedia(topic, limit=10)
            for r in results:
                candidates.append({
                    "title": r["title"],
                    "match_source": f"topic: {topic}",
                })
        return candidates
```

Note: This provider doesn't worry about:
- Duplicates (the pipeline deduplicates)
- Junk pages (the pipeline filters them)
- Scoring (the pipeline scores everything uniformly)
- Quality/views (the pipeline enriches them)

---

## Example: A provider using an external API

```python
class LLMProvider(MatchProvider):
    """Use an LLM to suggest relevant Wikipedia articles."""

    @property
    def name(self) -> str:
        return "llm"

    def find_candidates(self, course: dict) -> list[dict]:
        prompt = f"Suggest 5 Wikipedia articles relevant to: {course['title']}"
        # Call your LLM API here
        suggestions = call_llm_api(prompt)  # returns ["Title 1", "Title 2", ...]
        return [{"title": t, "match_source": "LLM suggestion"} for t in suggestions]
```

---

## Testing your provider

```bash
# Quick smoke test
python3 scripts/ad-hoc-match.py "6.S897" --provider my-custom --top 5

# Compare against default
python3 scripts/ad-hoc-match.py "6.S897" --top 5
python3 scripts/ad-hoc-match.py "6.S897" --provider my-custom --top 5

# Check filtering is working (shouldn't show glossary/list pages)
python3 scripts/ad-hoc-match.py "6.S897" --provider my-custom --top 20
```

## Adding your provider to the default set

If your provider should run by default, add it to `DEFAULT_PROVIDERS`:

```python
DEFAULT_PROVIDERS = ["corpus", "wikipedia", "acronym", "simplified", "my-custom"]
```

## Updating documentation

When you add a new provider, update:

1. **`docs/AD-HOC-MATCH.md`** — add your provider to the table in the Match Providers section
2. **`docs/HOWTO-NEW-PROVIDER.md`** — add a brief example if your provider demonstrates a new technique
3. **`README.md`** — mention the new `--provider` option if it represents a significant new capability
