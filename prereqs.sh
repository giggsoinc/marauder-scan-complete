#!/usr/bin/env bash
# =============================================================
# FILE: prereqs.sh
# VERSION: 1.0.0
# UPDATED: 2026-04-19
# OWNER: Giggso Inc
# PURPOSE: Create all AWS resources needed by PatronAI.
#          At every step lists existing resources — user chooses
#          to reuse or create new. Generates .env, packetbeat.yml,
#          agent/config.json, grafana datasource. Optionally SCPs
#          all generated files to the EC2.
# USAGE:   bash prereqs.sh   (run from marauder-scan-complete/)
# RUN ON:  Your Mac — not on the EC2
# BEFORE:  Run deploy_to_ec2.sh first to get code onto EC2
# AFTER:   SSH into EC2 and run docker-compose up -d
# NOTE:    Exceeds 150-line limit — single-script requirement
# =============================================================

set -euo pipefail

# ── Colours ───────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'

ok()      { echo -e "${GREEN}✓${NC} $1"; }
err()     { echo -e "${RED}✗${NC} $1" >&2; exit 1; }
warn()    { echo -e "${YELLOW}!${NC} $1"; }
info()    { echo -e "${BLUE}→${NC} $1"; }
ask()     { echo -e "\n${BOLD}$1${NC}"; }
divider() { echo -e "\n${BOLD}──────────────────────────────────────────────${NC}"; }
section() { echo -e "\n${BOLD}${BLUE}══════════════════════════════════════════════"; \
            echo -e "  $1"; \
            echo -e "══════════════════════════════════════════════${NC}"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Mac:  script lives in marauder-scan-complete/ alongside ghost-ai-scanner/
# EC2:  script lives inside the project root directly (deploy_to_ec2.sh copies contents, not folder)
if [[ -d "$SCRIPT_DIR/ghost-ai-scanner" ]]; then
  REPO_DIR="$SCRIPT_DIR/ghost-ai-scanner"
elif [[ -f "$SCRIPT_DIR/main.py" || -d "$SCRIPT_DIR/config" ]]; then
  REPO_DIR="$SCRIPT_DIR"
else
  err "Cannot find project root. Run from marauder-scan-complete/ (Mac) or marauder-scan/ (EC2)."
fi

EC2_HOST=""; EC2_KEY=""; EC2_USER=""; EC2_REMOTE_DIR=""
SNS_ARN=""; SCANNER_KEY_ID=""; SCANNER_KEY_SECRET=""

# ══════════════════════════════════════════════════════════════
# BANNER
# ══════════════════════════════════════════════════════════════
clear
echo -e "${BOLD}"
echo "=================================================="
echo "  PatronAI — AWS Prerequisites Setup"
echo "  Giggso Inc  |  v1.0.0"
echo "=================================================="
echo -e "${NC}"
echo "Run this on your Mac AFTER deploy_to_ec2.sh."
echo ""
echo "This script will:"
echo "  • Create S3 bucket, IAM user, SNS topic, VPC Flow Logs"
echo "  • Generate .env, packetbeat.yml, agent config"
echo "  • Optionally SCP all generated files to your EC2"
echo ""

# ══════════════════════════════════════════════════════════════
# STEP 1 — AWS CREDENTIALS
# ══════════════════════════════════════════════════════════════
section "STEP 1 — AWS Credentials"

command -v aws &>/dev/null || err "AWS CLI not found. Install: https://aws.amazon.com/cli/"

ask "AWS Region [us-east-1]:"
read -r AWS_REGION
AWS_REGION="${AWS_REGION:-us-east-1}"
export AWS_DEFAULT_REGION="$AWS_REGION"

# Check if credentials already work — instance profile, env vars, or ~/.aws/credentials
info "Checking for existing AWS credentials (instance profile / env / config)..."
AWS_ACCOUNT=$(aws sts get-caller-identity --query Account --output text 2>/dev/null || true)

if [[ -n "$AWS_ACCOUNT" && "$AWS_ACCOUNT" != "None" ]]; then
  ok "Credentials found automatically — Account: $AWS_ACCOUNT   Region: $AWS_REGION"
  warn "Using existing credentials (instance profile / environment). No key entry needed."
else
  warn "No automatic credentials found — please enter Access Key and Secret."
  ask "AWS Access Key ID:"
  read -r AWS_ACCESS_KEY_ID
  [[ -z "$AWS_ACCESS_KEY_ID" ]] && err "Cannot be empty"

  ask "AWS Secret Access Key:"
  read -r -s AWS_SECRET_ACCESS_KEY
  echo ""
  [[ -z "$AWS_SECRET_ACCESS_KEY" ]] && err "Cannot be empty"

  export AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY

  AWS_ACCOUNT=$(aws sts get-caller-identity --query Account --output text 2>/dev/null) \
    || err "Invalid credentials — check your Access Key ID and Secret Access Key."
  ok "Valid — Account: $AWS_ACCOUNT   Region: $AWS_REGION"
fi

# ══════════════════════════════════════════════════════════════
# STEP 2 — COMPANY CONFIGURATION
# ══════════════════════════════════════════════════════════════
section "STEP 2 — Company Configuration"

ask "Company name (display name, e.g. Acme Corp):"
read -r COMPANY_NAME
[[ -z "$COMPANY_NAME" ]] && err "Cannot be empty"

ask "Company slug (lowercase-no-spaces, e.g. acme):"
read -r COMPANY_SLUG
COMPANY_SLUG=$(echo "$COMPANY_SLUG" | tr '[:upper:]' '[:lower:]' | tr ' ' '-')
[[ -z "$COMPANY_SLUG" ]] && err "Cannot be empty"

ask "Allowed emails for Streamlit UI (comma-separated):"
read -r ALLOWED_EMAILS
[[ -z "$ALLOWED_EMAILS" ]] && err "At least one email required"

ask "Admin emails — can edit settings (comma-separated):"
read -r ADMIN_EMAILS
[[ -z "$ADMIN_EMAILS" ]] && err "At least one admin email required"

ask "Alert email for SNS subscription:"
read -r ALERT_EMAIL
ALERT_EMAIL="${ALERT_EMAIL//[$'\t\r\n']/}"   # strip newlines
ALERT_EMAIL="${ALERT_EMAIL// /}"              # strip spaces
[[ -z "$ALERT_EMAIL" ]] && err "Cannot be empty"
# Validate each comma-separated address individually
IFS=',' read -ra _EMAIL_LIST <<< "$ALERT_EMAIL"
for _EM in "${_EMAIL_LIST[@]}"; do
  [[ "$_EM" =~ ^[^@]+@[^@]+\.[^@]+$ ]] || err "Invalid email format: $_EM"
done
unset _EMAIL_LIST _EM

ask "Trinity webhook URL [optional — Enter to skip]:"
read -r TRINITY_WEBHOOK_URL
TRINITY_WEBHOOK_URL="${TRINITY_WEBHOOK_URL:-}"

ask "LogAnalyzer webhook URL [optional — Enter to skip]:"
read -r LOGANALYZER_WEBHOOK_URL
LOGANALYZER_WEBHOOK_URL="${LOGANALYZER_WEBHOOK_URL:-}"

ask "Scan interval seconds [300]:"
read -r SCAN_INTERVAL_SECS
SCAN_INTERVAL_SECS="${SCAN_INTERVAL_SECS:-300}"

ask "Dedup window minutes [60]:"
read -r DEDUP_WINDOW_MINUTES
DEDUP_WINDOW_MINUTES="${DEDUP_WINDOW_MINUTES:-60}"

ask "Grafana admin password [change-me-before-demo]:"
read -r -s GF_ADMIN_PASSWORD
GF_ADMIN_PASSWORD="${GF_ADMIN_PASSWORD:-change-me-before-demo}"
echo ""

# ══════════════════════════════════════════════════════════════
# STEP 3 — S3 BUCKET
# ══════════════════════════════════════════════════════════════
section "STEP 3 — S3 Bucket"
DEFAULT_BUCKET="marauder-scan-${COMPANY_SLUG}"

info "Listing all existing S3 buckets in this account..."
EXISTING_BUCKETS=()
while IFS= read -r line; do
  bucket=$(echo "$line" | awk '{print $3}')
  [[ -n "$bucket" ]] && EXISTING_BUCKETS+=("$bucket")
done < <(aws s3 ls 2>/dev/null || true)

S3_BUCKET=""; S3_CREATE=true
if [[ ${#EXISTING_BUCKETS[@]} -gt 0 ]]; then
  echo ""
  echo "  Existing buckets:"
  for i in "${!EXISTING_BUCKETS[@]}"; do
    echo "  [$((i+1))]  ${EXISTING_BUCKETS[$i]}"
  done
  CREATE_IDX=$(( ${#EXISTING_BUCKETS[@]} + 1 ))
  CUSTOM_IDX=$(( ${#EXISTING_BUCKETS[@]} + 2 ))
  echo "  [$CREATE_IDX]  Create: $DEFAULT_BUCKET"
  echo "  [$CUSTOM_IDX]  Create with custom name"
  ask "Choice [$CREATE_IDX]:"
  read -r C; C="${C:-$CREATE_IDX}"
  if [[ "$C" == "$CUSTOM_IDX" ]]; then
    ask "Bucket name:"; read -r S3_BUCKET; S3_CREATE=true
  elif [[ "$C" == "$CREATE_IDX" ]]; then
    S3_BUCKET="$DEFAULT_BUCKET"; S3_CREATE=true
  else
    S3_BUCKET="${EXISTING_BUCKETS[$(( C - 1 ))]}"; S3_CREATE=false
    ok "Reusing: $S3_BUCKET"
  fi
else
  warn "No existing buckets found."
  echo "  [1]  Create: $DEFAULT_BUCKET"
  echo "  [2]  Create with custom name"
  ask "Choice [1]:"
  read -r C; C="${C:-1}"
  [[ "$C" == "2" ]] && { ask "Bucket name:"; read -r S3_BUCKET; } || S3_BUCKET="$DEFAULT_BUCKET"
  S3_CREATE=true
fi

if [[ "$S3_CREATE" == true ]]; then
  info "Creating bucket: $S3_BUCKET"
  if ! aws s3api head-bucket --bucket "$S3_BUCKET" 2>/dev/null; then
    if [[ "$AWS_REGION" == "us-east-1" ]]; then
      aws s3api create-bucket --bucket "$S3_BUCKET" --region "$AWS_REGION" >/dev/null
    else
      aws s3api create-bucket --bucket "$S3_BUCKET" --region "$AWS_REGION" \
        --create-bucket-configuration LocationConstraint="$AWS_REGION" >/dev/null
    fi
  fi
  aws s3api put-bucket-versioning --bucket "$S3_BUCKET" \
    --versioning-configuration Status=Enabled >/dev/null
  aws s3api put-public-access-block --bucket "$S3_BUCKET" \
    --public-access-block-configuration \
    "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true" >/dev/null
  aws s3api put-bucket-lifecycle-configuration --bucket "$S3_BUCKET" \
    --lifecycle-configuration '{
      "Rules":[
        {"ID":"findings","Status":"Enabled","Filter":{"Prefix":"findings/"},
         "Transitions":[{"Days":30,"StorageClass":"STANDARD_IA"}],"Expiration":{"Days":365}},
        {"ID":"ocsf","Status":"Enabled","Filter":{"Prefix":"ocsf/"},
         "Transitions":[{"Days":30,"StorageClass":"STANDARD_IA"}],"Expiration":{"Days":90}},
        {"ID":"dedup","Status":"Enabled","Filter":{"Prefix":"dedup/"},"Expiration":{"Days":90}}
      ]
    }' >/dev/null
  ok "Bucket created and hardened: $S3_BUCKET"
fi

divider
echo -e "${BOLD}  Seed config files to S3${NC}"
echo "  [1]  Seed from local repo → s3://${S3_BUCKET}/config/"
echo "  [2]  Skip (already in bucket)"
ask "Choice [1]:"
read -r C; C="${C:-1}"
if [[ "$C" == "1" ]]; then
  aws s3 cp "$REPO_DIR/config/settings.json"    "s3://${S3_BUCKET}/config/settings.json"    >/dev/null
  aws s3 cp "$REPO_DIR/config/authorized.csv"   "s3://${S3_BUCKET}/config/authorized.csv"   >/dev/null
  aws s3 cp "$REPO_DIR/config/unauthorized.csv" "s3://${S3_BUCKET}/config/unauthorized.csv" >/dev/null
  ok "Config files seeded"
else
  warn "Seeding skipped"
fi

# ══════════════════════════════════════════════════════════════
# STEP 4 — IAM USER
# ══════════════════════════════════════════════════════════════
section "STEP 4 — IAM User"
IAM_USER="marauder-scan"
info "Checking IAM user '$IAM_USER'..."
IAM_EXISTS=false
aws iam get-user --user-name "$IAM_USER" &>/dev/null && IAM_EXISTS=true || true

if [[ "$IAM_EXISTS" == true ]]; then
  echo ""
  echo "  IAM user '$IAM_USER' already exists."
  echo "  [1]  Generate new access key for this user"
  echo "  [2]  Enter existing access key manually"
  echo "  [3]  Use my current credentials (not recommended for prod)"
  ask "Choice [1]:"
  read -r C; C="${C:-1}"
  if [[ "$C" == "1" ]]; then
    # Check existing key count — AWS limit is 2 per user
    KEY_COUNT=$(aws iam list-access-keys --user-name "$IAM_USER" \
      --query "length(AccessKeyMetadata)" --output text 2>/dev/null || echo 0)
    if [[ "$KEY_COUNT" -ge 2 ]]; then
      warn "User '$IAM_USER' already has $KEY_COUNT access keys (AWS limit: 2)."
      echo "  Existing keys:"
      aws iam list-access-keys --user-name "$IAM_USER" \
        --query "AccessKeyMetadata[*].[AccessKeyId,Status,CreateDate]" \
        --output table 2>/dev/null
      echo ""
      ask "Delete oldest key to make room? (y/N):"
      read -r DEL_R
      if [[ "$DEL_R" =~ ^[yY]$ ]]; then
        OLDEST_KEY=$(aws iam list-access-keys --user-name "$IAM_USER" \
          --query "AccessKeyMetadata | sort_by(@, &CreateDate)[0].AccessKeyId" \
          --output text 2>/dev/null)
        aws iam delete-access-key --user-name "$IAM_USER" \
          --access-key-id "$OLDEST_KEY" 2>/dev/null
        ok "Deleted oldest key: $OLDEST_KEY"
      else
        err "Cannot create new key — delete one manually or choose option 2"
      fi
    fi
    KEY_OUT=$(aws iam create-access-key --user-name "$IAM_USER")
    SCANNER_KEY_ID=$(echo "$KEY_OUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['AccessKey']['AccessKeyId'])")
    SCANNER_KEY_SECRET=$(echo "$KEY_OUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['AccessKey']['SecretAccessKey'])")
    ok "New access key generated"
  elif [[ "$C" == "2" ]]; then
    ask "Access Key ID for $IAM_USER:"; read -r SCANNER_KEY_ID
    ask "Secret Access Key:"; read -r -s SCANNER_KEY_SECRET; echo ""
    ok "Using manually entered credentials"
  else
    SCANNER_KEY_ID="${AWS_ACCESS_KEY_ID:-}"
    SCANNER_KEY_SECRET="${AWS_SECRET_ACCESS_KEY:-}"
    if [[ -z "$SCANNER_KEY_ID" ]]; then
      warn "No static credentials found — EC2 instance profile will handle scanner auth."
      SCANNER_KEY_ID="USE_INSTANCE_PROFILE"
      SCANNER_KEY_SECRET="USE_INSTANCE_PROFILE"
    else
      warn "Using your setup credentials — replace before production"
    fi
  fi
else
  echo ""
  echo "  [1]  Create IAM user '$IAM_USER' with scoped policy (recommended)"
  echo "  [2]  Use my current credentials"
  ask "Choice [1]:"
  read -r C; C="${C:-1}"
  if [[ "$C" == "1" ]]; then
    aws iam create-user --user-name "$IAM_USER" >/dev/null
    aws iam put-user-policy --user-name "$IAM_USER" \
      --policy-name "marauder-scan-policy" \
      --policy-document "{
        \"Version\":\"2012-10-17\",
        \"Statement\":[
          {\"Effect\":\"Allow\",\"Action\":[\"s3:GetObject\",\"s3:PutObject\",\"s3:ListBucket\",
            \"s3:DeleteObject\",\"s3:GetBucketLocation\"],
           \"Resource\":[\"arn:aws:s3:::${S3_BUCKET}\",\"arn:aws:s3:::${S3_BUCKET}/*\"]},
          {\"Effect\":\"Allow\",\"Action\":[\"sns:Publish\"],
           \"Resource\":\"arn:aws:sns:${AWS_REGION}:*:*\"},
          {\"Effect\":\"Allow\",\"Action\":[\"ec2:DescribeInstances\",\"ec2:DescribeNetworkInterfaces\"],
           \"Resource\":\"*\"},
          {\"Effect\":\"Allow\",\"Action\":[\"cloudtrail:LookupEvents\"],\"Resource\":\"*\"},
          {\"Effect\":\"Allow\",\"Action\":[\"identitystore:ListUsers\",\"identitystore:DescribeUser\"],
           \"Resource\":\"*\"}
        ]
      }" >/dev/null
    KEY_OUT=$(aws iam create-access-key --user-name "$IAM_USER")
    SCANNER_KEY_ID=$(echo "$KEY_OUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['AccessKey']['AccessKeyId'])")
    SCANNER_KEY_SECRET=$(echo "$KEY_OUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['AccessKey']['SecretAccessKey'])")
    ok "IAM user created with scoped policy and access key"
  else
    SCANNER_KEY_ID="${AWS_ACCESS_KEY_ID:-}"
    SCANNER_KEY_SECRET="${AWS_SECRET_ACCESS_KEY:-}"
    if [[ -z "$SCANNER_KEY_ID" ]]; then
      warn "No static credentials found — EC2 instance profile will handle scanner auth."
      SCANNER_KEY_ID="USE_INSTANCE_PROFILE"
      SCANNER_KEY_SECRET="USE_INSTANCE_PROFILE"
    else
      warn "Using your setup credentials — replace before production"
    fi
  fi
fi

# ══════════════════════════════════════════════════════════════
# STEP 5 — SNS TOPIC
# ══════════════════════════════════════════════════════════════
section "STEP 5 — SNS Alert Topic"
DEFAULT_SNS_NAME="patronai-alerts-${COMPANY_SLUG}"
info "Listing all existing SNS topics..."
SNS_TOPICS=()
while IFS= read -r arn; do
  [[ -n "$arn" ]] && SNS_TOPICS+=("$arn")
done < <(aws sns list-topics --region "$AWS_REGION" \
  --query 'Topics[*].TopicArn' --output text 2>/dev/null | tr '\t' '\n' || true)

subscribe_email() {
  local TOPIC_ARN="$1"
  local EMAILS="$2"
  IFS=',' read -ra _SUBS <<< "$EMAILS"
  for _ADDR in "${_SUBS[@]}"; do
    aws sns subscribe --topic-arn "$TOPIC_ARN" --protocol email \
      --notification-endpoint "$_ADDR" --region "$AWS_REGION" &>/dev/null || true
    ok "Subscription sent to $_ADDR — confirm via email"
  done
  unset _SUBS _ADDR
}

if [[ ${#SNS_TOPICS[@]} -gt 0 ]]; then
  echo ""
  echo "  Existing SNS topics:"
  for i in "${!SNS_TOPICS[@]}"; do
    echo "  [$((i+1))]  ${SNS_TOPICS[$i]}"
  done
  CREATE_IDX=$(( ${#SNS_TOPICS[@]} + 1 ))
  SKIP_IDX=$(( ${#SNS_TOPICS[@]} + 2 ))
  echo "  [$CREATE_IDX]  Create new: $DEFAULT_SNS_NAME"
  echo "  [$SKIP_IDX]  Skip SNS"
  ask "Choice [$CREATE_IDX]:"
  read -r C; C="${C:-$CREATE_IDX}"
  if [[ "$C" == "$SKIP_IDX" ]]; then
    SNS_ARN=""; warn "SNS skipped"
  elif [[ "$C" == "$CREATE_IDX" ]]; then
    SNS_ARN=$(aws sns create-topic --name "$DEFAULT_SNS_NAME" --region "$AWS_REGION" \
      --query 'TopicArn' --output text)
    subscribe_email "$SNS_ARN" "$ALERT_EMAIL"
  else
    SNS_ARN="${SNS_TOPICS[$(( C - 1 ))]}"
    ok "Reusing: $SNS_ARN"
    ask "Subscribe $ALERT_EMAIL to this topic? (y/N):"
    read -r SR
    [[ "$SR" =~ ^[yY]$ ]] && subscribe_email "$SNS_ARN" "$ALERT_EMAIL"
  fi
else
  echo ""
  echo "  [1]  Create SNS topic: $DEFAULT_SNS_NAME"
  echo "  [2]  Skip"
  ask "Choice [1]:"
  read -r C; C="${C:-1}"
  if [[ "$C" == "1" ]]; then
    SNS_ARN=$(aws sns create-topic --name "$DEFAULT_SNS_NAME" --region "$AWS_REGION" \
      --query 'TopicArn' --output text)
    subscribe_email "$SNS_ARN" "$ALERT_EMAIL"
  else
    SNS_ARN=""; warn "SNS skipped"
  fi
fi

# ══════════════════════════════════════════════════════════════
# STEP 6 — VPC FLOW LOGS
# ══════════════════════════════════════════════════════════════
section "STEP 6 — VPC Flow Logs"
info "Listing VPCs in $AWS_REGION..."
echo ""

VPC_IDS_LIST=(); VPC_NAMES_LIST=(); VPC_FL_STATUS=()
while IFS=$'\t' read -r vpc_id name; do
  [[ -z "$vpc_id" ]] && continue
  VPC_IDS_LIST+=("$vpc_id")
  VPC_NAMES_LIST+=("${name:-(no name)}")
  FL=$(aws ec2 describe-flow-logs \
    --filter "Name=resource-id,Values=$vpc_id" \
    --query 'FlowLogs[?LogDestinationType==`s3`].FlowLogId' \
    --output text 2>/dev/null || echo "")
  [[ -n "$FL" ]] && VPC_FL_STATUS+=("ENABLED → S3") || VPC_FL_STATUS+=("none")
done < <(aws ec2 describe-vpcs --region "$AWS_REGION" \
  --query 'Vpcs[*].[VpcId,Tags[?Key==`Name`].Value|[0]]' \
  --output text 2>/dev/null | grep -v "^$" || true)

if [[ ${#VPC_IDS_LIST[@]} -eq 0 ]]; then
  warn "No VPCs found — skipping"
else
  printf "  %-4s %-22s %-22s %s\n" "No." "VPC ID" "Name" "Flow Logs → S3"
  printf "  %-4s %-22s %-22s %s\n" "---" "------" "----" "--------------"
  for i in "${!VPC_IDS_LIST[@]}"; do
    printf "  [%s]  %-20s %-22s %s\n" \
      "$((i+1))" "${VPC_IDS_LIST[$i]}" "${VPC_NAMES_LIST[$i]}" "${VPC_FL_STATUS[$i]}"
  done
  echo ""
  echo "  Enter comma-separated numbers to enable Flow Logs (e.g. 1,2)"
  echo "  Press Enter to skip"
  ask "Selection:"
  read -r VPC_SEL

  if [[ -n "$VPC_SEL" ]]; then
    IFS=',' read -ra PICKS <<< "$VPC_SEL"
    for PICK in "${PICKS[@]}"; do
      PICK=$(echo "$PICK" | tr -d ' ')
      IDX=$(( PICK - 1 ))
      VID="${VPC_IDS_LIST[$IDX]}"
      if [[ "${VPC_FL_STATUS[$IDX]}" == *"ENABLED"* ]]; then
        warn "Flow Logs already enabled on $VID — skipping"
      else
        aws ec2 create-flow-logs \
          --resource-type VPC --resource-ids "$VID" \
          --traffic-type ALL --log-destination-type s3 \
          --log-destination "arn:aws:s3:::${S3_BUCKET}/ocsf/vpc-flow/" \
          --region "$AWS_REGION" >/dev/null 2>&1 \
          || warn "May already exist for $VID"
        ok "Flow Logs enabled: $VID → s3://${S3_BUCKET}/ocsf/vpc-flow/"
      fi
    done
  else
    warn "VPC Flow Logs skipped"
  fi
fi

# ══════════════════════════════════════════════════════════════
# STEP 7 — GENERATE CONFIG FILES
# ══════════════════════════════════════════════════════════════
section "STEP 7 — Generate Config Files"

# ── .env ──────────────────────────────────────────────────────
divider
echo -e "${BOLD}  .env${NC}"
echo "  [1]  Generate .env (overwrites if exists)"
echo "  [2]  Skip"
ask "Choice [1]:"
read -r C; C="${C:-1}"
if [[ "$C" == "1" ]]; then
  cat > "$REPO_DIR/.env" <<EOF
# Generated by prereqs.sh on $(date -u +%Y-%m-%dT%H:%M:%SZ)
# DO NOT COMMIT TO GIT

MARAUDER_SCAN_BUCKET=${S3_BUCKET}
AWS_REGION=${AWS_REGION}
AWS_ACCESS_KEY_ID=${SCANNER_KEY_ID}
AWS_SECRET_ACCESS_KEY=${SCANNER_KEY_SECRET}

COMPANY_NAME=${COMPANY_NAME}
COMPANY_SLUG=${COMPANY_SLUG}

ALLOWED_EMAILS=${ALLOWED_EMAILS}
ADMIN_EMAILS=${ADMIN_EMAILS}

ALERT_SNS_ARN=${SNS_ARN}
TRINITY_WEBHOOK_URL=${TRINITY_WEBHOOK_URL}
LOGANALYZER_WEBHOOK_URL=${LOGANALYZER_WEBHOOK_URL}

SCAN_INTERVAL_SECS=${SCAN_INTERVAL_SECS}
DEDUP_WINDOW_MINUTES=${DEDUP_WINDOW_MINUTES}
CROWDSTRIKE_ENABLED=false
CLOUD_PROVIDER=aws

GF_SECURITY_ADMIN_PASSWORD=${GF_ADMIN_PASSWORD}
GF_SECURITY_ADMIN_USER=admin
GF_AUTH_ANONYMOUS_ENABLED=false

STREAMLIT_PORT=8501
GRAFANA_PORT=3000
EOF
  chmod 600 "$REPO_DIR/.env"
  ok ".env → $REPO_DIR/.env  (chmod 600)"
else
  warn ".env skipped"
fi

# ── packetbeat.yml ────────────────────────────────────────────
divider
echo -e "${BOLD}  packetbeat.yml${NC}"
echo "  [1]  Generate from unauthorized.csv domain list"
echo "  [2]  Skip"
ask "Choice [1]:"
read -r C; C="${C:-1}"
if [[ "$C" == "1" ]]; then
  DOMAINS=()
  if [[ -f "$REPO_DIR/config/unauthorized.csv" ]]; then
    while IFS=',' read -r _n _c domain _p _s _notes; do
      domain=$(echo "$domain" | tr -d '"' | tr -d ' ')
      [[ -n "$domain" && "$domain" != "domain" ]] \
        && DOMAINS+=("$(echo "$domain" | sed 's/^\*\.//')")
    done < <(tail -n +2 "$REPO_DIR/config/unauthorized.csv")
  fi
  DOMAIN_FILTERS=""
  for d in "${DOMAINS[@]}"; do
    DOMAIN_FILTERS="${DOMAIN_FILTERS}            - contains:\n                destination.domain: \"${d}\"\n"
  done
  cat > "$REPO_DIR/packetbeat.yml" <<EOF
# PatronAI — packetbeat.yml — $(date -u +%Y-%m-%dT%H:%M:%SZ)
# DO NOT EDIT — regenerate via prereqs.sh

packetbeat.interfaces.device: any
packetbeat.interfaces.snaplen: 1514

packetbeat.protocols:
  - type: http
    ports: [80, 443, 8080, 8501, 3000, 8000, 8443, 5000]
    send_request: false
    send_response: false
  - type: dns
    ports: [53]
    include_authorities: true

processors:
  - drop_event:
      when:
        not:
          or:
$(printf "%b" "$DOMAIN_FILTERS")            - equals:
                destination.port: 11434
            - equals:
                destination.port: 1234
            - equals:
                destination.port: 8080
  - add_fields:
      target: ''
      fields:
        company: "${COMPANY_SLUG}"
        scanner: "marauder-scan"

output.file:
  enabled: true
  path: "/var/log/packetbeat"
  filename: "packetbeat"
  rotate_every_kb: 10240
  number_of_files: 7
  codec.json:
    pretty: false

logging.level: warning
logging.to_files: true
logging.files:
  path: /var/log/packetbeat
  name: packetbeat.log
  keepfiles: 3

queue.mem:
  events: 4096
  flush.min_events: 512
  flush.timeout: 5s
EOF
  ok "packetbeat.yml → $REPO_DIR/packetbeat.yml  (${#DOMAINS[@]} domains)"
else
  warn "packetbeat.yml skipped"
fi

# ── agent/config.json ─────────────────────────────────────────
divider
echo -e "${BOLD}  agent/config.json${NC}"
echo "  [1]  Generate"
echo "  [2]  Skip"
ask "Choice [1]:"
read -r C; C="${C:-1}"
if [[ "$C" == "1" ]]; then
  mkdir -p "$REPO_DIR/agent"
  cat > "$REPO_DIR/agent/config.json" <<EOF
{
  "bucket":           "${S3_BUCKET}",
  "region":           "${AWS_REGION}",
  "prefix":           "ocsf/agent/",
  "interval_seconds": 60,
  "company":          "${COMPANY_SLUG}"
}
EOF
  ok "agent/config.json → $REPO_DIR/agent/config.json"
else
  warn "agent/config.json skipped"
fi

# ── Grafana datasource ────────────────────────────────────────
divider
echo -e "${BOLD}  grafana/datasources/s3.json${NC}"
echo "  [1]  Generate"
echo "  [2]  Skip"
ask "Choice [1]:"
read -r C; C="${C:-1}"
if [[ "$C" == "1" ]]; then
  mkdir -p "$REPO_DIR/grafana/datasources"
  cat > "$REPO_DIR/grafana/datasources/s3.json" <<EOF
{
  "apiVersion": 1,
  "datasources": [{
    "name":      "GhostAI-S3",
    "type":      "marcusolsson-json-datasource",
    "access":    "proxy",
    "url":       "https://s3.${AWS_REGION}.amazonaws.com/${S3_BUCKET}",
    "isDefault": true,
    "jsonData":  {"bucket": "${S3_BUCKET}", "region": "${AWS_REGION}"}
  }]
}
EOF
  ok "grafana/datasources/s3.json generated"
else
  warn "Grafana datasource skipped"
fi

# ══════════════════════════════════════════════════════════════
# STEP 8 — SCP (Mac only — auto-skipped when running on EC2)
# ══════════════════════════════════════════════════════════════
section "STEP 8 — Deploy Generated Files"

# Detect EC2 — try IMDSv2 first, fall back to IMDSv1
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

if [[ "$ON_EC2" == true ]]; then
  ok "Running on EC2 — files already generated in $REPO_DIR"
  echo ""
  echo "  Generated files in place:"
  for F in ".env" "packetbeat.yml" "agent/config.json" "grafana/datasources/s3.json"; do
    [[ -f "$REPO_DIR/$F" ]] && echo "  ✓ $REPO_DIR/$F" || echo "  — $REPO_DIR/$F (not generated)"
  done
else
  echo "  [1]  SCP generated files to EC2 now"
  echo "  [2]  Skip — I'll copy manually"
  ask "Choice [1]:"
  read -r C; C="${C:-1}"

  if [[ "$C" == "1" ]]; then
    ask "EC2 public IP or hostname:"
    read -r EC2_HOST
    [[ -z "$EC2_HOST" ]] && err "Cannot be empty"

    ask "Path to SSH private key (.pem):"
    read -r EC2_KEY
    EC2_KEY="${EC2_KEY/#\~/$HOME}"
    [[ ! -f "$EC2_KEY" ]] && err "Key not found: $EC2_KEY"
    chmod 400 "$EC2_KEY" 2>/dev/null || true

    ask "SSH username [ec2-user]:"
    read -r EC2_USER
    EC2_USER="${EC2_USER:-ec2-user}"

    ask "Remote project directory [/home/${EC2_USER}/marauder-scan]:"
    read -r EC2_REMOTE_DIR
    EC2_REMOTE_DIR="${EC2_REMOTE_DIR:-/home/${EC2_USER}/marauder-scan}"

    info "Testing SSH..."
    ssh -i "$EC2_KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=10 \
      "${EC2_USER}@${EC2_HOST}" "echo ok" &>/dev/null \
      && ok "SSH OK" \
      || err "SSH failed — check key, username, port 22"

    for FILE in ".env" "packetbeat.yml" "agent/config.json" "grafana/datasources/s3.json"; do
      LOCAL="$REPO_DIR/$FILE"
      if [[ -f "$LOCAL" ]]; then
        ssh -i "$EC2_KEY" -o StrictHostKeyChecking=no \
          "${EC2_USER}@${EC2_HOST}" \
          "mkdir -p '${EC2_REMOTE_DIR}/$(dirname "$FILE")'" 2>/dev/null || true
        scp -i "$EC2_KEY" -o StrictHostKeyChecking=no \
          "$LOCAL" "${EC2_USER}@${EC2_HOST}:${EC2_REMOTE_DIR}/${FILE}"
        ok "Pushed: $FILE"
      fi
    done
    ssh -i "$EC2_KEY" -o StrictHostKeyChecking=no \
      "${EC2_USER}@${EC2_HOST}" "chmod 600 '${EC2_REMOTE_DIR}/.env'" 2>/dev/null || true
    ok "Remote .env chmod 600"
  else
    warn "SCP skipped — copy files manually:"
    warn "  scp -i your-key.pem .env ${EC2_USER}@${EC2_HOST:-<ec2-ip>}:${EC2_REMOTE_DIR:-<remote-dir>}/"
  fi
fi

# ══════════════════════════════════════════════════════════════
# DONE
# ══════════════════════════════════════════════════════════════
REMOTE_DIR_DISPLAY="${EC2_REMOTE_DIR:-<remote-dir>}"
EC2_IP="${EC2_HOST:-<ec2-ip>}"

echo ""
echo -e "${BOLD}${GREEN}"
echo "=================================================="
echo "  Prerequisites complete!"
echo "=================================================="
echo -e "${NC}"
echo "  S3 bucket : $S3_BUCKET"
echo "  IAM user  : $IAM_USER"
[[ -n "$SNS_ARN" ]] && echo "  SNS topic : $SNS_ARN"
[[ -n "$EC2_HOST" ]] && echo "  EC2       : ${EC2_USER}@${EC2_IP}"
echo ""
echo "Next steps:"
echo ""
echo "  1. Confirm SNS subscription emails: $ALERT_EMAIL"
echo ""
[[ -n "$EC2_HOST" ]] && echo "  2. SSH into EC2:"
[[ -n "$EC2_HOST" ]] && echo "     ssh -i $EC2_KEY ${EC2_USER}@${EC2_IP}"
echo ""
echo "  3. Start the scanner:"
echo "     cd ${REMOTE_DIR_DISPLAY} && docker-compose up -d"
echo ""
echo "  4. Populate ENI metadata cache (run once after first boot):"
echo "     docker exec patronai python3 scripts/refresh_eni_cache.py"
echo ""
echo "  5. Open dashboards:"
echo "     Grafana  : http://${EC2_IP}:3000"
echo "     Settings : http://${EC2_IP}:8501"
echo ""
echo -e "${YELLOW}IMPORTANT:${NC} .env contains AWS credentials — never commit to git."
echo ""
echo -e "${RED}${BOLD}⚠  SECURITY — ACTION REQUIRED BEFORE PRODUCTION  ⚠${NC}"
echo -e "${RED}   Security groups are currently open to 0.0.0.0/0 (the entire internet).${NC}"
echo -e "${RED}   Lock each port to your office/VPN IP before go-live:${NC}"
echo ""
echo "   AWS Console → EC2 → Security Groups → select your group"
echo "   Edit each inbound rule — change Source from 0.0.0.0/0 to <your-ip>/32"
echo ""
echo "   Ports to restrict:"
echo "     22   patronai-ssh       → your admin IP only"
echo "     80   patronai-nginx     → your office/VPN CIDR"
echo "     3000 patronai-grafana   → your office/VPN CIDR"
echo "     8501 patronai-streamlit → your office/VPN CIDR"
echo ""
echo "   Find your current IP: https://checkip.amazonaws.com"
echo -e "${RED}${BOLD}────────────────────────────────────────────────────${NC}"
echo ""
echo -e "${BOLD}Giggso Inc x TrinityOps.ai x AIRTaaS${NC}"
