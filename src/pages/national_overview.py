import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from pymongo.errors import PyMongoError

from src import data
from src.indicators import BY_COLUMN, CORE, REGISTRY
from src.pages.district_explorer import build_map
from src.styles import (
    PALETTE,
    badge,
    card_title,
    esc,
    note,
    page_header,
    render_html,
    section_title,
    show_district_table,
    style_chart,
)


def _open_district_explorer():
    st.session_state["main_nav"] = "District explorer"


# --------------------------------------------------------------------------
# Hero KPIs (core four indicators)
# --------------------------------------------------------------------------
def _kpi_html(national, context=None):
    """Headline cards. `context` maps a FinScope variable to a compact NBR strip (Combined mode)."""
    context = context or {}
    cards = []
    for item in CORE:
        row = national.loc[national["Indicator"].eq(item["national"])]
        if row.empty:
            continue
        row = row.iloc[0]
        value = float(row["Estimate (%)"])
        cards.append(
            f"""
            <div class="kpi" style="--accent:{item['accent']}">
              <div class="kpi-label"><i></i><span>{esc(item['kpi_label'])}</span></div>
              <div class="kpi-value">{value:.1f}<small>%</small></div>
              <div class="kpi-track"><div class="kpi-fill" style="width:{min(value, 100):.1f}%"></div></div>
              <div class="kpi-src">Share of adults · FinScope 2024</div>
              {context.get(item["variable"], "")}
            </div>
            """
        )
    return f'<div class="kpi-grid">{"".join(cards)}</div>'


# --------------------------------------------------------------------------
# What stands out
# --------------------------------------------------------------------------
def _insights_html(nat, district, urban_rural):
    cards = []

    bank, mobile = nat.get("Own bank account"), nat.get("Registered mobile-money user")
    if bank is not None and mobile is not None:
        lead = mobile - bank
        cards.append((BY_COLUMN["Registered mobile-money user (%)"], "Two ways in",
                      f"{abs(lead):.1f}<small>pp</small>",
                      f"Active mobile-money registration ({mobile:.1f}%) is well ahead of "
                      f"bank-account ownership ({bank:.1f}%)." if lead >= 0 else
                      f"Bank-account ownership ({bank:.1f}%) is ahead of mobile money ({mobile:.1f}%)."))

    group, emergency = nat.get("Saves with a group"), nat.get("Has emergency funds")
    if group is not None and emergency is not None:
        cards.append((BY_COLUMN["Has emergency funds (%)"], "Saving without a safety net",
                      f"{emergency:.1f}<small>%</small>",
                      f"have emergency funds, while <b>{group:.1f}%</b> save with a group. "
                      "Saving is common; a buffer for shocks is not."))

    metrics = [i for i in CORE if i["column"] in urban_rural.columns]
    by_area = urban_rural.set_index("Area")
    if {"Urban", "Rural"} <= set(by_area.index) and metrics:
        gaps = {i["column"]: float(by_area.loc["Urban", i["column"]] - by_area.loc["Rural", i["column"]])
                for i in metrics}
        widest = max(gaps, key=lambda c: abs(gaps[c]))
        item = BY_COLUMN[widest]
        cards.append((item, "Urban and rural",
                      f"{abs(gaps[widest]):.1f}<small>pp</small>",
                      f"Widest urban-rural gap is in <b>{item['label'].lower()}</b> "
                      f"(urban {by_area.loc['Urban', widest]:.1f}% vs rural {by_area.loc['Rural', widest]:.1f}%)."))

    col = "Owns a bank account (%)"
    item = BY_COLUMN[col]
    low, high = district.loc[district[col].idxmin()], district.loc[district[col].idxmax()]
    cards.append((item, "Across districts", f"{high[col] - low[col]:.1f}<small>pp</small>",
                  f"{item['label']} runs from <b>{low[col]:.1f}%</b> in {esc(low['District'])} "
                  f"to <b>{high[col]:.1f}%</b> in {esc(high['District'])}."))

    html = "".join(
        f"""
        <div class="ins" style="--accent:{it['accent']};--accent-text:{it['text_accent']}">
          <div class="ins-k">{esc(kicker)}</div><div class="ins-v">{value}</div><div class="ins-t">{text}</div>
        </div>
        """
        for it, kicker, value, text in cards
    )
    return f'<div class="ins-grid">{html}</div>'


# --------------------------------------------------------------------------
# Saving landscape
# --------------------------------------------------------------------------
LANDSCAPE = [
    "Saves with a group", "Currently uses a savings group", "Currently uses Umurenge SACCO",
    "Has emergency funds", "Does not save", "Own bank account",
]


def _landscape_figure(nat):
    rows = [(BY_COLUMN_BY_NATIONAL[name], nat[name]) for name in LANDSCAPE if name in nat]
    rows.sort(key=lambda r: r[1])
    fig = go.Figure(go.Bar(
        x=[v for _, v in rows], y=[it["label"] for it, _ in rows], orientation="h",
        marker=dict(color=[it["accent"] for it, _ in rows]),
        text=[v for _, v in rows], texttemplate="%{text:.1f}%", textposition="outside",
        textfont=dict(size=13, color=PALETTE["ink"]), cliponaxis=False,
        hovertemplate="<b>%{y}</b><br>%{x:.2f}% of adults<extra></extra>",
    ))
    fig.update_layout(bargap=0.36)
    fig.update_xaxes(range=[0, min(100, max(v for _, v in rows) + 12)], ticksuffix="%", title=None,
                     gridcolor=PALETTE["grid"], zeroline=False)
    fig.update_yaxes(title=None, showgrid=False, automargin=True, tickfont=dict(size=13, color=PALETTE["ink"]))
    return style_chart(fig, 380, margin=dict(l=4, r=30, t=8, b=4))


BY_COLUMN_BY_NATIONAL = {it["national"]: it for it in REGISTRY}


# --------------------------------------------------------------------------
# Urban / rural
# --------------------------------------------------------------------------
def _grouped_bars(urban_rural, nat, items):
    by_area = urban_rural.set_index("Area")
    labels = [it["short"] for it in items]
    series = [
        ("Urban", [float(by_area.loc["Urban", it["column"]]) for it in items], PALETTE["ink2"]),
        ("Rural", [float(by_area.loc["Rural", it["column"]]) for it in items], "#5FB8AB"),
    ]
    nat_values = [nat.get(it["national"]) for it in items]
    if all(v is not None for v in nat_values):
        series.append(("National", nat_values, "#B4C3CA"))
    fig = go.Figure()
    for name, values, color in series:
        fig.add_bar(x=labels, y=values, name=name, marker=dict(color=color),
                    text=values, texttemplate="%{text:.1f}%", textposition="outside",
                    textfont=dict(size=11.5, color=PALETTE["ink"]), cliponaxis=False,
                    hovertemplate="<b>%{x}</b><br>" + name + ": %{y:.2f}%<extra></extra>")
    top = max(v for _, vals, _ in series for v in vals)
    fig.update_layout(barmode="group", bargap=0.24, bargroupgap=0.06)
    fig.update_yaxes(range=[0, min(100, top + 14)], ticksuffix="%", title=None,
                     gridcolor=PALETTE["grid"], zeroline=False)
    fig.update_xaxes(title=None, showgrid=False, tickfont=dict(size=13, color=PALETTE["ink"]))
    return style_chart(fig, 380, margin=dict(l=4, r=10, t=34, b=4))


def _gap_figure(urban_rural, items):
    by_area = urban_rural.set_index("Area")
    labels = [it["short"] for it in items]
    gaps = [float(by_area.loc["Urban", it["column"]] - by_area.loc["Rural", it["column"]]) for it in items]
    fig = go.Figure(go.Bar(
        x=gaps, y=labels, orientation="h", marker=dict(color=[it["accent"] for it in items]),
        text=gaps, texttemplate="%{text:+.1f} pp", textposition="outside",
        textfont=dict(size=13, color=PALETTE["ink"]), cliponaxis=False,
        hovertemplate="<b>%{y}</b><br>Urban minus rural: %{x:+.2f} pp<extra></extra>"))
    bound = max(abs(g) for g in gaps) * 1.45 or 1
    fig.update_xaxes(range=[-bound, bound], title=None, ticksuffix=" pp", gridcolor=PALETTE["grid"],
                     zeroline=True, zerolinecolor=PALETTE["ink"], zerolinewidth=1.5)
    fig.update_yaxes(title=None, showgrid=False, autorange="reversed",
                     tickfont=dict(size=13.5, color=PALETTE["ink"]))
    for x, text, anchor in ((0.0, "Rural higher", "left"), (1.0, "Urban higher", "right")):
        fig.add_annotation(x=x, y=1.0, xref="paper", yref="paper", yanchor="bottom", xanchor=anchor,
                           text=text, showarrow=False, font=dict(size=12, color=PALETTE["muted"]))
    fig.update_layout(bargap=0.42)
    return style_chart(fig, 380, margin=dict(l=4, r=26, t=34, b=4))


# --------------------------------------------------------------------------
# Barriers
# --------------------------------------------------------------------------
def _reason_figure(barriers):
    ordered = barriers.sort_values("Weighted share (%)", ascending=True)
    fig = go.Figure(go.Bar(
        x=ordered["Weighted share (%)"], y=ordered["Reason (short)"], orientation="h",
        marker=dict(color=[data.BARRIER_FAMILY_COLORS[f] for f in ordered["Barrier family"]]),
        text=ordered["Weighted share (%)"], texttemplate="%{text:.1f}%", textposition="outside",
        textfont=dict(size=12, color=PALETTE["ink"]), cliponaxis=False,
        customdata=np.stack([ordered["Respondents"], ordered["Barrier family"]], axis=-1),
        hovertemplate="<b>%{y}</b><br>%{x:.2f}% of people without an account<br>"
                      "Family: %{customdata[1]}<br>%{customdata[0]:,} respondents<extra></extra>"))
    fig.update_layout(bargap=0.3)
    fig.update_xaxes(range=[0, 100], ticksuffix="%", title=None, gridcolor=PALETTE["grid"], zeroline=False)
    fig.update_yaxes(title=None, showgrid=False, automargin=True, tickfont=dict(size=12))
    return style_chart(fig, 470, margin=dict(l=4, r=40, t=8, b=4))


def _beyond_income_figure(barriers):
    rest = barriers[~barriers["Barrier family"].eq("No need or too little income")]
    rest = rest.sort_values("Weighted share (%)", ascending=True)
    fig = go.Figure(go.Bar(
        x=rest["Weighted share (%)"], y=rest["Reason (short)"], orientation="h",
        marker=dict(color=[data.BARRIER_FAMILY_COLORS[f] for f in rest["Barrier family"]]),
        text=rest["Weighted share (%)"], texttemplate="%{text:.1f}%", textposition="outside",
        textfont=dict(size=12, color=PALETTE["ink"]), cliponaxis=False,
        hovertemplate="<b>%{y}</b><br>%{x:.2f}% of people without an account<extra></extra>"))
    fig.update_layout(bargap=0.3)
    fig.update_xaxes(range=[0, float(rest["Weighted share (%)"].max()) * 1.3], ticksuffix="%", title=None,
                     gridcolor=PALETTE["grid"], zeroline=False)
    fig.update_yaxes(title=None, showgrid=False, automargin=True, tickfont=dict(size=12))
    return style_chart(fig, 470, margin=dict(l=4, r=40, t=8, b=4))


def _district_barrier_stack(district_barriers):
    shares = data.barrier_family_shares(district_barriers, by_district=True)
    wide = shares.pivot(index="District", columns="Barrier family", values="Weighted share (%)").fillna(0)
    stack = ["Access", "Cost", "Knowledge & paperwork"]
    for fam in stack:
        if fam not in wide.columns:
            wide[fam] = 0.0
    wide["total"] = wide[stack].sum(axis=1)
    wide = wide.sort_values("total", ascending=True)
    fig = go.Figure()
    for fam in stack:
        fig.add_bar(y=wide.index, x=wide[fam], orientation="h", name=fam,
                    marker=dict(color=data.BARRIER_FAMILY_COLORS[fam]),
                    hovertemplate="<b>%{y}</b><br>" + fam + ": %{x:.1f}%<extra></extra>")
    fig.add_trace(go.Scatter(x=wide["total"], y=wide.index, mode="text",
                             text=[f"{v:.1f}%" for v in wide["total"]], textposition="middle right",
                             textfont=dict(size=11, color=PALETTE["ink"]), hoverinfo="skip",
                             showlegend=False, cliponaxis=False))
    fig.update_layout(barmode="stack", bargap=0.28)
    fig.update_xaxes(title=None, ticksuffix="%", gridcolor=PALETTE["grid"], zeroline=False,
                     range=[0, float(wide["total"].max()) * 1.18])
    fig.update_yaxes(title=None, showgrid=False, tickfont=dict(size=11))
    return style_chart(fig, 780, margin=dict(l=4, r=30, t=34, b=4))


def _district_family_figure(rows):
    fam = data.barrier_family_shares(rows).set_index("Barrier family")["Weighted share (%)"]
    fam = fam.reindex(data.BARRIER_FAMILY_ORDER).dropna().sort_values(ascending=True)
    fig = go.Figure(go.Bar(
        x=fam.values, y=fam.index, orientation="h",
        marker=dict(color=[data.BARRIER_FAMILY_COLORS[f] for f in fam.index]),
        text=fam.values, texttemplate="%{text:.1f}%", textposition="outside",
        textfont=dict(size=12, color=PALETTE["ink"]), cliponaxis=False,
        hovertemplate="<b>%{y}</b><br>%{x:.2f}%<extra></extra>"))
    fig.update_layout(bargap=0.3)
    fig.update_xaxes(range=[0, 100], ticksuffix="%", title=None, gridcolor=PALETTE["grid"], zeroline=False)
    fig.update_yaxes(title=None, showgrid=False, automargin=True, tickfont=dict(size=12))
    return style_chart(fig, 330, margin=dict(l=4, r=40, t=8, b=4))


# --------------------------------------------------------------------------
# District map data
# --------------------------------------------------------------------------
def _map_figure(
    district,
    geojson,
    centers,
    center,
    metric,
    item,
    national_est,
    *,
    supply_points=(),
):
    frame = district.copy()
    frame["rank"] = frame[metric].rank(ascending=False, method="min")
    frame["diff"] = frame[metric] - national_est
    settings = {
        "basemap": "Light",
        "palette": "Indicator colours",
        "opacity": 0.92,
        "spotlight": "Off",
        "labels": False,
        "tilt": 0,
        "rotation": 0,
        "zoom": 6.8,
    }
    return build_map(
        frame,
        geojson,
        centers,
        center,
        item,
        metric,
        national_est,
        str(frame["District"].iloc[0]),
        item["short"],
        settings,
        supply_points=supply_points,
    )


def _ranking_html(district, metric, item):
    ordered = district.sort_values(metric, ascending=False)

    def rows(frame, start):
        return "".join(
            f'<div class="rk-row" style="--w:{max(0, min(float(r[metric]), 100)):.1f}">'
            f'<span class="rk-n">{start + i}</span><span class="rk-name">{esc(r["District"])}</span>'
            f'<span class="rk-v">{r[metric]:.1f}%</span></div>'
            for i, (_, r) in enumerate(frame.iterrows())
        )

    n = len(ordered)
    direction = (
        "Higher values indicate greater vulnerability." if item["polarity"] == "negative"
        else "Higher values indicate greater reported access or resilience."
        if item["polarity"] == "positive"
        else "This indicator has no inherently favourable direction."
    )
    return f"""
    <div style="--accent:{item['accent']}">
      <div class="rk-h">Highest five values</div><div class="rk">{rows(ordered.head(5), 1)}</div>
      <div class="rk-h">Lowest five values</div><div class="rk">{rows(ordered.tail(5), n - 4)}</div>
      <div class="micro">{direction} Lists rank this indicator only, not overall financial inclusion.</div>
    </div>
    """


# --------------------------------------------------------------------------
# Page
# --------------------------------------------------------------------------
def render_national_overview():
    from src.pages.nbr_dashboard import (
        combined_strip,
        current_mode,
        load_combined_context_data,
        render_combined_context,
        render_nbr_page,
    )

    mode = current_mode()
    if mode == "NBR Supply":
        render_nbr_page("national")
        return

    try:
        national = data.load_national()
        district = data.load_district()
        urban_rural = data.load_urban_rural()
    except (FileNotFoundError, ValueError, KeyError) as error:
        st.error("The overview data could not be loaded. Check the files in data/processed.")
        st.caption(str(error))
        return

    nat = dict(zip(national["Indicator"], national["Estimate (%)"].astype(float)))

    # ---- Hero + headline indicators ----------------------------------------
    # Combined mode: an approved, related NBR series is folded into the card it
    # relates to. Cards with no defensible related series stay exactly as in FinScope mode.
    kpi_context, kpi_notes = {}, []
    if mode == "Combined":
        for item in CORE:
            strip, entry = combined_strip(item["variable"], scope="National")
            if strip:
                kpi_context[item["variable"]] = strip
                kpi_notes.append((item["kpi_label"], entry))
    page_header(
        "Financial inclusion across Rwanda",
        "How people bank, use mobile money, borrow and save, based on "
        "weighted FinScope survey estimates.",
        pill="FinScope Rwanda 2024",
        size="tall",
        below_html=_kpi_html(national, kpi_context),
    )
    if kpi_notes:
        with st.expander("About the NBR lines in these cards"):
            st.caption(
                "NBR figures are administrative counts or volumes in their own units. "
                "They add supply-side context and never change the FinScope percentage."
            )
            for label, entry in kpi_notes:
                st.markdown(
                    f"**{esc(label)}** · {esc(entry['metric_label'])} "
                    f"({esc(entry.get('unit') or 'unit not specified')}). {esc(entry['limitations'])}"
                )
        for item in CORE:
            if item["kpi_label"] in {label for label, _ in kpi_notes}:
                render_combined_context(item["variable"])
    st.markdown("")

    # ---- What stands out ---------------------------------------------------
    section_title("What stands out",
                  "Four patterns in the data, worked out from the estimates on this page.")
    render_html(_insights_html(nat, district, urban_rural))
    st.caption(
        "**Why district comparisons matter:** A high national inclusion headline can coexist with "
        "substantial differences between districts and between types of services. The comparisons below "
        "show where estimates diverge from the national reference; they describe gaps, not their causes."
    )
    st.markdown("")

    # ---- Saving landscape ---------------------------------------------------
    if sum(1 for n in LANDSCAPE if n in nat) >= 4:
        section_title("How people save and cope",
                      "Community saving is commonly reported, but few adults have an emergency buffer.")
        left, right = st.columns([1.5, 1], gap="medium")
        with left:
            with st.container(key="card_landscape"):
                card_title("Saving, institutions and resilience",
                           "Share of adults. Channels overlap, so bars do not add up to 100%.")
                st.plotly_chart(_landscape_figure(nat), use_container_width=True,
                                key="ov_landscape", config={"displayModeBar": False})
        with right:
            with st.container(key="card_landscape_read"):
                card_title("Reading the picture")
                points = []
                g, b = nat.get("Saves with a group"), nat.get("Own bank account")
                if g and b:
                    points.append(f"<b>{g:.1f}%</b> of adults report saving with a group, about "
                                  f"<b>{g / b:.1f} times</b> the share who own a bank account ({b:.1f}%).")
                ns, em = nat.get("Does not save"), nat.get("Has emergency funds")
                if ns is not None and em is not None:
                    points.append(f"Most adults save in some way (<b>{100 - ns:.1f}%</b>), yet only "
                                  f"<b>{em:.1f}%</b> report emergency funds.")
                sc = nat.get("Currently uses Umurenge SACCO")
                if sc is not None:
                    points.append(f"<b>{sc:.1f}%</b> currently use an Umurenge SACCO, so the sector-level "
                                  "reported use is similar to the share who own a bank account.")
                render_html("".join(f'<div class="act" style="grid-template-columns:12px 1fr;padding:12px 0">'
                                    f'<div style="width:8px;height:8px;border-radius:50%;background:#1A8A7D;'
                                    f'margin-top:7px"></div><p class="act-p" style="margin:0">{p}</p></div>'
                                    for p in points))
                render_html('<div class="micro">These are separate survey questions, so they describe '
                            "participation, not the amount saved or whether savings are adequate.</div>")
                if mode == "Combined":
                    for variable in ("g3a_11", "qf4_06"):
                        strip, _ = combined_strip(variable, scope="National")
                        if strip:
                            render_html(strip)
                            render_combined_context(variable)
        st.markdown("")

    # ---- Urban and rural ------------------------------------------------------
    items = [it for it in REGISTRY if it["column"] in urban_rural.columns]
    if items and {"Urban", "Rural"} <= set(urban_rural["Area"]):
        section_title("Urban and rural",
                      "Where people live shapes access. Compare both areas with the national level.")
        left, right = st.columns([1.5, 1], gap="medium")
        with left:
            with st.container(key="card_urban_rural"):
                card_title("Urban, rural and national",
                           "Each group of bars is one indicator: urban, rural and the national level.")
                st.plotly_chart(_grouped_bars(urban_rural, nat, items), use_container_width=True,
                                key="ov_grouped", config={"displayModeBar": False})
                if "Valid respondents" in urban_rural.columns:
                    counts = " · ".join(f'{r["Area"]}: {int(r["Valid respondents"]):,}'
                                        for _, r in urban_rural.iterrows())
                    render_html(f'<div class="micro">Respondents · {esc(counts)}</div>')
        with right:
            with st.container(key="card_urban_rural_gap"):
                card_title("How big is the gap?", "Urban estimate minus rural estimate, in percentage points.")
                st.plotly_chart(_gap_figure(urban_rural, items), use_container_width=True,
                                key="ov_gap", config={"displayModeBar": False})
                render_html('<div class="micro">Bars to the right mean urban areas are higher; '
                            "bars to the left mean rural areas are higher.</div>")
        st.markdown("")

    # ---- Barriers ----------------------------------------------------------------
    barriers = data.load_barriers_national()
    district_barriers = data.load_barriers_district()
    if barriers is not None and not barriers.empty:
        section_title("Why do people lack a bank account?",
                      "Main reason given by adults without an account, using weighted FinScope 2024 estimates.")
        with st.container(key="card_bank_account_barriers"):
            tab_nat, tab_dist = st.tabs(["Nationally", "By district"])

            with tab_nat:
                fam = data.barrier_family_shares(barriers).set_index("Barrier family")["Weighted share (%)"]
                need = fam.get("No need or too little income", 0.0)
                cost, access, know = fam.get("Cost", 0.0), fam.get("Access", 0.0), fam.get("Knowledge & paperwork", 0.0)
                render_html(
                    f'<div class="micro" style="margin:0 0 10px;font-size:14px;color:#3F5560">'
                    f"<b>{need:.1f}%</b> of adults without an account say they do not need one or that their "
                    f"income is too limited to justify it. Beyond that, <b>cost ({cost:.1f}%)</b>, "
                    f"<b>distance and hours ({access:.1f}%)</b> and <b>knowledge and paperwork "
                    f"({know:.1f}%)</b> are the largest identifiable barriers.</div>"
                )
                c1, c2 = st.columns([1.2, 1], gap="large")
                with c1:
                    card_title("All reported reasons", "Share of people without an account, coloured by barrier family.")
                    st.plotly_chart(_reason_figure(barriers), use_container_width=True,
                                    key="ov_bank_account_barriers", config={"displayModeBar": False})
                with c2:
                    card_title("What remains beyond income",
                               "The same shares with the largest category removed, so smaller barriers are visible.")
                    st.plotly_chart(_beyond_income_figure(barriers), use_container_width=True,
                                    key="ov_barriers_beyond", config={"displayModeBar": False})
                render_html('<div class="micro">Population: adults who reported not having a bank account. '
                            "The largest category combines lack of need with insufficient income; the survey "
                            "does not separate those explanations. “Other” is kept as reported and has not been classified.</div>")

            with tab_dist:
                if district_barriers is None or district_barriers.empty:
                    st.info("District-level barrier data is not available.")
                else:
                    c1, c2 = st.columns([1.25, 1], gap="large")
                    with c1:
                        card_title("Where access, cost and knowledge barriers matter most",
                                   "Share of each district's adults without an account who cite these barriers.")
                        st.plotly_chart(_district_barrier_stack(district_barriers), use_container_width=True,
                                        key="ov_barrier_stack", config={"displayModeBar": False})
                    with c2:
                        districts = sorted(district_barriers["District"].dropna().astype(str).unique())
                        picked = st.selectbox("Inspect a district", districts, key="overview_barrier_district")
                        rows = district_barriers.loc[district_barriers["District"].eq(picked)]
                        base = int(rows["District non-account respondents"].iloc[0])
                        pop = float(rows["District weighted population"].iloc[0])
                        render_html(
                            f'<div class="gap-row" style="grid-template-columns:1fr 1fr;margin:6px 0 4px">'
                            f'<div class="gap"><span>Without an account</span><b>{base:,} respondents</b></div>'
                            f'<div class="gap"><span>Weighted adults represented (estimate)</span><b>{pop:,.0f}</b></div></div>'
                        )
                        card_title(f"Reasons in {picked}", "Weighted shares grouped by barrier family.")
                        st.plotly_chart(_district_family_figure(rows), use_container_width=True,
                                        key="ov_district_barriers_chart", config={"displayModeBar": False})
                        top = rows.sort_values("Weighted share (%)", ascending=False).iloc[0]
                        wide = data.margin_flag(base) == "wide"
                        render_html(
                            f'<div class="micro">Most common reason: <b>{esc(top["Reason (short)"])}</b> '
                            f'({top["Weighted share (%)"]:.1f}%). '
                            + (badge("Small base: read with care", "warn") if wide else
                               badge("Reasonable base for family-level shares", "ok"))
                            + " Individual reasons rest on small counts, so families are more reliable than single reasons. "
                            "The weighted base represents adults who reported no account and gave a reason; it is not "
                            "an estimate of people eligible for or likely to benefit from an investment.</div>"
                        )
        st.markdown("")

    # ---- Where the gaps are ----------------------------------------------------
    section_title("Where the gaps are",
                  "Compare district estimates with the national reference for one indicator at a time.")
    options = {it["short"]: it for it in REGISTRY if it["column"] in district.columns}
    with st.container(key="card_district_snapshot"):
        picked = st.pills("Indicator", list(options.keys()), selection_mode="single",
                          default=list(options.keys())[0], key="overview_district_indicator") \
            or list(options.keys())[0]
        item = options[picked]
        metric = item["column"]
        national_est = nat.get(item["national"])

        low = district.loc[district[metric].idxmin()]
        high = district.loc[district[metric].idxmax()]
        spread = float(high[metric] - low[metric])
        typical = float(np.median([data.moe_pp(v, n) for v, n in zip(district[metric], district["Valid respondents"])]))
        direction = (
            "Lower values indicate less reported access or resilience."
            if item["polarity"] == "positive"
            else "Higher values indicate greater reported vulnerability."
            if item["polarity"] == "negative"
            else "Neither higher nor lower is inherently better for this indicator."
        )
        below_national = int((district[metric] < national_est).sum()) if national_est is not None else None

        try:
            geojson = data.load_geojson()
            centers, center = data.geo_summary(geojson)
            map_ok = True
        except Exception:
            map_ok = False

        st.markdown("")
        render_html(f"""
        <div class="gap-row" style="grid-template-columns:repeat(3,minmax(0,1fr));margin:0 0 14px">
          <div class="gap"><span>Highest district</span><b>{esc(high["District"])} · {high[metric]:.1f}%</b></div>
          <div class="gap"><span>Lowest district</span><b>{esc(low["District"])} · {low[metric]:.1f}%</b></div>
          <div class="gap"><span>District range</span><b>{spread:.1f} pp</b></div>
        </div>""")
        benchmark_text = (
            f"National reference: <b>{national_est:.1f}%</b>; {below_national} of {len(district)} district estimates "
            f"are below it. {direction}"
            if national_est is not None
            else direction
        )
        render_html(
            f'<div class="micro">{benchmark_text} Map colours show district estimates, not distance from the '
            "national reference; the lists rank this indicator only, not overall financial inclusion.</div>"
        )

        selected_nbr_entry = None
        supply_points = []
        if mode == "Combined" and nbr_entries:
            if len(nbr_entries) == 1:
                selected_nbr_entry = nbr_entries[0]
            else:
                selected_index = st.selectbox(
                    "NBR marker series",
                    range(len(nbr_entries)),
                    format_func=lambda index: (
                        f"{nbr_entries[index]['metric_label']} · "
                        f"{nbr_entries[index].get('unit') or 'unit not specified'} · "
                        + " · ".join(
                            f"{key}: {value}"
                            for key, value in sorted(nbr_entries[index]["filters"].items())
                        )
                    ),
                    key=f"overview_nbr_map_series_{item['variable']}_{nbr_source_version}",
                )
                selected_nbr_entry = nbr_entries[selected_index]
            latest_date = max(
                (str(point["reporting_date"]) for point in selected_nbr_entry["points"]),
                default="",
            )
            supply_points = [
                point for point in selected_nbr_entry["points"]
                if str(point["reporting_date"]) == latest_date
            ]

        if map_ok:
            map_col, list_col = st.columns([1.35, 1], gap="large")
            with map_col:
                card_title(
                    "District pattern",
                    "FinScope estimates use the shaded map; NBR supply observations, when available, use separate markers and units.",
                )
                st.plotly_chart(_map_figure(
                    district,
                    geojson,
                    centers,
                    center,
                    metric,
                    item,
                    float(nat[item["national"]]),
                    supply_points=supply_points,
                ),
                                use_container_width=True, key="ov_district_map",
                                config={"displayModeBar": False, "scrollZoom": True})
            with list_col:
                render_html(_ranking_html(district, metric, item))
                st.button("Open the District explorer", key="ov_open_districts",
                          on_click=_open_district_explorer, use_container_width=True, icon=":material/map:")
        else:
            render_html(_ranking_html(district, metric, item))

        render_html(f'<div class="micro">A typical district estimate carries a sampling margin of about '
                    f"±{typical:.1f} pp under a simple-random-sample approximation. This is a district-only "
                    "illustrative margin, not a significance test for district-to-district or district-to-national "
                    "differences; the survey design information is unavailable.</div>")

        if selected_nbr_entry is not None:
            unit = selected_nbr_entry.get("unit") or "unit not specified"
            filters = " · ".join(
                f"{key}: {value}"
                for key, value in sorted(selected_nbr_entry["filters"].items())
            ) or "Filters not recorded"
            with st.expander(
                f"NBR observations · {selected_nbr_entry['metric_label']} · {unit}"
            ):
                st.caption(
                    f"Administrative values on {latest_date} · {filters}. "
                    "These are not FinScope ownership estimates."
                )
                st.dataframe(
                    pd.DataFrame([{
                        "District": point["geography"],
                        "Observed value": point["value"],
                        "Unit": unit,
                        "Reporting date": point["reporting_date"],
                    } for point in supply_points]),
                    hide_index=True,
                    use_container_width=True,
                )

        with st.expander("View district data"):
            show_district_table(district, sort_by=metric, key="download_district_results",
                                file_name="rwanda_district_indicator_results.csv", height=400)

    st.markdown("")
    note("How to interpret these figures",
         "These are survey-based weighted estimates from FinScope Rwanda 2024, not live measurements. "
         "A district with lower bank-account ownership may warrant further investigation, but these figures "
         "alone do not explain why the gap exists. Borrowing activity also does not measure every dimension "
         "of access to credit.")
    render_html('<div class="src-note">Source: FinScope Rwanda 2024. See Methodology &amp; sources for '
                "indicator definitions, data checks and limitations.</div>")
