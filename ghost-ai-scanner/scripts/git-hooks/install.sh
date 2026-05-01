#!/usr/bin/env bash
# =============================================================
# FILE: scripts/git-hooks/install.sh
# PURPOSE: Symlink the pre-commit hook into .git/hooks/.
#          Each developer runs this once after cloning. It's separate
#          from .git/hooks/ because git doesn't track that directory,
#          so the hook content lives in scripts/git-hooks/ where it CAN
#          be tracked + reviewed.
# USAGE: bash scripts/git-hooks/install.sh
# =============================================================

set -e

REPO_ROOT="$(git rev-parse --show-toplevel)"
HOOK_SOURCE="$REPO_ROOT/ghost-ai-scanner/scripts/git-hooks/pre-commit"
HOOK_DEST="$REPO_ROOT/.git/hooks/pre-commit"

# Some repos place ghost-ai-scanner at the root.
if [ ! -f "$HOOK_SOURCE" ]; then
    HOOK_SOURCE="$REPO_ROOT/scripts/git-hooks/pre-commit"
fi

if [ ! -f "$HOOK_SOURCE" ]; then
    echo "ERROR: cannot find pre-commit hook source at:"
    echo "  $REPO_ROOT/ghost-ai-scanner/scripts/git-hooks/pre-commit"
    echo "  $REPO_ROOT/scripts/git-hooks/pre-commit"
    exit 1
fi

if [ -e "$HOOK_DEST" ] && [ ! -L "$HOOK_DEST" ]; then
    echo "WARN: $HOOK_DEST already exists and is not a symlink."
    echo "      Backing it up to ${HOOK_DEST}.backup-$(date +%s)"
    mv "$HOOK_DEST" "${HOOK_DEST}.backup-$(date +%s)"
fi

ln -sf "$HOOK_SOURCE" "$HOOK_DEST"
chmod +x "$HOOK_SOURCE"
echo "Installed pre-commit hook:"
echo "  $HOOK_DEST -> $HOOK_SOURCE"

# Self-test: try the hook against an empty staging area (should pass).
if "$HOOK_SOURCE" >/dev/null; then
    echo "Self-test: PASS (hook runs cleanly with empty staging area)"
else
    echo "Self-test: FAIL (hook returned non-zero on empty staging — investigate)"
    exit 1
fi
