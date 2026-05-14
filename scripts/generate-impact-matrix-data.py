#!/usr/bin/env python3
"""Offline data generation for the Contribution Impact Matrix.

Fetches Popular pages, runs SQL queries for templates/metadata,
parses wikitext context with mwparserfromhell, and assembles into live-data.js.

Usage:
    python3 scripts/generate-impact-matrix-data.py
        Generate data for all default projects (8 OCW-aligned).

    python3 scripts/generate-impact-matrix-data.py --list
        List all available WikiProjects with Popular pages.

    python3 scripts/generate-impact-matrix-data.py --projects Chemistry,Physics
        Generate for specific projects only.

    python3 scripts/generate-impact-matrix-data.py --build
        Also rebuild standalone.html after generation.

    python3 scripts/generate-impact-matrix-data.py --skip-sql
        Skip SQL queries (no SSH tunnel needed), use cached data.

    python3 scripts/generate-impact-matrix-data.py --test-cache
        Run a cache timing verification test against a known article.
"""

import os
import sys
import re
import json
import time
import argparse
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import quote

import pymysql
from dotenv import load_dotenv
import mwparserfromhell

from wiki_cache import persistent_wiki_cache, WIKI_UA

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WIKI_DIR = PROJECT_ROOT / 'wiki'
DATA_DIR = WIKI_DIR / 'impact-matrix' / 'data'
INDEX_HTML = WIKI_DIR / 'impact-matrix' / 'index.html'
STANDALONE_HTML = WIKI_DIR / 'impact-matrix' / 'standalone.html'
LIVE_DATA_JS = DATA_DIR / 'live-data.js'
ENV_FILE = PROJECT_ROOT / '.env'
TUNNEL_PORT = 3306
TUNNEL_HOST = '127.0.0.1'

TEMPLATE_TARGETS = (
    'Citation_needed', 'Cn', 'Fact', 'Cite',
    'Refimprove', 'Sources', 'Cites',
    'Primary_sources', 'Primarysources',
    'Better_source_needed', 'Bsn',
    'Technical', 'Too_technical', 'Overly_technical',
    'Missing_information', 'Expand_section', 'Gap',
    'Unreferenced_section', 'Urs',
    'Scientific_verification', 'Verify',
)

TALK_TEMPLATE_TARGETS = (
    'Image_requested', 'Needs_image', 'Imagerequest',
    'Diagram_needed', 'Needs_diagram',
    'Video_requested', 'Needs_video',
)

DEFAULT_PROJECTS = [
    'Environment', 'Chemistry', 'Biology', 'Physics',
    'Computer science', 'Mathematics', 'Medicine', 'Business',
]

TEMPLATE_EXPLANATIONS = {
    'Citation needed': 'A specific claim needs a reliable source.',
    'Cn': 'A specific claim needs a reliable source.',
    'Fact': 'A specific claim needs a reliable source.',
    'Cite': 'A specific claim needs a reliable source.',
    'Refimprove': 'Article needs more references to reliable sources.',
    'Sources': 'Article needs more references to reliable sources.',
    'Cites': 'Article needs more references to reliable sources.',
    'Primary sources': 'Relies too heavily on primary sources.',
    'Primarysources': 'Relies too heavily on primary sources.',
    'Better source needed': 'The existing source is weak or outdated.',
    'Bsn': 'The existing source is weak or outdated.',
    'Technical': 'Article is too technical for a general audience.',
    'Too technical': 'Article is too technical for a general audience.',
    'Overly technical': 'Article is too technical for a general audience.',
    'Missing information': 'Article is missing important information.',
    'Expand section': 'A section is too brief and should be expanded.',
    'Gap': 'There is a gap in the article content.',
    'Unreferenced section': 'A section has no sources at all.',
    'Urs': 'A section has no sources at all.',
    'Scientific verification': 'Scientific claims need verification.',
    'Verify': 'The accuracy of this claim is disputed.',
    'Image requested': 'The article could benefit from an image.',
    'Needs image': 'The article could benefit from an image.',
    'Imagerequest': 'The article could benefit from an image.',
    'Diagram needed': 'A diagram or illustration would help explain this.',
    'Needs diagram': 'A diagram or illustration would help explain this.',
    'Video requested': 'The article could benefit from video content.',
    'Needs video': 'The article could benefit from video content.',
}


def val(v):
    if isinstance(v, bytes):
        return v.decode('utf-8')
    return v


def get_db():
    return pymysql.connect(
        host=TUNNEL_HOST, port=TUNNEL_PORT,
        user=os.getenv("TOOLFORGE_SQL_USER"),
        password=os.getenv("TOOLFORGE_SQL_PASSWORD"),
        database='enwiki_p', cursorclass=pymysql.cursors.DictCursor,
        charset='utf8mb4', connect_timeout=10
    )


# ─── CACHED API CALLS ───

@persistent_wiki_cache(ttl=604800)
def fetch_popular_pages(project, limit=500):
    """Fetch and parse a WikiProject's Popular pages table.

    URL: Wikipedia:WikiProject_{name}/Popular_pages
    Generated monthly by Community Tech bot for ~500 WikiProjects.

    Returns: list of dicts {title, views, quality, importance} or None.
    """
    project_enc = project.replace(' ', '_')
    page_title = f"Wikipedia:WikiProject_{project_enc}/Popular_pages"
    url = (
        f"https://en.wikipedia.org/w/api.php"
        f"?action=parse&page={quote(page_title)}&prop=text&format=json"
    )
    try:
        req = Request(url, headers={'User-Agent': WIKI_UA})
        data = json.loads(urlopen(req, timeout=15).read())
        html = data['parse']['text']['*']
    except Exception:
        return None

    table_match = re.search(
        r'<table class="wikitable[^>]*>.*?</table>', html, re.DOTALL
    )
    if not table_match:
        return None

    articles = []
    rows = re.findall(r'<tr>.*?</tr>', table_match.group(), re.DOTALL)
    for row in rows[1:]:
        cells = re.findall(r'<td[^>]*>.*?</td>', row, re.DOTALL)
        if len(cells) < 6:
            continue

        title_match = re.search(r'<a[^>]*>([^<]+)</a>', cells[1])
        if not title_match:
            continue
        title = title_match.group(1).strip()

        views_text = re.sub(r'<[^>]+>', '', cells[2]).strip().replace(',', '')
        try:
            views = int(re.search(r'[\d]+', views_text).group())
        except Exception:
            views = None

        quality = re.sub(r'<[^>]+>', '', cells[4]).strip()
        importance = re.sub(r'<[^>]+>', '', cells[5]).strip()

        if quality not in ('FA', 'GA', 'B', 'C', 'Start', 'Stub', 'List', 'FL', 'A'):
            quality = None
        if importance not in ('Top', 'High', 'Mid', 'Low'):
            importance = None

        articles.append({
            "title": title,
            "views": views,
            "quality": quality,
            "importance": importance,
        })
        if len(articles) >= limit:
            break

    return articles


@persistent_wiki_cache(ttl=None)
def fetch_wikitext(title):
    """Fetch raw wikitext for an article via action=parse&prop=wikitext.

    This is the expensive call (~1-2 sec per article). Cached indefinitely
    so re-runs are nearly instant.
    """
    url = (
        f"https://en.wikipedia.org/w/api.php"
        f"?action=parse&page={quote(title)}&prop=wikitext&format=json"
    )
    try:
        req = Request(url, headers={'User-Agent': WIKI_UA})
        data = json.loads(urlopen(req, timeout=15).read())
        return data['parse']['wikitext']['*']
    except Exception:
        return None


# ─── SQL QUERIES (not cached — fast < 1s per batch) ───

def get_batch_templates(conn, titles):
    """Batch-query template data for article titles.

    Two queries: article-body templates + talk-page templates.
    Uses templatelinks → linktarget join (post-migration schema).

    Returns: dict title → [display names with spaces].
    """
    if not titles:
        return {}
    result = {}
    try:
        for i in range(0, len(titles), 50):
            batch = titles[i:i + 50]
            ph = ','.join(['%s'] * len(batch))
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT p.page_title,
                           GROUP_CONCAT(DISTINCT lt.lt_title SEPARATOR ',') AS tmpl
                    FROM page p
                    LEFT JOIN templatelinks tlt ON tlt.tl_from = p.page_id
                    LEFT JOIN linktarget lt ON tlt.tl_target_id = lt.lt_id
                        AND lt.lt_namespace = 10
                        AND lt.lt_title IN (""" + ','.join('%s' for _ in TEMPLATE_TARGETS) + """)
                    WHERE p.page_title IN (""" + ph + """) AND p.page_namespace = 0
                    GROUP BY p.page_id
                """, TEMPLATE_TARGETS + tuple(batch))
                for r in cur.fetchall():
                    t = val(r['page_title'])
                    s = val(r['tmpl']) if r['tmpl'] else ''
                    result[t] = [x.replace('_', ' ') for x in s.split(',') if x]

                cur.execute("""
                    SELECT p2.page_title,
                           GROUP_CONCAT(DISTINCT lt.lt_title SEPARATOR ',') AS talk_tmpl
                    FROM page p2
                    LEFT JOIN page tp ON tp.page_title = p2.page_title AND tp.page_namespace = 1
                    LEFT JOIN templatelinks tlt ON tlt.tl_from = tp.page_id
                    LEFT JOIN linktarget lt ON tlt.tl_target_id = lt.lt_id
                        AND lt.lt_namespace = 10
                        AND lt.lt_title IN (""" + ','.join('%s' for _ in TALK_TEMPLATE_TARGETS) + """)
                    WHERE p2.page_title IN (""" + ph + """) AND p2.page_namespace = 0
                    GROUP BY p2.page_id
                """, TALK_TEMPLATE_TARGETS + tuple(batch))
                for r in cur.fetchall():
                    t = val(r['page_title'])
                    s = val(r['talk_tmpl']) if r['talk_tmpl'] else ''
                    talk_list = [x.replace('_', ' ') for x in s.split(',') if x]
                    if t in result:
                        result[t].extend(talk_list)
                    else:
                        result[t] = talk_list
    except pymysql.err.OperationalError as e:
        print(f"    [SQL error] {e}")
        return {}
    return result


def get_article_metadata(conn, titles):
    """Batch-query short description, last edit date, and article size.

    Returns: dict title → {short_desc, touched, page_len}.
    """
    if not titles:
        return {}
    result = {}
    try:
        for i in range(0, len(titles), 50):
            batch = titles[i:i + 50]
            ph = ','.join(['%s'] * len(batch))
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT p.page_title, p.page_touched, p.page_len,
                           pp.pp_value AS short_desc
                    FROM page p
                    LEFT JOIN page_props pp
                        ON pp.pp_page = p.page_id
                        AND pp.pp_propname = 'wikibase-shortdesc'
                    WHERE p.page_title IN (""" + ph + """) AND p.page_namespace = 0
                """, tuple(batch))
                for r in cur.fetchall():
                    t = val(r['page_title'])
                    result[t] = {
                        'short_desc': val(r['short_desc']) if r.get('short_desc') else None,
                        'touched': val(r['page_touched']) if r.get('page_touched') else None,
                        'page_len': r.get('page_len'),
                    }
    except pymysql.err.OperationalError as e:
        print(f"    [SQL error] {e}")
        return {}
    return result


# ─── WIKITEXT CONTEXT EXTRACTION ───

def extract_template_context(wikitext, template_names):
    """Parse wikitext with mwparserfromhell and extract context per template.

    For each unique template (deduplicated by text position):
      - Section name (walk sections, find containment)
      - |date= parameter value
      - Preceding sentence context (last \\n\\n before template, within 500 chars)
      - Context type (footnote/infobox/table/blockquote/minimal/inline)

    Returns: list of ctx dicts, or None if no context extracted.
    """
    try:
        parsed = mwparserfromhell.parse(wikitext)
    except Exception:
        return None

    search_names = set()
    for name in template_names:
        search_names.add(name.lower())
        search_names.add(name.replace(' ', '_').lower())

    sections = parsed.get_sections(flat=True)
    ctx_results = []
    seen_positions = set()

    for tmpl in parsed.ifilter_templates(recursive=True):
        tmpl_str = str(tmpl)
        pos = wikitext.find(tmpl_str)
        if pos == -1 or pos in seen_positions:
            continue

        raw_name = tmpl.name.strip()
        if raw_name.lower() not in search_names:
            alt_name = raw_name.replace(' ', '_')
            if alt_name.lower() not in search_names:
                alt_name2 = raw_name.replace('_', ' ')
                if alt_name2.lower() not in search_names:
                    continue

        seen_positions.add(pos)

        section_name = _find_section(sections, tmpl_str, pos, wikitext)
        date_val = _extract_date(tmpl)
        context_text, context_type = _classify_context(wikitext, pos)

        if len(context_text) > 150:
            context_text = context_text[:147] + '...'

        ctx_results.append({
            'name': raw_name,
            'section': section_name,
            'date': date_val,
            'context': context_text,
            'contextType': context_type,
        })

    return ctx_results if ctx_results else None


def _find_section(sections, tmpl_str, pos, full_wikitext):
    """Find the section heading that contains this template position."""
    best_section = ''
    best_start = 0

    for sec in sections:
        sec_text = str(sec)
        sec_pos = full_wikitext.find(sec_text)

        if sec_pos == -1:
            continue

        if sec_pos <= pos < sec_pos + len(sec_text):
            if sec_pos > best_start:
                best_section = _extract_heading(sec_text)
                best_start = sec_pos

    if not best_section:
        for sec in sections:
            sec_text = str(sec)
            sec_pos = full_wikitext.find(sec_text)
            if sec_pos != -1 and sec_pos < pos < sec_pos + len(sec_text):
                best_section = _extract_heading(sec_text)
                break

    return best_section or 'Lead'


def _extract_heading(sec_text):
    """Extract the section heading (content of == ... ==, === ... ===, etc.)."""
    m = re.search(r'^(={2,6})\s*(.+?)\s*\1\s*$', sec_text, re.MULTILINE)
    return m.group(2).strip() if m else ''


def _extract_date(tmpl):
    """Extract the |date= parameter from a template."""
    try:
        date_param = tmpl.get('date')
        raw = date_param.value if hasattr(date_param, 'value') else str(date_param)
        return raw.strip()
    except ValueError:
        return None


def _classify_context(wikitext, pos):
    """Classify the context type and extract preceding sentence.

    The context is ALWAYS the preceding sentence (last \\n\\n before template).
    The context type is determined independently for the detail panel hint.

    Returns: (context_text, context_type)
    """
    before = wikitext[:pos]
    context_text = _extract_preceding_sentence(before)

    # 1. Footnote check (must happen first — checks FULL text before pos)
    last_ref_open = before.rfind('<ref')
    last_ref_close = before.rfind('</ref>')
    if last_ref_open > last_ref_close:
        return context_text, 'footnote'

    window_start = max(0, pos - 500)
    window = wikitext[window_start:pos]

    # 2. Infobox
    if re.search(r'\{\{Infobox\b', window, re.IGNORECASE):
        return context_text, 'infobox'

    # 3. Table
    if '{|' in window:
        return context_text, 'table'

    # 4. Blockquote
    if '<blockquote' in window or '{{Quote' in window:
        return context_text, 'blockquote'

    # 5. Minimal
    if len(context_text.strip()) < 20:
        return context_text if context_text else window[-200:].strip(), 'minimal'

    return context_text, 'inline'


def _extract_preceding_sentence(before_text):
    """Extract the last sentence before a template position.

    Looks for the last \\n\\n preceding the template within 500 chars.
    Falls back to a shorter window if none found.
    """
    cutoff = max(0, len(before_text) - 500)
    recent = before_text[cutoff:]

    double_nl = recent.rfind('\n\n')
    if double_nl != -1:
        return recent[double_nl + 2:]

    single_nl = recent.rfind('\n')
    if single_nl != -1 and single_nl < len(recent) - 1:
        candidate = recent[single_nl + 1:]
        if len(candidate) > 20:
            return candidate

    return recent[-200:]


# ─── PROJECT PROCESSING ───

def process_project(project, limit=500, conn=None, skip_sql=False):
    """Run the full data generation pipeline for one WikiProject.

    Returns: {project, articles, total} or None if project has no Popular pages.
    """
    print(f"\n{'='*60}")
    print(f"Processing: {project}")
    print(f"{'='*60}")

    t_start = time.time()

    articles = fetch_popular_pages(project, limit)
    if not articles:
        print(f"  ✗ No Popular pages for '{project}'")
        return None

    print(f"  ✓ {len(articles)} articles from Popular pages")

    if conn and not skip_sql:
        titles = [a['title'] for a in articles if a['title']]

        print(f"  Fetching template data from SQL...")
        tmpl_map = get_batch_templates(conn, titles)
        print(f"  ✓ Templates for {len(tmpl_map)} articles")

        print(f"  Fetching article metadata from SQL...")
        meta_map = get_article_metadata(conn, titles)
        print(f"  ✓ Metadata for {len(meta_map)} articles")

        for a in articles:
            t = a['title']
            a['templates'] = tmpl_map.get(t, [])
            meta = meta_map.get(t, {})
            a['short_desc'] = meta.get('short_desc')
            a['touched'] = meta.get('touched')
            a['page_len'] = meta.get('page_len')
    else:
        reason = "skip_sql flag" if skip_sql else "no DB connection"
        print(f"  ⚠ Skipping SQL ({reason})")
        for a in articles:
            a['templates'] = []
            a['short_desc'] = None
            a['touched'] = None
            a['page_len'] = None

    templated = [a for a in articles if a.get('templates')]
    print(f"  {len(templated)} articles have templates")

    ctx_count = 0
    for i, a in enumerate(templated):
        wt = fetch_wikitext(a['title'])
        if wt:
            ctx = extract_template_context(wt, a['templates'])
            a['ctx'] = ctx
            if ctx:
                ctx_count += len(ctx)
        else:
            a['ctx'] = None

        if (i + 1) % 25 == 0 or i == len(templated) - 1:
            print(f"    Context: {i+1}/{len(templated)} articles ({ctx_count} templates found)")

    for a in (x for x in articles if not x.get('templates')):
        a['ctx'] = None

    elapsed = time.time() - t_start
    print(f"  ✓ Done ({elapsed:.0f}s)")

    return {
        "project": project,
        "articles": articles,
        "total": len(articles),
    }


def list_projects(db_conn):
    """Query enwiki_p for all WikiProjects with assessed articles."""
    try:
        with db_conn.cursor() as cur:
            cur.execute("""
                SELECT pap.pap_project_title, COUNT(*) AS cnt
                FROM page_assessments_projects pap
                JOIN page_assessments pa ON pap.pap_project_id = pa.pa_project_id
                JOIN page p ON pa.pa_page_id = p.page_id
                WHERE p.page_namespace = 0
                  AND pa.pa_class IN ('Stub','Start','C','B','GA')
                GROUP BY pap.pap_project_title
                HAVING cnt >= 10
                ORDER BY cnt DESC
            """)
            return [(val(r['pap_project_title']), r['cnt']) for r in cur.fetchall()]
    except pymysql.err.OperationalError as e:
        print(f"  [SQL error] {e}")
        return []


def discover_popular_pages(project_names=None):
    """Fetch the authoritative list of WikiProjects with Popular pages.

    Uses the Community Tech bot's maintainer page as the source of truth:
    https://en.wikipedia.org/wiki/User:Community_Tech_bot/Popular_pages

    Returns: list of project display names (underscores → spaces).
    """
    page = 'User:Community_Tech_bot/Popular_pages'
    url = (
        f"https://en.wikipedia.org/w/api.php"
        f"?action=parse&page={quote(page)}&prop=text&format=json"
    )
    try:
        req = Request(url, headers={'User-Agent': WIKI_UA})
        data = json.loads(urlopen(req, timeout=15).read())
        html = data['parse']['text']['*']
    except Exception as e:
        print(f"  [discover] Could not fetch bot page: {e}")
        return []

    links = re.findall(
        r'<a[^>]*href="/wiki/Wikipedia:WikiProject_([^"]+)/Popular_pages"[^>]*>',
        html
    )
    display_names = sorted(set(l.replace('_', ' ') for l in links))
    return display_names


# ─── OUTPUT ───

def build_standalone(html_path=INDEX_HTML, data_path=LIVE_DATA_JS, out_path=STANDALONE_HTML):
    """Embed LIVE_DATA inline into index.html to create self-contained file."""
    with open(data_path) as f:
        js = f.read()
    with open(html_path) as f:
        html = f.read()

    standalone = html.replace(
        '<script src="data/live-data.js"></script>',
        '<script>\n' + js + '\n</script>'
    )
    with open(out_path, 'w') as f:
        f.write(standalone)

    size_kb = os.path.getsize(out_path) / 1024
    print(f"\n✓ Standalone: {out_path} ({size_kb:.0f} KB)")


def write_live_data(all_data, path=LIVE_DATA_JS):
    """Write LIVE_DATA as var LIVE_DATA = {...} to a JS file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    js = 'var LIVE_DATA = ' + json.dumps(all_data, ensure_ascii=False) + ';\n'
    with open(path, 'w', encoding='utf-8') as f:
        f.write(js)
    size_kb = os.path.getsize(path) / 1024
    print(f"\n✓ Data written: {path} ({size_kb:.0f} KB)")


# ─── CACHE TEST ───

def test_cache():
    """Verify the cache works by timing a live call vs cached call."""
    print("\n" + "="*60)
    print("Cache Verification Test")
    print("="*60)

    test_article = "Earth"
    print(f"\nFetching wikitext for '{test_article}'...")

    t1 = time.time()
    wt1 = fetch_wikitext(test_article)
    t1_elapsed = time.time() - t1
    print(f"  First call (live):  {t1_elapsed:.2f}s, got {len(wt1) if wt1 else 0} chars")

    t2 = time.time()
    wt2 = fetch_wikitext(test_article)
    t2_elapsed = time.time() - t2
    print(f"  Second call (cache): {t2_elapsed:.2f}s, got {len(wt2) if wt2 else 0} chars")

    if wt1 and wt2 and wt1 == wt2:
        print(f"\n  ✓ Cache hit — content matches, speedup: {t1_elapsed/t2_elapsed:.0f}x faster")
    else:
        print(f"\n  ✗ Cache miss or content mismatch")

    print(f"\n  Testing force_refresh...")
    t3 = time.time()
    wt3 = fetch_wikitext(test_article, force_refresh=True)
    t3_elapsed = time.time() - t3
    print(f"  force_refresh call: {t3_elapsed:.2f}s — bypassed cache")

    print(f"\n  Cached keys in .wiki_cache/: {len(os.listdir(os.path.join(str(PROJECT_ROOT), '.wiki_cache'))) if os.path.isdir(os.path.join(str(PROJECT_ROOT), '.wiki_cache')) else 0}")
    print(f"  Cache dir: {PROJECT_ROOT}/.wiki_cache/")

    print(f"\n{'='*60}")
    print("Test complete.")
    print("="*60)
    return t1_elapsed, t2_elapsed


# ─── MAIN ───

def main():
    parser = argparse.ArgumentParser(
        description='Generate Contribution Impact Matrix data'
    )
    parser.add_argument(
        '--projects', type=str, default=None,
        help='Comma-separated WikiProject names (e.g. "Chemistry,Physics")'
    )
    parser.add_argument(
        '--all', action='store_true', dest='use_default',
        help='Use all default projects (8 OCW-aligned)'
    )
    parser.add_argument(
        '--list', action='store_true',
        help='List available WikiProjects (requires SSH tunnel)'
    )
    parser.add_argument(
        '--discover', action='store_true',
        help='Discover which WikiProjects have Popular pages (requires SSH tunnel)'
    )
    parser.add_argument(
        '--limit', type=int, default=500,
        help='Max articles per project (default: 500)'
    )
    parser.add_argument(
        '--build', action='store_true',
        help='Rebuild standalone.html after generation'
    )
    parser.add_argument(
        '--skip-sql', action='store_true',
        help='Skip SQL queries (no SSH tunnel needed)'
    )
    parser.add_argument(
        '--test-cache', action='store_true',
        help='Run cache timing verification test'
    )
    args = parser.parse_args()

    if args.test_cache:
        test_cache()
        return

    load_dotenv(dotenv_path=ENV_FILE)

    projects = None
    if args.projects:
        projects = [p.strip() for p in args.projects.split(',')]
    elif args.use_default or not args.list:
        projects = DEFAULT_PROJECTS

    if args.list or args.discover:
        if args.discover:
            print("Fetching canonical list from Community Tech bot's page...")
            with_popular = discover_popular_pages()
            print(f"\nWikiProjects WITH Popular pages ({len(with_popular)}):")
            for name in with_popular[:50]:
                print(f"  {name}")
            if len(with_popular) > 50:
                print(f"  ... and {len(with_popular) - 50} more")
            print(f"\nTotal: {len(with_popular)} projects have Popular pages")
            return

        conn = get_db()
        available = list_projects(conn)
        conn.close()

        print(f"\nWikiProjects with ≥10 assessed articles ({len(available)}):")
        for name, cnt in available[:100]:
            print(f"  {name} ({cnt} articles)")
        if len(available) > 100:
            print(f"  ... and {len(available) - 100} more")
        return

    if not projects:
        parser.print_help()
        return

    # Connect to DB
    conn = None
    if not args.skip_sql:
        try:
            conn = get_db()
            print("✓ SQL connection established")
        except Exception as e:
            print(f"⚠ Could not connect to enwiki_p: {e}")
            print("  Run with --skip-sql or set up SSH tunnel.")
            print(f"  Tunnel: ssh -L 3306:enwiki.analytics.db.svc.wikimedia.cloud:3306 "
                  f"{os.getenv('TOOLFORGE_USER', '$TOOLFORGE_USER')}@login.toolforge.org -N")
            conn = None

    print(f"\nGenerating data for {len(projects)} project(s): {', '.join(projects)}")
    print(f"Limit: {args.limit} articles per project")

    all_data = {}
    total_articles = 0
    total_time = time.time()

    for project in projects:
        result = process_project(project, limit=args.limit, conn=conn, skip_sql=args.skip_sql)
        if result:
            all_data[project] = result
            total_articles += result['total']

    if conn:
        conn.close()

    elapsed = time.time() - total_time
    print(f"\n{'='*60}")
    print(f"Generation complete: {len(all_data)} projects, {total_articles} articles")
    print(f"Total time: {elapsed:.0f}s ({elapsed/60:.1f}m)")

    write_live_data(all_data)

    if args.build:
        build_standalone()


if __name__ == '__main__':
    main()
