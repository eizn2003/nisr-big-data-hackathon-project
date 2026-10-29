import sys, textwrap
from streamlit.testing.v1 import AppTest
tree = sys.argv[1]
PRE = f"""
import sys; sys.path.insert(0, {tree!r}); sys.path.insert(0, '/home/claude/harness')
import streamlit as st
import synth
import src.nbr_dashboard as nd
from src.models.nbr_intelligence.indicator_mapping import MAPPING_BY_VARIABLE
from src.nbr_dashboard import build_nbr_indicator_registry
def _load(model_version, pages=None):
    pts = [p for p in synth.points() if pages is None or p["page"] in pages]
    return pts, {{"eligible_source_point_count": len(pts)}}, build_nbr_indicator_registry(pts), "snap"
nd.load_nbr_dashboard_data = _load
"""
results = []
def check(name, ok, detail=""):
    results.append(ok); print(("PASS" if ok else "FAIL"), name, detail)

def app(body):
    at = AppTest.from_string(PRE + textwrap.dedent(body), default_timeout=30)
    return at.run()

# 1 default mode
at = app("""
print_mode = nd.current_mode()
nd.render_mode_selector()
st.write("MODE=" + print_mode)
""")
check("default mode is Combined", any("MODE=Combined" in m.value for m in at.markdown) and not at.exception, str(at.exception))
at.button(key="dashboard_mode_nbr_supply").click().run()
check("mode switch to NBR Supply works", at.session_state["global_dashboard_mode"] == "NBR Supply")

# 2 NBR district page renders (no boundary file -> map-error path)
for view in ("district", "priority"):
    at = app(f"""
st.session_state["global_dashboard_mode"] = "NBR Supply"
st.session_state["nbr_source_page_district"] = "Inclusion"
st.session_state["nbr_source_page_priority"] = "Inclusion"
nd.render_nbr_page("{view}", selected_district="Gasabo")
""")
    check(f"NBR {view} page renders without exception", not at.exception, "; ".join(e.message for e in at.exception))
    html = " ".join(m.value for m in at.markdown)
    check(f"NBR {view}: sparkline inside KPI", "<svg" in html and "polyline" in html)
    check(f"NBR {view}: no run/record ids or snapshot hash on page",
          "Run ID" not in html and "Source record ID" not in html and "snap" not in " ".join(c.value for c in at.caption))

# 3 map click handoff in NBR district view
at = app("""
st.session_state["global_dashboard_mode"] = "NBR Supply"
st.session_state["nbr_source_page_district"] = "Inclusion"
st.session_state["nbr_source_page_priority"] = "Inclusion"
nd.render_nbr_page("district", selected_district="Gasabo")
""")
key = [k for k in list(at.session_state.keys()) if k.startswith("nbr_district_selected_")]
before = at.session_state[key[0]] if key else None
at.session_state["_nbr_dx_pending_district"] = "Kicukiro"
at.run()
after = at.session_state[key[0]] if key else None
check("pending map click selects the district", after == "Kicukiro" and not at.exception, f"{before}->{after} {[e.message for e in at.exception]}")

# 4 priority review panel (nested expander)
at = app("""
import src.nbr_dashboard as nd
nd.load_nbr_review_candidates = lambda v, pages: ([{"method": "robust_zscore", "district": "Gasabo", "page": "inclusion",
    "metric_label": "Bank customers", "filters": {}, "reporting_date": "2024-Q4", "observed_value": 121000, "direction": "up",
    "evidence_assessment": {"state": "needs_review"}, "quality_qualifications": ["Short history"], "score": 3.2,
    "threshold": 2.5, "run_id": "r1", "method_specific_rank": 1, "reason": "Jump vs history"}],
    {"assessment_id": "A1", "assessment_timestamp": "2026-10-01", "model_version": "m", "source_git_commit": "abc", "pages": ["inclusion"]})
nd.render_nbr_page("priority", selected_district="Gasabo")
""")
for b in at.button:
    if (b.label or "").startswith("Load review candidates"):
        b.click()
at.run()
check("review candidates panel renders", not at.exception, "; ".join(e.message for e in at.exception))

# 5 Combined strip + helpers
at = app("""
html = nd.combined_strip_html("k1", scope="National")
st.session_state["strip"] = html
st.session_state["strip_d"] = nd.combined_strip_html("k1", district="Gasabo", show_limitations=True)
st.session_state["strip_none"] = nd.combined_strip_html("zz")
st.session_state["fmt"] = [nd.fmt_value(1234567), nd.fmt_value(0.52341), nd.fmt_value(12.3456), nd.fmt_delta(-85000)]
""")
strip, strip_d, none = at.session_state["strip"], at.session_state["strip_d"], at.session_state["strip_none"]
check("national strip has value, unit, svg, no percent sign", "1,455,000" in strip and "customers" in strip and "<svg" in strip and "%" not in strip.replace("100%",""), strip[:200])
check("district strip shows limitation text visibly", "not an ownership percentage" in strip_d)
check("unmapped indicator gives no strip", none == "")
check("number formats", at.session_state["fmt"] == ["1,234,567", "0.5234", "12.35", "-85,000"], str(at.session_state["fmt"]))

# 6 click resolution
at = app("""
from src.pages.district_explorer import _clicked_district
names = ["Gasabo", "Kicukiro"]
st.session_state["r"] = [
  _clicked_district({"selection": {"points": [{"curve_number": 0, "location": "Gasabo"}]}}, names),
  _clicked_district({"selection": {"points": [{"curve_number": 1, "customdata": ["m", "1", "u", "d", "Kicukiro"]}]}}, names),
  _clicked_district({"selection": {"points": [{"curve_number": 1, "text": "Kicukiro"}]}}, names),
  _clicked_district({"selection": {"points": [{"curve_number": 1, "text": "Nowhere"}]}}, names),
  _clicked_district(None, names)]
""")
check("clicks resolve for districts and NBR markers", at.session_state["r"] == ["Gasabo", "Kicukiro", "Kicukiro", None, None], str(at.session_state["r"]))

# 7 national overview KPI html
at = app("""
from src.pages import national_overview as no
import pandas as pd
nat = pd.DataFrame({"Indicator": ["Own bank account"], "Estimate (%)": [53.2]})
strip, entry = nd.combined_strip("k1", scope="National")
st.session_state["k"] = no._kpi_html(nat, {"k1": strip})
st.session_state["k0"] = no._kpi_html(nat)
""")
k, k0 = at.session_state["k"], at.session_state["k0"]
check("national KPI: FinScope value primary, NBR strip inside card, no source variable text",
      "53.2" in k and "nbr-ctx" in k and "Source variable" not in k and k.count('class="kpi"') == 1)
check("national KPI without context is clean", "nbr-ctx" not in k0 and "53.2" in k0)

# 8 build_map with markers
at = app("""
import pandas as pd
from src.pages.district_explorer import build_map
gj = {"type":"FeatureCollection","features":[{"type":"Feature","properties":{"shapeName":n},"geometry":{"type":"Polygon","coordinates":[[[29,-2],[30,-2],[30,-1],[29,-2]]]}} for n in synth.DISTRICTS]}
centers = {n:(-1.9+i*.1, 29.9) for i,n in enumerate(synth.DISTRICTS)}
df = pd.DataFrame({"District": synth.DISTRICTS, "m":[40.,50.,60.], "rank":[3,2,1], "diff":[-1,0,1], "Valid respondents":[100,100,100]})
pts = [p for p in synth.points() if p["geography_level"]=="district" and p["reporting_date"]=="2024-Q4"]
cfg = {"scale":"Teal","accent":"#1A8A7D","title":"Bank"}
settings = dict(basemap="Light", palette="Indicator colours", opacity=.85, spotlight="Off", labels=False, tilt=0, rotation=0, zoom=7)
fig = build_map(df, gj, centers, (-1.9, 29.9), cfg, "m", 50.0, "Gasabo", "Bank", settings, supply_points=pts)
st.session_state["n"] = len(fig.data)
st.session_state["hover"] = fig.data[1].hovertemplate
st.session_state["cd"] = fig.data[1].customdata[0][-1]
""")
check("combined map: one choropleth + one marker trace, marker hover readable", at.session_state["n"] == 2 and "4g" not in at.session_state["hover"] and at.session_state["cd"] in ("Gasabo","Kicukiro","Nyarugenge"), at.session_state["hover"][:90] if not at.exception else str(at.exception))

# 9 other modes' methodology notes
at = app("""
st.session_state["global_dashboard_mode"] = "NBR Supply"
st.session_state["nbr_source_page_district"] = "Inclusion"
st.session_state["nbr_source_page_priority"] = "Inclusion"
nd.render_methodology_mode_note()
""")
check("methodology note renders in NBR mode", not at.exception, "; ".join(e.message for e in at.exception))
print(f"\n{sum(results)}/{len(results)} passed")
