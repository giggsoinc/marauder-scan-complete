#!/usr/bin/env bash
# =============================================================
# FILE: scripts/setup_hook_agents.sh
# VERSION: 1.3.0
# UPDATED: 2026-04-20
# OWNER: Giggso Inc
# PURPOSE: One-time post-deploy provisioning for agent delivery.
#          Applies iam-policy.json to the EC2 instance role (auto-detected).
#          Runs IAM Access Analyzer validate-policy after apply.
#          Creates config/HOOK_AGENTS/catalog.json on S3 if missing.
#          Verifies IAM permissions for SES + S3 config/HOOK_AGENTS/ prefix.
#          Run once after initial deployment or after bucket change.
# USAGE: bash scripts/setup_hook_agents.sh
# REQUIRES: aws CLI, MARAUDER_SCAN_BUCKET + AWS_REGION env vars
# AUDIT LOG:
#   v1.0.0  2026-04-19  Initial — agent delivery system
#   v1.1.0  2026-04-19  S3 prefix agents/ → config/HOOK_AGENTS/; IAM validation
#   v1.2.0  2026-04-19  Auto-detect EC2 instance role; apply iam-policy.json
#   v1.3.0  2026-04-20  IAM Access Analyzer validate-policy after apply
# =============================================================
set -euo pipefail

BUCKET="${MARAUDER_SCAN_BUCKET:-}"
REGION="${AWS_REGION:-us-east-1}"

[ -n "$BUCKET" ] || { echo "ERROR: MARAUDER_SCAN_BUCKET is not set." >&2; exit 1; }

echo "PatronAI — Agent Delivery Setup"
echo "Bucket : $BUCKET"
echo "Region : $REGION"
echo ""

# ── Apply IAM policy to EC2 instance role ────────────────────
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
POLICY_FILE="$SCRIPT_DIR/../iam-policy.json"

echo "Applying IAM policy..."
if [ ! -f "$POLICY_FILE" ]; then
  echo "  WARNING: iam-policy.json not found at $POLICY_FILE — skipping IAM update."
else
  # Auto-detect EC2 instance role via IMDSv2
  IMDS_TOKEN=$(curl -sf --max-time 3 -X PUT \
    -H "X-aws-ec2-metadata-token-ttl-seconds: 21600" \
    http://169.254.169.254/latest/api/token 2>/dev/null || echo "")
  INSTANCE_ROLE=$(curl -sf --max-time 3 \
    -H "X-aws-ec2-metadata-token: $IMDS_TOKEN" \
    http://169.254.169.254/latest/meta-data/iam/security-credentials/ 2>/dev/null || echo "")
  if [ -z "$INSTANCE_ROLE" ]; then
    echo "  WARNING: Could not detect EC2 instance role (not on EC2 or no role attached)."
    echo "  Apply manually: aws iam put-role-policy --role-name <ROLE> \\"
    echo "    --policy-name PatronAIPolicy --policy-document file://iam-policy.json"
  else
    aws iam put-role-policy \
      --role-name "$INSTANCE_ROLE" \
      --policy-name "PatronAIPolicy" \
      --policy-document "file://$POLICY_FILE" \
      --region "$REGION" \
      && echo "  PatronAIPolicy applied to role: $INSTANCE_ROLE" \
      || echo "  ERROR: Failed to apply IAM policy — check caller permissions."
  fi
fi

# ── IAM Access Analyzer — validate policy document ───────────
echo "Running IAM Access Analyzer on iam-policy.json..."
if [ -f "$POLICY_FILE" ]; then
  FINDINGS=$(aws accessanalyzer validate-policy \
    --policy-document "file://$POLICY_FILE" \
    --policy-type IDENTITY_POLICY \
    --region "$REGION" \
    --query 'findings[*].[findingType,issueCode,learnMoreLink]' \
    --output text 2>/dev/null || echo "ANALYZER_UNAVAILABLE")

  if [ "$FINDINGS" = "ANALYZER_UNAVAILABLE" ]; then
    echo "  WARNING: Access Analyzer unavailable — check IAM permissions or region support."
  elif [ -z "$FINDINGS" ]; then
    echo "  No issues found — policy is clean."
  else
    while IFS=$'\t' read -r ftype code link; do
      echo "    [$ftype] $code"
      [ -n "$link" ] && echo "      More info: $link"
    done <<< "$FINDINGS"
    echo "  Review findings before deploying to production."
  fi
else
  echo "  Skipped — iam-policy.json not found."
fi
echo ""

# ── Check S3 access ───────────────────────────────────────────
echo "Checking S3 access..."
aws s3 ls "s3://$BUCKET/" --region "$REGION" >/dev/null \
  && echo "  S3 bucket accessible." \
  || { echo "ERROR: Cannot access s3://$BUCKET/" >&2; exit 1; }

# ── Establish config/HOOK_AGENTS/ prefix ──────────────────────
HOOK_PREFIX="config/HOOK_AGENTS"
echo "Establishing s3://$BUCKET/$HOOK_PREFIX/ prefix..."
KEEP_TMP=$(mktemp)
aws s3api put-object --bucket "$BUCKET" \
  --key "$HOOK_PREFIX/.keep" --body "$KEEP_TMP" --region "$REGION" >/dev/null
rm -f "$KEEP_TMP"
echo "  Prefix marker created."

# ── Bootstrap catalog if missing ──────────────────────────────
CATALOG_KEY="$HOOK_PREFIX/catalog.json"
if aws s3api head-object --bucket "$BUCKET" --key "$CATALOG_KEY" \
       --region "$REGION" >/dev/null 2>&1; then
  echo "  Catalog already exists at s3://$BUCKET/$CATALOG_KEY"
else
  echo "  Creating empty catalog..."
  echo "[]" | aws s3 cp - "s3://$BUCKET/$CATALOG_KEY" \
    --region "$REGION" \
    --content-type "application/json" \
    --quiet
  echo "  Catalog created at s3://$BUCKET/$CATALOG_KEY"
fi

# ── Validate HOOK_AGENTS S3 write permission ──────────────────
echo ""
echo "Validating config/HOOK_AGENTS S3 write permissions..."
echo "test" | aws s3 cp - "s3://$BUCKET/$HOOK_PREFIX/.iam-test" \
  --region "$REGION" --quiet 2>/dev/null \
  && aws s3 rm "s3://$BUCKET/$HOOK_PREFIX/.iam-test" \
     --region "$REGION" --quiet 2>/dev/null \
  && echo "  HOOK_AGENTS write permission verified." \
  || echo "  ERROR: Cannot write to $HOOK_PREFIX/ — check IAM policy (HookAgentsDelivery)."

# ── Verify SES identity ───────────────────────────────────────
echo ""
echo "Checking SES sender identity..."
SES_SENDER="${SES_SENDER_EMAIL:-}"
if [ -n "$SES_SENDER" ]; then
  STATUS=$(aws ses get-identity-verification-attributes \
    --identities "$SES_SENDER" \
    --region "$REGION" \
    --query "VerificationAttributes.\"$SES_SENDER\".VerificationStatus" \
    --output text 2>/dev/null || echo "UNKNOWN")
  echo "  $SES_SENDER → $STATUS"
  if [ "$STATUS" != "Success" ]; then
    echo "  WARNING: SES sender not verified. Emails will not be delivered."
    echo "  Run: aws ses verify-email-identity --email-address $SES_SENDER --region $REGION"
  fi
else
  echo "  SES_SENDER_EMAIL not set — email delivery will be disabled."
  echo "  Set it in .env to enable automatic OTP emails."
fi

echo ""
echo "Setup complete. Agent delivery system ready."
echo "Open the PatronAI dashboard → Settings → Deploy Agents to generate packages."
