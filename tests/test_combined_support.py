"""Pure-logic tests for the Combined-mode helpers (no Streamlit, no MongoDB)."""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.pages import combined_support as cs


def _relationship(kind="contextual_indicator", levels=("national", "district"), page="branches"):
    return {
        "page": page,
        "relationship": kind,
        "available_levels": list(levels),
        "limitations": "Administrative count.",
    }


def _mapping(*relationships, reason=None, label="Own bank account"):
    return {
        "original_indicator_label": label,
        "nbr_relationships": list(relationships),
        "nbr_no_relevant_data_reason": reason,
    }


def _point(district, value, day="2026-10-24", **extra):
    return {"geography": district, "value": value, "reporting_date": day, **extra}


# ---------------------------------------------------------------- classification
def test_unconfigured_indicator_has_no_counterpart():
    state = cs.classify_mapping(None, "national")
    assert state.state == cs.STATE_NO_COUNTERPART


def test_no_relationship_uses_documented_reason():
    state = cs.classify_mapping(_mapping(reason="NBR has no education data."), "district")
    assert state.state == cs.STATE_NO_COUNTERPART
    assert "education" in state.body


def test_proxy_only_mapping_is_not_displayed():
    mapping = _mapping(_relationship("proxy_with_unresolved_definition"))
    assert cs.classify_mapping(mapping, "national").state == cs.STATE_NOT_APPROVED


def test_unsuitable_mapping_is_a_counterpart_gap_not_a_series():
    mapping = _mapping(_relationship("unsuitable"))
    assert cs.classify_mapping(mapping, "national").state == cs.STATE_NO_COUNTERPART


def test_level_unsupported_names_available_level():
    mapping = _mapping(_relationship(levels=("national",)))
    state = cs.classify_mapping(mapping, "district")
    assert state.state == cs.STATE_LEVEL_UNSUPPORTED
    assert "national" in state.body


def test_supported_configuration_returns_none():
    assert cs.classify_mapping(_mapping(_relationship()), "district") is None


def test_missing_observation_is_not_zero():
    state = cs.classify_context(
        _mapping(_relationship()), "district", [], geography="Gasabo",
    )
    assert state.state == cs.STATE_NO_OBSERVATION
    assert "Missing is not zero" in state.body
    assert "Gasabo" in state.body


def test_load_error_is_distinct_from_missing():
    state = cs.classify_context(
        _mapping(_relationship()), "national", [], error=RuntimeError("boom"),
    )
    assert state.state == cs.STATE_LOAD_ERROR
    assert "boom" not in state.body  # internal detail is not exposed


def test_available_when_points_exist():
    entries = [{"points": [_point("Gasabo", 3)]}]
    assert cs.classify_context(_mapping(_relationship()), "district", entries).available


@pytest.mark.parametrize("group", ["Education", "Area"])
def test_unsupported_population_dimensions(group):
    assert cs.scope_state(group).state == cs.STATE_SCOPE_UNSUPPORTED


def test_gender_is_not_scope_limited():
    assert cs.scope_state("Gender") is None


def test_age_groups_are_not_crosswalked_but_may_have_separate_nbr_segments():
    assert cs.scope_state("Age group") is None


# ---------------------------------------------------------------- observations
def test_valid_points_drop_invalid_and_never_fill_zero():
    points = [
        _point("A", 5),
        _point("B", None),
        _point("C", float("nan")),
        _point("D", -1),
        _point("E", "x"),
        {"geography": "F", "value": 2, "reporting_date": "not-a-date"},
    ]
    kept = cs.valid_points(points)
    assert [p["geography"] for p in kept] == ["A"]
    assert all(math.isfinite(p["value"]) for p in kept)


def test_valid_points_keep_genuine_zero():
    assert len(cs.valid_points([_point("A", 0)])) == 1


def test_latest_point_uses_latest_valid_date():
    points = [_point("A", 1, "2026-01-01"), _point("A", 9, "2026-06-01"), _point("A", None, "2026-12-01")]
    assert cs.latest_point(points)["value"] == 9


def test_entries_for_geography_keeps_metric_unit_and_filters():
    entry = {
        "metric_label": "Total Agents", "unit": "agents", "filters": {"Gender": "Female"},
        "points": [_point("Gasabo", 4), _point("Kicukiro", 7)],
    }
    local = cs.entries_for_geography([entry], "gasabo")
    assert len(local) == 1
    assert local[0]["metric_label"] == "Total Agents"
    assert local[0]["unit"] == "agents"
    assert local[0]["filters"] == {"Gender": "Female"}
    assert [p["geography"] for p in local[0]["points"]] == ["Gasabo"]
    assert cs.entries_for_geography([entry], "Nyagatare") == []


def test_snapshot_points_use_one_date_only():
    entry = {"points": [_point("A", 1, "2026-01-01"), _point("A", 2, "2026-06-01"), _point("B", 3, "2026-06-01")]}
    points, chosen = cs.snapshot_points(entry)
    assert chosen == "2026-06-01"
    assert {p["geography"] for p in points} == {"A", "B"}


def test_quality_flags_deduplicate():
    points = [
        {"quality_qualifications": [{"reason": "Unit unresolved."}]},
        {"quality_qualifications": [{"reason": "Unit unresolved."}], "repeated_snapshot_warning": True},
    ]
    flags = cs.quality_flags(points)
    assert flags.count("Unit unresolved.") == 1
    assert len(flags) == 2


# ---------------------------------------------------------------- recommendations
def test_finscope_gap_beyond_margin_is_investigate_not_intervene():
    rec = cs.finscope_position_recommendation(
        place="Nyamasheke", indicator="bank-account ownership", polarity="positive",
        diff_pp=-8.0, margin_pp=4.0,
    )
    assert rec.kind == cs.KIND_INVESTIGATE
    lowered = rec.text.lower()
    assert "does not explain" in lowered
    for banned in ("build", "deploy", "open a branch", "target"):
        assert banned not in lowered


def test_gap_within_margin_is_not_supported():
    rec = cs.finscope_position_recommendation(
        place="X", indicator="i", polarity="positive", diff_pp=-2.0, margin_pp=4.0,
    )
    assert rec.kind == cs.KIND_NOT_SUPPORTED


def test_negative_polarity_direction():
    unfavourable = cs.finscope_position_recommendation(
        place="X", indicator="i", polarity="negative", diff_pp=9.0, margin_pp=4.0,
    )
    favourable = cs.finscope_position_recommendation(
        place="X", indicator="i", polarity="negative", diff_pp=-9.0, margin_pp=4.0,
    )
    assert unfavourable.kind == cs.KIND_INVESTIGATE
    assert favourable.kind == cs.KIND_SUPPORTED


def test_neutral_polarity_is_descriptive():
    rec = cs.finscope_position_recommendation(
        place="X", indicator="i", polarity="neutral", diff_pp=9.0, margin_pp=4.0,
    )
    assert rec.kind == cs.KIND_SUPPORTED


def test_district_recommendations_missing_observation_asks_to_verify():
    state = cs.ContextState(cs.STATE_NO_OBSERVATION, "No observation.")
    items = cs.district_recommendations(
        district="Rusizi", indicator="bank accounts", polarity="positive", diff_pp=-6,
        margin_pp=3, state=state, nbr_label="Total Branches", local_points=[],
    )
    kinds = [item.kind for item in items]
    assert cs.KIND_VERIFY in kinds
    assert not any("zero" in i.text and i.kind == cs.KIND_SUPPORTED for i in items)


def test_single_reporting_date_cannot_support_a_trend():
    state = cs.ContextState(cs.STATE_AVAILABLE, "")
    items = cs.district_recommendations(
        district="Rusizi", indicator="x", polarity="positive", diff_pp=0, margin_pp=3,
        state=state, nbr_label="Total Branches", local_points=[_point("Rusizi", 4)],
    )
    monitor = next(i for i in items if i.kind == cs.KIND_MONITOR)
    assert "1 reporting date" in monitor.text
    assert "trend cannot be read" in monitor.text


def test_no_counterpart_blocks_supply_recommendation():
    state = cs.ContextState(cs.STATE_NO_COUNTERPART, "No approved NBR series is relevant.")
    items = cs.district_recommendations(
        district="Rusizi", indicator="x", polarity="positive", diff_pp=-9, margin_pp=3,
        state=state,
    )
    assert any(i.kind == cs.KIND_NOT_SUPPORTED for i in items)


def test_priority_recommendations_keep_nbr_out_of_score_and_flag_sensitivity():
    states = {
        "Bank account": cs.ContextState(cs.STATE_AVAILABLE, ""),
        "Emergency funds": cs.ContextState(cs.STATE_NO_COUNTERPART, "none"),
    }
    items = cs.priority_recommendations(
        district="Karongi", rank=2, total=30, score=41.2, driver="Bank account",
        driver_points=20.5, top10_count=3, combos=11, states=states,
        missing_district=["Bank account"],
    )
    kinds = {i.kind for i in items}
    assert {cs.KIND_SUPPORTED, cs.KIND_INVESTIGATE, cs.KIND_NOT_SUPPORTED, cs.KIND_VERIFY, cs.KIND_MONITOR} <= kinds
    assert any("does not change the score" in i.text for i in items)
    assert any("sensitive to indicator choice" in i.text for i in items)


def test_priority_zero_score_gives_no_priority_signal():
    items = cs.priority_recommendations(
        district="Kigali", rank=30, total=30, score=0.0, driver=None, driver_points=0,
        top10_count=0, combos=11, states={},
    )
    assert not any(i.kind == cs.KIND_INVESTIGATE for i in items)


def test_group_recommendations_education_has_no_nbr_comparison():
    items = cs.group_recommendations(
        group_type="Education", indicator="bank account", high_group="Tertiary",
        low_group="None", gap_pp=40, exceeds_margin=True, small_groups=["None"],
    )
    text = " ".join(i.text for i in items)
    assert "no education breakdown" in text
    assert any(i.kind == cs.KIND_NOT_SUPPORTED for i in items)


def test_group_recommendations_gender_partial_coverage_asks_to_verify():
    states = {
        "Female": cs.ContextState(cs.STATE_AVAILABLE, ""),
        "Male": cs.ContextState(cs.STATE_NO_OBSERVATION, "none"),
    }
    items = cs.group_recommendations(
        group_type="Gender", indicator="bank account", high_group="Male",
        low_group="Female", gap_pp=2, exceeds_margin=False, small_groups=[],
        gender_states=states,
    )
    verify = [i for i in items if i.kind == cs.KIND_VERIFY]
    assert verify and "Female" in verify[0].text and "Male" in verify[0].text


def test_national_recommendations_state_markers_are_counts_not_rates():
    state = cs.ContextState(cs.STATE_AVAILABLE, "")
    items = cs.national_recommendations(
        indicator="bank-account ownership", below_count=14, district_total=30,
        lowest_district="Nyamasheke", state=state, nbr_label="Total Branches",
        reported_districts=27, reporting_date="2026-10-24",
    )
    text = " ".join(i.text for i in items)
    assert "27 of 30" in text and "unknown, not zero" in text
    assert "not coverage rates" in text


# ---------------------------------------------------------------- html
def test_recommendations_html_escapes_and_orders():
    items = [
        cs.Recommendation(cs.KIND_NOT_SUPPORTED, "<b>x</b>"),
        cs.Recommendation(cs.KIND_SUPPORTED, "first"),
    ]
    html_block = cs.recommendations_html(items)
    assert "&lt;b&gt;" in html_block and "<b>x</b>" not in html_block
    assert html_block.index("Evidence supports") < html_block.index("Not yet supportable")


def test_empty_recommendations_render_nothing():
    assert cs.recommendations_html([]) == ""


def test_mapping_summary_reports_config_only():
    lookup = {
        "k1": _mapping(_relationship(), label="Bank account"),
        "e9b": _mapping(reason="none", label="Emergency funds"),
    }
    mapped, unmapped = cs.mapping_summary(["k1", "e9b", "zz"], "national", mapping_lookup=lookup)
    assert mapped == ["Bank account"]
    assert unmapped == ["Emergency funds", "zz"]


def test_load_context_distinguishes_district_absence_from_missing_series():
    lookup = {"k1": _mapping(_relationship())}
    entry = {"metric_label": "Total Branches", "unit": "branches", "points": [_point("Gasabo", 5)]}

    def loader(variable, **kwargs):
        return [entry], "v1"

    entries, version, state = cs.load_context(
        "k1", level="district", geography="Rusizi", loader=loader, mapping_lookup=lookup,
    )
    assert entries == [] and state.state == cs.STATE_NO_OBSERVATION

    entries, _, state = cs.load_context(
        "k1", level="district", geography="Gasabo", loader=loader, mapping_lookup=lookup,
    )
    assert state.available and entries[0]["points"][0]["geography"] == "Gasabo"


def test_load_context_does_not_query_when_unmapped():
    called = []

    def loader(*args, **kwargs):
        called.append(1)
        return [], None

    _, _, state = cs.load_context(
        "e9b", level="national", loader=loader, mapping_lookup={"e9b": _mapping(reason="none")},
    )
    assert state.state == cs.STATE_NO_COUNTERPART and not called


def test_load_context_reports_loader_failure():
    lookup = {"k1": _mapping(_relationship())}

    def loader(*args, **kwargs):
        raise RuntimeError("mongo down")

    _, _, state = cs.load_context("k1", level="national", loader=loader, mapping_lookup=lookup)
    assert state.state == cs.STATE_LOAD_ERROR


def test_mapping_rows_state_why_nothing_is_shown():
    lookup = {
        "k1": _mapping(
            {**_relationship(), "national_kpi_labels": ["Total Branches"],
             "district_table_labels": ["Branches by District"],
             "filter_scope": {"Institution Type": "Banks"}},
            _relationship("unsuitable", page="agents"),
        ),
        "e9b": _mapping(reason="NBR records no emergency-fund data."),
    }
    registry = [
        {"variable": "k1", "label": "Own bank account"},
        {"variable": "e9b", "label": "Emergency funds"},
        {"variable": "zz", "label": "Unmapped"},
    ]
    rows = cs.mapping_rows(lookup, registry)
    assert len(rows) == 4
    assert rows[0]["NBR relationship"].startswith("Contextual")
    assert rows[0]["Where shown"] == "national and district"
    assert "Institution Type: Banks" in rows[0]["Filter scope"]
    assert rows[1]["Where shown"] == "Not shown"
    assert rows[2]["Limitations / reason"] == "NBR records no emergency-fund data."
    assert rows[3]["NBR relationship"] == "None configured"


def test_contextual_variables_exclude_unsuitable_and_proxy():
    lookup = {
        "a": _mapping(_relationship()),
        "b": _mapping(_relationship("unsuitable")),
        "c": _mapping(_relationship("proxy_with_unresolved_definition")),
    }
    assert cs.contextual_variables(lookup) == ["a"]


def test_district_state_separates_missing_district_from_missing_series():
    available = cs.ContextState(cs.STATE_AVAILABLE, "")
    local = [{"points": [_point("Gasabo", 3)]}]
    assert cs.district_state(available, local, "Gasabo").available
    missing = cs.district_state(available, [], "Rusizi", label="Total Branches")
    assert missing.state == cs.STATE_NO_OBSERVATION and "Rusizi" in missing.body
    unmapped = cs.ContextState(cs.STATE_NO_COUNTERPART, "none")
    assert cs.district_state(unmapped, [], "Rusizi") is unmapped


def test_snapshot_table_marks_missing_districts_explicitly():
    table = cs.snapshot_table([_point("Gasabo", 5, unit="branches")], ["Gasabo", "Rusizi"])
    assert list(table["Status"]) == ["Recorded", "No observation (not zero)"]
    assert table.loc[1, "NBR value"] is None or table["NBR value"].isna().iloc[1]
    assert table.loc[0, "Unit"] == "branches"
