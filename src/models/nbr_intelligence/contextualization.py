"""Read-only FinScope contextualization and NBR cross-channel assessments."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.data_sources.mongodb_district_explorer import (
    _unit,
    parse_numeric_value,
)
from src.indicators import REGISTRY
from src.models.nbr_intelligence import MODEL_VERSION
from src.models.nbr_intelligence.experiment import (
    PROJECT_ROOT,
    _identity,
    _tentative_reconciliation_qualifications,
    load_mongodb_history,
    prepare_observations,
)
from src.models.nbr_intelligence.assessment import (
    source_revision_metadata,
    write_json_report_new,
)
from src.models.nbr_intelligence.indicator_mapping import (
    FINSCOPE_POPULATION,
    FINSCOPE_REFERENCE_PERIOD,
    FINSCOPE_WEIGHT,
    INDICATOR_MAPPING,
    MAPPING_BY_VARIABLE,
)
from src.models.nbr_intelligence.review import merge_review_queue_csv

CONTEXT_START_DATE = date(2025, 1, 1)
MIN_TREND_OBSERVATIONS = 3
SUFFICIENT_DIRECTIONAL_OBSERVATIONS = 5
FRESHNESS_TOLERANCE_DAYS = 8

CHANNEL_CLASSES = {
    "branches": "physical_access",
    "agents": "physical_access",
    "pos": "merchant_acceptance",
    "merchants": "merchant_acceptance",
    "mobile_banking": "digital_service_activity",
    "internet_banking": "digital_service_activity",
    "transactional": "account_activity",
    "cards": "payment_instrument_activity",
    "inclusion": "customer_reach",
    "depositors": "deposit_activity",
    "savings": "savings_activity",
    "credit": "credit_activity",
    "insurance": "insurance_activity",
}

_DEMOGRAPHIC_FILTERS = {
    "gender": "Gender",
    "age_group": "Age Segment",
}
_METADATA_FILTERS = {
    "Gender",
    "Age Segment",
    "Institution Type",
}


def _json_default(value: Any) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def _source_id(point: Mapping[str, Any]) -> str:
    payload = {
        key: point.get(key)
        for key in (
            "source_type",
            "page",
            "metric_label",
            "reporting_date",
            "combo_key",
            "geography",
            "run_id",
            "row_index",
        )
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:24]


def _filters_match(
    record_filters: Mapping[str, Any] | None,
    expected_filters: Mapping[str, Any],
) -> bool:
    if not isinstance(record_filters, Mapping):
        return False
    return all(
        str(record_filters.get(key, "")).strip().casefold()
        == str(value).strip().casefold()
        for key, value in expected_filters.items()
    )


def _prepare_kpi_points(
    runs: Sequence[Mapping[str, Any]],
    kpi_documents: Sequence[Mapping[str, Any]],
    qualifications: Mapping[tuple[str, str, str], Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    runs_by_key: dict[tuple[str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for run in runs:
        runs_by_key[_identity(run)].append(run)

    points = []
    excluded: defaultdict[str, int] = defaultdict(int)
    for document in kpi_documents:
        key = _identity(document)
        matches = runs_by_key.get(key, [])
        if not all(key):
            excluded["missing_observation_identity"] += 1
            continue
        if len(matches) != 1:
            excluded["missing_or_ambiguous_collection_run"] += 1
            continue
        run = matches[0]
        run_id = str(run.get("run_id", ""))
        if not run_id or str(document.get("run_id", "")) != run_id:
            excluded["run_id_mismatch"] += 1
            continue
        if run.get("filters_key") and run.get("filters_key") != key[2]:
            excluded["run_filter_key_mismatch"] += 1
            continue
        run_filters = run.get("filters")
        if not isinstance(run_filters, Mapping):
            run_filters = run.get("filters_requested")
        document_filters = document.get("filters")
        if not isinstance(run_filters, Mapping) or not isinstance(
            document_filters,
            Mapping,
        ):
            excluded["missing_filter_provenance"] += 1
            continue
        if run_filters != document_filters:
            excluded["run_filter_values_mismatch"] += 1
            continue
        if run.get("status") != "complete":
            excluded["collection_not_complete"] += 1
            continue
        if run.get("repeated_snapshot_warning"):
            excluded["repeated_snapshot"] += 1
            continue
        try:
            reporting_date = date.fromisoformat(key[1])
        except ValueError:
            excluded["invalid_reporting_date"] += 1
            continue

        filters = run_filters
        if not isinstance(filters, Mapping):
            filters = run.get("filters_requested")
        if not isinstance(filters, Mapping):
            excluded["missing_filter_provenance"] += 1
            continue
        requested_filters = document.get("filters_requested")
        run_requested_filters = run.get("filters_requested")
        if (
            isinstance(requested_filters, Mapping)
            and isinstance(run_requested_filters, Mapping)
            and requested_filters != run_requested_filters
        ):
            excluded["run_requested_filter_values_mismatch"] += 1
            continue
        collected_at = document.get("collected_at") or run.get("collected_at")
        if isinstance(collected_at, datetime):
            collected_at = collected_at.isoformat()
        if not isinstance(collected_at, str) or not collected_at.strip():
            excluded["missing_collection_timestamp"] += 1
            continue

        for metric in document.get("kpis", []):
            if not isinstance(metric, Mapping):
                continue
            if metric.get("metric_type") not in (None, "headline_kpi"):
                continue
            label = str(metric.get("metric_label", "")).strip()
            raw_value = metric.get("metric_value_numeric")
            if raw_value is None:
                raw_value = metric.get("metric_value")
            value = parse_numeric_value(raw_value)
            if not label or value is None or value < 0 or not math.isfinite(float(value)):
                excluded["missing_or_unsuitable_metric_value"] += 1
                continue
            point = {
                "source_type": "national_kpi",
                "page": key[0],
                "metric_label": label,
                "reporting_date": reporting_date.isoformat(),
                "collected_at": collected_at,
                "run_id": run_id,
                "combo_key": key[2],
                "filters": dict(filters),
                "geography_level": "national",
                "geography": "Rwanda",
                "value": float(value),
                "raw_value": raw_value,
                "unit": _unit(raw_value, label, True)[0],
                "unit_status": _unit(raw_value, label, True)[1],
                "quality_qualifications": (
                    [dict(qualifications[key])] if key in qualifications else []
                ),
            }
            point["source_record_id"] = _source_id(point)
            points.append(point)
    return points, dict(excluded)


def prepare_source_points(
    runs: Sequence[Mapping[str, Any]],
    kpi_documents: Sequence[Mapping[str, Any]],
    table_documents: Sequence[Mapping[str, Any]],
    *,
    as_of_date: date | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Prepare eligible national KPI and district table evidence without writes."""
    cutoff = as_of_date or date.today()
    qualifications = _tentative_reconciliation_qualifications(
        kpi_documents,
        table_documents,
    )
    observations, excluded_rows, excluded_values = prepare_observations(
        runs,
        table_documents,
    )
    points = []
    excluded_filter_provenance = 0
    for observation in observations:
        if not observation.filters:
            excluded_filter_provenance += 1
            continue
        point = {
            "source_type": "district_table",
            "page": observation.page,
            "metric_label": observation.metric_label,
            "reporting_date": observation.reporting_date.isoformat(),
            "collected_at": observation.collected_at,
            "run_id": observation.run_id,
            "combo_key": observation.combo_key,
            "filters": dict(observation.filters),
            "geography_level": "district",
            "geography": observation.district,
            "value": observation.value,
            "raw_value": observation.value,
            "unit": _unit(observation.value, observation.metric_label, False)[0],
            "unit_status": _unit(
                observation.value,
                observation.metric_label,
                False,
            )[1],
            "quality_qualifications": [],
        }
        scope_key = (
            observation.page,
            observation.reporting_date.isoformat(),
            observation.combo_key,
        )
        if scope_key in qualifications:
            point["quality_qualifications"].append(
                dict(qualifications[scope_key])
            )
        point["source_record_id"] = _source_id(point)
        points.append(point)

    kpi_points, excluded_kpis = _prepare_kpi_points(
        runs,
        kpi_documents,
        qualifications,
    )
    points.extend(kpi_points)
    points = [
        point for point in points
        if CONTEXT_START_DATE
        <= date.fromisoformat(point["reporting_date"])
        <= cutoff
    ]
    points.sort(key=lambda point: (
        point["page"],
        point["metric_label"],
        point["geography_level"],
        point["geography"],
        point["combo_key"],
        point["reporting_date"],
    ))
    return points, {
        "eligible_source_point_count": len(points),
        "eligible_district_table_point_count": sum(
            point["source_type"] == "district_table" for point in points
        ),
        "eligible_national_kpi_point_count": sum(
            point["source_type"] == "national_kpi" for point in points
        ),
        "excluded_table_rows_by_reason": excluded_rows,
        "excluded_table_values_by_reason": excluded_values,
        "excluded_table_points_missing_filter_provenance": (
            excluded_filter_provenance
        ),
        "excluded_kpi_documents_by_reason": excluded_kpis,
        "reporting_dates": sorted({
            point["reporting_date"] for point in points
        }),
        "context_start_date": CONTEXT_START_DATE.isoformat(),
        "reporting_date_semantics": (
            "NBR snapshot_date is the reporting date; collected_at is provenance."
        ),
    }


def _series_key(point: Mapping[str, Any]) -> tuple[str, str, str, str, str, str]:
    return (
        str(point["page"]),
        str(point["metric_label"]),
        str(point["geography_level"]),
        str(point["geography"]),
        str(point["combo_key"]),
        str(point["source_type"]),
    )


def summarize_trend(points: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Summarize one exact NBR metric/filter/geography series, without imputation."""
    ordered = sorted(points, key=lambda point: str(point["reporting_date"]))
    dates = [str(point["reporting_date"]) for point in ordered]
    source_record_ids = [
        str(point.get("source_record_id", "")) for point in ordered
    ]
    quality_qualifications = [
        qualification
        for point in ordered
        for qualification in point.get("quality_qualifications", [])
    ]
    if len(set(dates)) != len(dates):
        return {
            "direction": "not_assessable",
            "evidence_sufficiency_state": "not_comparable",
            "reason": "Multiple observations share a reporting date in this series.",
            "observations": ordered,
            "reporting_dates": dates,
            "observation_count": len(ordered),
            "source_record_ids": source_record_ids,
            "quality_qualifications": quality_qualifications,
        }
    if len(ordered) < MIN_TREND_OBSERVATIONS:
        return {
            "direction": "not_assessable",
            "evidence_sufficiency_state": "insufficient_evidence",
            "reason": (
                "At least three independent reporting dates are required to "
                "observe two successive changes."
            ),
            "observations": ordered,
            "reporting_dates": dates,
            "observation_count": len(ordered),
            "source_record_ids": source_record_ids,
            "quality_qualifications": quality_qualifications,
        }

    values = [float(point["value"]) for point in ordered]
    transitions = [
        (right - left)
        for left, right in zip(values, values[1:])
    ]
    positive = any(delta > 0 for delta in transitions)
    negative = any(delta < 0 for delta in transitions)
    direction = (
        "mixed"
        if positive and negative
        else "increasing"
        if positive
        else "decreasing"
        if negative
        else "unchanged"
    )
    dates_as_date = [date.fromisoformat(item) for item in dates]
    intervals = [
        (right - left).days
        for left, right in zip(dates_as_date, dates_as_date[1:])
    ]
    has_quality_qualification = any(
        point.get("quality_qualifications") for point in ordered
    )
    if len(ordered) < SUFFICIENT_DIRECTIONAL_OBSERVATIONS:
        sufficiency = "limited_evidence"
    elif has_quality_qualification:
        sufficiency = "limited_evidence"
    else:
        sufficiency = "sufficient_for_directional_assessment"

    return {
        "direction": direction,
        "evidence_sufficiency_state": sufficiency,
        "reason": (
            "Direction summarizes observed values only; no missing periods are "
            "interpolated and no long-term or causal conclusion is implied."
        ),
        "reporting_dates": dates,
        "observation_count": len(ordered),
        "interval_days": intervals,
        "first_value": values[0],
        "last_value": values[-1],
        "absolute_change": values[-1] - values[0],
        "percent_change": (
            (values[-1] - values[0]) / values[0] * 100
            if values[0] != 0 else None
        ),
        "source_record_ids": source_record_ids,
        "observations": ordered,
        "quality_qualifications": quality_qualifications,
    }


def _channel_scope(trend: Mapping[str, Any]) -> tuple[str, ...] | None:
    observations = trend.get("observations", [])
    if not observations:
        return None
    trend_filters = trend.get("filters", observations[0].get("filters", {}))
    if not isinstance(trend_filters, Mapping):
        return None
    expected_filters = {
        str(key).strip().casefold(): str(value).strip().casefold()
        for key, value in trend_filters.items()
    }
    if any(
        not isinstance(point.get("filters", trend_filters), Mapping)
        or {
            str(key).strip().casefold(): str(value).strip().casefold()
            for key, value in point.get("filters", trend_filters).items()
        } != expected_filters
        for point in observations
    ):
        return None

    if any(
        key not in _METADATA_FILTERS
        and str(value).strip().casefold() != "all"
        and not (
            "status" in str(key).casefold()
            and str(value).strip().casefold() == "active"
        )
        for key, value in trend_filters.items()
    ):
        return None
    return (
        str(trend.get("geography_level", "")),
        str(trend.get("geography", "")),
        str(trend_filters.get("Gender", "All")).strip().casefold(),
        str(trend_filters.get("Age Segment", "All")).strip().casefold(),
        str(trend_filters.get("Institution Type", "All")).strip().casefold(),
    )


def _channel_scope_exclusion_reason(
    trend: Mapping[str, Any],
) -> str | None:
    observations = trend.get("observations", [])
    if not observations:
        return "missing_observations"
    filters = trend.get("filters", observations[0].get("filters", {}))
    if not isinstance(filters, Mapping):
        return "invalid_filter_metadata"
    expected_filters = {
        str(key).strip().casefold(): str(value).strip().casefold()
        for key, value in filters.items()
    }
    if any(
        not isinstance(point.get("filters", filters), Mapping)
        or {
            str(key).strip().casefold(): str(value).strip().casefold()
            for key, value in point.get("filters", filters).items()
        } != expected_filters
        for point in observations
    ):
        return "inconsistent_filter_provenance"
    for key, value in filters.items():
        if key in _METADATA_FILTERS or str(value).strip().casefold() == "all":
            continue
        if "status" in str(key).casefold() and (
            str(value).strip().casefold() == "active"
        ):
            continue
        return "unsupported_non_default_filter"
    return None


def _channel_series_identity(
    trend: Mapping[str, Any],
) -> tuple[Any, ...]:
    filters = trend.get("filters", {})
    normalized_filters = tuple(sorted(
        (str(key).strip().casefold(), str(value).strip().casefold())
        for key, value in filters.items()
    )) if isinstance(filters, Mapping) else ()
    return (
        str(trend.get("page", "")),
        str(trend.get("metric_label", "")),
        str(trend.get("unit", "")),
        str(trend.get("unit_status", "")),
        normalized_filters,
        str(trend.get("geography_level", "")),
        str(trend.get("geography", "")),
        str(trend.get("source_type", "")),
    )


def _channel_series_signature(trend: Mapping[str, Any]) -> str:
    return json.dumps(
        {
            "identity": _channel_series_identity(trend),
            "observations": trend.get("observations", []),
        },
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    )


def _channel_series_id(trend: Mapping[str, Any]) -> str:
    serialized = json.dumps(
        _channel_series_identity(trend),
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:20]


def _channel_filters_compatible(
    first: Mapping[str, Any],
    second: Mapping[str, Any],
) -> tuple[bool, str]:
    first_filters = first.get("filters", {})
    second_filters = second.get("filters", {})
    if not isinstance(first_filters, Mapping) or not isinstance(
        second_filters, Mapping
    ):
        return False, "invalid_filter_metadata"

    def comparable_filters(filters: Mapping[str, Any]) -> dict[str, str]:
        return {
            str(key).strip().casefold(): str(value).strip().casefold()
            for key, value in filters.items()
            if key not in _METADATA_FILTERS
            and str(value).strip().casefold() != "all"
            and "status" not in str(key).casefold()
        }

    first_status = [
        (str(key).strip().casefold(), str(value).strip().casefold())
        for key, value in first_filters.items()
        if "status" in str(key).casefold()
        and str(value).strip().casefold() != "all"
    ]
    second_status = [
        (str(key).strip().casefold(), str(value).strip().casefold())
        for key, value in second_filters.items()
        if "status" in str(key).casefold()
        and str(value).strip().casefold() != "all"
    ]
    if comparable_filters(first_filters) != comparable_filters(second_filters):
        return False, "incompatible_filter_scope"
    if first_status == second_status:
        return True, "exact_filters"
    if (
        len(first_status) == 1
        and len(second_status) == 1
        and first_status[0][1] == "active"
        and second_status[0][1] == "active"
    ):
        return True, "page_specific_active_status_filters"
    return False, "incompatible_filter_scope"


def compare_cross_channel_trends(
    trends: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Compare distinct eligible series on exact common dates and compatible scope."""
    grouped: dict[tuple[str, ...], list[Mapping[str, Any]]] = defaultdict(list)
    excluded_series: dict[str, int] = defaultdict(int)
    identity_signatures: dict[tuple[Any, ...], list[str]] = defaultdict(list)
    identity_trends: dict[tuple[Any, ...], Mapping[str, Any]] = {}
    for trend in trends:
        page = str(trend.get("page", ""))
        if page not in CHANNEL_CLASSES:
            excluded_series["unmapped_page"] += 1
            continue
        scope = _channel_scope(trend)
        if scope is None:
            excluded_series[_channel_scope_exclusion_reason(trend) or "invalid_scope"] += 1
            continue
        identity = _channel_series_identity(trend)
        signature = _channel_series_signature(trend)
        identity_signatures[identity].append(signature)
        identity_trends[identity] = trend

    duplicate_series_count = 0
    for identity, signatures in identity_signatures.items():
        unique_signatures = set(signatures)
        if len(unique_signatures) > 1:
            excluded_series["ambiguous_duplicate_series_identity"] += len(
                signatures
            )
            duplicate_series_count += len(signatures)
            continue
        duplicate_series_count += len(signatures) - 1
        trend = identity_trends[identity]
        scope = _channel_scope(trend)
        if scope is not None:
            grouped[scope].append(trend)

    summary_counts: dict[str, int] = defaultdict(int)
    eligible_series = sum(len(items) for items in grouped.values())
    page_totals: dict[str, int] = defaultdict(int)
    scoped_page_totals: dict[tuple[str, ...], dict[str, int]] = defaultdict(
        lambda: defaultdict(int)
    )
    for scope, scope_trends in grouped.items():
        for trend in scope_trends:
            page = str(trend["page"])
            page_totals[page] += 1
            scoped_page_totals[scope][page] += 1
    all_cross_page_pairs = (
        eligible_series * eligible_series
        - sum(count * count for count in page_totals.values())
    ) // 2
    same_scope_cross_page_pairs = sum(
        (
            sum(page_counts.values()) ** 2
            - sum(count * count for count in page_counts.values())
        ) // 2
        for page_counts in scoped_page_totals.values()
    )
    incompatible_scope_pairs = all_cross_page_pairs - same_scope_cross_page_pairs
    if incompatible_scope_pairs:
        summary_counts["incompatible_scope"] = incompatible_scope_pairs
    findings = []
    for scope, scope_trends in sorted(grouped.items()):
        by_page: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for trend in scope_trends:
            by_page[str(trend["page"])].append(trend)
        page_names = sorted(by_page)
        for index, first_page in enumerate(page_names):
            for second_page in page_names[index + 1:]:
                for first in by_page[first_page]:
                    for second in by_page[second_page]:
                        summary_counts["candidate_pairs"] += 1
                        filters_compatible, filter_policy = (
                            _channel_filters_compatible(first, second)
                        )
                        if not filters_compatible:
                            summary_counts["incompatible_filter_scope"] += 1
                            continue
                        first_dates_lists: dict[str, list[Mapping[str, Any]]] = (
                            defaultdict(list)
                        )
                        second_dates_lists: dict[str, list[Mapping[str, Any]]] = (
                            defaultdict(list)
                        )
                        for point in first.get("observations", []):
                            first_dates_lists[str(point["reporting_date"])].append(point)
                        for point in second.get("observations", []):
                            second_dates_lists[str(point["reporting_date"])].append(point)
                        duplicate_date = any(
                            len(points) != 1
                            for points in (
                                *first_dates_lists.values(),
                                *second_dates_lists.values(),
                            )
                        )
                        if duplicate_date:
                            summary_counts["duplicate_reporting_dates"] += 1
                            continue
                        first_dates = {
                            day: points[0]
                            for day, points in first_dates_lists.items()
                        }
                        second_dates = {
                            day: points[0]
                            for day, points in second_dates_lists.items()
                        }
                        common_dates = sorted(set(first_dates) & set(second_dates))
                        if len(common_dates) < MIN_TREND_OBSERVATIONS:
                            summary_counts["insufficient_shared_dates"] += 1
                            continue
                        aligned = []
                        for trend, observations_by_date in (
                            (first, first_dates),
                            (second, second_dates),
                        ):
                            aligned_trend = summarize_trend([
                                observations_by_date[reporting_date]
                                for reporting_date in common_dates
                            ])
                            aligned.append({
                                "page": trend["page"],
                                "metric_label": trend["metric_label"],
                                "channel_class": CHANNEL_CLASSES[str(trend["page"])],
                                "unit": trend.get("unit", ""),
                                "unit_status": trend.get("unit_status", ""),
                                "direction": aligned_trend["direction"],
                                "evidence_sufficiency_state": aligned_trend[
                                    "evidence_sufficiency_state"
                                ],
                                "reporting_dates": common_dates,
                                "filters": trend["filters"],
                                "filter_compatibility_policy": filter_policy,
                                "geography_level": trend["geography_level"],
                                "geography": trend["geography"],
                                "source_record_ids": aligned_trend["source_record_ids"],
                                "observations": [
                                    {
                                        "reporting_date": str(
                                            observations_by_date[reporting_date][
                                                "reporting_date"
                                            ]
                                        ),
                                        "page": str(
                                            observations_by_date[reporting_date]["page"]
                                        ),
                                        "metric_label": str(
                                            observations_by_date[reporting_date][
                                                "metric_label"
                                            ]
                                        ),
                                        "observed_value": observations_by_date[
                                            reporting_date
                                        ]["value"],
                                        "unit": observations_by_date[
                                            reporting_date
                                        ].get("unit", trend.get("unit", "")),
                                        "filters": observations_by_date[
                                            reporting_date
                                        ].get("filters", trend["filters"]),
                                        "source_record_id": str(
                                            observations_by_date[reporting_date].get(
                                                "source_record_id", ""
                                            )
                                        ),
                                    }
                                    for reporting_date in common_dates
                                ],
                            })
                        directions = {item["direction"] for item in aligned}
                        physical_decrease_and_digital_increase = (
                            aligned[0]["direction"] == "decreasing"
                            and aligned[1]["direction"] == "increasing"
                            or aligned[1]["direction"] == "decreasing"
                            and aligned[0]["direction"] == "increasing"
                        ) and {
                            item["channel_class"]: item["direction"]
                            for item in aligned
                        } == {
                            "physical_access": "decreasing",
                            "digital_service_activity": "increasing",
                        }
                        if physical_decrease_and_digital_increase:
                            pattern = "possible_channel_substitution"
                        elif directions == {"increasing"}:
                            pattern = "complementary_growth"
                        elif directions == {"decreasing"}:
                            pattern = "broad_contraction"
                        else:
                            pattern = "mixed_trends"
                        findings.append({
                            "analytical_level": scope[0],
                            "geography": scope[1],
                            "gender_filter": scope[2],
                            "age_segment_filter": scope[3],
                            "institution_type_filter": scope[4],
                            "shared_reporting_dates": common_dates,
                            "pattern": pattern,
                            "pair_id": hashlib.sha256(
                                "|".join(sorted((
                                    _channel_series_id(first),
                                    _channel_series_id(second),
                                ))).encode("utf-8")
                            ).hexdigest()[:20],
                            "channels": aligned,
                            "missing_channel_pages": sorted(
                                set(CHANNEL_CLASSES) - set(page_names)
                            ),
                            "interpretation": (
                                "This pairwise classification describes the "
                                "separately filtered metric series only. It does "
                                "not establish substitution, access, usage, "
                                "causality, or an overall financial-inclusion change."
                            ),
                            "limitations": [
                                "No counts, rates, transactions, or customers are added together.",
                                "Only common reporting dates and compatible common filters are compared.",
                                "Distinct page-specific active-status filters are retained and are not asserted to define equivalent populations.",
                                "A page class does not make different metric labels the same construct.",
                                "A district or subgroup result is not generalized to other populations.",
                            ],
                        })
                        summary_counts["compared"] += 1

    return findings, {
        "channel_series_count": sum(
            trend.get("page") in CHANNEL_CLASSES for trend in trends
        ),
        "eligible_series_count": eligible_series,
        "excluded_series_by_reason": dict(sorted(excluded_series.items())),
        "duplicate_series_count": duplicate_series_count,
        "candidate_pair_count": all_cross_page_pairs,
        "comparison_counts_by_reason": dict(sorted(summary_counts.items())),
        "comparable_scope_count": len(findings),
        "patterns": {
            pattern: sum(item["pattern"] == pattern for item in findings)
            for pattern in (
                "possible_channel_substitution",
                "complementary_growth",
                "broad_contraction",
                "mixed_trends",
            )
        },
        "not_comparable_series_count": sum(
            trend.get("page") in CHANNEL_CLASSES
            and _channel_scope(trend) is None
            for trend in trends
        ),
    }


def load_finscope_baselines(processed_dir: Path) -> list[dict[str, Any]]:
    """Load published processed point estimates; never recompute weighted rates."""
    definitions = {item["variable"]: item for item in INDICATOR_MAPPING}
    variables_by_column = {
        item["column"]: item["variable"] for item in definitions.values()
    }
    baselines: list[dict[str, Any]] = []

    denominator_path = processed_dir / "indicator_denominator_validation.csv"
    denominators = {}
    if denominator_path.exists():
        with denominator_path.open(encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream):
                denominators[row.get("Variable", "")] = row

    for filename in ("national_financial_inclusion.csv", "national_extended_indicators.csv"):
        path = processed_dir / filename
        if not path.exists():
            continue
        with path.open(encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream):
                variable = row.get("Source variable", "")
                estimate = parse_numeric_value(row.get("Estimate (%)"))
                if variable not in definitions or estimate is None:
                    continue
                denominator = denominators.get(variable, {})
                baselines.append({
                    "analytical_level": "national",
                    "geography": "Rwanda",
                    "subgroup_type": "",
                    "subgroup": "",
                    "indicator_variable": variable,
                    "indicator_label": row.get("Indicator", ""),
                    "estimate_percent": float(estimate),
                    "valid_respondents": parse_numeric_value(
                        denominator.get("Valid responses")
                    ),
                    "baseline_source": filename,
                })

    for filename in ("district_financial_inclusion.csv", "district_extended_indicators.csv"):
        path = processed_dir / filename
        if not path.exists():
            continue
        with path.open(encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream):
                district = row.get("District", "").strip()
                for column, variable in variables_by_column.items():
                    estimate = parse_numeric_value(row.get(column))
                    if not district or estimate is None:
                        continue
                    baselines.append({
                        "analytical_level": "district",
                        "geography": district,
                        "subgroup_type": "",
                        "subgroup": "",
                        "indicator_variable": variable,
                        "indicator_label": definitions[variable][
                            "original_indicator_label"
                        ],
                        "estimate_percent": float(estimate),
                        "valid_respondents": parse_numeric_value(
                            row.get("Valid respondents")
                        ),
                        "baseline_source": filename,
                    })

    group_path = processed_dir / "population_group_indicators.csv"
    if group_path.exists():
        with group_path.open(encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream):
                group_type = row.get("Group type", "").strip()
                group = row.get("Group", "").strip()
                for column, variable in variables_by_column.items():
                    estimate = parse_numeric_value(row.get(column))
                    if not group_type or not group or estimate is None:
                        continue
                    baselines.append({
                        "analytical_level": "demographic",
                        "geography": "Rwanda",
                        "subgroup_type": group_type,
                        "subgroup": group,
                        "indicator_variable": variable,
                        "indicator_label": definitions[variable][
                            "original_indicator_label"
                        ],
                        "estimate_percent": float(estimate),
                        "valid_respondents": parse_numeric_value(
                            row.get("Valid respondents")
                        ),
                        "baseline_source": "population_group_indicators.csv",
                    })
    return baselines


def _matching_relationships(
    baseline: Mapping[str, Any],
) -> list[dict[str, Any]]:
    variable = str(baseline["indicator_variable"])
    indicator = MAPPING_BY_VARIABLE.get(variable)
    relationships = list((indicator or {}).get("nbr_relationships", []))
    level = str(baseline["analytical_level"])
    if level == "demographic":
        if baseline.get("subgroup_type") != "Gender":
            return []
        subgroup = str(baseline.get("subgroup", ""))
        if subgroup.casefold() not in {"male", "female"}:
            return []
        relationships = [
            relationship for relationship in relationships
            if relationship["filter_scope"].get("Gender", "").casefold() == "all"
            and "Age Segment" in relationship["filter_scope"]
        ]
        relationships = [
            {
                **relationship,
                "filter_scope": {
                    **relationship["filter_scope"],
                    "Gender": subgroup,
                    "Age Segment": "All",
                },
            }
            for relationship in relationships
        ]
        level = "national"
    return [
        relationship for relationship in relationships
        if level in relationship["available_levels"]
        and relationship["relationship"] != "unsuitable"
    ]


def _suggestion_outcome(
    polarity: str,
    direction: str,
) -> tuple[str, str]:
    if direction == "mixed":
        return "mixed_evidence", "Administrative observations moved in opposing directions."
    if direction == "unchanged":
        return "insufficient_evidence", "No change was observed in the selected administrative measure."
    if direction not in {"increasing", "decreasing"}:
        return "insufficient_evidence", "The administrative trend is not assessable."
    if polarity == "neutral":
        return (
            "insufficient_evidence",
            "The FinScope indicator is not inherently positive or negative.",
        )
    improvement_direction = "increasing" if polarity == "positive" else "decreasing"
    if direction == improvement_direction:
        return "potential_improvement", "The proxy/context indicator moved in a potentially favorable direction."
    return "potential_deterioration", "The proxy/context indicator moved in a potentially unfavorable direction."


def _channel_findings_for_trend(
    trend: Mapping[str, Any],
    findings: Sequence[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    source_ids = set(str(item) for item in trend.get("source_record_ids", []))
    if not source_ids:
        return []
    scope = (
        trend.get("geography_level"),
        trend.get("geography"),
        str(trend.get("filters", {}).get("Gender", "All")).casefold(),
        str(trend.get("filters", {}).get("Age Segment", "All")).casefold(),
        str(trend.get("filters", {}).get("Institution Type", "All")).casefold(),
    )
    matched = []
    for finding in findings:
        finding_scope = (
            finding.get("analytical_level"),
            finding.get("geography"),
            str(finding.get("gender_filter", "All")).casefold(),
            str(finding.get("age_segment_filter", "All")).casefold(),
            str(finding.get("institution_type_filter", "All")).casefold(),
        )
        if finding_scope != scope:
            continue
        for channel in finding.get("channels", []):
            if (
                channel.get("page") == trend.get("page")
                and channel.get("metric_label") == trend.get("metric_label")
                and source_ids.intersection(
                    str(item) for item in channel.get("source_record_ids", [])
                )
            ):
                matched.append(finding)
                break
    return matched


def _has_conflicting_channel_direction(
    trend: Mapping[str, Any],
    findings: Sequence[Mapping[str, Any]],
) -> bool:
    direction = str(trend.get("direction", ""))
    for finding in findings:
        for channel in finding.get("channels", []):
            if (
                channel.get("page") == trend.get("page")
                and channel.get("metric_label") == trend.get("metric_label")
                and set(str(item) for item in trend.get("source_record_ids", []))
                .intersection(
                    str(item) for item in channel.get("source_record_ids", [])
                )
            ):
                continue
            other_direction = str(channel.get("direction", ""))
            if direction == "mixed" or other_direction == "mixed":
                return True
            if {direction, other_direction} == {"increasing", "decreasing"}:
                return True
    return False


def generate_finscope_suggestions(
    baselines: Sequence[Mapping[str, Any]],
    trends: Sequence[Mapping[str, Any]],
    cross_channel_findings: Sequence[Mapping[str, Any]],
    source_quality_assessment: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Create qualified suggestions without replacing any FinScope estimate."""
    suggestions = []
    for baseline in baselines:
        relationships = _matching_relationships(baseline)
        indicator = MAPPING_BY_VARIABLE.get(str(baseline["indicator_variable"]), {})
        if not relationships:
            reason = (
                "NBR does not expose a documented matching demographic definition."
                if baseline["analytical_level"] == "demographic"
                else indicator.get("nbr_no_relevant_data_reason")
                or "No eligible, documented NBR mapping exists for this level."
            )
            suggestions.append({
                "analytical_level": baseline["analytical_level"],
                "geography": baseline["geography"],
                "subgroup_type": baseline["subgroup_type"],
                "subgroup": baseline["subgroup"],
                "indicator_variable": baseline["indicator_variable"],
                "indicator_label": baseline["indicator_label"],
                "finscope_estimate_percent": baseline["estimate_percent"],
                "finscope_reference_period": FINSCOPE_REFERENCE_PERIOD,
                "valid_respondents": baseline.get("valid_respondents"),
                "outcome": "insufficient_evidence",
                "evidence_sufficiency_state": "not_assessable",
                "suggested_interpretation": reason,
                "supporting_evidence": [],
                "contradictory_or_missing_evidence": [reason],
                "limitations": [
                    "The stored FinScope estimate remains the original survey result.",
                    "No current survey percentage is calculated or imputed.",
                ],
                "recommended_follow_up": (
                    "Obtain a documented, scope-compatible NBR metric or new survey evidence."
                ),
                "source_references": [{
                    "source": baseline["baseline_source"],
                    "indicator_variable": baseline["indicator_variable"],
                }],
            })
            continue

        for relationship in relationships:
            source_level = (
                "national"
                if baseline["analytical_level"] == "demographic"
                else baseline["analytical_level"]
            )
            expected_labels = (
                relationship["district_table_labels"]
                if source_level == "district"
                else relationship["national_kpi_labels"]
            )
            expected_filters = relationship["filter_scope"]
            matching_trends = [
                trend for trend in trends
                if trend["page"] == relationship["page"]
                and trend["metric_label"] in expected_labels
                and trend["geography_level"] == source_level
                and trend["geography"] == baseline["geography"]
                and _filters_match(trend["filters"], expected_filters)
            ]
            if not matching_trends:
                suggestions.append({
                    "analytical_level": baseline["analytical_level"],
                    "geography": baseline["geography"],
                    "subgroup_type": baseline["subgroup_type"],
                    "subgroup": baseline["subgroup"],
                    "indicator_variable": baseline["indicator_variable"],
                    "indicator_label": baseline["indicator_label"],
                    "finscope_estimate_percent": baseline["estimate_percent"],
                    "finscope_reference_period": FINSCOPE_REFERENCE_PERIOD,
                    "finscope_valid_respondents": baseline.get("valid_respondents"),
                    "nbr_metric": expected_labels,
                    "nbr_page": relationship["page"],
                    "nbr_observation_periods": [],
                    "nbr_observed_direction": "not_assessable",
                    "outcome": "insufficient_evidence",
                    "evidence_sufficiency_state": "not_assessable",
                    "suggested_interpretation": (
                        "No eligible, scope-matched NBR series was available."
                    ),
                    "supporting_evidence": [],
                    "contradictory_or_missing_evidence": [
                        "Required NBR metric, filter scope, geography, or reporting dates are missing."
                    ],
                    "limitations": [
                        relationship["limitations"],
                        "No missing observation is treated as zero.",
                        "The original FinScope estimate is not updated.",
                    ],
                    "recommended_follow_up": (
                        "Verify that an eligible complete NBR observation exists for the exact scope."
                    ),
                    "source_references": [{
                        "source": baseline["baseline_source"],
                        "indicator_variable": baseline["indicator_variable"],
                    }],
                })
                continue
            for trend in matching_trends:
                polarity = str(indicator.get("polarity", "neutral"))
                channel_outcome, channel_interpretation = _suggestion_outcome(
                    polarity,
                    str(trend["direction"]),
                )
                outcome = channel_outcome
                interpretation = channel_interpretation
                if relationship["relationship"] != "contextual_indicator":
                    outcome = "insufficient_evidence"
                    interpretation = (
                        "The NBR administrative proxy changed direction, but its "
                        "relationship to the FinScope measure is not established."
                    )
                sufficiency = trend["evidence_sufficiency_state"]
                if (
                    source_quality_assessment
                    and source_quality_assessment.get("freshness_status")
                    not in {"supported", "not_assessed"}
                ):
                    sufficiency = "limited_evidence"
                if relationship["relationship"] != "contextual_indicator":
                    sufficiency = (
                        "limited_evidence"
                        if sufficiency != "insufficient_evidence"
                        else sufficiency
                    )
                if trend["quality_qualifications"]:
                    sufficiency = "limited_evidence"

                related_channel_findings = _channel_findings_for_trend(
                    trend,
                    cross_channel_findings,
                )
                channel_conflict = _has_conflicting_channel_direction(
                    trend,
                    related_channel_findings,
                )
                if relationship["relationship"] == "contextual_indicator" and channel_conflict:
                    outcome = "mixed_evidence"
                    interpretation = (
                        "The mapped NBR channel moved in a different or mixed "
                        "direction from another comparable channel. Neither "
                        "movement establishes a change in the FinScope indicator."
                    )
                supporting = {
                    "page": trend["page"],
                    "metric_label": trend["metric_label"],
                    "unit": trend.get("unit", ""),
                    "unit_status": trend.get("unit_status", ""),
                    "relationship": relationship["relationship"],
                    "observed_direction": trend["direction"],
                    "observations": trend["observations"],
                    "source_record_ids": trend["source_record_ids"],
                    "filters": trend["filters"],
                    "run_ids": sorted({
                        point["run_id"] for point in trend["observations"]
                    }),
                    "quality_qualifications": trend["quality_qualifications"],
                }
                limitations = [
                    relationship["limitations"],
                    "Administrative counts are not survey ownership/use rates and have no inferred denominator.",
                    "The FinScope estimate and its 2024 reference period are preserved unchanged.",
                    "NBR reporting dates are irregular; changes are based only on observed dates.",
                    "This is a contextual hypothesis, not a causal or updated survey finding.",
                ]
                if related_channel_findings:
                    limitations.append(
                        "Cross-channel movements are reported separately and do not establish net access or substitution."
                    )
                suggestions.append({
                    "analytical_level": baseline["analytical_level"],
                    "geography": baseline["geography"],
                    "subgroup_type": baseline["subgroup_type"],
                    "subgroup": baseline["subgroup"],
                    "indicator_variable": baseline["indicator_variable"],
                    "indicator_label": baseline["indicator_label"],
                    "finscope_estimate_percent": baseline["estimate_percent"],
                    "finscope_reference_period": FINSCOPE_REFERENCE_PERIOD,
                    "finscope_valid_respondents": baseline.get("valid_respondents"),
                    "nbr_metric": trend["metric_label"],
                    "nbr_page": trend["page"],
                    "nbr_observation_periods": trend["reporting_dates"],
                    "nbr_observed_direction": trend["direction"],
                    "nbr_trend_summary": {
                        key: trend.get(key)
                        for key in (
                            "observation_count",
                            "first_value",
                            "last_value",
                            "absolute_change",
                            "percent_change",
                            "interval_days",
                        )
                    },
                    "outcome": outcome,
                    "nbr_channel_directional_signal": {
                        "outcome": channel_outcome,
                        "direction": trend["direction"],
                        "page": trend["page"],
                        "metric_label": trend["metric_label"],
                    },
                    "survey_indicator_conclusion": "not_established",
                    "evidence_sufficiency_state": sufficiency,
                    "suggested_interpretation": interpretation,
                    "supporting_evidence": [supporting],
                    "contradictory_or_missing_evidence": [
                        finding["pattern"]
                        for finding in related_channel_findings
                        if _has_conflicting_channel_direction(
                            trend,
                            [finding],
                        )
                    ],
                    "cross_channel_context": related_channel_findings,
                    "limitations": limitations,
                    "recommended_follow_up": (
                        "Verify source definitions, units, filters, and coverage; "
                        "use a new independent survey to estimate current ownership or use."
                    ),
                    "source_references": [
                        {
                            "source": baseline["baseline_source"],
                            "survey_dataset": "data/datasets/FinScope2024Rwanda.dta",
                            "indicator_variable": baseline["indicator_variable"],
                            "geography": baseline["geography"],
                            "subgroup_type": baseline["subgroup_type"],
                            "subgroup": baseline["subgroup"],
                            "valid_respondents": baseline.get("valid_respondents"),
                        },
                        {
                            "source": "NBR MongoDB observation",
                            "page": trend["page"],
                            "metric_label": trend["metric_label"],
                            "filters": trend["filters"],
                            "reporting_dates": trend["reporting_dates"],
                            "run_ids": supporting["run_ids"],
                            "source_record_ids": trend["source_record_ids"],
                        },
                    ],
                })

    return suggestions


def _trend_series(points: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str, str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for point in points:
        grouped[_series_key(point)].append(point)
    trends = []
    for _key, series in sorted(grouped.items()):
        summary = summarize_trend(series)
        first = series[0]
        trends.append({
            "page": first["page"],
            "metric_label": first["metric_label"],
            "geography_level": first["geography_level"],
            "geography": first["geography"],
            "combo_key": first["combo_key"],
            "filters": first["filters"],
            "source_type": first["source_type"],
            "unit": first.get("unit", ""),
            **summary,
        })
    return trends


def build_national_contextualization_report(
    points: Sequence[Mapping[str, Any]],
    baselines: Sequence[Mapping[str, Any]],
    *,
    assessed_at: datetime | None = None,
) -> dict[str, Any]:
    """Assess normalized national NBR observations against stored FinScope estimates."""
    timestamp = assessed_at or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    timestamp = timestamp.astimezone(timezone.utc)

    eligible_points = []
    excluded = defaultdict(int)
    for point in points:
        if (
            point.get("source_type") != "national_kpi"
            or point.get("geography_level") != "national"
            or str(point.get("geography", "")).casefold() != "rwanda"
            or not isinstance(point.get("filters"), Mapping)
        ):
            excluded["not_national_or_missing_filters"] += 1
            continue
        try:
            reporting_date = date.fromisoformat(
                str(point.get("reporting_date", ""))
            )
            value = float(point.get("value"))
        except (TypeError, ValueError):
            excluded["invalid_reporting_date_or_value"] += 1
            continue
        if value < 0 or not math.isfinite(value):
            excluded["invalid_reporting_date_or_value"] += 1
            continue
        normalized = dict(point)
        normalized["reporting_date"] = reporting_date.isoformat()
        normalized["value"] = value
        normalized["quality_qualifications"] = list(
            point.get("quality_qualifications", [])
        )
        eligible_points.append(normalized)

    eligible_points.sort(key=lambda point: (
        str(point.get("page", "")),
        str(point.get("metric_label", "")),
        str(point.get("combo_key", "")),
        str(point.get("reporting_date", "")),
        str(point.get("source_record_id", "")),
    ))
    trends = _trend_series(eligible_points)
    cross_channel_findings, cross_channel_summary = compare_cross_channel_trends(
        trends
    )
    national_baselines = [
        baseline for baseline in baselines
        if baseline.get("analytical_level") == "national"
        and str(baseline.get("geography", "")).casefold() == "rwanda"
    ]
    suggestions = generate_finscope_suggestions(
        national_baselines,
        trends,
        cross_channel_findings,
    )
    for suggestion in suggestions:
        suggestion["finscope_population"] = FINSCOPE_POPULATION
        suggestion["finscope_weight"] = FINSCOPE_WEIGHT
        supporting = suggestion.get("supporting_evidence", [])
        if not supporting:
            continue
        baseline = next(
            (
                item for item in national_baselines
                if item.get("indicator_variable")
                == suggestion.get("indicator_variable")
            ),
            None,
        )
        if baseline is not None:
            suggestion["finscope_source"] = baseline.get("baseline_source", "")
        relationship_type = supporting[0].get("relationship")
        relationship = next(
            (
                item
                for item in MAPPING_BY_VARIABLE.get(
                    str(suggestion.get("indicator_variable", "")),
                    {},
                ).get("nbr_relationships", [])
                if item.get("page") == suggestion.get("nbr_page")
                and item.get("relationship") == relationship_type
            ),
            None,
        )
        if relationship is not None:
            suggestion["mapping_status"] = relationship.get(
                "existing_mapping_status",
                "unresolved",
            )
            suggestion["mapping_relevance"] = relationship.get("relevance", "")

    return {
        "assessment": {
            "name": "National FinScope contextualization of NBR observations",
            "model_version": MODEL_VERSION,
            "assessment_timestamp": timestamp.isoformat(),
            "sources_assessed_separately": True,
            "FinScope_reference_period": FINSCOPE_REFERENCE_PERIOD,
            "FinScope_population": FINSCOPE_POPULATION,
            "FinScope_weight": FINSCOPE_WEIGHT,
            "NBR_scope": "National Rwanda KPI observations only",
            "method": (
                "Reuse observed-date trend summaries, cross-channel comparisons, "
                "approved mappings, and suggestion/evidence rules."
            ),
        },
        "source_data": {
            "eligible_national_nbr_observation_count": len(eligible_points),
            "eligible_national_finscope_baseline_count": len(national_baselines),
            "excluded_nbr_observations_by_reason": dict(sorted(excluded.items())),
            "reporting_dates": sorted({
                str(point["reporting_date"]) for point in eligible_points
            }),
        },
        "series_trends": trends,
        "cross_channel_summary": cross_channel_summary,
        "cross_channel_findings": cross_channel_findings,
        "suggestions": suggestions,
    }


def select_national_contextualization_findings(
    report: Mapping[str, Any],
    *,
    limit: int = 4,
    excluded_indicator_variables: Sequence[str] = (),
    excluded_source_record_ids: Sequence[str] = (),
) -> list[dict[str, Any]]:
    """Select changing findings, deduplicating indicators and source series."""
    if limit < 0:
        raise ValueError("limit must be zero or greater")
    if limit == 0:
        return []

    excluded_indicators = {str(item) for item in excluded_indicator_variables}
    excluded_sources = {str(item) for item in excluded_source_record_ids}
    eligible = []
    for suggestion in report.get("suggestions", []):
        if (
            suggestion.get("analytical_level") != "national"
            or str(suggestion.get("geography", "")).casefold() != "rwanda"
            or str(suggestion.get("indicator_variable", ""))
            in excluded_indicators
            or suggestion.get("evidence_sufficiency_state")
            not in {"sufficient_for_directional_assessment", "limited_evidence"}
            or suggestion.get("nbr_observed_direction")
            not in {"increasing", "decreasing", "mixed"}
        ):
            continue
        supporting = suggestion.get("supporting_evidence", [])
        if not supporting:
            continue
        evidence = supporting[0]
        observations = evidence.get("observations", [])
        source_ids = {
            str(item)
            for item in evidence.get("source_record_ids", [])
            if item
        }
        dates = sorted({
            str(point.get("reporting_date", ""))
            for point in observations
            if point.get("reporting_date")
        })
        if (
            len(dates) < MIN_TREND_OBSERVATIONS
            or source_ids.intersection(excluded_sources)
        ):
            continue
        latest_date = dates[-1]
        quality_qualifications = evidence.get("quality_qualifications", [])
        filters = evidence.get("filters", {})
        institution_type = (
            str(filters.get("Institution Type", "")).strip().casefold()
            if isinstance(filters, Mapping)
            else ""
        )
        indicator_label = str(suggestion.get("indicator_label", "")).casefold()
        institution_specific = bool(
            institution_type
            and institution_type != "all"
            and institution_type in indicator_label
        )
        eligible.append((
            (
                0
                if suggestion.get("evidence_sufficiency_state")
                == "sufficient_for_directional_assessment"
                else 1,
                bool(quality_qualifications),
                -date.fromisoformat(latest_date).toordinal(),
                0 if evidence.get("relationship") == "contextual_indicator" else 1,
                0 if institution_specific else 1,
                str(suggestion.get("indicator_variable", "")),
                str(suggestion.get("nbr_page", "")),
                str(suggestion.get("nbr_metric", "")),
                json.dumps(evidence.get("filters", {}), sort_keys=True),
            ),
            dict(suggestion),
            evidence,
        ))

    eligible.sort(key=lambda item: item[0])
    selected = []
    seen_series = set()
    seen_indicators = set()
    for _, suggestion, evidence in eligible:
        indicator_variable = str(suggestion.get("indicator_variable", ""))
        series_key = (
            str(evidence.get("page", "")),
            str(evidence.get("metric_label", "")),
            json.dumps(evidence.get("filters", {}), sort_keys=True),
        )
        if series_key in seen_series or indicator_variable in seen_indicators:
            continue
        seen_series.add(series_key)
        seen_indicators.add(indicator_variable)
        selected.append(suggestion)
        if len(selected) == limit:
            break
    return selected


def _health_context(
    health_report: Mapping[str, Any] | None,
) -> tuple[dict[tuple[str, str, str], list[dict[str, Any]]], dict[str, Any]]:
    scoped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    findings = (health_report or {}).get("findings", [])
    counts: defaultdict[str, int] = defaultdict(int)
    for finding in findings:
        if not isinstance(finding, Mapping):
            continue
        check = str(finding.get("check", ""))
        status = str(finding.get("status", ""))
        counts[f"{check}:{status}"] += 1
        evidence = finding.get("evidence")
        if status == "supported" or not isinstance(evidence, Mapping):
            continue
        page = str(evidence.get("page", evidence.get("page_id", "")))
        reporting_date = str(
            evidence.get("reporting_date", evidence.get("snapshot_date", ""))
        )
        combo_key = str(evidence.get("combo_key", ""))
        if page and reporting_date and combo_key:
            scoped[(page, reporting_date, combo_key)].append({
                "check": check,
                "status": status,
                "message": str(finding.get("message", "")),
            })
    summary = {
        "overall_status": (health_report or {}).get("status", "not_assessed"),
        "finding_counts_by_check_and_status": dict(sorted(counts.items())),
        "freshness_status": (
            "supported"
            if any(
                finding.get("check") == "freshness"
                and finding.get("status") == "supported"
                for finding in findings
                if isinstance(finding, Mapping)
            )
            else "limited"
            if any(
                finding.get("check") == "freshness"
                and finding.get("status") in {"tentative", "incomplete"}
                for finding in findings
                if isinstance(finding, Mapping)
            )
            else "not_assessed"
        ),
    }
    return scoped, summary


def _attach_quality_findings(
    points: Sequence[dict[str, Any]],
    scoped_findings: Mapping[tuple[str, str, str], Sequence[Mapping[str, Any]]],
) -> None:
    for point in points:
        key = (point["page"], point["reporting_date"], point["combo_key"])
        point["quality_qualifications"].extend(
            dict(finding) for finding in scoped_findings.get(key, [])
        )


def _enrich_indicator_mappings(
    points: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    enriched = json.loads(json.dumps(INDICATOR_MAPPING))
    for indicator in enriched:
        for relationship in indicator["nbr_relationships"]:
            labels = set(
                relationship["national_kpi_labels"]
                + relationship["district_table_labels"]
            )
            matches = [
                point for point in points
                if point["page"] == relationship["page"]
                and point["metric_label"] in labels
                and _filters_match(
                    point["filters"],
                    relationship["filter_scope"],
                )
            ]
            relationship["observed_reporting_dates"] = sorted({
                point["reporting_date"] for point in matches
            })
            relationship["observed_geography_levels"] = sorted({
                point["geography_level"] for point in matches
            })
            relationship["observed_metric_units"] = {
                label: sorted({
                    f"{point.get('unit') or 'unresolved'}:"
                    f"{point.get('unit_status') or 'unresolved'}"
                    for point in matches
                    if point["metric_label"] == label
                })
                for label in sorted(labels)
            }
            relationship["eligible_source_record_count"] = len(matches)
    return enriched


def build_contextualization_report(
    runs: Sequence[Mapping[str, Any]],
    kpi_documents: Sequence[Mapping[str, Any]],
    table_documents: Sequence[Mapping[str, Any]],
    baselines: Sequence[Mapping[str, Any]],
    *,
    assessed_at: datetime | None = None,
    data_health_report: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    assessed_at = assessed_at or datetime.now(timezone.utc)
    if assessed_at.tzinfo is None:
        assessed_at = assessed_at.replace(tzinfo=timezone.utc)
    assessed_at = assessed_at.astimezone(timezone.utc)
    points, source_summary = prepare_source_points(
        runs,
        kpi_documents,
        table_documents,
        as_of_date=assessed_at.date(),
    )
    scoped_findings, health_summary = _health_context(data_health_report)
    _attach_quality_findings(points, scoped_findings)
    trends = _trend_series(points)
    channel_findings, channel_summary = compare_cross_channel_trends(trends)
    suggestions = generate_finscope_suggestions(
        baselines,
        trends,
        channel_findings,
        health_summary,
    )
    public_trends = [
        {key: value for key, value in trend.items() if key != "observations"}
        for trend in trends
        if trend.get("observation_count", 0) >= MIN_TREND_OBSERVATIONS
    ]
    trend_coverage: dict[str, dict[str, int]] = defaultdict(
        lambda: defaultdict(int)
    )
    for trend in trends:
        trend_coverage[str(trend["page"])][
            str(trend["evidence_sufficiency_state"])
        ] += 1
    return {
        "assessment": {
            "name": "FinScope contextualization and NBR cross-channel assessment",
            "model_version": MODEL_VERSION,
            **source_revision_metadata(),
            "assessment_timestamp": assessed_at.isoformat(),
            "source_domains": ["FinScope survey", "NBR administrative observations"],
            "sources_fitted_or_evaluated_separately": True,
            "FinScope_reference_period": FINSCOPE_REFERENCE_PERIOD,
            "FinScope_population": FINSCOPE_POPULATION,
            "FinScope_weight": FINSCOPE_WEIGHT,
            "FinScope_baseline_not_recomputed": True,
            "NBR_data_read_only": True,
            "NBR_reporting_date_field": "snapshot_date",
            "NBR_collection_timestamp_field": "collected_at",
            "temporal_method": (
                "Observed endpoint and successive direction only; missing periods "
                "are never imputed and administrative observations are not converted "
                "to FinScope percentages."
            ),
            "sufficiency_rules": {
                "insufficient_evidence": (
                    "Fewer than three unique eligible NBR reporting dates; two "
                    "successive changes cannot be observed."
                ),
                "limited_evidence": (
                    "Three or four reporting dates, or any quality qualification, "
                    "or a proxy rather than a contextual indicator."
                ),
                "sufficient_for_directional_assessment": (
                    "At least five unique eligible dates, same exact series scope, "
                    "and no attached quality qualification. This does not imply "
                    "long-term stability or model accuracy."
                ),
            },
            "cross_channel_method": (
                "Compare directions only on shared reporting dates and matched "
                "geography, gender, age-segment, and institution filters. Serialize "
                "the exact aligned observations, including source IDs and filters. "
                "Keep metrics separate; no combined score or causal inference."
            ),
            "suggestion_outcome_policy": (
                "Unresolved proxy relationships remain insufficient_evidence. "
                "Opposing or internally mixed comparable channel directions make "
                "a contextual-indicator suggestion mixed_evidence. Directional "
                "NBR channel signals are not survey-indicator conclusions."
            ),
        },
        "source_data": source_summary,
        "source_quality_assessment": health_summary,
        "indicator_mappings": _enrich_indicator_mappings(points),
        "cross_channel_summary": channel_summary,
        "cross_channel_findings": channel_findings,
        "series_trends": public_trends,
        "series_coverage_by_page": {
            page: dict(counts)
            for page, counts in sorted(trend_coverage.items())
        },
        "suggestion_count": len(suggestions),
        "suggestions": suggestions,
        "limitations": [
            "NBR customer, account, channel, and policy counts have distinct or undocumented meanings and denominators.",
            "District tables and national KPIs are separate sources of aggregation; district rows are not summed into national estimates.",
            "FinScope age bins (16-24, 25-34, 35-44, 45-54, 55-64, 65+) do not match NBR Youth/Non-Youth definitions.",
            "NBR does not expose FinScope education or urban/rural dimensions in the configured data.",
            "The stored history is irregular; repeated-content snapshots and unknown districts are excluded by existing eligibility rules.",
            "No independent labels establish accuracy, precision, recall, or false-positive rates.",
        ],
    }


def _review_queue_report(
    report: Mapping[str, Any],
) -> dict[str, Any]:
    methods: dict[str, dict[str, Any]] = defaultdict(lambda: {"candidates": []})
    for suggestion in report.get("suggestions", []):
        supporting = suggestion.get("supporting_evidence", [])
        if not supporting:
            continue
        evidence = supporting[0]
        points = evidence.get("observations", [])
        latest = points[-1] if points else {}
        method = (
            "finscope_contextualization_"
            + str(suggestion["indicator_variable"])
        )
        candidate = {
            **suggestion,
            "method": method,
            "page": suggestion.get("nbr_page", ""),
            "metric_label": suggestion.get("nbr_metric", ""),
            "district": (
                suggestion.get("geography", "")
                if suggestion.get("analytical_level") == "district"
                else ""
            ),
            "reporting_date": latest.get("reporting_date", ""),
            "collected_at": latest.get("collected_at", ""),
            "run_id": latest.get("run_id", ""),
            "combo_key": latest.get("combo_key", ""),
            "filters": latest.get("filters", {}),
            "observed_value": latest.get("value", ""),
            "reason": suggestion.get("suggested_interpretation", ""),
            "evidence_assessment": {
                "state": suggestion.get("evidence_sufficiency_state", "")
            },
        }
        methods[method]["candidates"].append(candidate)
    return {
        "experiment": {
            "model_version": report["assessment"]["model_version"],
            "assessment_timestamp": report["assessment"]["assessment_timestamp"],
        },
        "evidence_assessment": {
            "model_version": report["assessment"]["model_version"],
            "assessment_timestamp": report["assessment"]["assessment_timestamp"],
        },
        "ranked_review_queues": {"methods": dict(methods)},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--review-csv", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        raise FileExistsError(
            f"Refusing to overwrite existing report: {args.output}"
        )
    runs, kpis, tables = load_mongodb_history()
    baselines = load_finscope_baselines(PROJECT_ROOT / "data" / "processed")
    from src.data_sources.mongodb_data_health import (
        assess_data_health,
        load_expected_data_registry,
    )
    from src.data_sources.mongodb_district_explorer import load_district_reference

    assessed_at = datetime.now(timezone.utc)
    registry = load_expected_data_registry(
        expected_districts=tuple(load_district_reference())
    )
    health_report = assess_data_health(
        runs,
        kpis,
        tables,
        registry=registry,
        as_of=assessed_at,
    )
    report = build_contextualization_report(
        runs,
        kpis,
        tables,
        baselines,
        assessed_at=assessed_at,
        data_health_report=health_report,
    )
    write_json_report_new(
        args.output,
        report,
        default=_json_default,
    )
    review_count = merge_review_queue_csv(
        _review_queue_report(report),
        args.review_csv,
    )
    print(
        f"Wrote {report['suggestion_count']} FinScope contextualization findings "
        f"to {args.output}; merged {review_count} review candidates into "
        f"{args.review_csv}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
