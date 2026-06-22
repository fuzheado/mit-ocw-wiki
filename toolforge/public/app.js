// app.js — Wiki MIT Contribution Workbench client
// Implements the Contribution Ladder UX: search → match → preview → apply.

const API = '/api';
const WIKIPEDIA_BASE = 'https://en.wikipedia.org/wiki/';

// ─── State ────────────────────────────────────────────────────────────────

const state = {
  courseSlug: null,
  courseId: null,
  courseTitle: null,
  courseUrl: null,
  courseDept: null,
  matches: [],
  selectedMatch: null,
  selectedRung: 'L1',
  activityLog: JSON.parse(localStorage.getItem('wiki-mit-activity') || '[]'),
};

// ─── DOM refs ─────────────────────────────────────────────────────────────

const $ = (sel) => document.querySelector(sel);

const els = {
  authDot: $('.auth-dot'),
  authLabel: $('#auth-label'),
  courseSearch: $('#course-search'),
  courseResults: $('#course-results'),
  matchBtn: $('#match-btn'),
  searchStatus: $('#search-status'),
  matchesSection: $('#matches-section'),
  matchCount: $('#match-count'),
  matchContext: $('#match-context'),
  matchesList: $('#matches-list'),
  detailPanel: $('#detail-panel'),
  detailTitle: $('#detail-title'),
  detailMeta: $('#detail-meta'),
  previewContent: $('#preview-content'),
  copyBtn: $('#copy-btn'),
  applyBtn: $('#apply-btn'),
  applyStatus: $('#apply-status'),
  rungDescription: $('#rung-description'),
  activitySection: $('#activity-section'),
  activityList: $('#activity-list'),
};

// ─── API helpers ──────────────────────────────────────────────────────────

async function apiFetch(path, options = {}) {
  const res = await fetch(API + path, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error(err.error || res.statusText);
  }
  return res.json();
}

// ─── Auth status ──────────────────────────────────────────────────────────

async function checkAuth() {
  try {
    const data = await apiFetch('/auth/status');
    els.authDot.className = 'auth-dot' + (data.authenticated ? ' active' : '');
    els.authLabel.textContent = data.authenticated
      ? `Logged in as ${data.username}`
      : 'Not authenticated (read-only)';
    return data;
  } catch {
    els.authLabel.textContent = 'API unavailable';
  }
}

// ─── Course search ────────────────────────────────────────────────────────

let searchTimeout;
let searchIndex = -1;

els.courseSearch.addEventListener('input', () => {
  clearTimeout(searchTimeout);
  const q = els.courseSearch.value.trim();
  if (q.length < 1) {
    els.courseResults.classList.add('hidden');
    els.matchBtn.disabled = true;
    state.courseSlug = null;
    return;
  }
  searchTimeout = setTimeout(() => searchCourses(q), 200);
});

els.courseSearch.addEventListener('keydown', (e) => {
  const items = els.courseResults.querySelectorAll('.dropdown-item');
  if (e.key === 'ArrowDown') { e.preventDefault(); searchIndex = Math.min(searchIndex + 1, items.length - 1); }
  else if (e.key === 'ArrowUp') { e.preventDefault(); searchIndex = Math.max(searchIndex - 1, 0); }
  else if (e.key === 'Enter') {
    e.preventDefault();
    if (searchIndex >= 0 && items[searchIndex]) items[searchIndex].click();
    else if (state.courseSlug) els.matchBtn.click();
    return;
  } else { searchIndex = -1; }
  items.forEach((item, i) => item.classList.toggle('active', i === searchIndex));
});

document.addEventListener('click', (e) => {
  if (!els.courseResults.contains(e.target) && e.target !== els.courseSearch) {
    els.courseResults.classList.add('hidden');
  }
});

async function searchCourses(q) {
  try {
    const data = await apiFetch(`/courses?q=${encodeURIComponent(q)}`);
    els.courseResults.innerHTML = data.results.length
      ? data.results.map((c, i) => `
        <div class="dropdown-item" data-slug="${c.slug}" data-id="${c.id}" data-title="${c.title}" data-dept="${c.department}">
          <div class="course-id">${c.id}</div>
          <div class="course-title">${c.title}</div>
          <div class="course-meta">${c.department || ''}${c.topics.length ? ' · ' + c.topics.slice(0,3).join(', ') : ''}</div>
        </div>`).join('')
      : '<div class="dropdown-item" style="color:var(--text-muted)">No courses found</div>';
    els.courseResults.classList.remove('hidden');
    searchIndex = -1;

    // Click handlers
    els.courseResults.querySelectorAll('.dropdown-item').forEach(item => {
      item.addEventListener('click', () => {
        const slug = item.dataset.slug;
        const id = item.dataset.id;
        const title = item.dataset.title;
        const dept = item.dataset.dept;
        els.courseSearch.value = `${id} — ${title}`;
        els.courseResults.classList.add('hidden');
        state.courseSlug = slug;
        state.courseId = id;
        state.courseTitle = title;
        state.courseDept = dept;
        state.courseUrl = `https://ocw.mit.edu/courses/${slug}/`;
        els.matchBtn.disabled = false;
      });
    });
  } catch (err) {
    // If API unavailable, allow free-text entry
    const q = els.courseSearch.value.trim();
    if (q) {
      state.courseSlug = q;
      state.courseId = q;
      state.courseTitle = q;
      state.courseUrl = q.startsWith('http') ? q : `https://ocw.mit.edu/search/?q=${encodeURIComponent(q)}`;
      els.matchBtn.disabled = false;
    }
    els.courseResults.classList.add('hidden');
  }
}

// ─── Match button ─────────────────────────────────────────────────────────

els.matchBtn.addEventListener('click', runMatch);

async function runMatch() {
  if (!state.courseSlug) return;

  els.matchBtn.disabled = true;
  els.matchBtn.innerHTML = '<span class="btn-icon">⏳</span> Searching...';
  els.searchStatus.classList.remove('hidden');
  els.searchStatus.className = 'status-msg loading';
  els.searchStatus.textContent = `Finding Wikipedia matches for ${state.courseId}...`;
  els.matchesSection.classList.remove('hidden');
  els.detailPanel.classList.add('hidden');
  els.matchesList.innerHTML = '';

  try {
    const data = await apiFetch(`/match?course=${encodeURIComponent(state.courseSlug)}`);
    state.matches = data.matches || [];

    els.matchCount.textContent = `${state.matches.length} matches`;
    els.matchContext.textContent = state.courseTitle
      ? `Matches for ${state.courseId}: ${state.courseTitle}`
      : `Matches for ${state.courseSlug}`;

    if (state.matches.length === 0) {
      els.searchStatus.className = 'status-msg';
      els.searchStatus.textContent = 'No strong matches found. Try a more specific course ID or search term.';
      els.matchBtn.innerHTML = '<span class="btn-icon">🔍</span> Find matches';
      els.matchBtn.disabled = false;
      return;
    }

    els.searchStatus.classList.add('hidden');
    renderMatches();
  } catch (err) {
    els.searchStatus.className = 'status-msg error';
    els.searchStatus.textContent = `Match failed: ${err.message}. Try: python3 scripts/ad-hoc-match.py "${state.courseSlug}" --top 5`;
  }
  els.matchBtn.innerHTML = '<span class="btn-icon">🔍</span> Find matches';
  els.matchBtn.disabled = false;
}

function renderMatches() {
  els.matchesList.innerHTML = state.matches.map((m, i) => `
    <div class="match-card" data-index="${i}">
      <span class="match-rank">${i + 1}</span>
      <div class="match-info">
        <div class="match-title">
          <a href="${WIKIPEDIA_BASE}${encodeURIComponent(m.title.replace(/ /g, '_'))}" target="_blank">${m.title}</a>
        </div>
        <div class="match-stats">
          <span>Quality: ${m.quality || '?'}</span>
          <span>Views: ${m.views || '?'}</span>
          ${m.templates ? `<span>Tags: ${m.templates}</span>` : ''}
        </div>
      </div>
      <div style="text-align:center">
        <div class="match-score">${m.score || '—'}</div>
        <div class="match-score-bar"><div class="match-score-fill" style="width:${Math.min(m.score || 0, 100)}%"></div></div>
      </div>
      <span class="match-chevron">→</span>
    </div>
  `).join('');

  // Click handlers for match cards
  els.matchesList.querySelectorAll('.match-card').forEach(card => {
    card.addEventListener('click', () => {
      els.matchesList.querySelectorAll('.match-card').forEach(c => c.classList.remove('selected'));
      card.classList.add('selected');
      const idx = parseInt(card.dataset.index);
      state.selectedMatch = state.matches[idx];
      showDetail(state.selectedMatch);
    });
  });
}

// ─── Detail panel ─────────────────────────────────────────────────────────

function showDetail(match) {
  els.detailPanel.classList.remove('hidden');
  els.detailTitle.textContent = match.title;
  els.detailMeta.innerHTML = `
    Quality: <strong>${match.quality || '?'}</strong>
    <span>Importance: <strong>${match.importance || '?'}</strong></span>
    <span>Views: <strong>${match.views || '?'}</strong></span>
    <span>Score: <strong>${match.score || '—'}</strong></span>
  `;

  // Reset rung tabs
  els.detailPanel.querySelectorAll('.rung-tab').forEach(t => {
    t.classList.toggle('active', t.dataset.rung === state.selectedRung);
  });

  updateRungDescription();
  updatePreview();
  els.applyStatus.classList.add('hidden');
}

// Rung tab clicks
els.detailPanel.addEventListener('click', (e) => {
  const tab = e.target.closest('.rung-tab');
  if (!tab) return;

  state.selectedRung = tab.dataset.rung;
  els.detailPanel.querySelectorAll('.rung-tab').forEach(t => t.classList.remove('active'));
  tab.classList.add('active');
  updateRungDescription();
  updatePreview();
  els.applyStatus.classList.add('hidden');
});

function updateRungDescription() {
  const descriptions = {
    L1: 'Post a reference suggestion on the article\'s <strong>Talk page</strong>. Does not modify the article itself — editors decide whether to use it. Safest option.',
    L2: 'Add an MIT OCW course link to the article\'s <strong>External links</strong> section. Very low risk — adds a resource without changing article content.',
  };
  els.rungDescription.innerHTML = descriptions[state.selectedRung] || '';
}

async function updatePreview() {
  if (!state.selectedMatch) return;
  els.previewContent.textContent = 'Generating wikitext...';
  els.copyBtn.disabled = true;
  els.applyBtn.disabled = true;

  try {
    const data = await apiFetch('/preview', {
      method: 'POST',
      body: JSON.stringify({
        level: state.selectedRung,
        courseId: state.courseId,
        courseTitle: state.courseTitle,
        courseUrl: state.courseUrl,
        description: `${state.courseId} — Full course with lectures and materials.`,
      }),
    });
    els.previewContent.textContent = data.wikitext;
    els.copyBtn.disabled = false;
    els.applyBtn.disabled = false;
  } catch (err) {
    // Fallback: generate client-side
    els.previewContent.textContent = generateWikitextLocal();
    els.copyBtn.disabled = false;
    els.applyBtn.disabled = false;
  }
}

function generateWikitextLocal() {
  const m = state.selectedMatch;
  const title = state.courseTitle || state.courseId;
  const url = state.courseUrl;
  if (state.selectedRung === 'L1') {
    return `{{Refideas
|1=[${url} ${state.courseId}: ${title}], MIT OpenCourseWare
|comment=${state.courseId} covers topics relevant to ${m.title}.
}}`;
  } else {
    return `* {{cite web |url=${url} |title=${title} |publisher=MIT OpenCourseWare}} — ${state.courseId}: Full course with lectures and materials.`;
  }
}

// Copy button
els.copyBtn.addEventListener('click', async () => {
  try {
    await navigator.clipboard.writeText(els.previewContent.textContent);
    els.copyBtn.textContent = '✅ Copied!';
    setTimeout(() => { els.copyBtn.textContent = '📋 Copy'; }, 2000);
  } catch {
    // Fallback
    const ta = document.createElement('textarea');
    ta.value = els.previewContent.textContent;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    els.copyBtn.textContent = '✅ Copied!';
    setTimeout(() => { els.copyBtn.textContent = '📋 Copy'; }, 2000);
  }
});

// ─── Apply button ─────────────────────────────────────────────────────────

els.applyBtn.addEventListener('click', applyEdit);

async function applyEdit() {
  if (!state.selectedMatch) return;
  const article = state.selectedMatch.title;
  const level = state.selectedRung;

  els.applyBtn.disabled = true;
  els.applyBtn.innerHTML = '<span class="btn-icon">⏳</span> Posting...';
  els.applyStatus.classList.remove('hidden');
  els.applyStatus.className = 'apply-status loading';
  els.applyStatus.textContent = `Posting ${level} edit to ${article}...`;

  try {
    const data = await apiFetch('/apply', {
      method: 'POST',
      body: JSON.stringify({
        level,
        article,
        courseId: state.courseId,
        courseTitle: state.courseTitle,
        courseUrl: state.courseUrl,
        description: `${state.courseId} — Full course with lectures and materials.`,
      }),
    });

    if (data.success) {
      els.applyStatus.className = 'apply-status success';
      els.applyStatus.textContent = `✅ ${level} edit applied to "${article}"! View on Wikipedia.`;
      els.applyBtn.innerHTML = '<span class="btn-icon">✅</span> Applied';
      logActivity(level, article, true);
    } else {
      throw new Error(data.error || 'Unknown error');
    }
  } catch (err) {
    els.applyStatus.className = 'apply-status error';
    // Provide fallback: link to manual edit
    const talkUrl = level === 'L1'
      ? `https://en.wikipedia.org/wiki/Talk:${encodeURIComponent(article.replace(/ /g, '_'))}`
      : `https://en.wikipedia.org/w/index.php?title=${encodeURIComponent(article.replace(/ /g, '_'))}&action=edit`;
    els.applyStatus.innerHTML = `
      ⚠️ Could not post automatically: ${err.message}<br>
      <a href="${talkUrl}" target="_blank" style="color:var(--primary);font-weight:600">
        → Open Wikipedia to paste manually
      </a>
    `;
    els.applyBtn.innerHTML = '<span class="btn-icon">📝</span> Apply to Wikipedia';
    els.applyBtn.disabled = false;
    logActivity(level, article, false);
  }
}

// ─── Activity log ─────────────────────────────────────────────────────────

function logActivity(level, article, success) {
  const entry = {
    level,
    article,
    course: state.courseId,
    time: new Date().toISOString(),
    success,
  };
  state.activityLog.unshift(entry);
  if (state.activityLog.length > 20) state.activityLog.length = 20;
  localStorage.setItem('wiki-mit-activity', JSON.stringify(state.activityLog));
  renderActivity();

  els.activitySection.classList.remove('hidden');
}

function renderActivity() {
  if (state.activityLog.length === 0) return;
  els.activityList.innerHTML = state.activityLog.slice(0, 10).map(a => `
    <div class="activity-item">
      <span class="activity-icon">${a.success ? '✅' : '⚠️'}</span>
      <span class="activity-detail">
        <strong>${a.level}</strong> — ${a.article} ← ${a.course}
      </span>
      <span class="activity-time">${new Date(a.time).toLocaleTimeString()}</span>
    </div>
  `).join('');
}

// ─── Init ──────────────────────────────────────────────────────────────────

(async () => {
  await checkAuth();
  renderActivity();
  if (state.activityLog.length > 0) {
    els.activitySection.classList.remove('hidden');
  }

  // Focus search on load
  els.courseSearch.focus();

  // Auto-detect course from URL hash: #6.006 or #6-006-introduction-to-algorithms
  const hash = window.location.hash.slice(1);
  if (hash) {
    els.courseSearch.value = hash;
    state.courseSlug = hash;
    state.courseId = hash;
    state.courseTitle = hash;
    els.matchBtn.disabled = false;
    // Optionally auto-trigger match
    // setTimeout(() => els.matchBtn.click(), 500);
  }
})();
