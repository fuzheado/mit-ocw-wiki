# All batches complete — summary

## What was done
All 26 API pages (offsets 0-2500) were processed:
- 2,573 course pages created (out of 2,577 in API — 4 OLL-hosted courses have non-OCW URLs)
- 2,142 instructor pages created
- 37 department pages updated with course links
- 110 topic pages updated with course links

## Anomalies
- 2 courses at offset 2400 had `null` slug in runs data — handled by falling back to URL
- 5 courses at offsets 2400-2500 point to `openlearninglibrary.mit.edu` instead of `ocw.mit.edu` — their slugs are full URLs (ugly but present)
- The script had to be fixed twice mid-run (null slug handling, missing `page_path`)

## State
- courses_bootstrap: **complete**
- Asset scanning, Wikipedia crossref, and lint stages remain
