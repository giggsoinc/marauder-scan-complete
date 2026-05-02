#!/usr/bin/env bash
# =============================================================
# FILE: scripts/start.sh
# VERSION: 1.0.0
# UPDATED: 2026-05-02
# OWNER: Giggso Inc
# PURPOSE: Safe wrapper around `docker compose up`.
#          Eliminates the "stale shell env shadows .env file" class
#          of bug that we hit on 2026-05-02 — where compose
#          interpolated AWS_ACCESS_KEY_ID from a shell that had
#          previously `source .env`'d an older value, instead of
#          reading the just-edited file. The container started
#          with stale credentials and STS rejected every call.
#
#          This script:
#            1. Unsets shell-exported vars that compose might
#               otherwise substitute in place of the on-disk .env.
#            2. Invokes `docker compose down` so the project state
#               is fully cleared (no cached interpolations).
#            3. Invokes `docker compose up -d --build`.
#            4. Verifies AWS credentials via STS from inside the
#               container — if STS fails, prints the actual reason
#               so the operator can act on it without rebuilding.
#
# USAGE: bash scripts/start.sh         # safe restart (default)
#        bash scripts/start.sh --no-build   # skip image rebuild
# =============================================================

set -euo pipefail

# ── Colours ───────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✓${NC} $1"; }
warn() { echo -e "${YELLOW}!${NC} $1"; }
err()  { echo -e "${RED}✗${NC} $1" >&2; exit 1; }
info() { echo -e "${BLUE}→${NC} $1"; }

# Locate the compose file. Allow override via env for non-default layouts.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_DIR="${COMPOSE_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}"
cd "$COMPOSE_DIR"

[[ -f docker-compose.yml ]] || err "docker-compose.yml not found in $COMPOSE_DIR (override with COMPOSE_DIR=...)"
[[ -f .env ]]               || err ".env not found in $COMPOSE_DIR — run scripts/setup.sh first"

# ── Step 1 — purge stale exported env that could shadow .env ──
# These are the variables that have a 1:1 ${VAR} reference in
# docker-compose.yml. If any of them is exported in the current
# shell (likely from `set -a; source .env` for diagnostics), the
# exported value wins over the freshly-edited on-disk .env.
# Unset them here so compose reads the file unambiguously.
info "Purging stale shell-exported env vars (AWS_*, GF_*, COMPANY_*, ROLLUP_*, LLM_*, etc.)"
unset \
    AWS_ACCESS_KEY_ID \
    AWS_SECRET_ACCESS_KEY \
    AWS_SESSION_TOKEN \
    AWS_REGION \
    AWS_DEFAULT_REGION \
    GF_SECURITY_ADMIN_USER \
    GF_SECURITY_ADMIN_PASSWORD \
    COMPANY_NAME \
    COMPANY_SLUG \
    ALLOWED_EMAILS \
    ADMIN_EMAILS \
    SUPPORT_EMAILS \
    ALERT_RECIPIENTS \
    ALERT_SNS_ARN \
    PATRONAI_FROM_EMAIL \
    PUBLIC_HOST \
    GRAFANA_URL \
    LLM_PROVIDER LLM_BASE_URL LLM_API_KEY LLM_MODEL LLM_MODEL_REPO \
    LLM_READ_TIMEOUT_S LLM_MAX_TOKENS \
    SES_SENDER_EMAIL SES_REGION \
    ROLLUP_HOURLY_OFFSET_MINUTES ROLLUP_INITIAL_BACKFILL_DAYS \
    CHAT_HISTORY_RETENTION_DAYS DOCS_REFRESH_INTERVAL_S \
    TRINITY_WEBHOOK_URL LOGANALYZER_WEBHOOK_URL \
    SCAN_INTERVAL_SECS DEDUP_WINDOW_MINUTES \
    CROWDSTRIKE_ENABLED CLOUD_PROVIDER \
    PATRONAI_BUCKET MARAUDER_SCAN_BUCKET 2>/dev/null || true

# ── Step 2 — clear compose project state ──────────────────────
info "Stopping any running stack (docker compose down)"
docker compose down --remove-orphans 2>&1 | sed 's/^/  /'

# ── Step 3 — start fresh ──────────────────────────────────────
BUILD_FLAG="--build"
if [[ "${1:-}" == "--no-build" ]]; then
    BUILD_FLAG=""
    warn "--no-build: reusing existing image (skip if you changed code or requirements.txt)"
fi
info "Starting stack: docker compose up -d $BUILD_FLAG"
# shellcheck disable=SC2086
docker compose up -d $BUILD_FLAG 2>&1 | sed 's/^/  /'

# ── Step 3b — pre-fetch the LLM model into the named volume ──
# Idempotent: skips if a .gguf already exists in the volume. On first
# deploy this avoids the 3-5 min "LLM unreachable" window users see
# while llama-server downloads the model in the background.
if [ -x "$SCRIPT_DIR/prefetch_model.sh" ]; then
    info "Ensuring chat LLM model is present (prefetch_model.sh)"
    bash "$SCRIPT_DIR/prefetch_model.sh" || \
        warn "Model prefetch returned non-zero — chat may take ~3-5 min to be available."
fi

# ── Step 4 — verify creds the same way that bit us last time ──
info "Waiting 10s for the container to come up..."
sleep 10

info "Verifying AWS credentials inside the container..."
STS_OUT=$(docker exec patronai python3 -c "
import boto3
try:
    r = boto3.client('sts').get_caller_identity()
    print('OK', r['Arn'])
except Exception as e:
    print('FAIL', type(e).__name__, str(e)[:200])
" 2>&1 || echo "FAIL (docker exec failed: container not ready?)")

case "$STS_OUT" in
    "OK "*)
        ok "STS check passed: ${STS_OUT:3}"
        ;;
    *"InvalidClientTokenId"*)
        warn "STS says: $STS_OUT"
        warn "→ The access key ID in .env is unknown to AWS."
        warn "  Likely: key was deleted/rotated since .env was last edited."
        warn "  Fix: mint a new key in IAM, paste both values into .env,"
        warn "       then re-run: bash scripts/start.sh"
        ;;
    *"SignatureDoesNotMatch"*)
        warn "STS says: $STS_OUT"
        warn "→ The secret in .env doesn't match the access key ID."
        warn "  Fix: re-paste both AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY"
        warn "       from the original IAM 'Create access key' download,"
        warn "       then re-run: bash scripts/start.sh"
        ;;
    *)
        warn "STS check did not pass (container may still be starting):"
        warn "  $STS_OUT"
        warn "Check logs:  docker logs -f patronai"
        ;;
esac

echo ""
ok "Done. Tail logs with:  docker logs -f patronai"
