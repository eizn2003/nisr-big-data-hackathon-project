"""Evidence-led NBR district exploration without a composite priority score."""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from datetime import date
from typing import Any, Callable, Mapping, Sequence

from pymongo.errors import PyMongoError

import plotly.graph_objects as go
import streamlit as st

from src.data_sources.mongodb_district_explorer import _unit
from src.styles import (
    PALETTE,
    card_title,
    esc,
    kpi_card,
    kpi_grid,
    page_header,
    style_chart,
)

_HISTORY_REQUIRED_FILTERS = {
    "Account/Policy Status": "Active",
    "Age Segment": "All",
    "Gender": "All",
    "Institution Type": "All",
    "Location": "All",
}


def _filters_key(filters: Mapping[str, Any]) -> str:
    return json.dumps(filters, sort_keys=True, ensure_ascii=False, default=str)


def _filter_label(filters: Mapping[str, Any]) -> str:
    if not filters:
        return "Filters not recorded"
    return " · ".join(
        f"{key}: {value}"
        for key, value in sorted(filters.items(), key=lambda item: str(item[0]))
    )


def _valid_reporting_date(value: Any) -> str | None:
    try:
        return date.fromisoformat(str(value)).isoformat()
    except (TypeError, ValueError):
        return None


def _numeric_value(value: Any) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if math.isfinite(numeric) and numeric >= 0 else None


def _priority_header_html(
    family: Mapping[str, Any] | None,
    snapshot: Mapping[str, Any] | None,
    reporting_date: str | None,
    page_labels: Mapping[str, str] | None = None,
) -> str:
    valid_snapshot = bool(family and snapshot and reporting_date)
    if valid_snapshot:
        rows = list(snapshot["districts"])
        valid_snapshot = bool(rows)
    else:
        rows = []

    if valid_snapshot:
        first = rows[0]
        last = rows[-1]
        page_label = (page_labels or {}).get(
            str(family["page"]),
            str(family["page"]).replace("_", " ").title(),
        )
        district_count = int(snapshot["observed_count"])
        expected = snapshot.get("expected_count")
        coverage_value = str(district_count)
        coverage_unit = f"/ {expected} districts" if expected is not None else "districts"
        coverage_fill = (
            district_count / max(int(expected), 1) * 100
            if expected is not None else 0
        )
        metric_context = (
            f"NBR {esc(page_label)} · "
            f"{esc(str(family['metric_label']))} · "
            f"{esc(str(family['unit']))}<br>"
            f"Latest eligible snapshot: {esc(_format_date(reporting_date))}<br>"
            f"Filters: {esc(_filter_label(family['filters']))}"
        )
        unknown = snapshot.get("unknown", [])
        if len(unknown) == 1:
            unknown_context = (
                "Unknown geography kept separate: "
                f"{_format_value(float(unknown[0]['value']))} {esc(str(family['unit']))}"
            )
        elif len(unknown) > 1:
            unknown_context = (
                f"Unknown geography kept separate: {len(unknown)} rows; "
                "no single value selected"
            )
        else:
            unknown_context = "Unknown geography: no eligible row reported"
        coverage_source = f"{metric_context}<br>{unknown_context}"
        cards = [
            kpi_card(
                "Districts reporting",
                esc(coverage_value),
                coverage_unit,
                coverage_fill,
                PALETTE["blue"],
                coverage_source,
                show_track=expected is not None,
            ),
            kpi_card(
                "Highest reported count",
                esc(_format_value(float(last["value"]))),
                esc(str(family["unit"])),
                0,
                PALETTE["teal"],
                f"<b>{esc(str(last['district']))}</b><br>{metric_context}",
                show_track=False,
            ),
            kpi_card(
                "Lowest reported count",
                esc(_format_value(float(first["value"]))),
                esc(str(family["unit"])),
                0,
                PALETTE["ink2"],
                f"<b>{esc(str(first['district']))}</b><br>{metric_context}",
                show_track=False,
            ),
        ]
    else:
        scope = "No eligible district series"
        if family:
            page_label = (page_labels or {}).get(
                str(family["page"]),
                str(family["page"]).replace("_", " ").title(),
            )
            scope = (
                f"NBR {esc(page_label)} · "
                f"{esc(str(family['metric_label']))} · "
                f"{esc(str(family['unit']))}"
            )
        cards = [
            kpi_card(
                label,
                "Unavailable",
                "",
                0,
                accent,
                f"{scope}<br>No eligible named-district snapshot",
                show_track=False,
            )
            for label, accent in (
                ("Districts reporting", PALETTE["blue"]),
                ("Highest reported count", PALETTE["teal"]),
                ("Lowest reported count", PALETTE["ink2"]),
            )
        ]
    return kpi_grid(cards, columns=3)


def _quality_messages(points: Sequence[Mapping[str, Any]]) -> list[str]:
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


def _priority_families(
    points: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for point in points:
        filters = point.get("filters")
        if (
            point.get("source_type") != "district_table"
            or point.get("geography_level") not in {"district", "unknown"}
            or point.get("unit") != "count"
            or point.get("unit_status") != "source_column"
            or not isinstance(filters, Mapping)
            or not str(point.get("geography", "")).strip()
        ):
            continue
        key = (
            str(point.get("page", "")),
            str(point.get("metric_label", "")),
            str(point.get("unit", "")),
            _filters_key(filters),
        )
        grouped[key].append(point)

    families = []
    for key, records in sorted(grouped.items()):
        page, metric, unit, serialized_filters = key
        filters = json.loads(serialized_filters)
        usable_dates = set()
        for point in records:
            if (
                point.get("geography_level") != "district"
                or point.get("repeated_snapshot_warning") is True
                or point.get("repeated_content_across_dates") is True
                or _numeric_value(point.get("value")) is None
            ):
                continue
            if _valid_reporting_date(point.get("reporting_date")) is not None:
                usable_dates.add(str(point["reporting_date"]))
        if not usable_dates:
            continue
        families.append({
            "page": page,
            "metric_label": metric,
            "unit": unit,
            "filters": filters,
            "filters_key": serialized_filters,
            "records": records,
            "dates": sorted(usable_dates),
        })
    return families


def _is_priority_family_record(
    point: Mapping[str, Any],
    family: Mapping[str, Any],
) -> bool:
    return (
        point.get("page") == family.get("page")
        and point.get("metric_label") == family.get("metric_label")
        and point.get("unit") == family.get("unit")
        and point.get("unit_status") == "source_column"
        and point.get("source_type") == "district_table"
        and point.get("geography_level") in {"district", "unknown"}
        and point.get("filters") == family.get("filters")
    )


def _priority_catalog_families(
    runs: Sequence[Mapping[str, Any]],
    *,
    page: str,
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for run in runs:
        if (
            run.get("page") != page
            or run.get("status") != "complete"
            or run.get("repeated_snapshot_warning") is True
            or run.get("table_status") != "extracted"
        ):
            continue
        reporting_date = _valid_reporting_date(run.get("snapshot_date"))
        filters = run.get("filters")
        if not isinstance(filters, Mapping):
            filters = run.get("filters_requested")
        if reporting_date is None or not isinstance(filters, Mapping):
            continue
        identity = (
            page,
            reporting_date,
            str(run.get("combo_key", "")),
        )
        if not identity[2]:
            continue
        for raw_label in run.get("table_columns", []):
            metric = str(raw_label).strip()
            unit, unit_status = _unit(None, metric, False)
            if not metric or unit != "count" or unit_status != "source_column":
                continue
            key = (page, metric, _filters_key(filters))
            family = grouped.setdefault(
                key,
                {
                    "page": page,
                    "metric_label": metric,
                    "unit": unit,
                    "filters": dict(filters),
                    "filters_key": key[2],
                    "records": [],
                    "dates": [],
                    "scope_keys": [],
                },
            )
            family["dates"].append(reporting_date)
            family["scope_keys"].append(identity)

    families = []
    for family in grouped.values():
        scope_by_date: dict[str, set[tuple[str, str, str]]] = defaultdict(set)
        for identity in family["scope_keys"]:
            scope_by_date[identity[1]].add(identity)
        family["dates"] = sorted(scope_by_date)
        family["scope_keys"] = tuple(sorted({
            identity
            for identities in scope_by_date.values()
            for identity in identities
        }))
        families.append(family)
    return sorted(
        families,
        key=lambda item: (
            str(item["metric_label"]),
            str(item["unit"]),
            str(item["filters_key"]),
        ),
    )


def _prepare_priority_snapshot(
    family: Mapping[str, Any],
    reporting_date: str,
    *,
    expected_districts: Sequence[str] = (),
) -> dict[str, Any]:
    records = [
        point
        for point in family["records"]
        if str(point.get("reporting_date", "")) == reporting_date
    ]
    expected_by_key = {
        str(name).strip().casefold(): str(name).strip()
        for name in expected_districts
        if str(name).strip()
    }
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    unknown_records = []
    unmatched_records: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    invalid_count = 0
    repeated_count = 0

    for point in records:
        if (
            point.get("repeated_snapshot_warning") is True
            or point.get("repeated_content_across_dates") is True
        ):
            repeated_count += 1
            continue
        if _numeric_value(point.get("value")) is None:
            invalid_count += 1
            continue
        geography = str(point.get("geography", "")).strip()
        if (
            point.get("geography_level") == "unknown"
            or geography.casefold() == "unknown"
        ):
            unknown_records.append(point)
            continue
        canonical = expected_by_key.get(geography.casefold())
        if expected_by_key and canonical is None:
            unmatched_records[geography].append(point)
            continue
        grouped[canonical or geography].append(point)

    districts = []
    duplicate_count = 0
    for geography, observations in grouped.items():
        if len(observations) != 1:
            duplicate_count += len(observations)
            continue
        point = observations[0]
        districts.append({
            "district": geography,
            "value": _numeric_value(point["value"]),
            "point": point,
        })
    districts.sort(key=lambda row: (row["value"], row["district"].casefold()))
    observed_districts = {row["district"] for row in districts}
    included_points = [
        row["point"] for row in districts
    ] + unknown_records + [
        point
        for observations in unmatched_records.values()
        for point in observations
    ]
    expected = len(expected_by_key) if expected_by_key else None
    return {
        "districts": districts,
        "unknown": unknown_records,
        "unmatched": sorted(unmatched_records),
        "invalid_count": invalid_count,
        "repeated_count": repeated_count,
        "duplicate_count": duplicate_count,
        "observed_count": len(districts),
        "expected_count": expected,
        "missing_count": (
            max(expected - len(observed_districts), 0)
            if expected is not None else None
        ),
        "quality_messages": _quality_messages(included_points),
    }


def _prepare_priority_history(
    family: Mapping[str, Any],
    district: str,
) -> dict[str, Any]:
    matches = [
        point
        for point in family["records"]
        if str(point.get("geography", "")).strip().casefold()
        == district.strip().casefold()
        and point.get("geography_level") == "district"
    ]
    by_date: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    invalid_dates = 0
    invalid_values = 0
    repeated_count = 0
    for point in matches:
        reporting_date = _valid_reporting_date(point.get("reporting_date"))
        if reporting_date is None:
            invalid_dates += 1
            continue
        if (
            point.get("repeated_snapshot_warning") is True
            or point.get("repeated_content_across_dates") is True
        ):
            repeated_count += 1
            continue
        if _numeric_value(point.get("value")) is None:
            invalid_values += 1
            continue
        by_date[reporting_date].append(point)

    observations = []
    duplicate_dates = []
    for reporting_date, dated_points in by_date.items():
        if len(dated_points) != 1:
            duplicate_dates.append(reporting_date)
            continue
        point = dated_points[0]
        observations.append({
            "reporting_date": reporting_date,
            "value": _numeric_value(point["value"]),
            "point": point,
        })
    observations.sort(key=lambda item: item["reporting_date"])
    return {
        "observations": observations,
        "duplicate_dates": sorted(duplicate_dates),
        "invalid_dates": invalid_dates,
        "invalid_values": invalid_values,
        "repeated_count": repeated_count,
        "quality_messages": _quality_messages(
            [item["point"] for item in observations]
        ),
    }


def _prepare_priority_matrix(
    family: Mapping[str, Any],
    *,
    expected_districts: Sequence[str],
) -> dict[str, Any]:
    dates = sorted({
        reporting_date
        for reporting_date in family["dates"]
        if _valid_reporting_date(reporting_date) is not None
    })
    snapshots = {
        reporting_date: _prepare_priority_snapshot(
            family,
            reporting_date,
            expected_districts=expected_districts,
        )
        for reporting_date in dates
    }
    district_names = sorted(
        {
            str(name).strip()
            for name in expected_districts
            if str(name).strip()
        }
        or {
            str(row["district"]).strip()
            for snapshot in snapshots.values()
            for row in snapshot["districts"]
            if str(row["district"]).strip()
        },
        key=str.casefold,
    )
    observed = {
        (str(row["district"]), reporting_date): float(row["value"])
        for reporting_date, snapshot in snapshots.items()
        for row in snapshot["districts"]
    }
    values = [
        [observed.get((district, reporting_date)) for reporting_date in dates]
        for district in district_names
    ]
    coverage = [
        {
            "reporting_date": reporting_date,
            "observed_count": int(snapshot["observed_count"]),
            "expected_count": snapshot["expected_count"],
        }
        for reporting_date, snapshot in snapshots.items()
    ]
    return {
        "dates": dates,
        "districts": district_names,
        "values": values,
        "coverage": coverage,
        "snapshots": snapshots,
    }


def _priority_matrix_is_eligible(
    family: Mapping[str, Any],
    matrix: Mapping[str, Any],
    *,
    expected_districts: Sequence[str],
) -> bool:
    records = family.get("records")
    if (
        family.get("metric_label") != "Customers"
        or family.get("unit") != "count"
        or not isinstance(family.get("filters"), Mapping)
        or not isinstance(records, Sequence)
        or not records
        or any(
            str(family["filters"].get(key, "")) != expected
            for key, expected in _HISTORY_REQUIRED_FILTERS.items()
        )
        or not expected_districts
    ):
        return False
    if any(
        not _is_priority_family_record(point, family)
        for point in records
    ):
        return False
    populated_dates = [
        row for row in matrix["coverage"]
        if row["observed_count"] > 0
    ]
    return len(populated_dates) >= 2 and bool(matrix["districts"])


def _format_value(value: float) -> str:
    return f"{value:,.0f}" if value.is_integer() else f"{value:,.2f}".rstrip("0").rstrip(".")


def _format_date(value: str) -> str:
    return date.fromisoformat(value).strftime("%d %B %Y")


def _priority_matrix_figure(
    matrix: Mapping[str, Any],
    *,
    selected_district: str | None,
    unit: str,
) -> go.Figure:
    dates = list(matrix["dates"])
    date_labels = [_format_date(item) for item in dates]
    districts = list(matrix["districts"])
    values = [list(row) for row in matrix["values"]]
    maximum = max(
        (float(value) for row in values for value in row if value is not None),
        default=1.0,
    )
    maximum = max(maximum, 1.0)
    figure = go.Figure(go.Heatmap(
        x=date_labels,
        y=districts,
        z=values,
        zmin=0,
        zmax=maximum,
        colorscale=[
            [0.0, "#173642"],
            [0.16, "#155B68"],
            [0.38, "#168A88"],
            [0.62, "#31B59A"],
            [0.82, "#A5CF75"],
            [1.0, "#F2C45B"],
        ],
        xgap=3,
        ygap=2,
        showscale=True,
        colorbar=dict(
            title=dict(
                text=f"Customers<br>({esc(unit)})",
                side="right",
                font=dict(color="#F1F6F7", size=12),
            ),
            thickness=18,
            len=0.82,
            outlinewidth=0,
            tickformat="~s",
            tickfont=dict(color="#D5E4E7", size=11),
            bgcolor="rgba(13,39,49,.92)",
            bordercolor="rgba(255,255,255,.12)",
            borderwidth=1,
        ),
        customdata=[
            [
                [_format_date(reporting_date), _format_value(float(value)), unit]
                if value is not None else
                [_format_date(reporting_date), "No observation", unit]
                for reporting_date, value in zip(dates, row)
            ]
            for row in values
        ],
        hoverongaps=False,
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Reporting date: %{customdata[0]}<br>"
            "Recorded customers: %{customdata[1]} %{customdata[2]}"
            "<extra></extra>"
        ),
        name="Recorded customers",
        showlegend=False,
    ))

    missing_x = []
    missing_y = []
    selected_x = []
    selected_y = []
    for row_index, district in enumerate(districts):
        for column_index, date_label in enumerate(date_labels):
            value = values[row_index][column_index]
            if value is None:
                missing_x.append(date_label)
                missing_y.append(district)
            elif district == selected_district:
                selected_x.append(date_label)
                selected_y.append(district)
    figure.add_trace(go.Scatter(
        x=missing_x,
        y=missing_y,
        mode="markers+text",
        marker=dict(
            symbol="square",
            size=18,
            color="#19323D",
            line=dict(color="#78909A", width=1.2),
        ),
        text=["—"] * len(missing_x),
        textposition="middle center",
        textfont=dict(color="#D7E1E4", size=11),
        name="No observation",
        customdata=[
            [district, date_labels[date_labels.index(label)]]
            for district, label in zip(missing_y, missing_x)
        ],
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>Reporting date: %{x}<br>"
            "No observation reported · missing, not zero<extra></extra>"
        ),
        showlegend=True,
    ))
    figure.add_trace(go.Scatter(
        x=selected_x,
        y=selected_y,
        mode="markers",
        marker=dict(
            symbol="square-open",
            size=22,
            color="#F3D27A",
            line=dict(color="#FFF1BF", width=2.5),
        ),
        name="Selected district",
        hoverinfo="skip",
        showlegend=True,
    ))

    figure.update_layout(
        height=max(690, min(930, 23 * len(districts) + 165)),
        margin=dict(l=12, r=118, t=76, b=110),
        plot_bgcolor="#152F3A",
        paper_bgcolor="#102B35",
        font=dict(
            family="Plus Jakarta Sans, Segoe UI, Arial, sans-serif",
            color="#E5EEF0",
            size=12,
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.035,
            xanchor="left",
            x=0,
            bgcolor="rgba(13,39,49,.86)",
            bordercolor="rgba(255,255,255,.12)",
            borderwidth=1,
            font=dict(color="#E5EEF0", size=11),
            itemclick=False,
            itemdoubleclick=False,
        ),
        hoverlabel=dict(
            bgcolor="#091D25",
            bordercolor="#52727B",
            font=dict(color="#FFFFFF", size=12),
        ),
        xaxis=dict(
            type="category",
            categoryorder="array",
            categoryarray=date_labels,
            tickangle=-28,
            tickfont=dict(color="#E5EEF0", size=11),
            showgrid=False,
            linecolor="rgba(188,211,216,.22)",
            title=dict(
                text="Actual reporting date · categorical spacing",
                font=dict(color="#B9CBD0", size=11),
                standoff=18,
            ),
        ),
        yaxis=dict(
            type="category",
            categoryorder="array",
            categoryarray=districts,
            autorange="reversed",
            tickfont=dict(color="#D8E4E8", size=11),
            showgrid=False,
            automargin=True,
            title=None,
        ),
    )
    return style_chart(
        figure,
        figure.layout.height,
        paper_bgcolor="#102B35",
        plot_bgcolor="#152F3A",
    )


def _historical_coverage_html(
    coverage: Sequence[Mapping[str, Any]],
) -> str:
    if not coverage:
        return ""
    rows = []
    for item in coverage:
        expected = item.get("expected_count")
        observed = int(item["observed_count"])
        total = f" of {int(expected)}" if expected is not None else ""
        rows.append(
            "<tr>"
            f"<td>{esc(_format_date(str(item['reporting_date'])))}</td>"
            f'<td><strong>{observed}{total}</strong></td>'
            "</tr>"
        )
    return (
        '<div style="margin-top:14px;padding:14px 16px;border:1px solid #DCE7EA;'
        'border-radius:14px;background:#F7FAFB">'
        '<div style="font-size:13px;font-weight:700;color:#163D4B;margin-bottom:8px">'
        "Named-district reporting coverage</div>"
        '<table style="width:100%;border-collapse:collapse;font-size:12px;color:#425B64">'
        "<thead><tr>"
        '<th style="text-align:left;padding:7px 8px;border-bottom:1px solid #DCE7EA">'
        "Reporting date</th>"
        '<th style="text-align:right;padding:7px 8px;border-bottom:1px solid #DCE7EA">'
        "Named districts observed</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
        '<div style="font-size:11px;color:#667D85;margin-top:8px">'
        "Coverage counts are shown separately from customer-count magnitude."
        "</div></div>"
    )


def _district_distribution_figure(
    snapshot: Mapping[str, Any],
    *,
    metric: str,
    unit: str,
    reporting_date: str,
    selected_district: str | None,
) -> go.Figure:
    districts = list(snapshot["districts"])
    values = [float(item["value"]) for item in districts]
    names = [str(item["district"]) for item in districts]
    selected = [
        index for index, name in enumerate(names)
        if name == selected_district
    ]
    other = [index for index in range(len(names)) if index not in selected]
    figure = go.Figure()
    if other:
        figure.add_trace(go.Bar(
            x=[values[index] for index in other],
            y=[names[index] for index in other],
            orientation="h",
            name="Other districts",
            marker=dict(color=PALETTE["teal"], cornerradius=4),
            text=[_format_value(values[index]) for index in other],
            textposition="outside",
            textfont=dict(color=PALETTE["ink2"], size=10),
            cliponaxis=False,
            customdata=[[reporting_date, metric, unit] for _ in other],
            hovertemplate=(
                "<b>%{y}</b><br>%{customdata[1]}: %{x:,.4~g} "
                "%{customdata[2]}<br>Reporting date: "
                "%{customdata[0]}<extra></extra>"
            ),
        ))
    if selected:
        figure.add_trace(go.Bar(
            x=[values[index] for index in selected],
            y=[names[index] for index in selected],
            orientation="h",
            name="Selected district",
            marker=dict(
                color=PALETTE["sun"],
                line=dict(color="#D49527", width=1),
                cornerradius=4,
            ),
            text=[_format_value(values[index]) for index in selected],
            textposition="outside",
            textfont=dict(color=PALETTE["ink"], size=10),
            cliponaxis=False,
            customdata=[[reporting_date, metric, unit] for _ in selected],
            hovertemplate=(
                "<b>%{y} · selected district</b><br>"
                "%{customdata[1]}: %{x:,.4~g} %{customdata[2]}<br>"
                "Reporting date: %{customdata[0]}<extra></extra>"
            ),
        ))
    figure.update_layout(
        barmode="overlay",
        bargap=0.28,
        height=max(440, min(len(names) * 25 + 125, 950)),
        margin=dict(l=12, r=74, t=38, b=52),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0,
        ),
        xaxis=dict(
            title=f"{metric} ({unit})",
            rangemode="tozero",
            showgrid=True,
            gridcolor="#E9EFF1",
            zeroline=False,
            ticks="outside",
            linecolor="#D5DFE5",
            tickformat=",.4~g",
        ),
        yaxis=dict(
            title=None,
            categoryorder="array",
            categoryarray=names,
            autorange="reversed",
            showgrid=False,
            tickfont=dict(size=11, color=PALETTE["ink2"]),
            automargin=True,
        ),
        plot_bgcolor="white",
        paper_bgcolor="rgba(0,0,0,0)",
        hoverlabel=dict(bgcolor=PALETTE["ink"], font=dict(color="white")),
    )
    return style_chart(
        figure,
        figure.layout.height,
        margin=dict(l=12, r=74, t=38, b=52),
    )


def _priority_history_figure(
    history: Mapping[str, Any],
    *,
    metric: str,
    unit: str,
    selected_date: str,
) -> go.Figure:
    observations = history["observations"]
    dates = [item["reporting_date"] for item in observations]
    values = [float(item["value"]) for item in observations]
    figure = go.Figure(go.Scatter(
        x=dates,
        y=values,
        mode="lines+markers",
        line=dict(color=PALETTE["teal"], width=3, shape="linear"),
        marker=dict(
            color=PALETTE["teal"],
            size=9,
            line=dict(color="white", width=2),
        ),
        name="Observed values",
        customdata=[[metric, unit] for _ in dates],
        hovertemplate=(
            "<b>%{x|%d %b %Y}</b><br>%{customdata[0]}: %{y:,.4~g} "
            "%{customdata[1]}<extra></extra>"
        ),
    ))
    selected_observations = [
        item for item in observations
        if item["reporting_date"] == selected_date
    ]
    if selected_observations:
        figure.add_trace(go.Scatter(
            x=[selected_observations[0]["reporting_date"]],
            y=[float(selected_observations[0]["value"])],
            mode="markers",
            marker=dict(
                color=PALETTE["sun"],
                size=14,
                line=dict(color="#FFFFFF", width=2),
            ),
            name="Selected reporting date",
            hovertemplate=(
                "<b>%{x|%d %b %Y} · selected</b><br>"
                f"{metric}: %{{y:,.4~g}} {unit}<extra></extra>"
            ),
        ))
    figure.update_layout(
        height=320,
        margin=dict(l=58, r=24, t=44, b=58),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0,
        ),
        xaxis=dict(
            title="Observed reporting date",
            type="date",
            showgrid=False,
            ticks="outside",
            linecolor="#D5DFE5",
            tickformat="%b %Y",
        ),
        yaxis=dict(
            title=f"{metric} ({unit})",
            rangemode="tozero",
            showgrid=True,
            gridcolor="#E9EFF1",
            zeroline=False,
        ),
        plot_bgcolor="white",
        paper_bgcolor="rgba(0,0,0,0)",
        hoverlabel=dict(bgcolor=PALETTE["ink"], font=dict(color="white")),
    )
    return style_chart(figure, 320, margin=dict(l=58, r=24, t=44, b=58))


def _widget_choice(
    label: str,
    options: Sequence[str],
    *,
    key: str,
    default: str | None = None,
    format_func: Any = None,
    disabled: bool = False,
) -> str:
    if not options:
        raise ValueError(f"{label} has no observed options.")
    current = st.session_state.get(key, default or options[0])
    if current not in options:
        current = default if default in options else options[0]
    if st.session_state.get(key) != current:
        st.session_state[key] = current
    arguments = {}
    if format_func is not None:
        arguments["format_func"] = format_func
    return st.selectbox(
        label,
        list(options),
        key=key,
        disabled=disabled,
        **arguments,
    )


def _widget_pill_choice(
    label: str,
    options: Sequence[str],
    *,
    key: str,
    default: str | None = None,
    disabled: bool = False,
) -> str:
    if not options:
        raise ValueError(f"{label} has no observed options.")
    current = st.session_state.get(key, default or options[0])
    if current not in options:
        current = default if default in options else options[0]
    if st.session_state.get(key) != current:
        st.session_state[key] = current
    selected = st.pills(
        label,
        options=list(options),
        selection_mode="single",
        default=current,
        key=key,
        disabled=disabled,
        width="stretch",
    )
    return selected or current


def _render_controls(
    families: Sequence[Mapping[str, Any]],
    source_version: str,
    *,
    filter_slots: Sequence[Any] | None = None,
    date_slot: Any | None = None,
) -> Mapping[str, Any]:
    page = str(families[0]["page"])
    measure_groups: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for item in families:
        measure_groups[
            (str(item["metric_label"]), str(item["unit"]))
        ].append(item)

    def measure_rank(measure: tuple[str, str]) -> tuple[Any, ...]:
        candidates = measure_groups[measure]
        latest_date = max(item["dates"][-1] for item in candidates)
        return (
            latest_date,
            sum(item["dates"][-1] == latest_date for item in candidates),
            sum(len(item["dates"]) for item in candidates),
            measure[0].casefold(),
            measure[1].casefold(),
        )

    metric, unit = max(
        measure_groups,
        key=measure_rank,
    )
    measure_families = [
        item for item in families
        if item["metric_label"] == metric and item["unit"] == unit
    ]
    hidden_scope_defaults = {
        "Account/Policy Status": "Active",
        "Location": "All",
    }
    fixed_scope_filters = {
        dimension: expected
        for dimension, expected in hidden_scope_defaults.items()
        if any(dimension in item["filters"] for item in measure_families)
    }
    measure_families = [
        item for item in measure_families
        if all(
            str(item["filters"].get(dimension, expected)) == expected
            for dimension, expected in hidden_scope_defaults.items()
        )
    ]
    visible_dimensions = {"Institution Type", "Age Segment", "Gender"}
    additional_dimensions = {
        str(key)
        for item in measure_families
        for key in item["filters"]
        if key not in hidden_scope_defaults and key not in visible_dimensions
    }
    for dimension in additional_dimensions:
        options = {
            str(item["filters"][dimension])
            for item in measure_families
            if dimension in item["filters"]
        }
        if len(options) == 1:
            fixed_scope_filters[dimension] = next(iter(options))
        elif "All" in options:
            fixed_scope_filters[dimension] = "All"
        else:
            st.info(
                f"The {dimension} filter has multiple observed values and cannot "
                "be represented in these controls; no scope has been selected."
            )
            return {}
    if not measure_families:
        st.info(
            "No eligible district series uses the standard Active and Location: All "
            "scope for this service."
        )
        return {}

    if filter_slots is None or date_slot is None:
        filter_columns = st.columns(3, gap="small")
        date_columns = st.columns(3, gap="small")
        filter_slots = filter_columns
        date_slot = date_columns[2]

    chosen_filters: dict[str, str] = dict(fixed_scope_filters)
    dimensions = ("Institution Type", "Age Segment", "Gender")
    for index, dimension in enumerate(dimensions):
        eligible = [
            item for item in measure_families
            if all(
                str(item["filters"].get(key, "")) == value
                for key, value in chosen_filters.items()
            )
        ]
        options = sorted({
            str(item["filters"][dimension])
            for item in eligible
            if dimension in item["filters"]
        }, key=str.casefold)
        available_options = options or ["Not reported"]
        disabled = len(options) != 0 and len(options) == 1
        filter_key = (
            f"nbr_priority_filter_{source_version}_{page}_{metric}_{unit}_"
            f"{hashlib.sha1(dimension.encode()).hexdigest()[:8]}"
        )
        with filter_slots[index].container():
            selected_value = _widget_pill_choice(
                dimension,
                available_options,
                key=filter_key,
                default="All" if "All" in options else None,
                disabled=disabled or not options,
            )
        if options:
            chosen_filters[dimension] = selected_value
    exact_filters_key = _filters_key(chosen_filters)
    family = next((
        item for item in measure_families
        if _filters_key(item["filters"]) == exact_filters_key
    ), None)
    if family is None:
        st.info("No eligible series matches this exact filter scope.")
        return {}
    date_key = f"nbr_priority_date_{source_version}_{page}_{metric}_{exact_filters_key}"
    with date_slot.container():
        reporting_date = _widget_choice(
            "Reporting date",
            family["dates"],
            key=date_key,
        )
    return {**family, "selected_date": reporting_date}


def _render_scope_details(
    snapshot: Mapping[str, Any],
    history: Mapping[str, Any],
    *,
    reference_error: str | None,
    historical_coverage: Sequence[Mapping[str, Any]] = (),
) -> None:
    with st.expander("Data coverage and qualifications"):
        if snapshot["expected_count"] is not None:
            st.caption(
                f"Named districts reported: {snapshot['observed_count']} of "
                f"{snapshot['expected_count']} · "
                f"{snapshot['missing_count']} not reported for this exact scope/date."
            )
        else:
            st.caption(
                f"Named districts reported: {snapshot['observed_count']}. "
                "Reference coverage could not be verified."
            )
        if historical_coverage:
            st.markdown(
                _historical_coverage_html(historical_coverage),
                unsafe_allow_html=True,
            )
        if snapshot["unknown"]:
            st.caption(
                f"Unknown-geography observations kept separate: "
                f"{len(snapshot['unknown'])}."
            )
        if snapshot["unmatched"]:
            st.caption(
                "Geography labels not matched to the district reference, kept separate: "
                + ", ".join(snapshot["unmatched"])
            )
        for message in snapshot["quality_messages"]:
            st.warning(message)
        exclusions = (
            snapshot["duplicate_count"]
            + snapshot["invalid_count"]
            + snapshot["repeated_count"]
        )
        if exclusions:
            st.warning(
                f"Excluded from district values: {snapshot['duplicate_count']} "
                f"duplicate/conflicting rows, {snapshot['invalid_count']} invalid "
                f"values, and {snapshot['repeated_count']} repeated-snapshot rows."
            )
        if (
            history["duplicate_dates"]
            or history["invalid_dates"]
            or history["invalid_values"]
            or history["repeated_count"]
        ):
            st.warning(
                "Some observations were excluded from the selected district history "
                "because of duplicate dates, invalid dates, invalid values, or "
                "repeated snapshots."
            )
        for message in history["quality_messages"]:
            st.warning(message)
        if reference_error:
            st.warning(f"District reference unavailable: {reference_error}")
        if not any((
            snapshot["unknown"],
            snapshot["unmatched"],
            exclusions,
            history["duplicate_dates"],
            history["invalid_dates"],
            history["invalid_values"],
            history["repeated_count"],
            reference_error,
        )):
            st.caption("No additional data-quality qualifications were detected in this view.")
        st.caption(
            "Counts are NBR administrative observations, not verified unique-person "
            "totals or population-adjusted measures. Ordering is descriptive only."
        )


def render_nbr_priority_explorer(
    load_page_data: Callable[
        [str],
        tuple[
            Sequence[Mapping[str, Any]],
            str,
            Mapping[str, Any],
        ],
    ],
    *,
    page_labels: Mapping[str, str],
    load_scope_data: Callable[
        [str, tuple[tuple[str, str, str], ...]],
        tuple[Sequence[Mapping[str, Any]], str, Mapping[str, Any]],
    ] | None = None,
    selected_district: str | None = None,
) -> None:
    header_slot = st.empty()
    st.markdown("")
    page_options = sorted(page_labels)
    page_key = "nbr_priority_page"
    with st.container(key="card_nbr_priority_controls"):
        card_title(
            "Choose evidence",
            "The latest eligible count measure is selected automatically. Choose an "
            "observed filter scope and reporting date.",
        )
        first_row = st.columns(3, gap="small")
        filter_slots = [column.empty() for column in first_row]
        second_row = st.columns(3, gap="small")
        with second_row[0]:
            selected_page = _widget_choice(
                "Service area",
                page_options,
                key=page_key,
                default="inclusion" if "inclusion" in page_options else None,
                format_func=lambda value: page_labels.get(value, value),
            )
        district_slot = second_row[1].empty()
        date_slot = second_row[2].empty()
    try:
        page_data, source_version, _ = load_page_data(selected_page)
    except (RuntimeError, ValueError, OSError, PyMongoError) as error:
        with header_slot.container():
            page_header(
                "Priority Explorer",
                "Explore NBR-reported district observations and decide what merits closer review.",
                pill="NBR Supply",
                pill_badge="BETA",
                size="tall",
                below_html=_priority_header_html(None, None, None, page_labels),
            )
        with st.container(key="card_nbr_priority_unavailable"):
            card_title("NBR data could not be loaded")
            st.error(
                "Priority Explorer requires validated NBR observations. "
                "Use Refresh NBR observations in the sidebar to try again."
            )
            st.caption(str(error))
        return

    families = (
        _priority_catalog_families(page_data, page=selected_page)
        if load_scope_data is not None
        else [
            family for family in _priority_families(page_data)
            if family["page"] == selected_page
        ]
    )
    if not families:
        with header_slot.container():
            page_header(
                "Priority Explorer",
                "Explore NBR-reported district observations and decide what merits closer review.",
                pill="NBR Supply",
                pill_badge="BETA",
                size="tall",
                below_html=_priority_header_html(None, None, None, page_labels),
            )
        with st.container(key="card_nbr_priority_unavailable"):
            card_title("No comparable district observations are available")
            st.info(
                "This view requires numeric district-table observations with a "
                "documented count unit and exact reporting scope."
            )
        return

    family = _render_controls(
        families,
        source_version,
        filter_slots=filter_slots,
        date_slot=date_slot,
    )
    if not family:
        with header_slot.container():
            page_header(
                "Priority Explorer",
                "Explore NBR-reported district observations and decide what merits closer review.",
                pill="NBR Supply",
                pill_badge="BETA",
                size="tall",
                below_html=_priority_header_html(None, None, None, page_labels),
            )
        return
    try:
        if load_scope_data is not None:
            family_points, _, _ = load_scope_data(
                selected_page,
                tuple(family["scope_keys"]),
            )
            family["records"] = [
                point for point in family_points
                if _is_priority_family_record(point, family)
            ]
    except (RuntimeError, ValueError, OSError, PyMongoError) as error:
        with st.container(key="card_nbr_priority_unavailable"):
            card_title("Selected NBR observations could not be loaded")
            st.error(
                "The exact selected metric and reporting scopes could not be read. "
                "No alternate data has been substituted."
            )
            st.caption(str(error))
        return

    expected_districts: tuple[str, ...] = ()
    reference_error = None
    try:
        from src.data_sources.mongodb_district_explorer import load_district_reference

        expected_districts = tuple(load_district_reference())
    except (OSError, ValueError) as error:
        reference_error = str(error)

    latest_date = family["dates"][-1]
    snapshot = _prepare_priority_snapshot(
        family,
        family["selected_date"],
        expected_districts=expected_districts,
    )
    latest_snapshot = (
        snapshot
        if family["selected_date"] == latest_date
        else _prepare_priority_snapshot(
            family,
            latest_date,
            expected_districts=expected_districts,
        )
    )
    historical_matrix = _prepare_priority_matrix(
        family,
        expected_districts=expected_districts,
    )
    with header_slot.container():
        page_header(
            "Priority Explorer",
            "Explore NBR-reported district observations and decide what merits closer review.",
            pill="NBR Supply",
            pill_badge="BETA",
            size="tall",
            below_html=_priority_header_html(
                family,
                latest_snapshot,
                latest_date,
                page_labels,
            ),
        )
    st.markdown("")

    if not snapshot["districts"]:
        with district_slot.container():
            _widget_choice(
                "Inspect a district",
                ["Not available"],
                key=f"nbr_priority_district_unavailable_{source_version}",
                disabled=True,
            )
        with st.container(key="card_nbr_priority_empty_snapshot"):
            card_title("No usable named-district observations for this date")
            st.info(
                "No eligible named-district values were available for the selected "
                "measure and exact scope. No other date or filter has been substituted."
            )
            _render_scope_details(
                snapshot,
                {
                    "duplicate_dates": [],
                    "invalid_dates": 0,
                    "invalid_values": 0,
                    "repeated_count": 0,
                    "quality_messages": [],
                },
                reference_error=reference_error,
                historical_coverage=historical_matrix["coverage"],
            )
        return

    districts = [str(item["district"]) for item in snapshot["districts"]]
    selection_key = (
        f"nbr_priority_district_{source_version}_"
        f"{hashlib.sha1((family['filters_key'] + family['page'] + family['metric_label']).encode()).hexdigest()[:10]}"
    )
    current_district = st.session_state.get(selection_key, selected_district)
    if current_district not in districts:
        current_district = districts[0]
    if st.session_state.get(selection_key) != current_district:
        st.session_state[selection_key] = current_district
    with district_slot.container():
        selected_district = _widget_choice(
            "Inspect a district",
            districts,
            key=selection_key,
            default=current_district,
        )
    selected_value = next(
        float(item["value"])
        for item in snapshot["districts"]
        if item["district"] == selected_district
    )
    history = _prepare_priority_history(family, selected_district)
    st.markdown("")

    with st.container(key="card_nbr_priority_distribution"):
        card_title(
            "District observations",
            "Reported values are ordered from lower to higher for comparison—not as a ranking of need.",
        )
        st.plotly_chart(
            _district_distribution_figure(
                snapshot,
                metric=str(family["metric_label"]),
                unit=str(family["unit"]),
                reporting_date=str(family["selected_date"]),
                selected_district=selected_district,
            ),
            width="stretch",
            key=(
                f"nbr_priority_distribution_{source_version}_"
                f"{family['page']}_{family['metric_label']}_"
                f"{family['selected_date']}_"
                f"{hashlib.sha1(family['filters_key'].encode()).hexdigest()[:8]}"
            ),
            config={"displayModeBar": False},
        )

    if _priority_matrix_is_eligible(
        family,
        historical_matrix,
        expected_districts=expected_districts,
    ):
        with st.container(key="card_nbr_priority_reporting_matrix"):
            card_title(
                "District Observations Across Reporting Dates",
                "Compare recorded customer counts for the same districts and exact filter scope "
                "across actual reporting snapshots.",
            )
            st.markdown(
                '<div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;'
                'margin:8px 0 14px;padding:10px 13px;border-radius:12px;'
                'background:#F1F6F7;border:1px solid #DCE7EA;color:#425B64;font-size:12px">'
                f'<span style="display:inline-flex;align-items:center;gap:6px;'
                'font-weight:700;color:#163D4B">'
                '<span style="width:9px;height:9px;border-radius:50%;'
                'background:#F2B84B;display:inline-block"></span>'
                f'Current focus: {esc(selected_district)}</span>'
                f'<span>{len(historical_matrix["dates"])} observed reporting dates</span>'
                f'<span>{len(historical_matrix["districts"])} named districts</span>'
                "</div>"
                '<div style="margin:0 0 12px;color:#50666E;font-size:12.5px;line-height:1.55">'
                "Each cell is an NBR-reported administrative count—not a population-adjusted "
                "financial-inclusion rate or a verified unique-person total. Dates are "
                "irregularly spaced; color shows count magnitude, not financial need or priority."
                "</div>",
                unsafe_allow_html=True,
            )
            st.plotly_chart(
                _priority_matrix_figure(
                    historical_matrix,
                    selected_district=selected_district,
                    unit=str(family["unit"]),
                ),
                width="stretch",
                key=(
                    f"nbr_priority_reporting_matrix_{source_version}_"
                    f"{family['page']}_{family['metric_label']}_"
                    f"{hashlib.sha1(family['filters_key'].encode()).hexdigest()[:8]}"
                ),
                config={"displayModeBar": False},
            )

    with st.container(key="card_nbr_priority_history"):
        card_title(
            f"{selected_district} · observed history",
            "Only actual reporting dates for this district and exact selected scope are shown.",
        )
        st.markdown(
            f'<div class="kpi-label" style="min-height:0">'
            f'{esc(selected_district)} · {esc(str(family["metric_label"]))}'
            f'</div><div class="kpi-value" style="color:{PALETTE["teal"]};'
            f'margin:4px 0 12px">'
            f'{esc(_format_value(selected_value))}'
            f'<small>{esc(str(family["unit"]))}</small></div>',
            unsafe_allow_html=True,
        )
        st.caption(
            f"Reported on {_format_date(str(family['selected_date']))}; "
            "this is an administrative count, not a population-adjusted rate."
        )
        if len(history["observations"]) >= 2:
            st.plotly_chart(
                _priority_history_figure(
                    history,
                    metric=str(family["metric_label"]),
                    unit=str(family["unit"]),
                    selected_date=str(family["selected_date"]),
                ),
                width="stretch",
                key=(
                    f"nbr_priority_history_{source_version}_{selected_district}_"
                    f"{family['page']}_{family['metric_label']}_"
                    f"{hashlib.sha1(family['filters_key'].encode()).hexdigest()[:8]}"
                ),
                config={"displayModeBar": False},
            )
        elif history["observations"]:
            item = history["observations"][0]
            st.info(
                f"One usable reporting date is available: {item['reporting_date']} · "
                f"{_format_value(float(item['value']))} {family['unit']}. "
                "A historical trend is not shown from a single observation."
            )
        else:
            st.info(
                "No comparable historical observations are available for this "
                "district in the selected exact scope."
            )

    _render_scope_details(
        snapshot,
        history,
        reference_error=reference_error,
        historical_coverage=historical_matrix["coverage"],
    )
