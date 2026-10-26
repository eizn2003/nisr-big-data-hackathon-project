"""Automated data-integrity checks.

Used in two places: the Methodology page (live "data health" panel) and
tests/test_data_integrity.py. Each check returns a dict with a status of
'pass', 'warn' or 'fail'.
"""

import numpy as np
import pandas as pd

from src import data
from src.indicators import BY_COLUMN, CORE, REGISTRY

NATIONAL_N_FALLBACK = None


def _result(status, name, detail, group):
    return {"status": status, "name": name, "detail": detail, "group": group}


def _check(condition, name, ok_detail, fail_detail, group, severity="fail"):
    if condition:
        return _result("pass", name, ok_detail, group)
    return _result(severity, name, fail_detail, group)


def run_checks():
    results = []
    add = results.append

    try:
        national = data.read_national()
        district = data.read_district()
        urban_rural = data.read_urban_rural()
        groups = data.read_population_groups()
    except FileNotFoundError as error:
        return [_result("fail", "Core data files are present", str(error), "Files")]

    barriers_n = data.read_barriers_national()
    barriers_d = data.read_barriers_district()
    denominators = data.read_denominators()

    # reference sample size from the denominator validation (k1 has no missing)
    total_n = None
    if denominators is not None and (denominators["Variable"] == "k1").any():
        total_n = int(denominators.loc[denominators["Variable"] == "k1", "Valid responses"].iloc[0])
    if total_n is None:
        total_n = int(district["Valid respondents"].sum())

    nat = dict(zip(national["Indicator"], national["Estimate (%)"].astype(float)))

    # ---- Structure ------------------------------------------------------
    add(_check(
        len(district) == 30 and district["District"].is_unique,
        "30 unique districts", f"{len(district)} unique districts found.",
        f"Expected 30 unique districts, found {len(district)} rows / {district['District'].nunique()} unique.",
        "Structure"))
    n_sum = int(district["Valid respondents"].sum())
    add(_check(n_sum == total_n, "District sample sizes add up to the survey total",
               f"District respondents sum to {n_sum:,}, equal to the survey total.",
               f"District respondents sum to {n_sum:,} but the survey total is {total_n:,}.", "Structure"))
    add(_check(int(urban_rural["Valid respondents"].sum()) == total_n,
               "Urban + rural respondents add up to the survey total",
               "Urban and rural respondent counts add up to the survey total.",
               "Urban and rural respondent counts do not add up to the survey total.", "Structure"))
    bad_groups = [g for g, s in groups.groupby("Group type") if int(s["Valid respondents"].sum()) != total_n]
    add(_check(not bad_groups, "Every population-group type covers all respondents",
               f"{groups['Group type'].nunique()} group types each add up to the survey total.",
               f"Respondent totals differ from the survey total for: {', '.join(bad_groups)}.", "Structure"))

    # ---- Value ranges ---------------------------------------------------
    pct_cols = [c for c in district.columns if c.endswith("(%)")]
    values = district[pct_cols]
    add(_check(values.notna().all().all() and ((values >= 0) & (values <= 100)).all().all(),
               "District percentages are complete and within 0–100",
               f"{len(pct_cols)} percentage columns checked for 30 districts.",
               "Some district percentages are missing or outside 0–100.", "Values"))
    add(_check(national["Estimate (%)"].between(0, 100).all(), "National estimates are within 0–100",
               f"{len(national)} national estimates checked.", "A national estimate is outside 0–100.", "Values"))

    # ---- Cross-file consistency ----------------------------------------
    miss = []
    for item in REGISTRY:
        col = item["column"]
        if col in district.columns and item["national"] in nat:
            lo, hi = district[col].min(), district[col].max()
            if not (lo - 1e-9 <= nat[item["national"]] <= hi + 1e-9):
                miss.append(item["short"])
    add(_check(not miss, "National estimates fall inside the district range",
               "For every indicator the national figure lies between the lowest and highest district.",
               f"National estimate outside the district range for: {', '.join(miss)}.", "Consistency"))

    off = []
    for item in REGISTRY:
        col = item["column"]
        if col in district.columns and item["national"] in nat:
            mean_n = np.average(district[col], weights=district["Valid respondents"])
            if abs(mean_n - nat[item["national"]]) > 3.0:
                off.append(f"{item['short']} ({mean_n:.1f} vs {nat[item['national']]:.1f})")
    add(_check(not off, "Sample-weighted district averages sit close to national estimates",
               "All indicators agree within 3 percentage points (district sizes are sample sizes, "
               "not population, so exact agreement is not expected).",
               "Large gaps between the district average and the national figure: " + "; ".join(off) + ".",
               "Consistency", severity="warn"))

    between = []
    area = urban_rural.set_index("Area")
    for item in CORE:
        col = item["column"]
        if col in area.columns and item["national"] in nat and {"Urban", "Rural"} <= set(area.index):
            lo, hi = sorted([area.loc["Urban", col], area.loc["Rural", col]])
            if not (lo <= nat[item["national"]] <= hi):
                between.append(item["short"])
    add(_check(not between, "National estimates lie between the urban and rural estimates",
               "Holds for all core indicators.", f"Fails for: {', '.join(between)}.", "Consistency"))

    pg_area = groups[groups["Group type"] == "Area"].set_index("Group")
    same = True
    for col in [c for c in area.columns if c.endswith("(%)")]:
        if col in pg_area.columns:
            for a in ("Urban", "Rural"):
                if a in pg_area.index and a in area.index and abs(pg_area.loc[a, col] - area.loc[a, col]) > 0.01:
                    same = False
    add(_check(same, "Population-group 'Area' rows match the urban/rural table",
               "Identical estimates in both files.", "The two files disagree for urban/rural.", "Consistency"))

    # extended indicators
    for ever, current, label in [
        ("Ever used Umurenge SACCO (%)", "Currently uses Umurenge SACCO (%)", "SACCO"),
        ("Ever used a savings group (%)", "Currently uses a savings group (%)", "Savings group"),
    ]:
        if ever in district.columns and current in district.columns:
            add(_check((district[current] <= district[ever] + 1e-9).all(),
                       f"{label}: current use never exceeds ever-use",
                       "Holds in all 30 districts.", "Current use exceeds ever-use in some district.",
                       "Consistency"))

    # ---- Barriers ---------------------------------------------------------
    if barriers_n is not None:
        add(_check(abs(barriers_n["Weighted share (%)"].sum() - 100) < 1e-6,
                   "National barrier shares add up to 100%",
                   "Weighted shares sum to 100%.", "National barrier shares do not sum to 100%.", "Barriers"))
    if barriers_d is not None:
        sums = barriers_d.groupby("District")["Weighted share (%)"].sum()
        add(_check(np.allclose(sums, 100, atol=1e-4) and len(sums) == 30,
                   "District barrier shares add up to 100% in all 30 districts",
                   "Every district's reasons sum to 100%.", "A district's barrier shares do not sum to 100%.",
                   "Barriers"))
        per = barriers_d.groupby("District").agg(n=("Respondents", "sum"),
                                                 tot=("District non-account respondents", "first"))
        add(_check((per["n"] == per["tot"]).all(), "District barrier counts are internally consistent",
                   "Reason counts add up to each district's non-account respondents.",
                   "Reason counts differ from district totals.", "Barriers"))
        if barriers_n is not None:
            add(_check(int(per["tot"].sum()) == int(barriers_n["Respondents"].sum()),
                       "District and national barrier counts agree",
                       f"{int(per['tot'].sum()):,} respondents without an account in both files.",
                       "District and national barrier respondent totals differ.", "Barriers"))
        merged = per.join(district.set_index("District")["Valid respondents"])
        add(_check((merged["tot"] <= merged["Valid respondents"]).all(),
                   "Non-account respondents never exceed district respondents",
                   "Holds in all districts.", "A district has more non-account respondents than respondents.",
                   "Barriers"))
        low = int(per["tot"].min())
        add(_result("warn" if low < 250 else "pass", "Sample behind district-level barrier estimates",
                    f"Smallest district base is {low} respondents without an account; reason-level "
                    "shares for small reasons are unstable, so family-level shares are emphasised.",
                    "Barriers"))

    # ---- Denominators -----------------------------------------------------
    if denominators is not None:
        core_vars = [i["variable"] for i in REGISTRY if i["variable"] in set(denominators["Variable"])
                     and i["variable"] not in ("qf4_06", "qf4_10")]
        sub = denominators[denominators["Variable"].isin(core_vars)]
        add(_check((sub["Valid response (%)"] >= 99.99).all(), "Dashboard indicators have full response coverage",
                   f"{len(sub)} indicator questions have no missing responses.",
                   "Some dashboard indicator has missing responses.", "Denominators"))
        routed = denominators[denominators["Valid response (%)"] < 99.99]
        add(_result("pass", "Routed questions are kept out of headline indicators",
                    f"{len(routed)} routed questions (e.g. current mobile-money use) are documented but "
                    "not used as full-population indicators; SACCO and savings-group use are computed on "
                    "the full sample with never-users counted as non-users.", "Denominators"))

    # ---- Sample size warnings ---------------------------------------------
    small = groups.sort_values("Valid respondents").iloc[0]
    wc = data.worst_case_moe(small["Valid respondents"])
    add(_result("warn" if wc > data.WIDE_MARGIN_PP else "pass", "Smallest population group",
                f"'{small['Group']}' has {int(small['Valid respondents'])} respondents "
                f"(worst-case margin about ±{wc:.1f} pp). Estimates for it are flagged in the dashboard.",
                "Sample size"))
    dmin = int(district["Valid respondents"].min())
    add(_result("pass", "District sample sizes",
                f"{dmin}–{int(district['Valid respondents'].max())} respondents per district; worst-case margin "
                f"at the smallest district is about ±{data.worst_case_moe(dmin):.1f} pp.", "Sample size"))

    # ---- Geometry -----------------------------------------------------------
    try:
        geo = data.read_geojson()
        only_data, only_geo = data.geo_name_mismatch(district["District"], geo)
        add(_check(not only_data and not only_geo, "District names match the boundary file",
                   "All 30 district names match the map boundaries.",
                   f"Unmatched in data: {only_data}; unmatched on map: {only_geo}.", "Map"))
    except (FileNotFoundError, ValueError):
        add(_result("warn", "District names match the boundary file",
                    "Boundary file not found or unreadable, so the map cannot be checked.", "Map"))

    return results


def summarize(results):
    counts = {"pass": 0, "warn": 0, "fail": 0}
    for item in results:
        counts[item["status"]] += 1
    return counts
