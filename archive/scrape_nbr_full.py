from pathlib import Path
from datetime import datetime, timezone
import csv
import json

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = PROJECT_ROOT / "data" / "raw" / "nbr"

URL = "https://fininclusion.bnr.rw/touchpoints/cards"

FILTER_NAMES = [
    "Gender",
    "Age Segment",
    "Institution Type",
    "Card Status",
    "Credit Product",
    "Card Type",
    "Location",
]

TABLE_VIEW_TEXT = "Click to view table"
TABLE_SELECTOR = "table.cell-table"
NEXT_BUTTON_SELECTOR = "button.next-page"


# --------------------------------------------------
# HELPERS
# --------------------------------------------------


def dismiss_disclaimer(page):
    """Dismiss the dashboard disclaimer if present."""
    button = page.locator("#close-disclaimer")

    if button.count() > 0 and button.is_visible():
        print("Dismissing dashboard disclaimer...")
        button.click()
        page.wait_for_timeout(1000)


def save_page_snapshot(page):
    """Save the dashboard HTML and screenshot."""
    html_path = OUTPUT_DIR / "nbr_dashboard.html"
    screenshot_path = OUTPUT_DIR / "nbr_dashboard.png"

    html_path.write_text(page.content(), encoding="utf-8")
    page.screenshot(path=str(screenshot_path), full_page=True)

    print("\n--- PAGE SNAPSHOT ---")
    print("HTML saved:", html_path)
    print("Screenshot saved:", screenshot_path)


def switch_to_table_view(page):
    """Open the dashboard's table view."""
    print("\n--- SWITCHING TO TABLE VIEW ---")

    candidates = page.get_by_text(TABLE_VIEW_TEXT, exact=False)

    for index in range(candidates.count()):
        candidate = candidates.nth(index)

        if candidate.is_visible():
            candidate.click()
            page.wait_for_timeout(1000)
            print("Table-view control clicked.")
            return

    # The table may already be active.
    if page.locator(TABLE_SELECTOR).count() > 0:
        print("Table already present; continuing.")
        return

    raise RuntimeError("Could not find the table-view control.")


def read_table(page):
    """Read headers and currently visible table rows."""
    table = page.locator(TABLE_SELECTOR).first

    if table.count() == 0:
        raise RuntimeError("Dashboard table was not found.")

    headers = [value.strip() for value in table.locator("thead th").all_inner_texts()]

    if not headers:
        headers = [value.strip() for value in table.locator("th").all_inner_texts()]

    rows = []

    for row in table.locator("tbody tr").all():
        values = [cell.inner_text().strip() for cell in row.locator("th, td").all()]

        if not values:
            continue

        # Ignore repeated header rows.
        if headers and values == headers:
            continue

        rows.append(values)

    return headers, rows


def extract_all_table_pages(page):
    """Collect rows from every table page and save one CSV."""
    print("\n--- PAGINATED TABLE EXTRACTION ---")

    headers, current_rows = read_table(page)

    if not headers:
        raise RuntimeError("Table headers could not be identified.")

    all_rows = []
    seen_rows = set()
    seen_page_signatures = set()
    page_number = 1
    max_pages = 100

    while True:
        headers_now, current_rows = read_table(page)

        if headers_now != headers:
            raise RuntimeError(
                "Table columns changed during pagination. "
                "Stopping to avoid mixing different tables."
            )

        signature = tuple(tuple(row) for row in current_rows)

        if signature in seen_page_signatures:
            print(
                f"Page {page_number}: repeated page contents detected. "
                "Stopping to prevent an infinite loop."
            )
            break

        seen_page_signatures.add(signature)

        added_this_page = 0

        for row in current_rows:
            row_key = tuple(row)

            if row_key not in seen_rows:
                seen_rows.add(row_key)
                all_rows.append(row)
                added_this_page += 1

        print(
            f"Page {page_number}: {len(current_rows)} rows visible; "
            f"{added_this_page} new rows added."
        )

        next_button = page.locator(NEXT_BUTTON_SELECTOR)

        if next_button.count() == 0:
            print("Next-page button not found; stopping.")
            break

        if next_button.is_disabled():
            print("Next-page button is disabled. Last page reached.")
            break

        if page_number >= max_pages:
            print(f"Safety limit of {max_pages} pages reached.")
            break

        previous_signature = signature

        next_button.click()

        # Wait until the table contents change.
        try:
            page.wait_for_function(
                """({selector, previous}) => {
                    const table = document.querySelector(selector);
                    if (!table) return false;

                    const rows = Array.from(
                        table.querySelectorAll("tbody tr")
                    ).map(row =>
                        Array.from(row.querySelectorAll("th, td"))
                            .map(cell => cell.innerText.trim())
                    );

                    return JSON.stringify(rows) !== previous;
                }""",
                arg={
                    "selector": TABLE_SELECTOR,
                    "previous": json.dumps(previous_signature),
                },
                timeout=10000,
            )
        except PlaywrightTimeoutError:
            print(
                "Table contents did not change after clicking Next. " "Stopping safely."
            )
            break

        page_number += 1

    csv_path = OUTPUT_DIR / "district_customer_ranking.csv"

    with csv_path.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as file:
        writer = csv.writer(file)
        writer.writerow(headers)
        writer.writerows(all_rows)

    print("\n--- EXTRACTION SUMMARY ---")
    print("Pages visited:", page_number)
    print("Unique rows collected:", len(all_rows))
    print("Columns:", headers)
    print("First five rows:", all_rows[:5])
    print("Saved CSV:", csv_path)

    return all_rows


def discover_filter_options(page):
    """Inspect the visible options for each dashboard filter."""
    print("\n--- ALL FILTER OPTIONS ---")

    filter_options = {}
    comboboxes = page.get_by_role("combobox")

    print("Comboboxes found:", comboboxes.count())

    for index, filter_name in enumerate(FILTER_NAMES):
        print(f"\n{filter_name}:")

        if index >= comboboxes.count():
            print("  Corresponding dropdown not found.")
            filter_options[filter_name] = []
            continue

        dropdown_input = comboboxes.nth(index)

        control = dropdown_input.locator(
            "xpath=ancestor::div[contains(@class, 'Select-control')]"
        )

        try:
            control.click(timeout=5000)
            page.wait_for_timeout(300)

            options = page.locator(".VirtualizedSelectOption")
            visible_options = []

            for option_index in range(options.count()):
                option = options.nth(option_index)

                if not option.is_visible():
                    continue

                value = option.inner_text().strip()

                if value and value not in visible_options:
                    visible_options.append(value)

            filter_options[filter_name] = visible_options

            print(
                "  Options visible:",
                visible_options or "None detected",
            )

        except Exception as error:
            filter_options[filter_name] = []
            print(f"  Could not inspect dropdown: {error}")

        finally:
            page.keyboard.press("Escape")
            page.wait_for_timeout(200)

    options_path = OUTPUT_DIR / "filter_options.json"

    options_path.write_text(
        json.dumps(filter_options, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("\nSaved filter options:", options_path)


# --------------------------------------------------
# MAIN
# --------------------------------------------------


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Opening: {URL}")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)

        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})

            page.goto(
                URL,
                wait_until="networkidle",
                timeout=60000,
            )

            page.wait_for_timeout(3000)
            dismiss_disclaimer(page)

            print("\nPage title:", page.title())
            print(
                "Inspection timestamp (UTC):",
                datetime.now(timezone.utc).isoformat(),
            )

            save_page_snapshot(page)
            switch_to_table_view(page)
            extract_all_table_pages(page)
            discover_filter_options(page)

            print("\n--- SUMMARY ---")
            print("Total tables:", page.locator("table").count())
            print("Filters inspected:", len(FILTER_NAMES))

        finally:
            browser.close()


if __name__ == "__main__":
    main()
