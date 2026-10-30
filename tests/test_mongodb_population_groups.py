import pandas as pd
from pathlib import Path

from src.data_sources.mongodb_population_groups import (
    GROUP_TYPE_COLUMN,
    build_population_group_results,
    query_population_groups,
)
from src.indicators import REGISTRY


def _frame():
    return pd.DataFrame(
        [
            {
                "Group type": "Gender",
                "Group": "Male",
                "Valid respondents": "10",
                "Owns a bank account (%)": "25.5",
                "Registered mobile-money user (%)": "60",
                "Borrowed in the past 12 months (%)": "35",
            },
            {
                "Group type": "Gender",
                "Group": "Unknown",
                "Valid respondents": "2",
                "Owns a bank account (%)": "0",
                "Registered mobile-money user (%)": "",
                "Borrowed in the past 12 months (%)": "25",
            },
            {
                "Group type": "Gender",
                "Group": None,
                "Valid respondents": None,
                "Owns a bank account (%)": None,
                "Registered mobile-money user (%)": None,
                "Borrowed in the past 12 months (%)": None,
            },
            {
                "Group type": "Age group",
                "Group": "16–24",
                "Valid respondents": "5",
                "Owns a bank account (%)": "10",
                "Registered mobile-money user (%)": "40",
                "Borrowed in the past 12 months (%)": "15",
            },
        ]
    )


def test_dimensions_categories_and_indicator_availability_follow_source_schema():
    results = build_population_group_results(_frame())

    assert results.dimensions["Gender"]["status"] == "available"
    assert results.dimensions["Gender"]["categories"] == ("Male", "Unknown")
    assert results.dimensions["Gender"]["unclassified_rows"] == 1
    assert results.dimensions["Education"]["status"] == "unavailable"
    assert results.dimensions["Education"]["categories"] == ()
    assert results.indicators["k1"]["status"] == "available"
    assert results.indicators["k1"]["definition"] == next(
        item["description"] for item in REGISTRY if item["variable"] == "k1"
    )
    assert results.indicators["qf4_06"]["status"] == "unavailable"
    assert results.indicators["qf4_10"]["status"] == "unavailable"


def test_query_returns_existing_estimates_without_recalculating():
    results = build_population_group_results(_frame())
    query = query_population_groups(results, "Gender", "k1")

    assert query.status == "available"
    assert query.observations["Group"].iloc[:2].tolist() == ["Male", "Unknown"]
    assert pd.isna(query.observations["Group"].iloc[2])
    assert query.observations["Owns a bank account (%)"].iloc[:2].tolist() == [25.5, 0.0]
    assert query.observations["Valid respondents"].iloc[:2].tolist() == [10, 2]
    assert query.observations[GROUP_TYPE_COLUMN].eq("Gender").all()
    assert "weighted survey estimates" in results.source_metadata["estimate_basis"].lower()
    assert results.source_metadata["collection_timestamp"] is None
    assert not {
        "NBR value",
        "FinScope-NBR difference",
        "Percentage point difference",
        "Correlation",
    }.intersection(query.observations.columns)


def test_missing_values_unknown_groups_and_unsupported_combinations_are_explicit():
    results = build_population_group_results(_frame())

    assert pd.isna(results.observations.loc[1, "Registered mobile-money user (%)"])
    unsupported_dimension = query_population_groups(results, "District", "k1")
    assert unsupported_dimension.status == "unsupported_dimension"
    assert unsupported_dimension.observations.empty

    unavailable_indicator = query_population_groups(results, "Gender", "qf4_06")
    assert unavailable_indicator.status == "indicator_unavailable"
    assert unavailable_indicator.observations.empty

    unsupported_indicator = query_population_groups(results, "Gender", "made_up")
    assert unsupported_indicator.status == "unsupported_indicator"
    assert unsupported_indicator.observations.empty


def test_nbr_context_is_separate_and_education_is_not_mapped_to_nbr():
    results = build_population_group_results(_frame())

    assert results.nbr_context["Gender"]["status"] == "not_displayed"
    assert results.nbr_context["Age group"]["status"] == "not_displayed"
    assert results.nbr_context["Education"]["status"] == "not_covered"
    assert "education" in results.nbr_context["Education"]["reason"].lower()
    assert not any(
        column.casefold().startswith("nbr")
        for column in results.observations.columns
    )


def test_missing_required_schema_is_reported():
    try:
        build_population_group_results(pd.DataFrame({"Group": ["Male"]}))
    except ValueError as error:
        assert "Group type" in str(error)
        assert "Valid respondents" in str(error)
    else:
        raise AssertionError("Missing required columns should be reported.")


def test_dimension_with_only_unclassified_rows_is_not_treated_as_comparable():
    frame = _frame().loc[lambda data: data["Group type"].eq("Gender")].copy()
    frame["Group"] = None
    results = build_population_group_results(frame)

    assert results.dimensions["Gender"]["status"] == "unclassified_only"
    assert results.dimensions["Gender"]["unclassified_rows"] == len(frame)
    query = query_population_groups(results, "Gender", "k1")
    assert query.status == "unclassified_only"
    assert len(query.observations) == len(frame)
    assert "group comparisons are unavailable" in query.message


def test_current_processed_population_groups_preserve_available_dimensions_and_indicators():
    project_root = Path(__file__).resolve().parents[1]
    frame = pd.read_csv(
        project_root / "data" / "processed" / "population_group_indicators.csv"
    )
    results = build_population_group_results(frame)

    assert set(results.observations[GROUP_TYPE_COLUMN].dropna()) == {
        "Gender", "Age group", "Education", "Area"
    }
    assert results.dimensions["Education"]["status"] == "available"
    assert results.dimensions["Gender"]["categories"] == ("Female", "Male")
    assert results.dimensions["Age group"]["categories"] == (
        "16–24", "25–34", "35–44", "45–54", "55–64", "65+"
    )
    assert results.indicators["qf4_06"]["status"] == "unavailable"
    assert results.indicators["qf4_10"]["status"] == "unavailable"
