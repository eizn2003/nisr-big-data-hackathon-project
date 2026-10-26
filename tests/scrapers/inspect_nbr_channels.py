import json
from pathlib import Path
from playwright.sync_api import sync_playwright

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = PROJECT_ROOT / "data" / "raw" / "nbr"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

URL = "https://fininclusion.bnr.rw/transactional"
CHANNELS_URL = "https://fininclusion.bnr.rw/channels"


def inspect_page(page, label):
    result = page.evaluate("""() => {
            const clean = text =>
                (text || "").replace(/\\\\s+/g, " ").trim();

            const visible = el => {
                const style = getComputedStyle(el);
                const rect = el.getBoundingClientRect();

                return style.display !== "none"
                    && style.visibility !== "hidden"
                    && Number(style.opacity) !== 0
                    && rect.width > 0
                    && rect.height > 0;
            };

            const elements = Array.from(
                document.querySelectorAll(
                    "h1, h2, h3, h4, h5, label, .card, .card-body, " +
                    ".card-title, .card-text, .large-data, .small-text, " +
                    "table, th, td, button, select, input, canvas, svg, " +
                    "[role='combobox'], [role='tab']"
                )
            ).filter(visible);

            return {
                url: location.href,
                title: document.title,
                headings: Array.from(
                    document.querySelectorAll("h1,h2,h3,h4,h5")
                ).filter(visible).map(el => clean(el.innerText)),
                elements: elements.map(el => ({
                    tag: el.tagName,
                    id: el.id || null,
                    class: typeof el.className === "string"
                        ? el.className
                        : null,
                    text: clean(el.innerText).slice(0, 500),
                    value: "value" in el ? el.value : null,
                    html: el.outerHTML.slice(0, 1200)
                })).slice(0, 250),
                visibleText: clean(document.body.innerText).slice(0, 15000)
            };
        }""")

    output_file = OUTPUT_DIR / f"channels_inspection_{label}.json"
    output_file.write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"\n{'=' * 65}")
    print(f"CHANNELS PAGE — {label}")
    print(f"URL: {result['url']}")
    print(f"Title: {result['title']}")
    print(f"Headings: {result['headings']}")
    print(f"Saved: {output_file}")
    print("=" * 65)

    print("\nVISIBLE PAGE TEXT:")
    print(result["visibleText"][:7000])

    print("\nPOTENTIAL KPI CARDS:")
    for item in result["elements"]:
        classes = item["class"] or ""
        if (
            "card" in classes.lower()
            or "large-data" in classes.lower()
            or "small-text" in classes.lower()
        ):
            if item["text"]:
                print(f"- {item['tag']} | {classes} | " f"{item['text'][:180]}")


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})

        print("Opening NBR dashboard...")
        page.goto(URL, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(2500)

        close_button = page.locator("#close-disclaimer")
        if close_button.count() and close_button.is_visible():
            close_button.click()
            page.wait_for_timeout(1000)

        print("Opening Channels section...")
        page.goto(CHANNELS_URL, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(4000)

        inspect_page(page, "current")

        page.screenshot(
            path=str(OUTPUT_DIR / "channels_inspection_current.png"), full_page=True
        )

        date_input = page.locator("#date")

        if date_input.count():
            print("\nSelecting historical date: 2025-02-24")
            date_input.fill("2025-02-24")
            date_input.press("Enter")
            date_input.press("Tab")
            page.wait_for_timeout(5000)

            print("Date shown:", date_input.input_value())
            inspect_page(page, "historical")

            page.screenshot(
                path=str(OUTPUT_DIR / "channels_inspection_historical.png"),
                full_page=True,
            )
        else:
            print(
                "\nNo #date input found on Channels. "
                "We'll inspect the saved HTML details to identify its controls."
            )

        input("\nInspection complete. Press Enter to close the browser...")
        browser.close()


if __name__ == "__main__":
    main()
