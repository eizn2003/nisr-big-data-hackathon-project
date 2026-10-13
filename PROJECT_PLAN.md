# Rwanda Financial Inclusion — Project Plan

## 1. Project Overview

**Proposed title:** Data-Driven Identification of Financially Underserved Communities in Rwanda for Targeted Financial Inclusion Interventions

**Objective:** Use available financial-access and socioeconomic data to identify underserved populations, examine disparities in financial inclusion, investigate factors associated with exclusion, and provide evidence to inform targeted interventions.

**Project duration:** 2 weeks

**Primary technology:** Python and Streamlit

## 2. Problem Statement

Access to financial services may differ across geographical areas and population groups. National-level financial inclusion statistics can conceal disparities in access, usage, and financial resilience.

This project will investigate these disparities using available data, distinguish direct evidence of financial exclusion from indicators of vulnerability, and identify areas that may warrant further investigation or targeted intervention.

The analysis will be constrained by the geographic detail, population coverage, quality, and availability of the selected datasets.

## 3. Research Questions

1. What does the available data reveal about financial inclusion and exclusion in Rwanda?
2. Which geographical areas or population groups demonstrate the largest measurable access gaps?
3. How do financial inclusion indicators vary by demographic and socioeconomic characteristics?
4. Which socioeconomic factors are associated with differences in financial access?
5. Where might targeted interventions be most valuable, based on transparent and defensible evidence?
6. How reliable are the findings, and what limitations should decision-makers consider?

## 4. Proposed Features

### 4.1 National Overview

Present a concise overview of financial inclusion using validated indicators.

Potential outputs:
- Financial inclusion and exclusion rates, where measurable.
- Formal versus informal financial service usage, where available.
- Key disparities and headline findings.
- Dataset coverage and analysis limitations.

### 4.2 Geographic Disparity Analysis

Compare financial inclusion indicators across geographical areas at the finest reliable level supported by the data.

Potential outputs:
- Area-level comparisons and rankings.
- Identification of areas with comparatively large access gaps.
- Geographic visualizations when suitable boundary data is available.

District-level conclusions will only be made if the dataset supports sufficiently reliable district-level estimates.

### 4.3 Demographic and Socioeconomic Analysis

Investigate differences in financial inclusion across available population characteristics.

Potential dimensions:
- Age and gender.
- Income or wealth indicators.
- Education and employment.
- Urban and rural residence.
- Other relevant characteristics supported by the data.

### 4.4 Relationship Analysis

Investigate associations between financial inclusion indicators and socioeconomic factors.

Potential methods:
- Descriptive statistics.
- Cross-tabulations and group comparisons.
- Correlation analysis where appropriate.
- Statistical tests or regression where justified by the data and study design.

Associations will not automatically be interpreted as causal relationships.

### 4.5 Evidence-Based Prioritization

Develop a transparent approach to identifying areas or population groups that may warrant further investigation or intervention.

The approach may consider:
- Magnitude of the measured financial-access gap.
- Number or proportion of people affected, where estimable.
- Relevant vulnerability indicators.
- Reliability and uncertainty of estimates.

Any composite score must have a documented rationale, defensible weighting, and sensitivity analysis. Where a defensible score cannot be constructed, findings will be presented as separate indicators rather than combined into an arbitrary ranking.

### 4.6 Interactive Dashboard

Provide a Streamlit interface for exploring the findings.

Potential capabilities:
- Filters for available geographical and demographic dimensions.
- Interactive charts and comparisons.
- Tables containing indicator values and relevant context.
- Clear explanations of indicators and methodology.
- Downloadable results where appropriate and permitted.

### 4.7 Recommendations

Translate findings into evidence-linked recommendations or areas for further investigation.

Recommendations must reflect the actual findings, data limitations, and context rather than assume that every observed disparity has the same cause.

## 5. Data Requirements

Candidate sources include:

- Rwanda FinScope 2024 and its associated documentation.
- National Bank of Rwanda financial inclusion indicators.
- Access to Finance Rwanda publications and reports.
- Relevant socioeconomic or geographic datasets where needed and available.

Before selecting the final dataset, establish:

- What population the data represents.
- Which financial inclusion indicators are directly measured.
- Available geographic and demographic detail.
- Whether survey weights, sampling design, or uncertainty estimates are documented.
- Missing data, sample sizes, and data quality.
- Access conditions and redistribution restrictions.
- Availability of compatible geographic boundary files.

**Important:** Candidate sources are not confirmed project inputs until their data, documentation, and access conditions have been checked.

## 6. Analytical Principles

1. Distinguish financial exclusion from financial vulnerability.
2. Prioritize direct financial-access measures over indirect socioeconomic proxies.
3. Use survey weights and sampling information where required and available.
4. Avoid unreliable rankings based on insufficient observations.
5. Report uncertainty and limitations alongside important findings.
6. Avoid causal claims unless supported by an appropriate research design.
7. Make prioritization methods transparent and reproducible.
8. Protect sensitive data and comply with dataset access and use conditions.

## 7. Initial Scope

### Core deliverables
- Data inventory and documented data dictionary.
- Cleaned, reproducible analytical dataset or processing workflow.
- Exploratory and comparative analysis.
- Evidence-based findings on financial inclusion disparities.
- Streamlit dashboard.
- Documented methodology, limitations, and recommendations.
- README with setup and execution instructions.

### Optional deliverables
- Interactive geographic maps.
- Clustering or segmentation.
- More advanced statistical models.
- Additional datasets for deeper geographic or socioeconomic analysis.

Optional work will only proceed when the core analysis is sound and sufficient time remains.

## 8. Two-Week Execution Plan

### Days 1–2: Research and Data Validation
- Inspect candidate datasets and documentation.
- Confirm access and usage conditions.
- Define measurable indicators and research questions.
- Establish the data dictionary and feasibility of geographic analysis.

**Milestone:** A verified dataset and a defensible analytical scope.

### Days 3–4: Data Preparation and Exploration
- Clean and validate data.
- Assess missing values and sample sizes.
- Calculate initial indicators.
- Explore national, geographic, and demographic disparities.

**Milestone:** Initial findings backed by reproducible analysis.

### Days 5–6: Statistical Analysis and Prioritization
- Investigate relevant associations.
- Evaluate the reliability of estimates.
- Develop and test a transparent prioritization method if justified.
- Document limitations.

**Milestone:** An evidence-based analytical approach.

### Days 7–9: Dashboard Development
- Implement the national overview and core comparisons.
- Add interactive filters and charts.
- Add maps only if the data supports them.

**Milestone:** An end-to-end working dashboard by Day 7, with subsequent improvements.

### Days 10–11: Validation
- Verify dashboard values against analytical outputs.
- Test calculations and filters.
- Review uncertainty, methodology, and interpretations.
- Correct misleading or unsupported conclusions.

**Milestone:** A validated prototype.

### Days 12–14: Finalization
- Improve usability and presentation.
- Test execution and deployment.
- Finalize documentation and recommendations.
- Prepare the demonstration and presentation.

**Milestone:** A reproducible, demonstrable final project.

## 9. Definition of Success

The project should:
- Answer the research questions that the available data can support.
- Distinguish measured exclusion from inferred vulnerability.
- Produce reproducible and explainable results.
- Avoid unsupported geographic rankings or causal conclusions.
- Present useful findings through an operational dashboard.
- Explain how the findings could inform further investigation or intervention.

## 10. Decisions Still to Be Confirmed

- Final dataset and access method.
- Geographic resolution supported by the data.
- Final indicator definitions.
- Whether composite prioritization is defensible.
- Whether mapping or clustering adds sufficient value.
- Final dashboard layout and code architecture.

These decisions will be made after initial data inspection rather than assumed in advance.