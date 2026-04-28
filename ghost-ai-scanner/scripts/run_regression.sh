#!/usr/bin/env bash
# =============================================================
# FILE: scripts/run_regression.sh
# PROJECT: PatronAI
# VERSION: 1.1.0
# UPDATED: 2026-04-18
# OWNER: Giggso Inc
# PURPOSE: Full regression test suite against LocalStack.
#          Starts LocalStack if not running, runs all unit and
#          integration tests, generates an HTML report, prints
#          a clean pass/fail summary.
# USAGE:
#   bash scripts/run_regression.sh
#   bash scripts/run_regression.sh --keep-localstack
#   bash scripts/run_regression.sh --unit-only
#   bash scripts/run_regression.sh --no-docker-build
# OUTPUT:
#   reports/regression-YYYY-MM-DD-HHMMSS.html
# =============================================================

set -euo pipefail

# ── Args ──────────────────────────────────────────────────────
KEEP_LOCALSTACK=false
UNIT_ONLY=false
NO_DOCKER_BUILD=false
for arg in "$@"; do
    case $arg in
        --keep-localstack) KEEP_LOCALSTACK=true ;;
        --unit-only)       UNIT_ONLY=true ;;
        --no-docker-build) NO_DOCKER_BUILD=true ;;
    esac
done

# ── Paths ─────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPORT_DIR="$REPO_DIR/reports"
TIMESTAMP=$(date +%Y-%m-%d-%H%M%S)
DATE_HUMAN=$(date '+%Y-%m-%d %H:%M:%S')
REPORT_FILE="$REPORT_DIR/regression-${TIMESTAMP}.html"
UNIT_LOG="/tmp/marauder-unit-${TIMESTAMP}.log"
INTG_LOG="/tmp/marauder-intg-${TIMESTAMP}.log"
LOCALSTACK_PORT=4566
LOCALSTACK_CONTAINER="marauder-scan-localstack-test"

# ── Colours ───────────────────────────────────────────────────
GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✓${NC} $1"; }
fail() { echo -e "${RED}✗${NC} $1"; }
info() { echo -e "${BLUE}→${NC} $1"; }
warn() { echo -e "${YELLOW}!${NC} $1"; }
hr()   { echo -e "${BOLD}──────────────────────────────────────────${NC}"; }

# ── Banner ────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}=============================================="
echo "  PatronAI — Regression Test Suite"
echo "  $DATE_HUMAN"
echo -e "==============================================${NC}"
echo ""

# ── Prerequisites ─────────────────────────────────────────────
info "Checking prerequisites..."
MISSING=0
command -v python3 >/dev/null 2>&1 || { fail "python3 not found"; MISSING=1; }
command -v pytest  >/dev/null 2>&1 || { fail "pytest not found — pip install pytest"; MISSING=1; }
command -v docker  >/dev/null 2>&1 || { fail "docker not found"; MISSING=1; }
command -v aws     >/dev/null 2>&1 || { fail "aws cli not found"; MISSING=1; }
[ $MISSING -eq 1 ] && { fail "Missing prerequisites. Aborting."; exit 1; }
ok "All prerequisites found"

mkdir -p "$REPORT_DIR"
cd "$REPO_DIR"

# ── LocalStack ────────────────────────────────────────────────
info "Checking LocalStack..."
LOCALSTACK_STARTED_BY_US=false

if curl -sf "http://localhost:${LOCALSTACK_PORT}/_localstack/health" >/dev/null 2>&1; then
    ok "LocalStack already running on port ${LOCALSTACK_PORT}"
else
    info "Starting LocalStack..."
    docker run -d \
        --name "$LOCALSTACK_CONTAINER" \
        --rm \
        -p "${LOCALSTACK_PORT}:4566" \
        -e SERVICES=s3,sns,ec2,cloudtrail \
        -e DEFAULT_REGION=us-east-1 \
        -e DEBUG=0 \
        localstack/localstack:3.4 >/dev/null 2>&1
    LOCALSTACK_STARTED_BY_US=true

    info "Waiting for LocalStack..."
    RETRIES=0
    until curl -sf "http://localhost:${LOCALSTACK_PORT}/_localstack/health" >/dev/null 2>&1; do
        RETRIES=$((RETRIES + 1))
        [ $RETRIES -gt 40 ] && { fail "LocalStack failed to start after 40s"; exit 1; }
        sleep 1
        echo -n "."
    done
    echo ""
    ok "LocalStack ready"
fi

# ── Environment ───────────────────────────────────────────────
export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test
export AWS_DEFAULT_REGION=us-east-1
export AWS_ENDPOINT_URL="http://localhost:${LOCALSTACK_PORT}"
export MARAUDER_SCAN_BUCKET=marauder-scan-test
export PYTHONPATH="$REPO_DIR/src:$REPO_DIR"

# ── Unit tests ────────────────────────────────────────────────
echo ""
hr; info "Running unit tests..."; hr
UNIT_EXIT=0
python3 -m pytest tests/unit/ --tb=short -v 2>&1 | tee "$UNIT_LOG" || UNIT_EXIT=$?
[ $UNIT_EXIT -eq 0 ] && ok "Unit tests passed" || fail "Unit tests had failures"

# ── Integration tests ─────────────────────────────────────────
INTG_EXIT=0
if [ "$UNIT_ONLY" = false ]; then
    echo ""
    hr; info "Running integration tests..."; hr
    python3 -m pytest tests/integration/ --tb=short -v 2>&1 | tee "$INTG_LOG" || INTG_EXIT=$?
    [ $INTG_EXIT -eq 0 ] && ok "Integration tests passed" || fail "Integration tests had failures"
else
    echo "skipped -- unit-only mode" > "$INTG_LOG"
    warn "Integration tests skipped (--unit-only)"
fi

# ── Docker build check ────────────────────────────────────────
DOCKER_EXIT=0
if [ "$NO_DOCKER_BUILD" = false ]; then
    echo ""
    hr; info "Docker build check..."; hr
    if docker build -q -t marauder-scan-test-build . >/tmp/marauder-docker-"${TIMESTAMP}".log 2>&1; then
        ok "Docker build succeeded"
        docker rmi marauder-scan-test-build -f >/dev/null 2>&1 || true
    else
        fail "Docker build failed — check /tmp/marauder-docker-${TIMESTAMP}.log"
        DOCKER_EXIT=1
    fi
else
    warn "Docker build skipped (--no-docker-build)"
fi

# ── Parse results ─────────────────────────────────────────────
parse_counts() {
    local log="$1"
    local p f e
    p=$(grep -oP '\d+(?= passed)' "$log" 2>/dev/null | head -1 || echo 0)
    f=$(grep -oP '\d+(?= failed)' "$log" 2>/dev/null | head -1 || echo 0)
    e=$(grep -oP '\d+(?= error)'  "$log" 2>/dev/null | head -1 || echo 0)
    echo "${p:-0} ${f:-0} ${e:-0}"
}

read -r UNIT_PASS UNIT_FAIL UNIT_ERR  <<< "$(parse_counts "$UNIT_LOG")"
read -r INTG_PASS INTG_FAIL INTG_ERR  <<< "$(parse_counts "$INTG_LOG")"

TOTAL_PASS=$(( UNIT_PASS + INTG_PASS ))
TOTAL_FAIL=$(( UNIT_FAIL + INTG_FAIL + UNIT_ERR + INTG_ERR ))
UNIT_TOTAL=$(( UNIT_PASS + UNIT_FAIL + UNIT_ERR ))
INTG_TOTAL=$(( INTG_PASS + INTG_FAIL + INTG_ERR ))
OVERALL_EXIT=$(( UNIT_EXIT + INTG_EXIT + DOCKER_EXIT ))

if [ $OVERALL_EXIT -eq 0 ]; then
    STATUS_LABEL="PASSED"; STATUS_COLOUR="#3FB950"
else
    STATUS_LABEL="FAILED"; STATUS_COLOUR="#F85149"
fi

if [ "$NO_DOCKER_BUILD" = true ]; then
    DOCKER_BADGE="SKIPPED"; DOCKER_COL="#8B949E"
elif [ $DOCKER_EXIT -eq 0 ]; then
    DOCKER_BADGE="PASSED";  DOCKER_COL="#3FB950"
else
    DOCKER_BADGE="FAILED";  DOCKER_COL="#F85149"
fi

# ── HTML report via Python ────────────────────────────────────
info "Generating HTML report..."

python3 - \
    "$UNIT_LOG" "$INTG_LOG" \
    "$UNIT_PASS" "$UNIT_FAIL" "$UNIT_TOTAL" \
    "$INTG_PASS" "$INTG_FAIL" "$INTG_TOTAL" \
    "$TOTAL_PASS" "$TOTAL_FAIL" \
    "$STATUS_LABEL" "$STATUS_COLOUR" \
    "$DOCKER_BADGE" "$DOCKER_COL" \
    "$DATE_HUMAN" "$MARAUDER_SCAN_BUCKET" \
    "$REPORT_FILE" << 'PYEOF'
import sys

unit_log_f, intg_log_f = sys.argv[1], sys.argv[2]
unit_pass,  unit_fail,  unit_total  = int(sys.argv[3]),  int(sys.argv[4]),  int(sys.argv[5])
intg_pass,  intg_fail,  intg_total  = int(sys.argv[6]),  int(sys.argv[7]),  int(sys.argv[8])
total_pass, total_fail              = int(sys.argv[9]),  int(sys.argv[10])
status,     colour                  = sys.argv[11],      sys.argv[12]
docker_badge, docker_col            = sys.argv[13],      sys.argv[14]
timestamp,  bucket,     report      = sys.argv[15],      sys.argv[16],      sys.argv[17]

with open(unit_log_f)  as f: unit_log  = f.read()
with open(intg_log_f)  as f: intg_log  = f.read()

def esc(s): return s.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

def colour_lines(text):
    out = []
    for line in text.split("\n"):
        e = esc(line)
        if " PASSED" in line:        out.append(f'<span class="lpass">{e}</span>')
        elif " FAILED" in line or " ERROR" in line: out.append(f'<span class="lfail">{e}</span>')
        elif "passed" in line and "==" in line:     out.append(f'<span class="lpass">{e}</span>')
        elif "failed" in line and "==" in line:     out.append(f'<span class="lfail">{e}</span>')
        elif "WARN" in line:         out.append(f'<span class="lwarn">{e}</span>')
        else:                        out.append(e)
    return "\n".join(out)

ub = "badge-pass" if unit_fail == 0 else "badge-fail"
ib = "badge-pass" if intg_fail == 0 else ("badge-skip" if intg_total == 0 else "badge-fail")
db = {"PASSED":"badge-pass","FAILED":"badge-fail","SKIPPED":"badge-skip"}.get(docker_badge,"badge-skip")

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PatronAI — Regression Report {timestamp}</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&family=DM+Sans:wght@400;500;600&display=swap');
*{{margin:0;padding:0;box-sizing:border-box;}}
body{{background:#0D1117;color:#C9D1D9;font-family:'DM Sans',sans-serif;font-size:14px;line-height:1.6;padding:40px 32px;max-width:1200px;margin:0 auto;}}
.header{{border-bottom:1px solid #21262D;padding-bottom:28px;margin-bottom:32px;}}
.eyebrow{{font-family:'JetBrains Mono',monospace;font-size:10px;letter-spacing:0.16em;text-transform:uppercase;color:#58A6FF;margin-bottom:10px;}}
.title{{font-size:28px;font-weight:600;color:#E6EDF3;margin-bottom:6px;}}
.meta{{font-family:'JetBrains Mono',monospace;font-size:11px;color:#8B949E;margin-bottom:18px;}}
.status{{display:inline-block;padding:7px 22px;border-radius:6px;font-family:'JetBrains Mono',monospace;font-size:14px;font-weight:700;letter-spacing:0.1em;background:{colour}22;color:{colour};border:1px solid {colour}55;}}
.grid{{display:grid;grid-template-columns:repeat(5,1fr);gap:14px;margin:28px 0;}}
.card{{background:#161B22;border:1px solid #21262D;border-radius:8px;padding:18px 20px;}}
.clabel{{font-family:'JetBrains Mono',monospace;font-size:9px;letter-spacing:0.14em;text-transform:uppercase;color:#8B949E;margin-bottom:8px;}}
.cval{{font-family:'JetBrains Mono',monospace;font-size:26px;font-weight:700;}}
.green{{color:#3FB950;}} .red{{color:#F85149;}} .blue{{color:#58A6FF;}} .muted{{color:#8B949E;font-size:16px;}}
.section{{background:#161B22;border:1px solid #21262D;border-radius:10px;margin-bottom:20px;overflow:hidden;}}
.sec-hdr{{padding:12px 20px;border-bottom:1px solid #21262D;display:flex;align-items:center;justify-content:space-between;gap:12px;}}
.sec-title{{font-family:'JetBrains Mono',monospace;font-size:10px;letter-spacing:0.12em;text-transform:uppercase;color:#8B949E;}}
.badge{{font-family:'JetBrains Mono',monospace;font-size:10px;font-weight:700;padding:3px 10px;border-radius:4px;letter-spacing:0.06em;white-space:nowrap;}}
.badge-pass{{background:#3FB95022;color:#3FB950;border:1px solid #3FB95044;}}
.badge-fail{{background:#F8514922;color:#F85149;border:1px solid #F8514944;}}
.badge-skip{{background:#8B949E22;color:#8B949E;border:1px solid #8B949E44;}}
pre{{padding:20px 22px;font-family:'JetBrains Mono',monospace;font-size:11px;line-height:1.8;overflow-x:auto;white-space:pre-wrap;word-break:break-word;max-height:520px;overflow-y:auto;}}
.lpass{{color:#3FB950;}} .lfail{{color:#F85149;}} .lwarn{{color:#D29922;}}
footer{{text-align:center;padding:28px 0;font-family:'JetBrains Mono',monospace;font-size:10px;color:#484F58;border-top:1px solid #21262D;margin-top:32px;letter-spacing:0.06em;}}
</style>
</head>
<body>
<div class="header">
  <div class="eyebrow">PatronAI · Regression Suite</div>
  <div class="title">Test Report</div>
  <div class="meta">Run: {esc(timestamp)} &nbsp;·&nbsp; Bucket: {esc(bucket)} &nbsp;·&nbsp; LocalStack: localhost:4566</div>
  <div class="status">{esc(status)}</div>
</div>

<div class="grid">
  <div class="card"><div class="clabel">Total Passed</div><div class="cval {'green' if total_pass > 0 else 'muted'}">{total_pass}</div></div>
  <div class="card"><div class="clabel">Total Failed</div><div class="cval {'red' if total_fail > 0 else 'green'}">{total_fail}</div></div>
  <div class="card"><div class="clabel">Unit Tests</div><div class="cval blue">{unit_pass}/{unit_total}</div></div>
  <div class="card"><div class="clabel">Integration</div><div class="cval blue">{intg_pass}/{intg_total}</div></div>
  <div class="card"><div class="clabel">Docker Build</div><div class="cval muted" style="color:{esc(docker_col)};font-size:14px;">{esc(docker_badge)}</div></div>
</div>

<div class="section">
  <div class="sec-hdr">
    <div class="sec-title">Unit Tests &nbsp;·&nbsp; normalizer · matcher · code_engine · summarizer</div>
    <div class="badge {ub}">{unit_pass} passed &nbsp; {unit_fail} failed</div>
  </div>
  <pre>{colour_lines(unit_log)}</pre>
</div>

<div class="section">
  <div class="sec-hdr">
    <div class="sec-title">Integration Tests &nbsp;·&nbsp; LocalStack · S3 · SNS · full pipeline cycle</div>
    <div class="badge {ib}">{intg_pass} passed &nbsp; {intg_fail} failed</div>
  </div>
  <pre>{colour_lines(intg_log)}</pre>
</div>

<footer>PatronAI &nbsp;·&nbsp; Giggso Inc &nbsp;·&nbsp; {esc(timestamp)}</footer>
</body>
</html>"""

with open(report, "w") as f:
    f.write(html)
print(f"Written: {report}")
PYEOF

# ── Cleanup ───────────────────────────────────────────────────
if [ "$LOCALSTACK_STARTED_BY_US" = true ] && [ "$KEEP_LOCALSTACK" = false ]; then
    docker stop "$LOCALSTACK_CONTAINER" >/dev/null 2>&1 || true
    ok "LocalStack stopped and cleaned up"
elif [ "$KEEP_LOCALSTACK" = true ]; then
    warn "LocalStack left running (--keep-localstack)"
fi

# ── Final summary ─────────────────────────────────────────────
echo ""
hr
echo -e "${BOLD}  Results${NC}"
hr
[ "$UNIT_FAIL"  -eq 0 ] \
    && ok "Unit tests:        ${UNIT_PASS}/${UNIT_TOTAL} passed" \
    || fail "Unit tests:        ${UNIT_PASS}/${UNIT_TOTAL} — ${UNIT_FAIL} FAILED"
[ "$INTG_FAIL"  -eq 0 ] \
    && ok "Integration tests: ${INTG_PASS}/${INTG_TOTAL} passed" \
    || fail "Integration tests: ${INTG_PASS}/${INTG_TOTAL} — ${INTG_FAIL} FAILED"
[ "$DOCKER_EXIT" -eq 0 ] && ok "Docker build:      ${DOCKER_BADGE}" || fail "Docker build:      ${DOCKER_BADGE}"
echo ""
echo -e "  Report → ${BLUE}${REPORT_FILE}${NC}"
echo ""

if [ $OVERALL_EXIT -ne 0 ]; then
    fail "REGRESSION FAILED — do not merge to main"
    exit 1
else
    ok "ALL TESTS PASSED — safe to merge"
    exit 0
fi
