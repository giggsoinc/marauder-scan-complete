# =============================================================
# FILE: tests/unit/test_drill_panel.py
# PROJECT: PatronAI — Mega-PR (drill-down everywhere)
# VERSION: 1.0.0
# UPDATED: 2026-04-27
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Lock the drill-down state contract:
#          - apply_drill is pure (no Streamlit import)
#          - set_drill / get_drill / clear_drill round-trip via
#            session_state with the documented panel_key prefix
#          - has_drill matches set/clear lifecycle
#          - apply_drill returns input unchanged for empty drill / bad field
# AUDIT LOG:
#   v1.0.0  2026-04-27  Initial. Mega-PR.
# =============================================================

import sys
import types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "dashboard"))


@pytest.fixture
def fake_streamlit(monkeypatch):
    """Inject a stub `streamlit` module exposing only what drill_panel
    touches at call-time: session_state (dict) and rerun (no-op)."""
    fake = types.ModuleType("streamlit")
    fake.session_state = {}
    fake.rerun = lambda: None
    monkeypatch.setitem(sys.modules, "streamlit", fake)
    yield fake


def test_apply_drill_filters_by_field_and_value():
    from ui.drill_panel import apply_drill
    events = [
        {"severity": "HIGH",   "owner": "alice"},
        {"severity": "LOW",    "owner": "bob"},
        {"severity": "HIGH",   "owner": "carol"},
    ]
    drill = {"label": "HIGH", "field": "severity", "value": "HIGH"}
    out = apply_drill(events, drill)
    assert len(out) == 2
    assert all(e["severity"] == "HIGH" for e in out)


def test_apply_drill_empty_returns_input_unchanged():
    from ui.drill_panel import apply_drill
    events = [{"x": 1}, {"x": 2}]
    assert apply_drill(events, {}) == events
    assert apply_drill(events, None) == events


def test_apply_drill_missing_field_returns_empty():
    from ui.drill_panel import apply_drill
    events = [{"severity": "HIGH"}, {"severity": "LOW"}]
    drill = {"label": "x", "field": "nonexistent", "value": "anything"}
    assert apply_drill(events, drill) == []


def test_apply_drill_blank_field_passthrough():
    from ui.drill_panel import apply_drill
    events = [{"a": 1}]
    drill = {"label": "x", "field": "", "value": 1}
    assert apply_drill(events, drill) == events


def test_set_get_clear_lifecycle(fake_streamlit):
    from ui.drill_panel import set_drill, get_drill, has_drill, clear_drill
    assert has_drill("kpi") is False
    set_drill("kpi", "Critical events", "severity", "CRITICAL")
    d = get_drill("kpi")
    assert d == {"label": "Critical events",
                 "field": "severity", "value": "CRITICAL"}
    assert has_drill("kpi") is True
    clear_drill("kpi")
    assert has_drill("kpi") is False
    assert get_drill("kpi") is None


def test_set_drill_uses_panel_key_prefix(fake_streamlit):
    from ui.drill_panel import set_drill
    set_drill("exec_kpis", "X", "owner", "alice")
    # Per docstring: stored at "drill_<panel_key>"
    assert "drill_exec_kpis" in fake_streamlit.session_state
    assert fake_streamlit.session_state["drill_exec_kpis"]["value"] == "alice"


def test_multiple_panels_dont_clobber(fake_streamlit):
    from ui.drill_panel import set_drill, get_drill
    set_drill("a", "A", "f", 1)
    set_drill("b", "B", "f", 2)
    assert get_drill("a")["value"] == 1
    assert get_drill("b")["value"] == 2


def test_get_drill_outside_streamlit_returns_none(monkeypatch):
    # Force ImportError when drill_panel tries `import streamlit`
    monkeypatch.setitem(sys.modules, "streamlit", None)
    from ui import drill_panel
    # Reload so the lazy-import path inside get_drill hits the patched module
    import importlib
    importlib.reload(drill_panel)
    assert drill_panel.get_drill("anything") is None
