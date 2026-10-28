import math

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src import data
from src.indicators import BY_NATIONAL
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
            "Close the gender gap in bank accounts",
            f"{f:.1f}% of women own a bank account against {m:.1f}% of men, a gap of {abs(m - f):.1f} pp that is "
            f"{verdict} the sampling margin (±{combined:.1f} pp). Women are named as a priority group in national "
            "financial inclusion planning.",
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
            "Build saving habits where saving is weakest",
            f"The share who do not save is highest among adults aged {top2.index[0]} ({top2.iloc[0]:.1f}%) and "
            f"{top2.index[1]} ({top2.iloc[1]:.1f}%), against {nat_ns:.1f}% nationally. Young adults are a named "
            "priority in national financial inclusion planning.",
            "Population groups › Age group › Doesn't save", "Population groups"))
    except Exception:
        pass

    # 3. Community channels
    gs, bank, sacco = nat.get("Saves with a group"), nat.get("Own bank account"), nat.get("Currently uses Umurenge SACCO")
    if gs is not None and bank is not None:
        actions.append((
            "Build on the channels people already use",
            f"{gs:.1f}% of adults save with a group"
            + (f" and {sacco:.1f}% currently use an Umurenge SACCO" if sacco is not None else "")
            + f", compared with {bank:.1f}% who own a bank account. Linking group and SACCO saving to formal, "
              "safe products reaches people where they already are.",
            "National overview › How people save and cope", "National overview"))

    # 4. Districts
    try:
        scored, combos = build_scores(district, nat, DEFAULT_COMPONENTS, 1.0)
        top = scored.sort_values("Priority score", ascending=False)
        robust = top[top["Top-10 combos"] >= round(0.8 * combos)].head(3)["District"].tolist()
        if robust:
            actions.append((
                "Target the districts that stay on the list however you score",
                f"{', '.join(robust)} remain in the top 10 under at least 80% of the indicator combinations tested, "
                "which makes them the most defensible starting point for district-level attention. Other districts move a lot "
                "depending on which indicators are used.",
                "Priority explorer › Rank stability", "Priority explorer"))
    except Exception:
        pass

    # 5. Barriers
    barriers = data.read_barriers_national()
    if barriers is not None:
        fam = data.barrier_family_shares(barriers).set_index("Barrier family")["Weighted share (%)"]
        need = fam.get("No need or too little income", 0.0)
        actions.append((
            "Match the response to the barrier",
            f"{need:.1f}% of adults without an account say they do not need one or that their income is too "
            "limited to justify it. Beyond income, cost and distance are the largest identifiable barriers, which suggests "
            "low-cost entry products and livelihood-linked saving may matter more than branch coverage alone.",
            "National overview › Why do people lack a bank account?", "National overview"))
    return actions


def render_policy_alignment():
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
    page_header(
        "Policy alignment and use",
        "How the evidence in this tool connects to Rwanda's national priorities, and who can act on it.",
        pill="NST2 · Vision 2050",
        size="tall",
        below_html=kpi_grid([
            kpi_card("Financially included", f"{OFFICIAL['included']:.0f}", "%", OFFICIAL["included"], "#8FB0C2",
                     "Formal or informal · published FinScope 2024 headline"),
            kpi_card("Formally served", f"{OFFICIAL['formal']:.0f}", "%", OFFICIAL["formal"], "#8FB0C2",
                     "Published headline · the 2024 target was 90%"),
            kpi_card("Own a bank account", f"{nat.get('Own bank account', float('nan')):.1f}", "%",
                     nat.get("Own bank account", 0), BY_NATIONAL["Own bank account"]["accent"],
                     "This dashboard · in own name"),
            kpi_card("Have emergency funds", f"{nat.get('Has emergency funds', float('nan')):.1f}", "%",
                     nat.get("Has emergency funds", 0), BY_NATIONAL["Has emergency funds"]["accent"],
                     "This dashboard · resilience"),
        ]),
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
            render_html(
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
         "and how reliable the estimates are.",
         "Priority explorer (rank stability, sampling margins) and a downloadable profile for every district.",
         "FinScope 2024 · NISR"),
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
         ["Which districts and groups fall furthest behind?", "Is a gap larger than sampling noise?",
          "Does the conclusion hold under different indicator choices?"], "Priority explorer"),
        ("District authorities", "Local government and planning teams",
         ["How does my district compare with the national level?", "What do people without an account say locally?",
          "Download a profile to support planning discussions."], "District explorer"),
        ("Financial service providers", "Banks, SACCOs, MFIs, mobile operators",
         ["Where is entry-level demand likely to be largest?", "Where do cost or distance barriers dominate?",
          "How much saving already happens in groups?"], "National overview"),
        ("Development partners and civil society", "Programme design and monitoring",
         ["Which women, youth and rural groups are most behind?", "Where should limited resources go first?",
          "What is the evidence base and how reliable is it?"], "Population groups"),
        ("Researchers and statisticians", "NISR and academic users",
         ["How is each indicator defined and weighted?", "Which automated data checks pass?",
          "What are the known limitations?"], "Methodology & sources"),
        ("Citizens and journalists", "Anyone curious about their area",
         ["How does my district compare?", "Which groups are most behind?",
          "What does the survey actually measure?"], "District explorer"),
    ]
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
         "The priority score is an exploratory screening tool, not an official ranking.", tone="info")
    st.markdown("")
    actions = _evidence_actions(nat, district, groups)
    with st.container(key="card_actions"):
        html = "".join(
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
