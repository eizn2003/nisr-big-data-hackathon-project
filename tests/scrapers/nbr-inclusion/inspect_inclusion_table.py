from playwright.sync_api import sync_playwright

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

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 1000})

    page.goto(URL, wait_until="networkidle", timeout=60000)
    page.add_style_tag(content=MODAL_CSS)
    page.wait_for_timeout(2000)

    # Open the dashboard table view.
    candidates = page.get_by_text("Click to View Table", exact=False)
    clicked = False

    for i in range(candidates.count()):
        candidate = candidates.nth(i)
        if candidate.is_visible():
            print("Clicking table control:", candidate.inner_text().strip())
            candidate.click()
            page.wait_for_timeout(1500)
            clicked = True
            break

    if not clicked:
        print("Table-view control was not found.")

    print("\n--- TABLE ELEMENTS ---")
    tables = page.locator("table")

    for i in range(tables.count()):
        table = tables.nth(i)
        print(
            f"Table {i}: visible={table.is_visible()}, "
            f"class={table.get_attribute('class')!r}"
        )

        if table.is_visible():
            print("  Headers:", table.locator("thead th").all_inner_texts())
            print("  First rows:", table.locator("tbody tr").all_inner_texts()[:5])

    print("\n--- PAGINATION CONTROLS ---")
    for selector in [
        "button.next-page",
        "button[aria-label*='Next']",
        "button",
    ]:
        controls = page.locator(selector)
        print(f"{selector}: {controls.count()} match(es)")

        if selector == "button":
            for i in range(min(controls.count(), 30)):
                button = controls.nth(i)
                if button.is_visible():
                    print(
                        f"  text={button.inner_text().strip()!r}, "
                        f"class={button.get_attribute('class')!r}, "
                        f"disabled={button.is_disabled()}"
                    )

    page.screenshot(
        path="data/raw/nbr/inclusion/inclusion_table_inspection.png",
        full_page=True,
    )
    browser.close()
