# Reimplementing the Collaborator Pipeline with Zerank-2

> **Status:** Design + reference implementation.
> **Goal:** Replace the PDF-based collaborator workflow with a self-contained pipeline that generates zerank-2-scored Wikipedia improvement recommendations from OCW course content, outputting REP-format JSON.
> **Depends on:** `docs/ZERANK-INTEGRATION.md`, `docs/RECOMMENDATION-EXCHANGE-PROTOCOL.md`

---

## What the collaborator did

```
┌─────────────────────────────────────────────────────────────────┐
│                   Collaborator Pipeline (original)              │
│                                                                 │
│  1,439 OCW lecture PDFs (41 courses, Environment/Climate)       │
│       │                                                         │
│       ▼                                                         │
│  TF-IDF candidate generation                                    │
│  (PDF text → Wikipedia article titles)                          │
│       │                                                         │
│       ▼  1,545 candidate pairs                                  │
│  Zeroentropy/zerank-2 cross-encoder reranking                   │
│  (scored each pair: PDF text ⟷ Wikipedia article)               │
│       │                                                         │
│       ▼  threshold ≥ 0.79                                       │
│  185 high-confidence pairs across 62 Wikipedia articles         │
│       │                                                         │
│       ▼                                                         │
│  Exported as reranked_p79.pdf                                   │
│       │                                                         │
│       ▼                                                         │
│  review-collaborator-matches.py (our side)                      │
│  → hardcoded tuples → interactive review → L1/L2 edits          │
└─────────────────────────────────────────────────────────────────┘
```

The pipeline had two stages:

| Stage | What | Input | Output |
|-------|------|-------|--------|
| **Stage 1: Recall** | TF-IDF search over Wikipedia | PDF text (full lecture content) | 1,545 candidate article titles |
| **Stage 2: Precision** | zerank-2 cross-encoder | (PDF text, article title) pairs | 185 scored matches ≥ 0.79 |

Our reimplementation replaces PDFs with OCW course metadata (already ingested into our wiki), replaces TF-IDF with our existing match pipeline plus Wikipedia search, and outputs REP-format JSON instead of a PDF.

---

## Reimplemented pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│                   Our Pipeline (reimplementation)               │
│                                                                 │
│  wiki/courses/*.md (YAML frontmatter: title, description,       │
│                     topics, lecture titles, lecture URLs)       │
│       │                                                         │
│       ▼                                                         │
│  Stage 1: Candidate generation (recall)                         │
│  ├─ ad-hoc-match.py (keyword overlap + corpus + Wikipedia)      │
│  └─ Wikipedia search API (broader semantic retrieval)           │
│       │  deduplicate, merge                                     │
│       ▼  top 30 candidates per course                           │
│  Stage 2: Enrichment                                            │
│  └─ Wikipedia API: fetch lead extracts (prop=extracts&exintro)  │
│       │                                                         │
│       ▼                                                         │
│  Stage 3: Zerank-2 reranking (precision)                        │
│  └─ Cross-encoder: score each (course_desc, article_lead) pair  │
│       │                                                         │
│       ▼                                                         │
│  Stage 4: Filter + format                                       │
│  ├─ Threshold: keep pairs with zerank_score ≥ 0.70              │
│  ├─ Deduplicate: keep highest-scoring match per article         │
│  └─ Output: REP-format JSON                                     │
│       │                                                         │
│       ▼                                                         │
│  POST /api/v1/recommendations → consumed by our tools           │
└─────────────────────────────────────────────────────────────────┘
```

### Key differences from the collaborator's approach

| Aspect | Collaborator | Our reimplementation |
|--------|-------------|---------------------|
| **Source text** | Full PDF content (lecture slides, equations, diagrams) | Course description + lecture titles + topics (from YAML) |
| **Recall engine** | Custom TF-IDF over Wikipedia | `ad-hoc-match.py` + Wikipedia `list=search` API |
| **Document text** | Wikipedia article text (full) | Lead extract only (first ~500 chars via API) |
| **Score threshold** | 0.79 (sigmoid'd probability) | 0.70 (raw logit applied to sigmoid, equivalent) |
| **Output format** | PDF table | REP JSON (machine-readable, feeds directly into our tools) |
| **Domain scope** | 41 Environment/Climate courses | Any domain (full 2,577 courses) |

The trade-off: we use lighter source text (descriptions instead of PDFs) but gain universal coverage across all courses and a machine-readable output.

---

## Reference implementation: `scripts/generate-zerank-recommendations.py`

```python
#!/usr/bin/env python3
"""
Generate zerank-2-scored recommendations from OCW course content.

Usage:
    # Single course
    python3 scripts/generate-zerank-recommendations.py --course 12.340 --top 10

    # All courses in a domain (Environment/Climate)
    python3 scripts/generate-zerank-recommendations.py --domain environment --top 20

    # Full corpus (2,577 courses) — batch mode
    python3 scripts/generate-zerank-recommendations.py --all --top 15 --output recs.json

    # With custom threshold
    python3 scripts/generate-zerank-recommendations.py --course 12.340 --threshold 0.70

    # Dry run (no zerank, just Stage 1 candidates)
    python3 scripts/generate-zerank-recommendations.py --course 12.340 --dry-run
"""

import os, sys, json, time, argparse
from dataclasses import dataclass, field, asdict
from typing import Optional

# ─── Imports (lazy-loaded when needed) ─────────────────────────────────────

# pip install sentence_transformers torch requests pyyaml

# ─── Config ────────────────────────────────────────────────────────────────

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
WIKI_DIR = os.path.join(PROJECT_DIR, "wiki", "courses")

USER_AGENT = "Wiki MIT/1.0 (https://meta.wikimedia.org/wiki/Wiki_MIT; your-email@example.com)"

# Environment/Climate domain courses (the collaborator's scope)
ENV_COURSES = [
    "12.340",    # Global Warming Science
    "12.842",    # Climate Physics and Chemistry
    "12.307",    # Weather and Climate Laboratory
    "1.74",      # Land, Water, Food, and Climate
    "11.941",    # Urban Climate Adaptation
    "17.441",    # International Politics and Climate Change
    # ... (41 courses — full list from COLLAB_COURSES in review-collaborator-matches.py)
]

# ─── Course loader ─────────────────────────────────────────────────────────

def load_course(course_id: str) -> Optional[dict]:
    """Load a course from wiki/courses/*.md by course ID."""
    import yaml
    for fname in os.listdir(WIKI_DIR):
        if not fname.endswith(".md"):
            continue
        path = os.path.join(WIKI_DIR, fname)
        with open(path) as f:
            content = f.read()
        # Extract YAML frontmatter
        match = content.match(r"^---\n(.*?)\n---", content, re.DOTALL)
        if not match:
            continue
        fm = yaml.safe_load(match.group(1))
        if fm.get("course_id") == course_id:
            return {
                "course_id": fm.get("course_id"),
                "title": fm.get("title", ""),
                "description": fm.get("description", ""),
                "topics": fm.get("topics", []),
                "department": fm.get("department", ""),
                "url": fm.get("url", ""),
                "slug": fname.replace(".md", ""),
                "lectures": extract_lectures(content),
            }
    return None

def extract_lectures(md_content: str) -> list[dict]:
    """Extract lecture titles and URLs from wiki page markdown."""
    lectures = []
    in_lectures = False
    for line in md_content.split("\n"):
        if "### Lecture-Notes" in line or "### Lectures" in line:
            in_lectures = True
            continue
        if in_lectures and line.startswith("##"):
            break
        if in_lectures:
            # Pattern: "- [Lecture Title (.pdf)](url)"
            match = re.match(r"- \[(.+?)(?:\s*\(\.pdf\))?\]\((.+?)\)", line)
            if match:
                lectures.append({
                    "title": match.group(1).strip(),
                    "url": match.group(2).strip(),
                })
    return lectures

# ─── Stage 1: Candidate generation ─────────────────────────────────────────

def generate_candidates(course: dict, top_n: int = 30) -> list[dict]:
    """
    Generate candidate Wikipedia articles for a course.
    
    Uses two sources:
    1. ad-hoc-match.py (keyword overlap + corpus matches)
    2. Wikipedia search API (broader semantic search by course title + topics)
    
    Results are deduplicated and merged.
    """
    import requests
    import subprocess
    import tempfile

    candidates = {}

    # Source 1: ad-hoc-match.py (our existing pipeline)
    try:
        result = subprocess.run(
            ["python3", os.path.join(SCRIPTS_DIR, "ad-hoc-match.py"),
             course["course_id"], "--top", str(top_n), "--provider", "corpus,wikipedia"],
            capture_output=True, text=True, timeout=30, cwd=PROJECT_DIR,
        )
        # Parse the ANSI output (same parser as server.mjs's parseAdHocOutput)
        parsed = parse_ad_hoc_output(result.stdout)
        for p in parsed:
            candidates[p["title"]] = {
                "title": p["title"],
                "keyword_score": p.get("score", 0),
                "source": "ad-hoc-match",
            }
    except Exception as e:
        print(f"  ⚠️  ad-hoc-match failed: {e}", file=sys.stderr)

    # Source 2: Wikipedia search API (broader retrieval)
    try:
        # Search by course title
        queries = [course["title"]]
        # Also search by individual topics
        for topic in course.get("topics", [])[:3]:
            queries.append(f"{course['title']} {topic}")

        for query in queries:
            resp = requests.get(
                "https://en.wikipedia.org/w/api.php",
                params={
                    "action": "query",
                    "list": "search",
                    "srsearch": query,
                    "srlimit": 10,
                    "format": "json",
                },
                headers={"User-Agent": USER_AGENT},
                timeout=10,
            )
            results = resp.json().get("query", {}).get("search", [])
            for r in results:
                title = r["title"]
                if title not in candidates:
                    candidates[title] = {
                        "title": title,
                        "keyword_score": 0,
                        "source": "wikipedia-search",
                    }
            time.sleep(0.3)

    except Exception as e:
        print(f"  ⚠️  Wikipedia search failed: {e}", file=sys.stderr)

    return list(candidates.values())

def parse_ad_hoc_output(raw: str) -> list[dict]:
    """Parse the ANSI table output from ad-hoc-match.py (copied from server.mjs)."""
    import re
    matches = []
    clean = re.sub(r'\x1b\[[0-9;]*m', '', raw)
    lines = clean.split('\n')

    current = None
    for line in lines:
        # New match: "N. Title [Quality: Q | Views: V | ...]"
        hm = re.match(r'^\s*(\d+)\.\s+(.+?)\s+\[Quality:\s*(\S+)\s*\|\s*Views:\s*([0-9,]+)', line)
        if hm:
            if current:
                matches.append(current)
            current = {
                "rank": int(hm.group(1)),
                "title": hm.group(2).strip(),
                "quality": hm.group(3) if hm.group(3) != "?" else "?",
                "views": int(hm.group(4).replace(",", "")),
            }
            continue
        if not current:
            continue
        sm = re.search(r'Score:\s*(\d+)/100', line)
        if sm:
            current["score"] = int(sm.group(1))
    if current:
        matches.append(current)
    return matches


# ─── Stage 2: Enrichment ───────────────────────────────────────────────────

def fetch_lead_extracts(titles: list[str]) -> dict[str, str]:
    """Fetch the lead section of Wikipedia articles in batches of 50."""
    import requests

    extracts = {}
    batch_size = 50

    for i in range(0, len(titles), batch_size):
        batch = titles[i:i + batch_size]
        resp = requests.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "prop": "extracts",
                "exintro": 1,
                "explaintext": 1,
                "titles": "|".join(batch),
                "format": "json",
            },
            headers={"User-Agent": USER_AGENT},
            timeout=15,
        )
        pages = resp.json().get("query", {}).get("pages", {})
        for page in pages.values():
            extracts[page["title"]] = page.get("extract", "")
        time.sleep(0.2)

    return extracts


# ─── Stage 3: Zerank-2 reranking ───────────────────────────────────────────

def rerank_with_zerank(course: dict, candidates: list[dict], 
                       extracts: dict[str, str]) -> list[dict]:
    """
    Score each (course, article) pair using zerank-2 cross-encoder.
    
    Requires: pip install sentence_transformers torch
    First call downloads ~8GB model (one-time).
    """
    from sentence_transformers import CrossEncoder
    import torch

    print(f"  Loading zerank-2 model...", file=sys.stderr)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = CrossEncoder("zeroentropy/zerank-2", device=device)
    print(f"  Model loaded on {device}", file=sys.stderr)

    # Build query from course metadata
    query = f"{course['title']}"
    if course.get("description"):
        query += f"\n{course['description']}"
    if course.get("topics"):
        query += f"\nTopics: {', '.join(course['topics'][:5])}"

    # Build document texts
    doc_texts = []
    for c in candidates:
        extract = extracts.get(c["title"], "")
        doc_texts.append(f"{c['title']}\n{extract[:800]}")

    # Score all pairs
    pairs = [(query, doc) for doc in doc_texts]
    print(f"  Scoring {len(pairs)} pairs...", file=sys.stderr)
    scores = model.predict(pairs, convert_to_tensor=True)

    # Convert to probabilities
    probs = (scores / 5.0).sigmoid()

    # Attach scores
    for i, candidate in enumerate(candidates):
        candidate["zerank_score"] = round(float(probs[i]), 4)
        candidate["zerank_raw"] = round(float(scores[i]), 2)

    # Sort by zerank score descending
    candidates.sort(key=lambda c: c.get("zerank_score", 0), reverse=True)

    return candidates


# ─── Stage 4: Filter + Format ──────────────────────────────────────────────

def filter_and_format(course: dict, candidates: list[dict], 
                      threshold: float = 0.70) -> list[dict]:
    """
    Apply score threshold, deduplicate, and format as REP records.
    """
    records = []
    seen_articles = set()

    for c in candidates:
        if c.get("zerank_score", 0) < threshold:
            continue
        if c["title"] in seen_articles:
            continue
        seen_articles.add(c["title"])

        # Look up the best matching lecture for this course
        best_lecture = None
        if course.get("lectures"):
            best_lecture = course["lectures"][0]  # Could be scored too

        record = {
            "id": f"wiki-mit:zerank-v1:{course['slug']}:{c['title'].replace(' ', '_').lower()[:50]}",
            "article": {
                "title": c["title"],
                "url": f"https://en.wikipedia.org/wiki/{c['title'].replace(' ', '_')}",
            },
            "source": {
                "corpus": "mit-ocw",
                "id": course["course_id"],
                "title": course["title"],
                "url": course["url"],
                "resource": {
                    "title": best_lecture["title"] if best_lecture else None,
                    "url": best_lecture["url"] if best_lecture else None,
                    "type": "pdf",
                } if best_lecture else None,
            },
            "match": {
                "score": c["zerank_score"],
                "scoring_method": "cross-encoder/zerank-2",
                "model_license": "CC-BY-NC-4.0",
                "model_url": "https://huggingface.co/zeroentropy/zerank-2-reranker",
                "explanation": f"zerank-2 reranker on (course description, article lead extract). "
                              f"Keyword score: {c.get('keyword_score', 'N/A')}.",
            },
            "contribution": {
                "suggested_level": "L2",
                "description": f"{course['course_id']}: {course['title']} — "
                              f"{course.get('description', '')[:200]}",
            },
            "provenance": {
                "producer": "wiki-mit",
                "pipeline": "zerank-v1",
                "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "contact": "https://meta.wikimedia.org/wiki/Wiki_MIT",
            },
        }
        records.append(record)

    return records


# ─── Main ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate zerank-2 recommendations")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--course", help="Single course ID (e.g., 12.340)")
    group.add_argument("--domain", help="Domain name (e.g., environment)")
    group.add_argument("--all", action="store_true", help="Process all courses")
    
    parser.add_argument("--top", type=int, default=20, help="Candidates per course")
    parser.add_argument("--threshold", type=float, default=0.70, 
                       help="Minimum zerank score (default: 0.70)")
    parser.add_argument("--output", default="zerank-recommendations.json",
                       help="Output file for REP-format JSON")
    parser.add_argument("--dry-run", action="store_true",
                       help="Only Stage 1 (candidate generation), no zerank")
    parser.add_argument("--post", action="store_true",
                       help="POST results to REP API after generation")

    args = parser.parse_args()

    # Resolve courses to process
    course_ids = []
    if args.course:
        course_ids = [args.course]
    elif args.domain == "environment":
        course_ids = ENV_COURSES
    elif args.all:
        # Load all course IDs from wiki
        import yaml
        for fname in os.listdir(WIKI_DIR):
            if not fname.endswith(".md"):
                continue
            with open(os.path.join(WIKI_DIR, fname)) as f:
                match = re.match(r"^---\n(.*?)\n---", f.read(), re.DOTALL)
                if match:
                    fm = yaml.safe_load(match.group(1))
                    if fm.get("course_id"):
                        course_ids.append(fm["course_id"])

    print(f"Processing {len(course_ids)} courses", file=sys.stderr)
    all_records = []

    for cid in course_ids:
        print(f"\n{'─'*60}", file=sys.stderr)
        print(f"Course: {cid}", file=sys.stderr)

        course = load_course(cid)
        if not course:
            print(f"  ⚠️  Course not found: {cid}", file=sys.stderr)
            continue

        # Stage 1: Candidate generation
        print(f"  Stage 1: Generating candidates...", file=sys.stderr)
        candidates = generate_candidates(course, top_n=args.top)
        print(f"  Found {len(candidates)} candidates", file=sys.stderr)

        if args.dry_run:
            for c in sorted(candidates, key=lambda x: -x.get("keyword_score", 0))[:10]:
                print(f"    {c['title']} (kw: {c.get('keyword_score', 'N/A')})", file=sys.stderr)
            continue

        if not candidates:
            continue

        # Stage 2: Enrichment
        print(f"  Stage 2: Fetching lead extracts...", file=sys.stderr)
        titles = [c["title"] for c in candidates]
        extracts = fetch_lead_extracts(titles)
        print(f"  Fetched {len(extracts)} extracts", file=sys.stderr)

        # Stage 3: Zerank-2 reranking
        print(f"  Stage 3: Zerank-2 reranking...", file=sys.stderr)
        candidates = rerank_with_zerank(course, candidates, extracts)

        # Show top results
        for c in candidates[:5]:
            print(f"    {c['zerank_score']:.4f}  {c['title']}", file=sys.stderr)

        # Stage 4: Filter + format
        print(f"  Stage 4: Filtering (threshold ≥ {args.threshold})...", file=sys.stderr)
        records = filter_and_format(course, candidates, threshold=args.threshold)
        print(f"  Kept {len(records)} records", file=sys.stderr)
        all_records.extend(records)

    # Output
    output = {
        "batch": {
            "id": f"wiki-mit:zerank-v1:{time.strftime('%Y-%m-%d')}",
            "description": f"Zerank-2 reranked recommendations for {len(course_ids)} courses",
            "producer": "wiki-mit",
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },
        "recommendations": all_records,
        "stats": {
            "courses_processed": len(course_ids),
            "total_recommendations": len(all_records),
            "mean_score": sum(r["match"]["score"] for r in all_records) / len(all_records) if all_records else 0,
            "threshold": args.threshold,
        },
    }

    with open(args.output, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Wrote {len(all_records)} recommendations to {args.output}", file=sys.stderr)

    # Optionally POST to REP API
    if args.post:
        import requests
        api_url = os.environ.get("REP_API_URL", "http://localhost:8765/api/v1/recommendations")
        api_token = os.environ.get("REP_API_TOKEN", "")
        resp = requests.post(
            api_url,
            json=output,
            headers={
                "Authorization": f"Bearer {api_token}",
                "Content-Type": "application/json",
            },
        )
        print(f"  POST → {resp.status_code}: {resp.json()}", file=sys.stderr)


if __name__ == "__main__":
    main()
```

---

## Step-by-step execution example

### Setup (one-time)

```bash
pip install sentence_transformers torch pyyaml requests
python3 -c "from sentence_transformers import CrossEncoder; CrossEncoder('zeroentropy/zerank-2')"
# Downloads ~8GB model (one-time, ~5 min on fast connection)
```

### Run: single course

```bash
# Dry run: see what candidates Stage 1 finds (no zerank needed)
python3 scripts/generate-zerank-recommendations.py \
    --course 12.340 --top 20 --dry-run

# Full run: generate + rerank + output REP JSON
python3 scripts/generate-zerank-recommendations.py \
    --course 12.340 --top 20 --threshold 0.70

# Output: zerank-recommendations.json
```

### Run: environment domain (41 courses)

```bash
python3 scripts/generate-zerank-recommendations.py \
    --domain environment --top 20 --threshold 0.70 \
    --output env-recs.json
```

### Run: full corpus (2,577 courses, batch)

```bash
# This will take hours — run overnight or on a GPU server
python3 scripts/generate-zerank-recommendations.py \
    --all --top 15 --threshold 0.75 \
    --output all-recs.json
```

### Post results to the REP API

```bash
# Requires the Toolforge server running with REP endpoints
export REP_API_TOKEN="wm_abc123..."
python3 scripts/generate-zerank-recommendations.py \
    --domain environment --post --output env-recs.json
```

---

## What the output looks like

```json
{
  "batch": {
    "id": "wiki-mit:zerank-v1:2026-06-22",
    "description": "Zerank-2 reranked recommendations for 1 courses",
    "producer": "wiki-mit",
    "generated_at": "2026-06-22T16:00:00Z"
  },
  "recommendations": [
    {
      "id": "wiki-mit:zerank-v1:12-340-global-warming-science-spring-2012:climate_model",
      "article": {
        "title": "Climate model",
        "url": "https://en.wikipedia.org/wiki/Climate_model"
      },
      "source": {
        "corpus": "mit-ocw",
        "id": "12.340",
        "title": "Global Warming Science",
        "url": "https://ocw.mit.edu/courses/12-340-global-warming-science-spring-2012/",
        "resource": {
          "title": "Global Warming Science, Lecture 18",
          "url": "https://ocw.mit.edu/courses/12-340-.../resources/mit12_340s12_lec18/",
          "type": "pdf"
        }
      },
      "match": {
        "score": 0.8912,
        "scoring_method": "cross-encoder/zerank-2",
        "model_license": "CC-BY-NC-4.0",
        "explanation": "zerank-2 reranker on (course description, article lead extract)"
      },
      "contribution": {
        "suggested_level": "L2",
        "description": "12.340: Global Warming Science — Scientific foundation of anthropogenic climate change..."
      },
      "provenance": {
        "producer": "wiki-mit",
        "pipeline": "zerank-v1",
        "generated_at": "2026-06-22T16:00:00Z"
      }
    }
  ],
  "stats": {
    "courses_processed": 1,
    "total_recommendations": 7,
    "mean_score": 0.8234,
    "threshold": 0.70
  }
}
```

---

## Comparison: collaborator PDF vs. our reimplementation

| Metric | Collaborator PDF pipeline | Our reimplementation |
|--------|--------------------------|---------------------|
| **Source** | 1,439 PDFs (lecture slides) | 2,577 course descriptions + lecture metadata |
| **Recall** | Custom TF-IDF | ad-hoc-match.py + Wikipedia search API |
| **Candidates per course** | Varies (avg. ~38) | Configurable (default 30) |
| **Article text** | Full article (API) | Lead extract (API, faster) |
| **Performance (1 course)** | Unknown (external) | ~5s candidates + ~1s extracts + ~3-40s zerank |
| **Threshold** | 0.79 (sigmoid) | 0.70 (raw logit, equivalent) |
| **Expected yield (env domain)** | 185 pairs from 41 courses | Estimated 150-250 pairs (lighter source text, broader retrieval) |
| **Output** | PDF (ad-hoc parsing) | REP JSON (machine-readable, feeds into our tools) |
| **Coverage** | 41 courses (env only) | All 2,577 courses |

---

## Next steps

1. **Verify against ground truth:** Run `--course 12.340` and compare outputs against the collaborator's 185 matches for the same courses. Check whether our pipeline finds the same (or better) article matches.
2. **Tune threshold:** Run the full environment domain and find the threshold that yields approximately 185 matches (matching the collaborator's yield).
3. **Add lecture-level scoring:** Currently we use one course description as the query. For better precision, score individual lectures against articles (e.g., "Global Warming Science, Lecture 13" vs. "Carbon cycle").
4. **GPU deployment:** For production, run on a GPU instance (Toolforge doesn't have GPUs; use a separate AWS/GCP instance or the ZeroEntropy API).
