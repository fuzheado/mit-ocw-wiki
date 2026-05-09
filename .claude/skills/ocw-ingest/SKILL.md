# ocw-ingest — Bulk ingest OCW courses from the MIT Learn API

Ingest courses from the MIT Learn API into the OCW LLM Wiki in batches. This skill handles bulk API pagination, Canonical Course Object extraction, checkpoint resume, and batch commits. It is designed for the OCW-specific workflow and replaces the generic one-at-a-time ingest for this project.

## When to use

- **Bootstrap:** first-time ingest of all 2,577 OCW courses (run `ocw-ingest bootstrap`)
- **Incremental:** fetch new/updated courses since last ingest (run `ocw-ingest incremental`)
- **Single course:** one-off ingest of a specific course by API ID (run `ocw-ingest single <id>`)

Do NOT use the generic `ingest` skill for OCW courses — it is designed for one-article-at-a-time ingestion from files or URLs.

## Data source

**MIT Learn API** — `GET /api/v1/courses/?offered_by=ocw&limit=100&offset=N`
- No auth required. Fully public.
- Returns 100 courses per page with full metadata.
- Paginate with the `offset` parameter (0, 100, 200, ...).

## Workflow

### Before starting

Read `_checkpoint.json` to determine current state. Report to the user what stage we are at and wait for confirmation.

### Bootstrap

```
1. Read _checkpoint.json → stage "courses_bootstrap"
2. Determine starting offset from last_offset
3. Fetch GET /api/v1/courses/?offered_by=ocw&limit=100&offset={last_offset}
4. For each course in the response:
   a. Extract Canonical Course Object (see Rule 1.1 in OCW-LLM-WIKI.md)
   b. Write wiki/courses/{slug}.md with YAML frontmatter
   c. Append course link to its wiki/departments/{code}.md (create if new)
   d. Append course link to each wiki/topics/{topic-slug}.md (create if new)
   e. Create wiki/instructors/{slug}.md if new instructor
5. Update wiki/index.md (refresh course count in the catalog)
6. Update _checkpoint.json: increment last_offset by 100, update counts
7. Append to wiki/log.md:
   ## [YYYY-MM-DD HH:MM] ocw-ingest | Batch offset={offset} ({N} courses)
8. Git commit with message: ocw: ingest batch offset={offset}
9. Repeat steps 3-8 until offset >= total_courses
```

### Incremental

```
1. Fetch GET /api/v1/courses/?offered_by=ocw&limit=1
   Compare total count with _checkpoint.json stats.total_courses_api
2. If same count → nothing to do. Report no new courses.
3. If higher → new courses exist. Determine which course IDs are new
   by comparing API results against existing wiki/courses/ pages.
4. Process new courses only using the per-course logic from Bootstrap step 4.
5. Update _checkpoint.json and log.
```

### Single course

```
1. Run: ocw-ingest single <course-id>
2. Fetch GET /api/v1/courses/{id}/
3. Create/update the course page and all related pages
4. Log and commit
```

## Rules

1. **Checkpoint first.** Always read `_checkpoint.json` before acting. Always update it after each batch.
2. **One batch = one commit.** Each batch of 100 courses gets its own git commit with prefix `ocw:`.
3. **Overlap-safe.** If interrupted mid-batch, the next run resumes at the stored `last_offset`. Re-processing a few courses is harmless (idempotent writes).
4. **Never invent metadata.** If a field is missing from the API, set it to `Unknown` and append `FIXME` to the page.
5. **Use `[[wikilinks]]` by slug.** A course page `wiki/courses/18-06-linear-algebra.md` is linked as `[[18-06-linear-algebra]]`, never as `[[courses/18-06-linear-algebra.md]]`. The build system resolves slugs by filename only.
6. **Update index after every batch.** `wiki/index.md` must always reflect the current state.
7. **Dry-run one course first.** Before running a full bootstrap, process one course and show the output to the user for approval.

## Example session

```
User: "Run ocw-ingest bootstrap"
Agent: Reads _checkpoint.json → stage courses_bootstrap, last_offset=0
Agent: Fetches offset 0, gets 100 courses
Agent: Processes all 100, creates 100 course pages, updates dept/topic/instructor pages
Agent: Updates _checkpoint.json → last_offset=100, courses_in_wiki=100
Agent: Commits "ocw: ingest batch offset=0 (100 courses)"
Agent: "Batch 0/26 done. Proceed to next batch?"
User: "Yes, continue"
...repeat...
```
