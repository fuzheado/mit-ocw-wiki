# Scalability & Domain Classification

## Context

The Contribution Impact Matrix currently handles 13 WikiProjects (11,500 articles)
in a single self-contained HTML file (~2.8 MB). The project has 942 WikiProjects
with Popular pages available. This document analyzes whether the single-file
architecture scales, and how to organize 942 projects for discoverability.

## Scalability Analysis

### Data Size Scaling

| Metric | 13 projects | 50 projects | 942 projects |
|--------|-------------|-------------|--------------|
| live-data.js | 2.8 MB | ~11 MB | ~203 MB |
| standalone.html | 2.8 MB | ~11 MB | ~203 MB |
| Browser script parse time | ~80 ms | ~300 ms | ~6-10 s |
| DOM memory estimate | ~15 MB | ~60 MB | ~1+ GB |

**Finding**: The single-file approach breaks well before 942 projects. Around 50-80
projects the standalone HTML becomes unwieldy (~10-15 MB). At 942, it is
unusable — browsers struggle with script parsing past 50-100 MB and memory
pressure becomes critical.

### Generation Time Scaling

| Phase | Per project | 942 projects (cold) | 942 projects (warm cache) |
|-------|-------------|---------------------|---------------------------|
| Popular pages fetch | ~1 s | ~15 min | ~15 min |
| SQL templates | ~2-5 s | ~30-60 min | ~30-60 min |
| Wikitext context (cold) | ~30-60 s | ~8-16 hr | ~10 min |
| Total | ~35-65 s | ~9-18 hr | ~55-85 min |

**Finding**: Generation time is acceptable with caching. The wikitext context
phase is the bottleneck (one API call per templated article). Once cached,
re-generation is fast. SQL queries are consistent regardless of cache state.

### Versioning Gap

The current format has no ingestion timestamp per project. If History is added
today and Geology tomorrow, and neither is refreshed for 6 months, there is no
signal that one dataset is staler than the other.

## Approaches Evaluated

### Option 1: Status Quo (Single File)

**How**: Keep appending to standalone.html as projects are added.

**Pros**: Simple, one file, no architectural changes.

**Cons**: 203 MB at scale — browsers cannot parse this. No per-project freshness.
Flat dropdown of 942 items with no search.

**Verdict**: Does not scale. Rejected.

### Option 2: Per-Project JS Files + Manifest

**How**: Each project gets its own `.js` file in `data/` (~200 KB each). A
`manifest.js` file lists all projects with metadata (slug, name, article count,
ingestion date, domain). The HTML loads the manifest via `<script>` tag, then
dynamically loads the chosen project's JS file on selection.

**Structure**:
```
wiki/impact-matrix/
  index.html           loads manifest + lazy-loads project JS
  standalone.html      embeds top-N projects (configurable)
  data/
    manifest.js        var MANIFEST = { ... }
    wp_environment.js  var PROJECT_DATA = { ... }
    wp_history.js      ...
```

**Key technical detail**: `<script src="...">` works from `file://` for
same-directory files. The earlier JSONP failure was about loading from
`en.wikipedia.org` (cross-origin). Local `.js` files in the same directory
load and execute without CORS restrictions.

**Pros**: ~200 KB loaded per project (not 203 MB). Per-project `date_gen` for
freshness tracking. Searchable picker reads from manifest (no directory scan).

**Cons**: Changes the architecture. Standalone becomes a multi-file tool unless
embedding is configurable.

**Verdict**: Best path forward. Selected.

### Option 3: Domain Packs

**How**: Group projects into ~15 domain bundles (e.g., "Science", "History",
"Arts"). Each pack is one JS file (~10-15 MB).

**Pros**: Fewer files than Option 2. Simpler loading scheme.

**Cons**: Each pack is 10-15 MB — still heavy. Less granular freshness tracking.
Cannot load individual projects.

**Verdict**: Middle ground but worse UX than Option 2. Rejected.

### Option 4: JSON Manifest + SQLite-in-the-Browser

**How**: Use a binary format or IndexedDB for client-side data storage.

**Pros**: Efficient storage, queryable.

**Cons**: Does not work from `file://` (IndexedDB requires a protocol like
http:// or https:// in most browsers). Adds significant complexity.

**Verdict**: Breaks the core constraint (`file://` compatibility). Rejected.

## Domain Classification Research

### Problem

942 WikiProjects need to be organized into categories so the picker is
navigable. Wikipedia has no official taxonomy for WikiProjects, and the
project names range from single words ("History") to compound hierarchies
("Agriculture/Livestock task force").

### Approach

Keyword-based whole-word matching with exclusion rules. Each domain defines:
- A set of match keywords (checked as `\bword\b` against the lowercased name)
- A set of exclusion terms (if matched, skip this domain)

Classification evaluates rules in priority order; first match wins.

### Data Source

The Community Tech bot maintains the canonical list at:
https://en.wikipedia.org/wiki/User:Community_Tech_bot/Popular_pages

This is the authoritative source — 942 projects. A single API call
(`action=parse`) returns the rendered page. Project names are extracted via
regex from wikilinks matching the pattern
`Wikipedia:WikiProject_{name}/Popular_pages`.

The alternative approach — querying the `enwiki_p` database for all distinct
`pap_project_title` values then batch-checking each via API — produced 2,993
false positives (sub-projects, task forces, redirects). The bot's page is the
correct source.

## Taxonomy Development

### Starting Point: Vital Articles

The initial ad-hoc keyword classification produced 25 domains with 334
uncategorized projects — too many categories, too many misses.

Wikipedia's own article-level taxonomy — the **Vital Articles hierarchy** 
(https://en.wikipedia.org/wiki/Template:Vital_articles) — was adopted as 
the structural backbone. Vital Articles organizes Wikipedia's most important 
10,000 (Level 4) and 50,000 (Level 5) articles into 11 top-level categories:

```
Level 4 categories:              Level 5 subcategories:
  People                           Writers, Artists, Entertainers, Philosophers,
                                   Religious figures, Politicians, Military,
                                   Scientists, Sports figures, Miscellaneous
  History                          (flat)
  Geography                        Basics, Physical, Regions & countries, Cities
  Arts                             Audiovisual arts, Narrative arts
  Philosophy and religion          (flat)
  Everyday life                    Sports, games and recreation
  Society and social sciences      Social studies, Politics & economics, Culture
  Biological and health sciences   Biology, Animals, Plants, Health
  Physical sciences                Basics & measurement, Astronomy, Chemistry,
                                   Earth science, Physics
  Technology                       (flat)
  Mathematics                      (flat)
```

This is a community-vetted taxonomy with decades of editorial consensus
behind it. It has clear parent-child structure and balanced granularity.

### Pragmatic Elevation Principle

The Vital hierarchy was designed for **article** classification, not
WikiProject classification. WikiProjects are editor-facing organizational
units, not article topics. Several Vital-level-4 categories bury WikiProject
clusters that editors would naturally look for at the top level.

The **pragmatic elevation principle** states: promote a cluster to a top-level
category when it has high WikiProject volume OR high user discoverability
expectations, even if the strict hierarchy would keep it nested.

Elevation decisions:

| Cluster | Count | Vital slot | Elevated? | Rationale |
|---------|-------|------------|-----------|-----------|
| Geography & Places | 265 | Top-level | Keep | Already top-level; no change needed |
| Sports & Games | 61 | Everyday life → subcategory | ✅ **Yes** | Third-largest cluster. Editors naturally look for "Sports" at top level, not under "Everyday life." |
| Transportation | 81 | Everyday life → implicit | ✅ **Yes** | Large, coherent cluster (aviation, roads, rail, shipping). Vital has no explicit slot; "Transportation" is a top-level search expectation. |
| Business & Economics | 15+ | Society → social sciences → politics & economics | ✅ **Yes** | Systematically undervalued in Vital's hierarchy despite massive article volume and editor interest. Independent top-level improves discoverability. |
| People & Biography | 32+ | Top-level | Keep | Small WikiProject count but largest article domain on Wikipedia. Vital correctly has it at top level. |
| Arts & Culture (Music/Film/Literature/Visual/Performing) | 57 | Arts → 5 subcategories | **Merge** | Splitting 57 projects into 5 separate picker categories adds noise. Unified "Arts & Culture" with sub-filters is more navigable. |
| Health, Medicine & Biology | 78 | Biological and health sciences → 4 subcats | **Expand** | Absorbs ~50 animal/plant/fungi subfields from uncategorized. Kept as top-level per Vital. |
| Philosophy & Religion | 27 | Top-level (merged) | Keep | Vital keeps them together; editors expect them grouped. |
| Society & Social Sciences | 27 | Top-level | Keep | Politics, Law, Education, Media logically cohere. |
| Education | 11 | Society → implicit | **NOT elevated** | 11 projects don't warrant their own slot; fine under Society. |
| Media & Journalism | 7 | Society → implicit | **NOT elevated** | Similar — small cluster, fits Society. |
| Agriculture & Food | 9 | Everyday life → implicit | **Merge into "Everyday Life & Food"** | Remnant of Everyday life after Sports/Transport elevated. |
| "Wikipedia" self-reference | ~30 | No Vital equivalent | ✅ **NEW category** | Abandoned articles, Disambiguation, Lists — no article-level taxonomy can classify these. |
| Military | ~20 | History | **NOT elevated** | Absorbed into History (Vital has no separate Military top-level). |

### Final Taxonomy (15 categories)

```
 1. Geography & Places         265  — countries, US states, cities, regions
 2. History                     91  — history, military, archaeology, medieval
 3. Sports & Games              61  — elevated from Everyday life
 4. Transportation              81  — elevated from Everyday life; aviation, roads, rail, shipping
 5. Health, Medicine & Biology  78  — expanded to absorb animal/plant/fungi subfields
 6. Arts & Culture              57  — unified from 5 sub-categories (music, film, lit, visual, performing)
 7. Technology & Engineering    19  — computing, electronics, engineering
 8. Society & Social Sciences   27  — politics, law, education, media, sociology
 9. Business & Economics        15  — elevated from Society; commerce, finance, brands
10. Philosophy & Religion       27  — kept together per Vital
11. People & Biography          32  — artists, bands, celebrities (absorbed ~25 from uncategorized)
12. Physical Sciences           20  — physics, astronomy, chemistry, earth sciences
13. Everyday Life & Food         9  — remnants: agriculture, food, drink, amusements
14. Wikipedia Maintenance       30  — NEW: meta-projects with no Vital equivalent
15. Mathematics                  2  — unchanged

Other / Uncategorized          ~80  — genuinely hard-to-classify
────────────────────────────────────
TOTAL                         942
```

### Comparison: Initial vs. Final

| Metric | Initial (ad-hoc) | Final (Vital-inspired) |
|--------|------------------|------------------------|
| Categories | 25 | 15 |
| Uncategorized | 334 | ~80 |
| Top-level elevations | — | Sports, Transportation, Business, Wikipedia Maintenance |
| People coverage | 7 | 32 (absorbed celebrity/band projects) |
| Science coverage | 28 (Health) + 11 (Physics) + 8 (Earth) + 4 (Chemistry) + 2 (Math) = 53 | 78 (Health/Biology) + 20 (Physical) + 2 (Math) = 100 — absorbed animal/plant niches |
| Source of authority | Ad-hoc keyword rules | Wikipedia's Vital Articles hierarchy + pragmatic elevation |

### Future Evolution

This taxonomy is not frozen. If a future analysis shows that "Transportation"
is being confused with "Technology & Engineering" in user testing, or that
"Philosophy & Religion" should split, the classification rules in
`scripts/classify_projects.py` can be updated. The taxonomy is a convenience
for the picker UI — it has no downstream dependencies beyond the manifest.

The broader implication: Wikipedia lacks an official WikiProject directory
with a consistent category system. This project's taxonomy could inform a
future community effort to standardize WikiProject organization, similar
to how the Vital Articles taxonomy standardizes article importance.

### Implementation

The classifier lives in `scripts/classify_projects.py`:

```
Usage:
    python3 scripts/classify_projects.py
```

Outputs:
1. Domain summary table with counts
2. Full list of uncategorized projects (for rule refinement)
3. Sample entries per domain
4. Manifest JSON preview

The classifier is standalone (no DB, no tunnel). It fetches the 942 project
names from the Community Tech bot page, classifies each, and prints results.

### Manifest Structure

The final `manifest.js` will be emitted by `generate-impact-matrix-data.py`
during the Option 2 refactor:

```js
var MANIFEST = {
  "version": 1,
  "generated": "2026-05-14T00:00:00Z",
  "total_projects": 942,
  "total_articles": 0,
  "domains": {
    "Geography & Places": [
      {
        "name": "Japan",
        "slug": "wp_japan",
        "articles": 1000,
        "limit": 1500,
        "date_gen": "2026-05-14T00:00:00Z"
      },
      ...
    ],
    ...
  }
};
```

## Final Decision

**Option 2 (Per-Project JS Files + Manifest) is selected as the implementation
path.**

Three-phase implementation plan:

1. **Data generation** — Update `generate-impact-matrix-data.py` to emit
   per-project JS files (`wp_{slug}.js`) alongside `manifest.js`. Each file
   contains `var PROJECT_DATA = { ... }`. The manifest gets a `date_gen`
   timestamp per project.

2. **Index.html** — Add `manifest.js` as a second script load. Rewrite the
   picker to read from `MANIFEST.domains` and show a grouped, searchable
   dropdown. On project selection, dynamically create a `<script>` tag for
   the project's JS file and initialize the visualization.

3. **Standalone** — Keep `standalone.html` working for a configurable subset
   (currently the 13 projects) by embedding both manifest and project data
   inline. The `--build` flag accepts `--standalone-projects=N` to control
   how many to embed.
