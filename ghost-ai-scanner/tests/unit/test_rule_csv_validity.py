# =============================================================
# FILE: tests/unit/test_rule_csv_validity.py
# PROJECT: PatronAI
# VERSION: 1.0.0
# UPDATED: 2026-04-25
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Run every shipped baseline CSV through its real validator.
#          Catches a broken row (typo, bad glob, severity drift) before
#          it ships and breaks self_check_rules() at customer boot.
#          Pure data — runs without AWS / LocalStack / network.
# AUDIT LOG:
#   v1.0.0  2026-04-25  Initial. Group 2.
# =============================================================

import os
import sys
from pathlib import Path

REPO   = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from matcher.rule_model import (  # noqa: E402
    parse_csv_text, validate_rule, validate_allow_rule, validate_code_rule,
)

CONFIG = REPO / "config"

CASES = (
    ("unauthorized.csv",            validate_rule),
    ("unauthorized_custom.csv",     validate_rule),
    ("authorized.csv",              validate_allow_rule),
    ("unauthorized_code.csv",       validate_code_rule),
    ("unauthorized_code_custom.csv", validate_code_rule),
    ("authorized_code.csv",         validate_code_rule),
)


def test_every_baseline_csv_validates_clean():
    """Loop every shipped CSV; surface any invalid rows with file + line context."""
    failures: list = []
    for fname, validator in CASES:
        path = CONFIG / fname
        if not path.exists():
            continue
        raw = path.read_text(encoding="utf-8")
        clean, errors = parse_csv_text(raw, validator)
        for e in errors:
            failures.append({"file": fname, "line": e["line"], "reason": e["reason"]})
    assert not failures, f"Invalid rows in shipped CSVs:\n{failures}"


def test_baseline_deny_above_strict_min():
    """Baseline unauthorized.csv must hold > 50 valid rows so self_check_rules
    never trips at boot on a fresh install."""
    raw = (CONFIG / "unauthorized.csv").read_text(encoding="utf-8")
    clean, _ = parse_csv_text(raw, validate_rule)
    assert len(clean) >= 50, f"baseline deny only has {len(clean)} valid rows (< 50)"


def test_baseline_code_deny_has_ide_plugins():
    """Group 2.A added IDE plugin entries; verify they survived."""
    raw = (CONFIG / "unauthorized_code.csv").read_text(encoding="utf-8")
    clean, _ = parse_csv_text(raw, validate_code_rule)
    patterns = {row["pattern"] for row in clean}
    expected = {"github.copilot", "codeium.codeium", "tabnine.tabnine-vscode",
                "continue.continue", "aws.amazon-q-vscode", "com.github.copilot"}
    missing = expected - patterns
    assert not missing, f"IDE plugin patterns missing from baseline: {missing}"


def test_baseline_network_deny_has_visual_builders():
    """Group 2.A added Flowise/BuildShip/Lovable/etc to network deny baseline."""
    raw = (CONFIG / "unauthorized.csv").read_text(encoding="utf-8")
    clean, _ = parse_csv_text(raw, validate_rule)
    domains = {row["domain"] for row in clean}
    expected = {"flowiseai.com", "buildship.com", "lovable.dev",
                "bolt.new", "v0.dev", "stack-ai.com"}
    missing = expected - domains
    assert not missing, f"Visual builder domains missing from baseline: {missing}"
