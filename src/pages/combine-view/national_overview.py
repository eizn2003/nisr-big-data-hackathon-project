from datetime import date
from importlib import import_module

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from pymongo.errors import PyMongoError

from src import data
from src.indicators import BY_COLUMN, CORE, REGISTRY
from src.models.nbr_intelligence.indicator_mapping import (
    DISPLAYABLE_RELATIONSHIPS,
    MAPPING_BY_VARIABLE,
)
from src.pages.barrier_charts import district_family_figure
from src.pages.combined_support import (
    STATE_AVAILABLE,
    context_state_html,
    header_pill,
    inject_combined_styles,
    latest_point,
    load_context,
    national_recommendations,
    render_recommendations,
    scope_state,
    snapshot_points,
    snapshot_table,
    source_row_html,
    eligible_state,
    entry_dates,
    reporting_date_choice,
    routed_note,
    state_summary_html,
    missing_indicator_note,
)
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

_combined_district_explorer = import_module("src.pages.combine-view.district_explorer")
_filtered_combined_entries = _combined_district_explorer._filtered_combined_entries
build_map = _combined_district_explorer.build_map


def _open_district_explorer():
    st.session_state["selected_page"] = "District explorer"


def _open_indicator_district_explorer(indicator):
    st.session_state["dx_indicator"] = indicator
    st.session_state["selected_page"] = "District explorer"


def _open_overview_page(page):
    st.session_state["selected_page"] = page


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
        cards.append(f"""
            <div class="kpi" style="--accent:{item['accent']}">
              <div class="kpi-label"><i></i><span>{esc(item['kpi_label'])}</span></div>
              <div class="kpi-value">{value:.1f}<small>%</small></div>
              <div class="kpi-track"><div class="kpi-fill" style="width:{min(value, 100):.1f}%"></div></div>
              <div class="kpi-src">Share of adults · FinScope 2024</div>
              {context.get(item["variable"], "")}
            </div>
            """)
    return f'<div class="kpi-grid">{"".join(cards)}</div>'


# --------------------------------------------------------------------------
# What stands out
# --------------------------------------------------------------------------
def _insights_html(nat, district, urban_rural):
    cards = []

    bank, mobile = nat.get("Own bank account"), nat.get("Registered mobile-money user")
    if bank is not None and mobile is not None:
        lead = mobile - bank
        cards.append(
            (
                BY_COLUMN["Registered mobile-money user (%)"],
                "Two ways in",
                f"{abs(lead):.1f}<small>pp</small>",
                (
                    f"Active mobile-money registration ({mobile:.1f}%) is well ahead of "
                    f"bank-account ownership ({bank:.1f}%)."
                    if lead >= 0
                    else f"Bank-account ownership ({bank:.1f}%) is ahead of mobile money ({mobile:.1f}%)."
                ),
            )
        )

    group, emergency = nat.get("Saves with a group"), nat.get("Has emergency funds")
    if group is not None and emergency is not None:
        cards.append(
            (
                BY_COLUMN["Has emergency funds (%)"],
                "Saving without a safety net",
                f"{emergency:.1f}<small>%</small>",
                f"have emergency funds, while <b>{group:.1f}%</b> save with a group. "
                "Saving is common; a buffer for shocks is not.",
            )
        )

    metrics = [i for i in CORE if i["column"] in urban_rural.columns]
    by_area = urban_rural.set_index("Area")
    if {"Urban", "Rural"} <= set(by_area.index) and metrics:
        gaps = {
            i["column"]: float(
                by_area.loc["Urban", i["column"]] - by_area.loc["Rural", i["column"]]
            )
            for i in metrics
        }
        widest = max(gaps, key=lambda c: abs(gaps[c]))
        item = BY_COLUMN[widest]
        cards.append(
            (
                item,
                "Urban and rural",
                f"{abs(gaps[widest]):.1f}<small>pp</small>",
                f"Widest urban-rural gap is in <b>{item['label'].lower()}</b> "
                f"(urban {by_area.loc['Urban', widest]:.1f}% vs rural {by_area.loc['Rural', widest]:.1f}%).",
            )
        )

    col = "Owns a bank account (%)"
    item = BY_COLUMN[col]
    low, high = (
        district.loc[district[col].idxmin()],
        district.loc[district[col].idxmax()],
    )
    cards.append(
        (
            item,
            "Across districts",
            f"{high[col] - low[col]:.1f}<small>pp</small>",
            f"{item['label']} runs from <b>{low[col]:.1f}%</b> in {esc(low['District'])} "
            f"to <b>{high[col]:.1f}%</b> in {esc(high['District'])}.",
        )
    )

    html = "".join(f"""
        <div class="ins" style="--accent:{it['accent']};--accent-text:{it['text_accent']}">
          <div class="ins-k">{esc(kicker)}</div><div class="ins-v">{value}</div><div class="ins-t">{text}</div>
        </div>
        """ for it, kicker, value, text in cards)
    return f'<div class="ins-grid">{html}</div>'


# --------------------------------------------------------------------------
# Saving landscape
# --------------------------------------------------------------------------
LANDSCAPE = [
    "Saves with a group",
    "Currently uses a savings group",
    "Currently uses Umurenge SACCO",
    "Has emergency funds",
    "Does not save",
    "Own bank account",
]


def _landscape_figure(nat):
    rows = [
        (BY_COLUMN_BY_NATIONAL[name], nat[name]) for name in LANDSCAPE if name in nat
    ]
    rows.sort(key=lambda r: r[1])
    fig = go.Figure(
        go.Bar(
            x=[v for _, v in rows],
            y=[it["label"] for it, _ in rows],
            orientation="h",
            marker=dict(color=[it["accent"] for it, _ in rows]),
            text=[v for _, v in rows],
            texttemplate="%{text:.1f}%",
            textposition="outside",
            textfont=dict(size=13, color=PALETTE["ink"]),
            cliponaxis=False,
            hovertemplate="<b>%{y}</b><br>%{x:.2f}% of adults<extra></extra>",
        )
    )
    fig.update_layout(bargap=0.36)
    fig.update_xaxes(
        range=[0, min(100, max(v for _, v in rows) + 12)],
        ticksuffix="%",
        title=None,
        gridcolor=PALETTE["grid"],
        zeroline=False,
    )
    fig.update_yaxes(
        title=None,
        showgrid=False,
        automargin=True,
        tickfont=dict(size=13, color=PALETTE["ink"]),
    )
    return style_chart(fig, 380, margin=dict(l=4, r=30, t=8, b=4))


BY_COLUMN_BY_NATIONAL = {it["national"]: it for it in REGISTRY}


# --------------------------------------------------------------------------
# Urban / rural
# --------------------------------------------------------------------------
def _grouped_bars(urban_rural, nat, items):
    by_area = urban_rural.set_index("Area")
    labels = [it["short"] for it in items]
    series = [
        (
            "Urban",
            [float(by_area.loc["Urban", it["column"]]) for it in items],
            PALETTE["ink2"],
        ),
        (
            "Rural",
            [float(by_area.loc["Rural", it["column"]]) for it in items],
            "#5FB8AB",
        ),
    ]
    nat_values = [nat.get(it["national"]) for it in items]
    if all(v is not None for v in nat_values):
        series.append(("National", nat_values, "#B4C3CA"))
    fig = go.Figure()
    for name, values, color in series:
        fig.add_bar(
            x=labels,
            y=values,
            name=name,
            marker=dict(color=color),
            text=values,
            texttemplate="%{text:.1f}%",
            textposition="outside",
            textfont=dict(size=11.5, color=PALETTE["ink"]),
            cliponaxis=False,
            hovertemplate="<b>%{x}</b><br>" + name + ": %{y:.2f}%<extra></extra>",
        )
    top = max(v for _, vals, _ in series for v in vals)
    fig.update_layout(barmode="group", bargap=0.24, bargroupgap=0.06)
    fig.update_yaxes(
        range=[0, min(100, top + 14)],
        ticksuffix="%",
        title=None,
        gridcolor=PALETTE["grid"],
        zeroline=False,
    )
    fig.update_xaxes(
        title=None, showgrid=False, tickfont=dict(size=13, color=PALETTE["ink"])
    )
    return style_chart(fig, 380, margin=dict(l=4, r=10, t=34, b=4))


def _gap_figure(urban_rural, items):
    by_area = urban_rural.set_index("Area")
    labels = [it["short"] for it in items]
    gaps = [
        float(by_area.loc["Urban", it["column"]] - by_area.loc["Rural", it["column"]])
        for it in items
    ]
    fig = go.Figure(
        go.Bar(
            x=gaps,
            y=labels,
            orientation="h",
            marker=dict(color=[it["accent"] for it in items]),
            text=gaps,
            texttemplate="%{text:+.1f} pp",
            textposition="outside",
            textfont=dict(size=13, color=PALETTE["ink"]),
            cliponaxis=False,
            hovertemplate="<b>%{y}</b><br>Urban minus rural: %{x:+.2f} pp<extra></extra>",
        )
    )
    bound = max(abs(g) for g in gaps) * 1.45 or 1
    fig.update_xaxes(
        range=[-bound, bound],
        title=None,
        ticksuffix=" pp",
        gridcolor=PALETTE["grid"],
        zeroline=True,
        zerolinecolor=PALETTE["ink"],
        zerolinewidth=1.5,
    )
    fig.update_yaxes(
        title=None,
        showgrid=False,
        autorange="reversed",
        tickfont=dict(size=13.5, color=PALETTE["ink"]),
    )
    for x, text, anchor in (
        (0.0, "Rural higher", "left"),
        (1.0, "Urban higher", "right"),
    ):
        fig.add_annotation(
            x=x,
            y=1.0,
            xref="paper",
            yref="paper",
            yanchor="bottom",
            xanchor=anchor,
            text=text,
            showarrow=False,
            font=dict(size=12, color=PALETTE["muted"]),
        )
    fig.update_layout(bargap=0.42)
    return style_chart(fig, 380, margin=dict(l=4, r=26, t=34, b=4))


# --------------------------------------------------------------------------
# Barriers
# --------------------------------------------------------------------------
def _reason_figure(barriers):
    ordered = barriers.sort_values("Weighted share (%)", ascending=True)
    fig = go.Figure(
        go.Bar(
            x=ordered["Weighted share (%)"],
            y=ordered["Reason (short)"],
            orientation="h",
            marker=dict(
                color=[data.BARRIER_FAMILY_COLORS[f] for f in ordered["Barrier family"]]
            ),
            text=ordered["Weighted share (%)"],
            texttemplate="%{text:.1f}%",
            textposition="outside",
            textfont=dict(size=12, color=PALETTE["ink"]),
            cliponaxis=False,
            customdata=np.stack(
                [ordered["Respondents"], ordered["Barrier family"]], axis=-1
            ),
            hovertemplate="<b>%{y}</b><br>%{x:.2f}% of people without an account<br>"
            "Family: %{customdata[1]}<br>%{customdata[0]:,} respondents<extra></extra>",
        )
    )
    fig.update_layout(bargap=0.3)
    fig.update_xaxes(
        range=[0, 100],
        ticksuffix="%",
        title=None,
        gridcolor=PALETTE["grid"],
        zeroline=False,
    )
    fig.update_yaxes(
        title=None, showgrid=False, automargin=True, tickfont=dict(size=12)
    )
    return style_chart(fig, 470, margin=dict(l=4, r=40, t=8, b=4))


def _beyond_income_figure(barriers):
    rest = barriers[~barriers["Barrier family"].eq("No need or too little income")]
    rest = rest.sort_values("Weighted share (%)", ascending=True)
    fig = go.Figure(
        go.Bar(
            x=rest["Weighted share (%)"],
            y=rest["Reason (short)"],
            orientation="h",
            marker=dict(
                color=[data.BARRIER_FAMILY_COLORS[f] for f in rest["Barrier family"]]
            ),
            text=rest["Weighted share (%)"],
            texttemplate="%{text:.1f}%",
            textposition="outside",
            textfont=dict(size=12, color=PALETTE["ink"]),
            cliponaxis=False,
            hovertemplate="<b>%{y}</b><br>%{x:.2f}% of people without an account<extra></extra>",
        )
    )
    fig.update_layout(bargap=0.3)
    fig.update_xaxes(
        range=[0, float(rest["Weighted share (%)"].max()) * 1.3],
        ticksuffix="%",
        title=None,
        gridcolor=PALETTE["grid"],
        zeroline=False,
    )
    fig.update_yaxes(
        title=None, showgrid=False, automargin=True, tickfont=dict(size=12)
    )
    return style_chart(fig, 470, margin=dict(l=4, r=40, t=8, b=4))


def _district_barrier_stack(district_barriers):
    shares = data.barrier_family_shares(district_barriers, by_district=True)
    wide = shares.pivot(
        index="District", columns="Barrier family", values="Weighted share (%)"
    ).fillna(0)
    stack = ["Access", "Cost", "Knowledge & paperwork"]
    for fam in stack:
        if fam not in wide.columns:
            wide[fam] = 0.0
    wide["total"] = wide[stack].sum(axis=1)
    wide = wide.sort_values("total", ascending=True)
    fig = go.Figure()
    for fam in stack:
        fig.add_bar(
            y=wide.index,
            x=wide[fam],
            orientation="h",
            name=fam,
            marker=dict(color=data.BARRIER_FAMILY_COLORS[fam]),
            hovertemplate="<b>%{y}</b><br>" + fam + ": %{x:.1f}%<extra></extra>",
        )
    fig.add_trace(
        go.Scatter(
            x=wide["total"],
            y=wide.index,
            mode="text",
            text=[f"{v:.1f}%" for v in wide["total"]],
            textposition="middle right",
            textfont=dict(size=11, color=PALETTE["ink"]),
            hoverinfo="skip",
            showlegend=False,
            cliponaxis=False,
        )
    )
    fig.update_layout(barmode="stack", bargap=0.28)
    fig.update_xaxes(
        title=None,
        ticksuffix="%",
        gridcolor=PALETTE["grid"],
        zeroline=False,
        range=[0, float(wide["total"].max()) * 1.18],
    )
    fig.update_yaxes(title=None, showgrid=False, tickfont=dict(size=11))
    return style_chart(fig, 780, margin=dict(l=4, r=30, t=34, b=4))


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
        "Higher values indicate greater vulnerability."
        if item["polarity"] == "negative"
        else (
            "Higher values indicate greater reported access or resilience."
            if item["polarity"] == "positive"
            else "This indicator has no inherently favourable direction."
        )
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
def _combined_branch_provenance(entry):
    rows = []
    for point in entry.get("points", []):
        rows.append(
            {
                "Reporting date": point.get("reporting_date", ""),
                "Source page": point.get("page", ""),
                "Source metric": point.get("metric_label", ""),
                "Raw value": point.get("raw_value", point.get("value")),
                "Normalized value": point.get("value"),
                "Unit": point.get("unit") or "Not specified",
                "Filters": " · ".join(
                    f"{key}: {value}"
                    for key, value in sorted(point.get("filters", {}).items())
                ),
                "Source": point.get("source_name", ""),
                "Source URL": point.get("source_url", ""),
                "Collected at": point.get("collected_at", ""),
                "Run ID": point.get("run_id", ""),
                "Source record ID": point.get("source_record_id", ""),
            }
        )
    return pd.DataFrame(rows)


def _combined_nbr_observations(entry):
    if not entry:
        return []

    expected_page = entry.get("page", "branches")
    expected_metric = entry.get("metric_label", "Total Branches")
    expected_filters = entry.get("filters", {})
    observations = {}
    ambiguous_dates = set()
    for point in entry.get("points", []):
        if (
            point.get("page") != expected_page
            or point.get("metric_label") != expected_metric
            or point.get("source_type") != "national_kpi"
            or point.get("geography_level") != "national"
            or point.get("geography") != "Rwanda"
            or point.get("filters") != expected_filters
            or point.get("unit") != entry.get("unit")
            or point.get("repeated_snapshot_warning") is True
        ):
            continue
        reporting_date = str(point.get("reporting_date", ""))
        try:
            date.fromisoformat(reporting_date)
            value = float(point.get("value"))
        except (TypeError, ValueError):
            continue
        if not np.isfinite(value) or value < 0:
            continue
        if reporting_date in observations and observations[reporting_date] != value:
            ambiguous_dates.add(reporting_date)
        else:
            observations[reporting_date] = value

    for reporting_date in ambiguous_dates:
        observations.pop(reporting_date, None)

    dates = sorted(observations)
    return [
        {"reporting_date": reporting_date, "value": observations[reporting_date]}
        for reporting_date in dates
    ]


def _combined_nbr_figure(observations, *, metric_label, unit_label):
    ordered = observations[-8:]
    latest = ordered[-1] if ordered else None
    axis_unit = unit_label if unit_label else "Unit not specified by source"
    latest_label = (
        f"Latest · {latest['value']:,.0f} {axis_unit}"
        if latest and unit_label
        else f"Latest · {latest['value']:,.0f} · unit not specified" if latest else ""
    )
    fig = go.Figure(
        go.Scatter(
            x=[item["reporting_date"] for item in ordered],
            y=[item["value"] for item in ordered],
            mode="markers+text",
            text=[f"{item['value']:,.0f}" for item in ordered],
            textposition="top center",
            textfont=dict(family="Fraunces, Georgia, serif", size=15, color="#F1F6F8"),
            line=dict(color="#79AEEF", width=3, shape="linear"),
            marker=dict(
                size=[16 if item is latest else 10 for item in ordered],
                color=[
                    PALETTE["sun"] if item is latest else "#79AEEF" for item in ordered
                ],
                line=dict(color="#0E2A35", width=2),
            ),
            hovertemplate=(
                f"<b>%{{x}}</b><br>%{{y:,.0f}} "
                f"{esc(unit_label) if unit_label else 'unit not specified'}"
                f"<extra>NBR · {esc(metric_label)}</extra>"
            ),
            showlegend=False,
        )
    )
    if latest:
        fig.add_annotation(
            x=latest["reporting_date"],
            y=latest["value"],
            text=esc(latest_label),
            showarrow=True,
            arrowhead=2,
            arrowsize=1,
            arrowwidth=1.5,
            arrowcolor=PALETTE["sun"],
            ax=0,
            ay=-42,
            bgcolor="#173D49",
            bordercolor="#79AEEF",
            borderwidth=1,
            borderpad=6,
            font=dict(
                color="#FFFFFF", size=12, family="Plus Jakarta Sans, Arial, sans-serif"
            ),
        )
    fig.update_xaxes(
        title=None,
        type="date",
        showgrid=False,
        tickangle=-20,
        tickformat="%b %Y",
        tickfont=dict(color="#D5E2E6"),
        linecolor="#45616A",
    )
    fig.update_yaxes(
        title=dict(
            text=f"Recorded value · {axis_unit}",
            font=dict(color="#D5E2E6"),
        ),
        rangemode="tozero",
        gridcolor="rgba(213,226,230,.16)",
        zeroline=False,
        tickfont=dict(color="#D5E2E6"),
    )
    fig.update_layout(
        height=390,
        margin=dict(l=18, r=20, t=58, b=44),
        paper_bgcolor="#0E2A35",
        plot_bgcolor="#123641",
        font=dict(
            family="Plus Jakarta Sans, Segoe UI, Arial, sans-serif",
            color="#EAF1F3",
            size=12,
        ),
        hoverlabel=dict(
            bgcolor="#0E2A35",
            bordercolor="#79AEEF",
            font=dict(color="#FFFFFF"),
        ),
        showlegend=False,
    )
    return fig


def _render_combined_contextual_finding(index, finding):
    evidence = finding["supporting_evidence"][0]
    source_points = evidence.get("observations", [])
    entry = {
        "page": evidence.get("page"),
        "metric_label": evidence.get("metric_label"),
        "unit": evidence.get("unit"),
        "filters": evidence.get("filters", {}),
        "points": source_points,
    }
    observations = _combined_nbr_observations(entry)
    if not observations:
        return

    trend = finding.get("nbr_trend_summary") or {}
    latest = max(
        source_points,
        key=lambda point: str(point.get("reporting_date", "")),
    )
    metric_label = str(evidence.get("metric_label", "NBR metric"))
    unit_label = str(evidence.get("unit") or "")
    unit_status = str(evidence.get("unit_status") or "unresolved")
    unit_display = (
        f"{unit_label} · {unit_status}" if unit_label else "Not specified by source"
    )
    filters_label = " · ".join(
        f"{name}: {value}"
        for name, value in sorted(evidence.get("filters", {}).items())
    )
    finding_key = (
        f"{index}_{finding.get('indicator_variable', 'indicator')}_"
        f"{evidence.get('page', 'page')}"
    )
    nbr_column, survey_column = st.columns([2.2, 1], gap="medium")
    with st.container(key=f"card_combined_finding_{finding_key}"):
        with nbr_column:
            card_title(
                f"NBR · {metric_label}",
                f"{evidence.get('page', '')} page · "
                f"NBR unit: {unit_display} · {filters_label}",
            )
            st.plotly_chart(
                _combined_nbr_figure(
                    observations,
                    metric_label=metric_label,
                    unit_label=unit_label,
                ),
                use_container_width=True,
                key=f"ov_combined_finding_{finding_key}",
                config={"displayModeBar": False},
            )
            st.caption(f"NBR · {latest.get('reporting_date', '')} · {filters_label}")
            change = trend.get("absolute_change")
            change_text = (
                f"Recorded change across {trend.get('observation_count', len(observations))} "
                f"snapshots: {float(change):+,.3g} {unit_label or '(unit not specified)'}."
                if change is not None
                else f"{len(observations)} recorded snapshots; no change magnitude is available."
            )
            st.caption(
                f"{observations[0]['reporting_date']} to "
                f"{observations[-1]['reporting_date']} · {change_text}"
            )
            if trend.get("percent_change") is not None:
                st.caption(
                    f"Change between recorded values: {float(trend['percent_change']):+.1f}% "
                    "(not a FinScope percentage)."
                )
            with st.expander("NBR source details"):
                st.dataframe(
                    _combined_branch_provenance(entry),
                    use_container_width=True,
                    hide_index=True,
                )

        with survey_column:
            indicator_label = str(finding.get("indicator_label", "FinScope estimate"))
            card_title(
                f"{finding.get('finscope_reference_period', 'FinScope')} · "
                f"{indicator_label}"
            )
            valid_responses = finding.get(
                "finscope_valid_respondents",
                finding.get("valid_respondents"),
            )
            response_note = (
                f"{int(valid_responses):,} valid responses"
                if valid_responses is not None
                else "valid-response count unavailable"
            )
            render_html(
                '<div class="kpi-value" style="color:#1A8A7D">'
                f'{float(finding["finscope_estimate_percent"]):.1f}'
                "<small>%</small></div>"
                '<div class="kpi-src">Weighted national estimate · '
                f"{esc(finding.get('finscope_population', 'Population not reported'))} · "
                f"{esc(finding.get('finscope_weight', 'Weight not reported'))} · "
                f"{esc(response_note)}</div>"
            )
            st.caption(
                f"FinScope · {finding.get('indicator_variable', '')} · "
                f"{finding.get('finscope_source', 'source file unavailable')}"
            )
            st.caption(
                f"NBR direction: {finding.get('nbr_observed_direction', 'not assessed')} · "
                f"Relationship: {finding.get('mapping_status', 'unresolved')} · "
                f"Evidence sufficiency: {finding.get('evidence_sufficiency_state', 'unassessed')}"
            )
            st.caption(
                "This trend is not an anomaly confidence score. No adjudicated labels "
                "are available to estimate detector accuracy."
            )
            st.markdown(
                f"**What this may suggest:** "
                f"{esc(finding['suggested_interpretation'])}"
            )
            with st.expander("Interpretation limits"):
                for limitation in finding.get("limitations", []):
                    st.caption(str(limitation))
                if finding.get("cross_channel_context"):
                    st.caption(
                        "NBR channel context is a separate administrative "
                        "comparison; it does not establish a survey change."
                    )
            st.button(
                "Inspect this indicator by district",
                key=f"national_finding_to_district_{finding_key}",
                on_click=_open_indicator_district_explorer,
                args=(
                    next(
                        (
                            item["short"]
                            for item in REGISTRY
                            if item["variable"] == finding.get("indicator_variable")
                        ),
                        "",
                    ),
                ),
                use_container_width=True,
                icon=":material/map:",
            )
    st.markdown("")


@st.cache_data(ttl=900, show_spinner=False)
def _build_national_contextualization_report(points):
    from pathlib import Path

    from src.models.nbr_intelligence.contextualization import (
        build_national_contextualization_report,
        load_finscope_baselines,
    )

    baselines = load_finscope_baselines(
        Path(__file__).resolve().parents[2] / "data" / "processed"
    )
    return build_national_contextualization_report(points, baselines)


def _load_national_combined_assessment():
    from src.pages.nbr_dashboard import load_combined_national_evidence

    points, _ = load_combined_national_evidence()
    return points, _build_national_contextualization_report(points)


def _national_signal_diagnostics(report, findings, excluded_source_record_ids=()):
    suggestions = [
        item
        for item in report.get("suggestions", [])
        if item.get("analytical_level") == "national"
        and str(item.get("geography", "")).casefold() == "rwanda"
    ]
    excluded_sources = {str(item) for item in excluded_source_record_ids}
    no_observations = []
    insufficient_history = []
    evaluated = []
    for item in suggestions:
        evidence = (item.get("supporting_evidence") or [{}])[0]
        observations = evidence.get("observations") or []
        if not observations:
            no_observations.append(item)
            continue
        dates = {
            str(point.get("reporting_date", ""))
            for point in observations
            if point.get("reporting_date")
        }
        if len(dates) < 3:
            insufficient_history.append(item)
        else:
            evaluated.append(item)
    selected_ids = {
        (
            str(item.get("indicator_variable", "")),
            str(item.get("nbr_page", "")),
            str(item.get("nbr_metric", "")),
        )
        for item in findings
    }
    headline_exclusions = [
        item
        for item in evaluated
        if str(item.get("indicator_variable", "")) == "k1"
        or excluded_sources.intersection(
            str(source_id)
            for evidence in item.get("supporting_evidence", [])
            for source_id in evidence.get("source_record_ids", [])
        )
    ]
    selected_count = len(selected_ids)
    return {
        "national_suggestion_count": len(suggestions),
        "no_observation_count": len(no_observations),
        "insufficient_history_count": len(insufficient_history),
        "evaluated_count": len(evaluated),
        "headline_exclusion_count": len(headline_exclusions),
        "selected_count": selected_count,
        "evaluated_not_selected_count": max(
            0, len(evaluated) - len(headline_exclusions) - selected_count
        ),
    }


def _approved_national_findings(report, headline_entries, limit=4):
    from src.models.nbr_intelligence.contextualization import (
        select_national_contextualization_findings,
    )

    shown_ids = []
    for entry in headline_entries.values():
        latest = latest_point(entry.get("points", []))
        if latest and latest.get("source_record_id"):
            shown_ids.append(str(latest["source_record_id"]))
    approved_report = {
        **report,
        "suggestions": [
            suggestion
            for suggestion in report.get("suggestions", [])
            if suggestion.get("mapping_status") in {"relevant", "conditional"}
        ],
    }
    return select_national_contextualization_findings(
        approved_report,
        limit=limit,
        excluded_indicator_variables=("k1",),
        excluded_source_record_ids=shown_ids,
    ), shown_ids


def _render_descriptive_nbr_context(points, item):
    if points is None:
        return
    from src.pages.nbr_dashboard import (
        _mapped_series,
        _render_observation_table,
        _render_trend,
        NBR_PAGE_LABELS,
    )

    allowed = set(DISPLAYABLE_RELATIONSHIPS) | {
        "proxy_with_unresolved_definition"
    }
    entries = _mapped_series(
        points,
        item["variable"],
        geography_level="national",
        geography=None,
        relationships=allowed,
    )
    descriptive = [
        entry
        for entry in entries
        if entry.get("relationship") not in DISPLAYABLE_RELATIONSHIPS
    ]
    if not descriptive:
        return

    st.markdown("**Descriptive administrative observations · not comparisons**")
    st.caption(
        "These original NBR measures are available to inspect, but their relationship "
        "to the selected FinScope indicator remains unresolved. No denominator, unique "
        "customer count, or survey-equivalent rate is inferred."
    )
    for index, entry in enumerate(descriptive):
        page_label = NBR_PAGE_LABELS.get(str(entry.get("page")), entry.get("page", "NBR"))
        unit = entry.get("unit") or "unit not specified"
        filters = _filters_text(entry)
        st.markdown(f"**{page_label} · {entry['metric_label']} · {unit}**")
        st.caption(
            f"National NBR observations · exact filters: {filters or 'not recorded'} · "
            f"mapping remains {_relationship_label(entry.get('relationship')).lower()}."
        )
        st.warning(str(entry.get("limitations") or "The relationship is unresolved."))
        _render_trend(
            entry["points"],
            title=f"{entry['metric_label']} · {unit}",
            snapshots=True,
            key_suffix=(
                f"descriptive_{item['variable']}_{entry['page']}_"
                f"{entry['metric_label']}_{index}"
            ),
        )
        _render_observation_table(entry["points"])


def _filters_text(entry):
    return " · ".join(
        f"{name}: {value}"
        for name, value in sorted((entry.get("filters") or {}).items())
    )


def _headline_entry(entries):
    """Prefer the approved branch series for the bank-account card, else the first series."""
    return next(
        (entry for entry in entries if entry.get("metric_label") == "Total Branches"),
        entries[0],
    )


def _combined_headline():
    """NBR strips for the four headline cards, keyed by FinScope variable.

    Returns (strips, entries, states). Each card gets either approved series
    context or an explicit state explaining why it is unavailable.
    """
    from src.pages.nbr_dashboard import context_strip_html

    strips, entries_by_variable, states = {}, {}, {}
    for item in CORE:
        variable = item["variable"]
        entries, _, state = load_context(variable, level="national")
        states[variable] = state
        if not entries:
            strips[variable] = context_state_html(
                state,
                label="NBR",
            )
            continue
        entry = _headline_entry(entries)
        entries_by_variable[variable] = entry
        strips[variable] = context_strip_html(
            entry,
            scope=_filters_text(entry),
            other_series=len(entries) - 1,
        )
    return strips, entries_by_variable, states


def _headline_coverage_caption(states):
    shown = [
        it["kpi_label"]
        for it in CORE
        if states[it["variable"]].state == STATE_AVAILABLE
    ]
    missing = {}
    for it in CORE:
        state = states[it["variable"]]
        if state.state != STATE_AVAILABLE:
            missing.setdefault(state.title.lower().replace("nbr", "NBR"), []).append(
                it["kpi_label"]
            )
    parts = []
    if shown:
        parts.append(f"NBR context accompanies: {', '.join(shown)}.")
    for title, labels in missing.items():
        parts.append(f"{', '.join(labels)}: {title}.")
    return (
        " ".join(parts)
        + " NBR values are administrative counts in their own units, kept apart from the survey percentages."
    )


def _render_combined_findings(
    headline_entries,
    nbr_error,
    *,
    assessment_snapshot=None,
    assessment_error=None,
):
    """Render approved national trend suggestions from the existing assessment."""
    section_title(
        "What the financial system is recording",
        "Observed NBR movements are reviewed beside FinScope 2024 only where an approved relationship "
        "exists. National trend suggestions are not the district anomaly detector.",
    )
    error = assessment_error or nbr_error
    findings = []
    report = None
    national_points = []
    shown_ids = []
    if error is None:
        if assessment_snapshot is not None:
            national_points, report = assessment_snapshot
        else:
            try:
                national_points, report = _load_national_combined_assessment()
            except (
                FileNotFoundError,
                OSError,
                ValueError,
                KeyError,
                TypeError,
                RuntimeError,
                PyMongoError,
            ) as caught:
                error = caught
    if error is None and report is not None:
        try:
            findings, shown_ids = _approved_national_findings(
                report,
                headline_entries,
            )
        except (ValueError, KeyError, TypeError) as caught:
            error = caught
    if error is not None:
        st.warning(
            "The national trend assessment could not be completed; no findings were substituted."
        )
        st.caption(
            "FinScope results are unaffected. Check the source read and assessment inputs."
        )
        st.caption(str(error))
        return
    if report is None:
        st.info("No national NBR assessment output is available.")
        return

    source = report.get("source_data", {})
    dates = source.get("reporting_dates", [])
    st.caption(
        f"Assessment source: {source.get('eligible_national_nbr_observation_count', 0):,} "
        f"eligible national KPI observations across {len(dates)} reporting dates"
        + (f" ({', '.join(map(str, dates))})." if dates else ".")
    )
    st.caption(
        "National suggestions summarize direction across observed dates; at least three "
        "independent reporting dates are needed for a directional summary, and five are "
        "needed for the report's sufficient-directional-evidence label. That label is not "
        "statistical confidence or detector accuracy."
    )

    all_national = [
        item
        for item in report.get("suggestions", [])
        if item.get("analytical_level") == "national"
        and str(item.get("geography", "")).casefold() == "rwanda"
    ]
    unresolved_count = sum(
        1 for item in all_national
        if item.get("mapping_status") not in {"relevant", "conditional"}
        and item.get("supporting_evidence")
    )
    diagnostics = _national_signal_diagnostics(report, findings, shown_ids)
    if findings:
        st.caption(
            f"{len(findings)} approved national trend suggestion(s) met the selection rules. "
            f"{unresolved_count} additional supported suggestions retain unresolved/non-approved "
            "relationships and are not presented as cross-source findings."
        )
    else:
        source_count = source.get("eligible_national_nbr_observation_count", 0)
        if not source_count:
            reason = "No eligible national NBR observations were available to assess."
        elif diagnostics["no_observation_count"]:
            reason = (
                f"{diagnostics['no_observation_count']} national suggestion(s) had no "
                "eligible scope-matched observations."
            )
        elif diagnostics["insufficient_history_count"]:
            reason = (
                f"{diagnostics['insufficient_history_count']} suggestion(s) had fewer "
                "than three independent reporting dates."
            )
        elif diagnostics["evaluated_count"]:
            reason = (
                "National trends were assessed, but none survived the approved-relationship, "
                "direction, headline de-duplication, and selection rules."
            )
        else:
            reason = "No national suggestion was eligible for selection."
        st.info(
            "No national findings currently meet the approved selection rules. "
            "No qualifying national trend finding is shown. "
            + reason
            + " Absence of a finding is not evidence of no change."
        )
    if diagnostics["evaluated_not_selected_count"]:
        st.caption(
            f"{diagnostics['evaluated_not_selected_count']} other scope-matched "
            "trend suggestion(s) were evaluated but not selected for this compact view."
        )
    if not findings:
        return
    for index, finding in enumerate(findings):
        _render_combined_contextual_finding(index, finding)


CHANNEL_VARIABLES = ("g3a_11", "qf4_06", "qf4_10", "e9b", "g3a_17")
_BY_VARIABLE = {it["variable"]: it for it in REGISTRY}


def _render_channel_context(nat):
    """NBR context for saving and community-channel indicators, inside the reading card."""
    from src.pages.nbr_dashboard import context_strip_html

    blocks, unmatched = [], []
    for variable in CHANNEL_VARIABLES:
        item = _BY_VARIABLE.get(variable)
        if item is None:
            continue
        entries, _, state = load_context(variable, level="national")
        if not entries:
            unmatched.append((item["short"], state))
            if routed_note(variable):
                blocks.append(
                    f'<div class="micro">{esc(item["short"])}: {esc(routed_note(variable))}</div>'
                )
            continue
        entry = entries[0]
        estimate = nat.get(item["national"])
        survey = f" · FinScope {estimate:.1f}%" if estimate is not None else ""
        blocks.append(
            f'<div style="margin-top:10px">{source_row_html("fs", item["short"] + survey)}'
            f"{context_strip_html(entry, scope=_filters_text(entry), other_series=len(entries) - 1)}</div>"
        )
    if blocks:
        render_html(
            '<div class="micro" style="margin-top:14px"><b>Administrative context</b> '
            "(separate unit and scope; context only)</div>" + "".join(blocks)
        )
    if unmatched:
        # Each reason is named separately: no counterpart, not approved, suppressed,
        # no observation and a failed read are different facts about the evidence.
        render_html(state_summary_html(unmatched))


def _valid_response_count(validation, variable):
    if (
        validation is None
        or not isinstance(validation, pd.DataFrame)
        or not {"Variable", "Valid responses"} <= set(validation.columns)
    ):
        return None
    rows = validation.loc[validation["Variable"].astype(str).eq(variable)]
    if rows.empty:
        return None
    value = pd.to_numeric(rows.iloc[0]["Valid responses"], errors="coerce")
    return int(value) if pd.notna(value) and value >= 0 else None


def _relationship_label(relationship):
    return {
        "contextual_indicator": "Relevant",
        "conditional_contextual_indicator": "Conditional",
        "proxy_with_unresolved_definition": "Unresolved",
        "unsuitable": "Unsuitable",
    }.get(str(relationship), "Unclassified")


def _render_unshown_relationships(mapping):
    relationships = mapping.get("nbr_relationships", [])
    unshown = [
        item
        for item in relationships
        if item.get("suppressed")
        or item.get("relationship") not in DISPLAYABLE_RELATIONSHIPS
    ]
    if not unshown:
        return
    with st.expander("Relationships not used as approved comparisons"):
        for relationship in unshown:
            label = _relationship_label(relationship.get("relationship"))
            if relationship.get("suppressed"):
                label = "Suppressed"
            st.markdown(f"**{label} · {relationship.get('page', 'NBR series')}**")
            detail = (
                relationship.get("suppression_reason")
                or relationship.get("limitations")
                or "This relationship is not eligible for analytical context."
            )
            st.caption(str(detail))


def _render_combined_indicator_explorer(
    national,
    nbr_error=None,
    *,
    national_points=None,
    assessment_error=None,
):
    national_labels = set(national["Indicator"].astype(str))
    options = {
        item["short"]: item
        for item in REGISTRY
        if item["national"] in national_labels
    }
    if not options:
        st.info("No registered FinScope indicators are available in the national estimates.")
        return

    section_title(
        "Explore a FinScope indicator",
        "Choose an indicator to see its 2024 survey estimate and any eligible NBR administrative context.",
    )
    with st.container(key="card_combined_indicator_explorer"):
        survey_column, context_column = st.columns([1, 1.15], gap="large")
        with survey_column:
            picked = st.selectbox(
                "FinScope indicator",
                list(options),
                key="combined_indicator_selectbox",
            )
            item = options[picked]
            row = national.loc[national["Indicator"].eq(item["national"])]
            estimate = (
                pd.to_numeric(row.iloc[0]["Estimate (%)"], errors="coerce")
                if not row.empty
                else None
            )
            card_title("FinScope Rwanda 2024", item["label"])
            if pd.notna(estimate):
                st.metric("Weighted survey estimate", f"{float(estimate):.1f}%")
            else:
                st.info("The FinScope estimate is not available for this indicator.")

            mapping = MAPPING_BY_VARIABLE.get(item["variable"], {})
            population = mapping.get(
                "survey_population", "Rwanda residents aged 16 years and older"
            )
            weight = mapping.get("survey_weight", "pop_wt")
            reference = mapping.get("survey_reference_period", "FinScope Rwanda 2024")
            st.caption(f"{reference} · {population} · survey weight: {weight}")
            st.markdown("**What this indicator measures**")
            st.write(item.get("description") or item["label"])
            denominator = mapping.get("survey_denominator")
            if denominator:
                st.caption(f"Estimate denominator: {denominator}")

            try:
                denominator_data = data.load_denominators()
            except (OSError, ValueError, KeyError) as error:
                denominator_data = None
                st.warning("The valid-response count could not be loaded.")
                st.caption(str(error))
            valid_responses = _valid_response_count(
                denominator_data, item["variable"]
            )
            st.caption(
                f"Valid responses: {valid_responses:,}"
                if valid_responses is not None
                else "Valid-response count unavailable; no count is inferred."
            )
            route_note = routed_note(item["variable"])
            if route_note:
                st.warning(route_note)

        with context_column:
            card_title(
                "NBR administrative context",
                "Separate administrative observations, shown only for eligible relationships and their exact source scope.",
            )
            mapping = MAPPING_BY_VARIABLE.get(item["variable"], {})
            configured = mapping.get("nbr_relationships", [])
            candidates = [
                relationship
                for relationship in configured
                if not relationship.get("suppressed")
                and relationship.get("relationship") in DISPLAYABLE_RELATIONSHIPS
            ]
            conditional = [
                relationship
                for relationship in candidates
                if relationship.get("relationship")
                == "conditional_contextual_indicator"
            ]
            if conditional:
                for relationship in conditional:
                    limitation = (
                        relationship.get("limitations")
                        or relationship.get("conditions")
                        or "This relationship has documented limitations."
                    )
                    st.warning(f"Conditional relationship. {limitation}")

            if nbr_error is not None:
                st.warning(
                    "NBR context could not be loaded. FinScope results are unchanged."
                )
                st.caption(str(nbr_error))
            else:
                entries, version, state = load_context(
                    item["variable"], level="national"
                )
                state = eligible_state(state, entries)
                if entries and state.available:
                    relationship_types = sorted(
                        {
                            _relationship_label(entry.get("relationship"))
                            for entry in entries
                        }
                    )
                    st.caption(
                        "Relationship class: " + ", ".join(relationship_types)
                    )
                    st.caption(
                        "NBR values are administrative context, not survey estimates "
                        "and do not explain or alter the FinScope result."
                    )
                    from src.pages.nbr_dashboard import render_combined_context

                    render_combined_context(
                        item["variable"],
                        entries=entries,
                        source_version=version,
                        expanded=True,
                    )
                else:
                    render_html(context_state_html(state, label=item["short"]))

            if assessment_error is not None and any(
                rel.get("relationship") == "proxy_with_unresolved_definition"
                for rel in configured
            ):
                st.warning(
                    "Descriptive NBR observations could not be loaded; this does not "
                    "change the unresolved relationship classification."
                )
            elif national_points is not None:
                _render_descriptive_nbr_context(national_points, item)

            _render_unshown_relationships(mapping)
            st.button(
                "Explore this indicator by district",
                key=f"combined_to_district_{item['variable']}",
                on_click=_open_indicator_district_explorer,
                args=(item["short"],),
                use_container_width=True,
                icon=":material/map:",
            )


def _render_district_supply_context(variable, district_name, heading):
    from src.pages.nbr_dashboard import context_strip_html

    entries, _, state = load_context(
        variable, level="district", geography=district_name
    )
    entries = _filtered_combined_entries(entries, variable)
    if not entries:
        state = eligible_state(state, entries)
        render_html(context_state_html(state, label=heading))
        return
    entry = entries[0]
    render_html(
        f'<div class="micro" style="margin-top:12px">{source_row_html("nbr", heading)}</div>'
        + context_strip_html(entry, scope=_filters_text(entry))
        + f'<div class="micro">Recorded administrative count for {esc(district_name)}. It does '
        "not show whether the barriers above concern distance or opening hours.</div>"
    )


def render_national_overview():
    from src.pages.nbr_dashboard import (
        current_mode,
        render_nbr_page,
    )

    mode = current_mode()
    if mode == "NBR Supply":
        render_nbr_page("national")
        return
    combined = mode == "Combined"

    try:
        national = data.load_national()
        district = data.load_district().copy()
        urban_rural = data.load_urban_rural()
    except (FileNotFoundError, ValueError, KeyError) as error:
        st.error(
            "The overview data could not be loaded. Check the files in data/processed."
        )
        st.caption(str(error))
        return

    nat = dict(zip(national["Indicator"], national["Estimate (%)"].astype(float)))

    headline_strips, headline_entries, headline_states = {}, {}, {}
    nbr_error = None
    assessment_snapshot = None
    assessment_error = None
    if combined:
        inject_combined_styles()
        try:
            headline_strips, headline_entries, headline_states = _combined_headline()
        except (RuntimeError, ValueError, OSError, PyMongoError) as error:
            nbr_error = error
        if nbr_error is None:
            try:
                assessment_snapshot = _load_national_combined_assessment()
            except (
                FileNotFoundError,
                OSError,
                ValueError,
                KeyError,
                TypeError,
                RuntimeError,
                PyMongoError,
            ) as error:
                assessment_error = error

    # ---- Hero + headline indicators ----------------------------------------
    page_header(
        "Financial inclusion across Rwanda",
        (
            "How people bank, use mobile money, borrow and save, from weighted FinScope "
            "survey estimates, with NBR administrative observations of the financial system alongside."
            if combined
            else "How people bank, use mobile money, borrow and save, based on "
            "weighted FinScope survey estimates."
        ),
        pill=header_pill(mode, "FinScope Rwanda 2024"),
        size="tall",
        mode=mode,
        intro=(
            "Survey and administrative sources measure different things, so every value keeps "
            "its own label, unit, date and scope. Nothing is calculated across them."
            if combined
            else ""
        ),
        below_html=_kpi_html(national, headline_strips),
    )
    if combined:
        if nbr_error is not None:
            st.caption(
                "NBR context is unavailable right now; every FinScope value below is unchanged."
            )
        else:
            st.caption(_headline_coverage_caption(headline_states))
        _render_combined_indicator_explorer(
            national,
            nbr_error,
            national_points=(
                assessment_snapshot[0] if assessment_snapshot is not None else None
            ),
            assessment_error=assessment_error,
        )
    st.markdown("")

    # ---- What stands out ---------------------------------------------------
    section_title(
        "What stands out",
        "Four patterns in the data, worked out from the estimates on this page.",
    )
    render_html(_insights_html(nat, district, urban_rural))
    st.caption(
        "**Why district comparisons matter:** A high national inclusion headline can coexist with "
        "substantial differences between districts and between types of services. The comparisons below "
        "show where estimates diverge from the national reference; they describe gaps, not their causes."
    )
    st.markdown("")

    # ---- Combined: administrative signals paired with the survey --------------
    if combined:
        _render_combined_findings(
            headline_entries,
            nbr_error,
            assessment_snapshot=assessment_snapshot,
            assessment_error=assessment_error,
        )
        st.markdown("")

    # ---- Saving landscape ---------------------------------------------------
    if sum(1 for n in LANDSCAPE if n in nat) >= 4:
        section_title(
            "How people save and cope",
            "Community saving is commonly reported, but few adults have an emergency buffer.",
        )
        left, right = st.columns([1.5, 1], gap="medium")
        with left:
            with st.container(key="card_landscape"):
                card_title(
                    "Saving, institutions and resilience",
                    "Share of adults. Channels overlap, so bars do not add up to 100%."
                    + (" Survey estimates only." if combined else ""),
                )
                st.plotly_chart(
                    _landscape_figure(nat),
                    use_container_width=True,
                    key="ov_landscape",
                    config={"displayModeBar": False},
                )
        with right:
            with st.container(key="card_landscape_read"):
                card_title("Reading the picture")
                points = []
                g, b = nat.get("Saves with a group"), nat.get("Own bank account")
                if g and b:
                    points.append(
                        f"<b>{g:.1f}%</b> of adults report saving with a group, about "
                        f"<b>{g / b:.1f} times</b> the share who own a bank account ({b:.1f}%)."
                    )
                ns, em = nat.get("Does not save"), nat.get("Has emergency funds")
                if ns is not None and em is not None:
                    points.append(
                        f"Most adults save in some way (<b>{100 - ns:.1f}%</b>), yet only "
                        f"<b>{em:.1f}%</b> report emergency funds."
                    )
                sc = nat.get("Currently uses Umurenge SACCO")
                if sc is not None:
                    points.append(
                        f"<b>{sc:.1f}%</b> currently use an Umurenge SACCO, so the sector-level "
                        "reported use is similar to the share who own a bank account."
                    )
                render_html(
                    "".join(
                        f'<div class="act" style="grid-template-columns:12px 1fr;padding:12px 0">'
                        f'<div style="width:8px;height:8px;border-radius:50%;background:#1A8A7D;'
                        f'margin-top:7px"></div><p class="act-p" style="margin:0">{p}</p></div>'
                        for p in points
                    )
                )
                render_html(
                    '<div class="micro">These are separate survey questions, so they describe '
                    "participation, not the amount saved or whether savings are adequate.</div>"
                )
                if combined and routed_note("qf4_06"):
                    render_html(
                        f'<div class="micro">SACCO and savings-group use: {esc(routed_note("qf4_06"))}</div>'
                    )
                if combined and nbr_error is None:
                    _render_channel_context(nat)
        st.markdown("")

    # ---- Urban and rural ------------------------------------------------------
    items = [it for it in REGISTRY if it["column"] in urban_rural.columns]
    if items and {"Urban", "Rural"} <= set(urban_rural["Area"]):
        section_title(
            "Urban and rural",
            "Where people live shapes access. Compare both areas with the national level.",
        )
        left, right = st.columns([1.5, 1], gap="medium")
        with left:
            with st.container(key="card_urban_rural"):
                card_title(
                    "Urban, rural and national",
                    "Each group of bars is one indicator: urban, rural and the national level.",
                )
                st.plotly_chart(
                    _grouped_bars(urban_rural, nat, items),
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
                    _gap_figure(urban_rural, items),
                    use_container_width=True,
                    key="ov_gap",
                    config={"displayModeBar": False},
                )
                render_html(
                    '<div class="micro">Bars to the right mean urban areas are higher; '
                    "bars to the left mean rural areas are higher.</div>"
                )
                if combined:
                    area = scope_state("Area")
                    render_html(context_state_html(area, label="Urban and rural"))
                    gap_note = missing_indicator_note(
                        REGISTRY, urban_rural, "urban/rural"
                    )
                    if gap_note:
                        render_html(f'<div class="micro">{esc(gap_note)}</div>')
        st.markdown("")

    # ---- Barriers ----------------------------------------------------------------
    barriers = data.load_barriers_national()
    district_barriers = data.load_barriers_district()
    if barriers is not None and not barriers.empty:
        section_title(
            "Why do people lack a bank account?",
            "Main reason given by adults without an account, using weighted FinScope 2024 estimates.",
        )
        with st.container(key="card_bank_account_barriers"):
            tab_nat, tab_dist = st.tabs(["Nationally", "By district"])

            with tab_nat:
                fam = data.barrier_family_shares(barriers).set_index("Barrier family")[
                    "Weighted share (%)"
                ]
                need = fam.get("No need or too little income", 0.0)
                cost, access, know = (
                    fam.get("Cost", 0.0),
                    fam.get("Access", 0.0),
                    fam.get("Knowledge & paperwork", 0.0),
                )
                render_html(
                    f'<div class="micro" style="margin:0 0 10px;font-size:14px;color:#3F5560">'
                    f"<b>{need:.1f}%</b> of adults without an account say they do not need one or that their "
                    f"income is too limited to justify it. Beyond that, <b>cost ({cost:.1f}%)</b>, "
                    f"<b>distance and hours ({access:.1f}%)</b> and <b>knowledge and paperwork "
                    f"({know:.1f}%)</b> are the largest identifiable barriers.</div>"
                )
                c1, c2 = st.columns([1.2, 1], gap="large")
                with c1:
                    card_title(
                        "All reported reasons",
                        "Share of people without an account, coloured by barrier family.",
                    )
                    st.plotly_chart(
                        _reason_figure(barriers),
                        use_container_width=True,
                        key="ov_bank_account_barriers",
                        config={"displayModeBar": False},
                    )
                with c2:
                    card_title(
                        "What remains beyond income",
                        "The same shares with the largest category removed, so smaller barriers are visible.",
                    )
                    st.plotly_chart(
                        _beyond_income_figure(barriers),
                        use_container_width=True,
                        key="ov_barriers_beyond",
                        config={"displayModeBar": False},
                    )
                render_html(
                    '<div class="micro">Population: adults who reported not having a bank account. '
                    "The largest category combines lack of need with insufficient income; the survey "
                    "does not separate those explanations. “Other” is kept as reported and has not been classified.</div>"
                )

            with tab_dist:
                if district_barriers is None or district_barriers.empty:
                    st.info("District-level barrier data is not available.")
                else:
                    c1, c2 = st.columns([1.25, 1], gap="large")
                    with c1:
                        card_title(
                            "Where access, cost and knowledge barriers matter most",
                            "Share of each district's adults without an account who cite these barriers.",
                        )
                        st.plotly_chart(
                            _district_barrier_stack(district_barriers),
                            use_container_width=True,
                            key="ov_barrier_stack",
                            config={"displayModeBar": False},
                        )
                    with c2:
                        districts = sorted(
                            district_barriers["District"].dropna().astype(str).unique()
                        )
                        picked = st.selectbox(
                            "Inspect a district",
                            districts,
                            key="overview_barrier_district",
                        )
                        rows = district_barriers.loc[
                            district_barriers["District"].eq(picked)
                        ]
                        base = int(rows["District non-account respondents"].iloc[0])
                        pop = float(rows["District weighted population"].iloc[0])
                        render_html(
                            f'<div class="gap-row" style="grid-template-columns:1fr 1fr;margin:6px 0 4px">'
                            f'<div class="gap"><span>Without an account</span><b>{base:,} respondents</b></div>'
                            f'<div class="gap"><span>Weighted adults represented (estimate)</span><b>{pop:,.0f}</b></div></div>'
                        )
                        card_title(
                            f"Reasons in {picked}",
                            "Weighted shares grouped by barrier family.",
                        )
                        st.plotly_chart(
                            district_family_figure(rows),
                            use_container_width=True,
                            key="ov_district_barriers_chart",
                            config={"displayModeBar": False},
                        )
                        top = rows.sort_values(
                            "Weighted share (%)", ascending=False
                        ).iloc[0]
                        wide = data.margin_flag(base) == "wide"
                        render_html(
                            f'<div class="micro">Most common reason: <b>{esc(top["Reason (short)"])}</b> '
                            f'({top["Weighted share (%)"]:.1f}%). '
                            + (
                                badge("Small base: read with care", "warn")
                                if wide
                                else badge(
                                    "Reasonable base for family-level shares", "ok"
                                )
                            )
                            + " Individual reasons rest on small counts, so families are more reliable than single reasons. "
                            "The weighted base represents adults who reported no account and gave a reason; it is not "
                            "an estimate of people eligible for or likely to benefit from an investment.</div>"
                        )
                        if combined and nbr_error is None:
                            _render_district_supply_context(
                                "k1", picked, f"Recorded in {picked}"
                            )
        st.markdown("")

    # ---- Where the gaps are ----------------------------------------------------
    section_title(
        "Where the gaps are",
        "Compare district estimates with the national reference for one indicator at a time.",
    )
    options = {it["short"]: it for it in REGISTRY if it["column"] in district.columns}
    with st.container(key="card_district_snapshot"):
        default_indicator = next(iter(options))
        picked = (
            st.pills(
                "Indicator",
                list(options.keys()),
                selection_mode="single",
                default=st.session_state.get("overview_district_indicator", default_indicator),
                key="overview_district_indicator",
            )
            or st.session_state.get("overview_district_indicator", default_indicator)
        )
        if picked not in options:
            picked = default_indicator
        item = options[picked]
        metric = item["column"]
        denominator = item["valid_count_column"]
        if denominator not in district.columns:
            st.error(
                "The district dataset is missing indicator-specific respondent "
                f"counts for {item['label']}."
            )
            return
        district["Valid respondents"] = pd.to_numeric(
            district[denominator], errors="coerce"
        )
        national_est = nat.get(item["national"])

        # NBR district context is looked up from the *current* indicator on every
        # run, so it can never be carried over from a previous selection.
        nbr_entries, nbr_state, nbr_entry, overlay_points, overlay_date = (
            [],
            None,
            None,
            [],
            "",
        )
        if combined and nbr_error is None:
            entries, _, nbr_state = load_context(item["variable"], level="district")
            nbr_entries = _filtered_combined_entries(entries, item["variable"])
            nbr_state = eligible_state(nbr_state, nbr_entries)
            if nbr_entries:
                series_key = f"overview_nbr_series_{item['variable']}"
                if len(nbr_entries) > 1:
                    index = st.session_state.get(series_key, 0)
                    if not isinstance(index, int) or index >= len(nbr_entries):
                        st.session_state[series_key] = 0
                    index = st.selectbox(
                        "NBR series shown as map markers",
                        range(len(nbr_entries)),
                        format_func=lambda i: (
                            f"{nbr_entries[i]['metric_label']} · "
                            f"{nbr_entries[i].get('unit') or 'unit not specified'}"
                        ),
                        key=series_key,
                    )
                else:
                    index = 0
                nbr_entry = nbr_entries[index]
                # The reporting date belongs to this exact series, so a date chosen for
                # another indicator or series can never be applied here.
                dates = entry_dates(nbr_entry)
                date_key = f"overview_nbr_date_{item['variable']}_{index}_{nbr_entry['metric_label']}_{nbr_entry.get('unit', '')}"
                chosen = reporting_date_choice(st.session_state, date_key, dates)
                if len(dates) > 1:
                    st.selectbox("NBR reporting date", dates[::-1], key=date_key)
                    chosen = st.session_state.get(date_key, chosen)
                overlay_points, overlay_date = snapshot_points(nbr_entry, chosen)
        elif combined:
            st.caption(
                "NBR map context is unavailable; FinScope estimates are unchanged."
            )

        low = district.loc[district[metric].idxmin()]
        high = district.loc[district[metric].idxmax()]
        spread = float(high[metric] - low[metric])
        typical = float(
            np.median(
                [
                    data.moe_pp(v, n)
                    for v, n in zip(district[metric], district["Valid respondents"])
                ]
            )
        )
        direction = (
            "Lower values indicate less reported access or resilience."
            if item["polarity"] == "positive"
            else (
                "Higher values indicate greater reported vulnerability."
                if item["polarity"] == "negative"
                else "Neither higher nor lower is inherently better for this indicator."
            )
        )
        below_national = (
            int((district[metric] < national_est).sum())
            if national_est is not None
            else None
        )

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

        recommendations = []
        if combined and nbr_state is not None:
            recommendations = national_recommendations(
                indicator=item["short"].lower(),
                below_count=below_national or 0,
                district_total=len(district),
                lowest_district=str(low["District"]),
                state=nbr_state,
                nbr_label=nbr_entry["metric_label"] if nbr_entry else "",
                reported_districts=len({p["geography"] for p in overlay_points}),
                reporting_date=overlay_date,
                polarity=item["polarity"],
            )

        if map_ok:
            map_col, list_col = st.columns([1.35, 1], gap="large")
            with map_col:
                card_title(
                    "District pattern",
                    "FinScope survey estimates shown by the shaded map."
                    + (
                        " NBR markers use a separate scale: larger means a larger recorded value."
                        if overlay_points
                        else ""
                    ),
                )
                if overlay_points:
                    unit = nbr_entry.get("unit") or "unit not specified"
                    render_html(
                        '<div class="chips" style="margin:0 0 6px"><span class="chip"><i style="background:'
                        f'{PALETTE["ink2"]};border-color:#fff"></i>NBR · {esc(nbr_entry["metric_label"])} · '
                        f"{esc(unit)} · {esc(overlay_date)} · {esc(_filters_text(nbr_entry))}</span></div>"
                    )
                st.plotly_chart(
                    _map_figure(
                        district,
                        geojson,
                        centers,
                        center,
                        metric,
                        item,
                        float(nat[item["national"]]),
                        supply_points=overlay_points,
                    ),
                    use_container_width=True,
                    key="ov_district_map",
                    config={"displayModeBar": False, "scrollZoom": True},
                )
                if combined and nbr_state is not None and not nbr_state.available:
                    render_html(context_state_html(nbr_state, label=item["short"]))
            with list_col:
                render_html(_ranking_html(district, metric, item))
                if recommendations:
                    render_recommendations(recommendations, title="Where to look next")
                st.button(
                    "Open the District explorer",
                    key="ov_open_districts",
                    on_click=_open_district_explorer,
                    use_container_width=True,
                    icon=":material/map:",
                )
        else:
            render_html(_ranking_html(district, metric, item))
            if recommendations:
                render_recommendations(recommendations, title="Where to look next")

        render_html(
            f'<div class="micro">A typical district estimate carries a sampling margin of about '
            f"±{typical:.1f} pp under a simple-random-sample approximation. This is a district-only "
            "illustrative margin, not a significance test for district-to-district or district-to-national "
            "differences; the survey design information is unavailable.</div>"
        )

        with st.expander("View district data"):
            show_district_table(
                district,
                sort_by=metric,
                key="download_district_results",
                file_name="rwanda_district_indicator_results.csv",
                height=400,
            )
        if combined and nbr_entry is not None:
            with st.expander("NBR observations behind the map markers"):
                st.caption(
                    f"{nbr_entry['metric_label']} · {overlay_date} · {_filters_text(nbr_entry)}. "
                    "Districts without a recorded observation are unknown, not zero."
                )
                st.dataframe(
                    snapshot_table(
                        overlay_points, sorted(district["District"].astype(str))
                    ),
                    use_container_width=True,
                    hide_index=True,
                    height=320,
                )

    st.markdown("")
    note(
        "How to interpret these figures",
        "These are survey-based weighted estimates from FinScope Rwanda 2024, not live measurements. "
        "A district with lower bank-account ownership may warrant further investigation, but these figures "
        "alone do not explain why the gap exists. Borrowing activity also does not measure every dimension "
        "of access to credit."
        + (
            " NBR values are administrative observations with their own units, dates and filters; "
            "they sit beside the survey estimates and are never combined with them."
            if combined
            else ""
        ),
    )
    render_html(
        '<div class="src-note">Source: FinScope Rwanda 2024'
        + (
            " (survey) and NBR administrative observations (supply side)"
            if combined
            else ""
        )
        + ". See Methodology &amp; sources for "
        "indicator definitions, data checks and limitations.</div>"
    )
