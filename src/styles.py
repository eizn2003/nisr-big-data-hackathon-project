"""Shared design system: tokens, global CSS, chart theme and small UI components."""

import html as _html

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
    render_html(f"<style>{_CSS}</style>")


# --------------------------------------------------------------------------
# Components
# --------------------------------------------------------------------------
def page_header(title, subtitle, pill=None, size="tall", below_html="", pill_badge=None):
    """Hero header. size: 'tall' (overlaps a KPI row) or 'compact'."""
    pill_badge_html = badge(pill_badge, "warn") if pill_badge else ""
    pill_html = (
        f'<div class="pg-pill"><i></i>{esc(pill)}{pill_badge_html}</div>'
        if pill else ""
    )
    render_html(
        f"""
        <div class="pg-hero {size}">
          <div class="pg-text">
            <h1 class="pg-title">{esc(title)}</h1>
            <p class="pg-sub">{esc(subtitle)}</p>
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
    return f"""
    <div class="kpi" style="--accent:{accent}">
      <div class="kpi-label"><i></i><span>{esc(label)}</span></div>
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
