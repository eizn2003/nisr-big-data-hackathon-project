"""Shared design system: tokens, global CSS, chart theme and small UI components."""

import html as _html

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# --------------------------------------------------------------------------
# Tokens
# --------------------------------------------------------------------------
PALETTE = {
    "ink": "#0E2A35",
    "ink2": "#163D4B",
    "text": "#12262F",
    "muted": "#5C707A",
    "line": "#E0E7EA",
    "grid": "#E9EFF1",
    "teal": "#1A8A7D",
    "sun": "#F2B84B",      # "selected" colour everywhere
    "coral": "#DB6A4E",
    "blue": "#2F6DB5",
    "amber": "#E0A12F",
    "white": "#FFFFFF",
}

FONT_STACK = "Plus Jakarta Sans, Segoe UI, Arial, sans-serif"

# Indicator colours, labels and wording live in src/indicators.py
from src.indicators import INDICATOR_THEME  # noqa: E402,F401

HERO_ART = (
    '<svg viewBox="0 0 600 240" preserveAspectRatio="xMaxYMax slice" '
    'width="100%" height="100%" aria-hidden="true">'
    '<circle cx="470" cy="78" r="34" fill="#F2B84B" opacity=".95"/>'
    '<path d="M0 176 C60 124 120 124 180 164 S300 194 360 144 S480 94 600 154 L600 240 L0 240Z" fill="#1A8A7D" opacity=".30"/>'
    '<path d="M0 198 C80 156 150 166 220 192 S360 208 430 172 S540 136 600 182 L600 240 L0 240Z" fill="#1A8A7D" opacity=".50"/>'
    '<path d="M0 226 C100 198 200 214 300 220 S480 204 600 220 L600 240 L0 240Z" fill="#0E2A35" opacity=".55"/>'
    "</svg>"
)

LOGO_SVG = (
    '<svg width="24" height="24" viewBox="0 0 24 24" aria-hidden="true">'
    '<circle cx="16.5" cy="7.5" r="3.2" fill="#F2B84B"/>'
    '<path d="M1 20 C5 11 9 11 12 16 C14 13 18 12 23 20Z" fill="#FFFFFF" opacity=".95"/>'
    "</svg>"
)


def esc(value) -> str:
    return _html.escape(str(value), quote=True)


def render_html(block: str) -> None:
    """Render an HTML block safely through Streamlit's markdown parser.

    Lines are stripped and joined so indentation never turns into a code block.
    """
    flat = " ".join(line.strip() for line in block.splitlines() if line.strip())
    st.markdown(flat, unsafe_allow_html=True)


# --------------------------------------------------------------------------
# Plotly theme
# --------------------------------------------------------------------------
def chart_layout(height=340, **extra):
    layout = dict(
        height=height,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FONT_STACK, color=PALETTE["text"], size=12),
        margin=dict(l=4, r=14, t=10, b=4),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.0,
            xanchor="left",
            x=0,
            bgcolor="rgba(0,0,0,0)",
            font=dict(size=12),
        ),
        hoverlabel=dict(
            bgcolor=PALETTE["ink"],
            bordercolor=PALETTE["ink"],
            font=dict(family=FONT_STACK, color="#FFFFFF", size=12),
        ),
    )
    layout.update(extra)
    return layout


def style_chart(fig, height=340, **extra):
    fig.update_layout(**chart_layout(height, **extra))
    return fig


# --------------------------------------------------------------------------
# Global CSS
# --------------------------------------------------------------------------
_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

:root{
  --bg:#F2F5F6; --surface:#FFFFFF; --ink:#0E2A35; --ink-2:#163D4B;
  --text:#12262F; --muted:#5C707A; --line:#E0E7EA;
  --teal:#1A8A7D; --teal-d:#126B61; --teal-l:#DCF0EC;
  --sun:#F2B84B; --coral:#DB6A4E; --blue:#2F6DB5;
  --shadow:0 1px 2px rgba(14,42,53,.04), 0 12px 28px -16px rgba(14,42,53,.18);
}

/* ---------- base ---------- */
html, body, .stApp, .stApp p, .stApp li, .stApp label, .stApp button,
.stApp input, .stApp textarea, .stApp h1, .stApp h2, .stApp h3, .stApp h4,
.stApp [data-testid="stMarkdownContainer"]{
  font-family:'Plus Jakarta Sans','Segoe UI',Arial,sans-serif;
}
.stApp{
  color-scheme:light;
  background:
    radial-gradient(900px 420px at 92% -8%, #DDEFEB 0%, rgba(221,239,235,0) 70%),
    var(--bg);
  color:var(--text);
}
header[data-testid="stHeader"]{background:transparent;}
.stApp [data-testid="stMarkdownContainer"], .stApp [data-testid="stWidgetLabel"],
.stApp [data-testid="stCaptionContainer"], .stApp [data-testid="stMain"] label{color:var(--text);}
div[data-baseweb="select"] *, div[data-baseweb="input"] input, [data-baseweb="popover"] li,
[data-baseweb="popover"] [role="option"]{color:var(--text);}
[data-testid="stPopoverBody"] *{color:var(--text);}
[data-testid="stDecoration"], [data-testid="stAppDeployButton"], [data-testid="stMainMenu"],
[data-testid="stToolbarActions"], #MainMenu, footer{display:none !important;}
header[data-testid="stHeader"]{z-index:999;}

/* sidebar toggle buttons: always reachable */
[data-testid="stExpandSidebarButton"], [data-testid="stSidebarCollapsedControl"],
[data-testid="collapsedControl"]{
  display:flex !important; visibility:visible !important; opacity:1 !important;
}
[data-testid="stExpandSidebarButton"], [data-testid="stSidebarCollapsedControl"] button,
[data-testid="collapsedControl"] button{
  background:var(--ink) !important; color:#fff !important; border-radius:12px !important;
  box-shadow:0 10px 22px -10px rgba(14,42,53,.6);
}
[data-testid="stExpandSidebarButton"] *, [data-testid="stSidebarCollapsedControl"] button *,
[data-testid="collapsedControl"] button *{color:#fff !important; fill:#fff !important;}
[data-testid="stSidebarCollapseButton"] button, [data-testid="stSidebarCollapseButton"] *{
  color:#B9C9D0 !important;
}
[data-testid="stSidebarCollapseButton"] button:hover{background:rgba(255,255,255,.1) !important;}
.block-container{max-width:1480px; padding:1.4rem 2.2rem 3rem;}
a{color:var(--teal);}
:focus-visible{outline:2px solid var(--sun); outline-offset:2px;}

/* ---------- sidebar ---------- */
[data-testid="stSidebar"]{
  background:
    radial-gradient(420px 260px at 0% 0%,rgba(26,138,125,.16),transparent 72%),
    linear-gradient(180deg,#102F3A 0%,#0A212A 100%);
  border-right:1px solid rgba(255,255,255,.08);
}
[data-testid="stSidebar"] .stMarkdown p{color:#B9C9D0;}
[data-testid="stSidebar"] .stButton > button{
  background:rgba(255,255,255,.06); color:#E8F0F2; border:1px solid rgba(255,255,255,.16);
}
[data-testid="stSidebar"] .stButton > button p{color:#E8F0F2;}
[data-testid="stSidebar"] .stButton > button:hover{
  background:rgba(255,255,255,.12); border-color:rgba(255,255,255,.3); color:#fff;
}
[data-testid="stSidebar"] .st-key-sidebar_navigation .stButton > button[kind="secondary"]{
  min-height:48px; justify-content:flex-start; text-align:left;
  padding:.38rem .72rem; border-radius:14px;
  border-color:rgba(255,255,255,.075);
  background:rgba(255,255,255,.035);
  box-shadow:inset 0 1px 0 rgba(255,255,255,.025);
  transition:transform .16s ease, background .16s ease, border-color .16s ease,
    box-shadow .16s ease;
}
[data-testid="stSidebar"] .st-key-sidebar_navigation .stButton > button[kind="secondary"] p{
  color:#B9C9D0; font-size:.86rem; font-weight:600; letter-spacing:.005em;
}
[data-testid="stSidebar"] .st-key-sidebar_navigation .stButton > button[kind="secondary"] [data-testid="stIconMaterial"]{
  color:#9DB6BE; font-size:19px;
}
[data-testid="stSidebar"] .st-key-sidebar_navigation .stButton > button[kind="secondary"]:hover{
  transform:translateX(2px); background:rgba(255,255,255,.085);
  border-color:rgba(255,255,255,.16);
}
[data-testid="stSidebar"] .st-key-sidebar_navigation .stButton > button[kind="primary"]{
  min-height:50px; justify-content:flex-start; text-align:left;
  padding:.38rem .72rem; border-radius:14px;
  border:1px solid rgba(106,202,183,.3); border-left:3px solid var(--sun);
  background:linear-gradient(105deg,rgba(26,138,125,.43),rgba(26,138,125,.19) 72%,rgba(242,184,75,.08));
  box-shadow:inset 0 1px 0 rgba(255,255,255,.08),0 8px 20px -16px rgba(0,0,0,.8);
  transition:transform .16s ease, filter .16s ease, box-shadow .16s ease;
}
[data-testid="stSidebar"] .st-key-sidebar_navigation .stButton > button[kind="primary"] p{
  color:#FFFFFF; font-size:.86rem; font-weight:700; letter-spacing:.005em;
}
[data-testid="stSidebar"] .st-key-sidebar_navigation .stButton > button[kind="primary"] [data-testid="stIconMaterial"]{
  color:var(--sun); font-size:20px;
}
[data-testid="stSidebar"] .st-key-sidebar_navigation .stButton > button[kind="primary"]:hover{
  filter:brightness(1.12); transform:translateX(2px);
}
[data-testid="stSidebar"] .st-key-sidebar_navigation .stButton > button:focus-visible{
  outline:2px solid var(--sun); outline-offset:2px;
}
.sb-brand{
  display:flex; gap:12px; align-items:center; padding:8px 4px 20px;
  border-bottom:1px solid rgba(255,255,255,.09); margin-bottom:8px;
}
.sb-logo{
  width:42px; height:42px; border-radius:12px; display:grid; place-items:center; flex:none;
  background:linear-gradient(145deg,#1A8A7D,#0F5C63);
  box-shadow:0 10px 24px -10px rgba(26,138,125,.95),inset 0 1px 0 rgba(255,255,255,.22);
}
.sb-name{font-family:'Fraunces',Georgia,serif; font-size:17px; font-weight:600; color:#FFFFFF !important; line-height:1.2;}
.sb-sub{font-size:12px; color:#8FA8B1 !important; margin-top:2px;}
.sb-section{
  display:flex; align-items:center; gap:9px; font-size:10px; font-weight:800;
  color:#89A5AE !important; letter-spacing:.14em; text-transform:uppercase;
  margin:16px 6px 8px;
}
.sb-section:before{
  content:""; width:7px; height:7px; border-radius:50%;
  background:var(--sun); box-shadow:0 0 12px rgba(242,184,75,.55);
}
.sb-mode-label{
  color:#89A5AE; font-size:10px; font-weight:800; letter-spacing:.14em;
  text-transform:uppercase; margin:9px 6px 7px;
}
.st-key-sidebar_mode_selector{margin:0 0 8px;}
[data-testid="stSidebar"] .st-key-sidebar_mode_selector .stButton > button{
  min-height:34px; justify-content:flex-start; text-align:left;
  padding:.28rem .72rem; border-radius:11px;
  font-size:.76rem; line-height:1.15; white-space:normal;
  transition:background .16s ease, border-color .16s ease, transform .16s ease;
}
[data-testid="stSidebar"] .st-key-sidebar_mode_selector .stButton > button[kind="secondary"]{
  color:#B9C9D0; background:rgba(255,255,255,.035);
  border-color:rgba(255,255,255,.11);
}
[data-testid="stSidebar"] .st-key-sidebar_mode_selector .stButton > button[kind="secondary"] p{
  color:#B9C9D0; font-size:.76rem; font-weight:700;
}
[data-testid="stSidebar"] .st-key-sidebar_mode_selector .stButton > button[kind="secondary"]:hover{
  transform:translateX(2px); color:#fff; background:rgba(255,255,255,.1);
  border-color:rgba(255,255,255,.25);
}
[data-testid="stSidebar"] .st-key-sidebar_mode_selector .stButton > button[kind="primary"]{
  min-height:36px; color:#fff; border:1px solid rgba(106,202,183,.4);
  border-left:3px solid var(--sun);
  background:linear-gradient(135deg,rgba(26,138,125,.78),rgba(18,107,97,.75));
  box-shadow:inset 0 1px 0 rgba(255,255,255,.12),0 6px 16px -12px rgba(0,0,0,.8);
}
[data-testid="stSidebar"] .st-key-sidebar_mode_selector .stButton > button[kind="primary"] p{
  color:#fff; font-size:.76rem; font-weight:800;
}
[data-testid="stSidebar"] .st-key-sidebar_mode_selector .stButton > button:focus-visible{
  outline:2px solid var(--sun); outline-offset:2px;
}
[data-testid="stSidebar"] .st-key-refresh_nbr_observations .stButton > button{
  min-height:34px; font-size:.75rem; background:rgba(255,255,255,.035);
  border-color:rgba(255,255,255,.12); color:#B9C9D0;
}
[data-testid="stSidebar"] .st-key-refresh_nbr_observations .stButton > button p{
  color:#B9C9D0; font-size:.75rem;
}
.sb-card, .sb-user{
  margin-top:18px; padding:14px; border-radius:14px;
  background:linear-gradient(145deg,rgba(255,255,255,.075),rgba(255,255,255,.035));
  border:1px solid rgba(255,255,255,.105); box-shadow:inset 0 1px 0 rgba(255,255,255,.04);
}
.sb-card b{color:#FFFFFF !important; font-size:13px;}
.sb-card span{display:block; font-size:12px; color:#9DB3BB !important; margin-top:4px; line-height:1.5;}
.sb-user{display:flex; gap:11px; align-items:center; margin-bottom:10px;}
.sb-avatar{
  width:36px; height:36px; border-radius:50%; flex:none; display:grid; place-items:center;
  background:linear-gradient(135deg,#F2B84B,#E0A12F); color:#0E2A35 !important; font-weight:800; font-size:14px;
}
.sb-email{font-size:12.5px; color:#E4EDF0 !important; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; max-width:180px;}
.sb-role{font-size:11.5px; color:#8FA8B1 !important;}

/* ---------- cards ---------- */
div[class*="st-key-card"]{
  background:var(--surface); border:1px solid var(--line); border-radius:18px;
  padding:22px 24px; box-shadow:var(--shadow);
}
.st-key-card_combined_finding{
  background:linear-gradient(135deg,#FFFFFF 0%,#F2F7FC 100%) !important;
  border-top:3px solid var(--blue) !important;
  box-shadow:0 16px 30px -20px rgba(14,42,53,.42) !important;
}
.st-key-nbr_context_card{
  background:var(--surface); border:1px solid var(--line); border-radius:18px;
  padding:22px 24px; box-shadow:var(--shadow); margin:14px 0;
}
.st-key-card_map{padding:0 !important; overflow:hidden;}
.st-key-card_controls{padding:14px 20px 16px;}
.st-key-card_nbr_map{padding:0 !important; overflow:hidden;}
.st-key-card_nbr_map .map-strip{padding:20px 22px 14px;}
.st-key-card_nbr_dx_map{
  padding:0 !important; overflow:hidden; border-left:0 !important;
  border-right:0 !important; border-bottom:0 !important;
  border-radius:18px 18px 0 0 !important; box-shadow:none !important;
}
.st-key-card_nbr_dx_map .map-strip{padding:20px 22px 14px;}
.st-key-card_nbr_dx_details{
  background:linear-gradient(180deg,#F0F6FA 0,#FFFFFF 190px) !important;
  padding:24px !important; min-height:700px;
}
.nbr-dx-inspector-title{
  display:flex; flex-direction:column; gap:4px; margin:0 0 4px;
  font-family:'Fraunces',Georgia,serif; font-size:22px; font-weight:600;
  color:var(--ink); letter-spacing:-.01em;
}
.nbr-dx-inspector-title span{
  font-family:'Plus Jakarta Sans',Arial,sans-serif; font-size:12px;
  font-weight:500; color:var(--muted); letter-spacing:0;
}
.st-key-card_nbr_dx_details .insp-value{font-size:52px; margin-top:20px;}
.st-key-card_nbr_dx_details .insp-value span{font-size:19px;}
.st-key-card_nbr_dx_details .insp-grid{
  grid-template-columns:repeat(2,minmax(0,1fr)); row-gap:14px;
}
.st-key-card_nbr_dx_details .insp-grid b{font-size:14px;}
.st-key-card_nbr_dx_details .insp-grid span{line-height:1.45;}
.st-key-card_nbr_dx_details .insp-note{
  margin-top:14px; border:1px solid #E1EAF0;
  background:rgba(255,255,255,.82);
}
.st-key-card_nbr_dx_controls [data-testid="stSegmentedControl"]{
  width:100%;
}
.st-key-card_nbr_dx_distribution{
  margin-top:28px; padding:28px 30px 24px !important;
  background:linear-gradient(180deg,#FFFFFF 0%,#F8FAFA 100%) !important;
}
.st-key-card_nbr_dx_distribution [data-testid="stPlotlyChart"]{
  overflow:hidden; border-radius:16px; background:#102B35;
}
.nbr-dx-distribution-legend{
  display:flex; flex-wrap:wrap; gap:10px 22px; align-items:center;
  margin:12px 0 24px; color:var(--muted); font-size:11.5px; font-weight:600;
}
.nbr-dx-distribution-legend span{display:inline-flex; align-items:center; gap:7px;}
.nbr-dx-distribution-legend i{
  display:inline-block; width:10px; height:10px; border-radius:50%;
}
.nbr-dx-distribution-legend i.selected{background:#F3D27A; box-shadow:0 0 0 3px #FFF4C7;}
.nbr-dx-distribution-legend i.higher{background:#218B83;}
.nbr-dx-distribution-legend i.lower{background:#C68755;}
.nbr-dx-distribution-legend i.other{background:#526D78;}
.nbr-dx-rank-heading{
  margin:2px 0 10px; color:var(--ink); font-size:14px; font-weight:700;
}
.nbr-dx-rank-heading span{
  display:block; margin-top:3px; color:var(--muted); font-size:11px; font-weight:500;
}
.nbr-dx-rank-list{
  display:grid; grid-template-columns:1fr; gap:5px;
}
.nbr-dx-rank-row{
  display:flex; align-items:center; justify-content:space-between; gap:10px;
  padding:8px 11px; border-radius:9px; background:#F0F4F4;
  color:#465D65; font-size:12px;
}
.nbr-dx-rank-row b{color:var(--ink); font-size:12px; white-space:nowrap;}
.nbr-dx-unknown{
  display:flex; flex-wrap:wrap; align-items:baseline; gap:4px 12px;
  margin-top:20px; padding:12px 14px; border-radius:12px;
  background:#FFF7E8; color:#684B22; font-size:12px;
}
.nbr-dx-unknown b{font-size:12px;}
.nbr-dx-unknown span{font-weight:700;}
.nbr-dx-unknown small{flex-basis:100%; color:#806A48; font-size:11px;}
.st-key-card_nbr_dx_history{
  margin-top:28px; padding:28px 30px 24px !important;
  background:linear-gradient(180deg,#FFFFFF 0%,#F7FAFA 100%) !important;
}
.st-key-card_nbr_dx_history [data-testid="stPlotlyChart"]{
  border-radius:16px; overflow:hidden;
}
.nbr-dx-history-legend{
  display:flex; flex-wrap:wrap; gap:9px 22px; align-items:center;
  margin:2px 0 20px; color:var(--muted); font-size:11.5px; font-weight:600;
}
.nbr-dx-history-legend span{display:inline-flex; align-items:center; gap:7px;}
.nbr-dx-history-legend i{
  display:inline-grid; place-items:center; width:12px; height:12px;
  border-radius:3px; font-size:12px; font-style:normal; font-weight:800;
}
.nbr-dx-history-legend i.value{background:#218B83;}
.nbr-dx-history-legend i.missing{color:#82969C; border:1px solid #AAB8BC;}
.nbr-dx-history-legend i.selected{background:#F3D27A; border:2px solid #FFF4C7;}
.nbr-dx-coverage{
  margin:4px 0 26px; padding:16px 18px; border-radius:14px;
  background:#F0F5F5;
}
.nbr-dx-coverage-title{
  margin-bottom:12px; color:var(--ink); font-size:13px; font-weight:700;
}
.nbr-dx-coverage-title span{
  display:block; margin-top:3px; color:var(--muted); font-size:11px; font-weight:500;
}
.nbr-dx-coverage-grid{
  display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr)); gap:8px;
}
.nbr-dx-coverage-item{
  display:grid; grid-template-columns:1fr auto; align-items:baseline; gap:2px 8px;
  padding:10px 11px; border-radius:10px; background:#FFFFFF;
}
.nbr-dx-coverage-item span{color:#52666E; font-size:11px; font-weight:600;}
.nbr-dx-coverage-item b{
  color:var(--ink); font-family:'Fraunces',Georgia,serif; font-size:20px;
}
.nbr-dx-coverage-item b small{
  margin-left:3px; color:var(--muted); font:500 11px 'Plus Jakarta Sans',Arial,sans-serif;
}
.nbr-dx-coverage-item em{
  grid-column:1 / -1; color:#7B6860; font-size:10px; font-style:normal;
}
.nbr-dx-incomplete{
  margin-top:12px; padding:10px 12px; border-radius:10px;
  background:#FFF7E8; color:#715323; font-size:12px;
}
.nbr-dx-incomplete b{color:#573D17;}
.nbr-dx-quality{
  display:grid; grid-template-columns:auto 1fr; gap:4px 10px;
  margin:8px 0; padding:11px 12px; border-radius:10px;
  border-left:3px solid #D5A044; background:#FFF8EB;
  color:#66522F; font-size:11.5px; line-height:1.5;
}
.nbr-dx-quality b{color:#6E4E15; white-space:nowrap;}
@media (max-width:768px){
  .st-key-card_nbr_dx_history{padding:20px 16px 18px !important;}
  .st-key-card_nbr_dx_distribution{padding:20px 16px 18px !important;}
  .nbr-dx-coverage-grid{grid-template-columns:repeat(2,minmax(0,1fr));}
}
.ct{font-family:'Fraunces',Georgia,serif; font-size:21px; font-weight:600; color:var(--ink); letter-spacing:-.01em; line-height:1.25;}
.cs{font-size:13.5px; color:var(--muted); margin-top:3px; line-height:1.5;}

/* ---------- widgets ---------- */
[data-testid="stWidgetLabel"] p{font-size:.78rem; font-weight:700; color:var(--muted);}
div[data-baseweb="select"] > div{
  background:#fff; border:1px solid var(--line); border-radius:12px; min-height:44px; box-shadow:none;
}
div[data-baseweb="select"] > div:hover{border-color:var(--teal);}
.stButton > button, .stDownloadButton > button, [data-testid="stPopover"] > button{
  border-radius:12px; min-height:44px; font-weight:600; background:#fff; color:var(--text);
  border:1px solid var(--line); transition:border-color .12s ease, color .12s ease, background .12s ease;
}
.stButton > button:hover, .stDownloadButton > button:hover, [data-testid="stPopover"] > button:hover{
  border-color:var(--teal); color:var(--teal-d); background:#F7FBFA;
}
.stButton > button[kind="primary"]{
  background:linear-gradient(135deg,#1A8A7D,#126B61); color:#fff; border:0; min-height:50px; font-size:1rem;
  box-shadow:0 14px 26px -14px rgba(26,138,125,.9);
}
.stButton > button[kind="primary"]:hover{background:linear-gradient(135deg,#1E9A8B,#146F65); color:#fff;}
[data-testid="stButtonGroup"] button{
  border-radius:999px; border:1px solid var(--line); background:#fff;
  font-weight:600; font-size:.85rem; min-height:40px; padding:0 16px;
}
[data-testid="stButtonGroup"] button p{color:var(--text);}
[data-testid="stButtonGroup"] button:hover{border-color:var(--teal);}
.stButton > button p, .stDownloadButton > button p, [data-testid="stPopover"] > button p{color:inherit;}
[data-testid="stButtonGroup"] button[data-testid="stBaseButton-segmented_controlActive"],
[data-testid="stButtonGroup"] button[aria-checked="true"]{
  background:var(--ink) !important; border-color:var(--ink) !important;
}
[data-testid="stButtonGroup"] button[data-testid="stBaseButton-segmented_controlActive"] p,
[data-testid="stButtonGroup"] button[aria-checked="true"] p{color:#fff !important;}
[data-testid="stExpander"]{border:1px solid var(--line); border-radius:14px; background:#fff;}
[data-testid="stDataFrame"]{border:1px solid var(--line); border-radius:14px; overflow:hidden;}
[data-testid="stAlert"]{border-radius:14px;}
[data-testid="stPlotlyChart"]{border-radius:12px;}

/* ---------- page header ---------- */
.stApp .pg-hero{
  position:relative; overflow:hidden; border-radius:22px; padding:34px 40px 40px; color:#fff;
  display:flex; justify-content:space-between; align-items:flex-start; gap:24px;
  background:linear-gradient(118deg,#0E2A35 0%,#12404A 58%,#17655E 100%);
}
.stApp .pg-hero.tall{padding-bottom:104px;}
.stApp .pg-hero.compact{padding:24px 32px 26px;}
.stApp .pg-hero .pg-text{position:relative; z-index:2; max-width:660px;}
.stApp .pg-hero .pg-title{
  font-family:'Fraunces',Georgia,serif; font-weight:600; font-size:clamp(28px,3vw,42px);
  line-height:1.1; letter-spacing:-.02em; margin:0 0 10px; padding:0; color:#fff;
}
.stApp .pg-hero.compact .pg-title{font-size:clamp(24px,2.4vw,32px); margin-bottom:6px;}
.stApp .pg-hero .pg-sub{color:#C5D6DB; font-size:15.5px; line-height:1.6; margin:0; max-width:58ch;}
.stApp .pg-hero .pg-intro{color:#C5D6DB; font-size:13px; line-height:1.55; margin:9px 0 0; max-width:62ch;}
.stApp .pg-hero.compact .pg-sub{font-size:14.5px;}
.pg-pill{
  position:relative; z-index:2; flex:none; display:inline-flex; gap:8px; align-items:center;
  padding:7px 13px; border-radius:999px; background:rgba(255,255,255,.10);
  border:1px solid rgba(255,255,255,.18); font-size:12.5px; font-weight:600; color:#E6F0F2;
}
.pg-pill .badge{font-size:10px; padding:2px 7px; background:rgba(255,243,214,.14); color:#FFE8AE; border-color:rgba(255,232,174,.32);}
.pg-pill i{width:7px; height:7px; border-radius:50%; background:var(--sun); display:inline-block;}
.pg-art{position:absolute; right:0; bottom:0; width:58%; height:100%; z-index:1; pointer-events:none;}
.pg-hero.compact .pg-art{width:40%; opacity:.8;}

/* ---------- KPI cards ---------- */
.kpi-grid{
  display:grid; grid-template-columns:repeat(var(--kpi-columns,4),minmax(0,1fr)); gap:16px;
  margin:-66px 24px 0; position:relative; z-index:3;
}
.kpi{
  background:#fff; border:1px solid var(--line); border-radius:18px; padding:18px 20px 16px;
  box-shadow:0 18px 32px -20px rgba(14,42,53,.42);
}
.kpi-label{display:flex; gap:8px; align-items:flex-start; font-size:13px; font-weight:600; color:var(--muted); line-height:1.35; min-height:36px;}
.kpi-label i{flex:none; width:9px; height:9px; margin-top:4px; border-radius:50%; background:var(--accent);}
.kpi-value{font-family:'Fraunces',Georgia,serif; font-size:42px; font-weight:600; line-height:1.1; color:var(--ink); margin:6px 0 12px; letter-spacing:-.02em;}
.kpi-value small{font-size:22px; color:var(--muted); margin-left:2px;}
.kpi-track{height:6px; border-radius:99px; background:#E9EFF1; overflow:hidden;}
.kpi-fill{height:100%; border-radius:99px; background:var(--accent);}
.kpi-src{margin-top:10px; font-size:11.5px; color:var(--muted);}

/* ---------- tiles, chips, notes ---------- */
.tile-grid{display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:14px; margin:8px 0 6px;}
.tile{border:1px solid var(--line); border-radius:14px; padding:14px 16px; background:#FAFCFC;}
.tile-k{font-size:12.5px; font-weight:600; color:var(--muted);}
.tile-v{font-family:'Fraunces',Georgia,serif; font-size:25px; font-weight:600; color:var(--ink); margin-top:4px; line-height:1.2;}
.tile-s{font-size:13.5px; font-weight:700; margin-top:2px; color:var(--accent-text,var(--accent));}
.gap-row{display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:10px; margin-top:14px;}
.gap{border-radius:12px; padding:10px 12px; background:#F3F7F8; border:1px solid var(--line);}
.gap span{display:block; font-size:11.5px; color:var(--muted); font-weight:600;}
.gap b{font-size:16px; color:var(--ink);}
.micro{font-size:12.5px; color:var(--muted); margin-top:12px;}
.note{
  display:flex; gap:14px; align-items:flex-start; padding:18px 20px; border-radius:16px;
  background:#E9F4F2; border:1px solid #CFE5E1;
}
.note-ic{flex:none; width:34px; height:34px; border-radius:10px; background:var(--teal); color:#fff; display:grid; place-items:center; font-weight:800;}
.note.warn{background:#FFF6E0; border-color:#F3DFA8;}
.note.warn .note-ic{background:#F2B84B; color:#0E2A35;}
.note.warn p{color:#5E4510;}
.note.info{gap:11px; padding:13px 16px; background:#F4F7F8; border-color:#E2E9EC;}
.note.info .note-ic{width:28px; height:28px; border-radius:9px; background:#E2EFED; color:#176C63;}
.note.info p{color:#4E626B;}
.note b{display:block; margin-bottom:4px; color:var(--ink); font-size:14.5px;}
.note p{margin:0; font-size:14px; line-height:1.65; color:#2B535A;}
.src-note{font-size:12.5px; color:var(--muted); margin-top:4px;}

/* ---------- map strip & inspector ---------- */
.map-strip{display:flex; justify-content:space-between; align-items:center; gap:16px; padding:18px 22px 14px; flex-wrap:wrap;}
.map-strip .ct{font-size:20px;}
.chips{display:flex; gap:8px; flex-wrap:wrap;}
.chip{display:inline-flex; gap:7px; align-items:center; font-size:12px; font-weight:600; padding:6px 11px; border-radius:99px; background:#F1F5F6; color:var(--text);}
.chip i{width:12px; height:12px; border-radius:3px; border:2.5px solid; display:inline-block;}
.insp-top{display:flex; justify-content:space-between; align-items:flex-start; gap:10px;}
.insp-name{font-family:'Fraunces',Georgia,serif; font-size:30px; font-weight:600; line-height:1.1; color:var(--ink);}
.insp-rank{flex:none; font-size:12px; font-weight:700; padding:5px 10px; border-radius:99px; background:#FFF3D6; color:#7A5410; border:1px solid #F5DDA0;}
.insp-value{font-family:'Fraunces',Georgia,serif; font-size:64px; font-weight:600; line-height:1; margin:16px 0 4px; color:var(--accent-text,var(--accent)); letter-spacing:-.02em;}
.insp-value span{font-size:28px; color:var(--muted);}
.insp-sub{font-size:13px; color:var(--muted);}
.meter{position:relative; height:44px; margin:20px 0 2px;}
.meter-track{position:absolute; left:0; right:0; top:24px; height:6px; border-radius:99px; background:#E4EBEE;}
.meter-mark{position:absolute; top:0; transform:translateX(-50%); display:flex; flex-direction:column; align-items:center; font-size:10.5px; font-weight:700; color:var(--ink); line-height:12px;}
.meter-mark::after{content:""; width:2px; height:14px; background:var(--ink);}
.meter-dot{position:absolute; top:19px; width:16px; height:16px; border-radius:50%; background:var(--sun); border:3px solid #fff; box-shadow:0 0 0 2px var(--ink); transform:translateX(-50%);}
.meter-ends{display:flex; justify-content:space-between; font-size:11.5px; color:var(--muted);}
.insp-grid{display:grid; grid-template-columns:repeat(3,1fr); gap:8px; margin-top:16px; padding-top:16px; border-top:1px solid var(--line);}
.insp-grid b{display:block; font-size:16px; color:var(--ink);}
.insp-grid span{font-size:11.5px; color:var(--muted);}
.insp-note{margin-top:6px; padding:12px 14px; border-radius:12px; background:#F3F7F8; font-size:12.5px; line-height:1.55; color:#3F5560;}


/* ---------- section titles & group cards ---------- */
.sec{margin:8px 2px 14px;}
.sec .ct{font-size:24px;}
.gcards{display:grid; grid-template-columns:repeat(auto-fit,minmax(176px,1fr)); gap:14px;}
.gcard{position:relative; background:#fff; border:1px solid var(--line); border-radius:20px; padding:24px 16px 18px; text-align:center; box-shadow:var(--shadow); transition:transform .15s ease, border-color .15s ease;}
.gcard:hover{transform:translateY(-3px); border-color:var(--accent);}
.ring{width:116px; height:116px; border-radius:50%; margin:0 auto 14px; display:grid; place-items:center;
  background:conic-gradient(var(--accent) calc(var(--v) * 1%), #E9EFF1 0);}
.ring-in{width:86px; height:86px; border-radius:50%; background:#fff; display:grid; place-items:center;
  font-family:'Fraunces',Georgia,serif; font-size:27px; font-weight:600; color:var(--ink); letter-spacing:-.02em;}
.ring-in small{font-size:14px; color:var(--muted); margin-left:1px;}
.gc-name{font-weight:700; color:var(--ink); font-size:15.5px; line-height:1.3;}
.gc-n{font-size:12px; color:var(--muted); margin-top:3px;}
.gc-badge{position:absolute; top:12px; right:12px; font-size:11px; font-weight:700; padding:3px 9px; border-radius:99px;}
.gc-badge.hi{background:#FFF3D6; color:#7A5410; border:1px solid #F5DDA0;}
.gc-badge.lo{background:#E9F0F3; color:#33505D; border:1px solid #D3DFE5;}
.gap-pill{display:inline-flex; align-items:center; gap:8px; padding:8px 14px; border-radius:99px; background:#FFF3D6; border:1px solid #F5DDA0; color:#5E4510; font-weight:700; font-size:13px;}
.kpi-src b{color:var(--ink);}
.spread-head{display:flex; justify-content:space-between; align-items:flex-start; gap:16px; flex-wrap:wrap;}


/* ---------- priority explorer ---------- */
.ev{border:1px solid var(--line); border-radius:16px; padding:16px 18px 12px; background:#FAFCFC; margin-bottom:12px;}
.ev-top{display:flex; justify-content:space-between; align-items:center; gap:10px; flex-wrap:wrap;}
.ev-name{display:flex; align-items:center; gap:9px; font-weight:700; font-size:15.5px; color:var(--ink);}
.ev-name i{width:10px; height:10px; border-radius:50%; background:var(--accent); display:inline-block;}
.ev-why{font-size:12.5px; color:var(--muted); margin:3px 0 0 19px;}
.ev-chip{font-size:12px; font-weight:700; padding:4px 11px; border-radius:99px;}
.ev-chip.flag{background:#FDEEE9; color:#8A2F18; border:1px solid #F4C9BC;}
.ev-chip.ok{background:#DCF0EC; color:#0F5A52; border:1px solid #B9DFD8;}
.ev-chip.na{background:#EEF2F4; color:#4C606A; border:1px solid #DCE4E8;}
.ev-nums{display:grid; grid-template-columns:repeat(3,1fr); gap:8px; margin-top:12px;}
.ev-nums b{display:block; font-family:'Fraunces',Georgia,serif; font-size:22px; font-weight:600; color:var(--ink);}
.ev-nums span{font-size:11.5px; color:var(--muted);}
.rank-hint{font-size:12.5px; color:var(--muted); margin-top:10px; line-height:1.6;}
.build{margin-top:14px; padding:14px 16px; border-radius:14px; background:#F3F7F8; font-size:13px; line-height:1.65; color:#3F5560;}
.build b{color:var(--ink);}


/* ---------- methodology ---------- */
[data-testid="stMain"], html{scroll-behavior:smooth;}
.toc{display:flex; gap:8px; flex-wrap:wrap; margin:6px 0 2px;}
.toc a{display:inline-flex; align-items:center; gap:8px; padding:8px 14px; border-radius:99px; background:#fff;
  border:1px solid var(--line); color:var(--ink); font-size:13px; font-weight:600; text-decoration:none;
  transition:border-color .12s ease, background .12s ease;}
.toc a:hover{border-color:var(--teal); background:#F7FBFA; color:var(--teal-d);}
.toc a b{display:grid; place-items:center; width:20px; height:20px; border-radius:50%; background:var(--ink); color:#fff; font-size:11px;}
.msec{display:flex; gap:14px; align-items:center; margin:38px 2px 14px; scroll-margin-top:80px;}
.msec-n{flex:none; width:42px; height:42px; border-radius:13px; background:var(--ink); color:#fff; display:grid; place-items:center;
  font-family:'Fraunces',Georgia,serif; font-weight:600; font-size:18px; box-shadow:0 10px 20px -12px rgba(14,42,53,.8);}
.msec .ct{font-size:27px;}
.mgrid{display:grid; grid-template-columns:repeat(auto-fit,minmax(270px,1fr)); gap:14px;}
.mgrid.wide{grid-template-columns:repeat(auto-fit,minmax(340px,1fr));}
.mcard{background:#fff; border:1px solid var(--line); border-radius:18px; padding:20px 22px; box-shadow:var(--shadow);}
.mc-ic{width:42px; height:42px; border-radius:12px; display:grid; place-items:center; background:#DCF0EC; color:#126B61;
  font-family:'Fraunces',Georgia,serif; font-size:20px; font-weight:600; margin-bottom:12px;}
.mc-ic.warn{background:#FFF3D6; color:#7A5410;}
.mc-t{display:flex; align-items:center; gap:9px; font-weight:700; color:var(--ink); font-size:16px; margin-bottom:6px; line-height:1.3;}
.mc-t i{flex:none; width:10px; height:10px; border-radius:50%; background:var(--accent); display:inline-block;}
.mc-p{font-size:14px; line-height:1.68; color:#3F5560; margin:0;}
.mc-read{margin-top:12px; padding:10px 12px; border-radius:12px; background:#F3F7F8; font-size:13px; line-height:1.6; color:#3F5560;}
.mc-read b{color:var(--ink);}
.code{display:inline-block; font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; font-size:12px; background:#EEF3F5;
  border:1px solid var(--line); padding:3px 8px; border-radius:8px; color:var(--ink); margin:2px 0 8px;}
.pipe{display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:30px;}
.step{position:relative; background:#fff; border:1px solid var(--line); border-radius:18px; padding:20px 20px 18px; box-shadow:var(--shadow);}
.step:not(:last-child)::after{content:"\\2192"; position:absolute; right:-24px; top:50%; transform:translateY(-50%);
  font-size:20px; color:var(--teal); font-weight:700;}
.step-n{display:inline-grid; place-items:center; width:30px; height:30px; border-radius:50%; background:var(--sun); color:var(--ink);
  font-weight:800; font-size:13px; margin-bottom:10px;}
.fchips{display:flex; gap:8px; flex-wrap:wrap; margin-top:14px;}
.file{display:flex; align-items:center; gap:12px; padding:12px 14px; border:1px solid var(--line); border-radius:14px; background:#fff;}
.file-ic{flex:none; padding:5px 8px; border-radius:8px; background:#DCF0EC; color:#126B61; font-size:10.5px; font-weight:800; letter-spacing:.04em;}
.file-ic.nb{background:#FFF3D6; color:#7A5410;}
.file-n{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; font-size:12.5px; color:var(--ink); word-break:break-all;}
.formula-sym{display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:10px; margin-top:6px;}
.formula-sym div{padding:10px 12px; border-radius:12px; background:#F3F7F8; font-size:12.5px; line-height:1.5; color:#3F5560;}
.formula-sym b{display:block; font-family:'Fraunces',Georgia,serif; font-size:17px; color:var(--ink);}
[data-testid="stLatex"], .katex-display{color:var(--ink);}
.st-key-card_formula .katex-display{margin:18px 0; font-size:1.35em;}
@media (max-width:1100px){ .pipe{grid-template-columns:repeat(2,minmax(0,1fr));} .step:nth-child(2)::after{display:none;} }
@media (max-width:640px){ .pipe{grid-template-columns:1fr;} .step::after{display:none;} .formula-sym{grid-template-columns:1fr;} }


/* ---------- overview body ---------- */
.ins-grid{display:grid; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); gap:16px;}
.ins{position:relative; overflow:hidden; background:#fff; border:1px solid var(--line); border-radius:20px; padding:22px 24px 20px; box-shadow:var(--shadow);}
.ins::after{content:""; position:absolute; right:-34px; top:-34px; width:120px; height:120px; border-radius:50%; background:var(--accent); opacity:.10;}
.ins-k{position:relative; z-index:1; font-size:12.5px; font-weight:700; color:var(--accent-text,var(--accent));}
.ins-v{position:relative; z-index:1; font-family:'Fraunces',Georgia,serif; font-size:46px; font-weight:600; line-height:1.05; color:var(--ink); margin:8px 0; letter-spacing:-.02em;}
.ins-v small{font-size:22px; color:var(--muted); margin-left:3px;}
.ins-t{position:relative; z-index:1; font-size:14px; line-height:1.6; color:#3F5560;}
.ins-t b{color:var(--ink);}
.rk-h{font-size:12.5px; font-weight:700; color:var(--muted); margin:4px 0 8px;}
.rk{display:grid; gap:6px; margin-bottom:16px;}
.rk-row{display:grid; grid-template-columns:22px 1fr auto; align-items:center; gap:10px; padding:9px 12px; border-radius:11px; font-size:13.5px;
  background:linear-gradient(90deg, color-mix(in srgb, var(--accent) 22%, white) calc(var(--w) * 1%), #F3F7F8 0);}
.rk-n{color:var(--muted); font-weight:700; font-size:12px;}
.rk-name{font-weight:600; color:var(--ink);}
.rk-v{font-weight:700; color:var(--ink);}
@media (max-width:900px){ .ins-grid{grid-template-columns:1fr;} }


/* ---------- pills (indicator pickers) ---------- */
[data-testid="stButtonGroup"] button[data-testid="stBaseButton-pillsActive"]{
  background:var(--ink) !important; border-color:var(--ink) !important;
}
[data-testid="stButtonGroup"] button[data-testid="stBaseButton-pillsActive"] p{color:#fff !important;}
[data-testid="stButtonGroup"]{gap:6px;}

/* ---------- badges ---------- */
.badge{display:inline-flex; align-items:center; gap:6px; font-size:11.5px; font-weight:700; padding:3px 10px; border-radius:99px; white-space:nowrap;}
.badge.ok{background:#DCF0EC; color:#0F5A52; border:1px solid #B9DFD8;}
.badge.warn{background:#FFF3D6; color:#7A5410; border:1px solid #F5DDA0;}
.badge.flag{background:#FDEEE9; color:#8A2F18; border:1px solid #F4C9BC;}
.badge.info{background:#E9F0F3; color:#33505D; border:1px solid #D3DFE5;}
.moe{font-size:12px; color:var(--muted); font-weight:600;}
.gc-rel{margin-top:8px;}

/* ---------- data-health checks ---------- */
.chk-sum{display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:12px; margin-bottom:14px;}
.chk-sum div{border:1px solid var(--line); border-radius:14px; padding:12px 14px; background:#fff;}
.chk-sum b{display:block; font-family:'Fraunces',Georgia,serif; font-size:28px; color:var(--ink);}
.chk-sum span{font-size:12.5px; color:var(--muted); font-weight:600;}
.chk-row{display:grid; grid-template-columns:28px 1fr; gap:12px; padding:11px 4px; border-top:1px solid var(--line);}
.chk-ic{width:24px; height:24px; border-radius:50%; display:grid; place-items:center; font-size:13px; font-weight:800; margin-top:1px;}
.chk-ic.pass{background:#DCF0EC; color:#0F5A52;}
.chk-ic.warn{background:#FFF3D6; color:#7A5410;}
.chk-ic.fail{background:#FDEEE9; color:#8A2F18;}
.chk-t{font-weight:700; color:var(--ink); font-size:14px;}
.chk-d{font-size:13px; color:#3F5560; line-height:1.55; margin-top:2px;}
.chk-g{font-size:11.5px; color:var(--muted); font-weight:700; margin-left:8px;}

/* ---------- policy alignment ---------- */
.al-row{display:grid; grid-template-columns:1.1fr 1.4fr 1fr; gap:18px; padding:18px 4px; border-top:1px solid var(--line); align-items:start;}
.al-row:first-child{border-top:0;}
.al-h{font-size:11.5px; font-weight:700; color:var(--muted); margin-bottom:4px;}
.al-t{font-weight:700; color:var(--ink); font-size:15px; line-height:1.4;}
.al-p{font-size:13.5px; color:#3F5560; line-height:1.6; margin:0;}
.al-src{font-size:12px; color:var(--muted); margin-top:6px;}
.stat-grid{display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:14px;}
.stat{background:#fff; border:1px solid var(--line); border-radius:18px; padding:18px 20px; box-shadow:var(--shadow);}
.stat b{display:block; font-family:'Fraunces',Georgia,serif; font-size:40px; font-weight:600; line-height:1.05; color:var(--ink); letter-spacing:-.02em;}
.stat b small{font-size:20px; color:var(--muted);}
.stat span{display:block; font-size:13px; color:#3F5560; margin-top:6px; line-height:1.5;}
.stat em{display:block; font-style:normal; font-size:11.5px; font-weight:700; color:var(--muted); margin-top:8px;}
.sh-grid{display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); gap:14px;}
.sh{background:#fff; border:1px solid var(--line); border-radius:18px; padding:20px 22px; box-shadow:var(--shadow);}
.sh-t{font-weight:700; font-size:16px; color:var(--ink);}
.sh-q{margin:8px 0 0; padding-left:18px; font-size:13.5px; line-height:1.65; color:#3F5560;}
.sh-q li{margin-bottom:4px;}
.sh-go{margin-top:10px; font-size:12.5px; font-weight:700; color:var(--teal-d);}
.act{display:grid; grid-template-columns:44px 1fr; gap:16px; padding:18px 4px; border-top:1px solid var(--line);}
.act:first-child{border-top:0;}
.act-n{width:44px; height:44px; border-radius:14px; background:var(--ink); color:#fff; display:grid; place-items:center; font-family:'Fraunces',Georgia,serif; font-size:19px; font-weight:600;}
.act-t{font-weight:700; color:var(--ink); font-size:15.5px;}
.act-p{font-size:13.5px; color:#3F5560; line-height:1.65; margin:4px 0 0;}
.act-e{font-size:12.5px; color:var(--teal-d); font-weight:700; margin-top:6px;}
.cmp{width:100%; border-collapse:collapse; font-size:13.5px;}
.cmp th{text-align:left; font-size:11.5px; color:var(--muted); font-weight:700; padding:8px 10px; border-bottom:1px solid var(--line);}
.cmp td{padding:11px 10px; border-bottom:1px solid var(--line); vertical-align:top; color:#3F5560; line-height:1.55;}
.cmp td b{color:var(--ink);}
@media (max-width:1100px){ .stat-grid{grid-template-columns:repeat(2,minmax(0,1fr));} .al-row{grid-template-columns:1fr;} }
@media (max-width:640px){ .stat-grid{grid-template-columns:1fr;} .chk-sum{grid-template-columns:1fr;} }

/* ---------- placeholder pages & footer ---------- */
.soon{position:relative; overflow:hidden; border-radius:22px; padding:44px 44px 150px; background:#fff; border:1px solid var(--line); box-shadow:var(--shadow);}
.soon-ic{width:54px; height:54px; border-radius:16px; background:var(--teal-l); display:grid; place-items:center; font-size:26px; margin-bottom:18px; position:relative; z-index:2;}
.stApp .soon .soon-t{font-family:'Fraunces',Georgia,serif; font-size:32px; font-weight:600; color:var(--ink); margin:0 0 8px; padding:0; position:relative; z-index:2;}
.stApp .soon .soon-p{font-size:15.5px; color:var(--muted); max-width:52ch; margin:0; position:relative; z-index:2;}
.soon .pg-art{width:70%; opacity:.55;}
.app-foot{margin-top:28px; padding-top:16px; border-top:1px solid var(--line); display:flex; justify-content:space-between; gap:12px; flex-wrap:wrap; font-size:12.5px; color:var(--muted);}

/* ---------- combined-mode source labels and reading notes ---------- */
.pg-hero.dual::after{content:"";position:absolute;left:0;right:0;bottom:0;height:4px;z-index:3;
  background:linear-gradient(90deg,#1A8A7D 0 50%,#2F6FB3 50% 100%);}
.src-tag{display:inline-flex;align-items:center;font-size:9.5px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;
  padding:3px 7px;border-radius:6px;white-space:nowrap;line-height:1;}
.src-tag.fs{background:#DCF0EC;color:#0F5A52;}
.src-tag.nbr{background:#E3EEF8;color:#245A99;}
.kpi-label .src-tag{margin-left:auto;flex:none;}
.cov{display:flex;flex-wrap:wrap;gap:10px;margin:0;}
.cov-chip{display:inline-flex;gap:9px;align-items:center;padding:8px 13px;border-radius:12px;font-size:12.5px;line-height:1.45;
  color:var(--text);background:#fff;border:1px solid var(--line);box-shadow:0 1px 2px rgba(14,42,53,.04);}
.cov-chip.fs{border-left:3px solid #1A8A7D;}
.cov-chip.nbr{border-left:3px solid #2F6FB3;}
.cov-chip.none{border-left:3px solid #B4C3CA;color:var(--muted);background:#F6F8F9;}
.fn-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px 30px;padding:4px 2px 2px;}
.fn-h{font-size:12px;font-weight:800;color:var(--ink);margin-bottom:4px;}
.fn-p{font-size:13px;line-height:1.6;color:#3F5560;margin:0;}
.fn-src{font-size:12px;color:var(--muted);margin-top:14px;}

/* ---------- responsive ---------- */
@media (max-width:1100px){
  .kpi-grid{grid-template-columns:repeat(2,minmax(0,1fr)); margin:-66px 12px 0;}
  .gap-row{grid-template-columns:repeat(2,minmax(0,1fr));}
}
@media (max-width:768px){
  .block-container{padding:1rem 1rem 2.5rem;}
  .stApp .pg-hero{padding:26px 22px 32px; flex-direction:column;}
  .stApp .pg-hero.tall{padding-bottom:92px;}
  .tile-grid{grid-template-columns:1fr;}
  .insp-value{font-size:52px;}
  .st-key-nbr_context_card{padding:16px;}
}
@media (max-width:560px){
  .kpi-grid{grid-template-columns:1fr;}
}
@media (prefers-reduced-motion:reduce){
  *{transition:none !important; animation:none !important;}
}
"""


def apply_global_styles():
    """Apply the shared design system across all dashboard pages."""
    render_html(f"<style>{_CSS}{_CSS_PRESENTATION}{_layout_css()}</style>")


# --------------------------------------------------------------------------
# Components
# --------------------------------------------------------------------------
MODE_PILLS = {
    "Combined": "FinScope survey + NBR supply",
    "FinScope": "FinScope Rwanda 2024",
    "NBR Supply": "NBR administrative data",
}


def mode_pill(mode):
    return MODE_PILLS.get(mode, MODE_PILLS["FinScope"])


def source_tag(kind):
    label = {"fs": "FinScope", "nbr": "NBR"}.get(kind, "")
    return f'<span class="src-tag {esc(kind)}">{label}</span>'


def coverage_html(chips):
    body = "".join(
        f'<span class="cov-chip {esc(kind)}">'
        + (source_tag(kind) if kind in ("fs", "nbr") else "")
        + f"<span>{esc(text)}</span></span>"
        for kind, text in chips
    )
    return f'<div class="cov">{body}</div>'


def page_footnotes(items, source="", title="About these figures"):
    items = [(heading, body) for heading, body in items if heading and body]
    if not items:
        return
    with st.expander(title):
        cells = "".join(
            f'<div><div class="fn-h">{esc(heading)}</div>'
            f'<p class="fn-p">{esc(body)}</p></div>'
            for heading, body in items
        )
        render_html(f'<div class="fn-grid">{cells}</div>')
        if source:
            render_html(f'<div class="fn-src">{source}</div>')


def page_header(
    title,
    subtitle,
    pill=None,
    size="tall",
    below_html="",
    pill_badge=None,
    intro="",
    mode=None,
):
    """Hero header. size: 'tall' (overlaps a KPI row) or 'compact'."""
    pill_badge_html = badge(pill_badge, "warn") if pill_badge else ""
    intro_html = f'<p class="pg-intro">{esc(intro)}</p>' if intro else ""
    pill_html = (
        f'<div class="pg-pill"><i></i>{esc(pill)}{pill_badge_html}</div>'
        if pill else ""
    )
    dual_class = " dual" if mode == "Combined" else ""
    render_html(
        f"""
        <div class="pg-hero {size}{dual_class}">
          <div class="pg-text">
            <h1 class="pg-title">{esc(title)}</h1>
            <p class="pg-sub">{esc(subtitle)}</p>
            {intro_html}
          </div>
          {pill_html}
          <div class="pg-art">{HERO_ART}</div>
        </div>
        {below_html}
        """
    )


def kpi_card(
    label,
    value,
    small="",
    fill=0,
    accent="#1A8A7D",
    src="",
    tag="",
    *,
    show_track=True,
):
    """One floating KPI card (used inside kpi_grid)."""
    width = max(0.0, min(float(fill), 100.0))
    track = (
        f'<div class="kpi-track"><div class="kpi-fill" style="width:{width:.1f}%">'
        "</div></div>"
        if show_track
        else ""
    )
    tag_html = source_tag(tag) if tag in ("fs", "nbr") else ""
    return f"""
    <div class="kpi" style="--accent:{accent}">
      <div class="kpi-label"><i></i><span>{esc(label)}</span>{tag_html}</div>
      <div class="kpi-value">{value}<small>{small}</small></div>
      {track}
      <div class="kpi-src">{src}</div>
    </div>
    """


def kpi_grid(cards, columns=4):
    return f'<div class="kpi-grid" style="--kpi-columns:{columns}">{"".join(cards)}</div>'


def badge(text, tone="info"):
    return f'<span class="badge {tone}">{esc(text)}</span>'


def card_title(title, subtitle=None):
    sub = f'<div class="cs">{esc(subtitle)}</div>' if subtitle else ""
    render_html(f'<div class="ct">{esc(title)}</div>{sub}')


def section_title(title, subtitle=None):
    sub = f'<div class="cs">{esc(subtitle)}</div>' if subtitle else ""
    render_html(f'<div class="sec"><div class="ct">{esc(title)}</div>{sub}</div>')


def note(title, body, tone=""):
    icon = "!" if tone == "warn" else "i"
    render_html(
        f"""
        <div class="note {tone}"><div class="note-ic">{icon}</div>
        <div><b>{esc(title)}</b><p>{esc(body)}</p></div></div>
        """
    )


def coming_soon(title, text, icon="✨"):
    render_html(
        f"""
        <div class="soon">
          <div class="soon-ic">{icon}</div>
          <h2 class="soon-t">{esc(title)}</h2>
          <p class="soon-p">{esc(text)}</p>
          <div class="pg-art">{HERO_ART}</div>
        </div>
        """
    )


def app_footer():
    render_html(
        """
        <div class="app-foot">
          <span>FinScope Rwanda 2024 · Survey-based financial inclusion estimates</span>
          <span>Rwanda Financial Inclusion Gap Explorer</span>
        </div>
        """
    )


def sidebar_brand():
    render_html(
        f"""
        <div class="sb-brand"><div class="sb-logo">{LOGO_SVG}</div>
        <div><div class="sb-name">Rwanda Financial Inclusion</div>
        <div class="sb-sub">Gap Explorer</div></div></div>
        """
    )


def sidebar_dataset_card():
    render_html(
        """
        <div class="sb-card"><b>FinScope Rwanda 2024</b>
        <span>Weighted survey estimates across 30 districts and eight inclusion indicators.</span></div>
        """
    )


def sidebar_user(email):
    initial = esc((email or "?")[0].upper())
    render_html(
        f"""
        <div class="sb-user"><div class="sb-avatar">{initial}</div>
        <div><div class="sb-email">{esc(email)}</div><div class="sb-role">Signed in</div></div></div>
        """
    )


def show_district_table(df, sort_by, key, file_name, height=430):
    """Styled district table with in-cell bars and a CSV export."""
    cols = ["District", "Valid respondents"] + [
        c for c in INDICATOR_THEME if c in df.columns
    ]
    table = df[cols].sort_values(sort_by, ascending=False).reset_index(drop=True)

    config = {
        "Valid respondents": st.column_config.NumberColumn("Respondents", format="%d"),
    }
    for col, theme in INDICATOR_THEME.items():
        if col in table.columns:
            config[col] = st.column_config.ProgressColumn(
                theme["short"], format="%.1f%%", min_value=0, max_value=100
            )

    st.dataframe(
        table,
        hide_index=True,
        column_config=config,
        use_container_width=True,
        height=height,
    )
    st.download_button(
        "Download district results (CSV)",
        data=table.to_csv(index=False).encode("utf-8"),
        file_name=file_name,
        mime="text/csv",
        key=key,
        icon=":material/download:",
    )


# ==========================================================================
# Presentation components
# Shared by every page (FinScope, Combined and the standalone views) so the
# new sections look and behave identically everywhere.
# ==========================================================================
_CSS_PRESENTATION = """
/* ---------- heat-map legend ---------- */
.x-legend{display:flex; align-items:center; gap:12px; flex-wrap:wrap; font-size:12px; color:var(--muted); margin:2px 0 10px;}
.x-legend .x-ramp{width:190px; height:9px; border-radius:99px; background:linear-gradient(90deg,#DB6A4E 0%,#F4EEE8 50%,#1A8A7D 100%);}
.x-legend b{color:var(--ink); font-weight:700;}

/* ---------- head-to-head districts ---------- */
.x-duel{margin-top:6px;}
.x-duel-head{display:grid; grid-template-columns:1fr 190px 1fr; gap:14px; align-items:center; margin-bottom:10px;}
.x-duel-name{font-family:'Fraunces',Georgia,serif; font-size:22px; font-weight:600; color:var(--ink); line-height:1.15;}
.x-duel-name small{display:block; font-family:'Plus Jakarta Sans',Arial,sans-serif; font-size:11px; font-weight:700;
  letter-spacing:.1em; text-transform:uppercase; margin-bottom:3px;}
.x-duel-name.a{text-align:right;} .x-duel-name.a small{color:#B07C16;}
.x-duel-name.b small{color:var(--blue);}
.x-duel-mid{text-align:center; font-size:11px; font-weight:800; letter-spacing:.12em; color:var(--muted); text-transform:uppercase;}
.x-duel-row{display:grid; grid-template-columns:1fr 190px 1fr; gap:14px; align-items:center; padding:9px 0; border-top:1px solid var(--line);}
.x-duel-side{display:flex; align-items:center; gap:10px;}
.x-duel-side.a{flex-direction:row-reverse;}
.x-duel-side b{font-family:'Fraunces',Georgia,serif; font-size:21px; font-weight:600; color:var(--ink); min-width:62px;}
.x-duel-side.a b{text-align:left;}
.x-duel-track{position:relative; flex:1; height:12px; border-radius:99px; background:#EDF2F4; overflow:hidden;}
.x-duel-fill{position:absolute; top:0; bottom:0; border-radius:99px;}
.x-duel-side.a .x-duel-fill{right:0; background:linear-gradient(270deg,#F2B84B,#F6CD7E);}
.x-duel-side.b .x-duel-fill{left:0; background:linear-gradient(90deg,#2F6DB5,#5B91CC);}
.x-duel-side.lead .x-duel-fill{box-shadow:0 0 0 2px rgba(14,42,53,.14);}
.x-duel-lab{text-align:center; line-height:1.3;}
.x-duel-lab span{display:block; font-weight:700; font-size:13px; color:var(--ink);}
.x-duel-lab em{display:inline-block; font-style:normal; margin-top:4px; padding:2px 9px; border-radius:99px; font-size:11px; font-weight:700;}
.x-duel-lab em.a{background:#FFF3D6; color:#7A5410; border:1px solid #F5DDA0;}
.x-duel-lab em.b{background:#E3EEF8; color:#245A99; border:1px solid #C9DDF0;}
.x-duel-lab em.tie{background:#EEF2F4; color:#4C606A; border:1px solid #DCE4E8;}
.x-duel-lab small{display:block; font-size:10.5px; color:var(--muted); margin-top:3px;}
.x-duel-sum{display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:10px; margin:2px 0 16px;}
.x-duel-sum div{border-radius:14px; padding:12px 14px; background:#F3F7F8; border:1px solid var(--line);}
.x-duel-sum b{display:block; font-family:'Fraunces',Georgia,serif; font-size:24px; color:var(--ink); line-height:1.15;}
.x-duel-sum span{font-size:12px; color:var(--muted); font-weight:600;}

/* ---------- priority shortlist ---------- */
.x-podium{display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:16px; margin:4px 0 6px;}
.x-pod{position:relative; overflow:hidden; border-radius:20px; padding:22px 22px 18px; color:#fff;
  background:radial-gradient(260px 160px at 100% 0%,rgba(242,184,75,.22),transparent 70%),linear-gradient(150deg,#163D4B 0%,#0E2A35 100%);
  box-shadow:0 18px 34px -22px rgba(14,42,53,.8);}
.x-pod.r2{background:radial-gradient(260px 160px at 100% 0%,rgba(95,184,171,.2),transparent 70%),linear-gradient(150deg,#1B4E5A 0%,#102F3A 100%);}
.x-pod.r3{background:radial-gradient(260px 160px at 100% 0%,rgba(143,176,194,.2),transparent 70%),linear-gradient(150deg,#245563 0%,#14323E 100%);}
.x-pod-rank{position:absolute; top:14px; right:18px; font-family:'Fraunces',Georgia,serif; font-size:56px; font-weight:600;
  line-height:1; color:rgba(255,255,255,.14);}
.x-pod-k{font-size:10.5px; font-weight:800; letter-spacing:.14em; text-transform:uppercase; color:#F2B84B;}
.x-pod-name{font-family:'Fraunces',Georgia,serif; font-size:28px; font-weight:600; line-height:1.15; margin:6px 0 2px; color:#fff;}
.x-pod-score{font-family:'Fraunces',Georgia,serif; font-size:40px; font-weight:600; line-height:1.1; color:#fff;}
.x-pod-score small{font-family:'Plus Jakarta Sans',Arial,sans-serif; font-size:12px; font-weight:600; color:#B9C9D0; margin-left:6px;}
.x-pod-bar{height:6px; border-radius:99px; background:rgba(255,255,255,.14); margin:12px 0 12px; overflow:hidden;}
.x-pod-bar i{display:block; height:100%; border-radius:99px; background:linear-gradient(90deg,#F2B84B,#F6CD7E);}
.x-pod-row{display:flex; justify-content:space-between; gap:10px; font-size:12.5px; color:#C9D9DE; padding:3px 0;}
.x-pod-row b{color:#fff; font-weight:700; text-align:right;}
.x-pod-tag{display:inline-block; margin-top:10px; font-size:11px; font-weight:700; padding:3px 10px; border-radius:99px;
  background:rgba(255,255,255,.1); border:1px solid rgba(255,255,255,.2); color:#E8F0F2;}

/* ---------- guided next steps ---------- */
.x-next{border-radius:16px; padding:16px 18px 14px; background:linear-gradient(160deg,#FFFFFF 0%,#F4F8F8 100%);
  border:1px solid var(--line); min-height:132px; position:relative;}
.x-next-n{display:inline-grid; place-items:center; width:26px; height:26px; border-radius:50%; background:var(--ink); color:#fff;
  font-size:12px; font-weight:800; margin-bottom:8px;}
.x-next-t{font-family:'Fraunces',Georgia,serif; font-size:19px; font-weight:600; color:var(--ink); line-height:1.2;}
.x-next-p{font-size:12.8px; line-height:1.55; color:#4E626B; margin:6px 0 0;}

/* ---------- coverage matrix ---------- */
.x-cov-wrap{overflow-x:auto;}
.x-cov-table{width:100%; border-collapse:separate; border-spacing:0; font-size:13px;}
.x-cov-table th{font-size:11px; font-weight:800; letter-spacing:.08em; text-transform:uppercase; color:var(--muted);
  text-align:center; padding:8px 10px; border-bottom:1px solid var(--line); white-space:nowrap;}
.x-cov-table th:first-child{text-align:left;}
.x-cov-table td{padding:9px 10px; border-bottom:1px solid #EEF2F4; text-align:center; color:var(--text);}
.x-cov-table td:first-child{text-align:left; font-weight:700; color:var(--ink);}
.x-cov-table td:first-child i{display:inline-block; width:9px; height:9px; border-radius:50%; margin-right:9px; background:var(--accent,#1A8A7D);}
.x-dot{display:inline-grid; place-items:center; width:22px; height:22px; border-radius:50%; font-size:12px; font-weight:800;}
.x-dot.yes{background:#DCF0EC; color:#0F5A52;}
.x-dot.no{background:#F1F4F5; color:#9AAAB2;}
.x-dot.part{background:#FFF3D6; color:#7A5410;}
.x-cov-sum{display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:10px; margin:0 0 14px;}
.x-cov-sum div{border-radius:14px; padding:12px 14px; background:#F3F7F8; border:1px solid var(--line);}
.x-cov-sum b{display:block; font-family:'Fraunces',Georgia,serif; font-size:26px; color:var(--ink); line-height:1.1;}
.x-cov-sum span{font-size:12px; color:var(--muted); font-weight:600;}

@media (max-width:900px){
  .x-podium{grid-template-columns:1fr;}
  .x-duel-head,.x-duel-row{grid-template-columns:1fr;}
  .x-duel-name.a{text-align:left;}
  .x-duel-side.a{flex-direction:row;}
  .x-duel-sum{grid-template-columns:1fr;}
}
"""

HEAT_DIVERGING = [[0.0, "#DB6A4E"], [0.5, "#F4EEE8"], [1.0, "#1A8A7D"]]


def _polarity_sign(polarity):
    """+1 when a higher value is favourable, -1 when lower is, 0 when neither."""
    return {"positive": 1, "negative": -1}.get(polarity, 0)


def district_heatmap_figure(district, items, nat, sort_by=None):
    """District x indicator matrix coloured by distance from the national estimate.

    Colour is polarity-aware (teal = more favourable than national, coral = less) and
    scaled *within each column*, so no indicator dominates and no overall score is
    implied. Descriptive indicators with no favourable direction are left out.
    Returns (figure, shown_items).
    """
    shown = [
        it for it in items
        if it["column"] in district.columns
        and it.get("national") in nat
        and _polarity_sign(it.get("polarity")) != 0
    ]
    if not shown or district.empty:
        return None, []

    frame = district[["District"] + [it["column"] for it in shown]].copy()
    sort_item = next((it for it in shown if it["short"] == sort_by), None)
    if sort_item is not None:
        frame = frame.sort_values(sort_item["column"], ascending=False)
    else:
        frame = frame.sort_values("District")
    frame = frame.reset_index(drop=True)

    values, diffs, norm = [], [], []
    for it in shown:
        col = pd.to_numeric(frame[it["column"]], errors="coerce")
        national = float(nat[it["national"]])
        diff = col - national
        adj = diff * _polarity_sign(it["polarity"])
        peak = float(adj.abs().max()) if adj.notna().any() else 0.0
        values.append(col.to_numpy(dtype=float))
        diffs.append(diff.to_numpy(dtype=float))
        norm.append((adj / peak).to_numpy(dtype=float) if peak > 0 else adj.fillna(0).to_numpy(dtype=float))

    z = pd.DataFrame(norm).T.to_numpy()
    text = pd.DataFrame(values).T.to_numpy()
    custom = [
        [[diffs[j][i], float(nat[shown[j]["national"]])] for j in range(len(shown))]
        for i in range(len(frame))
    ]
    fig = go.Figure(
        go.Heatmap(
            z=z,
            x=[it["short"] for it in shown],
            y=frame["District"].tolist(),
            text=text,
            texttemplate="%{text:.0f}%",
            textfont=dict(size=11),
            colorscale=HEAT_DIVERGING,
            zmin=-1,
            zmax=1,
            showscale=False,
            xgap=3,
            ygap=3,
            customdata=custom,
            hovertemplate=(
                "<b>%{y}</b><br>%{x}: %{text:.1f}%<br>"
                "National: %{customdata[1]:.1f}% (%{customdata[0]:+.1f} pp)<extra></extra>"
            ),
        )
    )
    fig.update_xaxes(side="top", title=None, showgrid=False, tickfont=dict(size=12))
    fig.update_yaxes(title=None, autorange="reversed", showgrid=False, automargin=True, tickfont=dict(size=11))
    style_chart(fig, max(420, 25 * len(frame) + 90), margin=dict(l=4, r=8, t=8, b=4))
    return fig, shown


def heatmap_legend_html(left="Weaker than national", right="Stronger than national"):
    return (
        '<div class="x-legend"><span>' + esc(left) + '</span><span class="x-ramp"></span><span>'
        + esc(right) + "</span><span>Shading is scaled within each column · numbers are district "
        "estimates · no overall score is implied</span></div>"
    )


def build_duel_rows(district, items, nat, a, b, moe_fn=None):
    """Rows comparing two districts on every indicator in the district table."""
    rows = []
    frame = district.set_index("District")
    if a not in frame.index or b not in frame.index:
        return rows
    for it in items:
        col = it["column"]
        if col not in frame.columns:
            continue
        va, vb = frame.at[a, col], frame.at[b, col]
        if pd.isna(va) or pd.isna(vb):
            continue
        margin = None
        count_col = it.get("valid_count_column")
        if moe_fn is not None and count_col in frame.columns:
            na, nb = frame.at[a, count_col], frame.at[b, count_col]
            if not (pd.isna(na) or pd.isna(nb)):
                margin = float((moe_fn(float(va), float(na)) ** 2 + moe_fn(float(vb), float(nb)) ** 2) ** 0.5)
        rows.append(
            dict(
                label=it["short"],
                polarity=it.get("polarity", "neutral"),
                a=float(va),
                b=float(vb),
                national=nat.get(it.get("national")),
                margin=margin,
            )
        )
    return rows


def district_duel_html(a, b, rows):
    """Butterfly comparison of two districts. Returns '' when there is nothing to compare."""
    if not rows:
        return ""
    top = max(max(r["a"], r["b"]) for r in rows) or 1.0
    ahead_a = ahead_b = 0
    body = []
    for r in rows:
        sign = _polarity_sign(r["polarity"])
        diff = r["a"] - r["b"]
        within = r["margin"] is not None and abs(diff) <= r["margin"]
        if abs(diff) < 0.05:
            cls, text = "tie", "Level"
        elif sign == 0:
            cls = "a" if diff > 0 else "b"
            text = f"{a if diff > 0 else b} higher by {abs(diff):.1f} pp"
        else:
            a_leads = diff * sign > 0
            cls = "a" if a_leads else "b"
            text = f"{a if a_leads else b} ahead by {abs(diff):.1f} pp"
            if not within:
                ahead_a += int(a_leads)
                ahead_b += int(not a_leads)
        if sign == 0 and cls == "tie":
            pass
        note_line = (
            f'<small>National {r["national"]:.1f}%</small>' if r["national"] is not None else ""
        )
        if within and cls != "tie":
            note_line = "<small>Gap within illustrative margin · " + (
                f'National {r["national"]:.1f}%' if r["national"] is not None else "no national value"
            ) + "</small>"
        lead_a = " lead" if cls == "a" and sign != 0 else ""
        lead_b = " lead" if cls == "b" and sign != 0 else ""
        body.append(
            f'<div class="x-duel-row">'
            f'<div class="x-duel-side a{lead_a}"><b>{r["a"]:.1f}%</b>'
            f'<div class="x-duel-track"><div class="x-duel-fill" style="width:{r["a"] / top * 100:.1f}%"></div></div></div>'
            f'<div class="x-duel-lab"><span>{esc(r["label"])}</span><em class="{cls}">{esc(text)}</em>{note_line}</div>'
            f'<div class="x-duel-side b{lead_b}"><b>{r["b"]:.1f}%</b>'
            f'<div class="x-duel-track"><div class="x-duel-fill" style="width:{r["b"] / top * 100:.1f}%"></div></div></div>'
            f"</div>"
        )
    directional = sum(1 for r in rows if _polarity_sign(r["polarity"]) != 0)
    summary = (
        f'<div class="x-duel-sum">'
        f"<div><b>{ahead_a}</b><span>{esc(a)} clearly ahead on</span></div>"
        f"<div><b>{directional - ahead_a - ahead_b}</b><span>of {directional} directional indicators level or within margin</span></div>"
        f"<div><b>{ahead_b}</b><span>{esc(b)} clearly ahead on</span></div>"
        f"</div>"
    )
    head = (
        f'<div class="x-duel-head"><div class="x-duel-name a"><small>Selected district</small>{esc(a)}</div>'
        f'<div class="x-duel-mid">vs</div>'
        f'<div class="x-duel-name b"><small>Compared with</small>{esc(b)}</div></div>'
    )
    return f'{summary}<div class="x-duel">{head}{"".join(body)}</div>'


def priority_shortlist_html(rows, top_score=None):
    """Top-three shortlist cards. Each row: rank, district, score, driver, driver_share, stability, baseline_rank."""
    if not rows:
        return ""
    peak = top_score or max(r["score"] for r in rows) or 1.0
    cards = []
    for r in rows[:3]:
        share = f'{r["driver_share"]:.0f}% of score' if r.get("driver_share") is not None else ""
        cards.append(
            f'<div class="x-pod r{min(int(r["rank"]), 3)}">'
            f'<div class="x-pod-rank">{int(r["rank"])}</div>'
            f'<div class="x-pod-k">Screening rank {int(r["rank"])}</div>'
            f'<div class="x-pod-name">{esc(r["district"])}</div>'
            f'<div class="x-pod-score">{r["score"]:.1f}<small>relative points</small></div>'
            f'<div class="x-pod-bar"><i style="width:{max(4.0, min(100.0, r["score"] / peak * 100)):.1f}%"></i></div>'
            f'<div class="x-pod-row"><span>Largest driver</span><b>{esc(r["driver"])}'
            + (f" · {esc(share)}" if share else "")
            + "</b></div>"
            + (
                f'<div class="x-pod-row"><span>Fixed baseline rank</span><b>#{int(r["baseline_rank"])}</b></div>'
                if r.get("baseline_rank") is not None else ""
            )
            + f'<span class="x-pod-tag">{esc(r["stability"])}</span></div>'
        )
    return f'<div class="x-podium">{"".join(cards)}</div>'


def group_divide_figure(rows):
    """Bar chart of how wide the gap is for each kind of group (gender, age, education, area)."""
    if not rows:
        return None
    ordered = sorted(rows, key=lambda r: r["spread"])
    fig = go.Figure(
        go.Bar(
            x=[r["spread"] for r in ordered],
            y=[r["type"] for r in ordered],
            orientation="h",
            marker=dict(color=[PALETTE["sun"] if r is ordered[-1] else "#8FB0C2" for r in ordered]),
            text=[f'{r["spread"]:.1f} pp · {r["low"]} → {r["high"]}' for r in ordered],
            textposition="outside",
            textfont=dict(size=12, color=PALETTE["ink"]),
            cliponaxis=False,
            customdata=[[r["low"], r["low_v"], r["high"], r["high_v"]] for r in ordered],
            hovertemplate=(
                "<b>%{y}</b><br>Lowest: %{customdata[0]} (%{customdata[1]:.1f}%)"
                "<br>Highest: %{customdata[2]} (%{customdata[3]:.1f}%)<extra></extra>"
            ),
        )
    )
    fig.update_layout(bargap=0.38)
    fig.update_xaxes(
        title=None, ticksuffix=" pp", gridcolor=PALETTE["grid"], zeroline=False,
        range=[0, max(r["spread"] for r in ordered) * 2.1],
    )
    fig.update_yaxes(title=None, showgrid=False, automargin=True, tickfont=dict(size=13))
    return style_chart(fig, max(220, 58 * len(ordered) + 48), margin=dict(l=4, r=24, t=8, b=4))


def coverage_matrix_html(rows, columns, summary=None):
    """What data exists for each indicator. rows: (label, accent, {column: True|False|'part'})."""
    if not rows:
        return ""
    head = "".join(f"<th>{esc(c)}</th>" for c in columns)
    body = []
    for label, accent, cells in rows:
        tds = []
        for c in columns:
            state = cells.get(c)
            if state == "part":
                tds.append('<td><span class="x-dot part" title="Partial">◐</span></td>')
            elif state:
                tds.append('<td><span class="x-dot yes" title="Available">✓</span></td>')
            else:
                tds.append('<td><span class="x-dot no" title="Not available">–</span></td>')
        body.append(f'<tr><td style="--accent:{accent}"><i></i>{esc(label)}</td>{"".join(tds)}</tr>')
    sum_html = ""
    if summary:
        sum_html = (
            '<div class="x-cov-sum">'
            + "".join(f"<div><b>{esc(v)}</b><span>{esc(k)}</span></div>" for k, v in summary)
            + "</div>"
        )
    return (
        f'{sum_html}<div class="x-cov-wrap"><table class="x-cov-table"><thead><tr><th>Indicator</th>{head}</tr></thead>'
        f'<tbody>{"".join(body)}</tbody></table></div>'
    )


NEXT_STEP_COPY = {
    "National overview": "The headline picture: access, saving, barriers and a district map.",
    "District explorer": "Click through all 30 districts, compare them with the national level and download a profile.",
    "Population groups": "See how gender, age, education and area change each indicator.",
    "Priority explorer": "Screen districts for follow-up and test how sensitive the ranking is.",
    "Policy alignment": "Connect the evidence to national strategy, and see who can act on it.",
    "Methodology & sources": "Definitions, weights, margins and the data checks behind every number.",
}
NEXT_STEP_FLOW = {
    "National overview": ["District explorer", "Population groups", "Priority explorer"],
    "District explorer": ["Priority explorer", "Population groups", "Policy alignment"],
    "Population groups": ["District explorer", "Priority explorer", "Policy alignment"],
    "Priority explorer": ["District explorer", "Policy alignment", "Methodology & sources"],
    "Policy alignment": ["National overview", "Priority explorer", "Methodology & sources"],
    "Methodology & sources": ["National overview", "District explorer", "Policy alignment"],
}
NEXT_STEP_ICONS = {
    "National overview": ":material/dashboard:",
    "District explorer": ":material/map:",
    "Population groups": ":material/groups:",
    "Priority explorer": ":material/flag:",
    "Policy alignment": ":material/account_balance:",
    "Methodology & sources": ":material/menu_book:",
}


def _goto_page(page):
    st.session_state["selected_page"] = page


def render_next_steps(current, title="Keep exploring", subtitle=None):
    """Three guided cards that move the audience to the next most useful page."""
    targets = NEXT_STEP_FLOW.get(current, [])
    if not targets:
        return
    section_title(title, subtitle or "Each page answers a different question about the same evidence.")
    cols = st.columns(len(targets), gap="medium")
    slug = current.lower().replace(" ", "_").replace("&", "and")
    for number, (col, page) in enumerate(zip(cols, targets), start=1):
        with col:
            render_html(
                f'<div class="x-next"><div class="x-next-n">{number}</div>'
                f'<div class="x-next-t">{esc(page)}</div>'
                f'<p class="x-next-p">{esc(NEXT_STEP_COPY.get(page, ""))}</p></div>'
            )
            st.button(
                f"Open {page}",
                key=f"next_{slug}_{number}",
                icon=NEXT_STEP_ICONS.get(page),
                on_click=_goto_page,
                args=(page,),
                use_container_width=True,
            )


# ==========================================================================
# Balanced side-by-side layouts
# --------------------------------------------------------------------------
# Streamlit stretches both columns of a row to the taller one, but a card only
# grows to its own content, so the shorter card leaves a blank gap beside a long
# one (a map next to a long inspector, a chart next to a long list...).
#
# Two layout-only behaviours fix this. Neither moves or hides any content:
#   FOLLOW  the shorter card stays in view while you scroll past the long one
#           (position: sticky). On screens shorter than 640px high, or narrower
#           than 900px, it simply keeps its natural height, as before.
#   FILL    the card stretches to the height of its row so bottoms line up
#           (screens 900px wide or more; narrower windows keep natural heights).
#
# To change which cards behave this way, edit the lists below. Keys are the
# `key=` names of st.container(...) cards. A card is only made to follow when it
# is the only element in its column, so it can never overlap a card stacked
# under it. Use a `follow_<tier>_<name>` container key to wrap content that is
# not a card (for example a map inside another card).
# ==========================================================================
# tier -> (tallest card in the tier in px, cards that follow). On a screen shorter than
# the card, it is pinned by its bottom edge so most of it stays in view.
FOLLOW_TIERS = {
    "s": (520, ("card_landscape", "card_urban_rural")),
    "m": (800, ("card_map", "card_priority_drivers")),
    "l": (830, ()),
}
# Cards that always stretch to match the row they sit in.
FILL_CARDS = (
    "card_landscape_read", "card_urban_rural_gap",
    "card_group_compare", "card_group_sizes", "card_group_matrix", "card_group_gaps",
    "card_group_divides", "card_group_divides_read",
    "card_ranking", "card_distribution",
    "card_priority_ranking", "card_priority_top",
    "card_depth", "card_depth_read",
)
_COLUMNS = ('[data-testid="stColumn"]', '[data-testid="column"]')


def _in_column(selector_inside_has, tail=""):
    """Selector for the direct child of a column that contains the given element."""
    return ", ".join(
        f'{col} > [data-testid="stVerticalBlock"] > *:has({selector_inside_has}){tail}'
        for col in _COLUMNS
    )


def _layout_css():
    fill_keys = [f".st-key-{k}" for k in FILL_CARDS]
    follow_keys = []
    for tier, (_, cards) in FOLLOW_TIERS.items():
        follow_keys += [f".st-key-{k}" for k in cards]
        follow_keys.append(f'[class*="st-key-follow_{tier}_"]')
    has_all = ", ".join(fill_keys + follow_keys)

    css = []
    # Columns that hold one of these cards become flex columns, so a card can grow
    # (FILL) or be pinned inside the column's full height (FOLLOW).
    css.append(
        ", ".join(f"{col}:has({has_all})" for col in _COLUMNS)
        + "{display:flex; flex-direction:column;}"
    )
    css.append(
        ", ".join(
            f'{col}:has({has_all}) > [data-testid="stVerticalBlock"]' for col in _COLUMNS
        )
        + "{flex:1 1 auto;}"
    )
    # FILL: the last element in the column grows to the row height. Wide screens only;
    # on narrow windows every card keeps its natural height. FOLLOW cards never grow.
    css.append(
        "@media (min-width:900px){"
        + _in_column(", ".join(fill_keys), ":last-child")
        + "{flex:1 1 auto; display:flex; flex-direction:column;}"
        + ", ".join(fill_keys)
        + "{flex:1 1 auto;}}"
    )
    # FOLLOW: pinned while the long neighbour scrolls past. The card's bottom edge is
    # pinned on screens shorter than the card, so most of it stays visible.
    for tier, (tallest, cards) in FOLLOW_TIERS.items():
        sel = [f".st-key-{k}" for k in cards] + [f'[class*="st-key-follow_{tier}_"]']
        css.append(
            "@media (min-width:900px) and (min-height:640px){"
            + _in_column(", ".join(sel), ":only-child")
            + f"{{position:sticky; top:min(4.5rem, calc(100vh - {tallest}px - 1rem)); align-self:flex-start; flex:0 0 auto; width:100%; z-index:2;}}"
            + ", ".join(sel)
            + "{flex:0 0 auto;}"
            + "}"
        )
    return "\n".join(css)
