"""Offline tests for nbr_engine.py.

Static tests need nothing. Browser tests drive a LOCAL MOCK dashboard (built from the CSS selectors in
the supplied scripts) with real Playwright + Chromium, and persist to an in-memory MongoDB (mongomock).
They prove the engine's logic; they do NOT prove the live fininclusion.bnr.rw markup behaves the same.

    pip install pytest mongomock
    pytest test_nbr_engine.py -v
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import mongomock
import pytest

import src.scrapers.nbr_engine as engine
import src.scrapers.scrape_nbr_backfill as scrape_nbr_backfill
import src.scrapers.scrape_nbr_current as scrape_nbr_current

HERE = Path(__file__).resolve().parent

# ------------------------------------------------------------------
# Mock dashboard
# ------------------------------------------------------------------

MOCK_HTML = r"""<!doctype html><html><head><meta charset="utf-8"><title>mock</title></head><body>
<div class="modal show" role="dialog" id="disc"><button id="close-disclaimer">Thanks!</button></div>
<div id="filters"></div>
<div id="datewrap"></div>
<div id="updating" style="display:none">Updating...</div>
<div id="kpis"></div>
<div id="plotwrap"></div>
<div id="viewwrap"></div>
<div id="tablewrap"></div>
<script>
const PAGES = {
  cards: ['Gender','Age Segment','Institution Type','Card Status','Card Product','Card Type','Location'],
  branches: ['Institution Type','Branch Status','Location'],
  swapped: ['Location','Card Type','Gender','Age Segment','Institution Type','Card Status','Card Product'],
  extra: ['Institution Type','Branch Status','Location','Surprise Filter'],
  nodate: ['Alpha'], notable: ['Alpha'], nochart: ['Alpha'], unverified: ['Alpha','Beta'],
};
const OPTIONS = {Gender:['All','Female','Male'], 'Age Segment':['All','Youth','Non-Youth'],
                 Location:['All','Kigali','North']};
const pageId = location.pathname.split('/').filter(Boolean).pop();
const labels = PAGES[pageId] || ['Alpha'];
const hasDate = pageId !== 'nodate', hasTable = pageId !== 'notable', hasChart = pageId !== 'nochart';
const state = {date: '2026-10-20', filters: {}, pageIdx: 0, tableOpen: false, openMenu: null};
labels.forEach(l => state.filters[l] = 'All');
const ROWS_PER_PAGE = 3, DISTRICTS = ['Gasabo','Kicukiro','Nyarugenge','Musanze','Huye','Rubavu','Unknown'];

function hsh(s){let h=7;for(const c of s){h=(h*31+c.charCodeAt(0))%1000003;}return h;}
function key(){return state.date+'|'+Object.keys(state.filters).sort().map(k=>k+'='+state.filters[k]).join(';');}
function tableRows(){
  const k = key();
  const rows = DISTRICTS.map(n => ({n, c: 100 + hsh(k+'|'+n)%900}));
  rows.sort((a,b)=> b.c-a.c || a.n.localeCompare(b.n));
  return rows.map((r,i)=>({n:r.n, c:r.c, rank:i+1}));
}
function update(){
  const u = document.getElementById('updating'); u.style.display='block';
  setTimeout(()=>{ render(); u.style.display='none'; }, 300);
}
function render(){
  const k = key();
  document.getElementById('kpis').innerHTML =
    card('Total Customers', (1000 + hsh(k)%9000).toLocaleString('en-US')) +
    card('Active Share', (20 + (hsh(k+'a')%600)/10).toFixed(1) + '%') +
    card('Touchpoints', String(50 + hsh(k+'b')%50));
  if (hasChart) {
    const m = 40 + hsh(k+'g')%21;
    document.getElementById('plotwrap').innerHTML = '<div class="js-plotly-plot" id="plot"></div>';
    document.getElementById('plot').data = [{type:'pie', labels:['Male','Female'], values:[m, 100-m]}];
  }
  if (hasTable) {
    document.getElementById('viewwrap').innerHTML = state.tableOpen ? '' : '<a id="viewbtn" href="#">Click to view Table</a>';
    const vb = document.getElementById('viewbtn');
    if (vb) vb.onclick = (e)=>{e.preventDefault(); state.tableOpen=true; render();};
    if (state.tableOpen) {
      const rows = tableRows(); const pages = Math.ceil(rows.length/ROWS_PER_PAGE);
      state.pageIdx = Math.min(state.pageIdx, pages-1);
      const slice = rows.slice(state.pageIdx*ROWS_PER_PAGE, (state.pageIdx+1)*ROWS_PER_PAGE);
      document.getElementById('tablewrap').innerHTML =
        '<table class="cell-table"><thead><tr><th>District</th><th>Customers</th><th>Rank</th></tr></thead><tbody>' +
        slice.map(r=>`<tr><td>${r.n}</td><td>${r.c}</td><td>${r.rank}</td></tr>`).join('') + '</tbody></table>' +
        `<button class="first-page" ${state.pageIdx===0?'disabled':''}>first</button>` +
        `<button class="next-page" ${state.pageIdx>=pages-1?'disabled':''}>next</button>`;
      document.querySelector('.first-page').onclick = ()=>{state.pageIdx=0; render();};
      document.querySelector('.next-page').onclick = ()=>{state.pageIdx++; render();};
    }
  }
}
function card(title, value){
  return `<div class="custom-card-margin card"><div class="card-body"><h4 class="card-title small-text">${title}</h4>` +
         `<p class="card-text large-data">${value}</p></div></div>`;
}
function renderFilters(){
  const wrap = document.getElementById('filters'); wrap.innerHTML = '';
  labels.forEach(label => {
    const opts = OPTIONS[label] || ['All','One','Two'];
    const div = document.createElement('div');
    div.className = label === 'Location' ? 'location-dropdown-card' : 'dropdown-card';
    div.innerHTML = `<div class="dropdown-card-header">${label}</div><div class="Select"><div class="Select-control">` +
      `<span class="Select-value-label">${state.filters[label]}</span><input role="combobox" aria-expanded="false"></div></div>`;
    const control = div.querySelector('.Select-control');
    control.onclick = () => {
      const open = div.querySelector('.Select-menu');
      document.querySelectorAll('.Select-menu').forEach(m => m.remove());
      if (open) return;
      const menu = document.createElement('div'); menu.className = 'Select-menu';
      opts.forEach(o => {
        const d = document.createElement('div'); d.className = 'VirtualizedSelectOption'; d.textContent = o;
        d.onclick = (ev) => { ev.stopPropagation(); state.filters[label] = o; menu.remove();
                              div.querySelector('.Select-value-label').textContent = o; update(); };
        menu.appendChild(d);
      });
      div.querySelector('.Select').appendChild(menu);
    };
    wrap.appendChild(div);
  });
}
document.addEventListener('keydown', e => { if (e.key === 'Escape') document.querySelectorAll('.Select-menu').forEach(m => m.remove()); });
if (hasDate) {
  document.getElementById('datewrap').innerHTML = '<input id="date" type="text" value="2026-10-20">';
  const input = document.getElementById('date');
  input.addEventListener('keydown', e => {
    if (e.key !== 'Enter') return;
    if (/^\d{4}-\d{2}-\d{2}$/.test(input.value) && input.value >= '2025-01-01') { state.date = input.value; update(); }
    else input.value = state.date;  // dashboard rejects out-of-range dates
  });
}
document.getElementById('close-disclaimer').onclick = () => document.getElementById('disc').remove();
renderFilters(); render();
</script></body></html>"""


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # same page for every path; JS reads the path
        body = MOCK_HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture(scope="session")
def mock_base():
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def _hsh(s: str) -> int:
    h = 7
    for c in s:
        h = (h * 31 + ord(c)) % 1000003
    return h


def expected_key(snapshot_date: str, filters: dict) -> str:
    return snapshot_date + "|" + ";".join(f"{k}={filters[k]}" for k in sorted(filters))


def expected_total(snapshot_date: str, filters: dict) -> str:
    return f"{1000 + _hsh(expected_key(snapshot_date, filters)) % 9000:,}"


def expected_male(snapshot_date: str, filters: dict) -> float:
    total = 100.0
    male = 40 + _hsh(expected_key(snapshot_date, filters) + "g") % 21
    return round(male / total * 100, 1)


CARD_LABELS = [
    "Gender",
    "Age Segment",
    "Institution Type",
    "Card Status",
    "Card Product",
    "Card Type",
    "Location",
]


@pytest.fixture()
def config_path(tmp_path, mock_base):
    cfg = {
        "defaults": {"gender_distribution": True, "date_selector": "#date"},
        "pages": {
            # Iterates Gender x Age Segment (2x2) and only reads the rest.
            "cards": {
                "url": f"{mock_base}/touchpoints/cards",
                "filters": [
                    {"label": "Gender", "options": ["All", "Female"]},
                    {"label": "Age Segment", "options": ["All", "Youth"]},
                    "Institution Type",
                    "Card Status",
                    "Card Product",
                    "Card Type",
                    "Location",
                ],
            },
            "branches": {
                "url": f"{mock_base}/touchpoints/branches",
                "filters": ["Institution Type", "Branch Status", "Location"],
            },
            # Same labels as cards but the dashboard shows them in a different order.
            "swapped": {
                "url": f"{mock_base}/touchpoints/swapped",
                "filters": [
                    {"label": "Gender", "options": ["Female"]},
                    *CARD_LABELS[1:],
                ],
            },
            "extra": {
                "url": f"{mock_base}/touchpoints/extra",
                "filters": ["Institution Type", "Branch Status", "Location"],
            },
            "missing": {
                "url": f"{mock_base}/touchpoints/branches",
                "filters": [
                    "Institution Type",
                    "Branch Status",
                    "Location",
                    "Does Not Exist",
                ],
            },
            "nodate": {"url": f"{mock_base}/touchpoints/nodate", "filters": ["Alpha"]},
            "notable": {
                "url": f"{mock_base}/touchpoints/notable",
                "filters": ["Alpha"],
            },
            "nochart": {
                "url": f"{mock_base}/touchpoints/nochart",
                "filters": ["Alpha"],
            },
            "unverified": {"url": f"{mock_base}/touchpoints/unverified"},
            "legacy": {
                "url": f"{mock_base}/inclusion",
                "handled_by": "backfill_nbr_inclusion_history.py",
            },
        },
    }
    path = tmp_path / "pages.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    return path


@pytest.fixture()
def store():
    db = mongomock.MongoClient()["test_nbr"]
    s = engine.Store(tables=db["tables"], kpis=db["kpis"], runs=db["runs"])
    engine.ensure_indexes(s)
    return s


@pytest.fixture()
def fast(monkeypatch, tmp_path):
    """Keep the real logic, shorten waits that only exist to be patient."""
    monkeypatch.setattr(engine, "DATE_STABLE_CHECKS", 2)
    monkeypatch.setattr(engine, "GENDER_WAIT_MS", 2500)
    monkeypatch.setattr(engine, "SHORT_WAIT_MS", 1000)
    monkeypatch.setattr(engine, "retry_pause", lambda attempt: None)
    monkeypatch.setattr(engine, "OUTPUT_DIR", tmp_path / "out")


def dates_file(tmp_path, *lines):
    path = tmp_path / "dates.txt"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# ------------------------------------------------------------------
# STATIC TESTS: configuration, structure, persistence rules
# ------------------------------------------------------------------

EXPECTED_URLS = {
    "agents": "https://fininclusion.bnr.rw/touchpoints/agents",
    "branches": "https://fininclusion.bnr.rw/touchpoints/branches",
    "cards": "https://fininclusion.bnr.rw/touchpoints/cards",
    "internet_banking": "https://fininclusion.bnr.rw/touchpoints/internet_banking",
    "merchants": "https://fininclusion.bnr.rw/touchpoints/merchants",
    "mobile_banking": "https://fininclusion.bnr.rw/touchpoints/mobile_banking",
    "pos": "https://fininclusion.bnr.rw/touchpoints/pos",
    "transactional": "https://fininclusion.bnr.rw/transactional",
    "depositors": "https://fininclusion.bnr.rw/depositors",
    "savings": "https://fininclusion.bnr.rw/savings",
    "credit": "https://fininclusion.bnr.rw/credit",
    "insurance": "https://fininclusion.bnr.rw/insurance",
}


def test_config_has_every_page_with_the_exact_urls():
    configs = engine.load_config(HERE / "nbr_pages.json")
    for page_id, url in EXPECTED_URLS.items():
        assert configs[page_id].url == url
    assert configs["inclusion"].handled_by == "backfill_nbr_inclusion_history.py"


def test_cards_and_branches_filter_labels_are_exact():
    configs = engine.load_config(HERE / "nbr_pages.json")
    assert [f.label for f in configs["cards"].filters] == [
        "Gender",
        "Age Segment",
        "Institution Type",
        "Card Status",
        "Card Product",
        "Card Type",
        "Location",
    ]
    assert [f.label for f in configs["branches"].filters] == [
        "Institution Type",
        "Branch Status",
        "Location",
    ]


def test_unverified_pages_do_not_invent_filter_lists():
    configs = engine.load_config(HERE / "nbr_pages.json")
    for page_id in ("agents", "pos", "transactional", "insurance"):
        assert configs[page_id].filters is None


def test_no_page_specifics_hardcoded_in_python():
    for name in ("nbr_engine.py", "scrape_nbr_backfill.py", "scrape_nbr_current.py"):
        source = (HERE / name).read_text(encoding="utf-8")
        for needle in (
            "bnr.rw/",
            "touchpoints",
            "Age Segment",
            "Card Status",
            "Branch Status",
            "Institution Type",
        ):
            assert needle not in source, f"{needle!r} hardcoded in {name}"


def test_both_entry_points_are_thin_wrappers_over_the_same_engine():
    assert scrape_nbr_backfill.run_cli is engine.run_cli
    assert scrape_nbr_current.run_cli is engine.run_cli
    for name in ("scrape_nbr_backfill.py", "scrape_nbr_current.py"):
        assert len((HERE / name).read_text().splitlines()) < 25


def test_config_errors_are_clear(tmp_path):
    empty = tmp_path / "empty.json"
    empty.write_text("")
    with pytest.raises(engine.ConfigError, match="empty"):
        engine.load_config(empty)
    bad = tmp_path / "bad.json"
    bad.write_text("{nope")
    with pytest.raises(engine.ConfigError, match="not valid JSON"):
        engine.load_config(bad)
    dup = tmp_path / "dup.json"
    dup.write_text(
        json.dumps({"pages": {"p": {"url": "https://x.y/p", "filters": ["A", "a"]}}})
    )
    with pytest.raises(engine.ConfigError, match="more than once"):
        engine.load_config(dup)
    both = tmp_path / "both.json"
    both.write_text(
        json.dumps(
            {
                "pages": {
                    "p": {
                        "url": "https://x.y/p",
                        "filters": [{"label": "A", "options": ["x"], "fixed": "x"}],
                    }
                }
            }
        )
    )
    with pytest.raises(engine.ConfigError, match="either"):
        engine.load_config(both)


def test_the_uploaded_empty_pages_file_is_reported_not_silently_accepted():
    uploaded = Path("/mnt/user-data/uploads/nbr_pages.json")
    if not uploaded.exists():
        pytest.skip("uploaded file not present")
    with pytest.raises(engine.ConfigError, match="empty"):
        engine.load_config(uploaded)


def test_page_selection_errors():
    configs = engine.load_config(HERE / "nbr_pages.json")
    with pytest.raises(engine.ConfigError, match="Unknown page"):
        engine.resolve_page_ids(configs, ["nope"], False)
    with pytest.raises(engine.ConfigError, match="not run by the shared engine"):
        engine.resolve_page_ids(configs, ["inclusion"], False)
    with pytest.raises(engine.ConfigError, match="Choose a page"):
        engine.resolve_page_ids(configs, None, False)
    assert engine.resolve_page_ids(configs, ["cards,branches", "cards"], False) == [
        "cards",
        "branches",
    ]
    assert "inclusion" not in engine.resolve_page_ids(configs, None, True)


def test_combinations_iterate_options_and_force_fixed_values():
    cfg = engine.PageConfig(
        "p",
        "https://x.y",
        "p",
        [
            engine.FilterSpec("A", options=("1", "2")),
            engine.FilterSpec("B", options=("x", "y", "z")),
            engine.FilterSpec("L", fixed="All"),
            engine.FilterSpec("R"),
        ],
    )
    combos = engine.build_combinations(cfg)
    assert len(combos) == 6 and all(c["L"] == "All" and "R" not in c for c in combos)
    assert engine.build_combinations(
        engine.PageConfig("q", "https://x.y", "q", None)
    ) == [{}]


def test_the_supplied_dates_file_parses_unchanged():
    dates_path = Path("/mnt/user-data/uploads/nbr_backfill_dates_1.txt")
    if not dates_path.exists():
        pytest.skip("uploaded file not present")
    dates, live = engine.load_dates(dates_path, today="2026-10-25")
    assert (
        len(dates) == 21
        and dates[0] == "2025-02-20"
        and dates[-1] == "2026-10-20"
        and not live
    )


def test_dates_file_validation(tmp_path):
    path = dates_file(
        tmp_path, "2025-02-20", "2025-13-40", "junk", "2099-01-01", "today"
    )
    with pytest.raises(engine.ConfigError, match="not a valid"):
        engine.load_dates(path, today="2026-10-25")
    path = dates_file(
        tmp_path, "2026-10-20", "2026-10-20", "2099-01-01", "today  # live"
    )
    dates, live = engine.load_dates(path, today="2026-10-25")
    assert dates == ["2026-10-20", "2026-10-25"] and live == {"2026-10-25"}


def _save(
    store,
    cfg,
    snapshot_date,
    assignments,
    kpi_value="10",
    rows=None,
    mode="backfill",
    **meta_extra,
):
    meta = {
        "mode": mode,
        "run_id": "r1",
        "date_source": "selected",
        "collected_at": engine.now_local(),
        "dashboard_date": snapshot_date,
        "gender_status": "extracted",
        **meta_extra,
    }
    table = {
        "headers": ["District", "Customers", "Rank"],
        "rows": rows or [["Gasabo", "5", "1"], ["Huye", "3", "2"]],
    }
    kpis = [
        {
            "metric_type": "headline_kpi",
            "metric_label": "Total",
            "metric_value": kpi_value,
            "gender": None,
            "extraction_method": "headline_card",
        },
        {
            "metric_type": "headline_kpi",
            "metric_label": "Total",
            "metric_value": "11",
            "gender": None,
            "extraction_method": "headline_card",
        },
    ]  # same label twice must not collide
    return engine.save_observations(
        store, cfg, snapshot_date, assignments, {"Gender": "All"}, kpis, table, meta
    )


def test_persistence_is_idempotent_and_never_deletes(store):
    cfg = engine.PageConfig("cards", "https://x.y/cards", "Cards", None)
    sentinel = {
        "page": "other_page",
        "snapshot_date": "2020-01-01",
        "combo_key": "{}",
        "row_index": 0,
        "keep": True,
    }
    store.tables.insert_one(dict(sentinel))
    assignments = {"Gender": "All"}
    _save(store, cfg, "2026-01-20", assignments)
    first = (
        store.tables.count_documents({}),
        store.kpis.count_documents({}),
        store.runs.count_documents({}),
    )
    _save(store, cfg, "2026-01-20", assignments)  # rerun
    assert (
        store.tables.count_documents({}),
        store.kpis.count_documents({}),
        store.runs.count_documents({}),
    ) == first
    assert (
        store.tables.count_documents({"page": "cards"}) == 2
        and store.kpis.count_documents({}) == 2
    )
    _save(store, cfg, "2026-02-20", assignments)  # new date adds, never replaces
    assert store.tables.count_documents({"page": "cards"}) == 4
    assert (
        store.tables.find_one({"keep": True}) is not None
    )  # unrelated record untouched
    district = store.tables.find_one({"page": "cards", "row_index": 0})
    assert (
        district["district"] == "Gasabo"
        and district["customers"] == 5
        and district["values"]["Customers"] == "5"
    )


def test_repeated_content_is_flagged_not_dropped(store):
    cfg = engine.PageConfig("cards", "https://x.y/cards", "Cards", None)
    _save(store, cfg, "2026-01-20", {})
    result = _save(store, cfg, "2026-02-20", {})
    assert result["repeated"] and result["previous_date"] == "2026-01-20"
    assert store.runs.count_documents({"status": "complete"}) == 2


def test_observation_date_and_collection_time_are_separate_fields(store):
    cfg = engine.PageConfig("cards", "https://x.y/cards", "Cards", None)
    _save(store, cfg, "2025-02-20", {})
    run = store.runs.find_one({})
    assert (
        run["snapshot_date"] == "2025-02-20"
        and run["run_date"] == run["collected_at"].date().isoformat()
    )
    assert run["snapshot_date"] != run["collected_at"].date().isoformat()
    assert run["dashboard_date"] == "2025-02-20" and run["date_source"] == "selected"


# ------------------------------------------------------------------
# BROWSER TESTS against the mock dashboard
# ------------------------------------------------------------------


@pytest.fixture(scope="session", autouse=True)
def _require_browser():
    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as p:
            p.chromium.launch().close()
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"Chromium unavailable: {exc}", allow_module_level=False)


def run(mode, config_path, store, *extra):
    return engine.run_cli(mode, ["--config", str(config_path), *extra], store=store)


def test_filters_are_matched_by_label_not_position(config_path, store, fast, tmp_path):
    # The 'swapped' dashboard lists Location first. Position-based mapping would change the wrong dropdown.
    code = run(
        "backfill",
        config_path,
        store,
        "--page",
        "swapped",
        "--dates-file",
        str(dates_file(tmp_path, "2026-03-20")),
    )
    assert code == 0
    runs = list(store.runs.find({"page": "swapped", "status": "complete"}))
    assert len(runs) == 1
    assert (
        runs[0]["filters"]["Gender"] == "Female"
        and runs[0]["filters"]["Location"] == "All"
    )
    kpi = store.kpis.find_one({"page": "swapped", "metric_label": "Total Customers"})
    assert kpi["metric_value"] == expected_total(
        "2026-03-20", {l: ("Female" if l == "Gender" else "All") for l in CARD_LABELS}
    )


def test_missing_or_unexpected_filters_are_reported_and_isolated(
    config_path, store, fast, tmp_path, capsys
):
    code = run(
        "backfill",
        config_path,
        store,
        "--page",
        "extra",
        "--page",
        "missing",
        "--page",
        "branches",
        "--dates-file",
        str(dates_file(tmp_path, "2026-03-20")),
    )
    out = capsys.readouterr().out
    assert code == 1
    assert "not in nbr_pages.json: ['Surprise Filter']" in out
    assert "missing from the dashboard: ['Does Not Exist']" in out
    assert (
        store.runs.count_documents({"page": "extra", "status": "failed"}) == 1
    )  # no retry storm
    assert (
        store.runs.count_documents({"page": "branches", "status": "complete"}) == 1
    )  # other page unaffected
    assert (
        store.tables.count_documents({"page": {"$in": ["extra", "missing"]}}) == 0
    )  # nothing saved for them


def test_backfill_cards_and_branches_end_to_end(
    config_path, store, fast, tmp_path, capsys
):
    dfile = str(dates_file(tmp_path, "2026-01-20", "2025-02-20"))
    assert (
        run(
            "backfill",
            config_path,
            store,
            "--page",
            "cards",
            "--page",
            "branches",
            "--dates-file",
            dfile,
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "Mode: BACKFILL" in out and "[cards]" in out and "[branches]" in out

    # cards: 2 dates x (2x2) combinations; branches: 2 dates x 1
    assert store.runs.count_documents({"page": "cards", "status": "complete"}) == 8
    assert store.runs.count_documents({"page": "branches", "status": "complete"}) == 2

    # The date change really took effect: stored values equal what the dashboard computes for THAT date+filters.
    for run_doc in store.runs.find({"page": "cards", "status": "complete"}):
        snap, filters = run_doc["snapshot_date"], run_doc["filters"]
        assert (
            run_doc["dashboard_date"] == snap and run_doc["date_source"] == "selected"
        )
        total = store.kpis.find_one(
            {
                "page": "cards",
                "snapshot_date": snap,
                "combo_key": run_doc["combo_key"],
                "metric_label": "Total Customers",
            }
        )
        assert total["metric_value"] == expected_total(snap, filters)
        assert total["metric_value_numeric"] == int(
            total["metric_value"].replace(",", "")
        )
        male = store.kpis.find_one(
            {
                "page": "cards",
                "snapshot_date": snap,
                "combo_key": run_doc["combo_key"],
                "gender": "Male",
            }
        )
        assert male["metric_value"] == expected_male(snap, filters)
        # Filter selections were actually applied, not just labeled.
        requested = run_doc["filters_requested"]
        assert all(filters[k] == v for k, v in requested.items())
        assert len(requested) == 2

    # Table: all 7 districts across 3 pages, district-level fields present, unit text preserved.
    rows = list(
        store.tables.find({"page": "branches", "snapshot_date": "2026-01-20"}).sort(
            "row_index", 1
        )
    )
    assert len(rows) == 7 and {r["district"] for r in rows} >= {"Gasabo", "Unknown"}
    assert [r["rank"] for r in rows] == sorted(r["rank"] for r in rows)
    assert (
        next(r for r in rows if r["district"] == "Unknown")["district_known"] is False
    )
    kpi_pct = store.kpis.find_one(
        {
            "page": "branches",
            "metric_label": "Active Share",
            "snapshot_date": "2026-01-20",
        }
    )
    assert kpi_pct["metric_value"].endswith("%") and isinstance(
        kpi_pct["metric_value_numeric"], float
    )

    # CSV exports exist
    assert (engine.OUTPUT_DIR / "cards" / "table_observations.csv").exists()

    # Rerun: nothing duplicated, everything skipped.
    before = {
        n: getattr(store, n).count_documents({}) for n in ("tables", "kpis", "runs")
    }
    assert (
        run(
            "backfill",
            config_path,
            store,
            "--page",
            "cards",
            "--page",
            "branches",
            "--dates-file",
            dfile,
        )
        == 0
    )
    assert before == {
        n: getattr(store, n).count_documents({}) for n in ("tables", "kpis", "runs")
    }
    assert (
        "All combinations already have terminal results; skipping."
        in capsys.readouterr().out
    )


def test_current_mode_uses_run_date_and_never_changes_the_dashboard_date(
    config_path, store, fast, capsys
):
    assert (
        run(
            "current",
            config_path,
            store,
            "--page",
            "cards",
            "--page",
            "branches",
            "--limit-combinations",
            "2",
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "Mode: CURRENT" in out and "Selecting date" not in out
    today = engine.now_local().date().isoformat()
    docs = list(store.runs.find({"status": "complete"}))
    assert len(docs) == 3  # cards: first 2 combos, branches: 1
    for d in docs:
        assert (
            d["snapshot_date"] == today
            and d["date_source"] == "live_run_date"
            and d["mode"] == "current"
        )
        assert (
            d["dashboard_date"] == "2026-10-20"
        )  # the dashboard's own default, untouched
        assert d["collected_at"] and d["run_date"] == today
    # Weekly rerun on the same day updates in place.
    before = store.runs.count_documents({})
    assert (
        run(
            "current",
            config_path,
            store,
            "--page",
            "cards",
            "--page",
            "branches",
            "--limit-combinations",
            "2",
        )
        == 0
    )
    assert store.runs.count_documents({}) == before


def test_backfill_and_current_store_the_same_document_shape(
    config_path, store, fast, tmp_path
):
    run(
        "backfill",
        config_path,
        store,
        "--page",
        "branches",
        "--dates-file",
        str(dates_file(tmp_path, "2026-01-20")),
    )
    run("current", config_path, store, "--page", "branches")
    back = store.runs.find_one({"mode": "backfill"})
    cur = store.runs.find_one({"mode": "current"})
    assert set(back) - {"_id"} == set(cur) - {"_id"}
    assert set(store.tables.find_one({"mode": "backfill"})) == set(
        store.tables.find_one({"mode": "current"})
    )


def test_date_failure_is_recorded_and_does_not_stop_other_pages_or_dates(
    config_path, store, fast, tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(engine, "MAX_RETRIES", 1)
    monkeypatch.setattr(engine, "PAGE_TIMEOUT_MS", 3000)
    # 'nodate' has no date input; 2024-01-20 is rejected by the dashboard; the other dates are fine.
    code = run(
        "backfill",
        config_path,
        store,
        "--page",
        "nodate",
        "--page",
        "branches",
        "--dates-file",
        str(dates_file(tmp_path, "2024-01-20", "2026-01-20")),
    )
    out = capsys.readouterr().out
    assert code == 1
    assert store.runs.count_documents({"page": "nodate", "status": "date_failed"}) == 2
    assert (
        store.runs.count_documents(
            {"page": "branches", "snapshot_date": "2024-01-20", "status": "date_failed"}
        )
        == 1
    )
    assert (
        store.runs.count_documents(
            {"page": "branches", "snapshot_date": "2026-01-20", "status": "complete"}
        )
        == 1
    )
    assert store.tables.count_documents({"page": "nodate"}) == 0
    assert (
        store.tables.count_documents(
            {"page": "branches", "snapshot_date": "2024-01-20"}
        )
        == 0
    )  # nothing saved under a wrong date
    assert "DATE FAILED" in out


def test_pages_without_a_table_or_chart_save_what_exists(
    config_path, store, fast, capsys
):
    assert (
        run("current", config_path, store, "--page", "notable", "--page", "nochart")
        == 0
    )
    notable = store.runs.find_one({"page": "notable"})
    assert (
        notable["table_status"] == "not_present"
        and notable["status"] == "complete"
        and notable["gender_count"] == 2
    )
    nochart = store.runs.find_one({"page": "nochart"})
    assert (
        nochart["gender_status"] == "absent"
        and nochart["gender_count"] == 0
        and nochart["table_rows"] == 7
    )
    assert store.tables.count_documents({"page": "notable"}) == 0
    assert (
        store.kpis.count_documents({"page": "nochart", "metric_type": "headline_kpi"})
        == 3
    )


def test_unverified_page_records_the_filters_it_actually_finds(
    config_path, store, fast, capsys
):
    assert run("current", config_path, store, "--page", "unverified") == 0
    doc = store.runs.find_one({"page": "unverified"})
    assert (
        doc["filters"] == {"Alpha": "All", "Beta": "All"}
        and doc["filters_config_status"] == "unverified"
    )
    assert "no verified filter list" in capsys.readouterr().out


def test_discover_lists_real_labels_and_options_without_touching_the_db(
    config_path, fast, capsys
):
    assert (
        engine.run_cli(
            "current",
            ["--config", str(config_path), "--page", "branches", "--discover"],
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "'Institution Type'" in out and "'Location'" in out and "'Kigali'" in out


def test_cli_reports_config_problems_with_exit_code_2(config_path, store, capsys):
    assert run("current", config_path, store, "--page", "legacy") == 2
    assert "backfill_nbr_inclusion_history.py" in capsys.readouterr().out
    assert run("current", config_path, store, "--page", "nope") == 2
    assert (
        engine.run_cli(
            "current",
            ["--config", str(HERE / "does_not_exist.json"), "--page", "cards"],
        )
        == 2
    )
