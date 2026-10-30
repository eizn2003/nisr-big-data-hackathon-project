"""Data layer: loaders, light preparation and uncertainty helpers.

Every loader has a plain function (used by validation and tests) and a
cached Streamlit wrapper (used by the pages).
"""

import json
import math
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "processed"
GEOJSON_PATH = ROOT / "geoBoundaries-RWA-ADM2.geojson"
FEATURE_PROP = "shapeName"


def _csv(name, required=True):
    path = DATA_DIR / name
    if not path.exists():
        if required:
            raise FileNotFoundError(f"Missing data file: data/processed/{name}")
        return None
    return pd.read_csv(path)


# --------------------------------------------------------------------------
# Plain loaders
# --------------------------------------------------------------------------
def read_national():
    national = _csv("national_financial_inclusion.csv")
    extra = _csv("national_extended_indicators.csv", required=False)
    if extra is not None:
        national = national[~national["Indicator"].isin(extra["Indicator"])]
        national = pd.concat([national, extra], ignore_index=True)
    return national


def read_district():
    district = _csv("district_financial_inclusion.csv")
    district["District"] = district["District"].astype(str).str.strip()
    extended = _csv("district_extended_indicators.csv", required=False)
    if extended is not None:
        extended["District"] = extended["District"].astype(str).str.strip()
        extra_cols = [c for c in extended.columns if c not in district.columns]
        district = district.merge(extended[["District"] + extra_cols], on="District", how="left")
    return district


def read_urban_rural():
    return _csv("urban_rural_financial_inclusion.csv")


def read_population_groups():
    return _csv("population_group_indicators.csv")


def read_barriers_national():
    barriers = _csv("bank_account_barriers.csv", required=False)
    return None if barriers is None else add_barrier_labels(barriers, "k17")


def read_barriers_district():
    barriers = _csv("district_bank_account_barriers.csv", required=False)
    if barriers is None:
        return None
    barriers["District"] = barriers["District"].astype(str).str.strip()
    return add_barrier_labels(barriers, "Reason")


def read_definitions():
    return _csv("indicator_definitions.csv", required=False)


def read_candidate_register():
    return _csv("indicator_candidate_register.csv", required=False)


def read_denominators():
    return _csv("indicator_denominator_validation.csv", required=False)


def read_geojson():
    if not GEOJSON_PATH.exists():
        raise FileNotFoundError("Boundary file geoBoundaries-RWA-ADM2.geojson not found in the project root.")
    with GEOJSON_PATH.open(encoding="utf-8") as file:
        return json.load(file)


# --------------------------------------------------------------------------
# Cached wrappers for pages
# --------------------------------------------------------------------------
load_national = st.cache_data(read_national)
load_district = st.cache_data(read_district)
load_urban_rural = st.cache_data(read_urban_rural)
load_population_groups = st.cache_data(read_population_groups)
load_barriers_national = st.cache_data(read_barriers_national)
load_barriers_district = st.cache_data(read_barriers_district)
load_definitions = st.cache_data(read_definitions)
load_candidate_register = st.cache_data(read_candidate_register)
load_denominators = st.cache_data(read_denominators)
load_geojson = st.cache_data(read_geojson)


def geo_summary(geojson):
    """District centroids (largest ring mean) and the map centre."""
    centers, lons, lats = {}, [], []
    for feature in geojson["features"]:
        geometry = feature["geometry"]
        rings = (
            [geometry["coordinates"][0]] if geometry["type"] == "Polygon"
            else [polygon[0] for polygon in geometry["coordinates"]]
        )
        ring = max(rings, key=len)
        name = feature["properties"].get(FEATURE_PROP)
        centers[name] = (
            sum(p[1] for p in ring) / len(ring),
            sum(p[0] for p in ring) / len(ring),
        )
        lons += [p[0] for p in ring]
        lats += [p[1] for p in ring]
    return centers, ((min(lats) + max(lats)) / 2, (min(lons) + max(lons)) / 2)


def geo_name_mismatch(districts, geojson):
    """Names present in one source but not the other."""
    geo = {f["properties"].get(FEATURE_PROP) for f in geojson["features"]}
    data = set(districts)
    return sorted(data - geo), sorted(geo - data)


# --------------------------------------------------------------------------
# Bank-account barriers
# --------------------------------------------------------------------------
BARRIER_LABELS = {
    "Does not need it - Insufficient or no money coming it to justify it":
        ("Does not need one / money too limited to justify it", "No need or too little income"),
    "Banks are too far away": ("Banks are too far away", "Access"),
    "Banking hours are not convenient": ("Banking hours not convenient", "Access"),
    "Cannot maintain the minimum balance": ("Cannot keep the minimum balance", "Cost"),
    "Bank service charges are too high": ("Service charges too high", "Cost"),
    "Does not have the documentation required": ("Lacks required documents", "Knowledge & paperwork"),
    "Does not know how to apply": ("Does not know how to apply", "Knowledge & paperwork"),
    "Does not understand benefits from having a bank account":
        ("Does not see the benefits", "Knowledge & paperwork"),
    "Does not trust banks": ("Does not trust banks", "Trust & permission"),
    "Need permission of someone else to open it": ("Needs someone else's permission", "Trust & permission"),
    "Can get services needed elsewhere in the community":
        ("Uses community alternatives", "Alternatives & product fit"),
    "Banks do not provide the products or services I need":
        ("Products do not fit needs", "Alternatives & product fit"),
    "Other specify": ("Other (not classified)", "Other"),
}
BARRIER_FAMILY_ORDER = [
    "No need or too little income", "Access", "Cost", "Knowledge & paperwork",
    "Trust & permission", "Alternatives & product fit", "Other",
]
BARRIER_FAMILY_COLORS = {
    "No need or too little income": "#B9C6CC",
    "Access": "#2F6DB5",
    "Cost": "#E0A12F",
    "Knowledge & paperwork": "#7B5EC2",
    "Trust & permission": "#C0508A",
    "Alternatives & product fit": "#4C9A52",
    "Other": "#8A9AA2",
}


def add_barrier_labels(frame, reason_col):
    frame = frame.copy()
    mapped = frame[reason_col].map(BARRIER_LABELS)
    frame["Reason (short)"] = [m[0] if isinstance(m, tuple) else r for m, r in zip(mapped, frame[reason_col])]
    frame["Barrier family"] = [m[1] if isinstance(m, tuple) else "Other" for m in mapped]
    return frame


def barrier_family_shares(barriers, by_district=False):
    keys = ["District", "Barrier family"] if by_district else ["Barrier family"]
    shares = barriers.groupby(keys)["Weighted share (%)"].sum().reset_index()
    return shares


# --------------------------------------------------------------------------
# Uncertainty helpers
# --------------------------------------------------------------------------
def moe_pp(p_percent, n, deff=1.0):
    """Illustrative 95% binomial margin under simple-random-sample assumptions.

    Uses the binomial formula with an optional design-effect multiplier. The
    supplied data omit strata and cluster identifiers, so this is not a
    design-correct margin; actual design-based uncertainty may differ.
    """
    if n is None or n <= 0 or pd.isna(p_percent):
        return float("nan")
    p = min(max(float(p_percent) / 100.0, 0.0), 1.0)
    return 1.96 * math.sqrt(deff * p * (1 - p) / float(n)) * 100.0


def worst_case_moe(n, deff=1.0):
    return moe_pp(50.0, n, deff)


WIDE_MARGIN_PP = 7.0


def margin_flag(n, deff=1.0):
    """'wide' when the worst-case margin exceeds 7 percentage points."""
    return "wide" if worst_case_moe(n, deff) > WIDE_MARGIN_PP else "ok"
