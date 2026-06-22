# Wiki MIT — Toolforge Workbench

Web-based contribution interface for connecting MIT OCW courses to Wikipedia.
Implements the Contribution Ladder: search → match → preview → apply.

## Quick Start

```bash
# Local dev (no auth needed for browsing)
cd toolforge
node server.mjs
# Open http://localhost:8765

# Or use the deploy script
./deploy.sh --local
```

## Deploy to Toolforge

### Prerequisites

1. **Toolforge account** with a tool created (`wiki-mit`):
   ```bash
   python3 ~/.pi/agent/skills/toolforge/scripts/login-toolsadmin.py \
     --create wiki-mit "Wiki MIT Workbench" "Contribution interface connecting MIT OCW to Wikipedia"
   ```

2. **Bot password** for Wikipedia editing (create at `Special:BotPasswords`):
   - Bot name: `ocw-workbench`
   - Grants: `Edit existing pages`, `Create, edit, and move pages`, `High-volume text querying`

3. **Credentials file** at `~/.wiki-mit.env`:
   ```bash
   export WIKI_BOT_USER="YourWikiUsername@ocw-workbench"
   export WIKI_BOT_PASS="your_bot_password_here"
   ```

### Deploy

```bash
cd toolforge
./deploy.sh
```

The app will be available at `https://wiki-mit.toolforge.org`.

### Check Status

```bash
TF_USER=$(python3 -c "import json; print(json.load(open('$HOME/.toolforge/config.json'))['shell_username'])")
ssh "$TF_USER@login.toolforge.org"

# On Toolforge:
become wiki-mit webservice --backend=kubernetes node22 status
become wiki-mit kubectl logs -f deployment/wiki-mit
```

## Architecture

```
Browser ←→ Toolforge Pod (Node.js server.mjs)
              │
              ├─ /api/courses      → Course index (from wiki/courses/*.md)
              ├─ /api/match        → ad-hoc-match.py (Python subprocess)
              ├─ /api/preview      → Server-generated wikitext
              ├─ /api/apply        → apply-l1-refideas.py / apply-l2-external-links.py
              └─ /api/oauth/*      → OAuth 2.0 flow (future)
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/health` | Health check + course count |
| `GET` | `/api/courses?q=...` | Search course index |
| `GET` | `/api/match?course=...` | Match course to Wikipedia articles |
| `POST` | `/api/preview` | Generate wikitext preview (L1/L2) |
| `POST` | `/api/apply` | Apply edit to Wikipedia (auth required) |
| `GET` | `/api/auth/status` | Current auth state |

## Auth modes

| Mode | When | Edit attribution |
|------|------|-----------------|
| **None** | No credentials set | Read-only (browse + preview) |
| **Bot password** | `WIKI_BOT_USER` + `WIKI_BOT_PASS` set | Bot account (e.g., `YourName@ocw-workbench`) |
| **OAuth 2.0** | `OAUTH_CLIENT_ID` + `OAUTH_CLIENT_SECRET` set | Individual editor accounts (future) |

## Project structure

```
toolforge/
├── server.mjs         # Zero-dependency Node.js server
├── package.json       # Minimal package metadata
├── deploy.sh          # Deploy to Toolforge + local dev mode
├── public/
│   ├── index.html     # Main UI (search → match → preview → apply)
│   ├── style.css      # Responsive card-based layout
│   └── app.js         # SPA logic, auth, API calls
└── README.md          # This file
```

Depends on scripts from the parent project at `../scripts/` (or `./scripts/` on Toolforge):
- `ad-hoc-match.py` — course → Wikipedia article matching
- `contribution-protocol.py` — L1-L5 data model and wikitext generation
- `apply-l1-refideas.py` — L1 refideas insertion
- `apply-l2-external-links.py` — L2 external links insertion
