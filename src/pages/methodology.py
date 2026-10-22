from pathlib import Path

import pandas as pd
import streamlit as st

from src.styles import (
    INDICATOR_THEME,
    PALETTE,
    card_title,
    esc,
    note,
    page_header,
    render_html,
)


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data" / "processed"
DEFINITIONS_PATH = DATA_DIR / "indicator_definitions.csv"

SECTIONS = [
    ("sec-source", "Data source"),
    ("sec-indicators", "Indicator definitions"),
    ("sec-weights", "Weighted estimates"),
    ("sec-districts", "District comparisons"),
    ("sec-scoring", "Priority scoring"),
    ("sec-limits", "Limitations"),
    ("sec-sources", "Sources"),
]

FALLBACK_ACCENTS = ["#1A8A7D", "#2F6DB5", "#E0A12F", "#DB6A4E", "#5FB8AB", "#163D4B"]


@st.cache_data
def load_definitions():
    if not DEFINITIONS_PATH.exists():
        return None

    definitions = pd.read_csv(DEFINITIONS_PATH)

    required = {
        "Indicator",
        "Source variable",
        "Definition",
        "Interpretation",
    }

    missing = required.difference(definitions.columns)
    if missing:
        raise ValueError(
            "Indicator definitions file is missing columns: "
            + ", ".join(sorted(missing))
        )

    return definitions


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _section(anchor, number, title, subtitle=None):
    sub = f'<div class="cs">{esc(subtitle)}</div>' if subtitle else ""
    render_html(
        f"""
        <div class="msec" id="{anchor}">
          <div class="msec-n">{number}</div>
          <div><div class="ct">{esc(title)}</div>{sub}</div>
        </div>
        """
    )


def _accent_for(indicator_name, position):
    name = str(indicator_name).lower()
    for theme in INDICATOR_THEME.values():
        if theme["national"].lower() in name or theme["label"].lower() in name:
            return theme["accent"]
    return FALLBACK_ACCENTS[position % len(FALLBACK_ACCENTS)]


def _fact(label, value, src, accent, size=34):
    return f"""
    <div class="kpi" style="--accent:{accent}">
      <div class="kpi-label"><i></i><span>{esc(label)}</span></div>
      <div class="kpi-value" style="font-size:{size}px;margin-bottom:8px">{value}</div>
      <div class="kpi-src" style="margin-top:0">{src}</div>
    </div>
    """


def _toc():
    links = "".join(
        f'<a href="#{anchor}"><b>{i}</b>{esc(title)}</a>'
        for i, (anchor, title) in enumerate(SECTIONS, start=1)
    )
    render_html(f'<div class="toc">{links}</div>')


def _definition_cards(definitions):
    cards = []
    for position, (_, row) in enumerate(definitions.iterrows()):
        accent = _accent_for(row["Indicator"], position)
        cards.append(
            f"""
            <div class="mcard" style="--accent:{accent}">
              <div class="mc-t"><i></i>{esc(row["Indicator"])}</div>
              <span class="code">{esc(row["Source variable"])}</span>
              <p class="mc-p">{esc(row["Definition"])}</p>
              <div class="mc-read"><b>How to read it.</b> {esc(row["Interpretation"])}</div>
            </div>
            """
        )
    render_html(f'<div class="mgrid wide">{"".join(cards)}</div>')


# --------------------------------------------------------------------------
# page
# --------------------------------------------------------------------------
def render_methodology():
    try:
        definitions = load_definitions()
        definitions_error = None
    except (OSError, ValueError) as error:
        definitions = None
        definitions_error = str(error)

    indicator_count = len(definitions) if definitions is not None else "—"

    # ---- Hero + facts ------------------------------------------------------
    facts = "".join(
        [
            _fact("Survey", "2024", "FinScope Rwanda", PALETTE["teal"], 42),
            _fact("Estimates", "Weighted", 'Individual survey weight <span class="code" style="margin:0">pop_wt</span>',
                  PALETTE["blue"], 32),
            _fact("Indicators documented", f"{indicator_count}",
                  "Definitions kept in indicator_definitions.csv" if definitions is not None
                  else "Definitions file not available", PALETTE["amber"], 42),
            _fact("Score components", "3", "Equal weight, relative screening only", PALETTE["coral"], 42),
        ]
    )

    page_header(
        "Methodology & sources",
        "The data, calculations, assumptions and limitations behind the "
        "Rwanda Financial Inclusion Gap Explorer.",
        pill="FinScope Rwanda 2024",
        size="tall",
        below_html=f'<div class="kpi-grid">{facts}</div>',
    )

    st.markdown("")
    render_html('<div class="sec"><div class="cs" style="margin:0 0 6px">Jump to a section</div></div>')
    _toc()

    # ---- 1. Data source -----------------------------------------------------
    _section("sec-source", 1, "Data source",
             "Where the numbers come from and what they represent.")
    with st.container(key="card_method_source"):
        render_html(
            """
            <p class="mc-p" style="font-size:15.5px">
            The current analysis uses <b>FinScope Rwanda 2024</b>, a survey used
            to examine financial inclusion in Rwanda.</p>
            <p class="mc-p" style="font-size:15.5px;margin-top:12px">
            District and population-group results are based on the respondents
            available in the supplied dataset. The dashboard does not treat
            these results as real-time measurements.</p>
            <div class="fchips">
              <span class="chip"><i style="border-color:#1A8A7D"></i>Survey-based estimates</span>
              <span class="chip"><i style="border-color:#2F6DB5"></i>30 districts</span>
              <span class="chip"><i style="border-color:#E0A12F"></i>Not a live measurement</span>
            </div>
            """
        )

    # ---- 2. Definitions -------------------------------------------------------
    _section("sec-indicators", 2, "Indicator definitions",
             "What each indicator measures and how to read it.")
    if definitions_error:
        st.warning("The indicator definitions could not be loaded.")
        st.caption(definitions_error)
    elif definitions is not None:
        _definition_cards(definitions)
        with st.expander("View definitions as a table"):
            st.dataframe(definitions, use_container_width=True, hide_index=True)
    else:
        note(
            "Definitions not available",
            "The indicator definitions CSV is not available or could not be "
            "read. The remaining methodology is still available below.",
        )

    # ---- 3. Weighted estimates ----------------------------------------------
    _section("sec-weights", 3, "Weighted estimates",
             "How each percentage in the dashboard is calculated.")
    f_left, f_right = st.columns([1.35, 1], gap="medium")

    with f_left:
        with st.container(key="card_formula"):
            card_title(
                "The weighted percentage",
                "Estimates use the individual survey weight pop_wt. For a "
                "binary indicator:",
            )
            st.latex(r"\hat{p} = \frac{\sum_i w_i\, y_i}{\sum_i w_i} \times 100")
            render_html(
                """
                <div class="formula-sym">
                  <div><b>p̂</b>The weighted percentage reported in the dashboard.</div>
                  <div><b>w<sub>i</sub></b>The weight of respondent i.</div>
                  <div><b>y<sub>i</sub></b>1 if the respondent meets the indicator definition, otherwise 0.</div>
                </div>
                """
            )

    with f_right:
        render_html(
            """
            <div class="mcard">
              <div class="mc-ic">✓</div>
              <div class="mc-t">Only valid responses count</div>
              <p class="mc-p">Only valid responses for the relevant indicator
              are included in each calculation.</p>
            </div>
            <div class="mcard" style="margin-top:14px">
              <div class="mc-ic">n</div>
              <div class="mc-t">Counts are sample counts</div>
              <p class="mc-p">Respondent counts shown in the dashboard are
              sample counts, not weighted population totals.</p>
            </div>
            """
        )

    # ---- 4. District comparisons --------------------------------------------
    _section("sec-districts", 4, "District comparisons",
             "District estimates are compared with national estimates to "
             "flag differences that may warrant closer investigation.")
    render_html(
        """
        <div class="mgrid">
          <div class="mcard"><div class="mc-ic">Δ</div>
            <div class="mc-t">Percentage points</div>
            <p class="mc-p">A percentage-point difference is the subtraction
            of two percentages.</p></div>
          <div class="mcard"><div class="mc-ic">↔</div>
            <div class="mc-t">Gap is not spread</div>
            <p class="mc-p">A district's gap from the national estimate is not
            the same as the spread between the highest and lowest districts.</p></div>
          <div class="mcard"><div class="mc-ic">≈</div>
            <div class="mc-t">Descriptive only</div>
            <p class="mc-p">Comparisons are descriptive and do not establish
            why a difference exists.</p></div>
        </div>
        """
    )

    # ---- 5. Priority scoring -------------------------------------------------
    _section("sec-scoring", 5, "Priority Explorer scoring",
             "An exploratory screening score built from three components.")
    render_html(
        """
        <div class="pipe">
          <div class="step"><div class="step-n">1</div><div class="mc-t">Measure the gap</div>
            <p class="mc-p">Compare each district with the national estimate, in the
            direction that signals a need. Only positive gaps count.</p></div>
          <div class="step"><div class="step-n">2</div><div class="mc-t">Normalize</div>
            <p class="mc-p">Scale each positive gap against the largest observed
            positive gap for that indicator in the district dataset.</p></div>
          <div class="step"><div class="step-n">3</div><div class="mc-t">Average</div>
            <p class="mc-p">The three normalized components receive equal weight
            in the overall score.</p></div>
          <div class="step"><div class="step-n">4</div><div class="mc-t">Read it relatively</div>
            <p class="mc-p">The result is a comparative score within this dataset,
            not an absolute measure.</p></div>
        </div>
        """
    )

    st.markdown("")
    bank = INDICATOR_THEME["Owns a bank account (%)"]["accent"]
    mobile = INDICATOR_THEME["Registered mobile-money user (%)"]["accent"]
    save = INDICATOR_THEME["Does not save (%)"]["accent"]
    borrow = INDICATOR_THEME["Borrowed in the past 12 months (%)"]["accent"]
    render_html(
        f"""
        <div class="mgrid">
          <div class="mcard" style="--accent:{bank}"><div class="mc-t"><i></i>Bank-account ownership</div>
            <p class="mc-p">Lower bank-account ownership than the national estimate.</p></div>
          <div class="mcard" style="--accent:{mobile}"><div class="mc-t"><i></i>Mobile-money registration</div>
            <p class="mc-p">Lower mobile-money registration than the national estimate.</p></div>
          <div class="mcard" style="--accent:{save}"><div class="mc-t"><i></i>Not saving</div>
            <p class="mc-p">A higher share of respondents who do not save than the
            national estimate.</p></div>
          <div class="mcard" style="--accent:{borrow}"><div class="mc-t"><i></i>Borrowing (not scored)</div>
            <p class="mc-p">Displayed as supporting evidence rather than being
            treated as inherently positive or negative.</p></div>
        </div>
        """
    )

    st.markdown("")
    note(
        "A relative screening measure",
        "The priority score is an exploratory, relative screening measure. "
        "It is not an official poverty index, a probability, or a measure of "
        "the number of people in need.",
        tone="warn",
    )

    # ---- 6. Limitations --------------------------------------------------------
    _section("sec-limits", 6, "Limitations",
             "What these results cannot tell you.")
    limitations = [
        ("Not a live picture", "FinScope 2024 does not provide a live picture of financial inclusion."),
        ("Survey uncertainty", "Survey estimates may be affected by sampling and measurement uncertainty."),
        ("No significance testing", "The available dataset does not currently provide the full survey-design "
         "information needed for design-correct confidence intervals and statistical-significance testing."),
        ("Smaller samples", "District estimates can be less stable when based on fewer respondents."),
        ("No causation", "Differences between groups do not establish causation."),
        ("External data", "External indicators, if added later, must have their own dates, sources, "
         "geographic coverage, and definitions documented."),
    ]
    cards = "".join(
        f"""
        <div class="mcard"><div class="mc-ic warn">!</div>
          <div class="mc-t">{esc(title)}</div><p class="mc-p">{esc(text)}</p></div>
        """
        for title, text in limitations
    )
    render_html(f'<div class="mgrid">{cards}</div>')

    # ---- 7. Sources --------------------------------------------------------------
    _section("sec-sources", 7, "Sources and reproducibility",
             "Where the processed outputs and the original data live.")
    with st.container(key="card_method_sources"):
        render_html(
            """
            <p class="mc-p" style="font-size:15px">The current processed outputs
            are stored in <span class="code" style="margin:0">data/processed/</span>,
            while the original survey file is stored in
            <span class="code" style="margin:0">data/datasets/</span>.</p>
            <div class="ct" style="font-size:17px;margin:18px 0 10px">Relevant project artifacts</div>
            """
        )
        files = [
            "national_financial_inclusion.csv",
            "district_financial_inclusion.csv",
            "district_gap_indicators.csv",
            "population_group_indicators.csv",
            "indicator_definitions.csv",
        ]
        rows = "".join(
            f'<div class="file"><span class="file-ic">CSV</span><span class="file-n">{esc(f)}</span></div>'
            for f in files
        )
        rows += (
            '<div class="file"><span class="file-ic nb">NB</span>'
            '<span class="file-n">Exploratory analysis and indicator-analysis notebooks</span></div>'
        )
        render_html(f'<div class="mgrid">{rows}</div>')