from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.scrapers.nbr_engine import (
    FilterSpec,
    PageConfig,
    build_combinations,
    is_combination_terminal,
    kpi_records_complete,
    load_config,
    read_filter_state,
    select_filter_option,
    terminal_combination_keys,
    wait_for_kpi_cards,
    wait_for_dashboard_update,
)


def test_build_combinations_uses_live_options_for_unverified_filter_labels():
    cfg = PageConfig(
        page_id="cards",
        url="https://example.test/cards",
        title="Cards",
        filters=[
            FilterSpec(label="Gender"),
            FilterSpec(label="Age Segment"),
            FilterSpec(label="Institution Type"),
        ],
    )

    combos = build_combinations(
        cfg,
        discovered_options={
            "Gender": ["All", "Female", "Male"],
            "Age Segment": ["All", "Youth", "Non-Youth"],
            "Institution Type": ["All", "Banks", "Sacco"],
        },
    )

    assert len(combos) == 3 * 3 * 3
    assert combos[0] == {
        "Gender": "All",
        "Age Segment": "All",
        "Institution Type": "All",
    }
    assert combos[-1] == {
        "Gender": "Male",
        "Age Segment": "Non-Youth",
        "Institution Type": "Sacco",
    }


def test_build_combinations_discovers_live_values_for_label_filters(monkeypatch):
    cfg = PageConfig(
        page_id="cards",
        url="https://example.test/cards",
        title="Cards",
        filters=[
            FilterSpec(label="Gender"),
            FilterSpec(label="Age Segment"),
            FilterSpec(label="Institution Type"),
        ],
    )

    monkeypatch.setattr(
        "src.scrapers.nbr_engine.discover_filter_options",
        lambda page, cfg: {
            "Gender": ["All", "Female", "Male"],
            "Age Segment": ["All", "Youth", "Non-Youth"],
            "Institution Type": ["All", "Banks", "Sacco"],
        },
    )

    combos = build_combinations(cfg, page=object())

    assert len(combos) == 3 * 3 * 3
    assert combos[0] == {
        "Gender": "All",
        "Age Segment": "All",
        "Institution Type": "All",
    }
    assert combos[-1] == {
        "Gender": "Male",
        "Age Segment": "Non-Youth",
        "Institution Type": "Sacco",
    }


def test_build_combinations_records_location_as_all_without_iterating_it():
    cfg = PageConfig(
        page_id="cards",
        url="https://example.test/cards",
        title="Cards",
        filters=[
            FilterSpec(label="Gender", options=("All", "Female", "Male")),
            FilterSpec(label="Location", fixed="All"),
            FilterSpec(label="Institution Type", options=("All", "Banks", "Sacco")),
        ],
    )

    combos = build_combinations(cfg)

    assert len(combos) == 3 * 3
    assert all(combo["Location"] == "All" for combo in combos)
    assert combos[0] == {
        "Gender": "All",
        "Institution Type": "All",
        "Location": "All",
    }
    assert combos[-1] == {
        "Gender": "Male",
        "Institution Type": "Sacco",
        "Location": "All",
    }


def test_build_combinations_keeps_fixed_values_when_configured():
    cfg = PageConfig(
        page_id="cards",
        url="https://example.test/cards",
        title="Cards",
        filters=[
            FilterSpec(label="Gender", options=("All", "Female", "Male")),
            FilterSpec(label="Location", fixed="All"),
        ],
    )

    combos = build_combinations(cfg)

    assert len(combos) == 3
    assert all(combo["Location"] == "All" for combo in combos)


def test_configured_13_page_products_and_fixed_filter_values():
    expected_counts = {
        "inclusion": 54,
        "transactional": 45,
        "depositors": 36,
        "savings": 36,
        "credit": 36,
        "insurance": 9,
        "agents": 5,
        "merchants": 5,
        "branches": 5,
        "cards": 36,
        "internet_banking": 36,
        "mobile_banking": 36,
        "pos": 6,
    }
    configs = load_config()
    assert set(configs) == set(expected_counts)

    actual_counts = {}
    for page_id, cfg in configs.items():
        discovered = {
            spec.label: [f"option-{index}" for index in range(spec.expected_count)]
            for spec in cfg.filters or []
            if spec.expected_count is not None
        }
        combos = build_combinations(cfg, discovered_options=discovered)
        actual_counts[page_id] = len(combos)
        assert all(
            combo[spec.label] == spec.fixed
            for combo in combos
            for spec in cfg.filters or []
            if spec.fixed is not None
        )
        assert all(
            combo[spec.label] == "All"
            for combo in combos
            for spec in cfg.filters or []
            if spec.ignored or spec.label == "Location"
        )

    assert actual_counts == expected_counts
    assert sum(actual_counts.values()) == 345


def test_kpi_records_complete_rejects_missing_reference_metrics():
    profile = {
        "headlines": frozenset({"total customers", "total cards"}),
        "genders": frozenset({"female", "male"}),
    }
    records = [
        {"metric_type": "headline_kpi", "metric_label": "Total Customers"},
        {"metric_type": "gender_distribution", "gender": "Female"},
        {"metric_type": "gender_distribution", "gender": "Male"},
    ]

    assert not kpi_records_complete(records, profile)
    records.append({"metric_type": "headline_kpi", "metric_label": "Total Cards"})
    assert kpi_records_complete(records, profile)


def test_kpi_records_complete_does_not_require_gender_chart_for_each_filter():
    profile = {
        "headlines": frozenset({"total customers", "total cards"}),
        "genders": frozenset({"female", "male"}),
    }
    records = [
        {"metric_type": "headline_kpi", "metric_label": "Total Customers"},
        {"metric_type": "headline_kpi", "metric_label": "Total Cards"},
        {"metric_type": "gender_distribution", "gender": "Female"},
    ]

    assert kpi_records_complete(records, profile)


def test_terminal_run_with_incomplete_kpi_counts_is_reprocessed(monkeypatch):
    class Runs:
        def find_one(self, _key):
            return {"status": "complete", "headline_kpi_count": 1, "gender_count": 2}

    class StoreStub:
        runs = Runs()

    profile = {
        "headlines": frozenset({"kpi one", "kpi two"}),
        "genders": frozenset({"female", "male"}),
    }
    monkeypatch.setattr(
        "src.scrapers.nbr_engine.expected_kpi_profile", lambda _page: profile
    )

    assert not is_combination_terminal(StoreStub(), "cards", "2026-10-20", "{}")


def test_terminal_run_does_not_require_gender_chart_count(monkeypatch):
    class Runs:
        def find_one(self, _key):
            return {"status": "complete", "headline_kpi_count": 2, "gender_count": 0}

    class StoreStub:
        runs = Runs()

    profile = {
        "headlines": frozenset({"kpi one", "kpi two"}),
        "genders": frozenset({"female", "male"}),
    }
    monkeypatch.setattr(
        "src.scrapers.nbr_engine.expected_kpi_profile", lambda _page: profile
    )

    assert is_combination_terminal(StoreStub(), "cards", "2026-10-20", "{}")


def test_configured_no_data_terminal_run_is_not_reprocessed(monkeypatch):
    class Runs:
        def find_one(self, _key):
            return {
                "status": "completed_no_data",
                "reason": "Configured as having no data for this page.",
            }

    class StoreStub:
        runs = Runs()

    monkeypatch.setattr(
        "src.scrapers.nbr_engine.expected_kpi_profile",
        lambda _page: {"headlines": frozenset({"kpi one"}), "genders": frozenset()},
    )

    assert is_combination_terminal(StoreStub(), "cards", "2026-10-20", "{}")


def test_dashboard_reported_no_data_run_is_retried(monkeypatch):
    class Runs:
        def find_one(self, _key):
            return {
                "status": "completed_no_data",
                "reason": "Dashboard reports: Data incomplete or missing.",
                "retryable": True,
            }

    class StoreStub:
        runs = Runs()

    monkeypatch.setattr(
        "src.scrapers.nbr_engine.expected_kpi_profile",
        lambda _page: {"headlines": frozenset({"kpi one"}), "genders": frozenset()},
    )

    assert not is_combination_terminal(StoreStub(), "cards", "2026-10-20", "{}")


def test_terminal_combinations_are_loaded_with_one_query(monkeypatch):
    class Runs:
        query_count = 0

        def find(self, query, projection):
            self.query_count += 1
            assert query == {
                "page": "cards",
                "snapshot_date": "2026-10-20",
                "combo_key": {"$in": ["complete", "incomplete", "no-data"]},
            }
            assert projection["combo_key"] == 1
            return [
                {
                    "combo_key": "complete",
                    "status": "complete",
                    "headline_kpi_count": 2,
                    "gender_count": 2,
                },
                {
                    "combo_key": "incomplete",
                    "status": "complete",
                    "headline_kpi_count": 1,
                    "gender_count": 2,
                },
                {"combo_key": "no-data", "status": "completed_no_data"},
            ]

    class StoreStub:
        runs = Runs()

    profile = {
        "headlines": frozenset({"total customers", "total cards"}),
        "genders": frozenset({"female", "male"}),
    }
    monkeypatch.setattr(
        "src.scrapers.nbr_engine.expected_kpi_profile", lambda _page: profile
    )

    terminal = terminal_combination_keys(
        StoreStub(), "cards", "2026-10-20", ["complete", "incomplete", "no-data"]
    )

    assert terminal == {"complete", "no-data"}
    assert StoreStub.runs.query_count == 1


def test_wait_for_kpi_cards_requires_all_expected_labels():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(
            '<div class="custom-card-margin card">'
            '<div class="card-title small-text">Total Customers</div>'
            '<div class="card-text large-data">100</div></div>'
        )

        assert not wait_for_kpi_cards(
            page, 100, frozenset({"total customers", "total cards"})
        )

        page.locator("body").evaluate("""body => body.insertAdjacentHTML("beforeend", `
                <div class="custom-card-margin card">
                    <div class="card-title small-text">Total Cards</div>
                    <div class="card-text large-data">120</div>
                </div>
            `)""")
        assert wait_for_kpi_cards(
            page, 1000, frozenset({"total customers", "total cards"})
        )
        browser.close()


def test_dashboard_update_wait_accepts_explicit_no_data_state():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(
            "<title>Updating...</title><div>Error: Data incomplete or missing.</div>"
        )

        wait_for_dashboard_update(page)

        browser.close()


def test_gender_male_selection_does_not_match_female_substring():
    from playwright.sync_api import sync_playwright

    cfg = PageConfig(
        page_id="cards",
        url="https://example.test/cards",
        title="Cards",
        filters=[FilterSpec(label="Gender")],
    )
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content("""<div class="dropdown-card">
                <label>Gender</label>
                <div class="Select-control">
                    <span class="Select-value-label">All</span>
                    <input id="gender-combobox" role="combobox">
                </div>
                <div class="VirtualizedSelectOption VirtualizedSelectFocusedOption" onclick="this.parentElement.querySelector('.Select-value-label').innerText=this.innerText">All</div>
                <div class="VirtualizedSelectOption" onclick="this.parentElement.querySelector('.Select-value-label').innerText=this.innerText">Female</div>
                <div class="VirtualizedSelectOption" onclick="this.parentElement.querySelector('.Select-value-label').innerText=this.innerText">Male</div>
            </div>""")
        page.evaluate("""() => {
                const input = document.querySelector('#gender-combobox');
                const options = Array.from(document.querySelectorAll('.VirtualizedSelectOption'));
                let focused = 0;
                input.addEventListener('keydown', event => {
                    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
                        event.preventDefault();
                        options[focused].classList.remove('VirtualizedSelectFocusedOption');
                        focused = Math.max(0, Math.min(options.length - 1, focused + (event.key === 'ArrowDown' ? 1 : -1)));
                        options[focused].classList.add('VirtualizedSelectFocusedOption');
                    } else if (event.key === 'Enter') {
                        event.preventDefault();
                        options[focused].click();
                    }
                });
            }""")

        select_filter_option(page, 0, "Gender", "Male")

        assert read_filter_state(page, cfg)["Gender"] == "Male"
        browser.close()
