from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import os
import re
import sys
import time
from datetime import date, datetime
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

# Date-selection settings (from the date-selection test script).
DEFAULT_DATES_FILE = (
    Path(__file__).resolve().parents[2] / "config" / "nbr_backfill_dates.txt"
)
DATE_INPUT_SELECTOR = "#date"
DATE_UPDATE_TIMEOUT_MS = 30_000
DATE_STABLE_CHECKS = 3
DATE_STABLE_DEADLINE_S = 45

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


def save_combination(districts, kpis_collection, runs, snapshot_date, filters, district_rows, kpi_values,
                     date_source="selected", dashboard_date=None):
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
            "run_date": collected_at.date().isoformat(),
            "date_source": date_source,
            "dashboard_date": dashboard_date,
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
        "run_date": collected_at.date().isoformat(),
        "date_source": date_source,
        "dashboard_date": dashboard_date,
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
            "run_date": collected_at.date().isoformat(),
            "date_source": date_source,
            "dashboard_date": dashboard_date,
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
        "snapshot_date", "run_date", "date_source", "dashboard_date", "collected_at", "source_url", "filters", "location_filter",
        "district", "district_known", "customers", "rank", "content_hash", "combination_content_hash",
    ])
    export_collection_csv(kpis_collection, "kpi_observations.csv", [
        "snapshot_date", "run_date", "date_source", "dashboard_date", "collected_at", "source_url", "filters", "location_filter",
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


# ============================================================
# DATE LIST AND DATE SELECTION
# ============================================================

def load_dates(path: Path) -> tuple[list[str], set[str]]:
    """Read dates (one per line; '#' starts a comment).

    Returns (dates, live_dates). A line saying `today` (or `latest`) means: do NOT
    touch the dashboard's date field; scrape what it currently shows and save it
    under the date this script ran on. Those dates are returned in live_dates.
    """
    today = now_local().date().isoformat()
    if not path.exists():
        return [], set()

    dates, seen, live, problems = [], set(), set(), []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        is_live = line.casefold() in {"today", "latest"}
        if is_live:
            line = today
        else:
            try:
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", line):
                    raise ValueError
                date.fromisoformat(line)
            except ValueError:
                problems.append(f"line {line_number}: {raw.strip()!r} is not a valid YYYY-MM-DD date")
                continue
        if line in seen:
            print(f"Note: duplicate date {line} on line {line_number} ignored.")
            continue
        seen.add(line)
        dates.append(line)
        if is_live:
            live.add(line)

    if problems:
        raise RuntimeError("Invalid entries in dates file:\n  " + "\n  ".join(problems))

    future = [d for d in dates if d > today]
    if future:
        print(f"WARNING: skipping future dates (today is {today}): {', '.join(future)}")
        dates = [d for d in dates if d <= today]
        if not dates:
            raise RuntimeError(f"No usable dates found in {path}")

    return sorted(dates), live  # ascending, so "previous snapshot" comparisons make sense


def wait_for_date_update(page):
    """Stricter wait used after a date change: indicators gone AND page text stable."""
    updating = page.get_by_text("Updating...", exact=False)
    try:
        for index in range(updating.count()):
            indicator = updating.nth(index)
            if indicator.is_visible():
                indicator.wait_for(state="hidden", timeout=DATE_UPDATE_TIMEOUT_MS)
    except PlaywrightTimeoutError as exc:
        raise RuntimeError("The dashboard's Updating indicator did not disappear.") from exc

    previous_text, stable_checks = None, 0
    deadline = time.monotonic() + DATE_STABLE_DEADLINE_S
    while time.monotonic() < deadline:
        current_text = page.locator("body").inner_text()
        if current_text == previous_text:
            stable_checks += 1
            if stable_checks >= DATE_STABLE_CHECKS:
                return
        else:
            stable_checks = 0
        previous_text = current_text
        time.sleep(1)
    raise RuntimeError(f"Dashboard text did not stabilize within {DATE_STABLE_DEADLINE_S} seconds.")


def read_selected_date(page) -> str:
    return page.locator(DATE_INPUT_SELECTOR).input_value().strip()


def select_date(page, target_date: str):
    """Select a date through the real input and confirm the field holds it."""
    date_input = page.locator(DATE_INPUT_SELECTOR)
    date_input.wait_for(state="visible", timeout=PAGE_TIMEOUT_MS)

    if read_selected_date(page) == target_date:
        return

    date_input.click()
    date_input.fill(target_date)
    date_input.press("Enter")
    wait_for_date_update(page)

    actual = read_selected_date(page)
    if actual != target_date:
        raise RuntimeError(f"Date selection failed: expected {target_date}, field contains {actual!r}.")


def assert_date_selected(page, target_date: str):
    """Guard against the dashboard silently reverting the date mid-scrape."""
    actual = read_selected_date(page)
    if actual != target_date:
        raise RuntimeError(f"Dashboard date changed unexpectedly: expected {target_date}, found {actual!r}.")


def load_dashboard(page):
    page.goto(URL, wait_until="domcontentloaded", timeout=60000)
    try:
        page.wait_for_load_state("networkidle", timeout=60000)
    except PlaywrightTimeoutError:
        print("  Network still active; continuing.")
    page.add_style_tag(content=MODAL_CSS)
    page.wait_for_timeout(1200)


# ============================================================
# MAIN
# ============================================================

def is_known_not_applicable(filters):
    return (filters["Institution Type"], filters["Account/Policy Status"]) in KNOWN_NOT_APPLICABLE


def is_known_no_data(filters):
    return (filters["Institution Type"], filters["Account/Policy Status"]) in KNOWN_NO_DATA


def scrape_combination(page, districts, kpis_collection, runs, snapshot_date, filters, live=False):
    """One combination with retries. Returns (status, repeated_flag, error)."""
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"  Attempt {attempt}/{MAX_RETRIES}")
            # Re-select the date if anything reset it (no-op when already correct).
            if not live:
                select_date(page, snapshot_date)
            apply_filters(page, filters)
            if not live:
                assert_date_selected(page, snapshot_date)
            open_table_view(page)
            reset_table_to_first_page(page)
            kpi_values = capture_kpis(page)
            district_rows = collect_all_district_rows(page)

            # Never save data under a date the dashboard is no longer showing.
            if not live:
                assert_date_selected(page, snapshot_date)

            repeated, previous_date = save_combination(
                districts, kpis_collection, runs, snapshot_date,
                filters, district_rows, kpi_values,
                date_source="live_run_date" if live else "selected",
                dashboard_date=read_selected_date(page),
            )
            print(f"  Saved {len(district_rows)} district rows and one KPI observation.")
            if kpi_values.get("total_customers") is None or kpi_values.get("financially_included_percent") is None:
                print("  NOTE: At least one KPI number could not be confidently parsed; raw KPI text was retained.")
            if repeated:
                print(f"  Same extracted content as an earlier snapshot ({previous_date}); new date retained.")
            return "complete", repeated, None
        except OptionNotAvailableError as exc:
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
    return "failed", False, last_error


def main():
    parser = argparse.ArgumentParser(description="Backfill NBR financial inclusion data for a list of dates.")
    parser.add_argument("--dates-file", type=Path, default=DEFAULT_DATES_FILE,
                        help=f"Text file with one YYYY-MM-DD date per line (default: {DEFAULT_DATES_FILE.name} next to this script).")
    parser.add_argument("--today", action="store_true",
                        help="Also scrape the dashboard as it currently stands, saved under today's run date.")
    parser.add_argument("--headed", action="store_true", help="Show the browser window (for debugging).")
    args = parser.parse_args()

    dates, live_dates = load_dates(args.dates_file)
    today_iso = now_local().date().isoformat()
    if args.today and today_iso not in dates:
        dates = sorted(dates + [today_iso])
        live_dates.add(today_iso)
    if not dates:
        print(f"No dates found in {args.dates_file}; running a live snapshot saved under today's date ({today_iso}).")
        dates, live_dates = [today_iso], {today_iso}
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

    print("NBR Financial Inclusion Dashboard — multi-date backfill scraper")
    print("URL:", URL)
    print("Dates file:", args.dates_file)
    print(f"Dates to process ({len(dates)}):", ", ".join(dates))
    print("Filter combinations per date:", len(combinations))
    if limit_value:
        print("TEST/LIMIT MODE: SCRAPER_MAX_COMBINATIONS=", limit_value)
    print("MongoDB database:", DATABASE_NAME)
    print("Output directory:", OUTPUT_DIR)

    client = None
    totals = dict(completed=0, skipped=0, failed=0, not_applicable=0, no_data=0)
    date_summaries = {}   # date -> dict
    failed_dates = []     # dates whose selection never verified

    try:
        client, districts, kpis_collection, runs = connect_mongodb()
        print("MongoDB connection successful.")

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=not args.headed)
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.set_default_timeout(PAGE_TIMEOUT_MS)
            try:
                load_dashboard(page)

                for date_index, snapshot_date in enumerate(dates, start=1):
                    print("\n" + "=" * 60)
                    live = snapshot_date in live_dates
                    print(f"DATE [{date_index}/{len(dates)}]: {snapshot_date}"
                          + ("  (LIVE: dashboard date untouched, saved under run date)" if live else ""))
                    print("=" * 60)

                    stats = dict(completed=0, skipped=0, failed=0, not_applicable=0, no_data=0, repeated=0)
                    date_summaries[snapshot_date] = stats

                    # Skip the whole date (and the browser work) if everything is already terminal.
                    pending = []
                    for filters in combinations:
                        if is_combination_terminal(runs, snapshot_date, filters):
                            stats["skipped"] += 1
                        else:
                            pending.append(filters)
                    if not pending:
                        print("All combinations already have terminal results; skipping date.")
                        for key in ("skipped",):
                            totals[key] += stats[key]
                        continue

                    # Select and verify the date BEFORE scraping anything.
                    date_ok = False
                    if live:
                        # Fresh page load = the dashboard's own default date; never select a date.
                        try:
                            load_dashboard(page)
                            print(f"Live mode: dashboard is showing {read_selected_date(page)!r}; "
                                  f"saving as snapshot_date {snapshot_date}.")
                            date_ok = True
                        except Exception as exc:
                            print(f"  LOAD ERROR: {type(exc).__name__}: {exc}")
                    for attempt in range(1, MAX_RETRIES + 1):
                        if date_ok:
                            break
                        try:
                            print(f"Selecting date (attempt {attempt}/{MAX_RETRIES})...")
                            if attempt > 1:
                                load_dashboard(page)
                            select_date(page, snapshot_date)
                            print(f"Date confirmed: {read_selected_date(page)}")
                            date_ok = True
                            break
                        except Exception as exc:
                            print(f"  DATE ERROR: {type(exc).__name__}: {exc}")
                            if attempt < MAX_RETRIES:
                                time.sleep(attempt * 2)
                    if not date_ok:
                        print(f"Could not select {snapshot_date}; NOT scraping it, to avoid saving data under the wrong date.")
                        failed_dates.append(snapshot_date)
                        continue

                    for index, filters in enumerate(pending, start=1):
                        print(f"\n[{snapshot_date}] [{index}/{len(pending)}] {filters}")

                        if is_known_not_applicable(filters):
                            mark_terminal(runs, snapshot_date, filters, "not_applicable",
                                          "This institution type does not offer this status option on the dashboard.")
                            print("  Not applicable; recorded without retrying.")
                            stats["not_applicable"] += 1
                            continue

                        if is_known_no_data(filters):
                            mark_terminal(runs, snapshot_date, filters, "completed_no_data",
                                          "Confirmed on dashboard: this institution/status combination has no data.")
                            print("  Confirmed no-data combination; recorded without retrying.")
                            stats["no_data"] += 1
                            continue

                        status, repeated, error = scrape_combination(
                            page, districts, kpis_collection, runs, snapshot_date, filters, live=live,
                        )
                        if status == "complete":
                            stats["completed"] += 1
                            stats["repeated"] += int(bool(repeated))
                        else:
                            mark_failed(runs, snapshot_date, filters, error, MAX_RETRIES)
                            stats["failed"] += 1
                            print("  Marked failed; will retry on a later run for this same snapshot date.")

                    for key in totals:
                        totals[key] += stats[key]

                    if stats["completed"] and stats["repeated"] == stats["completed"]:
                        print(f"\nWARNING: every combination scraped for {snapshot_date} is identical to an earlier date. "
                              "The date field changed, but please confirm the dashboard data really did.")
            finally:
                browser.close()

        export_all(districts, kpis_collection)

        print("\n--- BACKFILL SUMMARY ---")
        print(f"{'Date':<12}{'Saved':>7}{'Skipped':>9}{'N/A':>6}{'NoData':>8}{'Failed':>8}{'Repeat':>8}")
        for snapshot_date in dates:
            s = date_summaries.get(snapshot_date)
            if s is None or snapshot_date in failed_dates:
                print(f"{snapshot_date:<12}  DATE SELECTION FAILED")
                continue
            print(f"{snapshot_date:<12}{s['completed']:>7}{s['skipped']:>9}{s['not_applicable']:>6}"
                  f"{s['no_data']:>8}{s['failed']:>8}{s['repeated']:>8}")
        print("\nTotals:", totals)
        if failed_dates:
            print("Dates that could not be selected:", ", ".join(failed_dates))
        print("\nExisting snapshots and records were not deleted.")
        if totals["failed"] or failed_dates:
            print("Rerun the script: completed and terminal combinations are skipped, so only the failures are retried.")
    except PyMongoError as exc:
        print("MongoDB error:", exc)
        raise
    finally:
        if client is not None:
            client.close()

    if totals["failed"] or failed_dates:
        sys.exit(1)


if __name__ == "__main__":
    main()
