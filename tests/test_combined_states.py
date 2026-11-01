"""Evidence-state tests: pure logic plus the REAL approved mappings and nbr_pages.json.

Nothing here touches MongoDB. It verifies configuration (what is approved, suppressed,
or unsupported), not live NBR coverage."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.indicators import REGISTRY
from src.models.nbr_intelligence.indicator_mapping import (
    MAPPING_BY_VARIABLE,
)
from src.pages import combined_support as cs

PAGE_FILTERS = cs.load_nbr_page_filters()


def _rel(
    kind="contextual_indicator",
    page="branches",
    levels=("national", "district"),
    **extra,
):
    return {
        "page": page,
        "relationship": kind,
        "available_levels": list(levels),
        "limitations": "Administrative count.",
        **extra,
    }


def _mapping(*rels, reason=None):
    return {
        "original_indicator_label": "X",
        "nbr_relationships": list(rels),
        "nbr_no_relevant_data_reason": reason,
    }


# --------------------------------------------------------------- real configuration
EXPECTED = {  # variable -> (national, district) as configured today
    "k1": ("approved", "approved"),
    "f5": ("approved", "approved"),
    "h2_1": (cs.STATE_NOT_APPROVED, cs.STATE_NOT_APPROVED),
    "g3a_17": (cs.STATE_NOT_APPROVED, cs.STATE_NOT_APPROVED),
    "e9b": (cs.STATE_NO_COUNTERPART, cs.STATE_NO_COUNTERPART),
    "g3a_11": ("approved", "approved"),
    "qf4_06": ("approved", "approved"),
    "qf4_10": (cs.STATE_NO_COUNTERPART, cs.STATE_NO_COUNTERPART),
    "qf4_05": ("approved", "approved"),
    "qf5_05_6": ("approved", "approved"),
    "h3_09": ("approved", "approved"),
    "i5a_1": ("approved", "approved"),
    "qf1_06": ("approved", "approved"),
    "qf1_10": (cs.STATE_NO_COUNTERPART, cs.STATE_NO_COUNTERPART),
}


def test_every_registered_indicator_is_accounted_for():
    assert (
        {item["variable"] for item in REGISTRY}
        == set(EXPECTED)
        == set(MAPPING_BY_VARIABLE)
    )


@pytest.mark.parametrize("variable", list(EXPECTED))
def test_real_configuration_classification(variable):
    for level, expected in zip(("national", "district"), EXPECTED[variable]):
        state = cs.classify_mapping(MAPPING_BY_VARIABLE[variable], level)
        assert (state.state if state else "approved") == expected, (variable, level)


def test_g3a_11_branch_context_is_available_not_suppressed():
    mapping = MAPPING_BY_VARIABLE["g3a_11"]
    state = cs.classify_context(mapping, "district", [], geography="Gasabo")
    assert state.state == cs.STATE_NO_OBSERVATION
    assert "Missing is not zero" in state.body
    branch = next(r for r in mapping["nbr_relationships"] if r["page"] == "branches")
    assert branch["relationship"] == "contextual_indicator"
    assert branch["suppressed"] is False
    # qf4_06 uses the same SACCO branch page and stays approved
    assert not any(
        r["suppressed"] for r in MAPPING_BY_VARIABLE["qf4_06"]["nbr_relationships"]
    )


def test_gender_context_uses_only_pages_with_dynamic_gender_filters():
    for variable in ("k1", "f5", "g3a_11", "qf4_05", "qf1_06"):
        state = cs.classify_subgroup_scope(
            MAPPING_BY_VARIABLE[variable], "national", "Gender", PAGE_FILTERS
        )
        assert state is not None and state.state == cs.STATE_SCOPE_UNSUPPORTED, variable
    for variable in ("h3_09", "i5a_1"):
        assert cs.classify_subgroup_scope(
            MAPPING_BY_VARIABLE[variable], "national", "Gender", PAGE_FILTERS
        ) is None


def test_youth_segments_are_separate_and_conditional_scope_is_restricted():
    assert cs.scope_state("Age group") is None
    for variable in ("h3_09", "i5a_1"):
        assert cs.classify_subgroup_scope(
            MAPPING_BY_VARIABLE[variable], "national", "Age group", PAGE_FILTERS
        ) is None
    state = cs.classify_subgroup_scope(
        MAPPING_BY_VARIABLE["qf5_05_6"], "national", "Age group", PAGE_FILTERS
    )
    assert state.state == cs.STATE_SCOPE_UNSUPPORTED
    assert "all-demographic filters" in state.body


def test_combined_context_requires_exact_filters_and_supports_distinct_youth_slices():
    from src.models.nbr_intelligence.indicator_mapping import DISPLAYABLE_RELATIONSHIPS
    from src.pages.nbr_dashboard import _mapped_series

    insurance = MAPPING_BY_VARIABLE["i5a_1"]["nbr_relationships"][0]
    filters = dict(insurance["filter_scope"])
    filters["Gender"] = "Female"
    female = {
        "page": "insurance",
        "metric_label": "Total Policy Holders",
        "geography_level": "national",
        "geography": "Rwanda",
        "filters": filters,
        "value": 20,
        "reporting_date": "2026-10-24",
        "unit": "count",
        "source_record_id": "insurance-female",
    }
    entries = _mapped_series(
        [female],
        "i5a_1",
        geography_level="national",
        geography=None,
        subgroup_type="Gender",
        subgroup="Female",
        relationships=DISPLAYABLE_RELATIONSHIPS,
    )
    assert len(entries) == 1
    assert entries[0]["filters"]["Gender"] == "Female"
    extra_filter = {**female, "filters": {**filters, "Unexpected": "Other"}}
    assert _mapped_series(
        [extra_filter], "i5a_1", geography_level="national", geography=None,
        subgroup_type="Gender", subgroup="Female",
        relationships=DISPLAYABLE_RELATIONSHIPS,
    ) == []

    youth_filters = dict(insurance["filter_scope"])
    youth_filters["Age Segment"] = "Youth"
    youth = {
        **female,
        "filters": youth_filters,
        "source_record_id": "insurance-youth",
    }
    assert len(_mapped_series(
        [youth], "i5a_1", geography_level="national", geography=None,
        subgroup_type="Age group", subgroup="Youth",
        relationships=DISPLAYABLE_RELATIONSHIPS,
    )) == 1
    assert _mapped_series(
        [youth], "i5a_1", geography_level="national", geography=None,
        subgroup_type="Age group", subgroup="16–24",
        relationships=DISPLAYABLE_RELATIONSHIPS,
    ) == []

    conditional = MAPPING_BY_VARIABLE["qf5_05_6"]["nbr_relationships"][0]
    all_demographics = {
        "page": "mobile_banking",
        "metric_label": "Use Mobile Banking",
        "geography_level": "national",
        "geography": "Rwanda",
        "filters": dict(conditional["filter_scope"]),
        "value": 20,
        "reporting_date": "2026-10-24",
        "unit": "count",
        "source_record_id": "mobile-banking-all",
    }
    assert len(_mapped_series(
        [all_demographics], "qf5_05_6", geography_level="national", geography=None,
        relationships=DISPLAYABLE_RELATIONSHIPS,
    )) == 1
    assert _mapped_series(
        [all_demographics], "qf5_05_6", geography_level="national", geography=None,
        subgroup_type="Gender", subgroup="Female",
        relationships=DISPLAYABLE_RELATIONSHIPS,
    ) == []


def test_page_filter_configuration_matches_the_scraper_file():
    assert PAGE_FILTERS["branches"].get("Gender") is None
    assert PAGE_FILTERS["savings"]["Gender"] == "dynamic"
    assert (
        PAGE_FILTERS["agents"]["Gender"] == "ignored"
    )  # recorded as All, not a breakdown
    assert PAGE_FILTERS["mobile_banking"]["Gender"] == "dynamic"


# --------------------------------------------------------------- scope logic
def test_gender_scope_supported_when_a_page_exposes_gender():
    mapping = _mapping(_rel(page="savings"))
    assert (
        cs.classify_subgroup_scope(mapping, "national", "Gender", PAGE_FILTERS) is None
    )


def test_gender_scope_unknown_page_claims_nothing():
    mapping = _mapping(_rel(page="not_in_config"))
    assert (
        cs.classify_subgroup_scope(mapping, "national", "Gender", PAGE_FILTERS) is None
    )
    assert (
        cs.classify_subgroup_scope(_mapping(_rel()), "national", "Gender", None) is None
    )


def test_gender_scope_ignored_filter_is_not_a_breakdown():
    mapping = _mapping(_rel(page="agents"))
    assert (
        cs.classify_subgroup_scope(mapping, "national", "Gender", PAGE_FILTERS).state
        == cs.STATE_SCOPE_UNSUPPORTED
    )


def test_load_context_gender_scope_blocks_the_query():
    called = []

    def loader(*a, **k):
        called.append(1)
        return [], None

    lookup = {"k1": _mapping(_rel())}
    entries, _, state = cs.load_context(
        "k1",
        level="national",
        subgroup_type="Gender",
        subgroup="Female",
        loader=loader,
        mapping_lookup=lookup,
        page_filters=PAGE_FILTERS,
    )
    assert state.state == cs.STATE_SCOPE_UNSUPPORTED and entries == [] and not called


def test_gender_on_a_capable_page_distinguishes_missing_from_unsupported():
    lookup = {"k1": _mapping(_rel(page="savings", levels=("national",)))}
    _, _, state = cs.load_context(
        "k1",
        level="national",
        subgroup_type="Gender",
        subgroup="Male",
        loader=lambda *a, **k: ([], None),
        mapping_lookup=lookup,
        page_filters=PAGE_FILTERS,
    )
    assert state.state == cs.STATE_NO_OBSERVATION and "Gender: Male" in state.body


# --------------------------------------------------------------- state distinctness
def test_failed_read_is_never_reported_as_absence():
    lookup = {"k1": _mapping(_rel())}

    def boom(*a, **k):
        raise RuntimeError("down")

    _, _, state = cs.load_context(
        "k1", level="national", loader=boom, mapping_lookup=lookup
    )
    assert state.state == cs.STATE_LOAD_ERROR
    assert "missing is not zero" not in state.body.lower()
    assert "does not exist" not in state.body.lower() or "not" in state.body.lower()


def test_all_eight_classes_map_to_distinct_known_states():
    states = [k for _, keys, _ in cs.EVIDENCE_CLASSES for k in keys]
    assert set(states) == set(cs.STATE_TITLES)  # every state is explained
    assert len(cs.EVIDENCE_CLASSES) == 8


def test_eligible_state_marks_filtered_series_as_suppressed_not_no_counterpart():
    available = cs.ContextState(cs.STATE_AVAILABLE, "")
    assert cs.eligible_state(available, []).state == cs.STATE_SUPPRESSED
    assert cs.eligible_state(available, [{"points": [1]}]) is available
    other = cs.ContextState(cs.STATE_NO_OBSERVATION, "x")
    assert cs.eligible_state(other, []) is other


def test_state_summary_keeps_distinct_reasons_apart():
    items = [
        ("A", cs.ContextState(cs.STATE_SUPPRESSED, "not a proxy")),
        ("B", cs.ContextState(cs.STATE_LOAD_ERROR, "could not be read")),
        ("C", cs.ContextState(cs.STATE_NO_COUNTERPART, "none")),
        ("D", cs.ContextState(cs.STATE_AVAILABLE, "")),
    ]
    html = cs.state_summary_html(items)
    assert (
        "intentionally not shown" in html
        and "unavailable" in html
        and "No NBR counterpart" in html
    )
    assert html.count('class="micro"') == 3  # available adds nothing


def test_priority_recommendations_name_suppressed_and_failed_separately():
    states = {
        "Group saving": cs.ContextState(cs.STATE_SUPPRESSED, "x"),
        "Bank account": cs.ContextState(cs.STATE_LOAD_ERROR, "y"),
    }
    items = cs.priority_recommendations(
        district="D",
        rank=1,
        total=30,
        score=10.0,
        driver="Bank account",
        driver_points=5.0,
        top10_count=11,
        combos=11,
        states=states,
    )
    text = " ".join(i.text for i in items)
    assert "intentionally not shown" in text and "could not be loaded" in text
    assert "says nothing about whether the service or observation exists" in text


# --------------------------------------------------------------- reporting date
def test_reporting_date_choice_drops_stale_and_defaults_to_latest():
    session = {"k": "2025-01-01"}
    assert (
        cs.reporting_date_choice(session, "k", ["2026-01-01", "2026-06-01"])
        == "2026-06-01"
    )
    assert "k" not in session
    session["k"] = "2026-01-01"
    assert (
        cs.reporting_date_choice(session, "k", ["2026-01-01", "2026-06-01"])
        == "2026-01-01"
    )
    assert cs.reporting_date_choice(session, "k", []) is None and "k" not in session


def test_snapshot_uses_only_the_chosen_date():
    entry = {
        "points": [
            {"geography": "A", "value": 1, "reporting_date": "2026-01-01"},
            {"geography": "A", "value": 2, "reporting_date": "2026-06-01"},
            {"geography": "B", "value": 3, "reporting_date": "2026-06-01"},
        ]
    }
    points, chosen = cs.snapshot_points(entry, "2026-01-01")
    assert chosen == "2026-01-01" and [p["geography"] for p in points] == ["A"]


# --------------------------------------------------------------- mapping rows / reconciliation
def test_mapping_rows_label_the_suppressed_relationship():
    rows = cs.mapping_rows(MAPPING_BY_VARIABLE, REGISTRY)
    branch = [
        r for r in rows
        if r["FinScope variable"] == "g3a_11" and r["NBR page"] == "branches"
    ]
    assert len(branch) == 1
    assert branch[0]["NBR relationship"] == "Contextual indicator (shown)"
    assert branch[0]["Where shown"] == "national and district"
    conditional = [
        r for r in rows if r["FinScope variable"] == "qf5_05_6"
        and r["NBR page"] == "mobile_banking"
    ]
    assert len(conditional) == 1
    assert "Conditional" in conditional[0]["NBR relationship"]
    assert "exact active-account" in conditional[0]["Limitations / reason"]
    assert cs.contextual_variables(MAPPING_BY_VARIABLE) == [
        "k1", "f5", "g3a_11", "qf4_06", "qf4_05", "qf5_05_6",
        "h3_09", "i5a_1", "qf1_06",
    ]


def test_missing_indicator_note_names_columns_and_invents_nothing():
    import pandas as pd

    frame = pd.DataFrame({"Owns a bank account (%)": [1.0]})
    note = cs.missing_indicator_note(REGISTRY, frame, "population-group")
    assert "Mobile money" in note and "nothing has been estimated" in note
    full = pd.DataFrame({item["column"]: [1.0] for item in REGISTRY})
    assert cs.missing_indicator_note(REGISTRY, full, "x") == ""


def test_routed_indicator_notes_do_not_claim_confirmed_non_use():
    for variable in ("qf4_06", "qf4_10"):
        text = cs.routed_note(variable)
        assert (
            "not a confirmed non-use rate" in text
            and "counts them as non-users" in text
        )
    assert cs.routed_note("k1") == ""


# --------------------------------------------------------------- validation helpers
def test_indicator_coverage_check_warns_and_names_missing_columns():
    import pandas as pd
    from src import validation

    partial = pd.DataFrame({REGISTRY[0]["column"]: [1.0]})
    full = pd.DataFrame({item["column"]: [1.0] for item in REGISTRY})
    result = validation.indicator_coverage_check(partial, full)
    assert result["status"] == "warn" and "population-group" in result["detail"]
    assert (
        REGISTRY[1]["short"] in result["detail"]
        and "urban/rural" not in result["detail"]
    )
    assert validation.indicator_coverage_check(full, full)["status"] == "pass"


def test_routed_question_check_reports_shares_and_does_not_claim_confirmed_non_use():
    import pandas as pd
    from src import validation

    frame = pd.DataFrame(
        {
            "Variable": ["k1", "qf4_06", "qf4_10"],
            "Valid response (%)": [100.0, 41.2, 38.0],
        }
    )
    result = validation.routed_question_check(frame)
    assert result["status"] == "warn"
    assert (
        "41.2% valid responses" in result["detail"]
        and "38.0% valid responses" in result["detail"]
    )
    assert (
        "not confirmed non-use" in result["detail"]
        and "has not been verified" in result["detail"]
    )
    missing = validation.routed_question_check(frame.iloc[:1])
    assert (
        missing["status"] == "warn"
        and "not in the denominator file" in missing["detail"]
    )


def test_processed_registry_and_denominators_cover_every_active_indicator():
    from src import data

    register = data.read_candidate_register()
    denominators = data.read_denominators()
    active = register.loc[register["Status"].str.startswith("Implemented")]
    active_variables = set(active["Variable"])
    assert active["Variable"].is_unique
    assert active_variables == {item["variable"] for item in REGISTRY}
    assert active_variables <= set(denominators["Variable"])

    sacco = denominators.set_index("Variable").loc["qf4_06"]
    assert int(sacco["Valid responses"]) == 4172
    assert int(sacco["Missing responses"]) == 9822
