import math
from datetime import date
from typing import Any, Mapping, Sequence

import pandas as pd
import plotly.graph_objects as go
from plotly.colors import sample_colorscale
import streamlit as st
from pymongo.errors import PyMongoError

from src import data
from src.briefs import district_brief
from src.indicators import REGISTRY, available
from src.models.nbr_intelligence.experiment import (
    MIN_CROSS_SECTION_DISTRICTS,
    MIN_TRAINING_RATES,
    NBRObservation,
    evaluate_chronologically,
    evaluate_cross_sectionally_with_statuses,
)
from src.pages.nbr_dashboard import context_strip_html, fmt_value
from src.styles import (
    INDICATOR_THEME,
    PALETTE,
    badge,
    card_title,
    esc,
    kpi_card,
    kpi_grid,
    page_header,
    render_html,
    show_district_table,
    style_chart,
)

FEATURE_KEY = "properties.shapeName"

# Registry-driven: every indicator in the district table appears automatically.
INDICATORS = {
    item["short"]: {
        "column": item["column"],
        "title": item["label"],
        "national_label": item["national"],
        "accent": item["accent"],
        "text_accent": item["text_accent"],
        "scale": item["scale"],
        "description": item["description"],
        "interpretation": item["interpretation"],
        "polarity": item["polarity"],
        "variable": item["variable"],
    }
    for item in REGISTRY
}

_ESRI = "https://server.arcgisonline.com/ArcGIS/rest/services"
BASEMAPS = {
    "Light": {"style": "carto-positron", "dark": False},
    "Dark": {"style": "carto-darkmatter", "dark": True},
    "Streets": {"style": "open-street-map", "dark": False},
    "Satellite": {
        "style": "white-bg",
        "dark": True,
        "tiles": f"{_ESRI}/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}",
    },
    "Terrain": {
        "style": "white-bg",
        "dark": False,
        "tiles": f"{_ESRI}/World_Topo_Map/MapServer/tile/{{z}}/{{y}}/{{x}}",
    },
}
PALETTE_CHOICES = ["Indicator colours", "Viridis", "Plasma", "Cividis", "Turbo"]
SPOTLIGHTS = ["Off", "Top 5", "Bottom 5", "Both"]
NBR_INSTITUTION_COLOR_SCALES = {
    "all": [
        [0.0, "#167B76"],
        [0.28, "#20A69A"],
        [0.58, "#67C7B4"],
        [0.82, "#D39A5B"],
        [1.0, "#F3D27A"],
    ],
    "banks": [
        [0.0, "#EAF2FB"],
        [0.28, "#A9C7E8"],
        [0.58, "#6097CD"],
        [0.82, "#3267A8"],
        [1.0, "#183D70"],
    ],
    "e-money issuers": [
        [0.0, "#F2ECFA"],
        [0.28, "#C6AFE4"],
        [0.58, "#9B78CC"],
        [0.82, "#754CB0"],
        [1.0, "#482876"],
    ],
    "insurance": [
        [0.0, "#FBECEF"],
        [0.28, "#EFB3C2"],
        [0.58, "#DA7D9A"],
        [0.82, "#B94C70"],
        [1.0, "#7D2947"],
    ],
    "microfinance": [
        [0.0, "#E8F4F1"],
        [0.28, "#A6D8CA"],
        [0.58, "#66B6A1"],
        [0.82, "#318A78"],
        [1.0, "#15584E"],
    ],
    "sacco": [
        [0.0, "#FCF1E5"],
        [0.28, "#F0C99D"],
        [0.58, "#DEA05E"],
        [0.82, "#B97431"],
        [1.0, "#75451F"],
    ],
}


# --------------------------------------------------------------------------
# Data
# --------------------------------------------------------------------------
def _to_rgb(color):
    color = color.strip()
    if color.startswith("#"):
        color = color.lstrip("#")
        return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))
    values = color[color.index("(") + 1:color.index(")")].split(",")
    return tuple(float(v) for v in values[:3])


def _trace_classes():
    if hasattr(go, "Choroplethmap"):
        return go.Choroplethmap, go.Scattermap, "map"
    return go.Choroplethmapbox, go.Scattermapbox, "mapbox"


def _outline_layer(geojson, names, color, width, opacity=1.0):
    wanted = set(names)
    collection = {
        "type": "FeatureCollection",
        "features": [
            f for f in geojson["features"]
            if f["properties"].get("shapeName") in wanted
        ],
    }
    return dict(
        sourcetype="geojson",
        source=collection,
        type="line",
        color=color,
        line=dict(width=width),
        opacity=opacity,
    )


def build_map(
    df,
    geojson,
    centers,
    center,
    cfg,
    metric,
    national_est,
    selected,
    short,
    settings,
    *,
    value_unit="%",
    supply_points=(),
    nbr_style=False,
    hover_context="",
    value_range=None,
    nbr_institution=None,
):
    Choropleth, Labels, key = _trace_classes()
    base = BASEMAPS[settings["basemap"]]
    dark = base["dark"]

    scale = (
        NBR_INSTITUTION_COLOR_SCALES.get(
            str(nbr_institution or "all").strip().casefold(),
            NBR_INSTITUTION_COLOR_SCALES["all"],
        )
        if nbr_style
        else (
            cfg["scale"] if settings["palette"] == "Indicator colours"
            else settings["palette"]
        )
    )
    lo, hi = value_range or (
        float(df[metric].min()),
        float(df[metric].max()),
    )
    if hi <= lo:
        hi = lo + max(abs(lo) * 1e-6, 1e-6)

    respondents = (
        df["Valid respondents"].to_numpy()
        if "Valid respondents" in df
        else [None] * len(df)
    )
    ranks = df["rank"].to_numpy() if "rank" in df else [None] * len(df)
    differences = df["diff"].to_numpy() if "diff" in df else [None] * len(df)
    customdata = list(zip(respondents, ranks, differences))
    n = len(df)
    if nbr_style:
        hovertemplate = (
            "<b>%{location}</b><br>"
            + esc(short)
            + ": <b>%{z:,.4g}</b> "
            + esc(value_unit or "unit not specified")
            + "<br>Reporting date: "
            + esc(hover_context.split("\n", 1)[0])
            + "<br>Filters: "
            + esc(hover_context.split("\n", 1)[1] if "\n" in hover_context else "")
            + "<extra></extra>"
        )
        colorbar_title = f"{short} · {value_unit or 'unit not specified'}"
        colorbar_suffix = ""
        colorbar_tickformat = (
            ",.0f" if str(value_unit).strip().casefold() == "count"
            else ",.2~f"
        )
    elif national_est is None:
        hovertemplate = (
            "<b>%{location}</b><br>"
            + esc(short)
            + ": <b>%{z:,.4g}</b> "
            + esc(value_unit or "unit not specified")
            + "<br>Rank %{customdata[1]:.0f} of "
            + str(n)
            + "<extra></extra>"
        )
        colorbar_title = f"{short} · {value_unit or 'unit not specified'}"
        colorbar_suffix = ""
        colorbar_tickformat = None
    else:
        hovertemplate = (
            "<b>%{location}</b><br>"
            + short
            + ": <b>%{z:.1f}%</b><br>"
            + f"Rank %{{customdata[1]:.0f}} of {n} · "
            + "%{customdata[2]:+.1f} pp vs national<br>"
            + "%{customdata[0]:,.0f} respondents<extra></extra>"
        )
        colorbar_title = short
        colorbar_suffix = "%"
        colorbar_tickformat = None

    fig = go.Figure(
        Choropleth(
            geojson=geojson,
            featureidkey=FEATURE_KEY,
            locations=df["District"],
            z=df[metric],
            zmin=lo,
            zmax=hi,
            colorscale=scale,
            marker=dict(
                opacity=settings["opacity"],
                line=dict(
                    color="#6E9A96" if nbr_style else "#FFFFFF",
                    width=0.85 if nbr_style else 0.9,
                ),
            ),
            selected=dict(marker=dict(opacity=settings["opacity"])),
            unselected=dict(marker=dict(opacity=settings["opacity"])),
            customdata=customdata,
            hovertemplate=hovertemplate,
            colorbar=dict(
                title=dict(text=colorbar_title, side="top", font=dict(size=11)),
                orientation="h",
                x=0.02, y=0.04, xanchor="left", yanchor="bottom",
                len=0.34, thickness=10, nticks=4,
                ticksuffix=colorbar_suffix, outlinewidth=0,
                bgcolor="rgba(14,42,53,.78)" if dark else "rgba(255,255,255,.88)",
                tickfont=dict(size=11, color="#FFFFFF" if dark else PALETTE["ink"]),
                tickformat=colorbar_tickformat if nbr_style else None,
                xpad=12, ypad=10,
            ),
        )
    )

    if supply_points:
        marker_class = go.Scattermap if hasattr(go, "Scattermap") else go.Scattermapbox
        visible_supply = [
            point for point in supply_points
            if point.get("geography") in centers
        ]
        if visible_supply:
            values = [float(point["value"]) for point in visible_supply]
            low_supply, high_supply = min(values), max(values)
            marker_sizes = [
                11 + (
                    14 * math.sqrt((value - low_supply) / (high_supply - low_supply))
                    if high_supply > low_supply else 7
                )
                for value in values
            ]
            fig.add_trace(marker_class(
                lat=[centers[str(point["geography"])][0] for point in visible_supply],
                lon=[centers[str(point["geography"])][1] for point in visible_supply],
                text=[str(point["geography"]) for point in visible_supply],
                customdata=[[
                    point.get("metric_label", ""),
                    fmt_value(point.get("value")),
                    point.get("unit") or "unit not specified",
                    point.get("reporting_date", ""),
                    str(point["geography"]),
                ] for point in visible_supply],
                mode="markers",
                marker=dict(
                    size=marker_sizes,
                    color=PALETTE["ink2"],
                    opacity=0.86,
                ),
                selected=dict(marker=dict(opacity=0.86)),
                unselected=dict(marker=dict(opacity=0.86)),
                name="NBR supply · marker size",
                hovertemplate=(
                    "<b>%{text}</b><br>NBR · %{customdata[0]}: "
                    "<b>%{customdata[1]} %{customdata[2]}</b><br>"
                    "Reported %{customdata[3]}<extra>NBR supply</extra>"
                ),
            ))

    if settings.get("labels", False):
        span = max(hi - lo, 1e-9)
        try:
            fills = sample_colorscale(scale, [(v - lo) / span for v in df[metric]])
        except Exception:
            fills = ["rgb(128,128,128)"] * len(df)
        base_bg = 30 if dark else 240
        groups = {"#FFFFFF": [], PALETTE["ink"]: []}
        for district_name, fill in zip(df["District"], fills):
            if district_name not in centers:
                continue
            r, g, b = _to_rgb(fill)
            a = settings["opacity"]
            lum = (0.2126 * (a * r + (1 - a) * base_bg)
                   + 0.7152 * (a * g + (1 - a) * base_bg)
                   + 0.0722 * (a * b + (1 - a) * base_bg)) / 255
            groups["#FFFFFF" if lum < 0.52 else PALETTE["ink"]].append(district_name)
        for color, members in groups.items():
            if not members:
                continue
            fig.add_trace(
                Labels(
                    lat=[centers[d][0] for d in members],
                    lon=[centers[d][1] for d in members],
                    text=members,
                    mode="text",
                    textfont=dict(size=11, color=color),
                    hoverinfo="skip",
                    showlegend=False,
                )
            )

    layers = []
    if base.get("tiles"):
        layers.append(
            dict(
                below="traces",
                sourcetype="raster",
                source=[base["tiles"]],
                sourceattribution="Imagery © Esri",
            )
        )

    ranked = df.sort_values(metric, ascending=False)["District"].tolist()
    spot = settings["spotlight"]
    if nbr_style:
        layers.append(_outline_layer(
            geojson,
            [
                feature["properties"].get("shapeName", "")
                for feature in geojson["features"]
            ],
            "#78918F",
            0.8,
            0.7,
        ))
    if spot in ("Top 5", "Both"):
        layers.append(_outline_layer(geojson, ranked[:5], "#FFFFFF" if dark else PALETTE["ink"], 2.4))
    if spot in ("Bottom 5", "Both"):
        layers.append(_outline_layer(geojson, ranked[-5:], PALETTE["coral"], 2.4))

    layers.append(_outline_layer(
        geojson,
        [selected],
        "#F8F5EA" if nbr_style else PALETTE["ink"],
        7,
        0.85 if nbr_style else 0.55,
    ))
    layers.append(_outline_layer(
        geojson,
        [selected],
        "#F3D27A" if nbr_style else PALETTE["sun"],
        3.4,
    ))

    fig.update_layout(
        **{
            key: dict(
                style=base["style"],
                center=dict(lat=center[0], lon=center[1]),
                zoom=settings["zoom"],
                pitch=settings["tilt"],
                bearing=settings["rotation"],
                layers=layers,
            )
        }
    )
    fig.update_layout(
        height=700,
        margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Plus Jakarta Sans, Arial, sans-serif", color=PALETTE["ink"]),
        hoverlabel=dict(
            bgcolor=PALETTE["ink"], bordercolor=PALETTE["ink"],
            font=dict(family="Plus Jakarta Sans, Arial, sans-serif", color="#FFFFFF", size=12.5),
        ),
        uirevision=settings.get(
            "uirevision",
            f"{settings['basemap']}-{settings['tilt']}-{settings['rotation']}",
        ),
        dragmode="pan",
    )
    return fig


# --------------------------------------------------------------------------
# Small UI pieces
# --------------------------------------------------------------------------
def _meter_pos(value, lo, hi):
    if hi <= lo:
        return 50.0
    return max(3.0, min(97.0, (value - lo) / (hi - lo) * 100))


def _inspector_html(row, cfg, metric, national_est, lo, hi, n):
    est = float(row[metric])
    diff = est - national_est
    arrow = "▲" if diff >= 0 else "▼"
    margin = data.moe_pp(est, row["Valid respondents"])
    verdict = (
        badge("Difference larger than the sampling margin", "ok")
        if abs(diff) > margin else
        badge("Difference within the sampling margin", "warn")
    )
    return f"""
    <div style="--accent:{cfg['accent']};--accent-text:{cfg['text_accent']}">
      <div class="insp-top">
        <div class="insp-name">{esc(row['District'])}</div>
        <div class="insp-rank">#{int(row['rank'])} of {n}</div>
      </div>
      <div class="insp-value">{est:.1f}<span>%</span></div>
      <div class="insp-sub">{esc(cfg['title'])} · <span class="moe">±{margin:.1f} pp indicative margin</span></div>
      <div class="meter">
        <div class="meter-track"></div>
        <div class="meter-mark" style="left:{_meter_pos(national_est, lo, hi):.1f}%">National</div>
        <div class="meter-dot" style="left:{_meter_pos(est, lo, hi):.1f}%"></div>
      </div>
      <div class="meter-ends"><span>Lowest {lo:.1f}%</span><span>Highest {hi:.1f}%</span></div>
      <div class="insp-grid">
        <div><b>{national_est:.1f}%</b><span>National</span></div>
        <div><b>{arrow} {abs(diff):.1f} pp</b><span>{'Above' if diff >= 0 else 'Below'} national</span></div>
        <div><b>{int(row['Valid respondents']):,}</b><span>Respondents</span></div>
      </div>
      <div style="margin-top:12px">{verdict}</div>
    </div>
    """


def _jump_to(name):
    st.session_state["dx_district"] = name


def _filtered_combined_entries(entries, indicator_variable):
    filtered = []
    for entry in entries or []:
        if not entry or not entry.get("points"):
            continue
        page = str(entry.get("page") or entry.get("source_page") or "").casefold()
        filters = entry.get("filters") or {}
        if indicator_variable == "g3a_11" and page == "branches":
            continue
        if indicator_variable == "g3a_11" and str(filters.get("Institution Type", "")).casefold() == "sacco":
            continue
        filtered.append(entry)
    return filtered


def _combined_story_html(cfg, district_name, est, national_est, diff, combined_entry):
    direction = "above" if est >= national_est else "below"
    story = (
        f"<b>FinScope finding.</b> {esc(district_name)} reports "
        f"{est:.1f}% for {esc(cfg['title'])}, {abs(diff):.1f} percentage points "
        f"{direction} the weighted national estimate of {national_est:.1f}%. "
    )
    if combined_entry is None:
        context = (
            "No approved district-scoped NBR observation is available for this "
            "indicator and selected scope."
        )
    else:
        context = (
            "A separately labelled NBR administrative context is available in "
            "the evidence panel below."
        )
    return (
        f"<div class='insp-note'>{story}<br>{esc(cfg['interpretation'])}<br>"
        f"{esc(context)} The survey difference is descriptive, not a causal explanation.</div>"
    )


@st.cache_data(ttl=900, show_spinner=False)
def _combined_intelligence_assessment(
    points: Sequence[Mapping[str, Any]],
    expected_districts: Sequence[str],
    selected_district: str,
) -> dict[str, Any]:
    if not points:
        return {
            "state": "observation_unavailable",
            "reason": "No NBR observations are available for this approved series.",
        }

    observations = []
    table_documents = {}
    source_points = []
    required_fields = (
        "page",
        "metric_label",
        "geography",
        "reporting_date",
        "collected_at",
        "run_id",
        "combo_key",
        "filters",
        "value",
    )
    for point in points:
        if (
            point.get("source_type") != "district_table"
            or point.get("geography_level") != "district"
            or not all(point.get(field) is not None for field in required_fields)
            or not isinstance(point.get("filters"), Mapping)
            or not str(point.get("combo_key", "")).strip()
        ):
            return {
                "state": "unassessable_source_provenance",
                "reason": (
                    "One or more normalized NBR observations lacks the exact "
                    "district, date, filter, or collection provenance required "
                    "by the existing assessment."
                ),
            }
        try:
            reporting_date = date.fromisoformat(str(point["reporting_date"]))
            value = float(point["value"])
        except (TypeError, ValueError):
            return {
                "state": "unassessable_source_provenance",
                "reason": "An NBR observation has an invalid date or numeric value.",
            }
        if not math.isfinite(value) or value < 0:
            return {
                "state": "unassessable_source_provenance",
                "reason": "An NBR observation has an invalid numeric value.",
            }

        observation = NBRObservation(
            page=str(point["page"]),
            metric_label=str(point["metric_label"]),
            district=str(point["geography"]),
            combo_key=str(point["combo_key"]),
            reporting_date=reporting_date,
            collected_at=str(point["collected_at"]),
            run_id=str(point["run_id"]),
            filters=dict(point["filters"]),
            value=value,
        )
        observations.append(observation)
        source_points.append(dict(point))
        table_documents[(
            observation.page,
            reporting_date.isoformat(),
            observation.combo_key,
            observation.district.casefold(),
        )] = {
            "page": observation.page,
            "snapshot_date": reporting_date.isoformat(),
            "combo_key": observation.combo_key,
            "district": observation.district,
            "district_known": True,
        }

    cross_summary, cross_candidates, cross_states = (
        evaluate_cross_sectionally_with_statuses(
            observations,
            list(table_documents.values()),
            expected_districts,
        )
    )
    temporal_summary, temporal_cases = evaluate_chronologically(observations)

    selected_history = [
        observation
        for observation in observations
        if observation.district.casefold() == selected_district.casefold()
    ]
    latest = max(
        selected_history,
        key=lambda item: item.reporting_date,
        default=None,
    )
    if latest is None:
        peer_date = max(item.reporting_date for item in observations)
        return {
            "state": "observation_unavailable",
            "reason": (
                f"No district-scoped observation is recorded for "
                f"{selected_district} in this exact NBR series."
            ),
            "peer_date": peer_date.isoformat(),
            "peer_points": [
                point for point in source_points
                if point["reporting_date"] == peer_date.isoformat()
            ],
            "expected_district_count": len(expected_districts),
            "cross_section": {"state": "observation_unavailable"},
            "temporal": {"state": "observation_unavailable"},
        }

    event_key = (
        latest.page,
        latest.metric_label,
        latest.district.casefold(),
        latest.reporting_date.isoformat(),
        latest.combo_key,
    )
    cross_status = cross_states.get(event_key, {
        "state": "unassessable",
        "reason": "The assessment returned no status for this observation.",
    })
    cross_candidate = next(
        (
            candidate for candidate in cross_candidates
            if (
                candidate["page"],
                candidate["metric_label"],
                candidate["district"].casefold(),
                candidate["reporting_date"],
                candidate["combo_key"],
            ) == event_key
        ),
        None,
    )

    temporal_case = next(
        (
            case for case in temporal_cases
            if (
                case["page"],
                case["metric_label"],
                case["district"].casefold(),
                case["target"]["reporting_date"],
                case["combo_key"],
            ) == event_key
        ),
        None,
    )
    if temporal_case is None:
        temporal_state = (
            "insufficient_evidence"
            if len(selected_history) < MIN_TRAINING_RATES + 2
            else "unassessable"
        )
        temporal_details = {
            "state": temporal_state,
            "observation_count": len(selected_history),
            "minimum_observations": MIN_TRAINING_RATES + 2,
        }
    elif temporal_case["model_status"] != "scored":
        temporal_details = {
            "state": "unassessable",
            "observation_count": len(selected_history),
            "model_status": temporal_case["model_status"],
            "dispersion_status": temporal_case["model_dispersion_status"],
        }
    else:
        temporal_details = {
            "state": (
                "eligible_unusual_observation"
                if temporal_case["model_alert"]
                else "assessable_no_qualifying_signal"
            ),
            "observation_count": len(selected_history),
            "case": temporal_case,
        }

    latest_point = next(
        point for point in source_points
        if (
            point["geography"].casefold() == latest.district.casefold()
            and point["reporting_date"] == latest.reporting_date.isoformat()
        )
    )
    peer_points = [
        point for point in source_points
        if point["reporting_date"] == latest.reporting_date.isoformat()
    ]
    signal_found = (
        cross_status.get("state") == "eligible_unusual_observation"
        or temporal_details.get("state") == "eligible_unusual_observation"
    )
    if signal_found:
        recommendation = (
            f"For {selected_district}, verify the NBR source row, collection "
            "run, reporting date, and exact filters before interpreting this "
            "review signal."
        )
    elif (
        cross_status.get("state") == "insufficient_evidence"
        or temporal_details.get("state") == "insufficient_evidence"
    ):
        recommendation = (
            f"For {selected_district}, more compatible district observations or "
            "reporting snapshots are needed before this NBR series can support "
            "an unusualness assessment."
        )
    else:
        recommendation = (
            f"For {selected_district}, no unusual NBR signal was returned for "
            "the assessed scope; retain the administrative count as "
            "source-specific context, not a measure of FinScope access or use."
        )

    return {
        "state": "available",
        "observation": {
            "value": latest.value,
            "reporting_date": latest.reporting_date.isoformat(),
            "unit": latest_point.get("unit") or "unit not specified",
            "metric_label": latest.metric_label,
            "run_id": latest.run_id,
            "filters": latest.filters,
            "quality_qualifications": latest_point.get(
                "quality_qualifications", []
            ),
        },
        "peer_date": latest.reporting_date.isoformat(),
        "peer_points": peer_points,
        "expected_district_count": len(expected_districts),
        "cross_section": {
            **cross_status,
            "candidate": cross_candidate,
            "summary": cross_summary,
        },
        "temporal": temporal_details,
        "temporal_summary": temporal_summary,
        "recommendation": recommendation,
    }


def _kpi_context(entry, district_name):
    """NBR trend for the selected district, shown inside the primary KPI card."""
    if not entry:
        return ""
    local = [p for p in entry["points"] if p.get("geography") == district_name]
    if local:
        return context_strip_html(entry, local)
    return (
        '<div class="nbr-ctx"><div class="nbr-ctx-meta">'
        f'NBR · {esc(entry["metric_label"])}: no observation for this district</div></div>'
    )


def _clicked_district(event, names):
    points = []
    try:
        points = event.get("selection", {}).get("points", []) if event else []
    except AttributeError:
        points = []
    for point in points:
        custom = point.get("customdata")
        name = (
            point.get("location")
            or point.get("text")
            or (custom[-1] if isinstance(custom, (list, tuple)) and custom else None)
        )
        if isinstance(name, str) and name in names:
            return name
    return None


# --------------------------------------------------------------------------
# Page
# --------------------------------------------------------------------------
def render_district_explorer():
    from src.pages.nbr_dashboard import (
        current_mode,
        load_combined_context_data,
        render_combined_context,
        render_nbr_page,
    )

    mode = current_mode()
    if mode == "NBR Supply":
        render_nbr_page(
            "district",
            selected_district=st.session_state.get("dx_district"),
        )
        return

    try:
        district = data.load_district()
        national = data.load_national()
        geojson = data.load_geojson()
        centers, center = data.geo_summary(geojson)
    except (FileNotFoundError, ValueError, KeyError) as error:
        st.error(
            "The district data or boundary file could not be loaded. "
            "Check the files in data/processed and the project root."
        )
        st.caption(str(error))
        return

    present = {k: v for k, v in INDICATORS.items() if v["column"] in district.columns}

    only_data, only_geo = data.geo_name_mismatch(district["District"], geojson)
    if only_data or only_geo:
        st.warning(
            "Some district names in the data do not match the map boundaries and will not be coloured: "
            f"{', '.join(only_data) or 'none'} (data) · {', '.join(only_geo) or 'none'} (map)."
        )

    names = sorted(district["District"].unique())
    st.session_state.setdefault("dx_district", names[0])
    pending = st.session_state.pop("_dx_pending", None)
    if pending in names:
        st.session_state["dx_district"] = pending
    if st.session_state["dx_district"] not in names:
        st.session_state["dx_district"] = names[0]

    # Widget values are already in session_state before the widgets render,
    # so the hero can reflect the current selection while controls sit below it.
    indicator_name = st.session_state.get("dx_indicator")
    if indicator_name not in present:
        indicator_name = list(present.keys())[0]
    cfg = present[indicator_name]
    metric = cfg["column"]
    selected_district = st.session_state["dx_district"]
    combined_entries = []
    combined_version = None
    if mode == "Combined":
        try:
            combined_entries, combined_version = load_combined_context_data(
                cfg["variable"],
                geography_level="district",
            )
            combined_entries = _filtered_combined_entries(combined_entries, cfg["variable"])
        except (RuntimeError, ValueError, OSError, PyMongoError) as error:
            combined_context_error = error
        else:
            combined_context_error = None
    else:
        combined_context_error = None
    series_key = f"combined_dx_series_{cfg['variable']}_{combined_version or 'none'}"
    if combined_entries:
        series_index = st.session_state.get(series_key, 0)
        if not isinstance(series_index, int) or series_index >= len(combined_entries):
            series_index = 0
        combined_entry = combined_entries[series_index]
        latest_date = max(
            (str(point["reporting_date"]) for point in combined_entry["points"]),
            default="",
        )
        overlay_points = [
            point for point in combined_entry["points"]
            if str(point["reporting_date"]) == latest_date
        ]
    else:
        combined_entry = None
        overlay_points = []
    combined_intelligence = (
        _combined_intelligence_assessment(
            combined_entry["points"],
            names,
            selected_district,
        )
        if mode == "Combined" and combined_entry is not None
        else None
    )

    nat_hit = national.loc[
        national["Indicator"].eq(cfg["national_label"]), "Estimate (%)"
    ]
    if nat_hit.empty:
        st.error(f"National estimate missing for {indicator_name}.")
        return
    national_est = float(nat_hit.iloc[0])

    df = district.reset_index(drop=True).copy()
    df["rank"] = df[metric].rank(ascending=False, method="min").astype(int)
    df["diff"] = df[metric] - national_est
    n = len(df)
    lo, hi = float(df[metric].min()), float(df[metric].max())
    sel = df.loc[df["District"].eq(selected_district)].iloc[0]
    highest = df.loc[df[metric].idxmax()]
    lowest = df.loc[df[metric].idxmin()]
    est = float(sel[metric])
    diff = est - national_est
    margin = data.moe_pp(est, sel["Valid respondents"])
    clear = abs(diff) > margin

    page_header(
        "District explorer",
        f"How {cfg['title'].lower()} varies across Rwanda's {n} districts. "
        "Click any district on the map to inspect it.",
        pill="FinScope Rwanda 2024",
        size="tall",
        below_html=kpi_grid(
            [
                kpi_card("Selected district", f"{est:.1f}", "%", est, cfg["accent"],
                         f"<b>{esc(selected_district)}</b> · ±{margin:.1f} pp indicative"
                         + _kpi_context(combined_entry, selected_district)),
                kpi_card("National estimate", f"{national_est:.1f}", "%", national_est,
                         PALETTE["ink2"], "Weighted national level"),
                kpi_card("Difference from national", f"{diff:+.1f}", " pp",
                         abs(diff) / max(hi - lo, 1e-9) * 100, PALETTE["sun"],
                         ("Above" if diff >= 0 else "Below") + " national · "
                         + ("larger than margin" if clear else "within margin")),
                kpi_card("Rank among districts", f"#{int(sel['rank'])}", f" of {n}",
                         (n - int(sel["rank"]) + 1) / n * 100, "#5FB8AB",
                         f"Highest <b>{esc(highest['District'])}</b> · "
                         f"Lowest <b>{esc(lowest['District'])}</b>"),
            ]
        ),
    )

    st.markdown("")

    # ---- Controls -------------------------------------------------------
    with st.container(key="card_controls"):
        st.pills(
            "Indicator",
            list(present.keys()),
            selection_mode="single",
            default=list(present.keys())[0],
            key="dx_indicator",
        )
        if combined_entries and len(combined_entries) > 1:
            st.selectbox(
                "NBR supply series",
                range(len(combined_entries)),
                format_func=lambda index: (
                    f"{combined_entries[index]['metric_label']} · "
                    f"{combined_entries[index].get('unit') or 'unit not specified'}"
                ),
                key=series_key,
            )
        if combined_context_error is not None:
            st.caption("NBR supply context is temporarily unavailable; FinScope estimates are unchanged.")
        c_dist, c_set = st.columns([2.2, 1], gap="medium", vertical_alignment="bottom")
        with c_dist:
            st.selectbox("District", names, key="dx_district")
        with c_set:
            with st.popover(
                "Map settings",
                icon=":material/tune:",
                use_container_width=True,
            ):
                basemap = st.selectbox("Basemap", list(BASEMAPS), key="dx_basemap")
                palette = st.selectbox("Colours", PALETTE_CHOICES, key="dx_palette")
                opacity = st.slider("Fill opacity", 0.3, 1.0, 0.85, 0.05, key="dx_opacity")
                spotlight = st.selectbox("Outline extremes", SPOTLIGHTS, key="dx_spot")
                labels = st.toggle("Show district names", value=False, key="dx_labels")
                tilt = st.slider("Tilt", 0, 60, 0, key="dx_tilt")
                rotation = st.slider("Rotation", -90, 90, 0, key="dx_rot")

    settings = dict(
        basemap=basemap, palette=palette, opacity=opacity, spotlight=spotlight,
        labels=labels, tilt=tilt, rotation=rotation, zoom=7.3,
    )

    st.markdown("")

    # ---- Hero map + inspector --------------------------------------------
    map_col, insp_col = st.columns([2.85, 1], gap="medium")

    with map_col:
        with st.container(key="card_map"):
            legend = ""
            if spotlight in ("Top 5", "Both"):
                top_color = "#FFFFFF" if BASEMAPS[basemap]["dark"] else PALETTE["ink"]
                legend += (
                    f'<span class="chip"><i style="border-color:{top_color};'
                    f'background:{"#0E2A35" if top_color == "#FFFFFF" else "#fff"}"></i>Highest 5</span>'
                )
            if spotlight in ("Bottom 5", "Both"):
                legend += (
                    f'<span class="chip"><i style="border-color:{PALETTE["coral"]}"></i>Lowest 5</span>'
                )
            legend += (
                f'<span class="chip"><i style="border-color:{PALETTE["sun"]}"></i>Selected</span>'
            )
            render_html(
                f"""
                <div class="map-strip">
                  <div>
                    <div class="ct">{esc(cfg['title'])}</div>
                    <div class="cs">Click a district to inspect it · scroll to zoom · drag to pan</div>
                  </div>
                  <div class="chips">{legend}
                    {(f'<span class="chip"><i style="background:#163D4B;border-color:#fff"></i>NBR · {esc(combined_entry["metric_label"])} · marker size</span>' if overlay_points else '')}
                  </div>
                </div>
                """
            )

            fig = build_map(
                df, geojson, centers, center, cfg, metric, national_est,
                selected_district, indicator_name, settings,
                supply_points=overlay_points,
            )
            event = st.plotly_chart(
                fig,
                use_container_width=True,
                key="dx_map",
                on_select="rerun",
                selection_mode="points",
                config={
                    "scrollZoom": True,
                    "displaylogo": False,
                    "modeBarButtonsToRemove": ["select2d", "lasso2d"],
                },
            )

    # Map click -> selection (applied on the next run, before widgets render)
    clicked = _clicked_district(event, names)
    if clicked and clicked != st.session_state.get("_dx_last_click"):
        st.session_state["_dx_last_click"] = clicked
        if clicked != selected_district:
            st.session_state["_dx_pending"] = clicked
            st.rerun()

    with insp_col:
        with st.container(key="card_inspector"):
            render_html(_inspector_html(sel, cfg, metric, national_est, lo, hi, n))
            render_html(_combined_story_html(cfg, selected_district, est, national_est, diff, combined_entry))
            if combined_entry is not None:
                render_combined_context(
                    cfg["variable"],
                    district=selected_district,
                    entries=[combined_entry],
                    source_version=combined_version,
                    intelligence=combined_intelligence,
                )
            st.button(
                f"Highest: {highest['District']} · {highest[metric]:.1f}%",
                key="dx_go_high",
                on_click=_jump_to,
                args=(highest["District"],),
                use_container_width=True,
                icon=":material/arrow_upward:",
            )
            st.button(
                f"Lowest: {lowest['District']} · {lowest[metric]:.1f}%",
                key="dx_go_low",
                on_click=_jump_to,
                args=(lowest["District"],),
                use_container_width=True,
                icon=":material/arrow_downward:",
            )
            render_html(
                f"""
                <div class="insp-note"><b>{esc(cfg['description'])}</b><br>
                {esc(cfg['interpretation'])}<br>
                The gap between extremes is {hi - lo:.1f} pp. It is a
                description, not a causal explanation. The margin assumes simple
                random sampling, so the true uncertainty is larger.</div>
                """
            )
            nat_lookup = dict(zip(national["Indicator"], national["Estimate (%)"].astype(float)))
            st.download_button(
                "Download district profile",
                data=district_brief(
                    selected_district, df, nat_lookup,
                    barriers=data.load_barriers_district(),
                ),
                file_name=f"{selected_district.lower().replace(' ', '_')}_financial_inclusion_profile.md",
                mime="text/markdown",
                key="dx_brief",
                use_container_width=True,
                icon=":material/description:",
            )

    st.markdown("")

    # ---- Ranking + profile + distribution --------------------------------
    rank_col, side_col = st.columns([1.45, 1], gap="medium")

    with rank_col:
        with st.container(key="card_ranking"):
            card_title(
                "All districts, ranked",
                "The highlighted bar is your selected district; the dotted "
                "line is the national estimate.",
            )
            ordered = df.sort_values(metric, ascending=True)
            bar_colors = [
                PALETTE["sun"] if d == selected_district else cfg["accent"]
                for d in ordered["District"]
            ]
            rank_fig = go.Figure(
                go.Bar(
                    x=ordered[metric],
                    y=ordered["District"],
                    orientation="h",
                    marker=dict(color=bar_colors),
                    text=ordered[metric],
                    texttemplate="%{text:.1f}%",
                    textposition="outside",
                    cliponaxis=False,
                    textfont=dict(size=11, color=PALETTE["ink"]),
                    customdata=ordered[["Valid respondents"]],
                    hovertemplate=(
                        "%{y}<br>" + cfg["title"] + ": %{x:.2f}%<br>"
                        "%{customdata[0]:,.0f} respondents<extra></extra>"
                    ),
                )
            )
            rank_fig.add_vline(
                x=national_est, line_dash="dot", line_color=PALETTE["ink"], line_width=1.5
            )
            rank_fig.update_layout(bargap=0.32)
            rank_fig.update_xaxes(
                title=None, ticksuffix="%",
                range=[0, min(100, hi + 9)],
                gridcolor=PALETTE["grid"], zeroline=False,
            )
            rank_fig.update_yaxes(title=None, showgrid=False, tickfont=dict(size=11))
            st.plotly_chart(
                style_chart(rank_fig, 720, margin=dict(l=4, r=24, t=10, b=4)),
                use_container_width=True,
                key="dx_ranking",
                config={"displayModeBar": False},
            )

    with side_col:
        with st.container(key="card_profile"):
            card_title(
                f"{selected_district} across indicators",
                "The selected district against the national estimate.",
            )
            nat_map = dict(zip(national["Indicator"], national["Estimate (%)"]))
            shorts, d_vals, n_vals = [], [], []
            for column, theme in INDICATOR_THEME.items():
                if column in df.columns and theme["national"] in nat_map:
                    shorts.append(theme["short"])
                    d_vals.append(float(sel[column]))
                    n_vals.append(float(nat_map.get(theme["national"], float("nan"))))
            prof = go.Figure()
            prof.add_bar(
                y=shorts, x=d_vals, orientation="h", name=selected_district,
                marker_color=PALETTE["sun"],
                text=d_vals, texttemplate="%{text:.1f}%", textposition="outside",
                cliponaxis=False,
            )
            prof.add_bar(
                y=shorts, x=n_vals, orientation="h", name="National",
                marker_color=PALETTE["ink2"],
                text=n_vals, texttemplate="%{text:.1f}%", textposition="outside",
                cliponaxis=False,
            )
            prof.update_layout(barmode="group", bargap=0.3, bargroupgap=0.08)
            prof.update_xaxes(
                title=None, ticksuffix="%", range=[0, 100],
                gridcolor=PALETTE["grid"], zeroline=False,
            )
            prof.update_yaxes(title=None, autorange="reversed", showgrid=False)
            st.plotly_chart(
                style_chart(prof, max(330, 46 * len(shorts) + 40), margin=dict(l=4, r=26, t=10, b=4)),
                use_container_width=True,
                key="dx_profile",
                config={"displayModeBar": False},
            )

        st.markdown("")

        with st.container(key="card_distribution"):
            card_title(
                "Where districts cluster",
                f"How the {n} districts spread on {cfg['title'].lower()}.",
            )
            dist = go.Figure(
                go.Histogram(
                    x=df[metric], nbinsx=8,
                    marker=dict(color=cfg["accent"], opacity=0.55,
                                line=dict(color="#FFFFFF", width=1.5)),
                    hovertemplate="%{x}%: %{y} districts<extra></extra>",
                    showlegend=False,
                )
            )
            dist.add_vline(x=float(sel[metric]), line_color=PALETTE["sun"], line_width=4)
            dist.add_vline(x=national_est, line_color=PALETTE["ink"], line_width=1.8, line_dash="dot")
            dist.add_trace(go.Scatter(
                x=[None], y=[None], mode="lines", name=selected_district,
                line=dict(color=PALETTE["sun"], width=4)))
            dist.add_trace(go.Scatter(
                x=[None], y=[None], mode="lines", name="National",
                line=dict(color=PALETTE["ink"], width=2, dash="dot")))
            dist.update_layout(bargap=0.06)
            dist.update_xaxes(title=None, ticksuffix="%", showgrid=False, zeroline=False)
            dist.update_yaxes(title="Districts", dtick=2, gridcolor=PALETTE["grid"], zeroline=False)
            st.plotly_chart(
                style_chart(dist, 250),
                use_container_width=True,
                key="dx_distribution",
                config={"displayModeBar": False},
            )

    st.markdown("")

    # ---- Table ------------------------------------------------------------
    with st.container(key="card_table"):
        card_title(
            "District data",
            "Every indicator for every district, sorted by the indicator above. "
            "Use the search icon in the table to find a district.",
        )
        show_district_table(
            df,
            sort_by=metric,
            key="district_explorer_download",
            file_name="rwanda_district_explorer.csv",
            height=440,
        )

    render_html(
        '<div class="src-note">Source: FinScope Rwanda 2024. Estimates are '
        "weighted survey results, not live measurements. Differences alone "
        "do not establish statistical significance or explain their causes.</div>"
    )
