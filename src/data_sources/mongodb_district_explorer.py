"""Read and normalize NBR observations for independent district trend analysis.

The module reads existing MongoDB history only. It preserves administrative
observations separately from FinScope data and calculates historical changes
without producing projections.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATABASE_NAME = "nbr_financial_inclusion"
RUN_COLLECTION = "page_scrape_runs"
KPI_COLLECTION = "page_kpi_observations"
TABLE_COLLECTION = "page_table_observations"
REPORTING_DATES = (
    # 2026-10-27 is omitted from this common series because the branch run is
    # complete but explicitly flagged by the scraper as repeated content.
    "2025-02-20",
    "2025-11-20",
    "2026-08-20",
    "2026-10-24",
)
CHANGE_REVIEW_THRESHOLD_PERCENT = 50

_ALL_DEMOGRAPHICS = {"Gender": "All", "Age Segment": "All"}


@dataclass(frozen=True)
class PageSelection:
    page_id: str
    filters: Mapping[str, str]
    purpose: str
    kpi_labels: tuple[str, ...] = ()
    table_labels: tuple[str, ...] = ()
    historical_monitoring_eligible: bool = True


@dataclass(frozen=True)
class ApprovedNBRMapping:
    indicator_variable: str
    indicator_label: str
    page_id: str
    filters: Mapping[str, str]
    kpi_labels: tuple[str, ...]
    table_labels: tuple[str, ...]
    status: str
    relevance: str
    limitations: str
    conditions: str = ""


_INCLUSION_FILTERS = {
    "Gender": "All",
    "Age Segment": "All",
    "Account/Policy Status": "Active",
    "Location": "All",
}
_INSURANCE_FILTERS = {
    "Gender": "All",
    "Age Segment": "All",
    "Insurance Type": "All",
    "Policy Status": "Active",
    "Location": "All",
}
_MOBILE_BANKING_FILTERS = {
    "Gender": "All",
    "Age Segment": "All",
    "Institution Type": "All",
    "Account Status": "Active",
    "Account Type": "All",
    "Location": "All",
}

_TRANSACTIONAL_FILTERS = {
    **_ALL_DEMOGRAPHICS,
    "Institution Type": "All",
    "Account Status": "Active",
    "Account Type": "All",
    "Location": "All",
}
_CREDIT_FILTERS = {
    **_ALL_DEMOGRAPHICS,
    "Institution Type": "All",
    "Account Status": "Active",
    "Credit Category": "All",
    "Location": "All",
}
_SAVINGS_FILTERS = {
    **_ALL_DEMOGRAPHICS,
    "Institution Type": "All",
    "Account Status": "Active",
    "Account Type": "All",
    "Location": "All",
}


def _inclusion_filters(institution_type: str) -> dict[str, str]:
    return {**_INCLUSION_FILTERS, "Institution Type": institution_type}


def _mapping(
    indicator_variable: str,
    indicator_label: str,
    page_id: str,
    filters: Mapping[str, str],
    kpi_labels: tuple[str, ...],
    table_labels: tuple[str, ...],
    status: str,
    relevance: str,
    limitations: str,
    conditions: str = "",
) -> ApprovedNBRMapping:
    return ApprovedNBRMapping(
        indicator_variable=indicator_variable,
        indicator_label=indicator_label,
        page_id=page_id,
        filters=dict(filters),
        kpi_labels=kpi_labels,
        table_labels=table_labels,
        status=status,
        relevance=relevance,
        limitations=limitations,
        conditions=conditions,
    )


APPROVED_MAPPINGS = (
    _mapping(
        "k1", "Bank-account ownership", "branches",
        {"Institution Type": "Banks", "Branch Status": "Active", "Location": "All"},
        ("Total Branches",), ("Branches",), "relevant",
        "Recorded active bank-branch infrastructure.",
        "Branch presence is not individual account ownership.",
    ),
    _mapping(
        "k1", "Bank-account ownership", "inclusion",
        _inclusion_filters("Banks"), ("Banked", "Total Customers"), ("Customers",),
        "uncertain", "Potential banking customer activity.",
        "The Banked denominator and customer-count uniqueness are undocumented.",
    ),
    _mapping(
        "k1", "Bank-account ownership", "transactional",
        _TRANSACTIONAL_FILTERS, ("Have Transactional Accounts",), ("Customers",),
        "uncertain", "Potential transactional-banking activity.",
        "The account definition and customer-count uniqueness are undocumented.",
    ),
    _mapping(
        "k1", "Bank-account ownership", "depositors",
        _SAVINGS_FILTERS, ("Are Depositors",), ("Customers",), "uncertain",
        "Potential recorded deposit-taking activity.",
        "The depositor definition and customer-count uniqueness are undocumented.",
    ),
    _mapping(
        "f5", "Registered mobile-money use", "inclusion",
        _inclusion_filters("E-money issuers"),
        ("Subscribers", "Total Customers"), ("Customers",), "uncertain",
        "Potential e-money subscriber activity.",
        "Subscriber definition and KPI denominator are undocumented; district Customers is a separate measure.",
    ),
    _mapping(
        "f5", "Registered mobile-money use", "agents",
        {
            "Gender": "All",
            "Institution Type": "E-money Issuers",
            "Agent Status": "Active",
            "Location": "All",
        },
        ("Total Agents",), ("Agents",), "relevant",
        "Active e-money service-channel infrastructure alongside survey-reported mobile-money registration.",
        "Agent counts describe a service channel, not registered users or individual access. "
        "The district sum exceeds the national KPI in all four stored snapshots; preserve this "
        "reconciliation warning and do not infer coverage or inclusion progress.",
    ),
    _mapping(
        "qf4_05", "Current mobile-money operator use among ever-users", "agents",
        {
            "Gender": "All",
            "Institution Type": "E-money Issuers",
            "Agent Status": "Active",
            "Location": "All",
        },
        ("Total Agents",), ("Agents",), "relevant",
        "Active e-money service-channel infrastructure alongside current use among survey ever-users.",
        "Agent counts do not measure user ownership, availability to individuals, or transactions. "
        "The district sum exceeds the national KPI in all four stored snapshots; preserve the "
        "reconciliation warning and do not infer coverage or inclusion progress.",
    ),
    _mapping(
        "qf4_05", "Current mobile-money operator use among ever-users", "inclusion",
        _inclusion_filters("E-money issuers"),
        ("Subscribers",), ("Customers",), "uncertain",
        "Potential e-money subscriber context.",
        "The NBR subscriber definition and denominator are undocumented. The survey rate is "
        "among respondents routed from mobile-money ever-use, while district Customers are "
        "administrative counts; neither is directly comparable.",
    ),
    _mapping(
        "qf5_05_6", "Mobile-money transfer activity among ever-users", "mobile_banking",
        _MOBILE_BANKING_FILTERS,
        ("Use Mobile Banking",), ("Customers",), "conditional",
        "A distinct bank digital-channel signal alongside survey-reported mobile-money transfers.",
        "Mobile banking is not mobile money, and administrative Customers are not transaction "
        "counts. The national KPI unit/denominator is not documented; retain the source value, "
        "reporting date, and filters without comparing levels or inferring substitution.",
        "Show only the exact active-account, all-institution, all-demographic scope recorded "
        "by NBR; preserve the NBR metric label and unit as captured.",
    ),
    _mapping(
        "h3_09", "Informal-group borrowing in the past 12 months", "credit",
        _CREDIT_FILTERS,
        ("Total Customers",), ("Customers",), "relevant",
        "Regulated-credit customer activity as context alongside informal-group borrowing.",
        "NBR customers are an administrative count and are not the same people or borrowing "
        "sources as the FinScope group-loan measure. This does not measure formal credit "
        "availability to group borrowers or imply a relationship between the series.",
    ),
    _mapping(
        "i5a_1", "Medical-insurance coverage", "insurance",
        _INSURANCE_FILTERS,
        ("Total Policy Holders",), ("Policy Holders",), "relevant",
        "Active insurance-policy-holder counts as sector context alongside survey-reported medical coverage.",
        "The NBR count includes the page's unfiltered insurance types and is not a medical "
        "insurance prevalence estimate, unique-person count, or survey-equivalent measure.",
    ),
    _mapping(
        "qf1_06", "Ever used Umurenge SACCO", "branches",
        {"Institution Type": "Sacco", "Branch Status": "Active", "Location": "All"},
        ("Total Branches",), ("Branches",), "relevant",
        "Active SACCO infrastructure context for survey-reported ever-use.",
        "Branches describe cooperative infrastructure, not membership or individual use.",
    ),
    _mapping(
        "h2_1", "Borrowing in the past 12 months", "credit",
        _CREDIT_FILTERS, ("Borrowed",), ("Customers",), "uncertain",
        "Potential administrative credit activity.",
        "The reporting period, unit, and customer-count uniqueness are undocumented; this is not the survey's 12-month measure.",
    ),
    _mapping(
        "g3a_17", "Not saving", "savings",
        _SAVINGS_FILTERS, ("Saved",), ("Customers",), "uncertain",
        "Potential recorded savings-service activity.",
        "Definition and customer-count uniqueness are undocumented; this is not the inverse of not saving.",
    ),
    _mapping(
        "g3a_17", "Not saving", "depositors",
        _SAVINGS_FILTERS, ("Are Depositors",), ("Customers",), "uncertain",
        "Potential recorded deposit-taking activity.",
        "This does not cover all saving mechanisms and is not the inverse of not saving.",
    ),
    _mapping(
        "g3a_11", "Saving with a group", "inclusion",
        _inclusion_filters("Sacco"), ("SACCO Customers", "Total Customers"),
        ("Customers",), "uncertain", "Cooperative-service context only.",
        "SACCO customers do not establish group-saving participation or cover other group forms.",
    ),
    _mapping(
        "g3a_11", "Saving with a group", "branches",
        {"Institution Type": "Sacco", "Branch Status": "Active", "Location": "All"},
        ("Total Branches",), ("Branches",), "relevant",
        "Cooperative infrastructure context only.",
        "The national KPI exceeds the named-district sum by three in stored observations.",
    ),
    _mapping(
        "g3a_11", "Saving with a group", "agents",
        {
            "Gender": "All",
            "Institution Type": "Sacco",
            "Agent Status": "Active",
            "Location": "All",
        },
        ("Total Agents",), ("Agents",), "unsuitable",
        "Potential cooperative service-channel context.",
        "Stored observations cover only three districts; unsuitable for district-level monitoring.",
    ),
    _mapping(
        "qf4_06", "SACCO use", "inclusion",
        _inclusion_filters("Sacco"), ("SACCO Customers", "Total Customers"),
        ("Customers",), "uncertain", "Potential SACCO customer activity.",
        "Customer uniqueness and equivalence to Umurenge SACCO use are not established.",
    ),
    _mapping(
        "qf4_06", "SACCO use", "branches",
        {"Institution Type": "Sacco", "Branch Status": "Active", "Location": "All"},
        ("Total Branches",), ("Branches",), "relevant",
        "Recorded active SACCO infrastructure.",
        "The national KPI exceeds the named-district sum by three in stored observations.",
    ),
    _mapping(
        "qf4_06", "SACCO use", "agents",
        {
            "Gender": "All",
            "Institution Type": "Sacco",
            "Agent Status": "Active",
            "Location": "All",
        },
        ("Total Agents",), ("Agents",), "unsuitable",
        "Potential SACCO service-channel activity.",
        "Stored observations cover only three districts; unsuitable for district-level monitoring.",
    ),
)

NO_RELEVANT_NBR_DATA = {
    "e9b": "No relevant data identified from the NBR data currently available to this project.",
    "qf4_10": "No relevant data identified from the NBR data currently available to this project.",
    "qf1_10": (
        "NBR branch and regulated-provider counts do not represent use of informal "
        "savings groups such as VSLAs, tontines, or ikibina."
    ),
}


def _build_selections() -> tuple[PageSelection, ...]:
    grouped: dict[tuple[str, tuple[tuple[str, str], ...]], list[ApprovedNBRMapping]] = {}
    for mapping in APPROVED_MAPPINGS:
        key = (mapping.page_id, tuple(sorted(mapping.filters.items())))
        grouped.setdefault(key, []).append(mapping)

    selections = []
    for (page_id, filter_items), mappings in grouped.items():
        purpose = " ".join(
            f"{mapping.indicator_variable} ({mapping.status}): "
            f"{mapping.relevance} {mapping.limitations}"
            for mapping in mappings
        )
        selections.append(
            PageSelection(
                page_id=page_id,
                filters=dict(filter_items),
                purpose=purpose,
                kpi_labels=tuple(dict.fromkeys(
                    label for mapping in mappings for label in mapping.kpi_labels
                )),
                table_labels=tuple(dict.fromkeys(
                    label for mapping in mappings for label in mapping.table_labels
                )),
                historical_monitoring_eligible=all(
                    mapping.status != "unsuitable" for mapping in mappings
                ),
            )
        )
    return tuple(selections)


SELECTIONS = _build_selections()
UNSUITABLE_SERIES_KEYS = {
    (selection.page_id, json.dumps(selection.filters, ensure_ascii=False, sort_keys=True))
    for selection in SELECTIONS
    if not selection.historical_monitoring_eligible
}

_KPI_COUNT_LABELS = {
    "female customers",
    "male customers",
    "total accounts",
    "total customers",
    "total policy holders",
    "sacco customers",
    "total agents",
    "total branches",
    "total pos",
}
_TABLE_UNITS = {
    "customers": "count",
    "policy holders": "count",
    "agents": "count",
    "branches": "count",
    "pos": "count",
    "rank": "rank",
}
_KPI_TABLE_FIELDS = {
    "customers": "Total Customers",
    "policy holders": "Total Policy Holders",
    "agents": "Total Agents",
    "branches": "Total Branches",
    "pos": "Total POS",
}

NATIONAL_FIELDS = (
    "source_page",
    "reporting_date",
    "collected_at",
    "source_type",
    "metric_type",
    "metric_label",
    "value_raw",
    "value_numeric",
    "unit",
    "unit_status",
    "institution_type",
    "filters_json",
    "filters_requested_json",
    "geography_level",
    "run_id",
    "combo_key",
    "selection_purpose",
    "data_quality_status",
    "source_url",
    "source_name",
    "date_source",
    "dashboard_date",
    "run_status",
    "run_error",
    "repeated_snapshot_warning",
    "content_hash",
    "combination_content_hash",
    "ordinal",
    "source_metric_json",
    "source_observation_json",
    "source_run_json",
)
DISTRICT_FIELDS = (
    "source_page",
    "reporting_date",
    "collected_at",
    "source_type",
    "metric_label",
    "value_raw",
    "value_numeric",
    "unit",
    "unit_status",
    "institution_type",
    "filters_json",
    "filters_requested_json",
    "district",
    "district_id",
    "geography_level",
    "geography_status",
    "run_id",
    "combo_key",
    "selection_purpose",
    "data_quality_status",
    "source_url",
    "source_name",
    "date_source",
    "dashboard_date",
    "run_status",
    "run_error",
    "repeated_snapshot_warning",
    "content_hash",
    "combination_content_hash",
    "row_index",
    "rank",
    "source_column",
    "source_columns_json",
    "source_values_json",
    "source_numbers_json",
    "source_cells_json",
    "source_row_json",
    "source_run_json",
)
COVERAGE_FIELDS = (
    "source_page",
    "reporting_date",
    "filters_json",
    "selection_purpose",
    "run_id",
    "combo_key",
    "run_status",
    "table_status",
    "expected_table_rows",
    "source_table_rows",
    "known_districts",
    "missing_district_count",
    "missing_district_names_json",
    "unknown_district_rows",
    "unmatched_district_rows",
    "kpi_metric_count",
    "kpi_labels_json",
    "stored_kpi_labels_json",
    "excluded_kpi_labels_json",
    "table_columns_json",
    "repeated_snapshot_warning",
    "repeated_content_across_dates",
    "content_hash",
    "combination_content_hash",
    "table_total_label",
    "table_total_numeric",
    "national_total_label",
    "national_total_numeric",
    "table_minus_national",
    "validation_status",
    "validation_messages_json",
)
HISTORICAL_CHANGE_FIELDS = (
    "source_page",
    "metric_label",
    "unit",
    "filters_json",
    "district",
    "district_id",
    "geography_level",
    "from_reporting_date",
    "to_reporting_date",
    "elapsed_days",
    "from_value_raw",
    "to_value_raw",
    "from_value_numeric",
    "to_value_numeric",
    "absolute_change",
    "percent_change",
    "from_collected_at",
    "to_collected_at",
    "from_run_id",
    "to_run_id",
    "from_combo_key",
    "to_combo_key",
    "review_flags_json",
    "data_quality_status",
)


class ExtractionValidationError(RuntimeError):
    """Raised when a caller requests strict validation and issues are found."""

    def __init__(self, messages: list[str]):
        self.messages = messages
        super().__init__("District Explorer extraction validation failed:\n- " + "\n- ".join(messages))


@dataclass
class DistrictExplorerExtraction:
    national_rows: list[dict[str, Any]]
    district_rows: list[dict[str, Any]]
    coverage_rows: list[dict[str, Any]]
    validation_errors: list[str]
    reporting_dates: tuple[str, ...] = REPORTING_DATES

    @property
    def historical_changes_rows(self) -> list[dict[str, Any]]:
        return calculate_historical_changes(self.district_rows, self.reporting_dates)

    def to_dataframes(self):
        """Return the three stable output schemas as pandas DataFrames."""
        import pandas as pd

        return (
            pd.DataFrame(self.national_rows, columns=NATIONAL_FIELDS),
            pd.DataFrame(self.district_rows, columns=DISTRICT_FIELDS),
            pd.DataFrame(self.coverage_rows, columns=COVERAGE_FIELDS),
        )

    def to_historical_changes_dataframe(self):
        """Return historical district changes without changing export schemas."""
        import pandas as pd

        return pd.DataFrame(
            self.historical_changes_rows,
            columns=HISTORICAL_CHANGE_FIELDS,
        )


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=_json_default)


def _json_default(value: Any) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _format_number(value: int | float) -> str:
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, int):
        return f"{value:,}"
    return f"{value:,.10f}".rstrip("0").rstrip(".")


def parse_numeric_value(raw: Any) -> int | float | None:
    """Parse plain numbers or percentages without changing the source value."""
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return raw if math.isfinite(raw) else None
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not re.fullmatch(r"-?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?%?", text):
        return None
    value = text.removesuffix("%").replace(",", "")
    return float(value) if "." in value else int(value)


def _unit(raw: Any, label: str, is_kpi: bool) -> tuple[str, str]:
    if isinstance(raw, str) and raw.strip().endswith("%"):
        return "percent", "source_value"
    normalized_label = label.strip().casefold()
    if is_kpi and normalized_label in _KPI_COUNT_LABELS:
        return "count", "configured_source_label"
    if not is_kpi and normalized_label in _TABLE_UNITS:
        return _TABLE_UNITS[normalized_label], "source_column"
    return "", "unresolved"


def _selection_id(selection: PageSelection) -> tuple[str, str]:
    return selection.page_id, _json(selection.filters)


def _district_lookup(
    known_districts: Mapping[str, str] | set[str] | None,
) -> dict[str, tuple[str, str]]:
    if known_districts is None:
        known_districts = load_district_reference()
    if isinstance(known_districts, Mapping):
        return {
            str(name).strip().casefold(): (str(name).strip(), str(identifier))
            for name, identifier in known_districts.items()
        }
    return {str(name).strip().casefold(): (str(name).strip(), "") for name in known_districts}


def load_district_reference(
    path: Path | None = None,
) -> dict[str, str]:
    """Load exact district names and geoBoundaries shape IDs."""
    boundary_path = path or PROJECT_ROOT / "geoBoundaries-RWA-ADM2.geojson"
    geojson = json.loads(boundary_path.read_text(encoding="utf-8"))
    reference = {
        str(feature.get("properties", {}).get("shapeName", "")).strip():
        str(feature.get("properties", {}).get("shapeID", "")).strip()
        for feature in geojson.get("features", [])
        if feature.get("properties", {}).get("shapeName")
    }
    if not reference:
        raise ValueError(f"No district shapeName values found in {boundary_path}.")
    return reference


def _base_metadata(
    selection: PageSelection,
    run: Mapping[str, Any],
    record: Mapping[str, Any],
) -> dict[str, Any]:
    filters = run.get("filters")
    return {
        "source_page": run.get("page", selection.page_id),
        "reporting_date": run.get("snapshot_date", ""),
        "collected_at": _json_default(
            record.get("collected_at") or run.get("collected_at")
        )
        if record.get("collected_at") is not None or run.get("collected_at") is not None
        else "",
        "source_type": "administrative_dashboard",
        "institution_type": (
            filters.get("Institution Type", "")
            if isinstance(filters, Mapping)
            else ""
        ),
        "filters_json": _json(filters),
        "filters_requested_json": _json(run.get("filters_requested")),
        "run_id": run.get("run_id", ""),
        "combo_key": run.get("combo_key", ""),
        "selection_purpose": selection.purpose,
        "source_url": record.get("source_url") or run.get("source_url", ""),
        "source_name": record.get("source") or run.get("source", ""),
        "date_source": record.get("date_source") or run.get("date_source", ""),
        "dashboard_date": record.get("dashboard_date") or run.get("dashboard_date", ""),
        "run_status": run.get("status", ""),
        "run_error": run.get("error", ""),
        "repeated_snapshot_warning": bool(run.get("repeated_snapshot_warning", False)),
        "content_hash": record.get("content_hash") or run.get("content_hash", ""),
        "combination_content_hash": record.get("combination_content_hash")
        or run.get("content_hash", ""),
        "source_run_json": _json(run),
    }


def _record_link_errors(
    record: Mapping[str, Any],
    run: Mapping[str, Any],
    selection: PageSelection,
    expected_date: str,
    source_name: str,
) -> list[str]:
    errors = []
    for field in ("page", "snapshot_date", "combo_key", "run_id"):
        if record.get(field) != run.get(field):
            errors.append(
                f"{source_name} {field} mismatch for {selection.page_id} "
                f"{expected_date}: {record.get(field)!r} != {run.get(field)!r}."
            )
    if record.get("filters") != dict(selection.filters):
        errors.append(
            f"{source_name} filter metadata mismatch for {selection.page_id} "
            f"{expected_date}: {_json(record.get('filters'))}."
        )
    if record.get("filters_requested") not in (None, dict(selection.filters)):
        errors.append(
            f"{source_name} requested-filter metadata mismatch for "
            f"{selection.page_id} {expected_date}."
        )
    if record.get("dashboard_date") != run.get("dashboard_date"):
        errors.append(
            f"{source_name} dashboard date mismatch for {selection.page_id} {expected_date}."
        )
    if (
        record.get("collected_at") is not None
        and run.get("collected_at") is not None
        and record.get("collected_at") != run.get("collected_at")
    ):
        errors.append(
            f"{source_name} collection timestamp mismatch for "
            f"{selection.page_id} {expected_date}."
        )
    for key in ("run_id", "combo_key"):
        if not run.get(key):
            errors.append(f"Missing {key} for {selection.page_id} {expected_date}.")
    return errors


def _table_values(row: Mapping[str, Any]) -> tuple[list[str], dict[str, Any]]:
    columns = row.get("columns")
    values = row.get("values")
    if isinstance(columns, list):
        source_columns = [str(column) for column in columns]
    elif isinstance(values, Mapping):
        source_columns = [str(column) for column in values]
    else:
        source_columns = []
    if isinstance(values, Mapping):
        return source_columns, dict(values)
    cells = row.get("cells")
    if isinstance(cells, list) and source_columns:
        return source_columns, dict(zip(source_columns, cells))
    return source_columns, {}


def _error(
    errors: list[str],
    messages: list[str],
    message: str,
) -> None:
    errors.append(message)
    messages.append(message)


def normalize_observations(
    runs: list[dict[str, Any]],
    kpi_documents: list[dict[str, Any]],
    table_documents: list[dict[str, Any]],
    known_districts: Mapping[str, str] | set[str] | None = None,
    reporting_dates: tuple[str, ...] = REPORTING_DATES,
    selections: tuple[PageSelection, ...] = SELECTIONS,
    strict: bool = False,
) -> DistrictExplorerExtraction:
    """Validate selected records and normalize them into long-form observations.

    Partial or failed combinations remain visible in coverage_rows and
    validation_errors; they are never represented as numeric zero.
    """
    errors: list[str] = []
    national_rows: list[dict[str, Any]] = []
    district_rows: list[dict[str, Any]] = []
    coverage_rows: list[dict[str, Any]] = []
    district_map = _district_lookup(known_districts)
    index = {page: position for position, page in enumerate(dict.fromkeys(
        selection.page_id for selection in selections
    ))}
    date_index = {reporting_date: position for position, reporting_date in enumerate(reporting_dates)}
    grouped_kpis: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    grouped_tables: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for document in kpi_documents:
        grouped_kpis[
            (document.get("page", ""), document.get("snapshot_date", ""), document.get("combo_key", ""))
        ].append(document)
    for document in table_documents:
        grouped_tables[
            (document.get("page", ""), document.get("snapshot_date", ""), document.get("combo_key", ""))
        ].append(document)

    candidate_runs: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    selection_by_key = {_selection_id(selection): selection for selection in selections}
    for run in runs:
        page = run.get("page")
        reporting_date = run.get("snapshot_date")
        filters = run.get("filters")
        if not isinstance(filters, Mapping):
            continue
        selection = selection_by_key.get((page, _json(filters)))
        if selection and reporting_date in reporting_dates:
            candidate_runs[(page, reporting_date, _json(filters))].append(run)

    combination_hash_dates: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    combination_rows_by_hash: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)

    for reporting_date in reporting_dates:
        for selection in selections:
            filters_json = _json(selection.filters)
            key = (selection.page_id, reporting_date, filters_json)
            matching_runs = candidate_runs.get(key, [])
            messages: list[str] = []
            run: Mapping[str, Any] = matching_runs[0] if matching_runs else {}
            if not matching_runs:
                _error(
                    errors,
                    messages,
                    f"Missing run for {selection.page_id} {reporting_date} filters={filters_json}.",
                )
            elif len(matching_runs) > 1:
                _error(
                    errors,
                    messages,
                    f"Duplicate run records for {selection.page_id} {reporting_date}.",
                )
            if run:
                status = run.get("status")
                if status != "complete":
                    _error(
                        errors,
                        messages,
                        f"Run is not complete for {selection.page_id} {reporting_date}: {status!r}.",
                    )
                if not run.get("run_id"):
                    _error(errors, messages, f"Missing run_id for {selection.page_id} {reporting_date}.")
                if run.get("filters_requested") != dict(selection.filters):
                    _error(errors, messages, f"Requested filters mismatch for {selection.page_id} {reporting_date}.")
                if not run.get("combo_key"):
                    _error(errors, messages, f"Missing combo_key for {selection.page_id} {reporting_date}.")
                if run.get("filters_key") != run.get("combo_key"):
                    _error(errors, messages, f"Run filter key mismatch for {selection.page_id} {reporting_date}.")
                if run.get("dashboard_date") != reporting_date:
                    _error(errors, messages, f"Dashboard reporting date mismatch for {selection.page_id} {reporting_date}.")

            run_id = run.get("run_id", "")
            combo_key = run.get("combo_key", "")
            group_key = (selection.page_id, reporting_date, combo_key)
            matching_kpis = grouped_kpis.get(group_key, []) if combo_key else []
            matching_tables = grouped_tables.get(group_key, []) if combo_key else []
            usable_run = bool(
                run and len(matching_runs) == 1 and run.get("status") == "complete"
            )
            if run and len(matching_kpis) != 1:
                _error(
                    errors,
                    messages,
                    f"Expected one KPI document for {selection.page_id} {reporting_date}; "
                    f"found {len(matching_kpis)}.",
                )
            if run and not matching_tables:
                _error(errors, messages, f"Missing table observations for {selection.page_id} {reporting_date}.")
            elif run and len(matching_tables) != int(run.get("table_rows", 0) or 0):
                _error(
                    errors,
                    messages,
                    f"Table row count mismatch for {selection.page_id} {reporting_date}: "
                    f"run={run.get('table_rows')!r}, observations={len(matching_tables)}.",
                )
            if run and run.get("table_status") != "extracted":
                _error(
                    errors,
                    messages,
                    f"Table is not marked extracted for {selection.page_id} {reporting_date}: "
                    f"{run.get('table_status')!r}.",
                )
            for document in matching_kpis:
                link_errors = _record_link_errors(
                    document, run, selection, reporting_date, "KPI"
                )
                messages.extend(link_errors)
                errors.extend(link_errors)
            for document in matching_tables:
                link_errors = _record_link_errors(
                    document, run, selection, reporting_date, "Table"
                )
                messages.extend(link_errors)
                errors.extend(link_errors)
            if usable_run and matching_kpis and len(matching_kpis) == 1:
                kpi_document = matching_kpis[0]
                metrics = kpi_document.get("kpis")
                if not isinstance(metrics, list) or not metrics:
                    _error(errors, messages, f"No KPI metrics for {selection.page_id} {reporting_date}.")
                    metrics = []
                if kpi_document.get("kpi_count") not in (None, len(metrics)):
                    _error(errors, messages, f"KPI count mismatch for {selection.page_id} {reporting_date}.")
                seen_kpis: set[tuple[Any, Any]] = set()
                for metric in metrics:
                    metric_key = (metric.get("metric_type"), metric.get("ordinal"))
                    if metric_key in seen_kpis:
                        _error(
                            errors,
                            messages,
                            f"Duplicate KPI metric key {metric_key!r} for {selection.page_id} {reporting_date}.",
                        )
                    seen_kpis.add(metric_key)
                stored_labels = [_text(metric.get("metric_label")) for metric in metrics]
                selected_labels = selection.kpi_labels or tuple(stored_labels)
                missing_kpi_labels = sorted(set(selected_labels) - set(stored_labels))
                if missing_kpi_labels:
                    _error(
                        errors,
                        messages,
                        f"Missing selected KPI labels for {selection.page_id} {reporting_date}: "
                        f"{', '.join(missing_kpi_labels)}.",
                    )
                selected_metrics = [
                    metric for metric in metrics
                    if _text(metric.get("metric_label")) in selected_labels
                ]
                for metric in selected_metrics:
                    raw = metric.get("metric_value")
                    label = _text(metric.get("metric_label"))
                    numeric = parse_numeric_value(raw)
                    source_numeric = metric.get("metric_value_numeric")
                    if numeric is not None and parse_numeric_value(source_numeric) != numeric:
                        _error(
                            errors,
                            messages,
                            f"KPI numeric value mismatch for {selection.page_id} {reporting_date} {label!r}.",
                        )
                    elif numeric is None:
                        reason = "missing" if raw is None or not _text(raw).strip() else "non-numeric"
                        _error(
                            errors,
                            messages,
                            f"{reason.capitalize()} KPI value preserved for "
                            f"{selection.page_id} {reporting_date} {label!r}: {raw!r}.",
                        )
                    unit, unit_status = _unit(raw, label, is_kpi=True)
                    base = _base_metadata(selection, run, kpi_document)
                    row = {
                        **base,
                        "metric_type": metric.get("metric_type", ""),
                        "metric_label": label,
                        "value_raw": raw,
                        "value_numeric": numeric,
                        "unit": unit,
                        "unit_status": unit_status,
                        "geography_level": "national",
                        "data_quality_status": "valid" if not messages else "warning",
                        "ordinal": metric.get("ordinal", ""),
                        "content_hash": kpi_document.get("content_hash", ""),
                        "combination_content_hash": (
                            kpi_document.get("combination_content_hash")
                            or run.get("content_hash", "")
                        ),
                        "source_metric_json": _json(metric),
                        "source_observation_json": _json(kpi_document),
                    }
                    national_rows.append(row)

            district_names: set[str] = set()
            known_district_names: set[str] = set()
            row_indexes: set[Any] = set()
            table_columns: list[str] = []
            unknown_count = 0
            unmatched_count = 0
            field_totals: dict[str, float] = defaultdict(float)
            field_total_valid: dict[str, bool] = defaultdict(lambda: True)
            for table_row in matching_tables if usable_run else []:
                row_index = table_row.get("row_index")
                if row_index in row_indexes:
                    _error(
                        errors,
                        messages,
                        f"Duplicate table row_index {row_index!r} for {selection.page_id} {reporting_date}.",
                    )
                row_indexes.add(row_index)
                columns, values = _table_values(table_row)
                for column in columns:
                    if column not in table_columns:
                        table_columns.append(column)
                district = _text(
                    table_row.get("district")
                    if table_row.get("district") is not None
                    else values.get("District", "")
                ).strip()
                lookup = district_map.get(district.casefold())
                if not district or district.casefold() == "unknown" or table_row.get("district_known") is False:
                    geography_level = "unknown"
                    geography_status = "unknown"
                    district_id = ""
                    unknown_count += 1
                elif lookup:
                    geography_level = "district"
                    geography_status = "matched"
                    district, district_id = lookup
                    district_names.add(district)
                    known_district_names.add(district)
                else:
                    geography_level = "unknown"
                    geography_status = "unmatched"
                    district_id = ""
                    unmatched_count += 1
                    district_names.add(f"unmatched:{district}")
                    _error(errors, messages, f"Unmatched district name {district!r} on {selection.page_id}.")

                base = _base_metadata(selection, run, table_row)
                selected_columns = (
                    columns
                    if not selection.table_labels
                    else [
                        column for column in columns
                        if column in selection.table_labels or column.casefold() == "rank"
                    ]
                )
                for column in selected_columns:
                    if column.casefold() == "district":
                        continue
                    raw = values.get(column)
                    numeric = parse_numeric_value(raw)
                    source_numbers = table_row.get("numbers")
                    source_numbers = source_numbers if isinstance(source_numbers, Mapping) else {}
                    stored_numeric = source_numbers.get(column)
                    if numeric is not None and parse_numeric_value(stored_numeric) != numeric:
                        _error(
                            errors,
                            messages,
                            f"Table numeric value mismatch for {selection.page_id} {reporting_date}, "
                            f"row {row_index}, field {column!r}.",
                        )
                    elif numeric is None:
                        reason = "missing" if raw is None or not _text(raw).strip() else "non-numeric"
                        _error(
                            errors,
                            messages,
                            f"{reason.capitalize()} table value preserved for "
                            f"{selection.page_id} {reporting_date}, row {row_index}, "
                            f"field {column!r}: {raw!r}.",
                        )
                    normalized_field = column.strip().casefold()
                    if normalized_field in _KPI_TABLE_FIELDS and numeric is not None:
                        field_totals[column] += float(numeric)
                    elif normalized_field in _KPI_TABLE_FIELDS:
                        field_total_valid[column] = False
                    unit, unit_status = _unit(raw, column, is_kpi=False)
                    output_row = {
                        **base,
                        "metric_label": column,
                        "value_raw": raw,
                        "value_numeric": numeric,
                        "unit": unit,
                        "unit_status": unit_status,
                        "district": district,
                        "district_id": district_id,
                        "geography_level": geography_level,
                        "geography_status": geography_status,
                        "data_quality_status": (
                            "valid" if not messages and geography_level == "district" else "warning"
                        ),
                        "row_index": row_index,
                        "rank": values.get("Rank", ""),
                        "source_column": column,
                        "content_hash": table_row.get("content_hash", ""),
                        "combination_content_hash": (
                            table_row.get("combination_content_hash")
                            or run.get("content_hash", "")
                        ),
                        "source_columns_json": _json(table_row.get("columns", columns)),
                        "source_values_json": _json(values),
                        "source_numbers_json": _json(source_numbers),
                        "source_cells_json": _json(table_row.get("cells", [])),
                        "source_row_json": _json(table_row),
                    }
                    district_rows.append(output_row)
                    combination_rows_by_hash[
                        (
                            selection.page_id,
                            combo_key,
                            _text(run.get("combination_content_hash") or run.get("content_hash")),
                        )
                    ].append(output_row)

            expected_rows = run.get("table_rows", "") if run else ""
            if run and isinstance(expected_rows, int) and row_indexes != set(range(expected_rows)):
                _error(
                    errors,
                    messages,
                    f"Table row-index coverage mismatch for {selection.page_id} {reporting_date}.",
                )
            if matching_tables and "District" not in table_columns:
                _error(
                    errors,
                    messages,
                    f"District column is missing for {selection.page_id} {reporting_date}.",
                )
            if matching_tables and len(table_columns) < 2:
                _error(
                    errors,
                    messages,
                    f"No district metric columns found for {selection.page_id} {reporting_date}.",
                )
            missing_table_labels = sorted(set(selection.table_labels) - set(table_columns))
            if matching_tables and missing_table_labels:
                _error(
                    errors,
                    messages,
                    f"Missing selected table labels for {selection.page_id} {reporting_date}: "
                    f"{', '.join(missing_table_labels)}.",
                )
            missing_district_names = sorted(
                name
                for key_name, (name, _identifier) in district_map.items()
                if key_name not in {district.casefold() for district in known_district_names}
            )
            if matching_tables and missing_district_names:
                _error(
                    errors,
                    messages,
                    f"Missing {len(missing_district_names)} known districts for "
                    f"{selection.page_id} {reporting_date}: {', '.join(missing_district_names)}.",
                )
            stored_labels = []
            if matching_kpis and isinstance(matching_kpis[0].get("kpis"), list):
                stored_labels = [
                    _text(metric.get("metric_label"))
                    for metric in matching_kpis[0]["kpis"]
                ]
            selected_labels = selection.kpi_labels or tuple(stored_labels)
            labels = [label for label in selected_labels if label in stored_labels]
            excluded_labels = [label for label in stored_labels if label not in selected_labels]

            discrepancy = None
            table_total_label = ""
            national_total_label = ""
            table_total_numeric: Any = ""
            national_total_numeric: Any = ""
            if matching_kpis and len(matching_kpis) == 1:
                metrics = matching_kpis[0].get("kpis", [])
                for field, total in field_totals.items():
                    if not field_total_valid[field]:
                        continue
                    matching_label = _KPI_TABLE_FIELDS.get(field.casefold())
                    matching_metric = next(
                        (
                            metric for metric in metrics
                            if metric.get("metric_label") == matching_label
                        ),
                        None,
                    )
                    if matching_metric is None:
                        continue
                    source_total = parse_numeric_value(matching_metric.get("metric_value"))
                    if source_total is None:
                        continue
                    table_total_label = field
                    national_total_label = matching_label or ""
                    table_total_numeric = int(total) if total.is_integer() else total
                    national_total_numeric = source_total
                    discrepancy = table_total_numeric - source_total
                    if discrepancy:
                        _error(
                            errors,
                            messages,
                            f"KPI/table total differs for {selection.page_id} {reporting_date} "
                            f"({table_total_label}: {_format_number(table_total_numeric)}; "
                            f"{national_total_label}: {_format_number(national_total_numeric)}).",
                        )
                    break

            repeated_warning = bool(run.get("repeated_snapshot_warning")) if run else False
            if repeated_warning:
                messages.append("Scraper flagged repeated snapshot content.")
            content_hash = _text(
                (matching_kpis[0].get("combination_content_hash") if matching_kpis else None)
                or (matching_tables[0].get("combination_content_hash") if matching_tables else None)
                or (run.get("content_hash") if run else "")
            )
            if content_hash:
                combination_hash_dates[(selection.page_id, combo_key, content_hash)].add(reporting_date)
            coverage_rows.append(
                {
                    "source_page": selection.page_id,
                    "reporting_date": reporting_date,
                    "filters_json": filters_json,
                    "selection_purpose": selection.purpose,
                    "run_id": run_id,
                    "combo_key": combo_key,
                    "run_status": run.get("status", "missing"),
                    "table_status": run.get("table_status", ""),
                    "expected_table_rows": expected_rows,
                    "source_table_rows": len(matching_tables),
                    "known_districts": len(
                        {name for name in district_names if not name.startswith("unmatched:")}
                    ),
                    "missing_district_count": len(missing_district_names),
                    "missing_district_names_json": _json(missing_district_names),
                    "unknown_district_rows": unknown_count,
                    "unmatched_district_rows": unmatched_count,
                    "kpi_metric_count": len(labels),
                    "kpi_labels_json": _json(labels),
                    "stored_kpi_labels_json": _json(stored_labels),
                    "excluded_kpi_labels_json": _json(excluded_labels),
                    "table_columns_json": _json(table_columns),
                    "repeated_snapshot_warning": repeated_warning,
                    "repeated_content_across_dates": False,
                    "content_hash": run.get("content_hash", "") if run else "",
                    "combination_content_hash": content_hash,
                    "table_total_label": table_total_label,
                    "table_total_numeric": table_total_numeric,
                    "national_total_label": national_total_label,
                    "national_total_numeric": national_total_numeric,
                    "table_minus_national": discrepancy if discrepancy is not None else "",
                    "validation_status": "valid" if not messages else "warning",
                    "validation_messages_json": _json(messages),
                }
            )

    repeated_keys = {
        key for key, snapshot_dates in combination_hash_dates.items() if len(snapshot_dates) > 1
    }
    for coverage in coverage_rows:
        candidate_hash = _text(coverage.get("combination_content_hash"))
        repeated_key = (
            coverage["source_page"],
            coverage["combo_key"],
            candidate_hash,
        )
        if candidate_hash and repeated_key in repeated_keys:
            coverage["repeated_content_across_dates"] = True
            coverage["validation_status"] = "warning"
            messages = json.loads(coverage["validation_messages_json"])
            messages.append("Combination content is identical across selected reporting dates.")
            coverage["validation_messages_json"] = _json(sorted(set(messages)))

    coverage_by_key = {
        (row["source_page"], row["reporting_date"], row["combo_key"]): row
        for row in coverage_rows
    }
    for rows in (national_rows, district_rows):
        for row in rows:
            coverage = coverage_by_key.get(
                (row["source_page"], row["reporting_date"], row["combo_key"])
            )
            if coverage and coverage["validation_status"] != "valid":
                row["data_quality_status"] = "warning"

    national_rows.sort(
        key=lambda row: (
            date_index.get(row["reporting_date"], len(date_index)),
            index.get(row["source_page"], len(index)),
            row["filters_json"],
            _text(row.get("metric_type")),
            _text(row.get("ordinal")),
        )
    )
    district_rows.sort(
        key=lambda row: (
            date_index.get(row["reporting_date"], len(date_index)),
            index.get(row["source_page"], len(index)),
            row["filters_json"],
            int(row["row_index"]) if str(row["row_index"]).isdigit() else -1,
            row["source_column"],
        )
    )
    coverage_rows.sort(
        key=lambda row: (
            date_index.get(row["reporting_date"], len(date_index)),
            index.get(row["source_page"], len(index)),
            row["filters_json"],
        )
    )
    if strict and errors:
        raise ExtractionValidationError(errors)
    return DistrictExplorerExtraction(
        national_rows=national_rows,
        district_rows=district_rows,
        coverage_rows=coverage_rows,
        validation_errors=errors,
        reporting_dates=reporting_dates,
    )


def calculate_historical_changes(
    district_rows: list[dict[str, Any]],
    reporting_dates: tuple[str, ...] = REPORTING_DATES,
) -> list[dict[str, Any]]:
    """Calculate adjacent-period changes for matched district count observations.

    Unknown locations, ranks, non-count units, and missing numeric values are
    excluded. Missing periods are not filled or bridged, and no projections are
    calculated.
    """
    ordered_dates = tuple(sorted(set(reporting_dates), key=date.fromisoformat))
    if len(ordered_dates) != len(reporting_dates):
        raise ValueError("Reporting dates must be unique.")
    parsed_dates = {value: date.fromisoformat(value) for value in ordered_dates}
    observations: dict[
        tuple[str, str, str, str, str], dict[str, dict[str, Any]]
    ] = defaultdict(dict)

    for row in district_rows:
        if (
            row.get("geography_level") != "district"
            or row.get("geography_status") != "matched"
            or row.get("unit") != "count"
        ):
            continue
        if (
            _text(row.get("source_page")),
            _text(row.get("filters_json")),
        ) in UNSUITABLE_SERIES_KEYS:
            continue
        reporting_date = _text(row.get("reporting_date"))
        if reporting_date not in parsed_dates:
            continue
        if parse_numeric_value(row.get("value_numeric")) is None:
            continue
        district_key = _text(row.get("district_id")) or _text(row.get("district")).casefold()
        key = (
            _text(row.get("source_page")),
            _text(row.get("filters_json")),
            _text(row.get("combo_key")),
            district_key,
            _text(row.get("metric_label")),
        )
        if reporting_date in observations[key]:
            raise ValueError(
                "Duplicate district observation for "
                f"{key[0]} {reporting_date} {key[2]} {key[3]}."
            )
        observations[key][reporting_date] = row

    changes: list[dict[str, Any]] = []
    for (source_page, filters_json, _combo_key, _district_key, metric_label), dated_rows in observations.items():
        for from_date, to_date in zip(ordered_dates, ordered_dates[1:]):
            from_row = dated_rows.get(from_date)
            to_row = dated_rows.get(to_date)
            if from_row is None or to_row is None:
                continue
            from_value = parse_numeric_value(from_row.get("value_numeric"))
            to_value = parse_numeric_value(to_row.get("value_numeric"))
            if from_value is None or to_value is None:
                continue
            absolute_change = to_value - from_value
            percent_change = (
                absolute_change / from_value * 100
                if from_value > 0
                else None
            )
            review_flags = []
            if (
                percent_change is not None
                and abs(percent_change) >= CHANGE_REVIEW_THRESHOLD_PERCENT
            ):
                review_flags.append(
                    "Relative period change is at least "
                    f"{CHANGE_REVIEW_THRESHOLD_PERCENT}% and warrants source review."
                )
            if (
                from_row.get("data_quality_status") != "valid"
                or to_row.get("data_quality_status") != "valid"
            ):
                review_flags.append(
                    "At least one endpoint observation has a source-quality warning."
                )
            changes.append(
                {
                    "source_page": source_page,
                    "metric_label": metric_label,
                    "unit": "count",
                    "filters_json": filters_json,
                    "district": from_row.get("district", ""),
                    "district_id": from_row.get("district_id", ""),
                    "geography_level": "district",
                    "from_reporting_date": from_date,
                    "to_reporting_date": to_date,
                    "elapsed_days": (parsed_dates[to_date] - parsed_dates[from_date]).days,
                    "from_value_raw": from_row.get("value_raw", ""),
                    "to_value_raw": to_row.get("value_raw", ""),
                    "from_value_numeric": from_value,
                    "to_value_numeric": to_value,
                    "absolute_change": absolute_change,
                    "percent_change": percent_change,
                    "from_collected_at": from_row.get("collected_at", ""),
                    "to_collected_at": to_row.get("collected_at", ""),
                    "from_run_id": from_row.get("run_id", ""),
                    "to_run_id": to_row.get("run_id", ""),
                    "from_combo_key": from_row.get("combo_key", ""),
                    "to_combo_key": to_row.get("combo_key", ""),
                    "review_flags_json": _json(review_flags),
                    "data_quality_status": (
                        "valid" if not review_flags
                        else "warning"
                    ),
                }
            )

    changes.sort(
        key=lambda row: (
            row["from_reporting_date"],
            row["source_page"],
            row["filters_json"],
            row["district_id"],
            row["metric_label"],
        )
    )
    return changes


def _selected_pages() -> list[str]:
    return list(dict.fromkeys(selection.page_id for selection in SELECTIONS))


def read_mongodb_observations() -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Read the selected pages and common reporting dates from MongoDB."""
    try:
        from dotenv import load_dotenv
        from pymongo import MongoClient
    except ImportError as exc:
        raise RuntimeError(
            "Install the project requirements (python-dotenv and pymongo) to read MongoDB."
        ) from exc

    load_dotenv(PROJECT_ROOT / ".env")
    uri = os.getenv("MONGODB_URI") or os.getenv("MONGO_URI")
    if not uri:
        raise RuntimeError("Set MONGODB_URI or MONGO_URI in the project .env file.")
    client = MongoClient(uri, serverSelectionTimeoutMS=15000)
    try:
        client.admin.command("ping")
        database = client[DATABASE_NAME]
        query = {
            "page": {"$in": _selected_pages()},
            "snapshot_date": {"$in": list(REPORTING_DATES)},
        }
        runs = list(database[RUN_COLLECTION].find(query))
        observations = {
            collection: list(database[collection].find(query))
            for collection in (KPI_COLLECTION, TABLE_COLLECTION)
        }
        return runs, observations[KPI_COLLECTION], observations[TABLE_COLLECTION]
    finally:
        client.close()


def _write_csv(path: Path, fields: tuple[str, ...], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    field: _json(row.get(field)) if isinstance(row.get(field), (dict, list, tuple)) else row.get(field, "")
                    for field in fields
                }
            )


def export_district_explorer_observations(output_dir: Path | None = None) -> DistrictExplorerExtraction:
    """Read Mongo, validate selected records, and write three reproducible CSVs."""
    runs, kpis, tables = read_mongodb_observations()
    result = normalize_observations(
        runs,
        kpis,
        tables,
        known_districts=load_district_reference(),
    )
    target = output_dir or PROJECT_ROOT / "data" / "processed"
    _write_csv(
        target / "bnr_district_explorer_national_observations.csv",
        NATIONAL_FIELDS,
        result.national_rows,
    )
    _write_csv(
        target / "bnr_district_explorer_district_observations.csv",
        DISTRICT_FIELDS,
        result.district_rows,
    )
    _write_csv(
        target / "bnr_district_explorer_coverage.csv",
        COVERAGE_FIELDS,
        result.coverage_rows,
    )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "data" / "processed",
        help="Directory for the three District Explorer CSV outputs.",
    )
    args = parser.parse_args(argv)
    result = export_district_explorer_observations(args.output_dir)
    print(
        f"Exported {len(result.national_rows)} national KPI rows, "
        f"{len(result.district_rows)} district metric rows, and "
        f"{len(result.coverage_rows)} coverage rows to {args.output_dir}."
    )
    if result.validation_errors:
        print(f"Validation reported {len(result.validation_errors)} issue(s):", file=sys.stderr)
        for message in result.validation_errors:
            print(f"- {message}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
