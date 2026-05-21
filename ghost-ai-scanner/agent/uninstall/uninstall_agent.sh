#!/usr/bin/env bash
# =============================================================
# PatronAI — Agent Uninstaller (Mac / Linux)
# Removes all PatronAI hooks, schedulers, and agent files.
# Safe to run multiple times. No sudo required.
# Only removes PatronAI artifacts — nothing else is touched.
# USAGE: bash uninstall_agent.sh
# =============================================================

_info() { echo "[patronai] $*"; }
_ok()   { echo "[patronai] ✓ $*"; }

echo ""
echo "PatronAI Agent Uninstaller"
echo "=========================="
echo "This will remove the PatronAI agent from this machine."
echo "Your code and git repos are NOT affected."
echo ""
read -rp "Continue? [y/N] " CONFIRM
[[ "$CONFIRM" =~ ^[Yy]$ ]] || { echo "Aborted."; exit 0; }
echo ""

AGENT_DIR="$HOME/.patronai"

# ── 0. Notify server of uninstall (before deleting config) ───
CONFIG_FILE="$AGENT_DIR/config.json"
# Installer writes heartbeat_url (no extension); check both for safety
HB_URL_FILE="$AGENT_DIR/heartbeat_url"
[ -f "$HB_URL_FILE" ] || HB_URL_FILE="$AGENT_DIR/heartbeat_url.txt"
if [ -f "$CONFIG_FILE" ] && [ -f "$HB_URL_FILE" ]; then
  HB_URL=$(cat "$HB_URL_FILE" 2>/dev/null | tr -d '\n')
  TOKEN=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE')).get('token',''))" 2>/dev/null)
  DEVICE_UUID=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE')).get('device_uuid',''))" 2>/dev/null)
  EMAIL=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE')).get('email',''))" 2>/dev/null)
  COMPANY=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE')).get('company',''))" 2>/dev/null)
  if [ -n "$HB_URL" ] && [ -n "$TOKEN" ]; then
    PAYLOAD=$(python3 -c "
import json, platform
from datetime import datetime, timezone
print(json.dumps({
    'event_type': 'UNINSTALLED',
    'status': 'uninstalled',
    'device_id': platform.node(),
    'device_uuid': '$DEVICE_UUID',
    'email': '$EMAIL',
    'token': '$TOKEN',
    'company': '$COMPANY',
    'uninstalled_at': datetime.now(timezone.utc).isoformat(),
}))" 2>/dev/null)
    if [ -n "$PAYLOAD" ]; then
      HTTP=$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 \
             -X PUT "$HB_URL" -H 'Content-Type: application/json' -d "$PAYLOAD" 2>/dev/null)
      if [ "$HTTP" = "200" ] || [ "$HTTP" = "204" ]; then
        _ok "Server notified of uninstall."
      else
        _info "Could not notify server (non-fatal) - continuing uninstall."
      fi
    fi
  fi
fi

# ── 1. Stop and remove launchd jobs — Mac only ───────────────
if [ "$(uname -s)" = "Darwin" ]; then
  for LABEL in com.patronai.heartbeat com.patronai.scan; do
    PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"
    if [ -f "$PLIST" ]; then
      launchctl unload "$PLIST" 2>/dev/null || true
      rm -f "$PLIST"
      _ok "Removed launchd job: $LABEL"
    fi
  done
fi

# ── 2. Remove crontab entries — Linux only ───────────────────
if [ "$(uname -s)" != "Darwin" ]; then
  if crontab -l 2>/dev/null | grep -q patronai; then
    crontab -l 2>/dev/null | grep -v patronai | crontab -
    _ok "Removed crontab entries"
  fi
fi

# ── 3. Remove git pre-commit hooks (only if they point to patronai) ──
HOOK_SCRIPT="$AGENT_DIR/pre_commit_hook.sh"
REMOVED=0
while IFS= read -r -d '' GIT_DIR; do
  HOOK_PATH="$GIT_DIR/hooks/pre-commit"

  # Case A: symlink pointing to our hook script
  if [ -L "$HOOK_PATH" ] && [ "$(readlink "$HOOK_PATH")" = "$HOOK_SCRIPT" ]; then
    rm "$HOOK_PATH"
  # Case B: regular file containing patronai reference
  elif [ -f "$HOOK_PATH" ] && grep -q "patronai" "$HOOK_PATH" 2>/dev/null; then
    rm "$HOOK_PATH"
  else
    continue
  fi

  # Restore original hook backup if it exists
  if [ -f "${HOOK_PATH}.pre-patronai-backup" ]; then
    mv "${HOOK_PATH}.pre-patronai-backup" "$HOOK_PATH"
    _ok "Restored original hook in: $(dirname "$GIT_DIR")"
  elif [ -f "${HOOK_PATH}.backup" ]; then
    mv "${HOOK_PATH}.backup" "$HOOK_PATH"
    _ok "Restored original hook in: $(dirname "$GIT_DIR")"
  else
    _ok "Removed hook from: $(dirname "$GIT_DIR")"
  fi
  REMOVED=$((REMOVED + 1))
done < <(find "$HOME" -maxdepth 6 -name ".git" -type d -print0 2>/dev/null)
_info "Hooks removed from $REMOVED repositories."

# ── 4. Unwire git template dir (only if it points to patronai) ──
TPL=$(git config --global --get init.templateDir 2>/dev/null || echo "")
if [ "$TPL" = "$AGENT_DIR/git-template" ]; then
  git config --global --unset init.templateDir 2>/dev/null || true
  _ok "Cleared init.templateDir (was $TPL)"
elif [ -n "$TPL" ]; then
  EXP="${TPL/#~/$HOME}"
  # Only remove if the hook in the external templateDir is ours
  if [ -L "$EXP/hooks/pre-commit" ] && \
     [ "$(readlink "$EXP/hooks/pre-commit" 2>/dev/null)" = "$HOOK_SCRIPT" ]; then
    rm -f "$EXP/hooks/pre-commit"
    _ok "Removed PatronAI hook from external templateDir ($TPL)"
  elif [ -f "$EXP/hooks/pre-commit" ] && grep -q "patronai" "$EXP/hooks/pre-commit" 2>/dev/null; then
    rm -f "$EXP/hooks/pre-commit"
    _ok "Removed PatronAI hook from external templateDir ($TPL)"
  fi
fi

# ── 5. Remove agent directory ─────────────────────────────────
if [ -d "$AGENT_DIR" ]; then
  rm -rf "$AGENT_DIR"
  _ok "Removed $AGENT_DIR"
fi

echo ""
_info "Uninstall complete. No agent files remain on this machine."
_info "To deregister from the server, ask your admin to delete your entry in:"
_info "  Settings → Deploy Agents → Delete button on your row."
