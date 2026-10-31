import math

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src import data
from src.indicators import BY_NATIONAL, REGISTRY
from src.pages.combined_support import (
    contextual_variables,
    inject_combined_styles,
    latest_point,
    load_context,
    mapping_summary,
)
from src.pages.population_groups import load_group_data
from src.pages.priority_explorer import DEFAULT_COMPONENTS, build_scores
from src.styles import (
    PALETTE,
    card_title,
    esc,
    kpi_card,
    kpi_grid,
    note,
    page_header,
    render_html,
    section_title,
    style_chart,
)

# Published headline figures (FinScope Rwanda 2024, NISR / MINECOFIN). Shown for
# context only; the dashboard's own estimates come from the supplied dataset.
OFFICIAL = {
    "included": 96.0,   # financially included (formal and/or informal)
    "formal": 92.0,     # formally served
    "wallet": 77.0,     # adults with a registered mobile wallet in their name
    "banked": 22.0,     # banked (FinScope measurement framework)
    "excluded": 4.0,
}
SOURCES = [
    ("FinScope Survey 2024: NISR", "https://statistics.gov.rw/statistical-publications/business-establishment-finance-trade/finscope-survey-2024"),
    ("96% of Rwandans are financially included: MINECOFIN", "https://www.minecofin.gov.rw/news-detail/96-of-rwandans-are-financially-included-finscope-survey-2024"),
    ("National Strategy for Transformation (NST2) 2024–2029", "https://leap.unep.org/en/countries/rw/national-legislation/national-strategy-transformation-nst2-2024-2029"),
    ("National Financial Inclusion Roadmap 2025–2030: BNR", "https://www.bnr.rw/documents/National_Financial_Inclusion_Roadmap_2026-2030.pdf"),
    ("Financial Sector Development Strategy: MINECOFIN", "https://www.minecofin.gov.rw/news-detail/rwanda-unveils-financial-sector-development-strategy-2025-2029-to-drive-inclusive-economic-transformation"),
    ("Inside Rwanda's five-year strategy to double the savings rate: The New Times", "https://www.newtimes.co.rw/article/30645/news/economy/inside-rwandas-five-year-strategy-to-double-savings-rate"),
]


def _go(page):
    st.session_state["main_nav"] = page


def _link(label, url):
    return f'<a href="{url}" target="_blank" rel="noopener">{esc(label)}</a>'


def _depth_figure(nat):
    rows = [
        ("Financially included (formal or informal)", OFFICIAL["included"], "official"),
        ("Formally served", OFFICIAL["formal"], "official"),
        ("Registered mobile wallet in own name", OFFICIAL["wallet"], "official"),
    ]
    for national_name, label in [
        ("Registered mobile-money user", "Active registered mobile-money user"),
        ("Saves with a group", "Saves with a group"),
        ("Own bank account", "Owns a bank account"),
        ("Has emergency funds", "Has emergency funds"),
        ("Does not save", "Does not save"),
    ]:
        if national_name in nat:
            rows.append((label, nat[national_name], national_name))
    rows.sort(key=lambda r: r[1])
    colors = [
        "#B4C3CA" if kind == "official" else BY_NATIONAL[kind]["accent"] for _, _, kind in rows
    ]
    fig = go.Figure(go.Bar(
        x=[v for _, v, _ in rows], y=[label for label, _, _ in rows], orientation="h",
        marker=dict(color=colors), text=[v for _, v, _ in rows], texttemplate="%{text:.1f}%",
        textposition="outside", textfont=dict(size=13, color=PALETTE["ink"]), cliponaxis=False,
        hovertemplate="<b>%{y}</b><br>%{x:.1f}%<extra></extra>"))
    fig.update_layout(bargap=0.34)
    fig.update_xaxes(range=[0, 112], ticksuffix="%", title=None, gridcolor=PALETTE["grid"], zeroline=False)
    fig.update_yaxes(title=None, showgrid=False, automargin=True, tickfont=dict(size=13, color=PALETTE["ink"]))
    return style_chart(fig, 430, margin=dict(l=4, r=30, t=8, b=4))


def _evidence_actions(nat, district, groups):
    """Worked examples computed from the data. Each returns (title, text, evidence, page)."""
    actions = []

    # 1. Gender
    try:
        g = groups[groups["Group type"] == "Gender"].set_index("Group")
        col = "Owns a bank account (%)"
        m, f = float(g.loc["Male", col]), float(g.loc["Female", col])
        combined = math.sqrt(data.moe_pp(m, g.loc["Male", "Valid respondents"]) ** 2
                             + data.moe_pp(f, g.loc["Female", "Valid respondents"]) ** 2)
        verdict = "larger than" if abs(m - f) > combined else "within"
        actions.append((
            "Investigate the observed gender difference in bank-account ownership",
            f"{f:.1f}% of women own a bank account against {m:.1f}% of men, a gap of {abs(m - f):.1f} pp that is "
            f"{verdict} an illustrative combined margin (±{combined:.1f} pp). This is a descriptive comparison, "
            "not a design-correct significance test or causal finding. Women are named as a priority group in "
            "national financial inclusion planning.",
            "Population groups › Gender › Bank account", "Population groups"))
    except Exception:
        pass

    # 2. Youth and older adults
    try:
        a = groups[groups["Group type"] == "Age group"].set_index("Group")
        col = "Does not save (%)"
        top2 = a[col].sort_values(ascending=False).head(2)
        nat_ns = nat.get("Does not save")
        actions.append((
            "Investigate saving constraints for groups with higher non-saving estimates",
            f"The share who do not save is highest among adults aged {top2.index[0]} ({top2.iloc[0]:.1f}%) and "
            f"{top2.index[1]} ({top2.iloc[1]:.1f}%), against {nat_ns:.1f}% nationally. Young adults are a named "
            "priority in national financial inclusion planning. These descriptive results do not identify the "
            "reasons; validate barriers and intervention suitability with further evidence.",
            "Population groups › Age group › Doesn't save", "Population groups"))
    except Exception:
        pass

    # 3. Community channels
    gs, bank, sacco = nat.get("Saves with a group"), nat.get("Own bank account"), nat.get("Currently uses Umurenge SACCO")
    if gs is not None and bank is not None:
        actions.append((
            "Explore how existing community channels could support access",
            f"{gs:.1f}% of adults save with a group"
            + (f" and {sacco:.1f}% currently use an Umurenge SACCO" if sacco is not None else "")
            + f", compared with {bank:.1f}% who own a bank account. This pattern may warrant exploring how "
              "community channels relate to access to suitable formal products; the survey does not establish "
              "that a particular linkage would increase inclusion.",
            "National overview › How people save and cope", "National overview"))

    # 4. Districts
    try:
        scored, combos = build_scores(district, nat, DEFAULT_COMPONENTS, 1.0)
        top = scored.sort_values("Priority score", ascending=False)
        robust = top[top["Top-10 combos"] >= round(0.8 * combos)].head(3)["District"].tolist()
        if robust:
            actions.append((
                "Investigate districts that stay near the top across scoring scenarios",
                f"{', '.join(robust)} remain in the top 10 under at least 80% of the indicator combinations tested, "
                "so their relative positions are less sensitive to indicator choice. This does not establish greater "
                "absolute need or justify investment on its own. Other districts move more depending on which "
                "indicators are used.",
                "Priority explorer › Rank stability", "Priority explorer"))
    except Exception:
        pass

    # 5. Barriers
    barriers = data.read_barriers_national()
    if barriers is not None:
        fam = data.barrier_family_shares(barriers).set_index("Barrier family")["Weighted share (%)"]
        need = fam.get("No need or too little income", 0.0)
        actions.append((
            "Investigate reported barriers before designing a response",
            f"{need:.1f}% of adults without an account say they do not need one or that their income is too "
            "limited to justify it. Cost and distance are also reported barriers. These responses can inform "
            "follow-up research into product affordability, access and suitability; they do not prove which "
            "intervention would be effective.",
            "National overview › Why do people lack a bank account?", "National overview"))
    return actions


# FinScope variables behind each worked example and each alignment row (Combined mode only).
_ACTION_VARIABLES = {
    "Investigate the observed gender difference in bank-account ownership": ("k1",),
    "Explore how existing community channels could support access": ("g3a_11", "qf4_06"),
    "Investigate reported barriers before designing a response": ("k1",),
}
_ROW_VARIABLES = {
    "National Strategy for Transformation (NST2), 2024–2029": ("g3a_17", "e9b", "g3a_11", "qf4_06", "qf4_10"),
    "National Financial Inclusion Roadmap, 2025–2030": ("k1",),
    "Financial Sector Development Strategy": ("k1",),
    "Umurenge SACCO network and cooperative reforms": ("qf4_06", "qf4_10"),
    "District-level planning and targeting": ("k1", "g3a_11", "qf4_06", "qf4_10"),
}


def _labels():
    return {item["variable"]: item["short"] for item in REGISTRY}


def _filters_text(entry):
    return " · ".join(f"{k}: {v}" for k, v in sorted((entry.get("filters") or {}).items()))


def _nbr_row_text(title, mapping_lookup):
    """What NBR can add to one policy priority, read from the mapping configuration."""
    variables = _ROW_VARIABLES.get(title)
    if not variables:
        return ""
    level = "district" if title.startswith("District-level") else "national"
    mapped, unmapped = mapping_summary(
        variables, level, mapping_lookup=mapping_lookup, labels=_labels(),
    )
    parts = []
    if mapped:
        parts.append(f"NBR administrative context (separate source) is approved for {', '.join(mapped)}.")
    if unmapped:
        parts.append(f"No approved NBR counterpart at the {level} level for {', '.join(unmapped)}.")
    if title.startswith("National Financial Inclusion Roadmap"):
        parts.append(
            "Gender-specific NBR series appear only where the exact category is recorded; NBR has "
            "no age crosswalk, education or urban/rural breakdown."
        )
    return " ".join(parts)


def _nbr_line(variable, *, subgroup_type="", subgroup="", fmt_value):
    """One plain-text, source-labelled NBR observation (or the reason there is none)."""
    entries, _, state = load_context(
        variable, level="national", subgroup_type=subgroup_type, subgroup=subgroup,
    )
    if not entries:
        return f"{state.title}. {state.body}" if state.body else state.title
    entry = entries[0]
    latest = latest_point(entry["points"])
    if latest is None:
        return "No usable NBR observation."
    unit = entry.get("unit") or "unit not specified"
    scope = _filters_text(entry)
    return (
        f"NBR · {entry['metric_label']}: {fmt_value(latest['value'])} {unit} on "
        f"{latest['reporting_date']} ({scope}). Administrative count, not comparable with the survey percentages."
    )


def _action_nbr_note(title, fmt_value):
    variables = _ACTION_VARIABLES.get(title)
    if not variables:
        return ""
    if title.startswith("Investigate the observed gender difference"):
        return " ".join(
            f"{group}: {_nbr_line('k1', subgroup_type='Gender', subgroup=group, fmt_value=fmt_value)}"
            for group in ("Female", "Male")
        )
    return " ".join(_nbr_line(v, fmt_value=fmt_value) for v in variables)


def _evidence_gap_action(mapping_lookup):
    """A closing example about what the administrative evidence cannot yet support."""
    registry_vars = [item["variable"] for item in REGISTRY]
    mapped, unmapped = mapping_summary(
        registry_vars, "national", mapping_lookup=mapping_lookup, labels=_labels(),
    )
    contextual = set(contextual_variables(mapping_lookup)) & set(registry_vars)
    text = (
        f"{len(mapped)} of {len(registry_vars)} survey indicators have an approved national NBR series "
        f"({len(contextual)} have any approved contextual relationship). "
        + (f"No supply-side reading is possible for {', '.join(unmapped)}. " if unmapped else "")
        + "Before drawing supply-side conclusions for a district or group, confirm that an NBR observation "
        "exists for that exact metric, filter and reporting date; absence is unknown, not zero."
    )
    return (
        "Verify administrative coverage before drawing supply-side conclusions",
        text,
        "Methodology & sources › Using both sources",
        "Methodology & sources",
    )


def render_policy_alignment():
    from src.pages.nbr_dashboard import (
        context_strip_html,
        current_mode,
        fmt_value,
        render_methodology_mode_note,
    )

    mode = current_mode()
    combined = mode == "Combined"
    render_methodology_mode_note()
    mapping_lookup = {}
    if combined:
        from src.models.nbr_intelligence.indicator_mapping import MAPPING_BY_VARIABLE as mapping_lookup

        inject_combined_styles()
    try:
        national = data.load_national()
        district = data.load_district()
        groups = load_group_data()
    except (FileNotFoundError, ValueError, KeyError) as error:
        st.error("The data needed for this page could not be loaded.")
        st.caption(str(error))
        return
    nat = dict(zip(national["Indicator"], national["Estimate (%)"].astype(float)))

    # ---- Hero --------------------------------------------------------------
    strips, states = {}, {}
    if combined:
        for variable in ("k1", "e9b"):
            entries, _, state = load_context(variable, level="national")
            states[variable] = state
            if entries:
                strips[variable] = context_strip_html(
                    entries[0], scope=_filters_text(entries[0]), other_series=len(entries) - 1,
                )
    page_header(
        "Policy alignment and use",
        "How the evidence in this tool connects to Rwanda's national priorities, and who can act on it."
        + (" Where NBR administrative series are approved for a priority, they are named alongside the survey evidence." if combined else ""),
        pill="NST2 · Vision 2050" + (" · FinScope + NBR" if combined else ""),
        mode=mode,
        intro=(
            "Policy priorities are framed by the survey; NBR administrative series add supply-side context "
            "where an approved relationship exists. The two are never calculated against each other."
            if combined else ""
        ),
        size="tall",
        below_html=kpi_grid([
            kpi_card("Financially included", f"{OFFICIAL['included']:.0f}", "%", OFFICIAL["included"], "#8FB0C2",
                     "Formal or informal · published FinScope 2024 headline", tag="fs" if combined else ""),
            kpi_card("Formally served", f"{OFFICIAL['formal']:.0f}", "%", OFFICIAL["formal"], "#8FB0C2",
                     "Published headline · the 2024 target was 90%", tag="fs" if combined else ""),
            kpi_card("Own a bank account", f"{nat.get('Own bank account', float('nan')):.1f}", "%",
                     nat.get("Own bank account", 0), BY_NATIONAL["Own bank account"]["accent"],
                     "This dashboard · in own name" + strips.get("k1", ""), tag="fs" if combined else ""),
            kpi_card("Have emergency funds", f"{nat.get('Has emergency funds', float('nan')):.1f}", "%",
                     nat.get("Has emergency funds", 0), BY_NATIONAL["Has emergency funds"]["accent"],
                     "This dashboard · resilience" + strips.get("e9b", ""), tag="fs" if combined else ""),
        ]),
    )
    if combined:
        gaps = [
            f"{label}: {states[var].title.lower()}"
            for var, label in (("k1", "Bank account"), ("e9b", "Emergency funds"))
            if not states[var].available
        ]
        st.caption(
            "NBR context accompanies the cards that have an approved national series."
            + (" " + "; ".join(gaps) + "." if gaps else "")
            + " NBR values are administrative counts in their own units."
        )
    st.markdown("")

    # ---- 1. The challenge ----------------------------------------------------
    section_title("The challenge: broad inclusion, thin depth",
                  "Almost every adult uses some financial service. Far fewer hold the products that build "
                  "security.")
    left, right = st.columns([1.5, 1], gap="medium")
    with left:
        with st.container(key="card_depth"):
            card_title("Headline inclusion versus depth",
                       "Grey bars are published FinScope 2024 headlines. Coloured bars are estimates from the "
                       "supplied dataset, which this dashboard uses.")
            st.plotly_chart(_depth_figure(nat), use_container_width=True, key="pa_depth",
                            config={"displayModeBar": False})
    with right:
        with st.container(key="card_depth_read"):
            card_title("Which number answers which question?")
            depth_html = (
                """
                <table class="cmp">
                  <tr><th>Question</th><th>Measure</th></tr>
                  <tr><td>Does anyone use any financial service?</td><td><b>96%</b> financially included (formal or informal)</td></tr>
                  <tr><td>Do people use regulated services?</td><td><b>92%</b> formally served, driven mainly by mobile money</td></tr>
                  <tr><td>Do people hold a bank account?</td><td>FinScope's <b>banked</b> share is about 22%; this dashboard counts <b>own-name</b> accounts (20.2%)</td></tr>
                  <tr><td>Are people building security?</td><td>Emergency funds, saving and the barriers to accounts, which this tool adds</td></tr>
                </table>
                <div class="micro">Published figures describe the same 2024 survey but use different definitions, so
                they are not directly comparable with the indicators below.</div>
                """
            )
            if combined:
                depth_html = depth_html.replace(
                    "</table>",
                    "<tr><td>What does the financial system record?</td><td><b>NBR</b> administrative counts "
                    "(for example branches), in their own units. They are not rates of ownership or use.</td></tr></table>",
                    1,
                )
            render_html(depth_html)
    st.markdown("")

    # ---- 2. Alignment ----------------------------------------------------------
    section_title("Alignment with national priorities",
                  "What each strategy asks for, and where this tool provides evidence.")
    rows = [
        ("National Strategy for Transformation (NST2), 2024–2029",
         "The five-year roadmap toward Vision 2050 (upper-middle-income status by 2035). Priorities include a "
         "resilient, broader financial sector and doubling the national savings rate to 25.9% of GDP by 2029.",
         "Saving and resilience indicators (does not save, emergency funds, group saving, SACCO and savings-group "
         "use) on the National overview and District explorer.",
         _link("NST2 summary", SOURCES[2][1]) + " · " + _link("Savings target", SOURCES[5][1])),
        ("National Financial Inclusion Roadmap, 2025–2030",
         "Mandated through NST2 and led by the National Bank of Rwanda. Emphasises persistent gaps for youth, "
         "women and rural populations.",
         "Population groups (gender, age, education, area), urban-rural comparison and gap measures, each with "
         "sampling margins.",
         _link("Roadmap (BNR)", SOURCES[3][1])),
        ("Financial Sector Development Strategy",
         "Aims to deepen inclusion and financial literacy, with attention to underserved groups such as "
         "youth, women, MSMEs and agriculture.",
         "Barriers to bank accounts grouped into need and income, access, cost, and knowledge and paperwork; "
         "district-level barrier profiles.",
         _link("MINECOFIN strategy", SOURCES[4][1])),
        ("Umurenge SACCO network and cooperative reforms",
         "NST2 planning includes consolidating Umurenge SACCOs into a cooperative bank, which makes baseline "
         "SACCO reach by district relevant.",
         "Current SACCO use by district alongside bank accounts and savings groups.",
         _link("NST2 summary", SOURCES[2][1])),
        ("District-level planning and targeting",
         "National targets are delivered locally. District planning needs evidence on where gaps are largest "
         "and what additional evidence is needed before choosing an intervention.",
         "Priority explorer comparisons and sensitivity analysis, plus a downloadable district profile. "
         "These support investigation; they do not allocate funds or estimate investment reach.",
         "FinScope 2024 · NISR"),
    ]
    if combined:
        rows = [
            (t, ask, tool + (" " + _nbr_row_text(t, mapping_lookup) if _nbr_row_text(t, mapping_lookup) else ""), src)
            for t, ask, tool, src in rows
        ]
    with st.container(key="card_alignment"):
        html = "".join(
            f"""
            <div class="al-row">
              <div><div class="al-h">National priority</div><div class="al-t">{esc(t)}</div>
                <div class="al-src">{src}</div></div>
              <div><div class="al-h">What it asks for</div><p class="al-p">{esc(ask)}</p></div>
              <div><div class="al-h">Where this tool helps</div><p class="al-p">{esc(tool)}</p></div>
            </div>
            """
            for t, ask, tool, src in rows
        )
        render_html(html)
        render_html('<div class="micro">The indicators shown here are not themselves official strategy targets; '
                    "they are evidence that bears on the priorities above.</div>")
    st.markdown("")

    # ---- 3. Users ---------------------------------------------------------------------
    section_title("Who can use this, and for what", "Each audience can start from a different page.")
    users = [
        ("Policy makers and regulators", "MINECOFIN, BNR, sector regulators",
         ["Which districts and groups show comparatively large gaps?", "Which estimates and findings need validation?",
          "Does the relative pattern change under different indicator choices?"], "Priority explorer"),
        ("District authorities", "Local government and planning teams",
         ["How does my district compare with the national level?", "What do people without an account say locally?",
          "Download a profile to support planning discussions."], "District explorer"),
        ("Financial service providers", "Banks, SACCOs, MFIs, mobile operators",
         ["Where do survey indicators and reported barriers suggest questions to investigate?",
          "Which access, affordability or service questions need local validation?",
          "How common are community saving channels?"], "National overview"),
        ("Development partners and civil society", "Programme design and monitoring",
         ["Which women, youth and rural groups show comparatively low estimates?",
          "What additional evidence is needed before selecting an intervention?",
          "What is the evidence base and what are its limitations?"], "Population groups"),
        ("Researchers and statisticians", "NISR and academic users",
         ["How is each indicator defined and weighted?", "Which automated data checks pass?",
          "What are the known limitations?"], "Methodology & sources"),
        ("Citizens and journalists", "Anyone curious about their area",
         ["How does my district compare?", "Which groups have lower estimates on this indicator?",
          "What does the survey actually measure?"], "District explorer"),
    ]
    if combined:
        extra = {
            "Policy makers and regulators": "Where is NBR coverage missing, so supply-side questions cannot yet be answered?",
            "Financial service providers": "Which recorded NBR series exist for an area, and how recent are they?",
        }
        users = [(t, who, [*qs, extra[t]] if t in extra else qs, page) for t, who, qs, page in users]
    cards = "".join(
        f"""
        <div class="sh"><div class="sh-t">{esc(t)}</div>
          <div class="micro" style="margin:2px 0 0">{esc(who)}</div>
          <ul class="sh-q">{"".join(f"<li>{esc(q)}</li>" for q in qs)}</ul>
          <div class="sh-go">Start with: {esc(page)}</div></div>
        """
        for t, who, qs, page in users
    )
    render_html(f'<div class="sh-grid">{cards}</div>')
    st.markdown("")

    # ---- 4. Evidence to action --------------------------------------------------------------
    section_title("From evidence to action",
                  "Starting points drawn directly from the data. They indicate where to look, not why gaps exist.")
    note("How to interpret these results",
         "Estimates come from one survey, carry sampling uncertainty, and describe differences rather than causes. "
         "The priority score is an exploratory screening tool, not an official ranking. The dashboard does not "
         "measure investment demand, readiness, beneficiary counts, costs, or returns; use the findings to guide "
         "local validation, not as a funding allocation.", tone="info")
    st.markdown("")
    actions = _evidence_actions(nat, district, groups)
    notes = {}
    if combined:
        notes = {title: _action_nbr_note(title, fmt_value) for title, *_ in actions}
        actions = [*actions, _evidence_gap_action(mapping_lookup)]
    with st.container(key="card_actions"):
        html = "".join(
            f"""
            <div class="act"><div class="act-n">{i}</div>
              <div><div class="act-t">{esc(title)}</div><p class="act-p">{esc(text)}</p>
              <div class="act-e">Survey evidence: {esc(evidence)}</div>
              {f'<div class="act-e">Administrative context: {esc(notes[title])}</div>' if notes.get(title) else ""}
              </div></div>
            """
            for i, (title, text, evidence, _) in enumerate(actions, start=1)
        ) if combined else "".join(
            f"""
            <div class="act"><div class="act-n">{i}</div>
              <div><div class="act-t">{esc(title)}</div><p class="act-p">{esc(text)}</p>
              <div class="act-e">Evidence: {esc(evidence)}</div></div></div>
            """
            for i, (title, text, evidence, _) in enumerate(actions, start=1)
        )
        render_html(html)

    nav_cols = st.columns(4, gap="small")
    for col, page in zip(nav_cols, ["National overview", "District explorer", "Population groups", "Priority explorer"]):
        with col:
            st.button(f"Open {page}", key=f"pa_nav_{page}", on_click=_go, args=(page,), use_container_width=True)
    st.markdown("")

    # ---- Sources --------------------------------------------------------------------------------------
    with st.expander("Sources for this page"):
        render_html("".join(f'<div class="micro" style="margin:6px 0">{_link(label, url)}</div>'
                            for label, url in SOURCES))
        if combined:
            render_html('<div class="micro" style="margin:6px 0">NBR administrative observations: read from the '
                        "project's read-only NBR source; see Methodology &amp; sources › Using both sources.</div>")
