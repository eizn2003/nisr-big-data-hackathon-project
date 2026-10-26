from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.scrapers.nbr_engine import (
    LEGACY_KPI_INDEX,
    PageConfig,
    _merge_kpi_documents,
    migrate_kpi_observations,
    save_observations,
)


class CollectionStub:
    def __init__(self):
        self.delete_query = None
        self.replacements = []
        self.dropped_indexes = []
        self.migration_documents = []

    def bulk_write(self, _operations, ordered=False):
        assert ordered is False

    def delete_many(self, query):
        self.delete_query = query

    def update_one(self, *_args, **_kwargs):
        pass

    def replace_one(self, query, replacement, upsert=False):
        self.replacements.append((query, replacement, upsert))

    def index_information(self):
        return {LEGACY_KPI_INDEX: {"unique": True}}

    def aggregate(self, _pipeline):
        return [
            {
                "_id": {
                    "page": "cards",
                    "snapshot_date": "2026-10-20",
                    "combo_key": '{"Gender": "All"}',
                }
            }
        ]

    def find(self, _query):
        return SortedDocuments(self.migration_documents)

    def drop_index(self, name):
        self.dropped_indexes.append(name)

    def find_one(self, *_args, **_kwargs):
        return None


class SortedDocuments(list):
    def sort(self, _sort_spec):
        return self


class StoreStub:
    def __init__(self):
        self.tables = CollectionStub()
        self.kpis = CollectionStub()
        self.runs = CollectionStub()


def test_reextract_deletes_only_stale_trailing_table_rows():
    store = StoreStub()
    cfg = PageConfig(
        page_id="agents",
        url="https://example.test/agents",
        title="Agents",
        filters=[],
    )

    save_observations(
        store=store,
        cfg=cfg,
        snapshot_date="2026-10-20",
        assignments={"Gender": "All"},
        filters_actual={"Gender": "All"},
        kpi_records=[],
        table={
            "headers": ["District", "Agents", "Rank"],
            "rows": [["District A", "10", "1"], ["District B", "5", "2"]],
        },
        meta={
            "collected_at": datetime(2026, 10, 25),
            "date_source": "selected",
            "dashboard_date": "2026-10-20",
            "mode": "backfill",
            "run_id": "test",
            "gender_status": "disabled",
        },
    )

    assert store.tables.delete_query == {
        "page": "agents",
        "snapshot_date": "2026-10-20",
        "combo_key": '{"Gender": "All"}',
        "row_index": {"$gte": 2},
    }


def test_save_observations_stores_all_kpis_in_one_combination_document():
    store = StoreStub()
    cfg = PageConfig(
        page_id="cards",
        url="https://example.test/cards",
        title="Cards",
        filters=[],
    )
    kpis = [
        {
            "metric_type": "headline_kpi",
            "metric_label": "Total Customers",
            "metric_value": "100",
        },
        {
            "metric_type": "headline_kpi",
            "metric_label": "Total Cards",
            "metric_value": "120",
        },
        {
            "metric_type": "gender_distribution",
            "metric_label": "Female customers",
            "metric_value": 40,
            "gender": "Female",
        },
        {
            "metric_type": "gender_distribution",
            "metric_label": "Male customers",
            "metric_value": 60,
            "gender": "Male",
        },
    ]

    save_observations(
        store=store,
        cfg=cfg,
        snapshot_date="2026-10-20",
        assignments={"Gender": "All"},
        filters_actual={"Gender": "All"},
        kpi_records=kpis,
        table=None,
        meta={
            "collected_at": datetime(2026, 10, 25),
            "date_source": "selected",
            "dashboard_date": "2026-10-20",
            "mode": "backfill",
            "run_id": "test",
            "gender_status": "extracted",
        },
    )

    assert len(store.kpis.replacements) == 1
    query, document, upsert = store.kpis.replacements[0]
    assert query == {
        "page": "cards",
        "snapshot_date": "2026-10-20",
        "combo_key": '{"Gender": "All"}',
    }
    assert upsert is True
    assert document["kpi_count"] == 4
    assert [record["metric_label"] for record in document["kpis"]] == [
        "Total Customers",
        "Total Cards",
        "Female customers",
        "Male customers",
    ]
    assert "metric_label" not in document


def test_legacy_metric_documents_merge_without_losing_kpis():
    base = {
        "page": "cards",
        "snapshot_date": "2026-10-20",
        "combo_key": '{"Gender": "All"}',
        "filters": {"Gender": "All"},
    }
    records = [
        {
            "metric_type": "headline_kpi",
            "metric_label": "Total Customers",
            "metric_value": "100",
            "ordinal": 0,
        },
        {
            "metric_type": "headline_kpi",
            "metric_label": "Total Cards",
            "metric_value": "120",
            "ordinal": 1,
        },
        {
            "metric_type": "gender_distribution",
            "metric_label": "Female customers",
            "metric_value": 40,
            "gender": "Female",
            "ordinal": 0,
        },
        {
            "metric_type": "gender_distribution",
            "metric_label": "Male customers",
            "metric_value": 60,
            "gender": "Male",
            "ordinal": 1,
        },
    ]
    documents = [
        {**base, "_id": index, **record} for index, record in enumerate(records)
    ]

    merged = _merge_kpi_documents(documents)

    assert merged["kpi_count"] == 4
    assert [record["metric_label"] for record in merged["kpis"]] == [
        "Female customers",
        "Male customers",
        "Total Customers",
        "Total Cards",
    ]
    assert "metric_type" not in merged


def test_startup_migration_consolidates_legacy_documents_before_index_change():
    store = StoreStub()
    base = {
        "page": "cards",
        "snapshot_date": "2026-10-20",
        "combo_key": '{"Gender": "All"}',
        "filters": {"Gender": "All"},
        "collected_at": datetime(2026, 10, 25),
    }
    store.kpis.migration_documents = [
        {
            **base,
            "_id": index,
            **record,
        }
        for index, record in enumerate(
            [
                {
                    "metric_type": "headline_kpi",
                    "metric_label": "Total Customers",
                    "metric_value": "100",
                    "ordinal": 0,
                },
                {
                    "metric_type": "headline_kpi",
                    "metric_label": "Total Cards",
                    "metric_value": "120",
                    "ordinal": 1,
                },
                {
                    "metric_type": "gender_distribution",
                    "metric_label": "Female customers",
                    "metric_value": 40,
                    "gender": "Female",
                    "ordinal": 0,
                },
                {
                    "metric_type": "gender_distribution",
                    "metric_label": "Male customers",
                    "metric_value": 60,
                    "gender": "Male",
                    "ordinal": 1,
                },
            ]
        )
    ]

    migrate_kpi_observations(store)

    assert len(store.kpis.replacements) == 1
    query, document, upsert = store.kpis.replacements[0]
    assert query == {"_id": 3}
    assert upsert is True
    assert document["kpi_count"] == 4
    assert store.kpis.delete_query == {
        "page": "cards",
        "snapshot_date": "2026-10-20",
        "combo_key": '{"Gender": "All"}',
        "_id": {"$ne": 3},
    }
    assert store.kpis.dropped_indexes == [LEGACY_KPI_INDEX]
