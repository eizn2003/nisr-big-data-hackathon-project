"""Read-only assessment of the existing NBR collection history."""

from __future__ import annotations

import argparse
import json
import os
import statistics
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from src.data_sources.mongodb_district_explorer import (
    CHANGE_REVIEW_THRESHOLD_PERCENT,
    DATABASE_NAME,
    KPI_COLLECTION,
    RUN_COLLECTION,
    TABLE_COLLECTION,
    parse_numeric_value,
)
from src.data_sources.mongodb_district_explorer import APPROVED_MAPPINGS, NO_RELEVANT_NBR_DATA
from src.indicators import REGISTRY as FINSCOPE_INDICATORS

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "nbr_pages.json"
EXPECTED_FREQUENCY = "weekly"
EXPECTED_SCHEDULE = "Tuesday 15:23 UTC primary; Tuesday 17:41 UTC backup"
FRESHNESS_TOLERANCE_DAYS = 8
MIN_BASELINE_REPORTING_DATES = 3
SUPPORTED, TENTATIVE, INCOMPLETE, NOT_ASSESSABLE = (
    "supported",
    "tentative",
    "incomplete",
    "not_assessable",
)

_RECONCILIABLE_METRICS = {
    "branches": ("Branches", "Total Branches"),
    "pos": ("POS", "Total POS"),
    "agents": ("Agents", "Total Agents"),
}
_DISTRICT_COLUMN_NAMES = {"district", "district name"}


@dataclass(frozen=True)
class ExpectedPage:
    page_id: str
    title: str
    url: str
    filters: tuple[dict[str, Any], ...]
    expected_combinations: int | None
    dimensions: dict[str, dict[str, Any]]
    approved_metric_mappings: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class ExpectedDataRegistry:
    source: str
    pages: tuple[ExpectedPage, ...]
    collection_frequency: str
    collection_schedule: str
    freshness_tolerance_days: int
    reporting_date_field: str
    collection_timestamp_field: str
    finscope: dict[str, Any]
    unsupported_nbr_dimensions: dict[str, str]
    expected_districts: tuple[str, ...] = ()


@dataclass(frozen=True)
class HealthFinding:
    check: str
    status: str
    message: str
    evidence: dict[str, Any]


def _expected_combinations(filters: list[dict[str, Any]]) -> int | None:
    combinations = 1
    for spec in filters:
        if spec.get("ignore") or spec.get("fixed") is not None:
            continue
        count = spec.get("expected_count")
        if not isinstance(count, int) or count < 1:
            return None
        combinations *= count
    return combinations


def _dimension_expectations(filters: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result = {}
    for dimension, config_label in (("Gender", "Gender"), ("Age", "Age Segment")):
        spec = next(
            (item for item in filters if item.get("label") == config_label),
            None,
        )
        if spec is None or spec.get("ignore"):
            result[dimension] = {
                "status": "unsupported",
                "filter_label": config_label,
                "reason": "The page configuration does not collect this dimension.",
            }
        elif spec.get("fixed") is not None:
            result[dimension] = {
                "status": "fixed",
                "filter_label": config_label,
                "configured_value": spec["fixed"],
            }
        else:
            result[dimension] = {
                "status": "configured_requires_observation_verification",
                "filter_label": config_label,
                "expected_option_count": spec.get("expected_count"),
            }
    result["Education"] = {
        "status": "unsupported",
        "reason": "NBR does not provide an education breakdown.",
    }
    result["Area"] = {
        "status": "unsupported",
        "reason": "The NBR dashboard does not provide the FinScope urban/rural area breakdown.",
    }
    return result


def load_expected_data_registry(
    config_path: Path | None = None,
    expected_districts: tuple[str, ...] = (),
) -> ExpectedDataRegistry:
    """Build expectations from the scraper config and existing source definitions."""
    path = config_path or DEFAULT_CONFIG
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not load NBR page configuration {path}: {exc}") from exc

    mappings_by_page: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for mapping in APPROVED_MAPPINGS:
        mappings_by_page[mapping.page_id].append(
            {
                "indicator_variable": mapping.indicator_variable,
                "indicator_label": mapping.indicator_label,
                "filters": dict(mapping.filters),
                "kpi_labels": list(mapping.kpi_labels),
                "table_labels": list(mapping.table_labels),
                "status": mapping.status,
                "relevance": mapping.relevance,
                "limitations": mapping.limitations,
            }
        )

    pages = []
    for page_id, page in config.get("pages", {}).items():
        filters = page.get("filters", [])
        pages.append(
            ExpectedPage(
                page_id=page_id,
                title=page.get("title", page_id),
                url=page.get("url", ""),
                filters=tuple(dict(spec) for spec in filters),
                expected_combinations=_expected_combinations(filters),
                dimensions=_dimension_expectations(filters),
                approved_metric_mappings=tuple(mappings_by_page.get(page_id, ())),
            )
        )
    if not pages:
        raise ValueError(f"No NBR pages are configured in {path}.")

    return ExpectedDataRegistry(
        source="NBR Financial Inclusion Dashboard",
        pages=tuple(pages),
        collection_frequency=EXPECTED_FREQUENCY,
        collection_schedule=EXPECTED_SCHEDULE,
        freshness_tolerance_days=FRESHNESS_TOLERANCE_DAYS,
        reporting_date_field="snapshot_date",
        collection_timestamp_field="collected_at",
        finscope={
            "source": "FinScope Rwanda 2024",
            "indicators": [
                {
                    "variable": item["variable"],
                    "label": item["label"],
                    "column": item["column"],
                    "definition": item["description"],
                }
                for item in FINSCOPE_INDICATORS
            ],
            "dimensions": {
                "Gender": {"source_variable": "b2", "source": "FinScope"},
                "Age group": {"source_variable": "b1", "source": "FinScope"},
                "Education": {"source_variable": "c4a", "source": "FinScope"},
                "Area": {"source_variable": "a6", "source": "FinScope"},
            },
            "nbr_mappings_no_data": dict(NO_RELEVANT_NBR_DATA),
        },
        unsupported_nbr_dimensions={
            "Education": "NBR does not provide an education breakdown.",
            "Area": "NBR does not provide the FinScope urban/rural area breakdown.",
        },
        expected_districts=tuple(expected_districts),
    )


def _datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, datetime.min.time())
    elif isinstance(value, str) and value.strip():
        if "T" not in value and " " not in value:
            return None
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _reporting_date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _finding(check: str, status: str, message: str, **evidence: Any) -> HealthFinding:
    return HealthFinding(check, status, message, evidence)


def _run_key(record: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        str(record.get("page", "")),
        str(record.get("snapshot_date", "")),
        str(record.get("combo_key", "")),
    )


def _run_id(record: Mapping[str, Any]) -> str:
    return str(record.get("run_id", ""))


def _historical_period_coverage(
    runs: list[dict[str, Any]],
    kpi_documents: list[dict[str, Any]],
    table_documents: list[dict[str, Any]],
    pages: Mapping[str, ExpectedPage],
) -> list[dict[str, Any]]:
    periods: dict[date, list[dict[str, Any]]] = defaultdict(list)
    for run in runs:
        reporting_date = _reporting_date(run.get("snapshot_date"))
        if reporting_date is not None:
            periods[reporting_date].append(run)

    kpis_by_key = {_run_key(document): document for document in kpi_documents}
    table_groups = Counter(_run_key(row) for row in table_documents)
    table_columns_by_key: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for row in table_documents:
        table_columns_by_key[_run_key(row)].update(
            str(column) for column in row.get("columns", [])
        )

    summaries = []
    for reporting_date, period_runs in sorted(periods.items()):
        page_runs: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for run in period_runs:
            page_runs[str(run.get("page", ""))].append(run)
        observed_pages = set(page_runs)
        missing_pages = sorted(set(pages) - observed_pages)
        short_pages = {}
        for page_id, expected_page in pages.items():
            expected = expected_page.expected_combinations
            observed_combinations = {
                str(run.get("combo_key", ""))
                for run in page_runs.get(page_id, [])
                if run.get("combo_key")
            }
            if expected is not None and len(observed_combinations) < expected:
                short_pages[page_id] = {
                    "observed_combinations": len(observed_combinations),
                    "expected_combinations": expected,
                }
        failed_runs = [
            {"page": run.get("page"), "status": run.get("status"), "error": run.get("error")}
            for run in period_runs
            if run.get("status") not in {"complete", "completed_no_data", "not_applicable"}
        ]
        missing_kpis = []
        table_row_count_mismatches = []
        missing_required_observations = []
        for run in period_runs:
            if run.get("status") != "complete":
                continue
            key = _run_key(run)
            if key not in kpis_by_key:
                missing_kpis.append(list(key))
            actual_rows = table_groups.get(key, 0)
            expected_rows = run.get("table_rows")
            if isinstance(expected_rows, int) and actual_rows != expected_rows:
                table_row_count_mismatches.append({
                    "page": run.get("page"),
                    "snapshot_date": run.get("snapshot_date"),
                    "combo_key": run.get("combo_key"),
                    "expected_rows": expected_rows,
                    "observed_rows": actual_rows,
                })
            if run.get("table_status") != "extracted":
                missing_required_observations.append({
                    "page": run.get("page"),
                    "snapshot_date": run.get("snapshot_date"),
                    "combo_key": run.get("combo_key"),
                    "required": "extracted table",
                    "observed_status": run.get("table_status"),
                })
            expected_page = pages.get(str(run.get("page", "")))
            if expected_page is None:
                continue
            filters = run.get("filters")
            if not isinstance(filters, Mapping):
                filters = {}
            kpi_document = kpis_by_key.get(key)
            stored_kpi_labels = {
                str(metric.get("metric_label", ""))
                for metric in (kpi_document or {}).get("kpis", [])
            }
            stored_table_labels = table_columns_by_key[key]
            for expectation in expected_page.approved_metric_mappings:
                if not all(
                    filters.get(label) == value
                    for label, value in expectation["filters"].items()
                ):
                    continue
                missing_kpi_labels = sorted(
                    set(expectation["kpi_labels"]) - stored_kpi_labels
                )
                missing_table_labels = sorted(
                    set(expectation["table_labels"]) - stored_table_labels
                )
                if missing_kpi_labels or missing_table_labels:
                    missing_required_observations.append({
                        "page": run.get("page"),
                        "snapshot_date": run.get("snapshot_date"),
                        "combo_key": run.get("combo_key"),
                        "missing_kpi_labels": missing_kpi_labels,
                        "missing_table_labels": missing_table_labels,
                    })
        complete = (
            not missing_pages and not short_pages and not failed_runs
            and not missing_kpis and not table_row_count_mismatches
            and not missing_required_observations
        )
        summaries.append({
            "reporting_date": reporting_date.isoformat(),
            "status": SUPPORTED if complete else INCOMPLETE,
            "run_count": len(period_runs),
            "run_ids": sorted({_run_id(run) for run in period_runs if _run_id(run)}),
            "expected_pages": sorted(pages),
            "observed_pages": sorted(observed_pages),
            "missing_pages": missing_pages,
            "pages_with_fewer_combinations": short_pages,
            "failed_runs": failed_runs,
            "missing_kpi_documents": missing_kpis,
            "table_row_count_mismatches": table_row_count_mismatches,
            "missing_required_observations": missing_required_observations,
        })
    return summaries


def _metric_schema(
    kpi_documents: list[dict[str, Any]],
    table_documents: list[dict[str, Any]],
) -> dict[tuple[str, str, str], tuple[tuple[str, ...], tuple[str, ...]]]:
    labels_by_key: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    columns_by_key: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    keys = set()
    for document in kpi_documents:
        key = _run_key(document)
        keys.add(key)
        labels_by_key[key].update(
            str(metric.get("metric_label", ""))
            for metric in document.get("kpis", [])
            if metric.get("metric_label") is not None
        )
    for row in table_documents:
        key = _run_key(row)
        keys.add(key)
        columns_by_key[key].update(
            str(column) for column in row.get("columns", [])
        )
    return {
        key: (
            tuple(sorted(labels_by_key[key])),
            tuple(sorted(columns_by_key[key])),
        )
        for key in keys
    }


def _geographic_findings(
    table_documents: list[dict[str, Any]],
    expected_districts: tuple[str, ...],
) -> list[HealthFinding]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in table_documents:
        grouped[_run_key(row)].append(row)
    if not grouped:
        return [_finding(
            "geographic_coverage", NOT_ASSESSABLE,
            "No table observations are available to assess geographic coverage.",
        )]
    findings = []
    expected = {name.casefold(): name for name in expected_districts}
    for (page, reporting_date, combo_key), rows in sorted(grouped.items()):
        district_rows = [
            row for row in rows
            if any(
                str(column).strip().casefold() in _DISTRICT_COLUMN_NAMES
                for column in row.get("columns", [])
            )
        ]
        if not district_rows:
            findings.append(_finding(
                "geographic_coverage", NOT_ASSESSABLE,
                "The stored table has no recognized district column.",
                page=page,
                reporting_date=reporting_date,
                combo_key=combo_key,
            ))
            continue
        named = set()
        unknown = []
        unmatched = []
        for row in district_rows:
            values = row.get("values")
            values = values if isinstance(values, Mapping) else {}
            district = str(
                row.get("district")
                if row.get("district") is not None
                else next(
                    (value for key, value in values.items()
                     if str(key).strip().casefold() in _DISTRICT_COLUMN_NAMES),
                    "",
                )
            ).strip()
            normalized = district.casefold()
            if not district or normalized == "unknown" or row.get("district_known") is False:
                unknown.append(district or "<missing>")
            elif expected and normalized not in expected:
                unmatched.append(district)
            else:
                named.add(expected.get(normalized, district))
        missing = sorted(set(expected.values()) - named) if expected else []
        status = TENTATIVE if unknown or unmatched or missing else SUPPORTED
        findings.append(_finding(
            "geographic_coverage", status,
            "District coverage includes gaps or unclassified locations."
            if status == TENTATIVE else "Named district rows match the configured geography reference.",
            page=page,
            reporting_date=reporting_date,
            combo_key=combo_key,
            observed_named_districts=sorted(named),
            missing_districts=missing,
            unknown_rows=unknown,
            unmatched_rows=unmatched,
            expected_district_count=len(expected),
        ))
    return findings


def _schema_findings(
    runs: list[dict[str, Any]],
    kpi_documents: list[dict[str, Any]],
    table_documents: list[dict[str, Any]],
) -> list[HealthFinding]:
    signatures = _metric_schema(kpi_documents, table_documents)
    findings: list[HealthFinding] = []
    grouped: dict[tuple[str, str], list[tuple[str, tuple[tuple[str, ...], tuple[str, ...]]]]] = defaultdict(list)
    for (page, reporting_date, combo_key), signature in signatures.items():
        grouped[(page, combo_key)].append((reporting_date, signature))
    if not grouped:
        findings.append(_finding(
            "schema_consistency", NOT_ASSESSABLE,
            "No stored KPI/table schemas are available.",
        ))
    for (page, combo_key), history in sorted(grouped.items()):
        history.sort(key=lambda item: item[0])
        distinct_dates = {reporting_date for reporting_date, _signature in history}
        latest_date, latest_signature = history[-1]
        if len(distinct_dates) < 2:
            status = NOT_ASSESSABLE
            message = "Only one reporting snapshot is available; schema stability is not assessable."
            baseline_signature = latest_signature
            supporting_snapshots = 1
        else:
            prior_history = [
                (reporting_date, signature)
                for reporting_date, signature in history
                if reporting_date != latest_date
            ]
            signature_counts = Counter(signature for _reporting_date, signature in prior_history)
            baseline_signature, supporting_snapshots = signature_counts.most_common(1)[0]
            if latest_signature != baseline_signature:
                status = TENTATIVE
                message = "The latest KPI labels or table columns differ from the most common historical schema."
            else:
                status = SUPPORTED
                message = "The latest KPI labels and table columns match the most common historical schema."
        findings.append(_finding(
            "schema_consistency",
            status,
            message,
            page=page,
            combo_key=combo_key,
            reporting_dates=sorted(distinct_dates),
            supporting_snapshots=supporting_snapshots,
            latest_reporting_date=latest_date,
            latest_kpi_labels=list(latest_signature[0]),
            latest_table_columns=list(latest_signature[1]),
            baseline_kpi_labels=list(baseline_signature[0]),
            baseline_table_columns=list(baseline_signature[1]),
            schema_expectation_source="observed_history_not_documented_metric_contract",
        ))

    filter_history: dict[str, dict[str, dict[str, set[str]]]] = defaultdict(
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
            filter_history[page][reporting_date][str(label)].add(str(value))
    for page, by_date in sorted(filter_history.items()):
        dates = sorted(by_date)
        if len(dates) < 2:
            findings.append(_finding(
                "schema_consistency",
                NOT_ASSESSABLE,
                "Only one reporting snapshot is available to assess filter and dimension stability.",
                page=page,
                schema_component="filters_and_dimensions",
                reporting_dates=dates,
            ))
            continue
        signatures = {
            reporting_date: {
                label: sorted(values) for label, values in by_date[reporting_date].items()
            }
            for reporting_date in dates
        }
        historical_changes = []
        for previous_date, latest_date in zip(dates, dates[1:]):
            previous = signatures[previous_date]
            latest = signatures[latest_date]
            changed_labels = sorted(
                label
                for label in set(previous) | set(latest)
                if previous.get(label) != latest.get(label)
            )
            if changed_labels:
                historical_changes.append({
                    "previous_reporting_date": previous_date,
                    "latest_reporting_date": latest_date,
                    "changed_filters": {
                        label: {
                            "previous": previous.get(label, []),
                            "latest": latest.get(label, []),
                        }
                        for label in changed_labels
                    },
                })
        previous_date, latest_date = dates[-2], dates[-1]
        previous = signatures[previous_date]
        latest = signatures[latest_date]
        stable = not historical_changes
        findings.append(_finding(
            "schema_consistency",
            SUPPORTED if stable else TENTATIVE,
            "Filter labels and requested categories are unchanged across stored history."
            if stable else "Filter labels or requested categories changed during stored history.",
            page=page,
            schema_component="filters_and_dimensions",
            previous_reporting_date=previous_date,
            latest_reporting_date=latest_date,
            previous_filters=previous,
            latest_filters=latest,
            historical_changes=historical_changes,
        ))
    return findings


def _integrity_findings(
    runs: list[dict[str, Any]],
    kpi_documents: list[dict[str, Any]],
    table_documents: list[dict[str, Any]],
) -> list[HealthFinding]:
    duplicate_run_keys = [
        {"key": list(key), "count": count}
        for key, count in Counter(_run_key(run) for run in runs).items()
        if count > 1
    ]
    duplicate_kpi_keys = [
        {"key": list(key), "count": count}
        for key, count in Counter(_run_key(doc) for doc in kpi_documents).items()
        if count > 1
    ]
    duplicate_table_rows = []
    seen_table_keys = Counter(
        (*_run_key(row), row.get("row_index"))
        for row in table_documents
    )
    duplicate_table_rows = [
        {"key": list(key), "count": count}
        for key, count in seen_table_keys.items()
        if count > 1
    ]
    malformed = []
    missing_reporting_dates = []
    kpi_count_mismatches = []
    table_schema_mismatches = []
    provenance_mismatches = []
    runs_by_key = {_run_key(run): run for run in runs}
    for collection, documents in (("kpi", kpi_documents), ("table", table_documents)):
        for document in documents:
            run = runs_by_key.get(_run_key(document))
            if run is None:
                provenance_mismatches.append({
                    "collection": collection,
                    "key": list(_run_key(document)),
                    "issue": "no_matching_run",
                })
                continue
            if document.get("filters") != run.get("filters"):
                provenance_mismatches.append({
                    "collection": collection,
                    "key": list(_run_key(document)),
                    "issue": "filters_differ_from_run",
                })
            if document.get("filters_requested") != run.get("filters_requested"):
                provenance_mismatches.append({
                    "collection": collection,
                    "key": list(_run_key(document)),
                    "issue": "requested_filters_differ_from_run",
                })
            for field in ("run_id", "date_source", "dashboard_date", "collected_at"):
                document_value = document.get(field)
                run_value = run.get(field)
                if document_value is not None and run_value is not None and document_value != run_value:
                    provenance_mismatches.append({
                        "collection": collection,
                        "key": list(_run_key(document)),
                        "issue": f"{field}_differs_from_run",
                        "document_value": str(document_value),
                        "run_value": str(run_value),
                    })
    for run in runs:
        if (
            run.get("filters_key")
            and run.get("combo_key")
            and run["filters_key"] != run["combo_key"]
        ):
            provenance_mismatches.append({
                "collection": "runs",
                "key": list(_run_key(run)),
                "issue": "filters_key_differs_from_combo_key",
                "filters_key": run.get("filters_key"),
                "combo_key": run.get("combo_key"),
            })
    for document in kpi_documents:
        metrics = document.get("kpis")
        if isinstance(metrics, list) and document.get("kpi_count") not in (None, len(metrics)):
            kpi_count_mismatches.append({
                "key": list(_run_key(document)),
                "stored_count": document.get("kpi_count"),
                "observed_count": len(metrics),
            })
    for row in table_documents:
        columns = row.get("columns")
        values = row.get("values")
        if isinstance(columns, list) and isinstance(values, Mapping):
            missing_columns = [
                column for column in columns
                if column not in values
            ]
            if missing_columns:
                table_schema_mismatches.append({
                    "key": list(_run_key(row)),
                    "row_index": row.get("row_index"),
                    "missing_value_columns": missing_columns,
                })
    for collection, documents in (
        ("runs", runs),
        ("kpi", kpi_documents),
        ("table", table_documents),
    ):
        for index, document in enumerate(documents):
            reporting_date = document.get("snapshot_date")
            try:
                if not isinstance(reporting_date, str):
                    raise ValueError
                date.fromisoformat(reporting_date)
            except ValueError:
                malformed.append({
                    "collection": collection,
                    "index": index,
                    "field": "snapshot_date",
                    "value": reporting_date,
                })
            if not reporting_date:
                missing_reporting_dates.append({"collection": collection, "index": index})
            if document.get("collected_at") is not None and _datetime(document.get("collected_at")) is None:
                malformed.append({
                    "collection": collection,
                    "index": index,
                    "field": "collected_at",
                    "value": str(document.get("collected_at")),
                })
            elif document.get("collected_at") is None:
                malformed.append({
                    "collection": collection,
                    "index": index,
                    "field": "collected_at",
                    "issue": "missing_timestamp",
                })
            if not document.get("run_id") or not document.get("combo_key"):
                malformed.append({
                    "collection": collection,
                    "index": index,
                    "missing_fields": [
                        field for field in ("run_id", "combo_key")
                        if not document.get(field)
                    ],
                })
    problems = bool(
        duplicate_run_keys or duplicate_kpi_keys or duplicate_table_rows
        or malformed or missing_reporting_dates or kpi_count_mismatches
        or table_schema_mismatches or provenance_mismatches
    )
    return [_finding(
        "record_integrity",
        TENTATIVE if problems else SUPPORTED,
        "Duplicate, malformed, or incomplete record keys were found."
        if problems else "No duplicate keys or malformed reporting/collection metadata were found.",
        duplicate_run_keys=duplicate_run_keys,
        duplicate_kpi_keys=duplicate_kpi_keys,
        duplicate_table_rows=duplicate_table_rows,
        malformed_records=malformed,
        missing_reporting_dates=missing_reporting_dates,
        kpi_count_mismatches=kpi_count_mismatches,
        table_schema_mismatches=table_schema_mismatches,
        provenance_mismatches=provenance_mismatches,
    )]


def _value_findings(
    runs: list[dict[str, Any]],
    kpi_documents: list[dict[str, Any]],
    table_documents: list[dict[str, Any]],
) -> tuple[list[HealthFinding], list[dict[str, Any]]]:
    problems = []
    repeated = []
    for run in runs:
        if run.get("repeated_snapshot_warning"):
            repeated.append({
                "page": run.get("page"),
                "snapshot_date": run.get("snapshot_date"),
                "combo_key": run.get("combo_key"),
                "previous_matching_snapshot_date": run.get("previous_matching_snapshot_date"),
            })

    def inspect_value(collection: str, record: Mapping[str, Any], label: str, raw: Any):
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            problems.append({
                "collection": collection,
                "page": record.get("page"),
                "reporting_date": record.get("snapshot_date"),
                "metric_label": label,
                "issue": "missing_value",
                "raw_value": raw,
            })
            return
        numeric = parse_numeric_value(raw)
        if numeric is None:
            return
        is_percent = isinstance(raw, str) and raw.strip().endswith("%")
        known_count = label.strip().casefold() in {
            "agents", "branches", "customers", "policy holders", "pos", "cards",
            "total agents", "total branches", "total customers", "total policy holders",
            "total pos", "total cards",
        }
        if is_percent and not 0 <= numeric <= 100:
            issue = "percentage_outside_documented_bounds"
        elif known_count and numeric < 0:
            issue = "negative_count"
        else:
            return
        problems.append({
            "collection": collection,
            "page": record.get("page"),
            "reporting_date": record.get("snapshot_date"),
            "metric_label": label,
            "issue": issue,
            "raw_value": raw,
        })

    for document in kpi_documents:
        for metric in document.get("kpis", []):
            inspect_value(
                "kpi",
                document,
                str(metric.get("metric_label", "")),
                metric.get("metric_value"),
            )
    for row in table_documents:
        values = row.get("values")
        if isinstance(values, Mapping):
            for label, raw in values.items():
                if str(label).strip().casefold() not in _DISTRICT_COLUMN_NAMES | {"rank"}:
                    inspect_value("table", row, str(label), raw)

    findings = [_finding(
        "value_quality",
        TENTATIVE if problems or repeated else SUPPORTED,
        "Missing, out-of-bounds, or scraper-flagged repeated values need review."
        if problems or repeated else "No missing documented values or known-bound violations were found.",
        value_issues=problems,
        repeated_snapshot_warnings=repeated,
    )]

    # A descriptive baseline is exposed only after three distinct reporting dates.
    series: dict[tuple[str, str, str, str], dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    repeated_keys = {
        (
            str(run.get("page", "")),
            str(run.get("snapshot_date", "")),
            str(run.get("combo_key", "")),
        )
        for run in runs
        if run.get("repeated_snapshot_warning")
    }
    for row in table_documents:
        district = str(row.get("district") or "").strip()
        if not district or district.casefold() == "unknown" or row.get("district_known") is False:
            continue
        values = row.get("values")
        if not isinstance(values, Mapping):
            continue
        for label, raw in values.items():
            if str(label).strip().casefold() in _DISTRICT_COLUMN_NAMES | {"rank"}:
                continue
            numeric = parse_numeric_value(raw)
            if numeric is None:
                continue
            key = (
                str(row.get("page", "")),
                str(row.get("combo_key", "")),
                district,
                str(label),
            )
            series[key][str(row.get("snapshot_date", ""))].append(float(numeric))
    baselines = []
    for (page, combo_key, district, metric_label), date_values in sorted(series.items()):
        unique_values = [
            values[0]
            for reporting_date, values in date_values.items()
            if len(values) == 1
            and (page, reporting_date, combo_key) not in repeated_keys
        ]
        distinct_dates = sorted(
            reporting_date
            for reporting_date, values in date_values.items()
            if len(values) == 1
            and (page, reporting_date, combo_key) not in repeated_keys
        )
        duplicate_dates = sorted(
            date for date, values in date_values.items() if len(values) != 1
        )
        repeated_dates = sorted(
            date for date in date_values
            if (page, date, combo_key) in repeated_keys
        )
        sufficient = len(distinct_dates) >= MIN_BASELINE_REPORTING_DATES
        baseline = statistics.median(unique_values) if sufficient else None
        mad = (
            statistics.median([abs(value - baseline) for value in unique_values])
            if sufficient and baseline is not None else None
        )
        baseline_status = (
            NOT_ASSESSABLE if not sufficient
            else TENTATIVE if duplicate_dates or repeated_dates
            else SUPPORTED
        )
        baselines.append({
            "page": page,
            "combo_key": combo_key,
            "district": district,
            "metric_label": metric_label,
            "status": baseline_status,
            "observation_count": len(unique_values),
            "reporting_dates": distinct_dates,
            "duplicate_reporting_dates": duplicate_dates,
            "repeated_snapshot_dates": repeated_dates,
            "minimum_reporting_dates": MIN_BASELINE_REPORTING_DATES,
            "median": baseline,
            "median_absolute_deviation": mad,
            "interpretation": "Descriptive historical baseline only; not a forecast or anomaly score.",
        })
    return findings, baselines


def _change_findings(
    table_documents: list[dict[str, Any]],
) -> list[HealthFinding]:
    grouped: dict[tuple[str, str, str, str], list[tuple[date, float, Any]]] = defaultdict(list)
    for row in table_documents:
        district = str(row.get("district") or "").strip()
        if not district or district.casefold() == "unknown" or row.get("district_known") is False:
            continue
        reporting_date = row.get("snapshot_date")
        try:
            parsed_date = date.fromisoformat(str(reporting_date))
        except ValueError:
            continue
        values = row.get("values")
        if not isinstance(values, Mapping):
            continue
        for label, raw in values.items():
            if str(label).strip().casefold() in _DISTRICT_COLUMN_NAMES | {"rank"}:
                continue
            numeric = parse_numeric_value(raw)
            if numeric is None:
                continue
            grouped[(
                str(row.get("page", "")),
                str(row.get("combo_key", "")),
                district,
                str(label),
            )].append((parsed_date, float(numeric), raw))

    changes = []
    for (page, combo_key, district, metric_label), observations in grouped.items():
        observations.sort(key=lambda observation: observation[0])
        for previous, current in zip(observations, observations[1:]):
            from_date, from_value, from_raw = previous
            to_date, to_value, to_raw = current
            elapsed_days = (to_date - from_date).days
            if elapsed_days <= 0 or elapsed_days > registry_freshness_gap():
                continue
            if from_value == 0:
                if to_value == 0:
                    continue
                reason = "A non-zero value follows an observed zero; review the source records."
                relative_change = None
            else:
                relative_change = abs((to_value - from_value) / from_value * 100)
                if relative_change < CHANGE_REVIEW_THRESHOLD_PERCENT:
                    continue
                reason = (
                    f"Observed change is at least {CHANGE_REVIEW_THRESHOLD_PERCENT}% "
                    "between adjacent, closely spaced reporting dates."
                )
            changes.append({
                "page": page,
                "combo_key": combo_key,
                "district": district,
                "metric_label": metric_label,
                "from_reporting_date": from_date.isoformat(),
                "to_reporting_date": to_date.isoformat(),
                "elapsed_days": elapsed_days,
                "from_value_raw": from_raw,
                "to_value_raw": to_raw,
                "from_value_numeric": from_value,
                "to_value_numeric": to_value,
                "relative_change_percent": relative_change,
                "review_threshold_percent": CHANGE_REVIEW_THRESHOLD_PERCENT,
                "reason": reason,
            })
    if changes:
        return [_finding(
            "value_change_review", TENTATIVE,
            "Substantial changes between closely spaced observations warrant investigation; values are retained.",
            changes=changes,
            temporal_gap_days=registry_freshness_gap(),
            threshold_percent=CHANGE_REVIEW_THRESHOLD_PERCENT,
        )]
    return [_finding(
        "value_change_review", SUPPORTED,
        "No threshold-triggering change was found between adjacent observations within the weekly tolerance.",
        temporal_gap_days=registry_freshness_gap(),
        threshold_percent=CHANGE_REVIEW_THRESHOLD_PERCENT,
    )]


def registry_freshness_gap() -> int:
    """Use the declared weekly collection tolerance to avoid bridging gaps."""
    return FRESHNESS_TOLERANCE_DAYS


def _reconciliation_findings(
    kpi_documents: list[dict[str, Any]],
    table_documents: list[dict[str, Any]],
) -> list[HealthFinding]:
    kpis_by_key = {_run_key(document): document for document in kpi_documents}
    tables_by_key: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in table_documents:
        tables_by_key[_run_key(row)].append(row)
    findings = []
    for key, rows in sorted(tables_by_key.items()):
        page = key[0]
        if page not in _RECONCILIABLE_METRICS:
            continue
        table_label, kpi_label = _RECONCILIABLE_METRICS[page]
        values = [
            row.get("values", {}).get(table_label)
            for row in rows
            if isinstance(row.get("values"), Mapping)
        ]
        if len(values) != len(rows) or any(parse_numeric_value(value) is None for value in values):
            findings.append(_finding(
                "reconciliation", NOT_ASSESSABLE,
                "The source-reported total cannot be reconciled because one or more table values are missing or non-numeric.",
                page=page,
                reporting_date=key[1],
                combo_key=key[2],
                table_metric=table_label,
                kpi_metric=kpi_label,
            ))
            continue
        document = kpis_by_key.get(key)
        metric = next(
            (metric for metric in (document or {}).get("kpis", [])
             if metric.get("metric_label") == kpi_label),
            None,
        )
        if metric is None or parse_numeric_value(metric.get("metric_value")) is None:
            findings.append(_finding(
                "reconciliation", NOT_ASSESSABLE,
                "The matching source KPI is unavailable or non-numeric.",
                page=page,
                reporting_date=key[1],
                combo_key=key[2],
                table_metric=table_label,
                kpi_metric=kpi_label,
            ))
            continue
        table_sum = sum(parse_numeric_value(value) for value in values)
        kpi_value = parse_numeric_value(metric["metric_value"])
        matched = table_sum == kpi_value
        findings.append(_finding(
            "reconciliation",
            SUPPORTED if matched else TENTATIVE,
            "The compatible district-table and national KPI totals agree."
            if matched else "The compatible district-table and national KPI totals differ.",
            page=page,
            reporting_date=key[1],
            combo_key=key[2],
            table_metric=table_label,
            kpi_metric=kpi_label,
            table_sum=table_sum,
            kpi_value=kpi_value,
            difference=table_sum - kpi_value,
            includes_all_stored_table_rows=True,
        ))
    if not findings:
        findings.append(_finding(
            "reconciliation", NOT_ASSESSABLE,
            "No source-compatible KPI/table metric pairs are available.",
        ))
    return findings


def _dimension_findings(
    registry: ExpectedDataRegistry,
    latest_cycle: list[dict[str, Any]],
) -> list[HealthFinding]:
    findings = []
    for page in registry.pages:
        page_runs = [run for run in latest_cycle if run.get("page") == page.page_id]
        for dimension in ("Gender", "Age", "Education", "Area"):
            expectation = page.dimensions.get(
                dimension,
                {
                    "status": "unsupported",
                    "reason": "No support is configured for this NBR dimension.",
                },
            )
            if expectation["status"] == "unsupported":
                status = NOT_ASSESSABLE
                message = f"{dimension} is unsupported for this NBR page configuration."
                findings.append(_finding(
                    "dimension_coverage",
                    status,
                    message,
                    page=page.page_id,
                    dimension=dimension,
                    configuration=expectation,
                    observed_categories=[],
                ))
                continue
            if expectation["status"] == "fixed":
                label = expectation["filter_label"]
                observed = sorted({
                    str(run.get("filters", {}).get(label))
                    for run in page_runs
                    if isinstance(run.get("filters"), Mapping)
                    and run.get("filters", {}).get(label) not in (None, "")
                })
                findings.append(_finding(
                    "dimension_coverage",
                    NOT_ASSESSABLE,
                    f"{dimension} is fixed rather than independently varied on this page.",
                    page=page.page_id,
                    dimension=dimension,
                    configuration=expectation,
                    observed_categories=observed,
                    filter_scope={},
                ))
                continue
            if not page_runs:
                findings.append(_finding(
                    "dimension_coverage",
                    NOT_ASSESSABLE,
                    f"No runs are available in the latest collection cycle for {dimension} coverage.",
                    page=page.page_id,
                    dimension=dimension,
                    configuration=expectation,
                    observed_categories=[],
                ))
                continue

            filter_label = expectation["filter_label"]
            slices: dict[str, dict[str, Any]] = {}
            for run in page_runs:
                filters = run.get("filters")
                if not isinstance(filters, Mapping) or filter_label not in filters:
                    continue
                scope = {
                    str(label): value
                    for label, value in filters.items()
                    if label != filter_label
                }
                scope_key = json.dumps(scope, ensure_ascii=False, sort_keys=True, default=str)
                item = slices.setdefault(
                    scope_key,
                    {"scope": scope, "categories": set()},
                )
                item["categories"].add(str(filters[filter_label]))

            if not slices:
                findings.append(_finding(
                    "dimension_coverage",
                    NOT_ASSESSABLE,
                    f"No stored filter values are available for {dimension}.",
                    page=page.page_id,
                    dimension=dimension,
                    configuration=expectation,
                    observed_categories=[],
                ))
                continue
            expected_count = expectation.get("expected_option_count")
            for slice_value in slices.values():
                observed = sorted(slice_value["categories"])
                enough = isinstance(expected_count, int) and len(observed) >= expected_count
                status = SUPPORTED if enough else TENTATIVE
                applicable_mappings = [
                    {
                        "indicator_variable": mapping["indicator_variable"],
                        "kpi_labels": mapping["kpi_labels"],
                        "table_labels": mapping["table_labels"],
                    }
                    for mapping in page.approved_metric_mappings
                    if all(
                        slice_value["scope"].get(label) == value
                        for label, value in mapping["filters"].items()
                        if label != filter_label
                    )
                ]
                findings.append(_finding(
                    "dimension_coverage",
                    status,
                    f"{dimension} categories are present for this exact filter scope."
                    if enough else
                    f"{dimension} categories are incomplete for this exact filter scope.",
                    page=page.page_id,
                    dimension=dimension,
                    configuration=expectation,
                    filter_scope=slice_value["scope"],
                    observed_categories=observed,
                    expected_option_count=expected_count,
                    applicable_approved_metrics=applicable_mappings,
                ))
    findings.append(_finding(
        "dimension_coverage",
        NOT_ASSESSABLE,
        "Education and urban/rural Area are available in FinScope but have no matching NBR population-group dimension.",
        source="NBR",
        dimensions=["Education", "Area"],
    ))
    return findings


def _normal_status(findings: list[HealthFinding]) -> str:
    statuses = {finding.status for finding in findings}
    if INCOMPLETE in statuses:
        return INCOMPLETE
    if TENTATIVE in statuses:
        return TENTATIVE
    primary = {
        finding.check: finding.status
        for finding in findings
        if finding.check in {"freshness", "collection_completeness"}
    }
    if any(status == NOT_ASSESSABLE for status in primary.values()):
        return NOT_ASSESSABLE
    return SUPPORTED


def assess_data_health(
    runs: list[dict[str, Any]],
    kpi_documents: list[dict[str, Any]],
    table_documents: list[dict[str, Any]],
    *,
    registry: ExpectedDataRegistry | None = None,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    """Assess NBR collection history without modifying observations or records."""
    registry = registry or load_expected_data_registry()
    now = _datetime(as_of or datetime.now(timezone.utc))
    assert now is not None
    findings: list[HealthFinding] = []
    pages = {page.page_id: page for page in registry.pages}
    latest_cycle: list[dict[str, Any]] = []
    historical_periods = _historical_period_coverage(
        runs, kpi_documents, table_documents, pages
    )

    parsed_collections = [
        _datetime(run.get("collected_at"))
        for run in runs
        if run.get("collected_at") is not None
    ]
    valid_collections = [value for value in parsed_collections if value is not None]
    if not valid_collections:
        findings.append(_finding(
            "freshness", NOT_ASSESSABLE,
            "No parseable NBR collection timestamp is available.",
            timestamp_field=registry.collection_timestamp_field,
        ))
    else:
        latest_collection = max(valid_collections)
        age = now - latest_collection
        if age < timedelta(0):
            findings.append(_finding(
                "freshness", INCOMPLETE,
                "The latest collection timestamp is in the future.",
                latest_collected_at=latest_collection.isoformat(),
                assessed_at=now.isoformat(),
            ))
        elif age > timedelta(days=registry.freshness_tolerance_days):
            findings.append(_finding(
                "freshness", INCOMPLETE,
                "The latest NBR collection is stale for the configured weekly schedule.",
                latest_collected_at=latest_collection.isoformat(),
                age_days=age.total_seconds() / 86400,
                tolerance_days=registry.freshness_tolerance_days,
                schedule=registry.collection_schedule,
            ))
        else:
            findings.append(_finding(
                "freshness", SUPPORTED,
                "The latest collection falls within the configured freshness tolerance.",
                latest_collected_at=latest_collection.isoformat(),
                age_days=age.total_seconds() / 86400,
                tolerance_days=registry.freshness_tolerance_days,
            ))

    if not runs:
        findings.append(_finding(
            "collection_completeness", NOT_ASSESSABLE,
            "No collection run records are available.",
        ))
    else:
        latest_run = max(
            runs,
            key=lambda run: _datetime(run.get("collected_at")) or datetime.min.replace(tzinfo=timezone.utc),
        )
        reporting_dates = [
            reporting_date
            for run in runs
            if (reporting_date := _reporting_date(run.get("snapshot_date"))) is not None
        ]
        latest_reporting_date = max(reporting_dates) if reporting_dates else None
        latest_cycle = (
            [
                run for run in runs
                if _reporting_date(run.get("snapshot_date")) == latest_reporting_date
            ]
            if latest_reporting_date is not None
            else [run for run in runs if run.get("run_id") == latest_run.get("run_id")]
        )
        latest_run_id = max(
            latest_cycle,
            key=lambda run: _datetime(run.get("collected_at")) or datetime.min.replace(tzinfo=timezone.utc),
        ).get("run_id") if latest_cycle else latest_run.get("run_id")
        latest_run_ids = sorted({_run_id(run) for run in latest_cycle if _run_id(run)})
        found_pages = {str(run.get("page", "")) for run in latest_cycle}
        missing_pages = sorted(set(pages) - found_pages)
        failed_runs = [
            run for run in latest_cycle
            if run.get("status") not in {"complete", "completed_no_data", "not_applicable"}
        ]
        combos_by_page_date = Counter(
            (str(run.get("page", "")), str(run.get("snapshot_date", "")))
            for run in latest_cycle
        )
        short_pages = {}
        for page_id, reporting_date in {
            (str(run.get("page", "")), str(run.get("snapshot_date", "")))
            for run in latest_cycle
        }:
            expected = pages.get(page_id)
            if (
                expected is not None
                and expected.expected_combinations is not None
                and combos_by_page_date[(page_id, reporting_date)]
                < expected.expected_combinations
            ):
                short_pages[f"{page_id}@{reporting_date}"] = {
                    "observed_combinations": combos_by_page_date[(page_id, reporting_date)],
                    "expected_combinations": expected.expected_combinations,
                }
        expected_run_keys = {_run_key(run) for run in latest_cycle if _run_id(run)}
        kpi_keys = {_run_key(doc) for doc in kpi_documents}
        table_groups = Counter(_run_key(doc) for doc in table_documents)
        missing_kpis = sorted(
            key for key in expected_run_keys
            if any(
                _run_key(run) == key and run.get("status") == "complete"
                for run in latest_cycle
            )
            and key not in kpi_keys
        )
        wrong_table_counts = []
        missing_required_observations = []
        latest_keys = {_run_key(run) for run in latest_cycle}
        kpis_by_key = {_run_key(document): document for document in kpi_documents}
        table_columns_by_key: dict[tuple[str, str, str], set[str]] = defaultdict(set)
        for row in table_documents:
            table_columns_by_key[_run_key(row)].update(
                str(column) for column in row.get("columns", [])
            )
        for run in latest_cycle:
            if run.get("status") != "complete":
                continue
            actual = table_groups.get(_run_key(run), 0)
            expected_rows = run.get("table_rows")
            if run.get("table_status") != "extracted":
                missing_required_observations.append({
                    "page": run.get("page"),
                    "snapshot_date": run.get("snapshot_date"),
                    "combo_key": run.get("combo_key"),
                    "required": "extracted table",
                    "observed_status": run.get("table_status"),
                })
            if isinstance(expected_rows, int) and actual != expected_rows:
                wrong_table_counts.append({
                    "page": run.get("page"),
                    "snapshot_date": run.get("snapshot_date"),
                    "combo_key": run.get("combo_key"),
                    "expected_rows": expected_rows,
                    "observed_rows": actual,
                })
            kpi_document = kpis_by_key.get(_run_key(run))
            filters = run.get("filters")
            if not isinstance(filters, Mapping):
                filters = {}
            expected_page = pages.get(str(run.get("page", "")))
            if expected_page is None:
                continue
            for page_expectation in expected_page.approved_metric_mappings:
                mapping_filters = page_expectation["filters"]
                if not all(filters.get(label) == value for label, value in mapping_filters.items()):
                    continue
                stored_kpi_labels = {
                    str(metric.get("metric_label", ""))
                    for metric in (kpi_document or {}).get("kpis", [])
                }
                missing_kpi_labels = sorted(
                    set(page_expectation["kpi_labels"]) - stored_kpi_labels
                )
                stored_table_labels = table_columns_by_key[_run_key(run)]
                missing_table_labels = sorted(
                    set(page_expectation["table_labels"]) - stored_table_labels
                )
                if missing_kpi_labels or missing_table_labels:
                    missing_required_observations.append({
                        "page": run.get("page"),
                        "snapshot_date": run.get("snapshot_date"),
                        "combo_key": run.get("combo_key"),
                        "missing_kpi_labels": missing_kpi_labels,
                        "missing_table_labels": missing_table_labels,
                    })
        complete = (
            not missing_pages and not failed_runs and not short_pages
            and not missing_kpis and not wrong_table_counts
            and not missing_required_observations
            and all(period["status"] == SUPPORTED for period in historical_periods)
        )
        findings.append(_finding(
            "collection_completeness",
            SUPPORTED if complete else INCOMPLETE,
            "The latest reporting period and all stored historical periods include the configured pages and combinations."
            if complete else "The latest or a stored historical reporting period is missing pages, combinations, or observations.",
            latest_run_id=latest_run_id,
            latest_run_ids=latest_run_ids,
            latest_reporting_date=latest_reporting_date.isoformat() if latest_reporting_date else None,
            expected_pages=sorted(pages),
            observed_pages=sorted(found_pages),
            missing_pages=missing_pages,
            failed_runs=[
                {"page": run.get("page"), "status": run.get("status"), "error": run.get("error")}
                for run in failed_runs
            ],
            pages_with_fewer_combinations=short_pages,
            missing_kpi_documents=[list(key) for key in missing_kpis],
            table_row_count_mismatches=wrong_table_counts,
            missing_required_observations=missing_required_observations,
            latest_cycle_key_count=len(latest_keys),
            historical_reporting_periods=historical_periods,
        ))

    findings.extend(_geographic_findings(
        table_documents,
        registry.expected_districts,
    ))
    findings.extend(_schema_findings(runs, kpi_documents, table_documents))
    findings.extend(_integrity_findings(runs, kpi_documents, table_documents))
    value_findings, baselines = _value_findings(
        runs,
        kpi_documents,
        table_documents,
    )
    findings.extend(value_findings)
    findings.extend(_change_findings(table_documents))
    findings.extend(_reconciliation_findings(kpi_documents, table_documents))
    findings.extend(_dimension_findings(registry, latest_cycle))
    if not findings:
        findings.append(_finding(
            "overall", NOT_ASSESSABLE,
            "No data-health checks could be assessed.",
        ))

    return {
        "status": _normal_status(findings),
        "assessed_at": now.isoformat(),
        "source": registry.source,
        "expected_data": registry,
        "findings": [asdict(finding) for finding in findings],
        "learned_baselines": baselines,
    }


def assess_mongodb_data_health(
    *,
    config_path: Path | None = None,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    """Read all NBR history from the existing collections and assess it."""
    try:
        from dotenv import load_dotenv
        from pymongo import MongoClient
    except ImportError as exc:
        raise RuntimeError(
            "Install the project requirements (python-dotenv and pymongo) to assess MongoDB history."
        ) from exc

    from src.data_sources.mongodb_district_explorer import load_district_reference

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
                "filters": 1,
                "filters_requested": 1,
                "filters_key": 1,
                "status": 1,
                "table_status": 1,
                "table_rows": 1,
                "repeated_snapshot_warning": 1,
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

    expected_districts = tuple(load_district_reference())
    registry = load_expected_data_registry(config_path, expected_districts)
    return assess_data_health(runs, kpis, tables, registry=registry, as_of=as_of)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args(argv)
    result = assess_mongodb_data_health(config_path=args.config)
    serializable = {
        **result,
        "expected_data": {
            **asdict(result["expected_data"]),
            "pages": [asdict(page) for page in result["expected_data"].pages],
        },
    }
    print(json.dumps(serializable, indent=2, ensure_ascii=False, default=str))
    return 0 if result["status"] in {SUPPORTED, TENTATIVE} else 1


if __name__ == "__main__":
    raise SystemExit(main())
