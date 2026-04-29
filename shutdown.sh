#!/usr/bin/env bash
# =============================================================
# FILE: shutdown.sh
# VERSION: 1.0.0
# UPDATED: 2026-04-19
# OWNER: Giggso Inc
# PURPOSE: Clean shutdown of PatronAI on EC2.
#          Stops all containers gracefully, shows final log
#          summary, and optionally stops the EC2 instance.
# USAGE:   bash shutdown.sh   (from patronai/)
# =============================================================

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'

ok()      { echo -e "${GREEN}✓${NC} $1"; }
err()     { echo -e "${RED}✗${NC} $1" >&2; exit 1; }
warn()    { echo -e "${YELLOW}!${NC} $1"; }
info()    { echo -e "${BLUE}→${NC} $1"; }
ask()     { echo -e "\n${BOLD}$1${NC}"; }
divider() { echo -e "\n${BOLD}──────────────────────────────────────────────${NC}"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EC2_KEY=""; EC2_USER="ec2-user"; EC2_HOST=""; INSTANCE_ID=""
REMOTE_DIR="/home/ec2-user/marauder-scan"

# ══════════════════════════════════════════════════════════════
# BANNER
# ══════════════════════════════════════════════════════════════
clear
echo -e "${BOLD}"
echo "=================================================="
echo "  PatronAI — Clean Shutdown"
echo "  Giggso Inc  |  v1.0.0"
echo "=================================================="
echo -e "${NC}"
echo "This script will:"
echo "  • Stop all Docker containers gracefully (docker-compose down)"
echo "  • Show final log summary"
echo "  • Optionally stop the EC2 instance"
echo ""

# ── Detect if running directly ON the EC2 ─────────────────────
ON_EC2=false
IMDS_TOKEN=$(curl -sf --max-time 2 \
  -X PUT "http://169.254.169.254/latest/api/token" \
  -H "X-aws-ec2-metadata-token-ttl-seconds: 60" 2>/dev/null || echo "")
if [[ -n "$IMDS_TOKEN" ]]; then
  curl -sf --max-time 2 \
    -H "X-aws-ec2-metadata-token: $IMDS_TOKEN" \
    http://169.254.169.254/latest/meta-data/instance-id &>/dev/null \
    && ON_EC2=true || true
else
  curl -sf --max-time 2 \
    http://169.254.169.254/latest/meta-data/instance-id &>/dev/null \
    && ON_EC2=true || true
fi

# ══════════════════════════════════════════════════════════════
# PATH A — Running directly on EC2
# ══════════════════════════════════════════════════════════════
if [[ "$ON_EC2" == true ]]; then
  ok "Running on EC2 — shutting down locally"

  # Find the project dir
  if [[ -f "$SCRIPT_DIR/docker-compose.yml" ]]; then
    REMOTE_DIR="$SCRIPT_DIR"
  elif [[ -f "$SCRIPT_DIR/ghost-ai-scanner/docker-compose.yml" ]]; then
    REMOTE_DIR="$SCRIPT_DIR/ghost-ai-scanner"
  fi

  divider
  echo -e "${BOLD}STEP 1 — Container Status${NC}"
  cd "$REMOTE_DIR"
  docker-compose ps 2>/dev/null || warn "docker-compose not found or no containers running"

  divider
  echo -e "${BOLD}STEP 2 — Final Log Snapshot (last 20 lines per container)${NC}"
  echo ""
  for SVC in scanner grafana nginx; do
    LOGS=$(docker-compose logs --tail=20 "$SVC" 2>/dev/null || echo "")
    if [[ -n "$LOGS" ]]; then
      echo -e "${BOLD}  ── $SVC ──${NC}"
      echo "$LOGS" | tail -20
      echo ""
    fi
  done

  divider
  echo -e "${BOLD}STEP 3 — Stop Containers${NC}"
  ask "Stop all containers now? (y/N):"
  read -r STOP_R
  if [[ "$STOP_R" =~ ^[yY]$ ]]; then
    info "Running docker-compose down..."
    docker-compose down --timeout 30
    ok "All containers stopped"
  else
    warn "Shutdown cancelled — containers still running."
    exit 0
  fi

  ok "Shutdown complete."
  echo ""
  warn "To restart: cd $REMOTE_DIR && docker-compose up -d"
  exit 0
fi

# ══════════════════════════════════════════════════════════════
# PATH B — Running from Mac, SSH into EC2
# ══════════════════════════════════════════════════════════════

# ── STEP 1: AWS Credentials ───────────────────────────────────
divider
echo -e "${BOLD}STEP 1 — AWS Credentials${NC}"
command -v aws &>/dev/null || err "AWS CLI not found."

ask "AWS Access Key ID:"
read -r AWS_ACCESS_KEY_ID
[[ -z "$AWS_ACCESS_KEY_ID" ]] && err "Cannot be empty"

ask "AWS Secret Access Key:"
read -r -s AWS_SECRET_ACCESS_KEY
echo ""
[[ -z "$AWS_SECRET_ACCESS_KEY" ]] && err "Cannot be empty"

ask "AWS Region [us-east-1]:"
read -r AWS_REGION
AWS_REGION="${AWS_REGION:-us-east-1}"

export AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_DEFAULT_REGION="$AWS_REGION"
AWS_ACCOUNT=$(aws sts get-caller-identity --query Account --output text 2>/dev/null) \
  || err "Invalid credentials."
ok "Valid — Account: $AWS_ACCOUNT   Region: $AWS_REGION"

# ── STEP 2: Pick EC2 ─────────────────────────────────────────
divider
echo -e "${BOLD}STEP 2 — EC2 Instance${NC}"
info "Fetching running EC2 instances..."
echo ""

EC2_IDS=(); EC2_NAMES=(); EC2_PUB_IPS=(); EC2_STATES=()

while IFS=$'\t' read -r id name pub priv state; do
  [[ -z "$id" ]] && continue
  EC2_IDS+=("$id")
  EC2_NAMES+=("${name:-(no name)}")
  EC2_PUB_IPS+=("${pub:-${priv:---}}")
  EC2_STATES+=("$state")
done < <(aws ec2 describe-instances \
  --region "$AWS_REGION" \
  --query 'Reservations[*].Instances[*].[InstanceId,Tags[?Key==`Name`].Value|[0],PublicIpAddress,PrivateIpAddress,State.Name]' \
  --output text 2>/dev/null | grep -v "terminated" || true)

if [[ ${#EC2_IDS[@]} -eq 0 ]]; then
  warn "No EC2 instances found."
  ask "Enter EC2 IP or hostname manually:"
  read -r EC2_HOST
  [[ -z "$EC2_HOST" ]] && err "Cannot be empty"
else
  printf "  %-4s %-22s %-22s %-16s %s\n" "No." "Instance ID" "Name" "IP" "State"
  printf "  %-4s %-22s %-22s %-16s %s\n" "---" "-----------" "----" "--" "-----"
  for i in "${!EC2_IDS[@]}"; do
    printf "  [%s]  %-20s %-22s %-16s %s\n" \
      "$((i+1))" "${EC2_IDS[$i]}" "${EC2_NAMES[$i]}" \
      "${EC2_PUB_IPS[$i]}" "${EC2_STATES[$i]}"
  done
  echo ""
  ask "Which EC2 to shut down? [1]:"
  read -r PICK; PICK="${PICK:-1}"
  IDX=$(( PICK - 1 ))
  INSTANCE_ID="${EC2_IDS[$IDX]}"
  EC2_HOST="${EC2_PUB_IPS[$IDX]}"
  ok "Selected: $INSTANCE_ID  →  $EC2_HOST"
fi

# ── STEP 3: SSH details ───────────────────────────────────────
divider
echo -e "${BOLD}STEP 3 — SSH Connection${NC}"

ask "Path to SSH key (.pem):"
read -r EC2_KEY; EC2_KEY="${EC2_KEY/#\~/$HOME}"
[[ ! -f "$EC2_KEY" ]] && err "Key not found: $EC2_KEY"
chmod 400 "$EC2_KEY" 2>/dev/null || true

ask "SSH username [ec2-user]:"
read -r U; EC2_USER="${U:-ec2-user}"

ask "Remote project directory [/home/${EC2_USER}/marauder-scan]:"
read -r RD; REMOTE_DIR="${RD:-/home/${EC2_USER}/marauder-scan}"

info "Testing SSH..."
ssh -i "$EC2_KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=10 \
  "${EC2_USER}@${EC2_HOST}" "echo ok" &>/dev/null \
  && ok "SSH OK" \
  || err "SSH failed."

# ── STEP 4: Container status ──────────────────────────────────
divider
echo -e "${BOLD}STEP 4 — Container Status${NC}"
ssh -i "$EC2_KEY" -o StrictHostKeyChecking=no "${EC2_USER}@${EC2_HOST}" \
  "cd '${REMOTE_DIR}' && docker-compose ps 2>/dev/null || echo 'No containers found'"

# ── STEP 5: Final logs ────────────────────────────────────────
divider
echo -e "${BOLD}STEP 5 — Final Log Snapshot${NC}"
echo ""
for SVC in scanner grafana nginx; do
  echo -e "${BOLD}  ── $SVC (last 10 lines) ──${NC}"
  ssh -i "$EC2_KEY" -o StrictHostKeyChecking=no "${EC2_USER}@${EC2_HOST}" \
    "cd '${REMOTE_DIR}' && docker-compose logs --tail=10 ${SVC} 2>/dev/null || true"
  echo ""
done

# ── STEP 6: Stop containers ───────────────────────────────────
divider
echo -e "${BOLD}STEP 6 — Stop Containers${NC}"
ask "Stop all containers on EC2? (y/N):"
read -r STOP_R
if [[ "$STOP_R" =~ ^[yY]$ ]]; then
  info "Running docker-compose down (30s timeout per container)..."
  ssh -i "$EC2_KEY" -o StrictHostKeyChecking=no "${EC2_USER}@${EC2_HOST}" \
    "cd '${REMOTE_DIR}' && docker-compose down --timeout 30"
  ok "All containers stopped"
else
  warn "Container shutdown skipped."
fi

# ── STEP 7: Stop EC2 instance ─────────────────────────────────
divider
echo -e "${BOLD}STEP 7 — EC2 Instance${NC}"
echo ""
echo "  [1]  Stop EC2 instance $INSTANCE_ID (saves cost — data preserved)"
echo "  [2]  Terminate EC2 instance (PERMANENT — destroys everything)"
echo "  [3]  Leave EC2 running"
echo ""
ask "Choice [3]:"
read -r EC2_ACTION; EC2_ACTION="${EC2_ACTION:-3}"

case "$EC2_ACTION" in
  1)
    ask "Confirm stop instance $INSTANCE_ID? (y/N):"
    read -r CONF
    if [[ "$CONF" =~ ^[yY]$ ]]; then
      aws ec2 stop-instances --instance-ids "$INSTANCE_ID" --region "$AWS_REGION" >/dev/null
      ok "EC2 stop initiated — instance will be stopped in ~30s"
      warn "To restart: aws ec2 start-instances --instance-ids $INSTANCE_ID --region $AWS_REGION"
    fi
    ;;
  2)
    warn "TERMINATE will permanently destroy the instance and all local data."
    ask "Type 'terminate' to confirm:"
    read -r TERM_CONFIRM
    if [[ "$TERM_CONFIRM" == "terminate" ]]; then
      aws ec2 terminate-instances --instance-ids "$INSTANCE_ID" --region "$AWS_REGION" >/dev/null
      ok "Termination initiated — instance will be gone in ~1 min"
    else
      warn "Termination cancelled."
    fi
    ;;
  *)
    ok "EC2 left running at $EC2_HOST"
    ;;
esac

# ══════════════════════════════════════════════════════════════
# DONE
# ══════════════════════════════════════════════════════════════
echo ""
echo -e "${BOLD}${GREEN}"
echo "=================================================="
echo "  Shutdown complete"
echo "=================================================="
echo -e "${NC}"
echo "  EC2     : ${EC2_HOST}"
[[ "$EC2_ACTION" == "1" ]] && echo "  Status  : stopping"
[[ "$EC2_ACTION" == "2" ]] && echo "  Status  : terminated"
[[ "$EC2_ACTION" == "3" ]] && echo "  Status  : still running"
echo ""
echo "To restart containers:"
echo "  ssh -i $EC2_KEY ${EC2_USER}@${EC2_HOST}"
echo "  cd ${REMOTE_DIR} && docker-compose up -d"
echo ""
echo -e "${BOLD}Giggso Inc x TrinityOps.ai x AIRTaaS${NC}"
