import csv
import json
import math
import statistics
from datetime import date, datetime, timedelta, timezone

import pytest

from src.data_sources.nbr_anomaly_experiment import (
    NBRObservation,
    build_experiment_report,
    evaluate_chronologically,
    evaluate_cross_sectionally,
    prepare_observations,
    write_review_queue_csv,
)
from src.models.nbr_intelligence.assessment import write_json_report_new
from src.models.nbr_intelligence.experiment import _score_rate_deviation
import src.models.nbr_intelligence.contextualization as contextualization
import src.models.nbr_intelligence.experiment as experiment


def _records(
    values,
    *,
    page="branches",
    combo_key='{"Institution Type": "Banks"}',
    district="Alpha",
    repeated_dates=(),
    run_status="complete",
):
    runs = []
    tables = []
    start = date(2025, 1, 1)
    for index, value in enumerate(values):
        reporting_date = (start + timedelta(days=index * 30)).isoformat()
        run_id = f"run-{index}"
        run = {
            "page": page,
            "snapshot_date": reporting_date,
            "combo_key": combo_key,
            "run_id": run_id,
            "status": run_status,
            "repeated_snapshot_warning": reporting_date in repeated_dates,
            "collected_at": datetime(2025, 1, 2, tzinfo=timezone.utc) + timedelta(days=index),
            "filters": {"Institution Type": "Banks"},
        }
        runs.append(run)
        tables.append({
            "page": page,
            "snapshot_date": reporting_date,
            "combo_key": combo_key,
            "run_id": run_id,
            "collected_at": run["collected_at"],
            "district": district,
            "district_known": district.casefold() != "unknown",
            "values": {"District": district, "Branches": str(value)},
        })
    return runs, tables


def _observation(day, value, *, collected_at=None):
    return NBRObservation(
        page="branches",
        metric_label="Branches",
        district="Alpha",
        combo_key='{"Institution Type": "Banks"}',
        reporting_date=day,
        collected_at=collected_at or f"{day.isoformat()}T12:00:00+00:00",
        run_id=f"run-{day.isoformat()}",
        filters={"Institution Type": "Banks"},
        value=value,
    )


def _cross_section_records(values, *, filters=None, reporting_date="2026-10-27"):
    import json

    filters = filters or {"Institution Type": "Banks"}
    combo_key = json.dumps(filters, sort_keys=True)
    run_id = "cross-section-run"
    collected_at = datetime(2026, 10, 28, tzinfo=timezone.utc)
    common = {
        "page": "branches",
        "snapshot_date": reporting_date,
        "combo_key": combo_key,
        "run_id": run_id,
        "collected_at": collected_at,
        "filters": filters,
    }
    runs = [{
        **common,
        "status": "complete",
        "repeated_snapshot_warning": False,
    }]
    tables = []
    for district, value in values:
        tables.append({
            **common,
            "district": district,
            "district_known": district.casefold() != "unknown",
            "values": {"District": district, "Branches": str(value)},
        })
    return runs, tables


def test_preparation_preserves_zero_reporting_date_and_collection_timestamp():
    runs, tables = _records([0, 4])
    observations, excluded_rows, excluded_values = prepare_observations(runs, tables)

    assert [item.value for item in observations] == [0.0, 4.0]
    assert observations[0].reporting_date.isoformat() == runs[0]["snapshot_date"]
    assert observations[0].collected_at == runs[0]["collected_at"].isoformat()
    assert excluded_rows == {}
    assert excluded_values == {}


def test_preparation_excludes_failed_repeated_and_unknown_observations():
    runs, tables = _records([2, 3, 4])
    runs[1]["status"] = "failed"
    runs[2]["repeated_snapshot_warning"] = True
    tables[2]["district"] = "unknown"
    tables[2]["district_known"] = False

    observations, excluded_rows, _ = prepare_observations(runs, tables)

    assert len(observations) == 1
    assert excluded_rows == {
        "collection_not_complete": 1,
        "repeated_snapshot": 1,
    }


def test_preparation_does_not_merge_different_filter_combinations():
    runs_a, tables_a = _records([1, 2])
    tables_a[0]["values"]["POS"] = "3"
    runs_b, tables_b = _records(
        [100, 200],
        combo_key='{"Institution Type": "Sacco"}',
    )

    observations, _, _ = prepare_observations(
        runs_a + runs_b,
        tables_a + tables_b,
    )
    summary, _ = evaluate_chronologically(observations)

    assert {item.combo_key for item in observations} == {
        '{"Institution Type": "Banks"}',
        '{"Institution Type": "Sacco"}',
    }
    assert {item.metric_label for item in observations} == {"Branches", "POS"}
    assert summary["comparable_series"] == 3
    assert summary["series_without_a_walk_forward_test"] == 3


def test_duplicate_run_identity_and_duplicate_series_dates_are_excluded():
    runs, tables = _records([2])
    runs.append(dict(runs[0]))
    observations, excluded_rows, _ = prepare_observations(runs, tables)
    assert observations == []
    assert excluded_rows["missing_or_ambiguous_collection_run"] == 1

    runs, tables = _records([2])
    duplicate = dict(tables[0])
    duplicate["row_index"] = 1
    tables.append(duplicate)
    observations, _, excluded_values = prepare_observations(runs, tables)
    assert observations == []
    assert excluded_values["duplicate_series_reporting_date"] == 2


def test_run_id_and_filter_provenance_mismatches_are_excluded():
    runs, tables = _records([2, 3, 4])
    tables[0]["run_id"] = "different-run"
    runs[1]["filters_key"] = '{"Institution Type": "Sacco"}'
    tables[2]["filters"] = {"Institution Type": "Sacco"}

    observations, excluded_rows, _ = prepare_observations(runs, tables)

    assert observations == []
    assert excluded_rows == {
        "run_id_mismatch": 1,
        "run_filter_key_mismatch": 1,
        "run_filter_values_mismatch": 1,
    }


def test_missing_timestamp_invalid_date_and_unsuitable_values_are_excluded():
    runs, tables = _records([2, 3, 4, 5])
    runs[0]["collected_at"] = None
    tables[0]["collected_at"] = None
    invalid_date = "not-a-reporting-date"
    runs[1]["snapshot_date"] = invalid_date
    tables[1]["snapshot_date"] = invalid_date
    tables[2]["values"]["Branches"] = "not reported"
    tables[3]["values"]["Branches"] = "-1"

    observations, excluded_rows, excluded_values = prepare_observations(runs, tables)

    assert observations == []
    assert excluded_rows["missing_or_invalid_collection_timestamp"] == 1
    assert excluded_rows["invalid_reporting_date"] == 1
    assert excluded_rows["no_usable_metric_values"] == 2
    assert excluded_values == {
        "missing_or_non_numeric_value": 1,
        "negative_value": 1,
    }


def test_candidate_scores_only_after_three_prior_rates_and_flags_large_change():
    days = [date(2025, 1, 1) + timedelta(days=30 * index) for index in range(5)]
    observations = [
        _observation(day, value)
        for day, value in zip(days, [10, 12, 14, 16, 1000])
    ]

    summary, cases = evaluate_chronologically(observations)

    assert len(cases) == 1
    assert cases[0]["training_rate_count"] == 3
    assert cases[0]["model_status"] == "scored"
    assert cases[0]["model_alert"] is True
    assert cases[0]["model_signed_robust_score"] > 0
    assert cases[0]["model_robust_score"] == abs(
        cases[0]["model_signed_robust_score"]
    )
    assert cases[0]["deviation_direction"] == "above_historical_median"
    assert cases[0]["observed_change_direction"] == "increase"
    assert cases[0]["level_baseline_status"] == "scored"
    assert cases[0]["target"]["value"] == 1000
    assert summary["labeled_outcomes_available"] is False
    assert summary["precision_recall_or_false_alarm_rate"] is None


def test_cross_section_compares_only_exact_metric_date_and_filter_scope():
    districts = [(f"District {index:02}", 100 + index % 4) for index in range(11)]
    districts[-1] = ("District 10", 1000)
    runs, tables = _cross_section_records(districts)
    observations, _, _ = prepare_observations(runs, tables)

    summary, candidates = evaluate_cross_sectionally(observations, tables)

    assert summary["assessable_groups"] == 1
    assert summary["candidate_count"] == 1
    candidate = candidates[0]
    assert candidate["district"] == "District 10"
    assert candidate["direction"] == "high"
    assert candidate["reporting_date"] == "2026-10-27"
    assert candidate["filters"] == {"Institution Type": "Banks"}
    assert candidate["comparison_district_count"] == 11

    other_scope = [
        _observation(date(2026, 10, 27), 999)
    ]
    other_scope[0] = NBRObservation(
        **{
            **other_scope[0].__dict__,
            "combo_key": '{"Institution Type": "Sacco"}',
            "filters": {"Institution Type": "Sacco"},
        }
    )
    combined_summary, _ = evaluate_cross_sectionally(
        observations + other_scope,
        tables,
    )
    assert combined_summary["assessable_groups"] == 1
    assert combined_summary["groups_too_small"] == 1


def test_cross_section_qualifies_missing_and_unknown_geography_without_imputing():
    values = [(f"District {index:02}", 100 + index % 3) for index in range(11)]
    values[-1] = ("District 10", 1000)
    values.append(("unknown", 50000))
    runs, tables = _cross_section_records(values)
    observations, excluded_rows, _ = prepare_observations(runs, tables)
    expected = [f"District {index:02}" for index in range(13)]

    summary, candidates = evaluate_cross_sectionally(
        observations,
        tables,
        expected_districts=expected,
    )

    assert excluded_rows["unknown_or_unverified_district"] == 1
    assert summary["assessable_observations"] == 11
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate["observed_value"] == 1000
    assert candidate["expected_district_count"] == 13
    assert candidate["missing_district_count"] == 2
    assert candidate["unknown_rows"] == ["unknown"]
    assert {
        item["check"] for item in candidate["quality_qualifications"]
    } == {"geographic_coverage"}


def test_cross_section_threshold_and_small_value_sensitivity_are_reported():
    peers = [
        ("Peer 00", 96), ("Peer 01", 97), ("Peer 02", 98),
        ("Peer 03", 99), ("Peer 04", 99), ("Peer 05", 100),
        ("Peer 06", 100), ("Peer 07", 100), ("Peer 08", 100),
        ("Peer 09", 101), ("Peer 10", 101), ("Peer 11", 102),
        ("Peer 12", 102), ("Peer 13", 103), ("Peer 14", 104),
        ("Peer 15", 98), ("Peer 16", 99), ("Peer 17", 101),
        ("Peer 18", 102), ("Target", 107.8),
    ]
    runs, tables = _cross_section_records(peers)
    observations, _, _ = prepare_observations(runs, tables)

    summary, candidates = evaluate_cross_sectionally(observations, tables)

    target = next(item for item in candidates if item["district"] == "Target")
    assert target["absolute_robust_score"] >= 3.5
    assert target["sensitivity_1pct"]["classification_changes_with_1pct_perturbation"]
    assert summary["candidate_count_by_threshold"]["3.0"] >= summary["candidate_count_by_threshold"]["3.5"]
    assert summary["candidate_count_by_threshold"]["3.5"] >= summary["candidate_count_by_threshold"]["4.0"]
    assert summary["observations_changing_flag_under_plus_minus_1pct_perturbation"] >= 1


def test_cross_section_reports_zero_mad_and_small_scopes_as_unassessable():
    tied = [(f"District {index:02}", 7) for index in range(12)]
    runs, tables = _cross_section_records(tied)
    observations, _, _ = prepare_observations(runs, tables)

    summary, candidates = evaluate_cross_sectionally(observations, tables)

    assert summary["groups_with_zero_mad"] == 1
    assert summary["candidate_count"] == 0
    assert candidates == []


def test_report_compares_cross_sectional_and_temporal_flags_on_shared_cases():
    import json

    filters = {"Institution Type": "Banks"}
    combo_key = '{"Institution Type": "Banks"}'
    runs = []
    tables = []
    start = date(2025, 1, 1)
    for period in range(5):
        reporting_date = (start + timedelta(days=30 * period)).isoformat()
        run_id = f"shared-run-{period}"
        common = {
            "page": "branches",
            "snapshot_date": reporting_date,
            "combo_key": combo_key,
            "run_id": run_id,
            "collected_at": datetime(2025, 1, 2, tzinfo=timezone.utc)
            + timedelta(days=30 * period),
            "filters": filters,
        }
        runs.append({
            **common,
            "status": "complete",
            "repeated_snapshot_warning": False,
        })
        for district_index in range(11):
            value = 100 + district_index + period * (district_index + 1)
            if period == 4 and district_index == 10:
                value += 1000
            district = f"District {district_index:02}"
            tables.append({
                **common,
                "district": district,
                "district_known": True,
                "values": {"District": district, "Branches": str(value)},
            })

    report = build_experiment_report(
        runs,
        tables,
        expected_districts=[f"District {index:02}" for index in range(11)],
    )
    json.dumps(report)

    comparison = report["cross_sectional_temporal_comparison"]
    rate = comparison["methods"]["temporal_rate_mad"]
    level = comparison["methods"]["temporal_level_mad"]
    assert rate["common_assessable_cases"] == 11
    assert level["common_assessable_cases"] == 11
    assert rate["flagged_by_both"] > 0
    assert level["flagged_by_both"] > 0
    assert "_assessable_observation_keys" not in report["cross_sectional_evaluation"]
    for comparison in (rate, level):
        assert comparison["cross_sectional_candidates"] == (
            comparison["flagged_by_both"] + comparison["cross_sectional_only"]
        )
        assert comparison["temporal_candidates"] == (
            comparison["flagged_by_both"] + comparison["temporal_only"]
        )


def test_review_csv_preserves_candidate_and_leaves_human_fields_unreviewed(tmp_path):
    values = [(f"District {index:02}", 100 + index % 4) for index in range(11)]
    values[-1] = ("District 10", 1000)
    runs, tables = _cross_section_records(values)
    report = build_experiment_report(
        runs,
        tables,
        expected_districts=[f"District {index:02}" for index in range(11)],
    )
    output_path = tmp_path / "reviews" / "queue.csv"

    written = write_review_queue_csv(report, output_path)

    with output_path.open(encoding="utf-8-sig", newline="") as input_file:
        rows = list(csv.DictReader(input_file))
    assert written == len(rows) == 1
    row = rows[0]
    original = json.loads(row["original_candidate_json"])
    assert row["method"] == original["method"] == "cross_sectional_modified_z"
    assert row["page"] == original["page"] == "branches"
    assert row["observed_value"] == str(original["observed_value"])
    assert json.loads(row["filters_json"]) == original["filters"]
    assert json.loads(row["quality_qualifications_json"]) == (
        original["quality_qualifications"]
    )
    assert row["review_status"] == "pending"
    assert row["reviewer"] == ""
    assert row["reviewer_disposition"] == ""
    assert row["reviewer_rationale"] == ""
    assert row["supporting_source_evidence"] == ""
    assert row["review_timestamp"] == ""
    first_id = row["candidate_id"]

    write_review_queue_csv(report, output_path)
    with output_path.open(encoding="utf-8-sig", newline="") as input_file:
        repeated_row = next(csv.DictReader(input_file))
    assert repeated_row["candidate_id"] == first_id


def test_temporal_review_queue_serializes_signed_score_and_both_directions(
    tmp_path,
):
    runs, tables = _records([10, 12, 14, 16, 1000])
    report = build_experiment_report(runs, tables)
    output_path = tmp_path / "temporal-review.csv"

    write_review_queue_csv(report, output_path)

    with output_path.open(encoding="utf-8-sig", newline="") as input_file:
        row = next(
            item for item in csv.DictReader(input_file)
            if item["method"] == "temporal_rate_mad"
        )
    assert float(row["score"]) > 0
    assert float(row["signed_score"]) == float(row["score"])
    assert row["direction"] == "above_historical_median"
    assert row["observed_change_direction"] == "increase"


def test_walk_forward_fit_does_not_leak_the_test_or_future_values():
    days = [date(2025, 1, 1) + timedelta(days=30 * index) for index in range(6)]
    values_a = [10, 12, 14, 16, 30, 40]
    values_b = [10, 12, 14, 16, 30, 90000]

    _, cases_a = evaluate_chronologically([
        _observation(day, value) for day, value in zip(days, values_a)
    ])
    _, cases_b = evaluate_chronologically([
        _observation(day, value) for day, value in zip(days, values_b)
    ])

    assert cases_a[0]["target"]["value"] == cases_b[0]["target"]["value"] == 30
    assert cases_a[0]["training_rate_median_per_day"] == cases_b[0]["training_rate_median_per_day"]
    assert cases_a[0]["training_rate_mad_per_day"] == cases_b[0]["training_rate_mad_per_day"]
    assert cases_a[0]["model_robust_score"] == cases_b[0]["model_robust_score"]
    assert cases_a[0]["model_signed_robust_score"] == (
        cases_b[0]["model_signed_robust_score"]
    )
    assert cases_a[0]["level_baseline_median"] == cases_b[0]["level_baseline_median"]
    assert cases_a[0]["level_baseline_mad"] == cases_b[0]["level_baseline_mad"]


def test_zero_historical_mad_is_an_explicit_abstention():
    days = [date(2025, 1, 1) + timedelta(days=3 * index) for index in range(5)]
    observations = [
        _observation(day, value)
        for day, value in zip(days, [0, 0, 0, 0, 100])
    ]

    summary, cases = evaluate_chronologically(observations)

    assert cases[0]["model_status"] == "not_assessable_zero_training_mad"
    assert cases[0]["model_robust_score"] is None
    assert cases[0]["model_alert"] is False
    assert cases[0]["existing_50pct_8day_rule_alert"] is True
    assert cases[0]["level_baseline_status"] == "not_assessable_zero_training_mad"
    assert cases[0]["level_baseline_alert"] is False
    assert summary["model_abstentions_zero_mad"] == 1
    assert summary["level_baseline_abstentions_zero_mad"] == 1
    assert summary["existing_rule_alerts_where_model_abstained"] == 1


def test_large_decrease_is_alerted_with_negative_signed_deviation():
    days = [date(2025, 1, 1) + timedelta(days=30 * index) for index in range(5)]
    values = [100, 145, 180, 240, 30]
    _, cases = evaluate_chronologically([
        _observation(day, value) for day, value in zip(days, values)
    ])
    case = cases[0]

    assert case["model_status"] == "scored"
    assert case["model_alert"] is True
    assert case["model_signed_robust_score"] < 0
    assert case["model_robust_score"] == abs(case["model_signed_robust_score"])
    assert case["deviation_direction"] == "below_historical_median"
    assert case["observed_change_direction"] == "decrease"


def test_observation_near_historical_rate_median_is_not_alerted():
    days = [date(2025, 1, 1) + timedelta(days=30 * index) for index in range(5)]
    history_values = [100, 120, 155, 190]
    history_rates = [
        (math.log1p(right) - math.log1p(left)) / 30
        for left, right in zip(history_values, history_values[1:])
    ]
    expected_rate = statistics.median(history_rates)
    target_value = math.expm1(math.log1p(history_values[-1]) + expected_rate * 30)
    values = [*history_values, target_value]

    _, cases = evaluate_chronologically([
        _observation(day, value) for day, value in zip(days, values)
    ])
    case = cases[0]

    assert case["model_status"] == "scored"
    assert case["model_alert"] is False
    assert case["model_robust_score"] < 3.0
    assert case["deviation_direction"] in {
        "above_historical_median",
        "below_historical_median",
        "at_historical_median",
    }


def test_nonzero_mad_below_calculation_resolution_is_an_explicit_abstention():
    score, status = _score_rate_deviation(
        observed_rate=1e-8,
        center=0.0,
        mad=1e-20,
        dispersion_roundoff_bound=1e-18,
        historical_rates=[0.0, 0.0, 0.0],
    )

    assert score is None
    assert status == "below_floating_point_resolution"


def test_nonzero_mad_above_calculation_resolution_remains_scoreable():
    signed_score, status = _score_rate_deviation(
        observed_rate=-1e-4,
        center=0.0,
        mad=1e-5,
        dispersion_roundoff_bound=1e-18,
        historical_rates=[-1e-5, 0.0, 1e-5],
    )

    assert status == "resolved"
    assert signed_score is not None
    assert signed_score < 0


def test_small_nonzero_mad_with_discordant_history_abstains():
    days = [
        date(2025, 2, 20),
        date(2025, 11, 20),
        date(2026, 8, 20),
        date(2026, 10, 24),
        date(2026, 10, 27),
    ]
    values = [3239, 3381, 3214, 3247, 3185]

    summary, cases = evaluate_chronologically([
        _observation(day, value) for day, value in zip(days, values)
    ])
    case = cases[0]

    assert 0 < case["training_rate_mad_per_day"] < 1e-7
    assert case["model_dispersion_status"] == "discordant_training_rates"
    assert case["model_status"] == "not_assessable_discordant_training_rates"
    assert case["model_robust_score"] is None
    assert case["model_signed_robust_score"] is None
    assert case["model_alert"] is False
    assert summary["model_abstentions_discordant_training_rates"] == 1


def test_report_marks_repeated_snapshot_and_unknown_rows_as_unsuitable():
    runs, tables = _records([1, 2, 3, 4, 5])
    repeated_date = runs[1]["snapshot_date"]
    runs[1]["repeated_snapshot_warning"] = True
    runs[2]["status"] = "completed_no_data"
    tables[3]["district"] = "unknown"
    tables[3]["district_known"] = False

    report = build_experiment_report(runs, tables)

    assert report["data"]["excluded_table_rows_by_reason"]["repeated_snapshot"] == 1
    assert report["data"]["excluded_table_rows_by_reason"]["collection_not_complete"] == 1
    assert report["data"]["excluded_table_rows_by_reason"]["unknown_or_unverified_district"] == 1
    assert repeated_date not in report["data"]["reporting_dates"]


def test_tentative_kpi_reconciliation_is_attached_as_a_quality_qualification():
    runs, tables = _records([10, 12, 14, 16, 1000], page="agents")
    tables = [
        {
            **table,
            "values": {"District": "Alpha", "Agents": table["values"]["Branches"]},
        }
        for table in tables
    ]
    kpis = [
        {
            "page": run["page"],
            "snapshot_date": run["snapshot_date"],
            "combo_key": run["combo_key"],
            "kpis": [{
                "metric_label": "Total Agents",
                "metric_value": "1",
            }],
        }
        for run in runs
    ]

    report = build_experiment_report(runs, tables, kpis)

    assert report["data"]["tentative_reconciliation_scope_count"] == 5
    assert report["evaluation"]["walk_forward_test_cases"] == 1
    qualifications = report["cases"][0]["quality_qualifications"]
    assert len(qualifications) == 5
    assert {item["check"] for item in qualifications} == {"reconciliation"}


def test_anomaly_assessment_exposes_consistent_model_and_source_metadata():
    runs, tables = _records([10, 12, 14, 16, 20])
    report = build_experiment_report(runs, tables)

    experiment_metadata = report["experiment"]
    assessment_metadata = report["evidence_assessment"]
    assert experiment_metadata["model_version"] == "nbr-intelligence-0.4.4"
    assert experiment_metadata["source_git_commit"] == assessment_metadata[
        "source_git_commit"
    ]
    assert experiment_metadata["source_worktree_dirty"] == assessment_metadata[
        "source_worktree_dirty"
    ]


def test_json_report_writer_refuses_to_replace_existing_output(tmp_path):
    output = tmp_path / "historical.json"
    output.write_bytes(b"preserve this report")

    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        write_json_report_new(output, {"model_version": "new"})

    assert output.read_bytes() == b"preserve this report"
    assert list(tmp_path.iterdir()) == [output]


def test_both_report_clis_reject_existing_json_before_source_reads(
    tmp_path,
    monkeypatch,
):
    output = tmp_path / "existing.json"
    output.write_text("historical", encoding="utf-8")
    monkeypatch.setattr(
        experiment,
        "load_mongodb_history",
        lambda: pytest.fail("source data should not be loaded"),
    )
    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        experiment.main(["--output", str(output)])

    monkeypatch.setattr(
        contextualization,
        "load_mongodb_history",
        lambda: pytest.fail("source data should not be loaded"),
    )
    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        contextualization.main([
            "--output",
            str(output),
            "--review-csv",
            str(tmp_path / "review.csv"),
        ])
    assert output.read_text(encoding="utf-8") == "historical"
