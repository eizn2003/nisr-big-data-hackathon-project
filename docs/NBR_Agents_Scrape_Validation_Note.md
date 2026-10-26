# NBR Agents Dashboard — Scrape and Validation Note

**Project:** Rwanda Financial Inclusion Gap Explorer  
**Source:** National Bank of Rwanda (NBR), Financial Inclusion Dashboard  
**Page:** https://fininclusion.bnr.rw/touchpoints/agents  
**Verification snapshot:** 2026-10-24  
**Status:** Dashboard inspected; aggregation discrepancy documented; final baseline scraper prepared.

## What was inspected

The Agents page provides a national KPI and a paginated district table, with filters for gender, institution type, agent status, and location. The observed table had six rows per page and 30 districts total. The “Table” view control is `#touchpoints-agents-table-card`; table rows are in `table.cell-table`. A recurring “Important Notes” modal can block interaction; test automation hid it with CSS.

## Verified snapshot: Active agents, 2026-10-24

| Institution filter | National KPI | Sum of district rows | KPI minus district sum |
|---|---:|---:|---:|
| All | 159,286 | 167,615 | -8,329 |
| Banks | 4,872 | 5,878 | -1,006 |
| E-money Issuers | 155,211 | 161,799 | -6,588 |
| Microfinance | 216 | 218 | -2 |
| Sacco | 5 | 5 | 0 |

The four institution-specific national KPIs sum to **160,304**, which is **1,018 higher** than the “All” KPI of **159,286**.

### District values observed for All / Active

| District | Agents |
|---|---:|
| Nyarugenge | 95,124 |
| Gasabo | 18,204 |
| Kicukiro | 5,742 |
| Nyamagabe | 3,712 |
| Nyanza | 3,553 |
| Rubavu | 3,298 |
| Musanze | 2,765 |
| Nyagatare | 2,619 |
| Gisagara | 2,326 |
| Kamonyi | 2,213 |
| Rwamagana | 2,149 |
| Nyaruguru | 2,010 |
| Rusizi | 1,940 |
| Muhanga | 1,871 |
| Huye | 1,841 |
| Kayonza | 1,661 |
| Ruhango | 1,649 |
| Rutsiro | 1,635 |
| Nyabihu | 1,585 |
| Bugesera | 1,550 |
| Gatsibo | 1,484 |
| Karongi | 1,334 |
| Gicumbi | 1,109 |
| Gakenke | 1,095 |
| Ngoma | 1,051 |
| Kirehe | 1,050 |
| Nyamasheke | 874 |
| Rulindo | 783 |
| Burera | 714 |
| Ngororero | 674 |
| **Total** | **167,615** |

## Interpretation and limitations

- This is an observed aggregation discrepancy; its cause has **not** been established.
- Do not scale district values, replace the national KPI with the district sum, or force totals to match.
- Preserve the KPI and district table as separate observations and retain their difference as a validation field.
- Agent counts alone do not prove that financial inclusion improved, that agents are active/accessible in practice, or that an intervention caused change.
- A single snapshot is not a trend. Progress monitoring needs comparable dates, consistent filters/definitions, and multiple observations.
- Keep missing values missing; never silently convert `N/A` to zero.
- The prior attempt to restore the institution filter to “All” after selecting “Sacco” failed: KPI remained `5`. Do not treat that restoration as successful. Institution-specific figures above were captured under each selected institution; the failed restoration is an automation limitation.

## Final baseline run

From the project root with the `financial-inclusion` environment active:

```bash
pip install playwright pandas
playwright install chromium
python tests/scrapers/scrape_nbr_agents.py --date 2026-10-24
```

To watch the browser, add `--headed`:

```bash
python tests/scrapers/scrape_nbr_agents.py --date 2026-10-24 --headed
```

The script explicitly sets and verifies the date, records visible filter labels, captures the KPI, paginates the district table, and saves timestamped district CSV and audit JSON files under `data/raw/nbr/`. It returns exit status `2` when validation warnings are present. That means the scrape was saved but needs review; it does not mean the scrape returned no data.

**Important:** The script intentionally uses the dashboard's current/default filters instead of automating the cascading institution dropdown, because the earlier restoration attempt selected the wrong “All” option. Check the recorded filter labels in the audit JSON before interpreting a run. The expected baseline from prior inspection was All gender, All institution types, Active agents, All location.

## Current conclusion

This source is a candidate monitoring signal for agent distribution, but it is **not yet validated as a clean additive measure** across districts or institution categories. Keep source/date/filter provenance and the reconciliation warning. Do not use it alone to claim financial-inclusion progress or to rank districts without additional validation.
