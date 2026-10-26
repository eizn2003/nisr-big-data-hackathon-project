from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "data" / "raw" / "nbr"

DEFAULT_URL = "https://fininclusion.bnr.rw/transactional"

KPI_CARD_SELECTOR = ".custom-card-margin.card"
KPI_VALUE_SELECTOR = ".card-text.large-data"
KPI_LABEL_SELECTOR = ".card-title.small-text"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def dismiss_disclaimer(page) -> bool:
    """Dismiss the disclaimer when its Thanks control can be identified."""
    print("\n--- DISCLAIMER ---")

    # Prefer the exact accessible button.
    thanks = page.get_by_role(
        "button",
        name=re.compile(r"^\s*thanks!?\s*$", re.IGNORECASE),
    )

    try:
        for index in range(thanks.count()):
            button = thanks.nth(index)
            if button.is_visible():
                button.click(timeout=3000)
                page.wait_for_timeout(800)
                print("Clicked the Thanks button.")
                return True
    except PlaywrightTimeoutError:
        pass

    # Fallback: find visible exact text, including "Thanks!".
    thanks = page.get_by_text(
        re.compile(r"^\s*thanks!?\s*$", re.IGNORECASE),
        exact=True,
    )

    try:
        for index in range(thanks.count()):
            element = thanks.nth(index)

            if element.is_visible():
                element.click(timeout=3000)
                page.wait_for_timeout(800)
                print("Clicked the visible Thanks text.")
                return True
    except PlaywrightTimeoutError:
        pass

    print("Thanks control not found; continuing.")
    return False


def wait_for_dashboard(page, timeout_ms: int) -> bool:
    """Wait for real KPI content; do not depend on the document title."""
    try:
        page.wait_for_function(
            """
            (selector) => Array.from(document.querySelectorAll(selector))
                .some(card => {
                    const style = getComputedStyle(card);
                    const rect = card.getBoundingClientRect();
                    const value = card.querySelector(
                        ".card-text.large-data"
                    );
                    const label = card.querySelector(
                        ".card-title.small-text"
                    );

                    return rect.width > 0 &&
                           rect.height > 0 &&
                           style.display !== "none" &&
                           style.visibility !== "hidden" &&
                           value?.innerText.trim() &&
                           label?.innerText.trim();
                })
            """,
            arg=KPI_CARD_SELECTOR,
            timeout=timeout_ms,
        )
        page.wait_for_timeout(1500)
        return True
    except PlaywrightTimeoutError:
        return False


def extract_filters(page) -> dict:
    """Capture visible selected filter values when available."""
    filters = {}

    cards = page.locator(".dropdown-card, .location-dropdown-card")

    for index in range(cards.count()):
        card = cards.nth(index)

        try:
            if not card.is_visible():
                continue

            # The dashboard's filter cards usually use this header class.
            label_locator = card.locator(".dropdown-card-header, label").first

            value_locator = card.locator(
                ".Select-value-label, [class*='singleValue']"
            ).first

            label = label_locator.inner_text().strip() if label_locator.count() else ""
            value = value_locator.inner_text().strip() if value_locator.count() else ""

            if label and value:
                filters[label.rstrip(":")] = value

        except PlaywrightTimeoutError:
            continue

    return filters


def extract_headline_kpis(page, url: str, filters: dict) -> list[dict]:
    """Extract any headline KPI cards present on the current page."""
    records = []
    timestamp = utc_now()
    cards = page.locator(KPI_CARD_SELECTOR)

    for index in range(cards.count()):
        card = cards.nth(index)

        try:
            if not card.is_visible():
                continue

            value_locator = card.locator(KPI_VALUE_SELECTOR).first
            label_locator = card.locator(KPI_LABEL_SELECTOR).first

            # Some pages may not have this card structure. Skip it.
            if not value_locator.count() or not label_locator.count():
                continue

            value = value_locator.inner_text().strip()
            label = label_locator.inner_text().strip()

            if not label or not value:
                continue

            records.append(
                {
                    "source": "NBR Financial Inclusion Dashboard",
                    "page": url.rstrip("/").split("/")[-1],
                    "url": url,
                    "metric_type": "headline_kpi",
                    "metric_label": label,
                    "metric_value": value,
                    "gender": None,
                    "filters": filters,
                    "extracted_at_utc": timestamp,
                    "extraction_method": "headline_card",
                }
            )

        except PlaywrightTimeoutError:
            continue

    return records


def extract_gender_percentages(page, page_name, filters):
    """Extract gender percentages from the dashboard's Plotly pie chart."""

    try:
        page.wait_for_function(
            """
            () => Array.from(
                document.querySelectorAll(".js-plotly-plot")
            ).some(plot =>
                plot.data?.some(trace =>
                    trace.type === "pie" &&
                    Array.isArray(trace.labels) &&
                    Array.isArray(trace.values) &&
                    trace.labels.some(
                        label => String(label).trim().toLowerCase() === "male"
                    ) &&
                    trace.labels.some(
                        label => String(label).trim().toLowerCase() === "female"
                    )
                )
            )
            """,
            timeout=30000,
        )
    except PlaywrightTimeoutError:
        return []

    gender_data = page.evaluate("""
        () => {
            for (const plot of document.querySelectorAll(".js-plotly-plot")) {
                const trace = plot.data?.find(trace =>
                    trace.type === "pie" &&
                    Array.isArray(trace.labels) &&
                    Array.isArray(trace.values) &&
                    trace.labels.some(
                        label => String(label).trim().toLowerCase() === "male"
                    ) &&
                    trace.labels.some(
                        label => String(label).trim().toLowerCase() === "female"
                    )
                );

                if (!trace) continue;

                const total = trace.values.reduce(
                    (sum, value) => sum + Number(value),
                    0
                );

                if (
                    total <= 0 ||
                    trace.values.some(
                        value =>
                            !Number.isFinite(Number(value)) ||
                            Number(value) < 0
                    )
                ) {
                    return null;
                }

                return trace.labels.map((label, index) => ({
                    gender: String(label).trim(),
                    percentage: Number(
                        (
                            Number(trace.values[index]) /
                            total *
                            100
                        ).toFixed(1)
                    )
                }));
            }

            return null;
        }
        """)

    if not gender_data:
        return []

    records = []

    for item in gender_data:
        gender = item["gender"]

        if gender.lower() not in ("male", "female"):
            continue

        records.append(
            {
                "source": "NBR Financial Inclusion Dashboard",
                "page": page_name,
                "url": page.url,
                "metric_type": "gender_distribution",
                "metric_label": f"{gender} customers",
                "metric_value": item["percentage"],
                "gender": gender,
                "filters": filters.copy() if isinstance(filters, dict) else filters,
                "extracted_at_utc": utc_now(),
                "extraction_method": "plotly_pie_trace",
            }
        )

    return records


def main():
    parser = argparse.ArgumentParser(
        description="Extract available NBR dashboard KPI data."
    )
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--timeout", type=int, default=60000)
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    page_name = re.sub(
        r"[^a-zA-Z0-9_-]+",
        "_",
        args.url.rstrip("/").split("/")[-1] or "dashboard",
    )

    json_path = OUTPUT_DIR / f"nbr_kpis_{page_name}.json"
    csv_path = OUTPUT_DIR / f"nbr_kpis_{page_name}.csv"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.headed)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})

        try:
            print("Opening:", args.url)
            page.goto(
                args.url,
                wait_until="domcontentloaded",
                timeout=args.timeout,
            )
            page.wait_for_timeout(2000)

            disclaimer_dismissed = dismiss_disclaimer(page)
            dashboard_ready = wait_for_dashboard(page, args.timeout)

            if not dashboard_ready:
                print("No headline KPI cards detected.")
                print("Page title:", page.title())
                print("Page URL:", page.url)
                return

            filters = extract_filters(page)

            records = extract_headline_kpis(
                page,
                args.url,
                filters,
            )

            print(f"Headline KPIs extracted: {len(records)}", flush=True)

            print("Starting gender KPI extraction...", flush=True)

            try:
                gender_records = extract_gender_percentages(
                    page,
                    args.url,
                    filters,
                )
                print(
                    f"Gender KPI records extracted: {len(gender_records)}",
                    flush=True,
                )
                records.extend(gender_records)

            except Exception as exc:
                print(
                    f"Gender KPI extraction failed: {type(exc).__name__}: {exc}",
                    flush=True,
                )

            result = {
                "source": "NBR Financial Inclusion Dashboard",
                "page": page_name,
                "url": page.url,
                "extracted_at_utc": utc_now(),
                "disclaimer_dismissed": disclaimer_dismissed,
                "filters": filters,
                "kpi_count": len(records),
                "kpis": records,
            }

            json_path.write_text(
                json.dumps(result, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

            fields = [
                "source",
                "page",
                "url",
                "metric_type",
                "metric_label",
                "metric_value",
                "gender",
                "filters",
                "extracted_at_utc",
                "extraction_method",
            ]

            with csv_path.open(
                "w",
                newline="",
                encoding="utf-8",
            ) as file:
                writer = csv.DictWriter(file, fieldnames=fields)
                writer.writeheader()

                for record in records:
                    row = record.copy()
                    row["filters"] = json.dumps(
                        row["filters"],
                        ensure_ascii=False,
                    )
                    writer.writerow(row)

            print("\n--- KPI EXTRACTION SUMMARY ---")
            print("Page:", page_name)
            print("Disclaimer dismissed:", disclaimer_dismissed)
            print("Filters:", json.dumps(filters, ensure_ascii=False))
            print("Records extracted:", len(records))

            for record in records:
                print(
                    f"- [{record['metric_type']}] "
                    f"{record['metric_label']}: "
                    f"{record['metric_value']}"
                )

            print("\nJSON:", json_path)
            print("CSV:", csv_path)

        finally:
            browser.close()


if __name__ == "__main__":
    main()
