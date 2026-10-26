import json
from pathlib import Path

from playwright.sync_api import sync_playwright

# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

URL = "https://fininclusion.bnr.rw/inclusion"

PROJECT_ROOT = Path(__file__).resolve().parents[3]
OUTPUT_DIR = PROJECT_ROOT / "data" / "raw" / "nbr" / "inclusion"

OUTPUT_FILE = OUTPUT_DIR / "filter_options.json"
SCREENSHOT_FILE = OUTPUT_DIR / "filter_inspection.png"

FILTERS = [
    "Gender",
    "Age Segment",
    "Institution Type",
    "Account/Policy Status",
    "Location",
]

# Hide the disclaimer modal so it cannot intercept filter clicks.
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


# --------------------------------------------------
# FILTER INSPECTION
# --------------------------------------------------


def inspect_filter_options(page):
    """Open each filter and collect its visible dropdown options."""

    filter_options = {}
    comboboxes = page.get_by_role("combobox")

    print("\n--- INCLUSION FILTER OPTIONS ---")
    print("Comboboxes found:", comboboxes.count())

    for index, filter_name in enumerate(FILTERS):
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

    return filter_options


# --------------------------------------------------
# MAIN
# --------------------------------------------------


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Opening:", URL)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)

        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})

            page.goto(
                URL,
                wait_until="domcontentloaded",
                timeout=60000,
            )

            page.wait_for_timeout(3000)

            # Remove the disclaimer overlay if present.
            page.add_style_tag(content=MODAL_CSS)
            page.wait_for_timeout(500)

            # Wait for the dashboard's filter controls.
            page.get_by_role("combobox").first.wait_for(
                state="visible",
                timeout=30000,
            )

            print("Dashboard loaded.")

            filter_options = inspect_filter_options(page)

            # Save a screenshot for troubleshooting if needed.
            page.screenshot(
                path=str(SCREENSHOT_FILE),
                full_page=True,
            )

            # Save the discovered options.
            OUTPUT_FILE.write_text(
                json.dumps(
                    filter_options,
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            print("\n--- SUMMARY ---")

            for filter_name, options in filter_options.items():
                print(f"{filter_name}: {len(options)} options")

            print("\nSaved options:", OUTPUT_FILE)
            print("Saved screenshot:", SCREENSHOT_FILE)

        finally:
            browser.close()


if __name__ == "__main__":
    main()
