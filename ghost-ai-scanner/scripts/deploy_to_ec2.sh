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
# DONE + SSH IN
# ══════════════════════════════════════════════════════════════
echo ""
echo -e "${BOLD}${GREEN}"
echo "=================================================="
echo "  Transfer complete!"
echo "=================================================="
echo -e "${NC}"
echo "  EC2:       ${EC2_USER}@${EC2_HOST}"
echo "  Directory: ${EC2_REMOTE_DIR}"
echo ""
echo "What's next on the EC2:"
echo "  1. Run prereqs.sh to set up AWS resources and generate .env"
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
