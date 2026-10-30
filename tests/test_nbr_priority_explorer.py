import json

from streamlit.testing.v1 import AppTest

from src.data_sources.mongodb_district_explorer import load_district_reference
from src.pages.nbr_priority_explorer import (
    _district_distribution_figure,
    _historical_coverage_html,
    _priority_matrix_figure,
    _priority_matrix_is_eligible,
    _prepare_priority_matrix,
    _priority_header_html,
    _priority_catalog_families,
    _priority_families,
    _prepare_priority_history,
    _prepare_priority_snapshot,
    _priority_history_figure,
    _render_controls,
)

_HISTORY_FILTERS = {
    "Account/Policy Status": "Active",
    "Age Segment": "All",
    "Gender": "All",
    "Institution Type": "All",
    "Location": "All",
}


def _point(
    *,
    page="inclusion",
    metric="Customers",
    reporting_date="2026-10-27",
    value=10,
    geography="Kirehe",
    geography_level="district",
    filters=None,
    unit="count",
    unit_status="source_column",
    source_type="district_table",
    **overrides,
):
    return {
        "page": page,
        "metric_label": metric,
        "reporting_date": reporting_date,
        "value": value,
        "geography": geography,
        "geography_level": geography_level,
        "filters": filters or {"Institution Type": "Banks", "Location": "All"},
        "unit": unit,
        "unit_status": unit_status,
        "source_type": source_type,
        "source_record_id": f"{page}-{metric}-{reporting_date}-{geography}",
        **overrides,
    }


def _family(points, *, filters=None):
    families = _priority_families(points)
    return next(
        family for family in families
        if family["filters"] == (
            filters or {"Institution Type": "Banks", "Location": "All"}
        )
    )


def test_priority_families_keep_only_documented_district_count_series_and_exact_scopes():
    points = [
        _point(value=0),
        _point(
            value=999,
            filters={"Institution Type": "All", "Location": "All"},
        ),
        _point(value=888, source_type="national_kpi", geography="Rwanda",
               geography_level="national"),
        _point(value=777, unit_status="unresolved"),
        _point(value=666, unit=""),
        _point(value=555, repeated_snapshot_warning=True),
    ]

    families = _priority_families(points)

    assert len(families) == 2
    valid_family = next(
        family for family in families
        if family["filters"]["Institution Type"] == "Banks"
    )
    assert valid_family["dates"] == ["2026-10-27"]
    snapshot = _prepare_priority_snapshot(
        valid_family,
        "2026-10-27",
        expected_districts=("Kirehe", "Muhanga"),
    )
    assert [(row["district"], row["value"]) for row in snapshot["districts"]] == [
        ("Kirehe", 0.0),
    ]
    assert snapshot["missing_count"] == 1


def test_priority_catalog_builds_exact_count_scopes_without_table_values():
    filters = {"Institution Type": "Banks", "Location": "All"}
    runs = [
        {
            "page": "inclusion",
            "snapshot_date": reporting_date,
            "combo_key": f"scope-{reporting_date}",
            "status": "complete",
            "table_status": "extracted",
            "table_columns": ["District", "Customers", "Share"],
            "filters": filters,
        }
        for reporting_date in ("2026-08-20", "2026-10-27")
    ]
    runs.append({
        **runs[1],
        "snapshot_date": "2026-10-24",
        "combo_key": "repeated",
        "repeated_snapshot_warning": True,
    })

    families = _priority_catalog_families(runs, page="inclusion")

    assert len(families) == 1
    family = families[0]
    assert family["metric_label"] == "Customers"
    assert family["unit"] == "count"
    assert family["filters"] == filters
    assert family["dates"] == ["2026-08-20", "2026-10-27"]
    assert family["scope_keys"] == (
        ("inclusion", "2026-08-20", "scope-2026-08-20"),
        ("inclusion", "2026-10-27", "scope-2026-10-27"),
    )
    assert family["records"] == []


def test_priority_snapshot_excludes_conflicts_and_keeps_unknown_and_unmatched_separate():
    points = [
        _point(value=10),
        _point(value=11, source_record_id="conflicting-record"),
        _point(value=20, geography="Muhanga"),
        _point(value=8, geography="Unknown", geography_level="unknown"),
        _point(value=7, geography="New District"),
        _point(value=-1, geography="Nyagatare"),
        _point(value=12, geography="Rwamagana", repeated_snapshot_warning=True),
    ]
    family = _family(points)

    snapshot = _prepare_priority_snapshot(
        family,
        "2026-10-27",
        expected_districts=("Kirehe", "Muhanga", "Nyagatare"),
    )

    assert [(row["district"], row["value"]) for row in snapshot["districts"]] == [
        ("Muhanga", 20.0),
    ]
    assert len(snapshot["unknown"]) == 1
    assert snapshot["unmatched"] == ["New District"]
    assert snapshot["duplicate_count"] == 2
    assert snapshot["invalid_count"] == 1
    assert snapshot["repeated_count"] == 1
    assert snapshot["missing_count"] == 2


def test_priority_history_uses_actual_dates_and_omits_duplicate_date_without_interpolation():
    points = [
        _point(reporting_date="2025-02-20", value=5),
        _point(reporting_date="2025-11-20", value=7),
        _point(reporting_date="2026-08-20", value=8),
        _point(reporting_date="2026-08-20", value=9, source_record_id="duplicate"),
        _point(reporting_date="2026-10-27", value=0, geography="Muhanga"),
    ]
    family = _family(points)

    history = _prepare_priority_history(family, "Kirehe")
    figure = _priority_history_figure(
        history,
        metric="Customers",
        unit="count",
        selected_date="2025-11-20",
    )

    assert [item["reporting_date"] for item in history["observations"]] == [
        "2025-02-20",
        "2025-11-20",
    ]
    assert history["duplicate_dates"] == ["2026-08-20"]
    assert list(figure.data[0].x) == ["2025-02-20", "2025-11-20"]
    assert list(figure.data[0].y) == [5.0, 7.0]
    assert figure.data[0].mode == "lines+markers"
    assert figure.data[0].name == "Observed values"
    assert list(figure.data[1].x) == ["2025-11-20"]
    assert figure.data[1].name == "Selected reporting date"
    assert figure.layout.xaxis.type == "date"
    assert figure.layout.yaxis.rangemode == "tozero"


def test_priority_distribution_preserves_zero_and_selected_district_emphasis():
    points = [
        _point(value=0, geography="Kirehe"),
        _point(value=15, geography="Muhanga"),
    ]
    family = _family(points)
    snapshot = _prepare_priority_snapshot(family, "2026-10-27")
    figure = _district_distribution_figure(
        snapshot,
        metric="Customers",
        unit="count",
        reporting_date="2026-10-27",
        selected_district="Kirehe",
    )

    assert [row["value"] for row in snapshot["districts"]] == [0.0, 15.0]
    assert [
        (trace.name, list(trace.y), list(trace.x))
        for trace in figure.data
    ] == [
        ("Other districts", ["Muhanga"], [15.0]),
        ("Selected district", ["Kirehe"], [0.0]),
    ]
    assert list(figure.data[1].customdata[0]) == [
        "2026-10-27",
        "Customers",
        "count",
    ]
    assert figure.data[0].orientation == "h"
    assert figure.layout.barmode == "overlay"
    assert figure.layout.yaxis.categoryarray == ("Kirehe", "Muhanga")


def test_priority_history_matrix_preserves_actual_dates_zero_missing_and_selection():
    dates = ("2025-02-20", "2025-11-20", "2026-08-20")
    districts = ("Nyagatare", "Gasabo", "Kirehe")
    points = []
    for date_index, reporting_date in enumerate(dates):
        for district_index, district in enumerate(districts):
            if (district, reporting_date) == ("Gasabo", "2025-11-20"):
                continue
            value = 0 if (district, reporting_date) == ("Kirehe", dates[0]) else (
                100 * (date_index + 1) + district_index
            )
            points.append(_point(
                reporting_date=reporting_date,
                value=value,
                geography=district,
                filters=_HISTORY_FILTERS,
            ))
    family = _family(points, filters=_HISTORY_FILTERS)
    matrix = _prepare_priority_matrix(
        family,
        expected_districts=("Nyagatare", "Kirehe", "Gasabo"),
    )

    assert matrix["dates"] == list(dates)
    assert matrix["districts"] == ["Gasabo", "Kirehe", "Nyagatare"]
    assert matrix["values"] == [
        [101.0, None, 301.0],
        [0.0, 202.0, 302.0],
        [100.0, 200.0, 300.0],
    ]
    assert [row["observed_count"] for row in matrix["coverage"]] == [3, 2, 3]
    assert _priority_matrix_is_eligible(
        family,
        matrix,
        expected_districts=("Gasabo", "Kirehe", "Nyagatare"),
    )

    figure = _priority_matrix_figure(
        matrix,
        selected_district="Kirehe",
        unit="count",
    )
    assert figure.data[0].x == (
        "20 February 2025",
        "20 November 2025",
        "20 August 2026",
    )
    assert figure.data[0].y == ("Gasabo", "Kirehe", "Nyagatare")
    assert list(figure.data[0].z[0]) == [101.0, None, 301.0]
    assert list(figure.data[0].z[1]) == [0.0, 202.0, 302.0]
    assert figure.data[0].customdata[1][0] == [
        "20 February 2025",
        "0",
        "count",
    ]
    assert "Selected district" in {trace.name for trace in figure.data}
    missing = next(trace for trace in figure.data if trace.name == "No observation")
    assert list(missing.x) == ["20 November 2025"]
    assert list(missing.y) == ["Gasabo"]
    assert "missing, not zero" in missing.hovertemplate
    selected = next(trace for trace in figure.data if trace.name == "Selected district")
    assert list(selected.y) == ["Kirehe", "Kirehe", "Kirehe"]
    assert figure.layout.xaxis.type == "category"
    assert figure.layout.xaxis.categoryarray == (
        "20 February 2025",
        "20 November 2025",
        "20 August 2026",
    )


def test_priority_history_matrix_requires_canonical_comparable_scope_and_dates():
    points = [
        _point(
            reporting_date=reporting_date,
            geography=district,
            filters=_HISTORY_FILTERS,
        )
        for reporting_date in ("2026-08-20", "2026-10-27")
        for district in ("Kirehe", "Muhanga")
    ]
    family = _family(points, filters=_HISTORY_FILTERS)
    matrix = _prepare_priority_matrix(
        family,
        expected_districts=("Kirehe", "Muhanga"),
    )
    assert _priority_matrix_is_eligible(
        family,
        matrix,
        expected_districts=("Kirehe", "Muhanga"),
    )
    assert not _priority_matrix_is_eligible(
        {**family, "filters": {**_HISTORY_FILTERS, "Institution Type": "Banks"}},
        matrix,
        expected_districts=("Kirehe", "Muhanga"),
    )
    assert not _priority_matrix_is_eligible(
        {**family, "metric_label": "Accounts"},
        matrix,
        expected_districts=("Kirehe", "Muhanga"),
    )
    one_date = _prepare_priority_matrix(
        {**family, "dates": ["2026-10-27"]},
        expected_districts=("Kirehe", "Muhanga"),
    )
    assert not _priority_matrix_is_eligible(
        {**family, "dates": ["2026-10-27"]},
        one_date,
        expected_districts=("Kirehe", "Muhanga"),
    )
    wrong_page_record = dict(family["records"][0], page="savings")
    assert not _priority_matrix_is_eligible(
        {**family, "records": [wrong_page_record, *family["records"][1:]]},
        matrix,
        expected_districts=("Kirehe", "Muhanga"),
    )


def test_historical_coverage_disclosure_formats_dynamic_observation_counts():
    coverage = [
        {
            "reporting_date": "2025-02-20",
            "observed_count": 30,
            "expected_count": 30,
        },
        {
            "reporting_date": "2026-10-27",
            "observed_count": 28,
            "expected_count": 30,
        },
    ]

    html = _historical_coverage_html(coverage)

    assert "Named-district reporting coverage" in html
    assert "20 February 2025" in html
    assert "<strong>30 of 30</strong>" in html
    assert "27 October 2026" in html
    assert "<strong>28 of 30</strong>" in html
    assert _historical_coverage_html([]) == ""


def test_priority_page_renders_eligible_historical_matrix_and_coverage():
    reporting_dates = (
        "2025-02-20",
        "2025-11-20",
        "2026-08-20",
        "2026-10-24",
        "2026-10-27",
    )
    districts = sorted(load_district_reference())
    points = [
        _point(
            reporting_date=reporting_date,
            value=10_000 + (date_index * 1000) + district_index,
            geography=district,
            filters=_HISTORY_FILTERS,
        )
        for date_index, reporting_date in enumerate(reporting_dates)
        for district_index, district in enumerate(districts)
        if not (reporting_date == reporting_dates[2] and district_index == 0)
    ]
    points.extend([
        _point(
            metric="Branches",
            reporting_date=reporting_dates[0],
            geography=districts[0],
            filters=_HISTORY_FILTERS,
        ),
        _point(
            metric="Customers",
            reporting_date=reporting_dates[0],
            geography="Rwanda",
            geography_level="national",
            filters=_HISTORY_FILTERS,
            source_type="national_kpi",
        ),
    ])
    catalog = [
        {
            "page": "inclusion",
            "snapshot_date": reporting_date,
            "combo_key": f"scope-{reporting_date}",
            "status": "complete",
            "table_status": "extracted",
            "table_columns": ["Customers"],
            "filters": _HISTORY_FILTERS,
        }
        for reporting_date in reporting_dates
    ]
    script = (
        "import json\n"
        "import streamlit as st\n"
        "from src.pages.nbr_priority_explorer import render_nbr_priority_explorer\n"
        f"catalog = json.loads({json.dumps(json.dumps(catalog))})\n"
        f"points = json.loads({json.dumps(json.dumps(points))})\n"
        f"districts = json.loads({json.dumps(json.dumps(districts))})\n"
        "def load_page_data(page):\n"
        "    return catalog, 'catalog-version', {}\n"
        "def load_scope_data(page, scope_keys):\n"
        "    return points, 'data-version', {}\n"
        "render_nbr_priority_explorer(\n"
        "    load_page_data,\n"
        "    page_labels={'inclusion': 'Inclusion'},\n"
        "    load_scope_data=load_scope_data,\n"
        ")\n"
    )
    app = AppTest.from_string(script, default_timeout=30).run()

    assert not app.exception, [error.value for error in app.exception]
    matrix_chart = next(
        chart for chart in app.get("plotly_chart")
        if chart.key.startswith("nbr_priority_reporting_matrix_")
    )
    matrix_spec = json.loads(matrix_chart.proto.spec)
    assert matrix_spec["data"][0]["x"] == [
        "20 February 2025",
        "20 November 2025",
        "20 August 2026",
        "24 October 2026",
        "27 October 2026",
    ]
    assert len(matrix_spec["data"][0]["y"]) == 30
    assert len(matrix_spec["data"][0]["z"]) == 30
    assert all(len(row) == 5 for row in matrix_spec["data"][0]["z"])
    coverage_html = next(
        markdown.value for markdown in app.markdown
        if "Named-district reporting coverage" in markdown.value
    )
    assert "20 February 2025" in coverage_html
    assert "<strong>30 of 30</strong>" in coverage_html
    assert "20 August 2026" in coverage_html
    assert "<strong>29 of 30</strong>" in coverage_html


def test_priority_header_summarizes_latest_scope_without_district_scoring():
    points = [
        _point(reporting_date="2026-08-20", value=4),
        _point(reporting_date="2026-10-24", value=0, geography="Kirehe"),
        _point(reporting_date="2026-10-24", value=25, geography="Muhanga"),
        _point(
            reporting_date="2026-10-24",
            value=7,
            geography="Unknown",
            geography_level="unknown",
        ),
    ]
    family = _family(points)
    latest_date = family["dates"][-1]
    snapshot = _prepare_priority_snapshot(
        family,
        latest_date,
        expected_districts=("Kirehe", "Muhanga", "Gasabo"),
    )

    html = _priority_header_html(family, snapshot, latest_date)

    assert html.count('class="kpi"') == 3
    assert "Districts reporting" in html
    assert "2<small>/ 3 districts</small>" in html
    assert "Highest reported count" in html
    assert "25" in html
    assert "Muhanga" in html
    assert "Lowest reported count" in html
    assert "0" in html
    assert "Kirehe" in html
    assert "24 October 2026" in html
    assert "Institution Type: Banks" in html
    assert "Unknown geography kept separate: 7 count" in html
    assert "priority score" not in html.casefold()
    assert "rank" not in html.casefold()


def test_priority_header_marks_missing_snapshot_unavailable_not_zero():
    html = _priority_header_html(None, None, None)

    assert html.count('class="kpi"') == 3
    assert html.count("Unavailable") == 3
    assert "No eligible named-district snapshot" in html


def test_choose_evidence_hides_fixed_filters_and_source_measure_selector():
    points = []
    for metric, reporting_date in (
        ("Accounts", "2026-08-20"),
        ("Customers", "2026-10-27"),
    ):
        for institution in ("All", "Banks"):
            filters = {
                "Account/Policy Status": "Active",
                "Age Segment": "All",
                "Gender": "All",
                "Institution Type": institution,
                "Location": "All",
            }
            points.extend([
                _point(
                    metric=metric,
                    reporting_date=reporting_date,
                    geography=district,
                    filters=filters,
                )
                for district in ("Kirehe", "Muhanga")
            ])
    families = _priority_families(points)
    script = (
        "import json\n"
        "import streamlit as st\n"
        "from src.pages.nbr_priority_explorer import _render_controls\n"
        f"families = json.loads({json.dumps(json.dumps(families))})\n"
        "st.session_state['selected_scope'] = _render_controls(families, 'test-version')\n"
    )
    app = AppTest.from_string(script).run()

    assert not app.exception, [error.value for error in app.exception]
    assert [pill.label for pill in app.get("pills")] == [
        "Institution Type",
        "Age Segment",
        "Gender",
    ]
    assert [selectbox.label for selectbox in app.selectbox] == ["Reporting date"]
    assert app.session_state["selected_scope"]["metric_label"] == "Customers"
    assert app.session_state["selected_scope"]["filters"] == {
        "Account/Policy Status": "Active",
        "Age Segment": "All",
        "Gender": "All",
        "Institution Type": "All",
        "Location": "All",
    }

    institution_pill = next(
        pill for pill in app.get("pills")
        if pill.label == "Institution Type"
    )
    institution_pill.select("Banks").run()

    assert not app.exception, [error.value for error in app.exception]
    assert app.session_state["selected_scope"]["metric_label"] == "Customers"
    assert app.session_state["selected_scope"]["filters"]["Institution Type"] == "Banks"
    assert app.session_state["selected_scope"]["filters"]["Account/Policy Status"] == "Active"
    assert app.session_state["selected_scope"]["filters"]["Location"] == "All"


def test_priority_family_list_is_empty_without_eligible_observations():
    assert _priority_families([]) == []


def test_priority_route_surfaces_source_load_failure():
    script = (
        "import src.pages.nbr_dashboard as dashboard\n"
        "def fail_loading(*args, **kwargs):\n"
        "    raise RuntimeError('synthetic source read failure')\n"
        "dashboard.load_nbr_page_catalog = fail_loading\n"
        "dashboard.render_nbr_page('priority')\n"
    )
    app = AppTest.from_string(script, default_timeout=30).run()

    assert not app.exception, [error.value for error in app.exception]
    assert any(
        "synthetic source read failure" in caption.value
        for caption in app.caption
    )
    assert any("Priority Explorer requires validated NBR observations" in error.value
               for error in app.error)
    assert not app.get("plotly_chart")
