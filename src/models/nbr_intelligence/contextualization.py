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
    if len(set(dates)) != len(dates):
        return {
            "direction": "not_assessable",
            "evidence_sufficiency_state": "not_comparable",
            "reason": "Multiple observations share a reporting date in this series.",
            "observations": ordered,
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
        "source_record_ids": [
            str(point.get("source_record_id", "")) for point in ordered
        ],
        "observations": ordered,
        "quality_qualifications": [
            qualification
            for point in ordered
            for qualification in point.get("quality_qualifications", [])
        ],
    }


def _channel_scope(trend: Mapping[str, Any]) -> tuple[str, ...] | None:
    observations = trend.get("observations", [])
    if not observations:
        return None
    filters = observations[0].get("filters", {})
    if not isinstance(filters, Mapping):
        return None

    if any(
        key not in _METADATA_FILTERS
        and str(value).strip().casefold() != "all"
        and not (
            "status" in str(key).casefold()
            and str(value).strip().casefold() == "active"
        )
        for key, value in filters.items()
    ):
        return None
    return (
        str(trend.get("geography_level", "")),
        str(trend.get("geography", "")),
        str(filters.get("Gender", "All")).strip().casefold(),
        str(filters.get("Age Segment", "All")).strip().casefold(),
        str(filters.get("Institution Type", "All")).strip().casefold(),
    )


def compare_cross_channel_trends(
    trends: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Compare two distinct channel series at a time on aligned dates and scope."""
    grouped: dict[tuple[str, ...], list[Mapping[str, Any]]] = defaultdict(list)
    for trend in trends:
        page = str(trend.get("page", ""))
        channel_class = CHANNEL_CLASSES.get(page)
        if channel_class is None:
            continue
        scope = _channel_scope(trend)
        if scope is not None:
            grouped[scope].append(trend)

    findings = []
    for scope, scope_trends in sorted(grouped.items()):
        by_page: dict[str, Mapping[str, Any]] = {}
        for trend in scope_trends:
            page = str(trend["page"])
            if page not in by_page or len(trend.get("reporting_dates", [])) > len(
                by_page[page].get("reporting_dates", [])
            ):
                by_page[page] = trend
        page_trends = list(by_page.values())
        for index, first in enumerate(page_trends):
            for second in page_trends[index + 1:]:
                first_dates = {
                    str(point["reporting_date"]): point
                    for point in first.get("observations", [])
                }
                second_dates = {
                    str(point["reporting_date"]): point
                    for point in second.get("observations", [])
                }
                common_dates = sorted(set(first_dates) & set(second_dates))
                if len(common_dates) < MIN_TREND_OBSERVATIONS:
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
                        "geography_level": trend["geography_level"],
                        "geography": trend["geography"],
                        "source_record_ids": aligned_trend["source_record_ids"],
                    })
                directions = {item["direction"] for item in aligned}
                classes = {item["channel_class"] for item in aligned}
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
                    "channels": aligned,
                    "missing_channel_pages": sorted(
                        set(CHANNEL_CLASSES) - {
                            str(trend["page"]) for trend in page_trends
                        }
                    ),
                    "interpretation": (
                        "These two channel series moved in the stated directions "
                        "on shared reporting dates. This pattern does not establish "
                        "substitution, access, usage, or causality."
                    ),
                    "limitations": [
                        "No counts, rates, transactions, or customers are added together.",
                        "Only common reporting dates and compatible common filters are compared.",
                        "Page-specific active-status and All filters remain visible per channel.",
                        "A district or subgroup result is not generalized to other populations.",
                    ],
                })

    return findings, {
        "channel_series_count": sum(
            trend.get("page") in CHANNEL_CLASSES for trend in trends
        ),
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
                outcome, interpretation = _suggestion_outcome(
                    polarity,
                    str(trend["direction"]),
                )
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

                scope_filters = trend["filters"]
                group_key = (
                    trend["geography_level"],
                    trend["geography"],
                    str(scope_filters.get("Gender", "All")).casefold(),
                    str(scope_filters.get("Age Segment", "All")).casefold(),
                    str(scope_filters.get("Institution Type", "All")).casefold(),
                )
                related_channel_findings = [
                    finding for finding in cross_channel_findings
                    if (
                        finding["analytical_level"],
                        finding["geography"],
                        finding["gender_filter"],
                        finding["age_segment_filter"],
                        finding["institution_type_filter"],
                    ) == group_key
                ]
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
                    "evidence_sufficiency_state": sufficiency,
                    "suggested_interpretation": interpretation,
                    "supporting_evidence": [supporting],
                    "contradictory_or_missing_evidence": [
                        finding["pattern"] for finding in related_channel_findings
                        if finding["pattern"] in {
                            "possible_channel_substitution",
                            "mixed_trends",
                        }
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
                "geography, gender, age-segment, and institution filters. Keep "
                "metrics separate; no combined score or causal inference."
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
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=_json_default) + "\n",
        encoding="utf-8",
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
