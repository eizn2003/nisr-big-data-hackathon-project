from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.scrapers.nbr_engine import FilterSpec, PageConfig, build_combinations


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
