from __future__ import annotations

import time

from playwright.sync_api import (
    sync_playwright,
    TimeoutError as PlaywrightTimeoutError,
)

URL = "https://fininclusion.bnr.rw/inclusion"
TARGET_DATE = "2026-09-14"
TIMEOUT_MS = 30_000

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


def wait_for_dashboard_update(page):
    """Wait for loading indicators to disappear and page text to stabilize."""
    print("Waiting for the dashboard to finish updating...")

    updating = page.get_by_text("Updating...", exact=False)

    try:
        for index in range(updating.count()):
            indicator = updating.nth(index)

            if indicator.is_visible():
                indicator.wait_for(
                    state="hidden",
                    timeout=TIMEOUT_MS,
                )

    except PlaywrightTimeoutError as exc:
        raise RuntimeError(
            "The dashboard's Updating indicator did not disappear."
        ) from exc

    previous_text = None
    stable_checks = 0
    deadline = time.monotonic() + 45

    while time.monotonic() < deadline:
        current_text = page.locator("body").inner_text()

        if current_text == previous_text:
            stable_checks += 1

            if stable_checks >= 3:
                print("Dashboard text appears stable.")
                return
        else:
            stable_checks = 0

        previous_text = current_text
        time.sleep(1)

    raise RuntimeError("Dashboard text did not stabilize within 45 seconds.")


def main():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)

        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.set_default_timeout(10_000)

        try:
            print("Opening NBR Financial Inclusion dashboard...")

            page.goto(
                URL,
                wait_until="domcontentloaded",
                timeout=60_000,
            )

            try:
                page.wait_for_load_state(
                    "networkidle",
                    timeout=30_000,
                )
            except PlaywrightTimeoutError:
                print("Network still active; continuing.")

            # Hide the blocking introductory modal in this test only.
            page.add_style_tag(content=MODAL_CSS)
            page.wait_for_timeout(1000)

            date_input = page.locator("#date")
            date_input.wait_for(state="visible")

            original_date = date_input.input_value()
            print(f"Initial date: {original_date}")

            # Attempt to select a date through the actual input.
            print(f"Selecting target date: {TARGET_DATE}")

            date_input.click()
            date_input.fill(TARGET_DATE)
            date_input.press("Enter")

            wait_for_dashboard_update(page)

            selected_date = date_input.input_value()

            print("\n" + "=" * 55)
            print("DATE-SELECTION TEST RESULTS")
            print("=" * 55)
            print(f"Initial date:  {original_date}")
            print(f"Target date:   {TARGET_DATE}")
            print(f"Selected date: {selected_date}")

            if selected_date != TARGET_DATE:
                raise AssertionError(
                    f"Date selection failed: expected {TARGET_DATE}, "
                    f"but the field contains {selected_date}."
                )

            print("\nPASS: The date field shows the requested date.")
            print(
                "Please inspect the dashboard results to confirm "
                "they correspond to the selected date."
            )

            input("\nPress Enter to close the browser...")

        finally:
            browser.close()


if __name__ == "__main__":
    main()
