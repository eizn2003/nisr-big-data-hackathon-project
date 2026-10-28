"""Evidence sufficiency and assessment metadata for NBR detector outputs."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from src.models.nbr_intelligence import MODEL_VERSION

SUFFICIENT = "sufficient_for_stated_assessment"
LIMITED = "limited_evidence"
INSUFFICIENT = "insufficient_or_incomparable_evidence"
TEMPORAL_MIN_PRIOR_RATES_FOR_SUFFICIENCY = 11
FRESHNESS_TOLERANCE_DAYS = 8
_PROVENANCE_EXCLUSIONS = {
    "missing_observation_identity",
    "missing_or_ambiguous_collection_run",
    "run_id_mismatch",
    "run_filter_key_mismatch",
    "run_filter_values_mismatch",
}


def _health_findings(
    health_report: Mapping[str, Any] | None,
) -> tuple[dict[str, list[Mapping[str, Any]]], list[Mapping[str, Any]]]:
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    findings = list((health_report or {}).get("findings", []))
    for finding in findings:
        if not isinstance(finding, Mapping):
            continue
        grouped.setdefault(str(finding.get("check", "")), []).append(finding)
    return grouped, findings


def _health_state(findings: Sequence[Mapping[str, Any]]) -> str:
    if not findings:
        return INSUFFICIENT
    statuses = {str(finding.get("status", "")) for finding in findings}
    if statuses == {"supported"}:
        return SUFFICIENT
    if "not_assessable" in statuses and statuses <= {"not_assessable"}:
        return INSUFFICIENT
    return LIMITED


def _safe_evidence(finding: Mapping[str, Any]) -> dict[str, Any]:
    raw = finding.get("evidence")
    if not isinstance(raw, Mapping):
        return {}
    allowed = (
        "page",
        "page_id",
        "reporting_date",
        "snapshot_date",
        "status",
        "age_days",
        "tolerance_days",
        "missing_pages",
        "missing_combinations",
        "failed_runs",
        "repeated_snapshots",
        "unknown_district_count",
        "table_sum",
        "kpi_value",
        "difference",
        "reason",
    )
    return {key: raw[key] for key in allowed if key in raw}


def assess_evidence(
    *,
    observations: Sequence[Any],
    runs: Sequence[Mapping[str, Any]],
    table_documents: Sequence[Mapping[str, Any]],
    expected_districts: Sequence[str],
    excluded_rows: Mapping[str, int],
    excluded_values: Mapping[str, int],
    temporal_cases: Sequence[Mapping[str, Any]],
    cross_sectional_summary: Mapping[str, Any],
    cross_sectional_candidates: Sequence[Mapping[str, Any]],
    health_report: Mapping[str, Any] | None,
    assessed_at: datetime | None = None,
) -> dict[str, Any]:
    """Assess evidence quality without treating sufficiency as model accuracy."""
    now = assessed_at or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)

    reporting_dates = sorted({
        item.reporting_date.isoformat() for item in observations
    })
    collection_timestamps = sorted({
        item.collected_at for item in observations if item.collected_at
    })
    latest_collection = None
    if collection_timestamps:
        latest_collection = max(collection_timestamps)
    latest_collection_age_days = None
    if latest_collection:
        try:
            parsed = datetime.fromisoformat(
                latest_collection.replace("Z", "+00:00")
            )
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            latest_collection_age_days = (
                now - parsed.astimezone(timezone.utc)
            ).total_seconds() / 86400
        except ValueError:
            latest_collection_age_days = None

    provenance_exclusions = {
        key: count
        for key, count in excluded_rows.items()
        if key in _PROVENANCE_EXCLUSIONS and count
    }
    has_observations = bool(observations)
    provenance_state = (
        INSUFFICIENT if not has_observations
        else LIMITED if provenance_exclusions
        else SUFFICIENT
    )
    comparability_state = (
        SUFFICIENT
        if cross_sectional_summary.get("assessable_groups", 0)
        or temporal_cases
        else INSUFFICIENT
    )

    health_by_check, all_health_findings = _health_findings(health_report)
    freshness_findings = health_by_check.get("freshness", [])
    completeness_findings = health_by_check.get("collection_completeness", [])
    geographic_findings = health_by_check.get("geographic_coverage", [])
    freshness_state = _health_state(freshness_findings)
    completeness_state = _health_state(completeness_findings)
    geographic_state = _health_state(geographic_findings)

    temporal_scored = [
        case for case in temporal_cases
        if case.get("model_status") == "scored"
    ]
    temporal_abstentions = [
        case for case in temporal_cases
        if case.get("model_status") != "scored"
    ]
    temporal_prior_rates = [
        int(case.get("training_rate_count", 0))
        for case in temporal_scored
    ]
    if not temporal_scored:
        temporal_state = INSUFFICIENT
        temporal_reason = (
            "No temporal case met the detector's minimum prior-rate requirement."
        )
    elif min(temporal_prior_rates) >= TEMPORAL_MIN_PRIOR_RATES_FOR_SUFFICIENCY:
        temporal_state = SUFFICIENT
        temporal_reason = (
            "Scored cases have at least 11 prior independent daily-rate observations."
        )
    else:
        temporal_state = LIMITED
        temporal_reason = (
            "The detector can score cases with three prior rates, but current history "
            "does not meet the 11-rate evidence threshold; five reporting dates do "
            "not establish long-term behavior."
        )

    expected_count = len(expected_districts)
    cross_minimum = int(cross_sectional_summary.get("minimum_peer_districts", 10))
    assessable_groups = int(cross_sectional_summary.get("assessable_groups", 0))
    insufficient_cross_groups = int(
        cross_sectional_summary.get("groups_too_small", 0)
        + cross_sectional_summary.get("groups_with_zero_mad", 0)
    )
    if assessable_groups == 0:
        cross_state = INSUFFICIENT
        cross_reason = (
            "No peer group met the minimum distinct-district and nonzero-MAD rules."
        )
    elif not expected_count:
        cross_state = LIMITED
        cross_reason = "No expected-district reference was available to assess coverage."
    elif (
        int(cross_sectional_summary.get("groups_with_coverage_qualifications", 0))
        or cross_sectional_summary.get("groups_with_reconciliation_qualifications", 0)
    ):
        cross_state = LIMITED
        cross_reason = (
            "Peer comparisons are calculable, but some scopes have incomplete geography "
            "or tentative reconciliation findings."
        )
    else:
        cross_state = SUFFICIENT
        cross_reason = (
            "The assessed peer groups meet the minimum size, expected geography, and "
            "available quality checks; this supports comparison only, not a causal or "
            "service-gap conclusion."
        )

    digest_payload = [
        {
            "page": item.page,
            "metric_label": item.metric_label,
            "district": item.district,
            "reporting_date": item.reporting_date.isoformat(),
            "collected_at": item.collected_at,
            "run_id": item.run_id,
            "combo_key": item.combo_key,
            "value": item.value,
        }
        for item in observations
    ]
    observation_digest = hashlib.sha256(
        json.dumps(
            digest_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    health_counts = Counter(
        (str(finding.get("check", "")), str(finding.get("status", "")))
        for finding in all_health_findings
        if isinstance(finding, Mapping)
    )
    data_quality_findings = []
    for finding in all_health_findings:
        if not isinstance(finding, Mapping):
            continue
        if finding.get("status") in {"supported", "not_assessable"}:
            continue
        data_quality_findings.append({
            "check": finding.get("check"),
            "status": finding.get("status"),
            "message": finding.get("message"),
            "evidence": _safe_evidence(finding),
        })

    return {
        "model_version": MODEL_VERSION,
        "assessment_timestamp": now.isoformat(),
        "source": "NBR administrative observations only",
        "finscope_used": False,
        "evidence_period": {
            "reporting_dates": reporting_dates,
            "independent_reporting_date_count": len(reporting_dates),
            "latest_collection_timestamp": latest_collection,
            "latest_collection_age_days": latest_collection_age_days,
        },
        "eligible_population": {
            "observation_count": len(observations),
            "run_record_count": len(runs),
            "source_table_document_count": len(table_documents),
            "page_count": len({item.page for item in observations}),
            "comparable_series_count": len({
                (
                    item.page,
                    item.metric_label,
                    item.district.casefold(),
                    item.combo_key,
                )
                for item in observations
            }),
            "expected_district_count": expected_count or None,
            "eligible_observations_sha256": observation_digest,
        },
        "evidence_checks": {
            "availability": {
                "state": SUFFICIENT if has_observations else INSUFFICIENT,
                "eligible_observation_count": len(observations),
            },
            "provenance": {
                "state": provenance_state,
                "rejected_records_by_reason": provenance_exclusions,
            },
            "comparability": {
                "state": comparability_state,
                "policy": [
                    "Keep page, metric label, district, reporting date, and canonical filters separate.",
                    "Do not treat collection timestamp as reporting date.",
                    "Do not impute unknown or missing geography as zero.",
                ],
            },
            "completeness": {
                "state": completeness_state,
                "health_findings": [
                    {
                        "status": item.get("status"),
                        "message": item.get("message"),
                    }
                    for item in completeness_findings
                ],
            },
            "geographic_coverage": {
                "state": geographic_state,
                "expected_district_count": expected_count or None,
            },
            "freshness": {
                "state": freshness_state,
                "collection_timestamp_age_days": latest_collection_age_days,
                "tolerance_days": FRESHNESS_TOLERANCE_DAYS,
                "health_findings": [
                    {
                        "status": item.get("status"),
                        "message": item.get("message"),
                    }
                    for item in freshness_findings
                ],
            },
            "excluded_rows_by_reason": dict(excluded_rows),
            "excluded_values_by_reason": dict(excluded_values),
        },
        "task_assessments": {
            "cross_sectional_district_disparity": {
                "state": cross_state,
                "reason": cross_reason,
                "assessable_peer_groups": assessable_groups,
                "candidate_count": len(cross_sectional_candidates),
                "minimum_peer_districts": cross_minimum,
                "groups_not_assessable": insufficient_cross_groups,
                "groups_with_geographic_qualifications": int(
                    cross_sectional_summary.get(
                        "groups_with_coverage_qualifications",
                        0,
                    )
                ),
                "method": "cross-sectional modified robust z-score",
                "interpretation_boundary": (
                    "A peer disparity is not proof of an error, service gap, or causal barrier."
                ),
            },
            "temporal_change": {
                "state": temporal_state,
                "reason": temporal_reason,
                "scored_cases": len(temporal_scored),
                "abstained_cases": len(temporal_abstentions),
                "minimum_prior_rates_for_current_detector": 3,
                "prior_rates_for_sufficient_evidence": (
                    TEMPORAL_MIN_PRIOR_RATES_FOR_SUFFICIENCY
                ),
                "method": "walk-forward per-series median/MAD of daily log changes",
            },
            "data_quality_inconsistency": {
                "state": (
                    LIMITED if data_quality_findings else
                    SUFFICIENT if health_report else INSUFFICIENT
                ),
                "finding_count": len(data_quality_findings),
                "counts_by_check_and_status": {
                    f"{check}:{status}": count
                    for (check, status), count in sorted(health_counts.items())
                },
                "findings": data_quality_findings[:100],
                "truncated": len(data_quality_findings) > 100,
                "tentative_reconciliation_scope_count": int(
                    cross_sectional_summary.get(
                        "tentative_reconciliation_scope_count",
                        0,
                    )
                ),
            },
            "model_evaluation": {
                "state": INSUFFICIENT,
                "reason": (
                    "No independently adjudicated outcomes are available. Detector "
                    "agreement and evidence sufficiency are not accuracy measures."
                ),
                "independent_labels_available": False,
                "accuracy_metrics": None,
            },
        },
        "adaptation": {
            "new_observations": (
                "The next assessment reloads eligible MongoDB history and recomputes "
                "the deterministic statistical references; no model artifact is persisted."
            ),
            "unsupervised_refit": (
                "Robust medians/MADs are recomputed from eligible historical NBR observations "
                "during each assessment."
            ),
            "human_feedback": (
                "Reviewer fields are maintained separately in the CSV; no candidate "
                "prediction is used as a label."
            ),
            "trained_model_added": False,
            "reason": (
                "Only five irregular reporting dates, no adjudicated labels, incompatible "
                "metrics/scopes, and no scikit-learn dependency; the existing robust "
                "detectors are the defensible current baselines."
            ),
        },
    }


def attach_candidate_evidence(
    temporal_cases: Sequence[dict[str, Any]],
    cross_sectional_candidates: Sequence[dict[str, Any]],
    *,
    temporal_sufficiency_rates: int = TEMPORAL_MIN_PRIOR_RATES_FOR_SUFFICIENCY,
) -> None:
    """Attach task-specific evidence states to candidate source records."""
    for candidate in cross_sectional_candidates:
        peer_count = int(candidate.get("comparison_district_count", 0))
        expected_count = candidate.get("expected_district_count")
        qualifications = candidate.get("quality_qualifications", [])
        if peer_count < 10:
            state = INSUFFICIENT
            reason = "The peer group is smaller than the detector's minimum."
        elif expected_count is None:
            state = LIMITED
            reason = "Expected geographic coverage could not be verified."
        elif peer_count < int(expected_count) or qualifications:
            state = LIMITED
            reason = (
                "The peer comparison is calculable, but geography or data-quality "
                "qualifications remain."
            )
        else:
            state = SUFFICIENT
            reason = (
                "The exact-scope peer comparison meets the configured size and coverage "
                "checks; this does not establish accuracy or causation."
            )
        candidate["model_version"] = MODEL_VERSION
        candidate["evidence_assessment"] = {
            "question": "cross_sectional_district_disparity",
            "state": state,
            "reason": reason,
            "eligible_peer_count": peer_count,
            "expected_district_count": expected_count,
        }

    for case in temporal_cases:
        rates = int(case.get("training_rate_count", 0))
        if case.get("model_status") != "scored":
            state = INSUFFICIENT
            if case.get("model_dispersion_status") == "zero":
                reason = (
                    "The detector abstained because prior daily rates have zero MAD; "
                    "no nonzero historical scale is available."
                )
            elif (
                case.get("model_dispersion_status")
                == "below_floating_point_resolution"
            ):
                reason = (
                    "The detector abstained because the nonzero historical MAD is no "
                    "larger than the propagated floating-point resolution bound."
                )
            elif (
                case.get("model_dispersion_status")
                == "discordant_training_rates"
            ):
                reason = (
                    "The detector abstained because at least one prior daily rate "
                    "crosses the configured robust-score threshold, leaving the "
                    "historical dispersion internally discordant."
                )
            else:
                reason = (
                    "The detector abstained because the minimum prior-rate evidence "
                    "was unavailable."
                )
        elif rates >= temporal_sufficiency_rates:
            state = SUFFICIENT
            reason = (
                "The series meets the documented prior-rate evidence floor; this is not "
                "a claim of predictive accuracy."
            )
        else:
            state = LIMITED
            reason = (
                "The score is computable but based on fewer than 11 prior rates; "
                "interpret as an experimental review signal only."
            )
        case["model_version"] = MODEL_VERSION
        case["evidence_assessment"] = {
            "question": "temporal_change",
            "state": state,
            "reason": reason,
            "eligible_prior_rate_count": rates,
        }
