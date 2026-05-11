#!/usr/bin/env python3
"""Live query server for the Contribution Impact Matrix.

Usage:
    python3 scripts/impact-matrix-server.py

Then open http://localhost:8899/wiki/impact-matrix/index.html

Accepts:
    GET /api/projects  — list all WikiProjects with article counts
    GET /api/query?project=Chemistry&limit=200  — run killer query + pageview API
"""

import os, socket, subprocess, time, json, sys, re
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from urllib.request import Request, urlopen
import pymysql
from dotenv import load_dotenv

UA = 'MIT OCW Bot/1.0 (https://meta.wikimedia.org/wiki/Wiki_MIT; andrew.lih@gmail.com) ContentGapResearch'

load_dotenv(dotenv_path=Path('.env'))
# Debug: verify credentials loaded
_user = os.getenv("TOOLFORGE_USER")
_sql_user = os.getenv("TOOLFORGE_SQL_USER")
_sql_pass = os.getenv("TOOLFORGE_SQL_PASSWORD")
if not _user or not _sql_user or not _sql_pass:
    print("ERROR: Missing credentials in .env file. Check TOOLFORGE_USER, TOOLFORGE_SQL_USER, TOOLFORGE_SQL_PASSWORD", flush=True)
    sys.exit(1)

HOST, PORT = '127.0.0.1', 8899
TUNNEL_PORT = 3306
WIKI_DIR = Path(__file__).resolve().parent.parent / 'wiki'

# ─── SSH tunnel management ───
def ensure_tunnel():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(2)
        if s.connect_ex((HOST, TUNNEL_PORT)) == 0:
            return True
    user = os.getenv("TOOLFORGE_USER")
    if not user:
        return False
    proc = subprocess.Popen(
        ["ssh", "-L", f"{TUNNEL_PORT}:enwiki.analytics.db.svc.wikimedia.cloud:3306",
         f"{user}@login.toolforge.org", "-N", "-o", "BatchMode=yes"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    time.sleep(3)
    return proc.poll() is None

def get_db():
    return pymysql.connect(
        host=HOST, port=TUNNEL_PORT,
        user=os.getenv("TOOLFORGE_SQL_USER"),
        password=os.getenv("TOOLFORGE_SQL_PASSWORD"),
        database='enwiki_p', cursorclass=pymysql.cursors.DictCursor,
        charset='utf8mb4', connect_timeout=10
    )

def val(v):
    if isinstance(v, bytes): return v.decode('utf-8')
    return v

# ─── Template targets ───
TEMPLATE_TARGETS = (
    # Article-body templates (namespace 0)
    'Citation_needed', 'Cn', 'Fact', 'Cite',
    'Refimprove', 'Sources', 'Cites',
    'Primary_sources', 'Primarysources',
    'Better_source_needed', 'Bsn',
    'Technical', 'Too_technical', 'Overly_technical',
    'Missing_information', 'Expand_section', 'Gap',
    'Unreferenced_section', 'Urs',
    'Scientific_verification', 'Verify',
)

# Talk-page templates — placed on the article's talk page (namespace 1).
# These signal visual/media gaps that OCW materials (diagrams, images, video) can fill.
TALK_TEMPLATE_TARGETS = (
    'Image_requested', 'Needs_image', 'Imagerequest',
    'Diagram_needed', 'Needs_diagram',
    'Video_requested', 'Needs_video',
)

# ─── Popular pages fetcher ───
def fetch_popular_pages(project, limit=200):
    """Fetch and parse a WikiProject's Popular pages table.

    URL pattern: https://en.wikipedia.org/wiki/Wikipedia:WikiProject_{name}/Popular_pages

    The Community Tech bot generates these monthly for ~500 WikiProjects.
    Each table has exactly 6 columns, always in this order:

      Col 0 — Rank           Plain number (1-indexed within the project)
      Col 1 — Page title     Wikilink to the article: [[Article name]]
      Col 2 — Views          External link to pageviews.toolforge.org with FORMATNUM: {views}
      Col 3 — Daily average  FORMATNUM:{daily_avg}
      Col 4 — Assessment     Category link: [[:Category:{class}-Class articles|{class}]]
                              e.g. [[:Category:GA-Class articles|GA]]
                              Classes: FA, GA, B, C, Start, Stub
      Col 5 — Importance     Category link: [[:Category:{level}-importance articles|{level}]]
                              e.g. [[:Category:Top-importance articles|Top]]
                              Levels: Top, High, Mid, Low

    The table is fetched via action=parse with prop=text (rendered HTML).
    Parsing HTML rather than wikitext is acceptable here because:
    - The bot-generated wikitable renders to a stable, predictable HTML structure
    - Standard MediaWiki wikitable rendering hasn't changed in over a decade
    - The category-link pattern in the assessment/importance columns is
      trivially extractable from the rendered <a> tag text
    - mwparserfromhell was evaluated but adds complexity without benefit
      for this specific machine-generated table

    Returns: list of dicts with keys: title, views, quality, importance
             or None if the project has no Popular pages page.
    """
    page_title = f"Wikipedia:WikiProject_{project}/Popular_pages"
    url = f"https://en.wikipedia.org/w/api.php?action=parse&page={page_title}&prop=text&format=json"
    try:
        req = Request(url, headers={'User-Agent': UA})
        data = json.loads(urlopen(req, timeout=10).read())
        html = data['parse']['text']['*']
    except Exception:
        return None

    table_match = re.search(r'<table class="wikitable[^>]*>.*?</table>', html, re.DOTALL)
    if not table_match:
        return None

    articles = []
    rows = re.findall(r'<tr>.*?</tr>', table_match.group(), re.DOTALL)
    for row in rows[1:]:
        cells = re.findall(r'<td[^>]*>.*?</td>', row, re.DOTALL)
        if len(cells) < 6:
            continue
        # Cell 1: <a href="/wiki/Article_Name" title="Article Name">Article Name</a>
        title_match = re.search(r'<a[^>]*>([^<]+)</a>', cells[1])
        if not title_match:
            continue
        title = title_match.group(1).strip()
        # Cell 2: views (strip HTML, remove commas)
        views_text = re.sub(r'<[^>]+>', '', cells[2]).strip().replace(',', '')
        try:
            views = int(re.search(r'[\d]+', views_text).group())
        except Exception:
            views = None
        # Cell 4: assessment — link text is the class name
        quality = re.sub(r'<[^>]+>', '', cells[4]).strip()
        # Cell 5: importance — link text is the level name
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


def get_batch_templates(titles):
    """Batch-query template data for a list of article titles.
    
    Runs two queries per batch of 50:
      1) Article-body templates (citation needed, refimprove, etc.)
      2) Talk-page templates (image requested, video needed, etc.)
    
    Returns dict mapping title → list of template display names.
    """
    if not titles:
        return {}
    conn = get_db()
    result = {}
    try:
        for i in range(0, len(titles), 50):
            batch = titles[i:i+50]
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
                    result[t] = [x.replace('_',' ') for x in s.split(',') if x]
                
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
                    talk_list = [x.replace('_',' ') for x in s.split(',') if x]
                    if t in result:
                        result[t].extend(talk_list)
                    else:
                        result[t] = talk_list
    finally:
        conn.close()
    return result


def query_articles(project, limit=500):
    """Run the killer query for a WikiProject. Returns list of dicts."""
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT p.page_title, pa.pa_class, pa.pa_importance,
                       GROUP_CONCAT(DISTINCT lt.lt_title SEPARATOR ',') AS tmpl,
                       GROUP_CONCAT(DISTINCT lt2.lt_title SEPARATOR ',') AS talk_tmpl
                FROM page p
                JOIN page_assessments pa ON pa.pa_page_id = p.page_id
                JOIN page_assessments_projects pap ON pa.pa_project_id = pap.pap_project_id
                LEFT JOIN templatelinks tlt ON tlt.tl_from = p.page_id
                LEFT JOIN linktarget lt ON tlt.tl_target_id = lt.lt_id
                    AND lt.lt_namespace = 10
                    AND lt.lt_title IN (""" + ','.join('%s' for _ in TEMPLATE_TARGETS) + """)
                LEFT JOIN page tp ON tp.page_title = p.page_title AND tp.page_namespace = 1
                LEFT JOIN templatelinks tlt2 ON tlt2.tl_from = tp.page_id
                LEFT JOIN linktarget lt2 ON tlt2.tl_target_id = lt2.lt_id
                    AND lt2.lt_namespace = 10
                    AND lt2.lt_title IN (""" + ','.join('%s' for _ in TALK_TEMPLATE_TARGETS) + """)
                WHERE p.page_namespace = 0
                  AND pap.pap_project_title = %s
                  AND pa.pa_class IN ('Stub','Start','C','B','GA')
                  AND pa.pa_importance IN ('Top','High','Mid')
                GROUP BY p.page_id
                ORDER BY FIELD(pa.pa_importance, 'Top','High','Mid'),
                         FIELD(pa.pa_class, 'Stub','Start','C','B','GA')
                LIMIT %s
            """, TEMPLATE_TARGETS + TALK_TEMPLATE_TARGETS + (project, limit))
            rows = cur.fetchall()
    finally:
        conn.close()

    articles = []
    for r in rows:
        title = val(r['page_title'])
        tmpl_str = val(r['tmpl'])
        tmpl_list = [t.replace('_', ' ') for t in tmpl_str.split(',')] if tmpl_str else []
        talk_tmpl_str = val(r['talk_tmpl'])
        talk_list = [t.replace('_', ' ') for t in talk_tmpl_str.split(',')] if talk_tmpl_str else []
        all_tmpl = tmpl_list + talk_list
        articles.append({
            "title": title,
            "quality": val(r['pa_class']),
            "importance": val(r['pa_importance']),
            "templates": all_tmpl,
            "importance": val(r['pa_importance']),
            "templates": tmpl_list,
            "views": None
        })
    return articles

def enrich_pageviews(articles, period="20260401/20260430"):
    """Fetch monthly pageviews from the REST API for each article."""
    headers = {'User-Agent': UA}
    for a in articles:
        t = a['title']
        url = f"https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/all-agents/{t}/monthly/2026010100/2026050100"
        try:
            req = Request(url, headers=headers)
            resp = urlopen(req, timeout=5)
            data = json.loads(resp.read())
            a['views'] = sum(item['views'] for item in data.get('items', []))
        except Exception:
            a['views'] = None
    return articles

# ─── List available WikiProjects ───
def list_projects():
    conn = get_db()
    try:
        with conn.cursor() as cur:
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
                LIMIT 200
            """)
            return [{"name": val(r['pap_project_title']), "count": r['cnt']} for r in cur.fetchall()]
    finally:
        conn.close()

# ─── HTTP Handler ───
class ImpactHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if parsed.path == '/api/projects':
            self.send_json(list_projects())

        elif parsed.path == '/api/query':
            project = (params.get('project') or ['Environment'])[0]
            limit = int((params.get('limit') or ['200'])[0])
            self.send_json(self.run_query(project, limit))

        else:
            # Serve static files from wiki/
            self.directory = str(WIKI_DIR.parent)
            return super().do_GET()

    def run_query(self, project, limit):
        if not ensure_tunnel():
            return {"error": "SSH tunnel could not be established"}
        try:
            # Try Popular pages first (has pageviews), fall back to SQL
            articles = fetch_popular_pages(project, limit)
            source = "Popular pages"
            if articles is None:
                articles = query_articles(project, limit)
                articles = enrich_pageviews(articles)
                source = "SQL + REST API"
            else:
                # Enrich with template data from SQL
                titles = [a['title'] for a in articles]
                tmpl_map = get_batch_templates(titles)
                for a in articles:
                    a['templates'] = tmpl_map.get(a['title'], [])
            return {
                "project": project,
                "articles": articles,
                "total": len(articles),
                "source": source
            }
        except Exception as e:
            return {"error": str(e)}

    def send_json(self, data):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))

    def log_message(self, format, *args):
        sys.stderr.write(f"[impact-matrix] {args[0]} {args[1]} {args[2]}\n")

def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else PORT

    if not ensure_tunnel():
        print("WARNING: Could not establish SSH tunnel.", flush=True)
    else:
        print("SSH tunnel OK", flush=True)

    server = HTTPServer((HOST, port), ImpactHandler)
    print(f"Contribution Impact Matrix server running at:", flush=True)
    print(f"  http://{HOST}:{port}/wiki/impact-matrix/index.html", flush=True)
    print(f"  API: http://{HOST}:{port}/api/projects", flush=True)
    print(f"  API: http://{HOST}:{port}/api/query?project=Environment", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()

if __name__ == '__main__':
    main()
