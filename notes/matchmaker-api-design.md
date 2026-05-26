# Wiki MIT Matchmaker API — Design Document

## Motivation

The Contribution Impact Matrix identifies which articles need work. The
crossref heatmap shows where OCW courseware overlaps with those articles.
But neither tells an editor **exactly which course material to use and
how to cite it.**

The Matchmaker API bridges this gap: given a Wikipedia article (or a
specific claim within it), return ranked MIT OCW resources with direct
links and citation-ready snippets.

---

## Existing Context

This design builds on two existing pieces of work:

- **docs/crossref-strategy.md** — describes the three-tier matching strategy
  (keyword, SQL, semantic) currently used to generate the static heatmap.
  The Matchmaker API would replace or augment Tier 3 with live vector search.

- **Wiki MIT Technical Collaboration Briefing** — proposes the `/match/article`
  and `/match/claim` endpoints with vector embeddings and the Lift Wing API.

---

## Design Principles

1. **Editors come first.** Every response should reduce friction: include
   a citation snippet, a deep link, a course code. Don't make the editor
   click through three pages to find the useful part.

2. **Offline data gen first, live API second.** The Impact Matrix proved
   that pre-generation is robust. The Matchmaker should work in batch mode
   too — not require a live server for the basic use case.

3. **Fail gracefully.** No OCW match for this article? Return an empty
   list, not an error. Don't make the editor wonder if the tool is broken.

4. **Cost-aware.** Embedding calls and vector search cost money. Design
   the batching to minimize API calls without sacrificing quality.

---

## Architecture

### Data Sources

| Source | Content | Access | Cost |
|--------|---------|--------|------|
| MIT Learn API | Course metadata, descriptions, topics | Public REST | Free |
| MIT Learn `/vector_similar/` | Pre-computed course embeddings | Public REST | Free |
| OCW course pages (scraped) | Lecture titles, transcripts, slide text | Local (wiki/) | Free |
| Wikipedia API (`action=parse`) | Article wikitext and rendered text | Public REST | Free |
| Lift Wing API | Article topic model (outlinks) | Public REST | Free |

### Embedding Strategy

Two options:

**A. Use MIT Learn's built-in vector search.** The Learn API already has
a `/learning_resources/{id}/vector_similar/` endpoint. This costs nothing
extra and uses MIT's own embeddings (likely the same ones used for OCW
site search). The tradeoff: query-side embeddings must be computed by us,
and we need to host an embedding model or pay for one.

**B. Use a separate embedding model (e.g., OpenAI `text-embedding-3-small`
or a local SentenceTransformer model).** More flexible — we control the
latent space and can embed both Wikipedia articles and OCW materials into
the same space. The tradeoff: recurring cost per query or a GPU to run
the model locally.

**Recommendation: Start with Option A (MIT Learn's vector search) for
simplicity, then evaluate whether Option B improves match quality enough
to justify the cost.**

### Match Flow (Option A)

```
Editor pastes article title or claim text
                │
                ▼
    Fetch article content via Wikipedia API
    (action=parse&prop=text)
                │
                ▼
    [Optional] Lift Wing topic routing
    to narrow OCW course search space
    (e.g., "Physics" → only query
     physics-related courses)
                │
                ▼
    Compute query embedding
    (via MIT Learn API or local model)
                │
                ▼
    Query MIT Learn /vector_similar/
    for top-K similar courses
                │
                ▼
    Score & rank results
    (cosine similarity + quality boost
     + section-level match bonus)
                │
                ▼
    Return ranked matches with
    deep links and citation snippets
```

### Match Flow (Option B — Offline Batch)

```
    For each WikiProject article with
    maintenance templates (from LIVE_DATA):
                │
                ▼
    Compute article embedding
    (batch, cached)
                │
                ▼
    Compute OCW course embeddings
    (batch, cached once)
                │
                ▼
    Compute cosine similarity matrix
    Article × Course → score
                │
                ▼
    For each article, store
    top-5 course matches
    in a lookup table
                │
                ▼
    Serve from static data
    (no live API calls at runtime)
```

---

## Proposed Endpoints

### POST /v1/match/article

Given a Wikipedia article title, return ranked OCW resources.

**Request:**
```json
{
  "article_title": "Photosynthesis",
  "lang": "en",
  "max_results": 5,
  "include_sections": false
}
```

**Response:**
```json
{
  "query": "Photosynthesis",
  "article_url": "https://en.wikipedia.org/wiki/Photosynthesis",
  "quality": "GA",
  "importance": "Top",
  "matched_courses": [
    {
      "course_id": "7.05",
      "title": "General Biochemistry",
      "department": "Biology",
      "similarity_score": 0.91,
      "url": "https://ocw.mit.edu/courses/7-05-general-biochemistry-spring-2020/",
      "matched_topics": ["photosynthesis", "calvin cycle", "chloroplast"],
      "resources": [
        {
          "type": "video",
          "label": "Lecture 15: Photosynthesis",
          "url": "https://ocw.mit.edu/.../lecture-15/",
          "deep_link": "https://ocw.mit.edu/.../lecture-15/#t=120s"
        },
        {
          "type": "lecture_notes",
          "label": "Lecture 15: Photosynthesis Notes",
          "url": "https://ocw.mit.edu/.../lecture-15-notes.pdf"
        }
      ],
      "suggested_citation": "{{Cite web |url=https://ocw.mit.edu/courses/7-05-general-biochemistry-spring-2020/ |title=General Biochemistry |publisher=MIT OpenCourseWare |access-date=2026-05-18}}"
    }
  ]
}
```

### POST /v1/match/claim

Given a specific sentence or claim, return OCW materials that verify or
expand it.

**Request:**
```json
{
  "claim_text": "The Calvin cycle uses ATP and NADPH to convert carbon dioxide into glucose.",
  "resource_type": ["video", "lecture_notes"]
}
```

**Response:** Same structure as `/match/article`, but the match scores
are computed against the claim text rather than the full article.

---

## Phased Implementation

### Phase 0: Static Lookup Table (Current State)

The crossref heatmap already stores pre-computed matches between OCW
departments and WikiProjects. This is the coarsest level of matching
and requires no API.

**Output:** `wiki/reports/crossref-heatmap.html`
**Match scope:** Department × WikiProject

### Phase 1: Offline Per-Article Lookup

Extend the data generation pipeline to compute per-article matches.
For each article in LIVE_DATA that has maintenance templates, find the
top-N OCW courses using the existing docs/crossref-strategy scoring model
(keyword + SQL + simple semantic overlap).

**Output:** A `match_lookup.json` file keyed by article title, embedded
into the Impact Matrix detail panel at generation time.
**Match scope:** Article → OCW course
**Runtime API calls:** 0 (pre-generated)

### Phase 2: Hosted Lookup Service

Deploy a lightweight API on Toolforge that uses MIT Learn's
`/vector_similar/` endpoint for live queries. No embedding model to
host — outsource that to MIT Learn.

**Stack:** Flask/FastAPI on Toolforge, pymysql for Wikipedia metadata,
requests for MIT Learn API.
**Match scope:** Any Wikipedia article (not just the 11,500 in LIVE_DATA)
**Runtime API calls:** 2 (Wikipedia API + MIT Learn API) per query

### Phase 3: Full Semantic Matchmaker

Host a dedicated embedding model (e.g., SentenceTransformers
`all-MiniLM-L6-v2` or larger) alongside course embeddings.
Compute query embeddings locally, then cosine similarity against
pre-computed course embeddings. This removes the MIT Learn API
dependency and gives full control over the latent space.

**Stack:** FastAPI + ONNX or llama.cpp for embedding, numpy for
similarity search, Toolforge or a small VM for hosting.
**Match scope:** Any Wikipedia article, any OCW resource type
(including per-section and per-lecture matching)
**Runtime API calls:** 1 (Wikipedia API for article text)

---

## Open Questions

1. **Vector dimensionality.** What embedding dimension does MIT Learn's
   `/vector_similar/` expect? We need to match it or accept lower scores.
   (Needs investigation.)

2. **Citation format.** The suggested citation should follow Wikipedia's
   citation templates (`{{Cite web}}`, `{{Cite book}}`).
   Should it also include a `{{Refideas}}` wrapper for talk page use?

3. **Rate limits.** MIT Learn API rate limits are unknown. We should
   test with a small batch before designing the batch flow.

4. **Cost of Phase 3.** Hosting a SentenceTransformer model is cheap
   (~$5-10/mo on a tiny VM), but the initial batch embedding of 2,577
   courses × their assets may require significant compute. Cloud or local?

5. **Where to host.** Toolforge is the natural home (Wikimedia-aligned,
   free, already has SSH tunnel access). But Toolforge doesn't support
   Python web frameworks natively — it requires a Kubernetes pod or a
   PHP wrapper. A Linode/AWS Lightsail instance at ~$10/mo might be
   simpler.

6. **Does this replace or complement the heatmap?** The heatmap is a
   browseable overview. The API is a point-query tool. They serve
   different use cases and should coexist.

---

## Relationship to Existing Tools

| Tool | Input | Output | Pre-computed? | API needed? |
|------|-------|--------|---------------|-------------|
| Contribution Impact Matrix | WikiProject name | Scatterplot of articles | Yes | No (file://) |
| Crossref heatmap | None (browse) | Department × Project matrix | Yes | No (file://) |
| Matchmaker API (Phase 1) | Article title | Ranked OCW courses | Yes | No (static file) |
| Matchmaker API (Phase 2+) | Article title / claim | Ranked OCW courses + citations | No | Yes (hosted) |

The Phase 1 approach — a static `match_lookup.json` embedded during data
generation — is the most natural extension of the current architecture
and respects the `file://` constraint. Phase 2+ opens the door to live
queries for any article, but requires hosting.
