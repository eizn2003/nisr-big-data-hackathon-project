from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from src.data_sources.mongodb_data_health import (
    FRESHNESS_TOLERANCE_DAYS,
    INCOMPLETE,
    MIN_BASELINE_REPORTING_DATES,
    NOT_ASSESSABLE,
    SUPPORTED,
    TENTATIVE,
    ExpectedDataRegistry,
    ExpectedPage,
    _historical_period_coverage,
    _metric_schema,
    assess_data_health,
    load_expected_data_registry,
)


AS_OF = datetime(2026, 10, 28, 12, tzinfo=timezone.utc)


def _registry(*, pages=None, districts=("Alpha",)):
    pages = pages or (
        ExpectedPage(
            page_id="branches",
            title="Branches",
            url="https://example.invalid/branches",
            filters=({"label": "Institution Type", "expected_count": 1},),
            expected_combinations=1,
            dimensions={
                "Gender": {"status": "unsupported"},
                "Age": {"status": "unsupported"},
                "Education": {"status": "unsupported"},
            },
            approved_metric_mappings=(),
        ),
    )
    return ExpectedDataRegistry(
        source="NBR Financial Inclusion Dashboard",
        pages=tuple(pages),
        collection_frequency="weekly",
        collection_schedule="Tuesday primary; Tuesday backup",
        freshness_tolerance_days=FRESHNESS_TOLERANCE_DAYS,
        reporting_date_field="snapshot_date",
        collection_timestamp_field="collected_at",
        finscope={"dimensions": {"Education": {"source": "FinScope"}}},
        unsupported_nbr_dimensions={"Education": "NBR does not provide Education."},
        expected_districts=tuple(districts),
    )


def _documents(
    *,
    reporting_date="2026-10-24",
    collected_at="2026-10-27T15:23:00+02:00",
    run_status="complete",
    district="Alpha",
    district_value="0",
    kpi_value="0",
    metric_label="Branches",
):
    filters = {"Institution Type": "Banks", "Branch Status": "Active"}
    common = {
        "page": "branches",
        "snapshot_date": reporting_date,
        "dashboard_date": reporting_date,
        "collected_at": collected_at,
        "run_id": f"cycle-{reporting_date}",
        "combo_key": '{"Institution Type": "Banks"}',
        "filters": filters,
        "date_source": "selected",
    }
    run = {
        **common,
        "status": run_status,
        "table_status": "extracted",
        "table_rows": 1,
        "table_columns": ["District", "Branches"],
        "repeated_snapshot_warning": False,
    }
    kpi = {
        **common,
        "kpis": [{
            "metric_type": "headline_kpi",
            "metric_label": "Total Branches",
            "metric_value": kpi_value,
        }],
    }
    table = {
        **common,
        "row_index": 0,
        "district": district,
        "district_known": district.casefold() != "unknown",
        "columns": ["District", metric_label],
        "values": {"District": district, metric_label: district_value},
        "cells": [district, district_value],
    }
    return [run], [kpi], [table]


def _find(result, check):
    return [finding for finding in result["findings"] if finding["check"] == check]


def test_registry_reuses_nbr_configuration_and_separates_finscope_dimensions():
    root = Path(__file__).resolve().parents[1]
    registry = load_expected_data_registry(root / "config" / "nbr_pages.json")

    assert len(registry.pages) == 13
    branches = next(page for page in registry.pages if page.page_id == "branches")
    assert branches.expected_combinations == 5
    assert branches.dimensions["Education"]["status"] == "unsupported"
    agents = next(page for page in registry.pages if page.page_id == "agents")
    assert agents.dimensions["Gender"]["status"] == "unsupported"
    inclusion = next(page for page in registry.pages if page.page_id == "inclusion")
    assert inclusion.dimensions["Gender"]["status"] == "configured_requires_observation_verification"
    assert "Education" in registry.finscope["dimensions"]
    assert "Education" in registry.unsupported_nbr_dimensions
    assert registry.reporting_date_field == "snapshot_date"
    assert registry.collection_timestamp_field == "collected_at"


def test_metric_schema_aggregates_labels_and_columns_by_observation_key():
    kpis = [
        {
            "page": "branches",
            "snapshot_date": "2026-10-24",
            "combo_key": '{"Institution Type": "Banks"}',
            "kpis": [{"metric_label": "Total Branches"}, {"metric_label": "Other"}],
        },
        {
            "page": "branches",
            "snapshot_date": "2026-10-24",
            "combo_key": '{"Institution Type": "Banks"}',
            "kpis": [{"metric_label": "Total Branches"}],
        },
    ]
    tables = [
        {
            "page": "branches",
            "snapshot_date": "2026-10-24",
            "combo_key": '{"Institution Type": "Banks"}',
            "columns": ["District", "Branches"],
        },
        {
            "page": "branches",
            "snapshot_date": "2026-10-24",
            "combo_key": '{"Institution Type": "Banks"}',
            "columns": ["District", "Branches", "Rank"],
        },
        {
            "page": "pos",
            "snapshot_date": "2026-10-24",
            "combo_key": '{"Institution Type": "Banks"}',
            "columns": ["District", "POS"],
        },
    ]

    schema = _metric_schema(kpis, tables)

    assert schema[("branches", "2026-10-24", '{"Institution Type": "Banks"}')] == (
        ("Other", "Total Branches"),
        ("Branches", "District", "Rank"),
    )
    assert schema[("pos", "2026-10-24", '{"Institution Type": "Banks"}')] == (
        (),
        ("District", "POS"),
    )


def test_successful_and_failed_collection_are_classified_explicitly():
    runs, kpis, tables = _documents()
    result = assess_data_health(runs, kpis, tables, registry=_registry(), as_of=AS_OF)
    assert _find(result, "collection_completeness")[0]["status"] == SUPPORTED
    assert _find(result, "freshness")[0]["status"] == SUPPORTED

    runs[0]["status"] = "failed"
    failed = assess_data_health(runs, kpis, tables, registry=_registry(), as_of=AS_OF)
    assert _find(failed, "collection_completeness")[0]["status"] == INCOMPLETE
    assert "failed_runs" in _find(failed, "collection_completeness")[0]["evidence"]


def test_empty_history_is_not_misreported_as_healthy():
    result = assess_data_health([], [], [], registry=_registry(), as_of=AS_OF)
    assert result["status"] == NOT_ASSESSABLE
    assert _find(result, "freshness")[0]["status"] == NOT_ASSESSABLE
    assert _find(result, "collection_completeness")[0]["status"] == NOT_ASSESSABLE


def test_stale_collection_is_incomplete():
    runs, kpis, tables = _documents(collected_at="2026-10-01T10:00:00+00:00")
    result = assess_data_health(runs, kpis, tables, registry=_registry(), as_of=AS_OF)
    freshness = _find(result, "freshness")[0]
    assert freshness["status"] == INCOMPLETE
    assert freshness["evidence"]["tolerance_days"] == FRESHNESS_TOLERANCE_DAYS


def test_missing_expected_page_and_required_kpi_are_reported():
    runs, kpis, tables = _documents()
    second_page = ExpectedPage(
        page_id="agents",
        title="Agents",
        url="https://example.invalid/agents",
        filters=(),
        expected_combinations=1,
        dimensions={
            "Gender": {"status": "unsupported"},
            "Age": {"status": "unsupported"},
            "Education": {"status": "unsupported"},
        },
        approved_metric_mappings=(),
    )
    result = assess_data_health(
        runs, [], tables,
        registry=_registry(pages=(*_registry().pages, second_page)),
        as_of=AS_OF,
    )
    completeness = _find(result, "collection_completeness")[0]
    assert completeness["status"] == INCOMPLETE
    assert completeness["evidence"]["missing_pages"] == ["agents"]
    assert completeness["evidence"]["missing_kpi_documents"]


def test_completeness_combines_run_ids_within_the_same_reporting_period():
    branch_runs, branch_kpis, branch_tables = _documents()
    agent_runs, agent_kpis, agent_tables = _documents(
        collected_at="2026-10-28T10:00:00+00:00",
    )
    branch_runs[0]["run_id"] = "page-run-branches"
    branch_kpis[0]["run_id"] = "page-run-branches"
    branch_tables[0]["run_id"] = "page-run-branches"
    agent_runs[0]["page"] = "agents"
    agent_kpis[0]["page"] = "agents"
    agent_tables[0]["page"] = "agents"
    agent_runs[0]["run_id"] = "page-run-agents"
    agent_kpis[0]["run_id"] = "page-run-agents"
    agent_tables[0]["run_id"] = "page-run-agents"
    agents_page = ExpectedPage(
        page_id="agents",
        title="Agents",
        url="https://example.invalid/agents",
        filters=(),
        expected_combinations=1,
        dimensions={
            "Gender": {"status": "unsupported"},
            "Age": {"status": "unsupported"},
            "Education": {"status": "unsupported"},
        },
        approved_metric_mappings=(),
    )

    result = assess_data_health(
        branch_runs + agent_runs,
        branch_kpis + agent_kpis,
        branch_tables + agent_tables,
        registry=_registry(pages=(*_registry().pages, agents_page)),
        as_of=AS_OF,
    )
    completeness = _find(result, "collection_completeness")[0]
    assert completeness["status"] == SUPPORTED
    assert completeness["evidence"]["latest_reporting_date"] == "2026-10-24"
    assert completeness["evidence"]["latest_run_ids"] == [
        "page-run-agents",
        "page-run-branches",
    ]
    assert completeness["evidence"]["missing_pages"] == []


def test_historical_period_coverage_reports_missing_expected_combinations():
    page = ExpectedPage(
        page_id="branches",
        title="Branches",
        url="https://example.invalid/branches",
        filters=(),
        expected_combinations=2,
        dimensions={},
        approved_metric_mappings=(),
    )
    runs = [
        {
            "page": "branches",
            "snapshot_date": "2025-11-20",
            "combo_key": '{"Institution Type": "Banks"}',
            "run_id": "older-run",
            "status": "completed_no_data",
        },
        {
            "page": "branches",
            "snapshot_date": "2026-10-27",
            "combo_key": '{"Institution Type": "Banks"}',
            "run_id": "current-run-a",
            "status": "completed_no_data",
        },
        {
            "page": "branches",
            "snapshot_date": "2026-10-27",
            "combo_key": '{"Institution Type": "Sacco"}',
            "run_id": "current-run-b",
            "status": "completed_no_data",
        },
    ]

    periods = _historical_period_coverage(runs, [], [], {"branches": page})

    assert periods[0]["status"] == INCOMPLETE
    assert periods[0]["pages_with_fewer_combinations"] == {
        "branches": {"observed_combinations": 1, "expected_combinations": 2}
    }
    assert periods[1]["status"] == SUPPORTED
    assert periods[1]["run_ids"] == ["current-run-a", "current-run-b"]


def test_historical_period_coverage_checks_kpi_and_table_observations():
    page = ExpectedPage(
        page_id="branches",
        title="Branches",
        url="https://example.invalid/branches",
        filters=(),
        expected_combinations=1,
        dimensions={},
        approved_metric_mappings=(),
    )
    older_runs, _, older_tables = _documents(reporting_date="2025-11-20")
    latest_runs, latest_kpis, latest_tables = _documents(reporting_date="2026-10-27")
    periods = _historical_period_coverage(
        older_runs + latest_runs,
        latest_kpis,
        older_tables + latest_tables,
        {"branches": page},
    )

    assert periods[0]["status"] == INCOMPLETE
    assert periods[0]["missing_kpi_documents"] == [
        ["branches", "2025-11-20", '{"Institution Type": "Banks"}']
    ]
    assert periods[0]["table_row_count_mismatches"] == []
    assert periods[1]["status"] == SUPPORTED


def test_missing_metric_labels_required_by_approved_mapping_are_reported():
    runs, kpis, tables = _documents()
    page = ExpectedPage(
        page_id="branches",
        title="Branches",
        url="https://example.invalid/branches",
        filters=(),
        expected_combinations=1,
        dimensions={
            "Gender": {"status": "unsupported"},
            "Age": {"status": "unsupported"},
            "Education": {"status": "unsupported"},
        },
        approved_metric_mappings=(
            {
                "filters": {
                    "Institution Type": "Banks",
                    "Branch Status": "Active",
                },
                "kpi_labels": ["Total Branches", "Expected but missing"],
                "table_labels": ["Branches", "Expected table field missing"],
            },
        ),
    )
    result = assess_data_health(
        runs,
        kpis,
        tables,
        registry=_registry(pages=(page,)),
        as_of=AS_OF,
    )
    completeness = _find(result, "collection_completeness")[0]
    missing = completeness["evidence"]["missing_required_observations"]
    assert missing == [{
        "page": "branches",
        "snapshot_date": "2026-10-24",
        "combo_key": '{"Institution Type": "Banks"}',
        "missing_kpi_labels": ["Expected but missing"],
        "missing_table_labels": ["Expected table field missing"],
    }]


def test_missing_district_is_not_zero_and_actual_zero_is_preserved():
    runs, kpis, tables = _documents(district_value="0", kpi_value="0")
    registry = _registry(districts=("Alpha", "Beta"))
    result = assess_data_health(runs, kpis, tables, registry=registry, as_of=AS_OF)
    coverage = _find(result, "geographic_coverage")[0]
    assert coverage["status"] == TENTATIVE
    assert coverage["evidence"]["missing_districts"] == ["Beta"]
    assert tables[0]["values"]["Branches"] == "0"
    assert _find(result, "value_quality")[0]["evidence"]["value_issues"] == []


def test_unknown_geographic_category_is_reported_without_assignment():
    runs, kpis, tables = _documents(district="Unknown", district_value="4", kpi_value="4")
    result = assess_data_health(runs, kpis, tables, registry=_registry(), as_of=AS_OF)
    coverage = _find(result, "geographic_coverage")[0]
    assert coverage["status"] == TENTATIVE
    assert coverage["evidence"]["unknown_rows"] == ["Unknown"]


def test_schema_change_is_tentative_and_single_snapshot_is_not_assessable():
    runs, kpis, tables = _documents()
    single = assess_data_health(runs, kpis, tables, registry=_registry(), as_of=AS_OF)
    schema = _find(single, "schema_consistency")[0]
    assert schema["status"] == NOT_ASSESSABLE
    assert schema["evidence"]["supporting_snapshots"] == 1

    next_runs, next_kpis, next_tables = _documents(
        reporting_date="2026-10-27",
        collected_at="2026-10-28T10:00:00+00:00",
        metric_label="Branch count",
    )
    result = assess_data_health(
        runs + next_runs,
        kpis + next_kpis,
        tables + next_tables,
        registry=_registry(),
        as_of=AS_OF,
    )
    assert _find(result, "schema_consistency")[0]["status"] == TENTATIVE


def test_filter_dimension_changes_are_reported():
    first_runs, first_kpis, first_tables = _documents()
    second_runs, second_kpis, second_tables = _documents(
        reporting_date="2026-10-27",
        collected_at="2026-10-28T10:00:00+00:00",
    )
    second_runs[0]["filters"]["New filter"] = "value"
    result = assess_data_health(
        first_runs + second_runs,
        first_kpis + second_kpis,
        first_tables + second_tables,
        registry=_registry(),
        as_of=AS_OF,
    )
    filter_schema = next(
        finding for finding in _find(result, "schema_consistency")
        if finding["evidence"].get("schema_component") == "filters_and_dimensions"
    )
    assert filter_schema["status"] == TENTATIVE
    assert "New filter" in filter_schema["evidence"]["latest_filters"]


def test_historical_filter_changes_are_reported_when_latest_periods_match():
    first_runs, first_kpis, first_tables = _documents(reporting_date="2025-02-20")
    first_runs[0]["filters_requested"] = {
        **first_runs[0]["filters"],
        "Legacy filter": "Old option",
    }
    second_runs, second_kpis, second_tables = _documents(reporting_date="2025-11-20")
    latest_runs, latest_kpis, latest_tables = _documents(reporting_date="2026-10-27")
    second_runs[0]["filters_requested"] = dict(second_runs[0]["filters"])
    latest_runs[0]["filters_requested"] = dict(latest_runs[0]["filters"])

    result = assess_data_health(
        first_runs + second_runs + latest_runs,
        first_kpis + second_kpis + latest_kpis,
        first_tables + second_tables + latest_tables,
        registry=_registry(),
        as_of=AS_OF,
    )
    filter_schema = next(
        finding for finding in _find(result, "schema_consistency")
        if finding["evidence"].get("schema_component") == "filters_and_dimensions"
    )

    assert filter_schema["status"] == TENTATIVE
    assert filter_schema["evidence"]["previous_reporting_date"] == "2025-11-20"
    assert filter_schema["evidence"]["latest_reporting_date"] == "2026-10-27"
    assert filter_schema["evidence"]["historical_changes"] == [{
        "previous_reporting_date": "2025-02-20",
        "latest_reporting_date": "2025-11-20",
        "changed_filters": {
            "Legacy filter": {
                "previous": ["Old option"],
                "latest": [],
            },
        },
    }]


def test_duplicate_and_malformed_records_are_reported():
    runs, kpis, tables = _documents()
    duplicate = deepcopy(tables[0])
    tables.append(duplicate)
    malformed = deepcopy(runs[0])
    malformed["snapshot_date"] = "not-a-date"
    runs.append(malformed)
    result = assess_data_health(runs, kpis, tables, registry=_registry(), as_of=AS_OF)
    integrity = _find(result, "record_integrity")[0]
    assert integrity["status"] == TENTATIVE
    assert integrity["evidence"]["duplicate_table_rows"]
    assert any(
        item["field"] == "snapshot_date"
        for item in integrity["evidence"]["malformed_records"]
    )

    malformed_kpi = deepcopy(kpis[0])
    malformed_kpi["kpi_count"] = 4
    kpis.append(malformed_kpi)
    result = assess_data_health(runs, kpis, tables, registry=_registry(), as_of=AS_OF)
    integrity = _find(result, "record_integrity")[0]
    assert integrity["evidence"]["kpi_count_mismatches"]


def test_missing_collection_timestamp_and_mismatched_provenance_are_reported():
    runs, kpis, tables = _documents()
    tables[0]["collected_at"] = "2026-10-28T10:00:00+00:00"
    tables[0]["run_id"] = "different-run"
    kpis[0]["collected_at"] = None
    result = assess_data_health(runs, kpis, tables, registry=_registry(), as_of=AS_OF)
    integrity = _find(result, "record_integrity")[0]
    assert any(
        item.get("field") == "collected_at" and item.get("issue") == "missing_timestamp"
        for item in integrity["evidence"]["malformed_records"]
    )
    assert any(
        item["issue"] == "collected_at_differs_from_run"
        for item in integrity["evidence"]["provenance_mismatches"]
    )
    assert any(
        item["issue"] == "run_id_differs_from_run"
        for item in integrity["evidence"]["provenance_mismatches"]
    )


def test_reconciliation_is_checked_only_for_known_compatible_metrics():
    runs, kpis, tables = _documents(district_value="0", kpi_value="0")
    result = assess_data_health(runs, kpis, tables, registry=_registry(), as_of=AS_OF)
    assert _find(result, "reconciliation")[0]["status"] == SUPPORTED

    kpis[0]["kpis"][0]["metric_value"] = "2"
    result = assess_data_health(runs, kpis, tables, registry=_registry(), as_of=AS_OF)
    reconciliation = _find(result, "reconciliation")[0]
    assert reconciliation["status"] == TENTATIVE
    assert reconciliation["evidence"]["difference"] == -2


def test_documented_value_bounds_and_missing_values_are_flagged_not_replaced():
    runs, kpis, tables = _documents()
    kpis[0]["kpis"].append({
        "metric_type": "headline_kpi",
        "metric_label": "Rate",
        "metric_value": "120%",
    })
    tables[0]["values"]["Branches"] = ""
    result = assess_data_health(runs, kpis, tables, registry=_registry(), as_of=AS_OF)
    issues = _find(result, "value_quality")[0]["evidence"]["value_issues"]
    assert any(issue["issue"] == "percentage_outside_documented_bounds" for issue in issues)
    assert any(issue["issue"] == "missing_value" for issue in issues)
    assert tables[0]["values"]["Branches"] == ""


def test_substantial_change_flags_only_adjacent_observations_within_tolerance():
    first_runs, first_kpis, first_tables = _documents(
        reporting_date="2026-10-20",
        collected_at="2026-10-20T15:23:00+00:00",
        district_value="2",
        kpi_value="2",
    )
    second_runs, second_kpis, second_tables = _documents(
        reporting_date="2026-10-27",
        collected_at="2026-10-27T15:23:00+00:00",
        district_value="6",
        kpi_value="6",
    )
    result = assess_data_health(
        first_runs + second_runs,
        first_kpis + second_kpis,
        first_tables + second_tables,
        registry=_registry(),
        as_of=AS_OF,
    )
    change = _find(result, "value_change_review")[0]
    assert change["status"] == TENTATIVE
    assert change["evidence"]["changes"][0]["from_value_raw"] == "2"
    assert change["evidence"]["changes"][0]["to_value_raw"] == "6"

    third_runs, third_kpis, third_tables = _documents(
        reporting_date="2026-10-10",
        collected_at="2026-10-10T15:23:00+00:00",
        district_value="20",
        kpi_value="20",
    )
    spaced = assess_data_health(
        first_runs + third_runs,
        first_kpis + third_kpis,
        first_tables + third_tables,
        registry=_registry(),
        as_of=AS_OF,
    )
    assert _find(spaced, "value_change_review")[0]["status"] == SUPPORTED


def test_learned_baseline_requires_three_reporting_dates_and_is_descriptive():
    history = []
    runs, kpis, tables = _documents()
    history.extend(tables)
    result = assess_data_health(runs, kpis, history, registry=_registry(), as_of=AS_OF)
    baseline = result["learned_baselines"][0]
    assert baseline["status"] == NOT_ASSESSABLE
    assert baseline["median"] is None

    for reporting_date, collected_at, value in (
        ("2026-10-21", "2026-10-21T15:23:00+00:00", "2"),
        ("2026-10-14", "2026-10-14T15:23:00+00:00", "4"),
    ):
        _, _, rows = _documents(
            reporting_date=reporting_date,
            collected_at=collected_at,
            district_value=value,
        )
        history.extend(rows)
    result = assess_data_health(runs, kpis, history, registry=_registry(), as_of=AS_OF)
    baseline = result["learned_baselines"][0]
    assert len(baseline["reporting_dates"]) == MIN_BASELINE_REPORTING_DATES
    assert baseline["status"] == SUPPORTED
    assert baseline["median"] == 2
    assert "not a forecast" in baseline["interpretation"]


def test_learned_baseline_excludes_flagged_repeated_snapshots():
    history = []
    runs = []
    kpis = []
    for reporting_date, value in (
        ("2026-10-24", "8"),
        ("2026-10-21", "2"),
        ("2026-10-14", "4"),
        ("2026-10-27", "100"),
    ):
        repeated = reporting_date == "2026-10-27"
        dated_runs, dated_kpis, rows = _documents(
            reporting_date=reporting_date,
            collected_at=f"{reporting_date}T15:23:00+00:00",
            district_value=value,
            kpi_value=value,
        )
        dated_runs[0]["repeated_snapshot_warning"] = repeated
        runs.extend(dated_runs)
        kpis.extend(dated_kpis)
        history.extend(rows)

    result = assess_data_health(runs, kpis, history, registry=_registry(), as_of=AS_OF)
    baseline = result["learned_baselines"][0]
    assert baseline["status"] == TENTATIVE
    assert baseline["observation_count"] == 3
    assert baseline["reporting_dates"] == ["2026-10-14", "2026-10-21", "2026-10-24"]
    assert baseline["repeated_snapshot_dates"] == ["2026-10-27"]
    assert baseline["median"] == 4
    assert baseline["median_absolute_deviation"] == 2


def test_reporting_date_is_separate_from_collection_time_and_assessment_is_read_only():
    runs, kpis, tables = _documents(
        reporting_date="2026-10-24",
        collected_at="2026-10-27T15:23:00+02:00",
    )
    original = deepcopy((runs, kpis, tables))
    result = assess_data_health(runs, kpis, tables, registry=_registry(), as_of=AS_OF)
    assert result["assessed_at"] == AS_OF.isoformat()
    freshness = _find(result, "freshness")[0]
    assert freshness["evidence"]["latest_collected_at"].startswith("2026-10-27")
    assert runs[0]["snapshot_date"] == "2026-10-24"
    assert (runs, kpis, tables) == original


def test_dimension_checks_do_not_assume_nbr_support_from_other_pages():
    root = Path(__file__).resolve().parents[1]
    registry = load_expected_data_registry(root / "config" / "nbr_pages.json")
    inclusion_runs, _, _ = _documents()
    inclusion_runs[0]["page"] = "inclusion"
    inclusion_runs[0]["filters"] = {
        "Gender": "All",
        "Age Segment": "Youth",
    }
    agent_runs, _, _ = _documents()
    agent_runs[0]["page"] = "agents"
    agent_runs[0]["filters"] = {"Institution Type": "E-money Issuers"}
    result = assess_data_health(
        inclusion_runs + agent_runs,
        [],
        [],
        registry=registry,
        as_of=AS_OF,
    )
    inclusion_gender = next(
        finding for finding in _find(result, "dimension_coverage")
        if finding["evidence"].get("page") == "inclusion"
        and finding["evidence"].get("dimension") == "Gender"
    )
    agent_gender = next(
        finding for finding in _find(result, "dimension_coverage")
        if finding["evidence"].get("page") == "agents"
        and finding["evidence"].get("dimension") == "Gender"
    )
    assert inclusion_gender["status"] == TENTATIVE
    assert inclusion_gender["evidence"]["observed_categories"] == ["All"]
    assert agent_gender["status"] == NOT_ASSESSABLE
    education = next(
        finding for finding in _find(result, "dimension_coverage")
        if finding["evidence"].get("dimension") == "Education"
    )
    assert education["status"] == NOT_ASSESSABLE
