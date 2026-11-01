"""Smoke tests: every page renders without exceptions and survives interaction.

Run with:  pytest -q tests/test_pages_smoke.py
"""
import json
import sys
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]

PAGES = [
    ("national_overview", "render_national_overview"),
    ("district_explorer", "render_district_explorer"),
    ("population_groups", "render_population_groups"),
    ("priority_explorer", "render_priority_explorer"),
    ("policy_alignment", "render_policy_alignment"),
    ("methodology", "render_methodology"),
]


def _app(module, func):
    script = (
        f"import sys; sys.path.insert(0, r'{ROOT}')\n"
        "import streamlit as st\n"
        "st.session_state['global_dashboard_mode'] = 'FinScope'\n"
        f"from src.styles import apply_global_styles\n"
        f"from src.pages.{module} import {func}\n"
        f"apply_global_styles()\n{func}()\n"
    )
    return AppTest.from_string(script, default_timeout=90)


@pytest.mark.parametrize("module,func", PAGES)
def test_page_renders(module, func):
    at = _app(module, func).run()
    assert not at.exception, [e.value for e in at.exception]
    assert not at.error, [e.value for e in at.error]


def test_district_explorer_interactions():
    at = _app("district_explorer", "render_district_explorer").run()
    for label in ["Emergency funds", "Group saving", "SACCO use", "Doesn't save"]:
        at.session_state["dx_indicator"] = label
        at.run()
        assert not at.exception, (label, [e.value for e in at.exception])
    at.selectbox(key="dx_district").select("Kirehe").run()
    assert not at.exception, [e.value for e in at.exception]


def test_population_groups_interactions():
    at = _app("population_groups", "render_population_groups").run()
    for group in ["Gender", "Age group", "Education", "Area"]:
        for ind in ["Bank account", "Doesn't save", "Mobile money"]:
            at.session_state["population_groups_type"] = group
            at.session_state["population_groups_indicator"] = ind
            at.run()
            assert not at.exception, (group, ind, [e.value for e in at.exception])


def test_priority_explorer_interactions():
    at = _app("priority_explorer", "render_priority_explorer").run()
    combos = [["Bank account", "Doesn't save"], ["Bank account", "Mobile money", "Doesn't save", "Emergency funds"],
              ["Mobile money", "Emergency funds"]]
    for comps in combos:
        at.session_state["priority_explorer_components"] = comps
        at.run()
        assert not at.exception, (comps, [e.value for e in at.exception])
    # too few components falls back gracefully
    at.session_state["priority_explorer_components"] = ["Bank account"]
    at.run()
    assert not at.exception
    for deff in ["Moderate clustering (×1.5)", "Strong clustering (×2.0)"]:
        at.session_state["priority_explorer_deff"] = deff
        at.run()
        assert not at.exception
    at.session_state["priority_explorer_show"] = "All districts"
    at.run()
    assert not at.exception


def test_full_app_navigation():
    source = (ROOT / "app.py").read_text()
    source = source.replace("from src.auth import render_access_gate", "render_access_gate = lambda: True")
    script = (
        f"import sys; sys.path.insert(0, r'{ROOT}')\n"
        "import src.pages.nbr_dashboard as dashboard\n"
        "dashboard.load_nbr_dashboard_data = lambda version, pages=None, scope_keys=None: "
        "([], {'eligible_source_point_count': 0}, [], 'synthetic-empty')\n"
        "dashboard.load_combined_national_evidence = lambda: ([], [])\n"
        "dashboard.load_nbr_page_catalog = lambda version, page: ([], 'synthetic-empty', {})\n"
        + source
    )
    at = AppTest.from_string(script, default_timeout=90).run()
    assert not at.exception, [e.value for e in at.exception]
    assert at.session_state["global_dashboard_mode"] == "Combined"
    pages = [
        "National overview",
        "District explorer",
        "Population groups",
        "Priority explorer",
        "Policy alignment",
        "Methodology & sources",
    ]
    assert len(at.radio) == 0
    for index, label in enumerate(pages):
        at.button(key=f"nav_{index}").click().run()
        assert not at.exception, (label, [e.value for e in at.exception])
        assert at.session_state["selected_page"] == label
        assert at.session_state["global_dashboard_mode"] == "Combined"

    at.button(key="dashboard_mode_finscope").click().run()
    at.button(key="nav_1").click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert at.session_state["selected_page"] == "District explorer"
    assert at.session_state["global_dashboard_mode"] == "FinScope"

    at.button(key="dashboard_mode_nbr_supply").click().run()
    at.button(key="nav_4").click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert at.session_state["selected_page"] == "Policy alignment"
    assert at.session_state["global_dashboard_mode"] == "NBR Supply"


# --------------------------------------------------------------------------
# Displayed numbers must match the source data
# --------------------------------------------------------------------------
import re  # noqa: E402

import pandas as pd  # noqa: E402

DATA = ROOT / "data" / "processed"


def _html(at):
    return " ".join(e.value for e in at.markdown)


def test_national_kpis_match_source():
    national = pd.read_csv(DATA / "national_financial_inclusion.csv").set_index("Indicator")["Estimate (%)"]
    at = _app("national_overview", "render_national_overview")
    at.session_state["global_dashboard_mode"] = "FinScope"
    at.run()
    shown = [float(v) for v in re.findall(r'kpi-value">([\d.]+)<small>', _html(at))]
    expected = [national[n] for n in ["Own bank account", "Registered mobile-money user",
                                      "Borrowed in the past 12 months", "Does not save"]]
    assert len(shown) == 4
    for s, e in zip(shown, expected):
        assert abs(s - round(e, 1)) < 0.051, (shown, expected)


def test_combined_national_overview_uses_two_source_specific_headlines():
    script = (
        f"import sys; sys.path.insert(0, r'{ROOT}')\n"
        "import json\n"
        "import streamlit as st\n"
        "import src.pages.nbr_dashboard as dashboard\n"
        "st.session_state['global_dashboard_mode'] = 'Combined'\n"
        f"points = json.loads({json.dumps(json.dumps(_combined_evidence_points()))})\n"
        "st.session_state.setdefault('requested_pages', [])\n"
        "_original_loader = dashboard.load_nbr_dashboard_data\n"
        "def test_loader(version, pages=None):\n"
        "    st.session_state['requested_pages'].append(pages)\n"
        "    selected = [point for point in points if pages is None or point['page'] in pages]\n"
        "    return selected, {'eligible_source_point_count': len(selected)}, "
        "dashboard.build_nbr_indicator_registry(selected), dashboard._source_data_version(selected)\n"
        "dashboard.load_nbr_dashboard_data = test_loader\n"
        "from src.pages.national_overview import render_national_overview\n"
        "try:\n"
        "    render_national_overview()\n"
        "finally:\n"
        "    dashboard.load_nbr_dashboard_data = _original_loader\n"
    )
    at = AppTest.from_string(script, default_timeout=45).run()

    assert not at.exception, [error.value for error in at.exception]
    rendered = (
        _html(at)
        + " ".join(item.value for item in at.caption)
        + " ".join(item.value for item in at.info)
    )
    assert "Financial inclusion across Rwanda" in rendered
    assert rendered.split('<div class="sec">', 1)[0].count('class="kpi"') == 4
    assert "Owns a bank account" in rendered
    assert "20.2" in rendered
    assert "FinScope Rwanda 2024" in rendered
    assert "Total Branches" in rendered
    assert "Total Agents" in rendered
    assert "152" in rendered
    assert "999" not in rendered
    assert "2026-10-24" in rendered
    assert "Branch Status: Active · Institution Type: Banks · Location: All" in rendered
    assert "Institution Type: E-money Issuers" in rendered
    assert rendered.count('class="kpi"') == 4
    assert "What the financial system is recording" in rendered
    assert "No national findings currently meet" in rendered
    assert "NBR values are administrative counts in their own units" in rendered
    assert "NBR confirms FinScope" not in rendered
    assert "caused" not in rendered.lower()
    assert "financial inclusion has improved" not in rendered.lower()
    assert "Explore further" not in rendered
    assert not {
        "combined_nav_district",
        "combined_nav_population",
        "combined_nav_priority",
    }.intersection(button.key for button in at.button)
    assert not {
        "ov_combined_landscape",
        "ov_combined_barrier_families",
        "ov_combined_barrier_reasons",
    }.intersection(chart.key for chart in at.get("plotly_chart"))
    contextual_charts = [
        chart
        for chart in at.get("plotly_chart")
        if chart.key.startswith("ov_combined_finding_")
    ]
    assert not contextual_charts
    requested_pages = at.session_state["requested_pages"]
    requested_page_union = set().union(
        *(set(pages or ()) for pages in requested_pages)
    )
    assert {"agents", "branches"} <= requested_page_union
def _combined_nbr_points():
    filters = {
        "Institution Type": "Banks",
        "Branch Status": "Active",
        "Location": "All",
    }
    points = [
        {
            "page": "branches",
            "metric_label": "Total Branches",
            "reporting_date": date,
            "value": value,
            "raw_value": str(value),
            "geography": "Rwanda",
            "geography_level": "national",
            "filters": filters,
            "combo_key": json.dumps(filters, sort_keys=True),
            "unit": "count",
            "unit_status": "configured_source_label",
            "source_type": "national_kpi",
            "source_name": "NBR Financial Inclusion Dashboard",
            "source_url": "fixture://nbr/branches",
            "source_record_id": f"branches-{date}",
            "run_id": f"run-{date}",
            "collected_at": f"{date}T12:00:00+00:00",
        }
        for date, value in (("2026-08-20", 104), ("2026-10-24", 152))
    ]
    other_filter_point = {
        **points[-1],
        "value": 999,
        "filters": {**filters, "Gender": "Female"},
        "source_record_id": "off-scope-branch-observation",
    }
    return [*points, other_filter_point]


def _combined_evidence_points():
    points = _combined_nbr_points()
    series = (
        (
            "agents",
            "Total Agents",
            {
                "Gender": "All",
                "Institution Type": "E-money Issuers",
                "Agent Status": "Active",
                "Location": "All",
            },
            (
                ("2025-11-20", 155076),
                ("2026-08-20", 153971),
                ("2026-10-24", 155211),
                ("2026-10-27", 155211),
            ),
        ),
        (
            "branches",
            "Total Branches",
            {
                "Institution Type": "Sacco",
                "Branch Status": "Active",
                "Location": "All",
            },
            (
                ("2025-02-20", 624),
                ("2025-11-20", 760),
                ("2026-08-20", 632),
                ("2026-10-24", 635),
            ),
        ),
    )
    for page, metric, filters, dated_values in series:
        for reporting_date, value in dated_values:
            points.append({
                "page": page,
                "metric_label": metric,
                "reporting_date": reporting_date,
                "value": value,
                "raw_value": str(value),
                "geography": "Rwanda",
                "geography_level": "national",
                "filters": filters,
                "combo_key": json.dumps(filters, sort_keys=True),
                "unit": "count",
                "unit_status": "configured_source_label",
                "source_type": "national_kpi",
                "source_name": "NBR Financial Inclusion Dashboard",
                "source_url": f"fixture://nbr/{page}",
                "source_record_id": (
                    f"{page}-{reporting_date}-"
                    f"{json.dumps(filters, sort_keys=True)}"
                ),
                "run_id": f"run-{reporting_date}",
                "collected_at": f"{reporting_date}T12:00:00+00:00",
            })
    return points


def test_combined_evidence_series_requires_exact_national_metric_scope():
    from importlib import import_module

    _combined_nbr_observations = import_module(
        "src.pages.combine-view.national_overview"
    )._combined_nbr_observations

    filters = {
        "Gender": "All",
        "Institution Type": "E-money Issuers",
        "Agent Status": "Active",
        "Location": "All",
    }
    points = _combined_evidence_points()
    valid_agent = next(
        point
        for point in points
        if point["page"] == "agents"
        and point["reporting_date"] == "2026-10-27"
    )
    points.extend([
        {
            **valid_agent,
            "value": 999999,
            "filters": {**filters, "Gender": "Female"},
            "source_record_id": "wrong-filter",
        },
        {
            **valid_agent,
            "value": 888888,
            "geography": "Kirehe",
            "geography_level": "district",
            "source_type": "district_table",
            "source_record_id": "wrong-geography",
        },
        {
            **valid_agent,
            "value": 777777,
            "repeated_snapshot_warning": True,
            "source_record_id": "repeated-snapshot",
        },
    ])

    entry = {
        "page": "agents",
        "metric_label": "Total Agents",
        "unit": "count",
        "filters": filters,
        "points": points,
    }

    assert entry["points"]
    assert {
        (item["reporting_date"], item["value"])
        for item in _combined_nbr_observations(entry)
    } == {
        ("2025-11-20", 155076),
        ("2026-08-20", 153971),
        ("2026-10-24", 155211),
        ("2026-10-27", 155211),
    }


def test_combined_national_overview_keeps_unavailable_nbr_value_explicit():
    script = (
        f"import sys; sys.path.insert(0, r'{ROOT}')\n"
        "import streamlit as st\n"
        "import src.pages.nbr_dashboard as dashboard\n"
        "st.session_state['global_dashboard_mode'] = 'Combined'\n"
        "_original_loader = dashboard.load_nbr_dashboard_data\n"
        "requested_pages = []\n"
        "def test_loader(version, pages=None):\n"
        "    requested_pages.append(pages)\n"
        "    return [], {'eligible_source_point_count': 0}, [], 'empty-fixture'\n"
        "dashboard.load_nbr_dashboard_data = test_loader\n"
        "from src.pages.national_overview import render_national_overview\n"
        "try:\n"
        "    render_national_overview()\n"
        "finally:\n"
        "    dashboard.load_nbr_dashboard_data = _original_loader\n"
        "st.session_state['requested_pages'] = requested_pages\n"
    )
    at = AppTest.from_string(script, default_timeout=45).run()

    assert not at.exception, [error.value for error in at.exception]
    rendered = (
        _html(at)
        + " ".join(item.value for item in at.caption)
        + " ".join(item.value for item in at.info)
    )
    assert rendered.split('<div class="sec">', 1)[0].count('class="kpi"') == 4
    assert "supported, no matching observation" in rendered.casefold()
    assert "0 branches" not in rendered
    assert "No national findings currently meet" in rendered
    assert at.session_state["requested_pages"]
    requested_pages = at.session_state["requested_pages"]
    assert requested_pages
    requested_page_union = set().union(
        *(set(pages or ()) for pages in requested_pages)
    )
    assert {"agents", "branches"} <= requested_page_union


def test_combined_chart_labels_missing_nbr_units_instead_of_implying_a_count():
    from importlib import import_module

    _combined_nbr_figure = import_module(
        "src.pages.combine-view.national_overview"
    )._combined_nbr_figure

    chart = _combined_nbr_figure(
        [{"reporting_date": "2026-10-24", "value": 42}],
        metric_label="Administrative measure",
        unit_label="",
    )

    assert chart.layout.yaxis.title.text == (
        "Recorded value · Unit not specified by source"
    )
    assert "unit not specified" in chart.layout.annotations[0].text
    assert "unit not specified" in chart.data[0].hovertemplate

    counted_chart = _combined_nbr_figure(
        [{"reporting_date": "2026-10-24", "value": 42}],
        metric_label="Administrative measure",
        unit_label="count",
    )
    assert counted_chart.layout.yaxis.title.text == "Recorded value · count"
    assert "42 count" in counted_chart.layout.annotations[0].text


def test_district_hero_matches_source():
    district = pd.read_csv(DATA / "district_financial_inclusion.csv").set_index("District")
    at = _app("district_explorer", "render_district_explorer").run()
    name = at.selectbox(key="dx_district").value
    html = _html(at)
    shown = float(re.search(r'kpi-value">([\d.]+)<small>%', html).group(1))
    assert abs(shown - round(district.loc[name, "Owns a bank account (%)"], 1)) < 0.051
    at.session_state["dx_indicator"] = "Doesn't save"
    at.run()
    shown = float(re.search(r'kpi-value">([\d.]+)<small>%', _html(at)).group(1))
    assert abs(shown - round(district.loc[name, "Does not save (%)"], 1)) < 0.051


def test_population_hero_matches_source():
    groups = pd.read_csv(DATA / "population_group_indicators.csv")
    population_data = DATA / "population_group_indicators.csv"
    script = (
        f"import sys; sys.path.insert(0, r'{ROOT}')\n"
        "from types import SimpleNamespace\n"
        "import pandas as pd\n"
        "import streamlit as st\n"
        "st.session_state['global_dashboard_mode'] = 'FinScope'\n"
        "import src.pages.population_groups as page\n"
        "_original_loader = page.load_population_group_results\n"
        f"page.load_population_group_results = lambda: SimpleNamespace(observations=pd.read_csv(r'{population_data}'))\n"
        "try:\n"
        "    page.render_population_groups()\n"
        "finally:\n"
        "    page.load_population_group_results = _original_loader\n"
    )
    at = AppTest.from_string(script, default_timeout=90).run()
    at.session_state["population_groups_type"] = "Gender"
    at.session_state["population_groups_indicator"] = "Bank account"
    at.run()
    assert at.session_state["population_groups_indicator"] == "Bank account"
    assert at.session_state["population_groups_type"] == "Gender"
    gender = groups[groups["Group type"] == "Gender"]["Owns a bank account (%)"]
    values = [float(v) for v in re.findall(r'kpi-value">([\d.]+)<small>', _html(at))]
    assert abs(values[0] - round(gender.max(), 1)) < 0.051   # highest group
    assert abs(values[1] - round(gender.min(), 1)) < 0.051   # lowest group
    assert abs(values[2] - round(gender.max() - gender.min(), 1)) < 0.051   # gap


def test_priority_top_district_matches_independent_calculation():
    d = pd.read_csv(DATA / "district_financial_inclusion.csv")
    n = pd.read_csv(DATA / "national_financial_inclusion.csv").set_index("Indicator")["Estimate (%)"]
    spec = [("Owns a bank account (%)", "Own bank account", True),
            ("Registered mobile-money user (%)", "Registered mobile-money user", True),
            ("Does not save (%)", "Does not save", False),
            ("Has emergency funds (%)", "Has emergency funds", True)]
    parts = []
    for col, nat, lower_is_gap in spec:
        gap = (n[nat] - d[col]) if lower_is_gap else (d[col] - n[nat])
        gap = gap.clip(lower=0)
        parts.append(gap / gap.max() * 100)
    d["score"] = pd.concat(parts, axis=1).mean(axis=1)
    top = d.sort_values("score", ascending=False).iloc[0]
    at = _app("priority_explorer", "render_priority_explorer").run()
    assert at.selectbox(key="priority_explorer_district").value == top["District"]
    shown = float(re.search(r'kpi-value">([\d.]+)<small>relative points', _html(at)).group(1))
    assert abs(shown - round(top["score"], 1)) < 0.051


def test_priority_baseline_stays_fixed_in_what_if_scenario():
    at = _app("priority_explorer", "render_priority_explorer").run()
    before = float(re.search(
        r'kpi-value">([\d.]+)<small>relative points', _html(at)).group(1))

    at.session_state["priority_explorer_components"] = ["Bank account", "Mobile money"]
    at.run()

    after = float(re.search(
        r'kpi-value">([\d.]+)<small>relative points', _html(at)).group(1))
    assert after == before
    assert "What-if scenario" in _html(at)
