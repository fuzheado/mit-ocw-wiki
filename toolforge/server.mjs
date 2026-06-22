// server.mjs — Wiki MIT Contribution Workbench
// Zero-dependency Node.js web service for Wikimedia Toolforge
//
// Serves: static UI + API endpoints that proxy to Python contribution scripts.
// Auth: bot password (env vars) for now; OAuth 2.0 ready when consumer is registered.
// Deployment: scp to Toolforge, then `webservice --backend=kubernetes node22 start`.

import { createServer } from 'node:http';
import { readFile, access } from 'node:fs/promises';
import { join, extname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';
import { randomBytes } from 'node:crypto';

const __dirname = fileURLToPath(new URL('.', import.meta.url));
const PORT = parseInt(process.env.PORT || '8765', 10);

// ─── Config ────────────────────────────────────────────────────────────────

// Scripts directory — resolves for both local dev (../scripts) and Toolforge (./scripts)
let SCRIPTS_DIR = join(__dirname, '..', 'scripts');
let PROJECT_DIR = join(__dirname, '..');
try { await access(SCRIPTS_DIR); } catch {
  SCRIPTS_DIR = join(__dirname, 'scripts');
  PROJECT_DIR = __dirname;
}

// Auth: bot password from environment (set via `toolforge env set`)
const WIKI_BOT_USER = process.env.WIKI_BOT_USER || '';
const WIKI_BOT_PASS = process.env.WIKI_BOT_PASS || '';

// OAuth 2.0 (future — set when consumer is registered on meta)
const OAUTH_CLIENT_ID = process.env.OAUTH_CLIENT_ID || '';
const OAUTH_CLIENT_SECRET = process.env.OAUTH_CLIENT_SECRET || '';
const OAUTH_CALLBACK = process.env.OAUTH_CALLBACK || '';

// Simple session store (in-memory — survives pod restarts via NFS if needed)
const sessions = new Map();
const SESSION_TTL = 24 * 60 * 60 * 1000; // 24 hours

// ─── MIME types ─────────────────────────────────────────────────────────────

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.css':  'text/css; charset=utf-8',
  '.js':   'application/javascript; charset=utf-8',
  '.mjs':  'application/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png':  'image/png',
  '.svg':  'image/svg+xml',
};

// ─── Helpers ────────────────────────────────────────────────────────────────

function json(res, data, status = 200) {
  res.writeHead(status, { 'Content-Type': 'application/json', 'Cache-Control': 'no-cache' });
  res.end(JSON.stringify(data));
}

function jsonError(res, message, status = 400) {
  json(res, { error: message }, status);
}

async function parseBody(req) {
  const chunks = [];
  for await (const chunk of req) chunks.push(chunk);
  const raw = Buffer.concat(chunks).toString('utf-8');
  if (!raw) return {};
  try { return JSON.parse(raw); } catch { return Object.fromEntries(new URLSearchParams(raw)); }
}

function sessionId(req) {
  const cookie = req.headers.cookie || '';
  const match = cookie.match(/sid=([^;]+)/);
  return match ? match[1] : null;
}

function getSession(req) {
  const sid = sessionId(req);
  if (!sid) return null;
  const s = sessions.get(sid);
  if (!s) return null;
  if (Date.now() - s.created > SESSION_TTL) { sessions.delete(sid); return null; }
  return s;
}

function setSession(res, data = {}) {
  const sid = randomBytes(16).toString('hex');
  sessions.set(sid, { ...data, created: Date.now() });
  res.setHeader('Set-Cookie', `sid=${sid}; Path=/; HttpOnly; SameSite=Lax; Max-Age=${SESSION_TTL / 1000}`);
  return sid;
}

// ─── Python subprocess runner ────────────────────────────────────────────────

function runPython(script, args = [], env = {}, stdin = null) {
  return new Promise((resolve, reject) => {
    const proc = spawn('python3', [script, ...args], {
      cwd: PROJECT_DIR,
      env: { ...process.env, ...env },
      stdio: stdin ? ['pipe', 'pipe', 'pipe'] : ['ignore', 'pipe', 'pipe'],
    });

    let stdout = '', stderr = '';
    proc.stdout.on('data', d => stdout += d);
    proc.stderr.on('data', d => stderr += d);

    if (stdin) {
      proc.stdin.write(stdin);
      proc.stdin.end();
    }

    proc.on('close', code => {
      if (code === 0) {
        try { resolve(JSON.parse(stdout)); }
        catch { resolve({ raw: stdout }); }
      } else {
        reject(new Error(stderr || `Exit code ${code}`));
      }
    });
    proc.on('error', reject);
  });
}

// ─── Course index (built on startup) ─────────────────────────────────────────

let courseIndex = [];

async function loadCourseIndex() {
  const { readdir, readFile } = await import('node:fs/promises');
  const coursesDir = join(PROJECT_DIR, 'wiki', 'courses');
  try {
    const files = await readdir(coursesDir);
    const items = [];
    for (const f of files) {
      if (!f.endsWith('.md')) continue;
      try {
        const raw = await readFile(join(coursesDir, f), 'utf-8');
        const yamlMatch = raw.match(/^---\n([\s\S]*?)\n---/);
        if (!yamlMatch) continue;
        const fields = {};
        for (const line of yamlMatch[1].split('\n')) {
          const m = line.match(/^(\w[\w_-]*):\s*(.+)/);
          if (m) fields[m[1]] = m[2].trim().replace(/^['"]|['"]$/g, '');
        }
        items.push({
          slug: f.replace('.md', ''),
          id: fields.course_id || '',
          title: fields.title || '',
          department: fields.department || '',
          topics: (fields.topics || '').split(',').map(t => t.trim()).filter(Boolean),
          url: fields.url || `https://ocw.mit.edu/courses/${f.replace('.md', '')}/`,
        });
      } catch { /* skip malformed files */ }
    }
    courseIndex = items;
    console.log(`Loaded ${courseIndex.length} courses into index`);
  } catch (err) {
    console.log(`Course index not available: ${err.message}`);
  }
}

function searchCourses(query) {
  if (!query || query.length < 2) return courseIndex.slice(0, 20);
  const q = query.toLowerCase();
  return courseIndex.filter(c =>
    c.id.toLowerCase().includes(q) ||
    c.title.toLowerCase().includes(q) ||
    c.department?.toLowerCase().includes(q) ||
    c.topics.some(t => t.toLowerCase().includes(q))
  ).slice(0, 30);
}

// ─── Matching ────────────────────────────────────────────────────────────────

async function matchCourse(courseSlug) {
  try {
    const result = await runPython(
      join(SCRIPTS_DIR, 'ad-hoc-match.py'),
      [courseSlug, '--top', '10', '--provider', 'corpus,wikipedia'],
      { PYTHONIOENCODING: 'utf-8' }
    );
    // ad-hoc-match.py prints to stdout, not JSON — parse its table output
    return parseAdHocOutput(result.raw || '');
  } catch (err) {
    console.error(`Match failed: ${err.message}`);
    return [];
  }
}

function parseAdHocOutput(raw) {
  const matches = [];
  // Strip ANSI escape codes
  const clean = raw.replace(/\x1b\[[0-9;]*m/g, '');
  const lines = clean.split('\n');

  let current = null;
  for (const line of lines) {
    // New match: "N. Title [Quality: Q | Views: V | {{refideas}}: yes/no]"
    const headerMatch = line.match(/^\s*(\d+)\.\s+(.+?)\s+\[Quality:\s*(\S+)\s*\|\s*Views:\s*([0-9,]+)\s*\|\s*\{\{refideas\}\}:\s*(\S+)\]/);
    if (headerMatch) {
      if (current) matches.push(current);
      current = {
        rank: parseInt(headerMatch[1]),
        title: headerMatch[2].trim(),
        quality: headerMatch[3] === '?' ? '?' : headerMatch[3],
        views: parseInt(headerMatch[4].replace(/,/g, '')) || 0,
        importance: '?',
        templates: '',
        score: 0,
        match_source: '',
        refideas: headerMatch[5] === 'yes',
        course_slug: '',
        description: '',
      };
      continue;
    }

    if (!current) continue;

    // Score line
    const scoreMatch = line.match(/Score:\s*(\d+)\/100/);
    if (scoreMatch) {
      current.score = parseInt(scoreMatch[1]);
      continue;
    }

    // Source line
    const sourceMatch = line.match(/Source:\s*(.+)/);
    if (sourceMatch) {
      current.match_source = sourceMatch[1].trim();
      continue;
    }

    // L1 command line → extract course slug
    const l1Match = line.match(/--course\s+"([^"]+)"/);
    if (l1Match) {
      current.course_slug = l1Match[1];
      continue;
    }

    // Description (non-empty line between header and Score, not starting with →)
    const trimmed = line.trim();
    if (trimmed && !trimmed.startsWith('→') && !trimmed.startsWith('Score:') && !trimmed.startsWith('Source:')) {
      if (!current.description) current.description = trimmed;
    }
  }
  if (current) matches.push(current);

  return matches;
}

// ─── L1 / L2 contribution ───────────────────────────────────────────────────

async function applyL1(article, courseId, courseTitle, courseUrl) {
  try {
    const result = await runPython(
      join(SCRIPTS_DIR, 'apply-l1-refideas.py'),
      ['--yes', article, '--course-id', courseId, '--course-title', courseTitle, '--course-url', courseUrl],
      {
        WIKIPEDIA_USERNAME: WIKI_BOT_USER,
        WIKIPEDIA_BOT_PASSWORD: WIKI_BOT_PASS,
        PYTHONIOENCODING: 'utf-8',
      }
    );
    return { success: true, detail: result.raw || 'Edit applied' };
  } catch (err) {
    console.error(`L1 failed: ${err.message}`);
    return { success: false, error: err.message };
  }
}

async function applyL2(article, courseId, courseTitle, courseUrl, description) {
  try {
    const result = await runPython(
      join(SCRIPTS_DIR, 'apply-l2-external-links.py'),
      ['--yes', article, '--course-id', courseId, '--course-title', courseTitle, '--course-url', courseUrl, '--description', description],
      {
        WIKIPEDIA_USERNAME: WIKI_BOT_USER,
        WIKIPEDIA_BOT_PASSWORD: WIKI_BOT_PASS,
        PYTHONIOENCODING: 'utf-8',
      }
    );
    return { success: true, detail: result.raw || 'Edit applied' };
  } catch (err) {
    console.error(`L2 failed: ${err.message}`);
    return { success: false, error: err.message };
  }
}

// Generate wikitext without posting
async function previewL1(courseTitle, courseUrl, courseId) {
  const label = `${courseId}: ${courseTitle}`;
  return `{{Refideas
|1=[${courseUrl} ${label}], MIT OpenCourseWare
|comment=${courseId} covers topics relevant to this article.
}}`;
}

async function previewL2(courseTitle, courseUrl, courseId, description) {
  return `* {{cite web |url=${courseUrl} |title=${courseTitle} |publisher=MIT OpenCourseWare}} — ${description || `${courseId} — Full course with lectures and materials.`}`;
}

// ─── HTTP Server ────────────────────────────────────────────────────────────

const STATIC_CACHE = {};

async function serveStatic(res, pathname) {
  const filePath = join(__dirname, 'public', pathname === '/' ? 'index.html' : pathname);

  // Security: prevent directory traversal
  const resolved = filePath;
  const safeDir = join(__dirname, 'public') + '/';
  if (!resolved.startsWith(join(__dirname, 'public'))) {
    res.writeHead(403); res.end('Forbidden');
    return;
  }

  try {
    let data = STATIC_CACHE[pathname];
    if (!data) {
      data = await readFile(filePath);
      STATIC_CACHE[pathname] = data;
    }
    const ext = extname(filePath);
    res.writeHead(200, {
      'Content-Type': MIME[ext] || 'application/octet-stream',
      'Content-Length': data.length,
      'Cache-Control': ext === '.html' ? 'public, max-age=300' : 'public, max-age=3600',
    });
    res.end(data);
  } catch {
    res.writeHead(404, { 'Cache-Control': 'no-store' });
    res.end('Not found');
  }
}

const server = createServer(async (req, res) => {
  const url = new URL(req.url, `http://localhost:${PORT}`);
  const pathname = url.pathname;
  const method = req.method;

  // CORS (for local dev with file:// or different ports)
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization');

  if (method === 'OPTIONS') { res.writeHead(204); res.end(); return; }

  // ─── API Routes ──────────────────────────────────────────────────────

  if (pathname === '/api/health') {
    return json(res, {
      status: 'ok',
      courses: courseIndex.length,
      auth: !!WIKI_BOT_USER,
      time: new Date().toISOString(),
    });
  }

  // Course search
  if (pathname === '/api/courses' && method === 'GET') {
    const q = url.searchParams.get('q') || '';
    const results = searchCourses(q);
    return json(res, { results: results.map(c => ({
      slug: c.slug,
      id: c.id,
      title: c.title,
      department: c.department,
      topics: c.topics.slice(0, 5),
    })) });
  }

  // Match a course to Wikipedia articles
  if (pathname === '/api/match' && method === 'GET') {
    const course = url.searchParams.get('course') || '';
    if (!course) return jsonError(res, 'Missing ?course= parameter');
    const matches = await matchCourse(course);
    return json(res, { course, matches });
  }

  // Preview wikitext (L1 or L2)
  if (pathname === '/api/preview' && method === 'POST') {
    const body = await parseBody(req);
    const { level, courseId, courseTitle, courseUrl, description } = body;
    try {
      if (level === 'L1') {
        const wikitext = await previewL1(courseTitle, courseUrl, courseId);
        return json(res, { wikitext });
      } else if (level === 'L2') {
        const wikitext = await previewL2(courseTitle, courseUrl, courseId, description || '');
        return json(res, { wikitext });
      }
      return jsonError(res, `Unknown level: ${level}`);
    } catch (err) {
      return jsonError(res, err.message, 500);
    }
  }

  // Apply edit (L1 or L2)
  if (pathname === '/api/apply' && method === 'POST') {
    if (!WIKI_BOT_USER) return jsonError(res, 'Bot credentials not configured', 503);

    const body = await parseBody(req);
    const { level, article, courseId, courseTitle, courseUrl, description } = body;

    if (!article || !courseId || !courseUrl) {
      return jsonError(res, 'Missing required fields: article, courseId, courseUrl');
    }

    try {
      if (level === 'L1') {
        const result = await applyL1(article, courseId, courseTitle, courseUrl);
        return json(res, result, result.success ? 200 : 500);
      } else if (level === 'L2') {
        const result = await applyL2(article, courseId, courseTitle, courseUrl, description || '');
        return json(res, result, result.success ? 200 : 500);
      }
      return jsonError(res, `Unknown level: ${level}`);
    } catch (err) {
      return jsonError(res, err.message, 500);
    }
  }

  // Auth status
  if (pathname === '/api/auth/status') {
    const session = getSession(req);
    return json(res, {
      authenticated: !!session || !!WIKI_BOT_USER,
      username: session?.username || WIKI_BOT_USER?.split('@')[0] || null,
      method: WIKI_BOT_USER ? 'bot_password' : 'none',
    });
  }

  // OAuth 2.0 — start authorization
  if (pathname === '/api/oauth/login' && method === 'GET') {
    if (!OAUTH_CLIENT_ID) return jsonError(res, 'OAuth not configured', 501);
    const state = randomBytes(16).toString('hex');
    const oauthUrl = 'https://meta.wikimedia.org/rest.php/oauth2/authorize?' +
      new URLSearchParams({
        response_type: 'code',
        client_id: OAUTH_CLIENT_ID,
        redirect_uri: OAUTH_CALLBACK,
        state,
      }).toString();
    setSession(res, { oauthState: state });
    res.writeHead(302, { Location: oauthUrl });
    return res.end();
  }

  // OAuth 2.0 — callback
  if (pathname === '/api/oauth/callback' && method === 'GET') {
    const code = url.searchParams.get('code');
    const state = url.searchParams.get('state');
    const session = getSession(req);

    if (!code) return jsonError(res, 'Missing code');
    if (session?.oauthState !== state) return jsonError(res, 'State mismatch', 403);

    try {
      const tokenResp = await fetch('https://meta.wikimedia.org/rest.php/oauth2/access_token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({
          grant_type: 'authorization_code',
          code,
          client_id: OAUTH_CLIENT_ID,
          client_secret: OAUTH_CLIENT_SECRET,
        }).toString(),
      });
      const tokens = await tokenResp.json();
      if (tokens.error) throw new Error(tokens.error_description || tokens.error);

      // Get user profile
      const profileResp = await fetch('https://meta.wikimedia.org/rest.php/oauth2/resource/profile', {
        headers: { Authorization: `Bearer ${tokens.access_token}` },
      });
      const profile = await profileResp.json();

      setSession(res, {
        username: profile.username,
        accessToken: tokens.access_token,
        refreshToken: tokens.refresh_token,
        expiresAt: Date.now() + (tokens.expires_in * 1000),
      });

      res.writeHead(302, { Location: '/' });
      return res.end();
    } catch (err) {
      return jsonError(res, err.message, 500);
    }
  }

  // ─── Static files ────────────────────────────────────────────────────
  return serveStatic(res, pathname);
});

// ─── Startup ────────────────────────────────────────────────────────────────

await loadCourseIndex();

server.listen(PORT, () => {
  console.log(`Wiki MIT Workbench running on port ${PORT}`);
  console.log(`  Courses indexed: ${courseIndex.length}`);
  console.log(`  Auth: ${WIKI_BOT_USER ? 'bot password configured' : 'not configured'}`);
  console.log(`  OAuth: ${OAUTH_CLIENT_ID ? 'configured' : 'not configured'}`);
});
