import base64
import json
import re

import numpy as np
import pandas as pd
import pytest
import pymongo
from streamlit.testing.v1 import AppTest

import src.pages.nbr_dashboard as dashboard
from src.pages.district_explorer import build_map
from src.pages.nbr_dashboard import (
    _group_families,
    _mapped_series,
    _national_highlight_metadata,
    _national_highlight_figure,
    _national_infrastructure_series,
    _national_infrastructure_figure,
    _national_customer_comparison_series,
    _national_customer_comparison_figure,
    _compact_customer_count,
    _national_customer_unknown_counts,
    _national_supply_header_html,
    _population_group_header_html,
    _population_district_figure,
    _population_district_continuity_figure,
    _prepare_population_district_result,
    _prepare_population_district_continuity,
    _prepare_population_national_history,
    _prepare_population_national_result,
    _population_national_history_figure,
    _population_family_dates,
    _population_group_families,
    _population_indicator_options,
    _render_population_district_continuity,
    _render_population_national_values,
    _savings_activity_series,
    _savings_district_figure,
    _savings_trend_figure,
    _select_savings_coverage,
    _nbr_clicked_selection,
    _eligible_nbr_district_points,
    _nbr_district_quality_messages,
    _nbr_district_distribution_data,
    _nbr_district_distribution_figure,
    _nbr_district_history_data,
    _nbr_district_history_heatmap,
    _nbr_district_history_figure,
    _render_nbr_district_history_watchlist,
    _nbr_district_details_html,
    _nbr_district_snapshot,
    _nbr_district_snapshot_value_range,
    _nbr_district_service_options,
    _unknown_savings_customer,
    _source_data_version,
    NATIONAL_HEADER_KPIS,
    NATIONAL_INFRASTRUCTURE_SERIES,
    NATIONAL_CUSTOMER_COMPARISONS,
    build_nbr_indicator_registry,
    load_mongodb_history,
    render_nbr_page,
    render_nbr_savings_activity,
)


def _point(
    *,
    page="branches",
    metric="Branches",
    date="2026-10-24",
    value=5,
    geography="Kirehe",
    level="district",
    filters=None,
    unit="count",
    **overrides,
):
    filters = filters or {
        "Institution Type": "Banks",
        "Branch Status": "Active",
        "Location": "All",
    }
    return {
        "page": page,
        "metric_label": metric,
        "reporting_date": date,
        "value": value,
        "geography": geography,
        "geography_level": level,
        "filters": filters,
        "combo_key": json.dumps(filters, sort_keys=True),
        "unit": unit,
        "unit_status": "configured_source_label",
        "source_type": "district_table" if level == "district" else "national_kpi",
        "source_record_id": f"{page}-{metric}-{date}-{geography}",
        "run_id": f"run-{date}",
        "collected_at": f"{date}T12:00:00+00:00",
        **overrides,
    }


def _plotly_values(value):
    if isinstance(value, dict) and {"bdata", "dtype"} <= set(value):
        return np.frombuffer(
            base64.b64decode(value["bdata"]),
            dtype=np.dtype(value["dtype"]),
        ).tolist()
    return value


def test_nbr_registry_uses_only_observed_series_and_preserves_filter_identity():
    first = _point(value=5)
    second = _point(
        date="2026-08-20",
        value=6,
        filters={
            "Institution Type": "Banks",
            "Branch Status": "Active",
            "Location": "All",
            "Gender": "Female",
        },
    )

    registry = build_nbr_indicator_registry([first, second])

    assert len(registry) == 2
    assert {item["metric_label"] for item in registry} == {"Branches"}
    assert {item["unit"] for item in registry} == {"count"}
    assert {item["source_page"] for item in registry} == {"branches"}
    assert any(
        item["filters"].get("Gender") == "Female"
        for item in registry
    )
    assert all(item["reporting_dates"] for item in registry)
    assert all(item["geographies"] == ["Kirehe"] for item in registry)


def test_nbr_district_registry_exposes_observed_e_money_issuer_series():
    points = [
        _point(
            page="inclusion",
            metric="Customers",
            filters={
                "Account/Policy Status": "Active",
                "Age Segment": "All",
                "Gender": "All",
                "Institution Type": "E-money issuers",
                "Location": "All",
            },
            unit_status="source_column",
        ),
        _point(
            page="agents",
            metric="Agents",
            filters={
                "Agent Status": "Active",
                "Institution Type": "E-money Issuers",
                "Location": "All",
            },
            unit_status="source_column",
        ),
    ]

    registry = build_nbr_indicator_registry(_eligible_nbr_district_points(points))
    district_entries = [
        entry for entry in registry
        if entry["geography_level"] == "district"
    ]
    services = _nbr_district_service_options(district_entries)
    entries_by_page = {
        entry["source_page"]: entry
        for entry in district_entries
    }

    assert set(entries_by_page) == {"agents", "inclusion"}
    assert entries_by_page["inclusion"]["metric_label"] == "Customers"
    assert entries_by_page["inclusion"]["unit"] == "count"
    assert entries_by_page["inclusion"]["filters"]["Institution Type"] == "E-money issuers"
    assert entries_by_page["agents"]["metric_label"] == "Agents"
    assert entries_by_page["agents"]["filters"]["Institution Type"] == "E-money Issuers"
    assert {item["source_page"] for item in services.values()} == {
        "agents",
        "inclusion",
    }


def test_nbr_district_explorer_recolors_map_for_selected_e_money_series():
    points = []
    for institution, values in (
        ("All", (10, 20)),
        ("E-money Issuers", (1_000, 50_000)),
    ):
        filters = {
            "Agent Status": "Active",
            "Gender": "All",
            "Institution Type": institution,
            "Location": "All",
        }
        for district, value in zip(("Gasabo", "Kirehe"), values):
            points.append(_point(
                page="agents",
                metric="Agents",
                date="2026-10-27",
                value=value,
                geography=district,
                filters=filters,
                unit="count",
                unit_status="source_column",
                source_type="district_table",
            ))
    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"shapeName": district},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[
                        29.7, -2.5
                    ], [29.8, -2.5], [29.8, -2.4], [29.7, -2.4], [29.7, -2.5]]],
                },
            }
            for district in ("Gasabo", "Kirehe")
        ],
    }
    script = (
        "import json\n"
        "import src.pages.nbr_dashboard as dashboard\n"
        f"points = json.loads({json.dumps(json.dumps(points))})\n"
        f"geojson = json.loads({json.dumps(json.dumps(geojson))})\n"
        "_original_district_reference = dashboard.load_district_reference\n"
        "_original_geojson_loader = dashboard.data.load_geojson\n"
        "_original_geo_summary = dashboard.data.geo_summary\n"
        "dashboard.load_district_reference = lambda: ['Gasabo', 'Kirehe']\n"
        "dashboard.data.load_geojson = lambda: geojson\n"
        "dashboard.data.geo_summary = lambda _: ({'Gasabo': (-2.45, 29.75), "
        "'Kirehe': (-2.45, 29.75)}, (-2.45, 29.75))\n"
        "eligible = dashboard._eligible_nbr_district_points(points)\n"
        "registry = dashboard.build_nbr_indicator_registry(eligible)\n"
        "entries = [entry for entry in registry if entry['geography_level'] == 'district']\n"
        "services = dashboard._nbr_district_service_options(entries)\n"
        "try:\n"
        "    dashboard._render_nbr_district_explorer(\n"
        "        points, 'e-money-test', source_page='agents', selected_district='Kirehe',\n"
        "        district_entries=entries, service_options=services\n"
        "    )\n"
        "finally:\n"
        "    dashboard.load_district_reference = _original_district_reference\n"
        "    dashboard.data.load_geojson = _original_geojson_loader\n"
        "    dashboard.data.geo_summary = _original_geo_summary\n"
    )
    app = AppTest.from_string(script, default_timeout=45).run()

    assert not app.exception, [error.value for error in app.exception]
    institution_control = next(
        control for control in app.segmented_control
        if control.label == "Institution Type"
    )
    assert "E-money Issuers" in institution_control.options
    map_chart = next(chart for chart in app.get("plotly_chart") if chart.key == "nbr_dx_map")
    initial_spec = json.loads(map_chart.proto.spec)
    assert _plotly_values(initial_spec["data"][0]["z"]) == [10, 20]
    assert initial_spec["data"][0]["zmin"] == 10
    assert initial_spec["data"][0]["zmax"] == 20
    assert initial_spec["data"][0]["colorscale"][0][1] == "#167B76"

    institution_control.select("E-money Issuers").run()

    assert not app.exception, [error.value for error in app.exception]
    map_chart = next(chart for chart in app.get("plotly_chart") if chart.key == "nbr_dx_map")
    selected_spec = json.loads(map_chart.proto.spec)
    assert _plotly_values(selected_spec["data"][0]["z"]) == [1_000, 50_000]
    assert selected_spec["data"][0]["zmin"] == 1_000
    assert selected_spec["data"][0]["zmax"] == 50_000
    assert selected_spec["data"][0]["colorscale"][0][1] == "#F2ECFA"
    assert selected_spec["data"][0]["colorscale"] != initial_spec["data"][0]["colorscale"]
    assert selected_spec["data"][0]["colorbar"]["title"]["text"] == "Agents · count"
    assert selected_spec["data"][0]["colorbar"]["tickformat"] == ",.0f"
    rendered = "\n".join(
        [item.value for item in app.markdown]
        + [item.value for item in app.caption]
    )
    assert "Institution Type: E-money Issuers" in rendered
    assert "Kirehe" in rendered


def test_nbr_district_explorer_recolors_e_money_inclusion_customers():
    points = []
    for institution, values in (
        ("All", (10, 20)),
        ("E-money issuers", (100, 200)),
    ):
        filters = {
            "Account/Policy Status": "Active",
            "Age Segment": "All",
            "Gender": "All",
            "Institution Type": institution,
            "Location": "All",
        }
        for district, value in zip(("Gasabo", "Kirehe"), values):
            points.append(_point(
                page="inclusion",
                metric="Customers",
                date="2026-10-27",
                value=value,
                geography=district,
                filters=filters,
                unit="count",
                unit_status="source_column",
                source_type="district_table",
            ))
    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"shapeName": district},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[
                        29.7, -2.5
                    ], [29.8, -2.5], [29.8, -2.4], [29.7, -2.4], [29.7, -2.5]]],
                },
            }
            for district in ("Gasabo", "Kirehe")
        ],
    }
    script = (
        "import json\n"
        "import src.pages.nbr_dashboard as dashboard\n"
        f"points = json.loads({json.dumps(json.dumps(points))})\n"
        f"geojson = json.loads({json.dumps(json.dumps(geojson))})\n"
        "_original_district_reference = dashboard.load_district_reference\n"
        "_original_geojson_loader = dashboard.data.load_geojson\n"
        "_original_geo_summary = dashboard.data.geo_summary\n"
        "dashboard.load_district_reference = lambda: ['Gasabo', 'Kirehe']\n"
        "dashboard.data.load_geojson = lambda: geojson\n"
        "dashboard.data.geo_summary = lambda _: ({'Gasabo': (-2.45, 29.75), "
        "'Kirehe': (-2.45, 29.75)}, (-2.45, 29.75))\n"
        "eligible = dashboard._eligible_nbr_district_points(points)\n"
        "registry = dashboard.build_nbr_indicator_registry(eligible)\n"
        "entries = [entry for entry in registry if entry['geography_level'] == 'district']\n"
        "services = dashboard._nbr_district_service_options(entries)\n"
        "try:\n"
        "    dashboard._render_nbr_district_explorer(\n"
        "        points, 'inclusion-e-money-test', source_page='inclusion',\n"
        "        selected_district='Kirehe', district_entries=entries,\n"
        "        service_options=services\n"
        "    )\n"
        "finally:\n"
        "    dashboard.load_district_reference = _original_district_reference\n"
        "    dashboard.data.load_geojson = _original_geojson_loader\n"
        "    dashboard.data.geo_summary = _original_geo_summary\n"
    )
    app = AppTest.from_string(script, default_timeout=45).run()

    assert not app.exception, [error.value for error in app.exception]
    institution_control = next(
        control for control in app.segmented_control
        if control.label == "Institution Type"
    )
    assert "E-money issuers" in institution_control.options
    map_chart = next(chart for chart in app.get("plotly_chart") if chart.key == "nbr_dx_map")
    initial_spec = json.loads(map_chart.proto.spec)
    assert _plotly_values(initial_spec["data"][0]["z"]) == [10, 20]

    institution_control.select("E-money issuers").run()

    assert not app.exception, [error.value for error in app.exception]
    map_chart = next(chart for chart in app.get("plotly_chart") if chart.key == "nbr_dx_map")
    selected_spec = json.loads(map_chart.proto.spec)
    assert _plotly_values(selected_spec["data"][0]["z"]) == [100, 200]
    assert selected_spec["data"][0]["zmin"] == 100
    assert selected_spec["data"][0]["zmax"] == 200
    assert selected_spec["data"][0]["colorscale"][0][1] == "#F2ECFA"
    assert selected_spec["data"][0]["colorbar"]["title"]["text"] == "Customers · count"


def test_nbr_district_snapshot_keeps_exact_series_zero_missing_rank_and_coverage():
    filters = {
        "Institution Type": "Banks",
        "Branch Status": "Active",
        "Location": "All",
    }
    points = [
        _point(date="2025-11-20", value=2, geography="Kirehe", filters=filters),
        _point(date="2025-11-20", value=8, geography="Muhanga", filters=filters),
        _point(date="2026-10-24", value=0, geography="Kirehe", filters=filters),
        _point(date="2026-10-24", value=12, geography="Muhanga", filters=filters),
        _point(
            date="2026-10-24",
            value=999,
            geography="Gasabo",
            filters={**filters, "Institution Type": "Sacco"},
        ),
        _point(
            date="2026-10-24",
            value=500,
            geography="Unknown",
            filters=filters,
        ),
        _point(
            date="2026-10-24",
            value=500,
            geography="Gasabo",
            level="national",
            filters=filters,
        ),
        _point(
            date="2026-10-24",
            value=500,
            geography="Gasabo",
            filters=filters,
            repeated_snapshot_warning=True,
        ),
    ]

    eligible = _eligible_nbr_district_points(points)
    snapshot = _nbr_district_snapshot(
        eligible,
        page="branches",
        metric="Branches",
        filters=filters,
        unit="count",
        reporting_date="2026-10-24",
        district="Kirehe",
        expected_district_count=30,
    )
    missing = _nbr_district_snapshot(
        eligible,
        page="branches",
        metric="Branches",
        filters=filters,
        unit="count",
        reporting_date="2026-10-24",
        district="Gasabo",
        expected_district_count=30,
    )

    assert len(eligible) == 5
    registry = build_nbr_indicator_registry(eligible)
    exact_entry = next(
        entry for entry in registry
        if entry["filters"] == filters
    )
    assert exact_entry["reporting_dates"] == ["2025-11-20", "2026-10-24"]
    assert snapshot["current"]["value"] == 0
    assert snapshot["previous"]["reporting_date"] == "2025-11-20"
    assert snapshot["delta"] == -2
    assert snapshot["rank"] == 2
    assert snapshot["coverage"] == 2
    assert snapshot["expected_district_count"] == 30
    assert "Gasabo" not in snapshot["district_values"]
    assert missing["current"] is None
    assert missing["rank"] is None
    assert missing["delta"] is None


def test_nbr_district_distribution_ranks_compatible_counts_and_separates_unknown():
    filters = {
        "Institution Type": "All",
        "Branch Status": "Active",
        "Location": "All",
    }
    district_values = [
        (f"District {index:02}", (index - 1) * 10)
        for index in range(1, 12)
    ]
    points = [
        _point(
            date="2026-10-24",
            geography=district,
            value=value,
            filters=filters,
            quality_qualifications=[{
                "message": "District totals exceed the national KPI."
            }],
        )
        for district, value in district_values
    ]
    points.extend([
        _point(
            date="2026-10-24",
            geography="Unknown",
            value=999,
            level="unknown",
            filters=filters,
            source_type="district_table",
        ),
        _point(
            date="2026-10-24",
            geography="Other",
            value=1000,
            filters={**filters, "Institution Type": "Banks"},
        ),
        _point(
            date="2026-10-24",
            geography="Wrong unit",
            value=1001,
            filters=filters,
            unit="percent",
        ),
        _point(
            date="2026-10-24",
            geography="National",
            value=1002,
            level="national",
            filters=filters,
        ),
        _point(
            date="2026-10-24",
            geography="Repeated",
            value=1003,
            filters=filters,
            repeated_snapshot_warning=True,
        ),
    ])
    eligible = _eligible_nbr_district_points(points)
    snapshot = _nbr_district_snapshot(
        eligible,
        page="branches",
        metric="Branches",
        filters=filters,
        unit="count",
        reporting_date="2026-10-24",
        district="District 01",
        expected_district_count=30,
    )
    distribution = _nbr_district_distribution_data(
        snapshot,
        points,
        page="branches",
        metric="Branches",
        filters=filters,
        unit="count",
        reporting_date="2026-10-24",
    )
    figure = _nbr_district_distribution_figure(
        distribution,
        selected_district="District 01",
        metric="Branches",
        unit="count",
    )

    assert [point["geography"] for point in distribution["districts"]] == [
        district for district, _ in reversed(district_values)
    ]
    assert [point["geography"] for point in distribution["top"]] == [
        "District 11", "District 10", "District 09", "District 08", "District 07"
    ]
    assert [point["geography"] for point in distribution["bottom"]] == [
        "District 05", "District 04", "District 03", "District 02", "District 01"
    ]
    assert distribution["districts"][-1]["value"] == 0
    assert [row["geography"] for row in distribution["unknown"]] == ["Unknown"]
    assert "Unknown" not in [point["geography"] for point in distribution["top"]]
    assert figure.data[0].y[0] == "District 11"
    assert figure.data[0].x[-1] == 0
    assert figure.data[0].marker.color[-1] == "#F3D27A"
    assert snapshot["quality_qualifications"] == [
        "District totals exceed the national KPI."
    ]


def test_nbr_district_distribution_renders_unknown_and_quality_warning():
    filters = {
        "Institution Type": "All",
        "Branch Status": "Active",
        "Location": "All",
    }
    points = [
        _point(
            date="2026-10-24",
            geography=f"District {index:02}",
            value=index,
            filters=filters,
            quality_qualifications=[{
                "message": "Check reconciliation against the national KPI."
            }],
        )
        for index in range(1, 11)
    ]
    points.append(_point(
        date="2026-10-24",
        geography="Unknown",
        value=0,
        level="unknown",
        source_type="district_table",
        filters=filters,
    ))
    script = (
        "import json\n"
        "import src.pages.nbr_dashboard as dashboard\n"
        f"points = json.loads({json.dumps(json.dumps(points))})\n"
        "eligible = dashboard._eligible_nbr_district_points(points)\n"
        "snapshot = dashboard._nbr_district_snapshot(\n"
        "    eligible, page='branches', metric='Branches', filters="
        f"{filters!r}, unit='count', reporting_date='2026-10-24', "
        "district='District 01', expected_district_count=30)\n"
        "dashboard._render_nbr_district_distribution(\n"
        "    snapshot, points, page='branches', metric='Branches', filters="
        f"{filters!r}, unit='count', reporting_date='2026-10-24', "
        "selected_district='District 01')\n"
    )
    app = AppTest.from_string(script, default_timeout=30).run()

    assert not app.exception, [error.value for error in app.exception]
    rendered = " ".join(
        [item.value for item in app.markdown]
        + [item.value for item in app.caption]
    )
    assert "Unknown: 0 count" in rendered
    assert "not assigned to a district or included in rankings" in rendered
    assert "not treated as zero" in rendered
    assert [item.value for item in app.warning] == [
        "Check reconciliation against the national KPI."
    ]
    assert sum(
        chart.key.startswith("nbr_dx_distribution_")
        for chart in app.get("plotly_chart")
    ) == 1


def test_nbr_district_history_preserves_dates_compatibility_missing_zero_and_unknown():
    filters = {
        "Institution Type": "All",
        "Branch Status": "Active",
        "Location": "All",
    }
    points = [
        _point(
            date="2025-11-20",
            geography="A",
            value=0,
            filters=filters,
        ),
        _point(
            date="2025-11-20",
            geography="B",
            value=4,
            filters=filters,
        ),
        _point(
            date="2026-10-24",
            geography="A",
            value=2,
            filters=filters,
            quality_qualifications=[{
                "message": "District sum differs from the national KPI."
            }],
        ),
        _point(
            date="2026-10-24",
            geography="Unknown",
            value=8,
            level="unknown",
            source_type="district_table",
            filters=filters,
        ),
        _point(
            date="2026-10-24",
            geography="B",
            value=700,
            filters={**filters, "Institution Type": "Banks"},
        ),
        _point(
            date="2026-10-24",
            geography="C",
            value=800,
            filters=filters,
            unit="percent",
        ),
        _point(
            date="2026-10-24",
            geography="Repeated",
            value=900,
            filters=filters,
            repeated_snapshot_warning=True,
        ),
        _point(
            page="inclusion",
            metric="Customers",
            date="2026-10-24",
            geography="A",
            value=1000,
            filters=filters,
        ),
        _point(
            date="2026-10-24",
            geography="National",
            value=1100,
            level="national",
            filters=filters,
        ),
    ]
    eligible = _eligible_nbr_district_points(points)
    snapshot = _nbr_district_snapshot(
        eligible,
        page="branches",
        metric="Branches",
        filters=filters,
        unit="count",
        reporting_date="2026-10-24",
        district="A",
        expected_district_count=3,
    )
    history = _nbr_district_history_data(
        snapshot,
        points,
        page="branches",
        metric="Branches",
        filters=filters,
        unit="count",
        expected_districts=("A", "B", "C"),
    )
    heatmap = _nbr_district_history_heatmap(
        history,
        selected_district="A",
        metric="Branches",
        unit="count",
    )
    selected_trend = _nbr_district_history_figure(
        history,
        district="A",
        unit="count",
    )

    assert history["dates"] == ["2025-11-20", "2026-10-24"]
    assert history["coverage"] == [
        {"reporting_date": "2025-11-20", "reported": 2, "expected": 3, "missing": 1},
        {"reporting_date": "2026-10-24", "reported": 1, "expected": 3, "missing": 2},
    ]
    assert history["observations"][("A", "2025-11-20")]["value"] == 0
    assert ("B", "2026-10-24") not in history["observations"]
    assert history["missing_by_date"]["2026-10-24"] == ["B", "C"]
    assert [point["geography"] for point in history["unknown_by_date"]["2026-10-24"]] == [
        "Unknown"
    ]
    assert history["quality_by_date"]["2026-10-24"] == [
        "District sum differs from the national KPI."
    ]
    assert history["incomplete_history"] == [
        {"district": "B", "reported": 1, "expected": 2},
        {"district": "C", "reported": 0, "expected": 2},
    ]
    assert heatmap.data[0].z[0][0] == 0
    assert heatmap.data[0].z[1][1] is None
    assert heatmap.data[0].customdata[0][1] == (
        "2025-11-20: 0 → 2026-10-24: 2; change +2"
    )
    assert heatmap.data[1].name == "Missing observation"
    assert list(selected_trend.data[0].y) == [0, 2]
    assert selected_trend.data[0].connectgaps is False


def test_nbr_district_history_watchlist_renders_coverage_flags_and_unknown():
    filters = {
        "Institution Type": "All",
        "Branch Status": "Active",
        "Location": "All",
    }
    points = [
        _point(
            date=reporting_date,
            geography=district,
            value=value,
            filters=filters,
            quality_qualifications=([{
                "message": "NBR district count reconciliation qualification."
            }] if reporting_date == "2026-10-24" else []),
        )
        for reporting_date, district, value in (
            ("2025-11-20", "A", 0),
            ("2025-11-20", "B", 3),
            ("2026-10-24", "A", 2),
        )
    ]
    points.append(_point(
        date="2026-10-24",
        geography="Unknown",
        value=4,
        level="unknown",
        source_type="district_table",
        filters=filters,
    ))
    script = (
        "import json\n"
        "import src.pages.nbr_dashboard as dashboard\n"
        f"points = json.loads({json.dumps(json.dumps(points))})\n"
        "eligible = dashboard._eligible_nbr_district_points(points)\n"
        "snapshot = dashboard._nbr_district_snapshot(\n"
        "    eligible, page='branches', metric='Branches', filters="
        f"{filters!r}, unit='count', reporting_date='2026-10-24', "
        "district='A', expected_district_count=2)\n"
        "dashboard._render_nbr_district_history_watchlist(\n"
        "    snapshot, points, page='branches', metric='Branches', filters="
        f"{filters!r}, unit='count', selected_district='A', "
        "expected_districts=('A', 'B'), mappings=())\n"
    )
    app = AppTest.from_string(script, default_timeout=30).run()

    assert not app.exception, [error.value for error in app.exception]
    rendered = " ".join(
        [item.value for item in app.markdown]
        + [item.value for item in app.caption]
    )
    assert "Historical Change &amp; Coverage Watchlist" in rendered
    assert "2025-11-20" in rendered and "2026-10-24" in rendered
    assert "Unknown: 4 count" in rendered
    assert "Not assigned to a district" in rendered
    chart_keys = {chart.key for chart in app.get("plotly_chart")}
    assert any(key.startswith("nbr_dx_history_heatmap_") for key in chart_keys)
    assert any(key.startswith("nbr_dx_history_selected_") for key in chart_keys)


def test_nbr_district_details_distinguishes_observed_zero_from_missing():
    filters = {
        "Institution Type": "Banks",
        "Branch Status": "Active",
        "Location": "All",
    }
    points = _eligible_nbr_district_points([
        _point(date="2025-11-20", value=2, geography="Kirehe", filters=filters),
        _point(date="2025-11-20", value=8, geography="Muhanga", filters=filters),
        _point(date="2026-10-24", value=0, geography="Kirehe", filters=filters),
        _point(date="2026-10-24", value=12, geography="Muhanga", filters=filters),
    ])
    snapshot = _nbr_district_snapshot(
        points,
        page="branches",
        metric="Branches",
        filters=filters,
        unit="count",
        reporting_date="2026-10-24",
        district="Kirehe",
        expected_district_count=30,
    )
    observed_zero = _nbr_district_details_html(
        snapshot,
        district="Kirehe",
        metric="Branches",
        unit="count",
        reporting_date="2026-10-24",
        filters=filters,
    )
    missing_snapshot = _nbr_district_snapshot(
        points,
        page="branches",
        metric="Branches",
        filters=filters,
        unit="count",
        reporting_date="2026-10-24",
        district="Gasabo",
        expected_district_count=30,
    )
    missing = _nbr_district_details_html(
        missing_snapshot,
        district="Gasabo",
        metric="Branches",
        unit="count",
        reporting_date="2026-10-24",
        filters=filters,
    )

    assert '<div class="insp-value">0<span> count</span></div>' in observed_zero
    assert "#2 of 2" in observed_zero
    assert "Snapshot low 0" in observed_zero
    assert "Snapshot high 12" in observed_zero
    assert "Change since 2025-11-20" in observed_zero
    assert '<div class="insp-value">Unavailable<span> count</span></div>' in missing
    assert "Descriptive rank" in missing
    assert "District rank" not in missing


def test_nbr_district_quality_messages_are_deduplicated_and_renderable():
    qualification = {
        "message": "District agent totals exceed the national KPI."
    }
    points = [
        _point(
            page="agents",
            metric="Agents",
            value=10,
            geography="Kirehe",
            filters={"Institution Type": "E-money Issuers"},
            unit="count",
            quality_qualifications=[qualification],
        ),
        _point(
            page="agents",
            metric="Agents",
            value=11,
            geography="Muhanga",
            filters={"Institution Type": "E-money Issuers"},
            unit="count",
            quality_qualifications=[qualification],
        ),
    ]

    assert _nbr_district_quality_messages(points) == [
        "District agent totals exceed the national KPI."
    ]


def test_nbr_map_click_selection_is_limited_to_observed_districts():
    event = {
        "selection": {
            "points": [
                {"location": "Muhanga"},
            ],
        },
    }

    assert _nbr_clicked_selection(event, ["Kirehe", "Muhanga"], "Kirehe") == "Muhanga"
    assert _nbr_clicked_selection(event, ["Kirehe"], "Kirehe") is None


def test_nbr_reset_view_restores_map_orientation_without_clearing_analysis():
    script = (
        "import streamlit as st\n"
        "import src.pages.nbr_dashboard as dashboard\n"
        "st.session_state['nbr_dx_map_tilt'] = 35\n"
        "st.session_state['nbr_dx_map_rotation'] = -20\n"
        "st.session_state['nbr_dx_reset_revision'] = 2\n"
        "st.session_state['nbr_source_page_district'] = 'Branches'\n"
        "st.session_state['selected_district'] = 'Kirehe'\n"
        "dashboard._reset_nbr_map_view()\n"
    )

    app = AppTest.from_string(script).run()

    assert not app.exception, [error.value for error in app.exception]
    assert app.session_state["nbr_dx_map_tilt"] == 0
    assert app.session_state["nbr_dx_map_rotation"] == 0
    assert app.session_state["nbr_dx_reset_revision"] == 3
    assert app.session_state["nbr_source_page_district"] == "Branches"
    assert app.session_state["selected_district"] == "Kirehe"


def _header_point(spec, reporting_date, value, **overrides):
    return {
        "page": spec["page"],
        "metric_label": spec["metric"],
        "source_type": "national_kpi",
        "geography_level": "national",
        "geography": "Rwanda",
        "filters": spec["filters"],
        "unit": "count",
        "unit_status": "configured_source_label",
        "reporting_date": reporting_date,
        "value": value,
        **overrides,
    }


def _infrastructure_point(
    spec,
    *,
    geography,
    level,
    value,
    reporting_date="2026-10-24",
    **overrides,
):
    is_district = level == "district"
    metric = spec["district_metric"] if is_district else spec["national_metric"]
    return {
        "page": spec["page"],
        "metric_label": metric,
        "source_type": "district_table" if is_district else "national_kpi",
        "geography_level": level,
        "geography": geography,
        "filters": spec["filters"],
        "unit": "count",
        "unit_status": "source_column" if is_district else "configured_source_label",
        "reporting_date": reporting_date,
        "value": value,
        "source_record_id": f"{spec['page']}-{geography}-{reporting_date}",
        "run_id": f"{spec['page']}-{reporting_date}",
        "collected_at": f"{reporting_date}T12:00:00+00:00",
        **overrides,
    }


def _customer_comparison_point(
    comparison,
    group,
    *,
    geography,
    value,
    reporting_date="2026-10-27",
    **overrides,
):
    return {
        "page": "inclusion",
        "metric_label": "Customers",
        "source_type": "district_table",
        "geography_level": "district",
        "geography": geography,
        "filters": group["filters"],
        "unit": "count",
        "unit_status": "source_column",
        "reporting_date": reporting_date,
        "value": value,
        "combo_key": f"{comparison['key']}-{group['label']}",
        "run_id": f"{comparison['key']}-{group['label']}-run",
        "source_record_id": f"{comparison['key']}-{group['label']}-{geography}",
        "collected_at": f"{reporting_date}T12:00:00+00:00",
        **overrides,
    }


def _customer_total_point(institution, value, reporting_date="2026-10-27"):
    filters = {
        "Gender": "All",
        "Age Segment": "All",
        "Institution Type": institution,
        "Account/Policy Status": "Active",
        "Location": "All",
    }
    return {
        "page": "inclusion",
        "metric_label": "Total Customers",
        "source_type": "national_kpi",
        "geography_level": "national",
        "geography": "Rwanda",
        "filters": filters,
        "unit": "count",
        "unit_status": "configured_source_label",
        "reporting_date": reporting_date,
        "value": value,
        "repeated_snapshot_warning": False,
    }


def _population_header_points(reporting_date="2026-10-27"):
    values = {
        "Female": 4_151_429,
        "Male": 4_518_709,
        "Youth": 2_734_346,
        "Non-Youth": 5_935_792,
    }
    return [
        _point(
            page="inclusion",
            metric="Total Customers",
            date=reporting_date,
            value=values[group["label"]],
            geography="Rwanda",
            level="national",
            filters=group["filters"],
            unit="count",
            unit_status="configured_source_label",
            repeated_snapshot_warning=False,
        )
        for comparison in NATIONAL_CUSTOMER_COMPARISONS
        for group in comparison["groups"]
    ]


def test_nbr_supply_header_has_only_approved_latest_eligible_cards():
    points = [
        _header_point(NATIONAL_HEADER_KPIS[0], "2026-10-24", 17_386_969),
        _header_point(NATIONAL_HEADER_KPIS[0], "2026-10-27", 17_449_006),
        _header_point(NATIONAL_HEADER_KPIS[0], "2026-10-27", 999, filters={
            **NATIONAL_HEADER_KPIS[0]["filters"],
            "Institution Type": "Banks",
        }),
        _header_point(NATIONAL_HEADER_KPIS[1], "2026-10-27", 6_482),
        _header_point(NATIONAL_HEADER_KPIS[2], "2026-10-24", 1_991),
        _header_point(
            NATIONAL_HEADER_KPIS[2],
            "2026-10-27",
            1_991,
            repeated_snapshot_warning=True,
        ),
    ]

    html = _national_supply_header_html(points)

    assert html.count('class="kpi"') == 3
    assert "17,449,006" in html
    assert "6,482" in html
    assert "1,991" in html
    assert "2026-10-27" in html
    assert "2026-10-24" in html
    branch_card = re.search(r"Active branches.*?kpi-src\">(.*?)</div>", html, re.S)
    assert branch_card
    assert "2026-10-24" in branch_card.group(1)
    assert "999" not in html
    assert "Observed national value" not in html
    assert "Change from prior observation" not in html
    assert "Reporting dates" not in html
    assert "Coverage" not in html


def test_nbr_supply_header_shows_missing_observations_as_unavailable():
    html = _national_supply_header_html([])

    assert html.count('class="kpi"') == 3
    assert html.count("Unavailable") == 3
    assert "No eligible observation" in html
    assert ">0<" not in html


def test_population_group_header_uses_exact_latest_inclusion_observations():
    points = _population_header_points()
    points.extend([
        _point(
            page="inclusion",
            metric="Total Customers",
            value=999,
            geography="Rwanda",
            level="national",
            filters={
                **NATIONAL_CUSTOMER_COMPARISONS[0]["groups"][0]["filters"],
                "Institution Type": "Banks",
            },
            unit="count",
            unit_status="configured_source_label",
        ),
        _point(
            page="inclusion",
            metric="Total Customers",
            value=888,
            geography="Rwanda",
            level="national",
            filters=NATIONAL_CUSTOMER_COMPARISONS[0]["groups"][0]["filters"],
            unit="percent",
            unit_status="configured_source_label",
        ),
        _point(
            page="finscope",
            metric="Total Customers",
            value=777,
            geography="Rwanda",
            level="national",
            filters=NATIONAL_CUSTOMER_COMPARISONS[0]["groups"][0]["filters"],
            unit="count",
            unit_status="configured_source_label",
        ),
    ])
    unknown_counts = {
        "Gender:Female": 197_630,
        "Gender:Male": 243_942,
        "Age Segment:Youth": 151_121,
        "Age Segment:Non-Youth": 290_451,
    }

    html = _population_group_header_html(points, unknown_counts)

    assert html.count('class="kpi"') == 4
    assert "kpi-track" not in html
    for label in ("Female", "Male", "Youth", "Non-Youth"):
        assert label in html
    for value in ("4,151,429", "4,518,709", "2,734,346", "5,935,792"):
        assert value in html
    assert html.count("Total Customers") == 4
    assert html.count("27 October 2026") == 4
    assert "Filters:" not in html
    assert "Account/Policy Status" not in html
    assert "Institution Type" not in html
    assert "Location:" not in html
    assert "Gender: Female" not in html
    assert "Age Segment: Youth" not in html
    assert "Unknown geography (separate): 197,630" in html
    assert "Unknown geography (separate): 243,942" in html
    assert "Unknown geography (separate): 151,121" in html
    assert "Unknown geography (separate): 290,451" in html


def test_population_group_header_preserves_zero_and_rejects_ambiguous_latest():
    female_filters = NATIONAL_CUSTOMER_COMPARISONS[0]["groups"][0]["filters"]
    zero_point = _point(
        page="inclusion",
        metric="Total Customers",
        date="2026-10-27",
        value=0,
        geography="Rwanda",
        level="national",
        filters=female_filters,
        unit="count",
        unit_status="configured_source_label",
    )
    zero_html = _population_group_header_html([zero_point])
    assert "0<small>customers</small>" in zero_html
    assert "Unknown geography: not verified for this date" in zero_html

    ambiguous_points = [
        _point(
            page="inclusion",
            metric="Total Customers",
            date=reporting_date,
            value=value,
            geography="Rwanda",
            level="national",
            filters=female_filters,
            unit="count",
            unit_status="configured_source_label",
        )
        for reporting_date, value in (
            ("2026-10-24", 4_000_000),
            ("2026-10-27", 4_151_429),
            ("2026-10-27", 4_151_429),
        )
    ]
    ambiguous_html = _population_group_header_html(ambiguous_points)
    female_card = ambiguous_html.split("Female", 1)[1].split(
        '<div class="kpi"', 1
    )[0]
    assert "Unavailable" in female_card
    assert "No unique eligible observation" in female_card


def test_nbr_national_header_uses_shared_hero_and_exactly_three_kpis():
    points = [
        _header_point(spec, "2026-10-27", index + 1)
        for index, spec in enumerate(NATIONAL_HEADER_KPIS[:2])
    ]
    points.append(_header_point(NATIONAL_HEADER_KPIS[2], "2026-10-24", 3))
    script = (
        "import src.pages.nbr_dashboard as dashboard\n"
        f"points = {json.dumps(points)}\n"
        "requested_pages = []\n"
        "_original_dashboard_loader = dashboard.load_nbr_dashboard_data\n"
        "_original_source_loader = dashboard._load_nbr_source_documents\n"
        "_original_national_page = dashboard._render_nbr_national_page\n"
        "def test_loader(version, pages=None):\n"
        "    requested_pages.extend(pages or ())\n"
        "    return points, {'eligible_source_point_count': len(points)}, [], 'test-version'\n"
        "dashboard.load_nbr_dashboard_data = test_loader\n"
        "dashboard._load_nbr_source_documents = lambda *args, **kwargs: ([], [], [], {})\n"
        "dashboard._render_nbr_national_page = lambda *args: None\n"
        "try:\n"
        "    dashboard.render_nbr_page('national')\n"
        "finally:\n"
        "    dashboard.load_nbr_dashboard_data = _original_dashboard_loader\n"
        "    dashboard._load_nbr_source_documents = _original_source_loader\n"
        "    dashboard._render_nbr_national_page = _original_national_page\n"
    )
    app = AppTest.from_string(script, default_timeout=30).run()

    assert not app.exception, [error.value for error in app.exception]
    rendered = " ".join(
        [item.value for item in app.markdown]
        + [item.value for item in app.caption]
    )
    assert rendered.count("pg-hero") == 1
    assert rendered.count('class="kpi"') == 3
    assert rendered.count('class="kpi-grid"') == 1
    assert "NBR Financial Inclusion Overview" in rendered
    assert (
        "Explore Rwanda’s financial inclusion landscape through administrative data "
        "on transactional accounts and financial service infrastructure."
    ) in rendered
    assert "--kpi-columns:3" in rendered
    assert "NBR Supply" in rendered
    assert "BETA" in rendered
    assert "Experimental administrative observations for exploration." not in rendered
    assert "Active transactional accounts" in rendered
    assert "Active POS terminals" in rendered
    assert "Active branches" in rendered
    assert "Observed national value" not in rendered


def test_nbr_highlight_metadata_uses_latest_eligible_source_and_unknown_row():
    filters = {
        "Gender": "All",
        "Age Segment": "All",
        "Institution Type": "All",
        "Account/Policy Status": "Active",
        "Location": "All",
    }
    combo_key = json.dumps(filters, sort_keys=True)
    point = {
        "page": "inclusion",
        "metric_label": "Financially Included",
        "source_type": "national_kpi",
        "geography_level": "national",
        "geography": "Rwanda",
        "filters": filters,
        "reporting_date": "2026-10-27",
        "collected_at": "2026-10-27T17:50:01.685000",
        "run_id": "inclusion-run",
        "combo_key": combo_key,
        "value": 97.1,
        "quality_qualifications": [],
    }
    run = {
        "page": "inclusion",
        "snapshot_date": "2026-10-27",
        "combo_key": combo_key,
        "run_id": "inclusion-run",
        "status": "complete",
        "repeated_snapshot_warning": False,
        "filters": filters,
        "collected_at": "2026-10-27T17:50:01.685000",
    }
    kpi_document = {
        "page": "inclusion",
        "snapshot_date": "2026-10-27",
        "combo_key": combo_key,
        "run_id": "inclusion-run",
        "filters": filters,
        "kpis": [{
            "metric_type": "headline_kpi",
            "metric_label": "Financially Included",
            "metric_value": "97.1%",
        }],
    }
    unknown_row = {
        "page": "inclusion",
        "snapshot_date": "2026-10-27",
        "combo_key": combo_key,
        "run_id": "inclusion-run",
        "filters": filters,
        "district": "unknown",
        "district_known": False,
        "values": {"Customers": "441,572"},
    }

    metadata = _national_highlight_metadata(
        [point],
        [run],
        [kpi_document],
        [unknown_row],
    )

    assert metadata["inclusion_value"] == "97.1%"
    assert metadata["inclusion_reporting_date"] == "2026-10-27"
    assert metadata["inclusion_collected_at"] == "2026-10-27T17:50:01.685000"
    assert metadata["unknown_customer_count"] == 441572
    assert metadata["unknown_reporting_date"] == "2026-10-27"

    repeated = {**run, "repeated_snapshot_warning": True}
    unavailable = _national_highlight_metadata(
        [point],
        [repeated],
        [kpi_document],
        [unknown_row],
    )
    assert unavailable["inclusion_value"] is None
    assert unavailable["unknown_customer_count"] is None


def test_nbr_highlights_render_between_header_and_service_area():
    highlights = {
        "inclusion_value": "97.1%",
        "inclusion_reporting_date": "2026-10-27",
        "inclusion_collected_at": "2026-10-27T17:50:01.685000",
        "inclusion_quality_qualifications": [],
        "unknown_customer_count": 441572,
        "unknown_reporting_date": "2026-10-27",
    }
    points = [
        _header_point(spec, reporting_date, value)
        for spec, reporting_date, value in zip(
            NATIONAL_HEADER_KPIS,
            ("2026-10-27", "2026-10-27", "2026-10-24"),
            (17_449_006, 6_482, 1_991),
        )
    ]
    points.append(_customer_total_point("All", 8_670_138))
    for spec, district_values, national_value in (
        (NATIONAL_INFRASTRUCTURE_SERIES[0], (900, 1_063), 1_991),
        (NATIONAL_INFRASTRUCTURE_SERIES[1], (3_000, 3_471), 6_471),
    ):
        for district, value in zip(("Gasabo", "Kirehe"), district_values):
            points.append(_infrastructure_point(
                spec,
                geography=district,
                level="district",
                value=value,
            ))
        if spec["page"] == "pos":
            points.append(_infrastructure_point(
                spec,
                geography="Rwanda",
                level="national",
                value=national_value,
            ))
    group_values = (
        (("Female", 620, 480), ("Male", 680, 520)),
        (("Youth", 300, 240), ("Non-Youth", 1_000, 800)),
    )
    for comparison, comparison_values in zip(
        NATIONAL_CUSTOMER_COMPARISONS,
        group_values,
    ):
        for group, (_label, gasabo_value, kirehe_value) in zip(
            comparison["groups"],
            comparison_values,
        ):
            points.extend([
                _customer_comparison_point(
                    comparison,
                    group,
                    geography="Gasabo",
                    value=gasabo_value,
                ),
                _customer_comparison_point(
                    comparison,
                    group,
                    geography="Kirehe",
                    value=kirehe_value,
                ),
            ])
    script = (
        "import json\n"
        "import src.pages.nbr_dashboard as dashboard\n"
        "import streamlit as st\n"
        f"points = json.loads({json.dumps(json.dumps(points))})\n"
        f"highlights = {json.dumps(highlights)}\n"
        "_original_dashboard_loader = dashboard.load_nbr_dashboard_data\n"
        "_original_national_page = dashboard._render_nbr_national_page\n"
        "_original_savings_activity = dashboard.render_nbr_savings_activity\n"
        "st.session_state['requested_pages'] = []\n"
        "def test_loader(version, pages=None):\n"
        "    st.session_state['requested_pages'].append(list(pages or ()))\n"
        "    return points, {'national_highlights': highlights, "
        "'national_customer_unknown_counts': {'Gender:Female': 197630, "
        "'Gender:Male': 243942, 'Age Segment:Youth': 151121, "
        "'Age Segment:Non-Youth': 290451}}, [], 'test-version'\n"
        "dashboard.load_nbr_dashboard_data = test_loader\n"
        "dashboard._render_nbr_national_page = lambda *args: None\n"
        "dashboard.render_nbr_savings_activity = lambda: st.markdown("
        "'Recorded Savings-Service Activity')\n"
        "try:\n"
        "    dashboard.render_nbr_page('national')\n"
        "finally:\n"
        "    dashboard.load_nbr_dashboard_data = _original_dashboard_loader\n"
        "    dashboard._render_nbr_national_page = _original_national_page\n"
        "    dashboard.render_nbr_savings_activity = _original_savings_activity\n"
    )
    app = AppTest.from_string(script, default_timeout=30).run()

    assert not app.exception, [error.value for error in app.exception]
    rendered = " ".join(
        [item.value for item in app.markdown]
        + [item.value for item in app.caption]
        + [item.value for item in app.warning]
    )
    assert rendered.count("pg-hero") == 1
    assert rendered.count('class="kpi"') == 3
    assert rendered.count("NBR Data Highlights") == 1
    assert "97.1%" in rendered
    assert "27 October 2026" in rendered
    assert "441,572" in rendered
    assert "unknown" in rendered
    assert (
        rendered.index("NBR Data Highlights")
        < rendered.index("Recorded Savings-Service Activity")
        < rendered.index("Recorded Financial-Service Infrastructure by District")
        < rendered.index("NBR Customer Counts by District and Demographic Group")
    )
    assert "Female vs Male" in rendered
    assert "Youth vs Non-Youth" in rendered
    assert "Gender: Female" in rendered
    assert "Age Segment: Youth" in rendered
    assert "Unknown district" in rendered
    assert "Female: 197,630 · Male: 243,942" in rendered
    assert "Youth: 151,121 · Non-Youth: 290,451" in rendered
    assert "These are administrative customer counts" not in rendered
    assert "Interpretation" not in rendered
    assert "Service area" not in rendered
    assert "National measure" not in rendered
    assert "District sum" not in rendered
    assert "differs from the national KPI" not in rendered
    assert "How to read these counts" not in rendered
    assert any("inclusion" in pages for pages in app.session_state["requested_pages"])
    assert all("agents" not in pages for pages in app.session_state["requested_pages"])
    assert len(app.get("plotly_chart")) == 7
    assert len(app.warning) == 0


@pytest.mark.parametrize(
    "spec",
    NATIONAL_INFRASTRUCTURE_SERIES,
)
def test_nbr_infrastructure_series_requires_exact_eligible_scope(spec):
    district = _infrastructure_point(
        spec,
        geography="Kirehe",
        level="district",
        value=12,
    )
    national = _infrastructure_point(
        spec,
        geography="Rwanda",
        level="national",
        value=20,
    )
    mismatched_filter = {
        **district,
        "filters": {**spec["filters"], "Institution Type": "Banks"},
    }
    wrong_date = {
        **district,
        "reporting_date": "2026-10-27",
        "repeated_snapshot_warning": True,
    }
    unknown_district = {**district, "geography": "unknown"}

    districts, national_point = _national_infrastructure_series(
        [
            district,
            national,
            mismatched_filter,
            wrong_date,
            unknown_district,
        ],
        spec,
    )

    assert districts == [district]
    assert national_point == national


@pytest.mark.parametrize(
    "spec",
    NATIONAL_INFRASTRUCTURE_SERIES,
)
def test_nbr_infrastructure_series_rejects_duplicate_observations(spec):
    district = _infrastructure_point(
        spec,
        geography="Kirehe",
        level="district",
        value=12,
    )
    national = _infrastructure_point(
        spec,
        geography="Rwanda",
        level="national",
        value=20,
    )

    districts, national_point = _national_infrastructure_series(
        [district, {**district, "source_record_id": "duplicate"}, national],
        spec,
    )

    assert districts == []
    assert national_point is None


def test_nbr_infrastructure_figure_keeps_distinct_count_axis_and_provenance():
    spec = NATIONAL_INFRASTRUCTURE_SERIES[0]
    points = [
        _infrastructure_point(
            spec,
            geography="Gasabo",
            level="district",
            value=106,
        ),
        _infrastructure_point(
            spec,
            geography="Kirehe",
            level="district",
            value=85,
        ),
    ]

    figure = _national_infrastructure_figure(points, spec)

    assert figure.data[0].type == "bar"
    assert figure.data[0].orientation == "h"
    assert list(figure.data[0].y) == ["Gasabo", "Kirehe"]
    assert list(figure.data[0].text) == ["106.0", "85.0"]
    assert figure.data[0].textposition == "outside"
    assert list(figure.data[0].customdata[1]) == [
        "2026-10-24",
        "branches-2026-10-24",
        "branches-Kirehe-2026-10-24",
        "2026-10-24T12:00:00+00:00",
    ]
    assert figure.layout.xaxis.title.text == "Branches"
    assert figure.layout.xaxis.range[1] > 106
    assert figure.layout.height == 850
    assert figure.data[0].marker.color == "#28669B"

    pos_spec = NATIONAL_INFRASTRUCTURE_SERIES[1]
    pos_figure = _national_infrastructure_figure(
        [
            _infrastructure_point(
                pos_spec,
                geography="Gasabo",
                level="district",
                value=620,
            ),
            _infrastructure_point(
                pos_spec,
                geography="Kirehe",
                level="district",
                value=410,
            ),
        ],
        pos_spec,
    )
    assert [trace.type for trace in pos_figure.data] == ["bar", "scatter"]
    assert pos_figure.data[1].mode == "markers+text"
    assert pos_figure.data[1].marker.color == "#0D8174"
    assert pos_figure.layout.height == 780


@pytest.mark.parametrize("comparison", NATIONAL_CUSTOMER_COMPARISONS)
def test_nbr_customer_comparison_requires_exact_date_filters_and_matched_districts(
    comparison,
):
    points = []
    for group, base in zip(comparison["groups"], (100, 200)):
        points.extend([
            _customer_comparison_point(
                comparison,
                group,
                geography="Gasabo",
                value=base,
            ),
            _customer_comparison_point(
                comparison,
                group,
                geography="Kirehe",
                value=base + 20,
            ),
            _customer_comparison_point(
                comparison,
                group,
                geography="Gasabo",
                value=999,
                reporting_date="2026-10-24",
            ),
            _customer_comparison_point(
                comparison,
                group,
                geography="unknown",
                value=500,
            ),
            _customer_comparison_point(
                comparison,
                group,
                geography="Kirehe",
                value=888,
                filters={**group["filters"], "Institution Type": "Banks"},
            ),
        ])

    observations = _national_customer_comparison_series(points, comparison)

    assert observations is not None
    assert set(observations) == {group["label"] for group in comparison["groups"]}
    assert all(
        {point["geography"] for point in group_points} == {"Gasabo", "Kirehe"}
        for group_points in observations.values()
    )
    assert all(
        point["reporting_date"] == "2026-10-27"
        for group_points in observations.values()
        for point in group_points
    )
    assert all(
        point["geography"] != "unknown"
        for group_points in observations.values()
        for point in group_points
    )

    missing_paired_district = [
        point for point in points
        if not (
            point["geography"] == "Kirehe"
            and point["filters"] == comparison["groups"][1]["filters"]
            and point["reporting_date"] == "2026-10-27"
        )
    ]
    assert _national_customer_comparison_series(
        missing_paired_district,
        comparison,
    ) is None


@pytest.mark.parametrize("comparison", NATIONAL_CUSTOMER_COMPARISONS)
def test_nbr_customer_comparison_figure_pairs_values_in_one_district_order(
    comparison,
):
    observations = {}
    values = ((1_100_000, 320_000), (210_000, 220_000))
    for group, group_values in zip(comparison["groups"], values):
        observations[group["label"]] = [
            _customer_comparison_point(
                comparison,
                group,
                geography=district,
                value=value,
            )
            for district, value in zip(("Gasabo", "Kirehe"), group_values)
        ]

    figure = _national_customer_comparison_figure(observations, comparison)

    assert [trace.name for trace in figure.data] == [
        group["label"] for group in comparison["groups"]
    ]
    assert list(figure.data[0].y) == ["Gasabo", "Kirehe"]
    assert list(figure.data[1].y) == ["Gasabo", "Kirehe"]
    assert list(figure.data[0].text) == ["1.1M", "320k"]
    assert list(figure.data[1].text) == ["210k", "220k"]
    assert [trace.orientation for trace in figure.data] == ["h", "h"]
    assert figure.layout.barmode == "group"
    assert figure.layout.xaxis.title.text == "Customers (count)"
    assert figure.layout.xaxis.range[1] > 1_100_000
    assert figure.layout.xaxis.tickformat == ".3~s"
    assert figure.layout.height == 980
    assert len(figure.data[0].customdata) == 2


def test_nbr_customer_demographic_charts_have_no_institution_selector():
    points = []
    for comparison in NATIONAL_CUSTOMER_COMPARISONS:
        for group, group_base in zip(comparison["groups"], (100, 200)):
            points.extend([
                _customer_comparison_point(
                    comparison,
                    group,
                    geography="Gasabo",
                    value=group_base,
                ),
                _customer_comparison_point(
                    comparison,
                    group,
                    geography="Kirehe",
                    value=group_base + 10,
                ),
            ])
    script = (
        "import json\n"
        "import src.pages.nbr_dashboard as dashboard\n"
        f"points = json.loads({json.dumps(json.dumps(points))})\n"
        "dashboard._render_nbr_customer_counts_by_district(points, {})\n"
    )
    app = AppTest.from_string(script, default_timeout=30).run()

    assert not app.exception, [error.value for error in app.exception]
    assert not any(
        widget.label == "Institution Type"
        for widget in app.selectbox
    )
    charts = [json.loads(chart.proto.spec) for chart in app.get("plotly_chart")]
    assert len(charts) == 2
    assert charts[0]["data"][0]["x"] == [110, 100]
    assert charts[1]["data"][0]["x"] == [110, 100]
    assert all(
        "Institution Type: All" in trace["customdata"][0][4]
        for chart in charts
        for trace in chart["data"]
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (955, "955"),
        (1_500, "1.5k"),
        (15_500, "16k"),
        (1_260_000, "1.3M"),
    ],
)
def test_nbr_customer_count_labels_use_human_readable_scale(value, expected):
    assert _compact_customer_count(value) == expected


def test_nbr_customer_comparison_renders_two_full_width_charts():
    points = [_customer_total_point("All", 2_000_000)]
    for comparison in NATIONAL_CUSTOMER_COMPARISONS:
        for group, base in zip(comparison["groups"], (1_200_000, 900_000)):
            points.extend([
                _customer_comparison_point(
                    comparison,
                    group,
                    geography="Gasabo",
                    value=base,
                ),
                _customer_comparison_point(
                    comparison,
                    group,
                    geography="Kirehe",
                    value=base // 2,
                ),
            ])
    script = (
        "import json\n"
        "import streamlit as st\n"
        "import src.pages.nbr_dashboard as dashboard\n"
        f"points = json.loads({json.dumps(json.dumps(points))})\n"
        "st.session_state['chart_heights'] = []\n"
        "st.session_state['chart_stretch'] = []\n"
        "_original_plotly_chart = st.plotly_chart\n"
        "def capture_chart(figure, *args, **kwargs):\n"
        "    st.session_state['chart_heights'].append(figure.layout.height)\n"
        "    st.session_state['chart_stretch'].append(kwargs.get('use_container_width'))\n"
        "    return _original_plotly_chart(figure, *args, **kwargs)\n"
        "dashboard.st.plotly_chart = capture_chart\n"
        "try:\n"
        "    dashboard._render_nbr_customer_counts_by_district(points, {})\n"
        "finally:\n"
        "    dashboard.st.plotly_chart = _original_plotly_chart\n"
    )

    app = AppTest.from_string(script, default_timeout=30).run()

    assert not app.exception, [error.value for error in app.exception]
    assert len(app.get("plotly_chart")) == 2
    assert len(app.get("column")) == 0
    assert app.session_state["chart_heights"] == [980, 980]
    assert app.session_state["chart_stretch"] == [True, True]


def test_nbr_customer_unknown_counts_require_matching_complete_source_rows():
    points = []
    runs = []
    table_documents = []
    expected = {}
    for comparison in NATIONAL_CUSTOMER_COMPARISONS:
        for index, group in enumerate(comparison["groups"], start=1):
            point = _customer_comparison_point(
                comparison,
                group,
                geography="Gasabo",
                value=index * 100,
            )
            points.append(point)
            run = {
                "page": "inclusion",
                "snapshot_date": "2026-10-27",
                "combo_key": point["combo_key"],
                "run_id": point["run_id"],
                "status": "complete",
                "repeated_snapshot_warning": False,
                "collected_at": "2026-10-27T17:50:01.685000",
                "filters": group["filters"],
            }
            runs.append(run)
            unknown_count = index * 10_000
            expected[group["unknown_key"]] = unknown_count
            table_documents.append({
                "page": "inclusion",
                "snapshot_date": "2026-10-27",
                "combo_key": point["combo_key"],
                "run_id": point["run_id"],
                "filters": group["filters"],
                "district": "unknown",
                "district_known": False,
                "values": {"Customers": f"{unknown_count:,}"},
            })

    assert _national_customer_unknown_counts(
        points,
        runs,
        table_documents,
    ) == expected

    repeated_runs = [
        {**run, "repeated_snapshot_warning": True}
        if index == 0 else run
        for index, run in enumerate(runs)
    ]
    unavailable = _national_customer_unknown_counts(
        points,
        repeated_runs,
        table_documents,
    )
    assert unavailable[NATIONAL_CUSTOMER_COMPARISONS[0]["groups"][0]["unknown_key"]] is None


def test_nbr_highlight_charts_have_distinct_snapshot_visuals():
    points = [
        _header_point(spec, reporting_date, value)
        for spec, reporting_date, value in zip(
            NATIONAL_HEADER_KPIS,
            ("2025-02-20", "2025-02-20", "2025-02-20"),
            (13_992_018, 4_842, 2_022),
        )
    ]

    account_chart = _national_highlight_figure([points[0]], "transactional")
    pos_chart = _national_highlight_figure([points[1]], "pos")
    branch_chart = _national_highlight_figure([points[2]], "branches")

    assert account_chart.data[0].type == "scatter"
    assert account_chart.data[0].fill == "tozeroy"
    assert account_chart.data[0].line.color == "#247D8B"
    assert pos_chart.data[0].type == "bar"
    assert pos_chart.data[0].marker.color == ("#D8E5F1",)
    assert [trace.type for trace in branch_chart.data] == ["scatter", "scatter"]
    assert branch_chart.data[1].marker.symbol == "diamond"
    assert account_chart.layout.height == pos_chart.layout.height == branch_chart.layout.height == 310
    for chart in (account_chart, pos_chart, branch_chart):
        assert chart.layout.xaxis.type == "category"
        assert chart.data[-1].x[-1] == "2025-02-20"
        assert chart.layout.yaxis.range[0] == 0
        assert chart.layout.yaxis.range[1] > max(chart.data[-1].y)
        assert chart.layout.margin.t == 48
        assert chart.data[-1].cliponaxis is False


def test_nbr_registry_attaches_only_approved_relationships():
    point = _point()
    registry = build_nbr_indicator_registry([point])

    assert registry[0]["mappings"] == [{
        "indicator_variable": "k1",
        "indicator_label": "Bank-account ownership",
        "relationship": "contextual_indicator",
        "limitations": "Branch presence is not individual account ownership.",
    }]


def test_combined_mappings_abstain_for_unobserved_and_unresolved_dimensions():
    point = _point(
        page="inclusion",
        metric="Customers",
        filters={
            "Gender": "All",
            "Age Segment": "All",
            "Institution Type": "Banks",
            "Account/Policy Status": "Active",
            "Location": "All",
        },
    )

    unresolved = _mapped_series(
        [point],
        "k1",
        geography_level="district",
        geography="Kirehe",
    )
    age = _mapped_series(
        [point],
        "k1",
        geography_level="district",
        geography="Kirehe",
        subgroup_type="Age group",
        subgroup="Youth",
    )
    education = _mapped_series(
        [point],
        "k1",
        geography_level="district",
        geography="Kirehe",
        subgroup_type="Education",
        subgroup="Secondary",
    )

    assert len(unresolved) == 1
    assert unresolved[0]["relationship"] == "proxy_with_unresolved_definition"
    assert unresolved[0]["points"][0]["value"] == 5
    assert age == []
    assert education == []


def test_population_group_families_require_observed_multiple_categories():
    male_filters = {"Gender": "Male", "Institution Type": "Banks"}
    female_filters = {"Gender": "Female", "Institution Type": "Banks"}
    points = [
        _point(
            page="inclusion",
            metric="Customers",
            level="national",
            geography="Rwanda",
            filters=male_filters,
        ),
        _point(
            page="inclusion",
            metric="Customers",
            level="national",
            geography="Rwanda",
            filters=female_filters,
        ),
        _point(
            page="inclusion",
            metric="Customers",
            level="national",
            geography="Rwanda",
            date="2026-08-20",
            filters=male_filters,
        ),
    ]

    families = _group_families(points, "Gender")

    assert len(families) == 1
    assert set(families[0]["groups"]) == {"Male", "Female"}
    assert sum(len(items) for items in families[0]["groups"].values()) == 3
    assert _group_families(points, "Education") == []


def _population_group_points():
    points = []
    for dimension, groups in (
        ("Gender", ("Female", "Male")),
        ("Age Segment", ("Youth", "Non-Youth")),
    ):
        for group_index, group in enumerate(groups):
            filters = {
                "Gender": group if dimension == "Gender" else "All",
                "Age Segment": group if dimension == "Age Segment" else "All",
                "Institution Type": "All",
            }
            for reporting_date, date_offset in (
                ("2026-10-24", 0),
                ("2026-10-27", 10),
            ):
                points.append(_point(
                    page="inclusion",
                    metric="Total Customers",
                    date=reporting_date,
                    value=100 + group_index * 20 + date_offset,
                    geography="Rwanda",
                    level="national",
                    filters=filters,
                    unit="count",
                ))
            for district_index, district in enumerate(("Kirehe", "Muhanga")):
                for reporting_date, date_offset in (
                    ("2026-10-24", 0),
                    ("2026-10-27", 10),
                    ("2026-10-26", 20),
                ):
                    if reporting_date == "2026-10-27" and group == groups[0] and district == "Kirehe":
                        continue
                    points.append(_point(
                        page="inclusion",
                        metric="Customers",
                        date=reporting_date,
                        value=5 + group_index * 2 + district_index + date_offset,
                        geography=district,
                        level="district",
                        filters=filters,
                        unit="count",
                    ))
            points.append(_point(
                page="inclusion",
                metric="Customers",
                date="2026-10-27",
                value=999,
                geography="Unknown",
                level="unknown",
                filters=filters,
                unit="count",
            ))
    for gender, group_index in (("Female", 0), ("Male", 1)):
        bank_filters = {
            "Gender": gender,
            "Age Segment": "All",
            "Institution Type": "Banks",
        }
        points.append(_point(
            page="inclusion",
            metric="Total Customers",
            date="2026-10-24",
            value=210 + group_index,
            geography="Rwanda",
            level="national",
            filters=bank_filters,
            unit="count",
        ))
        for district_index, district in enumerate(("Kirehe", "Muhanga")):
            points.append(_point(
                page="inclusion",
                metric="Customers",
                date="2026-10-24",
                value=20 + group_index + district_index,
                geography=district,
                level="district",
                filters=bank_filters,
                unit="count",
            ))
    return points


def test_population_group_families_keep_metric_source_and_filter_scopes_separate():
    points = _population_group_points()
    points.extend([
        _point(
            page="inclusion",
            metric="Total Customers",
            value=500,
            geography="Rwanda",
            level="national",
            filters={
                "Gender": "Female",
                "Age Segment": "All",
                "Institution Type": "Banks",
            },
            unit="count",
        ),
        _point(
            page="inclusion",
            metric="Total Customers",
            value=600,
            geography="Rwanda",
            level="national",
            filters={
                "Gender": "Male",
                "Age Segment": "All",
                "Institution Type": "Banks",
            },
            unit="count",
        ),
        _point(
            page="inclusion",
            metric="Customers",
            value=500,
            geography="Rwanda",
            level="national",
            filters={
                "Gender": "Female",
                "Age Segment": "All",
                "Institution Type": "All",
            },
            unit="count",
        ),
        _point(
            page="inclusion",
            metric="Total Customers",
            value=500,
            geography="Rwanda",
            level="national",
            filters={
                "Gender": "Female",
                "Age Segment": "All",
                "Institution Type": "All",
            },
            unit="count",
            repeated_snapshot_warning=True,
        ),
    ])

    national = _population_group_families(
        points,
        dimension="Gender",
        geography_level="national",
        source_type="national_kpi",
    )
    district = _population_group_families(
        _eligible_nbr_district_points(points),
        dimension="Gender",
        geography_level="district",
        source_type="district_table",
        metric_label="Customers",
        unit="count",
    )

    assert {
        (family["metric_label"], family["base_filters"]["Institution Type"])
        for family in national
    } == {
        ("Total Customers", "All"),
        ("Total Customers", "Banks"),
    }
    all_scope_national = next(
        family for family in national
        if family["base_filters"]["Institution Type"] == "All"
    )
    assert _population_family_dates(all_scope_national, "Gender") == [
        "2026-10-24",
        "2026-10-27",
    ]
    assert {(family["metric_label"], family["source_type"]) for family in district} == {
        ("Customers", "district_table"),
    }
    all_scope_district = next(
        family for family in district
        if family["base_filters"]["Institution Type"] == "All"
    )
    assert _population_family_dates(all_scope_district, "Gender") == [
        "2026-10-24",
        "2026-10-26",
        "2026-10-27",
    ]
    assert all(
        point["geography"] != "Unknown"
        for family in district
        for group_points in family["groups"].values()
        for point in group_points
    )


def test_population_district_plot_preserves_missing_values_and_zero():
    points = [
        point for point in _population_group_points()
        if not (
            point["source_type"] == "district_table"
            and point["reporting_date"] == "2026-10-27"
            and point["geography"] == "Muhanga"
            and point["filters"]["Gender"] == "Female"
        )
    ]
    points.append(_point(
        page="inclusion",
        metric="Customers",
        date="2026-10-27",
        value=0,
        geography="Muhanga",
        level="district",
        filters={
            "Gender": "Female",
            "Age Segment": "All",
            "Institution Type": "All",
        },
        unit="count",
    ))
    families = _population_group_families(
        _eligible_nbr_district_points(points),
        dimension="Gender",
        geography_level="district",
        source_type="district_table",
        metric_label="Customers",
        unit="count",
    )
    family = next(
        item for item in families
        if item["base_filters"]["Institution Type"] == "All"
    )

    result = _prepare_population_district_result(
        points,
        family,
        dimension="Gender",
        reporting_date="2026-10-27",
        expected_districts=("Kirehe", "Muhanga"),
    )
    figure, rows = _population_district_figure(
        result,
        dimension="Gender",
    )

    assert [row["District"] for row in rows] == ["Kirehe", "Muhanga"]
    assert rows[0]["Female"] == "Not reported"
    assert rows[1]["Female"] == "0"
    assert [trace.name for trace in figure.data] == ["Female", "Male"]
    assert all(trace.type == "bar" for trace in figure.data)
    assert figure.layout.barmode == "group"
    assert list(figure.layout.yaxis.categoryarray) == ["Kirehe", "Muhanga"]
    assert list(figure.data[0].x) == [0]
    assert all(
        "Source record" not in trace.hovertemplate
        and "Collection run" not in trace.hovertemplate
        for trace in figure.data
    )
    assert all("999" not in str(trace.x) for trace in figure.data)
    assert result["coverage"] == {
        "both": 1,
        "partial": 1,
        "none": 0,
        "expected": 2,
    }


def test_population_national_values_keep_source_unit_and_missing_category_explicit():
    points = [
        _point(
            page="savings",
            metric="Saved",
            date="2026-10-27",
            value=12,
            geography="Rwanda",
            level="national",
            filters={
                "Gender": "Female",
                "Age Segment": "All",
                "Institution Type": "All",
            },
            unit="",
        ),
    ]
    family = {
        "page": "savings",
        "metric_label": "Saved",
        "unit": "",
        "unit_status": "configured_source_label",
        "geography_level": "national",
        "geography": "Rwanda",
        "source_type": "national_kpi",
        "base_filters": {
            "Age Segment": "All",
            "Institution Type": "All",
        },
        "groups": {"Female": [], "Male": []},
    }
    result = _prepare_population_national_result(
        points,
        family,
        dimension="Gender",
        reporting_date="2026-10-27",
    )
    script = (
        "import src.pages.nbr_dashboard as dashboard\n"
        f"result = {result!r}\n"
        "dashboard._render_population_national_values(\n"
        "    result, dimension='Gender'\n"
        ")\n"
    )
    app = AppTest.from_string(script).run()
    rendered = "\n".join(markdown.value for markdown in app.markdown)
    rendered += "\n" + "\n".join(caption.value for caption in app.caption)
    national_spec = json.loads(app.get("plotly_chart")[0].proto.spec)

    assert not app.exception, [error.value for error in app.exception]
    assert national_spec["data"][0]["type"] == "bar"
    assert national_spec["data"][0]["orientation"] == "h"
    assert "Source record" not in national_spec["data"][0]["hovertemplate"]
    assert "Saved" in rendered
    assert national_spec["data"][0]["x"] == [12.0]
    assert "Not reported for this exact scope." in rendered
    assert "Unit not recorded by source" in rendered
    assert "Institution Type:" not in rendered
    assert "Location:" not in rendered
    assert "Selected filters:" not in rendered
    assert not any(
        expander.label == "Source and filter details"
        for expander in app.expander
    )
    assert "Gap" not in rendered
    assert "%" not in rendered


def test_population_national_history_uses_exact_paired_dates_and_preserves_irregular_spacing():
    points = _population_group_points()
    families = _population_group_families(
        points,
        dimension="Gender",
        geography_level="national",
        source_type="national_kpi",
    )
    family = next(
        item for item in families
        if item["base_filters"]["Institution Type"] == "All"
    )
    mismatched_scope = _point(
        page="inclusion",
        metric="Total Customers",
        date="2026-10-25",
        value=9999,
        geography="Rwanda",
        level="national",
        filters={
            "Gender": "Female",
            "Age Segment": "All",
            "Institution Type": "Banks",
        },
        unit="count",
    )
    result = _prepare_population_national_history(
        [*points, mismatched_scope],
        family,
        dimension="Gender",
        selected_reporting_date="2026-10-24",
    )
    figure = _population_national_history_figure(result, dimension="Gender")

    assert result["dates"] == ["2026-10-24", "2026-10-27"]
    assert [trace.name for trace in figure.data] == ["Female", "Male"]
    assert list(figure.data[0].x) == ["2026-10-24", "2026-10-27"]
    assert list(figure.data[0].y) == [100.0, 110.0]
    assert list(figure.data[0].marker.size) == [12, 8]
    assert figure.layout.xaxis.type == "date"
    assert "Total Customers" in figure.data[0].customdata[0][3]
    assert result["groups"]["Female"]["2026-10-24"]["point"]["unit"] == "count"
    assert result["groups"]["Female"]["2026-10-24"]["point"]["source_record_id"]


def test_population_national_history_omits_unpaired_dates_without_interpolation():
    points = [
        point for point in _population_group_points()
        if not (
            point["source_type"] == "national_kpi"
            and point["reporting_date"] == "2026-10-24"
            and point["filters"]["Gender"] == "Male"
            and point["filters"]["Institution Type"] == "All"
        )
    ]
    family = next(
        item for item in _population_group_families(
            points,
            dimension="Gender",
            geography_level="national",
            source_type="national_kpi",
        )
        if item["base_filters"]["Institution Type"] == "All"
    )

    result = _prepare_population_national_history(
        points,
        family,
        dimension="Gender",
        selected_reporting_date="2026-10-24",
    )

    assert result["status"] == "available"
    assert result["dates"] == ["2026-10-27"]
    assert result["selected_reporting_date"] == "2026-10-24"
    assert result["groups"]["Male"]["2026-10-24"]["status"] == "missing"


def test_population_district_continuity_classifies_both_one_and_neither_and_excludes_unknown():
    points = _population_group_points()
    unknown_point = _point(
        page="inclusion",
        metric="Customers",
        date="2026-10-27",
        value=0,
        geography="Unknown",
        level="district",
        source_type="district_table",
        filters={
            "Gender": "Female",
            "Age Segment": "All",
            "Institution Type": "All",
        },
        unit="count",
    )
    points.append(unknown_point)
    mismatched_scope = _point(
        page="inclusion",
        metric="Customers",
        date="2026-10-25",
        value=999,
        geography="Kirehe",
        level="district",
        source_type="district_table",
        filters={
            "Gender": "Female",
            "Age Segment": "All",
            "Institution Type": "Banks",
        },
        unit="count",
    )
    points.append(mismatched_scope)
    family = next(
        item for item in _population_group_families(
            _eligible_nbr_district_points(points),
            dimension="Gender",
            geography_level="district",
            source_type="district_table",
            metric_label="Customers",
            unit="count",
        )
        if item["base_filters"]["Institution Type"] == "All"
    )
    result = _prepare_population_district_continuity(
        points,
        family,
        dimension="Gender",
        expected_districts=("Muhanga", "Kirehe", "Nyagatare"),
        selected_reporting_date="2026-10-27",
    )
    figure = _population_district_continuity_figure(result, dimension="Gender")
    date_index = result["dates"].index("2026-10-27")
    cells = {
        district: figure.data[0].z[index][date_index]
        for index, district in enumerate(result["district_names"])
    }

    assert result["status"] == "varies"
    assert "2026-10-25" not in result["dates"]
    assert cells["Muhanga"] == 2
    assert cells["Kirehe"] == 1
    assert cells["Nyagatare"] == 0
    assert result["districts"]["2026-10-27"]["Muhanga"]["Female"]["point"]["value"] == 16
    assert result["unknown_groups"]["2026-10-27"]["Female"]["status"] == "observed"
    assert "Unknown" not in figure.data[0].y
    assert list(figure.data[0].x) == result["dates"]
    assert "Female:" in figure.data[0].customdata[0][date_index][1]
    assert result["coverage_by_date"]["2026-10-27"] == {
        "both": 1,
        "one": 1,
        "neither": 1,
    }


def test_population_district_continuity_suppresses_complete_coverage():
    points = []
    for reporting_date in ("2026-10-24", "2026-10-27"):
        for group in ("Female", "Male"):
            for district in ("Kirehe", "Muhanga"):
                points.append(_point(
                    page="inclusion",
                    metric="Customers",
                    date=reporting_date,
                    value=0,
                    geography=district,
                    level="district",
                    source_type="district_table",
                    filters={
                        "Gender": group,
                        "Age Segment": "All",
                        "Institution Type": "All",
                    },
                    unit="count",
                ))
    family = next(
        item for item in _population_group_families(
            points,
            dimension="Gender",
            geography_level="district",
            source_type="district_table",
            metric_label="Customers",
            unit="count",
        )
    )

    result = _prepare_population_district_continuity(
        points,
        family,
        dimension="Gender",
        expected_districts=("Kirehe", "Muhanga"),
        selected_reporting_date="2026-10-27",
    )

    assert result["status"] == "complete"
    assert result["coverage"] == {"both": 4, "one": 0, "neither": 0}
    assert all(
        result["districts"][reporting_date][district][group]["status"] == "observed"
        for reporting_date in result["dates"]
        for district in ("Kirehe", "Muhanga")
        for group in ("Female", "Male")
    )


def test_population_district_continuity_hides_section_when_coverage_is_complete(monkeypatch):
    def unexpected_render(*args, **kwargs):
        pytest.fail("Complete district coverage should not render a section.")

    monkeypatch.setattr(
        "src.pages.nbr_dashboard.st.container",
        unexpected_render,
    )

    _render_population_district_continuity(
        {"status": "complete"},
        dimension="Gender",
    )


def test_population_preparation_matches_exact_filters_and_keeps_source_scopes_separate():
    points = _population_group_points()
    national = _population_group_families(
        points,
        dimension="Gender",
        geography_level="national",
        source_type="national_kpi",
    )
    family = next(
        item for item in national
        if item["base_filters"]["Institution Type"] == "All"
    )
    mismatched = _point(
        page="inclusion",
        metric="Total Customers",
        date="2026-10-27",
        value=9999,
        geography="Rwanda",
        level="national",
        filters={
            "Gender": "Female",
            "Age Segment": "All",
            "Institution Type": "Banks",
        },
        unit="count",
    )
    district_only = _point(
        page="inclusion",
        metric="Customers",
        date="2026-10-27",
        value=8888,
        geography="Rwanda",
        level="national",
        filters={
            "Gender": "Female",
            "Age Segment": "All",
            "Institution Type": "All",
        },
        unit="count",
    )
    result = _prepare_population_national_result(
        [*points, mismatched, district_only],
        family,
        dimension="Gender",
        reporting_date="2026-10-27",
    )

    assert result["status"] == "available"
    assert result["groups"]["Female"]["point"]["value"] == 110
    assert result["groups"]["Female"]["point"]["unit"] == "count"
    assert result["groups"]["Female"]["point"]["source_record_id"]
    assert result["groups"]["Female"]["point"]["filters"]["Institution Type"] == "All"


def test_population_preparation_distinguishes_zero_missing_and_conflicting_duplicates():
    points = _population_group_points()
    family = next(
        item for item in _population_group_families(
            points,
            dimension="Gender",
            geography_level="national",
            source_type="national_kpi",
        )
        if item["base_filters"]["Institution Type"] == "All"
    )
    female = _point(
        page="inclusion",
        metric="Total Customers",
        date="2026-10-27",
        value=0,
        geography="Rwanda",
        level="national",
        filters={
            "Gender": "Female",
            "Age Segment": "All",
            "Institution Type": "All",
        },
        unit="count",
    )
    duplicate = dict(female, value=1, source_record_id="conflicting-source-record")
    points = [
        point for point in points
        if not (
            point["source_type"] == "national_kpi"
            and point["reporting_date"] == "2026-10-27"
            and point["filters"]["Gender"] == "Female"
            and point["filters"]["Institution Type"] == "All"
        )
    ]
    points.extend([female, duplicate])

    result = _prepare_population_national_result(
        points,
        family,
        dimension="Gender",
        reporting_date="2026-10-27",
    )

    assert result["status"] == "partial"
    assert result["groups"]["Female"]["status"] == "conflicting_duplicates"
    assert result["groups"]["Female"]["point"] is None
    assert result["groups"]["Male"]["status"] == "observed"
    assert result["groups"]["Male"]["point"]["value"] == 130
    zero_result = _prepare_population_national_result(
        [female, *[
            point for point in points
            if point["source_type"] == "national_kpi"
            and point["reporting_date"] == "2026-10-27"
            and point["filters"]["Gender"] == "Male"
            and point["filters"]["Institution Type"] == "All"
        ]],
        family,
        dimension="Gender",
        reporting_date="2026-10-27",
    )
    assert zero_result["groups"]["Female"]["status"] == "observed"
    assert zero_result["groups"]["Female"]["point"]["value"] == 0


def test_population_district_preparation_reports_partial_coverage_and_unknown_geography():
    points = _population_group_points()
    family = next(
        item for item in _population_group_families(
            _eligible_nbr_district_points(points),
            dimension="Gender",
            geography_level="district",
            source_type="district_table",
            metric_label="Customers",
            unit="count",
        )
        if item["base_filters"]["Institution Type"] == "All"
    )
    result = _prepare_population_district_result(
        points,
        family,
        dimension="Gender",
        reporting_date="2026-10-27",
        expected_districts=("Kirehe", "Muhanga", "Nyagatare"),
    )

    assert result["status"] == "partial_coverage"
    assert result["coverage"] == {
        "both": 1,
        "partial": 1,
        "none": 1,
        "expected": 3,
    }
    assert result["districts"]["Kirehe"]["Female"]["status"] == "missing"
    assert result["districts"]["Muhanga"]["Female"]["point"]["value"] == 16
    unknown_point = _point(
        page="inclusion",
        metric="Customers",
        date="2026-10-27",
        value=999,
        geography="Unknown",
        level="unknown",
        filters={
            "Gender": "Female",
            "Age Segment": "All",
            "Institution Type": "All",
        },
        unit="count",
        source_type="district_table",
    )
    result = _prepare_population_district_result(
        [*points, unknown_point],
        family,
        dimension="Gender",
        reporting_date="2026-10-27",
        expected_districts=("Kirehe", "Muhanga", "Nyagatare"),
    )
    assert result["unknown_groups"]["Female"]["status"] == "observed"
    assert result["unknown_groups"]["Female"]["point"]["geography"] == "Unknown"
    figure, _ = _population_district_figure(result, dimension="Gender")
    assert all(999 not in trace.x for trace in figure.data)


def test_population_sections_resolve_independently_and_empty_district_reference_is_unavailable():
    points = _population_group_points()
    national_family = next(
        item for item in _population_group_families(
            points,
            dimension="Gender",
            geography_level="national",
            source_type="national_kpi",
        )
        if item["base_filters"]["Institution Type"] == "All"
    )
    national_result = _prepare_population_national_result(
        points,
        national_family,
        dimension="Gender",
        reporting_date="2026-10-27",
    )
    unavailable_district_result = _prepare_population_district_result(
        points,
        None,
        dimension="Gender",
        reporting_date="2026-10-27",
        expected_districts=("Kirehe", "Muhanga"),
    )
    empty_reference_result = _prepare_population_district_result(
        points,
        next(
            item for item in _population_group_families(
                points,
                dimension="Gender",
                geography_level="district",
                source_type="district_table",
                metric_label="Customers",
                unit="count",
            )
            if item["base_filters"]["Institution Type"] == "All"
        ),
        dimension="Gender",
        reporting_date="2026-10-27",
        expected_districts=(),
    )

    assert national_result["status"] == "available"
    assert unavailable_district_result["status"] == "unavailable"
    assert empty_reference_result["status"] == "unavailable"
    assert empty_reference_result["coverage"]["expected"] == 0


def test_population_subscriber_indicator_is_clear_without_relabeling_source_metric():
    options = _population_indicator_options([
        {
            "metric_label": "Subscribers",
            "unit": "count",
            "unit_status": "configured_source_label",
            "base_filters": {"Institution Type": "E-money issuers"},
        },
    ])

    assert [option["label"] for option in options] == [
        "Reported subscriber metric",
    ]
    assert options[0]["families"][0]["metric_label"] == "Subscribers"


def test_mode_selector_persists_selected_value_in_streamlit_session():
    app = AppTest.from_string(
        "from src.pages.nbr_dashboard import render_mode_selector\n"
        "render_mode_selector()"
    ).run()
    assert not app.exception
    assert app.session_state["global_dashboard_mode"] == "Combined"
    assert len(app.radio) == 0
    assert {
        app.button(key=f"dashboard_mode_{mode.lower().replace(' ', '_')}").label
        for mode in ("Combined", "FinScope", "NBR Supply")
    } == {"Combined", "FinScope", "NBR Supply"}

    app.button(key="dashboard_mode_nbr_supply").click().run()

    assert not app.exception
    assert app.session_state["global_dashboard_mode"] == "NBR Supply"


def test_beta_notice_renders_its_content():
    app = AppTest.from_string(
        "from src.pages.nbr_dashboard import render_beta_notice\n"
        "render_beta_notice()"
    ).run()

    assert not app.exception
    assert any("experimental signals" in item.value for item in app.markdown)


def test_mongodb_history_query_is_page_scoped_and_read_only(monkeypatch):
    observed_queries = []
    events = []

    class Cursor:
        def batch_size(self, _size):
            return self

        def max_time_ms(self, _milliseconds):
            return self

        def __iter__(self):
            return iter(())

    class Collection:
        def find(self, query, projection):
            observed_queries.append((query, projection))
            return Cursor()

    class Database:
        def __getitem__(self, _name):
            return Collection()

    class Client:
        def __init__(self, *_args, **_kwargs):
            events.append(("client", "opened"))

        def __getitem__(self, _name):
            return Database()

        def close(self):
            events.append(("client", "closed"))

    monkeypatch.setattr(pymongo, "MongoClient", Client)
    monkeypatch.setenv("MONGODB_URI", "mongodb://read-only-test.invalid")

    runs, kpis, tables = load_mongodb_history(pages=("branches", "credit"))
    scoped_runs, scoped_kpis, scoped_tables = load_mongodb_history(
        scope_keys=(("branches", "2026-10-24", "institution=All"),)
    )

    assert (runs, kpis, tables) == ([], [], [])
    assert (scoped_runs, scoped_kpis, scoped_tables) == ([], [], [])
    exact_query = {
        "$or": [{
            "page": "branches",
            "snapshot_date": "2026-10-24",
            "combo_key": "institution=All",
        }]
    }
    assert [query for query, _ in observed_queries[:3]] == [
        {"page": {"$in": ["branches", "credit"]}},
    ] * 3
    assert [query for query, _ in observed_queries[3:]] == [exact_query] * 3
    assert events == [
        ("client", "opened"),
        ("client", "closed"),
        ("client", "opened"),
        ("client", "closed"),
    ]


def test_registry_identity_is_stable_for_same_source_series():
    point = _point()

    first = build_nbr_indicator_registry([point])
    second = build_nbr_indicator_registry([json.loads(json.dumps(point))])

    assert first[0]["id"] == second[0]["id"]


def test_source_data_version_is_deterministic_and_changes_with_observations():
    first = _point(value=5)
    second = _point(date="2026-10-25", value=6)

    version = _source_data_version([first, second])

    assert _source_data_version([second, first]) == version
    assert _source_data_version([first, {**second, "value": 7}]) != version


def test_shared_district_map_keeps_choropleth_and_adds_nbr_markers():
    geojson = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "properties": {"shapeName": "Kirehe"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[
                    29.7, -2.5
                ], [29.8, -2.5], [29.8, -2.4], [29.7, -2.4], [29.7, -2.5]]],
            },
        }],
    }
    frame = pd.DataFrame([{
        "District": "Kirehe",
        "Owns a bank account (%)": 5.4,
        "Valid respondents": 464,
        "rank": 30,
        "diff": -14.8,
    }])
    settings = {
        "basemap": "Light",
        "palette": "Indicator colours",
        "opacity": 0.85,
        "spotlight": "Off",
        "labels": False,
        "tilt": 0,
        "rotation": 0,
        "zoom": 7.3,
    }

    figure = build_map(
        frame,
        geojson,
        {"Kirehe": (-2.45, 29.75)},
        (-2.45, 29.75),
        {"scale": ["#EAF6F3", "#0E2A35"], "accent": "#1A8A7D"},
        "Owns a bank account (%)",
        20.2,
        "Kirehe",
        "Bank account",
        settings,
        supply_points=[{
            "geography": "Kirehe",
            "metric_label": "Branches",
            "value": 3,
            "unit": "branches",
            "reporting_date": "2026-10-24",
        }],
    )

    assert [trace.type for trace in figure.data] == ["choroplethmap", "scattermap"]
    assert figure.data[1].name == "NBR supply · marker size"
    assert [str(value) for value in figure.data[1].customdata[0]] == [
        "Branches",
        "3",
        "branches",
        "2026-10-24",
        "Kirehe",
    ]
    assert figure.data[0].marker.line.color == "#FFFFFF"


def test_nbr_map_style_is_opt_in_and_keeps_3d_navigation_and_missing_values():
    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"shapeName": district},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[
                        29.7, -2.5
                    ], [29.8, -2.5], [29.8, -2.4], [29.7, -2.4], [29.7, -2.5]]],
                },
            }
            for district in ("Kirehe", "Muhanga", "Gasabo")
        ],
    }
    frame = pd.DataFrame([
        {"District": "Kirehe", "Value": 0, "rank": 2, "diff": None},
        {"District": "Muhanga", "Value": 5, "rank": 1, "diff": None},
    ])
    settings = {
        "basemap": "Dark",
        "palette": "Indicator colours",
        "opacity": 0.94,
        "spotlight": "Off",
        "labels": False,
        "tilt": 35,
        "rotation": 21,
        "zoom": 7.3,
        "uirevision": "test-reset-revision",
    }

    selected_snapshot = {
        "dated": [
            {"geography": "Kirehe", "value": 0},
            {"geography": "Muhanga", "value": 5},
        ],
        "series": [
            {"geography": "Kirehe", "value": 0},
            {"geography": "Kirehe", "value": 30},
            {"geography": "Muhanga", "value": 5},
        ],
    }
    figure = build_map(
        frame,
        geojson,
        {"Kirehe": (-2.45, 29.75), "Muhanga": (-2.45, 29.75)},
        (-2.45, 29.75),
        {"scale": []},
        "Value",
        None,
        "Kirehe",
        "Branches",
        settings,
        value_unit="count",
        nbr_style=True,
        hover_context="2026-10-24\nBranch Status: Active · Institution Type: All",
        value_range=_nbr_district_snapshot_value_range(selected_snapshot),
    )
    map_layout = figure.layout.map if hasattr(figure.layout, "map") else figure.layout.mapbox

    assert list(figure.data[0].locations) == ["Kirehe", "Muhanga"]
    assert figure.data[0].zmin == 0
    assert figure.data[0].zmax == 5
    assert figure.data[0].colorscale[0][1] == "#167B76"
    assert figure.data[0].colorscale[-1][1] == "#F3D27A"
    assert "2026-10-24" in figure.data[0].hovertemplate
    assert "Branch Status: Active" in figure.data[0].hovertemplate
    assert "count" in figure.data[0].colorbar.title.text
    assert figure.data[0].colorbar.tickformat == ",.0f"
    assert frame["District"].to_list() == ["Kirehe", "Muhanga"]
    assert map_layout.pitch == 35
    assert map_layout.bearing == 21
    assert figure.layout.uirevision == "test-reset-revision"
    assert {layer.color for layer in map_layout.layers if layer.type == "line"} >= {
        "#F8F5EA",
        "#F3D27A",
    }
    assert map_layout.layers[-1].source["features"][0]["properties"]["shapeName"] == "Kirehe"
    changed_metric = build_map(
        frame.assign(Value=[10, 20]),
        geojson,
        {"Kirehe": (-2.45, 29.75), "Muhanga": (-2.45, 29.75)},
        (-2.45, 29.75),
        {"scale": []},
        "Value",
        None,
        "Kirehe",
        "Agents",
        settings,
        value_unit="count",
        nbr_style=True,
        hover_context="2026-10-27\nAgent Status: Active · Institution Type: E-money Issuers",
        value_range=(10, 20),
        nbr_institution="E-money Issuers",
    )
    assert list(changed_metric.data[0].z) == [10, 20]
    assert changed_metric.data[0].zmin == 10
    assert changed_metric.data[0].zmax == 20
    assert changed_metric.data[0].colorbar.title.text == "Agents · count"
    assert changed_metric.data[0].colorscale[0][1] == "#F2ECFA"
    assert changed_metric.data[0].colorscale != figure.data[0].colorscale


def test_nbr_map_color_range_uses_only_the_selected_snapshot_and_keeps_zero():
    snapshot = {
        "dated": [
            {"geography": "Kirehe", "value": 0},
            {"geography": "Muhanga", "value": 12},
        ],
        "series": [
            {"geography": "Kirehe", "value": 0},
            {"geography": "Kirehe", "value": 90},
            {"geography": "Muhanga", "value": 12},
        ],
    }

    assert _nbr_district_snapshot_value_range(snapshot) == (0.0, 12.0)
    assert _nbr_district_snapshot_value_range({"dated": [], "series": [91]}) == (
        0.0,
        0.0,
    )


def _dashboard_points():
    points = [
        _point(
            metric="Total Branches",
            level="national",
            geography="Rwanda",
            date="2026-08-20",
            value=104,
        ),
        _point(
            metric="Total Branches",
            level="national",
            geography="Rwanda",
            date="2026-10-24",
            value=152,
        ),
    ]
    for district, base in (("Kirehe", 3), ("Muhanga", 5)):
        points.extend([
            _point(date="2026-08-20", value=base, geography=district),
            _point(date="2026-10-24", value=base + 1, geography=district),
        ])
    for gender, value in (("Female", 34), ("Male", 42)):
        for reporting_date in ("2026-08-20", "2026-10-24"):
            points.append(_point(
                page="inclusion",
                metric="Customers",
                date=reporting_date,
                value=value,
                geography="Rwanda",
                level="national",
                filters={"Gender": gender, "Institution Type": "Banks"},
            ))
    return points


def _population_dashboard_points():
    dashboard_points = [
        point for point in _dashboard_points()
        if not (
            point["page"] == "inclusion"
            and point["metric_label"] == "Customers"
            and point["geography_level"] == "national"
        )
    ]
    return [*dashboard_points, *_population_group_points()]


@pytest.mark.parametrize(
    "view, expected_text",
    [
        ("national", "NBR Financial Inclusion Overview"),
        ("district", "NBR District Insights"),
        ("population", "Population Group Insights"),
        ("priority", "Priority explorer"),
    ],
)
def test_nbr_supply_pages_render_with_observed_synthetic_points(view, expected_text):
    points = (
        _population_dashboard_points()
        if view == "population"
        else _dashboard_points()
    )
    if view == "priority":
        points = [
            {
                **point,
                "unit_status": "source_column",
                "combo_key": json.dumps(point["filters"], sort_keys=True),
            } if point["source_type"] == "district_table" else point
            for point in points
        ]
    render_call = f"dashboard.render_nbr_page({view!r}, selected_district='Kirehe')"
    script = (
        "import json\n"
        "import streamlit as st\n"
        "import src.pages.nbr_dashboard as dashboard\n"
        f"points = json.loads({json.dumps(json.dumps(points))})\n"
        "st.session_state['requested_pages'] = []\n"
        "_original_dashboard_loader = dashboard.load_nbr_dashboard_data\n"
        "_original_catalog_loader = dashboard.load_nbr_page_catalog\n"
        "_original_current_mode = dashboard.current_mode\n"
        "def dashboard_test_loader(version, pages=None, scope_keys=None):\n"
        "    st.session_state['requested_pages'].append(pages)\n"
        "    selected = [point for point in points if pages is None or point['page'] in pages]\n"
        "    if scope_keys is not None:\n"
        "        identities = {tuple(key) for key in scope_keys}\n"
        "        selected = [point for point in selected if "
        "(point['page'], point['reporting_date'], point.get('combo_key', '')) in identities]\n"
        "    return selected, {'eligible_source_point_count': len(selected)}, "
        "dashboard.build_nbr_indicator_registry(selected), "
        "dashboard._source_data_version(selected)\n"
        "def catalog_test_loader(version, page):\n"
        "    grouped = {}\n"
        "    for point in points:\n"
        "        if point['page'] != page or point['source_type'] != 'district_table':\n"
        "            continue\n"
        "        identity = (page, point['reporting_date'], point['combo_key'])\n"
        "        run = grouped.setdefault(identity, {'page': page, "
        "'snapshot_date': point['reporting_date'], 'combo_key': point['combo_key'], "
        "'status': 'complete', 'table_status': 'extracted', "
        "'table_columns': ['District', point['metric_label']], "
        "'filters': point['filters']})\n"
        "    return list(grouped.values()), 'synthetic-catalog', {}\n"
        "dashboard.load_nbr_dashboard_data = dashboard_test_loader\n"
        "dashboard.load_nbr_page_catalog = catalog_test_loader\n"
        "dashboard.current_mode = lambda: 'NBR Supply'\n"
        "try:\n"
        f"    {render_call}\n"
        "finally:\n"
        "    dashboard.load_nbr_dashboard_data = _original_dashboard_loader\n"
        "    dashboard.load_nbr_page_catalog = _original_catalog_loader\n"
        "    dashboard.current_mode = _original_current_mode\n"
    )
    app = AppTest.from_string(script, default_timeout=90).run()

    assert not app.exception, [error.value for error in app.exception]
    rendered = "\n".join(markdown.value for markdown in app.markdown)
    assert expected_text.casefold() in rendered.casefold()
    if view == "district":
        assert "NBR District Insights" in rendered
        assert "Explore NBR-reported service and customer measures" in rendered
        assert "NBR Supply" in rendered
        assert "BETA" in rendered
        assert rendered.count('class="kpi"') == 4
        assert rendered.index("NBR District Insights") < rendered.index(
            "NBR district controls"
        )
        assert (
            "NBR reports administrative data by service. Pick one to explore."
            not in rendered
        )
        service_area = next(
            box for box in app.selectbox if box.label == "Service area"
        )
        assert service_area.value == "Branches"
        assert "Selected district value" in rendered
        assert "Branches" in rendered
        assert "Kirehe" in rendered
        assert "4" in rendered
        assert "+1" in rendered
        assert "2026-08-20 → 2026-10-24" in rendered
        assert "<small> / 30</small>" in rendered
        assert "Branches · <b>Kirehe</b>" in rendered
        assert "Reported 2026-10-24" in rendered
        selected_value_card_start = rendered.index('<div class="kpi"')
        next_card_start = rendered.index('<div class="kpi"', selected_value_card_start + 1)
        selected_value_card = rendered[selected_value_card_start:next_card_start]
        assert "Branch Status: Active" not in selected_value_card
        assert "District sum" not in selected_value_card
        assert rendered.count("NBR district controls") == 1
        assert rendered.count(
            "Historical Change &amp; Coverage Watchlist"
        ) == 1
        assert sum(
            chart.key.startswith("nbr_dx_distribution_")
            for chart in app.get("plotly_chart")
        ) == 1
        assert sum(
            chart.key.startswith("nbr_dx_history_heatmap_")
            for chart in app.get("plotly_chart")
        ) == 1
        assert rendered.count("Descriptive rank") == 1
        assert any(box.label == "Measure" for box in app.selectbox)
        assert not any(
            caption.value.startswith(("Measure:", "Source:"))
            for caption in app.caption
        )
        assert not any(box.label == "Source metric" for box in app.selectbox)
        assert not any(box.label == "Observed filter coverage" for box in app.selectbox)
        assert any(box.label == "Reporting date" for box in app.selectbox)
        assert any(box.label == "District" for box in app.selectbox)
        district_key = f"nbr_district_selected_{_source_data_version(points)}"
        app.selectbox(key=district_key).select("Muhanga").run()
        assert not app.exception, [error.value for error in app.exception]
        assert app.session_state[district_key] == "Muhanga"
        rerendered = "\n".join(markdown.value for markdown in app.markdown)
        assert "Muhanga" in rerendered
        assert sum(chart.key == "nbr_dx_map" for chart in app.get("plotly_chart")) == 1
        assert sum(
            chart.key.startswith("nbr_dx_history_selected_")
            for chart in app.get("plotly_chart")
        ) == 1
    if view == "population":
        rendered += "\n" + "\n".join(caption.value for caption in app.caption)
        assert "NBR Supply" in rendered
        assert "BETA" in rendered
        assert "NBR-reported financial-service activity across demographic groups." in rendered
        assert rendered.count('class="kpi"') == 4
        assert rendered.count("Population Group Insights") == 1
        assert "Comparison controls" in rendered
        assert (
            "NBR reports administrative data by service. Pick one to explore."
            not in rendered
        )
        assert "National values by group" in rendered
        assert "District customer counts by group" in rendered
        assert "National group history" in rendered
        assert "District reporting continuity" in rendered
        assert "Total Customers" in rendered
        assert "Customers [count]" in rendered
        assert "population-adjusted inclusion rates" in rendered
        assert "Gap between groups" not in rendered
        assert "percentage difference" not in rendered
        assert "Selected filters:" not in rendered
        assert "Institution Type: E-money issuers" not in rendered
        assert "Location: All" not in rendered
        assert app.session_state["requested_pages"][-1] == ("inclusion",)
        assert any(box.label == "Service area" for box in app.selectbox)
        service_area = next(
            box for box in app.selectbox if box.label == "Service area"
        )
        assert service_area.value == "Inclusion"
        assert {control.label for control in app.get("segmented_control")} == {
            "Compare by",
        }
        compare_by = app.get("segmented_control")[0]
        assert tuple(compare_by.options) == ("Gender", "Age Segment")
        charts = app.get("plotly_chart")
        assert len(charts) == 4
        assert [chart.key.split("_Gender")[0] for chart in charts] == [
            "nbr_population_national",
            "nbr_population_history",
            "nbr_population_district",
            "nbr_population_continuity",
        ]
        assert any(
            chart.key.startswith(
                "nbr_population_national_Gender_2026-10-27_"
            )
            for chart in charts
        )
        history_chart = next(
            chart for chart in charts
            if chart.key.startswith("nbr_population_history_")
        )
        history_spec = json.loads(history_chart.proto.spec)
        assert len(history_spec["data"]) == 2
        assert history_spec["data"][0]["type"] == "scatter"
        assert history_spec["data"][0]["mode"] == "lines+markers"
        continuity_chart = next(
            chart for chart in charts
            if chart.key.startswith("nbr_population_continuity_")
        )
        continuity_spec = json.loads(continuity_chart.proto.spec)
        assert continuity_spec["data"][0]["type"] == "heatmap"
        assert any(
            chart.key.startswith(
                "nbr_population_district_Gender_2026-10-27_"
            )
            for chart in charts
        )
        pills = app.get("pills")
        assert any(pill.label == "Indicator" for pill in pills)
        institution_pills = [
            pill for pill in pills if pill.label == "Institution Type"
        ]
        assert len(institution_pills) == 2
        initial_date_pill = next(
            pill for pill in pills if pill.label == "Reporting date"
        )
        assert "26 October 2026 · Districts" in initial_date_pill.options
        assert "27 October 2026 · National + Districts" in initial_date_pill.options
        institution_pills[0].select("Banks").run()
        assert not app.exception, [error.value for error in app.exception]
        date_pill = next(
            pill for pill in app.get("pills")
            if pill.label == "Reporting date"
        )
        assert "27 October 2026 · Districts" in date_pill.options
        shared_date = "24 October 2026 · National + Districts"
        assert shared_date in date_pill.options
        date_pill.select(shared_date).run()
        assert not app.exception, [error.value for error in app.exception]
        national_chart = next(
            chart for chart in app.get("plotly_chart")
            if chart.key.startswith("nbr_population_national_")
        )
        national_spec = json.loads(national_chart.proto.spec)
        assert national_spec["data"][0]["x"] == [210.0, 211.0]
        history_chart = next(
            chart for chart in app.get("plotly_chart")
            if chart.key.startswith("nbr_population_history_")
        )
        history_spec = json.loads(history_chart.proto.spec)
        assert history_spec["data"][0]["x"] == ["2026-10-24"]
        assert history_spec["data"][0]["marker"]["size"] == [12]
        institution_pills = [
            pill for pill in app.get("pills")
            if pill.label == "Institution Type"
        ]
        institution_pills[1].select("Banks").run()
        assert not app.exception, [error.value for error in app.exception]
        assert "Education" not in "\n".join(
            markdown.value for markdown in app.markdown
        )
        dimension_control = next(
            control for control in app.get("segmented_control")
            if control.label == "Compare by"
        )
        dimension_control.select("Age Segment").run()
        assert not app.exception, [error.value for error in app.exception]
        rerendered = "\n".join(markdown.value for markdown in app.markdown)
        assert "Youth" in rerendered
        history_chart = next(
            chart for chart in app.get("plotly_chart")
            if chart.key.startswith("nbr_population_history_Age Segment_")
        )
        history_spec = json.loads(history_chart.proto.spec)
        assert [trace["name"] for trace in history_spec["data"]] == [
            "Youth",
            "Non-Youth",
        ]
        assert "Non-Youth" in rerendered
    map_keys = {
        chart.key
        for chart in app.get("plotly_chart")
        if chart.key in {"nbr_dx_map", "nbr_national_map"}
    }
    if view == "district":
        assert "nbr_dx_map" in map_keys
    if view == "population":
        assert map_keys == set()
    if view == "priority":
        service_area = next(
            selectbox for selectbox in app.selectbox
            if selectbox.label == "Service area"
        )
        if not any(
            chart.key.startswith("nbr_priority_distribution_")
            for chart in app.get("plotly_chart")
        ):
            service_area.select("branches").run()
            assert not app.exception, [error.value for error in app.exception]
        priority_control_labels = {
            control.label
            for control in [*app.get("pills"), *app.selectbox]
        }
        assert priority_control_labels == {
            "Institution Type",
            "Age Segment",
            "Gender",
            "Service area",
            "Inspect a district",
            "Reporting date",
        }
        assert {
            pill.label for pill in app.get("pills")
        } == {"Institution Type", "Age Segment", "Gender"}
        header_html = next(
            markdown.value for markdown in app.markdown
            if "Priority Explorer" in markdown.value
        )
        rendered = "\n".join(markdown.value for markdown in app.markdown)
        assert rendered.index("Priority Explorer") < rendered.index("Choose evidence")
        assert header_html.count('class="kpi"') == 3
        assert "Districts reporting" in header_html
        assert "Highest reported count" in header_html
        assert "Lowest reported count" in header_html
        assert "24 October 2026" in header_html
        assert "Branch Status: Active" in header_html
        assert not any(selectbox.label == "Basemap" for selectbox in app.selectbox)
        assert map_keys == set()
        assert any(
            "District observations" in markdown.value
            for markdown in app.markdown
        )
        assert any(
            "Priority Explorer" in markdown.value
            for markdown in app.markdown
        )
        assert any(selectbox.label == "Inspect a district" for selectbox in app.selectbox)
        date_select = next(
            selectbox for selectbox in app.selectbox
            if selectbox.label == "Reporting date"
        )
        assert date_select.options == ["2026-08-20", "2026-10-24"]
        date_select.select("2026-08-20").run()
        assert not app.exception, [error.value for error in app.exception]
        current_header = next(
            markdown.value for markdown in app.markdown
            if "Priority Explorer" in markdown.value
        )
        assert current_header == header_html
        distribution = next(
            chart for chart in app.get("plotly_chart")
            if chart.key.startswith("nbr_priority_distribution_")
        )
        distribution_spec = json.loads(distribution.proto.spec)
        assert sorted(
            value
            for trace in distribution_spec["data"]
            for value in _plotly_values(trace["x"])
        ) == [3.0, 5.0]
        assert {
            trace["name"] for trace in distribution_spec["data"]
        } == {"Other districts", "Selected district"}
        history_chart = next(
            chart for chart in app.get("plotly_chart")
            if chart.key.startswith("nbr_priority_history_")
        )
        history_spec = json.loads(history_chart.proto.spec)
        assert history_spec["data"][0]["mode"] == "lines+markers"
        assert history_spec["data"][0]["x"] == [
            "2026-08-20",
            "2026-10-24",
        ]
        district_select = next(
            selectbox for selectbox in app.selectbox
            if selectbox.label == "Inspect a district"
        )
        district_select.select("Muhanga").run()
        assert not app.exception, [error.value for error in app.exception]
        current_header = next(
            markdown.value for markdown in app.markdown
            if "Priority Explorer" in markdown.value
        )
        assert current_header == header_html
        assert any(
            "Muhanga · observed history" in markdown.value
            for markdown in app.markdown
        )


def test_combined_context_renders_separately_from_survey_data():
    points = _dashboard_points()
    script = (
        "import json\n"
        "import streamlit as st\n"
        "import src.pages.nbr_dashboard as dashboard\n"
        f"points = json.loads({json.dumps(json.dumps(points))})\n"
        "st.session_state.setdefault('requested_pages', [])\n"
        "_original_dashboard_loader = dashboard.load_nbr_dashboard_data\n"
        "def dashboard_test_loader(version, pages=None):\n"
        "    st.session_state['requested_pages'].append(pages)\n"
        "    selected = [point for point in points if pages is None or point['page'] in pages]\n"
        "    return selected, {'eligible_source_point_count': len(selected)}, "
        "dashboard.build_nbr_indicator_registry(selected), "
        "dashboard._source_data_version(selected)\n"
        "dashboard.load_nbr_dashboard_data = dashboard_test_loader\n"
        "try:\n"
        "    dashboard.render_combined_context('k1', district='Kirehe')\n"
        "finally:\n"
        "    dashboard.load_nbr_dashboard_data = _original_dashboard_loader\n"
    )
    app = AppTest.from_string(script, default_timeout=30).run()

    assert not app.exception, [error.value for error in app.exception]
    assert app.session_state["requested_pages"] == [("branches",)]
    assert any(
        "NBR supply context · Bank-account ownership" in expander.label
        for expander in app.expander
    )
    assert not any(selectbox.label == "NBR source page" for selectbox in app.selectbox)


def test_context_strip_html_uses_unit_fallback_when_missing():
    fallback = dashboard.context_strip_html({
        "metric_label": "Total Branches",
        "unit": "",
        "limitations": "Source limitation",
        "points": [{"reporting_date": "2026-10-24", "value": 42}],
    })
    assert "unit not specified" in fallback


def test_group_saving_combined_context_excludes_sacco_branches():
    points = [_point(
        page="branches",
        metric="Total Branches",
        date="2026-10-24",
        value=155,
        geography="Kirehe",
        level="district",
        filters={"Institution Type": "Sacco", "Branch Status": "Active", "Location": "All"},
        unit="count",
    )]
    original_loader = dashboard.load_nbr_dashboard_data
    dashboard.load_nbr_dashboard_data = lambda *args, **kwargs: (points, {}, [], "v1")
    try:
        entries, _ = dashboard.load_combined_context_data("g3a_11", geography_level="district", geography="Kirehe")
    finally:
        dashboard.load_nbr_dashboard_data = original_loader
    assert entries == []


def test_combined_national_context_keeps_primary_chart_visible():
    points = _dashboard_points()
    agent_filters = {
        "Gender": "All",
        "Institution Type": "E-money Issuers",
        "Agent Status": "Active",
        "Location": "All",
    }
    sacco_filters = {
        "Institution Type": "Sacco",
        "Branch Status": "Active",
        "Location": "All",
    }
    for page, metric, filters, observations in (
        (
            "agents",
            "Total Agents",
            agent_filters,
            (("2026-08-20", 153971), ("2026-10-24", 155211)),
        ),
        (
            "branches",
            "Total Branches",
            sacco_filters,
            (("2026-08-20", 632), ("2026-10-24", 635)),
        ),
    ):
        points.extend(
            _point(
                page=page,
                metric=metric,
                date=reporting_date,
                value=value,
                geography="Rwanda",
                level="national",
                filters=filters,
                unit="count",
            )
            for reporting_date, value in observations
        )
    script = (
        "import json\n"
        "import streamlit as st\n"
        "import src.pages.nbr_dashboard as dashboard\n"
        "st.session_state['global_dashboard_mode'] = 'Combined'\n"
        f"points = json.loads({json.dumps(json.dumps(points))})\n"
        "st.session_state.setdefault('requested_pages', [])\n"
        "_original_dashboard_loader = dashboard.load_nbr_dashboard_data\n"
        "def dashboard_test_loader(version, pages=None):\n"
        "    st.session_state['requested_pages'].append(pages)\n"
        "    selected = [point for point in points if pages is None or point['page'] in pages]\n"
        "    return selected, {'eligible_source_point_count': len(selected)}, "
        "dashboard.build_nbr_indicator_registry(selected), "
        "dashboard._source_data_version(selected)\n"
        "dashboard.load_nbr_dashboard_data = dashboard_test_loader\n"
        "from src.pages.national_overview import render_national_overview\n"
        "try:\n"
        "    render_national_overview()\n"
        "finally:\n"
        "    dashboard.load_nbr_dashboard_data = _original_dashboard_loader\n"
    )
    app = AppTest.from_string(script, default_timeout=45).run()

    assert not app.exception, [error.value for error in app.exception]
    assert app.session_state["requested_pages"]
    assert len(app.session_state["requested_pages"]) == 1
    chart_keys = {chart.key for chart in app.get("plotly_chart")}
    assert not any(key.startswith("ov_combined_finding_") for key in chart_keys)
    rendered = " ".join(
        [item.value for item in app.markdown]
        + [item.value for item in app.caption]
    )
    assert rendered.split('<div class="sec">', 1)[0].count('class="kpi"') == 2
    assert "Financial inclusion in Rwanda: people and the financial system" in rendered
    assert "Different measures, not a direct comparison" not in rendered


def test_combined_national_overview_uses_only_approved_national_branch_context():
    filters = {
        "Institution Type": "Banks",
        "Branch Status": "Active",
        "Location": "All",
    }
    point = _point(
        page="branches",
        metric="Total Branches",
        date="2026-10-24",
        value=152,
        geography="Rwanda",
        level="national",
        unit="count",
        filters=filters,
    )
    entry = {
        "page": "branches",
        "metric_label": "Total Branches",
        "display_label": "Branches · Total Branches",
        "unit": "count",
        "filters": filters,
        "geography_level": "national",
        "relationship": "contextual_indicator",
        "limitations": "Branch presence is not individual account ownership.",
        "points": [point],
    }
    app = AppTest.from_string(
        "import plotly.graph_objects as go\n"
        "import streamlit as st\n"
        "import src.pages.nbr_dashboard as dashboard\n"
        "import src.pages.national_overview as overview\n"
        "st.session_state['global_dashboard_mode'] = 'Combined'\n"
        "_original_shared_loader = dashboard.load_combined_national_evidence\n"
        "_original_nbr_loader = dashboard.load_nbr_dashboard_data\n"
        "_original_map_figure = overview._map_figure\n"
        f"entry = {entry!r}\n"
        "def test_shared_loader():\n"
        "    st.session_state.setdefault('shared_requests', []).append('called')\n"
        "    return [], [entry]\n"
        "dashboard.load_combined_national_evidence = test_shared_loader\n"
        "def empty_nbr_loader(version, pages=None):\n"
        "    return [], {'eligible_source_point_count': 0}, [], 'empty-fixture'\n"
        "dashboard.load_nbr_dashboard_data = empty_nbr_loader\n"
        "def capture_map(*args, **kwargs):\n"
        "    st.session_state['map_called'] = True\n"
        "    return go.Figure()\n"
        "overview._map_figure = capture_map\n"
        "try:\n"
        "    overview.render_national_overview()\n"
        "finally:\n"
        "    dashboard.load_combined_national_evidence = _original_shared_loader\n"
        "    dashboard.load_nbr_dashboard_data = _original_nbr_loader\n"
        "    overview._map_figure = _original_map_figure\n"
    ).run()

    assert not app.exception, [error.value for error in app.exception]
    rendered = "\n".join(markdown.value for markdown in app.markdown)
    assert app.session_state["shared_requests"] == ["called"]
    assert "Recorded active bank branches" in rendered
    assert "152" in rendered
    assert "2026-10-24" in rendered
    assert "Where the gaps are" not in rendered
    assert "map_called" not in app.session_state


def test_nbr_national_map_uses_only_exact_unit_and_reporting_date(monkeypatch):
    filters = {
        "Institution Type": "Banks",
        "Branch Status": "Active",
        "Location": "All",
    }
    points = [
        _point(
            metric="Customer accounts",
            level="national",
            geography="Rwanda",
            date="2026-10-24",
            value=100,
            filters=filters,
            unit="count",
        ),
        _point(
            metric="Customer accounts",
            geography="Kirehe",
            date="2026-10-24",
            value=20,
            filters=filters,
            unit="count",
        ),
        _point(
            metric="Customer accounts",
            geography="Muhanga",
            date="2026-10-24",
            value=2,
            filters=filters,
            unit="thousands",
        ),
        _point(
            metric="Customer accounts",
            geography="Rwamagana",
            date="2026-10-23",
            value=30,
            filters=filters,
            unit="count",
        ),
    ]
    app = AppTest.from_string(
        "import json\n"
        "import streamlit as st\n"
        "import plotly.graph_objects as go\n"
        "import src.pages.nbr_dashboard as dashboard\n"
        f"points = json.loads({json.dumps(json.dumps(points))})\n"
        "geojson = {'type': 'FeatureCollection', 'features': []}\n"
        "_original_geojson_loader = dashboard.data.load_geojson\n"
        "_original_geo_summary = dashboard.data.geo_summary\n"
        "dashboard.data.load_geojson = lambda: geojson\n"
        "dashboard.data.geo_summary = lambda _: ({}, (None, None))\n"
        "import src.pages.district_explorer as district_page\n"
        "_original_build_map = district_page.build_map\n"
        "def capture_map(frame, *args, **kwargs):\n"
        "    st.session_state['mapped_values'] = frame[['District', 'Value', 'Unit']].to_dict('records')\n"
        "    return go.Figure()\n"
        "district_page.build_map = capture_map\n"
        "registry = dashboard.build_nbr_indicator_registry(points)\n"
        "try:\n"
        "    dashboard._render_nbr_national_page(\n"
        "        points, {'eligible_source_point_count': len(points)}, registry, 'fixture', 'branches'\n"
        "    )\n"
        "finally:\n"
        "    dashboard.data.load_geojson = _original_geojson_loader\n"
        "    dashboard.data.geo_summary = _original_geo_summary\n"
        "    district_page.build_map = _original_build_map\n"
    ).run()

    assert not app.exception, [error.value for error in app.exception]
    assert app.session_state["mapped_values"] == [{
        "District": "Kirehe",
        "Value": 20,
        "Unit": "count",
    }]


def _savings_point(metric, level, reporting_date, value, *, filters=None, geography=None, unit):
    source_type = "district_table" if level == "district" else "national_kpi"
    return {
        "page": "savings",
        "metric_label": metric,
        "reporting_date": reporting_date,
        "value": value,
        "raw_value": value,
        "geography": geography or ("Rwanda" if level == "national" else "Gasabo"),
        "geography_level": level,
        "source_type": source_type,
        "filters": filters or {
            "Gender": "All",
            "Age Segment": "All",
            "Institution Type": "All",
            "Account Status": "Active",
            "Account Type": "All",
            "Location": "All",
        },
        "unit": unit,
        "unit_status": "source_value" if unit == "percent" else "configured_source_label",
        "source_record_id": f"{metric}-{level}-{reporting_date}-{geography}",
        "run_id": f"run-{reporting_date}",
        "combo_key": json.dumps(
            filters or {
                "Gender": "All",
                "Age Segment": "All",
                "Institution Type": "All",
                "Account Status": "Active",
                "Account Type": "All",
                "Location": "All",
            },
            sort_keys=True,
        ),
    }


def test_savings_activity_keeps_observed_dates_and_matching_scope():
    points = [
        _savings_point("Saved", "national", "2025-02-20", 26.5, unit="percent"),
        _savings_point("Total Customers", "national", "2025-02-20", 2_301_293, unit="count"),
        _savings_point("Saved", "national", "2025-11-20", 30.2, unit="percent"),
        _savings_point("Total Customers", "national", "2025-11-20", 2_622_710, unit="count"),
        _savings_point("Saved", "national", "2026-08-20", 31.3, unit="percent"),
        _savings_point("Total Customers", "national", "2026-08-20", 2_791_847, unit="count"),
        _savings_point("Saved", "national", "2026-10-24", 31.9, unit="percent"),
        _savings_point("Saved", "national", "2026-10-27", 32.8, unit="percent"),
        _savings_point("Total Customers", "national", "2026-10-24", 2_845_248, unit="count"),
        _savings_point("Saved", "national", "2026-10-24", 44.0, unit="percent", filters={
            "Gender": "Female",
            "Age Segment": "All",
            "Institution Type": "All",
            "Account Status": "Active",
            "Account Type": "All",
            "Location": "All",
        }),
        _savings_point("Customers", "district", "2026-10-24", 1_390_274, unit="count", geography="Gasabo"),
        _savings_point("Customers", "district", "2026-10-24", 8_463, unit="count", geography="Ngororero"),
    ]

    series = _savings_activity_series(points)

    assert len(series) == 1
    entry = series[0]
    assert entry["saved_dates"] == [
        "2025-02-20",
        "2025-11-20",
        "2026-08-20",
        "2026-10-24",
        "2026-10-27",
    ]
    assert entry["customer_dates"] == [
        "2025-02-20",
        "2025-11-20",
        "2026-08-20",
        "2026-10-24",
    ]
    assert len(entry["districts"]["2026-10-24"]) == 2
    saved_figure = _savings_trend_figure(
        [entry["saved"][day][0] for day in entry["saved_dates"]],
        metric_label="Saved",
        unit="percent",
    )
    count_figure = _savings_trend_figure(
        [entry["customers"][day][0] for day in entry["customer_dates"]],
        metric_label="Total Customers",
        unit="count",
    )
    district_figure = _savings_district_figure([
        *entry["districts"]["2026-10-24"],
        {"geography": "Unknown", "value": 2},
    ])
    assert list(saved_figure.data[0].x) == entry["saved_dates"]
    assert list(saved_figure.data[0].y) == [26.5, 30.2, 31.3, 31.9, 32.8]
    assert list(count_figure.data[0].y) == [2_301_293, 2_622_710, 2_791_847, 2_845_248]
    assert list(district_figure.data[0].y) == ["Gasabo", "Ngororero", "Unknown"]
    assert saved_figure.data[0].type == "scatter"
    assert saved_figure.data[0].fill == "tozeroy"
    assert saved_figure.data[0].line.color == "#087E78"
    assert saved_figure.layout.height == 430
    assert count_figure.data[0].type == "bar"
    assert count_figure.data[0].marker.color == "#3267A8"
    assert count_figure.layout.height == 380
    assert district_figure.data[0].type == "bar"
    assert district_figure.layout.height >= 560
    assert district_figure.layout.plot_bgcolor == "#F7F8F5"
    assert "#D79A2B" in district_figure.data[0].marker.color


def test_unknown_savings_customer_preserves_zero_and_distinguishes_missing():
    filters = {
        "Gender": "All",
        "Age Segment": "All",
        "Institution Type": "All",
        "Account Status": "Active",
        "Account Type": "All",
        "Location": "All",
    }
    filters_key = json.dumps(filters, sort_keys=True)
    run = {
        "page": "savings",
        "snapshot_date": "2026-10-24",
        "combo_key": filters_key,
        "run_id": "savings-run",
        "filters": filters,
        "filters_requested": filters,
        "status": "complete",
        "table_status": "extracted",
        "repeated_snapshot_warning": False,
    }
    unknown_row = {
        "page": "savings",
        "snapshot_date": "2026-10-24",
        "combo_key": filters_key,
        "run_id": "savings-run",
        "filters": filters,
        "filters_requested": filters,
        "district": "unknown",
        "district_known": False,
        "values": {"Customers": "0"},
    }

    assert _unknown_savings_customer(
        [run],
        [unknown_row],
        reporting_date="2026-10-24",
        filters=filters,
    ) == (0, "reported")
    assert _unknown_savings_customer(
        [run],
        [],
        reporting_date="2026-10-24",
        filters=filters,
    ) == (None, "not_reported")
    assert _unknown_savings_customer(
        [run],
        [unknown_row, unknown_row],
        reporting_date="2026-10-24",
        filters=filters,
    ) == (None, "unavailable")


def test_render_nbr_savings_activity_displays_separate_charts_and_limitations(monkeypatch):
    points = [
        _savings_point("Saved", "national", day, value, unit="percent")
        for day, value in (("2025-02-20", 26.5), ("2025-11-20", 30.2))
    ]
    points.extend(
        _savings_point("Total Customers", "national", day, value, unit="count")
        for day, value in (("2025-02-20", 2_301_293), ("2025-11-20", 2_622_710))
    )
    points.extend([
        _savings_point("Customers", "district", "2025-11-20", 10, unit="count", geography="Gasabo"),
    ])
    filters = points[0]["filters"]
    filters_key = json.dumps(filters, sort_keys=True)
    run = {
        "page": "savings",
        "snapshot_date": "2025-11-20",
        "combo_key": filters_key,
        "run_id": "savings-run",
        "filters": filters,
        "filters_requested": filters,
        "status": "complete",
        "table_status": "extracted",
        "repeated_snapshot_warning": False,
    }
    unknown_row = {
        "page": "savings",
        "snapshot_date": "2025-11-20",
        "combo_key": filters_key,
        "run_id": "savings-run",
        "filters": filters,
        "filters_requested": filters,
        "district": "unknown",
        "district_known": False,
        "values": {"Customers": "4"},
    }
    monkeypatch.setattr(
        "src.pages.nbr_dashboard.load_nbr_dashboard_data",
        lambda *_args, **_kwargs: (points, {}, [], "savings-test"),
    )
    monkeypatch.setattr(
        "src.pages.nbr_dashboard._load_nbr_source_documents",
        lambda *_args, **_kwargs: ([run], [], [unknown_row], {}),
    )
    kpi_documents = []
    for reporting_date in ("2025-02-20", "2025-11-20"):
        date_points = [
            point for point in points
            if point["geography_level"] == "national"
            and point["reporting_date"] == reporting_date
        ]
        kpi_documents.append({
            "page": "savings",
            "snapshot_date": reporting_date,
            "combo_key": date_points[0]["combo_key"],
            "run_id": date_points[0]["run_id"],
            "filters": filters,
            "kpis": [
                {
                    "metric_type": "headline_kpi",
                    "metric_label": point["metric_label"],
                    "metric_value": (
                        f'{point["value"]}%'
                        if point["metric_label"] == "Saved"
                        else str(point["value"])
                    ),
                    "metric_value_numeric": point["value"],
                }
                for point in date_points
            ],
        })
    script = (
        "import json\n"
        "import src.pages.nbr_dashboard as dashboard\n"
        f"points = json.loads({json.dumps(json.dumps(points))})\n"
        f"kpis = json.loads({json.dumps(json.dumps(kpi_documents))})\n"
        f"runs = json.loads({json.dumps(json.dumps([run]))})\n"
        f"tables = json.loads({json.dumps(json.dumps([unknown_row]))})\n"
        "dashboard.load_nbr_dashboard_data = lambda *args, **kwargs: (points, {}, [], 'savings-test')\n"
        "dashboard._load_nbr_source_documents = lambda *args, **kwargs: (runs, kpis, tables, {})\n"
        "dashboard.render_nbr_savings_activity()\n"
    )
    app = AppTest.from_string(script, default_timeout=30).run()

    assert not app.exception, [error.value for error in app.exception]
    rendered = " ".join(
        [item.value for item in app.markdown]
        + [item.value for item in app.caption]
    )
    assert "Recorded Savings-Service Activity" in rendered
    assert "Saved · reported percentage" in rendered
    assert "Total Customers · reported count" in rendered
    assert "Interpretation limits" not in rendered
    assert "denominator and definition of NBR’s Saved KPI" not in rendered
    assert "Unknown” is a count reported by NBR without an assigned district." in rendered
    assert "Only districts with reported counts are shown" in rendered
    assert "Source metric: Customers" not in rendered
    assert "Coverage:" not in rendered
    assert "Saved reports:" not in rendered
    assert "Total Customers reports:" not in rendered
    charts = app.get("plotly_chart")
    assert [chart.key.split("_")[-2] for chart in charts[:2]] == ["saved", "customers"]
    assert len(charts) == 3


def test_savings_coverage_uses_observed_filter_buttons_to_form_a_combination():
    series = [
        {"filters": {"Gender": gender, "Institution Type": institution}}
        for gender in ("All", "Female")
        for institution in ("All", "Banks")
    ]
    script = (
        "import streamlit as st\n"
        "import src.pages.nbr_dashboard as dashboard\n"
        f"series = {series!r}\n"
        "selected = dashboard._select_savings_coverage(series, 'coverage-test')\n"
        "st.session_state['selected_filters'] = selected['filters']\n"
    )
    app = AppTest.from_string(script, default_timeout=30).run()

    assert not app.exception, [error.value for error in app.exception]
    controls = app.get("segmented_control")
    assert len(controls) == 2
    assert {tuple(control.options) for control in controls} == {
        ("All", "Female"),
        ("All", "Banks"),
    }
    gender = next(control for control in controls if "Female" in control.options)
    gender.select("Female").run()
    institution = next(
        control
        for control in app.get("segmented_control")
        if "Banks" in control.options
    )
    institution.select("Banks").run()

    assert app.session_state["selected_filters"] == {
        "Gender": "Female",
        "Institution Type": "Banks",
    }
    assert not app.selectbox


def test_savings_coverage_hides_account_type_status_and_location_filters():
    series = [
        {
            "filters": {
                "Account Type": account_type,
                "Account Status": account_status,
                "Location": location,
                "Gender": gender,
                "Institution Type": institution,
            }
        }
        for account_type in ("All", "Savings")
        for account_status in ("Active",)
        for location in ("All", "Kigali")
        for gender in ("All", "Female")
        for institution in ("All", "Banks")
    ]
    script = (
        "import streamlit as st\n"
        "import src.pages.nbr_dashboard as dashboard\n"
        f"series = {series!r}\n"
        "selected = dashboard._select_savings_coverage(series, 'coverage-hidden-test')\n"
        "st.session_state['selected_filters'] = selected['filters']\n"
    )
    app = AppTest.from_string(script, default_timeout=30).run()

    assert not app.exception, [error.value for error in app.exception]
    controls = app.get("segmented_control")
    assert {control.label for control in controls} == {"Gender", "Institution Type"}
    assert all(
        dimension not in {control.label for control in controls}
        for dimension in ("Account Type", "Account Status", "Location")
    )
    assert app.session_state["selected_filters"] == {
        "Account Type": "All",
        "Account Status": "Active",
        "Gender": "All",
        "Institution Type": "All",
        "Location": "All",
    }


def test_district_coverage_uses_observed_filter_buttons_not_a_dropdown():
    series = [
        {
            "filters": {
                "Gender": gender,
                "Institution Type": institution,
                "Location": "All",
            },
        }
        for gender in ("All", "Female")
        for institution in ("All", "Banks")
    ]
    script = (
        "import streamlit as st\n"
        "import src.pages.nbr_dashboard as dashboard\n"
        f"series = {series!r}\n"
        "selected = dashboard._select_observed_filter_combination(\n"
        "    series, 'district-filter-test', state_prefix='nbr_dx_filter_test',\n"
        "    button_dimensions=('Institution Type',), full_width=True\n"
        ")\n"
        "st.session_state['selected_filters'] = selected['filters']\n"
    )
    app = AppTest.from_string(script, default_timeout=30).run()

    assert not app.exception, [error.value for error in app.exception]
    controls = app.get("segmented_control")
    assert len(controls) == 1
    assert not app.selectbox
    assert controls[0].label == "Institution Type"
    assert tuple(controls[0].options) == ("All", "Banks")
    controls[0].select("Banks").run()

    assert app.session_state["selected_filters"] == {
        "Gender": "All",
        "Institution Type": "Banks",
        "Location": "All",
    }


def test_district_coverage_shows_single_value_dimensions_as_buttons():
    filters = {
        "Branch Status": "Active",
        "Institution Type": "All",
        "Location": "All",
    }
    script = (
        "import streamlit as st\n"
        "import src.pages.nbr_dashboard as dashboard\n"
        f"series = [{{'filters': {filters!r}}}]\n"
        "selected = dashboard._select_observed_filter_combination(\n"
        "    series, 'district-single-values', state_prefix='nbr_dx_filter_single',\n"
        "    button_dimensions=('Institution Type',), full_width=True\n"
        ")\n"
        "st.session_state['selected_filters'] = selected['filters']\n"
    )
    app = AppTest.from_string(script, default_timeout=30).run()

    assert not app.exception, [error.value for error in app.exception]
    controls = app.get("segmented_control")
    assert {control.label: tuple(control.options) for control in controls} == {
        "Institution Type": ("All",),
    }


def test_nbr_district_map_border_styles_are_scoped_from_finscope():
    from src.styles import _CSS

    assert ".st-key-card_nbr_dx_map" in _CSS
    assert "border-left:0 !important" in _CSS
    assert ".st-key-card_map" in _CSS
    assert ".st-key-card_nbr_dx_details" in _CSS
