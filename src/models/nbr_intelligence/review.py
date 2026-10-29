"""Human-review queue serialization and preservation."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping

REVIEW_FIELDS = (
    "candidate_id",
    "assessment_id",
    "model_version",
    "evidence_sufficiency_state",
    "candidate_current",
    "assessment_timestamp",
    "method",
    "page",
    "metric_label",
    "district",
    "reporting_date",
    "collected_at",
    "run_id",
    "combo_key",
    "filters_json",
    "observed_value",
    "comparison_reference_json",
    "score",
    "signed_score",
    "threshold",
    "direction",
    "observed_change_direction",
    "reason",
    "quality_qualifications_json",
    "original_candidate_json",
    "review_status",
    "reviewer",
    "reviewer_disposition",
    "reviewer_rationale",
    "supporting_source_evidence",
    "review_timestamp",
)
HUMAN_REVIEW_FIELDS = (
    "review_status",
    "reviewer",
    "reviewer_disposition",
    "reviewer_rationale",
    "supporting_source_evidence",
    "review_timestamp",
)


def _candidate_identity(method: str, candidate: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "method": method,
        "page": candidate.get("page"),
        "metric_label": candidate.get("metric_label"),
        "district": candidate.get("district"),
        "reporting_date": candidate.get("reporting_date"),
        "combo_key": candidate.get("combo_key"),
        "run_id": candidate.get("run_id"),
    }


def _candidate_id(method: str, candidate: Mapping[str, Any]) -> str:
    serialized = json.dumps(
        _candidate_identity(method, candidate),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:20]


def _candidate_row(
    method: str,
    candidate: Mapping[str, Any],
    *,
    assessment_id: str,
    assessment_timestamp: str,
    model_version: str,
) -> dict[str, str]:
    comparison_reference = {
        key: value
        for key, value in candidate.items()
        if key in {
            "previous",
            "historical_training_observations",
            "peer_median",
            "peer_mad",
            "baseline_median_daily_rate",
            "baseline_mad_daily_rate",
            "baseline_median",
            "baseline_mad",
            "elapsed_days",
            "sensitivity_1pct",
            "sensitivity_plus_minus_1pct",
            "comparison_district_count",
        }
    }
    return {
        "candidate_id": _candidate_id(method, candidate),
        "assessment_id": assessment_id,
        "model_version": str(model_version),
        "evidence_sufficiency_state": str(
            candidate.get("evidence_assessment", {}).get("state", "")
        ),
        "candidate_current": "true",
        "assessment_timestamp": assessment_timestamp,
        "method": method,
        "page": str(candidate.get("page", "")),
        "metric_label": str(candidate.get("metric_label", "")),
        "district": str(candidate.get("district", "")),
        "reporting_date": str(candidate.get("reporting_date", "")),
        "collected_at": str(candidate.get("collected_at", "")),
        "run_id": str(candidate.get("run_id", "")),
        "combo_key": str(candidate.get("combo_key", "")),
        "filters_json": json.dumps(
            candidate.get("filters", {}),
            ensure_ascii=False,
            sort_keys=True,
        ),
        "observed_value": str(candidate.get("observed_value", "")),
        "comparison_reference_json": json.dumps(
            comparison_reference,
            ensure_ascii=False,
            sort_keys=True,
        ),
        "score": str(candidate.get(
            "absolute_robust_score",
            candidate.get("score", ""),
        )),
        "signed_score": str(candidate.get("signed_score", "")),
        "threshold": str(candidate.get("threshold", "")),
        "direction": str(candidate.get("direction", "")),
        "observed_change_direction": str(
            candidate.get("observed_change_direction", "")
        ),
        "reason": str(candidate.get("reason", "")),
        "quality_qualifications_json": json.dumps(
            candidate.get("quality_qualifications", []),
            ensure_ascii=False,
            sort_keys=True,
        ),
        "original_candidate_json": json.dumps(
            candidate,
            ensure_ascii=False,
            sort_keys=True,
        ),
        "review_status": "pending",
        "reviewer": "",
        "reviewer_disposition": "",
        "reviewer_rationale": "",
        "supporting_source_evidence": "",
        "review_timestamp": "",
    }


def _queue_rows(report: Mapping[str, Any]) -> tuple[list[dict[str, str]], str, str]:
    assessment = report.get("evidence_assessment", {})
    timestamp = str(assessment.get(
        "assessment_timestamp",
        report.get("experiment", {}).get("assessment_timestamp", ""),
    ))
    version = str(assessment.get(
        "model_version",
        report.get("experiment", {}).get("model_version", ""),
    ))
    assessment_id = f"{version}:{timestamp}"
    rows = []
    for method, queue in report.get("ranked_review_queues", {}).get(
        "methods", {}
    ).items():
        for candidate in queue.get("candidates", []):
            rows.append(_candidate_row(
                method,
                candidate,
                assessment_id=assessment_id,
                assessment_timestamp=timestamp,
                model_version=version,
            ))
    return rows, assessment_id, timestamp


def write_review_queue_csv(report: Mapping[str, Any], output_path: Path) -> int:
    """Write a fresh pending-only CSV; use merge for a persistent review artifact."""
    rows, _, _ = _queue_rows(report)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(output_path, rows, REVIEW_FIELDS)
    return len(rows)


def merge_review_queue_csv(report: Mapping[str, Any], output_path: Path) -> int:
    """Update candidate evidence while preserving every saved reviewer decision."""
    new_rows, _, _ = _queue_rows(report)
    old_rows: dict[str, dict[str, str]] = {}
    old_fields: list[str] = []
    if output_path.exists():
        with output_path.open(encoding="utf-8-sig", newline="") as source:
            reader = csv.DictReader(source)
            if not reader.fieldnames or "candidate_id" not in reader.fieldnames:
                raise ValueError(
                    f"Existing review CSV has no candidate_id column: {output_path}"
                )
            old_fields = list(reader.fieldnames)
            for row in reader:
                candidate_id = row.get("candidate_id", "")
                if not candidate_id:
                    raise ValueError(
                        f"Existing review CSV contains a row without candidate_id: {output_path}"
                    )
                if candidate_id in old_rows:
                    raise ValueError(
                        f"Existing review CSV has duplicate candidate_id {candidate_id}: "
                        f"{output_path}"
                    )
                old_rows[candidate_id] = {
                    key: value or "" for key, value in row.items() if key is not None
                }

    merged: dict[str, dict[str, str]] = {}
    for row in new_rows:
        candidate_id = row["candidate_id"]
        previous = old_rows.pop(candidate_id, None)
        if previous is not None:
            for field in HUMAN_REVIEW_FIELDS:
                row[field] = previous.get(field, row[field])
        merged[candidate_id] = row

    # Keep reviewed records that are no longer in the truncated current queues.
    for candidate_id, previous in old_rows.items():
        previous["candidate_current"] = "false"
        merged[candidate_id] = previous

    fieldnames = list(dict.fromkeys([*REVIEW_FIELDS, *old_fields]))
    ordered_rows = [merged[key] for key in sorted(merged)]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(output_path, ordered_rows, fieldnames)
    return len(new_rows)


def _atomic_write(
    output_path: Path,
    rows: list[Mapping[str, Any]],
    fieldnames: list[str] | tuple[str, ...],
) -> None:
    temporary_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8-sig",
            newline="",
            dir=output_path.parent,
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as output_file:
            temporary_path = output_file.name
            writer = csv.DictWriter(
                output_file,
                fieldnames=fieldnames,
                extrasaction="ignore",
            )
            writer.writeheader()
            writer.writerows(rows)
        os.replace(temporary_path, output_path)
    finally:
        if temporary_path and os.path.exists(temporary_path):
            os.unlink(temporary_path)
