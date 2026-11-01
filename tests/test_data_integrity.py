"""Run with:  pytest -q   (from the project root)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import data, validation  # noqa: E402
from src.indicators import REGISTRY  # noqa: E402


def test_no_failed_integrity_checks():
    failed = [r for r in validation.run_checks() if r["status"] == "fail"]
    assert not failed, "\n".join(f"{r['name']}: {r['detail']}" for r in failed)


def test_registry_columns_exist_in_district_data():
    district = data.read_district()
    missing = [i["column"] for i in REGISTRY if i["column"] not in district.columns]
    assert not missing, f"Registry indicators missing from district data: {missing}"
    missing_denominators = [
        i["valid_count_column"]
        for i in REGISTRY
        if i["column"] in district.columns
        and i["valid_count_column"] not in district.columns
    ]
    assert not missing_denominators, (
        f"Registry denominators missing from district data: {missing_denominators}"
    )


def test_population_group_data_contains_registered_denominators():
    groups = data.read_population_groups()
    missing_denominators = [
        i["valid_count_column"]
        for i in REGISTRY
        if i["column"] in groups.columns
        and i["valid_count_column"] not in groups.columns
    ]
    assert not missing_denominators, (
        f"Registry denominators missing from population-group data: "
        f"{missing_denominators}"
    )


def test_district_cache_invalidates_when_processed_files_change(tmp_path, monkeypatch):
    monkeypatch.setattr(data, "DATA_DIR", tmp_path)
    district_csv = tmp_path / "district_financial_inclusion.csv"
    district_csv.write_text("District,Sample estimate\nKigali,1\n", encoding="utf-8")

    before = data.load_district()
    assert before.loc[0, "Sample estimate"] == 1

    district_csv.write_text(
        "District,Sample estimate\nKigali,200\n",
        encoding="utf-8",
    )
    after = data.load_district()
    assert after.loc[0, "Sample estimate"] == 200


def test_population_group_cache_invalidates_when_processed_file_changes(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(data, "DATA_DIR", tmp_path)
    groups_csv = tmp_path / "population_group_indicators.csv"
    groups_csv.write_text("Group,Sample estimate\nWomen,1\n", encoding="utf-8")

    before = data.load_population_groups()
    assert before.loc[0, "Sample estimate"] == 1

    groups_csv.write_text(
        "Group,Sample estimate\nWomen,200\n",
        encoding="utf-8",
    )
    after = data.load_population_groups()
    assert after.loc[0, "Sample estimate"] == 200


def test_registry_has_a_national_estimate():
    national = data.read_national()
    missing = [i["national"] for i in REGISTRY if i["national"] not in set(national["Indicator"])]
    assert not missing, f"No national estimate for: {missing}"


def test_margin_of_error_behaves():
    assert data.moe_pp(50, 400) > data.moe_pp(10, 400)
    assert data.moe_pp(20, 400) > data.moe_pp(20, 1600)
    assert data.moe_pp(20, 400, deff=2) > data.moe_pp(20, 400)
