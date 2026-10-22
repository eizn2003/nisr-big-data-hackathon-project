from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.pages.district_explorer import _trace_classes, load_district_data
from src.styles import (
    INDICATOR_THEME,
    PALETTE,
    card_title,
    esc,
    note,
    page_header,
    render_html,
    section_title,
    show_district_table,
    style_chart,
)


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data" / "processed"

NATIONAL_TO_COLUMN = {t["national"]: col for col, t in INDICATOR_THEME.items()}
FALLBACK_ACCENTS = [t["accent"] for t in INDICATOR_THEME.values()]


@st.cache_data
def load_overview_data():
    national = pd.read_csv(DATA_DIR / "national_financial_inclusion.csv")
    district = pd.read_csv(DATA_DIR / "district_financial_inclusion.csv")
    urban_rural = pd.read_csv(DATA_DIR / "urban_rural_financial_inclusion.csv")
    return national, district, urban_rural


def _accent_for(indicator, position):
    column = NATIONAL_TO_COLUMN.get(indicator)
    if column:
        return INDICATOR_THEME[column]["accent"]
    return FALLBACK_ACCENTS[position % len(FALLBACK_ACCENTS)]


def _kpi_html(national):
    cards = []
    for position, (_, row) in enumerate(national.iterrows()):
        value = float(row["Estimate (%)"])
        accent = _accent_for(row["Indicator"], position)
        cards.append(
            f"""
            <div class="kpi" style="--accent:{accent}">
              <div class="kpi-label"><i></i><span>{esc(row["Indicator"])}</span></div>
              <div class="kpi-value">{value:.1f}<small>%</small></div>
              <div class="kpi-track"><div class="kpi-fill" style="width:{min(value, 100):.1f}%"></div></div>
              <div class="kpi-src">Source variable: {esc(row["Source variable"])}</div>
            </div>
            """
        )
    return f'<div class="kpi-grid">{"".join(cards)}</div>'


def _open_district_explorer():
    st.session_state["main_nav"] = "District explorer"


# --------------------------------------------------------------------------
# Insight strip
# --------------------------------------------------------------------------
def _insights_html(national, district, urban_rural):
    nat = dict(zip(national["Indicator"], national["Estimate (%)"].astype(float)))
    cards = []

    # 1. Mobile money vs bank accounts
    bank, mobile = nat.get("Own bank account"), nat.get("Registered mobile-money user")
    if bank is not None and mobile is not None:
        lead = mobile - bank
        leader, trailer = (
            ("Mobile-money registration", "bank-account ownership")
            if lead >= 0 else ("Bank-account ownership", "mobile-money registration")
        )
        cards.append((
            INDICATOR_THEME["Registered mobile-money user (%)"],
            "Two ways in",
            f"{abs(lead):.1f}<small>pp</small>",
            f"<b>{leader}</b> is ahead of {trailer} "
            f"({max(mobile, bank):.1f}% vs {min(mobile, bank):.1f}%).",
        ))

    # 2. Widest urban-rural gap
    metrics = [c for c in INDICATOR_THEME if c in urban_rural.columns]
    by_area = urban_rural.set_index("Area")
    if {"Urban", "Rural"} <= set(by_area.index) and metrics:
        gaps = {m: float(by_area.loc["Urban", m] - by_area.loc["Rural", m]) for m in metrics}
        widest = max(gaps, key=lambda m: abs(gaps[m]))
        theme = INDICATOR_THEME[widest]
        cards.append((
            theme,
            "Urban and rural",
            f"{abs(gaps[widest]):.1f}<small>pp</small>",
            f"Widest urban-rural gap is in <b>{theme['label'].lower()}</b> "
            f"(urban {by_area.loc['Urban', widest]:.1f}% vs rural {by_area.loc['Rural', widest]:.1f}%).",
        ))

    # 3. District spread
    col = "Owns a bank account (%)" if "Owns a bank account (%)" in district.columns else metrics[0]
    theme = INDICATOR_THEME[col]
    low, high = district.loc[district[col].idxmin()], district.loc[district[col].idxmax()]
    cards.append((
        theme,
        "Across districts",
        f"{high[col] - low[col]:.1f}<small>pp</small>",
        f"{theme['label']} runs from <b>{low[col]:.1f}%</b> in {esc(low['District'])} "
        f"to <b>{high[col]:.1f}%</b> in {esc(high['District'])}.",
    ))

    html = "".join(
        f"""
        <div class="ins" style="--accent:{theme['accent']};--accent-text:{theme['text_accent']}">
          <div class="ins-k">{esc(kicker)}</div>
          <div class="ins-v">{value}</div>
          <div class="ins-t">{text}</div>
        </div>
        """
        for theme, kicker, value, text in cards
    )
    return f'<div class="ins-grid">{html}</div>'


# --------------------------------------------------------------------------
# Urban / rural / national
# --------------------------------------------------------------------------
def _grouped_bars(urban_rural, national, metrics):
    """One group of columns per indicator: urban, rural and the national level."""
    by_area = urban_rural.set_index("Area")
    nat = dict(zip(national["Indicator"], national["Estimate (%)"].astype(float)))
    labels = [INDICATOR_THEME[m]["short"] for m in metrics]

    series = [
        ("Urban", [float(by_area.loc["Urban", m]) for m in metrics], PALETTE["ink2"]),
        ("Rural", [float(by_area.loc["Rural", m]) for m in metrics], "#5FB8AB"),
    ]
    nat_values = [nat.get(INDICATOR_THEME[m]["national"]) for m in metrics]
    if all(v is not None for v in nat_values):
        series.append(("National", nat_values, "#B4C3CA"))

    fig = go.Figure()
    for name, values, color in series:
        fig.add_bar(
            x=labels, y=values, name=name, marker=dict(color=color),
            text=values, texttemplate="%{text:.1f}%", textposition="outside",
            textfont=dict(size=11.5, color=PALETTE["ink"]), cliponaxis=False,
            hovertemplate="<b>%{x}</b><br>" + name + ": %{y:.2f}%<extra></extra>",
        )

    top = max(v for _, values, _ in series for v in values)
    fig.update_layout(barmode="group", bargap=0.24, bargroupgap=0.06)
    fig.update_yaxes(
        range=[0, min(100, top + 14)], ticksuffix="%", title=None,
        gridcolor=PALETTE["grid"], zeroline=False,
    )
    fig.update_xaxes(
        title=None, showgrid=False,
        tickfont=dict(size=13.5, color=PALETTE["ink"]),
    )
    return style_chart(fig, 380, margin=dict(l=4, r=10, t=34, b=4))


def _gap_figure(urban_rural, metrics):
    by_area = urban_rural.set_index("Area")
    labels = [INDICATOR_THEME[m]["short"] for m in metrics]
    gaps = [float(by_area.loc["Urban", m] - by_area.loc["Rural", m]) for m in metrics]
    colors = [INDICATOR_THEME[m]["accent"] for m in metrics]

    fig = go.Figure(go.Bar(
        x=gaps, y=labels, orientation="h", marker=dict(color=colors),
        text=gaps, texttemplate="%{text:+.1f} pp", textposition="outside",
        textfont=dict(size=13, color=PALETTE["ink"]), cliponaxis=False,
        hovertemplate="<b>%{y}</b><br>Urban minus rural: %{x:+.2f} pp<extra></extra>",
    ))
    bound = max(abs(g) for g in gaps) * 1.45 or 1
    fig.update_xaxes(
        range=[-bound, bound], title=None, ticksuffix=" pp",
        gridcolor=PALETTE["grid"], zeroline=True, zerolinecolor=PALETTE["ink"], zerolinewidth=1.5,
    )
    fig.update_yaxes(title=None, showgrid=False, autorange="reversed",
                     tickfont=dict(size=13.5, color=PALETTE["ink"]))
    for x, text, anchor in ((0.0, "Rural higher", "left"), (1.0, "Urban higher", "right")):
        fig.add_annotation(
            x=x, y=1.0, xref="paper", yref="paper", yanchor="bottom", xanchor=anchor,
            text=text, showarrow=False, font=dict(size=12, color=PALETTE["muted"]),
        )
    fig.update_layout(bargap=0.42)
    return style_chart(fig, 380, margin=dict(l=4, r=26, t=34, b=4))


# --------------------------------------------------------------------------
# District map
# --------------------------------------------------------------------------
def _map_figure(district, geojson, center, metric, theme):
    Choropleth, _, key = _trace_classes()
    lo, hi = float(district[metric].min()), float(district[metric].max())
    fig = go.Figure(Choropleth(
        geojson=geojson, featureidkey="properties.shapeName",
        locations=district["District"], z=district[metric], zmin=lo, zmax=hi,
        colorscale=theme["scale"],
        marker=dict(opacity=0.92, line=dict(color="#FFFFFF", width=0.9)),
        hovertemplate="<b>%{location}</b><br>" + theme["label"] + ": %{z:.1f}%<extra></extra>",
        colorbar=dict(
            orientation="h", x=0.02, y=0.03, xanchor="left", yanchor="bottom",
            len=0.42, thickness=10, nticks=4, ticksuffix="%", outlinewidth=0,
            bgcolor="rgba(255,255,255,.88)", xpad=12, ypad=8,
            tickfont=dict(size=11, color=PALETTE["ink"]),
        ),
    ))
    fig.update_layout(**{key: dict(
        style="carto-positron",
        center=dict(lat=center[0], lon=center[1]), zoom=6.8,
    )})
    fig.update_layout(
        height=520, margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor="rgba(0,0,0,0)",
        dragmode=False,
        hoverlabel=dict(bgcolor=PALETTE["ink"], bordercolor=PALETTE["ink"],
                        font=dict(color="#FFFFFF", size=12.5)),
    )
    return fig


def _ranking_html(district, metric, theme):
    ordered = district.sort_values(metric, ascending=False)

    def rows(frame, start):
        return "".join(
            f'<div class="rk-row" style="--w:{max(0, min(float(r[metric]), 100)):.1f}">'
            f'<span class="rk-n">{start + i}</span><span class="rk-name">{esc(r["District"])}</span>'
            f'<span class="rk-v">{r[metric]:.1f}%</span></div>'
            for i, (_, r) in enumerate(frame.iterrows())
        )

    n = len(ordered)
    return f"""
    <div style="--accent:{theme['accent']}">
      <div class="rk-h">Highest five districts</div>
      <div class="rk">{rows(ordered.head(5), 1)}</div>
      <div class="rk-h">Lowest five districts</div>
      <div class="rk">{rows(ordered.tail(5), n - 4)}</div>
    </div>
    """


# --------------------------------------------------------------------------
# Page
# --------------------------------------------------------------------------
def render_national_overview():
    try:
        national, district, urban_rural = load_overview_data()
    except (FileNotFoundError, ValueError, KeyError) as error:
        st.error(
            "The overview data could not be loaded. "
            "Check the files in data/processed."
        )
        st.caption(str(error))
        return

    district = district.copy()
    district["District"] = district["District"].astype(str).str.strip()

    # ---- Hero + headline indicators (unchanged) -------------------------
    page_header(
        "Financial inclusion across Rwanda",
        "How people bank, use mobile money, borrow and save, based on "
        "weighted FinScope survey estimates.",
        pill="FinScope Rwanda 2024",
        size="tall",
        below_html=_kpi_html(national),
    )

    st.markdown("")

    # ---- What stands out ---------------------------------------------------
    section_title(
        "What stands out",
        "Three patterns in the data, worked out from the estimates below.",
    )
    render_html(_insights_html(national, district, urban_rural))

    st.markdown("")

    # ---- Urban, rural and national ----------------------------------------
    metrics = [c for c in INDICATOR_THEME if c in urban_rural.columns]
    if metrics and {"Urban", "Rural"} <= set(urban_rural["Area"]):
        section_title(
            "Urban and rural",
            "Where people live shapes access. Compare both areas with the "
            "national level on every indicator.",
        )
        left, right = st.columns([1.5, 1], gap="medium")

        with left:
            with st.container(key="card_urban_rural"):
                card_title(
                    "Urban, rural and national",
                    "Each group of bars is one indicator, showing the urban "
                    "estimate, the rural estimate and the national level.",
                )
                st.plotly_chart(
                    _grouped_bars(urban_rural, national, metrics),
                    use_container_width=True,
                    key="ov_grouped",
                    config={"displayModeBar": False},
                )
                if "Valid respondents" in urban_rural.columns:
                    counts = " · ".join(
                        f'{r["Area"]}: {int(r["Valid respondents"]):,}'
                        for _, r in urban_rural.iterrows()
                    )
                    render_html(f'<div class="micro">Respondents · {esc(counts)}</div>')

        with right:
            with st.container(key="card_urban_rural_gap"):
                card_title(
                    "How big is the gap?",
                    "Urban estimate minus rural estimate, in percentage points.",
                )
                st.plotly_chart(
                    _gap_figure(urban_rural, metrics),
                    use_container_width=True,
                    key="ov_gap",
                    config={"displayModeBar": False},
                )
                render_html(
                    '<div class="micro">Bars to the right mean urban areas are '
                    "higher; bars to the left mean rural areas are higher.</div>"
                )

        st.markdown("")

    # ---- Where the gaps are ------------------------------------------------
    section_title(
        "Where the gaps are",
        "Pick an indicator to see how districts compare across the country.",
    )

    options = {t["short"]: col for col, t in INDICATOR_THEME.items()
               if col in district.columns}
    with st.container(key="card_district_snapshot"):
        picked = st.segmented_control(
            "Indicator",
            list(options.keys()),
            default=list(options.keys())[0],
            key="overview_district_indicator",
        ) or list(options.keys())[0]
        metric = options[picked]
        theme = INDICATOR_THEME[metric]

        low = district.loc[district[metric].idxmin()]
        high = district.loc[district[metric].idxmax()]
        spread = float(high[metric] - low[metric])

        try:
            _, _, geojson, _, center = load_district_data()
            map_ok = True
        except Exception:
            map_ok = False

        st.markdown("")
        info = f"""
        <div class="gap-row" style="grid-template-columns:repeat(3,minmax(0,1fr));margin:0 0 14px">
          <div class="gap"><span>Highest district</span><b>{esc(high["District"])} · {high[metric]:.1f}%</b></div>
          <div class="gap"><span>Lowest district</span><b>{esc(low["District"])} · {low[metric]:.1f}%</b></div>
          <div class="gap"><span>District range</span><b>{spread:.1f} pp</b></div>
        </div>
        """
        render_html(info)

        if map_ok:
            map_col, list_col = st.columns([1.35, 1], gap="large")
            with map_col:
                st.plotly_chart(
                    _map_figure(district, geojson, center, metric, theme),
                    use_container_width=True,
                    key="ov_district_map",
                    config={"displayModeBar": False, "scrollZoom": False},
                )
            with list_col:
                render_html(_ranking_html(district, metric, theme))
                st.button(
                    "Open the District explorer",
                    key="ov_open_districts",
                    on_click=_open_district_explorer,
                    use_container_width=True,
                    icon=":material/map:",
                )
        else:
            render_html(_ranking_html(district, metric, theme))

        with st.expander("View district data"):
            show_district_table(
                district,
                sort_by=metric,
                key="download_district_results",
                file_name="rwanda_district_indicator_results.csv",
                height=400,
            )

    st.markdown("")

    note(
        "How to interpret these figures",
        "These are survey-based weighted estimates from FinScope Rwanda 2024, "
        "not live measurements. A district with lower bank-account ownership "
        "may warrant further investigation, but these figures alone do not "
        "explain why the gap exists. Borrowing activity also does not measure "
        "every dimension of access to credit.",
    )
    render_html(
        '<div class="src-note">Source: FinScope Rwanda 2024. '
        "See Methodology &amp; sources for indicator definitions and limitations.</div>"
    )