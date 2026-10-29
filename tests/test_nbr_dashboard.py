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
    _national_highlight_metadata,
    _national_highlight_figure,
    _national_infrastructure_series,
    _national_infrastructure_figure,
    _national_customer_comparison_series,
    _national_customer_comparison_figure,
    _compact_customer_count,
    _national_customer_unknown_counts,
    _national_supply_header_html,
    _review_candidate_row,
    _savings_activity_series,
    _savings_district_figure,
    _savings_trend_figure,
    _select_savings_coverage,
    _unknown_savings_customer,
    _source_data_version,
    NATIONAL_HEADER_KPIS,
    NATIONAL_INFRASTRUCTURE_SERIES,
    NATIONAL_CUSTOMER_COMPARISONS,
    build_nbr_indicator_registry,
    load_mongodb_history,
    render_nbr_page,
    render_nbr_savings_activity,
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
        "dashboard._load_nbr_source_documents = lambda *args, **kwargs: ([], [], [])\n"
        "dashboard._render_nbr_national_page = lambda *args: None\n"
        "dashboard.render_nbr_page('national')\n"
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
        "import src.pages.nbr_dashboard as dashboard\n"
        "import streamlit as st\n"
        f"points = {json.dumps(points)}\n"
        f"highlights = {json.dumps(highlights)}\n"
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
        "dashboard.render_nbr_page('national')\n"
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
    points = []
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
        "dashboard._render_nbr_customer_counts_by_district(points, {})\n"
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
        lambda *_args, **_kwargs: ([run], [], [unknown_row]),
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
        "dashboard._load_nbr_source_documents = lambda *args, **kwargs: (runs, kpis, tables)\n"
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
