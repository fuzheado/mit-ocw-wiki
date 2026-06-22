#!/bin/bash
# deploy.sh — Deploy the Wiki MIT Workbench to Toolforge
#
# Usage:
#   ./deploy.sh              # Deploy to toolforge
#   ./deploy.sh --local      # Start locally for development
#
# Prerequisites:
#   - Toolforge account with SSH key loaded
#   - Tool created: https://toolsadmin.wikimedia.org/tools/create
#   - Bot password configured via: toolforge env set WIKI_BOT_USER=... WIKI_BOT_PASS=...

set -euo pipefail

TOOL_NAME="${TOOL_NAME:-wiki-mit}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ "${1:-}" = "--local" ]; then
  echo "Starting local dev server on http://localhost:8765"
  echo "  (OAuth callback, bot password, and course index may not work locally)"
  cd "$SCRIPT_DIR"
  node server.mjs
  exit 0
fi

echo "Deploying to Toolforge tool: $TOOL_NAME"

# Read shell username from config (non-echoing)
TF_USER=$(python3 -c "
import json, os
config = json.load(open(os.path.expanduser('~/.toolforge/config.json')))
print(config['shell_username'])
")

# 1. Create directories on Toolforge
echo "  → Creating directories..."
ssh "$TF_USER@login.toolforge.org" "
  sudo -niu tools.$TOOL_NAME mkdir -p /data/project/$TOOL_NAME/public
  sudo -niu tools.$TOOL_NAME mkdir -p /data/project/$TOOL_NAME/scripts
"

# 2. Copy server and public files
echo "  → Copying server..."
scp "$SCRIPT_DIR/server.mjs" "$SCRIPT_DIR/package.json" \
    "$TF_USER@login.toolforge.org:/data/project/$TOOL_NAME/"

echo "  → Copying static assets..."
scp "$SCRIPT_DIR/public/index.html" "$SCRIPT_DIR/public/style.css" "$SCRIPT_DIR/public/app.js" \
    "$TF_USER@login.toolforge.org:/data/project/$TOOL_NAME/public/"

# 3. Copy Python scripts (the project is at ../scripts relative to toolforge/)
echo "  → Copying project scripts..."
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
ssh "$TF_USER@login.toolforge.org" "
  sudo -niu tools.$TOOL_NAME mkdir -p /data/project/$TOOL_NAME/wiki/courses
  sudo -niu tools.$TOOL_NAME mkdir -p /data/project/$TOOL_NAME/.wiki_cache
"

# Copy key scripts
for script in \
  scripts/ad-hoc-match.py \
  scripts/contribution-protocol.py \
  scripts/apply-l1-refideas.py \
  scripts/apply-l2-external-links.py \
  scripts/refideas-add.py \
  scripts/lint-refideas.py \
  scripts/test-refideas.py \
  scripts/test-l1-refideas-insert.py \
  scripts/test-l2-external-links.py; do
  if [ -f "$PROJECT_DIR/$script" ]; then
    scp "$PROJECT_DIR/$script" "$TF_USER@login.toolforge.org:/data/project/$TOOL_NAME/scripts/"
  fi
done

# Copy course wiki files
echo "  → Copying course index..."
scp -r "$PROJECT_DIR/wiki/courses/"*.md "$TF_USER@login.toolforge.org:/data/project/$TOOL_NAME/wiki/courses/" 2>/dev/null || echo "    (no course files to copy — they can be generated later)"

# 4. Set environment variables (if configured locally)
if [ -f "$HOME/.wiki-mit.env" ]; then
  echo "  → Setting environment variables from ~/.wiki-mit.env..."
  source "$HOME/.wiki-mit.env"
  if [ -n "${WIKI_BOT_USER:-}" ]; then
    ssh "$TF_USER@login.toolforge.org" "sudo -niu tools.$TOOL_NAME toolforge env set WIKI_BOT_USER '$WIKI_BOT_USER'"
  fi
  if [ -n "${WIKI_BOT_PASS:-}" ]; then
    ssh "$TF_USER@login.toolforge.org" "sudo -niu tools.$TOOL_NAME toolforge env set WIKI_BOT_PASS '$WIKI_BOT_PASS'"
  fi
else
  echo "  ⚠️  No ~/.wiki-mit.env found. Set env vars manually:"
  echo "     ssh $TF_USER@login.toolforge.org"
  echo "     become $TOOL_NAME toolforge env set WIKI_BOT_USER YourUser@BotName"
  echo "     become $TOOL_NAME toolforge env set WIKI_BOT_PASS your_bot_password"
fi

# 5. Start webservice
echo "  → Starting webservice..."
ssh "$TF_USER@login.toolforge.org" "
  sudo -niu tools.$TOOL_NAME webservice --backend=kubernetes node22 restart
"

echo ""
echo "✅ Deployed! Visit: https://$TOOL_NAME.toolforge.org"
echo ""
echo "To check status:"
echo "  ssh $TF_USER@login.toolforge.org"
echo "  become $TOOL_NAME webservice --backend=kubernetes node22 status"
echo ""
echo "To view logs:"
echo "  ssh $TF_USER@login.toolforge.org"
echo "  become $TOOL_NAME kubectl logs -f deployment/$TOOL_NAME"
