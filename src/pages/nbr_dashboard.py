"""Shared mode selection and data-driven NBR dashboard components."""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from datetime import date
from typing import Any, Mapping, Sequence

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from pymongo.errors import PyMongoError

from src import data
from src.models.nbr_intelligence.contextualization import (
    _filters_match,
    prepare_source_points,
)
from src.models.nbr_intelligence.experiment import (
    build_experiment_report,
    load_mongodb_history,
)
from src.models.nbr_intelligence.indicator_mapping import MAPPING_BY_VARIABLE
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
_DIMENSIONS = {
    "Gender": "Gender",
    "Age Segment": "Age Segment (NBR Youth/Non-Youth)",
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
            load_nbr_review_candidates.clear()
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
    unit = str(entry.get("unit") or "").strip()
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
) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]], str]:
    """Cache one normalized source snapshot, registry, and provenance digest."""
    runs, kpis, tables = _load_nbr_source_documents(model_version, pages)
    points, summary = prepare_source_points(
        runs,
        kpis,
        tables,
        as_of_date=date.today(),
    )
    registry = build_nbr_indicator_registry(points)
    return points, summary, registry, _source_data_version(points)


@st.cache_data(ttl=900, show_spinner="Preparing experimental review candidates...")
def load_nbr_review_candidates(
    model_version: str,
    pages: tuple[str, ...],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Run existing read-only anomaly detectors for the priority review surface."""
    runs, kpis, tables = _load_nbr_source_documents(model_version, pages)
    from src.data_sources.mongodb_district_explorer import load_district_reference

    report = build_experiment_report(
        runs,
        tables,
        kpis,
        expected_districts=tuple(load_district_reference()),
    )
    experiment = report["experiment"]
    candidates = []
    for method, queue in report["ranked_review_queues"]["methods"].items():
        for candidate in queue["candidates"]:
            candidates.append({"method": method, **candidate})
    return candidates, {
        "assessment_id": experiment["assessment_id"],
        "assessment_timestamp": experiment["assessment_timestamp"],
        "model_version": experiment["model_version"],
        "source_git_commit": experiment.get("source_git_commit"),
        "pages": list(pages),
    }


@st.cache_data(ttl=900, show_spinner="Reading NBR source records...")
def _load_nbr_source_documents(
    model_version: str,
    pages: tuple[str, ...] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Cache a read-only source snapshot, optionally scoped to selected pages."""
    del model_version  # Version is part of the cache key for safe invalidation.
    return load_mongodb_history(pages=pages)


def _filters_key(filters: Mapping[str, Any]) -> str:
    return json.dumps(filters, sort_keys=True, ensure_ascii=False, default=str)


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


def select_review_candidates(
    candidates: Sequence[Mapping[str, Any]],
    *,
    page: str,
    metric: str,
    district: str,
    filters: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Keep only anomaly candidates matching the selected administrative series."""
    filters_key = _filters_key(filters)
    return [
        dict(candidate)
        for candidate in candidates
        if candidate.get("page") == page
        and candidate.get("metric_label") == metric
        and candidate.get("district") == district
        and _filters_key(candidate.get("filters", {})) == filters_key
    ]


def _review_candidate_row(
    candidate: Mapping[str, Any],
    *,
    unit: str,
    source_record_id: str,
) -> dict[str, Any]:
    evidence = candidate.get("evidence_assessment", {})
    evidence_state = (
        evidence.get("state", "unclassified")
        if isinstance(evidence, Mapping)
        else "unclassified"
    )
    return {
        "Method": candidate.get("method", ""),
        "Method rank": candidate.get("method_specific_rank"),
        "Reporting date": candidate.get("reporting_date", ""),
        "Observed value": candidate.get("observed_value"),
        "Unit": unit,
        "Direction": candidate.get("direction", ""),
        "Evidence state": evidence_state,
        "Run ID": candidate.get("run_id", ""),
        "Source record ID": source_record_id,
        "Reason": candidate.get("reason", ""),
    }


def _render_trend(
    points: Sequence[Mapping[str, Any]],
    *,
    title: str,
    compact: bool = False,
    key_suffix: str | None = None,
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
        mode="lines+markers+text",
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
    if subgroup_type and subgroup_type not in {"Gender"}:
        return []
    mapping = MAPPING_BY_VARIABLE.get(indicator_variable)
    if not mapping:
        return []
    entries: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for relationship in mapping["nbr_relationships"]:
        if (
            relationship["relationship"] == "unsuitable"
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
            # NBR Youth/Non-Youth is deliberately not crosswalked to FinScope age bins.
            continue
        for point in points:
            filters = point.get("filters")
            if (
                point.get("page") != relationship["page"]
                or point.get("metric_label") not in labels
                or point.get("geography_level") != geography_level
                or not isinstance(filters, Mapping)
                or not _filters_match(filters, expected_filters)
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
        if item["relationship"] == "contextual_indicator"
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
        relationships={"contextual_indicator"},
    )
    return entries, source_version


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


def _render_nbr_district_page(
    points: Sequence[Mapping[str, Any]],
    summary: Mapping[str, Any],
    registry: Sequence[Mapping[str, Any]],
    source_version: str,
    *,
    source_page: str,
    selected_district: str | None,
    priority_view: bool = False,
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
    delta = (
        float(selected_point["value"]) - float(previous["value"])
        if previous is not None else None
    )
    value = float(selected_point["value"])
    low, high = float(ranked["Value"].min()), float(ranked["Value"].max())
    value_fill = ((value - low) / (high - low) * 100) if high > low else 50
    if priority_view:
        geojson, centers, center = None, {}, (None, None)
        mapped_district_count = len(ranked)
        map_error = None
    else:
        try:
            geojson = data.load_geojson()
            centers, center = data.geo_summary(geojson)
            mapped_district_count = len(geojson["features"])
            map_error = None
        except (FileNotFoundError, ValueError, KeyError) as error:
            geojson, centers, center = None, {}, (None, None)
            mapped_district_count = len(ranked)
            map_error = error
    change_html = (
        fmt_delta(delta) if delta is not None else "Unavailable"
    )
    cards = [
        kpi_card(
            "Selected district value",
            f"{fmt_value(value)}",
            f" {unit or 'unit not specified'}",
            value_fill,
            PALETTE["teal"],
            f"<b>{esc(selected_district)}</b> · {esc(reporting_date)}"
            + kpi_trend_html(selected_history),
        ),
        kpi_card(
            "Change from prior observation",
            change_html,
            f" {unit or 'unit not specified'}",
            min(100, abs(delta or 0) / max(abs(value), 1) * 100),
            PALETTE["blue"] if (delta or 0) >= 0 else PALETTE["coral"],
            (
                f"Previous date: {esc(previous['reporting_date'])}"
                if previous is not None
                else "No earlier observation in this exact series"
            ),
        ),
        kpi_card(
            "Observed district position",
            f"#{int(rank_row['Rank'])}",
            f" of {len(ranked)}",
            (len(ranked) - int(rank_row["Rank"]) + 1) / max(len(ranked), 1) * 100,
            PALETTE["sun"],
            "Descriptive ranking for this measure and date",
        ),
        kpi_card(
            "Districts with data",
            f"{len(ranked)}",
            "" if priority_view else f" / {mapped_district_count}",
            len(ranked) / max(mapped_district_count, 1) * 100,
            PALETTE["ink2"],
            (
                "Districts in this selected comparison"
                if priority_view
                else (
                    "Out of all Rwandan districts"
                    if map_error is None
                    else "Map boundaries unavailable"
                )
            ),
        ),
    ]
    render_html(kpi_grid(cards))
    note(
        "Administrative evidence only",
        "Values and rankings describe the selected NBR metric and exact source filters. "
        "They do not measure household ownership, population access, or a change in financial inclusion.",
        tone="info",
    )
    if priority_view:
        with st.container(key="card_nbr_priority_comparison"):
            card_title(
                "Observed values by district",
                f"{metric} on {reporting_date} · {unit or 'unit not specified'} · "
                "descriptive comparison only; no priority score is calculated.",
            )
            comparison = ranked.sort_values("Value", ascending=True)
            figure = go.Figure(go.Bar(
                x=comparison["Value"],
                y=comparison["District"],
                orientation="h",
                marker=dict(color=PALETTE["teal"]),
                text=comparison["Value"],
                texttemplate="%{text:,.4g}",
                textposition="outside",
                cliponaxis=False,
                hovertemplate=(
                    "<b>%{y}</b><br>%{x:,.4g} "
                    f"{esc(unit or 'unit not specified')}<extra></extra>"
                ),
            ))
            figure.update_xaxes(
                title=f"{metric} · {unit or 'unit not specified'}",
                gridcolor=PALETTE["grid"],
                zeroline=False,
            )
            figure.update_yaxes(title=None, showgrid=False, automargin=True)
            st.plotly_chart(
                style_chart(figure, max(320, min(600, len(comparison) * 28 + 80))),
                use_container_width=True,
                key="nbr_priority_observed_values",
                config={"displayModeBar": False},
            )
    else:
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
    if not priority_view:
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
    if priority_view:
        _render_priority_review_panel(
            points,
            entry=entry,
            district=selected_district,
            selected_series=selected_history,
            source_version=source_version,
        )


def _render_priority_review_panel(
    points: Sequence[Mapping[str, Any]],
    *,
    entry: Mapping[str, Any],
    district: str,
    selected_series: Sequence[Mapping[str, Any]],
    source_version: str,
) -> None:
    with st.expander("Experimental anomaly review candidates"):
        note(
            "Human review required",
            "Candidates are method-specific anomaly signals, not confirmed changes in financial inclusion "
            "or a ranking of policy need. Source data remain read-only.",
            tone="warn",
        )
        if not st.button(
            "Load review candidates for this source snapshot",
            key=f"load_nbr_review_{source_version}_{district}",
            icon=":material/search:",
        ):
            st.caption("Detailed detector evaluation runs only when requested.")
            return
        try:
            candidates, assessment = load_nbr_review_candidates(
                source_version,
                (str(entry["source_page"]),),
            )
        except (RuntimeError, ValueError, OSError, PyMongoError, KeyError) as error:
            st.error("Experimental review candidates could not be prepared.")
            st.caption(str(error))
            return
        scoped_candidates = select_review_candidates(
            candidates,
            page=str(entry["source_page"]),
            metric=str(entry["metric_label"]),
            district=district,
            filters=entry["filters"],
        )
        st.caption(
            f"Assessed {assessment['assessment_timestamp']} · "
            f"{len(scoped_candidates)} candidate{'s' if len(scoped_candidates) != 1 else ''} "
            "for this measure and district."
        )
        if not scoped_candidates:
            empty_state(
                "No review candidates for this measure",
                "That does not establish that the series is normal or free of data-quality issues.",
            )
            return
        source_by_identity = {
            (
                str(point["reporting_date"]),
                str(point.get("run_id", "")),
                str(point["value"]),
            ): point
            for point in selected_series
        }
        rows = []
        for candidate in scoped_candidates:
            source_point = source_by_identity.get((
                str(candidate.get("reporting_date", "")),
                str(candidate.get("run_id", "")),
                str(candidate.get("observed_value", "")),
            ), {})
            rows.append(_review_candidate_row(
                candidate,
                unit=str(entry.get("unit") or "unit not specified"),
                source_record_id=str(source_point.get("source_record_id", "")),
            ))
        review_table = (
            pd.DataFrame(rows)
            .drop(columns=["Run ID", "Source record ID"], errors="ignore")
            .rename(columns={"Method rank": "Rank in method"})
        )
        review_table["Method"] = review_table["Method"].map(humanize)
        review_table["Evidence state"] = review_table["Evidence state"].map(humanize)
        st.dataframe(review_table, hide_index=True, use_container_width=True)
        st.markdown("**Evidence behind each candidate**")
        for candidate in scoped_candidates:
            st.markdown(
                f"**{humanize(candidate['method'])} · {candidate.get('reporting_date', '')}** — "
                f"{candidate.get('reason', 'No reason recorded')}"
            )
            evidence = candidate.get("evidence_assessment", {})
            state = evidence.get("state") if isinstance(evidence, Mapping) else None
            qualifications = candidate.get("quality_qualifications", []) or []
            facts = [
                f"Evidence: {humanize(state)}" if state else "",
                f"Score {candidate['score']:,.4g}" if isinstance(candidate.get("score"), (int, float)) else "",
                f"Threshold {candidate['threshold']:,.4g}" if isinstance(candidate.get("threshold"), (int, float)) else "",
            ]
            st.caption(" · ".join(fact for fact in facts if fact) or "No score recorded.")
            for item in qualifications:
                st.markdown(f"- {esc(item) if isinstance(item, str) else esc(json.dumps(item, default=str))}")
            with st.popover("Full detector output"):
                st.json({
                    "evidence_assessment": evidence,
                    "quality_qualifications": qualifications,
                    "score": candidate.get("score"),
                    "threshold": candidate.get("threshold"),
                })


def _render_combined_context(
    points: Sequence[Mapping[str, Any]],
    *,
    indicator_variable: str,
    district: str | None = None,
    subgroup_type: str = "",
    subgroup: str = "",
    source_version: str | None = None,
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
        relationships={"contextual_indicator"},
    )
    if not entries:
        return
    with st.expander(
        f"NBR supply context · "
        f"{MAPPING_BY_VARIABLE[indicator_variable]['original_indicator_label']}",
        expanded=False,
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
        st.caption(
            f"{entry['metric_label']}{geography_label}: "
            f"{fmt_value(latest['value'])} {entry.get('unit') or 'unit not specified'} "
            f"on {latest_date}. Administrative context only; it does not change "
            "the FinScope estimate."
            if latest else
            f"Observed source dates: {len(dates)} · latest reporting date {latest_date}."
        )
        st.warning(entry["limitations"])
        _render_trend(
            series_points,
            title=f"{entry['metric_label']} · {entry.get('unit') or 'unit not specified'}",
            compact=True,
            key_suffix=(
                f"{indicator_variable}_{district or 'national'}_"
                f"{subgroup_type}_{subgroup}_{source_version}"
            ),
        )
        with st.popover("View observations", icon=":material/table:"):
            _render_observation_table(series_points)


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
    with st.container(key="card_nbr_population_comparison"):
        card_title(
            "Gender and age segments in NBR data",
            "Only categories NBR reports are shown. Age segment is Youth/Non-Youth, not FinScope age bands.",
        )
        dimensions = [
            dimension for dimension in _DIMENSIONS
            if _group_families(points, dimension)
        ]
        if not dimensions:
            empty_state(
                "No comparable NBR breakdown",
                "NBR does not report education or urban/rural breakdowns, and its Youth/Non-Youth "
                "split does not match FinScope age bands. Use FinScope mode for those comparisons.",
            )
            return
        dimension = st.selectbox(
            "Observed NBR dimension",
            dimensions,
            format_func=lambda value: _DIMENSIONS[value],
            key=f"nbr_population_dimension_{source_version}",
        )
        families = _group_families(points, dimension)
        labels = [
            f"{NBR_PAGE_LABELS.get(str(item['page']), item['page'])} · "
            f"{item['metric_label']} · {item['geography_level']} "
            f"{item['geography']} · {item.get('unit') or 'unit not specified'} · "
            f"{_filter_label(item['base_filters'])}"
            for item in families
        ]
        selected = st.selectbox(
            "NBR metric and exact filter scope",
            range(len(families)),
            format_func=lambda index: labels[index],
            key=f"nbr_population_family_{source_version}",
        )
        family = families[selected]
        date_options = sorted({
            str(point["reporting_date"])
            for group_points in family["groups"].values()
            for point in group_points
        })
        reporting_date = st.selectbox(
            "NBR reporting date",
            date_options,
            index=len(date_options) - 1,
            key=f"nbr_population_date_{source_version}",
        )
        rows = []
        for group, group_points in sorted(family["groups"].items()):
            match = [
                point for point in group_points
                if str(point["reporting_date"]) == reporting_date
            ]
            for point in match:
                rows.append({
                    "Observed category": group,
                    "Metric": family["metric_label"],
                    "Value": point["value"],
                    "Unit": point.get("unit") or "Not specified",
                    "Reporting date": point["reporting_date"],
                    "Geography": point.get("geography", ""),
                    "Filters": _filter_label(point.get("filters", {})),
                    "Source": NBR_PAGE_LABELS.get(str(point.get("page", "")), point.get("page", "")),
                })
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            empty_state("No observations on this date", "Pick another NBR reporting date.")
        category_figure = go.Figure()
        for group, group_points in sorted(family["groups"].items()):
            ordered = sorted(
                group_points,
                key=lambda point: str(point["reporting_date"]),
            )
            category_figure.add_trace(go.Scatter(
                x=[point["reporting_date"] for point in ordered],
                y=[point["value"] for point in ordered],
                name=group,
                mode="lines+markers",
                connectgaps=False,
                hovertemplate=(
                    "<b>%{x}</b><br>%{y:,.7~r} "
                    + esc(family.get("unit") or "unit not specified")
                    + "<extra>%{fullData.name}</extra>"
                ),
            ))
        category_figure.update_xaxes(title="NBR reporting date", showgrid=False)
        category_figure.update_yaxes(
            title=f"{family['metric_label']} · {family.get('unit') or 'unit not specified'}",
            gridcolor=PALETTE["grid"],
            rangemode="tozero",
        )
        category_figure.update_layout(barmode="group")
        st.plotly_chart(
            style_chart(category_figure, 310),
            use_container_width=True,
            config={"displayModeBar": False},
            key=f"nbr_population_trends_{source_version}",
        )
        st.caption(
            "Categories are reported separately using the NBR source definitions. "
            "No FinScope age crosswalk, combined score, or inclusion-rate calculation is applied."
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
    default_page = "inclusion" if view in {"national", "population"} else "branches"
    initial_page = st.session_state.get(page_key, default_page)
    if initial_page not in source_pages:
        initial_page = default_page
        st.session_state[page_key] = initial_page
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
        "district": "District explorer",
        "population": "Population groups",
        "priority": "Priority explorer",
    }[view]
    description = {
        "national": (
            "Explore Rwanda’s financial inclusion landscape through administrative "
            "data on transactional accounts and financial service infrastructure."
        ),
        "district": "Explore district-level measures using the reporting scope and units provided by NBR.",
        "population": "Compare only demographic breakdowns reported for the selected NBR measure.",
        "priority": "Review observed district measures; no FinScope-derived priority score is applied.",
    }[view]

    if view == "national":
        page_key = "nbr_source_page_national"
        source_page = st.session_state.get(page_key, "inclusion")
        if source_page not in NBR_PAGE_LABELS:
            source_page = "inclusion"
        header_pages = tuple(
            spec["page"] for spec in NATIONAL_HEADER_KPIS
        )
        pages = tuple(sorted(set((*header_pages, source_page))))
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
            _render_service_area_selector(view)
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
        source_page = _render_service_area_selector(view)
        _render_nbr_national_page(
            points,
            summary,
            registry,
            source_version,
            source_page,
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

    if view in {"district", "priority"}:
        _render_nbr_district_page(
            points,
            summary,
            registry,
            source_version,
            source_page=source_page,
            selected_district=selected_district,
            priority_view=view == "priority",
        )
        return

    family_count = sum(
        len(_group_families(points, dimension))
        for dimension in _DIMENSIONS
    )
    dimensions = [
        dimension for dimension in _DIMENSIONS
        if _group_families(points, dimension)
    ]
    category_count = sum(
        len(family["groups"])
        for dimension in _DIMENSIONS
        for family in _group_families(points, dimension)
    )
    render_html(kpi_grid([
            kpi_card(
                "Observed NBR dimensions",
                f"{len(dimensions)}",
                "",
                len(dimensions) / max(len(_DIMENSIONS), 1) * 100,
                PALETTE["teal"],
                ", ".join(_DIMENSIONS[key] for key in dimensions) or "No supported breakdowns",
            ),
            kpi_card(
                "Comparable source families",
                f"{family_count}",
                "",
                min(family_count / 10 * 100, 100),
                PALETTE["blue"],
                "Same metric, unit, geography, date scope, and remaining filters",
            ),
            kpi_card(
                "Observed categories",
                f"{category_count}",
                "",
                min(category_count / 10 * 100, 100),
                PALETTE["sun"],
                "NBR labels retained as collected",
            ),
            kpi_card(
                "Available observations",
                f"{summary.get('eligible_source_point_count', 0):,}",
                "",
                100,
                PALETTE["ink2"],
                f"{NBR_PAGE_LABELS.get(source_page, source_page)} · selected source area",
            ),
        ]))
    with st.container(key="card_nbr_population"):
        _render_population_context(points, source_version=source_version)
    note(
        "Comparability limitation",
        "NBR Youth/Non-Youth is not crosswalked to FinScope age bands. Education and urban/rural "
        "comparisons are shown only if the selected NBR source actually provides those filters.",
        tone="info",
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
