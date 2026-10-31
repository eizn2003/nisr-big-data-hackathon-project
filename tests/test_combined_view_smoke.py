"""AppTest smoke tests: real page files, synthetic data (see smoke_stubs)."""
import sys
from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest

ROOT = str(Path(__file__).resolve().parents[1])
PAGES = {
    "national": ("src.pages.combine-view.national_overview", "render_national_overview"),
    "district": ("src.pages.combine-view.district_explorer", "render_district_explorer"),
    "population": ("src.pages.combine-view.population_groups", "render_population_groups"),
    "priority": ("src.pages.combine-view.priority_explorer", "render_priority_explorer"),
    "methodology": ("src.pages.combine-view.methodology", "render_methodology"),
    "policy": ("src.pages.combine-view.policy_alignment", "render_policy_alignment"),
}

def _script(module, func):
    return f'''
import sys
sys.path.insert(0, r"{ROOT}"); sys.path.insert(0, r"{ROOT}/tests")
import importlib
for k in [k for k in list(sys.modules) if k == "src" or k.startswith("src.")]: del sys.modules[k]
import smoke_stubs; smoke_stubs.install()
page = importlib.import_module("{module}")
page.{func}()
'''

def run(page, mode, setup=None):
    module, func = PAGES[page]
    at = AppTest.from_string(_script(module, func), default_timeout=60)
    at.session_state["global_dashboard_mode"] = mode
    if setup: setup(at)
    at.run()
    return at

def text(at):
    parts = [m.value for m in at.markdown] + [c.value for c in at.caption] + [w.value for w in at.warning] + [i.value for i in at.info]
    return "\n".join(parts)

@pytest.mark.parametrize("page", list(PAGES))
@pytest.mark.parametrize("mode", ["Combined", "FinScope"])
def test_page_renders_without_exception(page, mode):
    at = run(page, mode)
    assert not at.exception, [e.value for e in at.exception]


def test_app_routes_each_mode_to_the_matching_page_package():
    source = (Path(ROOT) / "app.py").read_text()
    source = source.replace(
        "from src.auth import render_access_gate",
        "render_access_gate = lambda: True",
    )
    source = source.replace(
        "from src.pages.nbr_dashboard import render_mode_selector",
        "render_mode_selector = lambda: st.session_state.setdefault("
        "'global_dashboard_mode', 'Combined')",
    )
    source = source.replace(
        "    from src.pages.nbr_dashboard import current_mode",
        "    current_mode = lambda: st.session_state.get("
        "'global_dashboard_mode', 'Combined')",
    )
    source = source.replace(
        "def render_selected_page(page):",
        """import types

def _record_module_import(name):
    st.session_state["resolved_page_module"] = name
    module_name = name.rsplit(".", 1)[-1]
    renderer_name = next(
        renderer for registered_module, renderer in PAGE_MODULES.values()
        if registered_module == module_name
    )
    return types.SimpleNamespace(**{renderer_name: lambda: None})

import_module = _record_module_import

def render_selected_page(page):""",
    )
    script = f"import sys; sys.path.insert(0, r'{ROOT}')\n" + source
    at = AppTest.from_string(script, default_timeout=30).run()
    assert not at.exception, [error.value for error in at.exception]
    assert at.session_state["resolved_page_module"] == (
        "src.pages.combine-view.national_overview"
    )

    at.session_state["global_dashboard_mode"] = "FinScope"
    at.run()
    assert not at.exception, [error.value for error in at.exception]
    assert at.session_state["resolved_page_module"] == "src.pages.national_overview"


@pytest.mark.parametrize("page", list(PAGES))
def test_nbr_mode_delegates(page):
    at = run(page, "NBR Supply")
    assert not at.exception
    if page not in ("methodology", "policy"):
        assert "NBR PAGE" in text(at)

@pytest.mark.parametrize("page", list(PAGES))
def test_finscope_mode_has_no_combined_markup(page):
    at = run(page, "FinScope")
    body = text(at)
    for marker in ("cmb-rec", "cmb-three", "Evidence-grounded", "NBR administrative context for these groups"):
        assert marker not in body

def test_national_combined_integrates_headline_and_map_context():
    at = run("national", "Combined")
    body = text(at)
    assert "NBR Total Branches" in body                       # strip inside the KPI card
    assert "What stands out" in body and "Where the gaps are" in body  # FinScope story preserved
    assert "NBR context accompanies" in body

def test_national_indicator_change_does_not_keep_stale_nbr_context():
    at = run("national", "Combined")
    # default indicator is bank account (k1) -> branch markers; switch to one with no counterpart
    pills = [p for p in at.get("button_group") if getattr(p, "key", "") == "overview_district_indicator"] if hasattr(at, "get") else []
    assert pills
    pills[0].set_value("Mobile money").run()
    body = text(at)
    assert not at.exception
    assert "Where to look next" in body
    assert "NBR observations behind the map markers" not in "\n".join(e.label for e in at.expander)

def test_district_combined_missing_district_is_explicit():
    def setup(at): at.session_state["dx_district"] = NAMES_LAST
    at = run("district", "Combined", setup)
    body = text(at)
    assert not at.exception
    assert "no observation" in body.lower()
    assert "Missing is not zero" in body

def test_district_combined_available_district_has_recommendations():
    def setup(at): at.session_state["dx_district"] = "District 01"
    at = run("district", "Combined", setup)
    body = text(at)
    assert "Next steps for District 01" in body and "Re-check" in body or "reporting date" in body

def test_population_gender_partial_nbr_coverage():
    # SYNTHETIC fixture: "Doesn't save" is given a gender-capable (Savings) page so the partial path runs.
    def setup(at): at.session_state["population_groups_indicator"] = "Doesn't save"
    at = run("population", "Combined", setup)
    body = text(at)
    assert not at.exception
    assert "NBR administrative context for these groups" in body
    assert "No NBR observation" in body            # Male has no exact-gender series
    assert "Verify data" in body

def test_population_gender_is_scope_unsupported_where_the_nbr_page_has_no_gender_filter():
    at = run("population", "Combined")             # bank account -> Branches page: no Gender breakdown
    body = text(at)
    assert not at.exception
    assert "has no Gender breakdown" in body
    assert "No NBR observation" not in body        # unsupported scope is not a missing observation

@pytest.mark.parametrize("group", ["Age group", "Education", "Area"])
def test_population_unsupported_dimensions(group):
    def setup(at): at.session_state["population_groups_type"] = group
    at = run("population", "Combined", setup)
    assert not at.exception
    assert "NBR does not cover this dimension" in text(at)

def test_priority_combined_explains_missing_counterparts_and_keeps_score_separate():
    at = run("priority", "Combined")
    body = text(at)
    assert not at.exception
    assert "NBR evidence (not scored)" in body
    assert "No NBR counterpart" in body or "NBR does not cover" in body
    assert "does not change the score" in body

def test_methodology_combined_adds_section_and_mapping():
    at = run("methodology", "Combined")
    assert not at.exception
    assert "Using both sources" in text(at)
    assert any("Contextual" in str(df.value.to_dict()) for df in at.dataframe)
    assert "Using both sources" not in text(run("methodology", "FinScope"))

def test_policy_combined_adds_nbr_context_and_gap_action():
    at = run("policy", "Combined")
    body = text(at)
    assert not at.exception
    assert "Verify administrative coverage" in body
    assert "Administrative context" in body
    assert "Verify administrative coverage" not in text(run("policy", "FinScope"))

NAMES_LAST = "District 29"


def _select(at, label):
    boxes = [b for b in at.selectbox if b.label == label]
    return boxes[0] if boxes else None

def test_national_nbr_reporting_date_drives_markers_and_resets_with_the_indicator():
    at = run("national", "Combined")
    box = _select(at, "NBR reporting date")
    assert box is not None and list(box.options) == ["2026-10-24", "2026-06-30"]
    box.select("2026-06-30").run()
    assert not at.exception
    dates = {str(v) for df in at.dataframe for v in df.value.get("Reporting date", [])}
    assert "2026-06-30" in dates and "2026-10-24" not in dates
    # a different indicator has its own series and its own control: nothing carries over
    pills = [p for p in at.get("button_group") if getattr(p, "key", "") == "overview_district_indicator"]
    pills[0].set_value("Mobile money").run()
    assert not at.exception and _select(at, "NBR reporting date") is None

def test_district_reporting_date_and_indicator_change_update_the_evidence():
    at = run("district", "Combined")
    box = _select(at, "NBR reporting date for map markers")
    assert box is not None
    box.select("2026-06-30").run()
    assert not at.exception and "2026-06-30" in text(at)
    def setup(at2): at2.session_state["dx_indicator"] = "Mobile money"
    at2 = run("district", "Combined", setup)
    assert _select(at2, "NBR reporting date for map markers") is None
    assert "not approved" in text(at2).lower() or "NBR series not approved" in text(at2)

def test_suppressed_series_is_reported_as_suppressed_everywhere_it_appears():
    def setup(at): at.session_state["dx_indicator"] = "Group saving"
    at = run("district", "Combined", setup)
    body = text(at)
    assert not at.exception
    assert "intentionally not shown" in body.lower()
    assert "No NBR observation" not in body and "Missing is not zero" not in body
    nat = text(run("national", "Combined"))
    assert "intentionally not shown" in nat.lower()           # national saving-context block

def test_failed_nbr_read_is_not_presented_as_absence():
    def setup(at): at.session_state["_stub_fail_vars"] = ["k1"]
    at = run("national", "Combined", setup)
    body = text(at)
    assert not at.exception
    assert "Bank account: NBR context unavailable" in body      # the failed indicator, named
    assert "Bank account: no nbr" not in body.lower()           # not reported as absence
    assert "no approved counterpart" not in body.lower()

def test_routed_question_limitation_is_stated_beside_the_estimate():
    def setup(at): at.session_state["dx_indicator"] = "SACCO"
    assert "not a confirmed non-use rate" in text(run("district", "Combined", setup))
    assert "not a confirmed non-use rate" in text(run("national", "Combined"))

def test_priority_score_stays_finscope_only_and_names_suppressed_context():
    body = text(run("priority", "Combined"))
    assert "does not change the score" in body and "NBR evidence (not scored)" in body

def test_methodology_lists_all_eight_classifications_and_the_routed_card():
    at = run("methodology", "Combined")
    body = text(at)
    assert not at.exception
    for label in ("Intentionally suppressed", "Data-loading failure", "Supported, no matching observation",
                  "Uncertain or unapproved relationship", "Unsupported dimension or level"):
        assert label in body
    assert "Questions with routed or missing answers" in body
    assert "Contextual, intentionally suppressed" in str([df.value.to_dict() for df in at.dataframe])

def _chart_keys(at):
    keys = []
    def walk(node):
        for child in getattr(node, "children", {}).values():
            if getattr(child, "type", "") == "plotly_chart":
                keys.append(str(getattr(child, "key", "") or ""))
            walk(child)
    walk(at.main)
    return keys

def test_combined_pages_reuse_a_single_map_and_never_add_one_elsewhere():
    def maps(page):
        return [k for k in _chart_keys(run(page, "Combined")) if "map" in k]
    assert len(maps("national")) == 1 and len(maps("district")) == 1   # one shared map, markers overlaid
    assert maps("population") == [] and maps("priority") == []