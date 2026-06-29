# Zerank-2 Reranker Integration

> **Status:** Design phase. Adds zeroentropy/zerank-2 cross-encoder reranking to the match pipeline, improving match quality beyond keyword overlap.
> **Model:** `zeroentropy/zerank-2` — 4B Qwen3-based cross-encoder, CC-BY-NC-4.0, SOTA on all public reranker benchmarks.
> **Reference:** [HuggingFace](https://huggingface.co/zeroentropy/zerank-2-reranker), [ZeroEntropy Docs](https://docs.zeroentropy.dev)

---

## What it does

The current match pipeline (`ad-hoc-match.py`) scores Wikipedia articles based on:
- Title keyword overlap with course title
- Maintenance templates
- Pageviews
- Pre-computed corpus matches

This is fast and works well for exact matches ("Introduction to Algorithms" ↔ "Algorithm"), but misses deeper semantic connections ("Global Warming Science" ↔ "Carbon cycle" — the course title doesn't mention carbon, but the course content covers it deeply).

The collaborator's pipeline proved this works: their TF-IDF+zerank-2 pipeline found 185 high-quality matches (≥0.79 threshold) across 62 articles in the Environment/Climate/Energy domain — most of which our keyword-based pipeline would miss.

**Zerank-2 adds a semantic reranking layer:** after our fast keyword pipeline finds candidate articles, zerank-2 scores each candidate by reading the course description and article text *together* as a cross-encoder, producing a much more accurate relevance score.

### Where it fits in the pipeline

```
Current pipeline:
  Course description
    → MatchProvider (keyword search, corpus lookup)
    → Filter (broad-field, junk pages, named entities, no-overlap)
    → Score (title overlap, templates, pageviews)
    → Rank
    → Display

With zerank-2:
  Course description
    → MatchProvider (keyword search, corpus lookup)     ← fast, wide net
    → Filter (broad-field, junk pages, named entities, no-overlap)
    → Enrich (fetch article lead extracts via API)      ← new step
    → Zerank-2 rerank (cross-encoder on top 20)         ← new step
    → Combine scores (keyword × zerank-2)               ← new step
    → Rank
    → Display
```

The keyword pipeline casts a wide net (top 20-50 candidates), then zerank-2 precisely reranks them. This is the standard retrieve-and-rerank architecture.

---

## How to use zerank-2

### Option A: Local model via Sentence Transformers

```bash
pip install sentence_transformers
```

```python
from sentence_transformers import CrossEncoder
import torch

# Load once (first call downloads ~8GB model)
model = CrossEncoder(
    "zeroentropy/zerank-2",
    device="cuda" if torch.cuda.is_available() else "cpu"
)

# Score pairs: each (query, document) pair gets one score
pairs = [
    ("Global Warming Science: climate physics, carbon cycle, greenhouse gases",
     "Carbon cycle — The carbon cycle is the biogeochemical cycle by which carbon is exchanged..."),
    ("Global Warming Science: climate physics, carbon cycle, greenhouse gases",
     "Algorithm — In mathematics and computer science, an algorithm is a finite sequence..."),
]

scores = model.predict(pairs, convert_to_tensor=True)
# → tensor([5.41, -4.50])  — raw "Yes" logits

# Convert to 0-1 probabilities
probs = (scores / 5.0).sigmoid()
# → tensor([0.746, 0.289])

# Or use model.rank() for a single query with multiple docs
rankings = model.rank(
    "Global Warming Science: climate physics, carbon cycle, greenhouse gases",
    [
        "Carbon cycle — The carbon cycle is...",
        "Algorithm — In mathematics and computer science...",
        "Climate change — Present-day climate change includes...",
    ]
)
# → sorted by score descending
```

### Option B: ZeroEntropy API

```bash
pip install zeroentropy
```

```python
from zeroentropy import ZeroEntropy

zclient = ZeroEntropy(api_key="ze_...")

response = zclient.models.rerank(
    model="zerank-2",
    query="Global Warming Science: climate physics, carbon cycle, greenhouse gases",
    documents=[
        "Carbon cycle — The carbon cycle is the biogeochemical cycle...",
        "Algorithm — In mathematics and computer science...",
    ],
)

for doc in response.results:
    print(f"Score: {doc.score:.3f} — {doc.document[:80]}...")
```

### Which option for our tool?

| Factor | Local (Sentence Transformers) | API (ZeroEntropy) |
|--------|------------------------------|-------------------|
| **Setup** | `pip install sentence_transformers` + 8GB download | `pip install zeroentropy` + API key |
| **Speed (CPU)** | ~2-5s per pair | ~200-500ms per batch |
| **Speed (GPU)** | ~50-200ms per batch | ~200-500ms per batch |
| **Cost** | Free | Usage-based (pricing TBD) |
| **Offline use** | ✅ | ❌ |
| **Rate limits** | None | API tier limits |
| **Production scale** | Needs GPU server | Managed, auto-scales |

**Recommendation:** Local model for development and single-course matching (20 candidates × 2s = 40s; acceptable for interactive use). ZeroEntropy API for batch processing or when GPU isn't available.

---

## Integration into ad-hoc-match.py

### New provider: `ZerankRerankProvider`

Rather than modifying the existing providers, add zerank-2 as a standalone provider that reranks candidates from other providers. This keeps the architecture clean — each provider does one thing.

```python
class ZerankRerankProvider(MatchProvider):
    """Rerank Wikipedia article candidates using zerank-2 cross-encoder.

    This provider does NOT find new candidates — it takes the output of
    other providers and reranks them by semantic relevance.

    Usage:
        --provider "corpus,wikipedia,zerank"
    """
    
    def __init__(self, model="zeroentropy/zerank-2", top_k=20, device=None):
        self.model_name = model
        self.top_k = top_k
        self._model = None
        self._device = device or ("cuda" if torch.cuda.is_available() else "cpu")

    @property
    def name(self) -> str:
        return "zerank"

    @property
    def model(self):
        if self._model is None:
            from sentence_transformers import CrossEncoder
            self._model = CrossEncoder(self.model_name, device=self._device)
        return self._model

    def find_candidates(self, course: dict) -> list[dict]:
        # This provider doesn't find new candidates — it's called separately
        # as a post-processing step in the pipeline
        return []

    def rerank(self, course: dict, candidates: list[dict]) -> list[dict]:
        """Rerank existing candidates by semantic relevance.

        Args:
            course: Course dict with title, description, topics
            candidates: List of candidate article dicts (must have 'title' and
                       optionally 'extract' — if no extract, fetch it)

        Returns:
            Same candidates with added 'zerank_score' field, re-sorted
        """
        # Build query from course metadata
        query = f"{course.get('title', '')}: {course.get('description', '')}"
        topics = course.get('topics', [])
        if topics:
            query += f" Topics: {', '.join(topics[:5])}"

        # Build document texts from article extracts
        doc_texts = []
        for c in candidates:
            text = c.get('extract', '')
            if not text:
                # Fetch lead extract if not provided
                text = self._fetch_extract(c['title'])
                c['extract'] = text

            # Combine title + lead for better context
            doc_texts.append(f"{c['title']} — {text[:500]}")

        # Score all pairs
        pairs = [(query, doc) for doc in doc_texts]
        scores = self.model.predict(pairs, convert_to_tensor=True)
        probs = (scores / 5.0).sigmoid()

        # Attach scores to candidates
        for i, candidate in enumerate(candidates):
            candidate['zerank_score'] = round(float(probs[i]), 4)
            candidate['zerank_raw'] = round(float(scores[i]), 2)

        # Re-sort by zerank score descending
        candidates.sort(key=lambda c: c.get('zerank_score', 0), reverse=True)

        return candidates

    def _fetch_extract(self, title: str) -> str:
        """Fetch the lead section extract of a Wikipedia article."""
        import requests
        resp = requests.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "prop": "extracts",
                "exintro": 1,
                "explaintext": 1,
                "titles": title,
                "format": "json",
            },
            headers={"User-Agent": "Wiki MIT/1.0 (https://meta.wikimedia.org/wiki/Wiki_MIT; your-email@example.com)"},
            timeout=10,
        )
        pages = resp.json().get("query", {}).get("pages", {})
        for page in pages.values():
            return page.get("extract", "")
        return ""
```

### Modified pipeline: two-stage scoring

```python
def run_pipeline_with_rerank(course, provider_names, top_n=10, use_zerank=True):
    """Two-stage pipeline: fast keyword search → zerank-2 rerank."""

    # Stage 1: Fast keyword-based candidate generation
    candidates = run_pipeline(course, provider_names, top_n=30)  # wider net

    if not use_zerank or len(candidates) < 2:
        return candidates[:top_n]

    # Stage 2: Semantic reranking with zerank-2
    reranker = ZerankRerankProvider()
    candidates = reranker.rerank(course, candidates)

    # Combine scores: weighted blend of keyword score + zerank score
    for c in candidates:
        keyword_score = c.get('score', 0) / 100.0  # normalize to 0-1
        zerank_score = c.get('zerank_score', 0)
        # 40% keyword, 60% zerank (tuneable)
        c['combined_score'] = round(0.4 * keyword_score + 0.6 * zerank_score, 4)

    # Re-sort by combined score
    candidates.sort(key=lambda c: c.get('combined_score', 0), reverse=True)

    return candidates[:top_n]
```

### CLI usage

```bash
# Current (keyword only):
python3 scripts/ad-hoc-match.py "12.340" --top 5

# With zerank-2 reranking:
python3 scripts/ad-hoc-match.py "12.340" --top 5 --rerank zerank

# With custom score blend:
python3 scripts/ad-hoc-match.py "12.340" --top 5 --rerank zerank --rerank-weight 0.7

# Use API instead of local model:
python3 scripts/ad-hoc-match.py "12.340" --top 5 --rerank zerank --zerank-api-key $ZE_KEY
```

---

## Score blending strategy

The key question: how to combine the keyword-based score (fast, structural) with the zerank-2 score (slow, semantic)?

### Option A: Weighted linear blend (default)

```
combined = α × keyword_score_norm + (1-α) × zerank_score
```

Where `α` is tunable (default 0.4 — favoring zerank):
- `α = 0.0`: pure zerank (ignores keyword signal entirely)
- `α = 0.4`: slight keyword boost (default — keeps structural signals)
- `α = 1.0`: pure keyword (zerank disabled)

### Option B: Zerank as a gate

Only use zerank when keyword scores are close (within 15 points). If one candidate is far ahead on keyword overlap, trust it. If scores are clustered, let zerank break the tie.

### Option C: Zerank as a boost

Keep keyword ranking, but boost candidates that zerank strongly confirms and demote those it strongly rejects:

```python
if zerank_score > 0.8:
    keyword_score += 15  # strong semantic match — boost
elif zerank_score < 0.3:
    keyword_score -= 10  # semantic mismatch — demote
```

**Recommendation:** Start with Option A (weighted blend, α=0.4) as the default. It's simple, tunable, and the weighting can be calibrated against the collaborator's 185 known-good matches.

---

## Performance estimates

| Scenario | Candidates | Keyword time | Zerank time (CPU) | Zerank time (GPU) | Total |
|----------|-----------|-------------|-------------------|-------------------|-------|
| Single course match | 20 | ~2s | ~40s | ~3s | 5-42s |
| Batch (10 courses) | 200 | ~15s | ~400s | ~20s | 35-415s |
| Full corpus (2,577 courses) | 50,000 | ~30min | ~28hr | ~1.5hr | 2-29hr |

**For interactive use** (single course match): CPU is borderline acceptable (40s wait). GPU makes it seamless (3s). The ZeroEntropy API would land in between (~5s per batch of 20).

**For batch processing**: GPU strongly recommended. On Toolforge, this would require a GPU-backed Kubernetes pod or the ZeroEntropy API.

---

## Evaluation: calibrating against known-good matches

The collaborator already provided 185 high-quality zerank-2 matches. We can use these to:

1. **Validate our integration:** Run our zerank-2 pipeline on the same 185 pairs and verify we get matching scores
2. **Tune the blend weight:** Optimize α by how well combined scores rank the known-good matches
3. **Set a score threshold:** Determine the minimum zerank score that correlates with human-acceptable matches

```python
def evaluate_against_ground_truth(reranker, course, ground_truth_pairs):
    """Score our zerank-2 output against collaborator's known scores."""
    results = []
    for article, expected_score, course_name, lecture in ground_truth_pairs:
        # Resolve course to metadata
        fm = resolve_course(course_name)
        # Get article extract
        extract = fetch_extract(article)
        # Score
        query = f"{fm['title']}: {fm.get('description', '')}"
        doc = f"{article} — {extract[:500]}"
        score = reranker.model.predict([(query, doc)])[0]
        prob = float((score / 5.0).sigmoid())

        results.append({
            'article': article,
            'expected': expected_score,
            'ours': round(prob, 4),
            'delta': round(prob - expected_score, 4),
        })

    # Metrics
    mae = sum(abs(r['delta']) for r in results) / len(results)
    correlation = pearsonr([r['expected'] for r in results],
                           [r['ours'] for r in results])

    return results, {'mae': mae, 'correlation': correlation}
```

---

## Implementation path

### Phase 1: Install + verify (30 min)

```bash
pip install sentence_transformers torch
python3 -c "
from sentence_transformers import CrossEncoder
model = CrossEncoder('zeroentropy/zerank-2')
print(model.predict([('test query', 'test document')]))
"
```

### Phase 2: Add ZerankRerankProvider to ad-hoc-match.py (1 session)

- Implement the provider class
- Add `--rerank zerank` CLI flag
- Add extract fetching (batch API call for lead sections)
- Add score blending logic

### Phase 3: Evaluate against collaborator data (1 session)

- Run the 185 known-good pairs through our pipeline
- Compute MAE and correlation
- Tune blend weight α
- Set score threshold for "high confidence" matches

### Phase 4: Integrate into Workbench UI (1 session)

- Show zerank score alongside keyword score in match cards
- Add "Rerank with zerank-2" toggle in the UI
- Color-code matches by zerank confidence

---

## Reference

| Document | Covers |
|----------|--------|
| `docs/AD-HOC-MATCH.md` | Match provider architecture (where ZerankRerankProvider plugs in) |
| `docs/HOWTO-NEW-PROVIDER.md` | How to add a provider |
| `docs/RECOMMENDATION-EXCHANGE-PROTOCOL.md` | Standard API for receiving zerank-scored matches from collaborators |
| `scripts/review-collaborator-matches.py` | Current collaborator pipeline (185 zerank-scored pairs) |
| [zerank-2 on HuggingFace](https://huggingface.co/zeroentropy/zerank-2-reranker) | Model card, usage, license |
| [ZeroEntropy rerank docs](https://docs.zeroentropy.dev/examples/rerank) | API-based reranking |
