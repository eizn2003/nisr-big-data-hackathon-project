import pandas as pd
import streamlit as st

from src import data, validation
from src.indicators import CORE, PRIORITY_CANDIDATES, REGISTRY
from src.pages.combined_support import (
    EVIDENCE_CLASSES,
    STATE_TITLES,
    ROUTED_INDICATOR_NOTES,
    contextual_variables,
    header_pill,
    mapping_rows,
)
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


COMBINED_SECTION = ("sec-combined", "Using both sources")


def _sections(combined):
    """Section list; Combined mode adds one section after the data source."""
    if not combined:
        return list(SECTIONS)
    return [SECTIONS[0], COMBINED_SECTION, *SECTIONS[1:]]


def _toc(sections=SECTIONS):
    links = "".join(
        f'<a href="#{a}"><b>{i}</b>{esc(t)}</a>'
        for i, (a, t) in enumerate(sections, start=1)
    )
    render_html(f'<div class="toc">{links}</div>')


def _indicator_cards():
    cards = []
    for item in REGISTRY:
        role = badge(
            "Core" if item["role"] == "core" else "Supporting",
            "ok" if item["role"] == "core" else "info",
        )
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


_DIMENSIONS = [
    (
        "National",
        "Yes",
        "Yes",
        "Both sources reported separately, with their own units and dates.",
    ),
    (
        "District",
        "Yes",
        "Yes, for some series",
        "NBR peer comparisons use the same metric, filters and reporting date.",
    ),
    (
        "Gender",
        "Yes",
        "Only on NBR pages with a Gender breakdown",
        "Shown only when the NBR page behind an approved series exposes Gender and stores that exact category. The branch series currently approved do not, so no gender context is shown.",
    ),
    (
        "Age group",
        "Yes",
        "Separate NBR Youth / Non-Youth slices where exact filters exist",
        "Shown only as NBR categories; never crosswalked to FinScope age bands.",
    ),
    (
        "Education",
        "Yes",
        "No",
        "NBR has no education breakdown; no comparison is made.",
    ),
    (
        "Urban/rural area",
        "Yes",
        "No",
        "NBR has no urban/rural breakdown; no comparison is made.",
    ),
]


def _routed_questions_card():
    """Show valid-response shares and denominator caveats for routed indicators."""
    frame = data.load_denominators()
    shares = {}
    if frame is not None and {"Variable", "Valid response (%)"} <= set(frame.columns):
        shares = dict(zip(frame["Variable"], frame["Valid response (%)"]))
    with st.container(key="card_combined_routed"):
        card_title(
            "Questions with routed or missing answers",
            "Existing calculations are unchanged; this states what the figures do and do not establish.",
        )
        rows = []
        for item in REGISTRY:
            variable = item["variable"]
            if variable not in ROUTED_INDICATOR_NOTES:
                continue
            share = shares.get(variable)
            rows.append(
                f"<tr><td><b>{esc(item['label'])}</b></td>"
                f"<td>{f'{float(share):.1f}%' if share is not None else 'Not available in the denominator file'}</td>"
                f"<td>{esc(ROUTED_INDICATOR_NOTES[variable])}</td></tr>"
            )
        render_html(
            '<table class="cmp"><tr><th>Indicator</th><th>Valid responses</th><th>How to read it</th></tr>'
            + "".join(rows)
            + "</table>"
        )
        render_html(
            '<div class="micro">For qf4_05 and qf5_05_6, skipped respondents are excluded from the estimate. '
            "The existing qf4_06 and qf4_10 current-use estimates use the full respondent population and treat "
            "missing answers as non-use; because the routing has not been verified, they are not confirmed "
            "non-use rates.</div>"
        )


def _render_combined_methodology():
    from src.models.nbr_intelligence.indicator_mapping import MAPPING_BY_VARIABLE

    render_html("""
        <div class="mgrid">
          <div class="mcard"><div class="mc-t">FinScope: people's reported behaviour</div>
            <p class="mc-p">A weighted household survey of Rwanda residents aged 16 and over (weight
            <span class="code" style="margin:0">pop_wt</span>). It describes what people report about access, use and
            experience, with sampling uncertainty. Values are percentages.</p></div>
          <div class="mcard"><div class="mc-t">NBR: recorded financial-system activity</div>
            <p class="mc-p">Administrative observations kept with the unit, filters and reporting date given by the
            source, for example a count of branches. They describe what institutions recorded, not what people
            report, and they are not rates of ownership or use.</p></div>
          <div class="mcard"><div class="mc-t">What a mapping means</div>
            <p class="mc-p">An approved mapping says an NBR series is thematically relevant to a survey indicator.
            It does not make the two equivalent, and neither source validates, explains or predicts the other.</p></div>
        </div>""")
    st.markdown("")
    with st.container(key="card_combined_mapping"):
        card_title(
            "Approved relationships between survey indicators and NBR series",
            "Read from the project configuration. Only relationships marked as contextual are ever shown on a page.",
        )
        rows = mapping_rows(MAPPING_BY_VARIABLE, REGISTRY)
        st.dataframe(
            pd.DataFrame(rows),
            use_container_width=True,
            hide_index=True,
            height=min(480, 44 + 36 * len(rows)),
        )
    st.markdown("")
    left, right = st.columns([1, 1], gap="medium")
    with left:
        with st.container(key="card_combined_dimensions"):
            card_title(
                "Where each source can be used",
                "By geography and population dimension.",
            )
            body = "".join(
                f"<tr><td><b>{esc(d)}</b></td><td>{esc(fs)}</td><td>{esc(nbr)}</td><td>{esc(why)}</td></tr>"
                for d, fs, nbr, why in _DIMENSIONS
            )
            render_html(
                f'<table class="cmp"><tr><th>Dimension</th><th>FinScope</th><th>NBR</th><th>How it is handled</th></tr>{body}</table>'
            )
    with right:
        with st.container(key="card_combined_states"):
            card_title(
                "How every relationship is classified",
                "Each case is named on the page instead of left blank.",
            )
            body = "".join(
                f'<tr><td><b>{esc(label)}</b><br><span class="micro">'
                f"{esc(' / '.join(STATE_TITLES[k] for k in keys))}</span></td><td>{esc(meaning)}</td></tr>"
                for label, keys, meaning in EVIDENCE_CLASSES
            )
            render_html(
                f'<table class="cmp"><tr><th>Classification</th><th>Meaning</th></tr>{body}</table>'
            )
    st.markdown("")
    _routed_questions_card()
    st.markdown("")
    note(
        "What Combined mode never does",
        "It does not subtract, divide, correlate or score across the two sources, treat an administrative count "
        "as a survey rate, fill missing observations with zero, or build a continuous history across missing dates. "
        "The priority score uses FinScope only; NBR context is reference material beside it.",
        tone="warn",
    )


def render_methodology():
    from src.pages.nbr_dashboard import current_mode, render_methodology_mode_note

    mode = current_mode()
    combined = mode == "Combined"
    render_methodology_mode_note()
    try:
        definitions = load_definitions()
    except (OSError, ValueError):
        definitions = None
    results = _checks()
    counts = validation.summarize(results)
    total_checks = sum(counts.values())

    n_context = 0
    if combined:
        from src.models.nbr_intelligence.indicator_mapping import (
            MAPPING_BY_VARIABLE as _MAPPING,
        )

        n_context = len(
            set(contextual_variables(_MAPPING)) & {i["variable"] for i in REGISTRY}
        )

    facts = "".join(
        [
            _fact("Survey", "2024", "FinScope Rwanda · NISR", PALETTE["teal"], 42),
            _fact(
                "Estimates",
                "Weighted",
                'Individual survey weight <span class="code" style="margin:0">pop_wt</span>',
                PALETTE["blue"],
                32,
            ),
            _fact(
                "Indicators documented",
                f"{len(REGISTRY)}",
                f"{len(CORE)} core and {len(REGISTRY) - len(CORE)} supporting"
                + (f" · {n_context} with approved NBR context" if combined else ""),
                PALETTE["amber"],
                42,
            ),
            _fact(
                "Automated data checks",
                f"{counts['pass']}/{total_checks}",
                f"{counts['fail']} failed · {counts['warn']} notes to read",
                PALETTE["coral"],
                42,
            ),
        ]
    )
    page_header(
        "Methodology & sources",
        "The data, calculations, assumptions, checks and limitations behind the Rwanda Financial Inclusion Gap Explorer."
        + (
            " This view also explains how NBR administrative observations are used alongside the survey."
            if combined
            else ""
        ),
        pill=header_pill(mode, "FinScope Rwanda 2024"),
        mode=mode,
        size="tall",
        below_html=f'<div class="kpi-grid">{facts}</div>',
    )
    st.markdown("")
    render_html(
        '<div class="sec"><div class="cs" style="margin:0 0 6px">Jump to a section</div></div>'
    )
    sections = _sections(combined)
    number = {anchor: i for i, (anchor, _) in enumerate(sections, start=1)}
    _toc(sections)

    # ---- 1. Data source -------------------------------------------------------
    _section(
        "sec-source",
        number["sec-source"],
        "Data source",
        "Where the numbers come from and what they represent.",
    )
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
        if combined:
            render_html("""<p class="mc-p" style="margin-top:12px">Combined mode adds
            <b>NBR administrative observations</b> as a separate, labelled source. They are never merged into the
            survey estimates described below.</p>""")

    if combined:
        _section(
            "sec-combined",
            number["sec-combined"],
            "Using both sources",
            "What each source measures, which relationships are approved, and where evidence is unavailable.",
        )
        _render_combined_methodology()

    # ---- 2. Indicators ---------------------------------------------------------------
    _section(
        "sec-indicators",
        number["sec-indicators"],
        "Indicator definitions",
        "Four core indicators and four supporting indicators, all defined in one registry.",
    )
    _indicator_cards()
    if definitions is not None:
        derived = definitions[
            ~definitions["Indicator"].isin(
                [i["label"] for i in REGISTRY] + [i["national"] for i in REGISTRY]
            )
        ]
        with st.expander("View the definitions file and derived measures"):
            st.dataframe(definitions, use_container_width=True, hide_index=True)
            if len(derived):
                st.caption(
                    "Rows that do not map to a dashboard indicator are derived 'distance from 100%' "
                    "measures kept for reference; the dashboard compares districts with the national "
                    "estimate instead."
                )

    # ---- 3. Weighted estimates -----------------------------------------------------------
    _section(
        "sec-weights",
        number["sec-weights"],
        "Weighted estimates",
        "How each percentage in the dashboard is calculated.",
    )
    f_left, f_right = st.columns([1.35, 1], gap="medium")
    with f_left:
        with st.container(key="card_formula"):
            card_title(
                "The weighted percentage",
                "Estimates use the individual survey weight pop_wt. For a binary indicator:",
            )
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
    _section(
        "sec-uncertainty",
        number["sec-uncertainty"],
        "Uncertainty and sampling margins",
        "How much an estimate could move by chance, and what the dashboard does about it.",
    )
    u_left, u_right = st.columns([1.2, 1], gap="medium")
    with u_left:
        with st.container(key="card_uncertainty"):
            card_title(
                "The indicative margin",
                "Shown as ± percentage points wherever a district or group estimate appears.",
            )
            st.latex(
                r"\text{margin} = 1.96\sqrt{\frac{d\,\hat{p}(1-\hat{p})}{n}}\times 100"
            )
            render_html(
                """<p class="mc-p"><b>n</b> is the number of respondents, <b>p̂</b> the estimate and
              <b>d</b> a design-effect multiplier (1.0 unless the user selects a higher assumption). The survey's
              strata and cluster identifiers are not in the supplied dataset. This illustrative binomial calculation
              uses a simple-random-sample assumption and does not account for the full survey design or weighting
              variance; actual design-based uncertainty may differ.</p>
              <p class="mc-p" style="margin-top:10px">A margin comparison is an illustrative caution flag only.
              It is not a confidence interval for the district-versus-national difference and does not establish
              whether that difference is statistically meaningful.</p>"""
            )
    with u_right:
        rows = "".join(
            f"<tr><td><b>{n:,}</b></td><td>±{data.moe_pp(20, n):.1f} pp</td><td>±{data.moe_pp(20, n, 2):.1f} pp</td>"
            f"<td>±{data.worst_case_moe(n):.1f} pp</td></tr>"
            for n in (144, 400, 800, 1800, 5800)
        )
        render_html(f"""
            <div class="mcard"><div class="mc-t">What the margin looks like</div>
            <table class="cmp"><tr><th>Respondents</th><th>20% estimate</th><th>20%, design effect 2</th>
            <th>Worst case (50%)</th></tr>{rows}</table>
            <div class="micro">The smallest district has 399 respondents and the smallest population group 144.
            Estimates are flagged as having a wide margin when the worst-case margin exceeds
            ±{data.WIDE_MARGIN_PP:.0f} pp.</div></div>""")

    # ---- 5. Comparisons --------------------------------------------------------------------------
    _section(
        "sec-districts",
        number["sec-districts"],
        "District and group comparisons",
        "District estimates are compared with national estimates to flag differences that may warrant closer investigation.",
    )
    render_html("""
        <div class="mgrid">
          <div class="mcard"><div class="mc-ic">Δ</div><div class="mc-t">Percentage points</div>
            <p class="mc-p">A percentage-point difference is the subtraction of two percentages.</p></div>
          <div class="mcard"><div class="mc-ic">↔</div><div class="mc-t">Gap is not spread</div>
            <p class="mc-p">A district's gap from the national estimate is not the same as the spread between the
            highest and lowest districts.</p></div>
          <div class="mcard"><div class="mc-ic">±</div><div class="mc-t">Margins are caution flags</div>
            <p class="mc-p">Displayed margins use district sample sizes and a simple-random-sample approximation.
            They are not confidence intervals for the district-versus-national difference and do not establish
            statistical significance.</p></div>
          <div class="mcard"><div class="mc-ic">≈</div><div class="mc-t">Descriptive only</div>
            <p class="mc-p">Comparisons are descriptive and do not establish why a difference exists.</p></div>
        </div>""")

    # ---- 6. Priority scoring ------------------------------------------------------------------------
    _section(
        "sec-scoring",
        number["sec-scoring"],
        "Priority Explorer scoring",
        "An exploratory screening score, with checks on how much it depends on choices.",
    )
    render_html("""
        <div class="pipe">
          <div class="step"><div class="step-n">1</div><div class="mc-t">Measure the gap</div>
            <p class="mc-p">Compare each district with the national survey estimate, a descriptive reference rather
            than a policy target. Only positive gaps in the selected direction count.</p></div>
          <div class="step"><div class="step-n">2</div><div class="mc-t">Normalize</div>
            <p class="mc-p">Scale each gap against the largest observed district gap for that indicator.</p></div>
          <div class="step"><div class="step-n">3</div><div class="mc-t">Average</div>
            <p class="mc-p">The fixed baseline equally weights four indicators across access/use and resilience.
            What-if scenarios equally weight their selected indicators. Scores are relative points, not percentages.</p></div>
          <div class="step"><div class="step-n">4</div><div class="mc-t">Test the choices</div>
            <p class="mc-p">Recompute the rank under every combination of two or more indicators and report how
            sensitive each district's position is to indicator choice. This is not a probability or confidence interval.</p></div>
        </div>""")
    st.markdown("")
    cards = "".join(
        f"""
        <div class="mcard" style="--accent:{i['accent']}"><div class="mc-t"><i></i>{esc(i['label'])}</div>
          <p class="mc-p">{'Lower than' if i['polarity'] == 'positive' else 'Higher than'} the national estimate signals a gap.
          {'Included by default.' if i['priority_default'] else 'Optional: add it with the indicator picker.'}</p></div>"""
        for i in PRIORITY_CANDIDATES
    )
    cards += """<div class="mcard" style="--accent:#E0A12F"><div class="mc-t"><i></i>Borrowing (not scored)</div>
        <p class="mc-p">Shown as supporting evidence rather than treated as inherently positive or negative.</p></div>"""
    render_html(f'<div class="mgrid">{cards}</div>')
    st.markdown("")
    note(
        "A relative screening measure",
        "The fixed baseline combines access/use (bank-account ownership and registered mobile-money use) with "
        "resilience (not saving and emergency funds). The national survey estimate is a descriptive comparator, "
        "not a policy target. Scores are exploratory relative points—not an official poverty index, probability, "
        "absolute population need, or estimate of investment returns. Use them to identify where to investigate; "
        "assess population reach, service availability, costs, intervention suitability, and current local context "
        "separately before allocating investment.",
        tone="warn",
    )

    # ---- 7. Barriers & group use ------------------------------------------------------------------------
    _section(
        "sec-barriers",
        number["sec-barriers"],
        "Barriers and community channels",
        "How the bank-account barriers and the SACCO and savings-group indicators are built.",
    )
    b_left, b_right = st.columns([1.2, 1], gap="medium")
    with b_left:
        with st.container(key="card_barrier_method"):
            card_title(
                "Reasons for not having a bank account",
                "Asked of adults who reported no bank account. Weighted shares add up to 100%.",
            )
            families = {}
            for reason, (short, family) in data.BARRIER_LABELS.items():
                families.setdefault(family, []).append(short)
            rows = "".join(
                f"<tr><td><b>{esc(f)}</b></td><td>{esc('; '.join(families[f]))}</td></tr>"
                for f in data.BARRIER_FAMILY_ORDER
                if f in families
            )
            render_html(
                f'<table class="cmp"><tr><th>Barrier family</th><th>Reasons grouped</th></tr>{rows}</table>'
                '<div class="micro">Families are an analytical grouping made for this dashboard. The largest '
                "category combines lack of need with insufficient income; the survey does not separate them.</div>"
            )
    with b_right:
        render_html(
            """
            <div class="mcard"><div class="mc-ic">∑</div><div class="mc-t">Current use of SACCOs and savings groups</div>
              <p class="mc-p">These questions are only asked of people who have ever used the service. The
              dashboard computes the share of <b>all</b> respondents who currently use each one, counting never-users
              as non-users, so the estimate covers the full sample and sits below the ever-use figure.</p></div>
            <div class="mcard" style="margin-top:14px"><div class="mc-ic">≠</div><div class="mc-t">Two group-saving questions</div>
              <p class="mc-p">'Saves with a group' (a saving-mechanism question) and 'Currently uses a savings
              group' (a provider-use question) are different measures and give different national figures.</p></div>"""
        )

    # ---- 8. Data quality ---------------------------------------------------------------------------------------
    _section(
        "sec-quality",
        number["sec-quality"],
        "Data quality and measurement notes",
        "Automated checks run each time this page loads, and as tests before release.",
    )
    with st.container(key="card_checks"):
        card_title(
            "Automated data checks",
            "Every check reads the processed files used by the dashboard.",
        )
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
    with st.expander(
        "Indicator candidate register (what was considered, kept and deferred)"
    ):
        if register is not None:
            st.dataframe(register, use_container_width=True, hide_index=True)
        st.caption(
            "Core indicators are retained as headline measures. Supporting indicators are kept where "
            "denominators and routing are understood. Deferred items are too sparse or too specific for general use."
        )
    with st.expander("Denominator and response validation"):
        if denominators is not None:
            st.dataframe(
                denominators.drop(columns=["Observed categories"], errors="ignore"),
                use_container_width=True,
                hide_index=True,
            )

    # ---- 9. Limitations -------------------------------------------------------------------------------------------
    _section(
        "sec-limits",
        number["sec-limits"],
        "Limitations",
        "What these results cannot tell you.",
    )
    limitations = [
        (
            "Not a live picture",
            "FinScope 2024 does not provide a live picture of financial inclusion.",
        ),
        (
            "Survey uncertainty",
            "Survey estimates may be affected by sampling and measurement uncertainty.",
        ),
        (
            "Margins are not a difference test",
            "The dataset lacks the survey-design information (strata and clusters) "
            "needed for design-correct uncertainty. Displayed district-only margins are illustrative caution flags, "
            "not confidence intervals for comparisons with the national estimate. Formal significance testing is not claimed.",
        ),
        (
            "Smaller samples",
            "District and group estimates are less stable when based on fewer respondents.",
        ),
        (
            "Population reach and investment",
            "Respondent counts are survey sample sizes, not the number of people "
            "who could benefit from investment. The dashboard does not estimate district population reach, costs, or "
            "returns. Before allocating funds, combine the screening with current population, service availability, "
            "intervention-eligibility data, and local validation.",
        ),
        ("No causation", "Differences between groups do not establish causation."),
        (
            "Mobile-money definition",
            "The mobile-money indicator is stricter than the published registered-wallet "
            "headline and should not be compared with it directly.",
        ),
        (
            "Barrier reasons",
            "The largest barrier category combines two explanations, and reason-level estimates for "
            "small districts rest on few respondents, so barrier families are emphasised.",
        ),
        (
            "External data",
            "External indicators, if added later, must have their own dates, sources, geographic "
            "coverage, and definitions documented.",
        ),
    ]
    if combined:
        limitations += [
            (
                "NBR counts are not rates",
                "Administrative counts describe recorded activity. They do not give the "
                "share of people who own, use or can reach a service, and say nothing about who is missing.",
            ),
            (
                "NBR units and filters",
                "Each NBR series keeps the unit and filters stored with the source; where the "
                "source gives no unit, the page says so rather than inferring one.",
            ),
            (
                "Missing is not zero",
                "A district or date without an NBR observation is unknown. It is never shown "
                "as zero or filled from neighbouring dates.",
            ),
            (
                "Demographic coverage",
                "NBR has no education or urban/rural breakdown, and its Youth and Non-Youth "
                "categories are not matched to survey age groups. Only exact observed Gender categories are used.",
            ),
            (
                "Experimental administrative data",
                "NBR observations are marked beta; unusual-observation signals "
                "are review prompts, not findings of exclusion or causation.",
            ),
        ]
    try:
        missing_ur = [
            i["short"]
            for i in REGISTRY
            if i["column"] not in data.read_urban_rural().columns
        ]
        missing_pg = [
            i["short"]
            for i in REGISTRY
            if i["column"] not in data.read_population_groups().columns
        ]
        gaps = sorted(set(missing_ur) | set(missing_pg))
        if gaps:
            limitations.append(
                (
                    "Breakdowns still to add",
                    f"{', '.join(gaps)} are not yet broken down by urban-rural "
                    "area or population group. They appear there automatically once those tables are rebuilt.",
                )
            )
    except Exception:
        pass
    cards = "".join(
        f'<div class="mcard"><div class="mc-ic warn">!</div><div class="mc-t">{esc(t)}</div>'
        f'<p class="mc-p">{esc(x)}</p></div>'
        for t, x in limitations
    )
    render_html(f'<div class="mgrid">{cards}</div>')

    # ---- 10. Sources -----------------------------------------------------------------------------------------------
    _section(
        "sec-sources",
        number["sec-sources"],
        "Sources and reproducibility",
        "Citation, files, and how to reproduce the results.",
    )
    with st.container(key="card_method_sources"):
        render_html(
            """
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
            <div class="ct" style="font-size:17px;margin:18px 0 10px">Project files</div>"""
        )
        files = (
            sorted(p.name for p in data.DATA_DIR.glob("*.csv"))
            if data.DATA_DIR.exists()
            else []
        )
        rows = "".join(
            f'<div class="file"><span class="file-ic">CSV</span><span class="file-n">{esc(f)}</span></div>'
            for f in files
        )
        rows += (
            '<div class="file"><span class="file-ic nb">PY</span><span class="file-n">scripts/build_processed_data.py '
            "(rebuilds every processed table, including the newer indicators, from the survey file)</span></div>"
            '<div class="file"><span class="file-ic nb">PY</span><span class="file-n">tests/ (data-integrity and page smoke tests)</span></div>'
            '<div class="file"><span class="file-ic nb">NB</span><span class="file-n">Exploratory analysis and '
            "indicator-analysis notebooks (02, 03, 04)</span></div>"
        )
        render_html(f'<div class="mgrid">{rows}</div>')
