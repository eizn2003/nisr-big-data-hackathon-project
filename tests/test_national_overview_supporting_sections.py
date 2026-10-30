from src.pages.national_overview_supporting_sections import (
    build_barrier_section,
    build_financial_service_network_section,
    build_navigation_cards,
    build_saving_resilience_frame,
    load_financial_service_network_candidates,
)


def test_financial_service_network_section_uses_existing_nbr_metadata_only():
    section = build_financial_service_network_section()
    candidates = section["candidate_metrics"]

    assert section["title"] == "The financial-service network"
    assert section["available"] is False
    assert any(item["source_page"] == "branches" and item["metric_label"] == "Total Branches" for item in candidates)
    assert any(item["source_page"] == "agents" and item["metric_label"] == "Total Agents" for item in candidates)
    assert all(item["value_numeric"] in (None, "") or item["value_numeric"] is None for item in candidates)


def test_financial_service_network_candidates_keep_exact_filters_and_labels():
    frame = load_financial_service_network_candidates()
    assert not frame.empty

    branch = frame[(frame["source_page"] == "branches") & (frame["metric_label"] == "Total Branches")].iloc[0]
    assert branch["institution_type"] in {"Banks", "Sacco"}
    assert branch["filters"]["Location"] == "All"
    assert branch["filters"]["Branch Status"] == "Active"

    agent = frame[(frame["source_page"] == "agents") & (frame["metric_label"] == "Total Agents")].iloc[0]
    assert agent["institution_type"] == "E-money Issuers"
    assert agent["filters"]["Agent Status"] == "Active"
    assert agent["filters"]["Location"] == "All"


def test_saving_resilience_uses_existing_finscope_labels_and_values():
    frame = build_saving_resilience_frame()
    labels = set(frame["indicator"])

    expected = {
        "Does not save": "g3a_17",
        "Has emergency funds": "e9b",
        "Saves with a group": "g3a_11",
        "Currently uses Umurenge SACCO": "qf4_06",
        "Currently uses a savings group": "qf4_10",
    }
    assert set(expected) <= labels

    for label, variable in expected.items():
        row = frame[frame["indicator"] == label].iloc[0]
        assert row["variable"] == variable
        assert 0.0 <= float(row["value"]) <= 100.0


def test_barrier_section_keeps_the_correct_denominator_and_family_labels():
    section = build_barrier_section()
    assert "without an account" in section["population_note"]
    assert "all Rwandan adults" in section["population_note"]
    rows = section["rows"]
    assert rows
    assert "No need or too little income" in {row["Barrier family"] for row in rows}
    assert any(row["Reason (short)"] == "Does not need one / money too limited to justify it" for row in rows)


def test_navigation_cards_target_real_pages():
    cards = build_navigation_cards()
    pages = {card["page"] for card in cards}
    expected = {"District explorer", "Population groups", "Priority explorer", "Methodology & sources"}
    assert expected <= pages
