"""Tests the table-building logic on a small synthetic survey (no .dta needed)."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_processed_data as bp  # noqa: E402


def _toy():
    rng = np.random.default_rng(7)
    n = 600
    yn = lambda p: rng.choice(["Yes", "No"], n, p=[p, 1 - p])
    df = pd.DataFrame({
        "pop_wt": rng.uniform(0.5, 3.0, n),
        "a2": pd.Categorical(rng.choice(["Alpha", "Beta", "Gamma"], n)),
        "a6": pd.Categorical(rng.choice(["Urban", "Rural"], n), categories=["Urban", "Rural"]),
        "b1": rng.integers(16, 80, n),
        "b2": pd.Categorical(rng.choice(["Male", "Female"], n), categories=["Male", "Female"]),
        "c4a": pd.Categorical(rng.choice(["None", "Primary", "Secondary"], n),
                              categories=["None", "Primary", "Secondary"]),
        "k1": yn(0.2), "h2_1": yn(0.4), "g3a_17": yn(0.2), "e9b": yn(0.2), "g3a_11": yn(0.5),
        "f5": rng.choice([bp.MOBILE_MONEY_ACTIVE, "You are registered but you have never used mobile money services"], n),
        "qf1_06": yn(0.25), "qf1_10": yn(0.5),
    })
    df["qf4_06"] = np.where(df["qf1_06"].eq("Yes"), yn(0.8), None)   # routed
    df["qf4_10"] = np.where(df["qf1_10"].eq("Yes"), yn(0.9), None)
    df["k17"] = np.where(df["k1"].eq("No"), rng.choice(["A reason", "Another reason"], n), None)
    return df


def test_weighted_percent_matches_manual_calculation():
    df = _toy()
    yes = df["k1"].eq("Yes")
    expected = 100 * df.loc[yes, "pop_wt"].sum() / df["pop_wt"].sum()
    assert abs(bp.weighted_percent(df, "k1") - expected) < 1e-9


def test_routed_current_use_counts_never_users_as_non_users():
    df = _toy()
    current = df["qf4_06"].eq("Yes")
    expected = 100 * df.loc[current, "pop_wt"].sum() / df["pop_wt"].sum()
    got = bp.weighted_percent(df, "qf4_06", "Yes", full_population=True)
    assert abs(got - expected) < 1e-9
    ever = bp.weighted_percent(df, "qf1_06", "Yes", full_population=True)
    assert got <= ever


def test_tables_have_expected_structure():
    tables = bp.build_tables(_toy())
    assert len(tables["district_financial_inclusion.csv"]) == 3
    assert set(tables["urban_rural_financial_inclusion.csv"]["Area"]) == {"Urban", "Rural"}
    pg = tables["population_group_indicators.csv"]
    assert set(pg["Group type"]) == {"Gender", "Age group", "Education", "Area"}
    for group_type, sub in pg.groupby("Group type"):
        assert sub["Valid respondents"].sum() == 600, group_type
    shares = tables["district_bank_account_barriers.csv"].groupby("District")["Weighted share (%)"].sum()
    assert np.allclose(shares, 100)
    for col in bp.RULES:
        assert col in pg.columns and col in tables["urban_rural_financial_inclusion.csv"].columns
