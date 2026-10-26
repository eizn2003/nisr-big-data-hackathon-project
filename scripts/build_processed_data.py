"""Rebuild every processed table from the FinScope 2024 survey file.

Usage (from the project root):
    python scripts/build_processed_data.py
    python scripts/build_processed_data.py --dta data/datasets/FinScope2024Rwanda.dta --out data/processed

It mirrors the logic in notebooks 02, 03 and 04 and removes the hand-typed
values (the notebooks hard-code the national emergency-fund and group-saving
estimates). It also fills in the newer indicators for the urban/rural and
population-group tables so every page can show all eight indicators.

Definitions
-----------
* Weighted estimate = 100 * sum(weight * yes) / sum(weight), weight = pop_wt.
* Direct questions use respondents with a valid answer as the denominator.
* "Current use" of a SACCO or savings group is routed from an "ever used"
  question, so never-users are counted as non-users (full-population denominator).
* Valid respondents = respondents with a positive weight.
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

WEIGHT = "pop_wt"
DISTRICT = "a2"
MOBILE_MONEY_ACTIVE = "You are a registered mobile money user"

# column label -> (survey variable, positive answer, full_population)
RULES = {
    "Owns a bank account (%)": ("k1", "Yes", False),
    "Registered mobile-money user (%)": ("f5", MOBILE_MONEY_ACTIVE, False),
    "Borrowed in the past 12 months (%)": ("h2_1", "Yes", False),
    "Does not save (%)": ("g3a_17", "Yes", False),
    "Has emergency funds (%)": ("e9b", "Yes", False),
    "Saves with a group (%)": ("g3a_11", "Yes", False),
    "Currently uses Umurenge SACCO (%)": ("qf4_06", "Yes", True),
    "Currently uses a savings group (%)": ("qf4_10", "Yes", True),
}
EXTENDED_RULES = {
    "Ever used Umurenge SACCO (%)": ("qf1_06", "Yes", True),
    "Currently uses Umurenge SACCO (%)": ("qf4_06", "Yes", True),
    "Ever used a savings group (%)": ("qf1_10", "Yes", True),
    "Currently uses a savings group (%)": ("qf4_10", "Yes", True),
}
CORE_FOUR = list(RULES)[:4]
DISTRICT_ORDER = CORE_FOUR[:4] + ["Valid respondents"] + list(RULES)[4:6]

NATIONAL_ROWS = {
    "Own bank account": ("Owns a bank account (%)", "k1", "Respondents who own a bank account"),
    "Registered mobile-money user": ("Registered mobile-money user (%)", "f5",
                                     "Respondents who describe themselves as registered mobile-money users"),
    "Borrowed in the past 12 months": ("Borrowed in the past 12 months (%)", "h2_1",
                                       "Respondents who reported borrowing in the past 12 months"),
    "Does not save": ("Does not save (%)", "g3a_17", "Respondents classified as not saving"),
    "Has emergency funds": ("Has emergency funds (%)", "e9b",
                            "Respondents who report setting aside emergency or rainy-day funds."),
    "Saves with a group": ("Saves with a group (%)", "g3a_11",
                           "Respondents who report saving with a group such as a cooperative, VSLA, tontine, or ikibina."),
}
NATIONAL_EXTENDED = {
    "Ever used Umurenge SACCO": ("Ever used Umurenge SACCO (%)", "qf1_06",
                                 "Respondents who have ever used an Umurenge SACCO."),
    "Currently uses Umurenge SACCO": ("Currently uses Umurenge SACCO (%)", "qf4_06",
                                      "Respondents who currently use an Umurenge SACCO. Respondents who never used one "
                                      "are counted as non-users (full-population denominator)."),
    "Ever used a savings group": ("Ever used a savings group (%)", "qf1_10",
                                  "Respondents who have ever used a savings group they save with or borrow from."),
    "Currently uses a savings group": ("Currently uses a savings group (%)", "qf4_10",
                                       "Respondents who currently use a savings group. Respondents who never used one "
                                       "are counted as non-users (full-population denominator)."),
}
AGE_BINS = [15, 24, 34, 44, 54, 64, float("inf")]
AGE_LABELS = ["16–24", "25–34", "35–44", "45–54", "55–64", "65+"]


def weighted_percent(frame, column, positive="Yes", full_population=False, weight=WEIGHT):
    """Weighted share answering `positive`, in percent."""
    w = pd.to_numeric(frame[weight], errors="coerce")
    usable = w.notna() & (w > 0)
    values = frame[column].astype("string").str.strip()
    base = usable if full_population else usable & values.notna()
    total = w[base].sum()
    if total == 0:
        return np.nan
    yes = (values.eq(positive).fillna(False)) & base
    return 100.0 * w[yes].sum() / total


def valid_respondents(frame, weight=WEIGHT):
    w = pd.to_numeric(frame[weight], errors="coerce")
    return int((w.notna() & (w > 0)).sum())


def estimate_row(frame, rules):
    return {label: weighted_percent(frame, col, pos, full) for label, (col, pos, full) in rules.items()}


def _grouped(frame, by):
    key = frame[by]
    if not isinstance(key.dtype, pd.CategoricalDtype):
        key = key.astype("category")
    return frame.groupby(key, observed=True, sort=True)


def build_tables(df):
    """Return every processed table as a dict of DataFrames."""
    out = {}

    # national
    rows = [
        {"Indicator": name, "Estimate (%)": weighted_percent(df, var, *(RULES[label][1:])),
         "Source variable": var, "Interpretation": text}
        for name, (label, var, text) in NATIONAL_ROWS.items()
    ]
    out["national_financial_inclusion.csv"] = pd.DataFrame(rows)
    rows = [
        {"Indicator": name, "Estimate (%)": weighted_percent(df, var, "Yes", True),
         "Source variable": var, "Interpretation": text}
        for name, (label, var, text) in NATIONAL_EXTENDED.items()
    ]
    out["national_extended_indicators.csv"] = pd.DataFrame(rows)

    # district
    d_rows, e_rows = [], []
    for name, group in _grouped(df, DISTRICT):
        base = {"District": str(name), "Valid respondents": valid_respondents(group)}
        d_rows.append({**base, **estimate_row(group, {k: v for k, v in RULES.items()
                                                      if k in DISTRICT_ORDER})})
        e_rows.append({**base, **estimate_row(group, EXTENDED_RULES)})
    district = pd.DataFrame(d_rows)
    out["district_financial_inclusion.csv"] = district[["District"] + DISTRICT_ORDER]
    out["district_extended_indicators.csv"] = pd.DataFrame(e_rows)

    # urban / rural and population groups (all eight dashboard indicators)
    area_rows = []
    for name, group in _grouped(df, "a6"):
        area_rows.append({"Area": str(name), "Valid respondents": valid_respondents(group),
                          **estimate_row(group, RULES)})
    out["urban_rural_financial_inclusion.csv"] = pd.DataFrame(area_rows)

    frame = df.copy()
    frame["Age group"] = pd.cut(frame["b1"], bins=AGE_BINS, labels=AGE_LABELS)
    group_cols = {"Gender": "b2", "Age group": "Age group", "Education": "c4a", "Area": "a6"}
    pg_rows = []
    for group_type, col in group_cols.items():
        for name, group in _grouped(frame, col):
            pg_rows.append({"Group type": group_type, "Group": str(name),
                            "Valid respondents": valid_respondents(group), **estimate_row(group, RULES)})
    out["population_group_indicators.csv"] = pd.DataFrame(pg_rows)

    # bank-account barriers (adults without an account who gave a reason)
    barrier = df.loc[(df["k1"] == "No") & df["k17"].notna(), [DISTRICT, "k17", WEIGHT]].copy()
    nat = (barrier.groupby("k17", observed=True)
           .agg(Respondents=("k17", "size"), Weighted_population=(WEIGHT, "sum")).reset_index())
    nat["Weighted share (%)"] = nat["Weighted_population"] / nat["Weighted_population"].sum() * 100
    out["bank_account_barriers.csv"] = nat.sort_values("Weighted share (%)", ascending=False).reset_index(drop=True)

    totals = (barrier.groupby(DISTRICT, observed=True)
              .agg(**{"District non-account respondents": ("k17", "size"),
                      "District weighted population": (WEIGHT, "sum")}).reset_index()
              .rename(columns={DISTRICT: "District"}))
    dist = (barrier.groupby([DISTRICT, "k17"], observed=True)
            .agg(Respondents=("k17", "size"), Weighted_population=(WEIGHT, "sum")).reset_index()
            .rename(columns={DISTRICT: "District", "k17": "Reason"}))
    dist = dist.merge(totals, on="District")
    dist["Weighted share (%)"] = dist["Weighted_population"] / dist["District weighted population"] * 100
    dist["District"] = dist["District"].astype(str)
    out["district_bank_account_barriers.csv"] = dist.sort_values(
        ["District", "Weighted share (%)"], ascending=[True, False]).reset_index(drop=True)
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    root = Path(__file__).resolve().parents[1]
    parser.add_argument("--dta", default=str(root / "data" / "datasets" / "FinScope2024Rwanda.dta"))
    parser.add_argument("--out", default=str(root / "data" / "processed"))
    args = parser.parse_args()

    df = pd.read_stata(args.dta, convert_categoricals=True)
    tables = build_tables(df)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, table in tables.items():
        numeric = table.select_dtypes("number").columns
        table[numeric] = table[numeric].round(4)
        table.to_csv(out_dir / name, index=False)
        print(f"wrote {name}: {len(table)} rows")
    print("Done. Run `pytest -q` to validate the rebuilt tables.")


if __name__ == "__main__":
    main()
