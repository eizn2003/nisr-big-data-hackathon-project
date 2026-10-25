from __future__ import annotations

import csv
import hashlib
import itertools
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne
from pymongo.errors import PyMongoError
from playwright.sync_api import (
    sync_playwright,
    TimeoutError as PlaywrightTimeoutError,
)

# ============================================================
# CONFIGURATION
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = PROJECT_ROOT / "data" / "raw" / "nbr" / "inclusion"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

URL = "https://fininclusion.bnr.rw/inclusion"
TIMEZONE = ZoneInfo("Africa/Kigali")
DATABASE_NAME = "nbr_financial_inclusion"
DISTRICT_COLLECTION = "agent_district_observations"
KPI_COLLECTION = "agent_kpi_observations"
RUN_COLLECTION = "scrape_runs"

TABLE_SELECTOR = "table.cell-table"
NEXT_BUTTON_SELECTOR = "button.next-page"
FIRST_BUTTON_SELECTOR = "button.first-page"
MAX_TABLE_PAGES = 100
MAX_RETRIES = 3
PAGE_TIMEOUT_MS = 20000
FILTER_SETTLE_MS = 700

FILTERS = {
    "Gender": ["All", "Female", "Male"],
    "Age Segment": ["All", "Youth", "Non-Youth"],
    "Institution Type": [
        "All", "Banks", "E-money issuers", "Insurance", "Microfinance", "Sacco"
    ],
    "Account/Policy Status": ["Active", "Matured", "Dormant", "Inactive"],
}
LOCATION_FILTER_INDEX = 4
FILTER_NAMES = list(FILTERS)

# Confirmed by inspecting the dashboard. These are not scraping errors.
KNOWN_NOT_APPLICABLE = {
    ("Insurance", "Matured"),
    ("Insurance", "Dormant"),
}
KNOWN_NO_DATA = {
    ("E-money issuers", "Matured"),
    ("E-money issuers", "Dormant"),
    ("Microfinance", "Matured"),
}

# Keep the existing dashboard disclaimer workaround.
MODAL_CSS = """
.modal, .modal.show, .modal-backdrop, [role="dialog"] {
    display: none !important;
    visibility: hidden !important;
    pointer-events: none !important;
}
body { overflow: auto !important; }
"""

load_dotenv(PROJECT_ROOT / ".env")
MONGODB_URI = os.getenv("MONGODB_URI") or os.getenv("MONGO_URI")
if not MONGODB_URI:
    raise RuntimeError(
        "MongoDB URI not found. Add MONGODB_URI or MONGO_URI to the project .env file."
    )


def now_local() -> datetime:
    return datetime.now(TIMEZONE)


def current_snapshot_date() -> str:
    return now_local().date().isoformat()


def filters_key(filters: dict[str, str]) -> str:
    return json.dumps(filters, sort_keys=True, ensure_ascii=False)


def stable_hash(value) -> str:
    payload = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def connect_mongodb():
    client = MongoClient(
        MONGODB_URI,
        serverSelectionTimeoutMS=15000,
        connectTimeoutMS=15000,
        socketTimeoutMS=30000,
    )
    client.admin.command("ping")
    db = client[DATABASE_NAME]
    districts = db[DISTRICT_COLLECTION]
    kpis = db[KPI_COLLECTION]
    runs = db[RUN_COLLECTION]

    # These indexes match the natural identity of each observation.
    districts.create_index(
        [
            ("snapshot_date", 1),
            ("filters.Gender", 1),
            ("filters.Age Segment", 1),
            ("filters.Institution Type", 1),
            ("filters.Account/Policy Status", 1),
            ("district", 1),
        ], unique=True, name="uniq_snapshot_filter_district",
    )
    for collection, name in ((kpis, "uniq_snapshot_filter_kpi"), (runs, "uniq_snapshot_filter_run")):
        collection.create_index(
            [
                ("snapshot_date", 1),
                ("filters.Gender", 1),
                ("filters.Age Segment", 1),
                ("filters.Institution Type", 1),
                ("filters.Account/Policy Status", 1),
            ], unique=True, name=name,
        )
    return client, districts, kpis, runs


# ============================================================
# FILTERS AND DASHBOARD WAITING
# ============================================================

def wait_for_dashboard_update(page):
    updating = page.get_by_text("Updating...", exact=False)
    try:
        if updating.count() and updating.first.is_visible():
            updating.first.wait_for(state="hidden", timeout=PAGE_TIMEOUT_MS)
    except PlaywrightTimeoutError as exc:
        raise RuntimeError("Dashboard did not finish updating.") from exc
    page.wait_for_timeout(FILTER_SETTLE_MS)


def select_filter_option(page, filter_name: str, option_text: str):
    filter_index = FILTER_NAMES.index(filter_name)
    comboboxes = page.get_by_role("combobox")
    if comboboxes.count() <= filter_index:
        raise RuntimeError(f"Dropdown not found: {filter_name}")

    dropdown = comboboxes.nth(filter_index)
    control = dropdown.locator("xpath=ancestor::div[contains(@class, 'Select-control')]")
    control.click(timeout=5000)
    page.wait_for_timeout(200)

    options = page.locator(".VirtualizedSelectOption")
    for index in range(options.count()):
        option = options.nth(index)
        if option.is_visible() and option.inner_text().strip().casefold() == option_text.casefold():
            option.click()
            wait_for_dashboard_update(page)
            return

    page.keyboard.press("Escape")
    raise OptionNotAvailableError(f"Option {option_text!r} not found for {filter_name!r}")


class OptionNotAvailableError(RuntimeError):
    """The selected option is not present in the live filter control."""


def keep_location_at_all(page):
    comboboxes = page.get_by_role("combobox")
    if comboboxes.count() <= LOCATION_FILTER_INDEX:
        raise RuntimeError("Location dropdown not found; refusing to collect with unknown location scope.")
    dropdown = comboboxes.nth(LOCATION_FILTER_INDEX)
    control = dropdown.locator("xpath=ancestor::div[contains(@class, 'Select-control')]")
    control.click(timeout=5000)
    page.wait_for_timeout(200)
    options = page.locator(".VirtualizedSelectOption")
    for index in range(options.count()):
        option = options.nth(index)
        if option.is_visible() and option.inner_text().strip().casefold() == "all":
            option.click()
            wait_for_dashboard_update(page)
            return
    page.keyboard.press("Escape")
    raise RuntimeError("Could not set Location to All.")


def apply_filters(page, filters: dict[str, str]):
    for name, value in filters.items():
        select_filter_option(page, name, value)
    keep_location_at_all(page)


# ============================================================
# TABLE EXTRACTION AND PAGINATION
# ============================================================

def open_table_view(page):
    table = page.locator(TABLE_SELECTOR).first
    if table.count() and table.is_visible():
        return
    candidates = page.get_by_text("Click to view Table", exact=False)
    for index in range(candidates.count()):
        candidate = candidates.nth(index)
        if candidate.is_visible():
            candidate.click()
            page.locator(TABLE_SELECTOR).first.wait_for(state="visible", timeout=PAGE_TIMEOUT_MS)
            return
    raise RuntimeError("Could not open dashboard table view.")


def read_table_page(page):
    table = page.locator(TABLE_SELECTOR).first
    table.wait_for(state="visible", timeout=PAGE_TIMEOUT_MS)
    rows = []
    for row in table.locator("tr").all():
        cells = [cell.inner_text().strip() for cell in row.locator("th, td").all()]
        cells = [value for value in cells if value]
        if cells:
            rows.append(cells)
    if rows and [v.casefold() for v in rows[0][:3]] == ["district", "customers", "rank"]:
        rows = rows[1:]
    return rows


def table_page_signature(rows) -> str:
    return stable_hash(rows)


def reset_table_to_first_page(page):
    first = page.locator(FIRST_BUTTON_SELECTOR).first
    if not first.count() or first.is_disabled():
        return
    before = page.locator(f"{TABLE_SELECTOR} tr").all_inner_texts()
    first.click()
    try:
        page.wait_for_function(
            """before => {
                const table = document.querySelector('table.cell-table');
                if (!table) return false;
                const rows = Array.from(table.querySelectorAll('tr')).map(r => r.innerText.trim());
                return JSON.stringify(rows) !== JSON.stringify(before);
            }""",
            arg=before,
            timeout=PAGE_TIMEOUT_MS,
        )
    except PlaywrightTimeoutError:
        # It may already be on page one; this is safe only if table remains visible.
        if not page.locator(TABLE_SELECTOR).is_visible():
            raise RuntimeError("Table disappeared while resetting pagination.")


def parse_integer(value: str):
    cleaned = value.replace(",", "").strip()
    if not cleaned or not re.fullmatch(r"-?\d+", cleaned):
        return None
    return int(cleaned)


def collect_all_district_rows(page):
    all_rows = []
    seen_pages = set()
    seen_districts = set()

    for page_number in range(1, MAX_TABLE_PAGES + 1):
        rows = read_table_page(page)
        if not rows:
            raise EmptyDashboardTableError(f"Table has no data rows on page {page_number}.")

        signature = table_page_signature(rows)
        if signature in seen_pages:
            raise RuntimeError(f"Repeated table page detected at page {page_number}; refusing to save incomplete data.")
        seen_pages.add(signature)

        for raw_row in rows:
            if len(raw_row) < 3:
                raise RuntimeError(f"Malformed table row on page {page_number}: {raw_row!r}")
            district = raw_row[0].strip()
            customers = parse_integer(raw_row[1])
            rank = parse_integer(raw_row[2])
            if not district or customers is None or rank is None:
                raise RuntimeError(f"Could not parse district/customer/rank row: {raw_row!r}")
            if customers < 0 or rank < 1:
                raise RuntimeError(f"Invalid customers or rank in row: {raw_row!r}")
            normalized = district.casefold()
            if normalized in seen_districts:
                raise RuntimeError(f"District appears more than once across pages: {district!r}")
            seen_districts.add(normalized)
            all_rows.append({"district": district, "customers": customers, "rank": rank})

        next_button = page.locator(NEXT_BUTTON_SELECTOR).first
        if not next_button.count() or next_button.is_disabled():
            break
        before_signature = signature
        before_dom_rows = page.locator(f"{TABLE_SELECTOR} tr").all_inner_texts()
        next_button.click()
        try:
            page.wait_for_function(
                """before => {
                    const table = document.querySelector('table.cell-table');
                    if (!table) return false;
                    const rows = Array.from(table.querySelectorAll('tr')).map(r => r.innerText.trim());
                    return JSON.stringify(rows) !== JSON.stringify(before);
                }""",
                arg=before_dom_rows,
                timeout=PAGE_TIMEOUT_MS,
            )
        except PlaywrightTimeoutError as exc:
            raise RuntimeError(f"Next page did not change after page {page_number} (signature {before_signature[:10]}).") from exc
    else:
        raise RuntimeError(f"Reached pagination safety limit of {MAX_TABLE_PAGES} pages.")

    if not all_rows:
        raise EmptyDashboardTableError("Dashboard table returned no valid district observations.")
    return all_rows


class EmptyDashboardTableError(RuntimeError):
    """The table is visible but contains no data rows."""


# ============================================================
# KPI CAPTURE
# ============================================================


def capture_kpis(page):
    """Extract KPI values from their DOM card containers."""
    cards = page.locator(
        "#inclusion-content .card"
    )

    financially_included_percent = None
    total_customers = None
    kpi_cards = []

    for index in range(cards.count()):
        card = cards.nth(index)

        label_locator = card.locator(
            ".card-body h4.card-title"
        )
        value_locator = card.locator(
            ".card-body p.large-data"
        )

        if not label_locator.count() or not value_locator.count():
            continue

        label = label_locator.first.inner_text().strip()
        value = value_locator.first.inner_text().strip()

        if not label or not value:
            continue

        kpi_cards.append({
            "label": label,
            "value": value,
        })

        normalized_label = label.casefold()

        if normalized_label == "financially included":
            match = re.fullmatch(
                r"([\d,]+(?:\.\d+)?)\s*%",
                value,
            )
            if match:
                financially_included_percent = float(
                    match.group(1).replace(",", "")
                )

        elif normalized_label == "total customers":
            match = re.fullmatch(r"[\d,]+", value)
            if match:
                total_customers = int(value.replace(",", ""))

    return {
        "kpi_cards": kpi_cards,
        "total_customers": total_customers,
        "financially_included_percent": financially_included_percent,
        "kpi_capture_method": "dom_card_label_value",
    }


# ============================================================
# SNAPSHOTS, CHECKPOINTS, AND PERSISTENCE
# ============================================================

def is_combination_terminal(runs, snapshot_date, filters):
    run = runs.find_one({"snapshot_date": snapshot_date, "filters": filters})
    return bool(run and run.get("status") in {"complete", "completed_no_data", "not_applicable"})


def previous_snapshot_matches(runs, snapshot_date, filters, content_hash):
    previous = runs.find_one({
        "filters": filters,
        "snapshot_date": {"$lt": snapshot_date},
        "content_hash": content_hash,
        "status": "complete",
    }, sort=[("snapshot_date", -1)])
    return previous is not None, (previous.get("snapshot_date") if previous else None)


def save_combination(districts, kpis_collection, runs, snapshot_date, filters, district_rows, kpi_values):
    collected_at = now_local()
    # Hash only meaningful extracted content, never collection timestamps or metadata.
    content_payload = {
        "district_rows": sorted(district_rows, key=lambda row: row["district"].casefold()),
        "kpi_values": {
            "total_customers": kpi_values.get("total_customers"),
            "financially_included_percent": kpi_values.get("financially_included_percent"),
            "kpi_text": kpi_values.get("kpi_text", []),
        },
    }
    content_hash = stable_hash(content_payload)
    repeated, previous_date = previous_snapshot_matches(runs, snapshot_date, filters, content_hash)

    operations = []
    for row in district_rows:
        document = {
            "snapshot_date": snapshot_date,
            "collected_at": collected_at,
            "source_url": URL,
            "filters": filters,
            "location_filter": "All",
            "district": row["district"],
            "district_known": row["district"].strip().casefold() != "unknown",
            "customers": row["customers"],
            "rank": row["rank"],
            "content_hash": stable_hash(row),
            "combination_content_hash": content_hash,
        }
        operations.append(UpdateOne(
            {"snapshot_date": snapshot_date, "filters": filters, "district": row["district"]},
            {"$set": document}, upsert=True,
        ))
    if operations:
        districts.bulk_write(operations, ordered=False)

    kpi_document = {
        "snapshot_date": snapshot_date,
        "collected_at": collected_at,
        "source_url": URL,
        "filters": filters,
        "location_filter": "All",
        **kpi_values,
        "content_hash": stable_hash(content_payload["kpi_values"]),
        "combination_content_hash": content_hash,
        "repeated_snapshot_warning": repeated,
        "previous_matching_snapshot_date": previous_date,
    }
    kpis_collection.update_one(
        {"snapshot_date": snapshot_date, "filters": filters},
        {"$set": kpi_document}, upsert=True,
    )

    runs.update_one(
        {"snapshot_date": snapshot_date, "filters": filters},
        {"$set": {
            "snapshot_date": snapshot_date,
            "collected_at": collected_at,
            "filters": filters,
            "filters_key": filters_key(filters),
            "status": "complete",
            "district_rows": len(district_rows),
            "content_hash": content_hash,
            "repeated_snapshot_warning": repeated,
            "previous_matching_snapshot_date": previous_date,
            "source_url": URL,
            "error": None,
        }}, upsert=True,
    )
    return repeated, previous_date


def mark_terminal(runs, snapshot_date, filters, status, reason):
    runs.update_one(
        {"snapshot_date": snapshot_date, "filters": filters},
        {"$set": {
            "snapshot_date": snapshot_date,
            "filters": filters,
            "filters_key": filters_key(filters),
            "status": status,
            "reason": reason,
            "collected_at": now_local(),
            "source_url": URL,
        }}, upsert=True,
    )


def mark_failed(runs, snapshot_date, filters, error, attempt_count):
    runs.update_one(
        {"snapshot_date": snapshot_date, "filters": filters},
        {"$set": {
            "snapshot_date": snapshot_date,
            "filters": filters,
            "filters_key": filters_key(filters),
            "status": "failed",
            "error": f"{type(error).__name__}: {error}",
            "attempt_count": attempt_count,
            "failed_at": now_local(),
            "source_url": URL,
        }}, upsert=True,
    )


# ============================================================
# CSV EXPORTS
# ============================================================

def export_collection_csv(collection, filename, fields):
    output_path = OUTPUT_DIR / filename
    cursor = collection.find({}, {"_id": 0}).sort([("snapshot_date", 1), ("collected_at", 1)])
    with output_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for document in cursor:
            row = dict(document)
            if isinstance(row.get("filters"), dict):
                row["filters"] = json.dumps(row["filters"], ensure_ascii=False, sort_keys=True)
            for field in ("kpi_text",):
                if isinstance(row.get(field), list):
                    row[field] = " | ".join(row[field])
            writer.writerow(row)
    print("Exported:", output_path)


def export_all(districts, kpis_collection):
    export_collection_csv(districts, "district_observations.csv", [
        "snapshot_date", "collected_at", "source_url", "filters", "location_filter",
        "district", "district_known", "customers", "rank", "content_hash", "combination_content_hash",
    ])
    export_collection_csv(kpis_collection, "kpi_observations.csv", [
        "snapshot_date", "collected_at", "source_url", "filters", "location_filter",
        "kpi_text", "total_customers", "financially_included_percent", "kpi_capture_method",
        "content_hash", "combination_content_hash", "repeated_snapshot_warning", "previous_matching_snapshot_date",
    ])


# ============================================================
# MAIN
# ============================================================

def is_known_not_applicable(filters):
    return (filters["Institution Type"], filters["Account/Policy Status"]) in KNOWN_NOT_APPLICABLE


def is_known_no_data(filters):
    return (filters["Institution Type"], filters["Account/Policy Status"]) in KNOWN_NO_DATA


def main():
    client = None
    completed = skipped = failed = not_applicable = no_data = 0
    snapshot_date = current_snapshot_date()
    combinations = [dict(zip(FILTERS.keys(), values)) for values in itertools.product(*FILTERS.values())]
    limit_value = os.getenv("SCRAPER_MAX_COMBINATIONS", "").strip()
    if limit_value:
        try:
            limit = int(limit_value)
            if limit < 1:
                raise ValueError
        except ValueError as exc:
            raise RuntimeError("SCRAPER_MAX_COMBINATIONS must be a positive integer when set.") from exc
        combinations = combinations[:limit]

    print("NBR Financial Inclusion Dashboard — full snapshot scraper")
    print("URL:", URL)
    print("Snapshot date (Africa/Kigali):", snapshot_date)
    print("Filter combinations in this run:", len(combinations))
    if limit_value:
        print("TEST/LIMIT MODE: SCRAPER_MAX_COMBINATIONS=", limit_value)
    print("MongoDB database:", DATABASE_NAME)
    print("Output directory:", OUTPUT_DIR)

    try:
        client, districts, kpis_collection, runs = connect_mongodb()
        print("MongoDB connection successful.")

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.set_default_timeout(PAGE_TIMEOUT_MS)
            try:
                page.goto(URL, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_load_state("networkidle", timeout=60000)
                page.add_style_tag(content=MODAL_CSS)
                page.wait_for_timeout(1200)

                for index, filters in enumerate(combinations, start=1):
                    print(f"\n[{index}/{len(combinations)}] {filters}")

                    if is_combination_terminal(runs, snapshot_date, filters):
                        print("  Already has a terminal result for this snapshot; skipping.")
                        skipped += 1
                        continue

                    if is_known_not_applicable(filters):
                        mark_terminal(runs, snapshot_date, filters, "not_applicable", "This institution type does not offer this status option on the dashboard.")
                        print("  Not applicable; recorded without retrying.")
                        not_applicable += 1
                        continue

                    if is_known_no_data(filters):
                        mark_terminal(runs, snapshot_date, filters, "completed_no_data", "Confirmed on dashboard: this institution/status combination has no data.")
                        print("  Confirmed no-data combination; recorded without retrying.")
                        no_data += 1
                        continue

                    last_error = None
                    for attempt in range(1, MAX_RETRIES + 1):
                        try:
                            print(f"  Attempt {attempt}/{MAX_RETRIES}")
                            apply_filters(page, filters)
                            open_table_view(page)
                            reset_table_to_first_page(page)
                            kpi_values = capture_kpis(page)
                            district_rows = collect_all_district_rows(page)

                            repeated, previous_date = save_combination(
                                districts, kpis_collection, runs, snapshot_date,
                                filters, district_rows, kpi_values,
                            )
                            print(f"  Saved {len(district_rows)} district rows and one KPI observation.")
                            if kpi_values.get("total_customers") is None or kpi_values.get("financially_included_percent") is None:
                                print("  NOTE: At least one KPI number could not be confidently parsed; raw KPI text was retained.")
                            if repeated:
                                print(f"  Same extracted content as an earlier snapshot ({previous_date}); new date retained.")
                            completed += 1
                            last_error = None
                            break
                        except OptionNotAvailableError as exc:
                            # Known status incompatibilities are handled above. Unexpected missing options
                            # are not silently accepted as valid empty results.
                            last_error = exc
                            print(f"  FILTER ERROR: {exc}")
                            break
                        except EmptyDashboardTableError as exc:
                            last_error = exc
                            print(f"  EMPTY TABLE: {exc}")
                            if attempt < MAX_RETRIES:
                                time.sleep(attempt * 2)
                        except Exception as exc:
                            last_error = exc
                            print(f"  ERROR: {type(exc).__name__}: {exc}")
                            if attempt < MAX_RETRIES:
                                time.sleep(attempt * 2)

                    if last_error is not None:
                        mark_failed(runs, snapshot_date, filters, last_error, MAX_RETRIES)
                        failed += 1
                        print("  Marked failed; will retry on a later run for this same snapshot date.")

            finally:
                browser.close()

        export_all(districts, kpis_collection)
        print("\n--- SCRAPE SUMMARY ---")
        print("Snapshot date:", snapshot_date)
        print("Total combinations:", len(combinations))
        print("Completed with data this run:", completed)
        print("Skipped terminal combinations:", skipped)
        print("Not applicable:", not_applicable)
        print("Confirmed no data:", no_data)
        print("Failed:", failed)
        print("\nExisting snapshots and records were not deleted.")
        if failed:
            print("Fix the listed failure causes, then rerun. Completed and explicitly terminal combinations will be skipped for this date.")
    except PyMongoError as exc:
        print("MongoDB error:", exc)
        raise
    finally:
        if client is not None:
            client.close()


if __name__ == "__main__":
    main()
