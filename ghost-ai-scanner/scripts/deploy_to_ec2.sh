#!/usr/bin/env bash
# =============================================================
# FILE: scripts/deploy_to_ec2.sh
# VERSION: 1.0.0
# UPDATED: 2026-04-19
# OWNER: Giggso Inc
# PURPOSE: List EC2 instances, pick one, SCP the full codebase
#          from this Mac to the chosen EC2, then open an SSH
#          session so you land inside the project directory.
# USAGE:   bash scripts/deploy_to_ec2.sh
# REQUIRES: AWS CLI v2, SSH key (.pem), outbound port 22 open
# =============================================================

set -euo pipefail

# ── Colours ───────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'

ok()   { echo -e "${GREEN}✓${NC} $1"; }
err()  { echo -e "${RED}✗${NC} $1" >&2; exit 1; }
warn() { echo -e "${YELLOW}!${NC} $1"; }
info() { echo -e "${BLUE}→${NC} $1"; }
ask()  { echo -e "\n${BOLD}$1${NC}"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"   # ghost-ai-scanner/

# ══════════════════════════════════════════════════════════════
# BANNER
# ══════════════════════════════════════════════════════════════
clear
echo -e "${BOLD}"
echo "=================================================="
echo "  PatronAI — Deploy Codebase to EC2"
echo "  Giggso Inc  |  v1.0.0"
echo "=================================================="
echo -e "${NC}"
echo "Source: $REPO_DIR"
echo "Steps:  credentials → pick EC2 → SSH details → SCP → SSH in"
echo ""

# ══════════════════════════════════════════════════════════════
# STEP 1 — AWS CREDENTIALS
# ══════════════════════════════════════════════════════════════
echo -e "${BOLD}──────────────────────────────────────────────${NC}"
echo -e "${BOLD}STEP 1 — AWS Credentials${NC}"
echo -e "${BOLD}──────────────────────────────────────────────${NC}"

command -v aws &>/dev/null || err "AWS CLI not found. Install it first: https://aws.amazon.com/cli/"

ask "AWS Access Key ID:"
read -r AWS_ACCESS_KEY_ID
[[ -z "$AWS_ACCESS_KEY_ID" ]] && err "Access Key ID cannot be empty"

ask "AWS Secret Access Key:"
read -r -s AWS_SECRET_ACCESS_KEY
echo ""
[[ -z "$AWS_SECRET_ACCESS_KEY" ]] && err "Secret Access Key cannot be empty"

ask "AWS Region [us-east-1]:"
read -r AWS_REGION
AWS_REGION="${AWS_REGION:-us-east-1}"

export AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_DEFAULT_REGION="$AWS_REGION"

info "Verifying credentials..."
AWS_ACCOUNT=$(aws sts get-caller-identity --query Account --output text 2>/dev/null) \
  || err "Invalid credentials — check your Access Key ID and Secret Access Key."
ok "Credentials valid — Account: $AWS_ACCOUNT   Region: $AWS_REGION"

# ══════════════════════════════════════════════════════════════
# STEP 2 — PICK AN EC2 INSTANCE
# ══════════════════════════════════════════════════════════════
echo ""
echo -e "${BOLD}──────────────────────────────────────────────${NC}"
echo -e "${BOLD}STEP 2 — Pick EC2 Instance${NC}"
echo -e "${BOLD}──────────────────────────────────────────────${NC}"
info "Fetching EC2 instances in $AWS_REGION..."
echo ""

EC2_IDS=()
EC2_NAMES=()
EC2_PUB_IPS=()
EC2_PRIV_IPS=()
EC2_STATES=()
EC2_TYPES=()

# Pull all instances — running and stopped
while IFS=$'\t' read -r id name pub priv state itype; do
  EC2_IDS+=("$id")
  EC2_NAMES+=("${name:-(no name)}")
  EC2_PUB_IPS+=("${pub:-—}")
  EC2_PRIV_IPS+=("${priv:-—}")
  EC2_STATES+=("$state")
  EC2_TYPES+=("$itype")
done < <(aws ec2 describe-instances \
  --region "$AWS_REGION" \
  --query 'Reservations[*].Instances[*].[InstanceId,Tags[?Key==`Name`].Value|[0],PublicIpAddress,PrivateIpAddress,State.Name,InstanceType]' \
  --output text 2>/dev/null \
  | grep -v "^$" \
  | grep -v "terminated" \
  || true)

if [[ ${#EC2_IDS[@]} -eq 0 ]]; then
  warn "No EC2 instances found in $AWS_REGION."
  echo ""
  echo "  [1]  Enter host IP or hostname manually"
  echo "  [2]  Exit and create an EC2 first"
  ask "Choice [1]:"
  read -r C; C="${C:-1}"
  [[ "$C" == "2" ]] && { echo "Exiting."; exit 0; }
  ask "EC2 public IP or hostname:"
  read -r EC2_HOST
  [[ -z "$EC2_HOST" ]] && err "Host cannot be empty"
else
  printf "  %-4s %-22s %-20s %-18s %-10s %s\n" \
    "No." "Instance ID" "Name" "Public IP" "State" "Type"
  printf "  %-4s %-22s %-20s %-18s %-10s %s\n" \
    "---" "-----------" "----" "---------" "-----" "----"
  for i in "${!EC2_IDS[@]}"; do
    printf "  [%s]  %-20s %-20s %-18s %-10s %s\n" \
      "$((i+1))" "${EC2_IDS[$i]}" "${EC2_NAMES[$i]}" \
      "${EC2_PUB_IPS[$i]}" "${EC2_STATES[$i]}" "${EC2_TYPES[$i]}"
  done
  echo ""
  echo "  [$(( ${#EC2_IDS[@]} + 1 ))]  Enter IP manually"
  ask "Which EC2 to deploy to? [1]:"
  read -r EC2_PICK
  EC2_PICK="${EC2_PICK:-1}"

  if [[ "$EC2_PICK" == "$(( ${#EC2_IDS[@]} + 1 ))" ]]; then
    ask "EC2 public IP or hostname:"
    read -r EC2_HOST
    [[ -z "$EC2_HOST" ]] && err "Host cannot be empty"
  else
    IDX=$(( EC2_PICK - 1 ))
    # Prefer public IP; fall back to private
    if [[ "${EC2_PUB_IPS[$IDX]}" != "—" ]]; then
      EC2_HOST="${EC2_PUB_IPS[$IDX]}"
    else
      EC2_HOST="${EC2_PRIV_IPS[$IDX]}"
      warn "No public IP — using private IP $EC2_HOST (requires VPN or bastion)"
    fi
    STATE="${EC2_STATES[$IDX]}"
    if [[ "$STATE" != "running" ]]; then
      warn "Instance state is '$STATE', not 'running'."
      ask "Start this instance? (y/N):"
      read -r START_R
      if [[ "$START_R" =~ ^[yY]$ ]]; then
        info "Starting instance ${EC2_IDS[$IDX]}..."
        aws ec2 start-instances --instance-ids "${EC2_IDS[$IDX]}" --region "$AWS_REGION" >/dev/null
        info "Waiting for instance to reach 'running' state (up to 2 min)..."
        aws ec2 wait instance-running --instance-ids "${EC2_IDS[$IDX]}" --region "$AWS_REGION"
        # Refresh public IP — it may change after start
        EC2_HOST=$(aws ec2 describe-instances \
          --instance-ids "${EC2_IDS[$IDX]}" \
          --region "$AWS_REGION" \
          --query 'Reservations[0].Instances[0].PublicIpAddress' \
          --output text 2>/dev/null)
        ok "Instance running — IP: $EC2_HOST"
      else
        err "Cannot connect to a stopped instance. Start it first."
      fi
    fi
    ok "Target: ${EC2_IDS[$IDX]}  (${EC2_NAMES[$IDX]})  →  $EC2_HOST"
  fi
fi

# ══════════════════════════════════════════════════════════════
# STEP 3 — SSH CONNECTION DETAILS
# ══════════════════════════════════════════════════════════════
echo ""
echo -e "${BOLD}──────────────────────────────────────────────${NC}"
echo -e "${BOLD}STEP 3 — SSH Connection Details${NC}"
echo -e "${BOLD}──────────────────────────────────────────────${NC}"

ask "Path to SSH private key (.pem file):"
read -r EC2_KEY
EC2_KEY="${EC2_KEY/#\~/$HOME}"
[[ ! -f "$EC2_KEY" ]] && err "Key file not found: $EC2_KEY"
chmod 400 "$EC2_KEY" 2>/dev/null || true

ask "SSH username [ec2-user]  (Ubuntu → ubuntu  |  Amazon Linux → ec2-user):"
read -r EC2_USER
EC2_USER="${EC2_USER:-ec2-user}"

DEFAULT_REMOTE="/home/${EC2_USER}/marauder-scan"
ask "Remote directory on EC2 [$DEFAULT_REMOTE]:"
read -r EC2_REMOTE_DIR
EC2_REMOTE_DIR="${EC2_REMOTE_DIR:-$DEFAULT_REMOTE}"

info "Testing SSH connection to ${EC2_USER}@${EC2_HOST}..."
ssh -i "$EC2_KEY" \
  -o StrictHostKeyChecking=no \
  -o ConnectTimeout=15 \
  "${EC2_USER}@${EC2_HOST}" "echo ok" &>/dev/null \
  && ok "SSH connection successful" \
  || err "SSH connection failed. Check: key path, username, security group port 22 open."

# ══════════════════════════════════════════════════════════════
# STEP 4 — SCP CODEBASE
# ══════════════════════════════════════════════════════════════
echo ""
echo -e "${BOLD}──────────────────────────────────────────────${NC}"
echo -e "${BOLD}STEP 4 — Transfer Codebase${NC}"
echo -e "${BOLD}──────────────────────────────────────────────${NC}"
echo ""
echo "  From : $REPO_DIR"
echo "  To   : ${EC2_USER}@${EC2_HOST}:${EC2_REMOTE_DIR}"
echo ""

# Show what will be transferred
FILE_COUNT=$(find "$REPO_DIR" \
  -not -path "*/.git/*" \
  -not -name ".DS_Store" \
  -not -name "*.pyc" \
  -not -path "*/__pycache__/*" \
  -type f | wc -l | tr -d ' ')
echo "  Files to transfer: ~$FILE_COUNT (excluding .git, __pycache__, .DS_Store)"
echo ""
ask "Proceed with transfer? (y/N):"
read -r SCP_CONFIRM
[[ ! "$SCP_CONFIRM" =~ ^[yY]$ ]] && { warn "Transfer cancelled."; exit 0; }

info "Creating remote directory..."
ssh -i "$EC2_KEY" -o StrictHostKeyChecking=no \
  "${EC2_USER}@${EC2_HOST}" "mkdir -p '${EC2_REMOTE_DIR}'"

info "Transferring files..."
rsync -avz --progress \
  --exclude ".git" \
  --exclude "__pycache__" \
  --exclude "*.pyc" \
  --exclude ".DS_Store" \
  --exclude "*.egg-info" \
  --exclude ".env" \
  -e "ssh -i '${EC2_KEY}' -o StrictHostKeyChecking=no" \
  "$REPO_DIR/" \
  "${EC2_USER}@${EC2_HOST}:${EC2_REMOTE_DIR}/" \
  2>/dev/null \
|| {
  # rsync not available — fall back to scp
  warn "rsync not found — falling back to scp (no progress bar)"
  scp -i "$EC2_KEY" \
    -o StrictHostKeyChecking=no \
    -r "$REPO_DIR/." \
    "${EC2_USER}@${EC2_HOST}:${EC2_REMOTE_DIR}/"
}

ok "Codebase transferred to ${EC2_HOST}:${EC2_REMOTE_DIR}"

# ══════════════════════════════════════════════════════════════
# STEP 5 — VERIFY ON EC2
# ══════════════════════════════════════════════════════════════
echo ""
echo -e "${BOLD}──────────────────────────────────────────────${NC}"
echo -e "${BOLD}STEP 5 — Verify Transfer${NC}"
echo -e "${BOLD}──────────────────────────────────────────────${NC}"
info "Checking remote file count..."
REMOTE_COUNT=$(ssh -i "$EC2_KEY" -o StrictHostKeyChecking=no \
  "${EC2_USER}@${EC2_HOST}" \
  "find '${EC2_REMOTE_DIR}' -type f | wc -l" 2>/dev/null | tr -d ' ')
ok "Remote file count: $REMOTE_COUNT"

info "Remote directory listing:"
ssh -i "$EC2_KEY" -o StrictHostKeyChecking=no \
  "${EC2_USER}@${EC2_HOST}" \
  "ls -la '${EC2_REMOTE_DIR}/'" 2>/dev/null

# ══════════════════════════════════════════════════════════════
# STEP 5.5 — BUILD .env ON EC2
# .env is NEVER transferred (excluded from rsync — production
# values differ from local dev). This step reads what is already
# on EC2, prompts only for missing vars, and appends them.
# Re-deploying skips vars that already exist — fully idempotent.
# ══════════════════════════════════════════════════════════════
echo ""
echo -e "${BOLD}──────────────────────────────────────────────${NC}"
echo -e "${BOLD}STEP 5.5 — Environment (.env on EC2)${NC}"
echo -e "${BOLD}──────────────────────────────────────────────${NC}"

ENV_FILE="${EC2_REMOTE_DIR}/.env"

# Read existing keys on EC2 so we don't overwrite them
EXISTING_KEYS=$(ssh -i "$EC2_KEY" -o StrictHostKeyChecking=no \
  "${EC2_USER}@${EC2_HOST}" \
  "[ -f '${ENV_FILE}' ] && grep -oP '^[A-Z_]+(?==)' '${ENV_FILE}' | tr '\n' ' ' || echo ''" \
  2>/dev/null)
info "Existing .env keys on EC2: ${EXISTING_KEYS:-none}"

# Helper: set a var only if not already present
_env_set() {
  local KEY="$1" PROMPT="$2" DEFAULT="$3" SECRET="$4"
  if echo "$EXISTING_KEYS" | grep -qw "$KEY"; then
    ok "  $KEY already set — skipping"
    return
  fi
  if [[ -n "$DEFAULT" ]]; then
    ask "  $KEY [$DEFAULT]:"
  else
    ask "  $KEY (required):"
  fi
  if [[ "$SECRET" == "yes" ]]; then
    read -r -s VAL; echo ""
  else
    read -r VAL
  fi
  VAL="${VAL:-$DEFAULT}"
  if [[ -z "$VAL" ]]; then
    warn "  $KEY left empty — app may not start correctly"
    return
  fi
  ssh -i "$EC2_KEY" -o StrictHostKeyChecking=no \
    "${EC2_USER}@${EC2_HOST}" \
    "echo '${KEY}=${VAL}' >> '${ENV_FILE}'"
  ok "  $KEY written"
}

echo ""
echo "  Enter values for each required var."
echo "  Press Enter to accept [default]. Already-set vars are skipped."
echo ""

ssh -i "$EC2_KEY" -o StrictHostKeyChecking=no \
  "${EC2_USER}@${EC2_HOST}" "touch '${ENV_FILE}'"

_env_set "MARAUDER_SCAN_BUCKET" "" "patronai"         ""
_env_set "AWS_REGION"           "" "us-east-1"        ""
_env_set "COMPANY_NAME"         "" "PatronAI"         ""
_env_set "GRAFANA_URL"          "" ""                 ""
_env_set "PUBLIC_HOST"          "" "$EC2_HOST"        ""
# LLM vars are written by Step 7 — skip here
ok ".env ready at ${ENV_FILE}"

# ══════════════════════════════════════════════════════════════
# STEP 6 — MCP SERVER SETUP
# (stdio transport — no persistent process; Claude Desktop
#  spawns it on demand via SSH. This step installs deps and
#  validates the server is importable after every deploy.)
# ══════════════════════════════════════════════════════════════
echo ""
echo -e "${BOLD}──────────────────────────────────────────────${NC}"
echo -e "${BOLD}STEP 6 — MCP Server Setup${NC}"
echo -e "${BOLD}──────────────────────────────────────────────${NC}"

MCP_SCRIPT="${EC2_REMOTE_DIR}/scripts/patronai_mcp_server.py"

info "Installing / updating Python dependencies (includes fastmcp)..."
ssh -i "$EC2_KEY" -o StrictHostKeyChecking=no \
  "${EC2_USER}@${EC2_HOST}" \
  "cd '${EC2_REMOTE_DIR}' && pip install -q -r requirements.txt 2>&1 | tail -5" \
  && ok "Dependencies installed" \
  || warn "pip install had warnings — check manually"

info "Making MCP server script executable..."
ssh -i "$EC2_KEY" -o StrictHostKeyChecking=no \
  "${EC2_USER}@${EC2_HOST}" \
  "chmod +x '${MCP_SCRIPT}'" \
  && ok "Script is executable: $MCP_SCRIPT"

info "Smoke-testing MCP server import..."
MCP_SMOKE=$(ssh -i "$EC2_KEY" -o StrictHostKeyChecking=no \
  "${EC2_USER}@${EC2_HOST}" \
  "cd '${EC2_REMOTE_DIR}' && \
   python -c \"
import sys
sys.path.insert(0, 'src')
from fastmcp import FastMCP
from chat.tools import get_summary_stats
from chat.tools_schema import TOOLS_SCHEMA
print('OK tools=%d' % len(TOOLS_SCHEMA))
\" 2>&1" || echo "FAIL")

if [[ "$MCP_SMOKE" == OK* ]]; then
  ok "MCP smoke test passed — $MCP_SMOKE"
else
  warn "MCP smoke test output: $MCP_SMOKE"
  warn "MCP server may need manual check — continuing deploy"
fi

# Print ready-to-paste Claude Desktop config
EC2_KEY_ABS=$(realpath "$EC2_KEY" 2>/dev/null || echo "$EC2_KEY")
echo ""
echo -e "${BOLD}${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}  PatronAI MCP — Claude Desktop Config${NC}"
echo -e "${BOLD}${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "  Add to: ~/.config/claude/claude_desktop_config.json"
echo "  (macOS: ~/Library/Application Support/Claude/claude_desktop_config.json)"
echo ""
echo '  "mcpServers": {'
echo '    "patronai": {'
echo '      "command": "ssh",'
echo '      "args": ['
echo "        \"-i\", \"${EC2_KEY_ABS}\","
echo '        "-o", "StrictHostKeyChecking=yes",'
echo "        \"${EC2_USER}@${EC2_HOST}\","
echo "        \"python ${MCP_SCRIPT}\""
echo '      ]'
echo '    }'
echo '  }'
echo ""
echo -e "${YELLOW}  V1 Security: SSH stdio only. Access = SSH key to EC2.${NC}"
echo -e "${YELLOW}  Revoke: remove public key from authorized_keys on EC2.${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# ══════════════════════════════════════════════════════════════
# STEP 7 — LLM SETUP (powers the 🤖 Ask AI chat widget)
# Priority: llama-server (already on box) → Ollama → offer install
# ══════════════════════════════════════════════════════════════
echo ""
echo -e "${BOLD}──────────────────────────────────────────────${NC}"
echo -e "${BOLD}STEP 7 — LLM Setup (Chat Widget)${NC}"
echo -e "${BOLD}──────────────────────────────────────────────${NC}"

# Detect what LLM runtime is available on EC2
LLM_DETECT=$(ssh -i "$EC2_KEY" -o StrictHostKeyChecking=no \
  "${EC2_USER}@${EC2_HOST}" \
  'if command -v llama-server &>/dev/null; then echo "llama";
   elif command -v ollama &>/dev/null; then echo "ollama";
   else echo "none"; fi' 2>/dev/null)

LLM_PROVIDER_VAL="openai_compat"
LLM_BASE_URL_VAL="http://localhost:8080"
LLM_MODEL_VAL=""

if [[ "$LLM_DETECT" == "llama" ]]; then
  ok "llama-server found on EC2 (port 8080)"
  LLM_BASE_URL_VAL="http://localhost:8080"
  # Search for the LFM2.5-1.2B-Thinking GGUF first, then any .gguf fallback.
  # Path patterns cover both bake-time copies (/models/lfm2*) and runtime
  # downloads via `llama-server --hf-repo` (HuggingFace cache layout).
  LLM_MODEL_PATH=$(ssh -i "$EC2_KEY" -o StrictHostKeyChecking=no \
    "${EC2_USER}@${EC2_HOST}" \
    'find /models -iname "lfm2*1.2b*thinking*.gguf" \
                  -o -iname "lfm2.5*.gguf" \
     2>/dev/null | head -1' \
    2>/dev/null || echo "")
  # Fallback to any .gguf present on the box
  if [[ -z "$LLM_MODEL_PATH" ]]; then
    LLM_MODEL_PATH=$(ssh -i "$EC2_KEY" -o StrictHostKeyChecking=no \
      "${EC2_USER}@${EC2_HOST}" \
      'find /models -name "*.gguf" 2>/dev/null | head -1' 2>/dev/null || echo "")
  fi
  if [[ -n "$LLM_MODEL_PATH" ]]; then
    ok "Model: $LLM_MODEL_PATH"
    # Install systemd service so llama-server survives reboots
    ssh -i "$EC2_KEY" -o StrictHostKeyChecking=no \
      "${EC2_USER}@${EC2_HOST}" "
      LLAMA_BIN=\$(which llama-server)
      sudo tee /etc/systemd/system/llama-server.service > /dev/null <<EOF
[Unit]
Description=llama.cpp server — LFM2.5-1.2B-Thinking
After=network.target
[Service]
ExecStart=\${LLAMA_BIN} --model ${LLM_MODEL_PATH} --port 8080 --ctx-size 4096
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
[Install]
WantedBy=multi-user.target
EOF
      sudo systemctl daemon-reload
      sudo systemctl enable --now llama-server
    "
    ok "llama-server systemd service installed and started"
  else
    warn "No .gguf found — expected at /models/lfm2.5-1.2b-thinking-q4_k_m.gguf or downloadable via --hf-repo"
    warn "Upload the model to EC2 then re-deploy to activate chat."
    LLM_DETECT="none"
  fi

elif [[ "$LLM_DETECT" == "ollama" ]]; then
  ok "Ollama found on EC2"
  LLM_BASE_URL_VAL="http://localhost:11434"

  # Pick model — default lfm2:1b (matches our llama-server default family;
  # ~750 MB, tool-capable, fits a t3.large CPU). Larger options stay
  # available for hosts with more RAM / GPU.
  ask "Ollama model to use [lfm2:1b]  (alternatives: qwen3:8b ~5.2GB, qwen3:14b, llama3.2):"
  read -r OLLAMA_MODEL
  OLLAMA_MODEL="${OLLAMA_MODEL:-lfm2:1b}"
  LLM_MODEL_VAL="$OLLAMA_MODEL"

  info "Pulling model $OLLAMA_MODEL (may take a few minutes)..."
  ssh -i "$EC2_KEY" -o StrictHostKeyChecking=no \
    "${EC2_USER}@${EC2_HOST}" \
    "ollama pull '${OLLAMA_MODEL}'" \
    && ok "Model ready: $OLLAMA_MODEL" \
    || warn "ollama pull had issues — check EC2 connectivity"

  # Ensure Ollama service is running
  ssh -i "$EC2_KEY" -o StrictHostKeyChecking=no \
    "${EC2_USER}@${EC2_HOST}" \
    "sudo systemctl enable --now ollama 2>/dev/null || \
     pgrep -f 'ollama serve' >/dev/null || \
     nohup ollama serve >> /tmp/ollama.log 2>&1 &"
  ok "Ollama service running"

else
  warn "No LLM runtime found on EC2."
  ask "Install Ollama now? (recommended for V1) (y/N):"
  read -r INSTALL_OLLAMA
  if [[ "$INSTALL_OLLAMA" =~ ^[yY]$ ]]; then
    info "Installing Ollama on EC2..."
    ssh -i "$EC2_KEY" -o StrictHostKeyChecking=no \
      "${EC2_USER}@${EC2_HOST}" \
      "curl -fsSL https://ollama.ai/install.sh | sh" \
      && ok "Ollama installed" \
      || err "Ollama install failed — check EC2 internet access"

    ask "Model to pull [lfm2:1b]  (~750 MB; or qwen3:8b ~5.2 GB if you need a bigger model):"
    read -r OLLAMA_MODEL
    OLLAMA_MODEL="${OLLAMA_MODEL:-lfm2:1b}"
    LLM_MODEL_VAL="$OLLAMA_MODEL"
    LLM_BASE_URL_VAL="http://localhost:11434"
    LLM_DETECT="ollama"

    info "Pulling $OLLAMA_MODEL..."
    ssh -i "$EC2_KEY" -o StrictHostKeyChecking=no \
      "${EC2_USER}@${EC2_HOST}" \
      "ollama pull '${OLLAMA_MODEL}'" \
      && ok "Model ready: $OLLAMA_MODEL"
    ssh -i "$EC2_KEY" -o StrictHostKeyChecking=no \
      "${EC2_USER}@${EC2_HOST}" \
      "sudo systemctl enable --now ollama 2>/dev/null || \
       nohup ollama serve >> /tmp/ollama.log 2>&1 &"
  else
    warn "Skipping LLM setup — chat widget will show 'LLM server unreachable'."
    warn "Place model at /models/lfm2.5-1.2b-thinking-q4_k_m.gguf and re-deploy to activate chat."
  fi
fi

# Write LLM vars to .env ONLY for non-default configs (cloud APIs).
# Local llama.cpp on port 8080 is the built-in default — no .env needed.
# Rule: if LLM_BASE_URL is the llama.cpp default AND no API key, skip .env.
_LLAMA_DEFAULT_URL="http://localhost:8080"
if [[ "$LLM_DETECT" != "none" ]]; then
  ENV_FILE="${EC2_REMOTE_DIR}/.env"
  if [[ "$LLM_BASE_URL_VAL" == "$_LLAMA_DEFAULT_URL" && -z "$LLM_MODEL_VAL" ]]; then
    ok "Local llama.cpp on :8080 — no .env LLM entries needed (built-in defaults)"
    # Remove any stale LLM_ lines from previous non-default deploys
    ssh -i "$EC2_KEY" -o StrictHostKeyChecking=no \
      "${EC2_USER}@${EC2_HOST}" \
      "sed -i '/^LLM_PROVIDER=/d;/^LLM_BASE_URL=/d;/^LLM_MODEL=/d;/^LLM_API_KEY=/d' \
       '${ENV_FILE}' 2>/dev/null || true"
  else
    # Non-default config (Ollama, cloud API) — write explicit vars
    ssh -i "$EC2_KEY" -o StrictHostKeyChecking=no \
      "${EC2_USER}@${EC2_HOST}" "
      touch '${ENV_FILE}'
      sed -i '/^LLM_PROVIDER=/d;/^LLM_BASE_URL=/d;/^LLM_MODEL=/d' '${ENV_FILE}'
      echo 'LLM_PROVIDER=${LLM_PROVIDER_VAL}' >> '${ENV_FILE}'
      echo 'LLM_BASE_URL=${LLM_BASE_URL_VAL}' >> '${ENV_FILE}'
      echo 'LLM_MODEL=${LLM_MODEL_VAL}'        >> '${ENV_FILE}'
    "
    ok ".env updated with LLM config (non-default: ${LLM_BASE_URL_VAL})"
  fi

  # Connectivity smoke test — give service 5 s to accept connections
  info "Testing LLM connectivity at ${LLM_BASE_URL_VAL}..."
  sleep 5
  LLM_OK=$(ssh -i "$EC2_KEY" -o StrictHostKeyChecking=no \
    "${EC2_USER}@${EC2_HOST}" \
    "curl -sf '${LLM_BASE_URL_VAL}/v1/models' | python3 -c \
     'import sys,json; d=json.load(sys.stdin); print(\"OK models=%d\"%len(d.get(\"data\",[])))' \
     2>/dev/null || echo FAIL" 2>/dev/null)
  if [[ "$LLM_OK" == OK* ]]; then
    ok "LLM ready — $LLM_OK"
  else
    warn "LLM not yet answering — model may still be loading (LFM2.5-1.2B-Thinking takes ~10-20 s on CPU)."
    warn "Check on EC2:  curl ${LLM_BASE_URL_VAL}/v1/models"
    warn "  or tail log:  journalctl -u llama-server -f"
  fi
fi

# ══════════════════════════════════════════════════════════════
# DONE + SSH IN
# ══════════════════════════════════════════════════════════════
echo ""
echo -e "${BOLD}${GREEN}"
echo "=================================================="
echo "  Deploy complete!"
echo "=================================================="
echo -e "${NC}"
echo "  EC2:       ${EC2_USER}@${EC2_HOST}"
echo "  Directory: ${EC2_REMOTE_DIR}"
echo "  MCP:       Ready — paste config above into Claude Desktop"
echo "  LLM:       ${LLM_BASE_URL_VAL} (${LLM_DETECT})"
echo ""
echo "Remaining on EC2 (first deploy only):"
echo "  1. Run prereqs.sh to set up AWS resources and .env"
echo "  2. docker-compose up -d"
echo ""
ask "Open SSH session to EC2 now? (y/N):"
read -r SSH_NOW
if [[ "$SSH_NOW" =~ ^[yY]$ ]]; then
  echo ""
  ok "Connecting to ${EC2_USER}@${EC2_HOST} — landing in ${EC2_REMOTE_DIR}"
  echo ""
  ssh -i "$EC2_KEY" \
    -o StrictHostKeyChecking=no \
    -t \
    "${EC2_USER}@${EC2_HOST}" \
    "cd '${EC2_REMOTE_DIR}' && exec \$SHELL -l"
else
  echo ""
  echo "To connect manually:"
  echo "  ssh -i $EC2_KEY ${EC2_USER}@${EC2_HOST}"
  echo "  cd ${EC2_REMOTE_DIR}"
fi
echo ""
echo -e "${BOLD}Giggso Inc x TrinityOps.ai x AIRTaaS${NC}"
