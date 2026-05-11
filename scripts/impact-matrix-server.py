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

# ─── Query helpers ───
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
    headers = {'User-Agent': 'MIT-OCW-Wiki/1.0 (research; impact-matrix)'}
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
            articles = query_articles(project, limit)
            articles = enrich_pageviews(articles)
            return {
                "project": project,
                "articles": articles,
                "total": len(articles),
                "note": "Live data from enwiki_p + REST API pageviews"
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
