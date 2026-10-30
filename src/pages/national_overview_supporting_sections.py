"""Modular supporting sections for the National Overview page.

This module intentionally stays isolated from the shared page renderer and the
first evidence section currently being developed elsewhere. It focuses on the
sections below that evidence block and reuses the project's existing data
loaders, labels, and style tokens without altering any shared files.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

csv.field_size_limit(10_000_000)

import pandas as pd
import plotly.graph_objects as go

from src import data
from src.indicators import BY_COLUMN
from src.styles import PALETTE, style_chart

ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = ROOT / "data" / "processed"


def _csv_paths_for_nbr_review() -> list[Path]:
    return sorted(PROCESSED_DIR.glob("nbr-finscope-contextualization-review*.csv"))


def load_financial_service_network_candidates() -> pd.DataFrame:
    """Return the available NBR branch/agent candidate metadata in the project.

    These rows are metadata-only in the current processed data: they identify the
    candidate metrics and their filters, but not all have matching numeric values in
    the project snapshot. This is reflected in the output and avoids fabricating
    missing national observations.
    """

    rows: list[dict[str, Any]] = []
    for path in _csv_paths_for_nbr_review():
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for item in reader:
                page = (item.get("page") or "").strip()
                metric = (item.get("metric_label") or "").strip()
                if page not in {"branches", "agents"}:
                    continue
                if metric not in {"Total Branches", "Total Agents"}:
                    continue
                filters = item.get("filters_json") or "{}"
                try:
                    filters_dict = json.loads(filters) if isinstance(filters, str) else filters
                except json.JSONDecodeError:
                    filters_dict = {}
                rows.append(
                    {
                        "source_page": page,
                        "metric_label": metric,
                        "reporting_date": item.get("reporting_date"),
                        "institution_type": filters_dict.get("Institution Type") or filters_dict.get("Institution Type "),
                        "branch_status": filters_dict.get("Branch Status"),
                        "agent_status": filters_dict.get("Agent Status"),
                        "location": filters_dict.get("Location"),
                        "filters": filters_dict,
                        "value_raw": item.get("value_raw"),
                        "value_numeric": item.get("value_numeric"),
                        "unit": item.get("unit"),
                        "unit_status": item.get("unit_status"),
                        "source_name": item.get("source_name"),
                        "source_url": item.get("source_url"),
                        "run_id": item.get("run_id"),
                        "data_quality_status": item.get("data_quality_status"),
                    }
                )

    if not rows:
        return pd.DataFrame(
            columns=[
                "source_page",
                "metric_label",
                "reporting_date",
                "institution_type",
                "branch_status",
                "agent_status",
                "location",
                "filters",
                "value_raw",
                "value_numeric",
                "unit",
                "unit_status",
                "source_name",
                "source_url",
                "run_id",
                "data_quality_status",
            ]
        )

    frame = pd.DataFrame(rows)
    frame["filters_json"] = frame["filters"].map(lambda value: json.dumps(value, sort_keys=True, ensure_ascii=False))
    deduped = frame.drop_duplicates(
        subset=[
            "source_page",
            "metric_label",
            "reporting_date",
            "institution_type",
            "filters_json",
        ],
        ignore_index=True,
    )
    return deduped.drop(columns=["filters_json"]).copy()


def build_financial_service_network_section() -> dict[str, Any]:
    """Build a structured section object with honest metadata-only service-network evidence."""

    candidates = load_financial_service_network_candidates()
    candidates["has_numeric_value"] = candidates["value_numeric"].notna() & (candidates["value_numeric"].astype(str).str.strip() != "")
    has_numeric = bool(candidates["has_numeric_value"].any())

    section = {
        "title": "The financial-service network",
        "intro": (
            "Administrative infrastructure is a useful complement to survey evidence, but it counts "
            "channels rather than people, use, affordability, or access."
        ),
        "available": has_numeric,
        "candidate_metrics": candidates.to_dict(orient="records"),
        "limit_note": (
            "Current processed national data does not contain validated national counts for these branch and "
            "agent totals, so the section stays explicit about what is known and what remains unresolved."
        )
        if not has_numeric
        else "Validated national values are present and can be surfaced once the needed extracted series are integrated.",
    }
    return section


def build_financial_service_network_figure() -> go.Figure:
    """A limitation-state figure for service-network evidence when counts are missing."""

    fig = go.Figure()
    fig.add_annotation(
        x=0.5,
        y=0.5,
        xref="paper",
        yref="paper",
        text="National branch and agent totals are not currently available in the processed national data.",
        showarrow=False,
        font=dict(size=18, color=PALETTE["ink"]),
        align="center",
    )
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    fig.update_layout(
        width=900,
        height=220,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=10, t=10, b=10),
    )
    return fig


def build_saving_resilience_frame() -> pd.DataFrame:
    national = data.read_national()
    metric_names = [
        "Does not save",
        "Has emergency funds",
        "Saves with a group",
        "Currently uses Umurenge SACCO",
        "Currently uses a savings group",
    ]
    rows = []
    for indicator in metric_names:
        row = national.loc[national["Indicator"].eq(indicator)]
        if row.empty:
            continue
        row = row.iloc[0]
        rows.append(
            {
                "indicator": indicator,
                "variable": row.get("Source variable"),
                "value": float(row.get("Estimate (%)")),
                "label": BY_COLUMN.get(row.get("Indicator"), {}).get("label", indicator),
                "short": BY_COLUMN.get(row.get("Indicator"), {}).get("short", indicator),
                "interpretation": row.get("Interpretation"),
            }
        )
    frame = pd.DataFrame(rows)
    return frame.sort_values("value", ascending=False).reset_index(drop=True)


def build_saving_resilience_figure(frame: pd.DataFrame | None = None) -> go.Figure:
    data_frame = frame if frame is not None else build_saving_resilience_frame()
    if data_frame.empty:
        return build_financial_service_network_figure()

    palette = [
        "#DB6A4E",
        "#7B5EC2",
        "#4C9A52",
        "#C0508A",
        "#8DA03A",
    ]
    fig = go.Figure(
        go.Bar(
            x=data_frame["value"],
            y=data_frame["indicator"],
            orientation="h",
            marker=dict(color=palette[: len(data_frame)]),
            text=[f"{value:.1f}%" for value in data_frame["value"]],
            textposition="outside",
            cliponaxis=False,
            hovertemplate=(
                "<b>%{y}</b><br>%{x:.2f}% of adults<extra></extra>"
            ),
        )
    )
    fig.update_layout(
        bargap=0.32,
        margin=dict(l=8, r=18, t=8, b=8),
        xaxis=dict(range=[0, 100], ticksuffix="%", gridcolor=PALETTE["grid"], zeroline=False),
        yaxis=dict(showgrid=False, automargin=True),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return style_chart(fig, 350)


def build_barrier_section() -> dict[str, Any]:
    barriers = data.read_barriers_national()
    if barriers is None or barriers.empty:
        return {
            "title": "Reported barriers",
            "population_note": "No national barriers data is available in the current processed files.",
            "rows": [],
            "figure": build_financial_service_network_figure(),
        }

    rows = barriers.sort_values("Weighted share (%)", ascending=False).copy()
    rows["Reason (short)"] = rows["Reason (short)"].astype(str)
    rows["Barrier family"] = rows["Barrier family"].astype(str)
    rows = rows[["Reason (short)", "Barrier family", "Weighted share (%)", "Respondents"]].copy()
    rows = rows.reset_index(drop=True)
    return {
        "title": "Reported barriers",
        "population_note": (
            "Share of respondents without an account who reported each barrier. The denominator is "
            "people without an account who provided a reason, not all Rwandan adults."
        ),
        "rows": rows.to_dict(orient="records"),
        "figure": build_barrier_figure(rows),
    }


def build_barrier_figure(frame: pd.DataFrame | list[dict[str, Any]] | None = None) -> go.Figure:
    rows = frame if frame is not None else build_barrier_section()["rows"]
    if rows is None:
        return build_financial_service_network_figure()
    if isinstance(rows, pd.DataFrame):
        df = rows.copy()
    else:
        df = pd.DataFrame(rows)
    if df.empty:
        return build_financial_service_network_figure()

    ordered = df.sort_values("Weighted share (%)", ascending=True).reset_index(drop=True)
    fig = go.Figure(
        go.Bar(
            x=ordered["Weighted share (%)"],
            y=ordered["Reason (short)"],
            orientation="h",
            marker=dict(color=[data.BARRIER_FAMILY_COLORS.get(f, PALETTE["blue"]) for f in ordered["Barrier family"]]),
            text=[f"{value:.1f}%" for value in ordered["Weighted share (%)"]],
            textposition="outside",
            cliponaxis=False,
            hovertemplate=(
                "<b>%{y}</b><br>%{x:.2f}% of people without an account<extra></extra>"
            ),
        )
    )
    fig.update_layout(
        bargap=0.30,
        margin=dict(l=10, r=20, t=8, b=8),
        xaxis=dict(range=[0, 100], ticksuffix="%", gridcolor=PALETTE["grid"], zeroline=False),
        yaxis=dict(showgrid=False, automargin=True),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return style_chart(fig, 380)


def build_navigation_cards() -> list[dict[str, str]]:
    return [
        {
            "page": "District explorer",
            "heading": "District Explorer",
            "description": "Compare district patterns in bank account ownership, mobile money, and service access.",
        },
        {
            "page": "Population groups",
            "heading": "Population groups",
            "description": "Explore differences across gender and age groups using the same survey definitions.",
        },
        {
            "page": "Priority explorer",
            "heading": "Priority explorer",
            "description": "See where the dashboard flags relative gaps and candidate priorities for follow-up.",
        },
        {
            "page": "Methodology & sources",
            "heading": "Methodology & sources",
            "description": "Review source definitions, caveats, and how the study preserves survey denominators.",
        },
    ]


__all__ = [
    "build_financial_service_network_section",
    "build_financial_service_network_figure",
    "build_saving_resilience_frame",
    "build_saving_resilience_figure",
    "build_barrier_section",
    "build_barrier_figure",
    "build_navigation_cards",
    "load_financial_service_network_candidates",
]
