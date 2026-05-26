# OCW LLM Wiki — Project Schema

An LLM Wiki (Karpathy pattern) for MIT OpenCourseWare. This document defines the schema, data sources, and workflows for building a persistent, interlinked markdown wiki from OCW's 2,500+ courses, then cross-referencing it with Wikipedia.

## Architecture

```
raw/                    # Immutable source data (never modified)
  api/                  # Raw JSON from MIT Learn API
    courses-page-*.json # Paginated course list responses
    departments.json    # Department list
    topics.json         # Topic hierarchy
  courses/              # Per-course raw JSON
    {course-id}.json    # Full course detail from API
  ocw-html/             # Scraped HTML pages from ocw.mit.edu

wiki/                   # LLM-generated markdown (the living artifact)
  index.md              # Catalog of all pages with links + summaries
  log.md                # Chronological record of all operations
  overview.md           # Top-level synthesis of OCW as a whole
  courses/              # One page per course
    {course-slug}.md    # Course summary page (see Normalization Protocol)
  departments/          # One page per department
    {dept}.md           # Department overview with course list
  topics/               # One page per topic
    {topic-slug}.md     # Topic summary with course references
  instructors/          # One page per instructor
    {instructor-slug}.md
  crossrefs/            # Wikipedia cross-references
    {topic-slug}.md     # Wiki page -> relevant OCW courses
  assets/               # Per-asset pages for reusable content
    {asset-slug}.md     # Individual lecture note, video, etc.
  reports/              # Generated analyses
    topic-coverage.md
    department-summary.md
    wikipedia-gap-analysis.md
```

## Data Sources

### Primary: MIT Learn API (no auth required)

Base URL: `https://api.learn.mit.edu/api/v1/`

**Courses list:** `GET /api/v1/courses/?offered_by=ocw&limit=100&offset=N`
- Returns 2,577 OCW courses (paginated, 100 per page, ~26 pages)
- Each result includes: title, description, url, course numbers, instructors, department, level, semester/year, topics, course features, image, view count, license info
- Use the `next` URL from the response to paginate

**Single course detail:** `GET /api/v1/courses/{id}/`
- Full detail including runs, instructors, content files

**Topics:** `GET /api/v1/topics/`
- 110 topics in a 2-level hierarchy (parent/child)

**Departments:** `GET /api/v1/departments/`
- All MIT academic departments

**Course features:** `GET /api/v1/course_features/`
- Learning resource types (lecture notes, videos, etc.)

**Content files:** `GET /api/v1/content_file_search/`
- Search within course materials

**Filtering available:**
- `offered_by=ocw` — OCW only
- `platform=ocw` — OCW platform only
- `department={code}` — filter by department
- `level={code}` — undergraduate, graduate, etc.
- `topic={name}` — filter by topic
- `sortby={field}` — sort results

### Secondary: OCW HTML pages

Course page pattern: `https://ocw.mit.edu/courses/{dept-num}-{slug}-{term-year}/`
- Use for content not available via API (full syllabus text, lecture content, etc.)

### Cross-reference: Wikipedia

Use Wikipedia API or Wikipedia dump for matching:
- `https://en.wikipedia.org/api/rest_v1/page/summary/{title}`
- Match by: topic name, course title keywords, department name

---

## 1. The Normalization Protocol

Because OCW layouts differ (API vs HTML), every course must be reduced to a Canonical Course Object.

### Rule 1.1 (Metadata Extraction)

Every wiki page in `wiki/courses/` must begin with YAML frontmatter containing:

```yaml
---
url: "https://ocw.mit.edu/courses/{dept-num}-{slug}-{term-year}/"
course_id: "{dept-num}"              # e.g. "18.06", "21H.151"
title: "{Full Course Name}"           # e.g. "Dynastic China"
year_published: {YYYY}                # Extracted from syllabus or URL
instructors: ["{Name1}", "{Name2}"]   # Primary faculty only
level: ["{undergraduate|graduate}"]
department: "{dept_code}"
topics: ["{topic1}", "{topic2}"]
license: "CC BY-NC-SA"                # or "All Rights Reserved"
views: {count}
completeness: {0.0-1.0}
last_modified: "{date}"
type: course
---
```

All fields are required. If a value cannot be found in the raw source, set it to `Unknown` and append a `FIXME` tag — never invent metadata (see Rule 4.2).

### Rule 1.2 (Asset Typing)

Every link or file detected within a course must be categorized into one of five types:

| Type | Tag | Description |
|------|-----|-------------|
| Lecture Notes | `[Lecture-Notes]` | Slide decks, PDF summaries, written lecture content |
| Video/Transcript | `[Video-Transcript]` | Recorded lectures, caption files, transcript PDFs |
| Problem Set | `[Problem-Set]` | Assignments, exams, solution keys |
| Reading List | `[Reading-List]` | Bibliographies, suggested readings, paper lists |
| Image/Gallery | `[Image-Gallery]` | Diagrams, photographs, data visualizations |

Each asset link in a course page's Materials section must be tagged. Example:

```markdown
## Materials

- [Lecture-Notes] Linear Algebra Basics (PDF)
- [Video-Transcript] Lecture 4: Eigenvalues (YouTube)
- [Problem-Set] Problem Set 3 with Solutions (PDF)
- [Reading-List] Week 5: Strang Chapters 7-9
- [Image-Gallery] Phase portrait diagrams (PNG)
```

---

## 2. Schema for Evolving Wiki Pages

### Wikilink conventions

The WikiWise build system resolves `[[wikilinks]]` by filename slug only (path is ignored). A file at `wiki/courses/21h-151-dynastic-china-fall-2024.md` has slug `21h-151-dynastic-china-fall-2024`. Always link as `[[slug]]` or `[[slug|display text]]`, never as `[[path/to/file.md|text]]`.

### Course page (`wiki/courses/{slug}.md`)

```markdown
---
url: "https://ocw.mit.edu/courses/21h-151-dynastic-china-fall-2024/"
course_id: "21H.151"
title: "Dynastic China"
year_published: 2024
instructors: ["Prof. Tristan G. Brown"]
level: ["undergraduate"]
department: "21H"
topics: ["Humanities", "History", "Asian History"]
license: "CC BY-NC-SA"
views: {count}
completeness: {0.0-1.0}
last_modified: "{date}"
type: course
---

# {course title}

{description}

## Course Info

- **Department:** [[{dept}|{dept name}]]
- **Course Number:** {course_id}
- **Instructors:** [[{slug}|{name}]]
- **Year:** {year_published}
- **Level:** {level}
- **Topics:** {topic links}
- **License:** {license}

## Materials

{Course features / learning resource types, each tagged per Rule 1.2}

## Wikipedia Bridge

### Related Articles

1. [[{slug}|{Wikipedia Article Title}]] — {relevance note}
2. ... (3-5 articles)

### Citation Template

```wikitext
{{cite web
 |url={url}
 |title={course title}
 |author={instructors}
 |website=MIT OpenCourseWare
 |access-date={current date}
}}
```
```

### Topic page (`wiki/topics/{topic-slug}.md`)

```markdown
---
id: topic-{id}
title: "{topic name}"
type: topic
parent: "{parent topic}"
courses_count: {N}
---

# {topic name}

Parent topic: {parent}

## Courses

{course links in this topic}

## Wikipedia Connections

{wikipedia articles that match this topic}
```

### Instructor page (`wiki/instructors/{slug}.md`)

```markdown
---
id: instructor-{id}
name: "{full name}"
type: instructor
courses_count: {N}
---

# {full name}

## Courses Taught at MIT

{course links}
```

### Asset page (`wiki/assets/{asset-slug}.md`)

```markdown
---
id: asset-{id}
type: "{Lecture-Notes|Video-Transcript|Problem-Set|Reading-List|Image-Gallery}"
source_course: "{course_id}"
title: "{asset title}"
url: "{direct URL or permalink}"
wikimedia_commons_candidate: {true|false}     # Rule 2.1
source_rich: {true|false}                      # Rule 2.2
---

# {asset title}

Part of: [[{slug}|{course name}]]

{description}

## Wikipedia Utility

[Visual-Rich] or [Source-Rich] — see Utility Rubric below.
```

### Cross-reference page (`wiki/crossrefs/{topic-slug}.md`)

```markdown
---
id: xref-{id}
type: crossref
wikipedia_article: "{article title}"
ocw_courses: [{course ids}]
match_method: "title|topic|keyword"
---

# Wikipedia: {article title} → OCW Courses

{summary of the Wikipedia article}

## Related OCW Courses

{course links with relevance explanation}

## Potential Use

- Direct citation as reference
- Complementary course material
- Media/content reuse (CC licensed)

## Citation Snippet

```wikitext
{{cite web |url={url} |title={title} |author={instructors} |website=MIT OpenCourseWare |access-date={date}}}
```
```

---

## Wikipedia Cross-Reference

See `docs/crossref-strategy.md` for the full strategy.

TL;DR — three-tier matching approach:
1. **Template-driven gaps** — find Wikipedia articles with `{{Citation needed}}`, `{{Missing information}}`, etc. in OCW topic areas
2. **Term-overlap discovery** — use lecture titles as Wikipedia search queries
3. **Structural gap analysis** — match OCW topic coverage against Wikipedia category gaps

Results populate two locations per course:
- Wikipedia Bridge section with 3-5 top matches and `{{cite web}}` templates
- `wiki/crossrefs/{article-slug}.md` hub pages aggregating all courses per article

---

## 5. Workflows

### 5.1 BOOTSTRAP — Ingest all courses

```
1. Fetch ALL courses from API (paginate through all 2,577)
   - GET /api/v1/courses/?offered_by=ocw&limit=100
   - Save raw JSON to raw/api/courses-page-*.json
   - Track: which pages fetched, any errors

2. Build course pages (apply Normalization Protocol)
   For each course:
   a. Extract Canonical Course Object per Rule 1.1
   b. Create wiki/courses/{slug}.md with full YAML frontmatter
   c. Catalog all assets per Rule 1.2
   d. Create asset pages in wiki/assets/
   e. Create/get department page, add course link
   f. Create/get topic pages, add course link
   g. Create/get instructor pages, add course link

3. Build department index
   For each unique department, create wiki/departments/{dept}.md

4. Build topic hierarchy
   For each topic, create wiki/topics/{slug}.md with parent/child links

5. Update wiki/index.md
   - List all pages by category with links
   - Add one-line summaries

6. Append to wiki/log.md
   - Entry: ## [YYYY-MM-DD] bootstrap | Ingested {N} OCW courses
```

### 5.2 INGEST — Add new courses (incremental)

```
1. Fetch current course list from API
2. Compare IDs with existing wiki course pages
3. For each new course: create page, run asset typing, update index, update topic/dept/instructor pages
4. Log the ingest
```

### 5.3 CROSSREF — Match courses to Wikipedia

```
1. For each course:
   a. Extract key terms: course title, topic names, department
   b. Query Wikipedia API for matching articles
   c. If match found:
      - Create wiki/crossrefs/{topic-slug}.md
      - Add Wikipedia Bridge section to course page
      - Generate citation template
   d. For each asset in the course:
      - Apply Wikipedia Utility Rubric (Rule 3)
      - Tag with [Visual-Rich] or [Source-Rich] if applicable

2. Match strategies (try in order):
   a) Topic-based: For each topic in OCW hierarchy, find Wikipedia article
   b) Title-based: Match course title keywords to Wikipedia page titles
   c) Department-based: Map departments to Wikipedia subject areas
   d) Instructor-based: Find Wikipedia articles for notable instructors

3. For each successful match, also check:
   - Can OCW material be cited as a reference in the Wikipedia article?
   - Is OCW media eligible for Wikimedia Commons upload?
   - Which specific Wikipedia sections (History, Content, References) the
     OCW material best supports
```

### 5.4 QUERY — Ask questions against the wiki

```
1. Read wiki/index.md to find relevant pages
2. Read candidate pages
3. Synthesize answer with citations linking to wiki pages
4. For valuable answers: save as new wiki page in wiki/reports/
```

### 5.5 LINT — Health check

```
Apply both general wiki linting and the OCW-specific integrity rules:

General:
- Orphan pages with no inbound links
- Broken internal wiki links
- Inconsistent frontmatter across pages
- Stale data (courses modified on OCW since last ingest)

Rule 4.1 (Link Rot Surveillance):
- Check stored URLs against their HTTP response
- If a URL from legacy ocw.mit.edu/courses/... is dead, suggest the
  Wayback Machine equivalent: https://web.archive.org/web/*/{url}
- Log any dead links in wiki/log.md with [BROKEN-LINK] tag

Rule 4.2 (Provenance):
- Never invent metadata. If a "Year" or "Instructor" cannot be found
  in the raw/ source, mark it as Unknown and add a FIXME tag in the
  frontmatter for manual review
- Do not infer or hallucinate values

Wikipedia-specific:
- Missing Wikipedia Bridge sections on course pages
- Courses flagged [Source-Rich] or [Visual-Rich] that lack a crossref
- Outdated citation templates (stale access-date)
```

### 5.6 GENERATE — Create derived artifacts

- **Slide deck** (Marp format) of OCW coverage by department
- **Topic coverage report:** which topics have most/fewest courses
- **Instructor directory:** all instructors with course counts
- **Department heat map:** course distribution across departments
- **Wikipedia gap analysis:** which Wikipedia articles lack OCW references
- **Commons upload manifest:** list of [Visual-Rich] assets ready for Wikimedia Commons
- **Citation database:** all generated citation templates in one file for bulk submission

---

## 6. Implementation Notes

### Rate limiting
The API is public but be respectful. Add 100-500ms delay between requests.

### Pagination
The courses endpoint returns `count: 2577`. Use `limit=100` and iterate `offset`:
```python
offset = 0
while url:
    response = get(f"{url}?offered_by=ocw&limit=100&offset={offset}")
    data = response.json()
    for course in data["results"]:
        process(course)
    offset += 100
    if offset >= data["count"]:
        break
```

### Deduplication
OCW sometimes has multiple runs of the same course (different semesters). Each is a separate entry in the API. Decide whether to keep them separate or merge.

### Image handling
Courses have an `image` object with `url` and `alt` text. Optionally download to `raw/assets/`.

### License tracking
All OCW content is CC BY-NC-SA 4.0. Track `license: "CC BY-NC-SA"` in frontmatter. Flag any third-party content as `"All Rights Reserved"` and add a FIXME.

## Version Control

See `docs/git-strategy.md` for version control best practices.

## Tools

- `qmd` — local search engine for markdown (BM25 + vector search)
- Obsidian — browse wiki with graph view, Dataview queries, Marp slides
- Obsidian Web Clipper — convert web pages to markdown for raw sources
- Wikipedia API — `https://en.wikipedia.org/api/rest_v1/page/summary/{title}`
- `curl` / `httpx` — for API fetching
- Wayback Machine API — `https://archive.org/wayback/available?url={url}` for link rot checks
