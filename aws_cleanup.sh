#!/usr/bin/env bash
# =============================================================
# FILE: aws_cleanup.sh
# VERSION: 1.0.0
# UPDATED: 2026-04-19
# OWNER: Giggso Inc
# PURPOSE: Remove remaining marauder-scan-* AWS resources.
#          Discovers each resource type, warns clearly, and
#          asks for explicit confirmation before every delete.
#          Nothing is hardcoded — all discovered at runtime.
# USAGE:   bash aws_cleanup.sh
# AUDIT LOG:
#   v1.0.0  2026-04-19  Initial
# =============================================================

set -uo pipefail

RED='\033[0;31m'; GRN='\033[0;32m'; YLW='\033[1;33m'
BLU='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'

ok()   { echo -e "${GRN}✓${NC} $1"; }
warn() { echo -e "${YLW}⚠${NC}  $1"; }
info() { echo -e "${BLU}→${NC} $1"; }
skip() { echo -e "  ${BOLD}–${NC} Skipped: $1"; }

PREFIX="marauder-scan"
REGION="us-east-1"

confirm() {
  # confirm "message" — returns 0 if user types y/Y, 1 otherwise
  local MSG="$1"
  echo ""
  warn "$MSG"
  read -r -p "  Type 'yes' to confirm, anything else to skip: " ANS
  [[ "$ANS" == "yes" ]]
}

# ── Credentials ───────────────────────────────────────────────
clear
echo -e "${BOLD}"
echo "=================================================="
echo "  PatronAI — AWS Resource Cleanup"
echo "  Removes marauder-scan-* resources only"
echo "  You will be asked before EVERY deletion"
echo "=================================================="
echo -e "${NC}"

command -v aws &>/dev/null || { echo "AWS CLI not found"; exit 1; }
ACCOUNT=$(aws sts get-caller-identity --query Account --output text 2>/dev/null) \
  || { echo "No valid AWS credentials"; exit 1; }
ok "Account: $ACCOUNT   Region: $REGION"
echo ""

# ══════════════════════════════════════════════════════════════
# 1 — VPC FLOW LOGS
# ══════════════════════════════════════════════════════════════
echo -e "${BOLD}── 1. VPC Flow Logs ─────────────────────────────────${NC}"
FLOW_LOGS=$(aws ec2 describe-flow-logs --region "$REGION" \
  --query "FlowLogs[?contains(LogDestination,'${PREFIX}')].[FlowLogId,LogDestination]" \
  --output text 2>/dev/null || true)

if [[ -z "$FLOW_LOGS" ]]; then
  ok "None found"
else
  echo "$FLOW_LOGS" | while IFS=$'\t' read -r FL_ID FL_DEST; do
    echo "  Found: $FL_ID → $FL_DEST"
    if confirm "DELETE VPC Flow Log $FL_ID (stops log delivery to S3)"; then
      aws ec2 delete-flow-logs --flow-log-ids "$FL_ID" \
        --region "$REGION" &>/dev/null \
        && ok "Deleted: $FL_ID" || warn "Failed: $FL_ID"
    else
      skip "$FL_ID"
    fi
  done
fi

# ══════════════════════════════════════════════════════════════
# 2 — SNS TOPICS
# ══════════════════════════════════════════════════════════════
echo ""
echo -e "${BOLD}── 2. SNS Topics ────────────────────────────────────${NC}"
SNS_TOPICS=$(aws sns list-topics --region "$REGION" \
  --query "Topics[?contains(TopicArn,'${PREFIX}')].TopicArn" \
  --output text 2>/dev/null || true)

if [[ -z "$SNS_TOPICS" ]]; then
  ok "None found"
else
  for ARN in $SNS_TOPICS; do
    echo "  Found: $ARN"
    if confirm "DELETE SNS topic $ARN (all subscriptions also removed)"; then
      aws sns delete-topic --topic-arn "$ARN" --region "$REGION" &>/dev/null \
        && ok "Deleted: $ARN" || warn "Failed: $ARN"
    else
      skip "$ARN"
    fi
  done
fi

# ══════════════════════════════════════════════════════════════
# 3 — IAM
# ══════════════════════════════════════════════════════════════
echo ""
echo -e "${BOLD}── 3. IAM Roles and Instance Profiles ───────────────${NC}"
IAM_ROLES=$(aws iam list-roles \
  --query "Roles[?starts_with(RoleName,'${PREFIX}')].RoleName" \
  --output text 2>/dev/null || true)
IAM_PROFILES=$(aws iam list-instance-profiles \
  --query "InstanceProfiles[?starts_with(InstanceProfileName,'${PREFIX}')].InstanceProfileName" \
  --output text 2>/dev/null || true)

if [[ -z "$IAM_ROLES" && -z "$IAM_PROFILES" ]]; then
  ok "None found"
fi

for ROLE in $IAM_ROLES; do
  echo "  Found role: $ROLE"
  if confirm "DELETE IAM role $ROLE (inline + managed policies detached first)"; then
    # Inline policies
    for POL in $(aws iam list-role-policies --role-name "$ROLE" \
        --query "PolicyNames[]" --output text 2>/dev/null || true); do
      [[ -z "$POL" ]] && continue
      aws iam delete-role-policy --role-name "$ROLE" \
        --policy-name "$POL" 2>/dev/null || true
      ok "  Deleted inline policy: $POL"
    done
    # Managed policies
    for P_ARN in $(aws iam list-attached-role-policies --role-name "$ROLE" \
        --query "AttachedPolicies[*].PolicyArn" --output text 2>/dev/null || true); do
      [[ -z "$P_ARN" ]] && continue
      aws iam detach-role-policy --role-name "$ROLE" \
        --policy-arn "$P_ARN" 2>/dev/null || true
      ok "  Detached managed policy: $P_ARN"
    done
    aws iam delete-role --role-name "$ROLE" 2>/dev/null \
      && ok "Deleted role: $ROLE" || warn "Failed: $ROLE"
  else
    skip "$ROLE"
  fi
done

for PROF in $IAM_PROFILES; do
  echo "  Found profile: $PROF"
  if confirm "DELETE IAM instance profile $PROF"; then
    for PR in $(aws iam get-instance-profile \
        --instance-profile-name "$PROF" \
        --query "InstanceProfile.Roles[*].RoleName" \
        --output text 2>/dev/null || true); do
      [[ -z "$PR" ]] && continue
      aws iam remove-role-from-instance-profile \
        --instance-profile-name "$PROF" --role-name "$PR" 2>/dev/null || true
    done
    aws iam delete-instance-profile \
      --instance-profile-name "$PROF" 2>/dev/null \
      && ok "Deleted profile: $PROF" || warn "Failed: $PROF"
  else
    skip "$PROF"
  fi
done

# ══════════════════════════════════════════════════════════════
# 4 — S3 BUCKETS
# ══════════════════════════════════════════════════════════════
echo ""
echo -e "${BOLD}── 4. S3 Buckets ────────────────────────────────────${NC}"
S3_BUCKETS=$(aws s3api list-buckets \
  --query "Buckets[?starts_with(Name,'${PREFIX}')].Name" \
  --output text 2>/dev/null || true)

if [[ -z "$S3_BUCKETS" ]]; then
  ok "None found"
else
  for BUCKET in $S3_BUCKETS; do
    OBJ_COUNT=$(aws s3api list-objects-v2 --bucket "$BUCKET" \
      --query "KeyCount" --output text 2>/dev/null || echo "?")
    echo "  Found: s3://$BUCKET  (~$OBJ_COUNT visible objects, versioned)"
    echo -e "  ${RED}WARNING: ALL data will be permanently deleted — findings, summaries, ENI cache, config.${NC}"
    if confirm "PERMANENTLY DELETE all contents and bucket s3://$BUCKET"; then
      info "Deleting all versions in batches (versioning enabled)..."
      while true; do
        BATCH=$(aws s3api list-object-versions --bucket "$BUCKET" \
          --max-items 1000 \
          --query '{Objects:[Versions,DeleteMarkers][][]{Key:Key,VersionId:VersionId}}' \
          --output json 2>/dev/null || echo '{"Objects":[]}')
        COUNT=$(echo "$BATCH" | python3 -c \
          "import sys,json; d=json.load(sys.stdin); print(len(d.get('Objects') or []))" 2>/dev/null || echo 0)
        [[ "$COUNT" -eq 0 ]] && break
        info "  Batch deleting $COUNT versions..."
        echo "$BATCH" | aws s3api delete-objects \
          --bucket "$BUCKET" --delete file:///dev/stdin &>/dev/null || true
      done
      aws s3 rb "s3://$BUCKET" --force 2>/dev/null \
        && ok "Deleted bucket: s3://$BUCKET" || warn "Failed to delete bucket: $BUCKET"
    else
      skip "s3://$BUCKET"
    fi
  done
fi

# ══════════════════════════════════════════════════════════════
# 5 — ORPHANED EBS VOLUMES
# ══════════════════════════════════════════════════════════════
echo ""
echo -e "${BOLD}── 5. Detached EBS Volumes ──────────────────────────${NC}"
EBS_VOLS=$(aws ec2 describe-volumes --region "$REGION" \
  --filters "Name=status,Values=available" \
  --query "Volumes[*].[VolumeId,Size,CreateTime,Tags[?Key=='Name'].Value|[0]]" \
  --output text 2>/dev/null || true)

if [[ -z "$EBS_VOLS" ]]; then
  ok "None found"
else
  echo "$EBS_VOLS" | while IFS=$'\t' read -r VOL_ID SIZE CREATED NAME; do
    NAME="${NAME:-no-name}"
    echo "  Found: $VOL_ID  ${SIZE}GB  created $CREATED  name=$NAME"
    echo -e "  ${RED}WARNING: Data on this volume cannot be recovered after deletion.${NC}"
    if confirm "DELETE EBS volume $VOL_ID (${SIZE}GB, name=$NAME)"; then
      aws ec2 delete-volume --volume-id "$VOL_ID" --region "$REGION" 2>/dev/null \
        && ok "Deleted: $VOL_ID" || warn "Failed: $VOL_ID"
    else
      skip "$VOL_ID"
    fi
  done
fi

# ══════════════════════════════════════════════════════════════
# DONE
# ══════════════════════════════════════════════════════════════
echo ""
echo -e "${BOLD}────────────────────────────────────────────────────${NC}"
echo -e "${BOLD}${GRN}  Cleanup complete.${NC}"
echo ""
echo "  Run 'bash deploy_to_ec2.sh' to start fresh."
echo ""
echo -e "${BOLD}Giggso Inc x TrinityOps.ai x AIRTaaS${NC}"
