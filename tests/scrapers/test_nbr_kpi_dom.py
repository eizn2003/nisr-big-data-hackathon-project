
from __future__ import annotations

from playwright.sync_api import sync_playwright

URL = "https://fininclusion.bnr.rw/inclusion"

# Inspect the DOM for elements that may contain KPI values.
# We deliberately do not use body.inner_text() to identify KPIs.
DOM_INSPECTION_JS = r"""
() => {
    const selectors = [
        '[class*="card"]',
        '[class*="kpi"]',
        '[class*="metric"]',
        '[class*="indicator"]',
        '[class*="counter"]',
        '[class*="stat"]',
        '[class*="widget"]',
        '[class*="value"]',
        '[class*="number"]',
        '[class*="total"]',
        '[data-testid]',
        '[aria-label]',
        'main',
        'section',
        'article'
    ];

    const elements = new Set();

    for (const selector of selectors) {
        document.querySelectorAll(selector).forEach(el => {
            elements.add(el);
        });
    }

    function describe(el) {
        return {
            tag: el.tagName.toLowerCase(),
            id: el.id || null,
            classes: typeof el.className === "string"
                ? el.className
                : null,
            testid: el.getAttribute("data-testid"),
            ariaLabel: el.getAttribute("aria-label"),
            role: el.getAttribute("role"),
            attributes: Array.from(el.attributes).reduce((out, attr) => {
                out[attr.name] = attr.value;
                return out;
            }, {}),
            directTextNodes: Array.from(el.childNodes)
                .filter(node => node.nodeType === Node.TEXT_NODE)
                .map(node => node.textContent.trim())
                .filter(Boolean),
            childElements: Array.from(el.children).map(child => ({
                tag: child.tagName.toLowerCase(),
                id: child.id || null,
                classes: typeof child.className === "string"
                    ? child.className
                    : null,
                directTextNodes: Array.from(child.childNodes)
                    .filter(node => node.nodeType === Node.TEXT_NODE)
                    .map(node => node.textContent.trim())
                    .filter(Boolean)
            })),
            outerHTML: el.outerHTML.slice(0, 2500)
        };
    }

    return {
        title: document.title,
        url: location.href,
        readyState: document.readyState,
        elementCount: elements.size,
        elements: Array.from(elements).map(describe)
    };
}
"""


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            viewport={"width": 1440, "height": 1000}
        )

        try:
            print("Opening dashboard...")
            page.goto(
                URL,
                wait_until="domcontentloaded",
                timeout=60000,
            )

            # Wait for the application to render its DOM.
            page.wait_for_timeout(5000)

            result = page.evaluate(DOM_INSPECTION_JS)

            print("\n=== DOCUMENT ===")
            print("Title:", result["title"])
            print("URL:", result["url"])
            print("Ready state:", result["readyState"])
            print("Candidate elements:", result["elementCount"])

            for index, element in enumerate(result["elements"]):
                print("\n" + "=" * 90)
                print(f"ELEMENT {index}")
                print("Tag:", element["tag"])
                print("ID:", element["id"])
                print("Classes:", element["classes"])
                print("Attributes:", element["attributes"])
                print("Direct text nodes:", element["directTextNodes"])
                print("Child elements:", element["childElements"])
                print("Outer HTML:")
                print(element["outerHTML"])

        finally:
            browser.close()


if __name__ == "__main__":
    main()
