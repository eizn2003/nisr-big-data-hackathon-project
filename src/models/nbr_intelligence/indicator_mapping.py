"""Evidence-grounded FinScope to NBR indicator relationships."""

from __future__ import annotations

from typing import Any

from src.data_sources.mongodb_district_explorer import (
    APPROVED_MAPPINGS,
    NO_RELEVANT_NBR_DATA,
)
from src.indicators import REGISTRY

FINSCOPE_REFERENCE_PERIOD = "FinScope Rwanda 2024"
FINSCOPE_POPULATION = "Rwanda residents aged 16 years and older"
FINSCOPE_WEIGHT = "pop_wt"

DISPLAYABLE_RELATIONSHIPS = frozenset({
    "contextual_indicator",
    "conditional_contextual_indicator",
})

_STATA_LABELS = {
    "k1": "K1.  you have a bank account in your name?",
    "f5": "F5. Which of the following statements best describes your experience with mobile",
    "h2_1": "H2_1. Borrowed money during the past 12 months",
    "g3a_17": "g3a. Saving with - Do not save",
    "e9b": "E9b. Set aside emergency/rainy-day funds to cover expenses",
    "g3a_11": "g3a. Saving with a group such as a coop, VSLA, tontine, ikibina",
    "qf4_06": "qf4_06. Do you currently use - Umurenge SACCO",
    "qf4_10": (
        "qf4_10. Do you currently use - Savings group you save with or borrow from"
    ),
    "qf4_05": "qf4_05. Do you currently use - Mobile money operator",
    "qf5_05_6": (
        "qf5_05_6. Mobile money operator-Sent money to, or received money from someone"
    ),
    "h3_09": (
        "h3. Borrowed money from a group such as a co-op, VLSA, tontine, ikibina"
    ),
    "i5a_1": "i5a_1. Medical insurance",
    "qf1_06": "qf1_06. Ever used - Umurenge SACCO",
    "qf1_10": "qf1_10. Ever used - Savings group",
}


def _survey_denominator(variable: str) -> str:
    validation_file = "data/processed/indicator_denominator_validation.csv"
    if variable in {"qf4_06", "qf4_10"}:
        ever_use_variable = "qf1_06" if variable == "qf4_06" else "qf1_10"
        return (
            "All respondents aged 16+; the processed estimate treats non-Yes "
            "current-use responses as non-use. In the current dataset, missing "
            f"values align exactly with respondents answering No to {ever_use_variable}; "
            "questionnaire routing was not independently verified. Estimates use "
            f"pop_wt. Item-valid and missing counts are in {validation_file}."
        )
    if variable in {"qf4_05", "qf5_05_6"}:
        return (
            "Valid responses among respondents aged 16+ who reported ever using "
            "a mobile-money operator (qf1_05=Yes); respondents outside this routed "
            "base are excluded. Estimates use pop_wt. Per-indicator valid counts "
            f"are in {validation_file}."
        )
    return (
        "Valid item responses among respondents aged 16+; estimates use pop_wt. "
        f"Per-indicator valid counts are in {validation_file}."
    )


def build_indicator_mapping() -> list[dict[str, Any]]:
    """Return mapping metadata while reusing the project's approved source mappings."""
    indicators = [dict(item) for item in REGISTRY]
    by_variable = {item["variable"]: item for item in indicators}
    mappings_by_variable: dict[str, list[dict[str, Any]]] = {
        variable: [] for variable in by_variable
    }

    for mapping in APPROVED_MAPPINGS:
        definition = by_variable.get(mapping.indicator_variable)
        if definition is None:
            continue
        mappings_by_variable[mapping.indicator_variable].append({
            "page": mapping.page_id,
            "filter_scope": dict(mapping.filters),
            "national_kpi_labels": list(mapping.kpi_labels),
            "district_table_labels": list(mapping.table_labels),
            "relationship": (
                "contextual_indicator"
                if mapping.status == "relevant"
                else "conditional_contextual_indicator"
                if mapping.status == "conditional"
                else "proxy_with_unresolved_definition"
                if mapping.status == "uncertain"
                else "unsuitable"
            ),
            "existing_mapping_status": mapping.status,
            "relevance": mapping.relevance,
            "limitations": mapping.limitations,
            "conditions": mapping.conditions,
            "suppressed": False,
            "suppression_reason": "",
            "unit_policy": (
                "Retain the NBR source label and unit metadata. Customer/count "
                "uniqueness and KPI denominators are not inferred."
            ),
            "available_levels": [
                level for level, labels in (
                    ("national", mapping.kpi_labels),
                    ("district", mapping.table_labels),
                ) if labels
            ],
            "demographic_policy": (
                "Use exact observed Gender or Youth/Non-Youth filters only where "
                "the NBR page exposes that filter. NBR Youth/Non-Youth categories "
                "are displayed separately and are not crosswalked to FinScope age bins."
            ),
        })

    result = []
    for variable, definition in by_variable.items():
        result.append({
            "variable": variable,
            "column": definition["column"],
            "original_indicator_label": definition["label"],
            "source_variable_label": _STATA_LABELS.get(variable, ""),
            "measurement_definition": definition["description"],
            "survey_reference_period": FINSCOPE_REFERENCE_PERIOD,
            "survey_population": FINSCOPE_POPULATION,
            "survey_weight": FINSCOPE_WEIGHT,
            "survey_denominator": _survey_denominator(variable),
            "geographic_and_demographic_scope": {
                "national": True,
                "district": True,
                "gender": variable in {item["variable"] for item in REGISTRY},
                "age_group": variable in {item["variable"] for item in REGISTRY},
                "education": variable in {item["variable"] for item in REGISTRY},
                "urban_rural": variable in {item["variable"] for item in REGISTRY},
            },
            "polarity": definition["polarity"],
            "interpretation": definition["interpretation"],
            "nbr_relationships": mappings_by_variable[variable],
            "nbr_no_relevant_data_reason": NO_RELEVANT_NBR_DATA.get(variable),
        })
    return result


INDICATOR_MAPPING = build_indicator_mapping()
MAPPING_BY_VARIABLE = {item["variable"]: item for item in INDICATOR_MAPPING}