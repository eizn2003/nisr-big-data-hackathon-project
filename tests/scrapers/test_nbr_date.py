import json
from pathlib import Path
from datetime import datetime, timezone

from playwright.sync_api import sync_playwright

URL = "https://fininclusion.bnr.rw/transactional"
TARGET_DATE = "2025-02-24"

PROJECT_ROOT = Path.cwd()
OUTPUT_DIR = PROJECT_ROOT / "data" / "raw" / "nbr"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def dismiss_disclaimer(page):
    close_button = page.locator("#close-disclaimer")
    if close_button.count() and close_button.is_visible():
        close_button.click()
        page.wait_for_timeout(1000)


def read_table(page):
    table = page.locator("table.cell-table")

    if not table.count():
        return []

    return table.locator("tr").evaluate_all("""
        rows => rows.map(row =>
            Array.from(row.querySelectorAll("th, td"))
                .map(cell => cell.innerText.trim())
        ).filter(row => row.length > 0)
    """)


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        try:
            print("Opening NBR dashboard...")
            page.goto(URL, wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(3000)
            dismiss_disclaimer(page)

            date_input = page.locator("#date")
            date_input.wait_for(state="visible")

            initial_date = date_input.input_value()
            print("Initially selected date:", initial_date)

            # Capture the current table for comparison.
            before_table = read_table(page)

            print(f"\nTrying to select {TARGET_DATE}...")
            date_input.click()
            date_input.fill(TARGET_DATE)
            date_input.press("Enter")
            date_input.press("Tab")

            # Allow the dashboard time to react to the selection.
            page.wait_for_timeout(5000)

            selected_date = date_input.input_value()
            after_table = read_table(page)

            result = {
                "requested_date": TARGET_DATE,
                "initial_date": initial_date,
                "selected_date_after_input": selected_date,
                "collection_timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "table_before": before_table,
                "table_after": after_table,
                "table_changed": before_table != after_table,
            }

            output_file = OUTPUT_DIR / "date_picker_test.json"
            output_file.write_text(
                json.dumps(result, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

            screenshot = OUTPUT_DIR / "date_picker_test.png"
            page.screenshot(path=str(screenshot), full_page=True)

            print("\n--- TEST RESULTS ---")
            print("Requested date:", TARGET_DATE)
            print("Date shown after selection:", selected_date)
            print("Table rows before:", len(before_table))
            print("Table rows after:", len(after_table))
            print("Table contents changed:", before_table != after_table)

            print("\nTable after selection:")
            for row in after_table[:8]:
                print(row)

            print("\nSaved test result:", output_file)
            print("Saved screenshot:", screenshot)

            if selected_date != TARGET_DATE:
                print(
                    "\nWARNING: The date input did not retain the "
                    "requested date. We need to inspect the calendar."
                )
            elif before_table == after_table:
                print(
                    "\nNOTE: The table did not change. This may mean "
                    "the snapshot is identical, the table is not yet "
                    "in view, or the date selection was not applied."
                )
            else:
                print("\nThe table changed after selecting the date.")

        finally:
            browser.close()


if __name__ == "__main__":
    main()
