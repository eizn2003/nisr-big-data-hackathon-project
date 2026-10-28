# NBR adaptive-intelligence experiment

## Learning objective

The experiment evaluates two separate questions using NBR administrative records only:

1. Is a district value unusual relative to peers in the **same page, exact metric label, reporting date, and canonical filter combination**?
2. Is an observation an unusual change relative to the history of the **same page, exact metric label, district, and canonical filter combination**?

Reporting periods come from `snapshot_date`; `collected_at` is retained as provenance and is never substituted for the reporting period.

The candidate estimates a per-day change in `log(1 + value)`, then compares the next observation with the median and median absolute deviation (MAD) of earlier rates. This can account for unequal elapsed days. The experiment compares it with two baselines: (1) a statistical historical-level median/MAD detector on the same prior observations, and (2) the existing 50%-within-eight-days review rule. It is an experimental statistical detector, not a supervised or production model.

## Preparation and evaluation protocol

The pipeline in [`experiment.py`](../src/models/nbr_intelligence/experiment.py) reads the existing NBR run, KPI, and district-table collections without writes. The legacy [`nbr_anomaly_experiment.py`](../src/data_sources/nbr_anomaly_experiment.py) entry point remains a compatibility wrapper. The pipeline:

- requires one matching `complete` collection run;
- verifies run IDs, canonical filter keys, and stored filter provenance before joining observations;
- excludes scraper-flagged repeated snapshots;
- excludes unknown or unverified districts, invalid reporting dates, missing collection timestamps, and nonnumeric, nonfinite, or negative values;
- preserves actual filters, `combo_key`, page, metric label, district, reporting date, collection timestamp, and run ID;
- keeps zero as a numeric observation and never turns a missing district into zero;
- qualifies evaluation cases when the existing KPI/table reconciliation check is tentative; it does not treat the discrepancy as a ground-truth error.

Evaluation is chronological and walk-forward. A candidate score requires three historical change rates (four prior observations); the target and future values are not used in fitting. The robust-score cutoff of 3.0 is fixed for this experiment and is not tuned on the test period. The reported `model_robust_score` is a **nonnegative deviation magnitude**: it is the absolute residual from the historical median daily rate divided by `1.4826 * MAD`. `model_signed_robust_score` preserves the residual sign; `deviation_direction` states whether the observed rate is above or below its historical median, and `observed_change_direction` separately states whether the observed value itself increased or decreased.

An exact-zero MAD remains an explicit abstention. A nonzero MAD is treated as unassessable when it is no larger than twice the largest floating-point resolution bound propagated from prior `log1p(value)`-per-day calculations. The detector also abstains if any prior rate itself reaches the existing 3.0 robust-score cutoff against that fitted history: that indicates an internally discordant training baseline whose MAD may be dominated by a cluster of rates while ignoring a materially different prior period. This reuses the established threshold rather than adding a new scale constant. These safeguards are distinct: one checks numerical resolution, the other checks historical consistency. The companion data-health mapping identifies `Customers` as a count unit, but the source does not provide a measurement-accuracy or repeatability bound; a count unit alone does not justify a practical scale floor. When historical rates are consistent and MAD is numerically resolvable, small MADs can still yield large scores, which remain limited-evidence review signals. No future target values are used to estimate dispersion or test historical consistency.

Each rerun refits from eligible historical NBR observations; it does not persist model state, modify source data, retrain from analyst decisions, or change its own threshold.

The statistical level baseline uses the median and MAD of the prior four or more raw values in that same series, with the same 3.0 robust-score cutoff and zero-MAD abstention. The rate candidate and level baseline are compared only where both could be scored. The existing percentage-change rule is retained as a separate comparator. Rate alerts are counted by both signed deviation direction and observed change direction; alert status continues to use the absolute magnitude.

## Results on the available history

The read-only run on **2026-10-28** processed 1,873 run records and 50,418 district-table documents covering 13 pages and five reporting dates: 2025-02-20, 2025-11-20, 2026-08-20, 2026-10-24, and 2026-10-27. The intervals are irregular (including a three-day latest interval), not a weekly training series.

After quality exclusions, the experiment retained 48,988 metric observations across 10,131 comparable series:

| Independent dates in series | Series |
|---:|---:|
| 1 | 328 |
| 2 | 40 |
| 3 | 18 |
| 4 | 199 |
| 5 | 9,546 |

It excluded 453 table rows from repeated snapshots and 977 rows from unknown or unverified geography. The full report retains the reasons and source provenance. The 20 tentative reconciliation scopes are attached to applicable Agent evaluation cases; they remain qualifications, not proof of bad data.

The walk-forward comparison produced:

| Measure | Result |
|---|---:|
| Test cases | 9,546 |
| Model-assessable cases | 9,462 |
| Explicit zero-MAD abstentions | 84 |
| Level-baseline-assessable cases | 9,458 |
| Level-baseline zero-MAD abstentions | 88 |
| Cases where both statistical methods were assessable | 9,442 |
| Historical-level baseline flags | 588 |
| Rate-model flags | 8,570 (90.57% of assessable cases) |
| Both statistical methods flagged | 574 |
| Rate-model-only flags among comparable cases | 7,986 |
| Level-baseline-only flags among comparable cases | 14 |
| Existing 50%/8-day rule alerts in test cases | 37 |
| Rate-model and existing-rule alerts shared | 31 |
| Existing-rule alerts among model abstentions | 6 |
| Rate-model-only flags versus existing rule among assessable cases | 8,539 |
| Adjudicated anomaly labels | None |
| Measurable precision, recall, or false-alarm rate | Not available |

The health report has 40 50%-change events overall. Three do not meet the experiment's minimum of four clean prior observations, so the comparable 50%/8-day baseline has 37 test-case alerts. The 84 model abstentions are not counted as either model alerts or confirmed normal observations.

The high model-flag rate is a warning, not a success claim. For example, the rate candidate flags the Bugesera `Agents` / `Institution Type=All` observation changing from 1,550 on 2026-10-24 to 1,552 on 2026-10-27 (score 8.13 against 3.0). The level baseline score is only 0.64 and the existing rule does not flag it. The same scope has tentative KPI/table discrepancies in the historical record. Small observed changes, only three training rates, unequal intervals, and source reconciliation limitations make such candidate scores unsuitable for operational conclusions. No ground-truth labels exist to determine whether these are true anomalies or false alarms.

## Temporal scoring audit (2026-10-28)

The original `model_robust_score` was intentionally an absolute standardized residual, so nonnegative scores were by design. The defect was that the report and review queue omitted its sign and did not separately identify the direction of the observed rate. Version `nbr-intelligence-0.3.0` retains the magnitude for thresholds and ranking and adds `model_signed_robust_score`, `deviation_direction`, and `observed_change_direction`.

The original extreme was Inclusion / Customers / Nyabihu, reporting date 2026-10-27, with `Institution Type=Insurance`, `Account/Policy Status=Active`, and all other filters set to `All`. Its prior values were 3,239 (2025-02-20), 3,381 (2025-11-20), 3,214 (2026-08-20), and 3,247 (2026-10-24), followed by 3,185 on 2026-10-27. The prior daily rates were approximately `0.0001571206`, `-0.0001854941`, and `0.0001571087`. The middle rate is about 19,435 robust deviations from the median under the same MAD, while the other two rates are nearly identical. With only three historical rates, the MAD (`1.1902237328072175e-08`) therefore represents a nearly tied pair and masks a discordant prior period. The floating-point resolution bound (`1.0942185325559283e-16`) is not the reason for abstention. The former 372,969.31 magnitude is not emitted as an alert in the revised assessment: the system now marks this case `not_assessable_discordant_training_rates`. This identifies an unstable historical baseline, not a source-data error or a confirmed service change.

The detector distinguishes exact-zero MAD, nonzero MAD below calculation resolution, and nonzero MAD from internally discordant historical rates. On this dataset, 3,367 cases abstain for historical discordance and none for floating-point resolution. This guard allows a small MAD when the fitted historical rates are consistent, but refuses to treat a small MAD created by an internally discordant history as reliable. It does not validate source measurement accuracy, and it does not make the remaining scores accurate or predictive.

The existing report and review CSV were not overwritten. The rerun used the same 1,873 runs, 50,418 table documents, 48,988 eligible observations, and 9,546 walk-forward cases:

| Temporal measure | Before (`nbr-intelligence-0.2.0`) | After (`nbr-intelligence-0.3.0`) |
|---|---:|---:|
| Assessable cases | 9,462 | 6,095 |
| Exact-zero MAD abstentions | 84 | 84 |
| Floating-point-resolution abstentions | Not measured | 0 |
| Discordant-training-rate abstentions | Not measured | 3,367 |
| Total abstentions | 84 | 3,451 |
| Alerts | 8,570 (90.57%) | 5,376 (88.20%) |
| Score median | 23.2991 | 15.7198 |
| Score p90 / p95 / p99 | 185.8342 / 388.7270 / 1,837.4255 | 61.9541 / 102.4463 / 294.3197 |
| Maximum score | 372,969.3083 | 1,437.3229 |
| Alert residual above / below historical median | 2,586 / 5,984 | 1,584 / 3,792 |
| Alert observed rate increase / decrease / unchanged | 2,574 / 5,967 / 29 | 1,585 / 3,789 / 2 |
| Temporal review-queue candidates | 8,570 | 5,376 |

The source history and eligible observation population are unchanged: 1,873 runs, 50,418 table documents, 48,988 eligible observations, and 9,546 walk-forward cases. The reduced maximum is due to abstaining on unstable fitted histories, not suppressing scores with a cap. A remaining extreme is Internet Banking / Customers / Ngoma (`Gender=Female`, `Institution Type=Banks`, other filters `All`) at 1,437.32; its observed rate rose and exceeded the historical median. The method still alerts on 88.20% of assessable cases, so the change does not establish improved accuracy or sufficient operational reliability. Reviewers should treat signed scores and directions as context and verify source records, filters, metric meaning, and collection provenance before any disposition.

## Cross-sectional peer comparison

The additional experimental detector calculates a modified robust z-score within each exact page/metric/date/filter scope:

`0.67449 * (district value - peer median) / peer MAD`

It requires at least 10 eligible district observations, uses a fixed absolute-score review threshold of 3.5, and abstains when peer MAD is zero. It reports counts at thresholds 3.0, 3.5, and 4.0; the threshold was not tuned against the observed candidates. Unknown and unverified locations are excluded, never imputed. Candidate evidence retains the actual source filters, run ID, reporting date, collection timestamp, peer median/MAD, comparison size, geography qualifications, and sensitivity to a +/-1% change in the target value.

On the same read-only history:

| Measure | Result |
|---|---:|
| Assessable peer groups | 1,642 |
| Observations in assessable peer groups | 48,930 |
| Peer groups below the 10-district minimum | 17 |
| Peer groups with zero MAD | 0 |
| Groups with a geographic coverage qualification | 1,032 |
| Candidate observations at threshold 3.0 | 4,997 |
| Candidate observations at threshold 3.5 | 4,510 (9.22% of assessable observations) |
| Candidate observations at threshold 4.0 | 4,207 |
| Assessable observations whose flag changed under +/-1% perturbation | 72 |
| Flagged candidates whose flag changed under +/-1% perturbation | 39 |

The 4,510 candidate records span 24 districts, 100 page/district pairs, and 1,054 distinct page/metric/district/filter series. Of these candidate records, 2,633 carry one or more data-quality qualifications. Counts are observation-level candidate counts, not counts of unique data problems or affected districts. The largest page counts are mobile banking (662), inclusion (619), transactional (534), credit (523), and internet banking (515). The ranked queue shows 100 of 4,510 cross-sectional candidates; rankings are method-specific and scores are not combined across methods.

The highest-scoring candidate is Credit / Customers / Gasabo for 2025-11-20 with filters `Gender=Female`, `Age Segment=Youth`, `Institution Type=Banks`, `Account Status=Active`, `Credit Category=All`, and `Location=All`. The stored value is 88,064; the 30-district peer median is 105 and MAD is 56.5. I verified the exact scope against the source records: it has one matching complete run and 30 known-location district rows. Other values in that same run range from 37 to 4,199. This is a strong review candidate, but it does not by itself establish whether the stored value is erroneous, reflects a legitimate scale difference, or reflects a source-definition issue. It should be checked against the originating NBR table before interpretation.

## Bounded source-record review

On 2026-10-28, a limited sample was checked read-only against `page_table_observations`, `page_scrape_runs`, and matching KPI observations. Checks included exact page/date/canonical filters, metric label, the candidate district value, collection status/time, repeated-snapshot flag, known/unknown geography, district sums where comparable, and the matching national KPI. The stored source rows identify values as counts or percentages through labels/formatting, but the inspected configuration does not define the underlying unit or population semantics; no unit has been inferred. No live-dashboard or upstream source-code verification was performed.

| Candidate | Verified stored-record evidence | Review classification |
|---|---|---|
| Credit / Customers / Gasabo, 2025-11-20; Female, Youth, Banks | The complete non-repeated run `35e5fdf63098` contains 30 known districts. Gasabo is 88,064; the district values sum to 97,619, matching the same-filter `Total Customers` KPI of 97,619. No unknown row or data-health qualification is present. | **Plausible genuine cross-sectional difference; upstream meaning still unverified.** Internal total agreement argues against a simple table-total mismatch, but does not establish that the unusual concentration or source definition is correct. |
| Savings / Customers / Gasabo, 2026-10-27; All genders, Youth, Banks | Complete, non-repeated run `ab7f5ea52d81`; 30 known districts plus an `unknown` row with value 2. Known-location peer median is 4,909.5; Gasabo is 556,001. All rows, including the unknown row, sum to 1,065,762, matching the same-filter `Total Customers` KPI. | **Plausible genuine cross-sectional difference; geography qualification remains.** The unknown row is excluded from peers and has not been assigned to a district. |
| Agents / Agents / Nyarugenge, 2026-10-27; E-money Issuers | Complete, non-repeated run `ab7f5ea52d81`; 30 known district rows. Nyarugenge is 93,954. District rows sum to 161,798, while the same-filter `Total Agents` KPI is 155,211, a measured difference of 6,587. | **Unresolved; discrepancy confirmed, cause not established.** This does not prove which stored value is wrong or whether source definitions differ. |
| Branches / Branches / Rusizi, 2025-11-20; Sacco | Complete, non-repeated run `35e5fdf63098`; 30 known districts and one `unknown` row valued 3. Rusizi is 154. All 31 rows sum to 760, matching the `Total Branches` KPI of 760; the 30 known-district rows sum to 757. | **Plausible genuine cross-sectional difference; geography qualification remains.** The `unknown` value was excluded from named peers; the aggregate reconciles only when that row is included. |
| Insurance / Policy Holders / Nyarugenge, 2026-10-27; Male, Youth | Complete, non-repeated run `ab7f5ea52d81`; 30 known districts and one `unknown` row valued 164. Nyarugenge is 48,603. All rows sum to 99,896, matching `Total Policy Holders` of 99,896. | **Plausible genuine cross-sectional difference; geography qualification remains.** The underlying insurance type/metric semantics are not documented in the inspected configuration. |
| Inclusion / Customers / Nyabihu, 2026-10-27; All genders/ages, Insurance (temporal-only candidate) | Complete, non-repeated run `ab7f5ea52d81`; 30 known districts plus an `unknown` row. Nyabihu changed from 3,247 on 2026-10-24 to 3,185 on 2026-10-27 (-62, about -1.9%). The 2026-10-27 table sums to 760,544, matching the same-filter `Total Customers` KPI. The value 3,185 is within that date's observed district range of 2,714–269,664. | **Unresolved; evidence does not support a large operational change.** The temporal score is extreme because it is normalized against a very small historical rate MAD; it is not evidence that the underlying 1.9% change is anomalous. |

These are checks of stored scraper observations and their metadata, not confirmation against the live NBR website. No sampled record establishes a confirmed source-data or collection error. The only confirmed discrepancy in this sample is the Agents table/KPI difference; its cause remains unknown. Observed consistency with an aggregate KPI is useful evidence but does not verify the correct unit, label, filter semantics, or upstream value.

### Rusizi Branches follow-up

The Rusizi candidate described in this review is the cross-sectional **Branches / Branches / Rusizi** observation for `snapshot_date=2025-11-20`, not the national `Institution Type=All` series. Its canonical combination is `{"Branch Status":"Active","Institution Type":"Sacco","Location":"All"}`; the applied filters are Institution Type **Sacco**, Branch Status **Active**, and Location **All** (as configured, Location is ignored/recorded as All). The stored table row is 154, rank 1, and is a district row—not a national or alternate aggregation. The candidate's peer median is 19.5 and MAD is 3.5 across 30 known districts. It ranks 2,460th of 4,510 peer candidates in the full report, so it is **not included** in the review CSV, which contains only the top 100 peer candidates; there is no corresponding candidate ID or review row in that CSV. The CSV was not changed.

Read-only source-document references for this candidate:

- The `page_scrape_runs` document `_id=6adf2299c0bb3bca8549d849` has run ID `35e5fdf63098`, status `complete`, `repeated_snapshot_warning=false`, and `collected_at=2026-10-26T09:51:20.497`. It has the same page, reporting date, canonical combination, and filters.
- The Rusizi table document `_id=6adf2299c0bb3bca8549d829` has `district=Rusizi`, `district_known=true`, `values.Branches="154"`, and `values.Rank="1"`; it has the same run ID, filters, `snapshot_date`, and `collected_at` as the matching run.
- The `unknown` table document `_id=6adf2299c0bb3bca8549d847` has `values.Branches="3"` and `district_known=false`.
- There are 31 numeric table rows: the 30 known districts sum to 757, and adding the unknown row's 3 gives 760. The KPI document `_id=6adf2299c0bb3bca8549d848` reports `Total Branches="760"` for the same page/date/`combo_key`.

The table rows and run directly share run ID `35e5fdf63098` and the same filter provenance. The KPI document has no `run_id`, `collected_at`, or filter-values field; its association is established by its matching page, `snapshot_date`, and canonical `combo_key` (and the one corresponding run for that identity), not by a run ID stored on the KPI itself. Thus the stored Sacco table and KPI are internally consistent when the unknown row is included. The candidate is a cross-sectional high value, not evidence of a source-data error. Whether the value 154 reflects the intended source definition still requires checking the originating NBR dashboard/table for that exact reporting date and filters.

The reported live values 1,991 total branches and 77 for Rusizi are not a like-for-like comparison with this Sacco candidate. The stored records contain those exact two values under **Institution Type=All**, Branch Status Active, Location All, on `snapshot_date=2026-10-24`: the table sums to 1,991 and its Rusizi row is 77. That scope is a different reporting date and filter from the candidate. A matching repeat-content scope is stored for `snapshot_date=2026-10-27` (run `ab7f5ea52d81`, complete but `repeated_snapshot_warning=true`); it also has 1,991 and 77 and is excluded from experiment fitting. The live observation's own reporting date and selected filters were not provided or verified, so the matching stored figures do not prove which saved snapshot or filter selection produced the live dashboard view. On the candidate date itself, the stored `Institution Type=All` scope is yet another distinct comparison: Rusizi 207 and `Total Branches` 2,049, with 31 rows summing to 2,049.

The change detector and peer detector were also compared only on shared observations assessable by both methods. This is the latest temporal test observation per series, not the full cross-sectional history:

| Shared-case comparison | Common cases | Peer only | Temporal only | Both | Neither |
|---|---:|---:|---:|---:|---:|
| Cross-sectional vs. temporal rate/MAD | 9,460 | 57 | 7,757 | 812 | 834 |
| Cross-sectional vs. temporal level/MAD | 9,456 | 823 | 542 | 46 | 8,045 |
| Cross-sectional vs. existing 50%/8-day rule | 9,540 | 873 | 37 | 0 | 8,630 |

The peer detector flags 869 of the common rate/MAD cases and 869 of the common level/MAD cases; the slight count difference from the 873 cases against the existing rule is due to the different temporal scoreability requirements. These comparisons show substantial method disagreement, not that one method is more accurate. The rate/MAD candidate still flags 90.57% of its assessable cases, versus 6.22% for the level baseline; 1,966 rate-model and 462 level-baseline classifications change under a +/-1% perturbation. No adjudicated labels are available for accuracy or false-alarm estimates.

**Conclusion:** the current history is insufficient to establish that either detector adds predictive value. Cross-sectional comparison provides a traceable way to surface large within-scope differences for human review, while the temporal rate/MAD formulation over-flags. Neither output should be used to rank districts for intervention or assert a financial-service gap. The five-point, irregular history does not support reliable weekly behavior learning or a meaningful labeled evaluation.

## Adaptation and data-collection plan

These are separate operations:

1. **Descriptive baselines:** the existing data-health component recomputes median/MAD summaries of eligible metric levels.
2. **Candidate fitting:** this experiment recomputes per-series historical change-rate median/MAD on each run using earlier, quality-qualified observations only.
3. **Threshold calibration:** the 3.0 cutoff is currently fixed; no automatic recalibration is performed.
4. **Review feedback:** analyst dispositions are not currently stored or used. If introduced later, they must remain separate from model output and require human review; predictions must never become their own labels.

The current review queue is an experimental, method-specific shortlist, not an intervention queue. It returns up to 100 ranked records per method (all 37 existing-rule cases fit) and marks truncation. No dispositions are fabricated or persisted. A future review log should record a stable candidate identity, reviewer, review date, disposition, evidence checked (including the original NBR source), and rationale. Keep these records separate from observations and predictions.

The handoff artifact is [`nbr-anomaly-human-review.csv`](../data/processed/nbr-anomaly-human-review.csv). It is generated from the existing ranked queues (337 rows in the current report), not from every candidate in the full report. It preserves each original candidate as JSON and exposes page, metric, district, reporting date, collection/run provenance, filters, score/reference, reason, and qualifications in separate columns. The `review_status` field starts as `pending`; reviewer, disposition, rationale, supporting evidence, and timestamp fields are blank. The artifact contains no analyst labels. Do not regenerate to the same path after recording reviews, because generation intentionally creates a fresh unreviewed handoff.

Continue the existing scheduled NBR collection and retain distinct `snapshot_date` and `collected_at`, canonical filters, run status, repeated-content metadata, and explicit unknown/missing states. Reassess after at least 12 consecutive quality-suitable weekly periods for the same series and at least four later chronological holdout periods. This is a practical minimum for a future evaluation, not a guarantee of statistical reliability. Record independent analyst dispositions for reviewed events before attempting supervised evaluation or threshold calibration.

Current outputs must not prioritize financial-inclusion interventions or assert a district service gap. Candidate scores describe within-scope statistical differences, not need, access, quality, causation, or error. NBR administrative evidence remains separate from FinScope survey evidence; neither is used to train or validate the other here.

## Reproduction

With the project's Python dependencies installed and `MONGODB_URI` or `MONGO_URI` available through the existing `.env` configuration:

```bash
python -m src.data_sources.nbr_anomaly_experiment \
  --output /tmp/nbr-intelligence-evaluation.json \
  --review-csv data/processed/nbr-anomaly-human-review.csv
```

The report includes the data-quality exclusions, walk-forward test cases, fit history, scores, baseline comparison, and source lineage. Rerunning after the existing scraper collects new records incorporates them on the next batch refit; no separate scheduler or database is introduced.
For a fresh review after a later collection, write the CSV to a new path or first preserve the reviewed artifact so entered human dispositions are not overwritten. Reviewers should inspect the source `run_id` and exact filters, check the corresponding source table/KPI records and quality qualifications, then complete only the reviewer columns; keep dispositions separate from model output.

The 2026-10-28 temporal audit was reproduced with:

```bash
python -m src.models.nbr_intelligence \
  --output data/processed/nbr-intelligence-temporal-audit-2026-10-28.json \
  --review-csv data/processed/nbr-anomaly-human-review-temporal-audit-2026-10-28.csv
```

The audit report is a separate full JSON assessment. The accompanying CSV has 437 rows: 337 currently shown ranked candidates (100 per statistical queue and 37 existing-rule alerts), plus 100 older temporal candidates retained with `candidate_current=false` after the new baseline-stability rule stopped ranking them. All reviewer fields remain pending in this run. The merge operation preserves any reviewer fields already entered in that separate CSV.

Focused validation:

```bash
python -m pytest -q tests/test_nbr_anomaly_experiment.py
python -m pytest -q tests/test_mongodb_data_health.py \
  tests/test_mongodb_district_explorer.py \
  tests/test_mongodb_population_groups.py
python -m pytest -q tests/test_pages_smoke.py \
  -k 'population_groups or district_explorer'
python -m py_compile src/models/nbr_intelligence/*.py \
  src/data_sources/nbr_anomaly_experiment.py \
  tests/test_nbr_anomaly_experiment.py
git diff --check
```

## FinScope-aware contextualization and cross-channel assessment

Version `nbr-intelligence-0.4.0` adds a separate read-only contextualization entry
point in [`contextualization.py`](../src/models/nbr_intelligence/contextualization.py)
and a reusable FinScope/NBR relationship registry in
[`indicator_mapping.py`](../src/models/nbr_intelligence/indicator_mapping.py).
It reuses the NBR observation eligibility rules, source-unit labeling, approved
indicator mappings, data-health checks, and human-review CSV merge behavior.
It does not replace the temporal or cross-sectional anomaly detectors.

### Source audit and valid analytical comparisons

The FinScope source is `data/datasets/FinScope2024Rwanda.dta` (13,994 respondents,
2,442 variables). `pop_wt` is labeled “Individual weight_16+ years old”; the survey
population is therefore residents aged 16 and above. The processed estimates and
denominators remain the system of record; this extension does not recompute or
change the weighted indicators. Existing processed coverage includes 8 national
point estimates, 30 districts × 8 measures, and 102 population-group rows across
gender, age, education, and urban/rural categories. Original values and valid
respondent counts are preserved from the processed CSVs. Item-level response
counts and weighted-valid coverage are available in
`data/processed/indicator_denominator_validation.csv`.

The mappings reuse `APPROVED_MAPPINGS` from
[`mongodb_district_explorer.py`](../src/data_sources/mongodb_district_explorer.py)
and indicator definitions from [`indicators.py`](../src/indicators.py). Mappings
retain original FinScope variables/labels, the 2024 reference period, adult
population and `pop_wt`, expected denominator documentation, NBR page, expected
metric labels, exact canonical filter scopes, observed reporting dates/geography/
units, and mapping limitations. They deliberately distinguish contextual
infrastructure from unresolved administrative proxies:

| FinScope measure | NBR evidence currently mapped | Interpretation boundary |
|---|---|---|
| `k1` bank-account ownership | Active branches; inclusion/banking customer counts; transactional customers; depositors | Branches describe infrastructure. Customer counts are not unique people or a survey ownership rate. |
| `f5` registered mobile-money user | E-money inclusion customer/subscriber labels and e-money agents | Proxy relationship and denominator are unresolved; neither yields a mobile-money ownership percentage. |
| `h2_1` borrowing in past 12 months | Credit-page Customers | Reporting period, unit, and customer uniqueness are not established as the survey's 12-month borrowing measure. |
| `g3a_17` does not save | Savings/depositor Customers | Not the inverse of non-saving; NBR service counts do not cover every saving mechanism. |
| `g3a_11` group saving | SACCO inclusion customers and active SACCO branches | SACCO-only infrastructure/customer context does not represent all group-saving forms. |
| `qf4_06` current Umurenge SACCO use | SACCO inclusion customers and active SACCO branches | Administrative customer counts are not the respondent rate; customer uniqueness/equivalence are unresolved. |
| `e9b` emergency funds; `qf4_10` current savings-group use | No relevant NBR mapping identified | No directional cross-source suggestion is inferred. |

Source labels and metric units are retained, including whether the unit came from
the source value, a configured count label, or a source table column. Unresolved
units remain unresolved. National KPI observations and district-table rows stay
at their own aggregation levels; district rows are never summed to manufacture a
national value.

NBR history in the read-only run contained 1,873 runs and 50,418 district-table
documents. Existing eligibility rules retained 48,988 district metric points
after excluding 453 repeated-content rows and 977 unknown/unverified geography
rows. Five distinct reporting dates exist overall (2025-02-20, 2025-11-20,
2026-08-20, 2026-10-24, 2026-10-27); some pages, including branches, have only
four eligible dates. The dates are irregular. This run also prepared 3,899
eligible national KPI points. KPI/table reconciliation and data-health findings
are attached as qualifications, not treated as labels or proof of error.

District and national trends can be described where exact-scope NBR observations
exist. NBR Gender filters were collected for several pages; where exact gender
filters and metric scopes match, a national gender count may contextualize—but
does not update—the corresponding FinScope gender estimate. NBR Youth/Non-Youth
filters are not crosswalked to FinScope's six age groups. Education and
urban/rural subgroup comparisons are unsupported because NBR does not provide
those matching dimensions. Unsupported subgroup rows are explicitly reported as
not assessable rather than borrowing a district or national trend.

### Trend and channel method

The contextualization summary uses eligible observations on their actual
`snapshot_date`. Three unique dates are the minimum to describe two successive
changes. Three or four dates are `limited_evidence`; five or more dates with
consistent exact scope and no quality qualification are
`sufficient_for_directional_assessment` only. This is a task-specific coverage
classification, not statistical confidence, accuracy, or evidence of
long-term behavior. Quality qualifications, unresolved proxy relationships, or
stale collection information keep interpretations limited. Missing observations
are never interpolated or set to zero.

Cross-channel comparisons are pairwise, use at least three shared reporting
dates, and require matching geography, gender, age-segment, and institution
scope. Page-specific active-status and other filters remain in the evidence.
Branches, agents, mobile banking, internet banking, POS, merchants, cards,
transactional, and customer-reach series are kept as separate measures with
their own labels and units. Findings distinguish possible channel substitution,
complementary growth, broad contraction, and mixed trends. They do not add
counts/customers/transactions or infer causality, customer deduplication,
affordability, travel time, access, or a net service improvement.

FinScope suggestions preserve the original estimate, survey period, and valid
respondent count. They provide the NBR trend, dates, filters, source run IDs,
source record references, mapping limitations, missing/contradictory channel
evidence, evidence state, and verification step. An unresolved proxy can show
its administrative trend but cannot produce a FinScope improvement/deterioration
claim. Anomaly scores do not drive suggestion direction. No current FinScope
percentage is estimated.

### Actual assessment and handoff

The assessment was run read-only on 2026-10-28. Its outputs are separate from the
original NBR report and anomaly review files:

- JSON report:
  [`nbr-finscope-contextualization-pairwise-2026-10-28.json`](../data/processed/nbr-finscope-contextualization-pairwise-2026-10-28.json)
- Human-review CSV:
  [`nbr-finscope-contextualization-review-pairwise-2026-10-28.csv`](../data/processed/nbr-finscope-contextualization-review-pairwise-2026-10-28.csv)

The first run produced 581 contextualization records before final proxy and
pairwise-classification refinements; the pairwise report is the current run.
Review rows use separate `finscope_contextualization_<variable>` methods in the
existing review schema. The CSV merge preserves human fields by stable candidate
ID; unreviewed records remain pending. The separate first-run outputs are
preserved for comparison and were not repurposed as current model predictions.

Representative evidence in the pairwise report:

- **National:** the original 20.20% FinScope `k1` baseline is retained. The NBR
  active-bank-branches series has four dates and is increasing; the output is a
  limited-evidence infrastructure context, not a revised ownership estimate.
- **District:** Kirehe's original 5.41% `k1` baseline is retained. Its mapped
  bank-branch series is unchanged over four eligible dates, so no improvement or
  deterioration suggestion is made from that series.
- **Gender:** FinScope's female bank ownership estimate is 15.48%. The report
  can show an exact-scope NBR female administrative series when present, but
  only as a limited-evidence proxy/context; it cannot establish a changed female
  ownership rate.
- **Age, education, urban/rural:** no matching NBR category exists for the
  FinScope age bins, education levels, or area categories; suggestions abstain.

### Reproduction

With the project's Python environment and MongoDB URI available:

```bash
.venv/bin/python -m src.models.nbr_intelligence.contextualization \
  --output data/processed/nbr-finscope-contextualization-pairwise-2026-10-28.json \
  --review-csv data/processed/nbr-finscope-contextualization-review-pairwise-2026-10-28.csv
```

Use new output filenames for subsequent assessments if an immutable report
snapshot is required. The review CSV merge preserves saved dispositions. A
rerun incorporates newly eligible NBR observations; it does not refit a
supervised model, learn from its own outputs, or write anything to MongoDB.
Independent human verification remains required before supervised evaluation
or any operational interpretation.
