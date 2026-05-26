# Overview

MIT OpenCourseWare publishes materials from **2,577 courses** across **37 departments** and **110 topics**, spanning all five MIT schools (Engineering, Science, Humanities/Arts/Social Sciences, Architecture/Planning, Management) plus the Schwarzman College of Computing.

All content is CC BY-NC-SA 4.0 licensed — freely usable with attribution. Course materials include lecture notes, video transcripts, problem sets, reading lists, and image galleries.

This wiki catalogs every course, links them by department, topic, and instructor, and cross-references them against Wikipedia to identify where MIT's open educational materials can improve the world's encyclopedia.

## Current state

- Courses ingested: **2,577** (all courses from MIT Learn API)
- Course pages with asset scans: **12** (hybrid-scanned; remaining 2,565 have basic metadata)
- Departments: **37** | Topics: **110** | Instructors: **2,142**
- Wikipedia cross-references: **57 candidate matches** across **9 WikiProjects** (demo; see [[crossref-summary]])
- Contribution Impact Matrix: **8 WikiProjects, 6,500 articles** visualized in standalone HTML (see wiki/impact-matrix/standalone.html)
- Match Heatmap: **18 OCW departments × 9 WikiProjects** interactive matrix (see [[crossref-heatmap]])

## Tools built

- **OCW Course Wiki** — 2,577 interlinked course pages with YAML frontmatter, typed assets, instructor index, and department pages
- **Match Heatmap** — cross-reference matrix showing where OCW departments overlap with Wikipedia WikiProjects
- **Contribution Impact Matrix** — D3.js bubble scatterplot surfacing high-impact Wikipedia articles by quality, pageviews, importance, and maintenance templates

## Next steps

See `docs/ROADMAP.md` for the full plan. In brief:

1. **Wire OCW match data into the Impact Matrix** (MIT Mode)
2. **Build per-article match lookup** (Matchmaker API Phase 1)
3. **Build contribution interface** — work queue for applying OCW-based edits to Wikipedia
