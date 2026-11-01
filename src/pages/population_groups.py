import math

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src import data
from src.data_sources.mongodb_population_groups import load_population_group_results
from src.indicators import available
from src.styles import (
    PALETTE,
    badge,
    card_title,
    esc,
    kpi_card,
    kpi_grid,
    note,
    page_header,
    render_html,
    section_title,
    style_chart,
)

GROUP_TYPES = ["Gender", "Age group", "Education", "Area"]
ORDINAL = {"Age group", "Education"}  # shown in natural order, not by value
HEAT_SCALE = ["#EAF6F3", "#9FD3CB", "#3AA597", "#17746A", "#0E2A35"]
KEY_GROUP, KEY_IND = "population_groups_type", "population_groups_indicator"


def load_group_data():
    frame = load_population_group_results().observations
    needed = {"Group type", "Group", "Valid respondents"}
    missing = needed.difference(frame.columns)
    if missing:
        raise ValueError("The population-group dataset is missing columns: " + ", ".join(sorted(missing)))
    frame["Valid respondents"] = pd.to_numeric(frame["Valid respondents"], errors="coerce")
    items = available(frame)
    if not items:
        raise ValueError("The population-group dataset has no recognised indicator columns.")
    missing_denominators = [
        item["valid_count_column"]
        for item in items
        if item["valid_count_column"] not in frame.columns
    ]
    if missing_denominators:
        raise ValueError(
            "The population-group dataset is missing indicator-specific respondent "
            "counts: " + ", ".join(missing_denominators)
        )
    for item in items:
        frame[item["column"]] = pd.to_numeric(frame[item["column"]], errors="coerce")
        frame[item["valid_count_column"]] = pd.to_numeric(
            frame[item["valid_count_column"]], errors="coerce"
        )
    return frame


def _fmt(n):
    return f"{int(n):,}" if pd.notna(n) else "n/a"


def _spread_figure(frame, metric, item):
    ordered = frame.sort_values(metric, ascending=True).reset_index(drop=True)
    values = ordered[metric].astype(float).tolist()
    names = ordered["Group"].astype(str).tolist()
    lo, hi = min(values), max(values)
    span = max(hi - lo, 1.0)
    x_min = max(0.0, lo - span * 0.55 - 4)
    x_max = min(100.0, hi + span * 0.55 + 4)

    colors = [item["accent"]] * len(values)
    opacity = [0.62] * len(values)
    colors[0], opacity[0] = PALETTE["ink2"], 1
    colors[-1], opacity[-1] = item["accent"], 1

    fig = go.Figure()
    fig.add_shape(type="line", x0=x_min, x1=x_max, y0=0, y1=0,
                  line=dict(color="#DCE5E8", width=6), layer="below")
    fig.add_vrect(x0=lo, x1=hi, fillcolor=item["accent"], opacity=0.14, line_width=0, layer="below")
    fig.add_trace(go.Scatter(
        x=values, y=[0] * len(values), mode="markers+text",
        text=[f"<b>{n}</b><br>{v:.1f}%" for n, v in zip(names, values)],
        textposition=["top center" if i % 2 == 0 else "bottom center" for i in range(len(values))],
        textfont=dict(size=12.5, color=PALETTE["ink"]),
        marker=dict(size=28, color=colors, opacity=opacity, line=dict(color="#FFFFFF", width=3.5)),
        hovertemplate="<b>%{customdata}</b><br>%{x:.2f}%<extra></extra>", customdata=names,
        cliponaxis=False, showlegend=False))
    fig.add_annotation(x=(lo + hi) / 2, y=1.0, xref="x", yref="paper", yanchor="bottom",
                       text=f"<b>Gap {hi - lo:.1f} pp</b>", showarrow=False,
                       bgcolor=PALETTE["sun"], font=dict(size=13, color=PALETTE["ink"]), borderpad=6)
    fig.update_xaxes(range=[x_min, x_max], ticksuffix="%", title=None, showgrid=False, zeroline=False)
    fig.update_yaxes(range=[-1, 1], visible=False)
    return style_chart(fig, 280, margin=dict(l=10, r=10, t=44, b=6))


def _group_cards(frame, metric, item, best, worst):
    cards = []
    for _, row in frame.iterrows():
        badges = ""
        if row["Group"] == best:
            badges = '<span class="gc-badge hi">Highest</span>'
        elif row["Group"] == worst:
            badges = '<span class="gc-badge lo">Lowest</span>'
        n = row["Valid respondents"]
        margin = data.moe_pp(row[metric], n)
        rel = badge("Small sample: wide margin", "warn") if data.margin_flag(n) == "wide" else ""
        cards.append(f"""
        <div class="gcard" style="--v:{max(0, min(float(row[metric]), 100)):.2f};--accent:{item['accent']}">
          {badges}
          <div class="ring"><div class="ring-in">{row[metric]:.0f}<small>%</small></div></div>
          <div class="gc-name">{esc(row["Group"])}</div>
          <div class="gc-n">n = {_fmt(n)} · <span class="moe">±{margin:.1f} pp</span></div>
          <div class="gc-rel">{rel}</div>
        </div>""")
    return f'<div class="gcards">{"".join(cards)}</div>'


def _controls(indicators):
    with st.container(key="card_controls"):
        c_group, c_ind = st.columns([1.3, 2.4], gap="large")
        with c_group:
            st.segmented_control("Compare by", GROUP_TYPES, default=GROUP_TYPES[0], key=KEY_GROUP)
        with c_ind:
            st.pills("Indicator", list(indicators.keys()), selection_mode="single",
                     default=list(indicators.keys())[0], key=KEY_IND)


def render_population_groups():
    from src.pages.nbr_dashboard import (
        current_mode,
        render_combined_context,
        render_nbr_page,
    )

    mode = current_mode()
    if mode == "NBR Supply":
        render_nbr_page("population")
        return

    try:
        frame = load_group_data().copy()
    except (FileNotFoundError, ValueError) as error:
        st.error("Could not load the population-group analysis data.")
        st.caption(str(error))
        return

    indicators = {it["short"]: it for it in available(frame)}

    group_type = st.session_state.get(KEY_GROUP) or GROUP_TYPES[0]
    chosen = st.session_state.get(KEY_IND)
    item = indicators.get(chosen) or list(indicators.values())[0]
    metric = item["column"]
    denominator = item["valid_count_column"]
    frame["Valid respondents"] = frame[denominator]

    subset = frame.loc[frame["Group type"].astype(str).eq(group_type)].copy()
    subset = subset.dropna(subset=["Group", metric]).reset_index(drop=True)
    if subset.empty:
        page_header("Population groups", "Compare financial inclusion across demographic and geographic groups.",
                    pill="FinScope Rwanda 2024", size="compact")
        st.warning(f"No estimates are available for {group_type.lower()} for this indicator.")
        _controls(indicators)
        return

    by_value = subset.sort_values(metric, ascending=False).reset_index(drop=True)
    shown = subset if group_type in ORDINAL else by_value  # display order
    hi_row, lo_row = by_value.iloc[0], by_value.iloc[-1]
    gap = float(hi_row[metric] - lo_row[metric])
    combined = math.sqrt(
        data.moe_pp(hi_row[metric], hi_row["Valid respondents"]) ** 2
        + data.moe_pp(lo_row[metric], lo_row["Valid respondents"]) ** 2
    )
    clear = gap > combined
    count = len(subset)
    total = float(subset["Valid respondents"].sum(skipna=True))
    value_direction = (
        "A higher value indicates more reported access or resilience."
        if item["polarity"] == "positive"
        else "A higher value indicates greater vulnerability for this measure."
        if item["polarity"] == "negative"
        else "Higher and lower values are descriptive; neither is inherently better."
    )

    # ---- Hero + headline cards -------------------------------------------
    page_header(
        "Population groups",
        f"How {item['label'].lower()} differs across {group_type.lower()} groups, from FinScope Rwanda 2024.",
        pill="FinScope Rwanda 2024",
        size="tall",
        below_html=kpi_grid([
            kpi_card("Highest value", f"{hi_row[metric]:.1f}", "%", hi_row[metric], item["accent"],
                     f"<b>{esc(hi_row['Group'])}</b>"),
            kpi_card("Lowest value", f"{lo_row[metric]:.1f}", "%", lo_row[metric], PALETTE["ink2"],
                     f"<b>{esc(lo_row['Group'])}</b>"),
            kpi_card("Gap between groups", f"{gap:.1f}", " pp", gap, PALETTE["sun"],
                     "Exceeds combined illustrative margin" if clear else "Within combined illustrative margin"),
            kpi_card("Groups compared", f"{count}", "", 100, "#5FB8AB",
                     f"{total:,.0f} respondents across groups"),
        ]),
    )
    st.markdown("")
    st.caption(
        f"Highest and lowest refer to the displayed indicator value, not an overall group ranking. "
        f"{value_direction} These are national group summaries, not district-by-group estimates."
    )
    _controls(indicators)
    st.markdown("")

    # ---- Spread ------------------------------------------------------------------
    with st.container(key="card_group_spread"):
        card_title("How far apart are the groups?",
                   f"Each dot is one {group_type.lower()} group on the same scale. The shaded band is the "
                   "gap between the highest and the lowest.")
        st.plotly_chart(_spread_figure(subset, metric, item), use_container_width=True,
                        key="population_groups_spread", config={"displayModeBar": False})
        verdict = (badge("Observed gap exceeds the combined illustrative margin", "info") if clear
                   else badge("Gap is within the combined illustrative margin", "warn"))
        render_html(f'<div class="micro" style="margin-top:0">{verdict} Combined indicative margin '
                    f"of the two extreme groups: ±{combined:.1f} pp (simple-random-sample approximation only; "
                    "not a formal test of the group difference because the survey design is unavailable. "
                    "The margin is an interpretation aid, not evidence that the observed difference is significant.</div>")
    st.markdown("")

    # ---- Group by group --------------------------------------------------------------
    order_note = "in natural order" if group_type in ORDINAL else "from highest to lowest"
    section_title("Group by group", f"{item['label']}, {order_note}.")
    render_html(_group_cards(shown, metric, item, hi_row["Group"], lo_row["Group"]))
    st.markdown("")

    # ---- Bars + sample sizes -------------------------------------------------------------
    height = max(300, 46 * count + 40)
    left, right = st.columns([1.55, 1], gap="medium")
    order = shown["Group"].tolist()

    with left:
        with st.container(key="card_group_compare"):
            card_title(f"{item['label']} by {group_type.lower()}",
                       "Whiskers show an indicative simple-random-sample margin, not a design-correct confidence "
                       "interval. Differences are descriptive and do not establish significance or causation.")
            margins = [data.moe_pp(v, n) for v, n in zip(shown[metric], shown["Valid respondents"])]
            fig = go.Figure(go.Bar(
                x=shown[metric], y=shown["Group"], orientation="h", marker=dict(color=item["accent"]),
                error_x=dict(type="data", array=margins, color=PALETTE["ink2"], thickness=1.6, width=5),
                text=shown[metric], texttemplate="%{text:.1f}%", textposition="outside",
                textfont=dict(size=12, color=PALETTE["ink"]), cliponaxis=False,
                hovertemplate="<b>%{y}</b><br>Estimate: %{x:.2f}%<extra></extra>"))
            fig.update_layout(bargap=0.34)
            fig.update_xaxes(title=None, ticksuffix="%",
                             range=[0, min(100, float((shown[metric] + pd.Series(margins)).max()) + 14)],
                             gridcolor=PALETTE["grid"], zeroline=False)
            fig.update_yaxes(title=None, showgrid=False, automargin=True, autorange="reversed",
                             categoryorder="array", categoryarray=order)
            st.plotly_chart(style_chart(fig, height, margin=dict(l=4, r=40, t=8, b=4)),
                            use_container_width=True, key="population_groups_chart",
                            config={"displayModeBar": False})

    with right:
        with st.container(key="card_group_sizes"):
            card_title("Who answered",
                       "Unweighted valid respondents per group. Amber bars have a wide worst-case margin.")
            sized = shown.dropna(subset=["Valid respondents"])
            colors = ["#E0A12F" if data.margin_flag(n) == "wide" else "#8FB0C2" for n in sized["Valid respondents"]]
            size_fig = go.Figure(go.Bar(
                x=sized["Valid respondents"], y=sized["Group"], orientation="h", marker=dict(color=colors),
                text=sized["Valid respondents"], texttemplate="%{text:,.0f}", textposition="outside",
                textfont=dict(size=12, color=PALETTE["ink"]), cliponaxis=False,
                hovertemplate="<b>%{y}</b><br>%{x:,.0f} respondents<extra></extra>"))
            size_fig.update_layout(bargap=0.34)
            size_fig.update_xaxes(title=None, range=[0, float(sized["Valid respondents"].max()) * 1.2],
                                  gridcolor=PALETTE["grid"], zeroline=False, tickformat="~s")
            size_fig.update_yaxes(title=None, showgrid=False, automargin=True, autorange="reversed",
                                  categoryorder="array", categoryarray=order)
            st.plotly_chart(style_chart(size_fig, height, margin=dict(l=4, r=40, t=8, b=4)),
                            use_container_width=True, key="population_groups_sizes",
                            config={"displayModeBar": False})
    st.markdown("")

    # ---- Heatmap + widest gap -------------------------------------------------------------
    unique = frame.loc[frame["Group type"].astype(str).eq(group_type)].dropna(subset=["Group"]) \
        .drop_duplicates("Group").set_index("Group").reindex(order)
    items = list(indicators.values())
    real = unique[[it["column"] for it in items]].to_numpy(dtype=float)
    heat_height = max(260, 52 * count + 80)

    heat_col, gap_col = st.columns([1.55, 1], gap="medium")
    with heat_col:
        with st.container(key="card_group_matrix"):
            card_title(f"Every indicator by {group_type.lower()}",
                       "Shading compares groups within each column, so the darkest cell marks the highest "
                       "value; whether that is favourable depends on the indicator.")
            norm = real.copy()
            for j in range(norm.shape[1]):
                col = norm[:, j]
                valid = col[~pd.isna(col)]
                norm[:, j] = (col - valid.min()) / (valid.max() - valid.min()) \
                    if valid.size and valid.max() > valid.min() else 0.5
            heat = go.Figure(go.Heatmap(
                z=norm, x=[it["short"] for it in items], y=order, text=real, texttemplate="%{text:.1f}%",
                textfont=dict(size=13), colorscale=HEAT_SCALE, showscale=False, xgap=4, ygap=4,
                customdata=real, hovertemplate="<b>%{y}</b><br>%{x}: %{customdata:.2f}%<extra></extra>"))
            heat.update_xaxes(side="top", title=None, showgrid=False, tickfont=dict(size=13))
            heat.update_yaxes(title=None, autorange="reversed", showgrid=False, automargin=True)
            st.plotly_chart(style_chart(heat, heat_height, margin=dict(l=4, r=8, t=8, b=4)),
                            use_container_width=True, key="population_groups_matrix",
                            config={"displayModeBar": False})
    with gap_col:
        with st.container(key="card_group_gaps"):
            card_title("Which indicator has the widest gap?",
                       f"Highest minus lowest {group_type.lower()} group, per indicator.")
            gaps = []
            for it in items:
                vals = unique[it["column"]].dropna()
                if not vals.empty:
                    gaps.append((it["short"], float(vals.max() - vals.min()), it["accent"]))
            gaps.sort(key=lambda g: g[1])
            gap_fig = go.Figure(go.Bar(
                x=[g[1] for g in gaps], y=[g[0] for g in gaps], orientation="h",
                marker=dict(color=[g[2] for g in gaps]), text=[g[1] for g in gaps],
                texttemplate="%{text:.1f} pp", textposition="outside",
                textfont=dict(size=13, color=PALETTE["ink"]), cliponaxis=False,
                hovertemplate="<b>%{y}</b><br>Gap: %{x:.2f} pp<extra></extra>"))
            gap_fig.update_layout(bargap=0.4)
            gap_fig.update_xaxes(title=None, ticksuffix=" pp",
                                 range=[0, max(g[1] for g in gaps) * 1.3 if gaps else 1],
                                 gridcolor=PALETTE["grid"], zeroline=False)
            gap_fig.update_yaxes(title=None, showgrid=False, automargin=True)
            st.plotly_chart(style_chart(gap_fig, heat_height, margin=dict(l=4, r=40, t=8, b=4)),
                            use_container_width=True, key="population_groups_gaps",
                            config={"displayModeBar": False})
    st.markdown("")

    # ---- Table -----------------------------------------------------------------------------
    with st.container(key="card_group_table"):
        card_title("Detailed results",
                   "Every indicator for each group. The selected-indicator margin is an illustrative "
                   "simple-random-sample calculation, not a design-correct uncertainty interval.")
        table = shown[["Group", "Valid respondents"]].copy()
        table["Margin (±pp)"] = [round(data.moe_pp(v, n), 1) for v, n in zip(shown[metric], shown["Valid respondents"])]
        for it in items:
            table[it["short"]] = unique[it["column"]].reindex(table["Group"]).to_numpy()
        table = table.rename(columns={"Group": group_type, "Valid respondents": "Valid respondents (n)"})
        table["Valid respondents (n)"] = table["Valid respondents (n)"].astype("Int64")
        config = {
            "Valid respondents (n)": st.column_config.NumberColumn("Respondents (n)", format="%d"),
            "Margin (±pp)": st.column_config.NumberColumn(f"Margin for {item['short']} (±pp)", format="%.1f"),
        }
        for it in items:
            config[it["short"]] = st.column_config.ProgressColumn(it["short"], format="%.1f%%",
                                                                  min_value=0, max_value=100)
        st.dataframe(table, hide_index=True, use_container_width=True, column_config=config,
                     height=min(440, 44 + 36 * len(table)))
        st.download_button("Download comparison (CSV)",
                           data=table.round(2).to_csv(index=False).encode("utf-8"),
                           file_name=f"population_groups_{group_type.lower().replace(' ', '_')}.csv",
                           mime="text/csv", key="population_groups_download", icon=":material/download:")
        if mode == "Combined":
            scope_copy = {
                "Gender": "NBR reports some measures by gender. Each series below keeps NBR's own units and is not "
                          "comparable with the FinScope percentages above.",
                "Age group": "NBR reports Youth and Non-Youth only, which does not map to FinScope age groups. "
                             "This comparison uses FinScope alone.",
                "Education": "NBR has no education breakdown. This comparison uses FinScope alone.",
                "Area": "NBR has no urban/rural breakdown. This comparison uses FinScope alone.",
            }[group_type]
            note("NBR context for this comparison", scope_copy, tone="info")
            if group_type == "Gender":
                for subgroup in shown["Group"].astype(str):
                    render_combined_context(
                        item["variable"],
                        subgroup_type="Gender",
                        subgroup=subgroup,
                    )
    st.markdown("")

    note("About this indicator", item["interpretation"])
    wide = [str(r["Group"]) for _, r in subset.iterrows() if data.margin_flag(r["Valid respondents"]) == "wide"]
    if wide:
        st.markdown("")
        note("Read small groups with care",
             f"{', '.join(wide)} {'has' if len(wide) == 1 else 'have'} a small number of respondents, so the "
             "estimate is indicative only. Interpret differences involving these groups with additional caution.",
             tone="warn")
    render_html('<div class="src-note">Source: FinScope Rwanda 2024. Percentages are weighted survey estimates; '
                "respondent counts are unweighted valid sample sizes. Margins are indicative (simple random "
                "sampling) and understate design-based uncertainty. NBR context is not combined with these estimates; "
                "Education is FinScope-only. Differences alone do not establish causation.</div>")
