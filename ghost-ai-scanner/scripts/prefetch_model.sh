#!/usr/bin/env bash
# =============================================================
# FILE: scripts/prefetch_model.sh
# VERSION: 1.0.0
# UPDATED: 2026-05-02
# OWNER: Giggso Inc
# PURPOSE: Pre-download the chat LLM model into the named Docker
#          volume BEFORE `docker compose up` starts the main
#          container. Without this, llama-server downloads the
#          model on first boot — ~3-5 min during which the chat
#          panel returns "LLM unreachable".
#
#          Idempotent: skips if a .gguf already exists in the
#          volume. Uses a one-shot llama-cli container (same
#          image as the runtime) so the download path is identical
#          to production — guarantees the model llama-server picks
#          on startup is the one we just placed.
#
# USAGE:   bash scripts/prefetch_model.sh
#          (called automatically by scripts/start.sh and
#           scripts/setup.sh; safe to call standalone any time.)
#
# REQUIRES:
#   - Docker daemon running.
#   - The patronai-scanner image built (compose builds it if missing).
#   - The patronai_patronai-models named volume (compose creates it
#     on first up; this script creates it explicitly if absent).
# =============================================================

set -euo pipefail

# ── Colours ───────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✓${NC} $1"; }
warn() { echo -e "${YELLOW}!${NC} $1"; }
info() { echo -e "${BLUE}→${NC} $1"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_DIR="${COMPOSE_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}"
cd "$COMPOSE_DIR"

# Project name controls the volume name. Compose uses the directory
# name unless overridden via COMPOSE_PROJECT_NAME or `-p`. We probe
# both common forms so this works regardless of how the operator
# invokes compose.
PROJECT_NAME="${COMPOSE_PROJECT_NAME:-$(basename "$COMPOSE_DIR")}"
VOLUME_CANDIDATES=(
    "${PROJECT_NAME}_patronai-models"   # compose default form
    "patronai-models"                    # bare name (legacy)
)

# Pick the first volume that already exists, else create the default.
VOLUME=""
for v in "${VOLUME_CANDIDATES[@]}"; do
    if docker volume inspect "$v" >/dev/null 2>&1; then
        VOLUME="$v"
        break
    fi
done
if [ -z "$VOLUME" ]; then
    VOLUME="${VOLUME_CANDIDATES[0]}"
    info "Creating named volume $VOLUME"
    docker volume create "$VOLUME" >/dev/null
fi

# Resolve the model repo from .env (or fall back to the default we
# baked into main.py). Don't `source .env` — it can have unquoted
# spaces that bash treats as commands. Just grep the line.
HF_REPO=$(grep -E '^LLM_MODEL_REPO=' .env 2>/dev/null | head -1 \
            | cut -d= -f2- | tr -d '"' || echo "")
HF_REPO="${HF_REPO:-LiquidAI/LFM2.5-1.2B-Thinking-GGUF}"

# ── Skip if a .gguf is already present in the volume ─────────
EXISTING=$(docker run --rm -v "$VOLUME":/models alpine \
    sh -c 'ls /models/*.gguf 2>/dev/null || true' 2>/dev/null | head -1)
if [ -n "$EXISTING" ]; then
    SIZE=$(docker run --rm -v "$VOLUME":/models alpine \
        sh -c "du -h '$EXISTING' 2>/dev/null | cut -f1" 2>/dev/null || echo "?")
    ok "Model already present in $VOLUME: $(basename "$EXISTING") ($SIZE) — skipping download"
    exit 0
fi

# ── Build the patronai-scanner image if missing ─────────────
IMAGE="${PROJECT_NAME}-scanner"
if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
    info "Image $IMAGE not built yet — running 'docker compose build scanner' first"
    docker compose build scanner 2>&1 | tail -3
fi

# ── Trigger the download via a one-shot llama-cli ───────────
# llama-cli with --hf-repo downloads the GGUF into LLAMA_CACHE
# (which we set to /models = the named volume) and runs a single
# token prediction to confirm load succeeded. Then exits.
info "Downloading $HF_REPO into volume $VOLUME (one-time, ~750 MB)..."
info "This usually takes 3-5 min on a typical EC2 connection."
docker run --rm \
    -v "$VOLUME":/models \
    -e LLAMA_CACHE=/models \
    "$IMAGE" \
    llama-cli --hf-repo "$HF_REPO" \
              --predict 1 -p "ok" \
              --log-disable 2>&1 | tail -10 || {
    warn "llama-cli prefetch returned non-zero — model may still have downloaded."
    warn "Verify with: docker run --rm -v $VOLUME:/models alpine ls -la /models"
}

# ── Confirm ─────────────────────────────────────────────────
DOWNLOADED=$(docker run --rm -v "$VOLUME":/models alpine \
    sh -c 'ls /models/*.gguf 2>/dev/null || true' 2>/dev/null | head -1)
if [ -n "$DOWNLOADED" ]; then
    SIZE=$(docker run --rm -v "$VOLUME":/models alpine \
        sh -c "du -h '$DOWNLOADED' 2>/dev/null | cut -f1" 2>/dev/null || echo "?")
    ok "Model ready: $(basename "$DOWNLOADED") ($SIZE) in volume $VOLUME"
    ok "Next: bash scripts/start.sh   (chat will be available immediately)"
else
    warn "No .gguf found in $VOLUME after download attempt."
    warn "Falling back to runtime download — chat will be unavailable for"
    warn "~3-5 min after 'docker compose up'."
    exit 1
fi
