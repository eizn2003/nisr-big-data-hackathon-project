"""Read-only NBR observation preparation and robust anomaly evaluation.

This module preserves the existing temporal and cross-sectional detectors.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.data_sources.mongodb_district_explorer import (
    CHANGE_REVIEW_THRESHOLD_PERCENT,
    DATABASE_NAME,
    KPI_COLLECTION,
    RUN_COLLECTION,
    TABLE_COLLECTION,
    parse_numeric_value,
)
from src.models.nbr_intelligence.assessment import (
    MODEL_VERSION,
    assess_evidence,
    attach_candidate_evidence,
    write_json_report_new,
)
from src.models.nbr_intelligence.review import (
    merge_review_queue_csv,
    write_review_queue_csv,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MIN_TRAINING_RATES = 3
ROBUST_SCORE_THRESHOLD = 3.0
BASELINE_MAX_GAP_DAYS = 8
MIN_CROSS_SECTION_DISTRICTS = 10
CROSS_SECTION_ROBUST_Z_THRESHOLD = 3.5
REVIEW_QUEUE_LIMIT_PER_METHOD = 100
TEMPORAL_SCORE_THRESHOLDS = (2.0, 2.5, 3.0, 3.5, 4.0)
LEVEL_SCORE_THRESHOLDS = (2.0, 2.5, 3.0, 3.5, 4.0)
_NON_METRIC_COLUMNS = {"district", "district name", "rank"}


@dataclass(frozen=True)
class NBRObservation:
    page: str
    metric_label: str
    district: str
    combo_key: str
    reporting_date: date
    collected_at: str
    run_id: str
    filters: dict[str, Any]
    value: float


def _identity(record: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        str(record.get("page", "")),
        str(record.get("snapshot_date", "")),
        str(record.get("combo_key", "")),
    )


def _timestamp_text(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str) and value.strip():
        try:
            datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
        return value.strip()
    return None


def prepare_observations(
    runs: Sequence[Mapping[str, Any]],
    table_documents: Sequence[Mapping[str, Any]],
) -> tuple[list[NBRObservation], dict[str, int], dict[str, int]]:
    """Keep only unique, complete, non-repeated, known-district numeric records."""
    runs_by_key: dict[tuple[str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for run in runs:
        runs_by_key[_identity(run)].append(run)

    excluded_rows: Counter[str] = Counter()
    excluded_values: Counter[str] = Counter()
    points_by_series_date: dict[
        tuple[str, str, str, str], dict[date, list[NBRObservation]]
    ] = defaultdict(lambda: defaultdict(list))

    for row in table_documents:
        key = _identity(row)
        matching_runs = runs_by_key.get(key, [])
        if not all(key):
            excluded_rows["missing_observation_identity"] += 1
            continue
        if len(matching_runs) != 1:
            excluded_rows["missing_or_ambiguous_collection_run"] += 1
            continue
        run = matching_runs[0]
        run_id = str(run.get("run_id", ""))
        if not run_id or str(row.get("run_id", "")) != run_id:
            excluded_rows["run_id_mismatch"] += 1
            continue
        if run.get("filters_key") and run.get("filters_key") != key[2]:
            excluded_rows["run_filter_key_mismatch"] += 1
            continue
        provenance_mismatch = False
        for field in ("filters", "filters_requested"):
            row_filters = row.get(field)
            run_filters = run.get(field)
            if (
                isinstance(row_filters, Mapping)
                and isinstance(run_filters, Mapping)
                and row_filters != run_filters
            ):
                provenance_mismatch = True
                break
        if provenance_mismatch:
            excluded_rows["run_filter_values_mismatch"] += 1
            continue
        if run.get("status") != "complete":
            excluded_rows["collection_not_complete"] += 1
            continue
        if run.get("repeated_snapshot_warning"):
            excluded_rows["repeated_snapshot"] += 1
            continue

        district = str(row.get("district") or "").strip()
        if (
            not district
            or district.casefold() == "unknown"
            or row.get("district_known") is not True
        ):
            excluded_rows["unknown_or_unverified_district"] += 1
            continue

        try:
            reporting_date = date.fromisoformat(key[1])
        except ValueError:
            excluded_rows["invalid_reporting_date"] += 1
            continue

        collected_at = _timestamp_text(row.get("collected_at"))
        if collected_at is None:
            collected_at = _timestamp_text(run.get("collected_at"))
        if collected_at is None:
            excluded_rows["missing_or_invalid_collection_timestamp"] += 1
            continue

        values = row.get("values")
        if not isinstance(values, Mapping):
            excluded_rows["missing_metric_values"] += 1
            continue

        usable_values = 0
        filters = run.get("filters")
        if not isinstance(filters, Mapping):
            filters = run.get("filters_requested")
        normalized_filters = dict(filters) if isinstance(filters, Mapping) else {}
        for raw_label, raw_value in values.items():
            label = str(raw_label).strip()
            if label.casefold() in _NON_METRIC_COLUMNS:
                continue
            value = parse_numeric_value(raw_value)
            if value is None or not math.isfinite(value):
                excluded_values["missing_or_non_numeric_value"] += 1
                continue
            if value < 0:
                excluded_values["negative_value"] += 1
                continue
            observation = NBRObservation(
                page=key[0],
                metric_label=label,
                district=district,
                combo_key=key[2],
                reporting_date=reporting_date,
                collected_at=collected_at,
                run_id=run_id,
                filters=normalized_filters,
                value=float(value),
            )
            points_by_series_date[
                (key[0], label, district.casefold(), key[2])
            ][reporting_date].append(observation)
            usable_values += 1
        if usable_values == 0:
            excluded_rows["no_usable_metric_values"] += 1

    observations: list[NBRObservation] = []
    for dates in points_by_series_date.values():
        for date_points in dates.values():
            if len(date_points) != 1:
                excluded_values["duplicate_series_reporting_date"] += len(date_points)
                continue
            observations.extend(date_points)

    observations.sort(
        key=lambda item: (
            item.page,
            item.metric_label,
            item.district.casefold(),
            item.combo_key,
            item.reporting_date,
        )
    )
    return observations, dict(excluded_rows), dict(excluded_values)


def _series_key(observation: NBRObservation) -> tuple[str, str, str, str]:
    return (
        observation.page,
        observation.metric_label,
        observation.district.casefold(),
        observation.combo_key,
    )


def _daily_log_rate(
    previous: NBRObservation,
    current: NBRObservation,
) -> float:
    elapsed_days = (current.reporting_date - previous.reporting_date).days
    if elapsed_days <= 0:
        raise ValueError("Reporting dates must be distinct and chronological.")
    return (math.log1p(current.value) - math.log1p(previous.value)) / elapsed_days


def _daily_log_rate_roundoff_bound(
    previous: NBRObservation,
    current: NBRObservation,
) -> float:
    """Estimate floating-point resolution of a daily log-rate calculation."""
    elapsed_days = (current.reporting_date - previous.reporting_date).days
    if elapsed_days <= 0:
        raise ValueError("Reporting dates must be distinct and chronological.")
    previous_log = math.log1p(previous.value)
    current_log = math.log1p(current.value)
    log_difference = current_log - previous_log
    return (
        math.ulp(previous_log)
        + math.ulp(current_log)
        + math.ulp(log_difference)
    ) / elapsed_days + math.ulp(log_difference / elapsed_days)


def _score_rate_deviation(
    observed_rate: float,
    center: float,
    mad: float,
    *,
    dispersion_roundoff_bound: float,
    historical_rates: Sequence[float],
) -> tuple[float | None, str]:
    """Score only when historical dispersion is nonzero and internally stable."""
    if mad == 0:
        return None, "zero"
    if mad <= dispersion_roundoff_bound:
        return None, "below_floating_point_resolution"
    if any(
        abs(rate - center) / (1.4826 * mad) >= ROBUST_SCORE_THRESHOLD
        for rate in historical_rates
    ):
        return None, "discordant_training_rates"
    return (observed_rate - center) / (1.4826 * mad), "resolved"


def _existing_change_rule(
    previous: NBRObservation,
    current: NBRObservation,
) -> bool:
    elapsed_days = (current.reporting_date - previous.reporting_date).days
    if elapsed_days <= 0 or elapsed_days > BASELINE_MAX_GAP_DAYS:
        return False
    if previous.value == 0:
        return current.value > 0
    relative_change = abs((current.value - previous.value) / previous.value * 100)
    return relative_change >= CHANGE_REVIEW_THRESHOLD_PERCENT


def _observation_evidence(observation: NBRObservation) -> dict[str, Any]:
    return {
        "reporting_date": observation.reporting_date.isoformat(),
        "collected_at": observation.collected_at,
        "value": observation.value,
        "run_id": observation.run_id,
        "filters": observation.filters,
    }


def _event_identity(
    page: str,
    metric_label: str,
    district: str,
    reporting_date: str,
    combo_key: str,
) -> tuple[str, str, str, str, str]:
    return (
        page,
        metric_label,
        district.casefold(),
        reporting_date,
        combo_key,
    )


def _evaluate_cross_sectionally(
    observations: Sequence[NBRObservation],
    table_documents: Sequence[Mapping[str, Any]],
    expected_districts: Sequence[str] = (),
    tentative_reconciliations: Mapping[
        tuple[str, str, str], Mapping[str, Any]
    ] | None = None,
) -> tuple[
    dict[str, Any],
    list[dict[str, Any]],
    set[tuple[str, str, str, str, str]],
]:
    """Compare districts only within the same page, metric, date, and combo."""
    tentative_reconciliations = tentative_reconciliations or {}
    grouped: dict[
        tuple[str, str, date, str], list[NBRObservation]
    ] = defaultdict(list)
    for observation in observations:
        grouped[(
            observation.page,
            observation.metric_label,
            observation.reporting_date,
            observation.combo_key,
        )].append(observation)

    expected_by_folded = {
        district.casefold(): district
        for district in expected_districts
    }
    scope_rows: dict[tuple[str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in table_documents:
        scope_rows[_identity(row)].append(row)

    candidates = []
    assessable_observations = 0
    assessable_groups = 0
    insufficient_groups = 0
    zero_mad_groups = 0
    incomplete_groups = 0
    sensitivity_flips = 0
    threshold_counts = Counter()
    scored_district_names = set()
    scored_series = set()
    assessable_observation_keys = set()

    for group_key, group in sorted(
        grouped.items(),
        key=lambda item: (
            item[0][0],
            item[0][1],
            item[0][2],
            item[0][3],
        ),
    ):
        page, metric_label, reporting_date, combo_key = group_key
        group.sort(key=lambda item: item.district.casefold())
        distinct_districts = {item.district.casefold() for item in group}
        if len(distinct_districts) != len(group):
            continue
        if len(group) < MIN_CROSS_SECTION_DISTRICTS:
            insufficient_groups += 1
            continue

        peer_values = [item.value for item in group]
        peer_median = statistics.median(peer_values)
        peer_mad = statistics.median(
            abs(value - peer_median) for value in peer_values
        )
        if peer_mad <= 0:
            zero_mad_groups += 1
            continue

        assessable_groups += 1
        assessable_observations += len(group)
        scored_district_names.update(item.district.casefold() for item in group)
        for item in group:
            assessable_observation_keys.add(_event_identity(
                item.page,
                item.metric_label,
                item.district,
                reporting_date.isoformat(),
                item.combo_key,
            ))
            scored_series.add((
                item.page,
                item.metric_label,
                item.district.casefold(),
                item.combo_key,
            ))

        scope_key = (page, reporting_date.isoformat(), combo_key)
        rows = scope_rows.get(scope_key, [])
        observed_named = set()
        unknown_rows = []
        unmatched_rows = []
        for row in rows:
            district = str(row.get("district") or "").strip()
            normalized = district.casefold()
            if (
                not district
                or normalized == "unknown"
                or row.get("district_known") is False
            ):
                unknown_rows.append(district or "<missing>")
            elif expected_by_folded and normalized not in expected_by_folded:
                unmatched_rows.append(district)
            else:
                observed_named.add(normalized)
        missing_districts = sorted(
            expected_by_folded[name]
            for name in set(expected_by_folded) - observed_named
        )
        coverage_qualifications = []
        if missing_districts:
            coverage_qualifications.append({
                "check": "geographic_coverage",
                "status": "tentative",
                "reason": "Expected districts are absent from this reporting/filter scope.",
                "missing_district_count": len(missing_districts),
                "missing_districts": missing_districts,
            })
        if unknown_rows:
            coverage_qualifications.append({
                "check": "geographic_coverage",
                "status": "tentative",
                "reason": "Unknown-location rows are excluded from peer comparisons.",
                "unknown_rows": unknown_rows,
            })
        if unmatched_rows:
            coverage_qualifications.append({
                "check": "geographic_coverage",
                "status": "tentative",
                "reason": "Unmatched location rows are excluded from peer comparisons.",
                "unmatched_rows": unmatched_rows,
            })
        if not expected_by_folded:
            coverage_qualifications.append({
                "check": "geographic_coverage",
                "status": "not_assessable",
                "reason": "No district reference was supplied for completeness checks.",
            })
        if coverage_qualifications:
            incomplete_groups += 1

        reconciliation = tentative_reconciliations.get(scope_key)
        quality_qualifications = list(coverage_qualifications)
        if reconciliation:
            quality_qualifications.append(dict(reconciliation))

        for item in group:
            score = 0.6744897501960817 * (item.value - peer_median) / peer_mad
            absolute_score = abs(score)
            for threshold in (3.0, CROSS_SECTION_ROBUST_Z_THRESHOLD, 4.0):
                if absolute_score >= threshold:
                    threshold_counts[threshold] += 1

            perturbed_alerts = []
            for multiplier in (0.99, 1.01):
                perturbed = item.value * multiplier
                perturbed_score = (
                    0.6744897501960817 * (perturbed - peer_median) / peer_mad
                )
                perturbed_alerts.append(
                    abs(perturbed_score) >= CROSS_SECTION_ROBUST_Z_THRESHOLD
                )
            current_alert = absolute_score >= CROSS_SECTION_ROBUST_Z_THRESHOLD
            if any(alert != current_alert for alert in perturbed_alerts):
                sensitivity_flips += 1

            if not current_alert:
                continue
            direction = "high" if score > 0 else "low"
            candidates.append({
                "method": "cross_sectional_modified_z",
                "page": page,
                "metric_label": metric_label,
                "district": item.district,
                "reporting_date": reporting_date.isoformat(),
                "collected_at": item.collected_at,
                "run_id": item.run_id,
                "combo_key": combo_key,
                "filters": item.filters,
                "observed_value": item.value,
                "peer_median": peer_median,
                "peer_mad": peer_mad,
                "robust_score": score,
                "absolute_robust_score": absolute_score,
                "threshold": CROSS_SECTION_ROBUST_Z_THRESHOLD,
                "direction": direction,
                "reason": (
                    f"{direction.title()} relative to {len(group)} eligible districts "
                    "in the same page, metric, reporting date, and filter scope."
                ),
                "comparison_district_count": len(group),
                "expected_district_count": len(expected_by_folded) or None,
                "observed_named_district_count": len(observed_named),
                "missing_district_count": len(missing_districts),
                "missing_districts": missing_districts,
                "unknown_rows": unknown_rows,
                "unmatched_rows": unmatched_rows,
                "sensitivity_1pct": {
                    "lower_value_alert": perturbed_alerts[0],
                    "higher_value_alert": perturbed_alerts[1],
                    "classification_changes_with_1pct_perturbation": any(
                        alert != current_alert for alert in perturbed_alerts
                    ),
                },
                "quality_qualifications": quality_qualifications,
                "interpretation": (
                    "Experimental peer outlier only; not evidence of a service gap."
                ),
            })

    candidates.sort(
        key=lambda candidate: (
            -candidate["absolute_robust_score"],
            candidate["page"],
            candidate["metric_label"],
            candidate["reporting_date"],
            candidate["combo_key"],
            candidate["district"].casefold(),
        )
    )
    total_observations = sum(len(group) for group in grouped.values())
    summary = {
        "method": "cross-sectional modified robust z-score",
        "status": "experimental_unsupervised_peer_comparison",
        "comparison_unit": [
            "page",
            "metric_label",
            "snapshot_date",
            "canonical combo_key",
        ],
        "minimum_peer_districts": MIN_CROSS_SECTION_DISTRICTS,
        "default_threshold": CROSS_SECTION_ROBUST_Z_THRESHOLD,
        "score_definition": (
            "0.67449 * (district value - peer median) / peer MAD; direction retained."
        ),
        "eligible_observations_in_groups": total_observations,
        "assessable_observations": assessable_observations,
        "assessable_groups": assessable_groups,
        "groups_too_small": insufficient_groups,
        "groups_with_zero_mad": zero_mad_groups,
        "groups_with_coverage_qualifications": incomplete_groups,
        "distinct_districts_in_assessable_groups": len(scored_district_names),
        "comparable_temporal_series_in_assessable_groups": len(scored_series),
        "candidate_count": len(candidates),
        "candidate_rate_of_assessable_observations": (
            len(candidates) / assessable_observations
            if assessable_observations else None
        ),
        "candidate_count_by_threshold": {
            str(threshold): threshold_counts[threshold]
            for threshold in (3.0, CROSS_SECTION_ROBUST_Z_THRESHOLD, 4.0)
        },
        "observations_changing_flag_under_plus_minus_1pct_perturbation": sensitivity_flips,
        "ranked_candidates": candidates,
        "limitations": [
            "Peer outliers may reflect genuine population or service-scale differences rather than errors.",
            "The detector is univariate within each exact source scope and does not infer a service gap.",
            "Scopes with fewer than the minimum peer count or zero MAD are not scored.",
            "Incomplete district coverage is qualified; missing and unknown locations are never imputed.",
            "No adjudicated labels exist to measure whether these candidates are useful.",
        ],
    }
    return summary, candidates, assessable_observation_keys


def evaluate_cross_sectionally(
    observations: Sequence[NBRObservation],
    table_documents: Sequence[Mapping[str, Any]],
    expected_districts: Sequence[str] = (),
    tentative_reconciliations: Mapping[
        tuple[str, str, str], Mapping[str, Any]
    ] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Return a JSON-serializable peer summary and its flagged observations."""
    summary, candidates, _ = _evaluate_cross_sectionally(
        observations,
        table_documents,
        expected_districts,
        tentative_reconciliations,
    )
    return summary, candidates


def _compare_cross_section_to_temporal(
    temporal_cases: Sequence[Mapping[str, Any]],
    cross_section_candidates: Sequence[Mapping[str, Any]],
    cross_section_assessable_keys: set[tuple[str, str, str, str, str]],
) -> dict[str, Any]:
    cross_candidates = {
        _event_identity(
            candidate["page"],
            candidate["metric_label"],
            candidate["district"],
            candidate["reporting_date"],
            candidate["combo_key"],
        )
        for candidate in cross_section_candidates
    }
    comparison_methods = {
        "temporal_rate_mad": ("model_status", "model_alert"),
        "temporal_level_mad": ("level_baseline_status", "level_baseline_alert"),
        "existing_50pct_8day_rule": (None, "existing_50pct_8day_rule_alert"),
    }
    comparisons = {}
    for method, (status_field, alert_field) in comparison_methods.items():
        common_keys = set()
        temporal_alerts = set()
        for case in temporal_cases:
            if status_field and case[status_field] != "scored":
                continue
            target = case["target"]
            identity = _event_identity(
                case["page"],
                case["metric_label"],
                case["district"],
                target["reporting_date"],
                case["combo_key"],
            )
            if identity not in cross_section_assessable_keys:
                continue
            common_keys.add(identity)
            if case[alert_field]:
                temporal_alerts.add(identity)
        cross_alerts = cross_candidates & common_keys
        both = cross_alerts & temporal_alerts
        comparisons[method] = {
            "common_assessable_cases": len(common_keys),
            "cross_sectional_candidates": len(cross_alerts),
            "temporal_candidates": len(temporal_alerts),
            "flagged_by_both": len(both),
            "cross_sectional_only": len(cross_alerts - temporal_alerts),
            "temporal_only": len(temporal_alerts - cross_alerts),
            "neither_flagged": len(common_keys - cross_alerts - temporal_alerts),
        }
    return {
        "comparison_unit": [
            "page",
            "metric_label",
            "district",
            "reporting_date",
            "canonical combo_key",
        ],
        "scope": (
            "Only observations assessable by cross-sectional peer comparison and "
            "the named temporal comparator are counted."
        ),
        "interpretation": (
            "Agreement is overlap between experimental flags, not evidence that "
            "either method is correct."
        ),
        "methods": comparisons,
    }


def evaluate_chronologically(
    observations: Sequence[NBRObservation],
    tentative_reconciliations: Mapping[
        tuple[str, str, str], Mapping[str, Any]
    ] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Walk forward; each test point is scored from earlier points only."""
    tentative_reconciliations = tentative_reconciliations or {}
    grouped: dict[tuple[str, str, str, str], list[NBRObservation]] = defaultdict(list)
    for observation in observations:
        grouped[_series_key(observation)].append(observation)

    cases: list[dict[str, Any]] = []
    insufficient_series = 0
    for series_key, series in sorted(grouped.items()):
        series.sort(key=lambda item: item.reporting_date)
        series_cases = 0
        for target_index in range(MIN_TRAINING_RATES + 1, len(series)):
            history = series[:target_index]
            previous = history[-1]
            target = series[target_index]
            training_rates = [
                _daily_log_rate(left, right)
                for left, right in zip(history, history[1:])
            ]
            if len(training_rates) < MIN_TRAINING_RATES:
                continue

            center = statistics.median(training_rates)
            mad = statistics.median(abs(rate - center) for rate in training_rates)
            observed_rate = _daily_log_rate(previous, target)
            rate_roundoff_bounds = [
                _daily_log_rate_roundoff_bound(left, right)
                for left, right in zip(history, history[1:])
            ]
            dispersion_roundoff_bound = (
                2 * max(rate_roundoff_bounds, default=0.0)
            )
            signed_model_score, dispersion_status = _score_rate_deviation(
                observed_rate,
                center,
                mad,
                dispersion_roundoff_bound=dispersion_roundoff_bound,
                historical_rates=training_rates,
            )
            model_assessable = signed_model_score is not None
            model_score = (
                abs(signed_model_score)
                if signed_model_score is not None else None
            )
            deviation_direction = (
                "above_historical_median"
                if observed_rate > center
                else "below_historical_median"
                if observed_rate < center
                else "at_historical_median"
            )
            observed_change_direction = (
                "increase" if observed_rate > 0
                else "decrease" if observed_rate < 0
                else "unchanged"
            )
            model_alert = (
                model_score is not None
                and model_score >= ROBUST_SCORE_THRESHOLD
            )
            level_center = statistics.median(item.value for item in history)
            level_mad = statistics.median(
                abs(item.value - level_center) for item in history
            )
            level_baseline_assessable = level_mad > 0
            level_baseline_score = (
                abs(target.value - level_center) / (1.4826 * level_mad)
                if level_baseline_assessable else None
            )
            level_baseline_alert = (
                level_baseline_score is not None
                and level_baseline_score >= ROBUST_SCORE_THRESHOLD
            )
            candidate_gap_days = (target.reporting_date - previous.reporting_date).days
            rate_perturbation_scores = None
            if model_assessable:
                previous_log_value = math.log1p(previous.value)
                rate_perturbation_scores = {
                    "lower_value_score": abs(
                        (
                            math.log1p(target.value * 0.99) - previous_log_value
                        ) / candidate_gap_days - center
                    ) / (1.4826 * mad),
                    "higher_value_score": abs(
                        (
                            math.log1p(target.value * 1.01) - previous_log_value
                        ) / candidate_gap_days - center
                    ) / (1.4826 * mad),
                }
            level_perturbation_scores = None
            if level_baseline_assessable:
                level_perturbation_scores = {
                    "lower_value_score": abs(
                        target.value * 0.99 - level_center
                    ) / (1.4826 * level_mad),
                    "higher_value_score": abs(
                        target.value * 1.01 - level_center
                    ) / (1.4826 * level_mad),
                }
            rate_perturbed_alerts = (
                {
                    direction: score >= ROBUST_SCORE_THRESHOLD
                    for direction, score in rate_perturbation_scores.items()
                }
                if rate_perturbation_scores is not None else None
            )
            level_perturbed_alerts = (
                {
                    direction: score >= ROBUST_SCORE_THRESHOLD
                    for direction, score in level_perturbation_scores.items()
                }
                if level_perturbation_scores is not None else None
            )
            quality_keys = {
                (item.page, item.reporting_date.isoformat(), item.combo_key)
                for item in (*history, target)
            }
            quality_qualifications = [
                dict(tentative_reconciliations[key])
                for key in sorted(quality_keys)
                if key in tentative_reconciliations
            ]
            case = {
                "page": series_key[0],
                "metric_label": series_key[1],
                "district": target.district,
                "combo_key": series_key[3],
                "target": _observation_evidence(target),
                "previous": _observation_evidence(previous),
                "historical_training_observations": [
                    _observation_evidence(item) for item in history
                ],
                "training_rate_count": len(training_rates),
                "training_rate_median_per_day": center,
                "training_rate_mad_per_day": mad,
                "observed_rate_per_day": observed_rate,
                "observed_change_direction": observed_change_direction,
                "deviation_direction": deviation_direction,
                "model_signed_robust_score": signed_model_score,
                "model_dispersion_status": dispersion_status,
                "training_rate_dispersion_roundoff_bound": (
                    dispersion_roundoff_bound
                ),
                "elapsed_days": candidate_gap_days,
                "existing_50pct_8day_rule_alert": _existing_change_rule(previous, target),
                "level_baseline_status": (
                    "scored" if level_baseline_assessable
                    else "not_assessable_zero_training_mad"
                ),
                "level_baseline_median": level_center,
                "level_baseline_mad": level_mad,
                "level_baseline_robust_score": level_baseline_score,
                "level_baseline_threshold": ROBUST_SCORE_THRESHOLD,
                "level_baseline_alert": level_baseline_alert,
                "model_status": (
                    "scored"
                    if model_assessable
                    else "not_assessable_zero_training_mad"
                    if dispersion_status == "zero"
                    else "not_assessable_discordant_training_rates"
                    if dispersion_status == "discordant_training_rates"
                    else "not_assessable_below_floating_point_resolution"
                ),
                "model_robust_score": model_score,
                "model_threshold": ROBUST_SCORE_THRESHOLD,
                "model_alert": model_alert,
                "model_sensitivity_plus_minus_1pct": {
                    "scores": rate_perturbation_scores,
                    "alerts": rate_perturbed_alerts,
                    "classification_changes": (
                        any(
                            alert != model_alert
                            for alert in rate_perturbed_alerts.values()
                        )
                        if rate_perturbed_alerts is not None else None
                    ),
                },
                "level_baseline_sensitivity_plus_minus_1pct": {
                    "scores": level_perturbation_scores,
                    "alerts": level_perturbed_alerts,
                    "classification_changes": (
                        any(
                            alert != level_baseline_alert
                            for alert in level_perturbed_alerts.values()
                        )
                        if level_perturbed_alerts is not None else None
                    ),
                },
                "quality_qualifications": quality_qualifications,
            }
            cases.append(case)
            series_cases += 1
        if series_cases == 0:
            insufficient_series += 1

    assessable = [case for case in cases if case["model_status"] == "scored"]
    model_abstentions_zero_mad = sum(
        case["model_dispersion_status"] == "zero" for case in cases
    )
    model_abstentions_roundoff = sum(
        case["model_dispersion_status"] == "below_floating_point_resolution"
        for case in cases
    )
    model_abstentions_discordant = sum(
        case["model_dispersion_status"] == "discordant_training_rates"
        for case in cases
    )
    model_scores = sorted(
        case["model_robust_score"] for case in assessable
    )
    level_assessable = [
        case for case in cases if case["level_baseline_status"] == "scored"
    ]
    directly_comparable = [
        case for case in cases
        if case["model_status"] == "scored"
        and case["level_baseline_status"] == "scored"
    ]
    baseline_alerts = sum(case["existing_50pct_8day_rule_alert"] for case in cases)
    baseline_alerts_assessable = sum(
        case["existing_50pct_8day_rule_alert"] for case in assessable
    )
    baseline_alerts_unassessed = sum(
        case["existing_50pct_8day_rule_alert"]
        for case in cases
        if case["model_status"] != "scored"
    )
    model_alerts = sum(case["model_alert"] for case in assessable)
    model_alert_cases = [case for case in assessable if case["model_alert"]]
    level_alert_cases = [
        case for case in level_assessable if case["level_baseline_alert"]
    ]
    temporal_threshold_counts = {
        str(threshold): sum(
            case["model_robust_score"] is not None
            and case["model_robust_score"] >= threshold
            for case in assessable
        )
        for threshold in TEMPORAL_SCORE_THRESHOLDS
    }
    level_threshold_counts = {
        str(threshold): sum(
            case["level_baseline_robust_score"] is not None
            and case["level_baseline_robust_score"] >= threshold
            for case in level_assessable
        )
        for threshold in LEVEL_SCORE_THRESHOLDS
    }
    overlap = sum(
        case["model_alert"] and case["existing_50pct_8day_rule_alert"]
        for case in assessable
    )
    baseline_only = sum(
        case["existing_50pct_8day_rule_alert"] and not case["model_alert"]
        for case in assessable
    )
    model_only = sum(
        case["model_alert"] and not case["existing_50pct_8day_rule_alert"]
        for case in assessable
    )
    level_baseline_alerts = sum(
        case["level_baseline_alert"] for case in level_assessable
    )
    model_vs_level_overlap = sum(
        case["model_alert"] and case["level_baseline_alert"]
        for case in directly_comparable
    )
    model_only_vs_level = sum(
        case["model_alert"] and not case["level_baseline_alert"]
        for case in directly_comparable
    )
    level_only_vs_model = sum(
        case["level_baseline_alert"] and not case["model_alert"]
        for case in directly_comparable
    )
    by_page = {}
    for page in sorted({case["page"] for case in cases}):
        page_cases = [case for case in cases if case["page"] == page]
        page_assessable = [
            case for case in page_cases if case["model_status"] == "scored"
        ]
        page_level_assessable = [
            case for case in page_cases
            if case["level_baseline_status"] == "scored"
        ]
        page_comparable = [
            case for case in page_cases
            if case["model_status"] == "scored"
            and case["level_baseline_status"] == "scored"
        ]
        page_model_alerts = sum(case["model_alert"] for case in page_assessable)
        page_level_alerts = sum(
            case["level_baseline_alert"] for case in page_level_assessable
        )
        by_page[page] = {
            "walk_forward_test_cases": len(page_cases),
            "model_assessable_cases": len(page_assessable),
            "model_abstentions_zero_mad": sum(
                case["model_dispersion_status"] == "zero"
                for case in page_cases
            ),
            "model_abstentions_below_floating_point_resolution": sum(
                case["model_dispersion_status"]
                == "below_floating_point_resolution"
                for case in page_cases
            ),
            "model_abstentions_discordant_training_rates": sum(
                case["model_dispersion_status"] == "discordant_training_rates"
                for case in page_cases
            ),
            "level_baseline_assessable_cases": len(page_level_assessable),
            "level_baseline_abstentions_zero_mad": (
                len(page_cases) - len(page_level_assessable)
            ),
            "level_baseline_alerts": page_level_alerts,
            "model_level_baseline_overlap": sum(
                case["model_alert"] and case["level_baseline_alert"]
                for case in page_comparable
            ),
            "model_only_vs_level_baseline": sum(
                case["model_alert"] and not case["level_baseline_alert"]
                for case in page_comparable
            ),
            "level_baseline_only": sum(
                case["level_baseline_alert"] and not case["model_alert"]
                for case in page_comparable
            ),
            "existing_rule_alerts": sum(
                case["existing_50pct_8day_rule_alert"] for case in page_cases
            ),
            "model_alerts": page_model_alerts,
            "model_alert_rate_on_assessable_cases": (
                page_model_alerts / len(page_assessable)
                if page_assessable else None
            ),
            "test_reporting_dates": sorted({
                case["target"]["reporting_date"] for case in page_cases
            }),
        }
    summary = {
        "comparable_series": len(grouped),
        "series_without_a_walk_forward_test": insufficient_series,
        "walk_forward_test_cases": len(cases),
        "model_assessable_cases": len(assessable),
        "model_abstentions_zero_mad": model_abstentions_zero_mad,
        "model_abstentions_below_floating_point_resolution": (
            model_abstentions_roundoff
        ),
        "model_abstentions_discordant_training_rates": (
            model_abstentions_discordant
        ),
        "model_abstentions_total": (
            model_abstentions_zero_mad
            + model_abstentions_roundoff
            + model_abstentions_discordant
        ),
        "level_baseline_assessable_cases": len(level_assessable),
        "level_baseline_abstentions_zero_mad": len(cases) - len(level_assessable),
        "model_and_level_baseline_comparable_cases": len(directly_comparable),
        "level_baseline_alerts": level_baseline_alerts,
        "model_level_baseline_overlap": model_vs_level_overlap,
        "model_only_vs_level_baseline": model_only_vs_level,
        "level_baseline_only": level_only_vs_model,
        "existing_rule_alerts_on_test_cases": baseline_alerts,
        "existing_rule_alerts_on_model_assessable_cases": baseline_alerts_assessable,
        "existing_rule_alerts_where_model_abstained": baseline_alerts_unassessed,
        "model_alerts": model_alerts,
        "model_alerts_by_deviation_direction": {
            "above_historical_median": sum(
                case["deviation_direction"] == "above_historical_median"
                for case in model_alert_cases
            ),
            "below_historical_median": sum(
                case["deviation_direction"] == "below_historical_median"
                for case in model_alert_cases
            ),
        },
        "model_alerts_by_observed_change_direction": {
            direction: sum(
                case["observed_change_direction"] == direction
                for case in model_alert_cases
            )
            for direction in ("increase", "decrease", "unchanged")
        },
        "model_robust_score_distribution": {
            "minimum": model_scores[0] if model_scores else None,
            "median": statistics.median(model_scores) if model_scores else None,
            "p90": (
                model_scores[math.ceil(0.90 * len(model_scores)) - 1]
                if model_scores else None
            ),
            "p95": (
                model_scores[math.ceil(0.95 * len(model_scores)) - 1]
                if model_scores else None
            ),
            "p99": (
                model_scores[math.ceil(0.99 * len(model_scores)) - 1]
                if model_scores else None
            ),
            "maximum": model_scores[-1] if model_scores else None,
        },
        "model_alert_distinct_district_names": len({
            case["district"].casefold() for case in model_alert_cases
        }),
        "model_alert_distinct_page_district_pairs": len({
            (case["page"], case["district"].casefold())
            for case in model_alert_cases
        }),
        "model_alert_distinct_series": len({
            (
                case["page"],
                case["metric_label"],
                case["district"].casefold(),
                case["combo_key"],
            )
            for case in model_alert_cases
        }),
        "level_baseline_alerts": level_baseline_alerts,
        "level_baseline_alert_distinct_district_names": len({
            case["district"].casefold() for case in level_alert_cases
        }),
        "level_baseline_alert_distinct_series": len({
            (
                case["page"],
                case["metric_label"],
                case["district"].casefold(),
                case["combo_key"],
            )
            for case in level_alert_cases
        }),
        "model_alert_rate_on_assessable_cases": (
            model_alerts / len(assessable) if assessable else None
        ),
        "model_alert_count_by_threshold": temporal_threshold_counts,
        "model_cases_changing_classification_under_plus_minus_1pct": sum(
            bool(case["model_sensitivity_plus_minus_1pct"]["classification_changes"])
            for case in assessable
        ),
        "level_baseline_alert_count_by_threshold": level_threshold_counts,
        "level_baseline_cases_changing_classification_under_plus_minus_1pct": sum(
            bool(case["level_baseline_sensitivity_plus_minus_1pct"]["classification_changes"])
            for case in level_assessable
        ),
        "alerts_detected_by_both": overlap,
        "existing_rule_only_alerts": baseline_only,
        "model_only_alerts": model_only,
        "by_page": by_page,
        "labeled_outcomes_available": False,
        "precision_recall_or_false_alarm_rate": None,
    }
    return summary, cases


def _historical_filter_scope_changes(
    runs: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    by_page_date: dict[str, dict[str, dict[str, set[str]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(set))
    )
    for run in runs:
        filters = run.get("filters_requested")
        if not isinstance(filters, Mapping):
            filters = run.get("filters")
        if not isinstance(filters, Mapping):
            continue
        page = str(run.get("page", ""))
        reporting_date = str(run.get("snapshot_date", ""))
        for label, value in filters.items():
            by_page_date[page][reporting_date][str(label)].add(str(value))

    changes = []
    for page, date_filters in sorted(by_page_date.items()):
        dates = sorted(date_filters)
        for previous_date, current_date in zip(dates, dates[1:]):
            previous = date_filters[previous_date]
            current = date_filters[current_date]
            changed_labels = sorted(
                label for label in set(previous) | set(current)
                if previous.get(label, set()) != current.get(label, set())
            )
            if not changed_labels:
                continue
            changes.append({
                "page": page,
                "previous_reporting_date": previous_date,
                "reporting_date": current_date,
                "changes": {
                    label: {
                        "previous_values": sorted(previous.get(label, set())),
                        "current_values": sorted(current.get(label, set())),
                    }
                    for label in changed_labels
                },
                "interpretation": (
                    "Filter scopes differ across reporting periods and are not "
                    "combined by the experiment."
                ),
            })
    return changes


def _ranked_review_queues(
    temporal_cases: Sequence[Mapping[str, Any]],
    cross_section_candidates: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    method_candidates: dict[str, list[dict[str, Any]]] = {
        "cross_sectional_modified_z": [
            dict(candidate) for candidate in cross_section_candidates
        ],
        "temporal_rate_mad": [],
        "temporal_level_mad": [],
        "existing_50pct_8day_rule": [],
    }
    for case in temporal_cases:
        common = {
            "page": case["page"],
            "metric_label": case["metric_label"],
            "district": case["district"],
            "reporting_date": case["target"]["reporting_date"],
            "collected_at": case["target"]["collected_at"],
            "run_id": case["target"]["run_id"],
            "combo_key": case["combo_key"],
            "filters": case["target"]["filters"],
            "observed_value": case["target"]["value"],
            "previous": case["previous"],
            "historical_training_observations": case[
                "historical_training_observations"
            ],
            "quality_qualifications": case["quality_qualifications"],
            "model_version": case.get("model_version", MODEL_VERSION),
            "evidence_assessment": case.get("evidence_assessment", {}),
            "assessment_timestamp": case.get("assessment_timestamp", ""),
        }
        if case["model_alert"]:
            method_candidates["temporal_rate_mad"].append({
                **common,
                "score": case["model_robust_score"],
                "signed_score": case["model_signed_robust_score"],
                "direction": case["deviation_direction"],
                "observed_change_direction": case[
                    "observed_change_direction"
                ],
                "threshold": case["model_threshold"],
                "baseline_median_daily_rate": case[
                    "training_rate_median_per_day"
                ],
                "baseline_mad_daily_rate": case["training_rate_mad_per_day"],
                "elapsed_days": case["elapsed_days"],
                "sensitivity_plus_minus_1pct": case[
                    "model_sensitivity_plus_minus_1pct"
                ],
                "reason": (
                    "Observed daily log-change rate is unusual relative to this "
                    "series' earlier reporting periods."
                ),
            })
        if case["level_baseline_alert"]:
            method_candidates["temporal_level_mad"].append({
                **common,
                "score": case["level_baseline_robust_score"],
                "threshold": case["level_baseline_threshold"],
                "baseline_median": case["level_baseline_median"],
                "baseline_mad": case["level_baseline_mad"],
                "sensitivity_plus_minus_1pct": case[
                    "level_baseline_sensitivity_plus_minus_1pct"
                ],
                "reason": (
                    "Observed metric level is unusual relative to this series' "
                    "earlier reporting periods."
                ),
            })
        if case["existing_50pct_8day_rule_alert"]:
            relative_change = (
                None if case["previous"]["value"] == 0
                else abs(
                    (
                        case["target"]["value"] - case["previous"]["value"]
                    ) / case["previous"]["value"] * 100
                )
            )
            method_candidates["existing_50pct_8day_rule"].append({
                **common,
                "score": relative_change,
                "threshold": CHANGE_REVIEW_THRESHOLD_PERCENT,
                "elapsed_days": case["elapsed_days"],
                "reason": (
                    "Existing rule: at least 50% relative change within eight "
                    "reporting days."
                ),
            })

    queues = {}
    for method, candidates in method_candidates.items():
        if method == "cross_sectional_modified_z":
            candidates.sort(
                key=lambda candidate: -candidate["absolute_robust_score"]
            )
            score_key = "absolute_robust_score"
        else:
            candidates.sort(key=lambda candidate: -(candidate["score"] or 0))
            score_key = "score"
        shown = candidates[:REVIEW_QUEUE_LIMIT_PER_METHOD]
        for rank, candidate in enumerate(shown, start=1):
            candidate["method_specific_rank"] = rank
        queues[method] = {
            "candidate_count": len(candidates),
            "shown_count": len(shown),
            "truncated": len(candidates) > len(shown),
            "ranked_by": score_key,
            "candidates": shown,
        }
    return {
        "ranking_policy": (
            "Ranks are method-specific. Scores from different methods are not "
            "combined or compared as a common priority scale."
        ),
        "human_disposition_policy": (
            "No analyst labels are fabricated or persisted. Record reviewed "
            "candidate ID, reviewer, disposition, evidence, and review date in a "
            "separate future review log; do not use model output as its own label."
        ),
        "methods": queues,
    }


def build_experiment_report(
    runs: Sequence[Mapping[str, Any]],
    table_documents: Sequence[Mapping[str, Any]],
    kpi_documents: Sequence[Mapping[str, Any]] = (),
    expected_districts: Sequence[str] = (),
    *,
    assessment_timestamp: datetime | None = None,
    data_health_report: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    observations, excluded_rows, excluded_values = prepare_observations(
        runs,
        table_documents,
    )
    tentative_reconciliations = _tentative_reconciliation_qualifications(
        kpi_documents,
        table_documents,
    )
    evaluation, cases = evaluate_chronologically(
        observations,
        tentative_reconciliations,
    )
    (
        cross_section,
        cross_section_candidates,
        cross_section_assessable_keys,
    ) = _evaluate_cross_sectionally(
        observations,
        table_documents,
        expected_districts,
        tentative_reconciliations,
    )
    method_comparison = _compare_cross_section_to_temporal(
        cases,
        cross_section_candidates,
        cross_section_assessable_keys,
    )
    cross_section["tentative_reconciliation_scope_count"] = len(
        tentative_reconciliations
    )
    cross_section["groups_with_reconciliation_qualifications"] = sum(
        1
        for page, reporting_date, combo_key in tentative_reconciliations
        if any(
            item.page == page
            and item.reporting_date.isoformat() == reporting_date
            and item.combo_key == combo_key
            for item in observations
        )
    )
    attach_candidate_evidence(cases, cross_section_candidates)
    series_dates: dict[tuple[str, str, str, str], set[date]] = defaultdict(set)
    for item in observations:
        series_dates[_series_key(item)].add(item.reporting_date)
    series_period_counts = Counter(len(dates) for dates in series_dates.values())
    reporting_dates = sorted({
        item.reporting_date.isoformat() for item in observations
    })
    pages = sorted({item.page for item in observations})
    evidence_assessment = assess_evidence(
        observations=observations,
        runs=runs,
        table_documents=table_documents,
        expected_districts=expected_districts,
        excluded_rows=excluded_rows,
        excluded_values=excluded_values,
        temporal_cases=cases,
        cross_sectional_summary=cross_section,
        cross_sectional_candidates=cross_section_candidates,
        health_report=data_health_report,
        assessed_at=assessment_timestamp,
    )
    for candidate in cross_section_candidates:
        candidate["assessment_timestamp"] = evidence_assessment[
            "assessment_timestamp"
        ]
    for case in cases:
        case["assessment_timestamp"] = evidence_assessment[
            "assessment_timestamp"
        ]
    review_queues = _ranked_review_queues(cases, cross_section_candidates)
    assessment_id = (
        f"{MODEL_VERSION}:{evidence_assessment['assessment_timestamp']}:"
        f"{evidence_assessment['eligible_population']['eligible_observations_sha256'][:12]}"
    )
    evidence_assessment["assessment_id"] = assessment_id
    return {
        "experiment": {
            "name": "NBR cross-sectional and temporal anomaly experiments",
            "status": "experimental_insufficient_labeled_history",
            "model_version": MODEL_VERSION,
            "source_git_commit": evidence_assessment["source_git_commit"],
            "source_worktree_dirty": evidence_assessment[
                "source_worktree_dirty"
            ],
            "assessment_id": assessment_id,
            "assessment_timestamp": evidence_assessment["assessment_timestamp"],
            "learning_objective": (
                "Identify explainable unusual district values within exact peer scopes "
                "and unusual changes within the same district-level series."
            ),
            "source": "NBR administrative observations only",
            "reporting_date_field": "snapshot_date",
            "collection_timestamp_field": "collected_at",
            "candidate": {
                "method": "median and median absolute deviation of prior daily log(1 + value) changes",
                "minimum_prior_rates": MIN_TRAINING_RATES,
                "robust_score_threshold": ROBUST_SCORE_THRESHOLD,
                "score_interpretation": (
                    "model_robust_score is the nonnegative deviation magnitude; "
                    "model_signed_robust_score signs the deviation from the "
                    "historical median daily rate."
                ),
                "dispersion_policy": (
                    "Abstain at zero MAD or when MAD is no larger than twice the "
                    "largest propagated floating-point resolution bound among prior "
                    "daily log rates. Also abstain if any prior rate itself meets the "
                    "existing 3.0 robust-score threshold relative to the fitted "
                    "history, since the historical scale is internally discordant. "
                    "No domain-unit scale floor is applied because source measurement "
                    "precision is not documented."
                ),
                "threshold_is_recalibrated": False,
            },
            "cross_sectional_candidate": {
                "method": "modified median/MAD z-score within exact page/metric/date/filter scope",
                "minimum_peer_districts": MIN_CROSS_SECTION_DISTRICTS,
                "robust_score_threshold": CROSS_SECTION_ROBUST_Z_THRESHOLD,
                "threshold_is_recalibrated": False,
            },
            "comparison_baseline": {
                "method": "existing 50% relative-change review rule within 8 reporting days",
                "threshold_percent": CHANGE_REVIEW_THRESHOLD_PERCENT,
                "maximum_gap_days": BASELINE_MAX_GAP_DAYS,
            },
            "fit_policy": (
                "Walk-forward evaluation. The test observation and future observations are "
                "never used to estimate its historical center or MAD."
            ),
            "adaptation_policy": (
                "Rerunning the command reloads current read-only NBR history and refits "
                "each score from eligible earlier observations. No model state or labels "
                "are written back to MongoDB."
            ),
        },
        "data": {
            "source_run_count": len(runs),
            "source_table_document_count": len(table_documents),
            "reporting_dates": reporting_dates,
            "page_count": len(pages),
            "pages": pages,
            "expected_district_count": len(expected_districts) or None,
            "eligible_observation_count": len(observations),
            "comparable_series_count": len(series_dates),
            "series_by_independent_reporting_period_count": {
                str(period_count): count
                for period_count, count in sorted(series_period_counts.items())
            },
            "excluded_table_rows_by_reason": excluded_rows,
            "excluded_metric_values_by_reason": excluded_values,
            "tentative_reconciliation_scope_count": len(tentative_reconciliations),
            "historical_filter_scope_changes": _historical_filter_scope_changes(runs),
            "incompatible_filter_scopes_kept_separate": True,
            "quality_policy": [
                "One matching collection run per page/reporting-date/canonical-filter key.",
                "Collection run status must be complete.",
                "Repeated-content snapshots are excluded.",
                "Unknown or unverified districts are excluded, never mapped to zero.",
                "Missing, non-numeric, non-finite, and negative metric values are excluded.",
                "Reporting date and collection timestamp are preserved separately.",
            ],
        },
        "evaluation": evaluation,
        "evidence_assessment": evidence_assessment,
        "cross_sectional_evaluation": cross_section,
        "cross_sectional_temporal_comparison": method_comparison,
        "cases": cases,
        "ranked_review_queues": review_queues,
        "limitations": [
            "Only five distinct reporting dates exist and the intervals are irregular.",
            "At most one walk-forward target per comparable series meets the minimum history.",
            "No adjudicated anomaly labels exist; alert agreement is not accuracy and false-alarm rates cannot be estimated.",
            "Three prior change rates provide only a weak descriptive reference, not a reliable learned normal pattern.",
            "Positive but numerically resolvable small MAD values can yield very large standardized scores. The source does not document metric units or measurement precision, so the experiment cannot justify a practical scale floor; such alerts remain limited-evidence review signals.",
            "The floating-point-resolution abstention is a calculation-precision safeguard, not a test of source measurement accuracy.",
            "A rate baseline is also unassessable when one of its own prior rates crosses the fixed 3.0 robust-score threshold; this avoids scoring a new point against a scale made artificially narrow by internally discordant history.",
            "A repeated-content flag means unchanged content across distinct reporting dates; it is excluded from fitting, not treated as an error label.",
            "The detector does not establish why a change occurred or whether it indicates a financial-service gap.",
            "Evidence sufficiency is task-specific and is not statistical confidence, detector accuracy, or a claim that a candidate is correct.",
        ],
        "future_collection_plan": {
            "minimum_for_reassessment": (
                "Collect at least 12 consecutive, quality-suitable weekly reporting periods "
                "for the same page/metric/district/filter series, followed by at least 4 "
                "chronological holdout periods."
            ),
            "retain": [
                "snapshot_date, collected_at, run_id, canonical combo_key, actual/requested filters, metric label, district, value",
                "collection status, repeated-snapshot flag and prior matching date",
                "unknown/unmatched geography and missing observations as explicit states",
            ],
            "human_review": (
                "Record analyst dispositions separately from model output; do not treat "
                "model alerts as labels or update thresholds automatically."
            ),
        },
    }


def _tentative_reconciliation_qualifications(
    kpi_documents: Sequence[Mapping[str, Any]],
    table_documents: Sequence[Mapping[str, Any]],
) -> dict[tuple[str, str, str], dict[str, Any]]:
    if not kpi_documents:
        return {}
    from src.data_sources.mongodb_data_health import _reconciliation_findings

    qualifications = {}
    for finding in _reconciliation_findings(
        list(kpi_documents),
        list(table_documents),
    ):
        if finding.status != "tentative":
            continue
        evidence = finding.evidence
        key = (
            str(evidence.get("page", "")),
            str(evidence.get("reporting_date", "")),
            str(evidence.get("combo_key", "")),
        )
        qualifications[key] = {
            "check": finding.check,
            "status": finding.status,
            "message": finding.message,
            "table_sum": evidence.get("table_sum"),
            "kpi_value": evidence.get("kpi_value"),
            "difference": evidence.get("difference"),
        }
    return qualifications


def load_mongodb_history() -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    """Load only the existing run and district-table records, without writes."""
    try:
        from dotenv import load_dotenv
        from pymongo import MongoClient
    except ImportError as exc:
        raise RuntimeError(
            "Install the project requirements (python-dotenv and pymongo) to load NBR history."
        ) from exc

    load_dotenv(PROJECT_ROOT / ".env")
    uri = os.getenv("MONGODB_URI") or os.getenv("MONGO_URI")
    if not uri:
        raise RuntimeError("Set MONGODB_URI or MONGO_URI in the project .env file.")
    client = MongoClient(uri, serverSelectionTimeoutMS=15000)
    try:
        client.admin.command("ping")
        database = client[DATABASE_NAME]
        runs = list(database[RUN_COLLECTION].find(
            {},
            {
                "_id": 0,
                "page": 1,
                "snapshot_date": 1,
                "collected_at": 1,
                "run_id": 1,
                "combo_key": 1,
                "filters_key": 1,
                "status": 1,
                "repeated_snapshot_warning": 1,
                "filters": 1,
                "filters_requested": 1,
                "table_status": 1,
                "table_rows": 1,
                "previous_matching_snapshot_date": 1,
            },
        ))
        kpis = list(database[KPI_COLLECTION].find(
            {},
            {
                "_id": 0,
                "page": 1,
                "snapshot_date": 1,
                "collected_at": 1,
                "run_id": 1,
                "combo_key": 1,
                "filters": 1,
                "filters_requested": 1,
                "date_source": 1,
                "dashboard_date": 1,
                "kpis": 1,
                "kpi_count": 1,
            },
        ))
        tables = list(database[TABLE_COLLECTION].find(
            {},
            {
                "_id": 0,
                "page": 1,
                "snapshot_date": 1,
                "collected_at": 1,
                "run_id": 1,
                "combo_key": 1,
                "filters": 1,
                "filters_requested": 1,
                "date_source": 1,
                "dashboard_date": 1,
                "district": 1,
                "district_known": 1,
                "columns": 1,
                "values": 1,
                "row_index": 1,
            },
        ))
    finally:
        client.close()
    return runs, kpis, tables


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        help="Write the complete JSON experiment report to this path.",
    )
    parser.add_argument(
        "--review-csv",
        type=Path,
        help="Write the existing ranked candidate queues as a human-review CSV.",
    )
    args = parser.parse_args(argv)
    if args.output and args.output.exists():
        raise FileExistsError(
            f"Refusing to overwrite existing report: {args.output}"
        )
    runs, kpis, tables = load_mongodb_history()
    from src.data_sources.mongodb_data_health import (
        assess_data_health,
        load_expected_data_registry,
    )
    from src.data_sources.mongodb_district_explorer import load_district_reference

    assessed_at = datetime.now(timezone.utc)
    expected_districts = tuple(load_district_reference())
    registry = load_expected_data_registry(expected_districts=expected_districts)
    health_report = assess_data_health(
        runs,
        kpis,
        tables,
        registry=registry,
        as_of=assessed_at,
    )
    report = build_experiment_report(
        runs,
        tables,
        kpis,
        expected_districts=expected_districts,
        assessment_timestamp=assessed_at,
        data_health_report=health_report,
    )
    if args.output:
        write_json_report_new(args.output, report)
        print(
            f"Wrote read-only NBR experiment report to {args.output} "
            f"({report['evaluation']['walk_forward_test_cases']} test cases)."
        )
    else:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    if args.review_csv:
        row_count = merge_review_queue_csv(report, args.review_csv)
        print(
            f"Merged {row_count} current candidates into human-review CSV "
            f"{args.review_csv}."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "NBRObservation",
    "MIN_TRAINING_RATES",
    "ROBUST_SCORE_THRESHOLD",
    "BASELINE_MAX_GAP_DAYS",
    "MIN_CROSS_SECTION_DISTRICTS",
    "CROSS_SECTION_ROBUST_Z_THRESHOLD",
    "evaluate_chronologically",
    "evaluate_cross_sectionally",
    "prepare_observations",
    "build_experiment_report",
    "load_mongodb_history",
    "write_review_queue_csv",
    "merge_review_queue_csv",
    "main",
]
