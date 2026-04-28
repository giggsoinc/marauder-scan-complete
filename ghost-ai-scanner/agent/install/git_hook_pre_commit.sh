#!/usr/bin/env bash
# =============================================================
# FILE: agent/install/git_hook_pre_commit.sh
# PROJECT: PatronAI — Marauder Scan code layer
# VERSION: 1.0.0
# UPDATED: 2026-04-18
# OWNER: Giggso Inc
# PURPOSE: Installs a pre-commit git hook on the device.
#          Hook extracts diffs on every commit, checks for AI
#          signal patterns, ships matching diffs to S3.
#          Zero inference. Zero LLM. Runs in milliseconds.
#          EC2 scanner does the analysis.
# USAGE: bash agent/install/git_hook_pre_commit.sh
# =============================================================

set -euo pipefail

AGENT_DIR="$HOME/.marauder-scan"
CONFIG="$AGENT_DIR/config.json"
HOOK_SCRIPT="$AGENT_DIR/pre_commit_hook.sh"

# ── Validate config ───────────────────────────────────────────
if [ ! -f "$CONFIG" ]; then
  echo "ERROR: marauder-scan agent config not found at $CONFIG"
  echo "Run the MDM install script first."
  exit 1
fi

BUCKET=$(python3 -c "import json; print(json.load(open('$CONFIG'))['bucket'])")
REGION=$(python3 -c "import json; print(json.load(open('$CONFIG'))['region'])")
COMPANY=$(python3 -c "import json; print(json.load(open('$CONFIG'))['company'])")

echo "Installing Marauder Scan pre-commit hook..."
echo "  Bucket:  $BUCKET"
echo "  Region:  $REGION"
echo "  Company: $COMPANY"

# ── Write the hook script ─────────────────────────────────────
cat > "$HOOK_SCRIPT" << 'HOOK_EOF'
#!/usr/bin/env bash
# Marauder Scan — pre-commit hook
# Ships AI signal diffs to S3 for analysis. Zero inference.

AGENT_DIR="$HOME/.marauder-scan"
CONFIG="$AGENT_DIR/config.json"

# Load config
BUCKET=$(python3 -c "import json; print(json.load(open('$CONFIG'))['bucket'])" 2>/dev/null)
REGION=$(python3 -c "import json; print(json.load(open('$CONFIG'))['region'])" 2>/dev/null)
COMPANY=$(python3 -c "import json; print(json.load(open('$CONFIG'))['company'])" 2>/dev/null)

if [ -z "$BUCKET" ]; then
  exit 0  # Config missing — skip silently, never block commits
fi

# AI signal patterns to detect in diffs
# All frameworks + MCP patterns from unauthorized_code.csv
AI_SIGNALS="langchain|langgraph|llama_index|llama-index|haystack|fastagency|mastra|\
autogen|ag2|semantic_kernel|SemanticKernel|crewai|CrewAI|metagpt|MetaGPT|\
from agents import|openai\.agents|Runner\.run|google\.adk|google_adk|\
pydantic_ai|smolagents|SmolaAgents|\
MCPServer|mcp_server|stdio_server|mcp\.run|use_mcp_tool|call_tool|\
from mcp import|modelcontextprotocol|mcp\.Client|@function_tool|\
import ollama|from ollama|llama_cpp|gpt4all|GPT4All|\
api\.openai\.com|api\.anthropic\.com|api\.cohere\.ai|api\.mistral\.ai|\
sk-proj-|sk-ant-|hf_[a-zA-Z0-9]"

# Extract staged diff
DIFF=$(git diff --cached --unified=3 2>/dev/null || echo "")

if [ -z "$DIFF" ]; then
  exit 0
fi

# Pre-filter — only ship if AI signals present
if ! echo "$DIFF" | grep -qiE "$AI_SIGNALS"; then
  exit 0  # No AI signals — exit cleanly
fi

# Build payload and ship to S3
DEVICE_ID=$(hostname)
TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)
REPO=$(git rev-parse --show-toplevel 2>/dev/null | xargs basename)
BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)
COMMIT_MSG=$(git log --format=%s -n 1 HEAD 2>/dev/null || echo "")

# Truncate diff to 5KB max
DIFF_SNIPPET=$(echo "$DIFF" | head -c 5120)

PAYLOAD=$(python3 -c "
import json, sys
payload = {
    'event_type':   'GIT_DIFF_SIGNAL',
    'source':       'marauder_scan_git_hook',
    'device_id':    '${DEVICE_ID}',
    'company':      '${COMPANY}',
    'repo':         '${REPO}',
    'branch':       '${BRANCH}',
    'commit_msg':   '${COMMIT_MSG}',
    'timestamp':    '${TIMESTAMP}',
    'diff_snippet': sys.argv[1],
}
print(json.dumps(payload))
" "$DIFF_SNIPPET" 2>/dev/null)

# Ship to S3 — fire and forget, never block the commit
S3_KEY="ocsf/agent/git-diffs/${DEVICE_ID}-${TIMESTAMP}.json"
aws s3 cp - "s3://${BUCKET}/${S3_KEY}" \
  --region "$REGION" \
  --content-type "application/json" \
  --quiet \
  <<< "$PAYLOAD" 2>/dev/null &

# Always exit 0 — never block commits
exit 0
HOOK_EOF

chmod +x "$HOOK_SCRIPT"

# ── Install hook into all git repos ──────────────────────────
HOOK_NAME="pre-commit"
INSTALL_COUNT=0

# Common code directories to search
for SEARCH_DIR in "$HOME" "/home" "/workspace" "/srv" "/opt"; do
  if [ ! -d "$SEARCH_DIR" ]; then continue; fi
  while IFS= read -r -d '' GIT_DIR; do
    HOOKS_DIR="${GIT_DIR}/.git/hooks"
    if [ ! -d "$HOOKS_DIR" ]; then continue; fi
    HOOK_PATH="$HOOKS_DIR/$HOOK_NAME"
    # Back up existing hook if present
    if [ -f "$HOOK_PATH" ] && [ ! -L "$HOOK_PATH" ]; then
      cp "$HOOK_PATH" "${HOOK_PATH}.pre-marauder-backup"
    fi
    # Install as symlink
    ln -sf "$HOOK_SCRIPT" "$HOOK_PATH"
    INSTALL_COUNT=$((INSTALL_COUNT + 1))
  done < <(find "$SEARCH_DIR" -maxdepth 4 -name ".git" -type d -print0 2>/dev/null)
done

echo "Marauder Scan pre-commit hook installed in $INSTALL_COUNT repositories."
echo "Commits with AI framework patterns will be shipped to S3 for analysis."
echo "Hook never blocks commits. Analysis is asynchronous."
