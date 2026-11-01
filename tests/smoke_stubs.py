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
    (
        "qf4_05",
        "Currently uses mobile-money operator (%)",
        "Currently uses mobile-money operator",
        "Mobile-money use",
        "positive",
        "supporting",
        False,
    ),
    (
        "qf5_05_6",
        "Sent or received money via mobile money (%)",
        "Sent or received money via mobile money",
        "Mobile-money transfers",
        "neutral",
        "supporting",
        False,
    ),
    (
        "h3_09",
        "Borrowed from an informal group (%)",
        "Borrowed from an informal group",
        "Informal-group borrowing",
        "neutral",
        "supporting",
        False,
    ),
    (
        "i5a_1",
        "Has medical insurance (%)",
        "Has medical insurance",
        "Medical insurance",
        "positive",
        "supporting",
        False,
    ),
    (
        "qf1_06",
        "Ever used Umurenge SACCO (%)",
        "Ever used Umurenge SACCO",
        "Ever used SACCO",
        "positive",
        "supporting",
        False,
    ),
    (
        "qf1_10",
        "Ever used a savings group (%)",
        "Ever used a savings group",
        "Ever used savings group",
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
            valid_count_column=f"Valid responses ({sh})",
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
    DIST[r["valid_count_column"]] = DIST["Valid respondents"]
NAT = pd.DataFrame(
    {
        "Indicator": [r["national"] for r in REG],
        "Estimate (%)": [45.0 + i * 2 for i in range(len(REG))],
    }
)
UR = pd.DataFrame(
    {
        "Area": ["Urban", "Rural"],
        "Valid respondents": [5000, 9000],
        **{r["column"]: [60.0, 40.0] for r in REG},
        **{r["valid_count_column"]: [5000, 9000] for r in REG},
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
                **{
                    r["valid_count_column"]: 300 if g != "None" else 150
                    for r in REG
                },
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
        survey_reference_period="FinScope Rwanda 2024",
        survey_population="Rwanda residents aged 16 years and older",
        survey_weight="pop_wt",
        survey_denominator="Synthetic valid item responses among adults aged 16+.",
    )
    for r in REG
}
# Mirrors the real configuration: active e-money agents are relevant service-channel
# context; subscriber counts remain unresolved proxies.
MAPPING["f5"]["nbr_relationships"] = [
    _rel(
        "agents",
        ["Total Agents"],
        ["Agents"],
        ["national", "district"],
        fs={
            "Gender": "All",
            "Institution Type": "E-money Issuers",
            "Agent Status": "Active",
            "Location": "All",
        },
    ),
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
MAPPING["k1"]["nbr_relationships"].extend(
    [
        _rel(
            "inclusion",
            ["Banked", "Total Customers"],
            ["Customers"],
            ["national", "district"],
            kind="proxy_with_unresolved_definition",
            fs={
                "Gender": "All",
                "Age Segment": "All",
                "Institution Type": "Banks",
                "Account/Policy Status": "Active",
                "Location": "All",
            },
        ),
        _rel(
            "transactional",
            ["Have Transactional Accounts"],
            ["Customers"],
            ["national", "district"],
            kind="proxy_with_unresolved_definition",
            fs={
                "Gender": "All",
                "Age Segment": "All",
                "Institution Type": "All",
                "Account Status": "Active",
                "Account Type": "All",
                "Location": "All",
            },
        ),
        _rel(
            "depositors",
            ["Are Depositors"],
            ["Customers"],
            ["national", "district"],
            kind="proxy_with_unresolved_definition",
            fs={
                "Gender": "All",
                "Age Segment": "All",
                "Institution Type": "All",
                "Account Status": "Active",
                "Account Type": "All",
                "Location": "All",
            },
        ),
        _rel(
            "cards",
            ["Total Cards"],
            ["Customers"],
            ["national", "district"],
            kind="unsuitable",
        ),
    ]
)
# Mirrors the real configuration: SACCO branches are available as infrastructure context.
MAPPING["g3a_11"]["nbr_relationships"] = [
    _rel(
        "branches",
        ["Total Branches"],
        ["Branches"],
        ["national", "district"],
        fs={
            "Institution Type": "Sacco",
            "Branch Status": "Active",
            "Location": "All",
        },
    ),
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
MAPPING["qf4_05"]["nbr_relationships"] = [
    _rel(
        "agents",
        ["Total Agents"],
        ["Agents"],
        ["national", "district"],
        fs={
            "Gender": "All",
            "Institution Type": "E-money Issuers",
            "Agent Status": "Active",
            "Location": "All",
        },
    )
]
MAPPING["qf5_05_6"]["nbr_relationships"] = [
    _rel(
        "mobile_banking",
        ["Use Mobile Banking"],
        ["Customers"],
        ["national", "district"],
        kind="conditional_contextual_indicator",
        fs={
            "Gender": "All",
            "Age Segment": "All",
            "Institution Type": "All",
            "Account Status": "Active",
            "Account Type": "All",
            "Location": "All",
        },
    )
]
MAPPING["qf5_05_6"]["nbr_relationships"][0]["limitations"] = (
    "Mobile banking is not mobile money, and the NBR KPI unit is unknown."
)
MAPPING["h3_09"]["nbr_relationships"] = [
    _rel(
        "credit",
        ["Total Customers"],
        ["Customers"],
        ["national", "district"],
        fs={
            "Gender": "All",
            "Age Segment": "All",
            "Institution Type": "All",
            "Account Status": "Active",
            "Credit Category": "All",
            "Location": "All",
        },
    )
]
MAPPING["i5a_1"]["nbr_relationships"] = [
    _rel(
        "insurance",
        ["Total Policy Holders"],
        ["Policy Holders"],
        ["national", "district"],
        fs={
            "Gender": "All",
            "Age Segment": "All",
            "Insurance Type": "All",
            "Policy Status": "Active",
            "Location": "All",
        },
    )
]
MAPPING["qf1_06"]["nbr_relationships"] = [
    _rel(
        "branches",
        ["Total Branches"],
        ["Branches"],
        ["national", "district"],
        fs={
            "Institution Type": "Sacco",
            "Branch Status": "Active",
            "Location": "All",
        },
    )
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
                    value=float(10 + len(g) + dates.index(d))
                    * float(st.session_state.get("_stub_nbr_scale", 1.0)),
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


def _entry(
    metric,
    level,
    unit,
    points,
    filters=None,
    relationship="contextual_indicator",
):
    return dict(
        page="p",
        metric_label=metric,
        unit=unit,
        filters=filters or {"Institution Type": "Banks"},
        geography_level=level,
        relationship=relationship,
        limitations="Administrative count.",
        points=points,
    )


def load_ctx(
    variable, *, geography_level, geography=None, subgroup_type="", subgroup=""
):
    if variable in st.session_state.get("_stub_fail_vars", ()):
        raise RuntimeError("simulated read failure")
    if variable in st.session_state.get("_stub_empty_vars", ()):
        return [], "v1"
    if variable == "qf5_05_6" and geography_level == "national":
        filters = {
            "Gender": "All",
            "Age Segment": "All",
            "Institution Type": "All",
            "Account Status": "Active",
            "Account Type": "All",
            "Location": "All",
        }
        points = _pts(
            "Use Mobile Banking",
            "national",
            ["Rwanda"],
            None,
        )
        for point in points:
            point["filters"] = filters
        entry = _entry(
            "Use Mobile Banking",
            "national",
            None,
            points,
            filters,
            relationship="conditional_contextual_indicator",
        )
        entry["limitations"] = (
            "Mobile banking is not mobile money, and the NBR KPI unit is unknown."
        )
        return [entry], "v1"
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
        load_denominators=lambda: pd.DataFrame(
            {
                "Variable": [r["variable"] for r in REG],
                "Valid responses": [600 for _ in REG],
            }
        ),
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
        CROSS_SECTION_ROBUST_Z_THRESHOLD=3.5,
        MIN_CROSS_SECTION_DISTRICTS=10,
        MIN_TRAINING_RATES=3,
        ROBUST_SCORE_THRESHOLD=3.0,
        NBRObservation=Obs,
        evaluate_chronologically=lambda o: ({}, []),
        evaluate_cross_sectionally_with_statuses=lambda a, b, c: ({}, [], {}),
    )
    _mod(
        "src.models.nbr_intelligence.indicator_mapping",
        DISPLAYABLE_RELATIONSHIPS=frozenset({
            "contextual_indicator",
            "conditional_contextual_indicator",
        }),
        MAPPING_BY_VARIABLE=MAPPING,
    )
    _mod(
        "src.models.nbr_intelligence.contextualization",
        MIN_TREND_OBSERVATIONS=3,
        SUFFICIENT_DIRECTIONAL_OBSERVATIONS=5,
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

    def render_context(indicator_variable, **kwargs):
        entries = kwargs.get("entries") or []
        st.caption(f"combined-context-detail:{indicator_variable}")
        for entry in entries:
            dates = ", ".join(sorted({
                str(point.get("reporting_date", ""))
                for point in entry.get("points", [])
            }))
            st.caption(
                f"{entry.get('metric_label', '')} · "
                f"{entry.get('unit') or 'unit not specified'} · {dates}"
            )
        intelligence = kwargs.get("intelligence")
        if intelligence:
            st.markdown("**NBR intelligence**")
            st.caption(
                f"Peer review: {intelligence.get('cross_section', {}).get('state', 'unavailable')} · "
                f"temporal review: {intelligence.get('temporal', {}).get('state', 'unavailable')}"
            )
            st.caption("Experimental, NBR-only review signals—not findings of financial exclusion.")

    def national_points():
        points = []
        for variable, mapping in MAPPING.items():
            for relationship in mapping["nbr_relationships"]:
                if "national" not in relationship["available_levels"]:
                    continue
                for label in relationship["national_kpi_labels"]:
                    points.append(
                        {
                            "page": relationship["page"],
                            "metric_label": label,
                            "geography_level": "national",
                            "geography": "Rwanda",
                            "source_type": "national_kpi",
                            "reporting_date": "2026-10-24",
                            "value": 123.0,
                            "unit": "count" if label in {"Total Customers", "Total Branches"} else None,
                            "filters": dict(relationship["filter_scope"]),
                            "source_record_id": f"{variable}-{relationship['page']}-{label}",
                        }
                    )
        return points, []

    def mapped_series(
        points,
        indicator_variable,
        *,
        geography_level,
        geography=None,
        subgroup_type="",
        subgroup="",
        relationships=None,
    ):
        mapping = MAPPING.get(indicator_variable) or {}
        result = []
        for relationship in mapping.get("nbr_relationships", []):
            relation = relationship["relationship"]
            if relation == "unsuitable" or (
                relationships is not None and relation not in relationships
            ):
                continue
            if subgroup_type:
                continue
            labels = (
                relationship["national_kpi_labels"]
                if geography_level == "national"
                else relationship["district_table_labels"]
            )
            filters = relationship["filter_scope"]
            for label in labels:
                matched = [
                    dict(point)
                    for point in points
                    if point.get("page") == relationship["page"]
                    and point.get("metric_label") == label
                    and point.get("geography_level") == geography_level
                    and point.get("filters") == filters
                    and (geography is None or point.get("geography") == geography)
                ]
                if matched:
                    result.append(
                        {
                            "page": relationship["page"],
                            "metric_label": label,
                            "unit": matched[0].get("unit"),
                            "filters": dict(filters),
                            "relationship": relation,
                            "limitations": relationship["limitations"],
                            "points": matched,
                        }
                    )
        return result

    def render_trend(points, *, title, compact=False, key_suffix=None, snapshots=False):
        st.caption(
            f"snapshot-trend:{title}:" +
            ",".join(str(point.get("reporting_date")) for point in points)
        )

    def render_observation_table(points):
        st.dataframe(pd.DataFrame(points), use_container_width=True, hide_index=True)

    _mod(
        "src.pages.nbr_dashboard",
        current_mode=current_mode,
        load_combined_context_data=load_ctx,
        load_combined_national_evidence=national_points,
        _mapped_series=mapped_series,
        _render_trend=render_trend,
        _render_observation_table=render_observation_table,
        NBR_PAGE_LABELS={
            "inclusion": "Inclusion",
            "transactional": "Transactional",
            "depositors": "Depositors",
        },
        context_strip_html=strip,
        fmt_value=lambda v: f"{v:,.0f}",
        render_nbr_page=lambda *a, **k: st.write("NBR PAGE"),
        render_methodology_mode_note=lambda: None,
        render_combined_context=render_context,
    )
