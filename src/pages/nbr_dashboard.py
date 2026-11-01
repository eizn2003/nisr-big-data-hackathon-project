"""Shared mode selection and data-driven NBR dashboard components."""

from __future__ import annotations

import hashlib
import json
import math
import time
from collections import defaultdict
from datetime import date, datetime
from typing import Any, Mapping, Sequence

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from pymongo.errors import PyMongoError

from src import data
from src.data_sources.mongodb_district_explorer import (
    load_district_reference,
    parse_numeric_value,
)
from src.models.nbr_intelligence.contextualization import (
    _filters_match,
    prepare_source_points,
)
from src.models.nbr_intelligence.experiment import load_mongodb_history
from src.models.nbr_intelligence.indicator_mapping import (
    DISPLAYABLE_RELATIONSHIPS,
    MAPPING_BY_VARIABLE,
)
from src.styles import (
    PALETTE,
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

MODE_KEY = "global_dashboard_mode"
MODES = ("Combined", "FinScope", "NBR Supply")
DEFAULT_MODE = "Combined"
MODE_ACCENTS = {
    "Combined": "#1A8A7D",
    "FinScope": "#1A8A7D",
    "NBR Supply": "#2F6FB3",
}
SUPPLY_ACCENT = "#2F6FB3"
NBR_NOTICE = (
    "This feature is in beta. Administrative trends and intelligence findings "
    "are experimental signals intended to support exploration and human review. "
    "Results may be incomplete or produce false alerts and should not be treated "
    "as confirmed changes in financial inclusion or as standalone grounds for "
    "policy decisions."
)
NBR_PAGE_LABELS = {
    "agents": "Agents",
    "branches": "Branches",
    "cards": "Cards",
    "credit": "Credit",
    "depositors": "Depositors",
    "inclusion": "Inclusion",
    "insurance": "Insurance",
    "internet_banking": "Internet Banking",
    "merchants": "Merchants",
    "mobile_banking": "Mobile Banking",
    "pos": "POS",
    "savings": "Savings",
    "transactional": "Transactional",
}
NATIONAL_HEADER_KPIS = (
    {
        "page": "transactional",
        "page_label": "Transactional",
        "metric": "Total Accounts",
        "label": "Active transactional accounts",
        "unit": "accounts",
        "filters": {
            "Gender": "All",
            "Age Segment": "All",
            "Account Status": "Active",
            "Account Type": "All",
            "Institution Type": "All",
            "Location": "All",
        },
        "context": "Accounts are not necessarily unique people.",
    },
    {
        "page": "pos",
        "page_label": "POS",
        "metric": "Total POS",
        "label": "Active POS terminals",
        "unit": "terminals",
        "filters": {
            "Terminal Status": "Active",
            "Institution Type": "All",
            "Location": "All",
        },
        "context": "Terminal count; not transaction volume or service coverage.",
    },
    {
        "page": "branches",
        "page_label": "Branches",
        "metric": "Total Branches",
        "label": "Active branches",
        "unit": "branches",
        "filters": {
            "Branch Status": "Active",
            "Institution Type": "All",
            "Location": "All",
        },
        "context": "Branch count; not a customer or inclusion measure.",
    },
)
NATIONAL_INCLUSION_FILTERS = {
    "Gender": "All",
    "Age Segment": "All",
    "Institution Type": "All",
    "Account/Policy Status": "Active",
    "Location": "All",
}
NATIONAL_INFRASTRUCTURE_REPORTING_DATE = "2026-10-24"
NATIONAL_CUSTOMER_COMPARISON_REPORTING_DATE = "2026-10-27"
NATIONAL_INFRASTRUCTURE_SERIES = (
    {
        "page": "branches",
        "page_label": "Branches",
        "district_metric": "Branches",
        "national_metric": "Total Branches",
        "title": "Active Branches by District",
        "unit": "branches",
        "chart_style": "ranked_bar",
        "height": 850,
        "filters": {
            "Branch Status": "Active",
            "Institution Type": "All",
            "Location": "All",
        },
        "color": "#2F6FB3",
    },
    {
        "page": "pos",
        "page_label": "POS",
        "district_metric": "POS",
        "national_metric": "Total POS",
        "title": "Active POS Terminals by District",
        "unit": "terminals",
        "chart_style": "lollipop",
        "height": 780,
        "filters": {
            "Terminal Status": "Active",
            "Institution Type": "All",
            "Location": "All",
        },
        "color": "#1A8A7D",
    },
)
NATIONAL_CUSTOMER_COMPARISONS = (
    {
        "key": "gender",
        "title": "Female vs Male",
        "metric": "Customers",
        "groups": (
            {
                "label": "Female",
                "filters": {
                    "Account/Policy Status": "Active",
                    "Age Segment": "All",
                    "Gender": "Female",
                    "Institution Type": "All",
                    "Location": "All",
                },
                "unknown_key": "Gender:Female",
                "color": "#3969AC",
            },
            {
                "label": "Male",
                "filters": {
                    "Account/Policy Status": "Active",
                    "Age Segment": "All",
                    "Gender": "Male",
                    "Institution Type": "All",
                    "Location": "All",
                },
                "unknown_key": "Gender:Male",
                "color": "#D98944",
            },
        ),
    },
    {
        "key": "age_segment",
        "title": "Youth vs Non-Youth",
        "metric": "Customers",
        "groups": (
            {
                "label": "Youth",
                "filters": {
                    "Account/Policy Status": "Active",
                    "Age Segment": "Youth",
                    "Gender": "All",
                    "Institution Type": "All",
                    "Location": "All",
                },
                "unknown_key": "Age Segment:Youth",
                "color": "#7656A6",
            },
            {
                "label": "Non-Youth",
                "filters": {
                    "Account/Policy Status": "Active",
                    "Age Segment": "Non-Youth",
                    "Gender": "All",
                    "Institution Type": "All",
                    "Location": "All",
                },
                "unknown_key": "Age Segment:Non-Youth",
                "color": "#3A8C78",
            },
        ),
    },
)
_DIMENSIONS = {
    "Gender": "Gender",
    "Age Segment": "Age Segment (NBR Youth/Non-Youth)",
}
_POPULATION_GROUPS = {
    "Gender": ("Female", "Male"),
    "Age Segment": ("Youth", "Non-Youth"),
}
_POPULATION_GROUP_COLORS = {
    "Female": "#3969AC",
    "Male": "#D98944",
    "Youth": "#7656A6",
    "Non-Youth": "#3A8C78",
}


def current_mode() -> str:
    mode = st.session_state.get(MODE_KEY, DEFAULT_MODE)
    return mode if mode in MODES else DEFAULT_MODE


def render_mode_selector() -> None:
    if MODE_KEY not in st.session_state:
        st.session_state[MODE_KEY] = DEFAULT_MODE
    inject_nbr_styles()
    st.markdown(
        '<div class="sb-mode-label">Analysis mode</div>',
        unsafe_allow_html=True,
    )
    selected = current_mode()
    with st.container(key="sidebar_mode_selector"):
        for mode in MODES:
            st.button(
                mode,
                key=f"dashboard_mode_{mode.lower().replace(' ', '_')}",
                type="primary" if mode == selected else "secondary",
                use_container_width=True,
                on_click=_set_mode,
                args=(mode,),
                help={
                    "Combined": "FinScope survey results with NBR supply context alongside.",
                    "FinScope": "FinScope survey results only.",
                    "NBR Supply": "NBR administrative observations only.",
                }[mode],
            )
    if selected != "FinScope":
        if st.button(
            "Refresh NBR observations",
            key="refresh_nbr_observations",
            icon=":material/refresh:",
            use_container_width=True,
            help="Clear cached NBR observations and reload the read-only source.",
        ):
            _load_nbr_source_documents.clear()
            load_nbr_dashboard_data.clear()
            load_nbr_page_catalog.clear()
            st.rerun()


def _set_mode(mode: str) -> None:
    if mode not in MODES:
        raise ValueError(f"Unknown dashboard mode: {mode}")
    st.session_state[MODE_KEY] = mode


BETA_SUMMARY = (
    "Experimental administrative observations for exploration."
)

_NBR_CSS = """
:root{--nbr-accent:%(supply)s;--mode-accent:%(mode)s;--nbr-ink:#163D4B;--nbr-muted:#5B7480;--nbr-line:#DCE5E8;}
.nbr-tag{display:inline-flex;align-items:center;gap:4px;font-size:10.5px;font-weight:700;line-height:1;padding:3px 6px;border-radius:5px;background:rgba(47,111,179,.12);color:var(--nbr-accent);white-space:nowrap}
.nbr-tag.beta{background:#FFF1CC;color:#6B4E00}
.nbr-beta{display:flex;gap:10px;align-items:center;margin:2px 0 14px;padding:8px 12px;border-left:3px solid #E0A12F;background:#FFFAEE;color:#4D421F;font-size:12.5px;line-height:1.5;border-radius:4px}
.nbr-highlight-value{font-family:Fraunces,Georgia,serif;font-size:40px;font-weight:600;line-height:1.1;letter-spacing:-.02em;color:#163D4B;margin:14px 0 10px;font-variant-numeric:tabular-nums}
.st-key-card_nbr_highlight_inclusion,.st-key-card_nbr_highlight_unknown_district{min-height:210px}
.st-key-card_nbr_highlight_trend_transactional,.st-key-card_nbr_highlight_trend_pos,.st-key-card_nbr_highlight_trend_branches{min-height:380px}
.st-key-card_nbr_infrastructure_branches{background:linear-gradient(180deg,#F4F8FC 0%%,#FFFFFF 170px)!important}
.st-key-card_nbr_infrastructure_pos{background:linear-gradient(180deg,#F1F8F6 0%%,#FFFFFF 170px)!important}
.nbr-unknown-counts{display:flex;flex-wrap:wrap;justify-content:space-between;gap:8px 18px;margin-top:8px;padding:13px 15px;border:1px solid #DCE5E8;border-radius:10px;background:#F7F9FA;color:#536A76;font-size:12px}
.nbr-unknown-counts b{color:#163D4B;font-size:12.5px;font-weight:700;font-variant-numeric:tabular-nums}
.nbr-ctx{margin-top:10px;padding-top:9px;border-top:1px solid var(--nbr-line);font-size:12px;color:var(--nbr-muted)}
.nbr-ctx-top{display:flex;align-items:center;gap:7px;margin-bottom:3px}
.nbr-ctx-label{font-weight:600;color:var(--nbr-ink);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.nbr-ctx-row{display:flex;align-items:center;justify-content:space-between;gap:10px}
.nbr-ctx-val{font-size:17px;font-weight:700;color:var(--nbr-ink);font-variant-numeric:tabular-nums;line-height:1.2}
.nbr-ctx-val small{font-size:11.5px;font-weight:500;color:var(--nbr-muted);margin-left:3px}
.nbr-ctx-meta{margin-top:2px;font-size:11.5px;color:var(--nbr-muted)}
.nbr-ctx svg{flex:none;overflow:visible}
.nbr-ctx-stack .nbr-ctx{margin-top:0;border-top:0;padding:10px 0 2px}
.nbr-empty{padding:22px 20px;border:1px dashed var(--nbr-line);border-radius:10px;background:rgba(255,255,255,.55);text-align:left}
.nbr-empty b{display:block;font-size:14.5px;color:var(--nbr-ink);margin-bottom:4px}
.nbr-empty span{font-size:13px;color:var(--nbr-muted);line-height:1.55}
@media (max-width:640px){.nbr-ctx-val{font-size:15px}.nbr-beta{font-size:12px}}
"""


def inject_nbr_styles() -> None:
    """Add the small set of NBR/Combined classes on top of the shared stylesheet."""
    css = _NBR_CSS % {"supply": SUPPLY_ACCENT, "mode": MODE_ACCENTS[current_mode()]}
    render_html("<style>" + " ".join(css.split()) + "</style>")


def fmt_value(value: Any) -> str:
    """Readable number: thousands separators for counts, 4 significant figures otherwise."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if math.isnan(number):
        return "n/a"
    return f"{number:,.0f}" if abs(number) >= 1000 else f"{number:,.4g}"


def fmt_delta(value: float) -> str:
    return ("+" if value > 0 else "-" if value < 0 else "") + fmt_value(abs(value))


def _exact_number(value: float) -> str:
    return f"{float(value):,.15g}"


def _national_supply_header_html(
    points: Sequence[Mapping[str, Any]],
) -> str:
    """Render the three approved supply KPIs from eligible normalized points."""
    cards = []
    for spec in NATIONAL_HEADER_KPIS:
        series = [
            point for point in points
            if point.get("page") == spec["page"]
            and point.get("metric_label") == spec["metric"]
            and point.get("source_type") == "national_kpi"
            and point.get("geography_level") == "national"
            and point.get("geography") == "Rwanda"
            and point.get("filters") == spec["filters"]
            and point.get("unit") == "count"
            and point.get("unit_status") == "configured_source_label"
            and point.get("repeated_snapshot_warning") is not True
        ]
        latest = max(
            series,
            key=lambda point: str(point.get("reporting_date", "")),
            default=None,
        )
        value = fmt_value(latest["value"]) if latest else "Unavailable"
        reporting_date = (
            esc(latest["reporting_date"]) if latest else "No eligible observation"
        )
        source = (
            f"NBR {esc(spec['page_label'])} · {esc(spec['metric'])}<br>"
            f"{reporting_date} · {esc(_filter_label(spec['filters']))}<br>"
            f"{esc(spec['context'])}"
        )
        cards.append(kpi_card(
            spec["label"],
            esc(value),
            spec["unit"],
            0,
            SUPPLY_ACCENT,
            source,
        ))
    return kpi_grid(cards, columns=3)


def _population_group_header_html(
    points: Sequence[Mapping[str, Any]],
    unknown_counts: Mapping[str, Any] | None = None,
) -> str:
    """Render the four population cards from exact national Inclusion series."""
    cards = []
    for comparison in NATIONAL_CUSTOMER_COMPARISONS:
        for group in comparison["groups"]:
            filters = group["filters"]
            series = [
                point for point in points
                if point.get("page") == "inclusion"
                and point.get("metric_label") == "Total Customers"
                and point.get("source_type") == "national_kpi"
                and point.get("geography_level") == "national"
                and point.get("geography") == "Rwanda"
                and point.get("filters") == filters
                and point.get("unit") == "count"
                and point.get("unit_status") == "configured_source_label"
                and point.get("repeated_snapshot_warning") is not True
            ]
            dated: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
            for point in series:
                reporting_date = str(point.get("reporting_date", ""))
                try:
                    date.fromisoformat(reporting_date)
                    value = float(point.get("value"))
                except (TypeError, ValueError):
                    continue
                if math.isfinite(value) and value >= 0:
                    dated[reporting_date].append(point)

            latest_date = max(dated, default=None)
            latest = dated[latest_date] if latest_date else []
            selected = latest[0] if len(latest) == 1 else None
            value = fmt_value(selected["value"]) if selected else "Unavailable"
            if selected:
                reporting_date = (
                    f"Total Customers · {esc(_display_reporting_date(latest_date))}"
                )
                unknown_count = (
                    unknown_counts.get(group["unknown_key"])
                    if latest_date == NATIONAL_CUSTOMER_COMPARISON_REPORTING_DATE
                    and isinstance(unknown_counts, Mapping)
                    else None
                )
                unknown_context = (
                    f"Unknown geography (separate): {fmt_value(unknown_count)}"
                    if unknown_count is not None
                    else "Unknown geography: not verified for this date"
                )
            else:
                reporting_date = (
                    "No unique eligible observation"
                    if latest_date
                    else "No eligible observation"
                )
                unknown_context = "Unknown geography: not verified"

            source = (
                f"NBR Inclusion · {reporting_date}<br>"
                f"{esc(unknown_context)}"
            )
            group_family = (
                "Gender" if comparison["key"] == "gender" else "Age Segment"
            )
            cards.append(kpi_card(
                f"{group_family} · {group['label']}",
                esc(value),
                "customers",
                0,
                group["color"],
                source,
                show_track=False,
            ))
    return kpi_grid(cards, columns=4)


def _national_highlight_metadata(
    points: Sequence[Mapping[str, Any]],
    runs: Sequence[Mapping[str, Any]],
    kpi_documents: Sequence[Mapping[str, Any]],
    table_documents: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Keep source display values and unknown-district counts tied to eligible evidence."""
    inclusion_series = [
        point for point in points
        if point.get("page") == "inclusion"
        and point.get("metric_label") == "Financially Included"
        and point.get("source_type") == "national_kpi"
        and point.get("geography_level") == "national"
        and point.get("geography") == "Rwanda"
        and point.get("filters") == NATIONAL_INCLUSION_FILTERS
        and point.get("repeated_snapshot_warning") is not True
    ]
    latest = max(
        inclusion_series,
        key=lambda point: str(point.get("reporting_date", "")),
        default=None,
    )
    empty = {
        "inclusion_value": None,
        "inclusion_reporting_date": None,
        "inclusion_collected_at": None,
        "inclusion_quality_qualifications": [],
        "unknown_customer_count": None,
        "unknown_reporting_date": None,
    }
    if latest is None:
        return empty

    identity = (
        str(latest["page"]),
        str(latest["reporting_date"]),
        str(latest.get("combo_key", "")),
    )
    matching_runs = [
        run for run in runs
        if (
            str(run.get("page", "")),
            str(run.get("snapshot_date", "")),
            str(run.get("combo_key", "")),
        ) == identity
        and run.get("run_id") == latest.get("run_id")
        and run.get("status") == "complete"
        and run.get("repeated_snapshot_warning") is not True
        and run.get("filters") == NATIONAL_INCLUSION_FILTERS
        and (
            not isinstance(run.get("filters_requested"), Mapping)
            or run.get("filters_requested") == NATIONAL_INCLUSION_FILTERS
        )
    ]
    matching_kpis = [
        document for document in kpi_documents
        if (
            str(document.get("page", "")),
            str(document.get("snapshot_date", "")),
            str(document.get("combo_key", "")),
        ) == identity
        and document.get("run_id") == latest.get("run_id")
        and document.get("filters") == NATIONAL_INCLUSION_FILTERS
        and (
            not isinstance(document.get("filters_requested"), Mapping)
            or document.get("filters_requested") == NATIONAL_INCLUSION_FILTERS
        )
    ]
    if len(matching_runs) != 1 or len(matching_kpis) != 1:
        return empty

    run = matching_runs[0]
    kpi_document = matching_kpis[0]
    inclusion_metrics = [
        metric for metric in kpi_document.get("kpis", [])
        if isinstance(metric, Mapping)
        and metric.get("metric_type") in (None, "headline_kpi")
        and metric.get("metric_label") == "Financially Included"
    ]
    if len(inclusion_metrics) != 1:
        return empty
    source_value = inclusion_metrics[0].get("metric_value")
    if not isinstance(source_value, str) or not source_value.strip().endswith("%"):
        return empty
    try:
        source_numeric_value = float(source_value.strip()[:-1].replace(",", ""))
    except ValueError:
        return empty
    if (
        not math.isfinite(source_numeric_value)
        or source_numeric_value != float(latest["value"])
    ):
        return empty
    collected_at = kpi_document.get("collected_at") or run.get("collected_at")
    if isinstance(collected_at, datetime):
        collected_at = collected_at.isoformat()
    try:
        datetime.fromisoformat(str(collected_at).replace("Z", "+00:00"))
    except ValueError:
        return empty

    unknown_rows = [
        row for row in table_documents
        if (
            str(row.get("page", "")),
            str(row.get("snapshot_date", "")),
            str(row.get("combo_key", "")),
        ) == identity
        and row.get("run_id") == latest.get("run_id")
        and row.get("filters") == NATIONAL_INCLUSION_FILTERS
        and (
            not isinstance(row.get("filters_requested"), Mapping)
            or row.get("filters_requested") == NATIONAL_INCLUSION_FILTERS
        )
        and str(row.get("district", "")).strip().casefold() == "unknown"
        and row.get("district_known") is False
    ]
    unknown_customer_count = None
    if len(unknown_rows) == 1:
        unknown_row = unknown_rows[0]
        row_collected_at = unknown_row.get("collected_at") or run.get("collected_at")
        try:
            datetime.fromisoformat(str(row_collected_at).replace("Z", "+00:00"))
        except ValueError:
            row_collected_at = None
        values = unknown_row.get("values")
        raw_count = values.get("Customers") if isinstance(values, Mapping) else None
        try:
            parsed_count = float(str(raw_count).replace(",", ""))
        except (TypeError, ValueError):
            parsed_count = math.nan
        if (
            row_collected_at is not None
            and math.isfinite(parsed_count)
            and parsed_count >= 0
            and parsed_count.is_integer()
        ):
            unknown_customer_count = int(parsed_count)

    return {
        "inclusion_value": source_value.strip(),
        "inclusion_reporting_date": str(latest["reporting_date"]),
        "inclusion_collected_at": str(collected_at) if collected_at else None,
        "inclusion_quality_qualifications": list(
            latest.get("quality_qualifications") or []
        ),
        "unknown_customer_count": unknown_customer_count,
        "unknown_reporting_date": (
            str(latest["reporting_date"]) if unknown_customer_count is not None else None
        ),
    }


def _national_kpi_series(
    points: Sequence[Mapping[str, Any]],
    spec: Mapping[str, Any],
) -> list[Mapping[str, Any]]:
    return sorted(
        (
            point for point in points
            if point.get("page") == spec["page"]
            and point.get("metric_label") == spec["metric"]
            and point.get("source_type") == "national_kpi"
            and point.get("geography_level") == "national"
            and point.get("geography") == "Rwanda"
            and point.get("filters") == spec["filters"]
            and point.get("unit") == "count"
            and point.get("unit_status") == "configured_source_label"
            and point.get("repeated_snapshot_warning") is not True
        ),
        key=lambda point: str(point.get("reporting_date", "")),
    )


def _national_highlight_figure(
    points: Sequence[Mapping[str, Any]],
    page: str,
) -> go.Figure:
    ordered = sorted(points, key=lambda point: str(point["reporting_date"]))
    dates = [str(point["reporting_date"]) for point in ordered]
    values = [float(point["value"]) for point in ordered]
    labels = [fmt_value(value) for value in values]
    unit = str(ordered[0].get("unit") or "count") if ordered else "count"
    y_max = max(values, default=0.0) * 1.2 or 1.0
    fig = go.Figure()

    if page == "transactional":
        fig.add_trace(go.Scatter(
            x=dates,
            y=values,
            mode="lines+markers+text",
            text=labels,
            textposition="top center",
            cliponaxis=False,
            line=dict(color="#247D8B", width=3),
            marker=dict(
                size=10,
                color="#FFFFFF",
                line=dict(color="#247D8B", width=3),
            ),
            fill="tozeroy",
            fillcolor="rgba(36,125,139,0.12)",
            hovertemplate=(
                "<b>%{x}</b><br>Observed: %{y:,.0f} "
                f"{esc(unit)}<extra>Active transactional accounts</extra>"
            ),
        ))
    elif page == "pos":
        palette = ["#D8E5F1", "#B6CDE2", "#8DAFCF", "#5F8FB8", "#286C91"]
        colors = [
            palette[round(index * (len(palette) - 1) / max(len(values) - 1, 1))]
            for index in range(len(values))
        ]
        fig.add_trace(go.Bar(
            x=dates,
            y=values,
            text=labels,
            textposition="outside",
            cliponaxis=False,
            marker=dict(
                color=colors,
                line=dict(color="#FFFFFF", width=1.5),
            ),
            hovertemplate=(
                "<b>%{x}</b><br>Observed: %{y:,.0f} "
                f"{esc(unit)}<extra>Active POS terminals</extra>"
            ),
        ))
    elif page == "branches":
        stem_x = []
        stem_y = []
        for reporting_date, value in zip(dates, values):
            stem_x.extend((reporting_date, reporting_date, None))
            stem_y.extend((0, value, None))
        fig.add_trace(go.Scatter(
            x=stem_x,
            y=stem_y,
            mode="lines",
            line=dict(color="rgba(195,126,56,0.42)", width=3),
            hoverinfo="skip",
            showlegend=False,
        ))
        fig.add_trace(go.Scatter(
            x=dates,
            y=values,
            mode="markers+text",
            text=labels,
            textposition="top center",
            cliponaxis=False,
            marker=dict(
                size=13,
                symbol="diamond",
                color="#C37E38",
                line=dict(color="#FFFFFF", width=2),
            ),
            hovertemplate=(
                "<b>%{x}</b><br>Observed: %{y:,.0f} "
                f"{esc(unit)}<extra>Active branches</extra>"
            ),
        ))
    else:
        raise ValueError(f"Unknown national highlight chart page: {page}")

    fig.update_xaxes(
        title=None,
        type="category",
        showgrid=False,
        tickfont=dict(size=11, color=PALETTE["muted"]),
        linecolor=PALETTE["line"],
        ticks="outside",
        ticklen=5,
    )
    fig.update_yaxes(
        title=unit,
        range=[0, y_max],
        gridcolor=PALETTE["grid"],
        zeroline=False,
        tickfont=dict(size=11, color=PALETTE["muted"]),
        ticks="outside",
        ticklen=4,
    )
    return style_chart(
        fig,
        310,
        margin=dict(l=8, r=16, t=48, b=24),
        bargap=0.48,
    )


def _national_infrastructure_series(
    points: Sequence[Mapping[str, Any]],
    spec: Mapping[str, Any],
) -> tuple[list[Mapping[str, Any]], Mapping[str, Any] | None]:
    district_points = [
        point for point in points
        if point.get("page") == spec["page"]
        and point.get("metric_label") == spec["district_metric"]
        and point.get("source_type") == "district_table"
        and point.get("geography_level") == "district"
        and str(point.get("geography", "")).strip().casefold() != "unknown"
        and point.get("reporting_date") == NATIONAL_INFRASTRUCTURE_REPORTING_DATE
        and point.get("filters") == spec["filters"]
        and point.get("unit") == "count"
        and point.get("unit_status") == "source_column"
        and point.get("repeated_snapshot_warning") is not True
    ]
    district_names = [str(point.get("geography", "")).strip() for point in district_points]
    if len(district_names) != len(set(district_names)):
        return [], None
    district_points.sort(
        key=lambda point: (
            float(point["value"]),
            str(point.get("geography", "")).casefold(),
        )
    )
    national_points = [
        point for point in points
        if point.get("page") == spec["page"]
        and point.get("metric_label") == spec["national_metric"]
        and point.get("source_type") == "national_kpi"
        and point.get("geography_level") == "national"
        and point.get("geography") == "Rwanda"
        and point.get("reporting_date") == NATIONAL_INFRASTRUCTURE_REPORTING_DATE
        and point.get("filters") == spec["filters"]
        and point.get("unit") == "count"
        and point.get("unit_status") == "configured_source_label"
        and point.get("repeated_snapshot_warning") is not True
    ]
    return district_points, national_points[0] if len(national_points) == 1 else None


def _national_infrastructure_figure(
    observations: Sequence[Mapping[str, Any]],
    spec: Mapping[str, Any],
) -> go.Figure:
    ordered = sorted(
        observations,
        key=lambda point: (
            -float(point["value"]),
            str(point.get("geography", "")).casefold(),
        ),
    )
    labels = [str(point["geography"]) for point in ordered]
    values = [float(point["value"]) for point in ordered]
    provenance = [
        [
            str(point.get("reporting_date", "")),
            str(point.get("run_id", "")),
            str(point.get("source_record_id", "")),
            str(point.get("collected_at", "")),
        ]
        for point in ordered
    ]
    hovertemplate = (
        "<b>%{y}</b><br>"
        f"{esc(spec['district_metric'])}: %{{x:,.0f}} {esc(spec['unit'])}<br>"
        "Reporting date: %{customdata[0]}<br>"
        "Run ID: %{customdata[1]}<br>"
        "Source record: %{customdata[2]}<br>"
        "Collected at: %{customdata[3]}<extra></extra>"
    )
    fig = go.Figure()
    if spec["chart_style"] == "ranked_bar":
        fig.add_trace(go.Bar(
            x=values,
            y=labels,
            orientation="h",
            text=values,
            texttemplate="%{text:,.0f}",
            textposition="outside",
            textfont=dict(size=12, color="#183A5B"),
            marker=dict(
                color="#28669B",
                line=dict(color="#17466F", width=0.8),
            ),
            cliponaxis=False,
            customdata=provenance,
            hovertemplate=hovertemplate,
        ))
        fig.update_layout(bargap=0.34)
        grid_color = "#E3EAF1"
        tick_color = "#35536F"
    elif spec["chart_style"] == "lollipop":
        fig.add_trace(go.Bar(
            x=values,
            y=labels,
            orientation="h",
            marker=dict(
                color="#DFECE9",
                line=dict(color="#DFECE9", width=0),
            ),
            hoverinfo="skip",
            showlegend=False,
        ))
        fig.add_trace(go.Scatter(
            x=values,
            y=labels,
            mode="markers+text",
            text=[fmt_value(value) for value in values],
            textposition="middle right",
            textfont=dict(size=12, color="#075C53"),
            marker=dict(
                size=13,
                color="#0D8174",
                line=dict(color="#FFFFFF", width=2),
                symbol="circle",
            ),
            cliponaxis=False,
            customdata=provenance,
            hovertemplate=hovertemplate,
            showlegend=False,
        ))
        fig.update_layout(bargap=0.72)
        grid_color = "#DCEBE8"
        tick_color = "#2D625C"
    else:
        raise ValueError(f"Unknown infrastructure chart style: {spec['chart_style']}")

    fig.update_layout(
        showlegend=False,
        plot_bgcolor="#FFFFFF",
        paper_bgcolor="#FFFFFF",
    )
    fig.update_xaxes(
        title=spec["unit"].capitalize(),
        rangemode="tozero",
        range=[0, max(values, default=0) * 1.16 or 1],
        gridcolor=grid_color,
        zeroline=False,
        tickformat=",.0f",
        ticks="outside",
        ticklen=5,
        tickcolor="#A9B8C2",
        tickfont=dict(size=11, color=tick_color),
        title_font=dict(size=12, color=tick_color),
    )
    fig.update_yaxes(
        title=None,
        autorange="reversed",
        showgrid=False,
        automargin=True,
        tickfont=dict(size=12, color=tick_color),
    )
    return style_chart(
        fig,
        max(spec["height"], 23 * len(labels) + 150),
        margin=dict(l=8, r=64, t=26, b=48),
    )


def _render_nbr_infrastructure_by_district(
    points: Sequence[Mapping[str, Any]],
) -> None:
    section_title(
        "Recorded Financial-Service Infrastructure by District",
        "NBR district observations · reporting date 24 October 2026",
    )
    for spec in NATIONAL_INFRASTRUCTURE_SERIES:
        with st.container(key=f"card_nbr_infrastructure_{spec['page']}"):
            card_title(
                spec["title"],
                f"NBR {spec['page_label']} · {spec['district_metric']} · "
                f"{_display_reporting_date(NATIONAL_INFRASTRUCTURE_REPORTING_DATE)} · "
                f"{_filter_label(spec['filters'])}",
            )
            district_points, national_point = _national_infrastructure_series(
                points,
                spec,
            )
            if not district_points or national_point is None:
                st.info(
                    "Eligible district observations and a matching national KPI "
                    "are not available for this reporting date."
                )
                continue
            st.plotly_chart(
                _national_infrastructure_figure(district_points, spec),
                use_container_width=True,
                config={"displayModeBar": False},
                key=f"nbr_infrastructure_{spec['page']}_20261024",
            )


def _national_customer_comparison_series(
    points: Sequence[Mapping[str, Any]],
    comparison: Mapping[str, Any],
) -> dict[str, list[Mapping[str, Any]]] | None:
    selected: dict[str, list[Mapping[str, Any]]] = {}
    district_sets: list[set[str]] = []
    for group in comparison["groups"]:
        observations = [
            point for point in points
            if point.get("page") == "inclusion"
            and point.get("metric_label") == comparison["metric"]
            and point.get("source_type") == "district_table"
            and point.get("geography_level") == "district"
            and point.get("reporting_date")
            == NATIONAL_CUSTOMER_COMPARISON_REPORTING_DATE
            and point.get("filters") == group["filters"]
            and point.get("unit") == "count"
            and point.get("unit_status") == "source_column"
            and str(point.get("geography", "")).strip()
            and str(point.get("geography", "")).strip().casefold() != "unknown"
            and point.get("repeated_snapshot_warning") is not True
        ]
        districts = [str(point["geography"]).strip() for point in observations]
        folded_districts = {district.casefold() for district in districts}
        if not observations or len(districts) != len(folded_districts):
            return None
        selected[group["label"]] = observations
        district_sets.append(set(districts))
    if not district_sets or any(names != district_sets[0] for names in district_sets[1:]):
        return None
    return selected


def _national_customer_unknown_counts(
    points: Sequence[Mapping[str, Any]],
    runs: Sequence[Mapping[str, Any]],
    table_documents: Sequence[Mapping[str, Any]],
) -> dict[str, int | None]:
    comparisons = NATIONAL_CUSTOMER_COMPARISONS
    result: dict[str, int | None] = {
        group["unknown_key"]: None
        for comparison in comparisons
        for group in comparison["groups"]
    }
    for comparison in comparisons:
        for group in comparison["groups"]:
            group_points = [
                point for point in points
                if point.get("page") == "inclusion"
                and point.get("metric_label") == comparison["metric"]
                and point.get("source_type") == "district_table"
                and point.get("geography_level") == "district"
                and point.get("reporting_date")
                == NATIONAL_CUSTOMER_COMPARISON_REPORTING_DATE
                and point.get("filters") == group["filters"]
                and point.get("unit") == "count"
                and point.get("unit_status") == "source_column"
            ]
            if not group_points:
                continue
            identities = {
                (
                    str(point.get("page", "")),
                    str(point.get("reporting_date", "")),
                    str(point.get("combo_key", "")),
                    str(point.get("run_id", "")),
                )
                for point in group_points
            }
            if len(identities) != 1:
                continue
            page, reporting_date, combo_key, run_id = next(iter(identities))
            matching_runs = [
                run for run in runs
                if (
                    str(run.get("page", "")),
                    str(run.get("snapshot_date", "")),
                    str(run.get("combo_key", "")),
                    str(run.get("run_id", "")),
                ) == (page, reporting_date, combo_key, run_id)
                and run.get("status") == "complete"
                and run.get("repeated_snapshot_warning") is not True
                and run.get("filters") == group["filters"]
                and (
                    not isinstance(run.get("filters_requested"), Mapping)
                    or run.get("filters_requested") == group["filters"]
                )
                and run.get("collected_at") is not None
            ]
            matching_rows = [
                row for row in table_documents
                if (
                    str(row.get("page", "")),
                    str(row.get("snapshot_date", "")),
                    str(row.get("combo_key", "")),
                    str(row.get("run_id", "")),
                ) == (page, reporting_date, combo_key, run_id)
                and row.get("filters") == group["filters"]
                and (
                    not isinstance(row.get("filters_requested"), Mapping)
                    or row.get("filters_requested") == group["filters"]
                )
                and str(row.get("district", "")).strip().casefold() == "unknown"
                and row.get("district_known") is False
            ]
            if len(matching_runs) != 1 or len(matching_rows) != 1:
                continue
            collected_at = (
                matching_rows[0].get("collected_at")
                or matching_runs[0].get("collected_at")
            )
            if isinstance(collected_at, datetime):
                collected_at = collected_at.isoformat()
            try:
                datetime.fromisoformat(str(collected_at).replace("Z", "+00:00"))
            except ValueError:
                continue
            values = matching_rows[0].get("values")
            raw_value = (
                values.get(comparison["metric"])
                if isinstance(values, Mapping)
                else None
            )
            try:
                value = float(str(raw_value).replace(",", ""))
            except (TypeError, ValueError):
                continue
            if math.isfinite(value) and value >= 0 and value.is_integer():
                result[group["unknown_key"]] = int(value)
    return result


def _national_customer_comparison_figure(
    observations: Mapping[str, Sequence[Mapping[str, Any]]],
    comparison: Mapping[str, Any],
) -> go.Figure:
    groups = comparison["groups"]
    totals: dict[str, float] = defaultdict(float)
    by_group_district: dict[str, dict[str, Mapping[str, Any]]] = {}
    for group in groups:
        values_by_district = {
            str(point["geography"]).strip(): point
            for point in observations[group["label"]]
        }
        by_group_district[group["label"]] = values_by_district
        for district, point in values_by_district.items():
            totals[district] += float(point["value"])
    district_order = sorted(
        totals,
        key=lambda district: (-totals[district], district.casefold()),
    )
    max_value = max(
        (
            float(point["value"])
            for group_points in observations.values()
            for point in group_points
        ),
        default=0,
    )
    figure = go.Figure()
    for group in groups:
        district_points = by_group_district[group["label"]]
        ordered_points = [district_points[district] for district in district_order]
        figure.add_trace(go.Bar(
            name=group["label"],
            x=[float(point["value"]) for point in ordered_points],
            y=district_order,
            orientation="h",
            text=[_compact_customer_count(point["value"]) for point in ordered_points],
            textposition="outside",
            textfont=dict(size=10, color=PALETTE["ink"]),
            marker=dict(
                color=group["color"],
                line=dict(color="#FFFFFF", width=0.8),
            ),
            cliponaxis=False,
            customdata=[
                [
                    point.get("reporting_date", ""),
                    point.get("run_id", ""),
                    point.get("source_record_id", ""),
                    point.get("collected_at", ""),
                    _filter_label(group["filters"]),
                ]
                for point in ordered_points
            ],
            hovertemplate=(
                "<b>%{y}</b><br>"
                f"{esc(group['label'])} · {esc(comparison['metric'])}: "
                "%{x:,.0f} customers<br>"
                "Reporting date: %{customdata[0]}<br>"
                "Filters: %{customdata[4]}<br>"
                "Run ID: %{customdata[1]}<br>"
                "Source record: %{customdata[2]}<extra></extra>"
            ),
        ))
    figure.update_layout(
        barmode="group",
        bargap=0.26,
        bargroupgap=0.05,
        plot_bgcolor="#FFFFFF",
        paper_bgcolor="#FFFFFF",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0,
            title=None,
        ),
    )
    figure.update_xaxes(
        title="Customers (count)",
        range=[0, max_value * 1.18 or 1],
        tickformat=".3~s",
        gridcolor=PALETTE["grid"],
        zeroline=False,
        ticks="outside",
        ticklen=5,
    )
    figure.update_yaxes(
        title=None,
        autorange="reversed",
        showgrid=False,
        automargin=True,
        tickfont=dict(size=11, color=PALETTE["ink"]),
    )
    return style_chart(
        figure,
        max(980, 27 * len(district_order) + 180),
        margin=dict(l=8, r=58, t=54, b=48),
    )


def _compact_customer_count(value: Any) -> str:
    count = float(value)
    if abs(count) >= 1_000_000:
        return f"{count / 1_000_000:.1f}M"
    if abs(count) >= 10_000:
        return f"{count / 1_000:.0f}k"
    if abs(count) >= 1_000:
        return f"{count / 1_000:.1f}k"
    return fmt_value(count)


def _render_nbr_customer_counts_by_district(
    points: Sequence[Mapping[str, Any]],
    unknown_counts: Mapping[str, int | None] | None = None,
) -> None:
    unknown_counts = unknown_counts or {}
    section_title(
        "NBR Customer Counts by District and Demographic Group",
        "NBR Inclusion · reported Customers · "
        f"{_display_reporting_date(NATIONAL_CUSTOMER_COMPARISON_REPORTING_DATE)}",
    )
    for comparison in NATIONAL_CUSTOMER_COMPARISONS:
        with st.container(key=f"card_nbr_customer_comparison_{comparison['key']}"):
            observations = _national_customer_comparison_series(
                points,
                comparison,
            )
            filter_summary = " · ".join(
                f"{group['label']}: {_filter_label(group['filters'])}"
                for group in comparison["groups"]
            )
            district_count = (
                len(next(iter(observations.values())))
                if observations is not None else 0
            )
            card_title(
                comparison["title"],
                f"Metric: {comparison['metric']} · Reporting date: "
                f"{_display_reporting_date(NATIONAL_CUSTOMER_COMPARISON_REPORTING_DATE)}"
                f" · {district_count} districts · {filter_summary}",
            )
            if observations is None:
                st.info(
                    "A matching eligible district series for both groups is "
                    "not available for this reporting date."
                )
                continue
            st.plotly_chart(
                _national_customer_comparison_figure(observations, comparison),
                use_container_width=True,
                config={"displayModeBar": False},
                key=f"nbr_customer_comparison_{comparison['key']}_20261027",
            )
            unknown_labels = []
            for group in comparison["groups"]:
                unknown_value = unknown_counts.get(group["unknown_key"])
                display_value = (
                    fmt_value(unknown_value)
                    if unknown_value is not None
                    else "Unavailable"
                )
                unknown_labels.append(f"{group['label']}: {display_value}")
            render_html(
                '<div class="nbr-unknown-counts">'
                '<span>Unknown district · shown separately</span>'
                f"<b>{esc(' · '.join(unknown_labels))}</b>"
                "</div>"
            )


def _display_reporting_date(value: Any) -> str:
    try:
        return date.fromisoformat(str(value)).strftime("%d %B %Y")
    except ValueError:
        return str(value or "No eligible observation")


def _render_nbr_data_highlights(
    points: Sequence[Mapping[str, Any]],
    metadata: Mapping[str, Any] | None = None,
) -> None:
    metadata = metadata or {}
    section_title(
        "NBR Data Highlights",
        "Observed NBR administrative figures and a source-data quality note.",
    )

    top_row = st.columns(2, gap="medium")
    with top_row[0]:
        with st.container(key="card_nbr_highlight_inclusion"):
            card_title(
                "NBR-reported Financially Included",
                _display_reporting_date(metadata.get("inclusion_reporting_date")),
            )
            value = metadata.get("inclusion_value")
            render_html(
                '<div class="nbr-highlight-value">'
                f"{esc(value) if value else 'Unavailable'}"
                "</div>"
            )
            st.caption(
                "The source-reported denominator and population definition are not "
                "documented; do not interpret this as a confirmed share of Rwanda’s "
                "population."
            )
            qualifications = metadata.get("inclusion_quality_qualifications") or []
            for qualification in qualifications:
                st.warning(str(qualification.get("message", "Data-quality qualification.")))
    with top_row[1]:
        with st.container(key="card_nbr_highlight_unknown_district"):
            card_title(
                "District assignment",
                metadata.get("unknown_reporting_date") or "Inclusion snapshot",
            )
            unknown_count = metadata.get("unknown_customer_count")
            render_html(
                '<div class="nbr-highlight-value">'
                f"{fmt_value(unknown_count) if unknown_count is not None else 'Unavailable'}"
                "</div>"
            )
            st.caption(
                "customers are recorded with an `unknown` district assignment. "
                "They are not assigned to a named district in district-level results."
                if unknown_count is not None
                else "No eligible unknown-district count is available for this snapshot."
            )

    def render_trend_card(spec: Mapping[str, Any]) -> None:
        with st.container(key=f"card_nbr_highlight_trend_{spec['page']}"):
            series = _national_kpi_series(points, spec)
            dates = sorted({
                str(point["reporting_date"]) for point in series
            })
            date_context = (
                f"{dates[0]} to {dates[-1]} · {len(dates)} observed dates"
                if dates else "No eligible observations"
            )
            card_title(spec["label"], date_context)
            st.plotly_chart(
                _national_highlight_figure(series, spec["page"]),
                use_container_width=True,
                config={"displayModeBar": False},
                key=(
                    "nbr_highlight_chart_"
                    + hashlib.sha1(spec["page"].encode()).hexdigest()[:10]
                ),
            )

    render_trend_card(NATIONAL_HEADER_KPIS[0])
    secondary_columns = st.columns(2, gap="medium")
    for column, spec in zip(secondary_columns, NATIONAL_HEADER_KPIS[1:]):
        with column:
            render_trend_card(spec)


def kpi_trend_html(points: Sequence[Mapping[str, Any]]) -> str:
    """Sparkline row for the primary NBR KPI, so supply mode matches Combined mode."""
    series = sorted(points, key=lambda item: str(item.get("reporting_date", "")))
    if len(series) < 2:
        return ""
    return (
        '<div class="nbr-ctx"><div class="nbr-ctx-row"><div class="nbr-ctx-meta">'
        f"{len(series)} reports since {esc(series[0]['reporting_date'])}</div>"
        f"{sparkline_svg([p['value'] for p in series])}</div></div>"
    )


def humanize(text: Any) -> str:
    """Turn an internal relationship code into plain words."""
    return str(text or "").replace("_", " ").strip().capitalize()


def empty_state(title: str, body: str) -> None:
    render_html(
        f'<div class="nbr-empty"><b>{esc(title)}</b><span>{esc(body)}</span></div>'
    )


def sparkline_svg(
    values: Sequence[float],
    *,
    width: int = 104,
    height: int = 30,
    color: str = SUPPLY_ACCENT,
) -> str:
    """Tiny inline trend line. Only observed points are drawn; nothing is interpolated."""
    numbers = [float(v) for v in values if v is not None and not math.isnan(float(v))]
    if not numbers:
        return ""
    pad = 4
    low, high = min(numbers), max(numbers)
    span = high - low
    inner_w, inner_h = width - 2 * pad, height - 2 * pad

    def point(index: int, number: float) -> tuple[float, float]:
        x = pad + (inner_w * index / (len(numbers) - 1) if len(numbers) > 1 else inner_w / 2)
        y = pad + (inner_h * (1 - (number - low) / span) if span > 0 else inner_h / 2)
        return x, y

    coords = [point(i, n) for i, n in enumerate(numbers)]
    last_x, last_y = coords[-1]
    line = (
        f'<polyline points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in coords)}" fill="none" '
        f'stroke="{color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'
        if len(coords) > 1 else ""
    )
    return (
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="Trend across {len(numbers)} reporting dates">{line}'
        f'<circle cx="{last_x:.1f}" cy="{last_y:.1f}" r="3" fill="{color}" stroke="#fff" stroke-width="1.5"/></svg>'
    )


def _unit_label(value: Any, *, fallback: str = "unit not specified") -> str:
    label = str(value or "").strip()
    return label or fallback


def context_strip_html(
    entry: Mapping[str, Any],
    points: Sequence[Mapping[str, Any]] | None = None,
    *,
    scope: str = "",
    other_series: int = 0,
    show_limitations: bool = False,
) -> str:
    """Compact NBR context for a FinScope KPI: label, latest value, trend, date."""
    series = sorted(
        points if points is not None else entry.get("points", []),
        key=lambda item: str(item.get("reporting_date", "")),
    )
    if not series:
        return ""
    latest = series[-1]
    unit = _unit_label(entry.get("unit"))
    count = len({str(item["reporting_date"]) for item in series})
    meta = f"{esc(latest['reporting_date'])}"
    if scope:
        meta += f" · {esc(scope)}"
    meta += f" · {count} report{'s' if count != 1 else ''} · context only"
    if other_series:
        meta += f" · {other_series} related series in the detail view"
    return (
        f'<div class="nbr-ctx" title="{esc(entry.get("limitations", ""))}">'
        f'<div class="nbr-ctx-top"><span class="nbr-tag">NBR supply</span>'
        f'<span class="nbr-ctx-label">{esc(entry["metric_label"])}</span></div>'
        f'<div class="nbr-ctx-row"><div class="nbr-ctx-val">{esc(fmt_value(latest["value"]))}'
        f'<small>{esc(unit)}</small></div>{sparkline_svg([p["value"] for p in series])}</div>'
        f'<div class="nbr-ctx-meta">{meta}</div>'
        + (
            f'<div class="nbr-ctx-meta">{esc(entry.get("limitations", ""))}</div>'
            if show_limitations and entry.get("limitations") else ""
        )
        + "</div>"
    )


def render_beta_notice() -> None:
    render_html(
        f'<div class="nbr-beta" title="{esc(NBR_NOTICE)}"><span class="nbr-tag beta">Beta</span>'
        f"<span>{esc(BETA_SUMMARY)}</span></div>"
    )


@st.cache_data(ttl=900, show_spinner="Loading validated NBR observations...")
def load_nbr_dashboard_data(
    model_version: str,
    pages: tuple[str, ...] | None = None,
    scope_keys: tuple[tuple[str, str, str], ...] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]], str]:
    """Cache one normalized source snapshot, registry, and provenance digest."""
    load_started = time.perf_counter()
    if scope_keys is None:
        runs, kpis, tables, mongo_metrics = _load_nbr_source_documents(
            model_version,
            pages,
        )
    else:
        runs, kpis, tables, mongo_metrics = _load_nbr_source_documents(
            model_version,
            pages,
            scope_keys,
        )
    mongo_elapsed = time.perf_counter() - load_started
    preparation_started = time.perf_counter()
    points, summary = prepare_source_points(
        runs,
        kpis,
        tables,
        as_of_date=date.today(),
    )
    preparation_elapsed = time.perf_counter() - preparation_started
    if pages is None or "inclusion" in pages:
        summary["national_highlights"] = _national_highlight_metadata(
            points,
            runs,
            kpis,
            tables,
        )
        summary["national_customer_unknown_counts"] = (
            _national_customer_unknown_counts(points, runs, tables)
        )
    registry_started = time.perf_counter()
    registry = build_nbr_indicator_registry(points)
    registry_elapsed = time.perf_counter() - registry_started
    digest_started = time.perf_counter()
    source_version = _source_data_version(points)
    digest_elapsed = time.perf_counter() - digest_started
    summary["performance"] = {
        **mongo_metrics,
        "mongo_collection_read_wall_seconds": round(mongo_elapsed, 4),
        "preparation_seconds": round(preparation_elapsed, 4),
        "registry_seconds": round(registry_elapsed, 4),
        "source_digest_seconds": round(digest_elapsed, 4),
        "total_seconds": round(time.perf_counter() - load_started, 4),
        "page_scope": list(pages) if pages is not None else None,
    }
    return points, summary, registry, source_version


@st.cache_data(ttl=900, show_spinner="Loading NBR reporting-scope catalog...")
def load_nbr_page_catalog(
    model_version: str,
    page: str,
) -> tuple[list[dict[str, Any]], str, dict[str, Any]]:
    """Load compact run metadata for controls without transferring table values."""
    del model_version
    metrics: dict[str, Any] = {}
    runs, _, _ = load_mongodb_history(
        pages=(page,),
        include_kpis=False,
        include_tables=False,
        load_metrics=metrics,
    )
    serialized = json.dumps(
        runs,
        sort_keys=True,
        ensure_ascii=False,
        default=str,
        separators=(",", ":"),
    )
    source_version = hashlib.sha1(serialized.encode("utf-8")).hexdigest()[:16]
    return runs, source_version, metrics


@st.cache_data(ttl=900, show_spinner="Reading NBR source records...")
def _load_nbr_source_documents(
    model_version: str,
    pages: tuple[str, ...] | None = None,
    scope_keys: tuple[tuple[str, str, str], ...] | None = None,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, Any],
]:
    """Cache a read-only source snapshot, optionally scoped to selected pages."""
    del model_version  # Version is part of the cache key for safe invalidation.
    metrics: dict[str, Any] = {}
    runs, kpis, tables = load_mongodb_history(
        pages=pages,
        scope_keys=scope_keys,
        load_metrics=metrics,
    )
    return runs, kpis, tables, metrics


def _filters_key(filters: Mapping[str, Any]) -> str:
    return json.dumps(filters, sort_keys=True, ensure_ascii=False, default=str)


def _filters_match_exact(
    actual: Mapping[str, Any] | None,
    expected: Mapping[str, Any],
) -> bool:
    if not isinstance(actual, Mapping):
        return False

    def normalize(values: Mapping[str, Any]) -> dict[str, str]:
        return {
            str(key).strip().casefold(): str(value).strip().casefold()
            for key, value in values.items()
        }

    return normalize(actual) == normalize(expected)


def _filter_label(filters: Mapping[str, Any]) -> str:
    if not filters:
        return "Filters not recorded"
    return " · ".join(
        f"{key}: {value}"
        for key, value in sorted(filters.items(), key=lambda item: str(item[0]))
    )


def _source_data_version(points: Sequence[Mapping[str, Any]]) -> str:
    records = [{
        "page": point.get("page"),
        "metric": point.get("metric_label"),
        "unit": point.get("unit"),
        "unit_status": point.get("unit_status"),
        "level": point.get("geography_level"),
        "geography": point.get("geography"),
        "date": point.get("reporting_date"),
        "collected_at": point.get("collected_at"),
        "value": point.get("value"),
        "filters": point.get("filters", {}),
        "source_type": point.get("source_type"),
        "source_record_id": point.get("source_record_id"),
        "run_id": point.get("run_id"),
    } for point in points]
    canonical = sorted(
        records,
        key=lambda record: json.dumps(
            record, sort_keys=True, ensure_ascii=False, default=str
        ),
    )
    serialized = json.dumps(
        canonical, sort_keys=True, ensure_ascii=False, default=str
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]


def build_nbr_indicator_registry(
    points: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Build UI options only from observed metric, unit, scope, and filter series."""
    grouped: dict[tuple[Any, ...], list[Mapping[str, Any]]] = defaultdict(list)
    for point in points:
        filters = point.get("filters")
        if not isinstance(filters, Mapping):
            continue
        key = (
            str(point.get("page", "")),
            str(point.get("metric_label", "")),
            str(point.get("unit", "")),
            str(point.get("unit_status", "")),
            str(point.get("geography_level", "")),
            _filters_key(filters),
            str(point.get("source_type", "")),
        )
        grouped[key].append(point)

    registry = []
    for key, series in sorted(grouped.items()):
        page, metric, unit, unit_status, level, filters_json, source_type = key
        filters = json.loads(filters_json)
        dates = sorted({str(point["reporting_date"]) for point in series})
        geographies = sorted({str(point["geography"]) for point in series})
        mapping_metadata = []
        for variable, mapping in MAPPING_BY_VARIABLE.items():
            for relationship in mapping["nbr_relationships"]:
                labels = (
                    relationship["national_kpi_labels"]
                    if level == "national"
                    else relationship["district_table_labels"]
                )
                if (
                    relationship["page"] == page
                    and metric in labels
                    and _filters_match(filters, relationship["filter_scope"])
                ):
                    mapping_metadata.append({
                        "indicator_variable": variable,
                        "indicator_label": mapping["original_indicator_label"],
                        "relationship": relationship["relationship"],
                        "limitations": relationship["limitations"],
                    })
        identity = "|".join(str(value) for value in key)
        registry.append({
            "id": hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20],
            "source_page": page,
            "metric_label": metric,
            "display_label": f"{NBR_PAGE_LABELS.get(page, page)} · {metric}",
            "unit": unit,
            "unit_status": unit_status,
            "geography_level": level,
            "filters": filters,
            "source_type": source_type,
            "reporting_dates": dates,
            "geographies": geographies,
            "observation_count": len(series),
            "mappings": mapping_metadata,
        })
    return registry


def _series_points(
    points: Sequence[Mapping[str, Any]],
    *,
    page: str,
    metric: str,
    geography_level: str,
    filters: Mapping[str, Any],
    unit: str | None = None,
    geography: str | None = None,
) -> list[dict[str, Any]]:
    return sorted(
        [
            dict(point)
            for point in points
            if point.get("page") == page
            and point.get("metric_label") == metric
            and point.get("geography_level") == geography_level
            and point.get("filters") == dict(filters)
            and (unit is None or str(point.get("unit", "")) == unit)
            and (geography is None or point.get("geography") == geography)
        ],
        key=lambda item: (str(item.get("reporting_date", "")), str(item.get("geography", ""))),
    )


def _entry_key(entry: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(entry["source_page"]),
        str(entry["metric_label"]),
        str(entry["geography_level"]),
        _filters_key(entry["filters"]),
    )


def _series_label(entry: Mapping[str, Any]) -> str:
    unit = str(entry.get("unit") or "unit not specified")
    scope = ", ".join(
        f"{key}={value}" for key, value in sorted(entry["filters"].items())
    )
    relation = ", ".join(
        sorted({humanize(item["relationship"]) for item in entry.get("mappings", [])})
    )
    return (
        f"{entry['display_label']} · {unit} · {entry['geography_level']} · "
        f"{scope or 'filters not recorded'}"
        + (f" · FinScope link: {relation.lower()}" if relation else "")
    )


def _render_trend(
    points: Sequence[Mapping[str, Any]],
    *,
    title: str,
    compact: bool = False,
    key_suffix: str | None = None,
    snapshots: bool = False,
) -> None:
    if not points:
        empty_state(
            "No observations to chart",
            "NBR has not reported this measure for the selected scope. Missing dates are not treated as zero.",
        )
        return
    ordered = sorted(points, key=lambda point: str(point["reporting_date"]))
    unit = str(ordered[0].get("unit") or "unit not specified")
    fig = go.Figure(go.Scatter(
        x=[item["reporting_date"] for item in ordered],
        y=[item["value"] for item in ordered],
        mode="markers+text" if snapshots else "lines+markers+text",
        text=[f"{fmt_value(item['value'])}" for item in ordered],
        textposition="top center",
        marker=dict(size=9, color=PALETTE["blue"]),
        line=dict(color=PALETTE["blue"], width=2.5),
        hovertemplate=(
            "<b>%{x}</b><br>Observed: %{y:,.7~r} "
            + esc(unit)
            + f"<extra>{esc(title)}</extra>"
        ),
    ))
    fig.update_xaxes(title=None, showgrid=False, type="category")
    fig.update_yaxes(title=unit, gridcolor=PALETTE["grid"], rangemode="tozero")
    st.plotly_chart(
        style_chart(fig, 170 if compact else 310),
        use_container_width=True,
        config={"displayModeBar": False},
        key=f"nbr_trend_{hashlib.sha1((key_suffix or title).encode()).hexdigest()[:10]}",
    )


def _render_observation_table(points: Sequence[Mapping[str, Any]]) -> None:
    rows = []
    for point in points:
        rows.append({
            "Geography": point.get("geography", ""),
            "Reporting date": point.get("reporting_date", ""),
            "Metric": point.get("metric_label", ""),
            "Value": point.get("value"),
            "Unit": point.get("unit") or "Not specified",
            "Filters": _filter_label(point.get("filters", {})),
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _mapped_series(
    points: Sequence[Mapping[str, Any]],
    indicator_variable: str,
    *,
    geography_level: str,
    geography: str | None,
    subgroup_type: str = "",
    subgroup: str = "",
    relationships: set[str] | None = None,
) -> list[dict[str, Any]]:
    if subgroup_type and subgroup_type not in {"Gender", "Age group"}:
        return []
    mapping = MAPPING_BY_VARIABLE.get(indicator_variable)
    if not mapping:
        return []
    entries: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for relationship in mapping["nbr_relationships"]:
        if (
            relationship["relationship"] == "unsuitable"
            or (
                subgroup_type
                and relationship["relationship"] == "conditional_contextual_indicator"
            )
            or (
                relationships is not None
                and relationship["relationship"] not in relationships
            )
        ):
            continue
        labels = (
            relationship["national_kpi_labels"]
            if geography_level == "national"
            else relationship["district_table_labels"]
        )
        expected_filters = dict(relationship["filter_scope"])
        if subgroup_type == "Gender" and subgroup:
            expected_filters["Gender"] = subgroup
        elif subgroup_type == "Age group":
            if subgroup not in {"Youth", "Non-Youth"}:
                continue
            expected_filters["Age Segment"] = subgroup
        for point in points:
            filters = point.get("filters")
            filters_match = _filters_match_exact(filters, expected_filters)
            if (
                point.get("page") != relationship["page"]
                or point.get("metric_label") not in labels
                or point.get("geography_level") != geography_level
                or not isinstance(filters, Mapping)
                or not filters_match
                or (geography is not None and point.get("geography") != geography)
            ):
                continue
            entry_key = (
                str(point["page"]),
                str(point["metric_label"]),
                str(point.get("unit", "")),
                _filters_key(filters),
            )
            entry = entries.setdefault(entry_key, {
                "page": point["page"],
                "metric_label": point["metric_label"],
                "display_label": (
                    f"{NBR_PAGE_LABELS.get(str(point['page']), point['page'])} · "
                    f"{point['metric_label']}"
                ),
                "unit": point.get("unit", ""),
                "unit_status": point.get("unit_status", ""),
                "filters": dict(filters),
                "geography_level": geography_level,
                "relationship": relationship["relationship"],
                "limitations": relationship["limitations"],
                "points": [],
            })
            point_id = (
                str(point.get("source_record_id", "")),
                str(point.get("reporting_date", "")),
                str(point.get("geography", "")),
            )
            if point_id not in entry.setdefault("_point_ids", set()):
                entry["points"].append(dict(point))
                entry["_point_ids"].add(point_id)
    for entry in entries.values():
        entry["points"].sort(key=lambda item: str(item["reporting_date"]))
        entry.pop("_point_ids", None)
    return list(entries.values())


def load_combined_context_data(
    indicator_variable: str,
    *,
    geography_level: str,
    geography: str | None = None,
    subgroup_type: str = "",
    subgroup: str = "",
) -> tuple[list[dict[str, Any]], str | None]:
    """Load only explicitly relevant source relationships for a survey view."""
    mapping = MAPPING_BY_VARIABLE.get(indicator_variable)
    if mapping is None:
        return [], None
    relationships = [
        item for item in mapping["nbr_relationships"]
        if item["relationship"] in DISPLAYABLE_RELATIONSHIPS
        and geography_level in item["available_levels"]
    ]
    pages = tuple(sorted({str(item["page"]) for item in relationships}))
    if not pages:
        return [], None
    points, _, _, source_version = load_nbr_dashboard_data(
        "nbr-dashboard-v2",
        pages,
    )
    entries = _mapped_series(
        points,
        indicator_variable,
        geography_level=geography_level,
        geography=geography,
        subgroup_type=subgroup_type,
        subgroup=subgroup,
        relationships=DISPLAYABLE_RELATIONSHIPS,
    )
    return entries, source_version


def load_combined_national_evidence(
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Load the approved national mapping pages through the existing cache."""
    relationships = [
        relationship
        for mapping in MAPPING_BY_VARIABLE.values()
        for relationship in mapping["nbr_relationships"]
        if "national" in relationship["available_levels"]
        and relationship["relationship"] != "unsuitable"
    ]
    pages = tuple(sorted({
        str(relationship["page"])
        for relationship in relationships
    }))
    if not pages:
        return [], []

    points, _, _, _ = load_nbr_dashboard_data(
        "nbr-dashboard-v2",
        pages,
    )
    national_kpis = [
        dict(point)
        for point in points
        if point.get("source_type") == "national_kpi"
    ]
    bank_account_entries = _mapped_series(
        points,
        "k1",
        geography_level="national",
        geography=None,
        relationships=DISPLAYABLE_RELATIONSHIPS,
    )
    return national_kpis, bank_account_entries


def _district_series_table(
    points: Sequence[Mapping[str, Any]],
    *,
    reporting_date: str,
) -> pd.DataFrame:
    return pd.DataFrame([{
        "District": point["geography"],
        "Value": point["value"],
        "Unit": point.get("unit") or "Not specified",
        "Reporting date": point["reporting_date"],
        "Source page": point.get("page", ""),
        "Metric": point.get("metric_label", ""),
        "Filters": _filter_label(point.get("filters", {})),
        "Run ID": point.get("run_id", ""),
        "Source record ID": point.get("source_record_id", ""),
    } for point in points if str(point.get("reporting_date")) == reporting_date])


def _nbr_district_header_cards(
    points: Sequence[Mapping[str, Any]],
    registry: Sequence[Mapping[str, Any]],
    *,
    source_page: str,
    source_version: str,
    selected_district: str | None,
) -> str:
    district_options = [
        item for item in registry if item.get("geography_level") == "district"
    ]
    page_entries = [
        item for item in district_options if item.get("source_page") == source_page
    ]
    if not page_entries:
        return kpi_grid([
            kpi_card(
                label,
                "Unavailable",
                "",
                0,
                accent,
                "No eligible district observation is available for this service.",
            )
            for label, accent in (
                ("Selected district value", SUPPLY_ACCENT),
                ("Change from prior observation", PALETTE["blue"]),
                ("Observed district position", PALETTE["sun"]),
                ("Districts with data", PALETTE["ink2"]),
            )
        ])

    metric_options = sorted({
        (str(item["metric_label"]), str(item.get("unit", "")))
        for item in page_entries
    })
    metric_labels = [
        f"{metric} · {unit or 'unit not specified'}"
        for metric, unit in metric_options
    ]
    metric_key = f"nbr_district_metric_{source_version}"
    selected_metric = st.session_state.get(metric_key, metric_labels[0])
    if selected_metric not in metric_labels:
        selected_metric = metric_labels[0]
    metric, unit = metric_options[metric_labels.index(selected_metric)]
    matching = [
        item for item in page_entries
        if item["metric_label"] == metric
        and str(item.get("unit", "")) == unit
    ]
    filter_options = {_filters_key(item["filters"]): item for item in matching}
    filter_keys = sorted(filter_options)
    filter_key = f"nbr_district_filters_{source_version}"
    selected_filter = st.session_state.get(filter_key, filter_keys[0])
    if selected_filter not in filter_options:
        selected_filter = filter_keys[0]
    filters = filter_options[selected_filter]["filters"]
    series = _series_points(
        points,
        page=source_page,
        metric=metric,
        geography_level="district",
        filters=filters,
        unit=unit,
    )
    dates = sorted({str(point["reporting_date"]) for point in series})
    date_key = f"nbr_district_date_{source_version}"
    reporting_date = st.session_state.get(date_key, dates[-1] if dates else "")
    if reporting_date not in dates:
        reporting_date = dates[-1] if dates else ""
    dated = [
        point for point in series
        if str(point.get("reporting_date")) == reporting_date
    ]
    district_values = {str(point["geography"]): point for point in dated}
    names = sorted(district_values)
    pending_district = st.session_state.get("_nbr_dx_pending_district")
    district_key = f"nbr_district_selected_{source_version}"
    district = st.session_state.get(
        district_key,
        pending_district or selected_district or (names[0] if names else None),
    )
    if pending_district in names:
        district = pending_district
    if district not in names:
        district = names[0] if names else None
    selected_point = district_values.get(district) if district else None
    ranked = pd.DataFrame([
        {"District": name, "Value": point["value"]}
        for name, point in district_values.items()
    ])
    rank = None
    if not ranked.empty:
        ranked["Rank"] = ranked["Value"].rank(
            ascending=False,
            method="min",
        ).astype(int)
        if district is not None:
            rank = int(ranked.loc[ranked["District"].eq(district), "Rank"].iloc[0])
        low, high = float(ranked["Value"].min()), float(ranked["Value"].max())
        value_fill = (
            (float(selected_point["value"]) - low) / (high - low) * 100
            if selected_point is not None and high > low else 50
        )
    else:
        value_fill = 0

    history = sorted(
        [point for point in series if point.get("geography") == district],
        key=lambda point: str(point.get("reporting_date", "")),
    )
    history_index = next(
        (
            index for index, point in enumerate(history)
            if selected_point is not None
            and point.get("source_record_id") == selected_point.get("source_record_id")
            and point.get("reporting_date") == selected_point.get("reporting_date")
        ),
        None,
    )
    previous = (
        history[history_index - 1]
        if history_index is not None and history_index > 0 else None
    )
    delta = (
        float(selected_point["value"]) - float(previous["value"])
        if selected_point is not None and previous is not None
        else None
    )
    expected_count = len(load_district_reference())
    selected_source = (
        f"{esc(metric)} · <b>{esc(district or 'District unavailable')}</b><br>"
        f"Reported {esc(reporting_date or 'date unavailable')}"
    )
    if selected_point is None:
        selected_value = "Unavailable"
    else:
        selected_value = _exact_number(float(selected_point["value"]))
    cards = [
        kpi_card(
            "Selected district value",
            esc(selected_value),
            f" {esc(unit or 'unit not specified')}",
            value_fill,
            SUPPLY_ACCENT,
            selected_source,
        ),
        kpi_card(
            "Change from prior observation",
            (
                ("+" if delta > 0 else "-" if delta < 0 else "")
                + _exact_number(abs(delta))
                if delta is not None else "Unavailable"
            ),
            f" {esc(unit or 'unit not specified')}",
            (
                min(
                    100,
                    abs(delta or 0)
                    / max(abs(float(selected_point["value"])), 1)
                    * 100,
                )
                if selected_point is not None else 0
            ),
            PALETTE["blue"] if (delta or 0) >= 0 else PALETTE["coral"],
            (
                f"{esc(previous['reporting_date'])} → {esc(reporting_date)}<br>"
                "Change in reported values only"
                if previous is not None
                else "No earlier eligible observation in this district series"
            ),
        ),
        kpi_card(
            "Observed district position",
            f"#{rank}" if rank is not None else "Unavailable",
            f" of {len(ranked)}" if rank is not None else "",
            (
                (len(ranked) - rank + 1) / max(len(ranked), 1) * 100
                if rank is not None else 0
            ),
            PALETTE["sun"],
            "Descriptive position among districts with valid observations",
        ),
        kpi_card(
            "Districts with data",
            f"{len(ranked)}",
            f" / {expected_count}",
            min(100, len(ranked) / max(expected_count, 1) * 100),
            PALETTE["ink2"],
            "Observed districts / verified district reference; missing is not zero",
        ),
    ]
    return kpi_grid(cards)


def _eligible_nbr_district_points(
    points: Sequence[Mapping[str, Any]],
    *,
    include_unknown: bool = False,
) -> list[dict[str, Any]]:
    """Keep unique numeric district rows, optionally retaining unclassified rows."""
    eligible = []
    seen: set[tuple[str, str, str, str, str, str]] = set()
    duplicates: set[tuple[str, str, str, str, str, str]] = set()
    for point in points:
        if (
            point.get("source_type") != "district_table"
            or point.get("geography_level")
            not in ({"district", "unknown"} if include_unknown else {"district"})
            or point.get("repeated_snapshot_warning") is True
            or point.get("repeated_content_across_dates") is True
            or not str(point.get("geography", "")).strip()
            or (
                not include_unknown
                and str(point.get("geography", "")).strip().casefold() == "unknown"
            )
            or not isinstance(point.get("filters"), Mapping)
        ):
            continue
        try:
            value = float(point["value"])
            date.fromisoformat(str(point["reporting_date"]))
        except (KeyError, TypeError, ValueError):
            continue
        if not math.isfinite(value) or value < 0:
            continue
        identity = (
            str(point.get("page", "")),
            str(point.get("metric_label", "")),
            str(point.get("geography", "")),
            str(point.get("reporting_date", "")),
            _filters_key(point["filters"]),
            str(point.get("unit", "")),
        )
        if identity in seen:
            duplicates.add(identity)
        else:
            seen.add(identity)
            eligible.append(dict(point))
    return [
        point
        for point in eligible
        if (
            str(point.get("page", "")),
            str(point.get("metric_label", "")),
            str(point.get("geography", "")),
            str(point.get("reporting_date", "")),
            _filters_key(point["filters"]),
            str(point.get("unit", "")),
        ) not in duplicates
    ]


def _nbr_district_snapshot(
    points: Sequence[Mapping[str, Any]],
    *,
    page: str,
    metric: str,
    filters: Mapping[str, Any],
    unit: str,
    reporting_date: str,
    district: str,
    expected_district_count: int,
) -> dict[str, Any]:
    """Describe one exact NBR series and snapshot without filling data gaps."""
    series = _series_points(
        _eligible_nbr_district_points(points),
        page=page,
        metric=metric,
        geography_level="district",
        filters=filters,
        unit=unit,
    )
    dates = sorted({str(point["reporting_date"]) for point in series})
    dated = [
        point for point in series
        if str(point["reporting_date"]) == reporting_date
    ]
    district_values = {str(point["geography"]): point for point in dated}
    ranked = sorted(
        district_values,
        key=lambda name: (-float(district_values[name]["value"]), name.casefold()),
    )
    rank = (
        1 + sum(
            float(district_values[name]["value"])
            > float(district_values[district]["value"])
            for name in ranked
        )
        if district in district_values else None
    )
    history = sorted(
        [
            point for point in series
            if str(point.get("geography")) == district
        ],
        key=lambda point: str(point["reporting_date"]),
    )
    current = district_values.get(district)
    history_index = next(
        (
            index for index, point in enumerate(history)
            if current is not None
            and point.get("reporting_date") == current.get("reporting_date")
            and point.get("source_record_id") == current.get("source_record_id")
        ),
        None,
    )
    if current is not None and history_index is None:
        history_index = next(
            (
                index for index, point in enumerate(history)
                if point.get("reporting_date") == current.get("reporting_date")
            ),
            None,
        )
    previous = (
        history[history_index - 1]
        if history_index is not None and history_index > 0 else None
    )
    delta = (
        float(current["value"]) - float(previous["value"])
        if current is not None and previous is not None
        else None
    )
    return {
        "series": series,
        "dates": dates,
        "dated": dated,
        "district_values": district_values,
        "districts": sorted({str(point["geography"]) for point in series}),
        "ranked_districts": ranked,
        "rank": rank,
        "history": history,
        "current": current,
        "previous": previous,
        "delta": delta,
        "coverage": len(district_values),
        "expected_district_count": expected_district_count,
        "value_range": (
            min(float(point["value"]) for point in dated),
            max(float(point["value"]) for point in dated),
        ) if dated else (0.0, 0.0),
        "quality_qualifications": _nbr_district_quality_messages(dated),
    }


def _nbr_district_distribution_data(
    snapshot: Mapping[str, Any],
    points: Sequence[Mapping[str, Any]],
    *,
    page: str,
    metric: str,
    filters: Mapping[str, Any],
    unit: str,
    reporting_date: str,
) -> dict[str, Any]:
    """Build a single-snapshot ranking and keep unclassified geography separate."""
    named_districts = sorted(
        snapshot.get("dated", []),
        key=lambda point: (
            -float(point["value"]),
            str(point["geography"]).casefold(),
        ),
    )
    eligible = _eligible_nbr_district_points(points, include_unknown=True)
    unknown_rows = [
        point
        for point in eligible
        if point.get("page") == page
        and point.get("metric_label") == metric
        and point.get("filters") == dict(filters)
        and str(point.get("unit", "")) == unit
        and str(point.get("reporting_date", "")) == reporting_date
        and (
            point.get("geography_level") == "unknown"
            or str(point.get("geography", "")).strip().casefold() == "unknown"
        )
    ]
    return {
        "districts": named_districts,
        "unknown": sorted(
            unknown_rows,
            key=lambda point: str(point.get("geography", "")).casefold(),
        ),
        "top": named_districts[:5] if len(named_districts) >= 10 else [],
        "bottom": named_districts[-5:] if len(named_districts) >= 10 else [],
        "quality_qualifications": _nbr_district_quality_messages(
            [*named_districts, *unknown_rows]
        ),
    }


def _nbr_district_distribution_figure(
    distribution: Mapping[str, Any],
    *,
    selected_district: str | None,
    metric: str,
    unit: str,
) -> go.Figure:
    """Rank observed district counts and mark the shared explorer selection."""
    districts = list(distribution["districts"])
    ordered = districts
    top_names = {
        str(point["geography"]) for point in distribution.get("top", [])
    }
    bottom_names = {
        str(point["geography"]) for point in distribution.get("bottom", [])
    }
    colors = []
    outlines = []
    for point in ordered:
        district = str(point["geography"])
        if district == selected_district:
            colors.append("#F3D27A")
            outlines.append("#FFF4C7")
        elif district in top_names:
            colors.append("#218B83")
            outlines.append("#176B67")
        elif district in bottom_names:
            colors.append("#C68755")
            outlines.append("#A66A40")
        else:
            colors.append("#526D78")
            outlines.append("#405A65")

    figure = go.Figure(go.Bar(
        x=[float(point["value"]) for point in ordered],
        y=[str(point["geography"]) for point in ordered],
        orientation="h",
        marker=dict(
            color=colors,
            line=dict(color=outlines, width=1.2),
            cornerradius=4,
        ),
        text=[fmt_value(point["value"]) for point in ordered],
        textposition="outside",
        textfont=dict(color="#D8E4E8", size=11),
        cliponaxis=False,
        customdata=[
            [
                f"Rank {index + 1} of {len(districts)}",
                " · currently selected district"
                if point["geography"] == selected_district else "",
            ]
            for index, point in enumerate(districts)
        ],
        hovertemplate=(
            "<b>%{y}</b><br>%{x:,.4g} "
            f"{esc(unit or 'unit not specified')}<br>%{{customdata[0]}}"
            "%{customdata[1]}<extra></extra>"
        ),
    ))
    figure.update_layout(
        showlegend=False,
        bargap=0.28,
        plot_bgcolor="#102B35",
        paper_bgcolor="#102B35",
        font=dict(
            family="Plus Jakarta Sans, Segoe UI, Arial, sans-serif",
            color="#E5EEF0",
            size=12,
        ),
        margin=dict(l=12, r=74, t=18, b=48),
        hoverlabel=dict(
            bgcolor="#091D25",
            bordercolor="#52727B",
            font=dict(color="#FFFFFF", size=12),
        ),
    )
    figure.update_xaxes(
        title=dict(text=f"{metric} · {unit or 'unit not specified'}", standoff=12),
        tickformat=",.4~g",
        rangemode="tozero",
        gridcolor="rgba(188,211,216,.14)",
        zeroline=False,
        linecolor="rgba(188,211,216,.18)",
        tickfont=dict(color="#B9CBD0", size=11),
    )
    figure.update_yaxes(
        title=None,
        categoryorder="array",
        categoryarray=[str(point["geography"]) for point in ordered],
        autorange="reversed",
        showgrid=False,
        automargin=True,
        tickfont=dict(color="#D8E4E8", size=11),
    )
    return style_chart(
        figure,
        max(440, min(900, 24 * len(districts) + 145)),
        paper_bgcolor="#102B35",
        plot_bgcolor="#102B35",
    )


def _render_nbr_district_distribution(
    snapshot: Mapping[str, Any],
    points: Sequence[Mapping[str, Any]],
    *,
    page: str,
    metric: str,
    filters: Mapping[str, Any],
    unit: str,
    reporting_date: str,
    selected_district: str | None,
) -> None:
    distribution = _nbr_district_distribution_data(
        snapshot,
        points,
        page=page,
        metric=metric,
        filters=filters,
        unit=unit,
        reporting_date=reporting_date,
    )
    with st.container(key="card_nbr_dx_distribution"):
        card_title(
            "District Distribution & Outlier Scan",
            (
                f"{metric} · {unit or 'unit not specified'} · "
                f"{reporting_date} · {_filter_label(filters)}"
            ),
        )
        st.caption(
            "Ranked reported values for the selected snapshot. Extremes are descriptive, "
            "not statistical outlier labels or performance judgments. "
            f"{len(distribution['districts'])} of "
            f"{snapshot.get('expected_district_count', 'unknown')} expected districts reported."
        )
        districts = distribution["districts"]
        if not districts:
            empty_state(
                "No district counts to compare",
                "No eligible named-district observations were reported for this exact series and date.",
            )
        else:
            st.plotly_chart(
                _nbr_district_distribution_figure(
                    distribution,
                    selected_district=selected_district,
                    metric=metric,
                    unit=unit,
                ),
                use_container_width=True,
                key=(
                    "nbr_dx_distribution_"
                    f"{page}_{reporting_date}_{hashlib.sha1(_filters_key(filters).encode()).hexdigest()[:8]}"
                ),
                config={"displayModeBar": False},
            )
            st.markdown(
                '<div class="nbr-dx-distribution-legend">'
                '<span><i class="selected"></i>Selected district</span>'
                '<span><i class="higher"></i>Five highest reported counts</span>'
                '<span><i class="lower"></i>Five lowest reported counts</span>'
                '<span><i class="other"></i>Other reported districts</span>'
                '</div>',
                unsafe_allow_html=True,
            )
            summary_col1, summary_col2 = st.columns(2, gap="large")
            for column, title, rows, bottom_group in (
                (summary_col1, "Highest reported counts", distribution["top"], False),
                (summary_col2, "Lowest reported counts", distribution["bottom"], True),
            ):
                with column:
                    st.markdown(
                        f'<div class="nbr-dx-rank-heading">{esc(title)}'
                        '<span>Descriptive order · not a quality rating</span></div>',
                        unsafe_allow_html=True,
                    )
                    if rows:
                        html_rows = "".join(
                            '<div class="nbr-dx-rank-row">'
                            f'<span>{(len(districts) - 5 + index) if bottom_group else index}. '
                            f'{esc(str(point["geography"]))}</span>'
                            f'<b>{esc(fmt_value(point["value"]))} '
                            f'{esc(unit or "unit not specified")}</b></div>'
                            for index, point in enumerate(rows, start=1)
                        )
                        render_html(f'<div class="nbr-dx-rank-list">{html_rows}</div>')
                    else:
                        st.caption(
                            "At least five eligible named districts are required "
                            "to show a five-place summary."
                        )
            unknown_rows = distribution["unknown"]
            if unknown_rows:
                unknown_labels = " · ".join(
                    f"{esc(str(point['geography']))}: "
                    f"{esc(fmt_value(point['value']))} {esc(unit or 'unit not specified')}"
                    for point in unknown_rows
                )
                st.markdown(
                    '<div class="nbr-dx-unknown">'
                    '<b>Unclassified source geography</b>'
                    f'<span>{unknown_labels}</span>'
                    '<small>Shown separately; not assigned to a district or included in rankings.</small>'
                    '</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.caption(
                    "No unclassified geography row was recorded for this snapshot."
                )
        for message in distribution["quality_qualifications"]:
            st.warning(message)
        st.caption(
            "NBR administrative counts only. Missing district observations are omitted, "
            "not treated as zero; counts are not population-adjusted rates."
        )


def _nbr_district_history_data(
    snapshot: Mapping[str, Any],
    points: Sequence[Mapping[str, Any]],
    *,
    page: str,
    metric: str,
    filters: Mapping[str, Any],
    unit: str,
    expected_districts: Sequence[str],
) -> dict[str, Any]:
    """Build exact-series history coverage, gaps, unknown rows, and flags."""
    series = list(snapshot.get("series", []))
    dates = sorted({str(point["reporting_date"]) for point in series})
    districts = sorted(
        set(str(district) for district in expected_districts)
        | {str(point["geography"]) for point in series}
    )
    observations = {
        (str(point["geography"]), str(point["reporting_date"])): point
        for point in series
    }
    coverage = []
    missing_by_date: dict[str, list[str]] = {}
    for reporting_date in dates:
        missing = [
            district for district in districts
            if (district, reporting_date) not in observations
        ]
        missing_by_date[reporting_date] = missing
        coverage.append({
            "reporting_date": reporting_date,
            "reported": sum(
                (district, reporting_date) in observations
                for district in districts
            ),
            "expected": len(districts),
            "missing": len(missing),
        })

    eligible_with_unknown = _eligible_nbr_district_points(
        points,
        include_unknown=True,
    )
    exact_points = [
        point
        for point in eligible_with_unknown
        if point.get("page") == page
        and point.get("metric_label") == metric
        and point.get("filters") == dict(filters)
        and str(point.get("unit", "")) == unit
        and str(point.get("reporting_date", "")) in dates
    ]
    unknown_by_date: dict[str, list[Mapping[str, Any]]] = {
        reporting_date: [] for reporting_date in dates
    }
    for point in exact_points:
        if (
            point.get("geography_level") == "unknown"
            or str(point.get("geography", "")).strip().casefold() == "unknown"
        ):
            unknown_by_date[str(point["reporting_date"])].append(point)

    quality_by_date = {
        reporting_date: _nbr_district_quality_messages([
            point for point in exact_points
            if str(point.get("reporting_date")) == reporting_date
        ])
        for reporting_date in dates
    }
    incomplete_history = [
        {
            "district": district,
            "reported": sum(
                (district, reporting_date) in observations
                for reporting_date in dates
            ),
            "expected": len(dates),
        }
        for district in districts
        if sum(
            (district, reporting_date) in observations
            for reporting_date in dates
        ) < len(dates)
    ]
    return {
        "dates": dates,
        "districts": districts,
        "observations": observations,
        "coverage": coverage,
        "missing_by_date": missing_by_date,
        "unknown_by_date": unknown_by_date,
        "quality_by_date": quality_by_date,
        "incomplete_history": incomplete_history,
        "series": series,
    }


def _nbr_district_history_heatmap(
    history: Mapping[str, Any],
    *,
    selected_district: str | None,
    metric: str,
    unit: str,
) -> go.Figure:
    """Show reported counts and explicit missing markers by district and date."""
    dates = list(history["dates"])
    districts = list(history["districts"])
    observations = history["observations"]
    values = [
        [
            float(observations[(district, reporting_date)]["value"])
            if (district, reporting_date) in observations
            else None
            for reporting_date in dates
        ]
        for district in districts
    ]
    max_value = max(
        (
            value
            for row in values
            for value in row
            if value is not None
        ),
        default=0.0,
    )
    deltas: dict[tuple[str, str], str] = {}
    by_district: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for point in history["series"]:
        by_district[str(point["geography"])].append(point)
    for district, observations_for_district in by_district.items():
        ordered = sorted(
            observations_for_district,
            key=lambda point: str(point["reporting_date"]),
        )
        for index in range(1, len(ordered)):
            previous = ordered[index - 1]
            current = ordered[index]
            delta = float(current["value"]) - float(previous["value"])
            deltas[(district, str(current["reporting_date"]))] = (
                f"{previous['reporting_date']}: {fmt_value(previous['value'])} "
                f"→ {current['reporting_date']}: {fmt_value(current['value'])}; "
                f"change {'+' if delta > 0 else ''}{fmt_value(delta)}"
            )

    figure = go.Figure()
    figure.add_trace(go.Heatmap(
        x=dates,
        y=districts,
        z=values,
        zmin=0,
        zmax=max_value if max_value > 0 else 1,
        colorscale=[
            [0.0, "#184650"],
            [0.30, "#147B77"],
            [0.62, "#71A99A"],
            [0.84, "#D0B879"],
            [1.0, "#C4774F"],
        ],
        colorbar=dict(
            title=dict(text=unit or "Value", side="right"),
            thickness=12,
            len=0.82,
            outlinewidth=0,
            tickfont=dict(color="#D5E2E5", size=10),
        ),
        customdata=[
            [
                deltas.get((district, reporting_date), "First eligible observation")
                if (district, reporting_date) in observations
                else "No eligible observation; missing, not zero"
                for reporting_date in dates
            ]
            for district in districts
        ],
        hoverongaps=False,
        hovertemplate=(
            "<b>%{y}</b><br>%{x}<br>"
            "Observed value: %{z:,.7~r} "
            f"{esc(unit or 'unit not specified')}<br>%{{customdata}}<extra></extra>"
        ),
        xgap=3,
        ygap=2,
        showscale=True,
    ))

    missing_x: list[str] = []
    missing_y: list[str] = []
    for district_index, district in enumerate(districts):
        for date_index, reporting_date in enumerate(dates):
            if values[district_index][date_index] is None:
                missing_x.append(reporting_date)
                missing_y.append(district)
    if missing_x:
        figure.add_trace(go.Scatter(
            x=missing_x,
            y=missing_y,
            mode="markers",
            marker=dict(
                symbol="x",
                size=8,
                color="#AAB8BC",
                line=dict(color="#DCE5E7", width=1.2),
            ),
            name="Missing observation",
            hovertemplate=(
                "<b>%{y}</b><br>%{x}<br>"
                "No eligible observation; missing, not zero<extra></extra>"
            ),
        ))

    selected_values = [
        (district, reporting_date)
        for district in districts
        if district == selected_district
        for reporting_date in dates
        if (district, reporting_date) in observations
    ]
    if selected_values:
        figure.add_trace(go.Scatter(
            x=[item[1] for item in selected_values],
            y=[item[0] for item in selected_values],
            mode="markers",
            marker=dict(
                symbol="square-open",
                size=19,
                color="#F3D27A",
                line=dict(color="#FFF4C7", width=2),
            ),
            name="Selected district",
            hoverinfo="skip",
            showlegend=False,
        ))
    figure.update_layout(
        plot_bgcolor="#102B35",
        paper_bgcolor="#102B35",
        showlegend=False,
        margin=dict(l=12, r=70, t=16, b=58),
        font=dict(
            family="Plus Jakarta Sans, Segoe UI, Arial, sans-serif",
            color="#DCE8EA",
            size=11,
        ),
        hoverlabel=dict(
            bgcolor="#091D25",
            bordercolor="#52727B",
            font=dict(color="#FFFFFF", size=12),
        ),
        xaxis=dict(
            type="category",
            categoryorder="array",
            categoryarray=dates,
            tickangle=-25,
            tickfont=dict(color="#CFDDE0", size=10),
            showgrid=False,
            title=None,
        ),
        yaxis=dict(
            categoryorder="array",
            categoryarray=districts,
            autorange="reversed",
            tickfont=dict(color="#CFDDE0", size=10),
            showgrid=False,
            title=None,
            automargin=True,
        ),
    )
    if dates:
        figure.add_annotation(
            x=0.5,
            y=1.08,
            xref="paper",
            yref="paper",
            text=(
                f"{esc(metric)} · {esc(unit or 'unit not specified')} · "
                f"{len(dates)} observed reporting dates"
            ),
            showarrow=False,
            font=dict(color="#B9CBD0", size=11),
        )
    height = max(540, min(920, 20 * len(districts) + 145))
    return style_chart(
        figure,
        height,
        paper_bgcolor="#102B35",
        plot_bgcolor="#102B35",
    )


def _nbr_district_history_figure(
    history: Mapping[str, Any],
    *,
    district: str | None,
    unit: str,
) -> go.Figure | None:
    """Trend selected district only, retaining explicit missing dates as gaps."""
    if not district or not history["dates"]:
        return None
    observations = history["observations"]
    values = [
        float(observations[(district, reporting_date)]["value"])
        if (district, reporting_date) in observations
        else None
        for reporting_date in history["dates"]
    ]
    if not any(value is not None for value in values):
        return None
    figure = go.Figure(go.Scatter(
        x=list(history["dates"]),
        y=values,
        mode="lines+markers",
        connectgaps=False,
        line=dict(color="#3BABA0", width=3),
        marker=dict(
            size=11,
            color=["#F3D27A" if value is not None else "#AAB8BC" for value in values],
            line=dict(color="#FFF4C7", width=1.5),
        ),
        customdata=[
            "Observed count" if value is not None else "Missing observation; not zero"
            for value in values
        ],
        hovertemplate=(
            "<b>%{x}</b><br>"
            "%{y:,.7~r} " + esc(unit or "unit not specified")
            + "<br>%{customdata}<extra></extra>"
        ),
    ))
    figure.update_layout(
        plot_bgcolor="#F5F8F8",
        paper_bgcolor="#FFFFFF",
        margin=dict(l=58, r=20, t=16, b=58),
        font=dict(
            family="Plus Jakarta Sans, Segoe UI, Arial, sans-serif",
            color="#163D4B",
            size=11,
        ),
        hoverlabel=dict(bgcolor="#0E2A35", bordercolor="#0E2A35", font=dict(color="#FFFFFF")),
    )
    figure.update_xaxes(
        type="category",
        categoryorder="array",
        categoryarray=list(history["dates"]),
        tickangle=-25,
        showgrid=False,
    )
    figure.update_yaxes(
        title=unit or "unit not specified",
        rangemode="tozero",
        gridcolor="#DDE7E8",
        zeroline=False,
    )
    return style_chart(figure, 300, paper_bgcolor="#FFFFFF", plot_bgcolor="#F5F8F8")


def _render_nbr_district_history_watchlist(
    snapshot: Mapping[str, Any],
    points: Sequence[Mapping[str, Any]],
    *,
    page: str,
    metric: str,
    filters: Mapping[str, Any],
    unit: str,
    selected_district: str | None,
    expected_districts: Sequence[str],
    mappings: Sequence[Mapping[str, Any]] = (),
) -> None:
    history = _nbr_district_history_data(
        snapshot,
        points,
        page=page,
        metric=metric,
        filters=filters,
        unit=unit,
        expected_districts=expected_districts,
    )
    dates = history["dates"]
    with st.container(key="card_nbr_dx_history"):
        card_title(
            "Historical Change & Coverage Watchlist",
            (
                f"{NBR_PAGE_LABELS.get(page, page)} · {metric} · "
                f"{unit or 'unit not specified'} · {_filter_label(filters)}"
            ),
        )
        st.caption(
            "Compatible district-table observations only. Dates are actual NBR snapshots; "
            "changes compare each district with its previous eligible observation."
        )
        if not dates:
            empty_state(
                "No eligible historical snapshots",
                "This exact metric, unit, and filter configuration has no district history to compare.",
            )
            return

        st.plotly_chart(
            _nbr_district_history_heatmap(
                history,
                selected_district=selected_district,
                metric=metric,
                unit=unit,
            ),
            use_container_width=True,
            key=(
                "nbr_dx_history_heatmap_"
                f"{page}_{hashlib.sha1(_filters_key(filters).encode()).hexdigest()[:8]}"
            ),
            config={"displayModeBar": False},
        )
        st.markdown(
            '<div class="nbr-dx-history-legend">'
            '<span><i class="value"></i>Observed count (colour scale)</span>'
            '<span><i class="missing">×</i>Missing observation</span>'
            '<span><i class="selected"></i>Selected district</span>'
            '</div>',
            unsafe_allow_html=True,
        )

        coverage_html = "".join(
            '<div class="nbr-dx-coverage-item">'
            f'<span>{esc(row["reporting_date"])}</span>'
            f'<b>{row["reported"]}<small> / {row["expected"]}</small></b>'
            f'<em>{row["missing"]} missing</em></div>'
            for row in history["coverage"]
        )
        render_html(
            '<div class="nbr-dx-coverage">'
            '<div class="nbr-dx-coverage-title">Snapshot coverage'
            '<span>Eligible named districts reported / expected</span></div>'
            f'<div class="nbr-dx-coverage-grid">{coverage_html}</div></div>'
        )

        trend = _nbr_district_history_figure(
            history,
            district=selected_district,
            unit=unit,
        )
        trend_col, quality_col = st.columns([1.2, 1], gap="large")
        with trend_col:
            card_title(
                f"{selected_district or 'Selected district'} · observed history",
                "Exact values on observed dates; gaps remain visible and are not interpolated.",
            )
            if trend is None:
                empty_state(
                    "No history for the selected district",
                    "The selected district has no eligible values in this series.",
                )
            else:
                st.plotly_chart(
                    trend,
                    use_container_width=True,
                    key=(
                        "nbr_dx_history_selected_"
                        f"{hashlib.sha1(str(selected_district).encode()).hexdigest()[:8]}"
                    ),
                    config={"displayModeBar": False},
                )
        with quality_col:
            card_title(
                "Data-quality watchlist",
                "Reported qualifications by exact snapshot; no new anomaly rule is applied.",
            )
            quality_rows = [
                (reporting_date, message)
                for reporting_date, messages in history["quality_by_date"].items()
                for message in messages
            ]
            if quality_rows:
                for reporting_date, message in quality_rows:
                    render_html(
                        '<div class="nbr-dx-quality">'
                        f'<b>{esc(reporting_date)}</b>'
                        f'<span>{esc(message)}</span></div>'
                    )
            else:
                st.caption(
                    "No stored reconciliation or quality qualification was attached "
                    "to the eligible observations shown."
                )
            if history["incomplete_history"]:
                incomplete = history["incomplete_history"]
                st.markdown(
                    f'<div class="nbr-dx-incomplete"><b>{len(incomplete)} districts</b> '
                    "have at least one missing value in the displayed snapshots.</div>",
                    unsafe_allow_html=True,
                )
            for mapping in mappings:
                limitation = str(mapping.get("limitations", "")).strip()
                if limitation and (
                    "district" in limitation.casefold()
                    or "unique" in limitation.casefold()
                    or "denominator" in limitation.casefold()
                ):
                    st.info(limitation)

        with st.expander("Districts missing by reporting date"):
            for reporting_date, missing in history["missing_by_date"].items():
                if missing:
                    st.markdown(
                        f"**{esc(reporting_date)} · {len(missing)} not reported**"
                    )
                    st.caption(", ".join(missing))
                else:
                    st.caption(f"{reporting_date}: all expected districts reported.")

        with st.expander("District history completeness"):
            if history["incomplete_history"]:
                for row in history["incomplete_history"]:
                    missing_dates = [
                        reporting_date
                        for reporting_date in dates
                        if (
                            row["district"],
                            reporting_date,
                        ) not in history["observations"]
                    ]
                    st.caption(
                        f'{row["district"]} · {row["reported"]}/{row["expected"]} '
                        f"eligible snapshots · missing on {', '.join(missing_dates)}"
                    )
            else:
                st.caption(
                    "Every expected district has an eligible observation for each displayed date."
                )

        unknown_dates = {
            reporting_date: rows
            for reporting_date, rows in history["unknown_by_date"].items()
            if rows
        }
        if unknown_dates:
            for reporting_date, rows in unknown_dates.items():
                values = " · ".join(
                    f"{point['geography']}: {fmt_value(point['value'])} "
                    f"{unit or 'unit not specified'}"
                    for point in rows
                )
                st.markdown(
                    '<div class="nbr-dx-unknown">'
                    f'<b>Unclassified geography · {esc(reporting_date)}</b>'
                    f'<span>{esc(values)}</span>'
                    '<small>Not assigned to a district and excluded from district coverage and comparisons.</small>'
                    '</div>',
                    unsafe_allow_html=True,
                )
        else:
            st.caption(
                "No unknown or unclassified geography rows were present in the eligible snapshots."
            )
        st.caption(
            "Administrative counts only. A change in count does not establish a change "
            "in financial inclusion, unique people served, or service accessibility."
        )


def _nbr_district_snapshot_value_range(
    snapshot: Mapping[str, Any],
) -> tuple[float, float]:
    values = [
        float(point["value"])
        for point in snapshot.get("dated", [])
        if isinstance(point.get("value"), (int, float))
        and math.isfinite(float(point["value"]))
    ]
    return (min(values), max(values)) if values else (0.0, 0.0)


def _nbr_district_quality_messages(
    points: Sequence[Mapping[str, Any]],
) -> list[str]:
    messages = []
    for point in points:
        qualifications = point.get("quality_qualifications") or []
        if not isinstance(qualifications, Sequence) or isinstance(qualifications, str):
            continue
        for qualification in qualifications:
            if isinstance(qualification, Mapping):
                message = str(qualification.get("message", "")).strip()
            else:
                message = str(qualification).strip()
            if message and message not in messages:
                messages.append(message)
    return messages


def _nbr_district_service_options(
    entries: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    series = sorted({
        (
            str(entry["source_page"]),
            str(entry["metric_label"]),
            str(entry.get("unit", "")),
        )
        for entry in entries
    })
    counts_by_page: dict[str, int] = defaultdict(int)
    for page, _, _ in series:
        counts_by_page[page] += 1
    options = {}
    for page, metric, unit in series:
        page_label = NBR_PAGE_LABELS.get(page, page)
        label = (
            page_label
            if counts_by_page[page] == 1
            else f"{page_label} · {metric} · {unit or 'unit not specified'}"
        )
        identity = json.dumps(
            [page, metric, unit],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        identifier = hashlib.sha1(identity.encode("utf-8")).hexdigest()[:12]
        options[identifier] = {
            "source_page": page,
            "metric_label": metric,
            "unit": unit,
            "label": label,
        }
    return options


def _nbr_district_details_html(
    snapshot: Mapping[str, Any],
    *,
    district: str,
    metric: str,
    unit: str,
    reporting_date: str,
    filters: Mapping[str, Any],
) -> str:
    current = snapshot.get("current")
    rank = snapshot.get("rank")
    coverage = int(snapshot.get("coverage", 0))
    expected = int(snapshot.get("expected_district_count", 0))
    previous = snapshot.get("previous")
    delta = snapshot.get("delta")
    low, high = snapshot.get("value_range", (0.0, 0.0))
    value = float(current["value"]) if current is not None else None
    meter = (
        max(3.0, min(97.0, (value - low) / (high - low) * 100))
        if value is not None and high > low else 50.0
    )
    rank_text = f"#{rank} of {coverage}" if rank is not None else "Unavailable"
    value_text = (
        esc(fmt_value(value))
        if value is not None
        else "Unavailable"
    )
    delta_text = (
        ("+" if float(delta) > 0 else "") + esc(fmt_value(delta))
        if delta is not None
        else "Unavailable"
    )
    previous_date = (
        str(previous.get("reporting_date", ""))
        if previous is not None else "No earlier observation"
    )
    return f"""
    <div style="--accent:#2F6FB3;--accent-text:#245A99">
      <div class="insp-top">
        <div class="insp-name">{esc(district)}</div>
        <div class="insp-rank">{rank_text}</div>
      </div>
      <div class="insp-value">{value_text}<span> {esc(unit or 'unit not specified')}</span></div>
      <div class="insp-sub">{esc(metric)} · reported {esc(reporting_date)}</div>
      <div class="meter">
        <div class="meter-track"></div>
        <div class="meter-dot" style="left:{meter:.1f}%"></div>
      </div>
      <div class="meter-ends">
        <span>Snapshot low {esc(fmt_value(low))}</span>
        <span>Snapshot high {esc(fmt_value(high))}</span>
      </div>
      <div class="insp-grid">
        <div><b>{esc(delta_text)}</b><span>Change since {esc(previous_date)}</span></div>
        <div><b>{coverage} / {expected}</b><span>Districts reported</span></div>
        <div><b>{rank_text}</b><span>Descriptive rank</span></div>
      </div>
      <div class="insp-note">
        <b>Source filters</b><br>{esc(_filter_label(filters))}
      </div>
      <div class="insp-note">
        Administrative count only. Rank is descriptive among districts with observations;
        this is not a population-adjusted access or priority measure.
      </div>
    </div>
    """


def _reset_nbr_map_view() -> None:
    st.session_state["nbr_dx_reset_revision"] = (
        int(st.session_state.get("nbr_dx_reset_revision", 0)) + 1
    )
    st.session_state["nbr_dx_map_tilt"] = 0
    st.session_state["nbr_dx_map_rotation"] = 0


def _nbr_clicked_selection(
    event: Mapping[str, Any] | None,
    districts: Sequence[str],
    current: str | None,
) -> str | None:
    from src.pages.district_explorer import _clicked_district

    clicked = _clicked_district(event, set(districts))
    return clicked if clicked and clicked != current else None


def _render_nbr_district_explorer(
    points: Sequence[Mapping[str, Any]],
    source_version: str,
    *,
    source_page: str,
    selected_district: str | None,
    district_entries: Sequence[Mapping[str, Any]],
    service_options: Mapping[str, Mapping[str, Any]],
) -> None:
    from src.pages.district_explorer import (
        BASEMAPS,
        SPOTLIGHTS,
        build_map,
    )

    eligible_points = _eligible_nbr_district_points(points)
    service_key = "nbr_dx_service"
    service_ids = list(service_options)
    selected_service = next(
        (
            identifier for identifier, item in service_options.items()
            if item["source_page"] == source_page
        ),
        service_ids[0] if service_ids else "",
    )
    if st.session_state.get(service_key) not in service_options:
        st.session_state[service_key] = selected_service

    st.markdown(
        '<div style="height:2.5rem" aria-hidden="true"></div>',
        unsafe_allow_html=True,
    )
    with st.container(key="card_nbr_dx_controls"):
        card_title(
            "NBR district controls",
            "Select an observed administrative series and snapshot. Filters and units stay tied to the source.",
        )
        source_pages = sorted(NBR_PAGE_LABELS)
        page_labels = [NBR_PAGE_LABELS[page] for page in source_pages]
        service_area_col, reporting_date_col = st.columns(
            [2.4, 1],
            gap="medium",
        )
        with service_area_col:
            st.selectbox(
                "Service area",
                page_labels,
                index=source_pages.index(source_page),
                key="nbr_source_page_district",
            )
        with reporting_date_col:
            reporting_date_slot = st.empty()
        if not district_entries:
            empty_state(
                "No eligible district observations",
                "No validated NBR district-table series are available. Missing or unknown geography is not mapped.",
            )
            service_page = None
            metric = ""
            unit = ""
            filters: Mapping[str, Any] = {}
            reporting_date = ""
            selected_district = None
            entry: Mapping[str, Any] = {}
            snapshot: Mapping[str, Any] = {}
        else:
            if len(service_ids) > 1:
                selected_service = st.selectbox(
                    "Measure",
                    service_ids,
                    format_func=lambda identifier: service_options[identifier]["label"],
                    key=service_key,
                )
            else:
                selected_service = service_ids[0]
            selected_series = service_options[selected_service]
            service_page = str(selected_series["source_page"])
            metric = str(selected_series["metric_label"])
            unit = str(selected_series.get("unit", ""))
            matching = [
                item for item in district_entries
                if item["source_page"] == service_page
                and item["metric_label"] == metric
                and str(item.get("unit", "")) == unit
            ]
            st.markdown("**Institution type**")
            entry = _select_observed_filter_combination(
                matching,
                source_version,
                state_prefix=f"nbr_dx_filter_{selected_service}",
                button_dimensions=("Institution Type",),
                full_width=True,
            )
            filters = entry["filters"]
            series = _series_points(
                eligible_points,
                page=service_page,
                metric=metric,
                geography_level="district",
                filters=filters,
                unit=unit,
            )
            dates = sorted({str(point["reporting_date"]) for point in series})
            date_key = f"nbr_district_date_{source_version}"
            reporting_date = st.session_state.get(date_key, dates[-1])
            if reporting_date not in dates:
                reporting_date = dates[-1]
            st.session_state[date_key] = reporting_date
            reporting_date = reporting_date_slot.selectbox(
                "Reporting date",
                dates,
                key=date_key,
            )

            expected_district_count = len(load_district_reference())
            preview = _nbr_district_snapshot(
                eligible_points,
                page=service_page,
                metric=metric,
                filters=filters,
                unit=unit,
                reporting_date=reporting_date,
                district="",
                expected_district_count=expected_district_count,
            )
            districts = preview["districts"]
            district_key = f"nbr_district_selected_{source_version}"
            pending = st.session_state.pop("_nbr_dx_pending_district", None)
            current_district = st.session_state.get(
                district_key,
                selected_district or (districts[0] if districts else ""),
            )
            if pending in districts:
                current_district = pending
            if current_district not in districts and districts:
                current_district = districts[0]
            st.session_state[district_key] = current_district
            district_col, settings_col = st.columns(
                [2.4, 1],
                gap="medium",
                vertical_alignment="bottom",
            )
            with district_col:
                selected_district = st.selectbox(
                    "District",
                    districts,
                    key=district_key,
                )
            with settings_col:
                with st.popover(
                    "Map settings",
                    icon=":material/tune:",
                    use_container_width=True,
                ):
                    basemap = st.selectbox(
                        "Basemap",
                        list(BASEMAPS),
                        index=list(BASEMAPS).index("Dark"),
                        key="nbr_dx_map_basemap",
                    )
                    opacity = st.slider(
                        "Fill opacity",
                        0.3,
                        1.0,
                        0.94,
                        0.05,
                        key="nbr_dx_map_opacity",
                    )
                    spotlight = st.selectbox(
                        "Outline extremes",
                        SPOTLIGHTS,
                        key="nbr_dx_map_spotlight",
                    )
                    labels = st.toggle(
                        "Show district names",
                        value=False,
                        key="nbr_dx_map_labels",
                    )
                    if basemap in {"Satellite", "Terrain"}:
                        st.caption(
                            "Satellite and terrain tiles are supplied by Esri."
                        )
                    tilt = st.slider(
                        "Tilt",
                        0,
                        60,
                        0,
                        key="nbr_dx_map_tilt",
                    )
                    rotation = st.slider(
                        "Rotation",
                        -90,
                        90,
                        0,
                        key="nbr_dx_map_rotation",
                    )
                    st.button(
                        "Reset view to Rwanda",
                        key="nbr_dx_reset_view",
                        on_click=_reset_nbr_map_view,
                        use_container_width=True,
                        icon=":material/center_focus_strong:",
                    )
            snapshot = _nbr_district_snapshot(
                eligible_points,
                page=service_page,
                metric=metric,
                filters=filters,
                unit=unit,
                reporting_date=reporting_date,
                district=selected_district,
                expected_district_count=expected_district_count,
            )
    st.markdown(
        '<div style="height:1.25rem" aria-hidden="true"></div>',
        unsafe_allow_html=True,
    )
    map_col, details_col = st.columns([2.35, 1], gap="large")
    with map_col:
        with st.container(key="card_nbr_dx_map"):
            card_title(
                "NBR district map",
                (
                    f"{metric} · {unit or 'unit not specified'} · "
                    f"reported {reporting_date}"
                    if service_page else "Map unavailable until eligible district observations are available."
                ),
            )
            if not snapshot or not snapshot.get("dated"):
                empty_state(
                    "No district observations for this date",
                    "No data is shown for missing districts; an unreported value is not zero.",
                )
            else:
                map_error = None
                try:
                    geojson = data.load_geojson()
                    centers, center = data.geo_summary(geojson)
                except (FileNotFoundError, ValueError, KeyError) as error:
                    map_error = error
                    geojson, centers, center = None, {}, (None, None)
                if map_error is not None:
                    st.error("NBR district boundaries could not be loaded.")
                    st.caption(str(map_error))
                else:
                    map_frame = pd.DataFrame([
                        {
                            "District": str(point["geography"]),
                            "Value": float(point["value"]),
                        }
                        for point in snapshot["dated"]
                    ])
                    map_frame["rank"] = map_frame["Value"].rank(
                        ascending=False,
                        method="min",
                    ).astype(int)
                    map_frame["diff"] = None
                    value_range = _nbr_district_snapshot_value_range(snapshot)
                    settings = {
                        "basemap": basemap,
                        "palette": "Indicator colours",
                        "opacity": opacity,
                        "spotlight": spotlight,
                        "labels": labels,
                        "tilt": tilt,
                        "rotation": rotation,
                        "zoom": 7.3,
                        "uirevision": (
                            f"nbr-{basemap}-{tilt}-{rotation}-"
                            f"{st.session_state.get('nbr_dx_reset_revision', 0)}"
                        ),
                    }
                    render_html(
                        '<div class="map-strip"><div class="chips">'
                        '<span class="chip"><i style="border-color:#F3D27A"></i>Selected district</span>'
                        '<span class="chip"><i style="background:#26363B;border-color:#789096"></i>No observation</span>'
                        f'<span class="chip">{snapshot["coverage"]} of '
                        f'{snapshot["expected_district_count"]} districts reported</span>'
                        '</div><div class="cs">Only observed Rwandan district values are coloured.</div></div>'
                    )
                    fig = build_map(
                        map_frame,
                        geojson,
                        centers,
                        center,
                        {"scale": []},
                        "Value",
                        None,
                        selected_district,
                        metric,
                        settings,
                        value_unit=unit,
                        nbr_style=True,
                        hover_context=(
                            f"{reporting_date}\n{_filter_label(filters)}"
                        ),
                        value_range=value_range,
                        nbr_institution=filters.get("Institution Type", "All"),
                    )
                    event = st.plotly_chart(
                        fig,
                        use_container_width=True,
                        key="nbr_dx_map",
                        on_select="rerun",
                        selection_mode="points",
                        config={
                            "scrollZoom": True,
                            "displaylogo": False,
                            "modeBarButtonsToRemove": ["select2d", "lasso2d"],
                        },
                    )
                    clicked = _nbr_clicked_selection(
                        event,
                        list(snapshot["district_values"]),
                        selected_district,
                    )
                    if clicked:
                        st.session_state["_nbr_dx_pending_district"] = clicked
                        st.rerun()

    with details_col:
        with st.container(key="card_nbr_dx_details"):
            if not snapshot:
                card_title("District details", "Details will appear when a district series is available.")
                empty_state(
                    "No district details available",
                    "NBR has not provided an eligible district observation for this service.",
                )
            else:
                current = snapshot["current"]
                st.markdown(
                    '<div class="nbr-dx-inspector-title">District details'
                    '<span>NBR-reported administrative observations</span></div>',
                    unsafe_allow_html=True,
                )
                if snapshot:
                    render_html(
                        _nbr_district_details_html(
                            snapshot,
                            district=str(selected_district or "District unavailable"),
                            metric=metric,
                            unit=unit,
                            reporting_date=reporting_date,
                            filters=filters,
                        )
                    )
                    if current is None:
                        st.caption(
                            f"NBR did not report this district for {reporting_date}. "
                            "The missing value is not zero."
                        )
                    for message in snapshot["quality_qualifications"]:
                        st.warning(message)
                    for mapping in entry.get("mappings", []):
                        limitation = str(mapping.get("limitations", "")).strip()
                        if limitation and (
                            "district" in limitation.casefold()
                            or "unique" in limitation.casefold()
                        ):
                            st.warning(limitation)
                    if snapshot["history"]:
                        card_title("Observed history", "Actual compatible reporting dates only.")
                        _render_trend(
                            snapshot["history"],
                            title=f"{metric} · {unit or 'unit not specified'}",
                            compact=True,
                            key_suffix=f"nbr-dx-{source_version}-{selected_district}",
                        )
                    else:
                        empty_state(
                            "No history for this district",
                            "No compatible historical observations are available.",
                        )
                    if current is not None:
                        with st.expander("Source record"):
                            st.json({
                                "source_page": service_page,
                                "source_metric": metric,
                                "unit": unit or "unit not specified",
                                "reporting_date": reporting_date,
                                "filters": dict(filters),
                                "source_record_id": current.get("source_record_id"),
                                "run_id": current.get("run_id"),
                                "collected_at": current.get("collected_at"),
                            })

    if snapshot and service_page:
        _render_nbr_district_distribution(
            snapshot,
            points,
            page=service_page,
            metric=metric,
            filters=filters,
            unit=unit,
            reporting_date=reporting_date,
            selected_district=selected_district,
        )
        _render_nbr_district_history_watchlist(
            snapshot,
            points,
            page=service_page,
            metric=metric,
            filters=filters,
            unit=unit,
            selected_district=selected_district,
            expected_districts=tuple(load_district_reference()),
            mappings=entry.get("mappings", []),
        )


def _render_nbr_district_page(
    points: Sequence[Mapping[str, Any]],
    summary: Mapping[str, Any],
    registry: Sequence[Mapping[str, Any]],
    source_version: str,
    *,
    source_page: str,
    selected_district: str | None,
) -> None:
    from src.pages.district_explorer import (
        BASEMAPS,
        PALETTE_CHOICES,
        SPOTLIGHTS,
        _clicked_district,
        build_map,
    )

    district_options = [
        item for item in registry if item.get("geography_level") == "district"
    ]
    if not district_options:
        with st.container(key="card_nbr_unavailable"):
            empty_state(
                "No district data for this service",
                "NBR has not provided a validated district-level series here. "
                "Unavailable is not zero and is not a negative finding.",
            )
        return

    page = source_page
    page_entries = [item for item in district_options if item["source_page"] == page]
    if not page_entries:
        with st.container(key="card_nbr_unavailable"):
            empty_state(
                "No district comparison for this service",
                "Try another service area, or use the National overview for national measures.",
            )
        return

    with st.container(key="card_controls"):
        card_title("District measure", "Choose a measure, who it covers, and the reporting date.")
        metric_col, filter_col, date_col = st.columns([1.5, 1.5, 1], gap="medium")
        metric_options = sorted({
            (str(item["metric_label"]), str(item.get("unit", "")))
            for item in page_entries
        })
        metric_labels = [
            f"{metric} · {unit or 'unit not specified'}"
            for metric, unit in metric_options
        ]
        metric_key = f"nbr_district_metric_{source_version}"
        current_metric = st.session_state.get(metric_key, metric_labels[0])
        if current_metric not in metric_labels:
            current_metric = metric_labels[0]
        with metric_col:
            metric_label = st.selectbox(
                "Measure",
                metric_labels,
                index=metric_labels.index(current_metric),
                key=metric_key,
            )
        metric, unit = metric_options[metric_labels.index(metric_label)]
        matching = [
            item for item in page_entries
            if item["metric_label"] == metric
            and str(item.get("unit", "")) == unit
        ]
        filter_options = {_filters_key(item["filters"]): item for item in matching}
        filter_keys = sorted(filter_options)
        filter_key = f"nbr_district_filters_{source_version}"
        selected_filter = st.session_state.get(filter_key, filter_keys[0])
        if selected_filter not in filter_options:
            selected_filter = filter_keys[0]
        with filter_col:
            selected_filter = st.selectbox(
                "Coverage",
                filter_keys,
                index=filter_keys.index(selected_filter),
                format_func=lambda value: _filter_label(filter_options[value]["filters"]),
                key=filter_key,
            )
        entry = dict(filter_options[selected_filter])
        entry["source_data_version"] = source_version
        series = _series_points(
            points,
            page=page,
            metric=metric,
            geography_level="district",
            filters=entry["filters"],
            unit=unit,
        )
        dates = sorted({str(point["reporting_date"]) for point in series})
        date_key = f"nbr_district_date_{source_version}"
        selected_date = st.session_state.get(date_key, dates[-1] if dates else "")
        if selected_date not in dates:
            selected_date = dates[-1] if dates else ""
        with date_col:
            if dates:
                reporting_date = st.selectbox(
                    "Reporting date",
                    dates,
                    index=dates.index(selected_date),
                    key=date_key,
                )
            else:
                reporting_date = ""

    if not series or not reporting_date:
        with st.container(key="card_nbr_unavailable"):
            empty_state(
                "No observations for this measure",
                "Try another measure or coverage. Missing observations are not interpolated or set to zero.",
            )
        return

    dated = [point for point in series if str(point["reporting_date"]) == reporting_date]
    district_values = {
        str(point["geography"]): point for point in dated
    }
    names = sorted(district_values)
    if not names:
        empty_state(
            "No district observations on this date",
            "Pick another reporting date to see districts NBR reported.",
        )
        return
    if selected_district not in names:
        selected_district = names[0]
    district_key = f"nbr_district_selected_{source_version}"
    # A map click is applied here, before the District selector is created.
    # Writing a widget's key after it exists in the same run raises an error.
    pending = st.session_state.pop("_nbr_dx_pending_district", None)
    if pending in names:
        st.session_state[district_key] = pending
    if st.session_state.get(district_key) not in names:
        st.session_state[district_key] = selected_district
    with st.container(key="card_controls_district"):
        st.selectbox(
            "District",
            names,
            key=district_key,
        )
    selected_district = st.session_state[district_key]
    selected_point = district_values.get(selected_district)
    if selected_point is None:
        empty_state(
            f"No {metric.lower()} for {selected_district}",
            f"NBR did not report this measure for {selected_district} on {reporting_date}. "
            "Choose another district or date; the gap is not treated as zero.",
        )
        return
    ranked = pd.DataFrame([{
        "District": name,
        "Value": point["value"],
        "Unit": point.get("unit") or "Not specified",
        "Source record ID": point.get("source_record_id", ""),
        "Run ID": point.get("run_id", ""),
    } for name, point in district_values.items()])
    ranked["Rank"] = ranked["Value"].rank(ascending=False, method="min").astype(int)
    rank_row = ranked.loc[ranked["District"].eq(selected_district)].iloc[0]
    selected_history = sorted(
        [
            point for point in series
            if point.get("geography") == selected_district
        ],
        key=lambda point: str(point["reporting_date"]),
    )
    history_index = next(
        index for index, point in enumerate(selected_history)
        if point is selected_point or (
            point.get("source_record_id") == selected_point.get("source_record_id")
            and point.get("reporting_date") == selected_point.get("reporting_date")
        )
    )
    previous = selected_history[history_index - 1] if history_index > 0 else None
    value = float(selected_point["value"])
    low, high = float(ranked["Value"].min()), float(ranked["Value"].max())
    try:
        geojson = data.load_geojson()
        centers, center = data.geo_summary(geojson)
        map_error = None
    except (FileNotFoundError, ValueError, KeyError) as error:
        geojson, centers, center = None, {}, (None, None)
        map_error = error
    note(
        "Administrative evidence only",
        "Values and rankings describe the selected NBR metric and exact source filters. "
        "They do not measure household ownership, population access, or a change in financial inclusion.",
        tone="info",
    )
    controls, settings_col = st.columns([2.4, 1], gap="medium")
    with settings_col:
        with st.popover("Map settings", icon=":material/tune:", use_container_width=True):
            basemap = st.selectbox("Basemap", list(BASEMAPS), key="nbr_dx_basemap")
            palette = st.selectbox("Colours", PALETTE_CHOICES, key="nbr_dx_palette")
            opacity = st.slider("Fill opacity", 0.3, 1.0, 0.85, 0.05, key="nbr_dx_opacity")
            spotlight = st.selectbox("Outline extremes", SPOTLIGHTS, key="nbr_dx_spotlight")
            tilt = st.slider("Tilt", 0, 60, 0, key="nbr_dx_tilt")
            rotation = st.slider("Rotation", -90, 90, 0, key="nbr_dx_rotation")
    with controls:
        st.caption(
            f"{NBR_PAGE_LABELS.get(page, page)} · {_filter_label(entry['filters'])}"
        )
    settings = {
        "basemap": basemap,
        "palette": palette,
        "opacity": opacity,
        "spotlight": spotlight,
        "tilt": tilt,
        "rotation": rotation,
        "zoom": 7.3,
        "labels": False,
    }
    map_col, inspector_col = st.columns([2.85, 1], gap="medium")
    with map_col:
        with st.container(key="card_nbr_map"):
            render_html(
                f'<div class="map-strip"><div><div class="ct">{esc(metric)}</div>'
                '<div class="cs">District values for the selected reporting date · '
                'click a district to inspect it</div></div>'
                f'<div class="chips"><span class="chip">{esc(unit or "Unit not specified")}</span>'
                '<span class="chip">Districts without data are left blank</span></div></div>'
            )
            if map_error is not None:
                st.warning("The NBR map is unavailable because district boundaries could not be loaded.")
                st.caption(str(map_error))
            if geojson is not None:
                map_frame = ranked.copy()
                map_frame["rank"] = map_frame["Rank"]
                map_frame["Valid respondents"] = None
                map_frame["diff"] = None
                map_cfg = {
                    "scale": (
                        [[0, "#EAF6F3"], [0.35, "#9FD3CB"], [0.7, "#3AA597"], [1, "#0E2A35"]]
                        if settings["palette"] == "Indicator colours"
                        else settings["palette"]
                    ),
                    "accent": PALETTE["teal"],
                }
                event = st.plotly_chart(
                    build_map(
                        map_frame,
                        geojson,
                        centers,
                        center,
                        map_cfg,
                        "Value",
                        None,
                        selected_district,
                        metric,
                        settings,
                        value_unit=unit,
                    ),
                    use_container_width=True,
                    key="nbr_dx_map",
                    on_select="rerun",
                    selection_mode="points",
                    config={
                        "scrollZoom": True,
                        "displaylogo": False,
                        "modeBarButtonsToRemove": ["select2d", "lasso2d"],
                    },
                )
                clicked = _clicked_district(event, names)
                if clicked and clicked != selected_district:
                    st.session_state["_nbr_dx_pending_district"] = clicked
                    st.rerun()
    with inspector_col:
        with st.container(key="card_nbr_inspector"):
            rank = int(rank_row["Rank"])
            meter = (value - low) / (high - low) * 100 if high > low else 50
            render_html(
                f'<div class="insp-top"><div class="insp-name">{esc(selected_district)}</div>'
                f'<div class="insp-rank">#{rank} of {len(ranked)}</div></div>'
                f'<div class="insp-value">{fmt_value(value)}<span> {esc(unit or "unit not specified")}</span></div>'
                f'<div class="insp-sub">{esc(metric)} · reporting date {esc(reporting_date)}</div>'
                f'<div class="meter"><div class="meter-track"></div>'
                f'<div class="meter-dot" style="left:{meter:.1f}%"></div></div>'
                f'<div class="meter-ends"><span>Lowest {fmt_value(low)}</span>'
                f'<span>Highest {fmt_value(high)}</span></div>'
                f'<div class="insp-note"><b>Observed administrative value</b><br>'
                f'{esc(_filter_label(entry["filters"]))}<br>'
                'This comparison does not imply a survey-measured access or ownership gap.</div>'
            )
            if previous is not None:
                st.caption(
                    f"Previous observation: {fmt_value(previous['value'])} {unit} "
                    f"on {previous['reporting_date']}."
                )
    trend_col, distribution_col = st.columns([1.45, 1], gap="medium")
    with trend_col:
        with st.container(key="card_nbr_trend"):
            card_title(
                f"{selected_district} over time",
                "Only observed reporting dates are connected; missing dates are not interpolated.",
            )
            _render_trend(
                selected_history,
                title=f"{metric} · {unit or 'unit not specified'}",
            )
    with distribution_col:
        with st.container(key="card_nbr_distribution"):
            card_title(
                "District distribution",
                f"Observed values among {len(ranked)} districts on {reporting_date}.",
            )
            histogram = go.Figure(go.Histogram(
                x=ranked["Value"],
                nbinsx=min(10, max(4, round(len(ranked) ** 0.5))),
                marker=dict(
                    color=PALETTE["teal"],
                    opacity=0.62,
                    line=dict(color="#FFFFFF", width=1.5),
                ),
                showlegend=False,
                hovertemplate=f"%{{x:,.7~r}} {esc(unit)}<br>%{{y}} districts<extra></extra>",
            ))
            histogram.add_vline(
                x=value,
                line_color=PALETTE["sun"],
                line_width=3,
                annotation_text=esc(selected_district),
            )
            histogram.update_xaxes(title=f"{metric} · {unit or 'unit not specified'}", showgrid=False)
            histogram.update_yaxes(title="Districts", gridcolor=PALETTE["grid"])
            st.plotly_chart(
                style_chart(histogram, 310),
                use_container_width=True,
                key="nbr_dx_distribution",
                config={"displayModeBar": False},
            )
    with st.container(key="card_nbr_table"):
        card_title(
            "District values",
            "Observed records for the selected metric, date, and exact filter scope. Missing districts are omitted, not set to zero.",
        )
        table = ranked.merge(
            _district_series_table(dated, reporting_date=reporting_date),
            on=["District", "Value", "Unit", "Source record ID", "Run ID"],
            how="left",
        ).sort_values("Rank")
        st.dataframe(
            table[[
                "Rank", "District", "Value", "Unit", "Reporting date", "Filters",
            ]],
            hide_index=True,
            use_container_width=True,
            height=440,
        )
    with st.expander("Observations, limitations and FinScope links"):
        st.caption(
            f"{summary.get('eligible_source_point_count', 0):,} NBR observations available "
            f"for {NBR_PAGE_LABELS.get(page, page).lower()}."
        )
        if entry.get("mappings"):
            for mapping in entry["mappings"]:
                st.markdown(
                    f"- **{esc(mapping['indicator_label'])}**: "
                    f"{esc(humanize(mapping['relationship']))}. {esc(mapping['limitations'])}"
                )
        else:
            st.caption("No approved FinScope relationship is configured for this series.")
        _render_observation_table(selected_history)
def _render_combined_context(
    points: Sequence[Mapping[str, Any]],
    *,
    indicator_variable: str,
    district: str | None = None,
    subgroup_type: str = "",
    subgroup: str = "",
    source_version: str | None = None,
    intelligence: Mapping[str, Any] | None = None,
    expanded: bool = False,
) -> None:
    source_version = source_version or _source_data_version(points)
    level = "district" if district else "national"
    entries = _mapped_series(
        points,
        indicator_variable,
        geography_level=level,
        geography= district,
        subgroup_type=subgroup_type,
        subgroup=subgroup,
        relationships=DISPLAYABLE_RELATIONSHIPS,
    )
    if not entries:
        if district and intelligence:
            with st.expander(
                f"NBR supply context · "
                f"{MAPPING_BY_VARIABLE[indicator_variable]['original_indicator_label']}",
                expanded=expanded,
            ):
                render_html(
                    '<span class="nbr-tag">NBR supply</span> '
                    '<span class="nbr-tag beta">Beta</span>'
                )
                st.caption(
                    "No district-scoped observation is recorded for the selected "
                    "district in this exact NBR series."
                )
                _render_combined_peer_comparison(intelligence, district)
                _render_combined_intelligence(intelligence, district)
        return
    with st.expander(
        f"NBR supply context · "
        f"{MAPPING_BY_VARIABLE[indicator_variable]['original_indicator_label']}",
        expanded=expanded or bool(district and intelligence),
    ):
        render_html('<span class="nbr-tag">NBR supply</span> <span class="nbr-tag beta">Beta</span>')
        labels = [_series_label(entry) for entry in entries]
        if len(entries) > 1:
            selected_label = st.selectbox(
                "Observed supply series",
                labels,
                key=(
                    f"combined_nbr_series_{indicator_variable}_"
                    f"{district or 'national'}_{subgroup or 'all'}_{source_version}"
                ),
            )
            entry = entries[labels.index(selected_label)]
        else:
            entry = entries[0]
        series_points = entry["points"]
        relationship = humanize(entry.get("relationship", "contextual_indicator"))
        st.caption(f"Relationship class: {relationship}.")
        st.caption(
            "Exact NBR filters: "
            + _filter_label(entry.get("filters", {}))
        )
        dates = sorted({str(point["reporting_date"]) for point in series_points})
        if not dates:
            empty_state("No NBR observations", "NBR has not reported this series for the selected geography.")
            return
        latest_date = dates[-1]
        latest = next(
            (point for point in series_points if str(point["reporting_date"]) == latest_date),
            None,
        )
        geography_label = f" in {district}" if district else " nationally"
        unit_label = _unit_label(entry.get("unit"))
        st.caption(
            f"{entry['metric_label']}{geography_label}: "
            f"{fmt_value(latest['value'])} {unit_label} on {latest_date}. "
            "Administrative context only; it does not change the FinScope estimate."
            if latest else
            f"Observed source dates: {len(dates)} · latest reporting date {latest_date}."
        )
        st.warning(entry["limitations"])
        st.caption(
            "Periodic reported snapshots are shown on their actual dates; "
            "missing dates are not interpolated."
        )
        _render_trend(
            series_points,
            title=f"{entry['metric_label']} · {unit_label}",
            compact=True,
            snapshots=True,
            key_suffix=(
                f"{indicator_variable}_{district or 'national'}_"
                f"{subgroup_type}_{subgroup}_{source_version}"
            ),
        )
        with st.popover("View observations", icon=":material/table:"):
            _render_observation_table(series_points)
        if district and intelligence:
            _render_combined_peer_comparison(intelligence, district)
            _render_combined_intelligence(intelligence, district)


def _combined_peer_figure(
    points: Sequence[Mapping[str, Any]],
    selected_district: str,
    unit: str,
) -> go.Figure | None:
    observed = [
        point for point in points
        if isinstance(point.get("geography"), str)
        and point.get("value") is not None
    ]
    if not observed:
        return None
    ordered = sorted(
        observed,
        key=lambda point: (float(point["value"]), str(point["geography"]).casefold()),
    )
    colors = [
        PALETTE["sun"]
        if str(point["geography"]).casefold() == selected_district.casefold()
        else PALETTE["blue"]
        for point in ordered
    ]
    fig = go.Figure(go.Bar(
        x=[float(point["value"]) for point in ordered],
        y=[str(point["geography"]) for point in ordered],
        orientation="h",
        marker_color=colors,
        text=[fmt_value(point["value"]) for point in ordered],
        textposition="outside",
        cliponaxis=False,
        hovertemplate=(
            "%{y}<br>Recorded: %{x:,.7~r} "
            + esc(unit or "unit not specified")
            + "<extra>NBR administrative observation</extra>"
        ),
    ))
    fig.update_xaxes(
        title=unit or "unit not specified",
        rangemode="tozero",
        gridcolor=PALETTE["grid"],
        zeroline=False,
    )
    fig.update_yaxes(title=None, showgrid=False, autorange="reversed")
    fig.update_layout(
        height=max(260, 20 * len(ordered) + 60),
        margin=dict(l=4, r=34, t=8, b=8),
        showlegend=False,
    )
    return fig


def _render_combined_peer_comparison(
    intelligence: Mapping[str, Any],
    selected_district: str,
) -> None:
    points = intelligence.get("peer_points", [])
    peer_date = intelligence.get("peer_date")
    if not points or not peer_date:
        return
    observation = intelligence.get("observation") or {}
    unit = str(
        observation.get("unit")
        or (points[0].get("unit") if points else None)
        or "unit not specified"
    )
    fig = _combined_peer_figure(points, selected_district, unit)
    if fig is None:
        return
    st.markdown("**Same-scope district snapshot**")
    st.caption(
        f"{peer_date} · same NBR metric, filters, and reporting date. "
        "Only recorded district observations are plotted; missing values are not zero."
    )
    st.plotly_chart(
        style_chart(fig, fig.layout.height),
        use_container_width=True,
        config={"displayModeBar": False},
        key=(
            f"combined_nbr_peers_{selected_district}_"
            f"{peer_date}_{_source_data_version(points)}"
        ),
    )
    expected_count = intelligence.get("expected_district_count")
    if expected_count:
        st.caption(
            f"{len(points)} of {expected_count} expected district observations "
            "are available for this reporting date."
        )
    if not any(
        str(point.get("geography", "")).casefold()
        == selected_district.casefold()
        for point in points
    ):
        st.caption(
            f"No observation is recorded for {selected_district} on this date."
        )


def _render_combined_intelligence(
    intelligence: Mapping[str, Any],
    selected_district: str,
) -> None:
    st.markdown("**NBR intelligence**")
    if intelligence.get("state") != "available":
        st.caption(str(intelligence.get("reason") or "NBR evidence is unavailable."))
        st.markdown(
            "**Evidence-led follow-up.** "
            f"For {esc(selected_district)}, resolve the missing observation or "
            "provenance gap before interpreting this NBR series; missing is not zero."
        )
        st.caption(
            "The NBR detector uses administrative observations only; it does not "
            "assess FinScope estimates."
        )
        return

    observation = intelligence["observation"]
    unit = str(observation.get("unit") or "unit not specified")
    cross = intelligence["cross_section"]
    cross_state = cross["state"]
    if cross_state == "eligible_unusual_observation":
        candidate = cross["candidate"]
        sensitivity = candidate["sensitivity_1pct"][
            "classification_changes_with_1pct_perturbation"
        ]
        st.markdown(
            f"**Peer signal · {candidate['reporting_date']}.** "
            f"{esc(selected_district)} recorded {fmt_value(candidate['observed_value'])} "
            f"{esc(unit)}, compared with a peer median of "
            f"{fmt_value(candidate['peer_median'])} {esc(unit)} across "
            f"{candidate['comparison_district_count']} districts in the same "
            "metric, date, and filter scope. The detector flags this observation "
            "as unusual for review."
        )
        if sensitivity:
            st.caption(
                "The peer flag changes under a 1% value perturbation; treat it "
                "as especially sensitive to measurement precision."
            )
    elif cross_state == "assessable_no_qualifying_signal":
        st.markdown(
            f"**Peer assessment · {observation['reporting_date']}.** "
            f"The exact-scope comparison covered "
            f"{cross['observed_district_count']} districts; no qualifying peer "
            "signal was returned."
        )
    elif cross_state == "insufficient_evidence":
        st.markdown(
            f"**Peer assessment not run · {observation['reporting_date']}.** "
            f"{cross['observed_district_count']} eligible district observations "
            f"were available; the detector requires at least "
            f"{cross['minimum_peer_districts']}."
        )
    elif cross_state == "unassessable_zero_peer_dispersion":
        st.markdown(
            f"**Peer assessment not assessable · {observation['reporting_date']}.** "
            "The observed district values had no peer dispersion."
        )
    else:
        st.markdown(
            f"**Peer assessment unavailable · {observation['reporting_date']}.** "
            f"{esc(str(cross.get('state', 'unassessable')).replace('_', ' '))}."
        )

    temporal = intelligence["temporal"]
    temporal_state = temporal["state"]
    if temporal_state == "eligible_unusual_observation":
        case = temporal["case"]
        previous = case["previous"]
        target = case["target"]
        st.markdown(
            f"**Historical signal · {target['reporting_date']}.** The recorded "
            f"{fmt_value(previous['value'])} {esc(unit)} on "
            f"{previous['reporting_date']} changed to "
            f"{fmt_value(target['value'])} {esc(unit)}. The detector flags the "
            "rate of change as unusual relative to this district's compatible "
            "NBR history."
        )
    elif temporal_state == "assessable_no_qualifying_signal":
        case = temporal["case"]
        st.markdown(
            f"**Historical assessment · {case['target']['reporting_date']}.** "
            f"The compatible series had {case['training_rate_count']} historical "
            "rates; no qualifying unusual rate-change signal was returned."
        )
    elif temporal_state == "insufficient_evidence":
        st.markdown(
            "**Historical assessment not run.** "
            f"{temporal['observation_count']} compatible snapshots are available; "
            f"at least {temporal['minimum_observations']} distinct snapshots are "
            "needed for the existing detector."
        )
    else:
        reason = str(
            temporal.get("dispersion_status")
            or temporal.get("model_status")
            or "insufficient comparable history"
        ).replace("_", " ")
        st.markdown(
            f"**Historical assessment not assessable.** {esc(reason)}."
        )

    qualifications = observation.get("quality_qualifications") or []
    if qualifications:
        reasons = [
            str(item.get("reason"))
            for item in qualifications
            if isinstance(item, Mapping) and item.get("reason")
        ]
        if reasons:
            st.caption("Source qualification: " + " ".join(reasons))
    st.markdown(
        f"**Evidence-led follow-up.** {esc(str(intelligence['recommendation']))}"
    )
    st.caption(
        "Experimental, NBR-only review signals—not findings of financial "
        "exclusion, causation, policy failure, or intervention priority."
    )


def combined_strip(
    indicator_variable: str,
    *,
    district: str | None = None,
    scope: str = "",
    show_limitations: bool = False,
) -> tuple[str, Mapping[str, Any] | None]:
    """Compact NBR strip and its series, or ("", None) when no approved related series exists."""
    try:
        entries, _ = load_combined_context_data(
            indicator_variable,
            geography_level="district" if district else "national",
            geography=district,
        )
    except (RuntimeError, ValueError, OSError, PyMongoError):
        return "", None
    entries = [entry for entry in entries if entry.get("points")]
    if not entries:
        return "", None
    entry = entries[0]
    return context_strip_html(
        entry,
        scope=scope,
        other_series=len(entries) - 1,
        show_limitations=show_limitations,
    ), entry


def combined_strip_html(indicator_variable: str, **kwargs: Any) -> str:
    return combined_strip(indicator_variable, **kwargs)[0]


def render_combined_context(
    indicator_variable: str,
    *,
    district: str | None = None,
    subgroup_type: str = "",
    subgroup: str = "",
    entries: Sequence[Mapping[str, Any]] | None = None,
    source_version: str | None = None,
    intelligence: Mapping[str, Any] | None = None,
    expanded: bool = False,
) -> None:
    if entries is None:
        try:
            entries, source_version = load_combined_context_data(
                indicator_variable,
                geography_level="district" if district else "national",
                geography=district,
                subgroup_type=subgroup_type,
                subgroup=subgroup,
            )
        except (RuntimeError, ValueError, OSError, PyMongoError) as error:
            st.warning("NBR context could not be loaded. FinScope results are unchanged.")
            st.caption(str(error))
            return
    if not entries:
        return
    _render_combined_context(
        [point for entry in entries for point in entry["points"]],
        indicator_variable=indicator_variable,
        district=district,
        subgroup_type=subgroup_type,
        subgroup=subgroup,
        source_version=source_version,
        intelligence=intelligence,
        expanded=expanded,
    )


def _group_families(
    points: Sequence[Mapping[str, Any]],
    dimension: str,
) -> list[dict[str, Any]]:
    families: dict[tuple[Any, ...], dict[str, Any]] = {}
    for point in points:
        filters = point.get("filters")
        value = str(filters.get(dimension, "All")) if isinstance(filters, Mapping) else "All"
        if not value or value.casefold() == "all":
            continue
        base_filters = {key: val for key, val in filters.items() if key != dimension}
        key = (
            point.get("page"),
            point.get("metric_label"),
            point.get("unit"),
            point.get("geography_level"),
            point.get("geography"),
            _filters_key(base_filters),
        )
        family = families.setdefault(key, {
            "page": point.get("page"),
            "metric_label": point.get("metric_label"),
            "unit": point.get("unit"),
            "geography_level": point.get("geography_level"),
            "geography": point.get("geography"),
            "base_filters": base_filters,
            "groups": defaultdict(list),
        })
        family["groups"][value].append(dict(point))
    result = []
    for family in families.values():
        if len(family["groups"]) >= 2:
            result.append(family)
    return sorted(
        result,
        key=lambda item: (
            str(item["geography_level"]),
            str(item["geography"]),
            str(item["page"]),
            str(item["metric_label"]),
            _filters_key(item["base_filters"]),
        ),
    )


def _render_population_context(
    points: Sequence[Mapping[str, Any]],
    *,
    source_version: str,
) -> None:
    eligible_district_points = _eligible_nbr_district_points(points)
    national_families = {
        dimension: _population_group_families(
            points,
            dimension=dimension,
            geography_level="national",
            source_type="national_kpi",
        )
        for dimension in _POPULATION_GROUPS
    }
    district_families = {
        dimension: _population_group_families(
            eligible_district_points,
            dimension=dimension,
            geography_level="district",
            source_type="district_table",
            metric_label="Customers",
            unit="count",
        )
        for dimension in _POPULATION_GROUPS
    }
    source_pages = sorted(NBR_PAGE_LABELS)
    page_labels = [NBR_PAGE_LABELS[page] for page in source_pages]
    selected_service = _selected_service_area("population")

    dimension_key = f"nbr_population_dimension_{source_version}"
    dimension_state_exists = dimension_key in st.session_state
    selected_dimension = st.session_state.get(dimension_key)
    if selected_dimension not in _POPULATION_GROUPS:
        selected_dimension = "Gender"
        if dimension_state_exists:
            st.session_state[dimension_key] = selected_dimension
    national_options = [
        family
        for family in national_families[selected_dimension]
        if family["page"] == selected_service
        and _population_family_dates(family, selected_dimension)
    ]
    district_options = [
        family
        for family in district_families[selected_dimension]
        if family["page"] == selected_service
        and _population_family_dates(family, selected_dimension)
    ]

    with st.container(key="card_nbr_population_comparison"):
        card_title("Comparison controls")
        service_col, dimension_col = st.columns(
            [1, 1.5],
            gap="medium",
            vertical_alignment="bottom",
        )
        with service_col:
            st.selectbox(
                "Service area",
                page_labels,
                index=source_pages.index(selected_service),
                key="nbr_source_page_population",
            )
        with dimension_col:
            st.segmented_control(
                "Compare by",
                options=list(_POPULATION_GROUPS),
                default=None if dimension_state_exists else selected_dimension,
                selection_mode="single",
                key=dimension_key,
                width="content",
            )
        selected_national = None
        metric_options = _population_indicator_options(national_options)
        indicator_key = (
            f"nbr_population_indicator_{source_version}_"
            f"{selected_service}_{selected_dimension}"
        )
        indicator_labels = [option["label"] for option in metric_options]
        indicator_state_exists = indicator_key in st.session_state
        selected_indicator = st.session_state.get(indicator_key)
        indicator = None
        if selected_indicator not in indicator_labels:
            selected_indicator = indicator_labels[0] if indicator_labels else None
            if indicator_state_exists:
                st.session_state[indicator_key] = None
        if indicator_labels:
            st.pills(
                "Indicator",
                options=indicator_labels,
                selection_mode="single",
                default=(
                    None if indicator_state_exists else selected_indicator
                ),
                key=indicator_key,
            )
            selected_indicator = st.session_state.get(indicator_key)
            indicator = next(
                (
                    option for option in metric_options
                    if option["label"] == selected_indicator
                ),
                None,
            )
            if not indicator:
                st.info(
                    "Select an indicator."
                )
        else:
            st.info("No national KPI supports this comparison.")

        national_filter_col, district_filter_col = st.columns(2, gap="medium")
        with national_filter_col:
            if indicator:
                selected_national = _render_population_filter_groups(
                    indicator["families"],
                    source_version=source_version,
                    state_prefix=(
                        f"nbr_population_national_filters_{selected_service}_"
                        f"{selected_dimension}"
                    ),
                    title="National filters",
                    unavailable_message="No matching national filter scope.",
                )
            else:
                st.caption("National filters · unavailable")
        with district_filter_col:
            selected_district = _render_population_filter_groups(
                district_options,
                source_version=source_version,
                state_prefix=(
                    f"nbr_population_district_filters_{selected_service}_"
                    f"{selected_dimension}"
                ),
                title="District filters",
                unavailable_message="No matching district filter scope.",
            )

        national_dates = (
            set(_population_family_dates(selected_national, selected_dimension))
            if selected_national else set()
        )
        district_dates = (
            set(_population_family_dates(selected_district, selected_dimension))
            if selected_district else set()
        )
        reporting_dates = sorted(national_dates | district_dates)
        date_labels = {
            reporting_date: (
                f"{_display_reporting_date(reporting_date)} · "
                f"{'National + Districts' if reporting_date in national_dates and reporting_date in district_dates else 'National' if reporting_date in national_dates else 'Districts'}"
            )
            for reporting_date in reporting_dates
        }
        date_key = (
            f"nbr_population_date_{source_version}_"
            f"{selected_service}_{selected_dimension}"
        )
        date_state_exists = date_key in st.session_state
        selected_date = st.session_state.get(date_key)
        if selected_date not in reporting_dates:
            selected_date = (
                None if date_state_exists
                else reporting_dates[-1] if reporting_dates
                else None
            )
            st.session_state[date_key] = selected_date
        if reporting_dates:
            date_options = [date_labels[item] for item in reporting_dates]
            selected_date_label = date_labels.get(selected_date)
            date_label_key = f"{date_key}_label"
            date_label_state_exists = date_label_key in st.session_state
            current_date_label = st.session_state.get(date_label_key)
            if current_date_label not in date_options:
                current_date_label = None
                if date_label_state_exists:
                    st.session_state[date_label_key] = None
            st.pills(
                "Reporting date",
                options=date_options,
                selection_mode="single",
                default=(
                    None if date_label_state_exists else selected_date_label
                ),
                key=date_label_key,
            )
            chosen_date_label = st.session_state.get(date_label_key)
            selected_date = next(
                (
                    value for value, label in date_labels.items()
                    if label == chosen_date_label
                ),
                None,
            )
            st.session_state[date_key] = selected_date
        else:
            st.info("No paired reporting dates available.")

    _render_population_national_values(
        _prepare_population_national_result(
            points, selected_national,
            dimension=selected_dimension,
            reporting_date=selected_date,
        ),
        dimension=selected_dimension,
    )
    national_history = _prepare_population_national_history(
        points,
        selected_national,
        dimension=selected_dimension,
        selected_reporting_date=selected_date,
    )
    _render_population_national_history(
        national_history,
        dimension=selected_dimension,
    )
    try:
        expected_districts = tuple(_population_expected_districts())
        reference_error = None
    except (OSError, ValueError) as error:
        expected_districts = ()
        reference_error = str(error)
    district_result = _prepare_population_district_result(
        points,
        selected_district,
        dimension=selected_dimension,
        reporting_date=selected_date,
        expected_districts=expected_districts,
    )
    _render_population_district_counts(
        district_result,
        dimension=selected_dimension,
        reference_error=reference_error,
    )
    district_continuity = _prepare_population_district_continuity(
        points,
        selected_district,
        dimension=selected_dimension,
        expected_districts=expected_districts,
        selected_reporting_date=selected_date,
    )
    _render_population_district_continuity(
        district_continuity,
        dimension=selected_dimension,
        reference_error=reference_error,
    )


def _population_indicator_options(
    families: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for family in families:
        grouped[(
            str(family.get("metric_label", "")),
            str(family.get("unit", "")),
            str(family.get("unit_status", "")),
        )].append(family)
    label_counts: dict[str, int] = defaultdict(int)
    for metric, _, _ in grouped:
        label_counts[metric] += 1
    result = []
    for (metric, unit, unit_status), items in sorted(grouped.items()):
        label = metric
        if metric.casefold() == "subscribers":
            label = "Reported subscriber metric"
        if label_counts[metric] > 1:
            label = f"{label} · {unit or 'Unit not recorded by source'}"
            if sum(
                1 for candidate in grouped
                if candidate[0] == metric and candidate[1] == unit
            ) > 1:
                label += f" · {unit_status or 'unit status not recorded'}"
        result.append({
            "label": label,
            "families": items,
        })
    return result


def _render_population_filter_groups(
    families: Sequence[Mapping[str, Any]],
    *,
    source_version: str,
    state_prefix: str,
    title: str,
    unavailable_message: str = (
        "No eligible source family is available for this filter scope."
    ),
) -> Mapping[str, Any] | None:
    if not families:
        st.info(unavailable_message)
        return None
    card_title(title)
    dimensions = sorted({
        str(key)
        for family in families
        for key in family["base_filters"]
    })
    selected_filters: dict[str, str] = {}
    invalid_selection = False
    for dimension in dimensions:
        options = sorted({
            str(family["base_filters"].get(dimension, ""))
            for family in families
        })
        state_key = (
            f"{state_prefix}_{hashlib.sha1(dimension.encode()).hexdigest()[:8]}_"
            f"{source_version}"
        )
        had_selection = state_key in st.session_state
        selected = st.session_state.get(state_key)
        if selected not in options:
            selected = (
                "All" if "All" in options
                else options[0] if len(options) == 1
                else None
            ) if not had_selection else None
            if had_selection:
                st.session_state[state_key] = None
        if len(options) > 1:
            st.pills(
                dimension,
                options=options,
                selection_mode="single",
                default=None if had_selection else selected,
                key=state_key,
                format_func=lambda value: value or "Not recorded",
            )
            selected = st.session_state.get(state_key)
        else:
            selected = options[0]
        if selected not in options:
            invalid_selection = True
        else:
            selected_filters[dimension] = str(selected)
    if invalid_selection:
        st.warning(
            "Choose a value for each filter group. The previous filter combination "
            "is unavailable here; no alternate scope has been selected."
        )
        return None
    matching = next(
        (
            family for family in families
            if all(
                str(family["base_filters"].get(key, "")) == value
                for key, value in selected_filters.items()
            )
        ),
        None,
    )
    if matching is None:
        st.warning(
            "This filter combination was not reported for the selected metric. "
            "Choose another observed combination; no values have been substituted."
        )
        return None
    return matching


def _population_group_families(
    points: Sequence[Mapping[str, Any]],
    *,
    dimension: str,
    geography_level: str,
    source_type: str,
    metric_label: str | None = None,
    unit: str | None = None,
) -> list[dict[str, Any]]:
    """Group exact NBR metric/filter families without mixing geography sources."""
    categories = _POPULATION_GROUPS[dimension]
    families: dict[tuple[Any, ...], dict[str, Any]] = {}
    for point in points:
        filters = point.get("filters")
        if (
            not isinstance(filters, Mapping)
            or point.get("source_type") != source_type
            or point.get("geography_level") != geography_level
            or (geography_level == "national" and point.get("geography") != "Rwanda")
            or (metric_label is not None and point.get("metric_label") != metric_label)
            or (unit is not None and str(point.get("unit", "")) != unit)
            or point.get("repeated_snapshot_warning") is True
            or point.get("repeated_content_across_dates") is True
        ):
            continue
        category = str(filters.get(dimension, ""))
        if category not in categories:
            continue
        try:
            reporting_date = date.fromisoformat(str(point.get("reporting_date", "")))
            value = float(point.get("value"))
        except (TypeError, ValueError):
            continue
        if not math.isfinite(value) or value < 0:
            continue
        base_filters = {key: val for key, val in filters.items() if key != dimension}
        geography = point.get("geography") if geography_level == "national" else None
        key = (
            point.get("page"),
            point.get("metric_label"),
            point.get("unit"),
            point.get("unit_status"),
            geography_level,
            geography,
            source_type,
            _filters_key(base_filters),
        )
        family = families.setdefault(
            key,
            {
                "page": point.get("page"),
                "metric_label": point.get("metric_label"),
                "unit": point.get("unit"),
                "unit_status": point.get("unit_status"),
                "geography_level": geography_level,
                "geography": geography,
                "source_type": source_type,
                "base_filters": base_filters,
                "groups": {group: [] for group in categories},
            },
        )
        normalized_point = dict(point)
        normalized_point["reporting_date"] = reporting_date.isoformat()
        family["groups"][category].append(normalized_point)
    return sorted(
        (
            family for family in families.values()
            if all(family["groups"][group] for group in categories)
        ),
        key=lambda family: (
            str(family["page"]),
            str(family["metric_label"]),
            str(family["unit"]),
            _filters_key(family["base_filters"]),
        ),
    )


def _population_family_dates(
    family: Mapping[str, Any],
    dimension: str,
) -> list[str]:
    categories = _POPULATION_GROUPS[dimension]
    by_group: dict[str, dict[str, list[Mapping[str, Any]]]] = {
        group: defaultdict(list) for group in categories
    }
    for group in categories:
        for point in family.get("groups", {}).get(group, []):
            by_group[group][str(point.get("reporting_date", ""))].append(point)
    candidate_dates = set(by_group[categories[0]]) & set(by_group[categories[1]])
    complete_dates = []
    for reporting_date in sorted(candidate_dates):
        if family.get("geography_level") == "national":
            complete = all(
                len(by_group[group][reporting_date]) == 1 for group in categories
            )
        else:
            complete = all(
                by_group[group][reporting_date] for group in categories
            )
        if complete:
            complete_dates.append(reporting_date)
    return complete_dates


def _population_exact_candidates(
    points: Sequence[Mapping[str, Any]],
    family: Mapping[str, Any],
    *,
    dimension: str,
    category: str,
    reporting_date: str | None,
    geography_level: str,
) -> list[Mapping[str, Any]]:
    expected_filters = {
        **dict(family["base_filters"]),
        dimension: category,
    }
    return [
        point
        for point in points
        if point.get("page") == family.get("page")
        and point.get("metric_label") == family.get("metric_label")
        and str(point.get("unit", "")) == str(family.get("unit", ""))
        and str(point.get("unit_status", "")) == str(family.get("unit_status", ""))
        and point.get("source_type") == family.get("source_type")
        and point.get("geography_level") == geography_level
        and (
            geography_level != "national"
            or point.get("geography") == family.get("geography") == "Rwanda"
        )
        and (
            reporting_date is None
            or str(point.get("reporting_date", "")) == reporting_date
        )
        and isinstance(point.get("filters"), Mapping)
        and _filters_key(point["filters"]) == _filters_key(expected_filters)
    ]


def _population_observation_state(
    candidates: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    eligible = [
        point for point in candidates
        if point.get("repeated_snapshot_warning") is not True
        and point.get("repeated_content_across_dates") is not True
    ]
    excluded_count = len(candidates) - len(eligible)
    valid = []
    invalid_count = 0
    for point in eligible:
        value = point.get("value")
        if isinstance(value, bool):
            invalid_count += 1
            continue
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            invalid_count += 1
            continue
        if not math.isfinite(numeric_value) or numeric_value < 0:
            invalid_count += 1
            continue
        valid.append((point, numeric_value))

    if len(eligible) > 1:
        values = {value for _, value in valid}
        status = "conflicting_duplicates" if len(values) > 1 else "duplicate_observations"
        return {
            "status": status,
            "point": None,
            "candidate_count": len(eligible),
            "invalid_count": invalid_count,
            "excluded_count": excluded_count,
        }
    if len(valid) == 1 and invalid_count == 0:
        point, numeric_value = valid[0]
        normalized = dict(point)
        normalized["value"] = numeric_value
        return {
            "status": "observed",
            "point": normalized,
            "candidate_count": 1,
            "invalid_count": 0,
            "excluded_count": excluded_count,
        }
    if invalid_count:
        status = "invalid_value"
    elif excluded_count:
        status = "excluded_repeated_snapshot"
    else:
        status = "missing"
    return {
        "status": status,
        "point": None,
        "candidate_count": 0,
        "invalid_count": invalid_count,
        "excluded_count": excluded_count,
    }


def _prepare_population_national_result(
    points: Sequence[Mapping[str, Any]],
    family: Mapping[str, Any] | None,
    *,
    dimension: str,
    reporting_date: str | None,
) -> dict[str, Any]:
    categories = _POPULATION_GROUPS[dimension]
    if family is None or reporting_date is None:
        return {
            "status": "unavailable",
            "reason": "No national KPI family or reporting date is selected.",
            "family": family,
            "reporting_date": reporting_date,
            "groups": {
                category: {"status": "missing", "point": None}
                for category in categories
            },
        }
    group_results = {}
    for category in categories:
        candidates = _population_exact_candidates(
            points,
            family,
            dimension=dimension,
            category=category,
            reporting_date=reporting_date,
            geography_level="national",
        )
        group_results[category] = _population_observation_state(candidates)
    available = all(
        group_results[category]["status"] == "observed"
        for category in categories
    )
    return {
        "status": "available" if available else "partial",
        "reason": (
            "" if available
            else "A category is missing, invalid, repeated, or ambiguous for this exact national scope."
        ),
        "family": family,
        "reporting_date": reporting_date,
        "groups": group_results,
    }


def _population_family_candidates(
    points: Sequence[Mapping[str, Any]],
    family: Mapping[str, Any],
    *,
    dimension: str,
    category: str,
    geography_level: str,
) -> list[Mapping[str, Any]]:
    return _population_exact_candidates(
        points,
        family,
        dimension=dimension,
        category=category,
        reporting_date=None,
        geography_level=geography_level,
    )


def _population_date_is_valid(value: Any) -> bool:
    try:
        date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return False
    return True


def _prepare_population_national_history(
    points: Sequence[Mapping[str, Any]],
    family: Mapping[str, Any] | None,
    *,
    dimension: str,
    selected_reporting_date: str | None,
) -> dict[str, Any]:
    categories = _POPULATION_GROUPS[dimension]
    if family is None:
        return {
            "status": "unavailable",
            "reason": "No national KPI family is selected for this comparison.",
            "family": None,
            "dates": [],
            "groups": {category: {} for category in categories},
            "selected_reporting_date": selected_reporting_date,
        }

    candidates = {
        category: _population_family_candidates(
            points,
            family,
            dimension=dimension,
            category=category,
            geography_level="national",
        )
        for category in categories
    }
    dates = sorted({
        reporting_date
        for group_points in candidates.values()
        for point in group_points
        if _population_date_is_valid(
            reporting_date := str(point.get("reporting_date", ""))
        )
    })
    group_results = {
        category: {
            reporting_date: _population_observation_state([
                point
                for point in candidates[category]
                if str(point.get("reporting_date", "")) == reporting_date
            ])
            for reporting_date in dates
        }
        for category in categories
    }
    paired_dates = [
        reporting_date
        for reporting_date in dates
        if all(
            group_results[category][reporting_date]["status"] == "observed"
            for category in categories
        )
    ]
    return {
        "status": "available" if paired_dates else "unavailable",
        "reason": (
            "" if paired_dates else
            "No reporting date has eligible observations for both groups under this exact scope."
        ),
        "family": family,
        "dates": paired_dates,
        "groups": group_results,
        "selected_reporting_date": selected_reporting_date,
    }


def _prepare_population_district_continuity(
    points: Sequence[Mapping[str, Any]],
    family: Mapping[str, Any] | None,
    *,
    dimension: str,
    expected_districts: Sequence[str],
    selected_reporting_date: str | None,
) -> dict[str, Any]:
    categories = _POPULATION_GROUPS[dimension]
    empty_coverage = {
        "both": 0,
        "one": 0,
        "neither": 0,
    }
    if family is None or not expected_districts:
        return {
            "status": "unavailable",
            "reason": (
                "No district-table family or named-district reference is available "
                "for this comparison."
            ),
            "family": family,
            "dates": [],
            "districts": {},
            "district_names": [],
            "coverage": empty_coverage,
            "unknown_groups": {},
            "unmatched_geographies": {},
            "selected_reporting_date": selected_reporting_date,
        }

    candidates = {
        category: _population_family_candidates(
            points,
            family,
            dimension=dimension,
            category=category,
            geography_level="district",
        )
        for category in categories
    }
    unknown_level_candidates = {
        category: _population_exact_candidates(
            points,
            family,
            dimension=dimension,
            category=category,
            reporting_date=None,
            geography_level="unknown",
        )
        for category in categories
    }
    unknown_candidates = {
        category: [
            point
            for point in (
                *candidates[category],
                *unknown_level_candidates[category],
            )
            if str(point.get("geography", "")).strip().casefold() == "unknown"
        ]
        for category in categories
    }
    canonical_districts = {
        str(name).strip().casefold(): str(name).strip()
        for name in expected_districts
        if str(name).strip()
    }
    district_names = sorted(set(canonical_districts.values()), key=str.casefold)
    candidate_dates = sorted({
        reporting_date
        for group_points in (*candidates.values(), *unknown_candidates.values())
        for point in group_points
        if _population_date_is_valid(
            reporting_date := str(point.get("reporting_date", ""))
        )
    })

    districts: dict[str, dict[str, dict[str, dict[str, Any]]]] = {}
    unknown_groups: dict[str, dict[str, dict[str, Any]]] = {}
    unmatched_geographies: dict[str, list[dict[str, str]]] = {}
    dates = []
    for reporting_date in candidate_dates:
        group_states: dict[str, dict[str, dict[str, Any]]] = {
            district: {} for district in district_names
        }
        for category in categories:
            scoped_date = [
                point for point in candidates[category]
                if str(point.get("reporting_date", "")) == reporting_date
            ]
            by_district: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
            for point in scoped_date:
                geography = str(point.get("geography", "")).strip()
                normalized = geography.casefold()
                if normalized in canonical_districts:
                    by_district[canonical_districts[normalized]].append(point)
            for district in district_names:
                group_states[district][category] = _population_observation_state(
                    by_district.get(district, [])
                )
            unknown_groups.setdefault(reporting_date, {})[category] = (
                _population_observation_state([
                    point for point in unknown_candidates[category]
                    if str(point.get("reporting_date", "")) == reporting_date
                ])
            )
            unmatched_by_label: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
            for point in scoped_date:
                geography = str(point.get("geography", "")).strip()
                normalized = geography.casefold()
                if (
                    geography
                    and normalized != "unknown"
                    and normalized not in canonical_districts
                ):
                    unmatched_by_label[geography].append(point)
            for geography, observations in unmatched_by_label.items():
                if _population_observation_state(observations)["status"] == "observed":
                    unmatched_geographies.setdefault(reporting_date, []).append({
                        "geography": geography,
                        "category": category,
                    })

        if not any(
            state["status"] == "observed"
            for group_states in group_states.values()
            for state in group_states.values()
        ):
            continue
        dates.append(reporting_date)
        districts[reporting_date] = group_states

    coverage_by_date = {}
    for reporting_date in dates:
        counts = {"both": 0, "one": 0, "neither": 0}
        for group_states in districts[reporting_date].values():
            observed_count = sum(
                group_states[category]["status"] == "observed"
                for category in categories
            )
            state = "both" if observed_count == 2 else "one" if observed_count == 1 else "neither"
            counts[state] += 1
        coverage_by_date[reporting_date] = counts
    coverage = {
        state: sum(counts[state] for counts in coverage_by_date.values())
        for state in ("both", "one", "neither")
    }
    observed_states = {
        state
        for counts in coverage_by_date.values()
        for state, count in counts.items()
        if count
    }
    if not dates:
        status = "unavailable"
        reason = "No eligible named-district observations are available for this exact scope."
    elif observed_states == {"both"}:
        status = "complete"
        reason = "All named districts have both groups reported on every available date."
    elif len(observed_states) == 1:
        status = "uniform_incomplete"
        reason = "Coverage is incomplete but does not vary across the available district-date cells."
    else:
        status = "varies"
        reason = ""
    return {
        "status": status,
        "reason": reason,
        "family": family,
        "dates": dates,
        "districts": districts,
        "district_names": district_names,
        "coverage": coverage,
        "coverage_by_date": coverage_by_date,
        "unknown_groups": unknown_groups,
        "unmatched_geographies": unmatched_geographies,
        "selected_reporting_date": selected_reporting_date,
    }


def _prepare_population_district_result(
    points: Sequence[Mapping[str, Any]],
    family: Mapping[str, Any] | None,
    *,
    dimension: str,
    reporting_date: str | None,
    expected_districts: Sequence[str],
) -> dict[str, Any]:
    categories = _POPULATION_GROUPS[dimension]
    if family is None or reporting_date is None:
        return {
            "status": "unavailable",
            "reason": "No district-table family or reporting date is selected.",
            "family": family,
            "reporting_date": reporting_date,
            "districts": [],
            "unknown_groups": {},
            "unexpected_groups": {},
            "coverage": {
                "both": 0,
                "partial": 0,
                "none": len(expected_districts),
                "expected": len(expected_districts),
            },
        }

    canonical_districts = {
        str(name).strip().casefold(): str(name).strip()
        for name in expected_districts
        if str(name).strip()
    }
    district_results = {
        name: {category: {"status": "missing", "point": None} for category in categories}
        for name in sorted(canonical_districts.values(), key=str.casefold)
    }
    unknown_candidates: dict[str, list[Mapping[str, Any]]] = {
        category: [] for category in categories
    }
    unexpected_candidates: dict[str, list[Mapping[str, Any]]] = {
        category: [] for category in categories
    }

    for category in categories:
        candidates = _population_exact_candidates(
            points,
            family,
            dimension=dimension,
            category=category,
            reporting_date=reporting_date,
            geography_level="district",
        )
        candidates.extend(
            point for point in _population_exact_candidates(
                points,
                family,
                dimension=dimension,
                category=category,
                reporting_date=reporting_date,
                geography_level="unknown",
            )
        )
        by_district: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for point in candidates:
            raw_district = str(point.get("geography", "")).strip()
            normalized = raw_district.casefold()
            if not raw_district or normalized == "unknown":
                unknown_candidates[category].append(point)
            elif normalized in canonical_districts:
                name = canonical_districts[normalized]
                by_district[name].append(point)
            else:
                unexpected_candidates[category].append(point)
        for district in district_results:
            district_results[district][category] = _population_observation_state(
                by_district.get(district, [])
            )

    both = sum(
        all(district_results[district][category]["status"] == "observed"
            for category in categories)
        for district in district_results
    )
    partial = sum(
        any(district_results[district][category]["status"] == "observed"
            for category in categories)
        and not all(district_results[district][category]["status"] == "observed"
                    for category in categories)
        for district in district_results
    )
    none = len(district_results) - both - partial
    unknown_groups = {
        category: _population_observation_state(unknown_candidates[category])
        for category in categories
    }
    unexpected_groups = {
        category: _population_observation_state(unexpected_candidates[category])
        for category in categories
    }
    status = (
        "unavailable" if not district_results
        else "available" if both == len(district_results)
        else "partial_coverage" if both or partial
        else "unavailable"
    )
    return {
        "status": status,
        "reason": (
            "" if status == "available"
            else "District coverage is partial or unavailable for this exact scope."
        ),
        "family": family,
        "reporting_date": reporting_date,
        "districts": district_results,
        "unknown_groups": unknown_groups,
        "unexpected_groups": unexpected_groups,
        "coverage": {
            "both": both,
            "partial": partial,
            "none": none,
            "expected": len(district_results),
        },
    }


@st.cache_data(show_spinner=False)
def _population_expected_districts() -> tuple[str, ...]:
    """Cache the static administrative district reference, not observations."""
    return tuple(sorted(load_district_reference(), key=str.casefold))


def _population_value(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "Not reported"
    if not math.isfinite(number):
        return "Not reported"
    return format(number, ",.15g")


def _population_status_label(status: str | None) -> str:
    return {
        "missing": "Not reported for this exact scope.",
        "invalid_value": "The stored value is invalid.",
        "excluded_repeated_snapshot": "Repeated snapshot excluded.",
        "duplicate_observations": "Multiple observations; no value selected.",
        "conflicting_duplicates": "Conflicting observations; no value selected.",
    }.get(str(status), "Unavailable for this exact scope.")


def _population_national_history_figure(
    result: Mapping[str, Any],
    *,
    dimension: str,
) -> go.Figure:
    family = result["family"]
    categories = _POPULATION_GROUPS[dimension]
    dates = result["dates"]
    figure = go.Figure()
    for category in categories:
        points = [
            result["groups"][category][reporting_date]["point"]
            for reporting_date in dates
        ]
        selected = result.get("selected_reporting_date")
        marker_sizes = [
            12 if reporting_date == selected else 8
            for reporting_date in dates
        ]
        marker_widths = [
            2.8 if reporting_date == selected else 1.2
            for reporting_date in dates
        ]
        figure.add_trace(go.Scatter(
            x=[point["reporting_date"] for point in points],
            y=[float(point["value"]) for point in points],
            name=category,
            mode="lines+markers",
            connectgaps=False,
            line=dict(
                color=_POPULATION_GROUP_COLORS[category],
                width=2.8,
            ),
            marker=dict(
                color=_POPULATION_GROUP_COLORS[category],
                size=marker_sizes,
                line=dict(color="white", width=marker_widths),
            ),
            customdata=[
                [
                    _display_reporting_date(point["reporting_date"]),
                    category,
                    _population_value(point["value"]),
                    str(family["metric_label"]),
                ]
                for point in points
            ],
            hovertemplate=(
                "<b>%{customdata[1]}</b><br>%{customdata[3]}: "
                "%{customdata[2]}<br>Reporting date: %{customdata[0]}"
                "<extra></extra>"
            ),
        ))
    unit = str(family.get("unit") or "Unit not recorded by source")
    figure.update_layout(
        height=330,
        margin=dict(l=20, r=28, t=22, b=58),
        plot_bgcolor="#FBFCFD",
        paper_bgcolor="white",
        hoverlabel=dict(bgcolor="#172B3A", font=dict(color="white")),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            x=0,
            title_text=None,
            font=dict(size=12, color=PALETTE["ink"]),
        ),
        xaxis=dict(
            title="NBR reporting date",
            type="date",
            tickformat="%d %b %Y",
            showgrid=False,
            linecolor="#D5DFE5",
            ticks="outside",
            tickcolor="#D5DFE5",
            tickfont=dict(size=10, color=PALETTE["muted"]),
        ),
        yaxis=dict(
            title=f"{family['metric_label']} · {unit}",
            rangemode="tozero",
            tickformat=",~g",
            showgrid=True,
            gridcolor="#E7EDF1",
            zerolinecolor="#A9B8C2",
            tickfont=dict(size=11, color=PALETTE["ink"]),
        ),
    )
    return style_chart(
        figure,
        330,
        margin=dict(l=20, r=28, t=22, b=58),
        plot_bgcolor="#FBFCFD",
        paper_bgcolor="white",
        hoverlabel=dict(
            bgcolor="#172B3A",
            bordercolor="#172B3A",
            font=dict(color="white", size=12),
        ),
    )


def _render_population_national_history(
    result: Mapping[str, Any],
    *,
    dimension: str,
) -> None:
    with st.container(key="card_nbr_population_national_history"):
        card_title(
            "National group history",
            "Observed paired national KPI values only; dates are not interpolated.",
        )
        family = result.get("family")
        if family is None or not result.get("dates"):
            st.info(
                result.get("reason")
                or "No paired national history is available for this exact scope."
            )
            return
        unit = str(family.get("unit") or "Unit not recorded by source")
        service_label = NBR_PAGE_LABELS.get(str(family["page"]), family["page"])
        st.caption(
            f"Rwanda · National KPI · {service_label} · "
            f"{family['metric_label']} · {unit} · "
            f"{len(result['dates'])} paired reporting dates"
        )
        selected_date = result.get("selected_reporting_date")
        if selected_date in result["dates"]:
            st.caption(
                f"Selected reporting date highlighted: "
                f"{_display_reporting_date(selected_date)}"
            )
        st.plotly_chart(
            _population_national_history_figure(result, dimension=dimension),
            width="stretch",
            key=(
                f"nbr_population_history_{dimension}_"
                f"{hashlib.sha1(_filters_key(family['base_filters']).encode()).hexdigest()[:8]}"
            ),
            config={"displayModeBar": False},
        )
        st.caption(
            "NBR administrative counts are not verified unique-person totals or "
            "population-adjusted inclusion rates."
        )


def _population_district_continuity_figure(
    result: Mapping[str, Any],
    *,
    dimension: str,
) -> go.Figure:
    categories = _POPULATION_GROUPS[dimension]
    districts = result["district_names"]
    dates = result["dates"]
    z_values = []
    hover_data = []
    text_values = []
    for district in districts:
        row_values = []
        row_hover = []
        row_text = []
        for reporting_date in dates:
            group_states = result["districts"][reporting_date][district]
            observed = [
                category for category in categories
                if group_states[category]["status"] == "observed"
            ]
            code = 2 if len(observed) == 2 else 1 if len(observed) == 1 else 0
            row_values.append(code)
            row_text.append(("Neither", "One", "Both")[code])
            row_hover.append([
                ", ".join(observed) if observed else "None",
                " · ".join(
                    f"{category}: {_population_status_label(group_states[category]['status'])}"
                    for category in categories
                ),
                _display_reporting_date(reporting_date),
            ])
        z_values.append(row_values)
        hover_data.append(row_hover)
        text_values.append(row_text)

    figure = go.Figure(go.Heatmap(
        x=dates,
        y=districts,
        z=z_values,
        customdata=hover_data,
        text=text_values,
        texttemplate="%{text}",
        textfont=dict(size=9, color="#17313D"),
        zmin=0,
        zmax=2,
        colorscale=[
            [0.0, "#E8EDF0"],
            [0.2499, "#E8EDF0"],
            [0.25, "#E6B45A"],
            [0.7499, "#E6B45A"],
            [0.75, "#4D9A83"],
            [1.0, "#4D9A83"],
        ],
        colorbar=dict(
            title=dict(text="Reported groups"),
            tickmode="array",
            tickvals=[0, 1, 2],
            ticktext=["Neither", "One", "Both"],
            thickness=14,
            len=0.76,
            outlinewidth=0,
            tickfont=dict(size=10, color=PALETTE["ink"]),
        ),
        xgap=3,
        ygap=2,
        hovertemplate=(
            "<b>%{y}</b><br>Reporting date: %{customdata[2]}<br>"
            "Groups with eligible observations: %{customdata[0]}<br>"
            "%{customdata[1]}<extra></extra>"
        ),
    ))
    figure.update_layout(
        height=max(540, min(25 * len(districts) + 145, 1000)),
        margin=dict(l=16, r=18, t=22, b=62),
        plot_bgcolor="white",
        paper_bgcolor="white",
        hoverlabel=dict(bgcolor="#172B3A", font=dict(color="white")),
        xaxis=dict(
            title="NBR reporting date",
            type="category",
            categoryorder="array",
            categoryarray=dates,
            tickmode="array",
            tickvals=dates,
            ticktext=[_display_reporting_date(item) for item in dates],
            tickangle=-28,
            showgrid=False,
            linecolor="#D5DFE5",
            ticks="outside",
            tickfont=dict(size=10, color=PALETTE["muted"]),
        ),
        yaxis=dict(
            title=None,
            categoryorder="array",
            categoryarray=districts,
            autorange="reversed",
            showgrid=False,
            tickfont=dict(size=10, color=PALETTE["ink"]),
        ),
    )
    selected_date = result.get("selected_reporting_date")
    if selected_date in dates:
        selected_index = dates.index(selected_date)
        figure.add_shape(
            type="rect",
            xref="x",
            yref="paper",
            x0=selected_index - 0.5,
            x1=selected_index + 0.5,
            y0=0,
            y1=1,
            fillcolor="rgba(47, 109, 181, 0.04)",
            line=dict(color="#2F6DB5", width=2),
            layer="above",
        )
    return style_chart(
        figure,
        figure.layout.height,
        margin=dict(l=16, r=18, t=22, b=62),
        hoverlabel=dict(
            bgcolor="#172B3A",
            bordercolor="#172B3A",
            font=dict(color="white", size=12),
        ),
    )


def _render_population_district_continuity(
    result: Mapping[str, Any],
    *,
    dimension: str,
    reference_error: str | None = None,
) -> None:
    if result.get("status") == "complete":
        return

    with st.container(key="card_nbr_population_district_continuity"):
        card_title(
            "District reporting continuity",
            "Observation coverage across named districts and actual reporting dates—not service availability.",
        )
        if reference_error:
            st.error(f"District reference could not be loaded: {reference_error}")
            return
        family = result.get("family")
        if family is None or not result.get("dates"):
            st.info(
                result.get("reason")
                or "Insufficient eligible district observations for a coverage matrix."
            )
            return
        coverage = result["coverage"]
        service_label = NBR_PAGE_LABELS.get(str(family["page"]), family["page"])
        st.caption(
            f"{service_label} · {family['metric_label']} [count] · "
            f"{len(result['dates'])} observed dates · "
            f"{len(result['districts'])} named districts"
        )
        if result.get("status") == "unavailable":
            st.info(result.get("reason", "Coverage variation cannot be shown."))
            return
        selected_date = result.get("selected_reporting_date")
        if selected_date in result["dates"]:
            st.caption(
                f"Selected reporting date highlighted: "
                f"{_display_reporting_date(selected_date)}"
            )
        st.markdown(
            f"**District-date cells:** {coverage['both']} both groups · "
            f"{coverage['one']} one group · {coverage['neither']} neither"
        )
        st.plotly_chart(
            _population_district_continuity_figure(result, dimension=dimension),
            width="stretch",
            key=(
                f"nbr_population_continuity_{dimension}_"
                f"{hashlib.sha1(_filters_key(family['base_filters']).encode()).hexdigest()[:8]}"
            ),
            config={"displayModeBar": False},
        )
        unknown_observations = [
            (reporting_date, category)
            for reporting_date, group_results in result["unknown_groups"].items()
            for category, state in group_results.items()
            if state["status"] == "observed"
        ]
        if unknown_observations:
            st.caption(
                f"{len(unknown_observations)} verified unknown-geography group/date "
                "observation(s) are kept outside the named-district matrix."
            )
        unmatched = [
            item
            for items in result.get("unmatched_geographies", {}).values()
            for item in items
        ]
        if unmatched:
            labels = sorted(
                {item["geography"] for item in unmatched},
                key=str.casefold,
            )
            st.caption(
                "Unmatched geography labels kept outside the matrix: "
                + ", ".join(labels)
            )
        st.caption(
            "Missing observations are not zero and do not establish service absence "
            "or financial exclusion."
        )


def _render_population_national_values(
    result: Mapping[str, Any],
    *,
    dimension: str,
) -> None:
    family = result.get("family")
    reporting_date = result.get("reporting_date")
    groups = result.get("groups", {})
    with st.container(key="card_nbr_population_national_values"):
        card_title(
            "National values by group",
            "Reported national values, shown side by side without a derived gap.",
        )
        if family is None:
            st.info(result.get("reason", "No national KPI family is available."))
            return
        unit = str(family.get("unit") or "")
        unit_label = unit or "Unit not recorded by source"
        service_label = NBR_PAGE_LABELS.get(str(family["page"]), family["page"])
        st.caption(
            f"Rwanda · National KPI · {service_label} · "
            f"{family['metric_label']} · {unit_label} · "
            f"{_display_reporting_date(reporting_date)}"
        )
        observed_values = [
            groups[category]["point"]["value"]
            for category in _POPULATION_GROUPS[dimension]
            if groups.get(category, {}).get("status") == "observed"
        ]
        if observed_values:
            figure = _population_national_figure(result, dimension=dimension)
            st.plotly_chart(
                figure,
                width="stretch",
                key=(
                    f"nbr_population_national_{dimension}_{reporting_date}_"
                    f"{hashlib.sha1(_filters_key(family['base_filters']).encode()).hexdigest()[:8]}"
                ),
                config={"displayModeBar": False},
            )
        if result.get("status") != "available":
            st.warning(
                result.get("reason")
                or "A category is missing, invalid, repeated, or ambiguous."
            )
            for category in _POPULATION_GROUPS[dimension]:
                group_result = groups.get(category, {})
                if group_result.get("status") != "observed":
                    st.caption(
                        f"{category}: {_population_status_label(group_result.get('status'))}"
                    )


def _population_national_figure(
    result: Mapping[str, Any],
    *,
    dimension: str,
) -> go.Figure:
    family = result["family"]
    groups = result["groups"]
    categories = _POPULATION_GROUPS[dimension]
    observed = [
        category for category in categories
        if groups.get(category, {}).get("status") == "observed"
    ]
    max_value = max(
        (float(groups[category]["point"]["value"]) for category in observed),
        default=0,
    )
    unit = str(family.get("unit") or "unit not recorded by source")
    figure = go.Figure()
    figure.add_trace(go.Bar(
        x=[groups[category]["point"]["value"] for category in observed],
        y=observed,
        orientation="h",
        text=[
            _population_value(groups[category]["point"]["value"])
            for category in observed
        ],
        textposition="outside",
        textfont=dict(size=13, color=PALETTE["ink"]),
        cliponaxis=False,
        marker=dict(color=[
            _POPULATION_GROUP_COLORS[category] for category in observed
        ]),
        customdata=[
            [
                category,
                _population_value(groups[category]["point"]["value"]),
                str(family["metric_label"]),
                _display_reporting_date(result["reporting_date"]),
            ]
            for category in observed
        ],
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>%{customdata[2]}: "
            "%{customdata[1]}<br>Reporting date: %{customdata[3]}<extra></extra>"
        ),
        showlegend=False,
    ))
    figure.update_layout(
        height=250,
        margin=dict(l=16, r=92, t=12, b=54),
        plot_bgcolor="#FBFCFD",
        paper_bgcolor="white",
        hoverlabel=dict(bgcolor="#172B3A", font=dict(color="white")),
        bargap=0.46,
        xaxis=dict(
            title=f"Reported value · {unit}",
            range=[0, max_value * 1.24 if max_value else 1],
            tickformat=",~g",
            showgrid=True,
            gridcolor="#E7EDF1",
            zerolinecolor="#A9B8C2",
            linecolor="#D5DFE5",
            ticks="outside",
            tickcolor="#D5DFE5",
        ),
        yaxis=dict(
            title=None,
            categoryorder="array",
            categoryarray=list(reversed(categories)),
            showgrid=False,
            tickfont=dict(size=14, color=PALETTE["ink"]),
        ),
    )
    return style_chart(figure, 250)


def _population_district_figure(
    result: Mapping[str, Any],
    *,
    dimension: str,
) -> tuple[go.Figure, list[dict[str, Any]]]:
    family = result["family"]
    reporting_date = str(result["reporting_date"])
    categories = _POPULATION_GROUPS[dimension]
    district_results = result["districts"]
    districts = list(district_results)
    max_value = max(
        (
            float(state["point"]["value"])
            for group_results in district_results.values()
            for state in group_results.values()
            if state.get("status") == "observed"
        ),
        default=0,
    )
    figure = go.Figure()
    for category in categories:
        present = [
            (district, district_results[district][category]["point"])
            for district in districts
            if district_results[district][category].get("status") == "observed"
        ]
        figure.add_trace(go.Bar(
            x=[float(point["value"]) for _, point in present],
            y=[district for district, _ in present],
            name=category,
            marker={
                "color": _POPULATION_GROUP_COLORS[category],
                "line": {"color": "white", "width": 0.8},
            },
            orientation="h",
            text=[_population_value(point["value"]) for _, point in present],
            textposition="outside",
            textfont=dict(size=10, color=PALETTE["ink"]),
            cliponaxis=False,
            customdata=[
                [
                    district,
                    _population_value(point["value"]),
                    _display_reporting_date(point["reporting_date"]),
                ]
                for district, point in present
            ],
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                f"{esc(category)}: %{{customdata[1]}} "
                f"{esc(str(family.get('unit') or 'count'))}<br>"
                "Reporting date: %{customdata[2]}<extra></extra>"
            ),
            showlegend=True,
        ))
    figure.update_layout(
        height=max(600, min(29 * len(districts) + 160, 1120)),
        margin=dict(l=16, r=88, t=34, b=56),
        plot_bgcolor="#FBFCFD",
        paper_bgcolor="white",
        hoverlabel=dict(bgcolor="#172B3A", font=dict(color="white")),
        barmode="group",
        bargap=0.28,
        bargroupgap=0.12,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            x=0,
            title_text=None,
            font=dict(size=12, color=PALETTE["ink"]),
            itemsizing="constant",
        ),
        xaxis=dict(
            title="Customers [count]",
            range=[0, max_value * 1.24 if max_value else 1],
            tickformat=",.0f",
            showgrid=True,
            gridcolor="#E7EDF1",
            zerolinecolor="#A9B8C2",
            linecolor="#D5DFE5",
            ticks="outside",
            tickcolor="#D5DFE5",
        ),
        yaxis=dict(
            title=None,
            categoryorder="array",
            categoryarray=districts,
            autorange="reversed",
            showgrid=False,
            tickfont=dict(size=11, color=PALETTE["ink"]),
        ),
    )
    figure.update_xaxes(automargin=True)
    figure.update_yaxes(automargin=True)
    figure.add_annotation(
        text="No bar means the observation was not reported for that group.",
        xref="paper",
        yref="paper",
        x=0,
        y=-0.19,
        xanchor="left",
        yanchor="top",
        showarrow=False,
        font=dict(size=10, color=PALETTE["muted"]),
    )
    table_rows = []
    for district in districts:
        row: dict[str, Any] = {"District": district}
        for category in categories:
            state = district_results[district][category]
            point = state.get("point")
            row[category] = _population_value(point["value"]) if point else {
                "missing": "Not reported",
                "invalid_value": "Invalid value",
                "duplicate_observations": "Duplicate",
                "conflicting_duplicates": "Conflicting duplicate",
                "excluded_repeated_snapshot": "Repeated snapshot excluded",
            }.get(state.get("status"), "Not reported")
        table_rows.append(row)
    return style_chart(figure, figure.layout.height), table_rows


def _render_population_district_counts(
    result: Mapping[str, Any],
    *,
    dimension: str,
    reference_error: str | None = None,
) -> None:
    family = result.get("family")
    reporting_date = result.get("reporting_date")
    with st.container(key="card_nbr_population_district_counts"):
        card_title(
            "District customer counts by group",
            "District-table Customers [count] · named districts · no population adjustment.",
        )
        if reference_error:
            st.error(f"District reference could not be loaded: {reference_error}")
        if family is None:
            st.info(result.get("reason", "No district-table family is available."))
            return
        service_label = NBR_PAGE_LABELS.get(str(family["page"]), family["page"])
        st.caption(
            f"{service_label} · {family['metric_label']} [count] · "
            f"{_display_reporting_date(reporting_date)}"
        )
        coverage = result["coverage"]
        st.markdown(
            f"**District coverage:** {coverage['both']} of {coverage['expected']} "
            f"with both groups · {coverage['partial']} partial · "
            f"{coverage['none']} not reported"
        )
        if result.get("status") == "unavailable":
            st.info(result.get("reason", "No eligible district observations are available."))
            return
        figure, table_rows = _population_district_figure(
            result,
            dimension=dimension,
        )
        st.plotly_chart(
            figure,
            width="stretch",
            key=f"nbr_population_district_{dimension}_{reporting_date}_{hashlib.sha1(_filters_key(family['base_filters']).encode()).hexdigest()[:8]}",
            config={"displayModeBar": False},
        )
        with st.expander("District values and missing observations"):
            st.dataframe(
                pd.DataFrame(table_rows),
                width="stretch",
                hide_index=True,
            )
            unknown_rows = []
            for category, state in result["unknown_groups"].items():
                if state["candidate_count"] or state["excluded_count"] or state["invalid_count"]:
                    unknown_rows.append({
                        "Geography": "Unknown / unclassified",
                        "Group": category,
                        "Status": state["status"],
                        "Verified observations": state["candidate_count"],
                        "Excluded repeated observations": state["excluded_count"],
                    })
            unexpected_rows = []
            for category, state in result["unexpected_groups"].items():
                if state["candidate_count"] or state["excluded_count"] or state["invalid_count"]:
                    unexpected_rows.append({
                        "Geography": "Unmatched district label",
                        "Group": category,
                        "Status": state["status"],
                        "Verified observations": state["candidate_count"],
                        "Excluded repeated observations": state["excluded_count"],
                    })
            if unknown_rows:
                st.caption("Verified unknown/unclassified geography (kept separate):")
                st.dataframe(
                    pd.DataFrame(unknown_rows),
                    width="stretch",
                    hide_index=True,
                )
            if unexpected_rows:
                st.caption("District labels not found in the boundary reference:")
                st.dataframe(
                    pd.DataFrame(unexpected_rows),
                    width="stretch",
                    hide_index=True,
                )
        st.caption(
            "Counts are administrative observations, not verified unique-person totals "
            "or population-adjusted inclusion rates."
        )


def _page_series_selection(
    points: Sequence[Mapping[str, Any]],
    *,
    registry: Sequence[Mapping[str, Any]],
    source_version: str,
    geography_level: str,
    view: str,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    scoped = [
        item for item in registry
        if item.get("geography_level") == geography_level
    ]
    if not scoped:
        return None, []
    pages = sorted({str(item["source_page"]) for item in scoped})
    page = pages[0]
    if len(pages) > 1:
        page = st.selectbox(
            "Service area",
            pages,
            format_func=lambda value: NBR_PAGE_LABELS.get(value, value),
            key=f"nbr_{view}_page_{source_version}",
        )
    page_series = [item for item in scoped if item["source_page"] == page]
    metrics = sorted({
        (str(item["metric_label"]), str(item.get("unit", "")))
        for item in page_series
    })
    metric_keys = [f"{label} · {unit or 'unit not specified'}" for label, unit in metrics]
    metric_key = st.selectbox(
        "Measure",
        metric_keys,
        key=f"nbr_{view}_metric_{source_version}",
    )
    metric, unit = metrics[metric_keys.index(metric_key)]
    matching_series = [
        item for item in page_series
        if item["metric_label"] == metric and str(item.get("unit", "")) == unit
    ]
    filter_options = {
        _filters_key(item["filters"]): item
        for item in matching_series
    }
    filter_keys = sorted(filter_options)
    selected_filters_key = st.selectbox(
        "Coverage",
        filter_keys,
        format_func=lambda value: _filter_label(filter_options[value]["filters"]),
        key=f"nbr_{view}_filters_{source_version}",
    )
    entry = dict(filter_options[selected_filters_key])
    entry["source_data_version"] = source_version
    filters = dict(entry["filters"])
    selected_points = _series_points(
        points,
        page=page,
        metric=metric,
        geography_level=geography_level,
        filters=filters,
    )
    return entry, selected_points




def _render_nbr_national_page(
    points: Sequence[Mapping[str, Any]],
    summary: Mapping[str, Any],
    registry: Sequence[Mapping[str, Any]],
    source_version: str,
    source_page: str,
) -> None:
    with st.container(key="card_controls"):
        card_title(
            "National measure",
            "Choose a measure, who it covers, and the reporting date.",
        )
        entry, series = _page_series_selection(
            points,
            registry=registry,
            source_version=source_version,
            geography_level="national",
            view="national",
        )
        if entry is None:
            empty_state(
                f"No national series for {NBR_PAGE_LABELS.get(source_page, source_page).lower()}",
                "NBR has not provided a validated national measure here. "
                "Unavailable is not zero and is not a negative finding. Try the District explorer.",
            )
            return
        if not series:
            empty_state(
                "No observations for this selection",
                "Try another measure or coverage.",
            )
            return
        dates = sorted({str(point["reporting_date"]) for point in series})
        date_key = f"nbr_national_date_{source_version}"
        initial = st.session_state.get(date_key, dates[-1])
        if initial not in dates:
            initial = dates[-1]
        reporting_date = st.selectbox(
            "Reporting date",
            dates,
            index=dates.index(initial),
            key=date_key,
        )
    selected = next(
        (
            point for point in series
            if str(point["reporting_date"]) == reporting_date
        ),
        None,
    )
    if selected is None:
        empty_state(
            "No national observation on this date",
            "Pick another reporting date from the list above.",
        )
        return
    ordered = sorted(series, key=lambda point: str(point["reporting_date"]))
    unit = str(entry.get("unit") or "unit not specified")
    district_series = _series_points(
        points,
        page=source_page,
        metric=str(entry["metric_label"]),
        geography_level="district",
        filters=entry["filters"],
    )
    district_values = {
        str(point["geography"]): point
        for point in district_series
        if str(point["reporting_date"]) == reporting_date
        and str(point.get("unit") or "unit not specified") == unit
    }
    if district_values:
        from src.pages.district_explorer import (
            _clicked_district,
            build_map,
        )

        with st.container(key="card_nbr_national_map"):
            card_title(
                "District pattern",
                "Same measure, unit, coverage, and reporting date as the national value. Districts without data are left blank.",
            )
            try:
                geojson = data.load_geojson()
                centers, center = data.geo_summary(geojson)
            except (FileNotFoundError, ValueError, KeyError) as error:
                st.info("A district map is unavailable because boundary data could not be loaded.")
                st.caption(str(error))
            else:
                district_frame = pd.DataFrame([
                    {
                        "District": geography,
                        "Value": point["value"],
                        "Unit": point.get("unit") or unit,
                        "Source record ID": point.get("source_record_id", ""),
                        "Run ID": point.get("run_id", ""),
                    }
                    for geography, point in district_values.items()
                ])
                district_frame["rank"] = district_frame["Value"].rank(
                    ascending=False,
                    method="min",
                )
                district_frame["Valid respondents"] = None
                district_frame["diff"] = None
                settings = {
                    "basemap": "Light",
                    "palette": "Viridis",
                    "opacity": 0.9,
                    "spotlight": "Off",
                    "labels": False,
                    "tilt": 0,
                    "rotation": 0,
                    "zoom": 6.8,
                }
                map_figure = build_map(
                    district_frame,
                    geojson,
                    centers,
                    center,
                    {
                        "scale": [
                            [0, "#EAF6F3"],
                            [0.35, "#9FD3CB"],
                            [0.7, "#3AA597"],
                            [1, "#0E2A35"],
                        ],
                        "accent": PALETTE["blue"],
                    },
                    "Value",
                    None,
                    str(district_frame["District"].iloc[0]),
                    str(entry["metric_label"]),
                    settings,
                    value_unit=unit,
                )
                event = st.plotly_chart(
                    map_figure,
                    use_container_width=True,
                    key=f"nbr_national_map_{source_version}",
                    on_select="rerun",
                    selection_mode="points",
                    config={"scrollZoom": True, "displaylogo": False},
                )
                clicked = _clicked_district(event, list(district_values))
                if clicked:
                    st.caption(
                        f"{clicked}: "
                        f"{fmt_value(district_values[clicked]['value'])} {unit} "
                        f"on {reporting_date}."
                    )
    else:
        with st.container(key="card_nbr_national_map"):
            card_title("District pattern")
            empty_state(
                "No district map for this measure and date",
                "NBR did not report district observations with the selected measure, coverage, and date.",
            )
    chart_col, summary_col = st.columns([1.5, 1], gap="medium")
    with chart_col:
        with st.container(key="card_nbr_national_trend"):
            card_title(
                "National trend",
                "Reported dates only; gaps between reports are not interpolated.",
            )
            _render_trend(ordered, title=f"{entry['metric_label']} · {unit}")
    with summary_col:
        with st.container(key="card_nbr_national_context"):
            card_title("About this measure", "What it covers and how to read it")
            render_html(
                f'<div class="insp-note"><b>{esc(entry["metric_label"])}</b><br>'
                f'Unit: {esc(unit)}<br>Service: {esc(NBR_PAGE_LABELS.get(source_page, source_page))}<br>'
                f'Coverage: {esc(_filter_label(entry["filters"]))}<br>'
                f'Reporting date: {esc(reporting_date)}</div>'
            )
            mappings = entry.get("mappings", [])
            if mappings:
                for mapping in mappings:
                    st.warning(
                        f"{humanize(mapping['relationship'])}: {mapping['limitations']}"
                    )
            else:
                st.caption("No approved FinScope relationship is configured for this measure.")
    with st.container(key="card_nbr_national_table"):
        card_title("National observations", "Every reported value for this measure and coverage.")
        _render_observation_table(ordered)
    with st.expander("About the data"):
        st.caption(
            f"{summary.get('eligible_source_point_count', 0):,} NBR observations available "
            f"for {NBR_PAGE_LABELS.get(source_page, source_page).lower()}."
        )
        st.caption(f"Unit confirmation: {humanize(entry.get('unit_status')) or 'Unresolved'}.")


def _render_service_area_selector(view: str) -> str:
    source_pages = sorted(NBR_PAGE_LABELS)
    page_labels = [NBR_PAGE_LABELS[page] for page in source_pages]
    page_key = f"nbr_source_page_{view}"
    initial_page = _selected_service_area(view)
    with st.container(key="card_nbr_page_selector"):
        card_title(
            "Service area",
            "NBR reports administrative data by service. Pick one to explore.",
        )
        selected_label = st.selectbox(
            "Service area",
            page_labels,
            index=source_pages.index(initial_page),
            key=page_key,
            label_visibility="collapsed",
        )
    return source_pages[page_labels.index(selected_label)]


def _selected_service_area(view: str) -> str:
    source_pages = sorted(NBR_PAGE_LABELS)
    page_labels = [NBR_PAGE_LABELS[page] for page in source_pages]
    page_key = f"nbr_source_page_{view}"
    default_page = "inclusion" if view in {"national", "population"} else "branches"
    selected = st.session_state.get(page_key)
    if selected in source_pages:
        page = str(selected)
        st.session_state[page_key] = NBR_PAGE_LABELS[page]
        return page
    if selected in page_labels:
        return source_pages[page_labels.index(selected)]
    return default_page


def render_nbr_page(
    view: str,
    *,
    selected_district: str | None = None,
) -> None:
    """Render source-aware NBR views from one cached, page-scoped snapshot."""
    if view not in {"national", "district", "population", "priority"}:
        raise ValueError(f"Unknown NBR dashboard view: {view}")
    title = {
        "national": "NBR Financial Inclusion Overview",
        "district": "NBR District Insights",
        "population": "Population Group Insights",
        "priority": "Priority explorer",
    }[view]
    description = {
        "national": (
            "Explore Rwanda’s financial inclusion landscape through administrative "
            "data on transactional accounts and financial service infrastructure."
        ),
        "district": (
            "Explore NBR-reported service and customer measures for a selected district. "
            "Choose a service, filters, and reporting date; each value retains its source unit and scope."
        ),
        "population": (
            "NBR-reported financial-service activity across demographic groups."
        ),
        "priority": (
            "Explore NBR-reported district observations and decide what merits closer review."
        ),
    }[view]

    if view == "national":
        header_pages = tuple(
            spec["page"] for spec in NATIONAL_HEADER_KPIS
        )
        pages = tuple(sorted(set((*header_pages, "inclusion"))))
        try:
            points, summary, registry, source_version = load_nbr_dashboard_data(
                "nbr-dashboard-v2",
                pages,
            )
        except (RuntimeError, ValueError, OSError, PyMongoError) as error:
            page_header(
                title,
                description,
                pill="NBR Supply",
                pill_badge="BETA",
                size="tall",
                below_html=_national_supply_header_html([]),
            )
            st.markdown("")
            _render_nbr_data_highlights([])
            st.markdown("")
            _render_nbr_customer_counts_by_district([])
            with st.container(key="card_nbr_unavailable"):
                card_title("NBR data could not be loaded")
                st.error(
                    "NBR administrative observations are unavailable right now. "
                    "Use Refresh NBR observations in the sidebar to try again; "
                    "FinScope modes are unaffected."
                )
                st.caption(str(error))
            return

        page_header(
            title,
            description,
            pill="NBR Supply",
            pill_badge="BETA",
            size="tall",
            below_html=_national_supply_header_html(points),
        )
        st.markdown("")
        _render_nbr_data_highlights(
            points,
            summary.get("national_highlights"),
        )
        st.markdown("")
        render_nbr_savings_activity()
        st.markdown("")
        _render_nbr_infrastructure_by_district(points)
        st.markdown("")
        _render_nbr_customer_counts_by_district(
            points,
            summary.get("national_customer_unknown_counts"),
        )
        return

    if view == "district":
        source_page = _selected_service_area(view)
        try:
            points, summary, registry, source_version = load_nbr_dashboard_data(
                "nbr-dashboard-v2",
                (source_page,),
            )
        except (RuntimeError, ValueError, OSError, PyMongoError) as error:
            page_header(
                title,
                description,
                pill="NBR Supply",
                size="tall",
            )
            st.markdown(
                '<div style="height:2.5rem" aria-hidden="true"></div>',
                unsafe_allow_html=True,
            )
            with st.container(key="card_nbr_unavailable"):
                card_title("NBR data could not be loaded")
                st.error(
                    "NBR administrative observations are unavailable right now. "
                    "Use Refresh NBR observations in the sidebar to try again; "
                    "FinScope modes are unaffected."
                )
                st.caption(str(error))
            return

        eligible_points = _eligible_nbr_district_points(points)
        district_entries = [
            item for item in build_nbr_indicator_registry(eligible_points)
            if item.get("geography_level") == "district"
            and item.get("source_type") == "district_table"
        ]
        service_options = _nbr_district_service_options(district_entries)
        service_ids = list(service_options)
        service_key = "nbr_dx_service"
        selected_service = st.session_state.get(service_key)
        if selected_service not in service_options:
            selected_service = next(
                (
                    identifier for identifier, item in service_options.items()
                    if item["source_page"] == source_page
                ),
                service_ids[0] if service_ids else "",
            )
        if selected_service:
            st.session_state[service_key] = selected_service
            selected_series = service_options[selected_service]
            source_page = str(selected_series["source_page"])
            metric = str(selected_series["metric_label"])
            unit = str(selected_series.get("unit", ""))
            metric_key = f"nbr_district_metric_{source_version}"
            st.session_state[metric_key] = (
                f"{metric} · {unit or 'unit not specified'}"
            )
            matching_entries = [
                item for item in district_entries
                if item["source_page"] == source_page
                and item["metric_label"] == metric
                and str(item.get("unit", "")) == unit
            ]
            _, selected_entry = _resolve_observed_filter_combination(
                matching_entries,
                source_version,
                state_prefix=f"nbr_dx_filter_{selected_service}",
                button_dimensions=("Institution Type",),
            )
            st.session_state[f"nbr_district_filters_{source_version}"] = (
                _filters_key(selected_entry["filters"])
            )
        header_cards = _nbr_district_header_cards(
            points,
            registry,
            source_page=source_page,
            source_version=source_version,
            selected_district=selected_district,
        )
        page_header(
            title,
            description,
            pill="NBR Supply",
            pill_badge="BETA",
            size="tall",
            below_html=header_cards,
        )
        _render_nbr_district_explorer(
            points,
            source_version,
            source_page=source_page,
            selected_district=selected_district,
            district_entries=district_entries,
            service_options=service_options,
        )
        return

    if view == "population":
        source_page = _selected_service_area(view)
        try:
            points, summary, _, source_version = load_nbr_dashboard_data(
                "nbr-dashboard-v2",
                (source_page,),
            )
        except (RuntimeError, ValueError, OSError, PyMongoError) as error:
            page_header(
                title,
                description,
                pill="NBR Supply",
                pill_badge="BETA",
                size="tall",
                below_html=_population_group_header_html([]),
            )
            with st.container(key="card_nbr_unavailable"):
                card_title("NBR data could not be loaded")
                st.error(
                    "NBR administrative observations are unavailable right now. "
                    "Use Refresh NBR observations in the sidebar to try again; "
                    "FinScope modes are unaffected."
                )
                st.caption(str(error))
            return

        page_header(
            title,
            description,
            pill="NBR Supply",
            pill_badge="BETA",
            size="tall",
            below_html=_population_group_header_html(
                points,
                summary.get("national_customer_unknown_counts"),
            ),
        )
        st.markdown(
            '<div style="height:1.75rem" aria-hidden="true"></div>',
            unsafe_allow_html=True,
        )
        _render_population_context(
            points,
            source_version=source_version,
        )
        return

    if view == "priority":
        from src.pages.nbr_priority_explorer import render_nbr_priority_explorer

        def load_priority_catalog(
            page: str,
        ) -> tuple[
            Sequence[Mapping[str, Any]],
            str,
            Mapping[str, Any],
        ]:
            runs, source_version, metrics = load_nbr_page_catalog(
                "nbr-dashboard-v2",
                page,
            )
            return runs, source_version, metrics

        def load_priority_scope(
            page: str,
            scope_keys: tuple[tuple[str, str, str], ...],
        ) -> tuple[
            Sequence[Mapping[str, Any]],
            str,
            Mapping[str, Any],
        ]:
            points, summary, _, source_version = load_nbr_dashboard_data(
                "nbr-dashboard-v2",
                (page,),
                scope_keys,
            )
            return points, source_version, summary

        render_nbr_priority_explorer(
            load_priority_catalog,
            page_labels=NBR_PAGE_LABELS,
            load_scope_data=load_priority_scope,
            selected_district=selected_district,
        )
        return

    page_header(
        title,
        description,
        pill="NBR Supply",
        size="tall",
    )
    render_beta_notice()
    source_page = _render_service_area_selector(view)
    try:
        points, summary, registry, source_version = load_nbr_dashboard_data(
            "nbr-dashboard-v2",
            (source_page,),
        )
    except (RuntimeError, ValueError, OSError, PyMongoError) as error:
        with st.container(key="card_nbr_unavailable"):
            card_title("NBR data could not be loaded")
            st.error(
                "NBR administrative observations are unavailable right now. "
                "Use Refresh NBR observations in the sidebar to try again; FinScope modes are unaffected."
            )
            st.caption(str(error))
        return

    if view == "district":
        _render_nbr_district_page(
            points,
            summary,
            registry,
            source_version,
            source_page=source_page,
            selected_district=selected_district,
        )
        return

def _savings_activity_series(
    points: Sequence[Mapping[str, Any]],
    kpi_documents: Sequence[Mapping[str, Any]] = (),
) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for point in points:
        page = point.get("page")
        metric = point.get("metric_label")
        level = point.get("geography_level")
        if (
            page != "savings"
            or level != "national"
            or point.get("geography") != "Rwanda"
            or point.get("source_type") != "national_kpi"
            or metric not in {"Saved", "Total Customers"}
            or not isinstance(point.get("filters"), Mapping)
        ):
            continue
        expected_unit = "percent" if metric == "Saved" else "count"
        normalized_point = dict(point)
        if kpi_documents:
            filters_key = _filters_key(point["filters"])
            matching_documents = [
                document
                for document in kpi_documents
                if document.get("page") == "savings"
                and str(document.get("snapshot_date", ""))
                == str(point.get("reporting_date", ""))
                and document.get("combo_key") == point.get("combo_key")
                and document.get("run_id") == point.get("run_id")
                and _filters_key(document.get("filters", {})) == filters_key
            ]
            if len(matching_documents) != 1:
                continue
            matching_metrics = [
                item
                for item in matching_documents[0].get("kpis", [])
                if isinstance(item, Mapping)
                and item.get("metric_label") == metric
                and item.get("metric_type") in (None, "headline_kpi")
            ]
            if len(matching_metrics) != 1:
                continue
            source_metric = matching_metrics[0]
            raw_value = source_metric.get("metric_value")
            numeric_value = parse_numeric_value(
                source_metric.get("metric_value_numeric")
                if source_metric.get("metric_value_numeric") is not None
                else raw_value
            )
            if (
                numeric_value is None
                or float(numeric_value) != float(point.get("value", math.nan))
                or (
                    expected_unit == "percent"
                    and not (
                        isinstance(raw_value, str)
                        and raw_value.strip().endswith("%")
                    )
                )
                or (
                    expected_unit == "count"
                    and isinstance(raw_value, str)
                    and raw_value.strip().endswith("%")
                )
            ):
                continue
            normalized_point["unit"] = expected_unit
            normalized_point["unit_status"] = (
                "source_value" if expected_unit == "percent"
                else "configured_source_label"
            )
            normalized_point["raw_value"] = raw_value
        elif point.get("unit") != expected_unit:
            continue
        filters_key = _filters_key(point["filters"])
        entry = grouped.setdefault(
            filters_key,
            {
                "filters": dict(point["filters"]),
                "saved": defaultdict(list),
                "customers": defaultdict(list),
                "districts": defaultdict(list),
            },
        )
        metric_key = "saved" if metric == "Saved" else "customers"
        entry[metric_key][str(point.get("reporting_date", ""))].append(normalized_point)

    for point in points:
        if (
            point.get("page") != "savings"
            or point.get("metric_label") != "Customers"
            or point.get("geography_level") != "district"
            or point.get("source_type") != "district_table"
            or point.get("unit") != "count"
            or not isinstance(point.get("filters"), Mapping)
        ):
            continue
        entry = grouped.get(_filters_key(point["filters"]))
        if entry is not None:
            entry["districts"][str(point.get("reporting_date", ""))].append(dict(point))

    result = []
    for key, entry in sorted(grouped.items()):
        saved = entry["saved"]
        customers = entry["customers"]
        saved_dates = sorted(
            reporting_date
            for reporting_date, observations in saved.items()
            if len(observations) == 1
        )
        customer_dates = sorted(
            reporting_date
            for reporting_date, observations in customers.items()
            if len(observations) == 1
        )
        if not saved_dates or not customer_dates:
            continue
        entry["filters_key"] = key
        entry["saved_dates"] = saved_dates
        entry["customer_dates"] = customer_dates
        result.append(entry)
    return result


def _unknown_savings_customer(
    runs: Sequence[Mapping[str, Any]],
    table_documents: Sequence[Mapping[str, Any]],
    *,
    reporting_date: str,
    filters: Mapping[str, Any],
) -> tuple[int | float | None, str]:
    filters_key = _filters_key(filters)
    matching_runs = [
        run
        for run in runs
        if run.get("page") == "savings"
        and str(run.get("snapshot_date", "")) == reporting_date
        and run.get("combo_key") == filters_key
        and run.get("filters") == dict(filters)
        and (
            not isinstance(run.get("filters_requested"), Mapping)
            or run.get("filters_requested") == dict(filters)
        )
        and run.get("status") == "complete"
        and run.get("table_status") == "extracted"
        and run.get("repeated_snapshot_warning") is not True
    ]
    if len(matching_runs) != 1:
        return None, "unavailable"
    run = matching_runs[0]
    unknown_rows = [
        row
        for row in table_documents
        if row.get("page") == "savings"
        and str(row.get("snapshot_date", "")) == reporting_date
        and row.get("combo_key") == filters_key
        and row.get("run_id") == run.get("run_id")
        and row.get("filters") == dict(filters)
        and (
            not isinstance(row.get("filters_requested"), Mapping)
            or row.get("filters_requested") == dict(filters)
        )
        and row.get("district_known") is False
        and str(row.get("district", "")).strip().casefold() == "unknown"
    ]
    if not unknown_rows:
        return None, "not_reported"
    if len(unknown_rows) != 1:
        return None, "unavailable"
    values = unknown_rows[0].get("values")
    raw_value = values.get("Customers") if isinstance(values, Mapping) else None
    value = parse_numeric_value(raw_value)
    if (
        value is None
        or value < 0
        or not float(value).is_integer()
        or (isinstance(raw_value, str) and raw_value.strip().endswith("%"))
    ):
        return None, "unavailable"
    return value, "reported"


def _savings_trend_figure(
    observations: Sequence[Mapping[str, Any]],
    *,
    metric_label: str,
    unit: str,
) -> go.Figure:
    ordered = sorted(observations, key=lambda point: str(point["reporting_date"]))
    values = [float(point["value"]) for point in ordered]
    dates = [str(point["reporting_date"]) for point in ordered]
    if unit == "percent":
        fig = go.Figure(
            go.Scatter(
                x=dates,
                y=values,
                mode="lines+markers",
                line=dict(color="#087E78", width=4, shape="linear"),
                marker=dict(
                    size=12,
                    color="#F2B84B",
                    line=dict(color="#FFFFFF", width=2.5),
                ),
                fill="tozeroy",
                fillcolor="rgba(8,126,120,0.13)",
                connectgaps=False,
                hovertemplate=(
                    f"<b>{esc(metric_label)}</b><br>%{{x}}<br>%{{y:.1f}}%"
                    "<extra></extra>"
                ),
            )
        )
        fig.update_xaxes(
            type="category",
            categoryorder="array",
            categoryarray=dates,
            title=None,
            showgrid=False,
            automargin=True,
        )
        fig.update_yaxes(
            title="Source-reported percent",
            ticksuffix="%",
            tickformat=".1f",
            rangemode="tozero",
            gridcolor="#D8E6E5",
            zeroline=False,
        )
        return style_chart(
            fig,
            430,
            paper_bgcolor="#FFFFFF",
            plot_bgcolor="#F1F8F7",
            font=dict(family="Plus Jakarta Sans, Segoe UI, Arial, sans-serif", color="#163D4B", size=13),
            margin=dict(l=64, r=28, t=38, b=52),
            hoverlabel=dict(bgcolor="#0E2A35", bordercolor="#0E2A35", font=dict(color="#FFFFFF", size=13)),
        )

    fig = go.Figure(
        go.Bar(
            x=dates,
            y=values,
            marker=dict(
                color="#3267A8",
                line=dict(color="#234B7A", width=1),
                cornerradius=5,
            ),
            text=[fmt_value(value) for value in values],
            textposition="outside",
            textfont=dict(size=12, color="#163D4B"),
            cliponaxis=False,
            hovertemplate=(
                f"<b>{esc(metric_label)}</b><br>%{{x}}<br>%{{y:,.0f}} customers"
                "<extra></extra>"
            ),
        )
    )
    fig.update_layout(bargap=0.48)
    fig.update_xaxes(
        type="category",
        categoryorder="array",
        categoryarray=dates,
        title=None,
        showgrid=False,
        automargin=True,
    )
    fig.update_yaxes(
        title="Customers",
        tickformat=",.0f",
        rangemode="tozero",
        gridcolor="#DEE7F1",
        zeroline=False,
    )
    return style_chart(
        fig,
        380,
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#F3F6FB",
        font=dict(family="Plus Jakarta Sans, Segoe UI, Arial, sans-serif", color="#163D4B", size=13),
        margin=dict(l=72, r=32, t=44, b=52),
        hoverlabel=dict(bgcolor="#0E2A35", bordercolor="#0E2A35", font=dict(color="#FFFFFF", size=13)),
    )


def _resolve_observed_filter_combination(
    series: Sequence[Mapping[str, Any]],
    source_version: str,
    *,
    state_prefix: str,
    button_dimensions: Sequence[str] | None = None,
) -> tuple[dict[str, str], Mapping[str, Any]]:
    dimensions = sorted({
        str(key)
        for entry in series
        for key in entry["filters"]
    })
    interactive_dimensions = set(
        dimensions if button_dimensions is None else button_dimensions
    )
    selected_filters: dict[str, str] = {}
    for dimension in dimensions:
        candidates = [
            entry
            for entry in series
            if all(
                str(entry["filters"].get(key, "")) == value
                for key, value in selected_filters.items()
            )
        ]
        options = sorted({
            str(entry["filters"][dimension])
            for entry in candidates
            if dimension in entry["filters"]
        })
        if not options:
            continue
        if dimension in interactive_dimensions:
            state_key = (
                f"{state_prefix}_{hashlib.sha1(dimension.encode()).hexdigest()[:8]}_"
                f"{source_version}"
            )
            selected = st.session_state.get(state_key)
            if selected not in options:
                selected = "All" if "All" in options else options[0]
        else:
            selected = "All" if "All" in options else options[0]
        selected_filters[dimension] = selected
    matching = [
        entry
        for entry in series
        if all(
            str(entry["filters"].get(key, "")) == value
            for key, value in selected_filters.items()
        )
    ]
    if not matching:
        raise ValueError("Selected filters do not match an observed NBR series.")
    return selected_filters, matching[0]


def _select_observed_filter_combination(
    series: Sequence[Mapping[str, Any]],
    source_version: str,
    *,
    state_prefix: str,
    button_dimensions: Sequence[str] | None = None,
    full_width: bool = False,
) -> Mapping[str, Any]:
    dimensions = sorted({
        str(key)
        for entry in series
        for key in entry["filters"]
    })
    interactive_dimensions = set(
        dimensions if button_dimensions is None else button_dimensions
    )
    selected_filters: dict[str, str] = {}
    controls = [st.container()] if full_width else st.columns(3, gap="small")
    control_index = 0
    for dimension in dimensions:
        candidates = [
            entry
            for entry in series
            if all(
                str(entry["filters"].get(key, "")) == value
                for key, value in selected_filters.items()
            )
        ]
        options = sorted({
            str(entry["filters"][dimension])
            for entry in candidates
            if dimension in entry["filters"]
        })
        if not options:
            continue
        if dimension in interactive_dimensions:
            state_key = (
                f"{state_prefix}_{hashlib.sha1(dimension.encode()).hexdigest()[:8]}_"
                f"{source_version}"
            )
            selected = st.session_state.get(state_key)
            if selected not in options:
                selected = "All" if "All" in options else options[0]
            if (
                state_key in st.session_state
                and st.session_state[state_key] not in options
            ):
                st.session_state[state_key] = selected
            with controls[control_index % len(controls)]:
                choice = st.segmented_control(
                    dimension,
                    options=options,
                    default=selected,
                    selection_mode="single",
                    key=state_key,
                    width="stretch" if full_width else "content",
                )
            control_index += 1
            selected = choice if choice in options else selected
        else:
            selected = "All" if "All" in options else options[0]
        selected_filters[dimension] = selected

    matching = [
        entry
        for entry in series
        if all(
            str(entry["filters"].get(key, "")) == value
            for key, value in selected_filters.items()
        )
    ]
    if not matching:
        raise ValueError("Selected filters do not match an observed NBR series.")
    return matching[0]


def _select_savings_coverage(
    series: Sequence[Mapping[str, Any]],
    source_version: str,
) -> Mapping[str, Any]:
    interactive_dimensions = {
        str(key)
        for entry in series
        for key in entry["filters"]
    } - {"Account Type", "Account Status", "Location"}
    return _select_observed_filter_combination(
        series,
        source_version,
        state_prefix="nbr_savings_filter",
        button_dimensions=tuple(sorted(interactive_dimensions)),
    )


def _savings_district_figure(
    observations: Sequence[Mapping[str, Any]],
) -> go.Figure:
    ordered = sorted(
        observations,
        key=lambda point: (
            str(point.get("geography", "")).casefold() == "unknown",
            -float(point["value"]),
            str(point.get("geography", "")).casefold(),
        ),
    )
    labels = [str(point["geography"]) for point in ordered]
    values = [float(point["value"]) for point in ordered]
    named_count = sum(label.casefold() != "unknown" for label in labels)
    palette = [
        "#0E2A35",
        "#164A55",
        "#1C6970",
        "#258B88",
        "#48A99A",
    ]
    colors = []
    for label in labels:
        if label.casefold() == "unknown":
            colors.append("#D79A2B")
            continue
        rank = len(colors)
        color_index = min(
            round(rank / max(named_count - 1, 1) * (len(palette) - 1)),
            len(palette) - 1,
        )
        colors.append(palette[color_index])
    fig = go.Figure(
        go.Bar(
            x=values,
            y=labels,
            orientation="h",
            marker=dict(color=colors),
            text=[fmt_value(value) for value in values],
            textposition="outside",
            textfont=dict(size=11, color="#163D4B"),
            cliponaxis=False,
            hovertemplate="<b>%{y}</b><br>%{x:,.0f} customers<extra></extra>",
        )
    )
    fig.update_layout(
        showlegend=False,
        bargap=0.24,
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#F7F8F5",
        font=dict(family="Plus Jakarta Sans, Segoe UI, Arial, sans-serif", color="#163D4B", size=12),
    )
    fig.update_xaxes(
        title="Recorded customers",
        rangemode="tozero",
        range=[0, max(values, default=0) * 1.16 or 1],
        tickformat=",.0f",
        gridcolor="#E2E7DF",
        zeroline=False,
    )
    fig.update_yaxes(title=None, autorange="reversed", showgrid=False, automargin=True)
    return style_chart(
        fig,
        max(560, 20 * len(labels) + 120),
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#F7F8F5",
        font=dict(family="Plus Jakarta Sans, Segoe UI, Arial, sans-serif", color="#163D4B", size=12),
        margin=dict(l=12, r=84, t=24, b=42),
        hoverlabel=dict(bgcolor="#0E2A35", bordercolor="#0E2A35", font=dict(color="#FFFFFF", size=12)),
    )


def render_nbr_savings_activity() -> None:
    """Render the NBR-only savings-service section on National Overview."""
    section_title(
        "Recorded Savings-Service Activity",
        "NBR administrative observations only; separate KPI trends and district customer counts.",
    )
    try:
        points, _, _, source_version = load_nbr_dashboard_data(
            "nbr-dashboard-v2",
            ("savings",),
        )
        runs, kpi_documents, table_documents, _ = _load_nbr_source_documents(
            "nbr-dashboard-v2",
            ("savings",),
        )
    except (RuntimeError, ValueError, OSError, PyMongoError) as error:
        with st.container(key="card_nbr_savings_unavailable"):
            card_title("Savings-service observations unavailable")
            st.error(
                "NBR savings-service observations could not be loaded. "
                "Unavailable data is not zero."
            )
            st.caption(str(error))
        return

    series = _savings_activity_series(points, kpi_documents)
    if not series:
        empty_state(
            "No comparable savings-service history",
            "NBR has not provided validated Saved and Total Customers observations "
            "with matching filters and reporting dates.",
        )
        return

    entry = _select_savings_coverage(series, source_version)
    saved_observations = [entry["saved"][date][0] for date in entry["saved_dates"]]
    customer_observations = [
        entry["customers"][date][0] for date in entry["customer_dates"]
    ]

    with st.container(key="card_nbr_savings_saved_trend"):
        card_title(
            "Saved · reported percentage",
            "Primary trend · actual NBR reporting dates only · no interpolation.",
        )
        st.plotly_chart(
            _savings_trend_figure(
                saved_observations,
                metric_label="Saved",
                unit="percent",
            ),
            use_container_width=True,
            key=f"nbr_savings_saved_{source_version}",
            config={"displayModeBar": False},
        )

    with st.container(key="card_nbr_savings_total_customers"):
        card_title(
            "Total Customers · reported count",
            "A separate count series on its own scale; not a population denominator.",
        )
        st.plotly_chart(
            _savings_trend_figure(
                customer_observations,
                metric_label="Total Customers",
                unit="count",
            ),
            use_container_width=True,
            key=f"nbr_savings_customers_{source_version}",
            config={"displayModeBar": False},
        )

    district_dates_with_rows = sorted(
        reporting_date
        for reporting_date, rows in entry["districts"].items()
        if rows
    )
    district_options: list[tuple[str, str]] = []
    for reporting_date in district_dates_with_rows:
        rows = entry["districts"][reporting_date]
        district_names = [str(point.get("geography", "")) for point in rows]
        if len(set(district_names)) != len(district_names) or not district_names:
            continue
        district_options.append((reporting_date, reporting_date))
    with st.container(key="card_nbr_savings_districts"):
        card_title(
            "District distribution · recorded customers",
            "Customer counts by district for one eligible NBR snapshot.",
        )
        if not district_options:
            empty_state(
                "No eligible district snapshot",
                "No matching district Customer rows are available for the selected coverage and paired dates.",
            )
        else:
            district_dates = [option[0] for option in district_options]
            date_key = f"nbr_savings_district_date_{source_version}"
            selected_date = st.session_state.get(date_key, district_dates[-1])
            if selected_date not in district_dates:
                selected_date = district_dates[-1]
            reporting_date = st.selectbox(
                "District snapshot reporting date",
                district_dates,
                index=district_dates.index(selected_date),
                key=date_key,
            )
            st.caption(
                f"Snapshot: {_display_reporting_date(reporting_date)} · "
                "Only locations reported by NBR are plotted."
            )
            rows = [
                dict(point)
                for point in entry["districts"][reporting_date]
            ]
            unknown_value, unknown_status = _unknown_savings_customer(
                runs,
                table_documents,
                reporting_date=reporting_date,
                filters=entry["filters"],
            )
            if unknown_status == "reported":
                rows.append({
                    "geography": "Unknown",
                    "value": unknown_value,
                })
            st.plotly_chart(
                _savings_district_figure(rows),
                use_container_width=True,
                key=f"nbr_savings_district_chart_{source_version}",
                config={"displayModeBar": False},
            )
            if unknown_status == "reported":
                st.caption(
                    "“Unknown” is a count reported by NBR without an assigned district."
                )
            elif unknown_status == "not_reported":
                st.caption(
                    "NBR did not report a separate count for customers with an unknown district."
                )
            else:
                st.caption(
                    "An unknown-district count could not be verified, so it is not shown."
                )
            st.caption(
                "Only districts with reported counts are shown; an unlisted district "
                "does not mean its count is zero."
            )

def render_methodology_mode_note() -> None:
    if current_mode() == "NBR Supply":
        render_beta_notice()
        note(
            "Reading NBR administrative evidence",
            "NBR observations describe recorded administrative metrics. They are distinct from "
            "FinScope survey estimates and do not establish population ownership, service access, "
            "causality, or a change in financial inclusion.",
            tone="info",
        )
    elif current_mode() == "Combined":
        note(
            "Two evidence sources, kept separate",
            "FinScope values are weighted survey estimates. NBR values are administrative "
            "observations with their own units and filters; neither source is used to calculate "
            "or validate the other.",
            tone="info",
        )
