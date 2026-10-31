"""Synthetic stand-ins for project modules that were not supplied (data, indicators,
Mongo-backed NBR loaders). They let the real page files run under Streamlit's AppTest.
This validates page wiring and Combined-mode logic only; it is NOT the real data."""

import sys, types, math
from pathlib import Path
import numpy as np
import pandas as pd
import streamlit as st

NAMES = [f"District {i:02d}" for i in range(30)]
SPEC = [  # variable, column, national, short, polarity, role, default
    (
        "k1",
        "Owns a bank account (%)",
        "Own bank account",
        "Bank account",
        "positive",
        "core",
        True,
    ),
    (
        "f5",
        "Registered mobile-money user (%)",
        "Registered mobile-money user",
        "Mobile money",
        "positive",
        "core",
        True,
    ),
    (
        "g3a_17",
        "Does not save (%)",
        "Does not save",
        "Doesn't save",
        "negative",
        "core",
        True,
    ),
    (
        "e9b",
        "Has emergency funds (%)",
        "Has emergency funds",
        "Emergency funds",
        "positive",
        "core",
        True,
    ),
    (
        "h2_1",
        "Borrowed in the past 12 months (%)",
        "Borrowed in the past 12 months",
        "Borrowing",
        "neutral",
        "supporting",
        False,
    ),
    (
        "g3a_11",
        "Saves with a group (%)",
        "Saves with a group",
        "Group saving",
        "positive",
        "supporting",
        False,
    ),
    (
        "qf4_06",
        "Currently uses Umurenge SACCO (%)",
        "Currently uses Umurenge SACCO",
        "SACCO",
        "positive",
        "supporting",
        False,
    ),
    (
        "qf4_10",
        "Currently uses a savings group (%)",
        "Currently uses a savings group",
        "Savings group",
        "positive",
        "supporting",
        False,
    ),
]
REG = []
for v, c, n, sh, pol, role, d in SPEC:
    REG.append(
        dict(
            variable=v,
            column=c,
            national=n,
            short=sh,
            label=c.replace(" (%)", ""),
            kpi_label=sh,
            polarity=pol,
            role=role,
            priority_default=d,
            accent="#1A8A7D",
            text_accent="#17746A",
            scale="Teal",
            description=f"{sh} description",
            interpretation=f"{sh} interpretation",
        )
    )
rng = np.random.default_rng(1)
DIST = pd.DataFrame(
    {"District": NAMES, "Valid respondents": rng.integers(400, 900, 30)}
)
for r in REG:
    DIST[r["column"]] = rng.uniform(10, 80, 30).round(2)
NAT = pd.DataFrame(
    {
        "Indicator": [r["national"] for r in REG],
        "Estimate (%)": [45.0 + i * 3 for i in range(8)],
    }
)
UR = pd.DataFrame(
    {
        "Area": ["Urban", "Rural"],
        "Valid respondents": [5000, 9000],
        **{r["column"]: [60.0, 40.0] for r in REG},
    }
)
GROUPS = []
for gt, groups in (
    ("Gender", ["Female", "Male"]),
    ("Age group", ["16-24", "25-34"]),
    ("Education", ["None", "Tertiary"]),
    ("Area", ["Urban", "Rural"]),
):
    for g in groups:
        GROUPS.append(
            {
                "Group type": gt,
                "Group": g,
                "Valid respondents": 300 if g != "None" else 150,
                **{r["column"]: float(rng.uniform(15, 75)) for r in REG},
            }
        )
GROUPS = pd.DataFrame(GROUPS)


def _mod(name, **attrs):
    m = types.ModuleType(name)
    m.__dict__.update(attrs)
    sys.modules[name] = m
    return m


def _rel(page, kpi, table, levels, kind="contextual_indicator", fs=None):
    return dict(
        page=page,
        relationship=kind,
        national_kpi_labels=kpi,
        district_table_labels=table,
        available_levels=levels,
        filter_scope=fs or {"Institution Type": "Banks"},
        limitations="Administrative count.",
        existing_mapping_status="relevant",
    )


MAPPING = {
    r["variable"]: dict(
        variable=r["variable"],
        original_indicator_label=r["label"],
        nbr_relationships=[],
        nbr_no_relevant_data_reason="NBR has no relevant series.",
    )
    for r in REG
}
# Mirrors the real configuration: mobile money has only an unapproved proxy (not shown).
MAPPING["f5"]["nbr_relationships"] = [
    _rel(
        "inclusion",
        ["Subscribers"],
        ["Customers"],
        ["national", "district"],
        kind="proxy_with_unresolved_definition",
    )
]
MAPPING["k1"]["nbr_relationships"] = [
    _rel(
        "branches",
        ["Total Branches"],
        ["Branches by District"],
        ["national", "district"],
    )
]
# Mirrors the real configuration: the SACCO-branch relationship is configured but declared suppressed.
MAPPING["g3a_11"]["nbr_relationships"] = [
    {
        **_rel(
            "branches",
            ["Total Branches"],
            ["Branches"],
            ["national", "district"],
            fs={"Institution Type": "Sacco"},
        ),
        "suppressed": True,
        "suppression_reason": "SACCO branches are not an approved proxy for saving with a group.",
    },
    _rel(
        "inclusion",
        ["SACCO Customers"],
        ["Customers"],
        ["national", "district"],
        kind="proxy_with_unresolved_definition",
    ),
]
# SYNTHETIC: a gender-capable page ("savings" exposes a dynamic Gender filter in nbr_pages.json) so the partial-coverage
# code path can be exercised. The real configuration has no approved relationship on such a page.
MAPPING["g3a_17"]["nbr_relationships"] = [
    _rel("savings", ["Saved"], [], ["national"], fs={"Institution Type": "All"})
]
MAPPING["qf4_06"]["nbr_relationships"] = [
    _rel("sacco", [], ["SACCO Branches"], ["district"])
]
MAPPING["qf4_10"]["nbr_relationships"] = [
    _rel("x", ["Groups"], [], ["national"], kind="proxy_with_unresolved_definition")
]


def _pts(
    metric, level, districts, unit, dates=("2026-06-30", "2026-10-24"), gender=None
):
    pts = []
    for d in dates:
        for g in districts:
            pts.append(
                dict(
                    page="p",
                    metric_label=metric,
                    geography=g,
                    geography_level=level,
                    reporting_date=d,
                    value=float(10 + len(g) + dates.index(d)),
                    unit=unit,
                    filters={},
                    source_record_id=f"{g}{d}",
                    source_type=(
                        "national_kpi" if level == "national" else "district_table"
                    ),
                    collected_at="x",
                    run_id="r",
                    combo_key="c",
                )
            )
    return pts


def _entry(metric, level, unit, points, filters=None):
    return dict(
        page="p",
        metric_label=metric,
        unit=unit,
        filters=filters or {"Institution Type": "Banks"},
        geography_level=level,
        relationship="contextual_indicator",
        limitations="Administrative count.",
        points=points,
    )


def load_ctx(
    variable, *, geography_level, geography=None, subgroup_type="", subgroup=""
):
    if variable in st.session_state.get("_stub_fail_vars", ()):
        raise RuntimeError("simulated read failure")
    if (
        variable == "g3a_17"
        and geography_level == "national"
        and subgroup_type == "Gender"
    ):
        if subgroup == "Female":
            return [
                _entry(
                    "Saved",
                    "national",
                    "customers",
                    _pts("Saved", "national", ["Rwanda"], "customers"),
                    {"Gender": "Female"},
                )
            ], "v1"
        return [], "v1"
    if variable == "k1" and geography_level == "national":
        return [
            _entry(
                "Total Branches",
                "national",
                "branches",
                _pts("Total Branches", "national", ["Rwanda"], "branches"),
            )
        ], "v1"
    if variable == "k1" and geography_level == "district":
        return [
            _entry(
                "Branches by District",
                "district",
                "branches",
                _pts("Branches by District", "district", NAMES[:25], "branches"),
            )
        ], "v1"
    if variable == "qf4_06" and geography_level == "district":
        return [
            _entry(
                "SACCO Branches",
                "district",
                "",
                _pts(
                    "SACCO Branches", "district", NAMES[:10], "", dates=("2026-10-24",)
                ),
            )
        ], "v1"
    return [], None


def install():
    root = str(Path(__file__).resolve().parents[1])
    for k in [k for k in list(sys.modules) if k == "src" or k.startswith("src.")]:
        del sys.modules[k]
    pkg = types.ModuleType("src")
    pkg.__path__ = [root + "/src"]
    sys.modules["src"] = pkg
    pages = types.ModuleType("src.pages")
    pages.__path__ = [root + "/src/pages"]
    sys.modules["src.pages"] = pages
    for k in [
        k
        for k in sys.modules
        if k.startswith("src.pages.") and k not in ("src.pages.combined_support",)
    ]:
        pass
    theme = {r["column"]: dict(national=r["national"], short=r["short"]) for r in REG}
    ind = _mod(
        "src.indicators",
        REGISTRY=REG,
        CORE=[r for r in REG if r["role"] == "core"],
        BY_COLUMN={r["column"]: r for r in REG},
        BY_NATIONAL={r["national"]: r for r in REG},
        PRIORITY_CANDIDATES=[
            r
            for r in REG
            if r["variable"] in ("k1", "f5", "g3a_17", "e9b", "g3a_11", "qf4_06")
        ],
        INDICATOR_THEME=theme,
        available=lambda frame: [r for r in REG if r["column"] in frame.columns],
    )
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "src.styles", str(Path(__file__).resolve().parents[1] / "src" / "styles.py")
    )
    styles = importlib.util.module_from_spec(spec)
    sys.modules["src.styles"] = styles
    spec.loader.exec_module(styles)
    feats = []
    centers = {}
    for i, n in enumerate(NAMES):
        x, y = 29 + (i % 6) * 0.3, -2.4 - (i // 6) * 0.3
        feats.append(
            {
                "type": "Feature",
                "properties": {"shapeName": n},
                "id": n,
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [x, y],
                            [x + 0.25, y],
                            [x + 0.25, y + 0.25],
                            [x, y + 0.25],
                            [x, y],
                        ]
                    ],
                },
            }
        )
        centers[n] = (y + 0.12, x + 0.12)
    geo = {"type": "FeatureCollection", "features": feats}

    def moe(p, n, deff=1.0):
        p = p / 100
        return 1.96 * math.sqrt(deff * p * (1 - p) / n) * 100

    data = _mod(
        "src.data",
        load_national=lambda: NAT.copy(),
        load_district=lambda: DIST.copy(),
        load_urban_rural=lambda: UR.copy(),
        load_geojson=lambda: geo,
        geo_summary=lambda g: (centers, (-2.6, 29.7)),
        geo_name_mismatch=lambda a, b: ([], []),
        moe_pp=moe,
        margin_flag=lambda n: "wide" if n < 200 else "ok",
        worst_case_moe=lambda n, d=1: moe(50, n, d),
        WIDE_MARGIN_PP=8,
        load_barriers_national=lambda: None,
        load_barriers_district=lambda: None,
        read_barriers_national=lambda: None,
        load_candidate_register=lambda: None,
        load_denominators=lambda: None,
        read_definitions=lambda: pd.DataFrame({"Indicator": ["x"]}),
        read_urban_rural=lambda: UR,
        read_population_groups=lambda: GROUPS,
        barrier_family_shares=lambda b: b,
        BARRIER_LABELS={},
        BARRIER_FAMILY_ORDER=[],
        BARRIER_FAMILY_COLORS={},
        DATA_DIR=Path("/nonexistent"),
    )
    sys.modules["src"].data = data
    _mod(
        "src.validation",
        run_checks=lambda: [],
        summarize=lambda r: {"pass": 0, "warn": 0, "fail": 0},
    )
    _mod("src.briefs", district_brief=lambda *a, **k: "brief")
    _mod("src.data_sources", __path__=[])

    class R:
        observations = GROUPS.copy()

    _mod(
        "src.data_sources.mongodb_population_groups",
        load_population_group_results=lambda: R(),
    )
    _mod("src.models", __path__=[])
    _mod("src.models.nbr_intelligence", __path__=[])

    class Obs:
        def __init__(self, **k):
            self.__dict__.update(k)

    _mod(
        "src.models.nbr_intelligence.experiment",
        MIN_CROSS_SECTION_DISTRICTS=5,
        MIN_TRAINING_RATES=3,
        NBRObservation=Obs,
        evaluate_chronologically=lambda o: ({}, []),
        evaluate_cross_sectionally_with_statuses=lambda a, b, c: ({}, [], {}),
    )
    _mod("src.models.nbr_intelligence.indicator_mapping", MAPPING_BY_VARIABLE=MAPPING)
    _mod(
        "src.models.nbr_intelligence.contextualization",
        build_national_contextualization_report=lambda p, b: {},
        load_finscope_baselines=lambda p: {},
        select_national_contextualization_findings=lambda *a, **k: [],
    )

    def strip(entry, points=None, *, scope="", other_series=0, show_limitations=False):
        pts = sorted(
            points if points is not None else entry["points"],
            key=lambda p: p["reporting_date"],
        )
        return f'<div class="nbr-ctx">NBR {entry["metric_label"]} {pts[-1]["value"]} {entry.get("unit") or "unit not specified"} {scope}</div>'

    def current_mode():
        return st.session_state.get("global_dashboard_mode", "Combined")

    _mod(
        "src.pages.nbr_dashboard",
        current_mode=current_mode,
        load_combined_context_data=load_ctx,
        context_strip_html=strip,
        fmt_value=lambda v: f"{v:,.0f}",
        render_nbr_page=lambda *a, **k: st.write("NBR PAGE"),
        render_methodology_mode_note=lambda: None,
        render_combined_context=lambda *a, **k: st.caption("combined-context-detail"),
        load_combined_national_evidence=lambda: ([], []),
    )
