#!/usr/bin/env bash
# =============================================================
# FILE: scripts/setup.sh
# VERSION: 1.0.0
# UPDATED: 2026-04-18
# OWNER: Giggso Inc
# PURPOSE: Interactive first-run setup for PatronAI.
#          Creates all AWS prerequisites, seeds S3 config files,
#          generates .env, packetbeat.yml and agent/config.json.
#          Run once on the EC2 before docker-compose up.
# USAGE: bash scripts/setup.sh
# REQUIRES: AWS CLI v2, configured with admin credentials
# =============================================================

set -euo pipefail

# ── Colours ───────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

# ── Helpers ───────────────────────────────────────────────────
ok()   { echo -e "${GREEN}✓${NC} $1"; }
err()  { echo -e "${RED}✗${NC} $1"; exit 1; }
warn() { echo -e "${YELLOW}!${NC} $1"; }
info() { echo -e "${BLUE}→${NC} $1"; }
ask()  { echo -e "${BOLD}$1${NC}"; }
step() { echo -e "\n${BOLD}[$1/$TOTAL_STEPS]${NC} $2..."; }

TOTAL_STEPS=15
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# ── Banner ────────────────────────────────────────────────────
clear
echo -e "${BOLD}"
echo "=================================================="
echo "  PatronAI — First Run Setup"
echo "  Giggso Inc"
echo "=================================================="
echo -e "${NC}"
echo "This script will:"
echo "  • Create your S3 bucket and seed config files"
echo "  • Create an IAM user and policy for the scanner"
echo "  • Create an SNS topic and subscribe your alert email"
echo "  • Enable VPC Flow Logs on your target VPCs"
echo "  • Generate .env, packetbeat.yml and agent config"
echo ""
echo "Estimated time: 5-10 minutes"
echo ""

# ── Prerequisites check ───────────────────────────────────────
info "Checking prerequisites..."

command -v aws >/dev/null 2>&1 || err "AWS CLI not found. Install it first: https://aws.amazon.com/cli/"
command -v docker >/dev/null 2>&1 || err "Docker not found. Install it first."
command -v docker-compose >/dev/null 2>&1 || err "docker-compose not found. Install it first."

AWS_IDENTITY=$(aws sts get-caller-identity 2>&1) || err "AWS credentials not configured. Run: aws configure"
ok "AWS CLI configured"
ok "Docker found"
ok "docker-compose found"

# ── Interactive questions ──────────────────────────────────────
echo ""
echo -e "${BOLD}AWS Configuration${NC}"
echo "--------------------------------------------------"

ask "AWS region [us-east-1]:"
read -r AWS_REGION
AWS_REGION="${AWS_REGION:-us-east-1}"

ask "Company name (display, e.g. Acme Corp):"
read -r COMPANY_NAME
[ -z "$COMPANY_NAME" ] && err "Company name cannot be empty"

ask "Company slug (lowercase, no spaces, e.g. acme):"
read -r COMPANY_SLUG
COMPANY_SLUG=$(echo "$COMPANY_SLUG" | tr '[:upper:]' '[:lower:]' | tr ' ' '-')
[ -z "$COMPANY_SLUG" ] && err "Company slug cannot be empty"

DEFAULT_BUCKET="marauder-scan-${COMPANY_SLUG}"
ask "S3 bucket name [${DEFAULT_BUCKET}]:"
read -r S3_BUCKET
S3_BUCKET="${S3_BUCKET:-$DEFAULT_BUCKET}"

echo ""
echo -e "${BOLD}Access Configuration${NC}"
echo "--------------------------------------------------"

ask "Allowed emails for Streamlit UI (comma separated):"
read -r ALLOWED_EMAILS
[ -z "$ALLOWED_EMAILS" ] && err "At least one allowed email required"

ask "Admin emails — can edit settings (comma separated):"
read -r ADMIN_EMAILS
[ -z "$ADMIN_EMAILS" ] && err "At least one admin email required"

ask "Alert email for SNS subscription:"
read -r ALERT_EMAIL
[ -z "$ALERT_EMAIL" ] && err "Alert email required"

# ── SES configuration (sender for OTP / welcome / alert email) ─
echo ""
echo -e "${BOLD}SES (Simple Email Service) — for OTP, welcome, alert mail${NC}"
echo "--------------------------------------------------"
echo "PatronAI uses SES to send agent-installer OTPs and user welcome"
echo "emails. The SENDER address (or its domain) must be verified in SES."
echo ""

# Default SES region = AWS_REGION (most common). Override only if SES is set
# up in a different region.
ask "SES region [${AWS_REGION}]:"
read -r SES_REGION
SES_REGION="${SES_REGION:-${AWS_REGION}}"

# Suggest the first ADMIN_EMAILS entry as the default sender — likely
# already verified or easy for the admin to verify (their own inbox).
DEFAULT_SES_SENDER=$(echo "$ADMIN_EMAILS" | cut -d',' -f1 | tr -d ' ')
ask "SES sender email [${DEFAULT_SES_SENDER}]:"
read -r SES_SENDER_EMAIL
SES_SENDER_EMAIL="${SES_SENDER_EMAIL:-${DEFAULT_SES_SENDER}}"
[ -z "$SES_SENDER_EMAIL" ] && err "SES sender email required"

# Single-email vs domain (DKIM):
# - Single: one click-to-verify email per address. Fine for a 1-2-user pilot.
# - Domain: one set of DKIM CNAME records, then ANY address @yourdomain works.
#   Strongly recommended for >5 users.
SES_SENDER_DOMAIN=$(echo "$SES_SENDER_EMAIL" | awk -F'@' '{print $2}')
echo ""
echo "Verification mode:"
echo "  1) Single email — verify just ${SES_SENDER_EMAIL} (good for testing)"
echo "  2) Whole domain (DKIM) — verify ${SES_SENDER_DOMAIN}, then any"
echo "     address @${SES_SENDER_DOMAIN} works (recommended for >5 users)"
ask "Mode [2]:"
read -r SES_VERIFY_MODE
SES_VERIFY_MODE="${SES_VERIFY_MODE:-2}"

echo ""
echo -e "${BOLD}Alerting (press Enter to skip optional fields)${NC}"
echo "--------------------------------------------------"

ask "Trinity webhook URL [optional]:"
read -r TRINITY_WEBHOOK_URL
TRINITY_WEBHOOK_URL="${TRINITY_WEBHOOK_URL:-}"

ask "LogAnalyzer webhook URL [optional]:"
read -r LOGANALYZER_WEBHOOK_URL
LOGANALYZER_WEBHOOK_URL="${LOGANALYZER_WEBHOOK_URL:-}"

echo ""
echo -e "${BOLD}Scanner Settings${NC}"
echo "--------------------------------------------------"

ask "Scan interval seconds [300]:"
read -r SCAN_INTERVAL_SECS
SCAN_INTERVAL_SECS="${SCAN_INTERVAL_SECS:-300}"

ask "Dedup window minutes [60]:"
read -r DEDUP_WINDOW_MINUTES
DEDUP_WINDOW_MINUTES="${DEDUP_WINDOW_MINUTES:-60}"

ask "Grafana admin password [press Enter to auto-generate]:"
read -r -s GF_ADMIN_PASSWORD
echo ""
if [ -z "$GF_ADMIN_PASSWORD" ]; then
    # 32-char URL-safe random — no known-default password ever ends up in .env.
    GF_ADMIN_PASSWORD="$(openssl rand -base64 24 | tr -d '/+=' | cut -c1-32)"
    echo -e "${YELLOW}Generated random Grafana admin password — save it now:${NC}"
    echo "  ${BOLD}${GF_ADMIN_PASSWORD}${NC}"
    echo "  (also written to .env as GF_SECURITY_ADMIN_PASSWORD; chmod 600)"
    echo ""
fi

echo ""
echo -e "${BOLD}VPC Flow Logs${NC}"
echo "--------------------------------------------------"
info "Fetching your VPCs..."
VPC_LIST=$(aws ec2 describe-vpcs \
  --region "$AWS_REGION" \
  --query 'Vpcs[*].[VpcId,Tags[?Key==`Name`].Value|[0]]' \
  --output text 2>/dev/null || echo "")

if [ -n "$VPC_LIST" ]; then
  echo "Available VPCs:"
  echo "$VPC_LIST"
  ask "VPC IDs to enable Flow Logs on (comma separated, or 'skip'):"
  read -r VPC_IDS
else
  warn "No VPCs found or insufficient permissions. Skipping VPC Flow Logs."
  VPC_IDS="skip"
fi

# ── Confirm ───────────────────────────────────────────────────
echo ""
echo -e "${BOLD}=================================================="
echo "  Review your configuration"
echo "==================================================${NC}"
echo "  Region:          $AWS_REGION"
echo "  Company:         $COMPANY_NAME ($COMPANY_SLUG)"
echo "  S3 bucket:       $S3_BUCKET"
echo "  Alert email:     $ALERT_EMAIL"
echo "  Allowed emails:  $ALLOWED_EMAILS"
echo "  Admin emails:    $ADMIN_EMAILS"
echo "  Scan interval:   ${SCAN_INTERVAL_SECS}s"
echo "  Dedup window:    ${DEDUP_WINDOW_MINUTES}m"
[ "$VPC_IDS" != "skip" ] && echo "  VPC Flow Logs:   $VPC_IDS"
echo ""
ask "Proceed? (y/N):"
read -r CONFIRM
[[ "$CONFIRM" != "y" && "$CONFIRM" != "Y" ]] && { warn "Setup cancelled."; exit 0; }

echo ""
echo -e "${BOLD}Running setup...${NC}"
echo ""

# ── STEP 1: S3 bucket ─────────────────────────────────────────
step 1 "Creating S3 bucket"
if aws s3api head-bucket --bucket "$S3_BUCKET" 2>/dev/null; then
  warn "Bucket $S3_BUCKET already exists — skipping creation"
else
  if [ "$AWS_REGION" = "us-east-1" ]; then
    aws s3api create-bucket \
      --bucket "$S3_BUCKET" \
      --region "$AWS_REGION" >/dev/null
  else
    aws s3api create-bucket \
      --bucket "$S3_BUCKET" \
      --region "$AWS_REGION" \
      --create-bucket-configuration LocationConstraint="$AWS_REGION" >/dev/null
  fi
fi
ok "S3 bucket: $S3_BUCKET"

# ── STEP 2: Bucket versioning ─────────────────────────────────
step 2 "Enabling S3 versioning"
aws s3api put-bucket-versioning \
  --bucket "$S3_BUCKET" \
  --versioning-configuration Status=Enabled >/dev/null
ok "Versioning enabled"

# ── STEP 3: Block public access ───────────────────────────────
step 3 "Blocking public S3 access"
aws s3api put-public-access-block \
  --bucket "$S3_BUCKET" \
  --public-access-block-configuration \
    "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true" >/dev/null
ok "Public access blocked"

# ── STEP 4: Lifecycle rules ───────────────────────────────────
step 4 "Setting S3 lifecycle rules"
aws s3api put-bucket-lifecycle-configuration \
  --bucket "$S3_BUCKET" \
  --lifecycle-configuration '{
    "Rules": [
      {
        "ID": "findings-archive",
        "Status": "Enabled",
        "Filter": {"Prefix": "findings/"},
        "Transitions": [{"Days": 30, "StorageClass": "STANDARD_IA"}],
        "Expiration": {"Days": 365}
      },
      {
        "ID": "ocsf-archive",
        "Status": "Enabled",
        "Filter": {"Prefix": "ocsf/"},
        "Transitions": [{"Days": 30, "StorageClass": "STANDARD_IA"}],
        "Expiration": {"Days": 90}
      },
      {
        "ID": "dedup-expire",
        "Status": "Enabled",
        "Filter": {"Prefix": "dedup/"},
        "Expiration": {"Days": 90}
      }
    ]
  }' >/dev/null
ok "Lifecycle rules set"

# ── STEP 5: IAM user ──────────────────────────────────────────
step 5 "Creating IAM user"
IAM_USER="marauder-scan"
if aws iam get-user --user-name "$IAM_USER" 2>/dev/null; then
  warn "IAM user $IAM_USER already exists — skipping creation"
else
  aws iam create-user --user-name "$IAM_USER" >/dev/null
fi
ok "IAM user: $IAM_USER"

# ── STEP 6: IAM policy ───────────────────────────────────────
step 6 "Attaching IAM policy"
IAM_POLICY=$(cat <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject","s3:PutObject","s3:ListBucket",
                 "s3:DeleteObject","s3:GetBucketLocation"],
      "Resource": [
        "arn:aws:s3:::${S3_BUCKET}",
        "arn:aws:s3:::${S3_BUCKET}/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": ["sns:Publish"],
      "Resource": "arn:aws:sns:${AWS_REGION}:*:marauder-scan-*"
    },
    {
      "Effect": "Allow",
      "Action": ["ec2:DescribeInstances","ec2:DescribeNetworkInterfaces"],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": ["cloudtrail:LookupEvents"],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": ["identitystore:ListUsers","identitystore:DescribeUser"],
      "Resource": "*"
    }
  ]
}
EOF
)
aws iam put-user-policy \
  --user-name "$IAM_USER" \
  --policy-name "marauder-scan-policy" \
  --policy-document "$IAM_POLICY" >/dev/null
ok "IAM policy attached"

# ── STEP 7: IAM access key ────────────────────────────────────
step 7 "Generating IAM access key"
KEY_OUTPUT=$(aws iam create-access-key --user-name "$IAM_USER" 2>/dev/null || echo "exists")
if [ "$KEY_OUTPUT" = "exists" ]; then
  warn "Access key already exists for $IAM_USER — using existing key from .env if present"
  AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID:-REPLACE_WITH_EXISTING_KEY}"
  AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY:-REPLACE_WITH_EXISTING_SECRET}"
else
  AWS_ACCESS_KEY_ID=$(echo "$KEY_OUTPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['AccessKey']['AccessKeyId'])")
  AWS_SECRET_ACCESS_KEY=$(echo "$KEY_OUTPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['AccessKey']['SecretAccessKey'])")
fi
ok "Access key generated"

# ── STEP 8: SNS topic ─────────────────────────────────────────
step 8 "Creating SNS topic"
SNS_ARN=$(aws sns create-topic \
  --name "marauder-scan-alerts" \
  --region "$AWS_REGION" \
  --query 'TopicArn' \
  --output text)
ok "SNS topic: $SNS_ARN"

# ── STEP 9: SNS subscription ──────────────────────────────────
step 9 "Subscribing alert email to SNS"
aws sns subscribe \
  --topic-arn "$SNS_ARN" \
  --protocol email \
  --notification-endpoint "$ALERT_EMAIL" \
  --region "$AWS_REGION" >/dev/null
ok "Subscription created — check $ALERT_EMAIL to confirm"

# ── STEP 9b: SES sender verification ──────────────────────────
step 9b "Configuring SES sender identity (region: $SES_REGION)"

if [ "$SES_VERIFY_MODE" = "1" ]; then
    # ── Single-email verification ───────────────────────────────
    echo "  Verifying single email: $SES_SENDER_EMAIL"
    SES_VERIFIED_STATUS=$(aws ses get-identity-verification-attributes \
        --identities "$SES_SENDER_EMAIL" \
        --region "$SES_REGION" \
        --query "VerificationAttributes.\"$SES_SENDER_EMAIL\".VerificationStatus" \
        --output text 2>/dev/null || echo "NotStarted")

    if [ "$SES_VERIFIED_STATUS" = "Success" ]; then
        ok "Sender already verified — no action needed"
    else
        aws ses verify-email-identity \
            --email-address "$SES_SENDER_EMAIL" \
            --region "$SES_REGION" >/dev/null
        ok "Verification email sent to $SES_SENDER_EMAIL"
        echo -e "  ${YELLOW}ACTION REQUIRED:${NC} open that inbox, click the AWS verification"
        echo "  link before sending any OTP / welcome email."
    fi
else
    # ── Domain (DKIM) verification ─────────────────────────────
    echo "  Verifying domain: $SES_SENDER_DOMAIN"
    DOMAIN_STATUS=$(aws ses get-identity-verification-attributes \
        --identities "$SES_SENDER_DOMAIN" \
        --region "$SES_REGION" \
        --query "VerificationAttributes.\"$SES_SENDER_DOMAIN\".VerificationStatus" \
        --output text 2>/dev/null || echo "NotStarted")

    if [ "$DOMAIN_STATUS" != "Success" ]; then
        aws ses verify-domain-identity \
            --domain "$SES_SENDER_DOMAIN" \
            --region "$SES_REGION" >/dev/null
    fi

    # Get DKIM tokens (3 CNAMEs the user must add to DNS)
    DKIM_TOKENS=$(aws ses verify-domain-dkim \
        --domain "$SES_SENDER_DOMAIN" \
        --region "$SES_REGION" \
        --query 'DkimTokens' \
        --output text 2>/dev/null || echo "")

    if [ -n "$DKIM_TOKENS" ]; then
        echo -e "  ${YELLOW}ACTION REQUIRED:${NC} add these 3 CNAME records to DNS for"
        echo "  $SES_SENDER_DOMAIN — then SES will auto-verify within ~72h"
        echo "  (usually <1h). Until then, sending will fail silently."
        echo ""
        for token in $DKIM_TOKENS; do
            echo "    Type:  CNAME"
            echo "    Name:  ${token}._domainkey.${SES_SENDER_DOMAIN}"
            echo "    Value: ${token}.dkim.amazonses.com"
            echo ""
        done
    fi

    if [ "$DOMAIN_STATUS" = "Success" ]; then
        ok "Domain $SES_SENDER_DOMAIN already verified — DKIM CNAMEs above"
        ok "are still required for production sending; verify they exist."
    else
        ok "Domain verification initiated for $SES_SENDER_DOMAIN"
    fi
fi

# ── Sandbox detection ──────────────────────────────────────────
QUOTA_MAX=$(aws ses get-send-quota \
    --region "$SES_REGION" \
    --query 'Max24HourSend' \
    --output text 2>/dev/null || echo "0")
QUOTA_INT=${QUOTA_MAX%.*}    # strip decimals — bash int comparison

if [ "$QUOTA_INT" -le "200" ]; then
    echo ""
    echo -e "  ${YELLOW}⚠ SES is in SANDBOX MODE${NC} (cap: ${QUOTA_MAX} emails / 24h,"
    echo "  recipients must be verified). To send to your team:"
    echo ""
    echo "    1. Open the SES console:"
    echo "       https://${SES_REGION}.console.aws.amazon.com/ses/home?region=${SES_REGION}#/account"
    echo "    2. Click 'Request production access'"
    echo "    3. Fill the use-case form — typical approval is ~24h"
    echo ""
    echo "  Until production access is granted, you can only send to verified"
    echo "  addresses. Verify your test recipients now via:"
    echo "    aws ses verify-email-identity --email <addr> --region $SES_REGION"
    echo ""
else
    ok "SES production access active (quota: ${QUOTA_MAX}/24h)"
fi

# ── STEP 10: VPC Flow Logs ────────────────────────────────────
step 10 "Enabling VPC Flow Logs"
if [ "$VPC_IDS" != "skip" ] && [ -n "$VPC_IDS" ]; then
  IFS=',' read -ra VPCS <<< "$VPC_IDS"
  for VPC_ID in "${VPCS[@]}"; do
    VPC_ID=$(echo "$VPC_ID" | tr -d ' ')
    aws ec2 create-flow-logs \
      --resource-type VPC \
      --resource-ids "$VPC_ID" \
      --traffic-type ALL \
      --log-destination-type s3 \
      --log-destination "arn:aws:s3:::${S3_BUCKET}/ocsf/vpc-flow/" \
      --region "$AWS_REGION" >/dev/null 2>&1 || warn "Flow Logs may already exist for $VPC_ID"
    ok "Flow Logs enabled: $VPC_ID"
  done
else
  warn "VPC Flow Logs skipped — enable manually via PREREQUISITES-TO-DO.md"
fi

# ── STEP 11: Seed S3 config files ─────────────────────────────
step 11 "Seeding S3 config files"
aws s3 cp "$REPO_DIR/config/settings.json" "s3://${S3_BUCKET}/config/settings.json" >/dev/null
aws s3 cp "$REPO_DIR/config/authorized.csv" "s3://${S3_BUCKET}/config/authorized.csv" >/dev/null
aws s3 cp "$REPO_DIR/config/unauthorized.csv" "s3://${S3_BUCKET}/config/unauthorized.csv" >/dev/null
ok "Config files seeded to S3"

# ── STEP 12: Generate .env ────────────────────────────────────
step 12 "Generating .env file"

# Detect EC2 public IP via instance metadata (IMDSv1 fallback)
EC2_PUBLIC_IP=$(curl -s --max-time 3 http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || echo "")
if [ -n "$EC2_PUBLIC_IP" ]; then
  ok "Detected EC2 public IP: $EC2_PUBLIC_IP"
else
  warn "Could not detect EC2 public IP — PUBLIC_HOST and GRAFANA_URL will be empty."
  warn "Set them manually in .env after generation."
fi

cat > "$REPO_DIR/.env" <<EOF
# Generated by setup.sh on $(date -u +%Y-%m-%dT%H:%M:%SZ)
# DO NOT COMMIT TO GIT
# ──────────────────────────────────────────────────────────────
# REQUIRED: MARAUDER_SCAN_BUCKET — the S3 bucket holding all
#   OCSF events, summaries, and config. The dashboard will show
#   SYNTHETIC demo data until this matches the actual bucket.
# ──────────────────────────────────────────────────────────────
MARAUDER_SCAN_BUCKET=${S3_BUCKET}
AWS_REGION=${AWS_REGION}
AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID}
AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}

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

# PUBLIC_HOST — EC2 public IP or DNS, no protocol, no trailing slash.
# Used by the Streamlit sidebar to build absolute Grafana links.
PUBLIC_HOST=${EC2_PUBLIC_IP}

# GRAFANA_URL — full Grafana base URL served via nginx /grafana subpath.
# Takes precedence over PUBLIC_HOST. Must be reachable from the user's browser.
GRAFANA_URL=${EC2_PUBLIC_IP:+http://${EC2_PUBLIC_IP}/grafana}

# ── SES (email) ───────────────────────────────────────────────
# SES sender identity. Verified by setup.sh via aws ses verify-*-identity.
# - Single-email mode: SES_SENDER_EMAIL must be the exact verified address.
# - Domain mode (DKIM): SES_SENDER_EMAIL can be any address @verified-domain.
SES_SENDER_EMAIL=${SES_SENDER_EMAIL}
# SES region — usually equals AWS_REGION; override only if SES is set up
# in a different region.
SES_REGION=${SES_REGION}
# Used by alerter as the From: header for SES-routed alert emails.
# Must resolve to an SES-verified identity in SES_REGION.
PATRONAI_FROM_EMAIL=${SES_SENDER_EMAIL}

STREAMLIT_PORT=8501
GRAFANA_PORT=3000

# Set ALERT_RECIPIENTS to comma-separated emails for SNS/SES alerts
ALERT_RECIPIENTS=
EOF
chmod 600 "$REPO_DIR/.env"
ok ".env generated (chmod 600)"

# Validate the most critical variable is non-empty
WRITTEN_BUCKET=$(grep "^MARAUDER_SCAN_BUCKET=" "$REPO_DIR/.env" | cut -d= -f2)
if [ -z "$WRITTEN_BUCKET" ]; then
  warn "MARAUDER_SCAN_BUCKET is empty in .env — dashboard will show demo data until fixed."
fi

# ── STEP 13: Generate packetbeat.yml ──────────────────────────
step 13 "Generating packetbeat.yml"
bash "$SCRIPT_DIR/generate_packetbeat_config.sh" "$S3_BUCKET" "$AWS_REGION" "$COMPANY_SLUG"
ok "packetbeat.yml generated"

# ── STEP 14: Generate agent config ───────────────────────────
step 14 "Generating agent config"
mkdir -p "$REPO_DIR/agent"
cat > "$REPO_DIR/agent/config.json" <<EOF
{
  "bucket": "${S3_BUCKET}",
  "region": "${AWS_REGION}",
  "prefix": "ocsf/agent/",
  "interval_seconds": 60,
  "company": "${COMPANY_SLUG}"
}
EOF
ok "agent/config.json generated"

# ── STEP 15: Generate Grafana datasource ──────────────────────
step 15 "Generating Grafana datasource config"
mkdir -p "$REPO_DIR/grafana/datasources"
cat > "$REPO_DIR/grafana/datasources/s3.json" <<EOF
{
  "apiVersion": 1,
  "datasources": [
    {
      "name": "GhostAI-S3",
      "type": "marcusolsson-json-datasource",
      "access": "proxy",
      "url": "https://s3.${AWS_REGION}.amazonaws.com/${S3_BUCKET}",
      "isDefault": true,
      "jsonData": {
        "queryParams": "",
        "bucket": "${S3_BUCKET}",
        "region": "${AWS_REGION}"
      }
    }
  ]
}
EOF
ok "grafana/datasources/s3.json generated"

# ── Done ──────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${GREEN}"
echo "=================================================="
echo "  Setup complete!"
echo "=================================================="
echo -e "${NC}"
echo "Next steps:"
echo ""
echo "  1. Check your email ($ALERT_EMAIL)"
echo "     Click the SNS subscription confirmation link."
echo ""
echo "  2. Start the scanner:"
echo "     cd $REPO_DIR"
echo "     docker-compose up -d"
echo ""
echo "  3. Open dashboards:"
echo "     Grafana:   http://$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || echo 'your-ec2-ip'):3000"
echo "     Settings:  http://$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || echo 'your-ec2-ip'):8501"
echo ""
echo "  4. Deploy Packetbeat and agent to managed devices"
echo "     See agent/install/ for MDM packages"
echo ""
echo -e "${YELLOW}IMPORTANT:${NC} .env contains AWS credentials."
echo "Never commit .env to git. Never share it in Slack or email."
echo ""
echo -e "${BOLD}Giggso Inc x TrinityOps.ai x AIRTaaS${NC}"
