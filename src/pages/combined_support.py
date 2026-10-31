"""Shared helpers for the Combined (FinScope + NBR) experience.

Design rules enforced here:

* FinScope and NBR values are never combined arithmetically. Nothing in this
  module subtracts, divides, correlates, or scores across the two sources.
* Every "no NBR context" outcome is classified into an explicit evidence
  state, so a missing observation is never shown as zero or silently omitted.
* Recommendations are restrained: they say what the displayed evidence
  supports, what needs investigation or verification, what to monitor, and
  what cannot yet be recommended. They never recommend building or deploying
  infrastructure.

The classification and recommendation logic is pure Python so it can be tested
without Streamlit, MongoDB, or the project data files.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

# ---------------------------------------------------------------------------
# Evidence states
# ---------------------------------------------------------------------------
STATE_AVAILABLE = "available"
STATE_NO_COUNTERPART = "no_counterpart"
STATE_NOT_APPROVED = "not_approved"
STATE_LEVEL_UNSUPPORTED = "level_unsupported"
STATE_SCOPE_UNSUPPORTED = "scope_unsupported"
STATE_NO_OBSERVATION = "no_observation"
STATE_LOAD_ERROR = "load_error"
STATE_SUPPRESSED = "suppressed"

STATE_TITLES = {
    STATE_AVAILABLE: "NBR context available",
    STATE_NO_COUNTERPART: "No NBR counterpart",
    STATE_NOT_APPROVED: "NBR series not approved",
    STATE_LEVEL_UNSUPPORTED: "NBR does not cover this level",
    STATE_SCOPE_UNSUPPORTED: "NBR does not cover this dimension",
    STATE_NO_OBSERVATION: "No NBR observation",
    STATE_LOAD_ERROR: "NBR context unavailable",
    STATE_SUPPRESSED: "NBR series intentionally not shown",
}

LEVEL_LABELS = {"national": "national", "district": "district"}


@dataclass(frozen=True)
class ContextState:
    """Why NBR context is (or is not) shown for a FinScope view."""

    state: str
    body: str

    @property
    def title(self) -> str:
        return STATE_TITLES.get(self.state, "NBR context")

    @property
    def available(self) -> bool:
        return self.state == STATE_AVAILABLE


def classify_mapping(
    mapping: Mapping[str, Any] | None,
    level: str,
) -> ContextState | None:
    """Classify the *configuration* (no data loaded).

    Returns None when an approved contextual relationship exists at ``level``;
    otherwise the reason NBR context cannot be shown.
    """
    if mapping is None:
        return ContextState(
            STATE_NO_COUNTERPART,
            "No NBR relationship is configured for this indicator.",
        )
    relationships = list(mapping.get("nbr_relationships") or [])
    contextual = [
        item for item in relationships
        if item.get("relationship") == "contextual_indicator"
        and not item.get("suppressed")
    ]
    if not contextual:
        suppressed = [item for item in relationships if item.get("suppressed")]
        if suppressed:
            reasons = list(dict.fromkeys(
                str(item.get("suppression_reason") or "").strip()
                for item in suppressed if item.get("suppression_reason")
            ))
            return ContextState(
                STATE_SUPPRESSED,
                " ".join(reasons)
                or "A related NBR series is configured but intentionally not shown for this indicator.",
            )
        reason = str(mapping.get("nbr_no_relevant_data_reason") or "").strip()
        if any(
            item.get("relationship") == "proxy_with_unresolved_definition"
            for item in relationships
        ):
            return ContextState(
                STATE_NOT_APPROVED,
                "Only proxy NBR series with unresolved definitions exist for this "
                "indicator, so none is displayed."
                + (f" {reason}" if reason else ""),
            )
        return ContextState(
            STATE_NO_COUNTERPART,
            reason or "No approved NBR series is relevant to this indicator.",
        )
    if not any(level in (item.get("available_levels") or []) for item in contextual):
        offered = sorted({
            LEVEL_LABELS.get(lv, lv)
            for item in contextual for lv in (item.get("available_levels") or [])
        })
        return ContextState(
            STATE_LEVEL_UNSUPPORTED,
            f"Approved NBR context for this indicator exists at the "
            f"{' and '.join(offered) or 'unspecified'} level only, not at the "
            f"{LEVEL_LABELS.get(level, level)} level.",
        )
    return None


def classify_context(
    mapping: Mapping[str, Any] | None,
    level: str,
    entries: Sequence[Mapping[str, Any]] | None,
    *,
    error: BaseException | None = None,
    geography: str | None = None,
    scope_label: str = "",
) -> ContextState:
    """Classify the outcome of a context lookup.

    ``entries`` must already be limited to the requested geography/scope; an
    empty list for an approved mapping is a missing observation, not a zero.
    """
    if error is not None:
        return ContextState(
            STATE_LOAD_ERROR,
            "The NBR source could not be read, so no NBR context is shown. "
            "FinScope values are unaffected.",
        )
    configuration = classify_mapping(mapping, level)
    if configuration is not None:
        return configuration
    if any(entry.get("points") for entry in entries or []):
        return ContextState(STATE_AVAILABLE, "")
    where = f" for {geography}" if geography else ""
    scope = f" ({scope_label})" if scope_label else ""
    return ContextState(
        STATE_NO_OBSERVATION,
        f"An NBR series is approved for this indicator, but no observation is "
        f"recorded{where}{scope}. Missing is not zero and does not mean services "
        "are absent.",
    )


#: Population dimensions the survey reports that the NBR source cannot match.
SCOPE_LIMITS = {
    "Age group": (
        STATE_SCOPE_UNSUPPORTED,
        "NBR reports Youth and Non-Youth only. Those categories are not "
        "crosswalked to FinScope age groups, so no NBR context is shown here.",
    ),
    "Education": (
        STATE_SCOPE_UNSUPPORTED,
        "NBR has no education breakdown, so this comparison uses FinScope alone.",
    ),
    "Area": (
        STATE_SCOPE_UNSUPPORTED,
        "NBR has no urban/rural breakdown, so this comparison uses FinScope alone.",
    ),
}


def scope_state(group_type: str) -> ContextState | None:
    """State for a population dimension NBR does not cover (None for Gender)."""
    limit = SCOPE_LIMITS.get(group_type)
    return ContextState(*limit) if limit else None


_NBR_PAGES_PATH = Path(__file__).resolve().parents[2] / "nbr_pages.json"
_UNSET: Any = object()


@lru_cache(maxsize=4)
def _read_page_filters(path: str) -> dict[str, dict[str, str]] | None:
    try:
        with open(path, encoding="utf-8") as handle:
            pages = json.load(handle)["pages"]
    except (OSError, ValueError, KeyError):
        return None
    result: dict[str, dict[str, str]] = {}
    for page_id, config in pages.items():
        kinds = {}
        for item in config.get("filters", []):
            label = str(item.get("label", ""))
            kinds[label] = (
                "ignored" if item.get("ignore")
                else "fixed" if "fixed" in item
                else "dynamic"
            )
        result[str(page_id)] = kinds
    return result


def load_nbr_page_filters(path: str | Path | None = None) -> dict[str, dict[str, str]] | None:
    """Which filters each NBR page actually exposes, from the scraper configuration.

    ``dynamic`` filters are discovered with all their options and stored per option;
    ``fixed`` and ``ignored`` ones are not available as breakdowns. Returns None when
    the configuration cannot be read, which callers must treat as *unknown*.
    """
    return _read_page_filters(str(path or _NBR_PAGES_PATH))


def classify_subgroup_scope(
    mapping: Mapping[str, Any] | None,
    level: str,
    subgroup_type: str,
    page_filters: Mapping[str, Mapping[str, str]] | None,
) -> ContextState | None:
    """Gender support for the exact pages behind an indicator (None = not ruled out).

    A page can only hold gender-specific observations if it exposes a dynamic Gender
    filter. When every contextual page for the indicator lacks one, the absence is a
    scope limit of the source, not a missing observation. If the configuration is
    unreadable or does not list a page, support is unknown and nothing is claimed.
    """
    if subgroup_type != "Gender" or page_filters is None or not mapping:
        return None
    pages = sorted({
        str(item.get("page"))
        for item in mapping.get("nbr_relationships") or []
        if item.get("relationship") == "contextual_indicator"
        and not item.get("suppressed")
        and level in (item.get("available_levels") or [])
    })
    if not pages or any(page not in page_filters for page in pages):
        return None
    if any(page_filters[page].get("Gender") == "dynamic" for page in pages):
        return None
    names = ", ".join(page.replace("_", " ").title() for page in pages)
    return ContextState(
        STATE_SCOPE_UNSUPPORTED,
        f"The NBR page behind this indicator ({names}) has no Gender breakdown, so NBR "
        "gender context cannot be shown. The survey comparison is unaffected.",
    )


def eligible_state(state: ContextState, entries: Sequence[Mapping[str, Any]] | None) -> ContextState:
    """State after page-level eligibility filtering.

    If a series was available but none of it is eligible for the view, say so; this is
    a display decision, not "no counterpart" and not a missing observation.
    """
    if state.available and not any(entry.get("points") for entry in entries or []):
        return ContextState(
            STATE_SUPPRESSED,
            "NBR records exist for this indicator, but none of the series is eligible "
            "for this view, so none is shown.",
        )
    return state


def resolve_reporting_date(dates: Sequence[str], current: str | None) -> str | None:
    """Keep the user's chosen date only if this series has it; otherwise the latest."""
    ordered = sorted({str(day) for day in dates})
    if not ordered:
        return None
    return current if current in ordered else ordered[-1]


def entry_dates(entry: Mapping[str, Any] | None) -> list[str]:
    """Reporting dates with at least one valid observation in a series."""
    return distinct_dates((entry or {}).get("points", []))


def reporting_date_choice(session: Any, key: str, dates: Sequence[str]) -> str | None:
    """Effective reporting date for a series; a stored choice this series lacks is dropped.

    ``session`` is any mutable mapping (Streamlit's ``session_state``). The key should
    identify the series (indicator, series, source version) so a date chosen for one
    series can never carry over to another.
    """
    ordered = sorted({str(day) for day in dates})
    if not ordered:
        session.pop(key, None)
        return None
    if session.get(key) not in ordered:
        session.pop(key, None)
    return session.get(key, ordered[-1])


def missing_indicator_note(registry: Iterable[Mapping[str, Any]], frame: Any, table: str) -> str:
    """Name registered indicators absent from a processed table (never invents columns)."""
    columns = set(getattr(frame, "columns", []))
    missing = [str(item.get("short") or item["variable"]) for item in registry if item["column"] not in columns]
    if not missing:
        return ""
    return (
        f"The {table} table does not include: {', '.join(missing)}. "
        "These indicators are not shown for this comparison; nothing has been estimated in their place."
    )


#: Survey questions that follow routing. The existing calculation is unchanged; this
#: wording tells readers what the figure does and does not establish.
ROUTED_INDICATOR_NOTES = {
    "qf4_06": (
        "Many respondents have no recorded answer to this question because it follows "
        "survey routing. The existing calculation counts them as non-users, so this is "
        "the share reporting current use among all respondents, not a confirmed non-use rate."
    ),
    "qf4_10": (
        "Many respondents have no recorded answer to this question because it follows "
        "survey routing. The existing calculation counts them as non-users, so this is "
        "the share reporting current use among all respondents, not a confirmed non-use rate."
    ),
}


def routed_note(variable: str) -> str:
    return ROUTED_INDICATOR_NOTES.get(variable, "")


# ---------------------------------------------------------------------------
# Observation helpers
# ---------------------------------------------------------------------------
def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def valid_points(points: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Observed points with a usable date and a finite, non-negative value."""
    result = []
    for point in points or []:
        value = _finite(point.get("value"))
        if value is None or value < 0:
            continue
        try:
            date.fromisoformat(str(point.get("reporting_date", "")))
        except ValueError:
            continue
        result.append(dict(point))
    return sorted(result, key=lambda item: str(item["reporting_date"]))


def distinct_dates(points: Iterable[Mapping[str, Any]]) -> list[str]:
    return sorted({str(item["reporting_date"]) for item in valid_points(points)})


def latest_point(points: Iterable[Mapping[str, Any]]) -> dict[str, Any] | None:
    ordered = valid_points(points)
    return ordered[-1] if ordered else None


def quality_flags(points: Iterable[Mapping[str, Any]]) -> list[str]:
    """Short, user-facing quality qualifications attached to observations."""
    flags: list[str] = []
    for point in points or []:
        if point.get("repeated_snapshot_warning") is True:
            flags.append("Some snapshots repeat an earlier value; read the trend with care.")
        for item in point.get("quality_qualifications") or []:
            reason = item.get("reason") if isinstance(item, Mapping) else None
            if reason:
                flags.append(str(reason))
    return list(dict.fromkeys(flags))


def entries_for_geography(
    entries: Sequence[Mapping[str, Any]] | None,
    geography: str | None,
) -> list[dict[str, Any]]:
    """Restrict series to one district without altering metric, unit or filters."""
    if geography is None:
        return [dict(entry) for entry in entries or [] if entry.get("points")]
    target = geography.casefold()
    local = []
    for entry in entries or []:
        points = [
            dict(point) for point in entry.get("points", [])
            if str(point.get("geography", "")).casefold() == target
        ]
        if points:
            local.append({**entry, "points": points})
    return local


def snapshot_points(
    entry: Mapping[str, Any] | None,
    reporting_date: str | None = None,
) -> tuple[list[dict[str, Any]], str]:
    """All district observations of one series on its latest (or given) date."""
    if not entry:
        return [], ""
    points = valid_points(entry.get("points", []))
    if not points:
        return [], ""
    chosen = reporting_date or str(points[-1]["reporting_date"])
    return [p for p in points if str(p["reporting_date"]) == chosen], chosen


def district_state(
    series_state: ContextState,
    local_entries: Sequence[Mapping[str, Any]],
    district: str,
    *,
    label: str = "",
) -> ContextState:
    """State for one district given the state of the all-district series."""
    if not series_state.available:
        return series_state
    if any(valid_points(entry.get("points", [])) for entry in local_entries or []):
        return ContextState(STATE_AVAILABLE, "")
    series = f" in {label}" if label else ""
    return ContextState(
        STATE_NO_OBSERVATION,
        f"NBR records this series for other districts, but no observation{series} "
        f"for {district}. Missing is not zero and does not mean services are absent.",
    )


def snapshot_table(points: Sequence[Mapping[str, Any]], names: Iterable[str]):
    """One row per district: the recorded value, or an explicit 'no observation'."""
    import pandas as pd

    by_name = {str(p.get("geography", "")).casefold(): p for p in points or []}
    rows = []
    for name in names:
        point = by_name.get(str(name).casefold())
        rows.append({
            "District": name,
            "NBR value": point["value"] if point else None,
            "Unit": (point.get("unit") or "unit not specified") if point else "",
            "Reporting date": point["reporting_date"] if point else "",
            "Status": "Recorded" if point else "No observation (not zero)",
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------
KIND_SUPPORTED = "supported"
KIND_INVESTIGATE = "investigate"
KIND_VERIFY = "verify"
KIND_MONITOR = "monitor"
KIND_NOT_SUPPORTED = "not_supported"

KIND_LABELS = {
    KIND_SUPPORTED: "Evidence supports",
    KIND_INVESTIGATE: "Investigate",
    KIND_VERIFY: "Verify data",
    KIND_MONITOR: "Monitor",
    KIND_NOT_SUPPORTED: "Not yet supportable",
}
KIND_ORDER = (
    KIND_SUPPORTED, KIND_INVESTIGATE, KIND_VERIFY, KIND_MONITOR, KIND_NOT_SUPPORTED,
)


@dataclass(frozen=True)
class Recommendation:
    kind: str
    text: str


def _plural(count: int, singular: str, plural: str | None = None) -> str:
    return f"{count} {singular if count == 1 else (plural or singular + 's')}"


def _nbr_coverage_recommendations(
    state: ContextState,
    *,
    label: str,
    geography: str | None,
    date_count: int,
    flags: Sequence[str] = (),
) -> list[Recommendation]:
    """Recommendations that depend only on NBR availability (no values compared)."""
    where = f" in {geography}" if geography else ""
    items: list[Recommendation] = []
    if state.state == STATE_AVAILABLE:
        if date_count < 2:
            items.append(Recommendation(
                KIND_MONITOR,
                f"NBR has recorded {label}{where} on {_plural(date_count, 'reporting date')}. "
                "A trend cannot be read yet; check the next reporting period.",
            ))
        else:
            items.append(Recommendation(
                KIND_MONITOR,
                f"Re-check {label}{where} at the next NBR reporting period. "
                f"{_plural(date_count, 'comparable reporting date')} are recorded so far.",
            ))
        if flags:
            items.append(Recommendation(
                KIND_VERIFY,
                "The source attaches quality qualifications to this series; read them "
                "before relying on the administrative count.",
            ))
    elif state.state == STATE_NO_OBSERVATION:
        items.append(Recommendation(
            KIND_VERIFY,
            f"Confirm with the NBR source whether {label} is reported{where}. "
            "Until then, treat the absence as unknown rather than as no services.",
        ))
    elif state.state == STATE_LOAD_ERROR:
        items.append(Recommendation(
            KIND_VERIFY,
            "Reload the NBR observations from the sidebar before drawing any "
            "supply-side reading.",
        ))
    else:
        items.append(Recommendation(
            KIND_NOT_SUPPORTED,
            "No supply-side recommendation can be made from NBR for this view: "
            + state.body[:1].lower() + state.body[1:],
        ))
    return items


def finscope_position_recommendation(
    *,
    place: str,
    indicator: str,
    polarity: str,
    diff_pp: float,
    margin_pp: float | None,
) -> Recommendation:
    """What a district-vs-national FinScope difference does and does not support."""
    size = abs(diff_pp)
    if polarity == "neutral":
        return Recommendation(
            KIND_SUPPORTED,
            f"{indicator} is descriptive: {place} differs from the national estimate "
            f"by {size:.1f} pp, with no inherently favourable direction.",
        )
    unfavourable = diff_pp < 0 if polarity == "positive" else diff_pp > 0
    if size == 0:
        return Recommendation(
            KIND_SUPPORTED,
            f"{place} is at the national estimate for {indicator}; the survey shows no gap here.",
        )
    if not unfavourable:
        return Recommendation(
            KIND_SUPPORTED,
            f"{place} is {size:.1f} pp on the more favourable side of the national "
            f"estimate for {indicator}; the survey shows no gap here.",
        )
    if margin_pp is not None and size > margin_pp:
        return Recommendation(
            KIND_INVESTIGATE,
            f"{place} is {size:.1f} pp on the less favourable side of the national "
            f"estimate for {indicator}, beyond its illustrative margin (±{margin_pp:.1f} pp). "
            "Look at the reported barriers and local service context next; the survey "
            "does not explain the difference.",
        )
    return Recommendation(
        KIND_NOT_SUPPORTED,
        f"{place} is {size:.1f} pp on the less favourable side of the national "
        f"estimate for {indicator}, within its illustrative margin"
        + (f" (±{margin_pp:.1f} pp)" if margin_pp is not None else "")
        + ". This is not strong enough to treat as a gap.",
    )


def district_recommendations(
    *,
    district: str,
    indicator: str,
    polarity: str,
    diff_pp: float,
    margin_pp: float | None,
    state: ContextState,
    nbr_label: str = "",
    local_points: Sequence[Mapping[str, Any]] = (),
    signal_found: bool = False,
) -> list[Recommendation]:
    items = [finscope_position_recommendation(
        place=district, indicator=indicator, polarity=polarity,
        diff_pp=diff_pp, margin_pp=margin_pp,
    )]
    flags = quality_flags(local_points)
    items.extend(_nbr_coverage_recommendations(
        state,
        label=nbr_label or "this NBR series",
        geography=district,
        date_count=len(distinct_dates(local_points)),
        flags=flags,
    ))
    if signal_found:
        items.append(Recommendation(
            KIND_VERIFY,
            "The existing NBR review detector returned a signal for this district. It "
            "is a prompt to check the source row, collection run and filters, not a "
            "finding about access.",
        ))
    return items


def priority_recommendations(
    *,
    district: str,
    rank: int,
    total: int,
    score: float,
    driver: str | None,
    driver_points: float,
    top10_count: int,
    combos: int,
    states: Mapping[str, ContextState],
    missing_district: Sequence[str] = (),
) -> list[Recommendation]:
    """Priority-screen recommendations. NBR never enters the score."""
    items: list[Recommendation] = []
    if score > 0 and driver:
        items.append(Recommendation(
            KIND_SUPPORTED,
            f"Under the selected indicators {district} ranks #{rank} of {total} on the "
            "relative FinScope gap score.",
        ))
        items.append(Recommendation(
            KIND_INVESTIGATE,
            f"{driver} contributes the most ({driver_points:.1f} points). Start the "
            "district review with that indicator and the reported barriers.",
        ))
    else:
        items.append(Recommendation(
            KIND_SUPPORTED,
            f"{district} shows no gap above the national estimate on the selected "
            "indicators, so the screen gives no reason to prioritise it.",
        ))
    if combos and top10_count < combos / 2:
        items.append(Recommendation(
            KIND_NOT_SUPPORTED,
            f"The rank is sensitive to indicator choice (top 10 in {top10_count} of "
            f"{combos} combinations), so it should not be read as a stable priority.",
        ))
    shown = [name for name, st_ in states.items() if st_.available]
    if missing_district:
        items.append(Recommendation(
            KIND_VERIFY,
            f"No NBR observation is recorded for {district} for: "
            f"{', '.join(missing_district)}. Confirm reporting coverage; absence is "
            "unknown, not zero.",
        ))
    no_counterpart = [
        name for name, st_ in states.items()
        if st_.state in (
            STATE_NO_COUNTERPART, STATE_NOT_APPROVED, STATE_LEVEL_UNSUPPORTED,
        )
    ]
    if no_counterpart:
        items.append(Recommendation(
            KIND_NOT_SUPPORTED,
            "No district-level NBR counterpart exists for: "
            f"{', '.join(no_counterpart)}. Supply-side context cannot be reviewed for these.",
        ))
    suppressed = [name for name, st_ in states.items() if st_.state == STATE_SUPPRESSED]
    if suppressed:
        items.append(Recommendation(
            KIND_NOT_SUPPORTED,
            f"A related NBR series is intentionally not shown for: {', '.join(suppressed)}, "
            "because it is not an approved proxy. This is a display decision, not a missing observation.",
        ))
    failed = [name for name, st_ in states.items() if st_.state == STATE_LOAD_ERROR]
    if failed:
        items.append(Recommendation(
            KIND_VERIFY,
            f"NBR context could not be loaded for: {', '.join(failed)}. Its absence here "
            "says nothing about whether the service or observation exists.",
        ))
    if shown:
        items.append(Recommendation(
            KIND_MONITOR,
            "NBR context for "
            f"{', '.join(shown)} is shown for reference only and does not change the "
            "score. Re-check it at the next reporting period.",
        ))
    return items


def group_recommendations(
    *,
    group_type: str,
    indicator: str,
    high_group: str,
    low_group: str,
    gap_pp: float,
    exceeds_margin: bool,
    small_groups: Sequence[str],
    gender_states: Mapping[str, ContextState] | None = None,
) -> list[Recommendation]:
    items: list[Recommendation] = []
    if exceeds_margin:
        items.append(Recommendation(
            KIND_INVESTIGATE,
            f"The {gap_pp:.1f} pp difference between {high_group} and {low_group} on "
            f"{indicator} exceeds the illustrative margin. Examine what the survey "
            f"records for {low_group} (barriers, channels used) before choosing any response.",
        ))
    else:
        items.append(Recommendation(
            KIND_NOT_SUPPORTED,
            f"The {gap_pp:.1f} pp difference between {high_group} and {low_group} is "
            "within the illustrative margin, so it should not be treated as a group gap.",
        ))
    if small_groups:
        items.append(Recommendation(
            KIND_VERIFY,
            f"{', '.join(small_groups)} rest on few respondents. A larger sample or a "
            "pooled estimate is needed before relying on them.",
        ))
    scope = scope_state(group_type)
    if scope is not None:
        items.append(Recommendation(
            KIND_NOT_SUPPORTED,
            "Supply-side context cannot be compared across these groups: "
            + scope.body[:1].lower() + scope.body[1:],
        ))
        items.append(Recommendation(
            KIND_VERIFY,
            f"Collecting {group_type.lower()}-level administrative data would be "
            "needed before any supply-side reading by this dimension.",
        ))
    elif gender_states is not None:
        have = [g for g, s in gender_states.items() if s.available]
        lacking = [g for g, s in gender_states.items() if not s.available]
        if have and not lacking:
            items.append(Recommendation(
                KIND_MONITOR,
                "NBR records a gender-specific series for every group shown. Track it "
                "over reporting periods; its counts are not comparable with survey percentages.",
            ))
        elif have:
            items.append(Recommendation(
                KIND_VERIFY,
                f"NBR has a gender-specific observation for {', '.join(have)} but not for "
                f"{', '.join(lacking)}. Confirm whether the missing category is unreported "
                "before comparing groups.",
            ))
        else:
            first = next(iter(gender_states.values()), None)
            items.append(Recommendation(
                KIND_NOT_SUPPORTED,
                "No gender-specific NBR observation exists for this indicator"
                + (f": {first.body[:1].lower() + first.body[1:]}" if first else "."),
            ))
    return items


def national_recommendations(
    *,
    indicator: str,
    below_count: int,
    district_total: int,
    lowest_district: str,
    state: ContextState,
    nbr_label: str = "",
    reported_districts: int = 0,
    reporting_date: str = "",
    polarity: str = "positive",
) -> list[Recommendation]:
    items: list[Recommendation] = []
    if polarity != "neutral" and district_total:
        items.append(Recommendation(
            KIND_INVESTIGATE,
            f"{below_count} of {district_total} district estimates for {indicator} lie "
            f"{'below' if polarity == 'positive' else 'above'} the national reference. "
            f"Open the District explorer to inspect {lowest_district} and the other "
            "lowest estimates; the map describes gaps, not their causes.",
        ))
    if state.state == STATE_AVAILABLE:
        items.append(Recommendation(
            KIND_VERIFY,
            f"NBR {nbr_label} is reported for {reported_districts} of {district_total} "
            f"districts on {reporting_date}. Districts without markers are unknown, not zero."
            if reported_districts < district_total else
            f"NBR {nbr_label} is reported for all {district_total} districts on "
            f"{reporting_date}.",
        ))
        items.append(Recommendation(
            KIND_NOT_SUPPORTED,
            "The markers show recorded administrative counts, not coverage rates. They "
            "cannot be used to say whether survey gaps are explained by supply.",
        ))
    else:
        items.extend(_nbr_coverage_recommendations(
            state, label=nbr_label or "an NBR series", geography=None, date_count=0,
        ))
    return items


# ---------------------------------------------------------------------------
# HTML (pure string builders)
# ---------------------------------------------------------------------------
def _esc(value: Any) -> str:
    import html

    return html.escape(str(value), quote=True)


def recommendations_html(items: Sequence[Recommendation], *, title: str = "Evidence-grounded next steps") -> str:
    if not items:
        return ""
    ordered = sorted(items, key=lambda item: KIND_ORDER.index(item.kind))
    rows = "".join(
        f'<div class="cmb-rec {_esc(item.kind)}"><span class="cmb-rec-k">'
        f"{_esc(KIND_LABELS[item.kind])}</span><span class=\"cmb-rec-t\">"
        f"{_esc(item.text)}</span></div>"
        for item in ordered
    )
    return (
        f'<div class="cmb-recs"><div class="cmb-recs-h">{_esc(title)}</div>{rows}</div>'
    )


def context_state_html(state: ContextState, *, label: str = "") -> str:
    heading = f"{label}: {state.title}" if label else state.title
    return (
        '<div class="nbr-empty cmb-state"><b>'
        f"{_esc(heading)}</b><span>{_esc(state.body)}</span></div>"
        if state.body else ""
    )


def source_row_html(source: str, text: str) -> str:
    tag = {"fs": "FinScope", "nbr": "NBR"}.get(source, source)
    return (
        f'<div class="cmb-src"><span class="src-tag {_esc(source)}">{_esc(tag)}</span>'
        f"<span>{_esc(text)}</span></div>"
    )


COMBINED_CSS = """
.cmb-recs{margin:12px 0 4px;padding:12px 14px;border:1px solid #DCE5E8;border-radius:10px;background:#F7FAFB}
.cmb-recs-h{font-size:11.5px;font-weight:700;letter-spacing:.04em;text-transform:uppercase;color:#4F6570;margin-bottom:8px}
.cmb-rec{display:grid;grid-template-columns:118px 1fr;gap:10px;align-items:start;padding:7px 0;border-top:1px solid #E6EDEF;font-size:13px;line-height:1.5;color:#2B4450}
.cmb-rec:first-of-type{border-top:0}
.cmb-rec-k{font-size:10.5px;font-weight:700;padding:3px 7px;border-radius:5px;text-align:center;white-space:nowrap}
.cmb-rec.supported .cmb-rec-k{background:#E3F2EF;color:#17746A}
.cmb-rec.investigate .cmb-rec-k{background:#E3EEF8;color:#245A99}
.cmb-rec.verify .cmb-rec-k{background:#FFF1CC;color:#6B4E00}
.cmb-rec.monitor .cmb-rec-k{background:#EEF1F4;color:#44586A}
.cmb-rec.not_supported .cmb-rec-k{background:#F6E9E4;color:#8A4A33}
.cmb-state{margin-top:10px}
.cmb-src{display:flex;gap:8px;align-items:center;font-size:12px;color:#5B7480;margin:4px 0}
.cmb-three{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin:2px 0 12px}
.cmb-three>div{padding:10px 12px;border:1px solid #DCE5E8;border-radius:10px;background:#fff;font-size:12px;color:#5B7480}
.cmb-three b{display:block;font-size:15px;color:#163D4B;margin:2px 0}
@media (max-width:760px){.cmb-rec{grid-template-columns:1fr}.cmb-three{grid-template-columns:1fr}}
"""


def inject_combined_styles() -> None:
    """Add the few Combined-only classes; safe to call on every render."""
    from src.styles import render_html

    render_html("<style>" + " ".join(COMBINED_CSS.split()) + "</style>")


def render_recommendations(items: Sequence[Recommendation], *, title: str = "Evidence-grounded next steps") -> None:
    from src.styles import render_html

    html_block = recommendations_html(items, title=title)
    if html_block:
        render_html(html_block)


# ---------------------------------------------------------------------------
# Loading (thin wrapper over the existing cached data-access function)
# ---------------------------------------------------------------------------
def load_context(
    variable: str,
    *,
    level: str,
    geography: str | None = None,
    subgroup_type: str = "",
    subgroup: str = "",
    loader: Callable[..., tuple[list[dict[str, Any]], str | None]] | None = None,
    mapping_lookup: Mapping[str, Mapping[str, Any]] | None = None,
    page_filters: Any = _UNSET,
) -> tuple[list[dict[str, Any]], str | None, ContextState]:
    """Entries limited to the requested scope, plus an explicit evidence state.

    District lookups fetch the whole district series once (one cached query for
    every district) and restrict to ``geography`` here, so a district with no
    observation is distinguishable from an indicator with no series at all.
    """
    if loader is None or mapping_lookup is None:
        from pymongo.errors import PyMongoError

        from src.models.nbr_intelligence.indicator_mapping import MAPPING_BY_VARIABLE
        from src.pages.nbr_dashboard import load_combined_context_data

        loader = loader or load_combined_context_data
        mapping_lookup = mapping_lookup or MAPPING_BY_VARIABLE
        recoverable: tuple[type[BaseException], ...] = (
            RuntimeError, ValueError, OSError, PyMongoError,
        )
    else:
        recoverable = (RuntimeError, ValueError, OSError)

    mapping = mapping_lookup.get(variable)
    configuration = classify_mapping(mapping, level)
    if configuration is not None:
        return [], None, configuration
    if subgroup_type == "Gender" and subgroup:
        filters = load_nbr_page_filters() if page_filters is _UNSET else page_filters
        scope_limit = classify_subgroup_scope(mapping, level, subgroup_type, filters)
        if scope_limit is not None:
            return [], None, scope_limit
    try:
        entries, version = loader(
            variable,
            geography_level=level,
            subgroup_type=subgroup_type,
            subgroup=subgroup,
        )
    except recoverable as error:
        return [], None, classify_context(mapping, level, [], error=error)
    entries = [entry for entry in entries or [] if entry.get("points")]
    if level == "district" and geography:
        entries = entries_for_geography(entries, geography)
    scope = f"Gender: {subgroup}" if subgroup_type == "Gender" and subgroup else ""
    return entries, version, classify_context(
        mapping, level, entries, geography=geography, scope_label=scope,
    )


def mapping_summary(
    variables: Iterable[str],
    level: str,
    *,
    mapping_lookup: Mapping[str, Mapping[str, Any]],
    labels: Mapping[str, str] | None = None,
) -> tuple[list[str], list[str]]:
    """(mapped, unmapped) display names for ``variables`` at ``level``, from config only."""
    mapped: list[str] = []
    unmapped: list[str] = []
    for variable in variables:
        mapping = mapping_lookup.get(variable)
        name = (labels or {}).get(variable) or (
            mapping.get("original_indicator_label") if mapping else None
        ) or variable
        (unmapped if classify_mapping(mapping, level) is not None else mapped).append(str(name))
    return mapped, unmapped


RELATIONSHIP_LABELS = {
    "contextual_indicator": "Contextual indicator (shown)",
    "contextual_suppressed": "Contextual, intentionally suppressed (not shown)",
    "proxy_with_unresolved_definition": "Proxy, definition unresolved (not shown)",
    "unsuitable": "Unsuitable (not shown)",
}


def mapping_rows(
    mapping_lookup: Mapping[str, Mapping[str, Any]],
    registry: Iterable[Mapping[str, Any]],
) -> list[dict[str, str]]:
    """Plain-language rows describing every configured FinScope-to-NBR relationship.

    One row per relationship; an indicator with none gets a single row that
    states why. Nothing is inferred beyond the configuration.
    """
    rows: list[dict[str, str]] = []
    for item in registry:
        variable = item["variable"]
        mapping = mapping_lookup.get(variable) or {}
        relationships = list(mapping.get("nbr_relationships") or [])
        base = {"FinScope indicator": str(item.get("label", variable)), "FinScope variable": variable}
        if not relationships:
            rows.append({
                **base,
                "NBR relationship": "None configured",
                "Where shown": "-",
                "NBR page": "-",
                "NBR metrics": "-",
                "Filter scope": "-",
                "Limitations / reason": str(
                    mapping.get("nbr_no_relevant_data_reason")
                    or "No approved NBR series is relevant to this indicator."
                ),
            })
            continue
        for rel in relationships:
            metrics = []
            if rel.get("national_kpi_labels"):
                metrics.append("National: " + ", ".join(rel["national_kpi_labels"]))
            if rel.get("district_table_labels"):
                metrics.append("District: " + ", ".join(rel["district_table_labels"]))
            suppressed = bool(rel.get("suppressed"))
            shown = rel.get("relationship") == "contextual_indicator" and not suppressed
            code = "contextual_suppressed" if suppressed else str(rel.get("relationship"))
            rows.append({
                **base,
                "NBR relationship": RELATIONSHIP_LABELS.get(code, code),
                "Where shown": (
                    " and ".join(
                        LEVEL_LABELS.get(lv, lv) for lv in rel.get("available_levels", [])
                    ) or "-"
                ) if shown else "Not shown",
                "NBR page": str(rel.get("page", "")),
                "NBR metrics": "; ".join(metrics) or "-",
                "Filter scope": ", ".join(
                    f"{k}: {v}" for k, v in sorted((rel.get("filter_scope") or {}).items())
                ) or "None",
                "Limitations / reason": " ".join(filter(None, (
                    str(rel.get("suppression_reason") or ""),
                    str(rel.get("limitations") or ""),
                ))),
            })
    return rows


def contextual_variables(mapping_lookup: Mapping[str, Mapping[str, Any]]) -> list[str]:
    """Variables that have at least one approved contextual relationship."""
    return [
        variable for variable, mapping in mapping_lookup.items()
        if any(
            rel.get("relationship") == "contextual_indicator" and not rel.get("suppressed")
            for rel in mapping.get("nbr_relationships") or []
        )
    ]


def state_summary_html(items: Iterable[tuple[str, ContextState]]) -> str:
    """One quiet line per distinct non-available state, naming the indicators it covers.

    Used where several indicators share a block, so a failed query, a suppressed series
    and a genuine absence are never collapsed into one "no counterpart" sentence.
    """
    groups: dict[tuple[str, str], list[str]] = {}
    for name, state in items:
        if state.available or not state.body:
            continue
        groups.setdefault((state.state, state.body), []).append(name)
    rows = "".join(
        f'<div class="micro"><b>{_esc(STATE_TITLES.get(key, key))}</b> · '
        f"{_esc(', '.join(names))}: {_esc(body)}</div>"
        for (key, body), names in groups.items()
    )
    return rows


#: How every FinScope-to-NBR relationship is classified, and which evidence state(s)
#: the interface uses for it. Read by the Methodology page and by tests.
EVIDENCE_CLASSES = (
    ("Relevant administrative context", (STATE_AVAILABLE,),
     "An approved, thematically relevant NBR series has observations for the selected "
     "geography, filters and date. It is shown beside the survey estimate, never combined with it."),
    ("Related, not equivalent", (STATE_AVAILABLE,),
     "Every shown series is related but not equivalent: a branch count is not account "
     "ownership. Its limitation is shown with it, and its unit and filters are never changed."),
    ("Uncertain or unapproved relationship", (STATE_NOT_APPROVED,),
     "Only proxies with unresolved definitions exist. They are not displayed as evidence."),
    ("Unsupported dimension or level", (STATE_SCOPE_UNSUPPORTED, STATE_LEVEL_UNSUPPORTED),
     "NBR does not cover the dimension (education, urban/rural, age bands, or a page with no "
     "Gender breakdown) or the geographic level."),
    ("No relevant NBR metric", (STATE_NO_COUNTERPART,),
     "No NBR data currently available to this project is relevant to the indicator."),
    ("Supported, no matching observation", (STATE_NO_OBSERVATION,),
     "A series is approved but nothing is recorded for this geography, group or filter. "
     "Missing is not zero."),
    ("Intentionally suppressed", (STATE_SUPPRESSED,),
     "A related series is configured but deliberately not shown because it is not an approved "
     "proxy. This is a display decision, not a missing observation."),
    ("Data-loading failure", (STATE_LOAD_ERROR,),
     "The NBR source could not be read. This is not evidence that a service or observation "
     "does not exist; FinScope values are unaffected."),
)


def header_pill(mode: str, finscope_label: str, *, mode_labels: Mapping[str, str] | None = None) -> str:
    """Pill text for page headers; Combined names both sources."""
    if mode == "Combined":
        labels = mode_labels or {"Combined": "FinScope survey + NBR supply"}
        return labels.get("Combined", "FinScope survey + NBR supply")
    return finscope_label