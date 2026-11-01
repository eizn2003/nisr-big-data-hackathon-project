"""Structured access to the existing FinScope population-group estimates.

The module adapts the project's processed survey table for Population Groups.
It does not query MongoDB or recompute any indicator estimates.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from src.indicators import REGISTRY

DATASET_NAME = "population_group_indicators.csv"
GROUP_TYPE_COLUMN = "Group type"
GROUP_COLUMN = "Group"
RESPONDENTS_COLUMN = "Valid respondents"
GROUP_DIMENSIONS = {
    "Gender": {"source_variable": "b2", "source": "FinScope"},
    "Age group": {"source_variable": "b1", "source": "FinScope"},
    "Education": {"source_variable": "c4a", "source": "FinScope"},
    "Area": {"source_variable": "a6", "source": "FinScope"},
}
SOURCE_METADATA = {
    "source": "FinScope Rwanda 2024",
    "reporting_period": "2024",
    "date_source": "FinScope survey wave in source dataset name",
    "dataset": DATASET_NAME,
    "estimate_basis": "Precomputed weighted survey estimates from the processed dataset.",
    "respondent_count_basis": "Unweighted valid respondent count.",
    "collection_timestamp": None,
    "limitations": (
        "The processed table contains group estimates and valid respondent counts, "
        "not row-level survey responses or collection timestamps."
    ),
}
NBR_CONTEXT_STATUS = {
    "Gender": {
        "status": "not_displayed",
        "reason": (
            "NBR context is kept separate. Page-, metric-, filter-, and observation-level "
            "coverage has not been verified by this Population Groups data source."
        ),
    },
    "Age group": {
        "status": "not_displayed",
        "reason": (
            "NBR context is kept separate. The dashboard's Age Segment categories and "
            "observations must be verified for each approved metric before display."
        ),
    },
    "Education": {
        "status": "not_covered",
        "reason": "The NBR dashboard does not provide an education breakdown.",
    },
    "Area": {
        "status": "not_covered",
        "reason": "The approved NBR population-group context does not provide this FinScope area breakdown.",
    },
}


@dataclass(frozen=True)
class PopulationGroupQuery:
    status: str
    group_type: str
    indicator_variable: str
    observations: pd.DataFrame
    message: str = ""


@dataclass(frozen=True)
class PopulationGroupResults:
    observations: pd.DataFrame
    dimensions: dict[str, dict[str, Any]]
    indicators: dict[str, dict[str, Any]]
    source_metadata: dict[str, Any]
    nbr_context: dict[str, dict[str, str]]


def build_population_group_results(
    frame: pd.DataFrame,
) -> PopulationGroupResults:
    """Describe existing group estimates without changing their definitions."""
    required = {GROUP_TYPE_COLUMN, GROUP_COLUMN, RESPONDENTS_COLUMN}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(
            "The population-group dataset is missing columns: "
            + ", ".join(sorted(missing))
        )

    observations = frame.copy()
    observations[RESPONDENTS_COLUMN] = pd.to_numeric(
        observations[RESPONDENTS_COLUMN], errors="coerce"
    )
    indicator_metadata = {}
    for item in REGISTRY:
        column = item["column"]
        if column in observations.columns:
            observations[column] = pd.to_numeric(
                observations[column], errors="coerce"
            )
        indicator_metadata[item["variable"]] = {
            "variable": item["variable"],
            "label": item["label"],
            "column": column,
            "definition": item["description"],
            "interpretation": item["interpretation"],
            "status": "available" if column in observations.columns else "unavailable",
        }

    dimension_metadata = {}
    for group_type, config in GROUP_DIMENSIONS.items():
        matching = observations.loc[
            observations[GROUP_TYPE_COLUMN].astype("string").eq(group_type)
        ]
        category_values = matching[GROUP_COLUMN]
        categories = tuple(
            sorted(
                {
                    str(value)
                    for value in category_values.dropna()
                    if str(value).strip()
                }
            )
        )
        dimension_metadata[group_type] = {
            **config,
            "status": (
                "available" if categories
                else "unclassified_only" if not matching.empty
                else "unavailable"
            ),
            "categories": categories,
            "unclassified_rows": int(
                (
                    category_values.isna()
                    | category_values.astype("string").str.strip().eq("").fillna(False)
                ).sum()
            ),
        }

    return PopulationGroupResults(
        observations=observations,
        dimensions=dimension_metadata,
        indicators=indicator_metadata,
        source_metadata=dict(SOURCE_METADATA),
        nbr_context={key: dict(value) for key, value in NBR_CONTEXT_STATUS.items()},
    )


def load_population_group_results() -> PopulationGroupResults:
    """Load the established processed FinScope table through the project loader."""
    from src.data import load_population_groups

    return build_population_group_results(load_population_groups())


def query_population_groups(
    results: PopulationGroupResults,
    group_type: str,
    indicator_variable: str,
) -> PopulationGroupQuery:
    """Select existing observations or return an explicit unsupported status."""
    empty = results.observations.iloc[0:0].copy()
    if group_type not in results.dimensions:
        return PopulationGroupQuery(
            "unsupported_dimension",
            group_type,
            indicator_variable,
            empty,
            f"Unsupported population-group dimension: {group_type}.",
        )
    if results.dimensions[group_type]["status"] != "available":
        if results.dimensions[group_type]["status"] == "unclassified_only":
            selected = results.observations.loc[
                results.observations[GROUP_TYPE_COLUMN]
                .astype("string")
                .eq(group_type)
            ].copy()
            return PopulationGroupQuery(
                "unclassified_only",
                group_type,
                indicator_variable,
                selected,
                f"Only unclassified rows are available for {group_type}; group comparisons are unavailable.",
            )
        return PopulationGroupQuery(
            "dimension_unavailable",
            group_type,
            indicator_variable,
            empty,
            f"No observations are available for {group_type}.",
        )
    indicator = results.indicators.get(indicator_variable)
    if indicator is None:
        return PopulationGroupQuery(
            "unsupported_indicator",
            group_type,
            indicator_variable,
            empty,
            f"Unsupported FinScope indicator: {indicator_variable}.",
        )
    if indicator["status"] != "available":
        return PopulationGroupQuery(
            "indicator_unavailable",
            group_type,
            indicator_variable,
            empty,
            f"No processed estimates are available for {indicator['label']}.",
        )

    mask = (
        results.observations[GROUP_TYPE_COLUMN]
        .astype("string")
        .eq(group_type)
    )
    selected = results.observations.loc[mask].copy()
    if selected.empty:
        return PopulationGroupQuery(
            "no_observations",
            group_type,
            indicator_variable,
            selected,
            f"No observations are available for {group_type}.",
        )
    return PopulationGroupQuery(
        "available",
        group_type,
        indicator_variable,
        selected,
    )
