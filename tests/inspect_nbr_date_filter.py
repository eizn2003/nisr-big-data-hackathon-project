from __future__ import annotations

import time
from pathlib import Path

from playwright.sync_api import (
    sync_playwright,
    TimeoutError as PlaywrightTimeoutError,
)

URL = "https://fininclusion.bnr.rw/inclusion"
TIMEOUT_MS = 30_000


def print_date_related_controls(page):
    """Inspect likely date controls without changing their values."""
    print("\n" + "=" * 65)
    print("DATE-RELATED CONTROLS")
    print("=" * 65)

    selectors = [
        "input",
        "select",
        "button",
        "[role='combobox']",
        "[role='button']",
        "[aria-haspopup]",
        "[class*='date' i]",
        "[class*='calendar' i]",
    ]

    seen = set()

    for selector in selectors:
        elements = page.locator(selector)

        try:
            count = min(elements.count(), 100)
        except Exception:
            continue

        for index in range(count):
            element = elements.nth(index)

            try:
                if not element.is_visible():
                    continue

                html = element.evaluate("(el) => el.outerHTML")

                # Avoid printing identical elements repeatedly.
                if html in seen:
                    continue
                seen.add(html)

                text = " ".join(element.inner_text(timeout=1000).split())[:100]

                # Print all inputs/selects and elements that look
                # relevant to date selection.
                relevant = selector in ("input", "select") or any(
                    word in html.lower()
                    for word in (
                        "date",
                        "calendar",
                        "datepicker",
                        "datetime",
                        "start-date",
                        "end-date",
                    )
                )

                if relevant:
                    print(f"\nSelector: {selector}")
                    if text:
                        print(f"Visible text: {text}")
                    print(f"HTML: {html[:1200]}")

            except Exception:
                continue


def wait_for_dashboard_update(page):
    """Wait for visible loading indicators and stable page text."""
    print("\nWaiting for the dashboard to finish updating...")

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

    # Some updates may not expose an Updating indicator.
    # Require the visible page text to stabilize instead.
    previous_text = None
    stable_checks = 0
    deadline = time.monotonic() + 30

    while time.monotonic() < deadline:
        current_text = page.locator("body").inner_text()

        if current_text == previous_text:
            stable_checks += 1
        else:
            stable_checks = 0

        if stable_checks >= 3:
            print("Dashboard text appears stable.")
            return

        previous_text = current_text
        time.sleep(1)

    raise RuntimeError("Dashboard text did not stabilize within 30 seconds.")


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
                print("Network did not become idle; " "continuing with DOM inspection.")

            page.wait_for_timeout(1500)

            print_date_related_controls(page)

            before_text = page.locator("body").inner_text()

            print("\n" + "=" * 65)
            print("MANUAL DATE-SELECTION TEST")
            print("=" * 65)
            print("1. Use the open browser to find the dashboard's date filter.")
            print(
                "2. Select a different historical date, preferably "
                "one month before the current selection."
            )
            print("3. Wait for the dashboard to display its updated results.")
            input(
                "\nAfter selecting the date and seeing the results, "
                "press Enter here..."
            )

            wait_for_dashboard_update(page)

            after_text = page.locator("body").inner_text()

            print("\n" + "=" * 65)
            print("TEST RESULTS")
            print("=" * 65)
            print(
                "Visible page text changed:",
                before_text != after_text,
            )

            if before_text == after_text:
                print(
                    "WARNING: The visible text is unchanged. "
                    "The date may not have changed, or the displayed "
                    "values may be identical."
                )
            else:
                print("\nUpdated page text (first 2500 characters):")
                print(after_text[:2500])

            print_date_related_controls(page)

            input("\nPress Enter to close the browser...")

        finally:
            browser.close()


if __name__ == "__main__":
    main()
