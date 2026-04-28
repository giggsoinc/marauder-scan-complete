#!/usr/bin/env bash
# =============================================================
# FILE: scripts/strip_cleanup_blocks.sh
# VERSION: 1.0.0
# UPDATED: 2026-04-26
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Pre-OSS-launch razor. Removes every CLEANUP-PHASE-* sentinel
#          block from the repo. Deletes legacy skipped test files. On
#          --final, also deletes codecleanup.md and itself.
#          Idempotent: running twice is safe (matches nothing the second time).
# DEPENDS: bash, sed, grep, find, awk
# AUDIT LOG:
#   v1.0.0  2026-04-26  Initial. Phase 1A discipline.
# =============================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FINAL=0
[[ "${1:-}" == "--final" ]] && FINAL=1

cd "$REPO_ROOT"

# Find all files containing any CLEANUP-PHASE- sentinel.
# Portable across bash 3.2 (macOS default) and 4+ (Linux). No mapfile.
FILES=()
while IFS= read -r line; do
  [[ -n "$line" ]] && FILES+=("$line")
done < <(grep -rl "CLEANUP-PHASE-" \
  --exclude="strip_cleanup_blocks.sh" \
  --exclude="codecleanup.md" \
  --exclude-dir=".git" \
  --exclude-dir="node_modules" \
  --exclude-dir=".venv" 2>/dev/null || true)

if [[ ${#FILES[@]} -eq 0 ]]; then
  echo "No CLEANUP-PHASE- sentinels found. Repo is clean."
  if [[ $FINAL -eq 1 ]]; then
    rm -f codecleanup.md
    rm -f "${BASH_SOURCE[0]}"
    echo "Deleted codecleanup.md and the razor script (--final passed)."
  fi
  exit 0
fi

echo "Found ${#FILES[@]} file(s) with sentinels:"
printf '  %s\n' "${FILES[@]}"
echo

if [[ $FINAL -eq 0 ]]; then
  echo "DRY RUN — re-run with --final to actually strip + delete."
  echo "Sentinel pairs that would be removed (per-file count):"
  for f in "${FILES[@]}"; do
    count=$(grep -c "BEGIN CLEANUP-PHASE-" "$f" 2>/dev/null || echo 0)
    echo "  $count  $f"
  done
  exit 0
fi

# --final: actually strip the blocks.
for f in "${FILES[@]}"; do
  # Use awk to drop every BEGIN..END inclusive block, in-place.
  awk '
    /# === BEGIN CLEANUP-PHASE-/ { skip=1; next }
    /# === END CLEANUP-PHASE-/   { skip=0; next }
    !skip
  ' "$f" > "$f.tmp" && mv "$f.tmp" "$f"
  echo "stripped: $f"
done

# Delete legacy skipped tests (any file marked whole-file in codecleanup.md).
# Whole-file removals are recorded under "Whole-file removal" section.
WHOLE_FILE_DELETE=$(awk '
  /^### Whole-file removal/ { in_section=1; next }
  /^##/                      { in_section=0 }
  in_section && /^\| `[^`]+`/ {
    match($0, /`[^`]+`/); print substr($0, RSTART+1, RLENGTH-2)
  }
' codecleanup.md 2>/dev/null || true)

if [[ -n "$WHOLE_FILE_DELETE" ]]; then
  echo "Deleting whole-file removals listed in codecleanup.md:"
  while IFS= read -r path; do
    [[ -z "$path" ]] && continue
    if [[ -f "$path" ]]; then
      rm -f "$path"
      echo "  removed: $path"
    fi
  done <<< "$WHOLE_FILE_DELETE"
fi

# Final cleanup: delete the MD and the razor itself.
rm -f codecleanup.md
echo "deleted: codecleanup.md"
rm -f "${BASH_SOURCE[0]}"
echo "deleted: scripts/strip_cleanup_blocks.sh"
echo
echo "Razor complete. Repo is OSS-ready."
