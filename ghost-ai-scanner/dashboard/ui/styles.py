# =============================================================
# FILE: dashboard/ui/styles.py
# VERSION: 2.1.0
# UPDATED: 2026-04-27
# OWNER: Giggso Inc (Ravi Venugopal)
# PURPOSE: Global CSS injection for PatronAI UI — LIGHT THEME.
#          DM Sans body, JetBrains Mono labels/code.
#          Hides Streamlit chrome — hamburger, footer, deploy ribbon.
#          Color tokens mirror dashboard/ui/theme.py.
# AUDIT LOG:
#   v1.0.0  2026-04-19  Initial — extracted from ghost_dashboard.py
#   v1.1.0  2026-04-19  Sidebar contrast + radio + link styles
#   v2.0.0  2026-04-27  Light-theme flip (Mega-PR). Pure white cards
#                       on off-white page; black text; sidebar gray.
#   v2.1.0  2026-04-27  Severity badge colors: HIGH → red, MEDIUM → amber,
#                       LOW → sky-blue. Matches theme.py v1.1.0.
# =============================================================

import streamlit as st

_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;600;700&family=DM+Sans:wght@300;400;500;600&display=swap');
html,body,[class*="css"]{font-family:'DM Sans',sans-serif;background-color:#F8F9FA!important;color:#1F2328!important}
#MainMenu,footer,header{visibility:hidden}
.block-container{padding:1.2rem 2rem 2rem 2rem!important;max-width:100%!important;background-color:#F8F9FA!important}
[data-testid="stAppViewContainer"]{background-color:#F8F9FA!important}
[data-testid="stSidebar"]{background:#F1F3F5!important;border-right:1px solid #E1E4E8!important}
[data-testid="stSidebar"] *{color:#1F2328!important}
[data-testid="stRadio"] label{color:#1F2328!important;font-family:'JetBrains Mono',monospace!important;font-size:12px!important;padding:6px 0!important}
[data-testid="stRadio"] label:hover{color:#0969DA!important}
[data-testid="stRadio"] [aria-checked="true"]+div{color:#0969DA!important;font-weight:600!important}
[data-testid="stRadio"] [data-baseweb="radio"] div:first-child{border-color:#D0D7DE!important}
[aria-checked="true"] [data-baseweb="radio"] div:first-child{background:#0969DA!important;border-color:#0969DA!important}
[data-testid="stMetric"]{background:#FFFFFF;border:1px solid #E1E4E8;border-radius:8px;padding:14px 18px!important;box-shadow:0 1px 0 rgba(27,31,36,.04)}
[data-testid="stMetricLabel"]{color:#57606A!important;font-size:11px!important;letter-spacing:.08em;text-transform:uppercase;font-family:'JetBrains Mono',monospace}
[data-testid="stMetricValue"]{color:#0D1117!important;font-size:22px!important;font-weight:600;font-family:'JetBrains Mono',monospace}
[data-testid="stTabs"] button{font-family:'JetBrains Mono',monospace!important;font-size:12px!important;color:#57606A!important;letter-spacing:.06em;text-transform:uppercase;border-bottom:2px solid transparent!important}
[data-testid="stTabs"] button[aria-selected="true"]{color:#0969DA!important;border-bottom:2px solid #0969DA!important;background:transparent!important}
[data-testid="stButton"] button{background:#FFFFFF!important;border:1px solid #D0D7DE!important;color:#1F2328!important;font-family:'JetBrains Mono',monospace!important;font-size:11px!important;border-radius:6px!important;letter-spacing:.05em}
[data-testid="stButton"] button:hover{background:#F6F8FA!important;border-color:#0969DA!important;color:#0969DA!important}
[data-testid="stButton"] button[kind="primary"]{background:#0969DA!important;border-color:#0969DA!important;color:#FFFFFF!important}
table{width:100%;border-collapse:collapse;font-family:'JetBrains Mono',monospace;font-size:12px;background:#FFFFFF}
th{background:#F6F8FA;color:#57606A;font-size:10px;letter-spacing:.1em;text-transform:uppercase;padding:10px 14px;border-bottom:1px solid #E1E4E8;text-align:left;font-weight:500}
td{padding:9px 14px;border-bottom:1px solid #E1E4E8;color:#1F2328;vertical-align:middle}
tr:hover td{background:#F6F8FA}
.badge{display:inline-block;padding:2px 8px;border-radius:4px;font-size:10px;font-weight:600;letter-spacing:.08em;font-family:'JetBrains Mono',monospace}
.badge-critical{background:rgba(153,27,27,.12);color:#991B1B;border:1px solid rgba(153,27,27,.50);font-weight:700}
.badge-high{background:rgba(220,38,38,.10);color:#DC2626;border:1px solid rgba(220,38,38,.45);font-weight:700}
.badge-medium{background:rgba(217,119,6,.15);color:#D97706;border:1px solid rgba(217,119,6,.50);font-weight:600}
.badge-low{background:rgba(2,132,199,.12);color:#0284C7;border:1px solid rgba(2,132,199,.40)}
.badge-clean{background:rgba(22,163,74,.12);color:#16A34A;border:1px solid rgba(22,163,74,.35)}
.badge-unknown{background:rgba(107,114,128,.12);color:#6B7280;border:1px solid rgba(107,114,128,.30)}
.dot-green{display:inline-block;width:8px;height:8px;background:#1A7F37;border-radius:50%;animation:pulse 2s infinite;margin-right:6px}
.dot-red{display:inline-block;width:8px;height:8px;background:#B91C1C;border-radius:50%;margin-right:6px}
.card{background:#FFFFFF;border:1px solid #E1E4E8;border-radius:8px;padding:18px 20px;margin-bottom:12px;box-shadow:0 1px 0 rgba(27,31,36,.04)}
.card-title{font-family:'JetBrains Mono',monospace;font-size:10px;color:#57606A;text-transform:uppercase;letter-spacing:.1em;margin-bottom:10px}
.drill-panel{background:#FFFFFF;border:1px solid #0969DA;border-radius:8px;padding:14px 18px;margin:8px 0 16px 0;box-shadow:0 2px 6px rgba(9,105,218,.08)}
.drill-chip{display:inline-block;padding:3px 10px;border-radius:12px;font-family:'JetBrains Mono',monospace;font-size:11px;background:#DDF4FF;color:#0969DA;border:1px solid #0969DA;margin-right:6px}
hr{border:none;border-top:1px solid #E1E4E8!important;margin:16px 0!important}
[data-testid="stTextInput"] input,[data-testid="stTextArea"] textarea,[data-testid="stSelectbox"] select,[data-testid="stNumberInput"] input{background:#FFFFFF!important;border:1px solid #D0D7DE!important;color:#1F2328!important;font-family:'JetBrains Mono',monospace!important;font-size:12px!important;border-radius:6px!important}
[data-testid="stSelectbox"] div[data-baseweb="select"]{background:#FFFFFF!important;border:1px solid #D0D7DE!important;border-radius:6px!important}
[data-testid="stSelectbox"] div[data-baseweb="select"] *{color:#1F2328!important}
input::placeholder,textarea::placeholder{color:#6E7781!important}
[data-testid="stExpander"]{background:#FFFFFF!important;border:1px solid #E1E4E8!important;border-radius:8px!important}
[data-testid="stAlert"]{background:#FFFFFF!important;border:1px solid #E1E4E8!important;border-radius:6px!important;font-family:'JetBrains Mono',monospace!important;font-size:12px!important;color:#1F2328!important}
[data-testid="stDataFrame"]{background:#FFFFFF!important;border:1px solid #E1E4E8!important;border-radius:6px!important}
@keyframes pulse{0%,100%{box-shadow:0 0 0 0 rgba(26,127,55,.4)}50%{box-shadow:0 0 0 6px rgba(26,127,55,0)}}
</style>
"""


def inject() -> None:
    """Inject global CSS into the Streamlit page."""
    st.markdown(_CSS, unsafe_allow_html=True)
