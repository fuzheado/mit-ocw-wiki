# Deep Asset Inspection for Zerank-2 Reranking

> **Status:** Design phase. Extends `docs/ZERANK-PIPELINE.md` to use actual lecture/reading text instead of course descriptions, matching what the collaborator's pipeline did with full PDF content.
> **Depends on:** `docs/ZERANK-INTEGRATION.md`, `docs/ZERANK-PIPELINE.md`

---

## What "deeper inspection" means

The shallow pipeline uses course-level metadata as the zerank-2 query:

```
Query: "Global Warming Science: Scientific foundation of anthropogenic climate change..."
       ↑ ~200 words from course description YAML

Document: "Climate model — Climate models are systems of differential equations..."
          ↑ ~500 words from Wikipedia lead extract
```

Deep inspection replaces the course description with actual lecture text:

```
Query: "Lecture 13: The Carbon Cycle. 3.1 Overview. The global carbon cycle
        consists of reservoirs (atmosphere, ocean, terrestrial biosphere,
        lithosphere) connected by fluxes... [continues for 2,000+ words]"
       ↑ full lecture PDF text extracted with pymupdf

Document: "Carbon cycle — The carbon cycle is the biogeochemical cycle..."
          ↑ Wikipedia lead extract
```

This is what the collaborator did. Their 0.946 score for "Carbon cycle" ← "Global Warming Science, Lecture 13" came from comparing the actual lecture text against the Wikipedia article — a semantic match our course-level description alone might score at 0.6-0.7.

---

## The asset pyramid

OCW courses contain multiple asset types with different content depth:

```
                        Highest signal ─┐
      Lecture videos    Full spoken       │  5,000-15,000 words
      (transcripts)     content           │
                                     ─────┤
   Lecture PDFs         Slides + notes    │  1,000-5,000 words
   (extracted)          + equations       │
                                     ─────┤
  Reading lists         Textbook chapters, │  500-2,000 words
                        paper references   │
                                     ─────┤
  Course description    Current pipeline   │  200-500 words
  (YAML frontmatter)    Already working   ─┘
```

For the collaborator's 41 environment courses:

| Asset type | Total count | Per course (avg) | Total extracted text |
|------------|------------|-------------------|---------------------|
| Lecture PDFs | 779 | 19 | ~1.5M words |
| Video transcripts | ~120 | ~3 | ~600K words |
| Reading lists | 41 | 1 | ~20K words |

For all 2,577 courses: ~50,000 PDFs, ~7,700 videos.

---

## Pipeline with deep inspection

```
wiki/courses/*.md ──► Extract lecture PDF URLs
     │
     ▼
Download PDFs → Extract text (pymupdf/fitz)
     │
     ▼
Split into chunks (500-word windows with 50-word overlap)
     │
     ▼
Fast triage: keyword overlap between chunk and candidate article titles
→ keep only top-N chunks per article (N=3)
     │
     ▼
Zerank-2: score each selected (chunk, article_lead) pair
     │
     ▼
Aggregate: best chunk score → lecture score → course score
     │
     ▼
Filter + REP output
```

### The triage step is what makes this practical

Without triage, every lecture chunk is compared to every candidate article:

| Scope | Lectures | × Candidates | = Zerank-2 calls | Time (CPU) |
|-------|----------|-------------|-----------------|------------|
| 1 course (19 lectures) | 19 | 30 | 570 | ~19 min |
| 41 courses (env domain) | 779 | 30 | 23,370 | ~13 hours |
| 2,577 courses | ~50,000 | 30 | 1,500,000 | ~35 days |

**With triage (keyword pre-filter, keep top 3 chunks per article):**

| Scope | Lectures | × Filtered | = Zerank-2 calls | Time (CPU) | Time (GPU) |
|-------|----------|-----------|-----------------|------------|------------|
| 1 course | 19 | 3/chunk → ~90 | 90 | ~3 min | ~15 sec |
| 41 courses | 779 | ~90 | 3,895 | ~2 hr | ~10 min |
| 2,577 courses | ~50,000 | ~250,000 | 250,000 | ~6 days | ~12 hr |

---

## Reference implementation highlights

### PDF text extraction

```python
import fitz  # pymupdf

def extract_pdf_text(url: str) -> str:
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    doc = fitz.open(stream=resp.content, filetype="pdf")
    text = "\n\n".join(page.get_text() for page in doc if page.get_text().strip())
    doc.close()
    return text
```

### Chunking with overlap

```python
def chunk_text(text: str, max_words: int = 500, overlap: int = 50) -> list[str]:
    words = text.split()
    chunks = []
    start = 0
    while start < len(words):
        chunks.append(" ".join(words[start:start + max_words]))
        start += max_words - overlap
    return chunks
```

### Triage: keyword pre-filter

```python
# Build keyword index from all lecture chunks
for chunk in all_chunks:
    keywords = set(w for w, c in Counter(chunk_words).most_common(30))

# For each candidate article, find most relevant chunks by keyword overlap
for candidate in candidates:
    article_words = set(title_words + extract_words)
    chunk_scores = [(len(ch.keywords & article_words), ch) for ch in all_chunks]
    top_chunks = sorted(chunk_scores, key=lambda x: -x[0])[:3]  # keep top 3
```

### Aggregate: best chunk wins

```python
# After zerank-2 scores all (chunk, article) pairs:
candidate_best = {}
for i, meta in enumerate(pair_metadata):
    score = float(probs[i])
    c_idx = meta["candidate_index"]
    if c_idx not in candidate_best or score > candidate_best[c_idx]["score"]:
        candidate_best[c_idx] = {
            "score": score,
            "lecture_title": meta["lecture_title"],
            "chunk_index": meta["chunk_index"],
        }
```

---

## Deep vs. shallow: when to use which

| Factor | Shallow (course description) | Deep (lecture text) |
|--------|------------------------------|---------------------|
| **Query length** | ~200 words | ~2,000-10,000 words |
| **Signal quality** | General topic only | Every subtopic the lecture covers |
| **Zerank-2 calls per course** | ~30 | ~90 (3 chunks × 30 candidates) |
| **Time per course** | ~3-40 seconds | ~3-15 minutes |
| **Best for** | Interactive Workbench, fast exploration | Batch recommendation generation |
| **Example match it catches** | "Algorithm" ← "6.006" (broad) | "Carbon cycle" ← "12.340 Lec 13" (specific) |

**Recommendation:** Shallow for the UI. Deep for batch generation — this is where the collaborator's quality came from.

---

## Implementation path

### Phase 1: Extract lecture text cache (1-2 sessions)

- `scripts/extract-lecture-text.py` — download PDFs, extract text, cache in `.wiki_cache/asset-text/`
- Parallel extraction with `ThreadPoolExecutor` (8 workers)
- Environment domain (41 courses, ~779 PDFs): ~30 minutes
- Output: one `.txt` file per lecture, keyed by course ID + URL hash

### Phase 2: Add `--deep` flag to zerank pipeline (1-2 sessions)

- When enabled: read cached lecture text instead of course description
- Triage: keyword overlap pre-filter (keep top 3 chunks per candidate)
- Chunk-level zerank-2 scoring
- Aggregate: best chunk → best lecture → course score

### Phase 3: Validate against collaborator ground truth (1 session)

- Run deep pipeline on the same 41 environment courses
- Compare with the 185 known-good matches
- Measure recall/precision, tune chunk size and threshold

### Phase 4: Scale to full corpus (batch, GPU)

- Run deep pipeline on all 2,577 courses using ZeroEntropy API
- Generate comprehensive REP-format recommendations

---

## Reference

| Document | Covers |
|----------|--------|
| `docs/ZERANK-INTEGRATION.md` | zerank-2 model details, usage, integration pattern |
| `docs/ZERANK-PIPELINE.md` | Shallow pipeline (course description → zerank-2 → REP) |
| `docs/RECOMMENDATION-EXCHANGE-PROTOCOL.md` | REP format for output |
| `scripts/scan-batch-parallel.py` | Existing parallel asset scanner (pattern to follow) |
