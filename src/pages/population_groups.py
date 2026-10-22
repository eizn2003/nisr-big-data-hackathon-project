from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.styles import (
    INDICATOR_THEME,
    PALETTE,
    card_title,
    esc,
    note,
    page_header,
    render_html,
    section_title,
    style_chart,
)


ROOT = Path(__file__).resolve().parents[2]
DATA_PATH = ROOT / "data" / "processed" / "population_group_indicators.csv"

GROUP_TYPES = ["Gender", "Age group", "Education", "Area"]

# short label -> data column (same four indicators as before)
INDICATORS = {t["short"]: col for col, t in INDICATOR_THEME.items()}

INDICATOR_NOTES = {
    "Bank account": (
        "Measures reported ownership of a bank account. "
        "Ownership does not necessarily indicate active account use."
    ),
    "Mobile money": (
        "Measures respondents who identify as registered mobile-money users. "
        "Registration is not a complete measure of transaction activity."
    ),
    "Borrowing": (
        "Measures recent borrowing activity, not only borrowing from formal "
        "financial institutions."
    ),
    "Doesn't save": (
        "A potential financial-vulnerability signal, not a direct measure "
        "of access to savings services."
    ),
}

HEAT_SCALE = ["#EAF6F3", "#9FD3CB", "#3AA597", "#17746A", "#0E2A35"]
KEY_GROUP, KEY_IND = "population_groups_type", "population_groups_indicator"


@st.cache_data
def load_group_data():
    data = pd.read_csv(DATA_PATH)

    required_columns = {
        "Group type",
        "Group",
        "Valid respondents",
        *INDICATORS.values(),
    }
    missing = required_columns.difference(data.columns)
    if missing:
        raise ValueError(
            "The population-group dataset is missing columns: "
            + ", ".join(sorted(missing))
        )

    data["Valid respondents"] = pd.to_numeric(
        data["Valid respondents"], errors="coerce"
    )
    for column in INDICATORS.values():
        data[column] = pd.to_numeric(data[column], errors="coerce")

    return data


def _kpi_cards(theme, hi, lo, diff, count, total):
    def card(label, value, small, fill, accent, src):
        return f"""
        <div class="kpi" style="--accent:{accent}">
          <div class="kpi-label"><i></i><span>{esc(label)}</span></div>
          <div class="kpi-value">{value}<small>{small}</small></div>
          <div class="kpi-track"><div class="kpi-fill" style="width:{max(0, min(fill, 100)):.1f}%"></div></div>
          <div class="kpi-src">{src}</div>
        </div>
        """

    cards = [
        card("Highest group", f"{hi[1]:.1f}", "%", hi[1], theme["accent"], f"<b>{esc(hi[0])}</b>"),
        card("Lowest group", f"{lo[1]:.1f}", "%", lo[1], PALETTE["ink2"], f"<b>{esc(lo[0])}</b>"),
        card("Gap between groups", f"{diff:.1f}", " pp", diff, PALETTE["sun"], "Highest minus lowest"),
        card("Groups compared", f"{count}", "", 100, "#5FB8AB",
             f"{total:,.0f} respondents across groups" if total else "Respondent counts unavailable"),
    ]
    return f'<div class="kpi-grid">{"".join(cards)}</div>'


def _spread_figure(selected, metric, theme):
    ordered = selected.sort_values(metric, ascending=True).reset_index(drop=True)
    values = ordered[metric].astype(float).tolist()
    names = ordered["Group"].astype(str).tolist()
    lo, hi = min(values), max(values)
    span = max(hi - lo, 1.0)
    x_min = max(0.0, lo - span * 0.55 - 4)
    x_max = min(100.0, hi + span * 0.55 + 4)

    colors = [theme["accent"]] * len(values)
    opacity = [0.62] * len(values)
    colors[0], opacity[0] = PALETTE["ink2"], 1
    colors[-1], opacity[-1] = theme["accent"], 1

    fig = go.Figure()
    fig.add_shape(
        type="line", x0=x_min, x1=x_max, y0=0, y1=0,
        line=dict(color="#DCE5E8", width=6), layer="below",
    )
    fig.add_vrect(
        x0=lo, x1=hi, fillcolor=theme["accent"], opacity=0.14,
        line_width=0, layer="below",
    )
    fig.add_trace(
        go.Scatter(
            x=values,
            y=[0] * len(values),
            mode="markers+text",
            text=[f"<b>{n}</b><br>{v:.1f}%" for n, v in zip(names, values)],
            textposition=[
                "top center" if i % 2 == 0 else "bottom center"
                for i in range(len(values))
            ],
            textfont=dict(size=12.5, color=PALETTE["ink"]),
            marker=dict(
                size=28, color=colors, opacity=opacity,
                line=dict(color="#FFFFFF", width=3.5),
            ),
            hovertemplate="<b>%{customdata}</b><br>%{x:.2f}%<extra></extra>",
            customdata=names,
            cliponaxis=False,
            showlegend=False,
        )
    )
    fig.add_annotation(
        x=(lo + hi) / 2, y=1.0, xref="x", yref="paper", yanchor="bottom",
        text=f"<b>Gap {hi - lo:.1f} pp</b>", showarrow=False,
        bgcolor=PALETTE["sun"], font=dict(size=13, color=PALETTE["ink"]),
        borderpad=6,
    )
    fig.update_xaxes(
        range=[x_min, x_max], ticksuffix="%", title=None,
        showgrid=False, zeroline=False,
    )
    fig.update_yaxes(range=[-1, 1], visible=False)
    return style_chart(fig, 280, margin=dict(l=10, r=10, t=44, b=6))


def _group_cards(selected, metric, theme):
    items = []
    last = len(selected) - 1
    for position, (_, row) in enumerate(selected.iterrows()):
        badge = ""
        if position == 0:
            badge = '<span class="gc-badge hi">Highest</span>'
        elif position == last and last > 0:
            badge = '<span class="gc-badge lo">Lowest</span>'
        n = row["Valid respondents"]
        n_text = f"n = {int(n):,}" if pd.notna(n) else "n unavailable"
        items.append(
            f"""
            <div class="gcard" style="--v:{max(0, min(float(row[metric]), 100)):.2f};--accent:{theme['accent']}">
              {badge}
              <div class="ring"><div class="ring-in">{row[metric]:.0f}<small>%</small></div></div>
              <div class="gc-name">{esc(row["Group"])}</div>
              <div class="gc-n">{n_text}</div>
            </div>
            """
        )
    return f'<div class="gcards">{"".join(items)}</div>'


def render_population_groups():
    try:
        data = load_group_data()
    except (FileNotFoundError, ValueError) as error:
        st.error("Could not load the population-group analysis data.")
        st.caption(str(error))
        return

    # Widget values already live in session_state before the widgets render,
    # so the hero can reflect the current selection even though the controls
    # appear below it.
    group_type = st.session_state.get(KEY_GROUP) or GROUP_TYPES[0]
    indicator_name = st.session_state.get(KEY_IND) or list(INDICATORS)[0]
    metric = INDICATORS[indicator_name]
    theme = INDICATOR_THEME[metric]

    subset = data.loc[data["Group type"].astype(str).eq(group_type)].copy()
    selected = subset.dropna(subset=["Group", metric]).sort_values(
        metric, ascending=False
    )

    if selected.empty:
        page_header(
            "Population groups",
            "Compare financial inclusion across demographic and geographic groups.",
            pill="FinScope Rwanda 2024",
            size="compact",
        )
        st.warning(
            f"No estimates are available for {group_type.lower()} "
            "for this indicator."
        )
        _controls()
        return

    highest = selected.iloc[0]
    lowest = selected.iloc[-1]
    difference = float(highest[metric] - lowest[metric])
    count = len(selected)
    total = float(selected["Valid respondents"].sum(skipna=True))

    # ---- Hero + headline cards -------------------------------------------
    page_header(
        "Population groups",
        f"How {theme['label'].lower()} differs across {group_type.lower()} "
        "groups, from FinScope Rwanda 2024.",
        pill="FinScope Rwanda 2024",
        size="tall",
        below_html=_kpi_cards(
            theme,
            (highest["Group"], float(highest[metric])),
            (lowest["Group"], float(lowest[metric])),
            difference,
            count,
            total,
        ),
    )

    st.markdown("")

    # ---- Controls ----------------------------------------------------------
    _controls()

    st.markdown("")

    # ---- Signature visual: the spread -------------------------------------
    with st.container(key="card_group_spread"):
        card_title(
            "How far apart are the groups?",
            f"Each dot is one {group_type.lower()} group on the same scale. "
            "The shaded band is the gap between the highest and the lowest.",
        )
        st.plotly_chart(
            _spread_figure(selected, metric, theme),
            use_container_width=True,
            key="population_groups_spread",
            config={"displayModeBar": False},
        )

    st.markdown("")

    # ---- Group-by-group rings ----------------------------------------------
    section_title(
        "Group by group",
        f"{theme['label']}, ranked from highest to lowest.",
    )
    render_html(_group_cards(selected, metric, theme))

    st.markdown("")

    # ---- Comparison bars + sample sizes ------------------------------------
    height = max(300, 46 * count + 40)
    left, right = st.columns([1.55, 1], gap="medium")

    with left:
        with st.container(key="card_group_compare"):
            card_title(
                f"{theme['label']} by {group_type.lower()}",
                "Weighted estimates. Differences describe the observed gap "
                "and do not establish causation or statistical significance.",
            )
            chart_data = selected.sort_values(metric, ascending=True)
            fig = go.Figure(
                go.Bar(
                    x=chart_data[metric],
                    y=chart_data["Group"],
                    orientation="h",
                    marker=dict(color=theme["accent"]),
                    text=chart_data[metric],
                    texttemplate="%{text:.1f}%",
                    textposition="outside",
                    cliponaxis=False,
                    textfont=dict(size=12, color=PALETTE["ink"]),
                    hovertemplate="<b>%{y}</b><br>Estimate: %{x:.2f}%<extra></extra>",
                )
            )
            fig.update_layout(bargap=0.34)
            fig.update_xaxes(
                title=None, ticksuffix="%",
                range=[0, min(100, float(chart_data[metric].max()) + 12)],
                gridcolor=PALETTE["grid"], zeroline=False,
            )
            fig.update_yaxes(title=None, showgrid=False, automargin=True)
            st.plotly_chart(
                style_chart(fig, height, margin=dict(l=4, r=30, t=8, b=4)),
                use_container_width=True,
                key="population_groups_chart",
                config={"displayModeBar": False},
            )

    with right:
        with st.container(key="card_group_sizes"):
            card_title(
                "Who answered",
                "Unweighted valid respondents per group. Smaller groups "
                "deserve more caution.",
            )
            sizes = selected.dropna(subset=["Valid respondents"]).sort_values(
                metric, ascending=True
            )
            size_fig = go.Figure(
                go.Bar(
                    x=sizes["Valid respondents"],
                    y=sizes["Group"],
                    orientation="h",
                    marker=dict(color="#8FB0C2"),
                    text=sizes["Valid respondents"],
                    texttemplate="%{text:,.0f}",
                    textposition="outside",
                    cliponaxis=False,
                    textfont=dict(size=12, color=PALETTE["ink"]),
                    hovertemplate="<b>%{y}</b><br>%{x:,.0f} respondents<extra></extra>",
                )
            )
            size_fig.update_layout(bargap=0.34)
            size_fig.update_xaxes(
                title=None,
                range=[0, float(sizes["Valid respondents"].max()) * 1.2]
                if not sizes.empty else None,
                gridcolor=PALETTE["grid"], zeroline=False, tickformat="~s",
            )
            size_fig.update_yaxes(title=None, showgrid=False, automargin=True)
            st.plotly_chart(
                style_chart(size_fig, height, margin=dict(l=4, r=40, t=8, b=4)),
                use_container_width=True,
                key="population_groups_sizes",
                config={"displayModeBar": False},
            )

    st.markdown("")

    # ---- Heatmap + widest gap ------------------------------------------------
    order = selected["Group"].tolist()
    unique = subset.dropna(subset=["Group"]).drop_duplicates("Group").set_index("Group")
    matrix = unique.reindex(order)
    columns = list(INDICATORS.values())
    shorts = list(INDICATORS.keys())
    real = matrix[columns].to_numpy(dtype=float)
    heat_height = max(260, 52 * count + 80)

    heat_col, gap_col = st.columns([1.55, 1], gap="medium")

    with heat_col:
        with st.container(key="card_group_matrix"):
            card_title(
                f"All four indicators by {group_type.lower()}",
                "Shading compares groups within each column, so the darkest "
                "cell marks the highest group for that indicator.",
            )
            norm = real.copy()
            for j in range(norm.shape[1]):
                col = norm[:, j]
                valid = col[~pd.isna(col)]
                if valid.size and valid.max() > valid.min():
                    norm[:, j] = (col - valid.min()) / (valid.max() - valid.min())
                else:
                    norm[:, j] = 0.5

            heat = go.Figure(
                go.Heatmap(
                    z=norm, x=shorts, y=order,
                    text=real, texttemplate="%{text:.1f}%",
                    textfont=dict(size=13),
                    colorscale=HEAT_SCALE, showscale=False,
                    xgap=4, ygap=4, customdata=real,
                    hovertemplate="<b>%{y}</b><br>%{x}: %{customdata:.2f}%<extra></extra>",
                )
            )
            heat.update_xaxes(side="top", title=None, showgrid=False, tickfont=dict(size=13))
            heat.update_yaxes(title=None, autorange="reversed", showgrid=False, automargin=True)
            st.plotly_chart(
                style_chart(heat, heat_height, margin=dict(l=4, r=8, t=8, b=4)),
                use_container_width=True,
                key="population_groups_matrix",
                config={"displayModeBar": False},
            )

    with gap_col:
        with st.container(key="card_group_gaps"):
            card_title(
                "Which indicator has the widest gap?",
                f"Highest minus lowest {group_type.lower()} group, per indicator.",
            )
            gaps = []
            for short, column in INDICATORS.items():
                values = subset[column].dropna()
                if not values.empty:
                    gaps.append((short, float(values.max() - values.min()),
                                 INDICATOR_THEME[column]["accent"]))
            gaps.sort(key=lambda item: item[1])

            gap_fig = go.Figure(
                go.Bar(
                    x=[g[1] for g in gaps],
                    y=[g[0] for g in gaps],
                    orientation="h",
                    marker=dict(color=[g[2] for g in gaps]),
                    text=[g[1] for g in gaps],
                    texttemplate="%{text:.1f} pp",
                    textposition="outside",
                    cliponaxis=False,
                    textfont=dict(size=13, color=PALETTE["ink"]),
                    hovertemplate="<b>%{y}</b><br>Gap: %{x:.2f} pp<extra></extra>",
                )
            )
            gap_fig.update_layout(bargap=0.4)
            gap_fig.update_xaxes(
                title=None, ticksuffix=" pp",
                range=[0, (max(g[1] for g in gaps) * 1.3) if gaps else 1],
                gridcolor=PALETTE["grid"], zeroline=False,
            )
            gap_fig.update_yaxes(title=None, showgrid=False, automargin=True)
            st.plotly_chart(
                style_chart(gap_fig, heat_height, margin=dict(l=4, r=40, t=8, b=4)),
                use_container_width=True,
                key="population_groups_gaps",
                config={"displayModeBar": False},
            )

    st.markdown("")

    # ---- Table ----------------------------------------------------------------
    with st.container(key="card_group_table"):
        card_title(
            "Detailed results",
            "Every indicator for each group, sorted by the indicator selected above.",
        )
        table = selected[["Group", "Valid respondents"]].copy()
        for short, column in INDICATORS.items():
            table[short] = unique[column].reindex(table["Group"]).to_numpy()
        table = table.rename(
            columns={"Group": group_type, "Valid respondents": "Valid respondents (n)"}
        )
        table["Valid respondents (n)"] = table["Valid respondents (n)"].astype("Int64")

        config = {
            "Valid respondents (n)": st.column_config.NumberColumn(
                "Respondents (n)", format="%d"
            )
        }
        for short in INDICATORS:
            config[short] = st.column_config.ProgressColumn(
                short, format="%.1f%%", min_value=0, max_value=100
            )

        st.dataframe(
            table, hide_index=True, use_container_width=True,
            column_config=config, height=min(440, 44 + 36 * len(table)),
        )
        st.download_button(
            "Download comparison (CSV)",
            data=table.round(2).to_csv(index=False).encode("utf-8"),
            file_name=f"population_groups_{group_type.lower().replace(' ', '_')}.csv",
            mime="text/csv",
            key="population_groups_download",
            icon=":material/download:",
        )

    st.markdown("")

    note("About this indicator", INDICATOR_NOTES[indicator_name])

    if group_type == "Education":
        st.markdown("")
        note(
            "Read small groups with care",
            "Education categories have different sample sizes. Interpret "
            "estimates for smaller groups, particularly vocational training, "
            "with additional caution.",
            tone="warn",
        )

    render_html(
        '<div class="src-note">Source: FinScope Rwanda 2024. Percentages are '
        "weighted survey estimates; respondent counts are unweighted valid "
        "sample sizes. Differences alone do not establish causation or "
        "statistical significance.</div>"
    )


def _controls():
    with st.container(key="card_controls"):
        c_group, c_ind = st.columns([1.5, 2], gap="large")
        with c_group:
            st.segmented_control(
                "Compare by",
                GROUP_TYPES,
                default=GROUP_TYPES[0],
                key=KEY_GROUP,
            )
        with c_ind:
            st.segmented_control(
                "Indicator",
                list(INDICATORS.keys()),
                default=list(INDICATORS.keys())[0],
                key=KEY_IND,
            )