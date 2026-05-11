# Wikipedia Cross-Reference Strategy

Stage 4 of the OCW LLM Wiki project. Goal: match MIT OCW courses and their assets to Wikipedia articles that would benefit from them, and generate actionable suggestions for contributors.

## What we have to work with

After hybrid scanning, each course page has rich, structured data:

- **YAML frontmatter** — course_id, title, topics, department, instructor, year, license
- **Asset inventory by type** — e.g., 25 Video-Transcript, 48 Lecture-Notes, 20 Problem-Set
- **Lecture titles** — e.g., "Lecture 9: Periodic Table; Ionic and Covalent Bonds" — each a self-contained keyword cluster useful as a Wikipedia search query
- **API metadata** — `ocw_topics` array, course description, all with standardized naming
- **Asset URLs** — direct links to YouTube, MP4 files, transcripts, OCW pages
- **Grouped format badges** — 🎬YouTube, 📺OCW, ⬇MP4, 📄Transcript — tells us what media exists for each lecture

## Data sources

### Option A: Wikipedia API (public, no auth)

The MediaWiki API (`api.wikipedia.org`) is fully public. Suitable for term discovery and small-scale matching:

- `list=search` — find articles by keyword (lecture titles)
- `list=embeddedin` — find pages with specific templates, but requires pagination
- `prop=info` with `inprop=size` — find short/"thin" articles
- `prop=pageassessments` — get quality/importance ratings

**Limitation:** Pagination. A single query returns at most 500 results, and finding all "Citation needed" templates across all chemistry articles would require ~10-50 sequential queries.

### Option B: Quarry SQL (faster, requires credentials)

[Quarry](https://meta.wikimedia.org/wiki/Research:Quarry) is a public SQL query service for Wikimedia databases. It runs arbitrary SQL against replicated databases, with results returned as flat tables. No pagination, no rate limits.

**Advantage over the API:** A single SQL query can do what takes 50+ API calls:

```sql
-- Find all articles in chemistry-related categories
-- that have maintenance templates AND quality ratings
SELECT
  p.page_title,
  pp.pageview_count,
  pa.quality_class,
  pa.importance_class,
  tl.template_name
FROM page p
JOIN categorylinks cl ON cl.cl_from = p.page_id
JOIN page_assessments pa ON pa.page_id = p.page_id
LEFT JOIN templatelinks tl ON tl.tl_from = p.page_id
WHERE cl.cl_to IN ('Chemistry', 'Thermodynamics', 'Chemical_bonding')
  AND tl.tl_title IN ('Citation_needed', 'Refimprove', 'More_citations_needed')
  AND pa.quality_class IN ('Stub', 'Start', 'C')
ORDER BY pa.importance_class DESC, pp.pageview_count DESC;
```

The example queries at `https://quarry.wmcloud.org/query/105029` show how to generate template usage histograms. The same approach can produce full article lists.

**Requires:** Quarry login credentials (you offered to provide). This is worth it — SQL access replaces the entire API-based template index build.

## Three target tiers

### Tier 1: Template-driven gaps

Highest priority. A Wikipedia article is actively asking for what OCW has.

**Wikipedia maintenance templates** relevant to OCW content:

| Template | Type | What OCW can provide |
|---|---|---|
| `{{Citation needed}}` | Inline | Lecture notes/transcripts as academic references |
| `{{More science citations needed}}` | Article | STEM courses with bibliographic reading lists |
| `{{More medical citations needed}}` | Article | HST and biological engineering courses |
| `{{Primary sources}}` | Article | Course materials as high-quality secondary/analytic sources |
| `{{Technical}}` | Article | Introductory "101" level courses providing clear foundational explanations |
| `{{Missing information}}` | Section | Specific lecture content filling knowledge gaps |
| `{{Unreferenced section}}` | Section | Course readings and citations for unsourced content |
| `{{No reliable sources}}` | Article | Stable MIT OCW links for niche technical subjects |
| `{{Refideas}}` | Talk page | Links to courses already being considered as sources |

**Media templates:**

| Template | Type | What OCW can provide |
|---|---|---|
| `{{Image requested}}` | Talk page | Diagrams, schematics, and slide decks from galleries |
| `{{Diagram needed}}` | Talk page | Technical diagrams from course PDFs and slides |
| `{{Video requested}}` | Talk page | YouTube lecture recordings |

**Approach with Quarry (preferred):**

1. **Run a single SQL query** to get all articles in OCW-relevant categories that have maintenance templates, joined with quality ratings and pageview data.
2. **Filter by quality** — restrict to Stub/Start/C-class where OCW contributions would have the most impact. Ignore GA/FA articles.
3. **Filter by template type** — prioritize `{{Missing information}}` and `{{Citation needed}}` over generic templates.
4. **Match against OCW courses** by topic overlap. A `{{Missing information}}` on a thermodynamics article matches courses with "Thermodynamics" in lecture titles.
5. **Score by specificity.** A `{{Citation needed}}` tag matched against "Lecture 7: Multielectron Atoms" is a direct, high-value hit.
6. **Generate specific edit suggestions:** "Add citation from OCW 5.111SC Lecture 7 for the claim about electron shielding effect."

**Approach without Quarry (fallback):**
Use `action=query&list=embeddedin` with each template name, paginating through results. Then cross-reference with category membership and quality ratings via API calls. Slower but doesn't require credentials.

### Tier 2: Term-overlap discovery

For courses without obvious template targets, use lecture titles as search queries.

**Approach:**

1. **Extract keyword phrases from lecture titles.** "Lecture 12: The Shapes of Molecules: VSEPR Theory" → query terms: `["VSEPR theory", "molecular shapes", "valence shell electron pair repulsion"]`
2. **Query Wikipedia API.** Use `action=opensearch` or `list=search` with each phrase. Lecture titles are essentially pre-written Wikipedia topic names.
3. **Compute text similarity.** Simple cosine similarity between the lecture title (cleaned) and Wikipedia article titles/opening paragraphs. A lecture titled "Schrödinger Equation" against the article "Schrödinger equation" is a near-perfect match.
4. **Rank matches by:**
   - Text similarity score (exact title match > partial > topic overlap)
   - Asset richness of the lecture (video + transcript > lecture notes only > no assets)
   - Course level alignment (introductory OCW course → introductory Wikipedia article)

### Tier 3: Structural gap analysis

Broader matches where OCW fills known gaps in Wikipedia's coverage.

**Approach:**

1. **Compare OCW topic hierarchy to Wikipedia category tree.** Courses in OCW topics with sparse Wikipedia category coverage are candidates for new "Further reading" or "External links" sections.
2. **Identify "thin" articles.** Use the Web API's `prop=info` with `inprop=size` (or a Quarry SQL query on `page_len`) to find articles below a byte threshold in topic areas where OCW has extensive courses.
3. **Map course asset types to Wikipedia needs:**
   - Heavy `[Reading-List]` courses → candidates for "Further reading" sections in Wikipedia
   - `[Image-Gallery]` and diagram assets → candidates for Wikimedia Commons upload
   - `[Video-Transcript]` lectures → candidates for "External links" with educational video

## Prioritization framework

The most impactful targets share a combination of signals. These can be obtained from Wikipedia's quality assessment, WikiProject ratings, and pageview data — all accessible via the API or Quarry.

### Quality signals

Articles in Wikipedia have quality classes on their Talk pages, set by WikiProject members:

| Class | Meaning | OCW priority |
|---|---|---|
| FA / GA | Featured / Good article | Low — already well-sourced |
| B | Mostly complete | Low — likely has sufficient references |
| C | Substantial but missing key content | **High** — likely to have templates requesting help |
| Start | Basic but incomplete | **High** — early stage, needs substantial work |
| Stub | Very short | **Medium** — may need creation-level help |
| List, Disambig | Non-article pages | Low |

[ORES](https://en.wikipedia.org/wiki/Wikipedia:Content_assessment) (Objective Revision Evaluation Service) provides AI-predicted quality scores via `api.wikimedia.org/service/lw/inference/v1/models/{model}:predict`. This is being migrated to the [Lift Wing](https://wikitech.wikimedia.org/wiki/Machine_Learning/LiftWing) system.

### WikiProject signals

WikiProjects are topic-aligned editing groups (e.g., WikiProject Chemistry, WikiProject Physics, WikiProject History). Each project maintains:

- An article list (all articles within their scope)
- Quality and importance ratings for each article
- "Popular pages" reports

WikiProject Popular pages reports are the single most useful prioritization tool. A bot generates [monthly lists](https://en.wikipedia.org/wiki/Wikipedia:WikiProject) for each project showing ~1,000 articles ranked by pageviews, with quality and importance ratings.

A typical Popular pages entry:
```
Rank | Article | Views/month | Quality | Importance
 1   | Chemistry | 450,000 | B | Top
45   | Chemical bond | 85,000 | C | High
92   | VSEPR theory | 32,000 | C | Mid
```

The high-impact quadrant for OCW is:
- **High traffic** (top quartile of pageviews within a WikiProject)
- **High importance** (Top or High importance rating)
- **Low quality** (Stub, Start, or C-class)
- **With maintenance templates** (actively requesting help)

### Unified scoring model

For each candidate article, compute a match score against each OCW course:

| Factor | Weight | How to compute |
|---|---|---|
| Template match | 30% | Does the Wikipedia article have a maintenance template relevant to the OCW course's topic? |
| Quality gap | 20% | Is the article C-class or below (higher score for larger gap) |
| Page traffic | 15% | Monthly pageviews from Popular pages report |
| Title similarity | 15% | Overlap between lecture title and article title |
| Asset richness | 10% | Does the OCW course have video, transcripts, or downloadable diagrams? |
| Topic alignment | 10% | Is the OCW course topic in the same WikiProject? |

**Threshold:** Only generate crossref links for matches above a minimum score. Keep the bridge section to 3-5 per course.

### Execution order

1. **First pass:** Run Popular pages filtering across WikiProjects matching OCW topics. Identify articles in the high-impact quadrant (high traffic × high importance × low quality × maintenance templates). These are the strongest candidates.
2. **Second pass:** Lecture title matching against remaining high-traffic articles.
3. **Third pass:** Broad topic-based matching for comprehensive coverage.

## Concrete process (per course)

For a single course page, the cross-reference script would:

1. **Build search term list** from:
   - `course_id` and `title` (e.g., "5.111SC Principles of Chemical Science")
   - `ocw_topics` array (e.g., "Chemistry", "Inorganic Chemistry", "Physical Chemistry")
   - Individual lecture titles (most specific)
2. **Hit Wikipedia API** for each term, deduplicate results
3. **Score each match** against the model above
4. **Select top 3-5 matches** for the Wikipedia Bridge section
5. **Generate output:**
   - Wikipedia Bridge section on the course page with pre-formatted `{{cite web}}` templates
   - A `wiki/crossrefs/{article-slug}.md` page aggregating all OCW courses referencing the same Wikipedia article
   - Specific edit suggestions where templates are found

## Crossref hub pages

The `wiki/crossrefs/` directory would contain one page per Wikipedia article that multiple OCW courses can improve:

```markdown
---
id: xref-vsepr-theory
type: crossref
wikipedia_article: "VSEPR theory"
ocw_courses: ["5.111SC", "5.112"]
match_methods: ["lecture-title"]
---

# Wikipedia: VSEPR theory → OCW Resources

## Maintenance templates found
- `{{Missing information|about=differences between VSEPR and MO theory}}`

## Related OCW Courses
- [[5.111SC Principles of Chemical Science]] — Lecture 12, video + transcript
- [[5.112 Principles of Chemical Science]] — Lectures 12-13, lecture notes

## Suggested edits
1. Use 5.111SC Lecture 12 to add a comparison of VSEPR and MO theory
2. Cite the course reading list as "Further reading"
3. Upload molecular geometry diagrams to Wikimedia Commons
```

These pages serve as a "Wikipedia gap map" — they show which articles have the most OCW resources pointed at them.

## Implementation considerations

1. **Breadth vs. depth.** 2,573 courses × 5 matches = ~13,000 crossrefs. This is a lot. A quality threshold is needed — only match when relevance is high or maintenance templates are found.
2. **Wikipedia API rate limits.** The API is public but rate-limited. Use `User-Agent` header, add delays between requests, and consider batching.
3. **Two-way linking.** Each crossref links both ways: course → Wikipedia AND crossref page → all OCW courses. This builds the "gap map."
4. **Targeted first pass.** Start with Tier 1 (template index). Use `embeddedin` to find pages with specific templates in OCW's topic areas. These are the highest-ROI matches — a clear action is already requested.
5. **Script location.** This would be a `scripts/crossref-wikipedia.py` following the same pattern as `scan-assets.py`.
