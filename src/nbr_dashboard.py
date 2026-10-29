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

MODE_KEY = "global_dashboard_mode"
MODES = ("Combined", "FinScope", "NBR Supply")
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
_DIMENSIONS = {
    "Gender": "Gender",
    "Age Segment": "Age Segment (NBR Youth/Non-Youth)",
}


def current_mode() -> str:
    mode = st.session_state.get(MODE_KEY, "FinScope")
    return mode if mode in MODES else "FinScope"


def render_mode_selector() -> None:
    if MODE_KEY not in st.session_state:
        st.session_state[MODE_KEY] = "FinScope"
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
                    "Combined": "Survey results with separate NBR context.",
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


def render_beta_notice() -> None:
    render_html = (
        '<div style="display:flex;gap:10px;align-items:flex-start;'
        'padding:12px 15px;border:1px solid #E8C86B;border-radius:12px;'
        'background:#FFF9E8;color:#4D421F;margin:8px 0 16px">'
        '<span style="font-size:11px;font-weight:800;letter-spacing:.08em;'
        'padding:3px 7px;border-radius:6px;background:#F2B84B;color:#0E2A35">'
        'BETA</span><span style="font-size:12.5px;line-height:1.55">'
        + esc(NBR_NOTICE)
        + "</span></div>"
    )
    st.markdown(render_html, unsafe_allow_html=True)


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


@st.cache_data
def _load_nbr_geo_data() -> tuple[
    dict[str, Any],
    dict[str, tuple[float, float]],
    tuple[float, float],
]:
    geojson, centers, center = _load_nbr_geo_data()
    return geojson, centers, center


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
        sorted({str(item["relationship"]) for item in entry.get("mappings", [])})
    )
    return (
        f"{entry['display_label']} · {unit} · {entry['geography_level']} · "
        f"{scope or 'filters not recorded'}"
        + (f" · FinScope mapping: {relation}" if relation else "")
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


def _render_trend(points: Sequence[Mapping[str, Any]], *, title: str) -> None:
    if not points:
        st.info("No observations are available for this exact series and scope.")
        return
    ordered = sorted(points, key=lambda point: str(point["reporting_date"]))
    unit = str(ordered[0].get("unit") or "unit not specified")
    fig = go.Figure(go.Scatter(
        x=[item["reporting_date"] for item in ordered],
        y=[item["value"] for item in ordered],
        mode="lines+markers+text",
        text=[f"{item['value']:,.4g}" for item in ordered],
        textposition="top center",
        marker=dict(size=9, color=PALETTE["blue"]),
        line=dict(color=PALETTE["blue"], width=2.5),
        customdata=[
            [
                item.get("source_record_id", ""),
                item.get("run_id", ""),
                item.get("collected_at", ""),
            ]
            for item in ordered
        ],
        hovertemplate=(
            "<b>%{x}</b><br>Observed: %{y:,.4g} "
            + esc(unit)
            + "<br>Source record: %{customdata[0]}"
            + "<br>Run: %{customdata[1]}"
            + "<br>Collected: %{customdata[2]}<extra></extra>"
        ),
    ))
    fig.update_xaxes(title="NBR reporting date", showgrid=False)
    fig.update_yaxes(title=f"{title} · {unit}", gridcolor=PALETTE["grid"], rangemode="tozero")
    st.plotly_chart(
        style_chart(fig, 310),
        use_container_width=True,
        config={"displayModeBar": False},
        key=f"nbr_trend_{hashlib.sha1(title.encode()).hexdigest()[:10]}",
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
            "Unit metadata": point.get("unit_status") or "Unresolved",
            "Source page": point.get("page", ""),
            "Source type": point.get("source_type", ""),
            "Filters": _filters_key(point.get("filters", {})),
            "Run ID": point.get("run_id", ""),
            "Source record ID": point.get("source_record_id", ""),
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
) -> list[dict[str, Any]]:
    if subgroup_type and subgroup_type not in {"Gender"}:
        return []
    mapping = MAPPING_BY_VARIABLE.get(indicator_variable)
    if not mapping:
        return []
    entries: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for relationship in mapping["nbr_relationships"]:
        if relationship["relationship"] == "unsuitable":
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
            entry["points"].append(dict(point))
    for entry in entries.values():
        entry["points"].sort(key=lambda item: str(item["reporting_date"]))
    return list(entries.values())


def _render_marker_map(
    points: Sequence[Mapping[str, Any]],
    *,
    selected_date: str,
    title: str,
) -> None:
    if not points:
        st.info("No district-level observations are available to map for this series.")
        return
    try:
        centers, center = data.geo_summary(data.load_geojson())
    except (FileNotFoundError, ValueError, KeyError) as error:
        st.warning("The NBR map is unavailable because district boundaries could not be loaded.")
        st.caption(str(error))
        return
    selected = [
        point for point in points
        if str(point.get("reporting_date")) == selected_date
        and point.get("geography") in centers
    ]
    if not selected:
        st.info(f"No map-ready district observations are available for {selected_date}.")
        return
    values = [float(point["value"]) for point in selected]
    low, high = min(values), max(values)
    lat, lon, sizes, hover, custom = [], [], [], [], []
    for point in selected:
        latitude, longitude = centers[str(point["geography"])]
        lat.append(latitude)
        lon.append(longitude)
        value = float(point["value"])
        ratio = (
            math.sqrt(max(0.0, value - low) / (high - low))
            if high > low else 0.5
        )
        sizes.append(10 + ratio * 22)
        hover.append(str(point["geography"]))
        custom.append([
            value,
            point.get("metric_label", ""),
            point.get("unit") or "unit not specified",
            point.get("page", ""),
            point.get("source_record_id", ""),
        ])
    scatter_class = go.Scattermap if hasattr(go, "Scattermap") else go.Scattermapbox
    map_key = "map" if hasattr(go, "Scattermap") else "mapbox"
    fig = go.Figure(scatter_class(
        lat=lat,
        lon=lon,
        text=hover,
        customdata=custom,
        mode="markers",
        marker=dict(size=sizes, color=PALETTE["ink2"], opacity=0.76),
        name="NBR marker size · selected metric",
        hovertemplate=(
            "<b>%{text}</b><br>%{customdata[1]}: %{customdata[0]:,.4g} "
            "%{customdata[2]}<br>Page: %{customdata[3]}<br>"
            f"Reporting date: {esc(selected_date)}<br>"
            "Source record: %{customdata[4]}<extra></extra>"
        ),
    ))
    fig.update_layout(**{
        map_key: dict(
            style="carto-positron",
            center={"lat": center[0], "lon": center[1]},
            zoom=6.7,
        )
    })
    fig.update_layout(
        height=510,
        margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h"),
    )
    st.plotly_chart(
        fig,
        use_container_width=True,
        config={"displayModeBar": False, "scrollZoom": True},
        key=f"nbr_map_{hashlib.sha1((title + selected_date).encode()).hexdigest()[:10]}",
    )
    st.caption(
        f"Marker size compares {title} values only within this selected series and date. "
        "It is not a FinScope color scale, access score, or inclusion measure."
    )


def _nbr_district_map(
    frame: pd.DataFrame,
    *,
    geojson: Mapping[str, Any],
    centers: Mapping[str, tuple[float, float]],
    center: tuple[float, float],
    selected_district: str,
    metric_label: str,
    unit: str,
    reporting_date: str,
    settings: Mapping[str, Any],
) -> go.Figure:
    from src.pages.district_explorer import (
        BASEMAPS,
        FEATURE_KEY,
        _outline_layer,
        _trace_classes,
    )

    choropleth, _, map_key = _trace_classes()
    base = BASEMAPS[settings["basemap"]]
    values = frame["Value"].astype(float)
    low, high = float(values.min()), float(values.max())
    if high == low:
        high = low + max(abs(low) * 1e-9, 1e-9)
    colorscale = (
        [[0, "#EAF6F3"], [0.35, "#9FD3CB"], [0.7, "#3AA597"], [1, "#0E2A35"]]
        if settings["palette"] == "Indicator colours"
        else settings["palette"]
    )
    layers = []
    if base.get("tiles"):
        layers.append({
            "below": "traces",
            "sourcetype": "raster",
            "source": [base["tiles"]],
            "sourceattribution": "Imagery © Esri",
        })
    ordered = frame.sort_values("Value", ascending=False)["District"].tolist()
    if settings["spotlight"] in {"Top 5", "Both"}:
        layers.append(_outline_layer(
            dict(geojson),
            ordered[:5],
            PALETTE["ink"],
            2.4,
        ))
    if settings["spotlight"] in {"Bottom 5", "Both"}:
        layers.append(_outline_layer(
            dict(geojson),
            ordered[-5:],
            PALETTE["coral"],
            2.4,
        ))
    layers.append(_outline_layer(
        dict(geojson), [selected_district], PALETTE["ink"], 7, 0.55
    ))
    layers.append(_outline_layer(
        dict(geojson), [selected_district], PALETTE["sun"], 3.4
    ))
    fig = go.Figure(choropleth(
        geojson=dict(geojson),
        featureidkey=FEATURE_KEY,
        locations=frame["District"],
        z=frame["Value"],
        zmin=low,
        zmax=high,
        colorscale=colorscale,
        marker=dict(
            opacity=settings["opacity"],
            line=dict(color="#FFFFFF", width=0.9),
        ),
        customdata=frame[["Unit", "Source record ID", "Run ID"]].to_numpy(),
        hovertemplate=(
            "<b>%{location}</b><br>"
            + esc(metric_label)
            + ": <b>%{z:,.4g}</b> %{customdata[0]}<br>"
            + f"Reporting date: {esc(reporting_date)}<br>"
            + "Source record: %{customdata[1]}<br>"
            + "Run: %{customdata[2]}<extra></extra>"
        ),
        colorbar=dict(
            title=dict(text=f"{metric_label} · {unit}", side="top", font=dict(size=11)),
            orientation="h",
            x=0.02,
            y=0.04,
            xanchor="left",
            yanchor="bottom",
            len=0.48,
            thickness=10,
            nticks=4,
            outlinewidth=0,
            bgcolor="rgba(255,255,255,.9)",
            tickfont=dict(size=11, color=PALETTE["ink"]),
        ),
        selected=dict(marker=dict(opacity=settings["opacity"])),
        unselected=dict(marker=dict(opacity=settings["opacity"])),
    ))
    fig.update_layout(**{
        map_key: {
            "style": base["style"],
            "center": {"lat": center[0], "lon": center[1]},
            "zoom": settings["zoom"],
            "pitch": settings["tilt"],
            "bearing": settings["rotation"],
            "layers": layers,
        }
    })
    fig.update_layout(
        height=700,
        margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Plus Jakarta Sans, Arial, sans-serif", color=PALETTE["ink"]),
        hoverlabel=dict(
            bgcolor=PALETTE["ink"],
            bordercolor=PALETTE["ink"],
            font=dict(
                family="Plus Jakarta Sans, Arial, sans-serif",
                color="#FFFFFF",
                size=12.5,
            ),
        ),
        uirevision=(
            f"{settings['basemap']}-{settings['tilt']}-{settings['rotation']}-"
            f"{reporting_date}"
        ),
        dragmode="pan",
    )
    return fig


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
    )

    title = "Priority Explorer · NBR Supply" if priority_view else "District Explorer · NBR Supply"
    description = (
        "Explore observed administrative values by district, with source-specific "
        "units, reporting dates, filters, and provenance. Values are not FinScope estimates."
    )

    def render_empty_header() -> None:
        page_header(
            title,
            description,
            pill="NBR Supply · BETA",
            size="tall",
        )

    district_options = [
        item for item in registry if item.get("geography_level") == "district"
    ]
    if not district_options:
        render_empty_header()
        with st.container(key="card_nbr_unavailable"):
            card_title("District data unavailable", "No validated district-level NBR series is currently available.")
            st.info(
                "The source did not provide an eligible district series. This is unavailable evidence, "
                "not a zero value or a negative finding."
            )
            st.caption(
                f"Eligible normalized observations: "
                f"{summary.get('eligible_source_point_count', 0):,}."
            )
        return

    st.session_state.pop("_nbr_dx_pending_district", None)
    page = source_page
    page_entries = [item for item in district_options if item["source_page"] == page]
    if not page_entries:
        render_empty_header()
        with st.container(key="card_nbr_unavailable"):
            card_title("No district series on this page")
            st.info("This NBR page has no eligible district series in the current read-only source snapshot.")
        return

    with st.container(key="card_controls"):
        card_title("Choose an NBR series", "Every choice is limited to a source-observed page, metric, and exact filter scope.")
        page_col, metric_col = st.columns([1, 1.4], gap="medium")
        with page_col:
            st.caption("NBR page")
            st.markdown(f"**{NBR_PAGE_LABELS.get(page, page)}**")
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
                "Administrative metric",
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
        filter_col, date_col = st.columns([1.5, 1], gap="medium")
        with filter_col:
            selected_filter = st.selectbox(
                "Exact observed filter combination",
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
        render_empty_header()
        with st.container(key="card_nbr_unavailable"):
            card_title("No observations for this series", "Try another exact metric or filter combination.")
            st.info("Missing observations remain unavailable; they are not interpolated or set to zero.")
        return

    dated = [point for point in series if str(point["reporting_date"]) == reporting_date]
    district_values = {
        str(point["geography"]): point for point in dated
    }
    names = sorted(district_values)
    if not names:
        render_empty_header()
        st.info("No district observations are available for this reporting date.")
        return
    if selected_district not in names:
        selected_district = names[0]
    pending = st.session_state.pop("_nbr_dx_pending_district", None)
    if pending in names:
        selected_district = pending
    district_key = f"nbr_district_selected_{source_version}"
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
        render_empty_header()
        st.info(f"No {metric} observation is available for {selected_district} on {reporting_date}.")
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
        f"{delta:+,.4g}" if delta is not None else "Unavailable"
    )
    cards = [
        kpi_card(
            "Selected district value",
            f"{value:,.4g}",
            f" {unit or 'unit not specified'}",
            value_fill,
            PALETTE["teal"],
            f"{esc(selected_district)} · {esc(reporting_date)}",
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
            "Descriptive ranking within this metric, date, and filter scope",
        ),
        kpi_card(
            "District observations",
            f"{len(ranked)}",
            f" / {mapped_district_count}",
            len(ranked) / max(mapped_district_count, 1) * 100,
            PALETTE["ink2"],
            (
                "Observed districts / Rwanda district boundaries"
                if map_error is None
                else "Observed districts; boundary coverage unavailable"
            ),
        ),
    ]
    page_header(
        title,
        f"{entry['display_label']} · {unit or 'unit not specified'} · {reporting_date}",
        pill="NBR Supply · BETA",
        size="tall",
        below_html=kpi_grid(cards),
    )
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
            f"Source page: {NBR_PAGE_LABELS.get(page, page)} · "
            f"Filters: {_filter_label(entry['filters'])}"
        )
    settings = {
        "basemap": basemap,
        "palette": palette,
        "opacity": opacity,
        "spotlight": spotlight,
        "tilt": tilt,
        "rotation": rotation,
        "zoom": 7.3,
    }
    map_col, inspector_col = st.columns([2.85, 1], gap="medium")
    with map_col:
        with st.container(key="card_nbr_map"):
            render_html(
                f'<div class="map-strip"><div><div class="ct">{esc(metric)}</div>'
                '<div class="cs">District values for the selected reporting date · '
                'click a district to inspect it</div></div>'
                '<div class="chips"><span class="chip">Observed NBR values</span>'
                '<span class="chip">No data is not zero</span></div></div>'
            )
            if map_error is not None:
                st.warning("The NBR map is unavailable because district boundaries could not be loaded.")
                st.caption(str(map_error))
            if geojson is not None:
                map_frame = ranked.rename(columns={"Value": "Value"}).copy()
                map_frame["Unit"] = unit or "unit not specified"
                event = st.plotly_chart(
                    _nbr_district_map(
                        map_frame,
                        geojson=geojson,
                        centers=centers,
                        center=center,
                        selected_district=selected_district,
                        metric_label=metric,
                        unit=unit or "unit not specified",
                        reporting_date=reporting_date,
                        settings=settings,
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
                    st.session_state[district_key] = clicked
                    st.rerun()
    with inspector_col:
        with st.container(key="card_nbr_inspector"):
            rank = int(rank_row["Rank"])
            meter = (value - low) / (high - low) * 100 if high > low else 50
            render_html(
                f'<div class="insp-top"><div class="insp-name">{esc(selected_district)}</div>'
                f'<div class="insp-rank">#{rank} of {len(ranked)}</div></div>'
                f'<div class="insp-value">{value:,.4g}<span> {esc(unit or "unit not specified")}</span></div>'
                f'<div class="insp-sub">{esc(metric)} · reporting date {esc(reporting_date)}</div>'
                f'<div class="meter"><div class="meter-track"></div>'
                f'<div class="meter-dot" style="left:{meter:.1f}%"></div></div>'
                f'<div class="meter-ends"><span>Lowest {low:,.4g}</span>'
                f'<span>Highest {high:,.4g}</span></div>'
                f'<div class="insp-note"><b>Observed administrative value</b><br>'
                f'{esc(_filter_label(entry["filters"]))}<br>'
                'This comparison does not imply a survey-measured access or ownership gap.</div>'
            )
            if previous is not None:
                st.caption(
                    f"Previous observation: {previous['value']:,.4g} {unit} "
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
                hovertemplate=f"%{{x:,.4g}} {esc(unit)}<br>%{{y}} districts<extra></extra>",
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
                "Rank", "District", "Value", "Unit", "Reporting date",
                "Filters", "Source page", "Metric", "Run ID", "Source record ID",
            ]],
            hide_index=True,
            use_container_width=True,
            height=440,
        )
    with st.expander("Source observations, limitations, and mapping"):
        st.caption(
            f"Normalized observations loaded: {summary.get('eligible_source_point_count', 0):,} · "
            f"Source snapshot: {source_version}"
        )
        if entry.get("mappings"):
            for mapping in entry["mappings"]:
                st.markdown(
                    f"- **{esc(mapping['indicator_label'])}** "
                    f"(`{esc(mapping['indicator_variable'])}`): "
                    f"{esc(mapping['relationship'])}. {esc(mapping['limitations'])}"
                )
        else:
            st.info("No approved FinScope relationship is configured for this exact series.")
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
            f"Assessment {assessment['assessment_id']} · {assessment['model_version']} · "
            f"{assessment['assessment_timestamp']} · source commit "
            f"{assessment.get('source_git_commit') or 'unavailable'} · "
            f"page scope {', '.join(assessment.get('pages', []))} · "
            f"source data {source_version} · {len(scoped_candidates)} candidate(s)."
        )
        if not scoped_candidates:
            st.info(
                "No candidate is recorded for this exact series. This does not establish that the series "
                "is normal or that no data-quality issue exists."
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
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        with st.expander("Candidate evidence qualifications"):
            for candidate in scoped_candidates:
                st.markdown(
                    f"**{candidate['method']} · {candidate.get('reporting_date', '')}** — "
                    f"{candidate.get('reason', 'No reason recorded')}"
                )
                st.json({
                    "evidence_assessment": candidate.get("evidence_assessment", {}),
                    "quality_qualifications": candidate.get("quality_qualifications", []),
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
    include_map: bool = False,
    source_version: str | None = None,
) -> None:
    source_version = source_version or _source_data_version(points)
    level = "district" if district else "national"
    if subgroup_type == "Gender" and not subgroup:
        mapping = MAPPING_BY_VARIABLE.get(indicator_variable, {})
        gender_options = set()
        for relationship in mapping.get("nbr_relationships", []):
            labels = (
                relationship["district_table_labels"]
                if level == "district"
                else relationship["national_kpi_labels"]
            )
            expected_filters = {
                key: value
                for key, value in relationship["filter_scope"].items()
                if key != "Gender"
            }
            gender_options.update(
                str(point["filters"]["Gender"])
                for point in points
                if point.get("page") == relationship["page"]
                and point.get("metric_label") in labels
                and point.get("geography_level") == level
                and (district is None or point.get("geography") == district)
                and isinstance(point.get("filters"), Mapping)
                and point["filters"].get("Gender", "All").casefold() != "all"
                and _filters_match(point["filters"], expected_filters)
            )
        if gender_options:
            subgroup = st.selectbox(
                "Observed NBR gender filter",
                sorted(gender_options),
                key=(
                    f"combined_nbr_gender_{indicator_variable}_"
                    f"{district or 'national'}_{source_version}"
                ),
            )
        else:
            st.info(
                "No NBR observations match an observed gender category for this "
                "indicator and exact geographic scope."
            )
            return
    entries = _mapped_series(
        points,
        indicator_variable,
        geography_level=level,
        geography=district,
        subgroup_type=subgroup_type,
        subgroup=subgroup,
    )
    with st.container(key="nbr_context_card"):
        render_html(badge("NBR Supply · BETA", "warn"))
        card_title(
            "NBR administrative context",
            "Separate administrative observations; they do not update the FinScope estimate.",
        )
        if not entries:
            st.info(
                "No eligible NBR series is available for this FinScope indicator and exact scope. "
                "This is unavailable evidence, not a negative finding."
            )
            return
        labels = [_series_label(entry) for entry in entries]
        selected_label = st.selectbox(
            "NBR series",
            labels,
            key=(
                f"combined_nbr_series_{indicator_variable}_"
                f"{district or 'national'}_{subgroup or 'all'}_{source_version}"
            ),
        )
        entry = entries[labels.index(selected_label)]
        series_points = entry["points"]
        dates = sorted({str(point["reporting_date"]) for point in series_points})
        latest_date = dates[-1]
        latest = [point for point in series_points if point["reporting_date"] == latest_date]
        if district:
            _render_trend(
                series_points,
                title=f"{entry['page']} · {entry['metric_label']}",
            )
        else:
            _render_trend(
                series_points,
                title=f"{entry['page']} · {entry['metric_label']}",
            )
        relation_label = (
            "Contextual indicator" if entry["relationship"] == "contextual_indicator"
            else "Proxy with unresolved definition"
        )
        st.caption(
            f"{relation_label} · {entry['page']} · {entry['metric_label']} · "
            f"{entry.get('unit') or 'unit not specified'} · {len(dates)} observed dates · "
            f"latest reporting date {latest_date} · source: NBR administrative dashboard."
        )
        st.warning(entry["limitations"])
        with st.expander("Source observations and filters"):
            _render_observation_table(series_points)
        if include_map:
            with st.expander("Show NBR supply locations"):
                map_dates = sorted({
                    str(point["reporting_date"])
                    for point in points
                    if point.get("page") == entry["page"]
                    and point.get("metric_label") == entry["metric_label"]
                    and point.get("geography_level") == "district"
                    and point.get("filters") == entry["filters"]
                })
                if map_dates:
                    map_date = st.selectbox(
                        "NBR map reporting date",
                        map_dates,
                        index=map_dates.index(latest_date)
                        if latest_date in map_dates else len(map_dates) - 1,
                        key=(
                            f"combined_nbr_map_date_{entry['page']}_"
                            f"{indicator_variable}_{source_version}"
                        ),
                    )
                    map_points = _series_points(
                        points,
                        page=entry["page"],
                        metric=entry["metric_label"],
                        geography_level="district",
                        filters=entry["filters"],
                    )
                    _render_marker_map(
                        map_points,
                        selected_date=map_date,
                        title=(
                            f"{entry['page']} · {entry['metric_label']} · "
                            f"{entry.get('unit') or 'unit not specified'}"
                        ),
                    )
                else:
                    st.info(
                        "This mapped FinScope context has no district-level NBR series "
                        "with the same exact filters."
                    )
        del latest


def render_combined_context(
    indicator_variable: str,
    *,
    district: str | None = None,
    subgroup_type: str = "",
    subgroup: str = "",
    include_map: bool = False,
) -> None:
    mapping = MAPPING_BY_VARIABLE.get(indicator_variable)
    if mapping is None:
        st.warning(
            "NBR administrative context is unavailable for this indicator; "
            "FinScope results remain unchanged."
        )
        return
    pages = tuple(sorted({
        str(relationship["page"])
        for relationship in mapping["nbr_relationships"]
        if relationship.get("relationship") != "unsuitable"
    }))
    if not pages:
        st.info("No NBR page is configured for this FinScope indicator.")
        return
    page_key = (
        f"combined_nbr_page_{indicator_variable}_{district or 'national'}_"
        f"{subgroup_type or 'all'}_{subgroup or 'all'}"
    )
    source_page = st.selectbox(
        "NBR source page",
        pages,
        format_func=lambda page: NBR_PAGE_LABELS.get(page, page),
        key=page_key,
        help="Choose one configured NBR page. Only its observations are loaded for this context.",
    )
    try:
        points, _, _, source_version = load_nbr_dashboard_data(
            "nbr-dashboard-v2",
            (source_page,),
        )
    except (RuntimeError, ValueError, OSError, PyMongoError) as error:
        st.warning("NBR administrative context is unavailable; FinScope results remain unchanged.")
        st.caption(str(error))
        return
    _render_combined_context(
        points,
        indicator_variable=indicator_variable,
        district=district,
        subgroup_type=subgroup_type,
        subgroup=subgroup,
        include_map=include_map,
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
            "NBR population-filter context",
            "Only observed NBR filters are shown; NBR Age Segment is Youth/Non-Youth, not FinScope age bands.",
        )
        dimensions = [
            dimension for dimension in _DIMENSIONS
            if _group_families(points, dimension)
        ]
        if not dimensions:
            st.info(
                "No NBR demographic comparison with multiple observed categories is available. "
                "Education and urban/rural breakdowns are not provided by this NBR dataset."
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
                    "Source page": point.get("page", ""),
                    "Source record ID": point.get("source_record_id", ""),
                })
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.info("No NBR category observations exist for this exact reporting date.")
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
                customdata=[
                    point.get("source_record_id", "") for point in ordered
                ],
                hovertemplate=(
                    "<b>%{x}</b><br>%{y:,.4g} "
                    + esc(family.get("unit") or "unit not specified")
                    + "<br>Source record: %{customdata}<extra>%{fullData.name}</extra>"
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
            "NBR source page",
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
        "Administrative metric",
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
        "Exact observed filter combination",
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
    page_title = "National Overview · NBR Supply"
    with st.container(key="card_controls"):
        card_title(
            "Choose a national series",
            "Metric and filter selections come from validated observations on this NBR page.",
        )
        entry, series = _page_series_selection(
            points,
            registry=registry,
            source_version=source_version,
            geography_level="national",
            view="national",
        )
        if entry is None:
            st.info(
                f"No validated national series is currently available on "
                f"{NBR_PAGE_LABELS.get(source_page, source_page)}."
            )
            st.caption("Unavailable data is not treated as a zero or negative finding.")
            return
        if not series:
            st.info("No observations match the selected metric and exact filter combination.")
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
        st.info("No national observation is recorded for the selected date.")
        return
    ordered = sorted(series, key=lambda point: str(point["reporting_date"]))
    index = next(
        index for index, point in enumerate(ordered)
        if point.get("source_record_id") == selected.get("source_record_id")
    )
    previous = ordered[index - 1] if index else None
    unit = str(entry.get("unit") or "unit not specified")
    value = float(selected["value"])
    delta = value - float(previous["value"]) if previous else None
    cards = [
        kpi_card(
            "Observed national value",
            f"{value:,.4g}",
            f" {unit}",
            50,
            PALETTE["teal"],
            f"{reporting_date} · {entry['metric_label']}",
        ),
        kpi_card(
            "Change from prior observation",
            f"{delta:+,.4g}" if delta is not None else "Unavailable",
            f" {unit}",
            min(100, abs(delta or 0) / max(abs(value), 1) * 100),
            PALETTE["blue"] if (delta or 0) >= 0 else PALETTE["coral"],
            f"Prior date: {previous['reporting_date']}" if previous else "No earlier observation",
        ),
        kpi_card(
            "Observed dates",
            f"{len(ordered)}",
            "",
            min(len(ordered) / 5 * 100, 100),
            PALETTE["sun"],
            "Recorded dates in this exact series",
        ),
        kpi_card(
            "Source record",
            "Available",
            "",
            100,
            PALETTE["ink2"],
            esc(selected.get("source_record_id", "")),
        ),
    ]
    page_header(
        page_title,
        f"{entry['display_label']} · {unit} · {reporting_date}",
        pill="NBR Supply · BETA",
        size="tall",
        below_html=kpi_grid(cards),
    )
    note(
        "Administrative evidence only",
        "Customer counts, service activity, and infrastructure measures retain their NBR units and filters. "
        "They are not converted into FinScope ownership percentages or conclusions about population access.",
        tone="info",
    )
    chart_col, summary_col = st.columns([1.5, 1], gap="medium")
    with chart_col:
        with st.container(key="card_nbr_national_trend"):
            card_title(
                "Observed national trend",
                "Only source-reported dates are plotted; no interpolation is applied.",
            )
            _render_trend(ordered, title=f"{entry['metric_label']} · {unit}")
    with summary_col:
        with st.container(key="card_nbr_national_context"):
            card_title("Selected series", "Scope and measurement details")
            render_html(
                f'<div class="insp-note"><b>{esc(entry["metric_label"])}</b><br>'
                f'Unit: {esc(unit)}<br>Page: {esc(NBR_PAGE_LABELS.get(source_page, source_page))}<br>'
                f'Filters: {esc(_filter_label(entry["filters"]))}<br>'
                f'Reporting date: {esc(reporting_date)}<br>'
                f'Source record: {esc(selected.get("source_record_id", ""))}</div>'
            )
            mappings = entry.get("mappings", [])
            if mappings:
                for mapping in mappings:
                    st.warning(
                        f"{mapping['relationship']}: {mapping['limitations']}"
                    )
            else:
                st.caption("No approved FinScope relationship is configured for this exact series.")
    with st.container(key="card_nbr_national_table"):
        card_title("National observations", "Values, dates, and provenance for this exact source series.")
        _render_observation_table(ordered)
    with st.expander("Source assessment"):
        st.caption(
            f"Eligible normalized NBR observations on this page: "
            f"{summary.get('eligible_source_point_count', 0):,} · source snapshot {source_version}"
        )
        st.caption(f"Unit metadata: {entry.get('unit_status') or 'unresolved'}.")


def render_nbr_page(
    view: str,
    *,
    selected_district: str | None = None,
) -> None:
    """Render source-aware NBR views from one cached, page-scoped snapshot."""
    if view not in {"national", "district", "population", "priority"}:
        raise ValueError(f"Unknown NBR dashboard view: {view}")
    render_beta_notice()
    title = {
        "national": "National overview · NBR Supply",
        "district": "District explorer · NBR Supply",
        "population": "Population groups · NBR Supply",
        "priority": "Priority explorer · NBR Supply",
    }[view]
    with st.container(key="card_nbr_page_selector"):
        card_title(
            "NBR administrative source",
            "Select a page to load only its validated observations and exact filters.",
        )
        source_pages = sorted(NBR_PAGE_LABELS)
        page_labels = [NBR_PAGE_LABELS[page] for page in source_pages]
        page_key = f"nbr_source_page_{view}"
        initial_page = st.session_state.get(
            page_key,
            "inclusion" if view in {"national", "population"} else "branches",
        )
        if initial_page not in source_pages:
            initial_page = source_pages[0]
        selected_label = st.selectbox(
            "NBR page",
            page_labels,
            index=source_pages.index(initial_page),
            key=page_key,
        )
        source_page = source_pages[page_labels.index(selected_label)]
    try:
        points, summary, registry, source_version = load_nbr_dashboard_data(
            "nbr-dashboard-v2",
            (source_page,),
        )
    except (RuntimeError, ValueError, OSError, PyMongoError) as error:
        page_header(
            title,
            "Read-only NBR administrative evidence",
            pill="NBR Supply · BETA",
            size="compact",
        )
        with st.container(key="card_nbr_unavailable"):
            card_title("NBR data could not be loaded")
            st.error("NBR administrative observations are currently unavailable.")
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
    if view == "national":
        _render_nbr_national_page(
            points,
            summary,
            registry,
            source_version,
            source_page,
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
    page_header(
        title,
        "Compare only demographic categories explicitly observed in the selected NBR source page. "
        "These source filters are not assumed to match FinScope categories.",
        pill="NBR Supply · BETA",
        size="tall",
        below_html=kpi_grid([
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
                "Eligible source points",
                f"{summary.get('eligible_source_point_count', 0):,}",
                "",
                100,
                PALETTE["ink2"],
                f"{NBR_PAGE_LABELS.get(source_page, source_page)} page · {source_version}",
            ),
        ]),
    )
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
