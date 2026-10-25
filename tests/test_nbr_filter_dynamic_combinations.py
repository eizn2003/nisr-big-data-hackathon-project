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


def test_build_combinations_ignores_location_filter():
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
    assert all("Location" not in combo for combo in combos)
    assert combos[0] == {"Gender": "All", "Institution Type": "All"}
    assert combos[-1] == {"Gender": "Male", "Institution Type": "Sacco"}


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
    assert all("Location" not in combo for combo in combos)


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


def test_no_data_terminal_run_is_not_reprocessed(monkeypatch):
    class Runs:
        def find_one(self, _key):
            return {"status": "completed_no_data"}

    class StoreStub:
        runs = Runs()

    monkeypatch.setattr(
        "src.scrapers.nbr_engine.expected_kpi_profile",
        lambda _page: {"headlines": frozenset({"kpi one"}), "genders": frozenset()},
    )

    assert is_combination_terminal(StoreStub(), "cards", "2026-10-20", "{}")


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
