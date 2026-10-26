from __future__ import annotations

import re
from pathlib import Path

from playwright.sync_api import sync_playwright

# ------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]

URL = "https://fininclusion.bnr.rw/inclusion"

OUTPUT_DIR = PROJECT_ROOT / "data" / "raw" / "nbr" / "inclusion" / "diagnostics"

OUTPUT_FILE = OUTPUT_DIR / "kpi_dom_inspection.txt"

KEYWORDS = re.compile(
    r"customers?|financially included|inclusion rate|"
    r"financial inclusion|mfi|bank|insurance|microfinance|"
    r"sacco|e-money|total",
    re.IGNORECASE,
)

NUMBER_PATTERN = re.compile(r"(?<!\w)\d[\d,]*(?:\.\d+)?\s*%?(?!\w)")

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


# ------------------------------------------------------------
# DOM INSPECTION
# ------------------------------------------------------------


def inspect_dashboard():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    report = []

    def log(text=""):
        report.append(str(text))

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)

        page = browser.new_page(viewport={"width": 1440, "height": 1000})

        try:
            print("Opening NBR financial inclusion dashboard...")

            page.goto(
                URL,
                wait_until="networkidle",
                timeout=60000,
            )

            page.add_style_tag(content=MODAL_CSS)
            page.wait_for_timeout(2000)

            # ------------------------------------------------
            # 1. PAGE INFORMATION
            # ------------------------------------------------

            log("=" * 80)
            log("NBR FINANCIAL INCLUSION KPI DOM INSPECTION")
            log("=" * 80)
            log(f"URL: {page.url}")
            log(f"Title: {page.title()}")

            # ------------------------------------------------
            # 2. VISIBLE BODY TEXT
            # ------------------------------------------------

            log("\n" + "=" * 80)
            log("SECTION 1: VISIBLE BODY TEXT")
            log("=" * 80)

            body_text = page.locator("body").inner_text()

            for index, line in enumerate(body_text.splitlines(), 1):
                line = line.strip()

                if line:
                    log(f"{index:04d}: {line}")

            # ------------------------------------------------
            # 3. KEYWORD AND NUMBER ELEMENTS
            # ------------------------------------------------

            log("\n" + "=" * 80)
            log("SECTION 2: KEYWORD / NUMERIC ELEMENTS AND ANCESTORS")
            log("=" * 80)

            elements = page.locator("body *:visible")

            count = elements.count()
            matches = 0

            for index in range(count):
                element = elements.nth(index)

                try:
                    text = element.inner_text(timeout=500)
                    text = " ".join(text.split())

                    if not text or len(text) > 300:
                        continue

                    has_keyword = bool(KEYWORDS.search(text))
                    has_number = bool(NUMBER_PATTERN.search(text))

                    if not (has_keyword or has_number):
                        continue

                    # Avoid printing a parent element's entire subtree
                    # repeatedly. Prefer elements with short text.
                    if len(text) > 180:
                        continue

                    tag = element.evaluate("(el) => el.tagName.toLowerCase()")

                    classes = element.evaluate("(el) => el.className?.toString() || ''")

                    element_id = element.get_attribute("id") or ""

                    log("\n" + "-" * 70)
                    log(f"Element index: {index}")
                    log(f"Tag: {tag}")
                    log(f"ID: {element_id}")
                    log(f"Classes: {classes}")
                    log(f"Text: {text}")

                    # Print the element and up to five ancestors.
                    ancestor_data = element.evaluate("""el => {
                            const result = [];
                            let node = el;

                            for (let i = 0; node && i < 6; i++) {
                                result.push({
                                    level: i,
                                    tag: node.tagName.toLowerCase(),
                                    id: node.id || "",
                                    classes:
                                        typeof node.className === "string"
                                            ? node.className
                                            : "",
                                    text: (node.innerText || "")
                                        .replace(/\\s+/g, " ")
                                        .trim()
                                        .slice(0, 400),
                                    html: node.outerHTML.slice(0, 1500)
                                });

                                node = node.parentElement;
                            }

                            return result;
                        }""")

                    for ancestor in ancestor_data:
                        log(
                            f"\nAncestor level {ancestor['level']}: "
                            f"<{ancestor['tag']}>"
                        )
                        log(f"ID: {ancestor['id']}")
                        log(f"Classes: {ancestor['classes']}")
                        log(f"Text: {ancestor['text']}")
                        log(f"HTML: {ancestor['html']}")

                    matches += 1

                except Exception as exc:
                    log(
                        f"Could not inspect element {index}: "
                        f"{type(exc).__name__}: {exc}"
                    )

            log(f"\nTotal matching elements: {matches}")

            # ------------------------------------------------
            # 4. LIKELY KPI CONTAINERS
            # ------------------------------------------------

            log("\n" + "=" * 80)
            log("SECTION 3: LIKELY CARD / KPI CONTAINERS")
            log("=" * 80)

            containers = page.locator("""
                [class*="card"],
                [class*="kpi"],
                [class*="metric"],
                [class*="indicator"],
                [class*="counter"],
                [class*="stat"],
                [class*="widget"]
                """)

            for index in range(containers.count()):
                container = containers.nth(index)

                try:
                    if not container.is_visible():
                        continue

                    text = " ".join(container.inner_text(timeout=500).split())

                    if not text or len(text) > 600:
                        continue

                    if not (KEYWORDS.search(text) or NUMBER_PATTERN.search(text)):
                        continue

                    log("\n" + "-" * 70)
                    log(f"Container index: {index}")
                    log(f"Text: {text}")

                    html = container.evaluate("(el) => el.outerHTML")

                    log("HTML:")
                    log(html[:4000])

                except Exception as exc:
                    log(f"Container inspection failed: " f"{type(exc).__name__}: {exc}")

            # ------------------------------------------------
            # 5. TABLE AND KPI-RELATED STRUCTURE
            # ------------------------------------------------

            log("\n" + "=" * 80)
            log("SECTION 4: HEADINGS, LABELS, AND TABLES")
            log("=" * 80)

            selectors = [
                "h1",
                "h2",
                "h3",
                "h4",
                "label",
                "[role='heading']",
                "table",
                "svg",
            ]

            for selector in selectors:
                locator = page.locator(selector)

                log(f"\nSelector: {selector}")
                log(f"Count: {locator.count()}")

                for index in range(min(locator.count(), 30)):
                    element = locator.nth(index)

                    try:
                        if not element.is_visible():
                            continue

                        text = " ".join(element.inner_text(timeout=500).split())

                        html = element.evaluate("(el) => el.outerHTML")

                        log(f"\n  Item {index}: {text[:250]}")
                        log(f"  HTML: {html[:1200]}")

                    except Exception:
                        continue

            # ------------------------------------------------
            # 6. WRITE REPORT
            # ------------------------------------------------

            OUTPUT_FILE.write_text(
                "\n".join(report),
                encoding="utf-8",
            )

            print("\nInspection complete.")
            print(f"Report saved to: {OUTPUT_FILE}")
            print(f"Matching elements: {matches}")

        finally:
            browser.close()


if __name__ == "__main__":
    inspect_dashboard()
