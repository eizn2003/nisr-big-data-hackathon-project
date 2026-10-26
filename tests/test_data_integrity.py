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


def test_registry_has_a_national_estimate():
    national = data.read_national()
    missing = [i["national"] for i in REGISTRY if i["national"] not in set(national["Indicator"])]
    assert not missing, f"No national estimate for: {missing}"


def test_margin_of_error_behaves():
    assert data.moe_pp(50, 400) > data.moe_pp(10, 400)
    assert data.moe_pp(20, 400) > data.moe_pp(20, 1600)
    assert data.moe_pp(20, 400, deff=2) > data.moe_pp(20, 400)
