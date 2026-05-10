# OCW LLM Wiki — Technical Overview

## Architecture

Three layers following the [LLM Wiki pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f):

```
raw/          Immutable source data from the MIT Learn API (JSON)
wiki/         LLM-generated markdown pages (the living artifact)
CLAUDE.md     Schema file telling the LLM how to maintain the wiki
```

## Data Source

**MIT Learn API** — `https://api.learn.mit.edu/api/v1/`

- Public, no auth required
- 2,577 OCW courses (filtered by `offered_by=ocw`)
- Paginated: 100 per page, 26 pages total
- Returns structured JSON with topics, departments, instructors, runs, course numbers
- Key insight: course readable IDs use format `{number}+{semester}_{year}` (e.g., `1.018J+fall_2009`)

**Known limitation:** Very new courses (e.g., RES.ENV-007 from Jan 2025) may not be indexed. Fall back to HTML scraping from `https://ocw.mit.edu/courses/{slug}/`.

## Wiki File Structure

| Directory | Purpose | Count |
|-----------|---------|-------|
| `wiki/courses/` | One page per course | ~2,577 when complete |
| `wiki/departments/` | 37 MIT departments | 37 |
| `wiki/topics/` | 110 topics (hierarchical) | 110 |
| `wiki/instructors/` | One page per instructor | grows with courses |
| `wiki/index.md` | Agent catalog of all pages | 1 |
| `wiki/log.md` | Append-only chronological log | 1 |
| `wiki/overview.md` | Top-level synthesis | 1 |

## Page Schema

Every course page has YAML frontmatter per the Normalization Protocol (Rule 1.1):
- `url`, `course_id`, `title`, `year_published`, `instructors`, `level`, `department`, `topics`, `license`, `views`, `completeness`, `last_modified`, `type`

All fields required. Missing values → `Unknown` + `FIXME` tag. Never invent metadata.

## Wikilink Convention

The WikiWise build system resolves links by **filename slug only** — path is ignored.
- File at `wiki/courses/15-071-the-analytics-edge-spring-2017.md` → slug `15-071-the-analytics-edge-spring-2017`
- Link as `[[15-071-the-analytics-edge-spring-2017|The Analytics Edge]]`, never as `[[courses/15-071.md]]`

## Ingestion Workflow

### Batch script
```bash
python3 scripts/ingest-batch.py --offset 0 --limit 100
```

The script:
1. Fetches one API page (100 courses)
2. For each course: extracts Canonical Course Object, writes `wiki/courses/{slug}.md`
3. Appends course links to department pages (creates if new)
4. Appends course links to topic pages (creates if new)  
5. Creates instructor pages (appends to existing if already known)
6. Saves raw JSON to `raw/api/courses-page-{offset}.json`
7. Commits locally with message `ocw: ingest batch offset={N}`

### Checkpoint system
`_checkpoint.json` tracks progress across sessions:
- `stages.courses_bootstrap.last_offset` — resume point
- `stages.courses_bootstrap.batches_done` — progress counter
- `stats.courses_in_wiki` — total pages created

### Ad-hoc single course
For individual courses (not in batch), fetch by readable_id:
```
GET /api/v1/courses/?offered_by=ocw&readable_id={id}%2B{semester}_{year}
```

## Wikipedia Cross-Reference (Stage 4, not yet run)

Planned approach:
- Match courses to Wikipedia articles by topic name, course title keywords, department
- Generate `{{cite web}}` citation templates for each match
- Flag `[Visual-Rich]` assets for Wikimedia Commons eligibility
- Flag `[Source-Rich]` reading lists for Wikipedia "Further reading" sections

## Tools

| Tool | Purpose |
|------|---------|
| WikiWise app | Local viewer, auto-recompiles on file changes |
| `scripts/ingest-batch.py` | Batch course ingestion |
| `scripts/scan-assets.py` | Asset inventory and video detection |
| `scripts/regenerate-index.py` | Rebuild wiki index from filesystem |
| `touch .rebuild` | Force WikiWise full recompile |
| `.claude/active-file` | Tracks which page user is viewing |

## Asset Scanning — Three Modes

The `scripts/scan-assets.py` script has three scanning modes, each with different strengths:

### `--deep` (URL deep scan)
Visits the course page and all its sub-pages, extracts sidebar links, detects embedded video, and catalogs downloadable files.

**Strengths:** Works for all courses regardless of API index status. Finds sidebar page structure (Syllabus, Calendar, Instructor Insights). Detects off-platform video (Dropbox, YouTube embeds) and legacy video gallery listings.

**Weaknesses:** Misses content files that aren't linked from visible pages. No YouTube IDs for direct video links. Slower (visits every sub-page individually). Less complete for video-rich courses.

### `--api` (API content file scan)
Fetches all content files for a course from the MIT Learn API's `/api/v1/courses/{id}/contentfiles/` endpoint.

**Strengths:** Authoritative inventory — the API knows about every file. Includes YouTube IDs, file extensions, content types, and descriptions. Much faster (single API call vs 50+ HTTP requests). More complete for well-indexed courses (292 files for 5.111SC vs 154 from URL scan).

**Weaknesses:** Only as complete as the API index. Newer courses (2024-2026) may have sparse data. No sidebar page structure. Generic "Resource" type for files the API can't classify.

### `--hybrid` (API + URL, merged)
Runs both scans and merges the results. API data is the authoritative base; URL deep scan supplements with sidebar pages and corrects generic types.

**Strengths:** Best of both worlds. API provides YouTube IDs, descriptions, and complete file inventory. Deep scan adds page structure and corrects types. Falls back to full deep scan when API is sparse.

**Weaknesses:** Slower (runs both scans). Duplicate handling adds complexity.

### Efficacy comparison

| Course | `--api` | `--deep` | `--hybrid` |
|--------|---------|----------|------------|
| **5.111SC** (2014, well-indexed) | 223 assets, 45 YouTube IDs | 154 assets, 35 video badges | **258 assets** (API + 35 sidebar pages) |
| **15.071** (2017, well-indexed) | 396 assets, 183 video files | 162 assets, 35 video badges | — |
| **2.782J** (2025, sparse API) | 7 assets, generic types | 50 assets, correct types | **7 assets, correct types** (URL types override) |

### Recommendation
Use `--hybrid` for best results. Fall back to `--deep` for very new courses not yet in the API.

## Git Strategy

- Commits after each batch with prefix `ocw:`
- No auto-push (slow)
- Push manually when convenient
- Branch for experiments (alternate topic hierarchies, crossref strategies)

## Index Auto-Regeneration

A git pre-commit hook at `scripts/pre-commit` automatically regenerates `wiki/index.md` and `wiki/instructors-index.md` whenever course, instructor, or department files change.

**Setup on fresh clone:** `cp scripts/pre-commit .git/hooks/pre-commit`

The instructors index (`wiki/instructors-index.md`) groups all 2,100+ instructors alphabetically by first letter (A-Z) with jump links. It's linked from the main index page.

## Log Convention

All log entries in `wiki/log.md` follow the format:

```
## [YYYY-MM-DD HH:MM] operation | [[slug|Course Number Title]] (details)
```

The wikilink format `[[slug|Course Number Title]]` makes entries clickable in WikiWise, jumping directly to the course page. Course number (e.g., "5.111SC") is prepended to the title for easy scanning.

## Video Detection Patterns

The deep scan detects video content using these patterns, in order of specificity:

| Pattern | Detects | Badge |
|---------|---------|-------|
| `Download video` / `Download transcript` / `View video page` | OCW embedded player | 📺Video |
| `youtube.com/embed` / `youtu.be` / `youtube.com/watch` | YouTube embeds | 🎬YouTube |
| `.mp4` / `video/mp4` / `video/webm` | Direct MP4 files | 📺Video |
| `class="video"` in HTML | Video embed elements | 📺Video |
| `img.youtube.com/vi/{id}/default.jpg` | YouTube video thumbnails (galleries without clickable links) | 🎬YouTube |
| External links to dropbox.com, vimeo.com, panopto.com, kaltura.com, zoom.us, archive.org | Off-platform video hosts | 🎬YouTube / 📺Video |

**Legacy video galleries:** For older courses (pre-2015), all lectures are listed on a single gallery page rather than individual sub-pages. The deep scan detects these inline listings and extracts each lecture title as a separate Video-Transcript asset.

**JavaScript-loaded galleries:** Modern OCW courses (2024+) often use JavaScript to load video galleries. The HTML may contain zero clickable YouTube links but dozens of `img.youtube.com/vi/{id}/default.jpg` thumbnail references. The deep scan extracts YouTube IDs from these thumbnails to construct direct video links.

## Asset Type Mapping

When using `--api` mode, the script maps the API's `content_feature_type` to wiki asset types:

| API feature_type | Wiki asset type |
|---|---|
| Lecture Videos, Other Video | Video-Transcript |
| Lecture Notes | Lecture-Notes |
| Problem Sets, Problem Set Solutions, Exams, Exam Solutions | Problem-Set |
| Projects, Projects with Examples, Assignments | Assignment |
| Readings, Reading Lists, Open Textbooks | Reading-List |
| Instructor Insights, Activity Assignments, Image Gallery | Resource / Image-Gallery |

**Video type override:** API content files with empty `content_feature_type` are checked for video indicators directly — if they have a `youtube_id`, `content_type == "video"`, or `file_extension` of `.mp4`/`.webm`, they are classified as Video-Transcript regardless. This catches files the API indexed without proper type tags (e.g., 17 videos in 1.258J were missing their feature type).

## API Readable ID Format

The API uses uppercase course IDs. The `course_id` in wiki frontmatter may be lowercase (e.g., `"21h.151"`), but the API expects uppercase (`"21H.151"`). The `--hybrid` and `--api` modes uppercase the course_id before constructing the `readable_id` parameter: `{COURSE_ID}+{semester}_{year}`.

## Hybrid Merge Logic

The `--hybrid` mode runs both API and deep scans, then merges:

1. Start with API results (authoritative file data with YouTube IDs, descriptions)
2. Run deep scan to discover sidebar pages AND external video links
3. External videos (YouTube, Dropbox, etc.) are separated from sidebar pages by checking URL prefixes first — YouTube URLs have fewer slashes than OCW sidebar URLs, so the check must be ordered correctly
4. For each sidebar page:
   - If its URL isn't in the API results, add it directly
   - If its URL IS in the API results but was typed as generic "Resource", replace with the deep scan's more specific type (e.g., "Syllabus", "Reading-List")
5. For each external video not already covered by the API, add it as a Video-Transcript asset
6. If the API returns no data (new/unindexed course), fall back to full deep scan results
