#!/usr/bin/env bash
# =============================================================
# FILE: teardown.sh
# VERSION: 1.0.0
# UPDATED: 2026-04-19
# OWNER: Giggso Inc
# PURPOSE: Full teardown of all AWS + EC2 resources created by
#          PatronAI / Marauder Scan. Discovers resources
#          dynamically by marauder-scan-* naming — nothing
#          hardcoded. Deletes in dependency order, validates
#          each removal, writes timestamped report.
# USAGE:   bash teardown.sh
# AUDIT LOG:
#   v1.0.0  2026-04-19  Initial
# =============================================================

set -euo pipefail
IFS=$'\n\t'

RED='\033[0;31m'; GRN='\033[0;32m'; YLW='\033[1;33m'
BLU='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'

ok()   { echo -e "${GRN}✓${NC} $1"; }
err()  { echo -e "${RED}✗${NC} $1" >&2; }
warn() { echo -e "${YLW}!${NC} $1"; }
info() { echo -e "${BLU}→${NC} $1"; }
div()  { echo -e "\n${BOLD}──────────────────────────────────────────────${NC}"; }

PREFIX="marauder-scan"
REGION="us-east-1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Works from marauder-scan-complete/ (Mac) or ~/marauder-scan/ (EC2)
if [[ -d "$SCRIPT_DIR/ghost-ai-scanner" ]]; then
  REPORT_DIR="$SCRIPT_DIR/ghost-ai-scanner/reports"
else
  REPORT_DIR="$SCRIPT_DIR/reports"
fi
mkdir -p "$REPORT_DIR"
REPORT="$REPORT_DIR/teardown-$(date -u +%Y-%m-%d-%H%M%S).txt"
declare -a REPORT_ROWS=()

ts()       { date -u +"%Y-%m-%dT%H:%M:%SZ"; }
log_row()  { REPORT_ROWS+=("$(ts)|$1|$2|$3"); }   # type|name|status

# ══════════════════════════════════════════════════════════════
# BANNER
# ══════════════════════════════════════════════════════════════
clear
echo -e "${BOLD}${RED}"
echo "=================================================="
echo "  PatronAI — FULL TEARDOWN"
echo "  Removes ALL marauder-scan-* AWS resources"
echo "  THIS CANNOT BE UNDONE"
echo "=================================================="
echo -e "${NC}"

# ══════════════════════════════════════════════════════════════
# STEP 1 — AWS CREDENTIALS
# ══════════════════════════════════════════════════════════════
div
echo -e "${BOLD}STEP 1 — AWS Credentials${NC}"
command -v aws &>/dev/null || { err "AWS CLI not found"; exit 1; }

if ! AWS_ACCOUNT=$(aws sts get-caller-identity \
    --query Account --output text 2>/dev/null); then
  err "No valid AWS credentials found. Configure ~/.aws/credentials or set env vars."
  exit 1
fi
ok "Account: $AWS_ACCOUNT   Region: $REGION"

# ══════════════════════════════════════════════════════════════
# STEP 2 — DISCOVER ALL MARAUDER-SCAN RESOURCES
# ══════════════════════════════════════════════════════════════
div
echo -e "${BOLD}STEP 2 — Discovering marauder-scan-* resources${NC}"
echo ""

# S3 buckets
S3_BUCKETS=$(aws s3api list-buckets \
  --query "Buckets[?starts_with(Name,'${PREFIX}')].Name" \
  --output text 2>/dev/null || true)

# SNS topics
SNS_TOPICS=$(aws sns list-topics --region "$REGION" \
  --query "Topics[?contains(TopicArn,'${PREFIX}')].TopicArn" \
  --output text 2>/dev/null || true)

# VPC Flow Logs targeting marauder-scan S3
FLOW_LOG_IDS=$(aws ec2 describe-flow-logs --region "$REGION" \
  --query "FlowLogs[?contains(LogDestination,'${PREFIX}')].FlowLogId" \
  --output text 2>/dev/null || true)

# IAM roles
IAM_ROLES=$(aws iam list-roles \
  --query "Roles[?starts_with(RoleName,'${PREFIX}')].RoleName" \
  --output text 2>/dev/null || true)

# IAM instance profiles
IAM_PROFILES=$(aws iam list-instance-profiles \
  --query "InstanceProfiles[?starts_with(InstanceProfileName,'${PREFIX}')].InstanceProfileName" \
  --output text 2>/dev/null || true)

# EC2 instances with marauder-scan instance profile (running/stopped only)
EC2_INSTANCES=$(aws ec2 describe-instances --region "$REGION" \
  --filters "Name=iam-instance-profile.arn,Values=*${PREFIX}*" \
            "Name=instance-state-name,Values=running,stopped,stopping,pending" \
  --query "Reservations[*].Instances[*].InstanceId" \
  --output text 2>/dev/null || true)

# EC2 SSH details for docker-compose down (public IP of found instances)
EC2_IPS=$(aws ec2 describe-instances --region "$REGION" \
  --filters "Name=iam-instance-profile.arn,Values=*${PREFIX}*" \
            "Name=instance-state-name,Values=running,stopped,stopping,pending" \
  --query "Reservations[*].Instances[*].PublicIpAddress" \
  --output text 2>/dev/null || true)

# ── Print discovery summary ───────────────────────────────────
echo "  Resources found:"
echo ""
printf "  %-20s %s\n" "S3 buckets:"       "${S3_BUCKETS:-none}"
printf "  %-20s %s\n" "SNS topics:"       "${SNS_TOPICS:-none}"
printf "  %-20s %s\n" "VPC flow logs:"    "${FLOW_LOG_IDS:-none}"
printf "  %-20s %s\n" "IAM roles:"        "${IAM_ROLES:-none}"
printf "  %-20s %s\n" "IAM profiles:"     "${IAM_PROFILES:-none}"
printf "  %-20s %s\n" "EC2 instances:"    "${EC2_INSTANCES:-none}"

# ── SSH key for EC2 ──────────────────────────────────────────
EC2_KEY=""; EC2_USER="ec2-user"; REMOTE_DIR="/home/ec2-user/marauder-scan"
if [[ -n "$EC2_INSTANCES" ]]; then
  echo ""
  echo -e "${BOLD}  EC2 found — SSH key needed to stop containers before termination.${NC}"
  read -r -p "  Path to SSH key (.pem) [press Enter to skip container shutdown]: " EC2_KEY
  EC2_KEY="${EC2_KEY/#\~/$HOME}"
  if [[ -n "$EC2_KEY" && ! -f "$EC2_KEY" ]]; then
    warn "Key not found: $EC2_KEY — will skip container shutdown"
    EC2_KEY=""
  fi
fi

# ══════════════════════════════════════════════════════════════
# STEP 3 — HARD CONFIRMATION GATE
# ══════════════════════════════════════════════════════════════
div
echo -e "${BOLD}${RED}STEP 3 — Confirmation${NC}"
echo ""
warn "This will permanently delete ALL resources listed above."
warn "S3 data, findings, summaries, ENI cache — ALL gone."
warn "EC2 instance will be TERMINATED (not stopped)."
echo ""
echo -e "  Type exactly:  ${BOLD}TEARDOWN ${S3_BUCKETS:-marauder-scan}${NC}"
echo ""
read -r -p "  > " CONFIRM

EXPECTED="TEARDOWN ${S3_BUCKETS:-marauder-scan}"
if [[ "$CONFIRM" != "$EXPECTED" ]]; then
  warn "Input did not match. Teardown cancelled — nothing was changed."
  exit 0
fi
echo ""
ok "Confirmed. Starting teardown at $(ts)"

# ══════════════════════════════════════════════════════════════
# STEP 4 — DELETE IN DEPENDENCY ORDER
# ══════════════════════════════════════════════════════════════

# ── 4a: VPC Flow Logs ────────────────────────────────────────
div
echo -e "${BOLD}4a — VPC Flow Logs${NC}"
if [[ -n "$FLOW_LOG_IDS" ]]; then
  for FL_ID in $FLOW_LOG_IDS; do
    info "Deleting flow log: $FL_ID"
    if aws ec2 delete-flow-logs --flow-log-ids "$FL_ID" \
        --region "$REGION" &>/dev/null; then
      ok "Deleted: $FL_ID"
      log_row "VPC_FLOW_LOG" "$FL_ID" "REMOVED"
    else
      err "Failed: $FL_ID"
      log_row "VPC_FLOW_LOG" "$FL_ID" "FAILED"
    fi
  done
else
  info "No VPC flow logs found"
fi

# ── 4b: EC2 containers (graceful docker-compose down) ────────
div
echo -e "${BOLD}4b — EC2 Docker Containers${NC}"
if [[ -n "$EC2_INSTANCES" && -n "$EC2_KEY" && -n "$EC2_IPS" ]]; then
  for IP in $EC2_IPS; do
    [[ "$IP" == "None" || -z "$IP" ]] && continue
    info "Stopping containers on $IP..."
    if ssh -i "$EC2_KEY" -o StrictHostKeyChecking=no \
        -o ConnectTimeout=15 "${EC2_USER}@${IP}" \
        "cd '$REMOTE_DIR' && docker-compose down --timeout 30 2>&1" \
        2>/dev/null; then
      ok "Containers stopped on $IP"
      log_row "DOCKER_CONTAINERS" "$IP" "REMOVED"
    else
      warn "Could not stop containers on $IP — continuing to EC2 termination"
      log_row "DOCKER_CONTAINERS" "$IP" "SKIPPED"
    fi
  done
else
  info "Skipping container shutdown (no EC2 found or no SSH key provided)"
fi

# ── 4c: EC2 instances ────────────────────────────────────────
div
echo -e "${BOLD}4c — EC2 Instances${NC}"
if [[ -n "$EC2_INSTANCES" ]]; then
  for INST in $EC2_INSTANCES; do
    info "Terminating: $INST"
    # Disassociate instance profile first
    ASSOC_ID=$(aws ec2 describe-iam-instance-profile-associations \
      --filters "Name=instance-id,Values=$INST" \
      --query "IamInstanceProfileAssociations[0].AssociationId" \
      --output text --region "$REGION" 2>/dev/null || true)
    if [[ -n "$ASSOC_ID" && "$ASSOC_ID" != "None" ]]; then
      aws ec2 disassociate-iam-instance-profile \
        --association-id "$ASSOC_ID" --region "$REGION" &>/dev/null || true
      ok "IAM profile disassociated from $INST"
    fi
    if aws ec2 terminate-instances --instance-ids "$INST" \
        --region "$REGION" &>/dev/null; then
      info "Waiting for $INST to terminate..."
      aws ec2 wait instance-terminated \
        --instance-ids "$INST" --region "$REGION" 2>/dev/null || true
      ok "Terminated: $INST"
      log_row "EC2_INSTANCE" "$INST" "REMOVED"
    else
      err "Termination failed: $INST"
      log_row "EC2_INSTANCE" "$INST" "FAILED"
    fi
  done
else
  info "No EC2 instances found"
fi

# ── 4d: SNS topics ───────────────────────────────────────────
div
echo -e "${BOLD}4d — SNS Topics${NC}"
if [[ -n "$SNS_TOPICS" ]]; then
  for ARN in $SNS_TOPICS; do
    info "Deleting SNS topic: $ARN"
    if aws sns delete-topic --topic-arn "$ARN" \
        --region "$REGION" &>/dev/null; then
      ok "Deleted: $ARN"
      log_row "SNS_TOPIC" "$ARN" "REMOVED"
    else
      err "Failed: $ARN"
      log_row "SNS_TOPIC" "$ARN" "FAILED"
    fi
  done
else
  info "No SNS topics found"
fi

# ── 4e: IAM — inline policies → role → instance profile ──────
div
echo -e "${BOLD}4e — IAM Roles and Profiles${NC}"
if [[ -n "$IAM_ROLES" ]]; then
  for ROLE in $IAM_ROLES; do
    info "Cleaning role: $ROLE"

    # Detach managed policies
    MANAGED=$(aws iam list-attached-role-policies --role-name "$ROLE" \
      --query "AttachedPolicies[*].PolicyArn" --output text 2>/dev/null || true)
    for P_ARN in $MANAGED; do
      [[ -z "$P_ARN" ]] && continue
      aws iam detach-role-policy --role-name "$ROLE" \
        --policy-arn "$P_ARN" 2>/dev/null || true
      ok "Detached managed policy: $P_ARN"
    done

    # Delete inline policies
    INLINE=$(aws iam list-role-policies --role-name "$ROLE" \
      --query "PolicyNames[]" --output text 2>/dev/null || true)
    for POL in $INLINE; do
      [[ -z "$POL" ]] && continue
      aws iam delete-role-policy --role-name "$ROLE" \
        --policy-name "$POL" 2>/dev/null || true
      ok "Deleted inline policy: $POL"
      log_row "IAM_INLINE_POLICY" "${ROLE}/${POL}" "REMOVED"
    done

    # Delete role
    if aws iam delete-role --role-name "$ROLE" 2>/dev/null; then
      ok "Deleted role: $ROLE"
      log_row "IAM_ROLE" "$ROLE" "REMOVED"
    else
      err "Failed to delete role: $ROLE"
      log_row "IAM_ROLE" "$ROLE" "FAILED"
    fi
  done
fi

if [[ -n "$IAM_PROFILES" ]]; then
  for PROF in $IAM_PROFILES; do
    # Remove any remaining role associations
    PROF_ROLES=$(aws iam get-instance-profile \
      --instance-profile-name "$PROF" \
      --query "InstanceProfile.Roles[*].RoleName" \
      --output text 2>/dev/null || true)
    for PR in $PROF_ROLES; do
      [[ -z "$PR" ]] && continue
      aws iam remove-role-from-instance-profile \
        --instance-profile-name "$PROF" --role-name "$PR" 2>/dev/null || true
    done
    if aws iam delete-instance-profile \
        --instance-profile-name "$PROF" 2>/dev/null; then
      ok "Deleted instance profile: $PROF"
      log_row "IAM_INSTANCE_PROFILE" "$PROF" "REMOVED"
    else
      err "Failed to delete profile: $PROF"
      log_row "IAM_INSTANCE_PROFILE" "$PROF" "FAILED"
    fi
  done
fi

# ── 4f: S3 — purge all versions then delete bucket ───────────
div
echo -e "${BOLD}4f — S3 Buckets${NC}"
if [[ -n "$S3_BUCKETS" ]]; then
  for BUCKET in $S3_BUCKETS; do
    info "Emptying versioned bucket: $BUCKET (batch delete)"

    # Batch-delete all versions and delete markers in chunks of 1000
    while true; do
      VERSIONS_JSON=$(aws s3api list-object-versions --bucket "$BUCKET" \
        --max-items 1000 \
        --query '{Objects: [Versions,DeleteMarkers][][]{Key:Key,VersionId:VersionId}}' \
        --output json 2>/dev/null || echo '{"Objects":[]}')
      COUNT=$(echo "$VERSIONS_JSON" | python3 -c \
        "import sys,json; d=json.load(sys.stdin); print(len(d.get('Objects') or []))" 2>/dev/null || echo 0)
      [[ "$COUNT" -eq 0 ]] && break
      info "  Deleting batch of $COUNT versions..."
      echo "$VERSIONS_JSON" | aws s3api delete-objects \
        --bucket "$BUCKET" --delete file:///dev/stdin &>/dev/null || true
    done

    if aws s3 rb "s3://$BUCKET" --force 2>/dev/null; then
      ok "Deleted bucket: s3://$BUCKET"
      log_row "S3_BUCKET" "$BUCKET" "REMOVED"
    else
      err "Failed to delete bucket: $BUCKET"
      log_row "S3_BUCKET" "$BUCKET" "FAILED"
    fi
  done
else
  info "No S3 buckets found"
fi

# ══════════════════════════════════════════════════════════════
# STEP 5 — VALIDATION SCAN
# ══════════════════════════════════════════════════════════════
div
echo -e "${BOLD}STEP 5 — Validation Scan${NC}"
echo ""
declare -a VAL_ROWS=()
val_row() { VAL_ROWS+=("$(ts)|$1|$2|$3"); }

# S3
for BUCKET in $S3_BUCKETS; do
  if aws s3api head-bucket --bucket "$BUCKET" &>/dev/null 2>&1; then
    err "STILL EXISTS: s3://$BUCKET"
    val_row "S3_BUCKET" "$BUCKET" "STILL_EXISTS"
  else
    ok "Confirmed gone: s3://$BUCKET"
    val_row "S3_BUCKET" "$BUCKET" "CONFIRMED_REMOVED"
  fi
done

# SNS
for ARN in $SNS_TOPICS; do
  if aws sns get-topic-attributes --topic-arn "$ARN" \
      --region "$REGION" &>/dev/null 2>&1; then
    err "STILL EXISTS: $ARN"
    val_row "SNS_TOPIC" "$ARN" "STILL_EXISTS"
  else
    ok "Confirmed gone: $ARN"
    val_row "SNS_TOPIC" "$ARN" "CONFIRMED_REMOVED"
  fi
done

# VPC Flow Logs
for FL_ID in $FLOW_LOG_IDS; do
  REMAINING=$(aws ec2 describe-flow-logs --flow-log-ids "$FL_ID" \
    --region "$REGION" \
    --query "FlowLogs[0].FlowLogId" \
    --output text 2>/dev/null || true)
  if [[ -n "$REMAINING" && "$REMAINING" != "None" ]]; then
    err "STILL EXISTS: $FL_ID"
    val_row "VPC_FLOW_LOG" "$FL_ID" "STILL_EXISTS"
  else
    ok "Confirmed gone: $FL_ID"
    val_row "VPC_FLOW_LOG" "$FL_ID" "CONFIRMED_REMOVED"
  fi
done

# IAM roles
for ROLE in $IAM_ROLES; do
  if aws iam get-role --role-name "$ROLE" &>/dev/null 2>&1; then
    err "STILL EXISTS: $ROLE"
    val_row "IAM_ROLE" "$ROLE" "STILL_EXISTS"
  else
    ok "Confirmed gone: $ROLE"
    val_row "IAM_ROLE" "$ROLE" "CONFIRMED_REMOVED"
  fi
done

# IAM profiles
for PROF in $IAM_PROFILES; do
  if aws iam get-instance-profile \
      --instance-profile-name "$PROF" &>/dev/null 2>&1; then
    err "STILL EXISTS: $PROF"
    val_row "IAM_INSTANCE_PROFILE" "$PROF" "STILL_EXISTS"
  else
    ok "Confirmed gone: $PROF"
    val_row "IAM_INSTANCE_PROFILE" "$PROF" "CONFIRMED_REMOVED"
  fi
done

# EC2
for INST in $EC2_INSTANCES; do
  STATE=$(aws ec2 describe-instances --instance-ids "$INST" \
    --query "Reservations[0].Instances[0].State.Name" \
    --output text --region "$REGION" 2>/dev/null || true)
  if [[ "$STATE" == "terminated" || -z "$STATE" ]]; then
    ok "Confirmed terminated: $INST"
    val_row "EC2_INSTANCE" "$INST" "CONFIRMED_REMOVED"
  else
    err "NOT terminated ($STATE): $INST"
    val_row "EC2_INSTANCE" "$INST" "STILL_EXISTS ($STATE)"
  fi
done

# ══════════════════════════════════════════════════════════════
# STEP 6 — WRITE REPORT
# ══════════════════════════════════════════════════════════════
div
echo -e "${BOLD}STEP 6 — Writing Report${NC}"

{
  echo "PatronAI / Marauder Scan — Teardown Report"
  echo "Generated : $(ts)"
  echo "Account   : $AWS_ACCOUNT"
  echo "Region    : $REGION"
  echo ""
  echo "── ACTIONS TAKEN ──────────────────────────────────────"
  printf "%-26s %-36s %-20s %s\n" "Timestamp" "Type" "Resource" "Status"
  printf "%-26s %-36s %-20s %s\n" "---------" "----" "--------" "------"
  for ROW in "${REPORT_ROWS[@]}"; do
    IFS='|' read -r TS TYPE NAME STATUS <<< "$ROW"
    printf "%-26s %-36s %-20s %s\n" "$TS" "$TYPE" "$NAME" "$STATUS"
  done
  echo ""
  echo "── VALIDATION SCAN ─────────────────────────────────────"
  printf "%-26s %-36s %-20s %s\n" "Timestamp" "Type" "Resource" "Result"
  printf "%-26s %-36s %-20s %s\n" "---------" "----" "--------" "------"
  for ROW in "${VAL_ROWS[@]}"; do
    IFS='|' read -r TS TYPE NAME STATUS <<< "$ROW"
    printf "%-26s %-36s %-20s %s\n" "$TS" "$TYPE" "$NAME" "$STATUS"
  done
  echo ""
  echo "── END OF REPORT ───────────────────────────────────────"
} > "$REPORT"

ok "Report written: $REPORT"

# ══════════════════════════════════════════════════════════════
# DONE
# ══════════════════════════════════════════════════════════════
div
echo -e "${BOLD}${GRN}"
echo "=================================================="
echo "  Teardown complete"
echo "  Giggso Inc x TrinityOps.ai x AIRTaaS"
echo "=================================================="
echo -e "${NC}"
echo "  Report: $REPORT"
echo ""
STILL=$(printf '%s\n' "${VAL_ROWS[@]}" | grep "STILL_EXISTS" | wc -l | tr -d ' ')
if [[ "$STILL" -gt 0 ]]; then
  warn "$STILL resource(s) could not be confirmed removed — check report"
else
  ok "All resources confirmed removed"
fi
echo ""
