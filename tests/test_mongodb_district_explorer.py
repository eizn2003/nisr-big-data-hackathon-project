import unittest
import json

from src.data_sources.mongodb_district_explorer import (
    APPROVED_MAPPINGS,
    CHANGE_REVIEW_THRESHOLD_PERCENT,
    ExtractionValidationError,
    HISTORICAL_CHANGE_FIELDS,
    NO_RELEVANT_NBR_DATA,
    PageSelection,
    REPORTING_DATES,
    SELECTIONS,
    calculate_historical_changes,
    normalize_observations,
)


class MongoDistrictExplorerTests(unittest.TestCase):
    def setUp(self):
        self.selections = (
            PageSelection(
                "inclusion",
                {
                    "Gender": "All",
                    "Age Segment": "All",
                    "Institution Type": "Banks",
                    "Account/Policy Status": "Active",
                    "Location": "All",
                },
                "Bank customers.",
            ),
            PageSelection(
                "credit",
                {
                    "Gender": "All",
                    "Age Segment": "All",
                    "Institution Type": "All",
                    "Account Status": "Active",
                    "Credit Category": "All",
                    "Location": "All",
                },
                "Credit customers.",
            ),
        )
        self.date = "2025-02-20"
        self.runs, self.kpis, self.tables = self.make_documents()
        self.district_reference = {"Gasabo": "shape-gasabo"}

    def make_documents(
        self,
        dates=None,
        customer_values=("100", "25"),
        national_total="125",
        repeat_hash="same-content",
    ):
        dates = dates or (self.date,)
        runs, kpis, tables = [], [], []
        for reporting_date in dates:
            for selection in self.selections:
                combo_key = json.dumps(
                    selection.filters, sort_keys=True, ensure_ascii=False
                )
                run_id = f"{selection.page_id}-{reporting_date}"
                common = {
                    "page": selection.page_id,
                    "snapshot_date": reporting_date,
                    "dashboard_date": reporting_date,
                    "combo_key": combo_key,
                    "filters_key": combo_key,
                    "run_id": run_id,
                    "filters": dict(selection.filters),
                    "filters_requested": dict(selection.filters),
                    "collected_at": f"{reporting_date}T12:00:00+02:00",
                }
                runs.append(
                    {
                        **common,
                        "status": "complete",
                        "table_status": "extracted",
                        "table_rows": 2,
                        "table_columns": ["District", "Customers", "Rank"],
                        "content_hash": repeat_hash,
                    }
                )
                metric_label = (
                    "Banked" if selection.page_id == "inclusion" else "Borrowed"
                )
                kpi_document = {
                    **common,
                    "kpi_count": 2,
                    "content_hash": f"{run_id}-kpi",
                    "combination_content_hash": repeat_hash,
                    "kpis": [
                        {
                            "metric_type": "headline_kpi",
                            "metric_label": metric_label,
                            "metric_value": "50.0%",
                            "metric_value_numeric": 50.0,
                            "ordinal": 0,
                        },
                        {
                            "metric_type": "headline_kpi",
                            "metric_label": "Total Customers",
                            "metric_value": national_total,
                            "metric_value_numeric": int(national_total),
                            "ordinal": 1,
                        },
                    ],
                }
                kpis.append(kpi_document)
                for row_index, (district, known, customers, rank) in enumerate(
                    (
                        ("Gasabo", True, customer_values[0], "1"),
                        ("unknown", False, customer_values[1], "2"),
                    )
                ):
                    values = {
                        "District": district,
                        "Customers": customers,
                        "Rank": rank,
                    }
                    tables.append(
                        {
                            **common,
                            "row_index": row_index,
                            "district": district,
                            "district_known": known,
                            "columns": ["District", "Customers", "Rank"],
                            "cells": list(values.values()),
                            "values": values,
                            "numbers": {
                                key: int(value)
                                for key, value in values.items()
                                if key != "District" and value != ""
                            },
                            "content_hash": f"{run_id}-row-{row_index}",
                            "combination_content_hash": repeat_hash,
                        }
                    )
        return runs, kpis, tables

    def normalize(self, **kwargs):
        return normalize_observations(
            self.runs,
            self.kpis,
            self.tables,
            known_districts=self.district_reference,
            reporting_dates=kwargs.pop("reporting_dates", (self.date,)),
            selections=kwargs.pop("selections", self.selections),
            **kwargs,
        )

    def test_selection_configuration_targets_independent_nbr_trends(self):
        self.assertEqual(
            {selection.page_id for selection in SELECTIONS},
            {
                "branches",
                "inclusion",
                "transactional",
                "depositors",
                "agents",
                "credit",
                "savings",
            },
        )
        self.assertEqual(len(SELECTIONS), 11)
        self.assertEqual(REPORTING_DATES, (
            "2025-02-20",
            "2025-11-20",
            "2026-08-20",
            "2026-10-24",
        ))
        self.assertFalse(
            {selection.page_id for selection in SELECTIONS}
            & {"pos", "insurance", "mobile_banking", "merchants", "cards"}
        )
        by_key = {
            (selection.page_id, selection.filters.get("Institution Type", "")): selection
            for selection in SELECTIONS
        }
        self.assertEqual(
            by_key[("branches", "Banks")].filters,
            {
                "Institution Type": "Banks",
                "Branch Status": "Active",
                "Location": "All",
            },
        )
        self.assertEqual(
            by_key[("branches", "Sacco")].filters,
            {
                "Institution Type": "Sacco",
                "Branch Status": "Active",
                "Location": "All",
            },
        )
        self.assertEqual(
            by_key[("inclusion", "E-money issuers")].filters,
            {
                "Gender": "All",
                "Age Segment": "All",
                "Institution Type": "E-money issuers",
                "Account/Policy Status": "Active",
                "Location": "All",
            },
        )
        self.assertEqual(
            by_key[("agents", "E-money Issuers")].filters,
            {
                "Gender": "All",
                "Institution Type": "E-money Issuers",
                "Agent Status": "Active",
                "Location": "All",
            },
        )
        self.assertEqual(
            by_key[("branches", "Banks")].kpi_labels,
            ("Total Branches",),
        )
        self.assertEqual(
            by_key[("inclusion", "E-money issuers")].kpi_labels,
            ("Subscribers", "Total Customers"),
        )
        self.assertEqual(
            by_key[("agents", "E-money Issuers")].table_labels,
            ("Agents",),
        )
        self.assertNotIn("2026-10-27", REPORTING_DATES)

    def test_approved_mapping_metadata_and_unmapped_indicators_are_exact(self):
        variables = {mapping.indicator_variable for mapping in APPROVED_MAPPINGS}
        self.assertEqual(
            variables | set(NO_RELEVANT_NBR_DATA),
            {"k1", "f5", "h2_1", "g3a_17", "e9b", "g3a_11", "qf4_06", "qf4_10"},
        )
        actual_mappings = {
            (
                mapping.indicator_variable,
                mapping.page_id,
                mapping.filters.get("Institution Type", "All"),
            ): (mapping.kpi_labels, mapping.table_labels, mapping.status)
            for mapping in APPROVED_MAPPINGS
        }
        self.assertEqual(
            actual_mappings,
            {
                ("k1", "branches", "Banks"): (("Total Branches",), ("Branches",), "relevant"),
                ("k1", "inclusion", "Banks"): (("Banked", "Total Customers"), ("Customers",), "uncertain"),
                ("k1", "transactional", "All"): (("Have Transactional Accounts",), ("Customers",), "uncertain"),
                ("k1", "depositors", "All"): (("Are Depositors",), ("Customers",), "uncertain"),
                ("f5", "inclusion", "E-money issuers"): (("Subscribers", "Total Customers"), ("Customers",), "uncertain"),
                ("f5", "agents", "E-money Issuers"): (("Total Agents",), ("Agents",), "uncertain"),
                ("h2_1", "credit", "All"): (("Borrowed",), ("Customers",), "uncertain"),
                ("g3a_17", "savings", "All"): (("Saved",), ("Customers",), "uncertain"),
                ("g3a_17", "depositors", "All"): (("Are Depositors",), ("Customers",), "uncertain"),
                ("g3a_11", "inclusion", "Sacco"): (("SACCO Customers", "Total Customers"), ("Customers",), "uncertain"),
                ("g3a_11", "branches", "Sacco"): (("Total Branches",), ("Branches",), "relevant"),
                ("g3a_11", "agents", "Sacco"): (("Total Agents",), ("Agents",), "unsuitable"),
                ("qf4_06", "inclusion", "Sacco"): (("SACCO Customers", "Total Customers"), ("Customers",), "uncertain"),
                ("qf4_06", "branches", "Sacco"): (("Total Branches",), ("Branches",), "relevant"),
                ("qf4_06", "agents", "Sacco"): (("Total Agents",), ("Agents",), "unsuitable"),
            },
        )
        self.assertEqual(
            NO_RELEVANT_NBR_DATA,
            {
                "e9b": "No relevant data identified from the NBR data currently available to this project.",
                "qf4_10": "No relevant data identified from the NBR data currently available to this project.",
            },
        )
        self.assertTrue(
            all(mapping.page_id != "pos" for mapping in APPROVED_MAPPINGS)
        )
        self.assertTrue(
            all(mapping.page_id != "mobile_banking" for mapping in APPROVED_MAPPINGS)
        )
        sacco_agent_mappings = [
            mapping for mapping in APPROVED_MAPPINGS
            if mapping.page_id == "agents"
            and mapping.filters.get("Institution Type") == "Sacco"
        ]
        self.assertEqual(
            {mapping.indicator_variable for mapping in sacco_agent_mappings},
            {"g3a_11", "qf4_06"},
        )
        self.assertTrue(all(mapping.status == "unsuitable" for mapping in sacco_agent_mappings))
        self.assertTrue(
            all("three districts" in mapping.limitations for mapping in sacco_agent_mappings)
        )
        e_money_agents = next(
            mapping for mapping in APPROVED_MAPPINGS
            if mapping.page_id == "agents"
            and mapping.filters.get("Institution Type") == "E-money Issuers"
        )
        self.assertIn(
            "district sums exceed the national kpi",
            e_money_agents.limitations.casefold(),
        )
        self.assertEqual(
            e_money_agents.kpi_labels,
            ("Total Agents",),
        )

    def test_normalizes_cross_page_kpis_and_table_fields(self):
        result = self.normalize()
        self.assertEqual(len(result.coverage_rows), 2)
        self.assertEqual(len(result.national_rows), 4)
        self.assertEqual(len(result.district_rows), 8)
        self.assertEqual(
            {row["source_page"] for row in result.district_rows},
            {"inclusion", "credit"},
        )
        customer = next(
            row
            for row in result.district_rows
            if row["source_page"] == "inclusion"
            and row["district"] == "Gasabo"
            and row["metric_label"] == "Customers"
        )
        self.assertEqual(customer["value_raw"], "100")
        self.assertEqual(customer["value_numeric"], 100)
        self.assertEqual(customer["district_id"], "shape-gasabo")
        self.assertEqual(customer["geography_level"], "district")
        self.assertEqual(customer["run_id"], f"inclusion-{self.date}")
        self.assertEqual(
            json.loads(customer["source_row_json"])["values"]["Customers"],
            "100",
        )
        rank = next(row for row in result.district_rows if row["metric_label"] == "Rank")
        self.assertEqual(rank["unit"], "rank")
        national = next(row for row in result.national_rows if row["metric_label"] == "Banked")
        self.assertEqual(national["geography_level"], "national")
        self.assertEqual(national["unit"], "percent")

    def test_normalization_keeps_only_configured_kpi_labels(self):
        banks = PageSelection(
            "inclusion",
            {
                "Gender": "All",
                "Age Segment": "All",
                "Institution Type": "Banks",
                "Account/Policy Status": "Active",
                "Location": "All",
            },
            "Configured count-only example.",
            ("Total Customers",),
        )
        self.kpis[0]["kpis"].extend(
            [
                {
                    "metric_type": "headline_kpi",
                    "metric_label": "Female customers",
                    "metric_value": "60",
                    "metric_value_numeric": 60,
                    "ordinal": 2,
                },
                {
                    "metric_type": "headline_kpi",
                    "metric_label": "Male customers",
                    "metric_value": "40",
                    "metric_value_numeric": 40,
                    "ordinal": 3,
                },
            ]
        )
        self.kpis[0]["kpi_count"] = 4
        result = normalize_observations(
            self.runs[:1],
            self.kpis[:1],
            self.tables[:2],
            known_districts=self.district_reference,
            reporting_dates=(self.date,),
            selections=(banks,),
        )
        self.assertEqual(
            {row["metric_label"] for row in result.national_rows},
            {"Total Customers"},
        )
        coverage = result.coverage_rows[0]
        self.assertEqual(
            json.loads(coverage["excluded_kpi_labels_json"]),
            ["Banked", "Female customers", "Male customers"],
        )

    def test_dataframe_schemas_are_explicit_and_deterministic(self):
        first = self.normalize()
        second = self.normalize()
        national, district, coverage = first.to_dataframes()
        self.assertEqual(list(national.columns), list(second.to_dataframes()[0].columns))
        self.assertEqual(list(district.columns), list(second.to_dataframes()[1].columns))
        self.assertEqual(list(coverage.columns), list(second.to_dataframes()[2].columns))
        self.assertEqual(national.to_dict("records"), second.to_dataframes()[0].to_dict("records"))
        self.assertEqual(len(district), 8)
        historical = first.to_historical_changes_dataframe()
        self.assertEqual(list(historical.columns), list(HISTORICAL_CHANGE_FIELDS))
        self.assertEqual(
            historical.to_dict("records"),
            first.historical_changes_rows,
        )

    def test_unknown_and_unmatched_districts_are_not_assigned_ids(self):
        unmatched = dict(self.tables[0])
        unmatched["district"] = "Unmatched label"
        unmatched["district_known"] = True
        unmatched["values"] = {
            **unmatched["values"],
            "District": "Unmatched label",
        }
        unmatched["cells"][0] = "Unmatched label"
        self.tables.append(unmatched)
        for run in self.runs:
            run["table_rows"] = 3
            run["table_columns"] = ["District", "Customers", "Rank"]
        result = self.normalize()
        unknown = next(row for row in result.district_rows if row["district"] == "unknown")
        unmatched_row = next(
            row for row in result.district_rows if row["district"] == "Unmatched label"
        )
        self.assertEqual(unknown["geography_status"], "unknown")
        self.assertEqual(unknown["district_id"], "")
        self.assertEqual(unmatched_row["geography_status"], "unmatched")
        self.assertEqual(unmatched_row["district_id"], "")
        self.assertTrue(any("Unmatched district name" in item for item in result.validation_errors))
        inclusion_coverage = next(
            row for row in result.coverage_rows if row["source_page"] == "inclusion"
        )
        self.assertEqual(inclusion_coverage["unknown_district_rows"], 1)
        self.assertEqual(inclusion_coverage["unmatched_district_rows"], 1)

    def test_zero_and_missing_values_keep_distinct_raw_source_values(self):
        self.tables[0]["values"]["Customers"] = "0"
        self.tables[0]["numbers"]["Customers"] = 0
        self.tables[1]["values"]["Customers"] = ""
        self.tables[1]["numbers"].pop("Customers")
        result = self.normalize()
        zero = next(
            row for row in result.district_rows
            if row["district"] == "Gasabo" and row["metric_label"] == "Customers"
        )
        missing = next(
            row for row in result.district_rows
            if row["district"] == "unknown" and row["metric_label"] == "Customers"
        )
        self.assertEqual((zero["value_raw"], zero["value_numeric"]), ("0", 0))
        self.assertEqual((missing["value_raw"], missing["value_numeric"]), ("", None))

    def test_reporting_date_and_collection_timestamp_are_separate(self):
        result = self.normalize()
        row = result.national_rows[0]
        self.assertEqual(row["reporting_date"], self.date)
        self.assertEqual(row["collected_at"], f"{self.date}T12:00:00+02:00")

    def test_historical_changes_use_adjacent_observed_counts_and_keep_provenance(self):
        dates = ("2025-02-20", "2025-11-20")
        runs, kpis, tables = self.make_documents(dates=dates)
        inclusion_run = next(
            run for run in runs
            if run["page"] == "inclusion" and run["snapshot_date"] == dates[1]
        )
        inclusion_kpi = next(
            doc for doc in kpis
            if doc["page"] == "inclusion" and doc["snapshot_date"] == dates[1]
        )
        district_row = next(
            row for row in tables
            if row["page"] == "inclusion"
            and row["snapshot_date"] == dates[1]
            and row["district"] == "Gasabo"
        )
        district_row["values"]["Customers"] = "150"
        district_row["numbers"]["Customers"] = 150
        district_row["cells"][1] = "150"
        total = next(
            metric for metric in inclusion_kpi["kpis"]
            if metric["metric_label"] == "Total Customers"
        )
        total["metric_value"] = "175"
        total["metric_value_numeric"] = 175

        normalized = normalize_observations(
            runs,
            kpis,
            tables,
            known_districts=self.district_reference,
            reporting_dates=dates,
            selections=self.selections,
        )
        changes = calculate_historical_changes(normalized.district_rows, dates)
        self.assertEqual(normalized.historical_changes_rows, changes)
        inclusion_change = next(
            row for row in changes if row["source_page"] == "inclusion"
        )
        self.assertEqual(len(changes), 2)
        self.assertEqual(inclusion_change["metric_label"], "Customers")
        self.assertEqual(inclusion_change["from_reporting_date"], dates[0])
        self.assertEqual(inclusion_change["to_reporting_date"], dates[1])
        self.assertEqual(inclusion_change["elapsed_days"], 273)
        self.assertEqual(inclusion_change["absolute_change"], 50)
        self.assertEqual(inclusion_change["percent_change"], 50)
        self.assertEqual(CHANGE_REVIEW_THRESHOLD_PERCENT, 50)
        self.assertIn("50%", json.loads(inclusion_change["review_flags_json"])[0])
        self.assertEqual(inclusion_change["data_quality_status"], "warning")
        self.assertEqual(inclusion_change["from_run_id"], f"inclusion-{dates[0]}")
        self.assertEqual(inclusion_change["to_run_id"], inclusion_run["run_id"])
        self.assertEqual(inclusion_change["to_combo_key"], inclusion_run["combo_key"])
        self.assertEqual(inclusion_change["district_id"], "shape-gasabo")
        self.assertNotIn("unknown", {row["district"] for row in changes})

    def test_missing_district_observation_is_not_filled_or_bridged(self):
        dates = ("2025-02-20", "2025-11-20")
        runs, kpis, tables = self.make_documents(dates=dates)
        tables = [
            row for row in tables
            if not (
                row["page"] == "inclusion"
                and row["snapshot_date"] == dates[1]
                and row["district"] == "Gasabo"
            )
        ]
        normalized = normalize_observations(
            runs,
            kpis,
            tables,
            known_districts=self.district_reference,
            reporting_dates=dates,
            selections=self.selections,
        )
        changes = calculate_historical_changes(normalized.district_rows, dates)
        self.assertNotIn("inclusion", {row["source_page"] for row in changes})
        self.assertEqual(
            {row["source_page"] for row in changes},
            {"credit"},
        )

    def test_historical_change_rejects_duplicate_observation_keys_and_zero_base(self):
        dates = ("2025-02-20", "2025-11-20")
        runs, kpis, tables = self.make_documents(dates=dates)
        normalized = normalize_observations(
            runs,
            kpis,
            tables,
            known_districts=self.district_reference,
            reporting_dates=dates,
            selections=self.selections,
        )
        gasabo = next(
            row for row in normalized.district_rows
            if row["source_page"] == "inclusion"
            and row["district"] == "Gasabo"
            and row["metric_label"] == "Customers"
            and row["reporting_date"] == dates[0]
        )
        zero_base_rows = [dict(row) for row in normalized.district_rows]
        zero_base = next(
            row for row in zero_base_rows
            if row["source_page"] == "inclusion"
            and row["district"] == "Gasabo"
            and row["metric_label"] == "Customers"
            and row["reporting_date"] == dates[0]
        )
        zero_base["value_raw"] = "0"
        zero_base["value_numeric"] = 0
        changes = calculate_historical_changes(zero_base_rows, dates)
        inclusion_change = next(
            row for row in changes if row["source_page"] == "inclusion"
        )
        self.assertIsNone(inclusion_change["percent_change"])
        self.assertEqual(inclusion_change["absolute_change"], 100)

        with self.assertRaisesRegex(ValueError, "Duplicate district observation"):
            calculate_historical_changes(
                normalized.district_rows + [dict(gasabo)],
                dates,
            )

    def test_historical_changes_require_the_same_combo_key(self):
        dates = ("2025-02-20", "2025-11-20")
        runs, kpis, tables = self.make_documents(dates=dates)
        normalized = normalize_observations(
            runs,
            kpis,
            tables,
            known_districts=self.district_reference,
            reporting_dates=dates,
            selections=self.selections,
        )
        rows = [dict(row) for row in normalized.district_rows]
        second_inclusion_row = next(
            row for row in rows
            if row["source_page"] == "inclusion"
            and row["district"] == "Gasabo"
            and row["reporting_date"] == dates[1]
        )
        second_inclusion_row["combo_key"] = "changed-filter-combination"
        changes = calculate_historical_changes(rows, dates)
        self.assertNotIn("inclusion", {row["source_page"] for row in changes})
        self.assertEqual({row["source_page"] for row in changes}, {"credit"})

    def test_unsuitable_sacco_agent_series_is_preserved_but_not_trended(self):
        selection = next(
            selection for selection in SELECTIONS
            if selection.page_id == "agents"
            and selection.filters.get("Institution Type") == "Sacco"
        )
        self.assertFalse(selection.historical_monitoring_eligible)
        dates = ("2025-02-20", "2025-11-20")
        filters_json = json.dumps(selection.filters, ensure_ascii=False, sort_keys=True)
        rows = [
            {
                "source_page": "agents",
                "filters_json": filters_json,
                "combo_key": json.dumps(selection.filters, sort_keys=True),
                "metric_label": "Agents",
                "unit": "count",
                "district": "Gasabo",
                "district_id": "shape-gasabo",
                "geography_level": "district",
                "geography_status": "matched",
                "reporting_date": reporting_date,
                "value_raw": value,
                "value_numeric": int(value),
                "data_quality_status": "valid",
            }
            for reporting_date, value in zip(dates, ("4", "8"))
        ]
        self.assertEqual(calculate_historical_changes(rows, dates), [])

    def test_agents_kpi_table_discrepancy_is_flagged_and_values_are_retained(self):
        filters = {
            "Gender": "All",
            "Institution Type": "E-money Issuers",
            "Agent Status": "Active",
            "Location": "All",
        }
        selection = PageSelection(
            "agents",
            filters,
            "E-money agent activity.",
            ("Total Agents",),
            ("Agents",),
        )
        combo_key = json.dumps(filters, ensure_ascii=False, sort_keys=True)
        common = {
            "page": "agents",
            "snapshot_date": self.date,
            "dashboard_date": self.date,
            "combo_key": combo_key,
            "filters_key": combo_key,
            "filters": filters,
            "filters_requested": filters,
            "run_id": "agents-run",
            "collected_at": "2026-10-26T12:00:00+02:00",
        }
        run = {
            **common,
            "status": "complete",
            "table_status": "extracted",
            "table_rows": 1,
            "table_columns": ["District", "Agents"],
            "content_hash": "agents-content",
        }
        kpi = {
            **common,
            "kpi_count": 1,
            "kpis": [
                {
                    "metric_type": "headline_kpi",
                    "metric_label": "Total Agents",
                    "metric_value": "10",
                    "metric_value_numeric": 10,
                    "ordinal": 0,
                }
            ],
        }
        table = {
            **common,
            "row_index": 0,
            "district": "Gasabo",
            "district_known": True,
            "columns": ["District", "Agents"],
            "cells": ["Gasabo", "12"],
            "values": {"District": "Gasabo", "Agents": "12"},
            "numbers": {"Agents": 12},
            "content_hash": "agents-row",
            "combination_content_hash": "agents-content",
        }
        result = normalize_observations(
            [run],
            [kpi],
            [table],
            known_districts=self.district_reference,
            reporting_dates=(self.date,),
            selections=(selection,),
        )
        coverage = result.coverage_rows[0]
        self.assertEqual(coverage["table_minus_national"], 2.0)
        self.assertEqual(coverage["validation_status"], "warning")
        self.assertTrue(any("KPI/table total differs" in error for error in result.validation_errors))
        district_value = result.district_rows[0]
        self.assertEqual((district_value["value_raw"], district_value["value_numeric"]), ("12", 12))

    def test_missing_run_and_failed_run_are_reported_without_zero_rows(self):
        self.runs = self.runs[:1]
        self.kpis = self.kpis[:1]
        self.tables = self.tables[:2]
        result = self.normalize()
        missing_coverage = next(
            row for row in result.coverage_rows if row["source_page"] == "credit"
        )
        self.assertEqual(missing_coverage["run_status"], "missing")
        self.assertEqual(missing_coverage["source_table_rows"], 0)
        self.assertTrue(any("Missing run for credit" in item for item in result.validation_errors))

        self.runs[0]["status"] = "completed_no_data"
        result = self.normalize(selections=(self.selections[0],))
        self.assertTrue(any("not complete" in item for item in result.validation_errors))
        self.assertEqual(result.national_rows, [])
        self.assertEqual(result.district_rows, [])

    def test_duplicate_run_kpi_and_table_keys_are_flagged(self):
        self.runs.append(dict(self.runs[0]))
        self.kpis.append(dict(self.kpis[0]))
        result = self.normalize()
        joined_errors = "\n".join(result.validation_errors)
        self.assertIn("Duplicate run records", joined_errors)
        self.assertIn("Expected one KPI document", joined_errors)

        self.runs, self.kpis, self.tables = self.make_documents()
        self.tables.append(dict(self.tables[0]))
        result = self.normalize()
        joined_errors = "\n".join(result.validation_errors)
        self.assertIn("Duplicate table row_index", joined_errors)

    def test_run_link_mismatch_is_reported(self):
        self.kpis[0]["run_id"] = "wrong-run"
        result = self.normalize()
        self.assertTrue(
            any("KPI run_id mismatch" in item for item in result.validation_errors)
        )

    def test_inconsistent_filter_and_collection_metadata_is_reported(self):
        self.tables[0]["filters_requested"] = {"Institution Type": "All"}
        self.tables[0]["collected_at"] = "2025-02-20T13:00:00+02:00"
        result = self.normalize()
        joined_errors = "\n".join(result.validation_errors)
        self.assertIn("requested-filter metadata mismatch", joined_errors)
        self.assertIn("collection timestamp mismatch", joined_errors)

    def test_missing_reporting_date_is_visible_in_coverage(self):
        result = self.normalize(reporting_dates=(self.date, "2025-11-20"))
        missing = next(
            row for row in result.coverage_rows
            if row["source_page"] == "inclusion" and row["reporting_date"] == "2025-11-20"
        )
        self.assertEqual(missing["run_status"], "missing")
        self.assertEqual(missing["validation_status"], "warning")

    def test_kpi_table_discrepancy_is_preserved_in_coverage(self):
        for document in self.kpis:
            total = next(
                metric for metric in document["kpis"]
                if metric["metric_label"] == "Total Customers"
            )
            total["metric_value"] = "200"
            total["metric_value_numeric"] = 200
        result = self.normalize()
        inclusion_coverage = next(
            row for row in result.coverage_rows if row["source_page"] == "inclusion"
        )
        self.assertEqual(inclusion_coverage["table_total_numeric"], 125.0)
        self.assertEqual(inclusion_coverage["national_total_numeric"], 200)
        self.assertEqual(inclusion_coverage["table_minus_national"], -75.0)
        gasabo_value = next(
            row for row in result.district_rows
            if row["source_page"] == "inclusion"
            and row["district"] == "Gasabo"
            and row["metric_label"] == "Customers"
        )
        self.assertEqual(gasabo_value["value_raw"], "100")

    def test_repeated_content_is_flagged_across_dates(self):
        second_date = "2025-11-20"
        runs, kpis, tables = self.make_documents(dates=(self.date, second_date))
        result = normalize_observations(
            runs,
            kpis,
            tables,
            known_districts=self.district_reference,
            reporting_dates=(self.date, second_date),
            selections=(self.selections[0],),
        )
        self.assertTrue(
            all(row["repeated_content_across_dates"] for row in result.coverage_rows)
        )
        self.assertTrue(
            all(row["data_quality_status"] == "warning" for row in result.national_rows)
        )

    def test_strict_mode_raises_for_validation_issues(self):
        self.tables.pop()
        with self.assertRaises(ExtractionValidationError):
            self.normalize(strict=True)


if __name__ == "__main__":
    unittest.main()
