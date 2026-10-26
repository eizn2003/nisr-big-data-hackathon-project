from playwright.sync_api import sync_playwright

URL = "https://fininclusion.bnr.rw/transactional"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()
    page.goto(URL, wait_until="networkidle", timeout=60000)
    page.wait_for_timeout(3000)

    # Dismiss the disclaimer if present.
    close_button = page.locator("#close-disclaimer")
    if close_button.count() and close_button.is_visible():
        close_button.click()
        page.wait_for_timeout(1000)

    print("\n--- VISIBLE INPUTS ---")
    inputs = page.locator("input:visible")
    for i in range(inputs.count()):
        el = inputs.nth(i)
        print(
            {
                "index": i,
                "type": el.get_attribute("type"),
                "placeholder": el.get_attribute("placeholder"),
                "value": el.input_value(),
                "aria_label": el.get_attribute("aria-label"),
                "class": el.get_attribute("class"),
                "outer_html": el.evaluate("(el) => el.parentElement?.outerHTML")[:700],
            }
        )

    print("\n--- DATE-RELATED ELEMENTS ---")
    elements = page.locator(
        "[class*='date'], [id*='date'], "
        "[aria-label*='date' i], "
        "button:visible, label:visible"
    )

    seen = set()
    for i in range(min(elements.count(), 100)):
        el = elements.nth(i)
        try:
            info = el.evaluate("""el => ({
                tag: el.tagName,
                text: (el.innerText || '').trim().slice(0, 100),
                id: el.id,
                class: typeof el.className === 'string'
                    ? el.className : '',
                aria: el.getAttribute('aria-label'),
                title: el.getAttribute('title')
            })""")
            key = (info["tag"], info["text"], info["id"], info["class"], info["aria"])
            if key not in seen:
                seen.add(key)
                print(info)
        except Exception:
            pass

    input("\nInspect the dashboard if needed, then press Enter to close...")
    browser.close()
