# Wikidata Vector Database for OCW→Wikipedia Matching

> **Status:** Feasibility analysis. Evaluates whether the Wikidata Vector Database (`wd-vectordb.wmcloud.org`) can improve our OCW course → Wikipedia article matching pipeline.
> **Answer:** Yes — but as a **complementary signal**, not a replacement for keyword matching or zerank-2. It adds a structured semantic dimension that neither text-based approach captures.

---

## What the Wikidata Vector Database is

A live REST API (`wd-vectordb.wmcloud.org`) that stores vector embeddings for ~30 million Wikidata items. Launched October 2025 by Wikimedia Deutschland, currently in alpha.

| Property | Value |
|----------|-------|
| **Items covered** | ~30M (all with at least one Wikipedia article) |
| **Embedding model** | Jina.AI, 100+ languages, 8192 token context |
| **Embedding date** | September 2024 dump (updates planned) |
| **Search method** | Hybrid: vector similarity + keyword, merged via Reciprocal Rank Fusion |
| **Language support** | Per-language sharding (April 2026), `lang=all` for cross-lingual |
| **Access** | Free, no auth required, rate limits apply |

### API Endpoints

| Endpoint | What it does |
|----------|-------------|
| `GET /item/query/?query=...&lang=en` | Semantic search for Wikidata items (QIDs) |
| `GET /property/query/?query=...` | Semantic search for Wikidata properties (PIDs) |
| `GET /similarity-score/?query=...&ids=Q1|Q2|...` | Score similarity between a query and specific items |

Example:

```bash
curl "https://wd-vectordb.wmcloud.org/item/query/?query=carbon+cycle&lang=en&limit=5"
```

Returns:
```json
{
  "items": [
    {"id": "Q167751", "label": "carbon cycle", "score": 0.92, "rrf_score": 0.98},
    {"id": "Q7942",   "label": "climate change", "score": 0.78, "rrf_score": 0.85},
    ...
  ]
}
```

---

## How it compares to our existing signals

| Signal | What it captures | Example |
|--------|-----------------|---------|
| **Keyword overlap** (ad-hoc-match.py) | Exact word matching: "Algorithm" in course title ↔ "Algorithm" in article title | Fast, structural, but misses synonyms |
| **Zerank-2** (cross-encoder) | Full-text semantic relevance: reads course description + article lead together | Deep semantic understanding, but text-only |
| **Wikidata vectors** | Structured concept similarity: how close are these two concepts in Wikidata's knowledge graph? | Captures conceptual relationships invisible to text |

### Concrete example: "12.340 Global Warming Science"

| Approach | Top match | Why |
|----------|-----------|-----|
| **Keyword** | "Global warming" (title match) | Direct keyword overlap with course title |
| **Zerank-2** | "Climate model" (0.89) | Reads the course description mentioning climate models |
| **Wikidata vectors** | Would find "Carbon cycle" (Q167751), "Radiative forcing" (Q7258934), "Climate sensitivity" (Q521783) | These concepts are graph-neighbors of climate science in Wikidata, even though they share no words with the course title |

Zerank-2 might also find these, but only if the course description or lecture text mentions them. Wikidata vectors find them through the structured knowledge graph.

---

## Three ways Wikidata vectors could improve our pipeline

### 1. Concept Expansion: Enrich course queries with related Wikidata items

```
OCW Course: "12.340 Global Warming Science"
    │
    ▼
Wikidata Vector Search: "global warming science"
    → Q7942 (climate change) — score 0.89
    → Q167751 (carbon cycle) — score 0.82
    → Q521783 (climate sensitivity) — score 0.78
    → Q7258934 (radiative forcing) — score 0.75
    │
    ▼
Add these concept labels as additional search queries:
    "global warming science" + "climate change" + "carbon cycle" + ...
    │
    ▼
Wikipedia Search API with expanded query → broader candidate set
```

This catches articles that are conceptually related but share no keywords with the course title. The collaborator's pipeline found "Carbon cycle" for "Global Warming Science" — Wikidata vectors would surface this relationship automatically.

**Implementation:** New `WikidataExpansionProvider` in `ad-hoc-match.py`.

```python
class WikidataExpansionProvider(MatchProvider):
    """Expand course query with semantically related Wikidata concepts."""
    
    name = "wikidata"
    
    def find_candidates(self, course: dict) -> list[dict]:
        # 1. Search Wikidata vectors for concepts related to course title + topics
        related_items = self._search_wikidata_vectors(course["title"])
        
        # 2. For each related Wikidata item, find its Wikipedia article (sitelink)
        expanded_queries = []
        for item in related_items[:10]:
            article = self._get_wikipedia_sitelink(item["id"])
            if article and article not in seen:
                expanded_queries.append(article)
        
        # 3. Also use the concept labels as search terms
        concept_labels = [item["label"] for item in related_items[:5]]
        expanded_search = f"{course['title']} {' '.join(concept_labels)}"
        
        # 4. Search Wikipedia with expanded terms
        from_wikipedia = search_wikipedia(expanded_search, limit=15)
        
        return expanded_queries + from_wikipedia
```

### 2. Match Verification: Score candidate articles by Wikidata concept proximity

```
Candidate article: "Carbon cycle"
    │
    ▼
Wikidata Vector Search: "carbon cycle" → Q167751
    │
    ▼
/similarity-score/?query=global+warming+science&ids=Q167751
    → score: 0.82  ← carbon cycle is semantically close to global warming science
    
Candidate article: "Baseball"
    │
    ▼
/similarity-score/?query=global+warming+science&ids=Q5369
    → score: 0.12  ← baseball is not related
```

This gives us a Wikidata-based relevance score for every candidate, independent of text overlap. We can blend it with keyword and zerank-2 scores:

```python
combined_score = (
    0.3 × keyword_score_norm +    # structural match
    0.4 × zerank_score +           # semantic text match
    0.3 × wikidata_score           # concept graph match
)
```

### 3. Article Quality Signal: Wikidata item richness as a proxy for article maturity

Articles whose corresponding Wikidata items have many statements, references, and sitelinks are typically better-maintained. This is a complementary quality signal to PageAssessments:

```python
def wikidata_richness(qid: str) -> float:
    """Score Wikidata item completeness as a quality proxy."""
    # Via Wikidata API:
    item = get_entity(qid)
    statements = len(item.get("claims", {}))
    sitelinks = len(item.get("sitelinks", {}))
    references = count_references(item)
    
    # Normalize to 0-1
    return min(1.0, (statements * 0.3 + sitelinks * 0.4 + references * 0.3) / 50)
```

---

## Limitations

| Limitation | Impact on our use case |
|-----------|----------------------|
| **Alpha release** | API may change, rate limits unclear, no SLA |
| **September 2024 dump** | New Wikidata items created after Sept 2024 are not embedded. Items edited since then may have stale vectors. |
| **Item-level, not article-level** | Vectors represent Wikidata items, not Wikipedia articles directly. An article without a Wikidata item has no vector. |
| **Text input, not article text** | The embedding is of the Wikidata item's label + description + aliases (short text), not the full Wikipedia article. Different from zerank-2's deep text comparison. |
| **~30M items** | Only items with Wikipedia articles are included. Niche concepts without articles are absent. |
| **Jina.AI model** | The embedding model may not perform identically on all domains (STEM vs. humanities). |

---

## Should we use it?

| Use case | Wikidata vectors? | Why |
|----------|------------------|-----|
| **Fast interactive matching** (Workbench UI) | ⚠️ Maybe — adds 200-500ms per API call | Latency-sensitive; might slow the UX |
| **Concept expansion** (batch candidate generation) | ✅ Yes — adds candidates keyword search misses | Batch-friendly, no latency concern |
| **Match scoring** (blend with zerank-2) | ✅ Yes — orthogonal signal | Different dimension from text scoring |
| **Article quality signal** | ✅ Yes — complementary to PageAssessments | Useful for prioritizing edits |
| **Replacing keyword matching** | ❌ No — Wikidata vectors alone are too lossy for article retrieval | Keyword matching is still essential |

---

## Implementation path

### Phase 1: Concept expansion prototype (1 session)

- `WikidataExpansionProvider` in `ad-hoc-match.py`
- Calls `wd-vectordb.wmcloud.org/item/query/` with course title
- Extracts Wikipedia sitelinks from top-N related items
- Adds them as candidates alongside keyword results
- Evaluate: how many new candidates does this surface?

### Phase 2: Wikidata similarity scoring (1 session)

- Add `wikidata_score` field to candidate articles
- Call `/similarity-score/` for each candidate's Wikidata item against the course title
- Blend with existing keyword + zerank-2 scores
- Tune blend weights against collaborator ground truth

### Phase 3: Wikidata richness quality signal (shared with dashboard)

- Add Wikidata item statement/sitelink counts to the dashboard
- Use as an additional quality column in the article table

---

## Reference

| Resource | URL |
|----------|-----|
| Wikidata Embedding Project | https://www.wikidata.org/wiki/Wikidata:Embedding_Project |
| Wikidata Vector Database | https://www.wikidata.org/wiki/Wikidata:Vector_Database |
| Vector DB API | https://wd-vectordb.wmcloud.org/ |
| API Documentation | https://wd-vectordb.wmcloud.org/docs |
| Vector DB GitHub | https://github.com/wmde/WikidataSearch |
| Vectors on HuggingFace | https://huggingface.co/datasets/philippesaade/Wikidata_Vectors_0.2 |
| `docs/ZERANK-INTEGRATION.md` | Zerank-2 cross-encoder integration |
| `docs/ZERANK-PIPELINE.md` | Full matching pipeline architecture |
