# Recommendation Exchange Protocol (REP)

> **Status:** Design phase. Generalizes the collaborator PDF pipeline into a standard API for sharing Wikipedia improvement recommendations between producers (anyone with a matching pipeline) and consumers (Wiki MIT contribution tools).
>
> **Motivation:** Currently, external recommendations arrive as PDFs with ad-hoc parsing scripts (`review-collaborator-matches.py`). A proper API would allow any producer — academic labs, GLAM institutions, other WikiProjects — to submit scored matches in a standard format, and our tools to consume them uniformly.

---

## Table of Contents

1. [Overview](#overview)
2. [Data Model](#data-model)
3. [REST API](#rest-api)
4. [Authentication](#authentication)
5. [Client Libraries](#client-libraries)
6. [Examples](#examples)
7. [Consumer Pipeline](#consumer-pipeline)

---

## Overview

### Producer → Consumer Flow

```
┌─────────────────┐     POST /api/v1/recommendations     ┌─────────────────┐
│                 │  ──────────────────────────────────►  │                 │
│   Producer      │     { recommendations: [...] }        │   Wiki MIT      │
│   (any pipeline)│                                       │   Consumer      │
│                 │  ◄──────────────────────────────────  │                 │
└─────────────────┘     { batch_id, accepted, ... }       └────────┬────────┘
                                                                   │
                                                   ┌────────────────┴────────┐
                                                   ▼                         ▼
                                            L1 Editor              L2 Editor
                                         (refideas on Talk)    (external links)
```

The producer runs their own matching pipeline (TF-IDF, cross-encoder, LLM, whatever) and wants to share the results. They POST a JSON batch to our API. We deduplicate, score, and route to the appropriate contribution editor.

### Design Principles

1. **Dead simple for producers.** A single JSON file POSTed to a single endpoint. No SDK needed (curl works).
2. **Producers don't need to know our internals.** They send their data in their format, and we map it to ours.
3. **Scores are preserved but normalized.** Every scoring method is different. We keep the original score and add our own normalized score.
4. **Idempotent.** Posting the same batch twice doesn't create duplicate recommendations.
5. **Status-tracked.** Producers can query the status of their batch: how many were accepted, applied, rejected.

---

## Data Model

### RecommendationRecord

The core unit — one recommendation from a producer.

```json
{
  "id": "producer:my-pipeline:batch-3:item-42",
  "article": {
    "title": "Climate change",
    "url": "https://en.wikipedia.org/wiki/Climate_change"
  },
  "source": {
    "corpus": "mit-ocw",
    "id": "12.340",
    "title": "Global Warming Science",
    "url": "https://ocw.mit.edu/courses/12-340-global-warming-science/",
    "resource": {
      "title": "Global Warming Science, Lecture 13",
      "url": "https://ocw.mit.edu/courses/12-340-global-warming-science/resources/lecture-13/",
      "type": "pdf"
    }
  },
  "match": {
    "score": 0.946,
    "scoring_method": "cross-encoder/zerank-2",
    "explanation": "TF-IDF candidate → zerank-2 reranker, top 10 per article"
  },
  "contribution": {
    "suggested_level": "L2",
    "description": "Lecture 13 covers the carbon cycle with detailed quantitative models."
  },
  "provenance": {
    "producer": "climate-ml-lab",
    "pipeline": "tfidf-zerank-v2",
    "generated_at": "2026-06-15T10:30:00Z",
    "contact": "researcher@example.edu"
  }
}
```

### Field Reference

#### `id` (string, required)

Unique identifier for this recommendation. Should be globally unique — we recommend the format:
`{producer}:{pipeline}:{batch_id}:{item_id}`

Used for idempotency: if we've already processed this ID, we skip it.

#### `article` (object, required)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `title` | string | ✅ | Wikipedia article title (exact, case-sensitive) |
| `url` | string | ❌ | Full Wikipedia URL (used for verification) |

Either `title` or `url` must be provided. If both, `title` is authoritative.

#### `source` (object, required)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `corpus` | string | ✅ | Corpus identifier: `mit-ocw`, `arxiv`, `jstor`, `pubmed`, etc. |
| `id` | string | ✅ | Unique ID within the corpus (e.g., course ID, DOI, arXiv ID) |
| `title` | string | ✅ | Human-readable title of the source |
| `url` | string | ✅ | Canonical URL for the source |
| `resource` | object | ❌ | Specific resource within the source (lecture, chapter, figure) |
| `resource.title` | string | - | Title of the specific resource |
| `resource.url` | string | - | Direct URL to the resource |
| `resource.type` | string | - | `pdf`, `video`, `lecture_notes`, `dataset`, `image`, `other` |

#### `match` (object, required)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `score` | float | ✅ | Raw match score (producer's own scale) |
| `scoring_method` | string | ✅ | Method identifier: `cross-encoder/zerank-2`, `tfidf/cosine`, `llm/gpt-4`, etc. |
| `explanation` | string | ❌ | Human-readable description of the matching pipeline |

Scores are preserved verbatim. The consumer may normalize them for cross-producer comparison, but the original score is never discarded.

#### `contribution` (object, optional)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `suggested_level` | string | ❌ | Suggested contribution level: `L1`, `L2`, `L3` |
| `description` | string | ❌ | One-sentence description of why this source is relevant |
| `edit_summary` | string | ❌ | Suggested Wikipedia edit summary |
| `custom_wikitext` | string | ❌ | Pre-formatted wikitext (if producer wants full control) |

If `contribution` is omitted, the consumer generates L1 Refideas wikitext by default.

#### `provenance` (object, required)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `producer` | string | ✅ | Identifier for the producing entity (org, lab, project) |
| `pipeline` | string | ✅ | Pipeline version identifier |
| `generated_at` | string | ✅ | ISO 8601 timestamp of generation |
| `contact` | string | ❌ | Email or contact URL for questions |

---

## REST API

### Base URL

```
https://wiki-mit.toolforge.org/api/v1
```

(Currently local: `http://localhost:8765/api/v1`)

### `POST /recommendations`

Submit a batch of recommendations.

**Request:**
```json
{
  "batch": {
    "id": "climate-ml-lab:batch-2026-06-15",
    "description": "Climate/Environment matches from cross-encoder pipeline, June 2026",
    "producer": "climate-ml-lab",
    "generated_at": "2026-06-15T10:30:00Z"
  },
  "recommendations": [
    { "... RecommendationRecord ..." },
    { "... RecommendationRecord ..." }
  ]
}
```

**Response (201):**
```json
{
  "batch_id": "climate-ml-lab:batch-2026-06-15",
  "status": "accepted",
  "stats": {
    "submitted": 185,
    "accepted": 178,
    "duplicates_skipped": 5,
    "invalid_skipped": 2
  },
  "invalid": [
    {
      "id": "climate-ml-lab:batch-2026-06-15:item-14",
      "error": "article.title is empty"
    }
  ],
  "processed_at": "2026-06-22T15:00:00Z"
}
```

**Response (409 — duplicate batch):**
```json
{
  "batch_id": "climate-ml-lab:batch-2026-06-15",
  "status": "duplicate",
  "message": "Batch already processed on 2026-06-15T10:35:00Z. 178 recommendations accepted."
}
```

### `GET /recommendations`

List recommendations with optional filters.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `producer` | string | Filter by producer ID |
| `corpus` | string | Filter by source corpus |
| `article` | string | Filter by Wikipedia article title |
| `level` | string | Filter by contribution level (L1, L2, L3) |
| `status` | string | `pending`, `accepted`, `applied`, `rejected` |
| `min_score` | float | Minimum raw score |
| `limit` | int | Max results (default 50, max 500) |
| `offset` | int | Pagination offset |

**Response (200):**
```json
{
  "total": 178,
  "limit": 50,
  "offset": 0,
  "recommendations": [
    { "... RecommendationRecord with consumer metadata ..." }
  ]
}
```

### `GET /recommendations/{id}`

Get a single recommendation by ID.

**Response (200):**
```json
{
  "recommendation": { "... RecommendationRecord with full status ..." },
  "status_history": [
    { "status": "pending", "at": "2026-06-15T10:35:00Z" },
    { "status": "applied", "at": "2026-06-16T14:22:00Z", "revision_id": 123456789 }
  ]
}
```

### `GET /batches`

List submitted batches.

| Parameter | Type | Description |
|-----------|------|-------------|
| `producer` | string | Filter by producer |
| `limit` | int | Max results |

**Response (200):**
```json
{
  "batches": [
    {
      "id": "climate-ml-lab:batch-2026-06-15",
      "producer": "climate-ml-lab",
      "submitted_at": "2026-06-15T10:30:00Z",
      "stats": { "submitted": 185, "accepted": 178, "applied": 42 }
    }
  ]
}
```

### `GET /health`

Health check.

**Response (200):**
```json
{
  "status": "ok",
  "recommendations_total": 178,
  "recommendations_pending": 136,
  "producers": ["climate-ml-lab"],
  "version": "1.0.0"
}
```

---

## Authentication

### Phase 1: Token-based (simple)

Producers authenticate with a pre-shared API token:

```bash
curl -X POST https://wiki-mit.toolforge.org/api/v1/recommendations \
  -H "Authorization: Bearer $WIKI_MIT_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d @batch.json
```

Tokens are issued per producer and stored in environment variables on the server. This is sufficient for a small number of trusted producers.

### Phase 2: API key management (scalable)

A simple management endpoint for producers to register and get tokens:

```
POST /api/v1/producers/register
  { "name": "climate-ml-lab", "contact": "researcher@example.edu" }
  → { "producer_id": "climate-ml-lab", "api_token": "wm_abc123..." }
```

---

## Client Libraries

### Python (minimal)

```python
import requests

class WikiMITClient:
    def __init__(self, base_url, api_token):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_token}",
            "User-Agent": "MyPipeline/1.0 (contact@example.edu)"
        })

    def submit_batch(self, batch_id, recommendations, description=""):
        resp = self.session.post(
            f"{self.base_url}/api/v1/recommendations",
            json={
                "batch": {
                    "id": batch_id,
                    "description": description,
                    "producer": self.producer_id,
                    "generated_at": datetime.utcnow().isoformat() + "Z"
                },
                "recommendations": recommendations
            }
        )
        resp.raise_for_status()
        return resp.json()

# Usage:
client = WikiMITClient("https://wiki-mit.toolforge.org", token)
result = client.submit_batch(
    "my-lab:batch-001",
    [
        {
            "id": "my-lab:pipeline-v1:batch-001:item-1",
            "article": {"title": "Climate change"},
            "source": {
                "corpus": "mit-ocw",
                "id": "12.340",
                "title": "Global Warming Science",
                "url": "https://ocw.mit.edu/courses/12-340-.../"
            },
            "match": {"score": 0.946, "scoring_method": "cross-encoder/zerank-2"},
            "provenance": {
                "producer": "my-lab",
                "pipeline": "pipeline-v1",
                "generated_at": "2026-06-22T15:00:00Z"
            }
        }
    ]
)
print(f"Accepted: {result['stats']['accepted']}")
```

### curl (zero-dependency)

```bash
curl -X POST https://wiki-mit.toolforge.org/api/v1/recommendations \
  -H "Authorization: Bearer $WIKI_MIT_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "batch": {
      "id": "my-lab:batch-001",
      "producer": "my-lab",
      "generated_at": "2026-06-22T15:00:00Z"
    },
    "recommendations": [
      {
        "id": "my-lab:batch-001:item-1",
        "article": {"title": "Climate change"},
        "source": {
          "corpus": "mit-ocw",
          "id": "12.340",
          "title": "Global Warming Science",
          "url": "https://ocw.mit.edu/courses/12-340-.../"
        },
        "match": {"score": 0.946, "scoring_method": "cross-encoder/zerank-2"},
        "provenance": {
          "producer": "my-lab",
          "pipeline": "pipeline-v1",
          "generated_at": "2026-06-22T15:00:00Z"
        }
      }
    ]
  }'
```

---

## Consumer Pipeline (What Wiki MIT Does With Submissions)

When a batch is received, the consumer runs this pipeline:

```
POST /recommendations
  │
  ▼
1. Validate
   - All required fields present?
   - article.title is non-empty?
   - source.url is a valid URL?
   - Batch ID not already processed?
  │
  ▼
2. Deduplicate
   - Check recommendation ID against processed IDs
   - Check (article.title, source.url) against existing recommendations
  │
  ▼
3. Normalize
   - Resolve source.corpus + source.id to internal CorpusItem
   - Normalize article.title (redirect resolution, underscore normalization)
   - Add consumer metadata (quality, views, WikiProject from PageAssessments)
  │
  ▼
4. Score
   - Preserve producer's raw score
   - Optionally add consumer-side normalized score for cross-producer ranking
  │
  ▼
5. Store
   - Save to database (SQLite on NFS, or PostgreSQL on Toolforge)
   - Status: 'pending'
  │
  ▼
6. Route
   - If contribution.suggested_level is set → use it
   - Otherwise → default to L1 (talk page refideas)
   - Queue for editor review or automated application
  │
  ▼
7. Notify (future)
   - Webhook callback to producer with batch status
   - Email notification for applied/rejected recommendations
```

---

## Migrating from the Current PDF Pipeline

The current `review-collaborator-matches.py` hardcodes 185 tuples:

```python
("Climate change", 0.946, "Global Warming Science", "Global Warming Science, Lecture 13")
```

### Step 1: Export existing data to REP format

Write a one-time migration script that converts the hardcoded tuples:

```python
for article, score, course, lecture in COLLAB_MATCHES:
    record = {
        "id": f"climate-ml-lab:zerank-v1:batch-001:{slugify(article)}-{slugify(lecture)}",
        "article": {"title": article},
        "source": {
            "corpus": "mit-ocw",
            "id": resolve_course_id(course),
            "title": course,
            "url": resolve_course_url(course),
            "resource": {"title": lecture, "url": resolve_lecture_url(lecture), "type": "pdf"}
        },
        "match": {"score": score, "scoring_method": "cross-encoder/zerank-2"},
        "provenance": {
            "producer": "climate-ml-lab",
            "pipeline": "tfidf-zerank-v1",
            "generated_at": "2026-05-01T00:00:00Z",
            "contact": "..."
        }
    }
    # POST to API or write to JSON file
```

### Step 2: Deprecate the PDF script

Once the API is operational, `review-collaborator-matches.py` becomes:
1. A migration script (convert old PDF data to REP JSON)
2. A consumer-side reviewer (fetch pending recommendations from API, review, apply)

---

## Implementation Path

### Sprint 1: Schema + Validation (1 session)

- Define the JSON Schema (JSON Schema or TypeScript types)
- Implement `POST /api/v1/recommendations` in `toolforge/server.mjs`
- Validation: required fields, URL format, batch idempotency
- Storage: JSON files on NFS or in-memory for prototype

### Sprint 2: Storage + Query (1 session)

- SQLite database on Toolforge NFS
- `GET /recommendations`, `GET /recommendations/{id}`, `GET /batches`
- Filtering by producer, corpus, article, status, score

### Sprint 3: Auth + Migration (1 session)

- Token-based authentication
- Migration script: convert existing COLLAB_MATCHES to REP format
- POST the 185 existing matches to the API

### Sprint 4: Consumer Pipeline (1-2 sessions)

- Normalization: resolve source IDs to internal CorpusItems
- Scoring: preserve producer score + add consumer normalized score
- Routing: queue for L1/L2 editors
- Dashboard: show REP-submitted recommendations alongside OCW matches

---

## Reference

| Document | Covers |
|----------|--------|
| `docs/CONTRIBUTION-PROTOCOL.md` | Internal ContributionRecord schema (what REP feeds into) |
| `docs/CONTRIBUTION-LADDER.md` | Multi-corpus framework (REP's `source.corpus` field) |
| `docs/CONTRIBUTION-UI.md` | Interface options for the review queue |
| `toolforge/DESIGN.md` | Server architecture (where REP endpoints live) |
| `scripts/review-collaborator-matches.py` | Current ad-hoc PDF pipeline (to be replaced by REP) |
