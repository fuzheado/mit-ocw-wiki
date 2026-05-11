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

**Approach:**

1. **Build a template index.** Use `action=query&list=embeddedin` with each template name to find Wikipedia pages containing maintenance templates, filtered to topic categories matching OCW's hierarchy (110 topics).
2. **Match templates to OCW courses by topic overlap.** A `{{Missing information}}` tag on a thermodynamics article matches courses with "Thermodynamics" in lecture titles.
3. **Score by specificity.** A `{{Citation needed}}` tag matched against "Lecture 7: Multielectron Atoms" is a direct, high-value hit. A generic `{{More citations needed}}` template on "Chemistry" is weak.
4. **Generate specific edit suggestions:** "Add citation from OCW 5.111SC Lecture 7 for the claim about electron shielding effect."

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
2. **Identify "thin" articles.** Use the Web API's `prop=info` with `inprop=size` to find articles below a byte threshold in topic areas where OCW has extensive courses.
3. **Map course asset types to Wikipedia needs:**
   - Heavy `[Reading-List]` courses → candidates for "Further reading" sections in Wikipedia
   - `[Image-Gallery]` and diagram assets → candidates for Wikimedia Commons upload
   - `[Video-Transcript]` lectures → candidates for "External links" with educational video

## Scoring model

Each potential match between an OCW course/lecture and a Wikipedia article should get a score:

| Factor | Weight | How to compute |
|---|---|---|
| Template match | 40% | Does the Wikipedia article have a maintenance template relevant to the OCW course's topic? |
| Title similarity | 25% | Cosine similarity or simple overlap between lecture title and article title |
| Asset richness | 15% | Does the OCW course have video, transcripts, or downloadable diagrams for this topic? |
| Topic alignment | 10% | Is the OCW course topic in the same Wikipedia category? |
| License compatibility | 10% | CC BY-NC-SA materials can be cited; some assets can be uploaded to Commons |

**Threshold:** Only generate crossref links for matches above a minimum score. Keep the bridge section to 3-5 per course.

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
