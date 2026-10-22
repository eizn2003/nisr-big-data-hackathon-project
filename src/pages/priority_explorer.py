from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.styles import (
    INDICATOR_THEME,
    PALETTE,
    card_title,
    esc,
    kpi_card,
    kpi_grid,
    note,
    page_header,
    render_html,
    style_chart,
)


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data" / "processed"

DISTRICT_PATH = DATA_DIR / "district_financial_inclusion.csv"
NATIONAL_PATH = DATA_DIR / "national_financial_inclusion.csv"


INDICATORS = {
    "Bank-account ownership": {
        "column": "Owns a bank account (%)",
        "national_name": "Own bank account",
        "direction": "lower",
        "explanation": "Lower ownership than the national estimate",
    },
    "Mobile-money registration": {
        "column": "Registered mobile-money user (%)",
        "national_name": "Registered mobile-money user",
        "direction": "lower",
        "explanation": "Lower registration than the national estimate",
    },
    "Savings vulnerability": {
        "column": "Does not save (%)",
        "national_name": "Does not save",
        "direction": "higher",
        "explanation": "Higher share reporting that they do not save",
    },
}

KEY_DISTRICT = "priority_explorer_district"
KEY_SHOW = "priority_explorer_show"
SHOW_OPTIONS = ["Top 10", "Top 15", "All districts"]


def _accent(item):
    return INDICATOR_THEME[item["column"]]["accent"]


@st.cache_data
def load_priority_data():
    districts = pd.read_csv(DISTRICT_PATH)
    national = pd.read_csv(NATIONAL_PATH)

    required_district = {
        "District",
        "Valid respondents",
        *[item["column"] for item in INDICATORS.values()],
    }
    missing = required_district.difference(districts.columns)

    if missing:
        raise ValueError(
            "District dataset is missing: " + ", ".join(sorted(missing))
        )

    required_national = {"Indicator", "Estimate (%)"}
    if not required_national.issubset(national.columns):
        raise ValueError("National indicator dataset has unexpected columns.")

    for item in INDICATORS.values():
        name = item["national_name"]
        match = national.loc[national["Indicator"].eq(name), "Estimate (%)"]

        if match.empty:
            raise ValueError(f"National estimate not found for {name}.")

        item_value = pd.to_numeric(match.iloc[0], errors="coerce")
        if pd.isna(item_value):
            raise ValueError(f"National estimate is invalid for {name}.")

    return districts, national


def build_priority_scores(districts, national):
    result = districts.copy()

    # Positive gaps indicate a result that warrants closer attention.
    gap_columns = []

    for label, item in INDICATORS.items():
        column = item["column"]
        national_value = float(
            national.loc[
                national["Indicator"].eq(item["national_name"]),
                "Estimate (%)",
            ].iloc[0]
        )

        result[column] = pd.to_numeric(result[column], errors="coerce")

        gap_column = f"{label} priority gap (pp)"

        if item["direction"] == "lower":
            result[gap_column] = (
                national_value - result[column]
            ).clip(lower=0)
        else:
            result[gap_column] = (
                result[column] - national_value
            ).clip(lower=0)

        gap_columns.append(gap_column)

    # Scale each gap by its largest observed positive gap.
    # This gives the three components equal weight.
    normalized_columns = []

    for gap_column in gap_columns:
        max_gap = result[gap_column].max()
        normalized_column = f"{gap_column} normalized"

        if pd.isna(max_gap) or max_gap == 0:
            result[normalized_column] = 0.0
        else:
            result[normalized_column] = (
                result[gap_column] / max_gap
            ) * 100

        normalized_columns.append(normalized_column)

    result["Priority score"] = (
        result[normalized_columns].mean(axis=1)
    )

    result["Indicators available"] = (
        result[gap_columns].notna().sum(axis=1)
    )

    result["Screening status"] = result["Indicators available"].map(
        lambda count: (
            "Complete" if count == len(gap_columns)
            else "Incomplete evidence"
        )
    )

    # UI only: keep each indicator's share of the score for the charts.
    for label, norm_col in zip(INDICATORS, normalized_columns):
        result[f"{label} contribution"] = result[norm_col] / len(INDICATORS)

    result = result.drop(columns=normalized_columns)
    return result, gap_columns


# --------------------------------------------------------------------------
# UI helpers
# --------------------------------------------------------------------------
def _meter_pos(value, lo, hi):
    if hi <= lo:
        return 50.0
    return max(3.0, min(97.0, (value - lo) / (hi - lo) * 100))


def _jump_to(name):
    st.session_state[KEY_DISTRICT] = name


def _evidence_html(selected, national, ranked, label, item):
    column = item["column"]
    national_value = float(
        national.loc[
            national["Indicator"].eq(item["national_name"]), "Estimate (%)"
        ].iloc[0]
    )
    value = selected[column]
    lo, hi = float(ranked[column].min()), float(ranked[column].max())
    accent = _accent(item)

    if pd.isna(value):
        chip = '<span class="ev-chip na">Estimate unavailable</span>'
        nums = f"""
        <div class="ev-nums"><div><b>n/a</b><span>District</span></div>
        <div><b>{national_value:.1f}%</b><span>National</span></div>
        <div><b>n/a</b><span>Gap</span></div></div>
        """
        meter = ""
    else:
        value = float(value)
        gap = (
            national_value - value if item["direction"] == "lower"
            else value - national_value
        )
        if item["direction"] == "lower":
            text = "Below national estimate" if gap > 0 else "At or above national estimate"
        else:
            text = "Above national estimate" if gap > 0 else "At or below national estimate"
        chip = f'<span class="ev-chip {"flag" if gap > 0 else "ok"}">{text}</span>'
        nums = f"""
        <div class="ev-nums">
          <div><b>{value:.1f}%</b><span>{esc(selected['District'])}</span></div>
          <div><b>{national_value:.1f}%</b><span>National</span></div>
          <div><b>{max(gap, 0):.1f} pp</b><span>Gap toward priority</span></div>
        </div>
        """
        meter = f"""
        <div class="meter">
          <div class="meter-track"></div>
          <div class="meter-mark" style="left:{_meter_pos(national_value, lo, hi):.1f}%">National</div>
          <div class="meter-dot" style="left:{_meter_pos(value, lo, hi):.1f}%"></div>
        </div>
        <div class="meter-ends"><span>Lowest district {lo:.1f}%</span><span>Highest {hi:.1f}%</span></div>
        """

    return f"""
    <div class="ev" style="--accent:{accent}">
      <div class="ev-top"><div class="ev-name"><i></i>{esc(label)}</div>{chip}</div>
      <div class="ev-why">{esc(item['explanation'])}</div>
      {nums}
      {meter}
    </div>
    """


def _donut(selected):
    labels = list(INDICATORS.keys())
    values = [float(selected[f"{label} contribution"]) for label in labels]
    colors = [_accent(item) for item in INDICATORS.values()]
    score = float(selected["Priority score"])

    if sum(values) <= 0:
        pie = go.Pie(
            labels=["No gap above national"], values=[1], hole=0.7,
            marker=dict(colors=["#E4EBEE"]), textinfo="none",
            hoverinfo="skip", showlegend=False,
        )
    else:
        pie = go.Pie(
            labels=labels, values=values, hole=0.7, sort=False,
            marker=dict(colors=colors, line=dict(color="#FFFFFF", width=3)),
            textinfo="none", direction="clockwise",
            hovertemplate="<b>%{label}</b><br>%{value:.1f} of 100 points<extra></extra>",
            showlegend=False,
        )
    fig = go.Figure(pie)
    fig.add_annotation(
        text=f"<b style='font-size:34px'>{score:.1f}</b><br>"
             f"<span style='font-size:12px;color:{PALETTE['muted']}'>out of 100</span>",
        showarrow=False, font=dict(color=PALETTE["ink"], size=16),
    )
    return style_chart(fig, 280, margin=dict(l=4, r=4, t=4, b=4))


def _ranking_figure(ranked, selected_district, show):
    if show == "Top 10":
        pool = ranked.head(10)
    elif show == "Top 15":
        pool = ranked.head(15)
    else:
        pool = ranked
    if selected_district not in pool["District"].values:
        pool = pd.concat([pool, ranked.loc[ranked["District"].eq(selected_district)]])
    chart = pool.sort_values("Priority score", ascending=True)

    is_sel = chart["District"].eq(selected_district)
    line_colors = [PALETTE["sun"] if v else "#FFFFFF" for v in is_sel]
    line_widths = [3 if v else 0.6 for v in is_sel]

    fig = go.Figure()
    for label, item in INDICATORS.items():
        fig.add_bar(
            y=chart["District"],
            x=chart[f"{label} contribution"],
            orientation="h",
            name=label,
            marker=dict(
                color=_accent(item),
                line=dict(color=line_colors, width=line_widths),
            ),
            hovertemplate=(
                "<b>%{y}</b><br>" + label
                + ": %{x:.1f} points<extra></extra>"
            ),
        )
    fig.add_trace(
        go.Scatter(
            x=chart["Priority score"], y=chart["District"],
            mode="text", text=[f"{v:.1f}" for v in chart["Priority score"]],
            textposition="middle right", textfont=dict(size=12, color=PALETTE["ink"]),
            hoverinfo="skip", showlegend=False, cliponaxis=False,
        )
    )
    fig.update_layout(barmode="stack", bargap=0.3)
    fig.update_xaxes(
        title=None, range=[0, min(100, float(chart["Priority score"].max()) + 10)],
        gridcolor=PALETTE["grid"], zeroline=False,
    )
    fig.update_yaxes(title=None, showgrid=False, tickfont=dict(size=11.5))
    height = max(380, 34 * len(chart) + 70)
    return style_chart(fig, height, margin=dict(l=4, r=24, t=34, b=4)), height


# --------------------------------------------------------------------------
# Page
# --------------------------------------------------------------------------
def render_priority_explorer():
    try:
        districts, national = load_priority_data()
        scored, gap_columns = build_priority_scores(districts, national)
    except (FileNotFoundError, ValueError, KeyError) as error:
        st.error("Could not load the priority analysis data.")
        st.caption(str(error))
        return

    # Exclude districts with incomplete component data from the ranking.
    ranked = scored.loc[
        scored["Screening status"].eq("Complete")
    ].copy()

    if ranked.empty:
        st.warning("There are no districts with complete indicator data.")
        return

    ranked = ranked.sort_values(
        "Priority score", ascending=False
    ).reset_index(drop=True)
    ranked["Rank"] = ranked.index + 1
    total = len(ranked)

    names = ranked["District"].tolist()
    st.session_state.setdefault(KEY_DISTRICT, names[0])
    if st.session_state[KEY_DISTRICT] not in names:
        st.session_state[KEY_DISTRICT] = names[0]

    selected_district = st.session_state[KEY_DISTRICT]
    selected = ranked.loc[ranked["District"].eq(selected_district)].iloc[0]
    score = float(selected["Priority score"])

    # Largest single driver of the selected district's score
    contribs = {
        label: float(selected[f"{label} contribution"]) for label in INDICATORS
    }
    driver_label = max(contribs, key=contribs.get)
    driver_item = INDICATORS[driver_label]
    if score > 0:
        driver_html = (
            f'<span style="font-size:25px">'
            f'{esc(INDICATOR_THEME[driver_item["column"]]["short"])}</span>'
        )
        driver_fill = contribs[driver_label] / score * 100
        driver_src = f"<b>{driver_fill:.0f}%</b> of the score"
    else:
        driver_html = '<span style="font-size:25px">None</span>'
        driver_fill = 0
        driver_src = "No gap above national"

    max_n = float(ranked["Valid respondents"].max())

    # ---- Hero + headline cards -------------------------------------------
    page_header(
        "Priority explorer",
        "Screen districts whose bank, mobile-money and savings results fall "
        "behind national estimates, and see what drives each score.",
        pill="Exploratory screening",
        size="tall",
        below_html=kpi_grid(
            [
                kpi_card("Relative priority score", f"{score:.1f}", "/100", score,
                         PALETTE["sun"], f"<b>{esc(selected_district)}</b>"),
                kpi_card("Screening rank", f"#{int(selected['Rank'])}", f" of {total}",
                         (total - int(selected["Rank"]) + 1) / total * 100,
                         PALETTE["ink2"], "Rank 1 = largest relative gaps"),
                kpi_card("Largest driver", driver_html, "", driver_fill,
                         _accent(driver_item), driver_src),
                kpi_card("Valid respondents", f"{int(selected['Valid respondents']):,}", "",
                         float(selected["Valid respondents"]) / max_n * 100,
                         "#5FB8AB",
                         f"{int(selected['Indicators available'])}/3 indicators available"),
            ]
        ),
    )

    st.markdown("")

    note(
        "An exploratory screening score",
        "This is not an official poverty ranking. It compares FinScope Rwanda "
        "2024 estimates with national estimates and does not establish "
        "causation or current conditions.",
        tone="warn",
    )

    st.markdown("")

    # ---- Controls ----------------------------------------------------------
    with st.container(key="card_controls"):
        c_dist, c_show = st.columns([1.3, 2], gap="large", vertical_alignment="bottom")
        with c_dist:
            st.selectbox("Explore a district", names, key=KEY_DISTRICT)
        with c_show:
            show = st.segmented_control(
                "Districts shown in the ranking",
                SHOW_OPTIONS,
                default=SHOW_OPTIONS[1],
                key=KEY_SHOW,
            ) or SHOW_OPTIONS[1]

    st.markdown("")

    # ---- Evidence + score composition --------------------------------------
    left, right = st.columns([1.45, 1], gap="medium")

    with left:
        with st.container(key="card_priority_evidence"):
            card_title(
                f"Why {selected_district} appears on the screen",
                "Each indicator compared with the national estimate. The "
                "yellow dot is this district, the tick is the national level.",
            )
            for label, item in INDICATORS.items():
                render_html(_evidence_html(selected, national, ranked, label, item))

    with right:
        with st.container(key="card_priority_drivers"):
            card_title(
                "What drives the score",
                "Each indicator contributes up to a third of the 100 points.",
            )
            st.plotly_chart(
                _donut(selected),
                use_container_width=True,
                key="priority_donut",
                config={"displayModeBar": False},
            )
            legend = "".join(
                f'<div class="gap" style="margin-bottom:8px"><span>'
                f'<i style="display:inline-block;width:9px;height:9px;border-radius:50%;'
                f'background:{_accent(item)};margin-right:7px"></i>{esc(label)}</span>'
                f'<b>{contribs[label]:.1f} pts</b></div>'
                for label, item in INDICATORS.items()
            )
            render_html(legend)
            render_html(
                '<div class="rank-hint">Higher scores mean larger relative gaps '
                "across the three indicators. Scores are comparative within this "
                "dataset, not probabilities or percentages of people in need.</div>"
            )

    st.markdown("")

    # ---- Ranking + top five ------------------------------------------------
    rank_col, top_col = st.columns([1.6, 1], gap="medium")

    with rank_col:
        with st.container(key="card_priority_ranking"):
            card_title(
                "Screening ranking",
                "Bars are split by indicator so you can see what builds each "
                "score. The selected district has a yellow outline.",
            )
            fig, _ = _ranking_figure(ranked, selected_district, show)
            st.plotly_chart(
                fig,
                use_container_width=True,
                key="priority_explorer_ranking",
                config={"displayModeBar": False},
            )

    with top_col:
        with st.container(key="card_priority_top"):
            card_title(
                "Highest screening scores",
                "Jump straight to the districts with the largest relative gaps.",
            )
            for _, row in ranked.head(5).iterrows():
                st.button(
                    f"{int(row['Rank'])}  ·  {row['District']}  ·  {row['Priority score']:.1f}",
                    key=f"pe_jump_{row['District']}",
                    on_click=_jump_to,
                    args=(row["District"],),
                    use_container_width=True,
                )
            render_html(
                f"""
                <div class="build"><b>How the score is built.</b><br>
                For each of three indicators, the gap to the national estimate is
                measured in the direction that signals a need (below national for
                banking and mobile money, above national for not saving).
                Each gap is scaled by the largest gap among districts, and the
                three scaled gaps are averaged with equal weight.</div>
                """
            )

    st.markdown("")

    # ---- Ranked table --------------------------------------------------------
    with st.container(key="card_priority_table"):
        card_title(
            "Ranked results",
            "All districts with complete indicator data, from the largest to "
            "the smallest relative gap.",
        )

        display_columns = [
            "District",
            "Priority score",
            "Valid respondents",
            "Owns a bank account (%)",
            "Registered mobile-money user (%)",
            "Does not save (%)",
            "Screening status",
        ]
        display = ranked[display_columns].copy()
        display["Priority score"] = display["Priority score"].round(1)
        for column in display_columns[3:6]:
            display[column] = display[column].round(2)

        st.dataframe(
            display,
            hide_index=True,
            use_container_width=True,
            height=440,
            column_config={
                "Priority score": st.column_config.ProgressColumn(
                    "Priority score", format="%.1f", min_value=0, max_value=100
                ),
                "Valid respondents": st.column_config.NumberColumn(
                    "Respondents", format="%d"
                ),
                "Owns a bank account (%)": st.column_config.ProgressColumn(
                    "Bank account", format="%.1f%%", min_value=0, max_value=100
                ),
                "Registered mobile-money user (%)": st.column_config.ProgressColumn(
                    "Mobile money", format="%.1f%%", min_value=0, max_value=100
                ),
                "Does not save (%)": st.column_config.ProgressColumn(
                    "Doesn't save", format="%.1f%%", min_value=0, max_value=100
                ),
            },
        )

        st.download_button(
            "Download priority screening results (CSV)",
            data=display.to_csv(index=False).encode("utf-8"),
            file_name="district_priority_screening.csv",
            mime="text/csv",
            key="priority_explorer_download",
            icon=":material/download:",
        )

    render_html(
        '<div class="src-note">Source: FinScope Rwanda 2024. Respondent counts '
        "are unweighted sample sizes; indicator percentages are weighted "
        "estimates. The score uses equal weighting of three normalized gaps. "
        "No confidence intervals or statistical-significance claims are made.</div>"
    )