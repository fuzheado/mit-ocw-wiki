# Running Zerank-2 on Google Colab Free GPU

> **Status:** Feasibility evaluation.
> **Question:** Can Google Colab's free GPU tier run zerank-2 for our recommendation pipeline, and at what performance?
> **Answer:** Yes — for our full 2,577-course batch it takes ~30-60 minutes (shallow) or ~2-4 hours (deep), fitting comfortably in one session. The T4's 15 GB VRAM is sufficient for the 4B model.

---

## Colab Free Tier Specs

| Resource | Specification | Notes |
|----------|--------------|-------|
| **GPU** | NVIDIA T4 | 15-16 GB VRAM (~15 GB usable after ECC) |
| **System RAM** | ~12-13 GB | Enough for data loading |
| **Disk** | ~78 GB ephemeral | Lost when session ends |
| **Session limit** | Up to 12 hours | Practically 2-6 hours on free tier |
| **Idle timeout** | ~90 min inactivity | Keep notebook running with progress output |
| **Weekly GPU quota** | ~15-30 GPU hours | Dynamic, not guaranteed |
| **Concurrent notebooks** | 2 | Can run two scoring jobs in parallel |
| **Cost** | Free | No credit card needed |

## Zerank-2 Memory Requirements

| Component | Size |
|-----------|------|
| Model weights (bfloat16) | 4B × 2 bytes = **8 GB** |
| Attention KV cache + activations | ~2-3 GB (batch size 1) |
| Sentence Transformers overhead | ~0.5 GB |
| **Total VRAM needed** | **~10-12 GB** |
| T4 available VRAM | **~15 GB** |
| **Headroom** | **~3-5 GB** ✅ |

The 4B model fits comfortably. You can even increase batch size to 4-8 pairs for throughput without OOM.

---

## Performance Estimates

| Task | Pairs | CPU (MacBook) | Colab T4 GPU | Speedup |
|------|-------|--------------|-------------|---------|
| Single pair | 1 | 2-5 sec | <50 ms | 40-100× |
| One course (shallow) | 20 | 40-100 sec | ~1 sec | 40-100× |
| One course (deep, triage) | 90 | 3-6 min | ~3-5 sec | 36-72× |
| 41 courses env domain (shallow) | 1,230 | 40-100 min | ~1-2 min | 40-50× |
| 41 courses env domain (deep, triage) | 3,895 | ~2 hr | ~2-4 min | 30-60× |
| 2,577 courses (shallow) | 77,310 | ~43 hr | **~30-60 min** | 43-86× |
| 2,577 courses (deep, triage) | 250,000 | ~6 days | **~2-4 hr** | 36-72× |

**Key takeaway:** The full 2,577-course deep pipeline, which takes 6 days on CPU, runs in 2-4 hours on Colab's free T4. That's a single afternoon session.

---

## Colab Notebook: Step-by-Step

### Cell 1: Setup

```python
# Install dependencies (needed each session)
!pip install -q sentence_transformers torch requests pyyaml

import torch
import json
import time
import requests
from sentence_transformers import CrossEncoder
from google.colab import drive

# Verify GPU (PyTorch 2.x uses total_memory; 1.x used total_mem)
print(f"GPU available: {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"GPU: {torch.cuda.get_device_name(0)}")
    props = torch.cuda.get_device_properties(0)
    vram = getattr(props, 'total_memory', None) or getattr(props, 'total_mem', 0)
    print(f"VRAM: {vram / 1e9:.1f} GB")
else:
    print("No GPU detected. Go to Runtime → Change runtime type → T4 GPU")
    print("If T4 is already selected, GPUs may be at capacity — try again later.")

# Mount Google Drive for persistence
drive.mount('/content/drive')
```

**Output:**
```
GPU available: True
GPU: Tesla T4
VRAM: 15.8 GB
```

### Cell 2: Load model (one-time per session, ~2 min download)

```python
# Load zerank-2 — downloads ~8 GB (one-time per session)
print("Loading zerank-2...")
model = CrossEncoder(
    "zeroentropy/zerank-2",
    device="cuda"
)
print("Model loaded.")

# Quick smoke test
scores = model.predict([("test query", "test document")])
print(f"Smoke test score: {float(scores[0]):.2f}")
```

### Cell 3: Load data from GitHub

```python
# Load course data from our repo (or upload JSON)
COURSE_DATA_URL = "https://raw.githubusercontent.com/fuzheado/mit-ocw-wiki/main/dashboard/ocw-census.js"

# Or from Google Drive
# COURSE_DATA_PATH = "/content/drive/MyDrive/wiki-mit/course-data.json"

import urllib.request

# Fetch course metadata (you'd pre-generate this as JSON)
resp = requests.get(
    "https://raw.githubusercontent.com/fuzheado/mit-ocw-wiki/main/scripts/...",
    headers={"User-Agent": "Colab-Zerank/1.0"}
)
courses = resp.json()  # list of {course_id, title, description, topics, ...}

# Fetch article extracts (pre-computed from our pipeline)
articles = []  # load from file or API

print(f"Loaded {len(courses)} courses")
```

### Cell 4: Run scoring (the main event)

```python
# Scoring loop with progress tracking
results = []
total_pairs = 0
start_time = time.time()

for i, course in enumerate(courses):
    # Build query from course metadata
    query = f"{course['title']}"
    if course.get('description'):
        query += f"\n{course['description']}"
    if course.get('topics'):
        query += f"\nTopics: {', '.join(course['topics'][:5])}"

    # Candidate articles for this course
    candidates = course.get('candidates', [])  # pre-generated Stage 1 candidates

    if not candidates:
        continue

    # Build (query, document) pairs
    doc_texts = [f"{c['title']}\n{c.get('extract', '')[:800]}" for c in candidates]
    pairs = [(query, doc) for doc in doc_texts]

    # Score all pairs for this course
    scores = model.predict(pairs, convert_to_tensor=True)
    probs = (scores / 5.0).sigmoid()

    # Attach scores
    for j, candidate in enumerate(candidates):
        candidate['zerank_score'] = round(float(probs[j]), 4)
        candidate['zerank_raw'] = round(float(scores[j]), 2)

    # Keep high-scoring results
    for c in candidates:
        if c.get('zerank_score', 0) >= 0.70:
            results.append({
                'course_id': course['course_id'],
                'course_title': course['title'],
                'article': c['title'],
                'zerank_score': c['zerank_score'],
            })

    total_pairs += len(pairs)

    # Progress
    elapsed = time.time() - start_time
    pairs_per_sec = total_pairs / elapsed if elapsed > 0 else 0
    print(f"[{i+1}/{len(courses)}] {course['course_id']} — "
          f"{len(candidates)} candidates, {len(pairs)} pairs "
          f"({pairs_per_sec:.0f} pairs/sec, ETA: {(len(courses)-i-1) * (elapsed/(i+1))/60:.0f} min)")

    # Save checkpoint every 50 courses (to Google Drive)
    if (i + 1) % 50 == 0:
        checkpoint_path = f"/content/drive/MyDrive/wiki-mit/zerank-results-{i+1}.json"
        with open(checkpoint_path, 'w') as f:
            json.dump(results, f)
        print(f"  💾 Checkpoint saved: {len(results)} results")

# Final save
final_path = "/content/drive/MyDrive/wiki-mit/zerank-results-final.json"
with open(final_path, 'w') as f:
    json.dump(results, f)

elapsed = time.time() - start_time
print(f"\n✅ Done! {len(results)} recommendations in {elapsed/60:.1f} minutes")
print(f"   {total_pairs} pairs scored at {total_pairs/elapsed:.0f} pairs/sec")
print(f"   Saved to {final_path}")
```

### Cell 5: POST results to REP API

```python
# Optionally post results to our Toolforge API
API_URL = "https://wiki-mit.toolforge.org/api/v1/recommendations"
API_TOKEN = "wm_..."  # or read from Google Drive secrets file

batch = {
    "batch": {
        "id": f"colab-zerank:{time.strftime('%Y-%m-%d')}",
        "description": f"Zerank-2 scored recommendations for {len(courses)} courses via Colab T4",
        "producer": "wiki-mit-colab",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    },
    "recommendations": [
        {
            "id": f"colab-zerank:{r['course_id']}:{r['article'].replace(' ', '_')[:50]}",
            "article": {"title": r["article"]},
            "source": {
                "corpus": "mit-ocw",
                "id": r["course_id"],
                "title": r["course_title"],
                "url": f"https://ocw.mit.edu/search/?q={r['course_id']}",
            },
            "match": {
                "score": r["zerank_score"],
                "scoring_method": "cross-encoder/zerank-2",
                "explanation": "Colab T4 GPU batch scoring",
            },
            "provenance": {
                "producer": "wiki-mit-colab",
                "pipeline": "colab-zerank-v1",
                "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            },
        }
        for r in results
    ],
}

resp = requests.post(
    API_URL,
    json=batch,
    headers={
        "Authorization": f"Bearer {API_TOKEN}",
        "Content-Type": "application/json",
    },
)
print(f"POST → {resp.status_code}: {resp.json()}")
```

---

## Limitations & Workarounds

| Limitation | Impact | Workaround |
|-----------|--------|------------|
| **Session timeout (12h max, often 2-6h)** | Full corpus deep pipeline (4h) fits; larger batches may not | Checkpoint every 50 courses to Google Drive; resume from checkpoint in new session |
| **GPU not always available** | Sometimes T4s are exhausted, you get CPU | Try again later; Colab Pro ($10/mo) guarantees T4 access |
| **Storage is ephemeral** | All files lost when session ends | Save to Google Drive (`/content/drive/MyDrive/`) or POST to REP API |
| **Idle disconnect (~90 min)** | Session dies if no cell is running | Keep the scoring loop printing progress; this counts as activity |
| **8 GB model download per session** | 2-3 min download each time | Save model to Google Drive and load from there (avoids re-download) |
| **Weekly GPU quota (15-30 hrs)** | Enough for several full runs per week | Plan batch runs; use CPU for dev/testing |
| **Network speed for data loading** | If loading course data from external sources | Pre-package data into a single JSON, upload to Drive once |

### Saving the model to Google Drive (avoid re-downloading)

```python
# Save model to Drive (run once)
model.save("/content/drive/MyDrive/wiki-mit/zerank-2-model")

# Load from Drive in future sessions:
model = CrossEncoder("/content/drive/MyDrive/wiki-mit/zerank-2-model", device="cuda")
```

---

## Comparison: Colab vs. Alternatives

| Option | GPU | VRAM | Cost | Best for |
|--------|-----|------|------|----------|
| **Colab Free** | T4 | 15 GB | Free | Batch scoring (2-4 hr runs), prototyping |
| **Colab Pro** | T4/V100 | 15-16 GB | $10/mo | Guaranteed GPU access, longer sessions |
| **Colab Pro+** | V100/A100 | 16-40 GB | $50/mo | Heavy batch processing, background execution |
| **ZeroEntropy API** | Managed | N/A | Per-request pricing | Production, no GPU management |
| **Local MacBook CPU** | None | N/A | Free (electricity) | Dev/testing, single-course matching |
| **Toolforge** | None | N/A | Free | Serving, not scoring |

**Recommendation:** Colab Free for weekly batch scoring (2-4 hour jobs on T4), ZeroEntropy API or Colab Pro for production-scale needs.

---

## Concrete Workflow: Weekly Batch

1. **Sunday evening:** Open Colab notebook, connect to T4 GPU
2. **Load data:** Fetch latest course metadata + candidate articles from GitHub
3. **Run scoring:** ~2-4 hours for full deep pipeline, ~30-60 min for shallow
4. **Save:** Results to Google Drive (JSON) + POST to REP API
5. **Monday morning:** New recommendations are available in the Workbench

All free. All automated with a few clicks. The notebook can even be scheduled with Google Colab's "execute on schedule" feature (Pro required) or triggered manually.

---

## Reference

| Document | Covers |
|----------|--------|
| `docs/ZERANK-INTEGRATION.md` | zerank-2 model details, sentence_transformers usage |
| `docs/ZERANK-PIPELINE.md` | Shallow pipeline architecture |
| `docs/ZERANK-DEEP-INSPECTION.md` | Deep pipeline with lecture text |
| `docs/RECOMMENDATION-EXCHANGE-PROTOCOL.md` | REP API for posting results |
