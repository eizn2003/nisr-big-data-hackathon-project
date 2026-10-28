"""Export validated NBR Inclusion observations for the National Overview.

The national CSV has one row per stored KPI. The district CSV has one row per
non-geographic table field and district, with source columns, row indices, raw
values, and full source records retained for provenance.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATABASE_NAME = "nbr_financial_inclusion"
PAGE_ID = "inclusion"
REPORTING_DATES = (
    "2025-02-20",
    "2025-11-20",
    "2026-08-20",
    "2026-10-24",
)
INSTITUTION_TYPES = (
    "All",
    "Banks",
    "E-money issuers",
    "Insurance",
    "Microfinance",
    "Sacco",
)
FIXED_FILTERS = {
    "Gender": "All",
    "Age Segment": "All",
    "Account/Policy Status": "Active",
    "Location": "All",
}
NATIONAL_OUTPUT = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "bnr_inclusion_national_observations.csv"
)
DISTRICT_OUTPUT = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "bnr_inclusion_district_observations.csv"
)

RUN_COLLECTION = "page_scrape_runs"
KPI_COLLECTION = "page_kpi_observations"
TABLE_COLLECTION = "page_table_observations"


@dataclass(frozen=True)
class ExtractionSpec:
    page_id: str
    reporting_dates: tuple[str, ...]
    selection_filter: str
    selections: tuple[str, ...]
    fixed_filters: dict[str, str]
    district_column: str = "District"


INCLUSION_SPEC = ExtractionSpec(
    page_id=PAGE_ID,
    reporting_dates=REPORTING_DATES,
    selection_filter="Institution Type",
    selections=INSTITUTION_TYPES,
    fixed_filters=FIXED_FILTERS,
)


class ExtractionValidationError(RuntimeError):
    """Raised when selected Mongo observations do not meet extraction checks."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("Inclusion extraction validation failed:\n- " + "\n- ".join(errors))


@dataclass
class ExtractionResult:
    national_rows: list[dict[str, Any]]
    district_rows: list[dict[str, Any]]
    source_table_rows: int
    validated_combinations: int
    unknown_district_rows: int
    unmatched_district_names: tuple[str, ...]
    district_quality_warnings: tuple[str, ...]


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=_json_default)


def _json_default(value: Any) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def _stable_id(*parts: Any) -> str:
    payload = json.dumps(parts, ensure_ascii=False, sort_keys=True, default=_json_default)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def parse_numeric_value(raw: Any) -> int | float | None:
    """Parse a numeric source value without changing or replacing its raw form."""
    if isinstance(raw, bool) or raw is None:
        return None
    if isinstance(raw, (int, float)):
        return raw if math.isfinite(raw) else None
    if not isinstance(raw, str):
        return None

    text = raw.strip()
    if not re.fullmatch(r"-?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?%?", text):
        return None
    number = text.removesuffix("%").replace(",", "")
    if "." in number:
        return float(number)
    return int(number)


def _unit_from_raw(raw: Any) -> tuple[str, str]:
    if isinstance(raw, str) and raw.strip().endswith("%"):
        return "percent", "source_indicated"
    return "", "unresolved"


def _combo_key(filters: dict[str, Any]) -> str:
    return json.dumps(filters, sort_keys=True, ensure_ascii=False)


def _expected_filters(spec: ExtractionSpec, selection: str) -> dict[str, str]:
    return {**spec.fixed_filters, spec.selection_filter: selection}


def _expected_combinations(spec: ExtractionSpec) -> list[tuple[str, str, dict[str, str]]]:
    return [
        (reporting_date, selection, _expected_filters(spec, selection))
        for reporting_date in spec.reporting_dates
        for selection in spec.selections
    ]


def _run_is_candidate(run: dict[str, Any], spec: ExtractionSpec) -> bool:
    snapshot_date = run.get("snapshot_date")
    if snapshot_date not in spec.reporting_dates:
        return False
    expected_keys = {
        _combo_key(filters)
        for _, _, filters in _expected_combinations(spec)
    }
    if run.get("combo_key") in expected_keys:
        return True

    filters = run.get("filters")
    if not isinstance(filters, dict):
        return False
    return (
        filters.get(spec.selection_filter) in spec.selections
        and all(filters.get(key) == value for key, value in spec.fixed_filters.items())
    )


def _record_group_key(document: dict[str, Any]) -> tuple[Any, Any, Any]:
    return (
        document.get("page"),
        document.get("snapshot_date"),
        document.get("combo_key"),
    )


def _numeric_matches(raw_value: Any, source_numeric: Any) -> bool:
    parsed = parse_numeric_value(raw_value)
    if parsed is None:
        return source_numeric is None
    stored = parse_numeric_value(source_numeric)
    return stored is not None and parsed == stored


def _validate_document_metadata(
    document: dict[str, Any],
    run: dict[str, Any],
    expected_filters: dict[str, str],
    source_name: str,
    selection_filter: str,
    selection: str,
    errors: list[str],
) -> bool:
    valid = True
    for field in ("page", "snapshot_date", "combo_key", "run_id"):
        if document.get(field) != run.get(field):
            errors.append(
                f"{source_name} metadata mismatch for {run.get('snapshot_date')} "
                f"{selection_filter}={selection}: {field} "
                f"{document.get(field)!r} != {run.get(field)!r}."
            )
            valid = False
    filters = document.get("filters")
    if filters != expected_filters:
        errors.append(
            f"{source_name} filter metadata mismatch for {run.get('snapshot_date')} "
            f"{selection_filter}={selection}: {_json(filters)}."
        )
        valid = False
    requested_filters = document.get("filters_requested")
    if requested_filters is not None and requested_filters != expected_filters:
        errors.append(
            f"{source_name} requested-filter mismatch for {run.get('snapshot_date')} "
            f"{selection_filter}={selection}: {_json(requested_filters)}."
        )
        valid = False
    if document.get("dashboard_date") != run.get("dashboard_date"):
        errors.append(
            f"{source_name} dashboard date mismatch for {run.get('snapshot_date')} "
            f"{selection_filter}={selection}."
        )
        valid = False
    run_collected_at = run.get("collected_at")
    observation_collected_at = document.get("collected_at")
    if (
        run_collected_at is not None
        and observation_collected_at is not None
        and observation_collected_at != run_collected_at
    ):
        errors.append(
            f"{source_name} collection timestamp mismatch for {run.get('snapshot_date')} "
            f"{selection_filter}={selection}."
        )
        valid = False
    return valid


def _base_observation(
    run: dict[str, Any],
    observation: dict[str, Any],
    filters: dict[str, str],
    selection: str,
    selection_filter: str,
    geography_level: str,
    geography_id: str,
    geography_status: str,
) -> dict[str, Any]:
    collected_at = observation.get("collected_at")
    return {
        "source_page": run["page"],
        "reporting_date": run["snapshot_date"],
        "collected_at": _json_default(collected_at) if collected_at is not None else "",
        "source_type": "administrative_dashboard",
        "source_name": observation.get("source") or run.get("source"),
        "selection_filter": selection_filter,
        "selection_value": selection,
        "institution_type": selection if "Institution Type" in filters else "",
        "filters_json": _json(filters),
        "geography_level": geography_level,
        "geography_id": geography_id,
        "geography_status": geography_status,
        "run_id": run.get("run_id"),
        "combo_key": run.get("combo_key"),
        "dashboard_date": run.get("dashboard_date"),
        "date_source": observation.get("date_source"),
        "source_url": observation.get("source_url") or run.get("source_url"),
        "run_status": run.get("status"),
        "run_table_status": run.get("table_status"),
        "run_error": run.get("error"),
        "run_repeated_snapshot_warning": run.get("repeated_snapshot_warning"),
        "source_run_json": _json(run),
    }


def normalize_observations(
    spec: ExtractionSpec,
    runs: list[dict[str, Any]],
    kpi_documents: list[dict[str, Any]],
    table_documents: list[dict[str, Any]],
    known_districts: set[str] | None = None,
) -> ExtractionResult:
    """Validate selected records and return deterministic normalized observations."""
    errors: list[str] = []
    expected = _expected_combinations(spec)
    expected_by_key = {
        (reporting_date, _combo_key(filters)): (selection, filters)
        for reporting_date, selection, filters in expected
    }

    run_buckets: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for run in runs:
        if run.get("page") != spec.page_id or not _run_is_candidate(run, spec):
            continue
        filters = run.get("filters")
        if isinstance(filters, dict):
            selection = filters.get(spec.selection_filter)
            if selection in spec.selections:
                run_buckets[(run.get("snapshot_date"), selection)].append(run)
                continue
        expected_match = expected_by_key.get((run.get("snapshot_date"), run.get("combo_key")))
        if expected_match:
            run_buckets[(run.get("snapshot_date"), expected_match[0])].append(run)

    kpi_groups: dict[tuple[Any, Any, Any], list[dict[str, Any]]] = defaultdict(list)
    for document in kpi_documents:
        kpi_groups[_record_group_key(document)].append(document)
    table_groups: dict[tuple[Any, Any, Any], list[dict[str, Any]]] = defaultdict(list)
    for document in table_documents:
        table_groups[_record_group_key(document)].append(document)

    national_rows: list[dict[str, Any]] = []
    district_rows: list[dict[str, Any]] = []
    coverage_by_combo: dict[tuple[str, str], set[tuple[str, bool]]] = {}
    source_table_rows = 0
    unknown_district_rows = 0
    unmatched_district_names: set[str] = set()
    district_quality_warnings: set[str] = set()
    known_district_names = (
        {name.casefold() for name in known_districts}
        if known_districts is not None
        else None
    )
    valid_combinations = 0

    for reporting_date, selection, expected_filters in expected:
        combo_key = _combo_key(expected_filters)
        bucket_key = (reporting_date, selection)
        matching_runs = run_buckets.get(bucket_key, [])
        if not matching_runs:
            errors.append(
                f"Missing run for {reporting_date}, {spec.selection_filter}={selection}, "
                f"filters={_json(expected_filters)}."
            )
            continue
        if len(matching_runs) != 1:
            errors.append(
                f"Duplicate runs for {reporting_date}, {spec.selection_filter}={selection}."
            )
            continue

        run = matching_runs[0]
        if run.get("page") != spec.page_id:
            errors.append(f"Run page mismatch for {reporting_date}, {selection}.")
        if run.get("snapshot_date") != reporting_date:
            errors.append(f"Run reporting date mismatch for {reporting_date}, {selection}.")
        if run.get("combo_key") != combo_key:
            errors.append(
                f"Run combination key mismatch for {reporting_date}, {selection}: "
                f"{run.get('combo_key')!r}."
            )
        if run.get("filters") != expected_filters:
            errors.append(
                f"Run filter metadata mismatch for {reporting_date}, {selection}: "
                f"{_json(run.get('filters'))}."
            )
        if run.get("filters_requested") != expected_filters:
            errors.append(
                f"Run requested-filter metadata mismatch for {reporting_date}, {selection}: "
                f"{_json(run.get('filters_requested'))}."
            )
        if run.get("filters_key") != combo_key:
            errors.append(
                f"Run filter-key mismatch for {reporting_date}, {selection}: "
                f"{run.get('filters_key')!r}."
            )
        if run.get("status") != "complete":
            detail = run.get("error") or run.get("reason") or "no error detail"
            errors.append(
                f"Run is not successful for {reporting_date}, {selection}: "
                f"{run.get('status')!r}; {detail}."
            )
        if not run.get("run_id"):
            errors.append(f"Run ID is missing for {reporting_date}, {selection}.")

        group_key = (spec.page_id, reporting_date, combo_key)
        matching_kpis = kpi_groups.get(group_key, [])
        if not matching_kpis:
            errors.append(f"Missing KPI observation for {reporting_date}, {selection}.")
        elif len(matching_kpis) != 1:
            errors.append(f"Duplicate KPI observations for {reporting_date}, {selection}.")

        matching_tables = table_groups.get(group_key, [])
        if not matching_tables:
            errors.append(f"Missing district table observations for {reporting_date}, {selection}.")
        if run.get("table_status") != "extracted":
            errors.append(
                f"District table is not marked extracted for {reporting_date}, {selection}: "
                f"{run.get('table_status')!r}."
            )
        expected_table_rows = run.get("table_rows")
        if not isinstance(expected_table_rows, int) or expected_table_rows < 1:
            errors.append(
                f"Invalid expected district-row count for {reporting_date}, {selection}: "
                f"{expected_table_rows!r}."
            )
        elif len(matching_tables) != expected_table_rows:
            errors.append(
                f"District-row count mismatch for {reporting_date}, {selection}: "
                f"run reports {expected_table_rows}, found {len(matching_tables)}."
            )

        if len(matching_kpis) != 1:
            continue
        kpi_document = matching_kpis[0]
        _validate_document_metadata(
            kpi_document,
            run,
            expected_filters,
            "KPI",
            spec.selection_filter,
            selection,
            errors,
        )
        metrics = kpi_document.get("kpis")
        if not isinstance(metrics, list) or not metrics:
            errors.append(f"No KPI metrics stored for {reporting_date}, {selection}.")
            metrics = []
        if kpi_document.get("kpi_count") != len(metrics):
            errors.append(
                f"KPI count mismatch for {reporting_date}, {selection}: "
                f"stored {kpi_document.get('kpi_count')!r}, actual {len(metrics)}."
            )

        metric_keys: set[tuple[Any, Any]] = set()
        for metric in metrics:
            metric_key = (metric.get("metric_type"), metric.get("ordinal"))
            if metric_key in metric_keys:
                errors.append(
                    f"Duplicate KPI metric key {metric_key!r} for {reporting_date}, {selection}."
                )
            metric_keys.add(metric_key)
            raw_value = metric.get("metric_value")
            numeric_value = parse_numeric_value(raw_value)
            if not _numeric_matches(raw_value, metric.get("metric_value_numeric")):
                errors.append(
                    f"KPI numeric value mismatch for {reporting_date}, {selection}, "
                    f"{metric.get('metric_label')!r}."
                )
            unit, unit_status = _unit_from_raw(raw_value)
            common = _base_observation(
                run,
                kpi_document,
                expected_filters,
                selection,
                spec.selection_filter,
                "national",
                "",
                "national",
            )
            national_rows.append(
                {
                    "observation_id": _stable_id(
                        spec.page_id, reporting_date, combo_key, "kpi", metric_key
                    ),
                    **common,
                    "page": spec.page_id,
                    "snapshot_date": reporting_date,
                    "combo_key": combo_key,
                    "institution_type": selection,
                    "filters_json": _json(expected_filters),
                    "metric_type": metric.get("metric_type"),
                    "metric_label": metric.get("metric_label"),
                    "metric_value": raw_value,
                    "metric_value_numeric": metric.get("metric_value_numeric"),
                    "metric_gender": metric.get("gender"),
                    "extraction_method": metric.get("extraction_method"),
                    "ordinal": metric.get("ordinal"),
                    "value_raw": raw_value,
                    "value_numeric": numeric_value,
                    "unit": unit,
                    "unit_status": unit_status,
                    "definition_status": "unresolved",
                    "source_observation_json": _json(metric),
                }
            )

        row_indexes: set[int] = set()
        district_names: set[tuple[str, bool]] = set()
        for row in matching_tables:
            row_index = row.get("row_index")
            if not isinstance(row_index, int):
                errors.append(f"Invalid table row index for {reporting_date}, {selection}: {row_index!r}.")
                continue
            if row_index in row_indexes:
                errors.append(
                    f"Duplicate district row key {row_index} for {reporting_date}, {selection}."
                )
                continue
            row_indexes.add(row_index)
            if not _validate_document_metadata(
                row,
                run,
                expected_filters,
                "Table",
                spec.selection_filter,
                selection,
                errors,
            ):
                continue
            columns = row.get("columns")
            values = row.get("values")
            numbers = row.get("numbers")
            if not isinstance(columns, list) or not isinstance(values, dict):
                errors.append(
                    f"Invalid table schema for row {row_index}, {reporting_date}, {selection}."
                )
                continue
            if run.get("table_columns") and columns != run.get("table_columns"):
                errors.append(
                    f"Table columns differ from run metadata for row {row_index}, "
                    f"{reporting_date}, {selection}."
                )
            if spec.district_column not in columns or spec.district_column not in values:
                errors.append(
                    f"District field {spec.district_column!r} missing in row {row_index}, "
                    f"{reporting_date}, {selection}."
                )
                continue
            district_raw = values[spec.district_column]
            district_name = str(district_raw).strip() if district_raw is not None else ""
            source_known = row.get("district_known") is True
            district_is_named = bool(district_name) and district_name.casefold() != "unknown"
            reference_match = (
                known_district_names is None
                or district_name.casefold() in known_district_names
            )
            district_known = source_known and district_is_named and reference_match
            if source_known and district_is_named and not reference_match:
                unmatched_district_names.add(district_name)
            if source_known != (district_is_named and reference_match):
                district_quality_warnings.add(
                    f"District {district_name!r} has source district_known={source_known} "
                    f"but reference match={district_is_named and reference_match}."
                )
            if district_known:
                district_status = (
                    "source_marked_known" if known_districts is None else "matched_reference"
                )
            elif source_known and district_is_named:
                district_status = "unmatched"
            else:
                district_status = "unknown"
            district_level = "district" if district_known else "unknown"
            district_id = district_name if district_known else ""
            district_key = (district_name, district_known)
            district_name_key = district_name.casefold()
            if any(name.casefold() == district_name_key for name, _ in district_names):
                errors.append(
                    f"Duplicate district label {district_name!r} for {reporting_date}, "
                    f"{selection}."
                )
            district_names.add(district_key)
            if not district_known:
                unknown_district_rows += 1

            for column in columns:
                if column == spec.district_column:
                    continue
                if column not in values:
                    errors.append(
                        f"Table value missing for column {column!r}, row {row_index}, "
                        f"{reporting_date}, {selection}."
                    )
                    continue
                raw_value = values[column]
                numeric_value = parse_numeric_value(raw_value)
                stored_numeric = numbers.get(column) if isinstance(numbers, dict) else None
                if column in (numbers or {}) and not _numeric_matches(raw_value, stored_numeric):
                    errors.append(
                        f"Table numeric value mismatch for column {column!r}, row {row_index}, "
                        f"{reporting_date}, {selection}."
                    )
                elif numeric_value is not None and column not in (numbers or {}):
                    errors.append(
                        f"Parsed table numeric value is absent from source numbers for "
                        f"{column!r}, row {row_index}, {reporting_date}, {selection}."
                    )
                unit, unit_status = _unit_from_raw(raw_value)
                common = _base_observation(
                    run,
                    row,
                    expected_filters,
                    selection,
                    spec.selection_filter,
                    district_level,
                    district_id,
                    district_status,
                )
                district_rows.append(
                    {
                        "observation_id": _stable_id(
                            spec.page_id, reporting_date, combo_key, row_index, column
                        ),
                        **common,
                        "page": spec.page_id,
                        "snapshot_date": reporting_date,
                        "combo_key": combo_key,
                        "institution_type": selection,
                        "filters_json": _json(expected_filters),
                        "row_index": row_index,
                        "district": row.get("district"),
                        "district_known": row.get("district_known"),
                        "metric_label": column,
                        "metric_value": raw_value,
                        "metric_value_numeric": stored_numeric,
                        "value_raw": raw_value,
                        "value_numeric": numeric_value,
                        "unit": unit,
                        "unit_status": unit_status,
                        "definition_status": "unresolved",
                        "original_column": column,
                        "original_columns_json": _json(columns),
                        "original_values_json": _json(values),
                        "original_numbers_json": _json(numbers or {}),
                        "customers": row.get("customers"),
                        "rank": row.get("rank"),
                        "source_observation_json": _json(row),
                    }
                )
        if isinstance(expected_table_rows, int):
            expected_row_indexes = set(range(expected_table_rows))
            if row_indexes != expected_row_indexes:
                errors.append(
                    f"District row-index coverage mismatch for {reporting_date}, {selection}: "
                    f"expected {sorted(expected_row_indexes)}, found {sorted(row_indexes)}."
                )

        source_table_rows += len(matching_tables)
        coverage_by_combo[bucket_key] = district_names
        if expected_table_rows == len(matching_tables) and len(matching_kpis) == 1:
            valid_combinations += 1

    if coverage_by_combo:
        reference_combo = next(iter(coverage_by_combo))
        reference_coverage = coverage_by_combo[reference_combo]
        for combo, coverage in coverage_by_combo.items():
            if coverage != reference_coverage:
                errors.append(
                    f"District coverage differs for {combo[0]}, "
                    f"{spec.selection_filter}={combo[1]} compared with "
                    f"{reference_combo[0]}, {spec.selection_filter}={reference_combo[1]}."
                )

    if errors:
        raise ExtractionValidationError(errors)

    national_rows.sort(
        key=lambda row: (
            spec.reporting_dates.index(row["reporting_date"]),
            spec.selections.index(row["selection_value"]),
            row.get("metric_type") or "",
            row.get("ordinal") if row.get("ordinal") is not None else -1,
        )
    )
    district_rows.sort(
        key=lambda row: (
            spec.reporting_dates.index(row["reporting_date"]),
            spec.selections.index(row["selection_value"]),
            row["row_index"],
            row["original_column"],
        )
    )
    return ExtractionResult(
        national_rows=national_rows,
        district_rows=district_rows,
        source_table_rows=source_table_rows,
        validated_combinations=valid_combinations,
        unknown_district_rows=unknown_district_rows,
        unmatched_district_names=tuple(sorted(unmatched_district_names)),
        district_quality_warnings=tuple(sorted(district_quality_warnings)),
    )


def _write_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=fields, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def _national_fields() -> list[str]:
    return [
        "observation_id",
        "source_page",
        "reporting_date",
        "collected_at",
        "source_type",
        "source_name",
        "page",
        "snapshot_date",
        "dashboard_date",
        "date_source",
        "source_url",
        "run_id",
        "combo_key",
        "institution_type",
        "selection_filter",
        "selection_value",
        "filters_json",
        "geography_level",
        "geography_id",
        "geography_status",
        "run_status",
        "run_table_status",
        "run_error",
        "run_repeated_snapshot_warning",
        "metric_type",
        "metric_label",
        "metric_value",
        "metric_value_numeric",
        "metric_gender",
        "extraction_method",
        "ordinal",
        "value_raw",
        "value_numeric",
        "unit",
        "unit_status",
        "definition_status",
        "source_observation_json",
        "source_run_json",
    ]


def _district_fields() -> list[str]:
    return [
        "observation_id",
        "source_page",
        "reporting_date",
        "collected_at",
        "source_type",
        "source_name",
        "page",
        "snapshot_date",
        "dashboard_date",
        "date_source",
        "source_url",
        "run_id",
        "combo_key",
        "institution_type",
        "selection_filter",
        "selection_value",
        "filters_json",
        "geography_level",
        "geography_id",
        "geography_status",
        "run_status",
        "run_table_status",
        "run_error",
        "run_repeated_snapshot_warning",
        "row_index",
        "district",
        "district_known",
        "metric_label",
        "metric_value",
        "metric_value_numeric",
        "value_raw",
        "value_numeric",
        "unit",
        "unit_status",
        "definition_status",
        "original_column",
        "original_columns_json",
        "original_values_json",
        "original_numbers_json",
        "customers",
        "rank",
        "source_observation_json",
        "source_run_json",
    ]


def _load_district_names() -> set[str]:
    path = PROJECT_ROOT / "geoBoundaries-RWA-ADM2.geojson"
    if not path.exists():
        raise RuntimeError(f"District reference file is missing: {path}")
    geojson = json.loads(path.read_text(encoding="utf-8"))
    names = {
        str(feature.get("properties", {}).get("shapeName", "")).strip()
        for feature in geojson.get("features", [])
    }
    names.discard("")
    if not names:
        raise RuntimeError(f"District reference file contains no shapeName values: {path}")
    return names


def export_inclusion_observations() -> tuple[int, int]:
    load_dotenv(PROJECT_ROOT / ".env")
    uri = os.getenv("MONGODB_URI") or os.getenv("MONGO_URI")
    if not uri:
        raise RuntimeError("Set MONGODB_URI or MONGO_URI in the project .env file.")

    try:
        from pymongo import MongoClient
    except ImportError as exc:
        raise RuntimeError(
            "pymongo is required to read the NBR MongoDB database; install project requirements."
        ) from exc

    client = MongoClient(
        uri,
        serverSelectionTimeoutMS=15_000,
        connectTimeoutMS=15_000,
        socketTimeoutMS=30_000,
    )
    try:
        client.admin.command("ping")
        db = client[DATABASE_NAME]
        run_documents = list(
            db[RUN_COLLECTION].find(
                {"page": INCLUSION_SPEC.page_id, "snapshot_date": {"$in": list(REPORTING_DATES)}}
            )
        )
        expected_keys = [
            {
                "page": INCLUSION_SPEC.page_id,
                "snapshot_date": reporting_date,
                "combo_key": _combo_key(filters),
            }
            for reporting_date, _, filters in _expected_combinations(INCLUSION_SPEC)
        ]
        kpi_documents = list(db[KPI_COLLECTION].find({"$or": expected_keys}))
        table_documents = list(db[TABLE_COLLECTION].find({"$or": expected_keys}))
        result = normalize_observations(
            INCLUSION_SPEC,
            run_documents,
            kpi_documents,
            table_documents,
            known_districts=_load_district_names(),
        )

        _write_csv(NATIONAL_OUTPUT, _national_fields(), result.national_rows)
        _write_csv(DISTRICT_OUTPUT, _district_fields(), result.district_rows)
        print(
            f"Validated {result.validated_combinations} combinations; "
            f"{result.source_table_rows} source district rows, "
            f"{result.unknown_district_rows} unknown/unmatched source district rows."
        )
        if result.district_quality_warnings:
            print(
                "District quality warnings (affected rows remain unknown): "
                + " ".join(result.district_quality_warnings)
            )
        return len(result.national_rows), len(result.district_rows)
    finally:
        client.close()


if __name__ == "__main__":
    national_count, district_count = export_inclusion_observations()
    print(f"National KPI observations: {national_count} -> {NATIONAL_OUTPUT}")
    print(f"District metric observations: {district_count} -> {DISTRICT_OUTPUT}")
