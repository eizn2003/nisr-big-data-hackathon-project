# NBR dashboard modes

The shared mode selector in the sidebar applies to National Overview, District
Explorer, Population Groups, and Priority Explorer:

- **FinScope** (default) preserves the survey-based pages and estimates.
- **Combined** adds a separate NBR context panel only where an approved
  indicator relationship and an observation at the selected scope exist.
- **NBR Supply** displays observed NBR administrative values, units, filters,
  dates, provenance, and historical trends without reusing FinScope scores.

NBR series choices are built from successfully normalized source observations.
Page, metric, unit, geographic level, and the full observed filter combination
are kept as series identity. District maps show the selected metric at one
reporting date; marker size is not an inclusion score. Population-group NBR
comparisons are limited to observed Gender and NBR Youth/Non-Youth filter
categories. NBR age categories are not crosswalked to FinScope age bands, and
Education and urban/rural NBR comparisons are not presented without supporting
observations.

NBR data access reuses the existing read-only MongoDB history loader with a
page predicate applied to the runs, KPI, and district-table collections. Only
the selected NBR page is normalized for the active view. Combined mode offers
configured source pages for each FinScope indicator. On the Combined National
Overview it loads the union of approved national-mapping pages once, then runs
the existing contextualization and evidence-selection functions over eligible
national KPI observations and processed FinScope baselines. At most four
directional findings with sufficient or limited evidence are shown; the
headline bank-account and active-bank-branch series are excluded from that
section. Other Combined pages continue to load only their selected indicator's
configured pages. The source documents and normalized view are cached for at
most 15 minutes. A sidebar refresh action clears the source, normalized-view,
and review-result caches. The deterministic digest of the normalized page
snapshot versions selection state and cached review results.

The National Overview shows each FinScope indicator at most once, even if its
approved mappings match multiple NBR series. When different survey indicators
map to the same NBR series, evidence sufficiency, quality qualifications,
recency, and relationship type guide selection; an explicit institution-name
match breaks remaining ties. NBR units and their status are shown from
normalized source metadata. If the source does not specify a unit, the chart
labels that explicitly rather than assuming the value is a count.

The Priority Explorer's experimental candidate panel runs only when requested
and limits the existing anomaly detectors to the selected source page. Its
method-specific rankings remain separate and require source verification and
human review. It does not create a FinScope priority score or recommend policy
action. The large generated contextualization reports are not loaded or parsed
by the dashboard; the National Overview builds a page-scoped assessment in
memory from the cached normalized data and does not read serialized reports.

In the measured environment, an unfiltered cold read of 1,873 run records,
1,719 KPI documents, and 50,418 table documents took 199.1 seconds to fetch
and 210.6 seconds through normalization, registry construction, and hashing.
A cold `branches` page read took 3.26 seconds to fetch and 3.36 seconds end to
end (25 runs, 25 KPIs, 764 table records, and 619 eligible observations).
That is an observed page-specific reduction of about 98% in source-fetch time
for this page. Cached interactions should not repeat the read before the
15-minute TTL; this is a measured cold-run comparison, not a latency guarantee
for every NBR page or network condition.

All NBR observations and candidate findings are experimental administrative
evidence. They do not establish population ownership, service access,
substitution, causality, or a change in financial inclusion. Missing
observations are not treated as zero, and unavailable comparisons are not
negative findings.

Run the app with:

```bash
streamlit run app.py
```

Focused dashboard checks:

```bash
.venv/bin/python -m pytest -q tests/test_nbr_dashboard.py
```
