"""Smoke tests: every page renders without exceptions and survives interaction.

Run with:  pytest -q tests/test_pages_smoke.py
"""
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
    script = f"import sys; sys.path.insert(0, r'{ROOT}')\n" + source
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
    at = _app("national_overview", "render_national_overview").run()
    shown = [float(v) for v in re.findall(r'kpi-value">([\d.]+)<small>', _html(at))]
    expected = [national[n] for n in ["Own bank account", "Registered mobile-money user",
                                      "Borrowed in the past 12 months", "Does not save"]]
    assert len(shown) == 4
    for s, e in zip(shown, expected):
        assert abs(s - round(e, 1)) < 0.051, (shown, expected)


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
    at = _app("population_groups", "render_population_groups").run()
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
            ("Does not save (%)", "Does not save", False)]
    parts = []
    for col, nat, lower_is_gap in spec:
        gap = (n[nat] - d[col]) if lower_is_gap else (d[col] - n[nat])
        gap = gap.clip(lower=0)
        parts.append(gap / gap.max() * 100)
    d["score"] = pd.concat(parts, axis=1).mean(axis=1)
    top = d.sort_values("score", ascending=False).iloc[0]
    at = _app("priority_explorer", "render_priority_explorer").run()
    assert at.selectbox(key="priority_explorer_district").value == top["District"]
    shown = float(re.search(r'kpi-value">([\d.]+)<small>/100', _html(at)).group(1))
    assert abs(shown - round(top["score"], 1)) < 0.051
