import pandas as pd
import streamlit as st

from src import data, validation
from src.indicators import CORE, PRIORITY_CANDIDATES, REGISTRY
from src.styles import (
    PALETTE,
    badge,
    card_title,
    esc,
    note,
    page_header,
    render_html,
)

SECTIONS = [
    ("sec-source", "Data source"),
    ("sec-indicators", "Indicators"),
    ("sec-weights", "Weighted estimates"),
    ("sec-uncertainty", "Uncertainty"),
    ("sec-districts", "Comparisons"),
    ("sec-scoring", "Priority scoring"),
    ("sec-barriers", "Barriers and group use"),
    ("sec-quality", "Data quality"),
    ("sec-limits", "Limitations"),
    ("sec-sources", "Sources"),
]


@st.cache_data
def _checks():
    return validation.run_checks()


@st.cache_data
def load_definitions():
    return data.read_definitions()


def _section(anchor, number, title, subtitle=None):
    sub = f'<div class="cs">{esc(subtitle)}</div>' if subtitle else ""
    render_html(f"""
        <div class="msec" id="{anchor}"><div class="msec-n">{number}</div>
        <div><div class="ct">{esc(title)}</div>{sub}</div></div>""")


def _fact(label, value, src, accent, size=34):
    return f"""
    <div class="kpi" style="--accent:{accent}">
      <div class="kpi-label"><i></i><span>{esc(label)}</span></div>
      <div class="kpi-value" style="font-size:{size}px;margin-bottom:8px">{value}</div>
      <div class="kpi-src" style="margin-top:0">{src}</div>
    </div>"""


def _toc():
    links = "".join(f'<a href="#{a}"><b>{i}</b>{esc(t)}</a>' for i, (a, t) in enumerate(SECTIONS, start=1))
    render_html(f'<div class="toc">{links}</div>')


def _indicator_cards():
    cards = []
    for item in REGISTRY:
        role = badge("Core" if item["role"] == "core" else "Supporting", "ok" if item["role"] == "core" else "info")
        cards.append(f"""
        <div class="mcard" style="--accent:{item['accent']}">
          <div class="mc-t"><i></i>{esc(item['label'])}</div>
          <div style="margin-bottom:8px"><span class="code">{esc(item['variable'])}</span> {role}</div>
          <p class="mc-p">{esc(item['description'])}</p>
          <div class="mc-read"><b>How to read it.</b> {esc(item['interpretation'])}</div>
        </div>""")
    render_html(f'<div class="mgrid wide">{"".join(cards)}</div>')


def _checks_panel(results):
    counts = validation.summarize(results)
    render_html(f"""
        <div class="chk-sum">
          <div><b>{counts['pass']}</b><span>checks passed</span></div>
          <div><b>{counts['warn']}</b><span>notes to read</span></div>
          <div><b>{counts['fail']}</b><span>checks failed</span></div>
        </div>""")
    icon = {"pass": "✓", "warn": "!", "fail": "×"}
    rows = "".join(f"""
        <div class="chk-row"><div class="chk-ic {r['status']}">{icon[r['status']]}</div>
          <div><div class="chk-t">{esc(r['name'])}<span class="chk-g">{esc(r['group'])}</span></div>
          <div class="chk-d">{esc(r['detail'])}</div></div></div>""" for r in results)
    render_html(rows)


def render_methodology():
    from src.nbr_dashboard import render_methodology_mode_note

    render_methodology_mode_note()
    try:
        definitions = load_definitions()
    except (OSError, ValueError):
        definitions = None
    results = _checks()
    counts = validation.summarize(results)
    total_checks = sum(counts.values())

    facts = "".join([
        _fact("Survey", "2024", "FinScope Rwanda · NISR", PALETTE["teal"], 42),
        _fact("Estimates", "Weighted", 'Individual survey weight <span class="code" style="margin:0">pop_wt</span>',
              PALETTE["blue"], 32),
        _fact("Indicators documented", f"{len(REGISTRY)}",
              f"{len(CORE)} core and {len(REGISTRY) - len(CORE)} supporting", PALETTE["amber"], 42),
        _fact("Automated data checks", f"{counts['pass']}/{total_checks}",
              f"{counts['fail']} failed · {counts['warn']} notes to read", PALETTE["coral"], 42),
    ])
    page_header(
        "Methodology & sources",
        "The data, calculations, assumptions, checks and limitations behind the Rwanda Financial Inclusion Gap Explorer.",
        pill="FinScope Rwanda 2024", size="tall", below_html=f'<div class="kpi-grid">{facts}</div>')
    st.markdown("")
    render_html('<div class="sec"><div class="cs" style="margin:0 0 6px">Jump to a section</div></div>')
    _toc()

    # ---- 1. Data source -------------------------------------------------------
    _section("sec-source", 1, "Data source", "Where the numbers come from and what they represent.")
    with st.container(key="card_method_source"):
        render_html("""
            <p class="mc-p" style="font-size:15.5px">The analysis uses <b>FinScope Rwanda 2024</b>, the national
            financial inclusion survey produced by Access to Finance Rwanda with the National Institute of Statistics
            of Rwanda (NISR). Fieldwork ran from 6 September to 8 October 2024.</p>
            <p class="mc-p" style="font-size:15.5px;margin-top:12px">The supplied dataset contains 13,994 valid adult
            respondents. District, urban-rural and population-group results are weighted estimates from these
            respondents. They are survey-based and are not real-time measurements.</p>
            <div class="fchips">
              <span class="chip"><i style="border-color:#1A8A7D"></i>Survey-based estimates</span>
              <span class="chip"><i style="border-color:#2F6DB5"></i>30 districts</span>
              <span class="chip"><i style="border-color:#E0A12F"></i>Not a live measurement</span>
            </div>""")

    # ---- 2. Indicators ---------------------------------------------------------------
    _section("sec-indicators", 2, "Indicator definitions",
             "Four core indicators and four supporting indicators, all defined in one registry.")
    _indicator_cards()
    if definitions is not None:
        derived = definitions[~definitions["Indicator"].isin(
            [i["label"] for i in REGISTRY] + [i["national"] for i in REGISTRY])]
        with st.expander("View the definitions file and derived measures"):
            st.dataframe(definitions, use_container_width=True, hide_index=True)
            if len(derived):
                st.caption("Rows that do not map to a dashboard indicator are derived 'distance from 100%' "
                           "measures kept for reference; the dashboard compares districts with the national "
                           "estimate instead.")

    # ---- 3. Weighted estimates -----------------------------------------------------------
    _section("sec-weights", 3, "Weighted estimates", "How each percentage in the dashboard is calculated.")
    f_left, f_right = st.columns([1.35, 1], gap="medium")
    with f_left:
        with st.container(key="card_formula"):
            card_title("The weighted percentage",
                       "Estimates use the individual survey weight pop_wt. For a binary indicator:")
            st.latex(r"\hat{p} = \frac{\sum_i w_i\, y_i}{\sum_i w_i} \times 100")
            render_html("""
                <div class="formula-sym">
                  <div><b>p̂</b>The weighted percentage reported in the dashboard.</div>
                  <div><b>w<sub>i</sub></b>The weight of respondent i.</div>
                  <div><b>y<sub>i</sub></b>1 if the respondent meets the indicator definition, otherwise 0.</div>
                </div>""")
    with f_right:
        render_html("""
            <div class="mcard"><div class="mc-ic">✓</div><div class="mc-t">Only valid responses count</div>
              <p class="mc-p">Only valid responses for the relevant indicator are included. Each dashboard
              indicator has full response coverage; routed questions are handled separately (see data quality).</p></div>
            <div class="mcard" style="margin-top:14px"><div class="mc-ic">n</div>
              <div class="mc-t">Counts are sample counts</div>
              <p class="mc-p">Respondent counts shown in the dashboard are sample counts, not weighted population
              totals.</p></div>""")

    # ---- 4. Uncertainty ---------------------------------------------------------------------
    _section("sec-uncertainty", 4, "Uncertainty and sampling margins",
             "How much an estimate could move by chance, and what the dashboard does about it.")
    u_left, u_right = st.columns([1.2, 1], gap="medium")
    with u_left:
        with st.container(key="card_uncertainty"):
            card_title("The indicative margin",
                       "Shown as ± percentage points wherever a district or group estimate appears.")
            st.latex(r"\text{margin} = 1.96\sqrt{\frac{d\,\hat{p}(1-\hat{p})}{n}}\times 100")
            render_html("""<p class="mc-p"><b>n</b> is the number of respondents, <b>p̂</b> the estimate and
              <b>d</b> a design-effect multiplier (1.0 unless the user selects a higher assumption). The survey's
              strata and cluster identifiers are not in the supplied dataset, so the formula assumes simple random
              sampling. The true design-based margin is therefore <b>larger</b>, and every margin shown is a
              minimum.</p>
              <p class="mc-p" style="margin-top:10px">Where a gap is smaller than the margin, the dashboard labels it
              as within the margin and does not treat it as a real difference.</p>""")
    with u_right:
        rows = "".join(
            f"<tr><td><b>{n:,}</b></td><td>±{data.moe_pp(20, n):.1f} pp</td><td>±{data.moe_pp(20, n, 2):.1f} pp</td>"
            f"<td>±{data.worst_case_moe(n):.1f} pp</td></tr>" for n in (144, 400, 800, 1800, 5800))
        render_html(f"""
            <div class="mcard"><div class="mc-t">What the margin looks like</div>
            <table class="cmp"><tr><th>Respondents</th><th>20% estimate</th><th>20%, design effect 2</th>
            <th>Worst case (50%)</th></tr>{rows}</table>
            <div class="micro">The smallest district has 399 respondents and the smallest population group 144.
            Estimates are flagged as having a wide margin when the worst-case margin exceeds
            ±{data.WIDE_MARGIN_PP:.0f} pp.</div></div>""")

    # ---- 5. Comparisons --------------------------------------------------------------------------
    _section("sec-districts", 5, "District and group comparisons",
             "District estimates are compared with national estimates to flag differences that may warrant closer investigation.")
    render_html("""
        <div class="mgrid">
          <div class="mcard"><div class="mc-ic">Δ</div><div class="mc-t">Percentage points</div>
            <p class="mc-p">A percentage-point difference is the subtraction of two percentages.</p></div>
          <div class="mcard"><div class="mc-ic">↔</div><div class="mc-t">Gap is not spread</div>
            <p class="mc-p">A district's gap from the national estimate is not the same as the spread between the
            highest and lowest districts.</p></div>
          <div class="mcard"><div class="mc-ic">±</div><div class="mc-t">Compare with the margin</div>
            <p class="mc-p">A difference smaller than the indicative margin should not be read as real. Ranks of
            neighbouring districts are often not meaningfully different.</p></div>
          <div class="mcard"><div class="mc-ic">≈</div><div class="mc-t">Descriptive only</div>
            <p class="mc-p">Comparisons are descriptive and do not establish why a difference exists.</p></div>
        </div>""")

    # ---- 6. Priority scoring ------------------------------------------------------------------------
    _section("sec-scoring", 6, "Priority Explorer scoring",
             "An exploratory screening score, with checks on how much it depends on choices.")
    render_html("""
        <div class="pipe">
          <div class="step"><div class="step-n">1</div><div class="mc-t">Measure the gap</div>
            <p class="mc-p">Compare each district with the national estimate, in the direction that signals a
            need. Only positive gaps count.</p></div>
          <div class="step"><div class="step-n">2</div><div class="mc-t">Normalize</div>
            <p class="mc-p">Scale each gap against the largest observed gap for that indicator.</p></div>
          <div class="step"><div class="step-n">3</div><div class="mc-t">Average</div>
            <p class="mc-p">The chosen components receive equal weight in the score (0 to 100).</p></div>
          <div class="step"><div class="step-n">4</div><div class="mc-t">Test the choices</div>
            <p class="mc-p">Recompute the rank under every combination of two or more indicators and report how
            stable each district's rank is.</p></div>
        </div>""")
    st.markdown("")
    cards = "".join(f"""
        <div class="mcard" style="--accent:{i['accent']}"><div class="mc-t"><i></i>{esc(i['label'])}</div>
          <p class="mc-p">{'Lower than' if i['polarity'] == 'positive' else 'Higher than'} the national estimate signals a gap.
          {'Included by default.' if i['priority_default'] else 'Optional: add it with the indicator picker.'}</p></div>"""
        for i in PRIORITY_CANDIDATES)
    cards += """<div class="mcard" style="--accent:#E0A12F"><div class="mc-t"><i></i>Borrowing (not scored)</div>
        <p class="mc-p">Shown as supporting evidence rather than treated as inherently positive or negative.</p></div>"""
    render_html(f'<div class="mgrid">{cards}</div>')
    st.markdown("")
    note("A relative screening measure",
         "The priority score is an exploratory, relative screening measure. It is not an official poverty index, "
         "a probability, or a measure of the number of people in need.", tone="warn")

    # ---- 7. Barriers & group use ------------------------------------------------------------------------
    _section("sec-barriers", 7, "Barriers and community channels",
             "How the bank-account barriers and the SACCO and savings-group indicators are built.")
    b_left, b_right = st.columns([1.2, 1], gap="medium")
    with b_left:
        with st.container(key="card_barrier_method"):
            card_title("Reasons for not having a bank account",
                       "Asked of adults who reported no bank account. Weighted shares add up to 100%.")
            families = {}
            for reason, (short, family) in data.BARRIER_LABELS.items():
                families.setdefault(family, []).append(short)
            rows = "".join(f"<tr><td><b>{esc(f)}</b></td><td>{esc('; '.join(families[f]))}</td></tr>"
                           for f in data.BARRIER_FAMILY_ORDER if f in families)
            render_html(f'<table class="cmp"><tr><th>Barrier family</th><th>Reasons grouped</th></tr>{rows}</table>'
                        '<div class="micro">Families are an analytical grouping made for this dashboard. The largest '
                        "category combines lack of need with insufficient income; the survey does not separate them.</div>")
    with b_right:
        render_html("""
            <div class="mcard"><div class="mc-ic">∑</div><div class="mc-t">Current use of SACCOs and savings groups</div>
              <p class="mc-p">These questions are only asked of people who have ever used the service. The
              dashboard computes the share of <b>all</b> respondents who currently use each one, counting never-users
              as non-users, so the estimate covers the full sample and sits below the ever-use figure.</p></div>
            <div class="mcard" style="margin-top:14px"><div class="mc-ic">≠</div><div class="mc-t">Two group-saving questions</div>
              <p class="mc-p">'Saves with a group' (a saving-mechanism question) and 'Currently uses a savings
              group' (a provider-use question) are different measures and give different national figures.</p></div>""")

    # ---- 8. Data quality ---------------------------------------------------------------------------------------
    _section("sec-quality", 8, "Data quality and measurement notes",
             "Automated checks run each time this page loads, and as tests before release.")
    with st.container(key="card_checks"):
        card_title("Automated data checks", "Every check reads the processed files used by the dashboard.")
        _checks_panel(results)
    st.markdown("")
    render_html("""
        <div class="mgrid wide">
          <div class="mcard"><div class="mc-ic warn">!</div><div class="mc-t">What 'registered mobile-money user' counts</div>
            <p class="mc-p">Question F5 has six answers. The indicator counts only 'You are a registered mobile money
            user' (9,434 respondents, 67.4% unweighted). Respondents who say they are registered but have never used it
            (452) or used it before but not any more (883) are separate answers and are not counted. Together the three
            registered answers make up 77.0% of respondents, in line with the published headline for registered
            wallets. The dashboard indicator is therefore stricter than that headline and is labelled
            'active registered user'.</p></div>
          <div class="mcard"><div class="mc-ic warn">!</div><div class="mc-t">Provider-level questions use routing</div>
            <p class="mc-p">Questions such as current use of a mobile-money operator were only asked of ever-users
            (4,915 respondents), so skipped answers are not 'No'. These are documented in the candidate register and
            are not used as full-population indicators. They give a lower mobile-money figure than question F5 and
            are not comparable with it.</p></div>
        </div>""")
    st.markdown("")
    register = data.load_candidate_register()
    denominators = data.load_denominators()
    with st.expander("Indicator candidate register (what was considered, kept and deferred)"):
        if register is not None:
            st.dataframe(register, use_container_width=True, hide_index=True)
        st.caption("Core indicators are retained as headline measures. Supporting indicators are kept where "
                   "denominators and routing are understood. Deferred items are too sparse or too specific for general use.")
    with st.expander("Denominator and response validation"):
        if denominators is not None:
            st.dataframe(denominators.drop(columns=["Observed categories"], errors="ignore"),
                         use_container_width=True, hide_index=True)

    # ---- 9. Limitations -------------------------------------------------------------------------------------------
    _section("sec-limits", 9, "Limitations", "What these results cannot tell you.")
    limitations = [
        ("Not a live picture", "FinScope 2024 does not provide a live picture of financial inclusion."),
        ("Survey uncertainty", "Survey estimates may be affected by sampling and measurement uncertainty."),
        ("Margins are minimums", "The dataset lacks the survey-design information (strata and clusters) needed "
         "for design-correct confidence intervals, so the margins shown assume simple random sampling and understate "
         "true uncertainty. Formal significance testing is not claimed."),
        ("Smaller samples", "District and group estimates are less stable when based on fewer respondents."),
        ("No causation", "Differences between groups do not establish causation."),
        ("Mobile-money definition", "The mobile-money indicator is stricter than the published registered-wallet "
         "headline and should not be compared with it directly."),
        ("Barrier reasons", "The largest barrier category combines two explanations, and reason-level estimates for "
         "small districts rest on few respondents, so barrier families are emphasised."),
        ("External data", "External indicators, if added later, must have their own dates, sources, geographic "
         "coverage, and definitions documented."),
    ]
    try:
        missing_ur = [i["short"] for i in REGISTRY if i["column"] not in data.read_urban_rural().columns]
        missing_pg = [i["short"] for i in REGISTRY if i["column"] not in data.read_population_groups().columns]
        gaps = sorted(set(missing_ur) | set(missing_pg))
        if gaps:
            limitations.append(("Breakdowns still to add", f"{', '.join(gaps)} are not yet broken down by urban-rural "
                                "area or population group. They appear there automatically once those tables are rebuilt."))
    except Exception:
        pass
    cards = "".join(f'<div class="mcard"><div class="mc-ic warn">!</div><div class="mc-t">{esc(t)}</div>'
                    f'<p class="mc-p">{esc(x)}</p></div>' for t, x in limitations)
    render_html(f'<div class="mgrid">{cards}</div>')

    # ---- 10. Sources -----------------------------------------------------------------------------------------------
    _section("sec-sources", 10, "Sources and reproducibility", "Citation, files, and how to reproduce the results.")
    with st.container(key="card_method_sources"):
        render_html("""
            <div class="ct" style="font-size:17px;margin:0 0 8px">Data citation</div>
            <p class="mc-p"><b>FinScope 2024, Financial Inclusion in Rwanda.</b> Producer: Access to Finance Rwanda,
            with the National Institute of Statistics of Rwanda (NISR). Reference ID
            <span class="code" style="margin:0">RWA-NISR-FINSCOPE-2024-v01</span>. Fieldwork 6 September to
            8 October 2024. Available from the NISR microdata catalogue and the
            <a href="https://statistics.gov.rw/statistical-publications/business-establishment-finance-trade/finscope-survey-2024"
            target="_blank" rel="noopener">NISR FinScope 2024 page</a>.</p>
            <p class="mc-p" style="margin-top:10px">Processed outputs are stored in
            <span class="code" style="margin:0">data/processed/</span>; the original survey file is in
            <span class="code" style="margin:0">data/datasets/</span>.</p>
            <div class="ct" style="font-size:17px;margin:18px 0 10px">Project files</div>""")
        files = sorted(p.name for p in data.DATA_DIR.glob("*.csv")) if data.DATA_DIR.exists() else []
        rows = "".join(f'<div class="file"><span class="file-ic">CSV</span><span class="file-n">{esc(f)}</span></div>'
                       for f in files)
        rows += ('<div class="file"><span class="file-ic nb">PY</span><span class="file-n">scripts/build_processed_data.py '
                 "(rebuilds every processed table, including the newer indicators, from the survey file)</span></div>"
                 '<div class="file"><span class="file-ic nb">PY</span><span class="file-n">tests/ (data-integrity and page smoke tests)</span></div>'
                 '<div class="file"><span class="file-ic nb">NB</span><span class="file-n">Exploratory analysis and '
                 "indicator-analysis notebooks (02, 03, 04)</span></div>")
        render_html(f'<div class="mgrid">{rows}</div>')
