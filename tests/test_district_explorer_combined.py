import json
from datetime import date

from streamlit.testing.v1 import AppTest

from src.pages.district_explorer import (
    _combined_intelligence_assessment,
    _combined_story_html,
)


def _nbr_points(*, outlier=None):
    filters = {
        "Branch Status": "Active",
        "Institution Type": "Banks",
        "Location": "All",
    }
    combo_key = json.dumps(filters, sort_keys=True)
    dates = [
        "2025-01-01",
        "2025-04-01",
        "2025-07-01",
        "2025-10-01",
        "2026-01-01",
    ]
    points = []
    for reporting_date in dates:
        for district_index in range(30):
            district = f"District {district_index:02}"
            value = 100 + district_index
            if outlier == (district, reporting_date):
                value = 1000
            points.append({
                "source_type": "district_table",
                "page": "branches",
                "metric_label": "Total Branches",
                "reporting_date": reporting_date,
                "collected_at": f"{reporting_date}T12:00:00+00:00",
                "run_id": f"run-{reporting_date}",
                "combo_key": combo_key,
                "filters": filters,
                "geography_level": "district",
                "geography": district,
                "value": value,
                "unit": "count",
                "unit_status": "explicit",
                "source_record_id": f"{district}-{reporting_date}",
                "quality_qualifications": [],
            })
    return points


def test_combined_district_findings_change_when_a_new_nbr_observation_arrives():
    expected_districts = tuple(
        f"District {index:02}" for index in range(30)
    )
    selected = "District 15"
    original = _combined_intelligence_assessment(
        _nbr_points(),
        expected_districts,
        selected,
    )
    _combined_intelligence_assessment.clear()
    updated = _combined_intelligence_assessment(
        _nbr_points(outlier=(selected, "2026-01-01")),
        expected_districts,
        selected,
    )

    assert original["cross_section"]["state"] == "assessable_no_qualifying_signal"
    assert updated["cross_section"]["state"] == "eligible_unusual_observation"
    assert updated["cross_section"]["candidate"]["observed_value"] == 1000
    assert updated["cross_section"]["candidate"]["reporting_date"] == "2026-01-01"
    assert updated["temporal"]["state"] == "unassessable"


def test_combined_intelligence_is_selected_district_specific():
    analysis = _combined_intelligence_assessment(
        _nbr_points(outlier=("District 15", "2026-01-01")),
        tuple(f"District {index:02}" for index in range(30)),
        "District 15",
    )
    _combined_intelligence_assessment.clear()
    comparison = _combined_intelligence_assessment(
        _nbr_points(outlier=("District 15", "2026-01-01")),
        tuple(f"District {index:02}" for index in range(30)),
        "District 14",
    )

    assert analysis["cross_section"]["state"] == "eligible_unusual_observation"
    assert comparison["cross_section"]["state"] == "assessable_no_qualifying_signal"
    assert comparison["observation"]["value"] == 114


def test_combined_intelligence_distinguishes_insufficient_and_unassessable_peers():
    points = _nbr_points()
    latest = [
        point for point in points
        if point["reporting_date"] == "2026-01-01"
    ]
    insufficient = _combined_intelligence_assessment(
        latest[:9],
        tuple(f"District {index:02}" for index in range(30)),
        "District 00",
    )
    zero_dispersion_points = [dict(point, value=100) for point in latest]
    zero_dispersion = _combined_intelligence_assessment(
        zero_dispersion_points,
        tuple(f"District {index:02}" for index in range(30)),
        "District 00",
    )

    assert insufficient["cross_section"]["state"] == "insufficient_evidence"
    assert insufficient["cross_section"]["observed_district_count"] == 9
    assert zero_dispersion["cross_section"]["state"] == (
        "unassessable_zero_peer_dispersion"
    )


def test_missing_selected_district_is_unavailable_not_zero_or_national():
    latest = [
        point for point in _nbr_points()
        if point["reporting_date"] == "2026-01-01"
        and point["geography"] != "District 00"
    ]
    analysis = _combined_intelligence_assessment(
        latest,
        tuple(f"District {index:02}" for index in range(30)),
        "District 00",
    )

    assert analysis["state"] == "observation_unavailable"
    assert "District 00" in analysis["reason"]
    assert "observation" not in analysis
    assert all(point["geography"] != "District 00" for point in analysis["peer_points"])


def test_combined_intelligence_panel_renders_peer_and_temporal_states():
    points = _nbr_points(outlier=("District 15", "2026-01-01"))
    expected = [f"District {index:02}" for index in range(30)]
    script = (
        "import json\n"
        "import src.pages.district_explorer as explorer\n"
        "import src.pages.nbr_dashboard as dashboard\n"
        f"points = json.loads({json.dumps(json.dumps(points))})\n"
        f"expected = json.loads({json.dumps(json.dumps(expected))})\n"
        "selected = 'District 15'\n"
        "analysis = explorer._combined_intelligence_assessment(points, expected, selected)\n"
        "dashboard._render_combined_peer_comparison(analysis, selected)\n"
        "dashboard._render_combined_intelligence(analysis, selected)\n"
    )
    app = AppTest.from_string(script, default_timeout=30).run()

    assert not app.exception, [error.value for error in app.exception]
    rendered = "\n".join(item.value for item in app.markdown)
    assert "Same-scope district snapshot" in rendered
    assert "Peer signal" in rendered
    assert "Historical assessment not assessable" in rendered
    assert "Evidence-led follow-up" in rendered
    assert len(app.get("plotly_chart")) == 1


def test_combined_story_keeps_finscope_and_nbr_evidence_separate():
    story = _combined_story_html(
        {
            "title": "Bank-account ownership",
            "interpretation": "Reported account ownership among surveyed adults.",
        },
        "Kirehe",
        40.0,
        50.0,
        -10.0,
        {
            "metric_label": "Total Branches",
            "points": [{
                "geography": "Kirehe",
                "value": 999,
                "unit": "count",
                "reporting_date": date(2026, 1, 1).isoformat(),
            }],
        },
    )

    assert "Kirehe reports 40.0%" in story
    assert "10.0 percentage points below" in story
    assert "999" not in story
    assert "separately labelled NBR administrative context" in story
