import csv
import json
import re
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

URL = "https://fininclusion.bnr.rw/inclusion"

OUTPUT_DIR = Path("data/raw/nbr/inclusion")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

RUN_TIMESTAMP = datetime.now().astimezone().isoformat(timespec="seconds")


def clean_text(value):
    return re.sub(r"\s+", " ", value or "").strip()


def read_filters(page):
    """Read the currently displayed values of the dashboard filters."""
    filters = {}

    labels = [
        "Gender",
        "Age Segment",
        "Institution Type",
        "Account/Policy Status",
        "Location",
    ]

    controls = page.locator('input[role="combobox"]')

    for index, label in enumerate(labels):
        if index >= controls.count():
            filters[label] = None
            continue

        control = controls.nth(index)

        # React Select may display the selected value in a sibling element.
        try:
            value = control.evaluate("""
                el => {
                    const container = el.closest('.Select');
                    if (container) {
                        const selected = container.querySelector(
                            '.Select-value-label'
                        );
                        if (selected) return selected.innerText.trim();
                    }

                    const labelled = el.getAttribute('aria-label');
                    if (labelled) return labelled;

                    return el.value || null;
                }
            """)
            filters[label] = clean_text(value) if value else None
        except Exception:
            filters[label] = None

    return filters


def read_headline_metrics(page):
    """Capture the visible headline KPI cards without assuming their order."""
    metrics = []

    cards = page.locator("#numeric_card")

    for index in range(cards.count()):
        card = cards.nth(index)

        if not card.is_visible():
            continue

        text = clean_text(card.inner_text())

        if text:
            metrics.append(
                {
                    "card_index": index,
                    "displayed_text": text,
                }
            )

    # The financial inclusion percentage may be displayed outside the KPI card.
    body_text = page.locator("body").inner_text()

    percentage_match = re.search(
        r"(\d+(?:\.\d+)?)\s*%\s*Financially Included",
        body_text,
        flags=re.IGNORECASE,
    )

    return {
        "kpi_cards": metrics,
        "financially_included_percent": (
            float(percentage_match.group(1)) if percentage_match else None
        ),
    }


def open_district_table(page):
    """
    Locate the district section and attempt to switch it to Table view.
    Returns whether an HTML table becomes visible.
    """
    section = page.get_by_text("CUSTOMERS BY DISTRICT", exact=True).first

    if not section.count():
        print("District section not found.")
        return False

    # Search within the district section's nearest containing component.
    for ancestor_level in range(1, 6):
        ancestor = section.locator("xpath=" + "/.." * ancestor_level)

        try:
            text = clean_text(ancestor.inner_text(timeout=2000))
        except Exception:
            continue

        if "Click to view Table" not in text:
            continue

        button = ancestor.get_by_text("Click to view Table", exact=True).first

        if button.count():
            try:
                button.click(timeout=5000, force=True)
                page.wait_for_timeout(1500)

                table = page.locator("table.cell-table")
                if table.count() and table.first.is_visible():
                    print("District table opened.")
                    return True
            except PlaywrightTimeoutError:
                pass
            except Exception as exc:
                print(f"Table-view attempt: {exc}")

    # Fallback: try the visible Table control anywhere on the page.
    table_control = page.get_by_text("Click to view Table", exact=True).first

    if table_control.count():
        try:
            table_control.click(timeout=5000, force=True)
            page.wait_for_timeout(1500)

            table = page.locator("table.cell-table")
            if table.count() and table.first.is_visible():
                print("District table opened using fallback.")
                return True
        except Exception as exc:
            print(f"Fallback table-view attempt: {exc}")

    print("Could not confirm that district Table view opened.")
    return False


def extract_visible_table(page):
    """Extract headers and visible rows from an HTML table, if available."""
    table = page.locator("table.cell-table").first

    if not table.count() or not table.is_visible():
        return [], []

    headers = [
        clean_text(value) for value in table.locator("thead th").all_inner_texts()
    ]

    rows = []

    while True:
        for row in table.locator("tbody tr").all():
            cells = [
                clean_text(value) for value in row.locator("th, td").all_inner_texts()
            ]

            if cells and cells not in rows:
                rows.append(cells)

        next_button = page.locator(".previous-next-container .next-page").first

        if not next_button.count() or not next_button.is_visible():
            break

        classes = next_button.get_attribute("class") or ""
        aria_disabled = next_button.get_attribute("aria-disabled")

        if "disabled" in classes.lower() or aria_disabled == "true":
            break

        try:
            next_button.click(timeout=3000)
            page.wait_for_timeout(700)
        except Exception:
            break

    return headers, rows


def main():
    result = {
        "source": URL,
        "scraped_at": RUN_TIMESTAMP,
        "filters": {},
        "metrics": {},
        "district_table": {
            "headers": [],
            "rows": [],
            "extraction_status": "not_attempted",
        },
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        try:
            print(f"Opening {URL}")
            page.goto(
                URL,
                wait_until="domcontentloaded",
                timeout=60000,
            )

            page.locator('input[role="combobox"]').first.wait_for(
                state="attached", timeout=30000
            )

            # Wait for initial dashboard data to populate.
            page.wait_for_function(
                """() => {
                    const card = document.querySelector('#numeric_card');
                    return card && card.innerText.trim().length > 0;
                }""",
                timeout=30000,
            )
            page.wait_for_timeout(1500)

            result["filters"] = read_filters(page)
            result["metrics"] = read_headline_metrics(page)

            print("\nHeadline metrics:")
            print(json.dumps(result["metrics"], indent=2))

            print("\nCurrent filters:")
            print(json.dumps(result["filters"], indent=2))

            table_opened = open_district_table(page)

            if table_opened:
                headers, rows = extract_visible_table(page)
                result["district_table"] = {
                    "headers": headers,
                    "rows": rows,
                    "extraction_status": ("success" if rows else "table_empty"),
                }
            else:
                result["district_table"][
                    "extraction_status"
                ] = "table_view_not_confirmed"

            # Keep an artifact for diagnosing the first real run.
            page.screenshot(
                path=str(OUTPUT_DIR / "inclusion_latest.png"),
                full_page=True,
            )

            json_path = OUTPUT_DIR / "inclusion_latest.json"
            with json_path.open("w", encoding="utf-8") as file:
                json.dump(result, file, indent=2, ensure_ascii=False)

            if result["district_table"]["rows"]:
                csv_path = OUTPUT_DIR / "inclusion_districts_latest.csv"
                with csv_path.open("w", newline="", encoding="utf-8-sig") as file:
                    writer = csv.writer(file)
                    if result["district_table"]["headers"]:
                        writer.writerow(result["district_table"]["headers"])
                    writer.writerows(result["district_table"]["rows"])

                print(f"\nDistrict CSV saved: {csv_path}")

            print(f"\nJSON saved: {json_path}")
            print(
                "District extraction status:",
                result["district_table"]["extraction_status"],
            )

        finally:
            browser.close()


if __name__ == "__main__":
    main()
