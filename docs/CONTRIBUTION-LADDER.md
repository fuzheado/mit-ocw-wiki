# Contribution Ladder — A General Framework

> **Status:** Design phase. MIT OCW is the first corpus implementation; the framework generalizes to any citable knowledge corpus.
> **Depends on:** `docs/CONTRIBUTION-LEVELS.md`, `docs/CONTRIBUTION-PROTOCOL.md`, `docs/AD-HOC-MATCH.md`, `docs/HOWTO-NEW-PROVIDER.md`

---

## What it is

The Contribution Ladder is a **corpus-agnostic framework** for connecting any citable knowledge corpus to Wikipedia's editing workflow. It presents editors with a progressive ladder of contribution types — from safe talk-page suggestions to direct article edits — and wires together corpus ingestion, article matching, wikitext formatting, and the editing interface.

An editor climbing the ladder:

```
Rung 5: Write new content           ─┐
Rung 4: Fill [missing information]    ├─ Content creation (corpus-specific prose)
Rung 3: Replace [citation needed]    ─┘
Rung 2: Add external link            ─┐
Rung 1: Suggest as {{refideas}}       └─ Mechanical (pure formatting)
```

Each rung requires the editor to invest slightly more trust and skill, but the framework itself stays identical regardless of what corpus is being cited — MIT OCW, arXiv preprints, JSTOR journals, government reports, or library special collections.

### Why a ladder?

Wikipedia already has a contribution gradient. An edit that adds a talk page comment faces near-zero scrutiny. An edit that replaces a `{{citation needed}}` tag faces moderate scrutiny. An edit that writes a new section faces high scrutiny. The ladder mirrors this real editorial gradient and makes it navigable.

More importantly, the ladder is **the same for every corpus**. Whether you're citing an OCW lecture or a NOAA climate report, the path from "find match" to "post edit" is identical. What changes is the citation format and the matching strategy — both of which are pluggable.

---

## Architecture

The framework has four pluggable abstractions, one shared engine, and one corpus-agnostic UI:

```
┌─────────────────────────────────────────────────────────────┐
│                   CORPUS LADDER FRAMEWORK                    │
│                                                             │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐    │
│  │   Corpus     │   │    Match     │   │   Action     │    │
│  │  Connector   │   │   Provider   │   │  Formatter   │    │
│  │              │   │              │   │              │    │
│  │ ingest()     │   │ candidates() │   │ format_l1()  │    │
│  │ normalize()  │   │              │   │ format_l2()  │    │
│  │ validate()   │   │              │   │ format_l3()  │    │
│  └──────┬───────┘   └──────┬───────┘   └──────┬───────┘    │
│         │                  │                   │             │
│         ▼                  ▼                   ▼             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              Contribution Ladder Engine               │   │
│  │                                                      │   │
│  │  CorpusItem ──► MatchProvider ──► Candidate articles  │   │
│  │       │                                          │    │   │
│  │       ▼                                          ▼    │   │
│  │  Enrich (quality, views, templates) + Score + Rank    │   │
│  │       │                                               │   │
│  │       ▼                                               │   │
│  │  Generate ContributionRecord(s) for each rung level   │   │
│  │  using corpus-specific ActionFormatter                │   │
│  │       │                                               │   │
│  │       ▼                                               │   │
│  │  Feed Work Queue (filterable by project, level, corpus)│   │
│  └──────────────────────┬───────────────────────────────┘   │
│                         │                                   │
│                         ▼                                   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              Ladder UI (corpus-agnostic)              │   │
│  │                                                      │   │
│  │  Select corpus: [OCW ▾] [arXiv] [JSTOR] [+ Add...]   │   │
│  │  Filter by WikiProject, quality, level, score        │   │
│  │                                                      │   │
│  │  ┌─ Article ────┬─ Match ────┬─ Rung ───┬─ Action ─┐ │   │
│  │  │ Photovoltaics │ 3.003 (92) │ L1 ▼     │ [Apply]   │ │   │
│  │  │ Solar cell    │ 2.627 (88) │ L3 ▼     │ [Apply]   │ │   │
│  │  │ Thin film     │ 3.024 (76) │ L2 ▼     │ [Apply]   │ │   │
│  │  └──────────────┴───────────┴─────────┴───────────┘  │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## Pluggable abstractions

### 1. Corpus Connector — ingests and normalizes a corpus

Each corpus has its own API, schema, and quirks. The connector normalizes everything into a uniform `CorpusItem`.

```python
class CorpusConnector(ABC):
    """Ingest and normalize a corpus into a stream of CorpusItems."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier, e.g. 'mit-ocw', 'arxiv', 'jstor'."""
        ...

    @abstractmethod
    def ingest(self, **kwargs) -> Iterator[CorpusItem]:
        """Fetch and yield normalized items from the corpus source."""
        ...

@dataclass
class CorpusItem:
    id: str                    # e.g., "5.111SC" or "arxiv:2101.00123"
    title: str                 # human-readable title
    url: str                   # canonical URL for the item
    corpus: str                # matches CorpusConnector.name
    description: str           # 1-3 sentence summary
    tags: list[str]            # subjects, keywords, categories
    resources: list[Resource]  # videos, PDFs, datasets within the item
    license: str               # SPDX identifier
    metadata: dict             # corpus-specific extras (year, authors, etc.)

@dataclass
class Resource:
    type: str                  # "video", "pdf", "lecture_notes", "dataset", "image"
    url: str                   # direct URL to the resource
    title: str | None = None
```

The OCW connector (`scripts/ocw-ingest`) is the first implementation. It wraps the MIT Learn API, normalizes course metadata, and writes `wiki/courses/{slug}.md` with YAML frontmatter. A generalized version would also write normalized `CorpusItem` records to the work queue.

### 2. Match Provider — maps corpus items to Wikipedia articles

**Already pluggable** (`docs/HOWTO-NEW-PROVIDER.md`). The `MatchProvider` ABC in `scripts/ad-hoc-match.py` defines the interface:

```python
class MatchProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...
    
    @abstractmethod
    def find_candidates(self, course: dict) -> list[dict]:
        """Return candidate Wikipedia articles. 
        Each dict must have at minimum: title (str).
        Optional: templates, quality, views, match_source, wikiproject."""
        ...
```

The pipeline handles deduplication, enrichment (quality, pageviews, descriptions), five filter layers (broad-field, junk page types, named entities, generic words, no-overlap), scoring (corpus bonus + title specificity + acronym overlap + templates + pageviews), and ranking — all automatically for every provider.

For the generalized ladder, the only change is: `course: dict` becomes `item: CorpusItem`. The match logic itself is identical.

Four providers exist today (`corpus`, `wikipedia`, `acronym`, `simplified`). Each new corpus adds at least one provider (e.g., `arxiv` searches by paper keywords, `jstor` searches by journal subject headings).

### 3. Action Formatter — renders corpus items as Wikipedia wikitext

This is the abstraction that makes the ladder corpus-agnostic. Each corpus defines how its items are cited:

```python
class ActionFormatter(ABC):
    """Format corpus items into Wikipedia wikitext for each contribution level."""

    @property
    @abstractmethod
    def corpus_name(self) -> str:
        """Human-readable corpus name, e.g. 'MIT OpenCourseWare', 'arXiv'."""
        ...

    @abstractmethod
    def format_l1_refideas(self, item: CorpusItem, resource: Resource | None, 
                           note: str | None) -> str:
        """Generate the {{refideas}} wikitext line for a corpus item.
        
        Returns a string like:
          [url Title], Publisher (resource_type: resource_title) — note
        """
        ...

    @abstractmethod
    def format_l2_external_link(self, item: CorpusItem, description: str) -> str:
        """Generate an external links bullet for a corpus item.
        
        Returns a string like:
          * {{cite web |url=... |title=... |publisher=...}} — description
        """
        ...

    @abstractmethod
    def format_l3_citation(self, item: CorpusItem, resource: Resource) -> str:
        """Generate a <ref> citation replacing {{citation needed}}.
        
        Returns a string like:
          <ref>{{cite web |url=... |title=... |publisher=... |access-date=...}}</ref>
        """
        ...

    @abstractmethod
    def edit_summary(self, level: str, item: CorpusItem, article: str) -> str:
        """Generate the Wikipedia edit summary for a contribution."""
        ...
```

**Example: MIT OCW formatter**
```wikitext
# L1 refideas:
[https://ocw.mit.edu/courses/5-111sc-.../ MIT 5.111SC: Principles of Chemical Science], 
MIT OpenCourseWare (video lecture, lecture notes, and problem set with solutions)

# L2 external link:
* {{cite web |url=https://ocw.mit.edu/courses/6-006-.../ |title=Introduction to Algorithms 
  |publisher=MIT OpenCourseWare}} — Full course with video lectures and problem sets.

# L3 citation:
<ref>{{cite web |url=https://ocw.mit.edu/courses/5-111sc-.../lecture-7/ 
  |title=Lecture 7: Multi-electron Atoms (5.111SC) |publisher=MIT OpenCourseWare 
  |access-date=2026-05-25}}</ref>
```

**Example: arXiv formatter**
```wikitext
# L1 refideas:
[https://arxiv.org/abs/2101.00123 Attention Is All You Need], arXiv (2021)

# L2 external link:
* {{cite arXiv |eprint=2101.00123 |title=Attention Is All You Need |year=2021}} 
  — Foundational paper on transformer architectures.

# L3 citation:
<ref>{{cite arXiv |eprint=2101.00123 |title=Attention Is All You Need 
  |year=2021}}</ref>
```

Each corpus uses Wikipedia's existing citation templates (`{{cite web}}`, `{{cite arXiv}}`, `{{cite journal}}`, `{{cite book}}`, `{{cite report}}`, etc.) — no new templates needed. The formatter just maps `CorpusItem` fields to the right template parameters.

### 4. Contribution Ladder Engine — wires everything together

The engine is the shared pipeline that:

1. **Ingests** from one or more `CorpusConnector` instances
2. **Matches** each `CorpusItem` to Wikipedia articles via one or more `MatchProvider` instances
3. **Enriches** candidates with quality ratings, pageviews, short descriptions (one batch API call per 50 candidates)
4. **Filters** out noise: broad-field articles, disambiguation/glossary/list pages, named entities on weak matches, zero-overlap candidates
5. **Scores** candidates using the unified scoring formula (corpus bonus + title specificity + acronym overlap + templates + pageviews)
6. **Generates** `ContributionRecord` objects for each combination of (article, corpus item, rung level) using the corpus's `ActionFormatter`
7. **De-duplicates** against previously applied contributions (by article + corpus item URL)
8. **Feeds** the work queue — a filterable, sortable list of pending `ContributionRecord` items

The engine is corpus-agnostic. It treats every `CorpusItem` identically regardless of source. The only corpus-specific code lives in the three plugins (connector, provider, formatter).

### 5. The ContributionRecord — generalized data model

`docs/CONTRIBUTION-PROTOCOL.md` defines the full schema. For the generalized framework, the `source` block is generalized from OCW-specific field names to corpus-agnostic ones:

| OCW-specific (current) | Generalized (target) |
|------------------------|---------------------|
| `source.course_id` | `source.id` |
| `source.course_title` | `source.title` |
| `source.course_url` | `source.url` |
| `source.lecture_title` | `source.resource_title` |
| `source.lecture_url` | `source.resource_url` |
| `source.license` = `"CC BY-NC-SA 4.0"` | `source.license` = any SPDX identifier |
| `source.corpus` (implicit: `"mit-ocw"`) | `source.corpus` = `CorpusConnector.name` |
| `action.edit_summary` = `"...via Wiki MIT"` | `action.edit_summary` = `"...via Wiki {corpus_name}"` |

All other fields — the article target, the action type, the review fields, the work queue structure — remain identical regardless of corpus.

---

## Adding a new corpus: arXiv walkthrough

Adding a corpus requires three small plugins. Here's arXiv as an example.

### Plugin 1: ArxivConnector

```python
class ArxivConnector(CorpusConnector):
    name = "arxiv"
    
    def ingest(self, category: str = "cs.AI", max_results: int = 100) -> Iterator[CorpusItem]:
        """Fetch papers from arXiv API by category."""
        import feedparser
        url = (f"https://export.arxiv.org/api/query?"
               f"search_query=cat:{category}&start=0&max_results={max_results}")
        feed = feedparser.parse(url)
        for entry in feed.entries:
            arxiv_id = entry.id.split("/abs/")[-1]
            yield CorpusItem(
                id=f"arxiv:{arxiv_id}",
                title=entry.title.strip(),
                url=entry.id,
                corpus="arxiv",
                description=entry.summary[:500],
                tags=[entry.get("arxiv_primary_category", {}).get("term", "")],
                resources=[Resource(type="pdf", url=entry.id.replace("/abs/", "/pdf/"))],
                license="arXiv non-exclusive license",
                metadata={
                    "year": entry.published[:4] if "published" in entry else None,
                    "authors": [a.name for a in entry.authors]
                }
            )
```

### Plugin 2: ArxivMatchProvider

```python
class ArxivMatchProvider(MatchProvider):
    name = "arxiv"
    
    def find_candidates(self, item: CorpusItem) -> list[dict]:
        """Search Wikipedia by paper title keywords and author names."""
        # Extract significant words from title, skip common stopwords
        keywords = extract_keywords(item.title, item.description)
        query = " OR ".join(keywords[:5])
        results = search_wikipedia(query, limit=10)
        return [
            {"title": r["title"], "match_source": f"arxiv:{item.id}"}
            for r in results
        ]
```

### Plugin 3: ArxivFormatter

```python
class ArxivFormatter(ActionFormatter):
    corpus_name = "arXiv"
    
    def format_l1_refideas(self, item, resource=None, note=None):
        year = f" ({item.metadata['year']})" if item.metadata.get("year") else ""
        return f"[{item.url} {item.title}], arXiv{year}"
    
    def format_l2_external_link(self, item, description):
        eprint = item.id.split(":")[-1] if ":" in item.id else item.id
        year = f" |year={item.metadata['year']}" if item.metadata.get("year") else ""
        return (f"* {{{{cite arXiv |eprint={eprint} "
                f"|title={item.title}{year}}}}} — {description}")
    
    def format_l3_citation(self, item, resource):
        eprint = item.id.split(":")[-1] if ":" in item.id else item.id
        year = f" |year={item.metadata['year']}" if item.metadata.get("year") else ""
        return (f"<ref>{{{{cite arXiv |eprint={eprint} "
                f"|title={item.title}{year}}}}}</ref>")
    
    def edit_summary(self, level, item, article):
        return f"/* Suggested reference */ via Wiki arXiv — {item.id}"
```

### Registration

```python
register_corpus("arxiv", ArxivConnector(), ArxivMatchProvider(), ArxivFormatter())
```

Total: ~70 lines of corpus-specific code. The ladder engine handles everything else.

---

## Corpus candidates beyond MIT OCW

| Corpus | Why it fits the ladder | L1-L3 potential | License / citation |
|--------|----------------------|-----------------|-------------------|
| **arXiv** | Preprints on every STEM topic. Perfect for `[citation needed]` replacement | Very high | `arXiv.org perpetual, non-exclusive` — compatible with citation |
| **JSTOR** | Peer-reviewed journals across all academic fields. Stable DOIs | High | Mixed publisher licenses — but citation is Fair Use |
| **PubMed Central** | Open-access biomedical papers. Structured, citable | High | Mostly CC BY — ideal |
| **CORE** (UK) | World's largest open-access aggregator. 200M+ papers | High | Mixed — open-access filter available |
| **Library of Congress Digital Collections** | Primary sources, maps, photographs, manuscripts | Medium (L1-L2) | Mostly public domain or rights-cleared |
| **Data.gov / government portals** | Official statistics, reports, environmental data | Medium | Public domain (US government works) |
| **Wikimedia Commons** (as a corpus) | Images, videos, diagrams already on Commons — need placement | Medium (L2-L3) | Already free-licensed |
| **OpenStax / Open textbooks** | Peer-reviewed open textbooks — chapter-level citations | High | CC BY |
| **Internet Archive** | Books, archived web, audio, video | Medium | Mixed — millions of public domain works |
| **SSRN / RePEc** | Social science and economics preprints | Medium | Preprint license — citable |
| **NOAA / NASA climate data** | Authoritative scientific data and reports | Medium | Public domain |
| **HathiTrust Digital Library** | Scanned books from academic libraries | Medium | Mixed — large public domain subset |

---

## Design principles

### 1. Start advisory, not automated

Every corpus begins at Rung 1 (talk page `{{refideas}}` suggestions). Direct article edits (L2+) require demonstrated match quality and community acceptance. This protects Wikipedia's editorial norms and builds trust incrementally.

### 2. Pre-fill everything

Every suggestion includes a complete, ready-to-paste wikitext snippet. The editor never needs to format a citation by hand. For the advisory phase (pre-OAuth), the interface provides a "Copy to clipboard" button for every rung.

### 3. One record, one edit

Each `ContributionRecord` maps to exactly one Wikipedia edit. No multi-step records. This keeps the work queue atomic and resumable — if an edit fails or an editor stops mid-session, nothing is lost.

### 4. Corpus-agnostic scoring

Every corpus item's matches are scored by the same formula. The pipeline doesn't care whether the source is OCW, arXiv, or JSTOR — only the match quality matters. This makes cross-corpus comparisons meaningful.

### 5. Per-corpus metrics

Acceptance rates, revert rates, and editor feedback are tracked per corpus. Underperforming corpora get throttled back to advisory-only (L1). High-performing corpora earn the right to offer L2+ edits. The ladder controls this escalation.

### 6. Respect the `file://` constraint (Phase 1)

The contribution interface should work as static HTML initially, like the Impact Matrix. No server required for browsing, filtering, and generating wikitext. OAuth authentication and one-click editing are a Phase 2 upgrade — the advisory version delivers value on its own.

---

## Implementation path

### Phase 1: Generalize the data model (1 session)

- Rename OCW-specific fields in `ContributionRecord` to generalized equivalents
- Make backward-compatible: old OCW records continue to work, new corpora use new field names
- Update `scripts/contribution-protocol.py` validation rules
- Update `docs/CONTRIBUTION-PROTOCOL.md`

### Phase 2: Extract ActionFormatter ABC (1 session)

- Extract the wikitext generation from `contribution-protocol.py` into an `OcwFormatter` class
- Define the `ActionFormatter` ABC with `format_l1`, `format_l2`, `format_l3`, `edit_summary`
- Add MIT OCW as the first implementation
- Refactor `build_refideas_wikitext()` to accept an `ActionFormatter` parameter
- 22 existing L1 insert tests should pass unchanged

### Phase 3: Add a second corpus — arXiv (1-2 sessions)

- Write `ArxivConnector` (ingests from arXiv API by category)
- Write `ArxivMatchProvider` (registers in `ad-hoc-match.py`)
- Write `ArxivFormatter` (uses `{{cite arXiv}}` template)
- Register all three with `register_corpus()`
- Generate a work queue mixing OCW and arXiv records

### Phase 4: Build the static ladder UI (1-2 sessions)

- `wiki/editor/index.html` — filterable work queue with corpus selector
- Reads `live-data.js` and `ocw-matches.js` (plus any new corpus match data)
- Shows rung selector per article: L1 (refideas), L2 (external link), L3 (citation) where applicable
- "Copy to clipboard" for each pre-formatted wikitext snippet
- Works from `file://`

### Phase 5: OAuth + one-click editing (1-2 sessions)

- Add OAuth 2.0 flow (either on-wiki or Toolforge callback)
- "Apply" button replaces copy-to-clipboard
- Edit attribution: individual editor accounts, not a bot
- Rate limiting and confirmation dialogs

### Phase 6: Additional corpora and rungs

- Add JSTOR, PubMed Central, or government data as new corpora
- Graduate the OCW pipeline to L3 (replace `{{cn}}`) as acceptance rates validate match quality
- Per-corpus dashboards showing edit count, acceptance rate, revert rate

---

## Reference

| Document | Covers |
|----------|--------|
| `docs/CONTRIBUTION-LEVELS.md` | Full L1-L5 specification and processing details |
| `docs/CONTRIBUTION-PROTOCOL.md` | `ContributionRecord` schema, validation rules, work queue structure |
| `docs/AD-HOC-MATCH.md` | Match provider architecture, 5 filter layers, scoring formula |
| `docs/HOWTO-NEW-PROVIDER.md` | Step-by-step guide for writing a `MatchProvider` |
| `docs/ROADMAP.md` | Project roadmap — Phase 2 (subsystem integration) and Phase 3 (contribution interface) |
| `docs/L1-REFIDEAS.md` | L1 algorithm, pure function pattern, linter/fixer tools |
| `docs/L2-EXTERNAL-LINKS.md` | L2 algorithm, section targeting, course resolution |
