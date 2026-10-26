
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

URL = "https://fininclusion.bnr.rw/inclusion"

MODAL_CSS = """
.modal, .modal.show, .modal-backdrop, [role="dialog"] {
    display: none !important;
    visibility: hidden !important;
    pointer-events: none !important;
}
body {
    overflow: auto !important;
}
"""

FILTERS = {
    "Gender": ["All", "Female", "Male"],
    "Age Segment": ["All", "Youth", "Non-Youth"],
    "Institution Type": [
        "All", "Banks", "E-money issuers",
        "Insurance", "Microfinance", "Sacco",
    ],
    "Account/Policy Status": [
        "Active", "Matured", "Dormant", "Inactive",
    ],
}

# Representative combinations, not an exhaustive combination test.
TEST_CASES = [
    {
        "Gender": "All",
        "Age Segment": "All",
        "Institution Type": "All",
        "Account/Policy Status": "Active",
    },
    {
        "Gender": "Female",
        "Age Segment": "Youth",
        "Institution Type": "Banks",
        "Account/Policy Status": "Active",
    },
    {
        "Gender": "Male",
        "Age Segment": "Non-Youth",
        "Institution Type": "Sacco",
        "Account/Policy Status": "Dormant",
    },
]

LOCATION_FILTER_INDEX = 4
TABLE_SELECTOR = "table.cell-table"
NEXT_BUTTON_SELECTOR = "button.next-page"


def select_filter_option(page, filter_name, option_text):
    """Select an option from a dashboard dropdown."""
    comboboxes = page.get_by_role("combobox")
    filter_index = list(FILTERS).index(filter_name)

    if comboboxes.count() <= filter_index:
        raise RuntimeError(
            f"Could not find dropdown for {filter_name!r}."
        )

    dropdown = comboboxes.nth(filter_index)
    control = dropdown.locator(
        "xpath=ancestor::div[contains(@class, 'Select-control')]"
    )

    control.click(timeout=5000)
    page.wait_for_timeout(300)

    options = page.locator(".VirtualizedSelectOption")
    found = False

    for index in range(options.count()):
        option = options.nth(index)

        if not option.is_visible():
            continue

        text = option.inner_text().strip()

        if text.casefold() == option_text.casefold():
            option.click()
            found = True
            break

    if not found:
        page.keyboard.press("Escape")
        raise RuntimeError(
            f"Option {option_text!r} not found in {filter_name!r}."
        )

    # Allow the dashboard to process the filter change.
    page.wait_for_timeout(1000)
    print(f"  Selected {filter_name}: {option_text}")


def keep_location_at_all(page):
    """Keep the Location dropdown set to All."""
    comboboxes = page.get_by_role("combobox")

    if comboboxes.count() <= LOCATION_FILTER_INDEX:
        raise RuntimeError("Could not find the Location dropdown.")

    dropdown = comboboxes.nth(LOCATION_FILTER_INDEX)
    control = dropdown.locator(
        "xpath=ancestor::div[contains(@class, 'Select-control')]"
    )

    control.click(timeout=5000)
    page.wait_for_timeout(300)

    options = page.locator(".VirtualizedSelectOption")

    for index in range(options.count()):
        option = options.nth(index)

        if option.is_visible() and option.inner_text().strip().casefold() == "all":
            option.click()
            page.wait_for_timeout(1000)
            print("  Location: All")
            return

    page.keyboard.press("Escape")
    raise RuntimeError("Could not find 'All' in the Location dropdown.")


def wait_for_dashboard_update(page):
    """Wait for the dashboard to finish its visible update, if indicated."""
    updating = page.get_by_text("Updating...", exact=False)

    try:
        if updating.count() > 0:
            updating.first.wait_for(state="hidden", timeout=15000)
    except PlaywrightTimeoutError:
        raise RuntimeError(
            "Dashboard remained in its Updating state for too long."
        )


def open_table_view(page):
    """Open the dashboard's table view."""
    candidates = page.get_by_text("Click to view table", exact=False)

    for index in range(candidates.count()):
        candidate = candidates.nth(index)

        if candidate.is_visible():
            candidate.click()
            page.locator(TABLE_SELECTOR).wait_for(
                state="visible", timeout=15000
            )
            page.wait_for_timeout(500)
            return

    if page.locator(TABLE_SELECTOR).is_visible():
        return

    raise RuntimeError("Could not open the inclusion table.")


def read_current_page(page):
    """Read the current table page, including tables without a thead."""
    table = page.locator(TABLE_SELECTOR).first

    if table.count() == 0:
        raise RuntimeError("Inclusion table was not found.")

    rows = []

    for row in table.locator("tr").all():
        values = [
            cell.inner_text().strip()
            for cell in row.locator("th, td").all()
        ]
        values = [value for value in values if value]

        if values:
            rows.append(values)

    # Some dashboard tables place headings in the first table row.
    if rows and [v.casefold() for v in rows[0][:3]] == [
        "district", "customers", "rank"
    ]:
        rows = rows[1:]

    return rows


def wait_for_page_change(page, previous_rows):
    """Wait until the table's visible row contents change after pagination."""
    previous_text = "\n".join(previous_rows)

    page.wait_for_function(
        """previousText => {
            const table = document.querySelector("table.cell-table");
            if (!table) return false;

            const currentText = Array.from(
                table.querySelectorAll("tr")
            ).map(row => row.innerText.trim()).join("\\n");

            return currentText !== previousText;
        }""",
        arg=previous_text,
        timeout=15000,
    )


def extract_all_table_pages(page):
    """Collect unique district rows from every available table page."""
    all_rows = []
    seen_rows = set()
    seen_pages = set()

    for page_number in range(100):
        rows = read_current_page(page)

        if not rows:
            print("  No rows on current page; stopping.")
            break

        signature = tuple(tuple(row) for row in rows)

        if signature in seen_pages:
            print("  Repeated page detected; stopping pagination.")
            break

        seen_pages.add(signature)

        for row in rows:
            row_key = tuple(row)

            if row_key not in seen_rows:
                seen_rows.add(row_key)
                all_rows.append(row)

        print(
            f"  Table page {page_number + 1}: "
            f"{len(rows)} rows; {len(all_rows)} unique rows collected"
        )

        next_button = page.locator(NEXT_BUTTON_SELECTOR)

        if next_button.count() == 0 or next_button.is_disabled():
            break

        previous_rows = page.locator(
            f"{TABLE_SELECTOR} tr"
        ).all_inner_texts()

        next_button.click()

        try:
            wait_for_page_change(page, previous_rows)
        except PlaywrightTimeoutError:
            # Do not silently assume pagination succeeded.
            print("  WARNING: Table did not visibly change after Next.")
            break

    return all_rows


def run_test_case(page, case_number, filters):
    print(f"\n--- TEST CASE {case_number} ---")

    for filter_name, option in filters.items():
        select_filter_option(page, filter_name, option)

    keep_location_at_all(page)
    wait_for_dashboard_update(page)

    print("Selected combination:", filters)

    open_table_view(page)
    rows = extract_all_table_pages(page)

    print(f"District rows collected: {len(rows)}")

    for row in rows[:5]:
        print(" ", row)

    if not rows:
        raise AssertionError(
            f"No district rows collected for test case {case_number}."
        )

    return rows


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            viewport={"width": 1440, "height": 1000}
        )

        try:
            print("Opening:", URL)
            page.goto(
                URL,
                wait_until="networkidle",
                timeout=60000,
            )
            page.add_style_tag(content=MODAL_CSS)
            page.wait_for_timeout(1500)

            results = []

            for case_number, filters in enumerate(TEST_CASES, start=1):
                rows = run_test_case(page, case_number, filters)
                results.append({
                    "filters": filters,
                    "row_count": len(rows),
                    "rows": rows,
                })

            print("\n--- TEST SUMMARY ---")
            for index, result in enumerate(results, start=1):
                print(
                    f"Case {index}: "
                    f"{result['row_count']} rows; "
                    f"filters={result['filters']}"
                )

            print("\nAll representative combinations returned table rows.")

        finally:
            browser.close()


if __name__ == "__main__":
    main()
