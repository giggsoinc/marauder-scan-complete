# =============================================================
# FILE: dashboard/ui/reports/_header.py
# VERSION: 1.0.0
# UPDATED: 2026-04-28
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Shared HTML/CSS report primitives used by all r*.py
#          builders. wrap_html() assembles a complete HTML doc.
#          Pure functions — no Streamlit, no boto3.
# AUDIT LOG:
#   v1.0.0  2026-04-28  Initial.
# =============================================================

from datetime import datetime, timezone

_SEV_RANK = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "CLEAN": 0}

_CSS = """
*{box-sizing:border-box;margin:0;padding:0}
@page{size:A4;margin:18mm}
body{font-family:Helvetica,Arial,sans-serif;color:#1F2328;font-size:11px;line-height:1.5}
.rh{display:flex;align-items:flex-start;border-bottom:3px solid #0969DA;padding-bottom:16px;margin-bottom:24px;gap:16px}
.logo{width:68px;height:68px;object-fit:contain;flex-shrink:0}
.logo-ph{width:68px;height:68px;background:#F6F8FA;border:1px solid #D0D7DE;border-radius:4px;display:flex;align-items:center;justify-content:center;font-size:8px;color:#999;flex-shrink:0}
.ht{flex:1}
.cn{font-size:20px;font-weight:700}
.rt{font-size:14px;color:#0969DA;font-weight:600;margin-top:3px}
.rm{font-size:10px;color:#57606A;font-family:monospace;margin-top:5px;line-height:1.8}
.conf{background:#CF222E;color:white;font-size:9px;font-weight:700;padding:4px 8px;border-radius:3px;letter-spacing:1px;white-space:nowrap}
.sec{margin:18px 0}
.st{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;border-left:4px solid #0969DA;padding-left:8px;margin-bottom:8px}
.kr{display:flex;gap:10px;margin:12px 0}
.kc{flex:1;border:1px solid #D0D7DE;border-radius:6px;padding:12px;text-align:center}
.kv{font-size:26px;font-weight:700;color:#0969DA}
.kl{font-size:9px;color:#57606A;margin-top:3px;text-transform:uppercase}
.kc.crit .kv{color:#CF222E}
.kc.high .kv{color:#D1242F}
.vb{background:#FFF8C5;border:1px solid #D4A72C;border-radius:6px;padding:12px;margin:14px 0;font-size:11px}
.gb{background:#FFF1F0;border:1px solid #CF222E;border-radius:6px;padding:10px;margin:10px 0;font-size:10px}
.ok{background:#DAFBE1;border:1px solid #1A7F37;border-radius:6px;padding:10px;margin:10px 0;font-size:10px}
table{width:100%;border-collapse:collapse;font-size:10px;margin:8px 0}
th{background:#F6F8FA;font-weight:700;text-align:left;padding:5px 8px;border-bottom:2px solid #D0D7DE;white-space:nowrap}
td{padding:4px 8px;border-bottom:1px solid #F0F0F0;font-family:monospace}
tr:nth-child(even) td{background:#FAFAFA}
.sc{background:#CF222E;color:white;padding:2px 5px;border-radius:3px;font-size:9px;font-weight:700}
.sh{background:#D1242F;color:white;padding:2px 5px;border-radius:3px;font-size:9px}
.sm{background:#D4A72C;color:white;padding:2px 5px;border-radius:3px;font-size:9px}
.sl{background:#1A7F37;color:white;padding:2px 5px;border-radius:3px;font-size:9px}
.rf{border-top:1px solid #D0D7DE;margin-top:28px;padding-top:8px;font-size:9px;color:#6E7781;display:flex;justify-content:space-between}
"""


def now_utc() -> str:
    """Current UTC timestamp as YYYY-MM-DD HH:MM."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")


def sev_tag(sev: str) -> str:
    """HTML severity badge span."""
    cls = {"CRITICAL": "sc", "HIGH": "sh", "MEDIUM": "sm"}.get(
        (sev or "LOW").upper(), "sl")
    return f'<span class="{cls}">{(sev or "LOW").upper()}</span>'


def max_sev(evts: list) -> str:
    """Highest severity string across a list of events."""
    best = "LOW"
    for e in evts:
        s = (e.get("severity") or "LOW").upper()
        if _SEV_RANK.get(s, 0) > _SEV_RANK.get(best, 0):
            best = s
    return best


def filter_by_date(events: list, d_from: str, d_to: str) -> list:
    """Filter events whose timestamp[:10] falls in [d_from, d_to]."""
    if not d_from and not d_to:
        return events
    out = []
    for e in events:
        d = (e.get("timestamp") or e.get("date") or "")[:10]
        if (not d_from or d >= d_from) and (not d_to or d <= d_to):
            out.append(e)
    return out


def wrap_html(title: str, body: str, company: str, d_from: str,
              d_to: str, admin_email: str, logo_b64: str = "",
              ts: str = "") -> str:
    """Assemble a complete HTML report document."""
    ts = ts or now_utc()
    co = company or "PatronAI"
    logo = (f'<img src="data:image/png;base64,{logo_b64}" class="logo" alt="Logo">'
            if logo_b64 else '<div class="logo-ph">LOGO</div>')
    hdr = (f'<div class="rh">{logo}<div class="ht">'
           f'<div class="cn">{co}</div>'
           f'<div class="rt">{title}</div>'
           f'<div class="rm">Period: {d_from} → {d_to}<br>'
           f'Generated: {ts} UTC · By: {admin_email}</div>'
           f'</div><div class="conf">CONFIDENTIAL</div></div>')
    ftr = (f'<div class="rf"><span>PatronAI · {co}</span>'
           f'<span>CONFIDENTIAL · Do not distribute</span>'
           f'<span>Generated {ts}</span></div>')
    return (f"<!DOCTYPE html><html><head><meta charset='UTF-8'>"
            f"<style>{_CSS}</style></head><body>{hdr}{body}{ftr}</body></html>")
