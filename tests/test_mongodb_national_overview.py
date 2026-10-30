import unittest

from src.data_sources.mongodb_national_overview import (
    ExtractionSpec,
    ExtractionValidationError,
    _combo_key,
    normalize_observations,
    parse_numeric_value,
)


class MongoNationalOverviewTests(unittest.TestCase):
    def setUp(self):
        self.spec = ExtractionSpec(
            page_id="inclusion",
            reporting_dates=("2025-02-20",),
            selection_filter="Institution Type",
            selections=("All", "Banks"),
            fixed_filters={
                "Gender": "All",
                "Age Segment": "All",
                "Account/Policy Status": "Active",
                "Location": "All",
            },
        )
        self.runs, self.kpis, self.tables = self._observations()

    def _observations(self):
        runs = []
        kpis = []
        tables = []
        for selection in self.spec.selections:
            filters = {**self.spec.fixed_filters, "Institution Type": selection}
            combo_key = _combo_key(filters)
            run_id = f"run-{selection}"
            common = {
                "page": self.spec.page_id,
                "snapshot_date": "2025-02-20",
                "dashboard_date": "2025-02-20",
                "combo_key": combo_key,
                "run_id": run_id,
                "filters": filters,
                "filters_requested": filters,
                "filters_key": combo_key,
            }
            runs.append(
                {
                    **common,
                    "status": "complete",
                    "table_status": "extracted",
                    "table_rows": 2,
                    "table_columns": ["District", "Customers", "Rank"],
                }
            )
            kpis.append(
                {
                    **common,
                    "kpi_count": 1,
                    "kpis": [
                        {
                            "metric_type": "headline_kpi",
                            "metric_label": "Financially Included",
                            "metric_value": "50.0%",
                            "metric_value_numeric": 50.0,
                            "ordinal": 0,
                        }
                    ],
                }
            )
            for row_index, (district, known, customers, rank) in enumerate(
                (("Gasabo", True, "100", "1"), ("unknown", False, "25", "2"))
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
                        "customers": int(customers),
                        "rank": int(rank),
                        "columns": ["District", "Customers", "Rank"],
                        "values": values,
                        "numbers": {
                            "Customers": int(customers),
                            "Rank": int(rank),
                        },
                    }
                )
        return runs, kpis, tables

    def test_numeric_normalization_keeps_percent_and_grouped_values(self):
        self.assertEqual(parse_numeric_value("1,234"), 1234)
        self.assertEqual(parse_numeric_value("50.0%"), 50.0)
        self.assertIsNone(parse_numeric_value("not reported"))
        self.assertIsNone(parse_numeric_value(True))

    def test_combination_key_uses_complete_sorted_filters(self):
        filters = {
            "Institution Type": "Banks",
            "Gender": "All",
            "Age Segment": "All",
            "Account/Policy Status": "Active",
            "Location": "All",
        }
        self.assertEqual(_combo_key(filters), _combo_key(dict(reversed(list(filters.items())))))
        self.assertNotEqual(
            _combo_key(filters),
            _combo_key({**filters, "Account/Policy Status": "Inactive"}),
        )

    def test_inconsistent_combination_key_is_reported(self):
        runs = [dict(run) for run in self.runs]
        runs[0]["combo_key"] = "not-the-filter-combination"
        with self.assertRaises(ExtractionValidationError) as raised:
            normalize_observations(self.spec, runs, self.kpis, self.tables)
        self.assertIn("Run combination key mismatch", str(raised.exception))

    def test_normalizes_source_kpis_and_table_metrics(self):
        result = normalize_observations(
            self.spec, self.runs, self.kpis, self.tables
        )
        self.assertEqual(result.validated_combinations, 2)
        self.assertEqual(result.source_table_rows, 4)
        self.assertEqual(len(result.national_rows), 2)
        self.assertEqual(len(result.district_rows), 8)
        national = result.national_rows[0]
        self.assertEqual(national["metric_label"], "Financially Included")
        self.assertEqual(national["value_raw"], "50.0%")
        self.assertEqual(national["value_numeric"], 50.0)
        self.assertEqual(national["unit"], "percent")
        self.assertEqual(national["geography_level"], "national")

    def test_unknown_district_is_not_assigned_a_geographic_id(self):
        result = normalize_observations(
            self.spec, self.runs, self.kpis, self.tables
        )
        unknown = next(row for row in result.district_rows if row["district"] == "unknown")
        self.assertEqual(unknown["geography_level"], "unknown")
        self.assertEqual(unknown["geography_status"], "unknown")
        self.assertEqual(unknown["geography_id"], "")

    def test_unmatched_source_district_is_preserved_as_unknown(self):
        tables = []
        for source_row in self.tables:
            row = dict(source_row)
            if row["district"] == "Gasabo":
                row["district"] = "Unmatched label"
                row["values"] = {**row["values"], "District": "Unmatched label"}
            tables.append(row)
        result = normalize_observations(
            self.spec,
            self.runs,
            self.kpis,
            tables,
            known_districts={"Gasabo"},
        )
        unmatched = next(
            row for row in result.district_rows if row["district"] == "Unmatched label"
        )
        self.assertEqual(unmatched["geography_level"], "unknown")
        self.assertEqual(unmatched["geography_status"], "unmatched")
        self.assertEqual(unmatched["geography_id"], "")
        self.assertEqual(result.unmatched_district_names, ("Unmatched label",))

    def test_missing_kpi_observation_is_reported(self):
        with self.assertRaises(ExtractionValidationError) as raised:
            normalize_observations(self.spec, self.runs, [], self.tables)
        self.assertIn("Missing KPI observation", str(raised.exception))

    def test_missing_table_observation_is_reported(self):
        with self.assertRaises(ExtractionValidationError) as raised:
            normalize_observations(self.spec, self.runs, self.kpis, [])
        self.assertIn("Missing district table observations", str(raised.exception))

    def test_completed_no_data_run_is_not_accepted_as_zero(self):
        runs = [dict(run) for run in self.runs]
        runs[0]["status"] = "completed_no_data"
        with self.assertRaises(ExtractionValidationError) as raised:
            normalize_observations(self.spec, runs, self.kpis, self.tables)
        self.assertIn("completed_no_data", str(raised.exception))

    def test_duplicate_district_observation_key_is_reported(self):
        duplicate = dict(self.tables[0])
        with self.assertRaises(ExtractionValidationError) as raised:
            normalize_observations(
                self.spec, self.runs, self.kpis, [*self.tables, duplicate]
            )
        self.assertIn("Duplicate district row key", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
