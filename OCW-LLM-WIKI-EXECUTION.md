# OCW LLM Wiki — Execution Plan

How to run this project in stages, one session at a time.

## Stage 0: Smoke Test

Goal: prove the LLM can find the API, count courses, and build the scaffolding — without processing any individual courses.

Ask the LLM to do exactly this:

1. Fetch `GET /api/v1/courses/?offered_by=ocw&limit=1` to confirm the API responds
2. Note the `count` field (should be ~2,577)
3. Fetch `GET /api/v1/departments/` and `GET /api/v1/topics/`
4. Create `wiki/index.md` — empty skeleton with sections (courses/, departments/, topics/, etc.) and a note saying "0 courses processed yet"
5. Create `wiki/overview.md` — one-paragraph summary: "OCW has {N} courses across {M} departments and {P} topics. This wiki will ingest them incrementally."
6. Create `wiki/log.md` with first entry: `## [YYYY-MM-DD] smoke-test | API confirmed. {N} courses, {M} departments, {P} topics`
7. Create `_checkpoint.json` — see below

Nothing more. No course pages, no department pages, no instructor pages. Just the shell.

**Success criteria:** you have 4 markdown files + 1 JSON file, and the LLM proves it can talk to the API.

---

## Stage 1: Bootstrap Departments & Topics

Goal: build the non-course scaffolding so course pages have places to link to.

1. Fetch all departments from the API
2. For each, create `wiki/departments/{code}.md` with name and empty course list
3. Fetch all topics
4. For each, create `wiki/topics/{slug}.md` with parent/child links and empty course list
5. Update `wiki/index.md` with real department/topic page counts
6. Update `_checkpoint.json` — stage-1 complete

---

## Stage 2: Bootstrap Courses (in batches)

Goal: process all 2,577 courses in batches of ~100 (matching API pagination).

Each batch:

1. Fetch 100 courses: `GET /api/v1/courses/?offered_by=ocw&limit=100&offset={N}`
2. For each course:
   a. Extract Canonical Course Object per Rule 1.1
   b. Write `wiki/courses/{slug}.md`
   c. Add course link to its `wiki/departments/{code}.md`
   d. Add course link to its `wiki/topics/{slug}.md` pages
   e. Create `wiki/instructors/{slug}.md` if new instructor
3. Update `wiki/index.md` — refresh course count
4. Commit (see git guide)
5. Update `_checkpoint.json` — record offset processed

Do not run CROSSREF or asset typing during this stage. Just the canonical course object.

---

## Stage 3: Asset Scan & Typing

Goal: enrich each course page with typed asset lists (Rule 1.2).

For each course page in `wiki/courses/`:
1. Visit the course URL (or use content files API)
2. Catalog all links into the five asset types
3. Append to the Materials section of the course page
4. Optionally create `wiki/assets/{slug}.md` for high-value assets

Run in batches. This is the most expensive stage — each course may have dozens of assets.

---

## Stage 4: Wikipedia CrossRef

Goal: match OCW courses to Wikipedia articles (Section 3-4 of the schema).

For each course page:
1. Extract key terms (title, topics, department)
2. Query Wikipedia API
3. If match found: create crossref page, add Wikipedia Bridge section to course page, generate citation template
4. Apply Utility Rubric tagging

---

## Stage 5: Lint & Generate Reports

Goal: health check and produce derived artifacts.

---

## Checkpoint System

The LLM needs to know what's been done between sessions. Use a `_checkpoint.json` at the project root:

```json
{
  "version": 1,
  "stages": {
    "smoke_test": true,
    "departments_topics": false,
    "courses_bootstrap": {
      "complete": false,
      "batches_done": 0,
      "total_batches": 26,
      "last_offset": 0,
      "last_commit": ""
    },
    "asset_scan": {
      "complete": false,
      "courses_done": 0,
      "last_course_id": null
    },
    "crossref": {
      "complete": false,
      "courses_done": 0
    },
    "lint_report": false
  },
  "stats": {
    "total_courses_api": 2577,
    "courses_in_wiki": 0,
    "departments": 0,
    "topics": 0,
    "instructors": 0,
    "crossrefs": 0
  }
}
```

### How the LLM uses it

**Start of a session:**
1. Read `_checkpoint.json`
2. Read last N lines of `wiki/log.md`
3. Determine what to do next
4. Proceed

**End of a session / after each batch:**
1. Update `_checkpoint.json` with new counts and progress
2. Append to `wiki/log.md`
3. Commit

### Why not just `log.md`?

`log.md` is great for human reading but hard to parse programmatically. The LLM can read it, but extracting "which offset to resume from" from 26+ entries is error-prone. A JSON checkpoint is machine-readable and unambiguous. The LLM can update `_checkpoint.json` in one file write instead of scanning a growing log.

Use both: `_checkpoint.json` for precise state, `log.md` for human narrative.

---

## Best Practices for Incremental Execution

### 1. Defensive starts
At the beginning of every session, tell the LLM:

> "Read `_checkpoint.json` and `wiki/log.md`. Tell me what stage we're at and what the next action should be. Do not proceed until I confirm."

This prevents the LLM from re-doing work or skipping ahead.

### 2. Explicit batch boundaries
Don't say "process all remaining courses." Say:

> "Process the next batch of 100 courses starting at offset {N}. Update `_checkpoint.json` when done."

### 3. Overlap tolerance
Design for the case where a batch is partially done and then interrupted. Each course page write is atomic — if offset 500 was recorded but only 80 of 100 courses were processed, the next session picks up at offset 500 and overwrites/re-checks those 80. Slight waste of API calls, but safe.

### 4. Dry-run first
Before each new stage, do one unit first:

> "Process one course as a test. Show me the output. Do not continue until I approve the format."

### 5. Commit after every batch
Each batch of 100 courses = one commit. This makes it trivial to bisect if the LLM introduces bad data. The git guide has the exact commands.

### 6. Session handoff
When ending a session, paste this into the chat:

> "Session ending. Checkpoint is at offset {N}. Next session should resume at offset {N}. Logged at {timestamp}."
