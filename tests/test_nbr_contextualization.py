import csv
import json
from copy import deepcopy
from datetime import date, datetime, timezone
from pathlib import Path

from src.models.nbr_intelligence.contextualization import (
    _matching_relationships,
    _review_queue_report,
    build_contextualization_report,
    compare_cross_channel_trends,
    generate_finscope_suggestions,
    load_finscope_baselines,
    prepare_source_points,
    summarize_trend,
)
from src.models.nbr_intelligence.indicator_mapping import (
    FINSCOPE_REFERENCE_PERIOD,
    INDICATOR_MAPPING,
    MAPPING_BY_VARIABLE,
)
from src.models.nbr_intelligence.review import merge_review_queue_csv


def _point(
    page,
    label,
    day,
    value,
    *,
    geography="Kirehe",
    filters=None,
    level="district",
    source_type="district_table",
):
    return {
        "page": page,
        "metric_label": label,
        "reporting_date": day,
        "value": value,
        "geography": geography,
        "geography_level": level,
        "filters": filters or {
            "Institution Type": "Banks",
            "Gender": "All",
            "Age Segment": "All",
            "Branch Status": "Active",
        },
        "source_type": source_type,
        "unit": "count",
        "source_record_id": f"{page}-{label}-{day}",
        "run_id": f"run-{page}-{day}",
        "collected_at": f"{day}T12:00:00+00:00",
        "combo_key": "{}",
        "quality_qualifications": [],
    }


def _channel_trend(page, label, values, *, institution="Banks", dates=None):
    dates = dates or ["2025-01-01", "2025-06-01", "2025-12-01"]
    filters = {
        "Institution Type": institution,
        "Gender": "All",
        "Age Segment": "All",
        "Branch Status" if page == "branches" else "Account Status": "Active",
        "Location": "All",
    }
    observations = [
        _point(
            page,
            label,
            day,
            value,
            filters=filters,
        )
        for day, value in zip(dates, values)
    ]
    return {
        "page": page,
        "metric_label": label,
        "geography_level": "district",
        "geography": "Kirehe",
        "filters": filters,
        "unit": "count",
        **summarize_trend(observations),
    }


def _source_records(values, filters=None):
    filters = filters or {
        "Institution Type": "Banks",
        "Branch Status": "Active",
        "Location": "All",
    }
    runs = []
    tables = []
    for index, (reporting_date, value) in enumerate(values):
        run_id = f"run-{index}"
        common = {
            "page": "branches",
            "snapshot_date": reporting_date,
            "combo_key": json.dumps(filters, sort_keys=True),
            "run_id": run_id,
            "collected_at": datetime.fromisoformat(
                f"{reporting_date}T12:00:00+00:00"
            ),
            "filters": filters,
        }
        runs.append({
            **common,
            "status": "complete",
            "repeated_snapshot_warning": False,
        })
        tables.append({
            **common,
            "district": "Kirehe",
            "district_known": True,
            "values": {"District": "Kirehe", "Branches": str(value)},
        })
    return runs, [], tables


def test_mapping_preserves_survey_scope_and_marks_proxy_boundaries():
    assert len(INDICATOR_MAPPING) == 8
    assert MAPPING_BY_VARIABLE["k1"]["survey_reference_period"] == (
        FINSCOPE_REFERENCE_PERIOD
    )
    assert MAPPING_BY_VARIABLE["k1"]["survey_weight"] == "pop_wt"
    assert any(
        item["page"] == "branches"
        and item["relationship"] == "contextual_indicator"
        for item in MAPPING_BY_VARIABLE["k1"]["nbr_relationships"]
    )
    assert MAPPING_BY_VARIABLE["qf4_10"]["nbr_relationships"] == []
    assert MAPPING_BY_VARIABLE["e9b"]["nbr_no_relevant_data_reason"]


def test_processed_finscope_baselines_reuse_existing_estimates():
    baselines = load_finscope_baselines(
        Path(__file__).resolve().parents[1]
        / "data"
        / "processed"
    )
    kirehe = next(
        item for item in baselines
        if item["analytical_level"] == "district"
        and item["geography"] == "Kirehe"
        and item["indicator_variable"] == "k1"
    )
    national = next(
        item for item in baselines
        if item["analytical_level"] == "national"
        and item["indicator_variable"] == "k1"
    )
    assert kirehe["estimate_percent"] == 5.41
    assert national["estimate_percent"] == 20.2
    assert national["valid_respondents"] == 13994


def test_trend_requires_three_dates_and_never_treats_missing_as_zero():
    two_dates = [
        _point("branches", "Branches", "2025-01-01", 4),
        _point("branches", "Branches", "2025-12-01", 10),
    ]
    summary = summarize_trend(two_dates)
    assert summary["direction"] == "not_assessable"
    assert summary["evidence_sufficiency_state"] == "insufficient_evidence"

    three_dates = [
        _point("branches", "Branches", "2025-01-01", 4),
        _point("branches", "Branches", "2025-06-01", 7),
        _point("branches", "Branches", "2025-12-01", 10),
    ]
    summary = summarize_trend(three_dates)
    assert summary["direction"] == "increasing"
    assert summary["observation_count"] == 3
    assert summary["evidence_sufficiency_state"] == "limited_evidence"
    assert summary["interval_days"] == [151, 183]


def test_trend_direction_distinguishes_decrease_unchanged_and_mixed():
    base = ["2025-01-01", "2025-06-01", "2025-12-01"]
    assert summarize_trend([
        _point("branches", "Branches", day, value)
        for day, value in zip(base, [10, 7, 4])
    ])["direction"] == "decreasing"
    assert summarize_trend([
        _point("branches", "Branches", day, 4)
        for day in base
    ])["direction"] == "unchanged"
    assert summarize_trend([
        _point("branches", "Branches", day, value)
        for day, value in zip(base, [4, 10, 7])
    ])["direction"] == "mixed"


def test_cross_channel_reports_possible_substitution_without_a_combined_score():
    findings, summary = compare_cross_channel_trends([
        _channel_trend("branches", "Branches", [10, 8, 6]),
        _channel_trend("mobile_banking", "Customers", [100, 130, 170]),
    ])
    assert len(findings) == 1
    assert findings[0]["pattern"] == "possible_channel_substitution"
    assert summary["comparable_scope_count"] == 1
    assert "combined_score" not in findings[0]
    assert len(findings[0]["channels"]) == 2
    assert findings[0]["channels"][0]["metric_label"] == "Branches"
    assert findings[0]["channels"][1]["metric_label"] == "Customers"
    assert summary["comparison_counts_by_reason"]["compared"] == 1


def test_cross_channel_compares_all_metrics_on_a_page_without_collapsing_identity():
    branches = _channel_trend("branches", "Branches", [10, 8, 6])
    branch_locations = _channel_trend(
        "branches",
        "Branch Locations",
        [4, 5, 6],
    )
    mobile = _channel_trend("mobile_banking", "Customers", [50, 80, 90])

    findings, summary = compare_cross_channel_trends(
        [branches, branch_locations, mobile]
    )

    assert len(findings) == 2
    assert {
        finding["channels"][0]["metric_label"]
        for finding in findings
    } == {"Branches", "Branch Locations"}
    assert all(
        finding["channels"][1]["metric_label"] == "Customers"
        for finding in findings
    )
    assert len({finding["pair_id"] for finding in findings}) == 2
    assert summary["comparison_counts_by_reason"]["compared"] == 2


def test_shorter_series_is_compared_when_it_has_more_date_overlap():
    longest = _channel_trend(
        "branches",
        "Branch Count",
        [1, 2, 3, 4, 5],
        dates=[
            "2024-12-01",
            "2025-01-01",
            "2025-06-01",
            "2026-01-01",
            "2026-06-01",
        ],
    )
    shorter = _channel_trend(
        "branches",
        "Active Locations",
        [10, 9, 8],
        dates=["2025-01-01", "2025-06-01", "2025-12-01"],
    )
    mobile = _channel_trend(
        "mobile_banking",
        "Customers",
        [100, 110, 120],
        dates=["2025-01-01", "2025-06-01", "2025-12-01"],
    )

    findings, summary = compare_cross_channel_trends(
        [longest, shorter, mobile]
    )

    assert len(findings) == 1
    assert findings[0]["channels"][0]["metric_label"] == "Active Locations"
    assert findings[0]["shared_reporting_dates"] == [
        "2025-01-01",
        "2025-06-01",
        "2025-12-01",
    ]
    assert summary["comparison_counts_by_reason"] == {
        "candidate_pairs": 2,
        "compared": 1,
        "insufficient_shared_dates": 1,
    }


def test_cross_channel_classifies_complementary_growth_and_broad_contraction():
    growth, _ = compare_cross_channel_trends([
        _channel_trend("branches", "Branches", [5, 8, 10]),
        _channel_trend("mobile_banking", "Customers", [50, 80, 90]),
    ])
    decline, _ = compare_cross_channel_trends([
        _channel_trend("branches", "Branches", [10, 8, 6]),
        _channel_trend("mobile_banking", "Customers", [90, 80, 70]),
    ])
    assert growth[0]["pattern"] == "complementary_growth"
    assert decline[0]["pattern"] == "broad_contraction"


def test_cross_channel_rejects_mismatched_scopes_or_too_few_shared_dates():
    mismatched_scope, scope_summary = compare_cross_channel_trends([
        _channel_trend("branches", "Branches", [5, 8, 10], institution="Banks"),
        _channel_trend("mobile_banking", "Customers", [50, 80, 90], institution="Sacco"),
    ])
    mismatched_dates, date_summary = compare_cross_channel_trends([
        _channel_trend("branches", "Branches", [5, 8, 10]),
        _channel_trend(
            "mobile_banking",
            "Customers",
            [50, 80, 90],
            dates=["2025-06-01", "2025-12-01", "2026-06-01"],
        ),
    ])
    assert mismatched_scope == []
    assert mismatched_dates == []
    assert scope_summary["comparison_counts_by_reason"]["incompatible_scope"] == 1
    assert (
        date_summary["comparison_counts_by_reason"]["insufficient_shared_dates"]
        == 1
    )


def test_cross_channel_rejects_incompatible_additional_filters():
    branches = _channel_trend("branches", "Branches", [5, 8, 10])
    mobile = _channel_trend("mobile_banking", "Customers", [50, 80, 90])
    mobile["filters"] = dict(mobile["filters"])
    mobile["filters"].pop("Account Status")
    for point in mobile["observations"]:
        point["filters"] = dict(mobile["filters"])

    findings, summary = compare_cross_channel_trends([branches, mobile])

    assert findings == []
    assert (
        summary["comparison_counts_by_reason"]["incompatible_filter_scope"]
        == 1
    )


def test_cross_channel_deduplicates_series_and_skips_duplicate_reporting_dates():
    branches = _channel_trend("branches", "Branches", [10, 8, 6])
    mobile = _channel_trend("mobile_banking", "Customers", [50, 80, 90])

    findings, duplicate_summary = compare_cross_channel_trends(
        [branches, branches, mobile]
    )
    assert len(findings) == 1
    assert duplicate_summary["duplicate_series_count"] == 1
    assert duplicate_summary["candidate_pair_count"] == 1

    branches_with_duplicate_date = dict(branches)
    branches_with_duplicate_date["observations"] = [
        *branches["observations"],
        dict(branches["observations"][0]),
    ]
    duplicate_date_findings, date_summary = compare_cross_channel_trends(
        [branches_with_duplicate_date, mobile]
    )
    assert duplicate_date_findings == []
    assert (
        date_summary["comparison_counts_by_reason"]["duplicate_reporting_dates"]
        == 1
    )


def test_gender_mapping_is_exact_and_age_bins_are_not_crosswalked():
    gender = {
        "analytical_level": "demographic",
        "indicator_variable": "k1",
        "subgroup_type": "Gender",
        "subgroup": "Female",
    }
    age = {
        **gender,
        "subgroup_type": "Age group",
        "subgroup": "16–24",
    }
    matched = [
        relationship["filter_scope"]
        for relationship in _matching_relationships(gender)
    ]
    assert matched
    assert all(item["Gender"] == "Female" for item in matched)
    assert all(item["Age Segment"] == "All" for item in matched)
    assert _matching_relationships(age) == []


def test_contextual_suggestion_keeps_original_baseline_and_excludes_future_dates():
    source_data = [
        ("2025-01-01", 10),
        ("2025-03-01", 12),
        ("2025-05-01", 15),
        ("2025-07-01", 20),
    ]
    runs, kpis, tables = _source_records(source_data)
    originals = deepcopy((runs, kpis, tables))
    baseline = {
        "analytical_level": "district",
        "geography": "Kirehe",
        "subgroup_type": "",
        "subgroup": "",
        "indicator_variable": "k1",
        "indicator_label": "Bank-account ownership",
        "estimate_percent": 5.41,
        "valid_respondents": 464,
        "baseline_source": "district_financial_inclusion.csv",
    }
    report = build_contextualization_report(
        runs,
        kpis,
        tables,
        [baseline],
        assessed_at=datetime(2025, 6, 30, tzinfo=timezone.utc),
    )
    suggestion = next(
        item for item in report["suggestions"]
        if item["indicator_variable"] == "k1"
        and item["nbr_page"] == "branches"
    )
    assert suggestion["finscope_estimate_percent"] == 5.41
    assert suggestion["finscope_reference_period"] == "FinScope Rwanda 2024"
    assert suggestion["nbr_observation_periods"] == [
        "2025-01-01", "2025-03-01", "2025-05-01"
    ]
    assert suggestion["outcome"] == "potential_improvement"
    assert suggestion["evidence_sufficiency_state"] == "limited_evidence"
    assert suggestion["nbr_metric"] == "Branches"
    assert report["assessment"]["FinScope_baseline_not_recomputed"] is True
    assert (runs, kpis, tables) == originals


def test_anomaly_scores_do_not_create_contextual_suggestions():
    baseline = {
        "analytical_level": "district",
        "geography": "Kirehe",
        "subgroup_type": "",
        "subgroup": "",
        "indicator_variable": "k1",
        "indicator_label": "Bank-account ownership",
        "estimate_percent": 5.41,
        "baseline_source": "district_financial_inclusion.csv",
    }
    suggestion = generate_finscope_suggestions(
        [baseline],
        [],
        [],
    )[0]
    assert suggestion["outcome"] == "insufficient_evidence"
    assert suggestion["supporting_evidence"] == []


def test_unresolved_nbr_proxy_direction_does_not_imply_survey_improvement():
    baseline = {
        "analytical_level": "national",
        "geography": "Rwanda",
        "subgroup_type": "",
        "subgroup": "",
        "indicator_variable": "f5",
        "indicator_label": "Registered mobile-money user",
        "estimate_percent": 66.61,
        "baseline_source": "national_financial_inclusion.csv",
    }
    trend = {
        "page": "inclusion",
        "metric_label": "Total Customers",
        "geography_level": "national",
        "geography": "Rwanda",
        "filters": {
            "Gender": "All",
            "Age Segment": "All",
            "Account/Policy Status": "Active",
            "Location": "All",
            "Institution Type": "E-money issuers",
        },
        "direction": "increasing",
        "evidence_sufficiency_state": "limited_evidence",
        "reporting_dates": ["2025-01-01", "2025-06-01", "2025-12-01"],
        "observations": [
            _point(
                "inclusion",
                "Customers",
                day,
                value,
                geography="Rwanda",
                level="national",
                filters={
                    "Gender": "All",
                    "Age Segment": "All",
                    "Account/Policy Status": "Active",
                    "Location": "All",
                    "Institution Type": "E-money issuers",
                },
                source_type="national_kpi",
            )
            for day, value in zip(
                ["2025-01-01", "2025-06-01", "2025-12-01"],
                [10, 15, 20],
            )
        ],
        "quality_qualifications": [],
        "source_record_ids": ["one", "two", "three"],
    }
    suggestion = generate_finscope_suggestions([baseline], [trend], [])[0]
    assert suggestion["outcome"] == "insufficient_evidence"
    assert suggestion["nbr_observed_direction"] == "increasing"
    assert "relationship to the FinScope measure is not established" in (
        suggestion["suggested_interpretation"]
    )
    assert suggestion["survey_indicator_conclusion"] == "not_established"


def test_kirehe_bank_customer_proxy_remains_insufficient_evidence():
    filters = {
        "Gender": "All",
        "Age Segment": "All",
        "Institution Type": "Banks",
        "Account/Policy Status": "Active",
        "Location": "All",
    }
    dates = [
        "2025-02-20",
        "2025-11-20",
        "2026-08-20",
        "2026-10-24",
        "2026-10-27",
    ]
    values = [24916, 22862, 22703, 22139, 21943]
    observations = [
        _point(
            "inclusion",
            "Customers",
            day,
            value,
            filters=filters,
        )
        for day, value in zip(dates, values)
    ]
    trend = {
        "page": "inclusion",
        "metric_label": "Customers",
        "geography_level": "district",
        "geography": "Kirehe",
        "filters": filters,
        "direction": "decreasing",
        "evidence_sufficiency_state": "limited_evidence",
        "reporting_dates": dates,
        "observations": observations,
        "quality_qualifications": [],
        "source_record_ids": [
            item["source_record_id"] for item in observations
        ],
    }
    baseline = {
        "analytical_level": "district",
        "geography": "Kirehe",
        "subgroup_type": "",
        "subgroup": "",
        "indicator_variable": "k1",
        "indicator_label": "Bank-account ownership",
        "estimate_percent": 5.41,
        "baseline_source": "district_financial_inclusion.csv",
    }

    suggestions = generate_finscope_suggestions([baseline], [trend], [])
    suggestion = next(
        item for item in suggestions
        if item.get("nbr_page") == "inclusion"
    )

    assert suggestion["finscope_estimate_percent"] == 5.41
    assert suggestion["outcome"] == "insufficient_evidence"
    assert suggestion["nbr_observed_direction"] == "decreasing"
    assert suggestion["nbr_channel_directional_signal"]["direction"] == "decreasing"
    assert suggestion["survey_indicator_conclusion"] == "not_established"
    assert suggestion["supporting_evidence"][0]["relationship"] == (
        "proxy_with_unresolved_definition"
    )


def test_muhanga_sacco_branch_decline_and_internet_growth_become_mixed_evidence():
    dates = ["2025-02-20", "2025-11-20", "2026-08-20", "2026-10-24"]
    internet_banking_dates = [*dates, "2026-10-27"]
    branches = _channel_trend(
        "branches",
        "Branches",
        [20, 19, 19, 19],
        institution="Sacco",
        dates=dates,
    )
    internet_banking = _channel_trend(
        "internet_banking",
        "Customers",
        [104, 123, 145, 152, 151],
        institution="Sacco",
        dates=internet_banking_dates,
    )
    branches["geography"] = "Muhanga"
    internet_banking["geography"] = "Muhanga"
    for trend in (branches, internet_banking):
        trend["observations"] = [
            {**point, "geography": "Muhanga"}
            for point in trend["observations"]
        ]
    channel_findings, _ = compare_cross_channel_trends(
        [branches, internet_banking]
    )
    baseline = {
        "analytical_level": "district",
        "geography": "Muhanga",
        "subgroup_type": "",
        "subgroup": "",
        "indicator_variable": "qf4_06",
        "indicator_label": "Currently uses an Umurenge SACCO",
        "estimate_percent": 18.57,
        "baseline_source": "district_extended_indicators.csv",
    }

    suggestions = generate_finscope_suggestions(
        [baseline],
        [branches, internet_banking],
        channel_findings,
    )
    branch_suggestion = next(
        item for item in suggestions
        if item.get("nbr_page") == "branches"
    )

    assert channel_findings[0]["pattern"] == "possible_channel_substitution"
    assert branch_suggestion["nbr_channel_directional_signal"]["direction"] == (
        "decreasing"
    )
    assert branch_suggestion["outcome"] == "mixed_evidence"
    assert branch_suggestion["contradictory_or_missing_evidence"] == [
        "possible_channel_substitution"
    ]
    assert branch_suggestion["cross_channel_context"][0]["channels"][1][
        "direction"
    ] == "increasing"
    aligned_channels = {
        channel["page"]: channel
        for channel in branch_suggestion["cross_channel_context"][0]["channels"]
    }
    branch_channel = aligned_channels["branches"]
    internet_channel = aligned_channels["internet_banking"]
    assert [
        (item["reporting_date"], item["observed_value"])
        for item in branch_channel["observations"]
    ] == list(zip(dates, [20, 19, 19, 19]))
    assert [
        (item["reporting_date"], item["observed_value"])
        for item in internet_channel["observations"]
    ] == list(zip(dates, [104, 123, 145, 152]))
    assert all(
        item["page"] == "internet_banking"
        and item["metric_label"] == "Customers"
        and item["unit"] == "count"
        and item["filters"]["Institution Type"] == "Sacco"
        and item["source_record_id"]
        for item in internet_channel["observations"]
    )
    assert internet_banking["direction"] == "mixed"
    assert internet_banking["first_value"] == 104
    assert internet_banking["last_value"] == 151
    assert internet_banking["reporting_dates"] == internet_banking_dates
    assert internet_channel["observations"][-1]["observed_value"] == 152
    assert internet_banking["observations"][-1]["value"] == 151
    assert (
        branch_suggestion["cross_channel_context"][0]["channels"][1][
            "filter_compatibility_policy"
        ]
        == "page_specific_active_status_filters"
    )
    assert branch_suggestion["survey_indicator_conclusion"] == "not_established"
    assert "neither movement establishes a change" in (
        branch_suggestion["suggested_interpretation"].casefold()
    )


def test_conflicting_channels_do_not_override_unresolved_proxy_abstention():
    filters = {
        "Gender": "All",
        "Age Segment": "All",
        "Institution Type": "E-money issuers",
        "Account/Policy Status": "Active",
        "Location": "All",
    }
    dates = ["2025-01-01", "2025-06-01", "2025-12-01"]
    observations = [
        _point(
            "inclusion",
            "Total Customers",
            day,
            value,
            geography="Rwanda",
            level="national",
            filters=filters,
            source_type="national_kpi",
        )
        for day, value in zip(dates, [10, 15, 20])
    ]
    trend = {
        "page": "inclusion",
        "metric_label": "Total Customers",
        "geography_level": "national",
        "geography": "Rwanda",
        "filters": filters,
        "direction": "increasing",
        "evidence_sufficiency_state": "limited_evidence",
        "reporting_dates": dates,
        "observations": observations,
        "quality_qualifications": [],
        "source_record_ids": [
            item["source_record_id"] for item in observations
        ],
    }
    conflicting = {
        "analytical_level": "national",
        "geography": "Rwanda",
        "gender_filter": "all",
        "age_segment_filter": "all",
        "institution_type_filter": "e-money issuers",
        "pattern": "mixed_trends",
        "channels": [
            {
                "page": "inclusion",
                "metric_label": "Customers",
                "direction": "increasing",
                "source_record_ids": trend["source_record_ids"],
            },
            {
                "page": "agents",
                "metric_label": "Agents",
                "direction": "decreasing",
                "source_record_ids": ["agent-1", "agent-2", "agent-3"],
            },
        ],
    }
    baseline = {
        "analytical_level": "national",
        "geography": "Rwanda",
        "subgroup_type": "",
        "subgroup": "",
        "indicator_variable": "f5",
        "indicator_label": "Registered mobile-money user",
        "estimate_percent": 66.61,
        "baseline_source": "national_financial_inclusion.csv",
    }

    suggestion = generate_finscope_suggestions(
        [baseline],
        [trend],
        [conflicting],
    )[0]

    assert suggestion["outcome"] == "insufficient_evidence"
    assert suggestion["nbr_channel_directional_signal"]["direction"] == "increasing"
    assert suggestion["survey_indicator_conclusion"] == "not_established"


def test_source_extraction_excludes_repeated_or_mismatched_runs():
    filters = {"Institution Type": "Banks"}
    common = {
        "page": "branches",
        "snapshot_date": "2025-01-01",
        "combo_key": json.dumps(filters, sort_keys=True),
        "run_id": "run-1",
        "collected_at": datetime(2025, 1, 2, tzinfo=timezone.utc),
        "filters": filters,
    }
    run = {**common, "status": "complete", "repeated_snapshot_warning": False}
    kpi = {
        **common,
        "kpis": [{
            "metric_type": "headline_kpi",
            "metric_label": "Total Branches",
            "metric_value": "77",
        }],
    }
    points, summary = prepare_source_points(
        [run],
        [kpi],
        [],
        as_of_date=date(2025, 12, 31),
    )
    assert len(points) == 1
    assert points[0]["geography_level"] == "national"
    assert points[0]["value"] == 77
    assert summary["eligible_national_kpi_point_count"] == 1

    mismatch = {**kpi, "run_id": "other-run"}
    points, summary = prepare_source_points(
        [run],
        [mismatch],
        [],
        as_of_date=date(2025, 12, 31),
    )
    assert points == []
    assert summary["excluded_kpi_documents_by_reason"]["run_id_mismatch"] == 1


def test_review_queue_preserves_disposition_when_context_is_rerun(tmp_path):
    runs, kpis, tables = _source_records([
        ("2025-01-01", 10),
        ("2025-03-01", 12),
        ("2025-05-01", 15),
    ])
    baseline = {
        "analytical_level": "district",
        "geography": "Kirehe",
        "subgroup_type": "",
        "subgroup": "",
        "indicator_variable": "k1",
        "indicator_label": "Bank-account ownership",
        "estimate_percent": 5.41,
        "baseline_source": "district_financial_inclusion.csv",
    }
    report = build_contextualization_report(runs, kpis, tables, [baseline])
    assert report["assessment"]["model_version"] == "nbr-intelligence-0.4.4"
    assert report["assessment"]["source_git_commit"]
    assert isinstance(report["assessment"]["source_worktree_dirty"], bool)
    review_report = _review_queue_report(report)
    path = tmp_path / "context-review.csv"
    merge_review_queue_csv(review_report, path)
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert rows
    assert {
        row["model_version"] for row in rows
    } == {report["assessment"]["model_version"]}
    rows[0]["review_status"] = "reviewed"
    rows[0]["reviewer"] = "reviewer@example.invalid"
    rows[0]["reviewer_disposition"] = "needs_source_verification"
    rows[0]["reviewer_rationale"] = "Check documented count definition."
    rows[0]["supporting_source_evidence"] = "NBR source table checked."
    rows[0]["review_timestamp"] = "2026-10-29T00:00:00Z"
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    merge_review_queue_csv(review_report, path)
    with path.open(encoding="utf-8-sig", newline="") as stream:
        saved = list(csv.DictReader(stream))
    assert saved[0]["review_status"] == "reviewed"
    assert saved[0]["reviewer"] == "reviewer@example.invalid"
    assert saved[0]["reviewer_disposition"] == "needs_source_verification"
    assert saved[0]["reviewer_rationale"] == "Check documented count definition."
    assert saved[0]["supporting_source_evidence"] == "NBR source table checked."
    assert saved[0]["review_timestamp"] == "2026-10-29T00:00:00Z"
    assert saved[0]["model_version"] == report["assessment"]["model_version"]
