"""Shared NBR Financial Inclusion Dashboard scraping engine.

Both entry points (scrape_nbr_backfill.py and scrape_nbr_current.py) are thin
wrappers around run_cli() in this module. Page URLs and filter labels live in
nbr_pages.json; nothing page-specific is hardcoded here.

Components reused from the existing project scripts:
  * filter interaction, dashboard waiting, table pagination, MongoDB connection
    conventions, retry/terminal-status checkpointing: backfill_nbr_inclusion_history.py
  * date selection + strict "dashboard finished updating" wait: test_nbr_date_selection.py
  * headline KPI and Plotly gender-pie extraction: test_nbr_kpi_discovery.py
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import os
import re
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright
from pymongo import MongoClient, UpdateOne

# ============================================================
# CONSTANTS
# ============================================================


def _find_project_root() -> Path:
    override = os.getenv("NBR_PROJECT_ROOT")
    if override:
        return Path(override).resolve()
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / ".env").exists():
            return parent
    # Same default as the existing scrapers (scripts live two levels below the root).
    return here.parents[2] if len(here.parents) > 2 else here.parent


PROJECT_ROOT = _find_project_root()
OUTPUT_DIR = PROJECT_ROOT / "data" / "raw" / "nbr"
PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "nbr_pages.json"
DEFAULT_DATES_FILE = PROJECT_ROOT / "config" / "nbr_backfill_dates.txt"

TIMEZONE = ZoneInfo("Africa/Kigali")
DATABASE_NAME = "nbr_financial_inclusion"  # same database as the existing scrapers
TABLE_COLLECTION = "page_table_observations"
KPI_COLLECTION = "page_kpi_observations"
RUN_COLLECTION = "page_scrape_runs"
TERMINAL_STATUSES = {"complete", "completed_no_data", "not_applicable"}

SOURCE_NAME = "NBR Financial Inclusion Dashboard"
TABLE_SELECTOR = "table.cell-table"
NEXT_BUTTON_SELECTOR = "button.next-page"
FIRST_BUTTON_SELECTOR = "button.first-page"
KPI_CARD_SELECTOR = ".custom-card-margin.card"
KPI_VALUE_SELECTOR = ".card-text.large-data"
KPI_LABEL_SELECTOR = ".card-title.small-text"
MAX_TABLE_PAGES = 100
MAX_RETRIES = 3
PAGE_TIMEOUT_MS = 20000
FILTER_SETTLE_MS = 700
SHORT_WAIT_MS = 3000  # used once a page has proven to lack KPI cards / a gender chart
GENDER_WAIT_MS = 30000

DATE_UPDATE_TIMEOUT_MS = 30_000
DATE_STABLE_CHECKS = 3
DATE_STABLE_DEADLINE_S = 45

# Same disclaimer workaround the proven inclusion backfill uses.
MODAL_CSS = """
.modal, .modal.show, .modal-backdrop, [role="dialog"] {
    display: none !important;
    visibility: hidden !important;
    pointer-events: none !important;
}
body { overflow: auto !important; }
"""

# Nearest filter "card" around a dropdown (same classes test_nbr_kpi_discovery.py reads).
FILTER_CARD_XPATH = (
    "xpath=ancestor::*[contains(concat(' ', normalize-space(@class), ' '), ' dropdown-card ') "
    "or contains(concat(' ', normalize-space(@class), ' '), ' location-dropdown-card ')][1]"
)


class ConfigError(RuntimeError):
    """nbr_pages.json (or the CLI selection) is invalid."""


class FilterConfigError(RuntimeError):
    """The filters on the live dashboard do not match the configuration."""


class OptionNotAvailableError(RuntimeError):
    """The requested option is not present in the live filter control."""


class EmptyDashboardTableError(RuntimeError):
    """The table is visible but contains no data rows."""


class PageAborted(RuntimeError):
    """A deterministic page-level problem; retrying other combinations would not help."""


def retry_pause(attempt: int):
    time.sleep(attempt * 2)


def log(message: str = "", prefix: str = ""):
    print(f"{prefix}{message}", flush=True)


# ============================================================
# SMALL HELPERS
# ============================================================


def now_local() -> datetime:
    return datetime.now(TIMEZONE)


def norm_label(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().rstrip(":").strip()).casefold()


def ignore_filter_label(label: str | None) -> bool:
    return norm_label(label or "") == "location"


def filters_key(filters: dict) -> str:
    return json.dumps(filters, sort_keys=True, ensure_ascii=False)


def stable_hash(value) -> str:
    payload = json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def parse_number(raw):
    """Best-effort numeric reading of a raw cell/KPI string. The raw text is always kept too."""
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return raw
    text = str(raw).strip().replace(",", "")
    match = re.fullmatch(r"-?\d+(?:\.\d+)?%?", text)
    if not match:
        return None
    text = text.rstrip("%")
    return float(text) if "." in text else int(text)


# ============================================================
# PAGE CONFIGURATION
# ============================================================


@dataclass(frozen=True)
class FilterSpec:
    label: str
    options: tuple | None = None  # iterate every option
    fixed: str | None = None  # force this value


@dataclass
class PageConfig:
    page_id: str
    url: str
    title: str
    filters: list[FilterSpec] | None  # None = unverified
    known_not_applicable: list[dict] = field(default_factory=list)
    known_no_data: list[dict] = field(default_factory=list)
    gender_distribution: bool = True
    date_selector: str = "#date"
    handled_by: str | None = None

    @property
    def filters_verified(self) -> bool:
        return self.filters is not None


def _parse_filter(page_id: str, raw) -> FilterSpec:
    if isinstance(raw, str):
        label, options, fixed = raw.strip(), None, None
    elif isinstance(raw, dict) and isinstance(raw.get("label"), str):
        label = raw["label"].strip()
        options, fixed = raw.get("options"), raw.get("fixed")
        if options is not None:
            if not (
                isinstance(options, list)
                and options
                and all(isinstance(o, str) and o.strip() for o in options)
            ):
                raise ConfigError(
                    f"Page {page_id!r}, filter {label!r}: 'options' must be a non-empty list of strings."
                )
            options = tuple(o.strip() for o in options)
        if fixed is not None and not (isinstance(fixed, str) and fixed.strip()):
            raise ConfigError(
                f"Page {page_id!r}, filter {label!r}: 'fixed' must be a non-empty string."
            )
        if options and fixed:
            raise ConfigError(
                f"Page {page_id!r}, filter {label!r}: use either 'options' or 'fixed', not both."
            )
    else:
        raise ConfigError(
            f"Page {page_id!r}: each filter must be a label string or an object with a 'label'."
        )
    if not label:
        raise ConfigError(f"Page {page_id!r}: a filter has an empty label.")
    return FilterSpec(
        label=label, options=options, fixed=fixed.strip() if fixed else None
    )


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> dict[str, PageConfig]:
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"Page configuration not found: {path}")
    text = path.read_text(encoding="utf-8-sig")
    if not text.strip():
        raise ConfigError(f"Page configuration is empty: {path}")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ConfigError(
            f"Page configuration is not valid JSON ({path}): {exc}"
        ) from exc
    pages = data.get("pages") if isinstance(data, dict) else None
    if not isinstance(pages, dict) or not pages:
        raise ConfigError(f"{path} must contain a non-empty 'pages' object.")
    defaults = data.get("defaults") or {}

    configs: dict[str, PageConfig] = {}
    for page_id, raw in pages.items():
        if not isinstance(raw, dict):
            raise ConfigError(f"Page {page_id!r} must be an object.")
        url = raw.get("url")
        if not isinstance(url, str) or not re.match(r"^https?://", url):
            raise ConfigError(f"Page {page_id!r} needs an absolute http(s) 'url'.")
        filters = None
        if raw.get("filters") is not None:
            if not isinstance(raw["filters"], list):
                raise ConfigError(f"Page {page_id!r}: 'filters' must be a list.")
            filters = [_parse_filter(page_id, item) for item in raw["filters"]]
            labels = [norm_label(f.label) for f in filters]
            if len(set(labels)) != len(labels):
                raise ConfigError(
                    f"Page {page_id!r} lists the same filter label more than once."
                )
        for key in ("known_not_applicable", "known_no_data"):
            value = raw.get(key, [])
            if not (
                isinstance(value, list) and all(isinstance(v, dict) for v in value)
            ):
                raise ConfigError(
                    f"Page {page_id!r}: {key!r} must be a list of objects."
                )
        configs[page_id] = PageConfig(
            page_id=page_id,
            url=url,
            title=raw.get("title", page_id),
            filters=filters,
            known_not_applicable=raw.get("known_not_applicable", []),
            known_no_data=raw.get("known_no_data", []),
            gender_distribution=bool(
                raw.get(
                    "gender_distribution", defaults.get("gender_distribution", True)
                )
            ),
            date_selector=raw.get(
                "date_selector", defaults.get("date_selector", "#date")
            ),
            handled_by=raw.get("handled_by"),
        )
    return configs


def runnable_pages(configs: dict[str, PageConfig]) -> list[str]:
    return [pid for pid, cfg in configs.items() if not cfg.handled_by]


def resolve_page_ids(
    configs: dict[str, PageConfig], requested: list[str] | None, all_pages: bool
) -> list[str]:
    if all_pages:
        return runnable_pages(configs)
    ids: list[str] = []
    for item in requested or []:
        ids.extend(part.strip() for part in item.split(",") if part.strip())
    if not ids:
        raise ConfigError(
            "Choose a page with --page <id> (or --all-pages). Available: "
            + ", ".join(configs)
        )
    for pid in ids:
        if pid not in configs:
            raise ConfigError(
                f"Unknown page {pid!r}. Available pages: {', '.join(configs)}"
            )
        if configs[pid].handled_by:
            raise ConfigError(
                f"Page {pid!r} is intentionally not run by the shared engine; its data is collected by "
                f"{configs[pid].handled_by} (existing collections and indexes)."
            )
    return list(dict.fromkeys(ids))


def discover_filter_options(page, cfg: PageConfig) -> dict[str, list[str]]:
    """Read the dashboard's live options for each configured filter label.

    This allows the engine to work with minimal config (just labels) and still count all
    combinations exposed by the current page. If a filter has an explicit value in the config
    already, that fixed value wins and is not iterated. `Location` is intentionally ignored
    because the district table already contains the dimension we need at row level.
    """
    bar = read_filter_bar(page)
    found = validate_filter_bar(cfg, bar)
    live_options: dict[str, list[str]] = {}
    for spec in [s for s in (cfg.filters or []) if not ignore_filter_label(s.label)]:
        entry = found.get(norm_label(spec.label))
        if entry is None:
            continue
        control = (
            combobox_locators(page)
            .nth(entry["index"])
            .locator("xpath=ancestor::div[contains(@class, 'Select-control')]")
        )
        try:
            control.click(timeout=5000)
            page.wait_for_timeout(300)
            visible = page.locator(".VirtualizedSelectOption")
            options: list[str] = []
            for i in range(visible.count()):
                option = visible.nth(i)
                text = option.inner_text().strip() if option.is_visible() else ""
                if text and text not in options:
                    options.append(text)
            if options:
                live_options[spec.label] = options
        except (
            Exception
        ):  # noqa: BLE001 - no hard failure when a control is temporarily unavailable
            pass
        finally:
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass
            page.wait_for_timeout(200)
    return live_options


def build_combinations(
    cfg: PageConfig, page=None, discovered_options: dict[str, list[str]] | None = None
) -> list[dict]:
    """Requested filter assignments (iterated options + fixed values).

    When a page has label-based filters in nbr_pages.json, the live dropdown values must be
    discovered from the current dashboard before generating the Cartesian product. Falling back to a
    single static default assignment is only valid when no dynamic data can be discovered.
    `Location` is intentionally excluded because the district table already exposes those rows.
    """
    specs = [s for s in (cfg.filters or []) if not ignore_filter_label(s.label)]
    if page is not None and not cfg.filters:
        found = validate_filter_bar(cfg, read_filter_bar(page))
        specs = [
            FilterSpec(label=entry["label"])
            for entry in found.values()
            if not ignore_filter_label(entry["label"])
        ]

    needs_dynamic_discovery = page is not None and any(
        spec.fixed is None and spec.options is None for spec in specs
    )
    if discovered_options is None and needs_dynamic_discovery:
        discovered_options = discover_filter_options(page, cfg)

    iterated: list[tuple[str, tuple[str, ...]]] = []
    fixed: dict[str, str] = {}
    for spec in specs:
        if spec.fixed:
            fixed[spec.label] = spec.fixed
        elif spec.options:
            iterated.append((spec.label, tuple(spec.options)))
        elif discovered_options and spec.label in discovered_options:
            iterated.append((spec.label, tuple(discovered_options[spec.label])))
        elif page is not None and cfg.filters is not None:
            state = read_filter_state(page, cfg)
            value = state.get(spec.label)
            if value:
                fixed[spec.label] = value

    if not iterated:
        return [dict(fixed)]
    combos = []
    for values in itertools.product(*(opts for _, opts in iterated)):
        combo = {label: v for (label, _), v in zip(iterated, values)}
        combo.update(fixed)
        combos.append(combo)
    return combos


def matches_partial(filters: dict, patterns: list[dict]) -> bool:
    return any(
        all(
            norm_label(str(filters.get(k, ""))) == norm_label(str(v))
            for k, v in p.items()
        )
        for p in patterns
    )


# ============================================================
# DASHBOARD LOADING AND WAITING
# ============================================================


def dismiss_disclaimer(page):
    """Close the site disclaimer/login overlay so the real dashboard filters become usable."""
    selectors = [
        "#close-disclaimer",
        "button:has-text('Thanks!')",
        "button:has-text('I understand')",
        "button:has-text('Close')",
        "[role='dialog'] button",
    ]
    for attempt in range(1, 4):
        for selector in selectors:
            try:
                button = page.locator(selector)
                if button.count() and button.first.is_visible():
                    button.first.click(timeout=5000)
                    page.wait_for_timeout(800)
                    return
            except Exception:
                pass
        page.wait_for_timeout(1500)
    try:
        page.add_style_tag(content=MODAL_CSS)
        page.wait_for_timeout(300)
    except Exception:
        pass


def load_dashboard(page, url: str):
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    try:
        page.wait_for_load_state("networkidle", timeout=60000)
    except PlaywrightTimeoutError:
        log("  Network still active; continuing.")
    page.wait_for_timeout(2500)
    dismiss_disclaimer(page)
    page.add_style_tag(content=MODAL_CSS)
    page.wait_for_timeout(1200)


def wait_for_dashboard_update(page):
    updating = page.get_by_text("Updating...", exact=False)
    try:
        if updating.count() and updating.first.is_visible():
            updating.first.wait_for(state="hidden", timeout=PAGE_TIMEOUT_MS)
    except PlaywrightTimeoutError as exc:
        raise RuntimeError("Dashboard did not finish updating.") from exc
    page.wait_for_timeout(FILTER_SETTLE_MS)


# ============================================================
# DATE SELECTION (from test_nbr_date_selection.py)
# ============================================================


def load_dates(path: Path, today: str | None = None) -> tuple[list[str], set[str]]:
    """Read dates (one per line; '#' starts a comment). Returns (dates, live_dates).

    A line saying `today`/`latest` means: leave the dashboard's date alone and save the
    snapshot under the date the script ran on.
    """
    today = today or now_local().date().isoformat()
    path = Path(path)
    if not path.exists():
        return [], set()
    dates, seen, live, problems = [], set(), set(), []
    for number, raw in enumerate(
        path.read_text(encoding="utf-8-sig").splitlines(), start=1
    ):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        is_live = line.casefold() in {"today", "latest"}
        if is_live:
            line = today
        else:
            try:
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", line):
                    raise ValueError
                date.fromisoformat(line)
            except ValueError:
                problems.append(
                    f"line {number}: {raw.strip()!r} is not a valid YYYY-MM-DD date"
                )
                continue
        if line in seen:
            log(f"Note: duplicate date {line} on line {number} ignored.")
            continue
        seen.add(line)
        dates.append(line)
        if is_live:
            live.add(line)
    if problems:
        raise ConfigError("Invalid entries in dates file:\n  " + "\n  ".join(problems))
    future = [d for d in dates if d > today]
    if future:
        log(f"WARNING: skipping future dates (today is {today}): {', '.join(future)}")
        dates = [d for d in dates if d <= today]
        if not dates:
            raise ConfigError(f"No usable dates found in {path}")
    return sorted(dates), live


def wait_for_date_update(page):
    """Indicators gone AND page text stable (proven in the date-selection test)."""
    updating = page.get_by_text("Updating...", exact=False)
    try:
        for index in range(updating.count()):
            indicator = updating.nth(index)
            if indicator.is_visible():
                indicator.wait_for(state="hidden", timeout=DATE_UPDATE_TIMEOUT_MS)
    except PlaywrightTimeoutError as exc:
        raise RuntimeError(
            "The dashboard's Updating indicator did not disappear."
        ) from exc
    previous_text, stable = None, 0
    deadline = time.monotonic() + DATE_STABLE_DEADLINE_S
    while time.monotonic() < deadline:
        current = page.locator("body").inner_text()
        if current == previous_text:
            stable += 1
            if stable >= DATE_STABLE_CHECKS:
                return
        else:
            stable = 0
        previous_text = current
        time.sleep(1)
    raise RuntimeError(
        f"Dashboard text did not stabilize within {DATE_STABLE_DEADLINE_S} seconds."
    )


def read_selected_date(page, selector: str) -> str:
    return page.locator(selector).input_value().strip()


def select_date(page, selector: str, target: str):
    date_input = page.locator(selector)
    try:
        date_input.wait_for(state="visible", timeout=PAGE_TIMEOUT_MS)
    except PlaywrightTimeoutError as exc:
        raise RuntimeError(
            f"Date input {selector!r} was not found on this page; cannot select {target}."
        ) from exc
    if read_selected_date(page, selector) == target:
        return
    date_input.click()
    date_input.fill(target)
    date_input.press("Enter")
    wait_for_date_update(page)
    actual = read_selected_date(page, selector)
    if actual != target:
        raise RuntimeError(
            f"Date selection failed: expected {target}, field contains {actual!r}."
        )


def assert_date_selected(page, selector: str, target: str):
    actual = read_selected_date(page, selector)
    if actual != target:
        raise RuntimeError(
            f"Dashboard date changed unexpectedly: expected {target}, found {actual!r}."
        )


# ============================================================
# FILTERS: label-based, never positional guessing
# ============================================================


def combobox_locators(page):
    """Return the dashboard's actual filter controls, which are custom combobox inputs rather than native select elements."""
    return page.locator(
        '[role="combobox"], input[role="combobox"], .Select-input input, .Select-control input'
    )


def read_filter_bar(page) -> list[dict]:
    """Every dropdown on the page with the label and selected value read from ITS OWN card."""
    comboboxes = combobox_locators(page)
    bar = []
    for index in range(comboboxes.count()):
        field = comboboxes.nth(index)
        card = field.locator(FILTER_CARD_XPATH)
        label = value = ""
        if card.count():
            label_loc = card.locator(".dropdown-card-header, label").first
            value_loc = card.locator(
                ".Select-value-label, [class*='singleValue']"
            ).first
            label = label_loc.inner_text().strip() if label_loc.count() else ""
            value = value_loc.inner_text().strip() if value_loc.count() else ""
        bar.append({"index": index, "label": label.rstrip(":").strip(), "value": value})
    return bar


def validate_filter_bar(cfg: PageConfig, bar: list[dict]) -> dict[str, dict]:
    """Match configured labels to dropdowns. Returns {normalized label: bar entry}.

    `Location` is intentionally ignored because the district table already contains the district rows,
    and this scraper does not iterate by district as a filter dimension.
    """
    unlabeled = [b["index"] for b in bar if not b["label"]]
    if unlabeled:
        raise FilterConfigError(
            f"[{cfg.page_id}] Could not read a label for dropdown(s) at position {unlabeled}; "
            "refusing to guess which filter they are."
        )
    found: dict[str, dict] = {}
    for entry in bar:
        key = norm_label(entry["label"])
        if ignore_filter_label(entry["label"]):
            continue
        if key in found:
            raise FilterConfigError(
                f"[{cfg.page_id}] The dashboard shows the filter {entry['label']!r} more than once."
            )
        found[key] = entry
    if cfg.filters is None:
        return found  # unverified page: accept whatever is really there
    expected = {
        norm_label(s.label): s.label
        for s in cfg.filters
        if not ignore_filter_label(s.label)
    }
    missing = [label for key, label in expected.items() if key not in found]
    unexpected = [e["label"] for key, e in found.items() if key not in expected]
    if missing or unexpected:
        parts = []
        if missing:
            parts.append(f"missing from the dashboard: {missing}")
        if unexpected:
            parts.append(f"on the dashboard but not in nbr_pages.json: {unexpected}")
        raise FilterConfigError(
            f"[{cfg.page_id}] Filter mismatch - "
            + "; ".join(parts)
            + f". Dashboard filters found: {[b['label'] for b in bar if not ignore_filter_label(b['label'])]}"
        )
    return found


def read_filter_state(page, cfg: PageConfig) -> dict[str, str]:
    """Actual selected value of every filter, keyed by its (configured or observed) label."""
    found = validate_filter_bar(cfg, read_filter_bar(page))
    if cfg.filters is None:
        return {entry["label"]: entry["value"] for entry in found.values()}
    return {
        spec.label: found[norm_label(spec.label)]["value"]
        for spec in cfg.filters
        if not ignore_filter_label(spec.label)
    }


def select_filter_option(page, index: int, label: str, option_text: str):
    comboboxes = combobox_locators(page)
    if comboboxes.count() <= index:
        raise RuntimeError(f"Dropdown not found: {label}")
    control = comboboxes.nth(index).locator(
        "xpath=ancestor::div[contains(@class, 'Select-control')]"
    )
    control.click(timeout=5000)
    page.wait_for_timeout(200)
    options = page.locator(".VirtualizedSelectOption")
    for i in range(options.count()):
        option = options.nth(i)
        if (
            option.is_visible()
            and option.inner_text().strip().casefold() == option_text.casefold()
        ):
            option.click()
            wait_for_dashboard_update(page)
            return
    page.keyboard.press("Escape")
    raise OptionNotAvailableError(f"Option {option_text!r} not found for {label!r}")


def apply_filters(page, cfg: PageConfig, assignments: dict[str, str]):
    if not assignments:
        return
    found = validate_filter_bar(cfg, read_filter_bar(page))
    for label, value in list(assignments.items()):
        if ignore_filter_label(label):
            continue
        entry = found[norm_label(label)]  # present: validated above
        select_filter_option(page, entry["index"], label, value)


def verify_assignments(state: dict[str, str], assignments: dict[str, str]):
    for label, wanted in assignments.items():
        actual = state.get(label)
        if actual is None or norm_label(actual) != norm_label(wanted):
            raise RuntimeError(
                f"Filter {label!r} should be {wanted!r} but the dashboard shows {actual!r}."
            )


# ============================================================
# KPI EXTRACTION (from test_nbr_kpi_discovery.py)
# ============================================================

_PIE_CHECK_JS = """
() => Array.from(document.querySelectorAll(".js-plotly-plot")).some(plot =>
    plot.data?.some(trace =>
        trace.type === "pie" &&
        Array.isArray(trace.labels) && Array.isArray(trace.values) &&
        trace.labels.some(l => String(l).trim().toLowerCase() === "male") &&
        trace.labels.some(l => String(l).trim().toLowerCase() === "female")))
"""

_PIE_READ_JS = """
() => {
    for (const plot of document.querySelectorAll(".js-plotly-plot")) {
        const trace = plot.data?.find(trace =>
            trace.type === "pie" &&
            Array.isArray(trace.labels) && Array.isArray(trace.values) &&
            trace.labels.some(l => String(l).trim().toLowerCase() === "male") &&
            trace.labels.some(l => String(l).trim().toLowerCase() === "female"));
        if (!trace) continue;
        const total = trace.values.reduce((s, v) => s + Number(v), 0);
        if (total <= 0 || trace.values.some(v => !Number.isFinite(Number(v)) || Number(v) < 0)) return null;
        return trace.labels.map((label, i) => ({
            gender: String(label).trim(),
            percentage: Number((Number(trace.values[i]) / total * 100).toFixed(1))
        }));
    }
    return null;
}
"""

_KPI_READY_JS = """
(args) => Array.from(document.querySelectorAll(args.card)).some(card => {
    const style = getComputedStyle(card);
    const rect = card.getBoundingClientRect();
    const value = card.querySelector(args.value);
    const label = card.querySelector(args.label);
    return rect.width > 0 && rect.height > 0 && style.display !== "none" &&
           style.visibility !== "hidden" && value?.innerText.trim() && label?.innerText.trim();
})
"""


def wait_for_kpi_cards(page, timeout_ms: int) -> bool:
    try:
        page.wait_for_function(
            _KPI_READY_JS,
            arg={
                "card": KPI_CARD_SELECTOR,
                "value": KPI_VALUE_SELECTOR,
                "label": KPI_LABEL_SELECTOR,
            },
            timeout=timeout_ms,
        )
        page.wait_for_timeout(500)
        return True
    except PlaywrightTimeoutError:
        return False


def extract_headline_kpis(page) -> list[dict]:
    records = []
    cards = page.locator(KPI_CARD_SELECTOR)
    for index in range(cards.count()):
        card = cards.nth(index)
        try:
            if not card.is_visible():
                continue
            value_loc = card.locator(KPI_VALUE_SELECTOR).first
            label_loc = card.locator(KPI_LABEL_SELECTOR).first
            if not value_loc.count() or not label_loc.count():
                continue
            value, label = (
                value_loc.inner_text().strip(),
                label_loc.inner_text().strip(),
            )
            if not label or not value:
                continue
            records.append(
                {
                    "metric_type": "headline_kpi",
                    "metric_label": label,
                    "metric_value": value,  # raw text kept intact, units included
                    "gender": None,
                    "extraction_method": "headline_card",
                }
            )
        except PlaywrightTimeoutError:
            continue
    return records


def extract_gender_percentages(page, timeout_ms: int) -> list[dict]:
    try:
        page.wait_for_function(_PIE_CHECK_JS, timeout=timeout_ms)
    except PlaywrightTimeoutError:
        return []
    data = page.evaluate(_PIE_READ_JS)
    records = []
    for item in data or []:
        gender = item["gender"]
        if gender.lower() not in ("male", "female"):
            continue
        records.append(
            {
                "metric_type": "gender_distribution",
                "metric_label": f"{gender} customers",
                "metric_value": item["percentage"],
                "gender": gender,
                "extraction_method": "plotly_pie_trace",
            }
        )
    return records


# ============================================================
# TABLE EXTRACTION AND PAGINATION
# ============================================================

_TABLE_JS = """
(selector) => {
    const table = document.querySelector(selector);
    if (!table) return null;
    const headers = Array.from(table.querySelectorAll("thead th")).map(c => c.innerText.trim());
    let inferred = null;
    const rows = [];
    for (const tr of table.querySelectorAll("tr")) {
        if (tr.closest("thead")) continue;
        const cells = Array.from(tr.querySelectorAll("th, td"));
        if (!cells.length) continue;
        const values = cells.map(c => c.innerText.trim());
        if (!headers.length && inferred === null && cells.every(c => c.tagName === "TH")) {
            inferred = values;
            continue;
        }
        if (values.some(v => v)) rows.push(values);
    }
    return { headers: headers.length ? headers : (inferred || []), rows };
}
"""


def table_is_present(page) -> bool:
    table = page.locator(TABLE_SELECTOR).first
    return bool(table.count() and table.is_visible())


def open_table_view(page) -> bool:
    """True if a table is available. False if the page genuinely offers none."""
    if table_is_present(page):
        return True
    candidates = page.get_by_text("Click to view Table", exact=False)
    for index in range(candidates.count()):
        candidate = candidates.nth(index)
        if candidate.is_visible():
            candidate.click()
            page.locator(TABLE_SELECTOR).first.wait_for(
                state="visible", timeout=PAGE_TIMEOUT_MS
            )
            return True
    return False


def read_table_page(page) -> tuple[list[str], list[list[str]]]:
    page.locator(TABLE_SELECTOR).first.wait_for(
        state="visible", timeout=PAGE_TIMEOUT_MS
    )
    data = page.evaluate(_TABLE_JS, TABLE_SELECTOR)
    if data is None:
        raise RuntimeError("Dashboard table disappeared while reading it.")
    return data["headers"], data["rows"]


def _rows_text(page):
    return page.locator(f"{TABLE_SELECTOR} tr").all_inner_texts()


_ROWS_CHANGED_JS = """
(args) => {
    const table = document.querySelector(args.selector);
    if (!table) return false;
    const rows = Array.from(table.querySelectorAll('tr')).map(r => r.innerText.trim());
    return JSON.stringify(rows) !== JSON.stringify(args.before);
}
"""


def reset_table_to_first_page(page):
    first = page.locator(FIRST_BUTTON_SELECTOR).first
    if not first.count() or first.is_disabled():
        return
    before = _rows_text(page)
    first.click()
    try:
        page.wait_for_function(
            _ROWS_CHANGED_JS,
            arg={"selector": TABLE_SELECTOR, "before": before},
            timeout=PAGE_TIMEOUT_MS,
        )
    except PlaywrightTimeoutError:
        if not table_is_present(page):
            raise RuntimeError("Table disappeared while resetting pagination.")


def collect_table(page) -> dict:
    """Every row of every table page, with headers. Strict: refuses to return partial data."""
    headers: list[str] | None = None
    all_rows: list[list[str]] = []
    seen_pages = set()
    synthesized = False
    for page_number in range(1, MAX_TABLE_PAGES + 1):
        page_headers, rows = read_table_page(page)
        if not rows:
            raise EmptyDashboardTableError(
                f"Table has no data rows on page {page_number}."
            )
        if headers is None:
            headers = page_headers
            if not headers:
                headers = [f"column_{i}" for i in range(1, len(rows[0]) + 1)]
                synthesized = True
        elif page_headers and page_headers != headers:
            raise RuntimeError(
                "Table columns changed during pagination; refusing to mix different tables."
            )
        signature = stable_hash(rows)
        if signature in seen_pages:
            raise RuntimeError(
                f"Repeated table page detected at page {page_number}; refusing to save incomplete data."
            )
        seen_pages.add(signature)
        for row in rows:
            if len(row) != len(headers):
                raise RuntimeError(
                    f"Row has {len(row)} cells but the table has {len(headers)} columns: {row!r}"
                )
            all_rows.append(row)
        next_button = page.locator(NEXT_BUTTON_SELECTOR).first
        if not next_button.count() or next_button.is_disabled():
            break
        before = _rows_text(page)
        next_button.click()
        try:
            page.wait_for_function(
                _ROWS_CHANGED_JS,
                arg={"selector": TABLE_SELECTOR, "before": before},
                timeout=PAGE_TIMEOUT_MS,
            )
        except PlaywrightTimeoutError as exc:
            raise RuntimeError(
                f"Next page did not change after page {page_number}."
            ) from exc
    else:
        raise RuntimeError(
            f"Reached pagination safety limit of {MAX_TABLE_PAGES} pages."
        )
    return {
        "headers": headers,
        "rows": all_rows,
        "pages": page_number,
        "headers_synthesized": synthesized,
    }


# ============================================================
# MONGODB PERSISTENCE
# ============================================================


@dataclass
class Store:
    tables: object
    kpis: object
    runs: object
    client: object = None


def connect_mongodb() -> Store:
    load_dotenv(PROJECT_ROOT / ".env")
    uri = os.getenv("MONGODB_URI") or os.getenv("MONGO_URI")
    if not uri:
        raise ConfigError(
            "MongoDB URI not found. Add MONGODB_URI or MONGO_URI to the project .env file."
        )
    client = MongoClient(
        uri,
        serverSelectionTimeoutMS=15000,
        connectTimeoutMS=15000,
        socketTimeoutMS=30000,
    )
    try:
        client.admin.command("ping")
        db = client[DATABASE_NAME]
        store = Store(
            tables=db[TABLE_COLLECTION],
            kpis=db[KPI_COLLECTION],
            runs=db[RUN_COLLECTION],
            client=client,
        )
        ensure_indexes(store)
    except Exception:
        client.close()
        raise
    return store


def ensure_indexes(store: Store):
    base = [("page", 1), ("snapshot_date", 1), ("combo_key", 1)]
    store.tables.create_index(
        base + [("row_index", 1)], unique=True, name="uniq_page_snapshot_combo_row"
    )
    store.kpis.create_index(
        base + [("metric_type", 1), ("ordinal", 1)],
        unique=True,
        name="uniq_page_snapshot_combo_metric",
    )
    store.runs.create_index(base, unique=True, name="uniq_page_snapshot_combo_run")


def run_key(page_id: str, snapshot_date: str, combo_key: str) -> dict:
    return {"page": page_id, "snapshot_date": snapshot_date, "combo_key": combo_key}


def is_combination_terminal(
    store: Store, page_id: str, snapshot_date: str, combo_key: str
) -> bool:
    run = store.runs.find_one(run_key(page_id, snapshot_date, combo_key))
    return bool(run and run.get("status") in TERMINAL_STATUSES)


def previous_snapshot_matches(
    store: Store, page_id: str, combo_key: str, snapshot_date: str, content_hash: str
):
    previous = store.runs.find_one(
        {
            "page": page_id,
            "combo_key": combo_key,
            "snapshot_date": {"$lt": snapshot_date},
            "content_hash": content_hash,
            "status": "complete",
        },
        sort=[("snapshot_date", -1)],
    )
    return previous is not None, (previous.get("snapshot_date") if previous else None)


def _base_doc(cfg: PageConfig, snapshot_date: str, combo_key: str, meta: dict) -> dict:
    collected_at = meta["collected_at"]
    return {
        "source": SOURCE_NAME,
        "page": cfg.page_id,
        "source_url": cfg.url,
        "snapshot_date": snapshot_date,  # observation key: selected date (backfill) or run date (current)
        "combo_key": combo_key,
        "collected_at": collected_at,  # when the scraper actually ran
        "run_date": collected_at.date().isoformat(),
        "date_source": meta["date_source"],
        "dashboard_date": meta.get(
            "dashboard_date"
        ),  # what the dashboard's date field showed
        "mode": meta["mode"],
        "run_id": meta["run_id"],
    }


def save_observations(
    store, cfg, snapshot_date, assignments, filters_actual, kpi_records, table, meta
) -> dict:
    combo_key = filters_key(assignments)
    base = _base_doc(cfg, snapshot_date, combo_key, meta)
    base["filters"] = filters_actual
    base["filters_requested"] = assignments

    content_hash = stable_hash(
        {
            "kpis": [
                (r["metric_type"], r["metric_label"], r["metric_value"])
                for r in kpi_records
            ],
            "table": table and {"headers": table["headers"], "rows": table["rows"]},
        }
    )
    repeated, previous_date = previous_snapshot_matches(
        store, cfg.page_id, combo_key, snapshot_date, content_hash
    )

    if table:
        headers = table["headers"]
        district_col = next(
            (i for i, h in enumerate(headers) if norm_label(h) == "district"), None
        )
        ops = []
        for row_index, row in enumerate(table["rows"]):
            doc = dict(base)
            doc.update(
                {
                    "row_index": row_index,
                    "columns": headers,
                    "cells": row,
                    "values": dict(zip(headers, row)),  # raw text, units intact
                    "numbers": {
                        h: n
                        for h, v in zip(headers, row)
                        if (n := parse_number(v)) is not None
                    },
                    "content_hash": stable_hash(row),
                    "combination_content_hash": content_hash,
                }
            )
            if (
                district_col is not None
            ):  # district-level observation (matches the inclusion schema)
                doc["district"] = row[district_col].strip()
                doc["district_known"] = doc["district"].casefold() != "unknown"
                for field_name in ("customers", "rank"):
                    col = next(
                        (
                            i
                            for i, h in enumerate(headers)
                            if norm_label(h) == field_name
                        ),
                        None,
                    )
                    if col is not None:
                        doc[field_name] = parse_number(row[col])
            ops.append(
                UpdateOne(
                    {
                        **run_key(cfg.page_id, snapshot_date, combo_key),
                        "row_index": row_index,
                    },
                    {"$set": doc},
                    upsert=True,
                )
            )
        store.tables.bulk_write(ops, ordered=False)

    ordinals: dict[str, int] = {}
    kpi_ops = []
    for record in kpi_records:
        ordinal = ordinals.get(record["metric_type"], 0)
        ordinals[record["metric_type"]] = ordinal + 1
        doc = dict(base)
        doc.update(record)
        doc.update(
            {
                "ordinal": ordinal,
                "metric_value_numeric": parse_number(record["metric_value"]),
                "content_hash": stable_hash(record),
                "combination_content_hash": content_hash,
            }
        )
        kpi_ops.append(
            UpdateOne(
                {
                    **run_key(cfg.page_id, snapshot_date, combo_key),
                    "metric_type": record["metric_type"],
                    "ordinal": ordinal,
                },
                {"$set": doc},
                upsert=True,
            )
        )
    if kpi_ops:
        store.kpis.bulk_write(kpi_ops, ordered=False)

    run_doc = dict(base)
    run_doc.update(
        {
            "status": "complete",
            "error": None,
            "filters_key": filters_key(filters_actual),
            "filters_config_status": (
                "verified" if cfg.filters_verified else "unverified"
            ),
            "headline_kpi_count": sum(
                1 for r in kpi_records if r["metric_type"] == "headline_kpi"
            ),
            "gender_count": sum(
                1 for r in kpi_records if r["metric_type"] == "gender_distribution"
            ),
            "gender_status": meta["gender_status"],
            "table_status": "extracted" if table else "not_present",
            "table_rows": len(table["rows"]) if table else 0,
            "table_columns": table["headers"] if table else [],
            "content_hash": content_hash,
            "repeated_snapshot_warning": repeated,
            "previous_matching_snapshot_date": previous_date,
            "attempt_count": meta.get("attempt_count", 1),
        }
    )
    store.runs.update_one(
        run_key(cfg.page_id, snapshot_date, combo_key), {"$set": run_doc}, upsert=True
    )
    return {"repeated": repeated, "previous_date": previous_date}


def mark_run(
    store: Store,
    cfg: PageConfig,
    snapshot_date: str,
    combo_key: str,
    status: str,
    meta: dict,
    **extra,
):
    doc = {
        "source": SOURCE_NAME,
        "page": cfg.page_id,
        "source_url": cfg.url,
        "snapshot_date": snapshot_date,
        "combo_key": combo_key,
        "status": status,
        "mode": meta["mode"],
        "run_id": meta["run_id"],
        "date_source": meta["date_source"],
        "collected_at": now_local(),
        **extra,
    }
    store.runs.update_one(
        run_key(cfg.page_id, snapshot_date, combo_key), {"$set": doc}, upsert=True
    )


def mark_failed(store, cfg, snapshot_date, combo_key, meta, error, attempts):
    mark_run(
        store,
        cfg,
        snapshot_date,
        combo_key,
        "failed",
        meta,
        error=f"{type(error).__name__}: {error}",
        attempt_count=attempts,
        failed_at=now_local(),
    )


# ============================================================
# CSV EXPORT (per page, same style as the inclusion exports)
# ============================================================


def export_page_csv(store: Store, page_id: str):
    out_dir = OUTPUT_DIR / page_id
    out_dir.mkdir(parents=True, exist_ok=True)
    specs = [
        (
            store.tables,
            "table_observations.csv",
            [
                "page",
                "snapshot_date",
                "run_date",
                "date_source",
                "dashboard_date",
                "collected_at",
                "source_url",
                "filters",
                "row_index",
                "district",
                "customers",
                "rank",
                "values",
                "content_hash",
            ],
        ),
        (
            store.kpis,
            "kpi_observations.csv",
            [
                "page",
                "snapshot_date",
                "run_date",
                "date_source",
                "dashboard_date",
                "collected_at",
                "source_url",
                "filters",
                "metric_type",
                "metric_label",
                "metric_value",
                "metric_value_numeric",
                "gender",
                "extraction_method",
                "content_hash",
            ],
        ),
    ]
    for collection, filename, fields in specs:
        cursor = collection.find({"page": page_id}, {"_id": 0}).sort(
            [("snapshot_date", 1), ("combo_key", 1), ("collected_at", 1)]
        )
        path = out_dir / filename
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            for document in cursor:
                row = dict(document)
                for key in ("filters", "values"):
                    if isinstance(row.get(key), dict):
                        row[key] = json.dumps(
                            row[key], ensure_ascii=False, sort_keys=True
                        )
                writer.writerow(row)
        log(f"Exported: {path}")


# ============================================================
# COLLECTION WORKFLOW
# ============================================================


@dataclass
class PageRuntime:
    """Per-run memory so pages without a KPI strip / gender chart do not wait full timeouts each time."""

    kpi_wait_ms: int = PAGE_TIMEOUT_MS
    gender_wait_ms: int = field(default_factory=lambda: GENDER_WAIT_MS)
    loaded: bool = False


@dataclass
class DateOutcome:
    saved: int = 0
    skipped: int = 0
    failed: int = 0
    not_applicable: int = 0
    no_data: int = 0
    repeated: int = 0
    date_error: str | None = None


@dataclass
class PageOutcome:
    page_id: str
    dates: dict[str, DateOutcome] = field(default_factory=dict)
    page_error: str | None = None

    @property
    def failed(self) -> bool:
        return bool(
            self.page_error
            or any(d.failed or d.date_error for d in self.dates.values())
        )


def scrape_combination(
    page, cfg, runtime, snapshot_date, live, assignments, meta, store, prefix
):
    """One filter combination with retries. Returns the save result dict; raises on final failure."""
    selector = cfg.date_selector
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            log(f"  Attempt {attempt}/{MAX_RETRIES}", prefix)
            if not live:
                select_date(page, selector, snapshot_date)  # no-op when already correct
            apply_filters(page, cfg, assignments)
            state = read_filter_state(page, cfg)
            verify_assignments(state, assignments)
            if not live:
                assert_date_selected(page, selector, snapshot_date)

            kpi_ready = wait_for_kpi_cards(page, runtime.kpi_wait_ms)
            runtime.kpi_wait_ms = PAGE_TIMEOUT_MS if kpi_ready else SHORT_WAIT_MS
            records = extract_headline_kpis(page) if kpi_ready else []

            gender_status = "disabled"
            if cfg.gender_distribution:
                gender = extract_gender_percentages(page, runtime.gender_wait_ms)
                gender_status = "extracted" if gender else "absent"
                runtime.gender_wait_ms = GENDER_WAIT_MS if gender else SHORT_WAIT_MS
                records.extend(gender)

            table = None
            if open_table_view(page):
                reset_table_to_first_page(page)
                table = collect_table(page)

            if not records and not table:
                raise EmptyDashboardTableError(
                    "No KPI cards, gender chart or table could be extracted from this page."
                )
            if not kpi_ready:
                log("  NOTE: no headline KPI cards detected on this page.", prefix)
            if table is None:
                log("  NOTE: this page offers no table view; saving KPIs only.", prefix)

            if not live:
                assert_date_selected(page, selector, snapshot_date)
            dashboard_date = (
                read_selected_date(page, selector)
                if page.locator(selector).count()
                else None
            )

            meta = {
                **meta,
                "collected_at": now_local(),
                "dashboard_date": dashboard_date,
                "gender_status": gender_status,
                "attempt_count": attempt,
            }
            result = save_observations(
                store, cfg, snapshot_date, assignments, state, records, table, meta
            )
            log(
                f"  Saved {len(records)} KPI/gender records and {len(table['rows']) if table else 0} table rows "
                f"(gender chart: {gender_status}).",
                prefix,
            )
            if result["repeated"]:
                log(
                    f"  Same extracted content as an earlier snapshot ({result['previous_date']}); new date retained.",
                    prefix,
                )
            return result
        except FilterConfigError:
            raise  # deterministic: retrying cannot fix a config/dashboard mismatch
        except OptionNotAvailableError as exc:
            last_error = exc
            log(f"  FILTER ERROR: {exc}", prefix)
            break
        except Exception as exc:  # noqa: BLE001 - retried, then recorded
            last_error = exc
            log(f"  ERROR: {type(exc).__name__}: {exc}", prefix)
            if attempt < MAX_RETRIES:
                retry_pause(attempt)
    raise last_error  # type: ignore[misc]


def prepare_date(page, cfg, runtime, snapshot_date, live, prefix) -> str | None:
    """Load/select and verify the date BEFORE scraping. Returns an error string on failure."""
    if live:
        try:
            load_dashboard(page, cfg.url)
            runtime.loaded = True
            shown = (
                read_selected_date(page, cfg.date_selector)
                if page.locator(cfg.date_selector).count()
                else None
            )
            log(
                f"Live mode: dashboard shows {shown!r}; saving as snapshot_date {snapshot_date}.",
                prefix,
            )
            return None
        except Exception as exc:  # noqa: BLE001
            return f"{type(exc).__name__}: {exc}"
    last = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            log(f"Selecting date (attempt {attempt}/{MAX_RETRIES})...", prefix)
            if attempt > 1 or not runtime.loaded:
                load_dashboard(page, cfg.url)
                runtime.loaded = True
            select_date(page, cfg.date_selector, snapshot_date)
            log(
                f"Date confirmed: {read_selected_date(page, cfg.date_selector)}", prefix
            )
            return None
        except Exception as exc:  # noqa: BLE001
            last = f"{type(exc).__name__}: {exc}"
            log(f"  DATE ERROR: {last}", prefix)
            if attempt < MAX_RETRIES:
                retry_pause(attempt)
    return last


def collect_page(page, store, cfg, schedule, mode, run_id, limit=None) -> PageOutcome:
    prefix = f"[{cfg.page_id}] "
    outcome = PageOutcome(cfg.page_id)
    runtime = PageRuntime()
    load_dashboard(page, cfg.url)
    combos = build_combinations(cfg, page=page)
    if limit:
        combos = combos[:limit]
    if not cfg.filters_verified:
        log(
            "WARNING: no verified filter list in nbr_pages.json for this page; recording the filters actually "
            "shown. Run --discover to list them.",
            prefix,
        )
    log(f"URL: {cfg.url}", prefix)
    log(
        f"Filters configured: {[s.label for s in cfg.filters] if cfg.filters is not None else 'UNVERIFIED'}",
        prefix,
    )
    log(f"Combinations per date: {len(combos)}", prefix)

    for date_index, (snapshot_date, live) in enumerate(schedule, start=1):
        log("\n" + "=" * 60, prefix)
        log(
            f"DATE [{date_index}/{len(schedule)}]: {snapshot_date}"
            + ("  (LIVE: saved under run date)" if live else ""),
            prefix,
        )
        entry = outcome.dates.setdefault(snapshot_date, DateOutcome())
        date_source = "live_run_date" if live else "selected"
        meta = {"mode": mode, "run_id": run_id, "date_source": date_source}

        pending = []
        for assignments in combos:
            if is_combination_terminal(
                store, cfg.page_id, snapshot_date, filters_key(assignments)
            ):
                entry.skipped += 1
            else:
                pending.append(assignments)
        if not pending:
            log("All combinations already have terminal results; skipping.", prefix)
            continue

        error = prepare_date(page, cfg, runtime, snapshot_date, live, prefix)
        if error:
            entry.date_error = error
            mark_run(
                store, cfg, snapshot_date, "__date__", "date_failed", meta, error=error
            )
            log(
                f"Could not prepare {snapshot_date}; NOT scraping it, to avoid saving data under the wrong date.",
                prefix,
            )
            runtime.loaded = False
            continue

        for index, assignments in enumerate(pending, start=1):
            ck = filters_key(assignments)
            log(
                f"\n[{snapshot_date}] [{index}/{len(pending)}] requested filters: {assignments or 'default view'}",
                prefix,
            )
            if matches_partial(assignments, cfg.known_not_applicable):
                mark_run(
                    store,
                    cfg,
                    snapshot_date,
                    ck,
                    "not_applicable",
                    meta,
                    filters_requested=assignments,
                    reason="Configured as not applicable for this page.",
                )
                entry.not_applicable += 1
                log("  Not applicable; recorded without retrying.", prefix)
                continue
            if matches_partial(assignments, cfg.known_no_data):
                mark_run(
                    store,
                    cfg,
                    snapshot_date,
                    ck,
                    "completed_no_data",
                    meta,
                    filters_requested=assignments,
                    reason="Configured as having no data for this page.",
                )
                entry.no_data += 1
                log(
                    "  Confirmed no-data combination; recorded without retrying.",
                    prefix,
                )
                continue
            try:
                result = scrape_combination(
                    page,
                    cfg,
                    runtime,
                    snapshot_date,
                    live,
                    assignments,
                    meta,
                    store,
                    prefix,
                )
                entry.saved += 1
                entry.repeated += int(bool(result["repeated"]))
            except FilterConfigError as exc:
                mark_failed(store, cfg, snapshot_date, ck, meta, exc, 1)
                outcome.page_error = str(exc)
                log(f"  PAGE ABORTED: {exc}", prefix)
                return outcome  # nothing else on this page can be trusted
            except Exception as exc:  # noqa: BLE001
                mark_failed(store, cfg, snapshot_date, ck, meta, exc, MAX_RETRIES)
                entry.failed += 1
                log(
                    "  Marked failed; will retry on a later run for this same snapshot date.",
                    prefix,
                )

        if entry.saved and entry.repeated == entry.saved:
            log(
                f"\nWARNING: every combination scraped for {snapshot_date} is identical to an earlier date. "
                "Please confirm the dashboard data really changed.",
                prefix,
            )
    return outcome


def discover_page(page, cfg: PageConfig) -> dict:
    """Read-only: print real filter labels, selected values and options. Writes nothing to the DB."""
    load_dashboard(page, cfg.url)
    bar = read_filter_bar(page)
    log(f"[{cfg.page_id}] {cfg.url}")
    discovered = []
    for entry in bar:
        options: list[str] = []
        control = (
            combobox_locators(page)
            .nth(entry["index"])
            .locator("xpath=ancestor::div[contains(@class, 'Select-control')]")
        )
        try:
            control.click(timeout=5000)
            page.wait_for_timeout(300)
            visible = page.locator(".VirtualizedSelectOption")
            for i in range(visible.count()):
                option = visible.nth(i)
                text = option.inner_text().strip() if option.is_visible() else ""
                if text and text not in options:
                    options.append(text)
        except Exception as exc:  # noqa: BLE001
            log(f"  could not read options for {entry['label']!r}: {exc}")
        finally:
            page.keyboard.press("Escape")
            page.wait_for_timeout(200)
        discovered.append(
            {"label": entry["label"], "selected": entry["value"], "options": options}
        )
        log(
            f"  [{entry['index']}] {entry['label']!r}: selected={entry['value']!r} options={options}"
        )
    snippet = {"url": cfg.url, "filters": [d["label"] for d in discovered]}
    log(
        '\nPaste into nbr_pages.json to verify this page (add {"label":..., "options":[...]} to iterate):'
    )
    log(json.dumps(snippet, indent=2, ensure_ascii=False))
    return {"page": cfg.page_id, "filters": discovered}


# ============================================================
# CLI
# ============================================================


def build_parser(mode: str) -> argparse.ArgumentParser:
    description = {
        "backfill": "Backfill NBR dashboard pages across the dates in the dates file.",
        "current": "Collect the current NBR dashboard snapshot (saved under today's run date).",
    }[mode]
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--page",
        action="append",
        help="Page id from nbr_pages.json (repeat, or comma-separate).",
    )
    parser.add_argument(
        "--all-pages", action="store_true", help="Run every page in nbr_pages.json."
    )
    parser.add_argument(
        "--list-pages", action="store_true", help="Show configured pages and exit."
    )
    parser.add_argument(
        "--discover",
        action="store_true",
        help="Print the live filter labels/options for --page and exit.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="Page configuration JSON.",
    )
    parser.add_argument(
        "--headed", action="store_true", help="Show the browser window."
    )
    parser.add_argument(
        "--limit-combinations",
        type=int,
        help="Only scrape the first N filter combinations (testing).",
    )
    if mode == "backfill":
        parser.add_argument(
            "--dates-file",
            type=Path,
            default=DEFAULT_DATES_FILE,
            help="One YYYY-MM-DD date per line.",
        )
        parser.add_argument(
            "--today",
            action="store_true",
            help="Also scrape the current dashboard under today's run date.",
        )
    return parser


def build_schedule(mode: str, args) -> list[tuple[str, bool]]:
    today = now_local().date().isoformat()
    if mode == "current":
        return [(today, True)]
    dates, live = load_dates(args.dates_file, today)
    if args.today and today not in dates:
        dates, live = sorted(dates + [today]), live | {today}
    if not dates:
        raise ConfigError(
            f"No dates found in {args.dates_file}. Add dates, a `today` line, or pass --today."
        )
    return [(d, d in live) for d in dates]


def print_summary(outcomes: list[PageOutcome]):
    log("\n--- SUMMARY ---")
    log(
        f"{'Page':<18}{'Date':<12}{'Saved':>6}{'Skip':>6}{'N/A':>5}{'NoData':>7}{'Fail':>6}{'Repeat':>7}"
    )
    for outcome in outcomes:
        if outcome.page_error:
            log(f"{outcome.page_id:<18}PAGE ABORTED: {outcome.page_error}")
        for snapshot_date, d in outcome.dates.items():
            if d.date_error:
                log(
                    f"{outcome.page_id:<18}{snapshot_date:<12}DATE FAILED: {d.date_error}"
                )
                continue
            log(
                f"{outcome.page_id:<18}{snapshot_date:<12}{d.saved:>6}{d.skipped:>6}{d.not_applicable:>5}"
                f"{d.no_data:>7}{d.failed:>6}{d.repeated:>7}"
            )


def run_cli(
    mode: str, argv: list[str] | None = None, store: Store | None = None
) -> int:
    """Shared entry point. `store` may be injected (tests); otherwise MongoDB is opened from .env."""
    args = build_parser(mode).parse_args(argv)
    try:
        configs = load_config(args.config)
        if args.list_pages:
            for pid, cfg in configs.items():
                state = (
                    f"handled by {cfg.handled_by}"
                    if cfg.handled_by
                    else (
                        f"{len(cfg.filters)} filters"
                        if cfg.filters is not None
                        else "filters UNVERIFIED"
                    )
                )
                log(f"{pid:<18}{cfg.url}  ({state})")
            return 0
        page_ids = resolve_page_ids(configs, args.page, args.all_pages)
        schedule = None if args.discover else build_schedule(mode, args)
    except ConfigError as exc:
        log(f"CONFIG ERROR: {exc}")
        return 2

    run_id = uuid.uuid4().hex[:12]
    log("NBR Financial Inclusion Dashboard scraper")
    log(
        f"Mode: {'DISCOVER' if args.discover else mode.upper()} | run_id: {run_id} | pages: {', '.join(page_ids)}"
    )
    if schedule:
        log(
            f"Dates ({len(schedule)}): "
            + ", ".join(d + ("*" if live else "") for d, live in schedule)
            + (
                "   (* = live: saved under run date)"
                if any(live for _, live in schedule)
                else ""
            )
        )

    limit = args.limit_combinations or (
        int(os.getenv("SCRAPER_MAX_COMBINATIONS", "0") or 0) or None
    )
    owns_store = False
    outcomes: list[PageOutcome] = []
    try:
        if not args.discover and store is None:
            store = connect_mongodb()
            owns_store = True
            log("MongoDB connection successful.")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=not args.headed)
            try:
                page = browser.new_page(viewport={"width": 1440, "height": 1000})
                page.set_default_timeout(PAGE_TIMEOUT_MS)
                for pid in page_ids:
                    cfg = configs[pid]
                    try:
                        if args.discover:
                            discover_page(page, cfg)
                            continue
                        outcomes.append(
                            collect_page(
                                page, store, cfg, schedule, mode, run_id, limit
                            )
                        )
                    except (
                        Exception
                    ) as exc:  # noqa: BLE001 - one page must not take down the others
                        log(f"[{pid}] PAGE FAILED: {type(exc).__name__}: {exc}")
                        outcomes.append(
                            PageOutcome(pid, page_error=f"{type(exc).__name__}: {exc}")
                        )
            finally:
                browser.close()
        if args.discover:
            return 0
        for outcome in outcomes:
            export_page_csv(store, outcome.page_id)
        print_summary(outcomes)
        failed = [o.page_id for o in outcomes if o.failed]
        if failed:
            log(
                f"\nFailures on: {', '.join(failed)}. Rerun the same command: completed combinations are skipped, "
                "so only failures are retried. Existing records were not deleted."
            )
            return 1
        log("\nAll requested pages completed. Existing records were not deleted.")
        return 0
    except KeyboardInterrupt:
        log(
            "\nInterrupted. Browser and database connections are being closed; completed work is already saved."
        )
        if outcomes:
            print_summary(outcomes)
        return 130
    finally:
        if owns_store and store is not None and store.client is not None:
            store.client.close()
