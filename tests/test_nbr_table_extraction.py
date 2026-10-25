from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.scrapers.nbr_engine import PageConfig, save_observations


class CollectionStub:
    def __init__(self):
        self.delete_query = None

    def bulk_write(self, _operations, ordered=False):
        assert ordered is False

    def delete_many(self, query):
        self.delete_query = query

    def update_one(self, *_args, **_kwargs):
        pass

    def find_one(self, *_args, **_kwargs):
        return None


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