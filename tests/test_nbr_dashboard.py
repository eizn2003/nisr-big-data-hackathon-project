import json
import re

import pandas as pd
import pytest
import pymongo
from streamlit.testing.v1 import AppTest

from src.pages.district_explorer import build_map
from src.pages.nbr_dashboard import (
    _group_families,
    _mapped_series,
    _national_supply_header_html,
    _review_candidate_row,
    _source_data_version,
    NATIONAL_HEADER_KPIS,
    build_nbr_indicator_registry,
    load_mongodb_history,
    render_nbr_page,
    select_review_candidates,
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
        "unit": unit,
        "unit_status": "configured_source_label",
        "source_type": "district_table" if level == "district" else "national_kpi",
        "source_record_id": f"{page}-{metric}-{date}-{geography}",
        "run_id": f"run-{date}",
        "collected_at": f"{date}T12:00:00+00:00",
    }


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
        "def test_loader(version, pages=None):\n"
        "    requested_pages.extend(pages or ())\n"
        "    return points, {'eligible_source_point_count': len(points)}, [], 'test-version'\n"
        "dashboard.load_nbr_dashboard_data = test_loader\n"
        "dashboard._render_nbr_national_page = lambda *args: None\n"
        "dashboard.render_nbr_page('national')\n"
    )
    app = AppTest.from_string(script, default_timeout=30).run()

    assert not app.exception, [error.value for error in app.exception]
    rendered = " ".join(item.value for item in app.markdown)
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
    assert "Active transactional accounts" in rendered
    assert "Active POS terminals" in rendered
    assert "Active branches" in rendered
    assert "Observed national value" not in rendered


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


def test_mode_selector_persists_selected_value_in_streamlit_session():
    app = AppTest.from_string(
        "from src.nbr_dashboard import render_mode_selector\n"
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
        "from src.nbr_dashboard import render_beta_notice\n"
        "render_beta_notice()"
    ).run()

    assert not app.exception
    assert any("experimental signals" in item.value for item in app.markdown)


def test_mongodb_history_query_is_page_scoped_and_read_only(monkeypatch):
    observed_queries = []
    events = []

    class Collection:
        def find(self, query, projection):
            observed_queries.append((query, projection))
            return []

    class Database:
        def __getitem__(self, _name):
            return Collection()

    class Admin:
        def command(self, command):
            events.append(("admin", command))

    class Client:
        admin = Admin()

        def __init__(self, *_args, **_kwargs):
            events.append(("client", "opened"))

        def __getitem__(self, _name):
            return Database()

        def close(self):
            events.append(("client", "closed"))

    monkeypatch.setattr(pymongo, "MongoClient", Client)
    monkeypatch.setenv("MONGODB_URI", "mongodb://read-only-test.invalid")

    runs, kpis, tables = load_mongodb_history(pages=("branches", "credit"))

    assert (runs, kpis, tables) == ([], [], [])
    assert [query for query, _ in observed_queries] == [
        {"page": {"$in": ["branches", "credit"]}},
    ] * 3
    assert events == [
        ("client", "opened"),
        ("admin", "ping"),
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


def test_review_candidates_match_exact_series_scope_only():
    filters = {"Institution Type": "Banks", "Branch Status": "Active"}
    candidate = {
        "page": "branches",
        "metric_label": "Branches",
        "district": "Muhanga",
        "filters": filters,
        "reporting_date": "2026-10-24",
    }

    selected = select_review_candidates(
        [
            candidate,
            {**candidate, "district": "Kirehe"},
            {**candidate, "filters": {**filters, "Gender": "Female"}},
            {**candidate, "metric_label": "Internet Banking Customers"},
        ],
        page="branches",
        metric="Branches",
        district="Muhanga",
        filters=filters,
    )

    assert selected == [candidate]


def test_review_candidate_rows_preserve_evidence_state_and_provenance():
    row = _review_candidate_row(
        {
            "method": "temporal_level_mad",
            "reporting_date": "2026-10-24",
            "observed_value": 6,
            "run_id": "run-2026-10-24",
            "evidence_assessment": {"state": "limited"},
        },
        unit="count",
        source_record_id="table-42",
    )

    assert row["Evidence state"] == "limited"
    assert row["Source record ID"] == "table-42"
    assert row["Observed value"] == 6


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


@pytest.mark.parametrize(
    "view, expected_text",
    [
        ("national", "National overview"),
        ("district", "District explorer"),
        ("population", "Population groups"),
        ("priority", "Priority explorer"),
    ],
)
def test_nbr_supply_pages_render_with_observed_synthetic_points(view, expected_text):
    points = _dashboard_points()
    script = (
        "import json\n"
        "import src.nbr_dashboard as dashboard\n"
        f"points = json.loads({json.dumps(json.dumps(points))})\n"
        "_original_dashboard_loader = dashboard.load_nbr_dashboard_data\n"
        "_original_review_loader = dashboard.load_nbr_review_candidates\n"
        "def dashboard_test_loader(version, pages=None):\n"
        "    selected = [point for point in points if pages is None or point['page'] in pages]\n"
        "    return selected, {'eligible_source_point_count': len(selected)}, "
        "dashboard.build_nbr_indicator_registry(selected), "
        "dashboard._source_data_version(selected)\n"
        "dashboard.load_nbr_dashboard_data = dashboard_test_loader\n"
        "dashboard.load_nbr_review_candidates = lambda version: ([], "
        "{'assessment_id': 'test-assessment', 'assessment_timestamp': "
        "'2026-10-29T00:00:00+00:00', 'model_version': 'test-model', "
        "'source_git_commit': None})\n"
        "try:\n"
        f"    dashboard.render_nbr_page({view!r}, selected_district='Kirehe')\n"
        "finally:\n"
        "    dashboard.load_nbr_dashboard_data = _original_dashboard_loader\n"
        "    dashboard.load_nbr_review_candidates = _original_review_loader\n"
    )
    app = AppTest.from_string(script, default_timeout=30).run()

    assert not app.exception, [error.value for error in app.exception]
    assert any(expected_text.casefold() in markdown.value.casefold() for markdown in app.markdown)
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
        assert not any(selectbox.label == "Basemap" for selectbox in app.selectbox)
        assert map_keys == set()
        assert any(
            "Observed values by district" in markdown.value
            for markdown in app.markdown
        )


def test_combined_context_renders_separately_from_survey_data():
    points = _dashboard_points()
    script = (
        "import json\n"
        "import streamlit as st\n"
        "import src.nbr_dashboard as dashboard\n"
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


def test_combined_national_context_uses_existing_reading_card():
    points = _dashboard_points()
    script = (
        "import json\n"
        "import streamlit as st\n"
        "import src.nbr_dashboard as dashboard\n"
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
    assert all(pages == ("branches",) for pages in app.session_state["requested_pages"])
    assert any(
        "About the NBR lines in these cards" in expander.label
        for expander in app.expander
    )
    assert any(
        "NBR supply context · Bank-account ownership" in expander.label
        for expander in app.expander
    )


def test_national_overview_selects_one_nbr_series_for_shared_map():
    filters = {"Institution Type": "Banks", "Location": "All"}
    entries = [
        {
            "metric_label": "Branches",
            "unit": "branches",
            "filters": filters,
            "points": [{
                "geography": "Kirehe",
                "value": 5,
                "reporting_date": "2026-10-24",
            }],
        },
        {
            "metric_label": "Customers",
            "unit": "customers",
            "filters": {**filters, "Account Status": "Active"},
            "points": [{
                "geography": "Kirehe",
                "value": 9,
                "reporting_date": "2026-10-24",
            }],
        },
    ]
    app = AppTest.from_string(
        "import plotly.graph_objects as go\n"
        "import streamlit as st\n"
        "import src.nbr_dashboard as dashboard\n"
        "import src.pages.national_overview as overview\n"
        "st.session_state['global_dashboard_mode'] = 'Combined'\n"
        "st.session_state['overview_district_indicator'] = 'Bank account'\n"
        "_original_context_loader = dashboard.load_combined_context_data\n"
        "_original_strip = dashboard.combined_strip\n"
        "_original_map_figure = overview._map_figure\n"
        f"entries = {entries!r}\n"
        "dashboard.load_combined_context_data = lambda *args, **kwargs: (entries, 'fixture')\n"
        "dashboard.combined_strip = lambda *args, **kwargs: ('', None)\n"
        "def capture_map(*args, supply_points=(), **kwargs):\n"
        "    st.session_state['map_values'] = [point['value'] for point in supply_points]\n"
        "    return go.Figure()\n"
        "overview._map_figure = capture_map\n"
        "try:\n"
        "    overview.render_national_overview()\n"
        "finally:\n"
        "    dashboard.load_combined_context_data = _original_context_loader\n"
        "    dashboard.combined_strip = _original_strip\n"
        "    overview._map_figure = _original_map_figure\n"
    ).run()

    assert not app.exception, [error.value for error in app.exception]
    selector = app.selectbox(key="overview_nbr_map_series_k1_fixture")
    assert selector.options[0].startswith("Branches · branches")
    assert selector.options[1].startswith("Customers · customers")
    assert app.session_state["map_values"] == [5]

    selector.select(selector.options[1]).run()

    assert not app.exception, [error.value for error in app.exception]
    assert app.session_state["map_values"] == [9]


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
        "import src.nbr_dashboard as dashboard\n"
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
