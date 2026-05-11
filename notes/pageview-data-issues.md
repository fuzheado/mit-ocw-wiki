# Pageview Data: Issues & Resolution

## The problem

The Contribution Impact Matrix needs monthly pageviews for every article to plot them on the Y-axis. We tried three approaches:

### 1. SQL: `page_props` → `pageview_daily_average`

**Result: 0 rows.** The `enwiki_p` analytics replica (MariaDB) does not have the `pageview_daily_average` property populated in `page_props`. This prop is set by the Community Tech bot and only exists on the production Wiki replicas, not the analytics replicas available via Toolforge SSH tunnel.

Other `page_props` entries exist (`wikibase_item`, `page_image_free`, etc.) but none contain pageview or traffic data.

**Relevant tables checked and absent:**
- `page_props` WHERE `pp_propname = 'pageview_daily_average'` → 0
- No `pageview`, `popular`, or `traffic` tables exist in `enwiki_p`

### 2. REST API: `/metrics/pageviews/per-article/.../monthly/`

**Result: Rate-limited heavily.** The Wikimedia pageview REST API returns HTTP 429 after ~10-20 sequential requests. Even with:
- 5 parallel workers → immediate 429s
- Sequential single-threaded requests → 429s after ~15 requests
- 0.5s delay between batches → still 429s

The monthly endpoint appears to have a stricter rate limit than the general API. Only ~3% of articles (24/800) returned data in our last attempt.

The API works for individual, ad-hoc lookups but cannot sustain batch fetching of 100-800 articles.

### 3. REST API fallback: daily endpoint, different date ranges

Trying `daily/` instead of `monthly/`, or shifting date ranges, did not improve results. The rate limit is per-endpoint and per-IP. Multiple sequential requests to the same endpoint trigger it regardless of date range.

## The solution: WikiProject Popular pages

Every WikiProject with Popular pages enabled has a page like:
`https://en.wikipedia.org/wiki/Wikipedia:WikiProject_Environment/Popular_pages`

This is a **pre-compiled monthly table** maintained by the Community Tech bot containing:
- Rank (1-1000)
- Article title
- Monthly views (exact number)
- Daily average
- Assessment/quality (Stub, Start, C, B, GA, FA)
- Importance (Low, Mid, High, Top)

**Advantages:**
- Already has accurate pageview counts (no API calls needed)
- Already has quality and importance ratings (confirmed matching our SQL data)
- Covers the top 1000 articles per project (more than enough for the scatterplot)
- Available via the standard `action=parse` API in a single request

**Disadvantages:**
- Only ~500 WikiProjects generate Popular pages (the user notes others can be requested)
- Only covers the top 1000 articles per project (not all assessed articles)
- The page is updated monthly (fine for our purposes)

## Implementation plan

1. Fetch Popular pages via `action=parse&page=Wikipedia:WikiProject_{name}/Popular_pages`
2. Parse the wikitable: 6 columns (Rank, Title, Views, DailyAvg, Assessment, Importance)
3. Join with SQL query for template data (the SQL part works fine — only pageviews were broken)
4. For projects without Popular pages: fall back to SQL-only with a "no pageview data" notice
5. Cache results locally so repeated loads are instant
