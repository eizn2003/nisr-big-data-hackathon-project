import itertools

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src import data
from src.briefs import district_brief
from src.indicators import BY_COLUMN, BY_NATIONAL, PRIORITY_CANDIDATES
from src.pages.national_overview import _district_family_figure
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
    style_chart,
)

KEY_DISTRICT = "priority_explorer_district"
KEY_SHOW = "priority_explorer_show"
KEY_COMPS = "priority_explorer_components"
KEY_DEFF = "priority_explorer_deff"
SHOW_OPTIONS = ["Top 10", "Top 15", "All districts"]
DEFF_OPTIONS = {
    "Simple random sample (×1.0)": 1.0,
    "Moderate clustering (×1.5)": 1.5,
    "Strong clustering (×2.0)": 2.0,
}
CANDIDATES = {it["short"]: it for it in PRIORITY_CANDIDATES}
BASELINE_COMPONENTS = tuple(it["short"] for it in PRIORITY_CANDIDATES if it["priority_default"])
DEFAULT_COMPONENTS = list(BASELINE_COMPONENTS)
TOP_N_STABILITY = 10


# --------------------------------------------------------------------------
# Scoring (same method as before, generalised to user-selected components)
# --------------------------------------------------------------------------
def build_scores(districts, nat, components, deff):
    """Score districts on the chosen components using comparative gap points.

    For each candidate indicator the gap is measured in the direction that
    signals a need (below national for positive indicators, above national for
    vulnerability indicators), floored at zero, and scaled by the largest gap
    among districts. The score is the equal-weight mean of the chosen components.
    It is a relative 0–100 point scale, not a percentage or an estimate of need.
    """
    df = districts.copy()
    for item in PRIORITY_CANDIDATES:
        col = item["column"]
        national_value = float(nat[item["national"]])
        df[col] = pd.to_numeric(df[col], errors="coerce")
        raw = national_value - df[col] if item["polarity"] == "positive" else df[col] - national_value
        gap = raw.clip(lower=0)
        top = gap.max()
        df[f"gap::{col}"] = gap
        df[f"norm::{col}"] = gap / top * 100 if top and top > 0 else 0.0
        margin = pd.Series([data.moe_pp(v, n, deff) for v, n in zip(df[col], df["Valid respondents"])],
                           index=df.index)
        df[f"moe::{col}"] = margin
        df[f"signal::{col}"] = (gap > margin) & gap.notna()

    chosen = [CANDIDATES[s]["column"] for s in components]
    norm_cols = [f"norm::{c}" for c in chosen]
    df["Priority score"] = df[norm_cols].mean(axis=1, skipna=False)
    for item_col in chosen:
        df[f"contrib::{item_col}"] = df[f"norm::{item_col}"] / len(chosen)
    df["Indicators available"] = df[[f"gap::{c}" for c in chosen]].notna().sum(axis=1)
    df["Screening status"] = np.where(df["Indicators available"] == len(chosen), "Complete", "Incomplete evidence")
    df["Gaps exceeding district-only margin"] = df[[f"signal::{c}" for c in chosen]].sum(axis=1).astype(int)

    # robustness: rank under every combination of 2+ candidate indicators
    all_cols = [it["column"] for it in PRIORITY_CANDIDATES]
    combos = [c for r in range(2, len(all_cols) + 1) for c in itertools.combinations(all_cols, r)]
    ranks = pd.DataFrame(index=df.index)
    for i, combo in enumerate(combos):
        score = df[[f"norm::{c}" for c in combo]].mean(axis=1, skipna=False)
        ranks[i] = score.rank(ascending=False, method="min")
    df["Best rank"] = ranks.min(axis=1)
    df["Worst rank"] = ranks.max(axis=1)
    df["Top-10 combos"] = (ranks <= TOP_N_STABILITY).sum(axis=1)
    return df, len(combos)


def _stability_label(k, m):
    if k >= round(0.8 * m):
        return "Consistently high"
    if k == 0:
        return "Not in the top 10"
    return "Sensitive to indicator choice"


# --------------------------------------------------------------------------
# UI helpers
# --------------------------------------------------------------------------
def _meter_pos(value, lo, hi):
    if hi <= lo:
        return 50.0
    return max(3.0, min(97.0, (value - lo) / (hi - lo) * 100))


def _jump_to(name):
    st.session_state[KEY_DISTRICT] = name


def _evidence_html(row, nat, frame, item, deff):
    col = item["column"]
    national_value = float(nat[item["national"]])
    value = row[col]
    lo, hi = float(frame[col].min()), float(frame[col].max())
    explanation = ("Lower than the national estimate signals a gap" if item["polarity"] == "positive"
                   else "Higher than the national estimate signals a gap")
    if pd.isna(value):
        return (f'<div class="ev" style="--accent:{item["accent"]}"><div class="ev-top">'
                f'<div class="ev-name"><i></i>{esc(item["label"])}</div><span class="ev-chip na">Estimate unavailable</span>'
                f"</div></div>")
    value = float(value)
    gap = float(row[f"gap::{col}"])
    margin = float(row[f"moe::{col}"])
    if gap <= 0:
        chip = '<span class="ev-chip ok">At or better than national</span>'
    elif gap > margin:
        chip = '<span class="ev-chip flag">Gap exceeds district-only illustrative margin</span>'
    else:
        chip = '<span class="ev-chip na">Gap within district-only illustrative margin</span>'
    return f"""
    <div class="ev" style="--accent:{item['accent']}">
      <div class="ev-top"><div class="ev-name"><i></i>{esc(item['label'])}</div>{chip}</div>
      <div class="ev-why">{explanation}</div>
      <div class="ev-nums">
        <div><b>{value:.1f}%</b><span>{esc(row['District'])} · district-only ±{margin:.1f} pp</span></div>
        <div><b>{national_value:.1f}%</b><span>National</span></div>
        <div><b>{gap:.1f} pp</b><span>Gap toward priority</span></div>
      </div>
      <div class="meter"><div class="meter-track"></div>
        <div class="meter-mark" style="left:{_meter_pos(national_value, lo, hi):.1f}%">National</div>
        <div class="meter-dot" style="left:{_meter_pos(value, lo, hi):.1f}%"></div></div>
      <div class="meter-ends"><span>Lowest district {lo:.1f}%</span><span>Highest {hi:.1f}%</span></div>
    </div>
    """


def _donut(row, components):
    items = [CANDIDATES[s] for s in components]
    values = [float(row[f"contrib::{it['column']}"]) for it in items]
    score = float(row["Priority score"])
    if sum(values) <= 0:
        pie = go.Pie(labels=["No gap above national"], values=[1], hole=0.7, marker=dict(colors=["#E4EBEE"]),
                     textinfo="none", hoverinfo="skip", showlegend=False)
    else:
        pie = go.Pie(labels=[it["label"] for it in items], values=values, hole=0.7, sort=False,
                     marker=dict(colors=[it["accent"] for it in items], line=dict(color="#FFFFFF", width=3)),
                     textinfo="none", direction="clockwise", showlegend=False,
                     hovertemplate="<b>%{label}</b><br>%{value:.1f} of 100 points<extra></extra>")
    fig = go.Figure(pie)
    fig.add_annotation(text=f"<b style='font-size:34px'>{score:.1f}</b><br>"
                            f"<span style='font-size:12px;color:{PALETTE['muted']}'>relative points</span>",
                       showarrow=False, font=dict(color=PALETTE["ink"], size=16))
    return style_chart(fig, 280, margin=dict(l=4, r=4, t=4, b=4))


def _ranking_figure(ranked, selected_district, show, components):
    pool = ranked.head(10) if show == "Top 10" else ranked.head(15) if show == "Top 15" else ranked
    if selected_district not in pool["District"].values:
        pool = pd.concat([pool, ranked.loc[ranked["District"].eq(selected_district)]])
    chart = pool.sort_values("Priority score", ascending=True)
    is_sel = chart["District"].eq(selected_district)
    fig = go.Figure()
    for short in components:
        it = CANDIDATES[short]
        fig.add_bar(y=chart["District"], x=chart[f"contrib::{it['column']}"], orientation="h", name=it["label"],
                    marker=dict(color=it["accent"],
                                line=dict(color=[PALETTE["sun"] if v else "#FFFFFF" for v in is_sel],
                                          width=[3 if v else 0.6 for v in is_sel])),
                    hovertemplate="<b>%{y}</b><br>" + it["label"] + ": %{x:.1f} points<extra></extra>")
    fig.add_trace(go.Scatter(x=chart["Priority score"], y=chart["District"], mode="text",
                             text=[f"{v:.1f}" for v in chart["Priority score"]], textposition="middle right",
                             textfont=dict(size=12, color=PALETTE["ink"]), hoverinfo="skip",
                             showlegend=False, cliponaxis=False))
    fig.update_layout(barmode="stack", bargap=0.3)
    fig.update_xaxes(title="Relative screening points (0–100)",
                     range=[0, min(100, float(chart["Priority score"].max()) + 10)],
                     gridcolor=PALETTE["grid"], zeroline=False)
    fig.update_yaxes(title=None, showgrid=False, tickfont=dict(size=11.5))
    return style_chart(fig, max(380, 34 * len(chart) + 70), margin=dict(l=4, r=24, t=34, b=4))


def _stability_figure(ranked, selected_district, combos):
    top = ranked.head(15)
    if selected_district not in top["District"].values:
        top = pd.concat([top, ranked.loc[ranked["District"].eq(selected_district)]])
    top = top.sort_values("Rank")
    fig = go.Figure()
    for _, r in top.iterrows():
        fig.add_trace(go.Scatter(x=[r["Best rank"], r["Worst rank"]], y=[r["District"]] * 2, mode="lines",
                                 line=dict(color="#CBD8DD", width=7), hoverinfo="skip", showlegend=False))
    is_sel = top["District"].eq(selected_district)
    fig.add_trace(go.Scatter(
        x=top["Rank"], y=top["District"], mode="markers", showlegend=False,
        marker=dict(size=15, color=[PALETTE["sun"] if v else PALETTE["ink2"] for v in is_sel],
                    line=dict(color="#FFFFFF", width=2.5)),
        customdata=np.stack([top["Best rank"], top["Worst rank"], top["Top-10 combos"]], axis=-1),
        hovertemplate=f"<b>%{{y}}</b><br>Rank with chosen indicators: %{{x:.0f}}<br>"
                      f"Range across {combos} combinations: %{{customdata[0]:.0f}} to %{{customdata[1]:.0f}}<br>"
                      f"Top 10 in %{{customdata[2]:.0f}} of {combos}<extra></extra>"))
    fig.update_xaxes(title="Rank (1 = largest relative gaps)", range=[0, max(31, float(top["Worst rank"].max()) + 2)],
                     gridcolor=PALETTE["grid"], zeroline=False, dtick=5)
    fig.update_yaxes(title=None, showgrid=False, autorange="reversed", tickfont=dict(size=11.5))
    return style_chart(fig, max(380, 30 * len(top) + 80), margin=dict(l=4, r=20, t=10, b=4))


# --------------------------------------------------------------------------
# Page
# --------------------------------------------------------------------------
def render_priority_explorer():
    try:
        districts = data.load_district()
        national = data.load_national()
        nat = dict(zip(national["Indicator"], national["Estimate (%)"].astype(float)))
        missing = [it["national"] for it in PRIORITY_CANDIDATES if it["national"] not in nat
                   or it["column"] not in districts.columns]
        if missing:
            raise ValueError("Missing data for: " + ", ".join(missing))
    except (FileNotFoundError, ValueError, KeyError) as error:
        st.error("Could not load the priority analysis data.")
        st.caption(str(error))
        return

    chosen = st.session_state.get(KEY_COMPS) or DEFAULT_COMPONENTS
    too_few = len(chosen) < 2
    components = DEFAULT_COMPONENTS if too_few else [s for s in CANDIDATES if s in chosen]
    deff = DEFF_OPTIONS.get(st.session_state.get(KEY_DEFF), 1.0)

    baseline_scored, combos = build_scores(districts, nat, BASELINE_COMPONENTS, deff)
    if tuple(components) == BASELINE_COMPONENTS:
        scored = baseline_scored
    else:
        scored, _ = build_scores(districts, nat, components, deff)
    baseline = baseline_scored.loc[baseline_scored["Screening status"].eq("Complete")].copy()
    baseline = baseline.sort_values("Priority score", ascending=False).reset_index(drop=True)
    baseline_total = len(baseline)
    baseline_by_district = baseline.set_index("District")[["Priority score"]].rename(
        columns={"Priority score": "Baseline score"})
    baseline_by_district["Baseline rank"] = (
        baseline_by_district["Baseline score"].rank(ascending=False, method="min").astype(int))

    ranked = scored.loc[scored["Screening status"].eq("Complete")].copy()
    if ranked.empty:
        st.warning("There are no districts with complete indicator data.")
        return
    ranked = ranked.sort_values("Priority score", ascending=False).reset_index(drop=True)
    ranked = ranked.join(baseline_by_district, on="District")
    ranked["Rank"] = ranked["Priority score"].rank(ascending=False, method="min").astype(int)
    total = len(ranked)

    names = ranked["District"].tolist()
    st.session_state.setdefault(KEY_DISTRICT, names[0])
    if st.session_state[KEY_DISTRICT] not in names:
        st.session_state[KEY_DISTRICT] = names[0]
    selected_district = st.session_state[KEY_DISTRICT]
    sel = ranked.loc[ranked["District"].eq(selected_district)].iloc[0]
    score = float(sel["Priority score"])
    baseline_score = float(sel["Baseline score"])
    k = int(sel["Top-10 combos"])

    contribs = {s: float(sel[f"contrib::{CANDIDATES[s]['column']}"]) for s in components}
    driver = max(contribs, key=contribs.get)
    if score > 0:
        driver_html = f'<span style="font-size:25px">{esc(driver)}</span>'
        driver_fill, driver_src = contribs[driver] / score * 100, f"<b>{contribs[driver] / score * 100:.0f}%</b> of the score"
    else:
        driver_html, driver_fill, driver_src = '<span style="font-size:25px">None</span>', 0, "No gap above national"

    # ---- Hero ---------------------------------------------------------------
    page_header(
        "Priority explorer",
        "Compare district-level access and resilience gaps, explore what drives them, and identify where "
        "further investigation may be useful before investment decisions.",
        pill="Decision-support screening · FinScope Rwanda 2024",
        size="tall",
        below_html=kpi_grid([
            kpi_card("Baseline score", f"{baseline_score:.1f}", "relative points",
                     baseline_score, PALETTE["sun"],
                     f"<b>{esc(selected_district)}</b> · baseline rank {int(sel['Baseline rank'])} of {baseline_total}"),
            kpi_card("What-if scenario rank", f"#{int(sel['Rank'])}", f" of {total}",
                     (total - int(sel["Rank"]) + 1) / total * 100, PALETTE["ink2"],
                     f"Scenario score: {score:.1f} relative points"),
            kpi_card("Largest scenario driver", driver_html, "", driver_fill,
                     CANDIDATES[driver]["accent"], driver_src),
            kpi_card("Top-10 sensitivity", f"{k}/{combos}", "", k / combos * 100, "#5FB8AB",
                     f"Top 10 across {k} of {combos} indicator combinations"),
        ]),
    )
    st.markdown("")
    note("About the screening score",
         "The fixed baseline equally averages four normalized gaps: bank-account ownership and current "
         "registered mobile-money use (access/use), plus not saving and emergency funds (resilience). Each "
         "district is compared with the national survey estimate, which is a descriptive reference, not a policy "
         "target. Scores are relative points (not percentages, probabilities, or counts of people in need). "
         "Use them to identify where to investigate, not as a stand-alone investment allocation or proof of cause.",
         tone="info")
    st.caption(
        "**For investment planning:** Survey respondent counts are sample sizes, not beneficiaries. "
        "Estimate potential reach using current district population, service availability, and intervention "
        "eligibility, then validate locally."
    )
    st.markdown("")

    # ---- Controls -----------------------------------------------------------------
    with st.container(key="card_controls"):
        c1, c2 = st.columns([1.2, 2.2], gap="large", vertical_alignment="bottom")
        with c1:
            st.selectbox("Explore a district", names, key=KEY_DISTRICT)
        with c2:
            st.pills("What-if scenario indicators (baseline remains fixed)", list(CANDIDATES.keys()),
                     selection_mode="multi", default=DEFAULT_COMPONENTS, key=KEY_COMPS)
        c3, c4 = st.columns([1.2, 2.2], gap="large", vertical_alignment="bottom")
        with c3:
            show = st.segmented_control("Districts shown in the ranking", SHOW_OPTIONS,
                                        default=SHOW_OPTIONS[1], key=KEY_SHOW) or SHOW_OPTIONS[1]
        with c4:
            st.segmented_control("Illustrative margin assumption (not a significance test)", list(DEFF_OPTIONS.keys()),
                                 default=list(DEFF_OPTIONS.keys())[0], key=KEY_DEFF)
    if too_few:
        st.warning("A what-if scenario needs at least two indicators. Showing the fixed four-indicator baseline.")
    if tuple(components) != BASELINE_COMPONENTS:
        note("What-if scenario",
             f"The ranking below uses {', '.join(components)} with equal indicator weights. It is a scenario "
             "comparison; the fixed four-indicator baseline score and rank above remain unchanged.",
             tone="info")
    st.markdown("")

    # ---- Evidence + composition ---------------------------------------------------------
    left, right = st.columns([1.45, 1], gap="medium")
    with left:
        with st.container(key="card_priority_evidence"):
            card_title(f"Why {selected_district} appears on the screen",
                       "The selected scenario indicators against the national estimate. The yellow dot is this district; "
                       "the tick is the national level.")
            for s in components:
                render_html(_evidence_html(sel, nat, ranked, CANDIDATES[s], deff))
            borrow = BY_COLUMN["Borrowed in the past 12 months (%)"]
            if borrow["column"] in ranked.columns and borrow["national"] in nat:
                render_html(
                    f'<div class="micro">Supporting evidence, not scored: {esc(selected_district)} borrowing '
                    f"{float(sel[borrow['column']]):.1f}% vs {nat[borrow['national']]:.1f}% nationally. "
                    "Borrowing is not treated as inherently good or bad.</div>")
    with right:
        with st.container(key="card_priority_drivers"):
            card_title("What drives the score",
                       "Indicators have equal weight; their point contributions vary with the observed gaps.")
            st.plotly_chart(_donut(sel, components), use_container_width=True, key="priority_donut",
                            config={"displayModeBar": False})
            legend = "".join(
                f'<div class="gap" style="margin-bottom:8px"><span><i style="display:inline-block;width:9px;'
                f'height:9px;border-radius:50%;background:{CANDIDATES[s]["accent"]};margin-right:7px"></i>'
                f'{esc(CANDIDATES[s]["label"])}</span><b>{contribs[s]:.1f} pts</b></div>' for s in components)
            render_html(legend)
            beyond = int(sel["Gaps exceeding district-only margin"])
            render_html(f'<div class="rank-hint">{beyond} of {len(components)} gaps exceed the district-only '
                        "illustrative margin. This is not a test of the difference from the national estimate: "
                        "the survey design is unavailable, and the two estimates are not independent. Scores "
                        "are not percentages or counts of people in need.</div>")
    st.markdown("")

    # ---- Barriers for this district --------------------------------------------------------
    barriers = data.load_barriers_district()
    if barriers is not None and selected_district in set(barriers["District"]):
        rows = barriers.loc[barriers["District"].eq(selected_district)]
        base = int(rows["District non-account respondents"].iloc[0])
        fam = data.barrier_family_shares(rows).set_index("Barrier family")["Weighted share (%)"]
        need = fam.get("No need or too little income", 0.0)
        other = fam.drop(labels=["No need or too little income", "Other"], errors="ignore").sort_values(ascending=False)
        with st.container(key="card_priority_barriers"):
            b1, b2 = st.columns([1.1, 1], gap="large")
            with b1:
                card_title(f"What people without an account say in {selected_district}",
                           f"Reasons given by {base:,} respondents without a bank account (weighted shares).")
                render_html(
                    f'<p class="mc-p" style="font-size:14.5px"><b>{need:.1f}%</b> say they do not need an account or '
                    f"that their income is too limited to justify one. Among the other reasons, "
                    f"<b>{other.index[0].lower()} ({other.iloc[0]:.1f}%)</b> is the largest"
                    + (f", followed by <b>{other.index[1].lower()} ({other.iloc[1]:.1f}%)</b>" if len(other) > 1 else "")
                    + ".</p>"
                    '<div class="micro">This helps match the response to the barrier: where income is the main '
                    "constraint, product design and livelihoods may matter more than branch coverage. Read as an "
                    "indication, not a causal diagnosis.</div>")
            with b2:
                st.plotly_chart(_district_family_figure(rows), use_container_width=True,
                                key="priority_barrier_chart", config={"displayModeBar": False})
        st.markdown("")

    # ---- Ranking + top five ---------------------------------------------------------------------
    rank_col, top_col = st.columns([1.6, 1], gap="medium")
    with rank_col:
        with st.container(key="card_priority_ranking"):
            card_title("What-if scenario ranking",
                       "Bars show the chosen indicators' contributions to the scenario score. "
                       "Baseline rank is shown separately in the results table.")
            st.plotly_chart(_ranking_figure(ranked, selected_district, show, components), use_container_width=True,
                            key="priority_explorer_ranking", config={"displayModeBar": False})
    with top_col:
        with st.container(key="card_priority_top"):
            card_title("Highest scenario scores",
                       "These districts have the largest relative gaps under the selected what-if indicators.")
            for _, r in ranked.head(5).iterrows():
                st.button(f"{int(r['Rank'])}  ·  {r['District']}  ·  {r['Priority score']:.1f}",
                          key=f"pe_jump_{r['District']}", on_click=_jump_to, args=(r["District"],),
                          use_container_width=True)
            render_html(
                '<div class="build"><b>How the score is built.</b><br>For each chosen indicator, the gap to the '
                "national estimate is measured in the direction that signals a gap (below national for positive "
                "indicators; above national for not saving). Each gap is floored at zero, scaled against the "
                "largest district gap for that indicator, then averaged equally. This is a relative point score; "
                "it does not measure absolute need, population reach, or investment return. Indicator choice "
                "changes the scenario ranking, not the fixed baseline.</div>")
            st.download_button(
                "Download district profile",
                data=district_brief(
                    selected_district, districts, nat, barriers=barriers,
                    priority=dict(score=score, rank=int(sel["Rank"]), total=total,
                                  baseline_score=baseline_score, baseline_rank=int(sel["Baseline rank"]),
                                  baseline_total=baseline_total, components=components,
                                  robust_text=f"Top 10 across {k} of {combos} indicator combinations "
                                              f"({_stability_label(k, combos).lower()}); this is sensitivity to "
                                              "indicator choice, not a probability.",
                                  drivers=", ".join(f"{s} {v:.1f} pts" for s, v in
                                                    sorted(contribs.items(), key=lambda x: -x[1])))),
                file_name=f"{selected_district.lower().replace(' ', '_')}_priority_profile.md",
                mime="text/markdown", key="pe_brief", use_container_width=True, icon=":material/description:")
    st.markdown("")

    # ---- Stability ----------------------------------------------------------------------------------
    with st.container(key="card_priority_stability"):
        card_title("How stable is each district's rank?",
                   f"The bar spans the best and worst rank across all {combos} combinations of two or more "
                   "candidate indicators. The dot is the rank under your current what-if scenario.")
        st.plotly_chart(_stability_figure(ranked, selected_district, combos), use_container_width=True,
                        key="priority_stability", config={"displayModeBar": False})
        render_html('<div class="micro">The bar is a rank range, not a confidence interval. A district ranked in '
                    "the top 10 across many combinations is less sensitive to indicator choice; a wide range or "
                    "low top-10 frequency means its position is more choice-sensitive. This is not a probability "
                    "that the district needs investment.</div>")
    st.markdown("")

    # ---- Table -----------------------------------------------------------------------------------------
    with st.container(key="card_priority_table"):
        card_title("Scenario results with fixed-baseline comparison",
                   "Scenario rank follows the selected indicators. Baseline rank always uses the four documented "
                   "access/use and resilience indicators; sample counts are not population totals.")
        table = ranked[["Rank", "District", "Priority score", "Baseline rank", "Baseline score",
                        "Best rank", "Worst rank", "Top-10 combos", "Valid respondents"]].copy()
        table = table.rename(columns={
            "Rank": "Scenario rank",
            "Priority score": "Scenario score (points)",
            "Baseline score": "Baseline score (points)",
            "Valid respondents": "Survey respondents (n)",
        })
        table["Stability"] = [_stability_label(v, combos) for v in table["Top-10 combos"]]
        table["Rank range across indicator sets"] = (
            table["Best rank"].astype(int).astype(str) + "–" + table["Worst rank"].astype(int).astype(str))
        table["Top-10 indicator sets"] = table["Top-10 combos"].astype(int).astype(str) + f" of {combos}"
        table["Gaps exceeding district-only illustrative margin"] = (
            ranked["Gaps exceeding district-only margin"].astype(int))
        for short, it in CANDIDATES.items():
            table[short] = ranked[it["column"]].round(2)
        table["Scenario score (points)"] = table["Scenario score (points)"].round(1)
        table["Baseline score (points)"] = table["Baseline score (points)"].round(1)
        table = table.drop(columns=["Best rank", "Worst rank", "Top-10 combos"])
        cfg = {
            "Scenario score (points)": st.column_config.ProgressColumn(
                "Scenario score (relative points)", format="%.1f", min_value=0, max_value=100),
            "Baseline score (points)": st.column_config.ProgressColumn(
                "Baseline score (relative points)", format="%.1f", min_value=0, max_value=100),
            "Survey respondents (n)": st.column_config.NumberColumn("Survey sample n", format="%d"),
            "Gaps exceeding district-only illustrative margin": st.column_config.NumberColumn(
                f"District-only margin flags (of {len(components)})", format="%d"),
        }
        for short in CANDIDATES:
            cfg[short] = st.column_config.ProgressColumn(short, format="%.1f%%", min_value=0, max_value=100)
        st.dataframe(table, hide_index=True, use_container_width=True, height=440, column_config=cfg)
        download_table = table.copy()
        download_table.insert(0, "Scenario indicators", ", ".join(components))
        download_table.insert(1, "Fixed baseline indicators", ", ".join(BASELINE_COMPONENTS))
        download_table.insert(
            2, "Score interpretation",
            "Relative normalized gap points; not population need, probability, target attainment, or investment advice")
        download_table.insert(
            3, "Population reach",
            "Not estimated. Respondent counts are sample sizes, not beneficiaries; use current district population, "
            "service availability, intervention eligibility, costs, and local validation before estimating reach or returns.")
        st.download_button("Download priority screening results (CSV)",
                           data=download_table.to_csv(index=False).encode("utf-8"),
                           file_name="district_priority_screening.csv", mime="text/csv",
                           key="priority_explorer_download", icon=":material/download:")

    render_html('<div class="src-note">Source: FinScope Rwanda 2024. Respondent counts are unweighted sample sizes; '
                "indicator percentages are weighted estimates. The fixed baseline equally weights four normalized "
                "gaps across access/use and resilience; the what-if score equally weights only its selected indicators. "
                "Scores are relative points, not percentages, population counts, or investment recommendations. "
                "Margins are district-only illustrative binomial margins with an optional design-effect assumption; "
                "the survey design is unavailable, so these do not test the district-versus-national difference or "
                "support formal significance claims. Validate current population reach, costs, service availability, "
                "and local context before investment decisions.</div>")
