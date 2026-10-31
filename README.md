# 1. Introduction

## 1.1 Background

Financial inclusion plays an important role in promoting economic development, reducing poverty, and improving the financial well-being of individuals and households. Access to appropriate financial services enables people to save money, access credit, make transactions, manage financial risks, and participate more effectively in economic activities. However, access to financial services does not necessarily mean that all population groups enjoy the same level of access or usage.

In Rwanda, the National Financial Inclusion Survey (FinScope Rwanda 2024) provides important insights into the financial behaviours, access to financial services, and financial needs of the population. The survey reported that 96% of Rwandan adults were financially included, while 4% remained financially excluded. Although these national figures demonstrate significant progress, national-level statistics alone do not fully reveal differences in financial inclusion across geographical areas and population groups.

Understanding these differences requires examining financial inclusion at more detailed levels, including districts, urban and rural communities, gender, age groups, and educational backgrounds. It is also important to understand the barriers that prevent individuals from accessing particular financial services.

To make such information more accessible and useful for analysis, this project introduces the **Rwanda Financial Inclusion Gap Explorer**, an interactive data analytics and decision-support dashboard built around FinScope Rwanda 2024 survey data, with additional contextual information from National Bank of Rwanda administrative data.

## 1.2 Problem Statement

Despite the availability of comprehensive financial inclusion survey data, extracting meaningful insights from large survey datasets and reports can be challenging, particularly when users need to compare different geographical areas and population groups.

National financial inclusion statistics provide an overview of the country's progress but may conceal inequalities in access to and usage of specific financial services. For example, a high national inclusion rate does not necessarily indicate that individuals across all districts have equal access to banking services, mobile money, savings opportunities, or credit facilities.

Furthermore, identifying differences in financial inclusion is only one part of the challenge. Stakeholders also need to understand the indicators contributing to these differences, examine reported barriers, and assess which geographical areas or population groups may require further investigation.

Without an accessible analytical platform, exploring these relationships may require considerable manual effort involving survey reports, statistical software, spreadsheets, and separate data sources.

The Rwanda Financial Inclusion Gap Explorer addresses this challenge by providing an interactive environment through which users can explore financial inclusion indicators, compare geographical and demographic groups, examine reported barriers, and identify potential areas of concern using available evidence.

## 1.3 Project Overview

The Rwanda Financial Inclusion Gap Explorer is a Python-based analytical dashboard developed using Streamlit. Its primary purpose is to transform financial inclusion data into accessible, interactive, and understandable insights that can support evidence-based analysis and decision-making.

The project primarily uses the FinScope Rwanda 2024 survey dataset to calculate and visualize financial inclusion indicators at national and district levels. It also provides comparisons across selected population groups, including gender, age, education, and urban or rural residence.

The platform incorporates several analytical capabilities, including:

- **National Overview:** Shows the national financial-inclusion picture and highlights how district, urban-rural, service-use, and reported-barrier patterns can differ behind the national headline.
- **District Explorer:** Lets users compare selected indicators across Rwanda's districts and with national estimates, helping reveal local gaps that national averages can hide.
- **Population Groups:** Compares available survey indicators across gender, age, education, and urban-rural groups to show how reported access and financial resilience differ.
- **Priority Explorer:** Screens for districts with relatively larger gaps across a fixed four-indicator baseline, explains the score's drivers, and lets users test how rankings change in what-if scenarios. The score is a comparison aid, not a count of people in need or an investment decision.
- **Policy Alignment:** Connects selected findings to national priorities and presents questions for further investigation; it does not prescribe interventions or decide where funding should go.
- **Methodology and Sources:** Explains how indicators and comparisons are produced, where the data comes from, and what limitations users should consider.

In addition to the FinScope survey analysis, the platform incorporates a separate data collection and analysis component based on publicly accessible National Bank of Rwanda (BNR) financial inclusion dashboard information. This component uses browser automation to collect selected administrative indicators, which are stored and managed separately for subsequent analysis and visualization.

The two data sources provide complementary perspectives. FinScope offers survey-based estimates of financial access and usage among individuals, while BNR administrative data provides additional information about financial institutions and service delivery. The platform maintains the distinction between these sources to avoid treating administrative observations as equivalent to survey estimates.

Overall, the system is designed to make financial inclusion evidence easier to explore, interpret, and compare while maintaining transparency regarding the definitions and limitations of the available data.

## 1.4 Project Objectives

The overall objective of the project is to develop an interactive and explainable analytical platform that facilitates the exploration of financial inclusion gaps in Rwanda using survey data and complementary administrative information.

The specific objectives are:

1. To process and analyze FinScope Rwanda 2024 survey data to generate relevant financial inclusion indicators and statistical summaries.
2. To provide interactive visualizations and comparisons of financial inclusion across Rwanda's districts and selected population groups.
3. To examine reported barriers affecting access to financial services, particularly the reasons individuals do not have bank accounts.
4. To develop an exploratory district-screening mechanism that identifies differences between district-level indicators and national estimates while examining the stability of comparative rankings.
5. To integrate complementary financial inclusion information from the Bank of Rwanda administrative dashboard, where available, while maintaining clear distinctions between survey and administrative data.
6. To provide transparent methodological explanations, data sources, indicator definitions, and analytical limitations to support responsible interpretation of the results.

## 1.5 Scope of the Project

The project focuses on exploring financial inclusion in Rwanda using the 2024 FinScope survey as its primary source of analytical data.

Geographically, the survey analysis covers Rwanda's 30 districts, allowing users to examine variations in financial inclusion across different parts of the country. The analysis focuses on adults aged 16 years and above, consistent with the survey population.

The FinScope component covers eight indicators defined in the application's indicator registry:

**Core indicators:**

- Ownership of a bank account.
- Registration as a mobile money user.
- Borrowing within the previous 12 months.
- Saving behaviour.

**Supporting indicators:**

- Access to emergency funds.
- Saving through groups.
- Current use of an Umurenge SACCO.
- Current use of savings groups.

The dashboard further supports selected comparisons based on gender, age, education, and urban or rural residence, as well as an examination of reported barriers to bank account ownership.

The project also includes a complementary administrative-data component that collects selected information from the National Bank of Rwanda financial inclusion dashboard. This component covers different financial-service areas, including banking, agents, branches, credit, insurance, savings, and transactions, depending on data availability.

The analytical scope is primarily descriptive and exploratory. The platform identifies patterns, differences, and potential areas requiring further investigation. Its district-screening functionality is not intended to constitute an official poverty index, a definitive measure of financial need, or an automated policy recommendation system. Similarly, observed differences between population groups should not be interpreted as evidence of causal relationships.

The project therefore provides an interactive environment for understanding financial inclusion patterns, exploring potential gaps, and supporting evidence-informed discussions among stakeholders.

# 2. Rationale for Using Regularly Collected Administrative Data

## 2.1 Moving Beyond Static Financial Inclusion Reporting

The development of the Rwanda Financial Inclusion Gap Explorer was motivated by a fundamental question: **What additional value can a data platform provide to policymakers beyond presenting existing statistics through a more accessible interface?**

Financial inclusion surveys and statistical reports provide valuable evidence about the state of financial inclusion. They help establish how individuals access and use financial services, their financial behaviours, and the barriers they experience. However, even when several existing datasets are brought together in an interactive dashboard, the platform's analytical value remains constrained by the age, scope and frequency of the underlying information.

A platform built entirely around static datasets risks reproducing information that policymakers and other stakeholders may already have access to, only in a more organized or visually accessible format. Improved presentation and exploration are useful, but they do not necessarily address the challenge of observing developments between major data collection and publication cycles.

This creates a temporal limitation. By the time a survey has been conducted, processed, analyzed and published, the conditions it describes may already have changed. A subsequent survey may not become available for several years. Consequently, a platform that relies exclusively on historical survey results can provide a valuable historical picture but may have limited capacity to monitor more recent developments.

The project therefore explored an alternative approach. Rather than attempting to repeatedly establish the country's exact financial inclusion level using information that was not designed for continuous monitoring, could the platform provide defensible, regularly collected signals about how financial services are developing and where potential gaps may remain?

This question influenced the decision to complement FinScope Rwanda 2024 with regularly collected administrative information from the National Bank of Rwanda (BNR).

## 2.2 Combining Survey Evidence with Regularly Collected Administrative Information

The project does not abandon historical survey data. Instead, it recognizes that different data sources can contribute different forms of evidence.

FinScope Rwanda 2024 provides the primary survey-based perspective. It offers detailed information about individuals' financial access, usage, behaviour and reported barriers. Its weighted estimates help describe financial inclusion among the surveyed population during the 2024 survey period.

BNR administrative information provides a complementary perspective through selected indicators recorded within the financial system. These observations can provide information about financial service activity, geographical distribution and other available administrative measures.

To make this information useful beyond a single collection, the project developed a browser-automation system that interacts with the public BNR Financial Inclusion Dashboard and collects selected observations on a weekly schedule. The collected records are preserved in MongoDB, allowing historical observations to be examined rather than simply replacing previous values with the latest available information.

This creates two complementary analytical perspectives:

- **FinScope survey evidence:** What do individuals report about their access to and use of financial services?
- **BNR administrative evidence:** What activity and service-related patterns are recorded by the financial system within the indicators and definitions available from the administrative source?

The distinction is important. A survey estimate of the percentage of adults who own a bank account is not equivalent to an administrative count of customers or active accounts. The two sources have different collection methods, units, populations, denominators and purposes. They must therefore be interpreted separately.

The value comes from examining what each source establishes and identifying where their findings can provide useful context for one another.

## 2.3 Understanding the Difference Between Financial Inclusion and Practical Access

Financial inclusion, physical availability and practical accessibility are related, but they are not interchangeable.

Consider a hypothetical individual who is classified as financially included but must travel approximately one hour by bus to reach the nearest bank branch.

That individual is not necessarily financially excluded. They may own an account, use mobile money or access other financial services. Nevertheless, the distance and time required to reach a physical banking facility may represent a practical access gap.

Now consider other individuals living in the same area who do not use the same financial services. The distance to available banking facilities may be one factor worth investigating when examining their lower adoption of those services.

This example illustrates why an overall financial inclusion classification does not necessarily reveal every practical challenge experienced by individuals and communities.

It also demonstrates the value of examining different forms of evidence together. Survey findings can reveal differences in individual adoption and reported financial behaviour, while administrative information can provide additional context about the distribution and recorded activity of financial services.

For example, if survey evidence indicates relatively low adoption of a particular service in a location, administrative observations about the availability or activity of that service may help provide further context. Where appropriate geographical information is available, stakeholders could investigate whether the observed patterns are consistent with potential service-access challenges.

The bus-travel example is illustrative and is not a finding derived from the BNR dataset. The current project does not claim to measure individual travel times to bank branches or establish that physical distance causes lower adoption.

The broader point is that **being financially included does not necessarily mean having convenient access to every financial service, and the presence of a financial service does not necessarily mean that individuals are adopting or using it.**

## 2.4 Why Regular Collection Matters

Regularly collecting administrative observations introduces a monitoring dimension that cannot be achieved through historical survey data alone.

The project uses scheduled GitHub Actions workflows to collect current BNR dashboard observations weekly. It also includes a backup collection workflow and a manually dispatched historical backfill workflow. The scraper interacts with the dashboard's dynamic pages, applies available filters, selects reporting dates, extracts indicators and paginated tables, and stores the resulting observations with their collection metadata.

This allows the platform to preserve a sequence of dated observations and examine changes across the periods for which suitable data is available.

The monitoring approach creates opportunities to:

- Observe changes in recorded financial service activity.
- Examine how selected indicators vary across districts and other available geographical units.
- Identify locations with comparatively low recorded activity or adoption.
- Investigate whether previously observed patterns persist, improve or become more pronounced.
- Examine relationships between administrative observations and relevant FinScope survey findings.
- Identify unusual observations that may warrant further verification and investigation.

However, the frequency of collection should not be confused with the frequency of updates made by the original data provider. The project collects snapshots weekly; it does not guarantee that every underlying BNR indicator is updated every week or that the source represents real-time financial activity.

Similarly, a successful collection does not independently establish that the source's definitions, values or coverage are correct. The project therefore preserves source information, collection dates, filter combinations, run statuses and other metadata to support traceability and data-quality assessment.

## 2.5 From Data Presentation to Evidence-Based Exploration

The project's objective is not to produce another dashboard that simply presents historical statistics in a more attractive format. It is to provide an environment where stakeholders can explore established survey findings alongside regularly collected administrative observations.

The two sources can help answer different but related questions:

- What financial inclusion patterns were observed in the 2024 survey?
- Which districts or population groups show comparatively different levels of access and usage?
- What changes are visible in the administrative observations collected over time?
- Are there locations where selected administrative indicators suggest a pattern that deserves closer examination?
- Where do survey findings and administrative observations provide complementary context?
- Which observations require additional evidence before they can support a policy conclusion?

The project also introduces exploratory statistical methods for identifying unusual changes and differences between districts in the administrative data. These methods are intended to help prioritize observations for review, not automatically determine that a district has a financial inclusion problem.

By combining detailed household survey evidence with more frequently collected administrative observations, the Rwanda Financial Inclusion Gap Explorer seeks to move beyond a static presentation of historical statistics.

It is best understood as an **evidence-based financial inclusion exploration and monitoring platform**. Its purpose is to help stakeholders examine patterns, observe selected developments, identify potential gaps and determine where further investigation or policy attention may be warranted.

It does not independently establish the country's current financial inclusion level, prove the causes of observed differences or automatically prescribe policy interventions.

---

# 3. Technologies, System Architecture and Capabilities

## 3.1 Technology Stack Overview

The Rwanda Financial Inclusion Gap Explorer is implemented primarily in Python. Its architecture combines survey-data processing, interactive visualization, browser-based data collection, document storage and experimental statistical analysis.

The main technologies were selected to support the project's analytical and operational requirements without introducing an unnecessarily complex frontend/backend architecture.

| Technology | General capabilities | Role in the project |
|---|---|---|
| Python | General-purpose programming, automation and data analysis | Main programming language for the dashboard, processing pipeline, scraper, intelligence package and tests |
| Streamlit | Development of interactive web applications using Python | Dashboard interface, navigation, authentication, caching and user interactions |
| Pandas | DataFrame manipulation, grouping, aggregation and file processing | FinScope processing, administrative-data normalization and statistical summaries |
| NumPy | Numerical operations and array-based calculations | Supporting numerical calculations and validation |
| Plotly | Interactive charts, maps and data visualizations | District maps, comparisons, distributions and historical trends |
| GeoJSON | Representation of geographical features | Rwanda district boundaries used in geographical visualizations |
| Playwright | Automated browser interaction and testing | Dynamic interaction with the BNR dashboard and extraction of selected information |
| Chromium | Browser execution engine | Runs the automated browser sessions controlled by Playwright |
| MongoDB | Document-oriented database storage and querying | Historical storage of BNR observations, collection runs and table records |
| PyMongo | Python interface for MongoDB | Database writes by the scraper and reads by the dashboard |
| Jupyter Notebook | Interactive computational environment | Exploratory analysis and development of FinScope indicators |
| Matplotlib and Seaborn | Statistical and analytical visualization | Exploratory plots in the research and analysis notebooks |
| pytest | Automated Python testing | Testing data processing, model functions, scraper behavior and application pages |
| GitHub Actions | Hosted workflow automation | Scheduled BNR collection, backup collection and manual historical backfill |

The application uses Streamlit's native capabilities and does not implement a separate React frontend or independent API backend. This keeps the application architecture relatively simple and allows the analytical logic to remain within the Python project.

The declared dependencies are maintained in `requirements.txt`. Some dependencies support development notebooks and historical analysis rather than the production dashboard itself. Python 3.12 is explicitly specified in the BNR collection workflows; a project-wide supported Python version range is not separately declared.

## 3.2 Programming and Data Processing Technologies

### Python

Python provides the common development environment for the project's different components. Its ecosystem supports data processing, statistical calculations, web automation, database communication and application development.

Within the project, Python is used to:

- Load and process FinScope survey microdata.
- Calculate weighted indicators and group-level summaries.
- Validate processed datasets and indicator relationships.
- Automate interaction with the BNR dashboard.
- Normalize and store administrative observations.
- Perform experimental anomaly detection and contextual analysis.
- Run automated tests.

Using a common programming language across these components reduces the need to maintain separate implementations for data processing, collection and application logic.

### Pandas and NumPy

Pandas provides the primary tabular data-processing functionality. It is used to load the FinScope Stata dataset, manipulate survey variables, group observations, calculate weighted estimates and export processed results to CSV files.

NumPy supports numerical operations and validation used throughout the processing and analysis pipeline.

The project applies survey weights through the `pop_wt` variable when calculating relevant FinScope estimates. Indicator definitions and denominator rules are implemented explicitly rather than relying on a general-purpose survey-analysis package.

For example, direct questions use valid item responses, while certain routed current-use indicators count individuals who have never used the service as non-users in the full-population denominator.

The main implementation is distributed across:

- `build_processed_data.py` — processes the original survey and generates analytical outputs.
- `data.py` — loads processed data and provides application-side data access.
- `indicators.py` — centralizes indicator definitions and metadata.
- `validation.py` — performs data-quality and consistency checks.

### Jupyter Notebook

Jupyter provides an interactive environment for investigating the original survey, testing indicator definitions and developing analytical approaches before incorporating them into the application.

The project includes the following notebooks:

- `01_exploratory_data_analysis.ipynb`
- `02_financial_inclusion_indicators.ipynb`
- `03_population_group_analysis.ipynb`
- `04_extended_financial_inclusion_indicators.ipynb`

These notebooks document exploratory and analytical work. They are development and research resources, not components executed by the production dashboard during normal operation.

### Processing Outputs

The application reads processed CSV files rather than loading and recalculating the complete FinScope microdata whenever a user opens a dashboard page.

This separates the computationally heavier survey-processing stage from the interactive application stage.

It also means that rebuilding the dashboard's survey outputs requires access to the original microdata and the processing scripts. The original Stata file is present in the development workspace but is excluded from the tracked Git repository. A repository checkout alone therefore does not guarantee that all raw inputs required to reproduce the processed outputs will be available.

## 3.3 Application and Visualization Technologies

### Streamlit

Streamlit provides the main application interface and application execution environment.

The application entry point is `app.py`, which loads the dashboard pages and coordinates navigation, application state and authentication.

The current dashboard contains six main analytical pages:

1. National Overview
2. District Explorer
3. Population Groups
4. Priority Explorer
5. Policy Alignment
6. Methodology and Sources

Streamlit provides the user-facing controls, navigation, tables, session state and caching mechanisms. The application also uses custom HTML and CSS to support interface styling and layout.

Data loading is cached to reduce unnecessary repeated processing and database queries during user interactions.

Streamlit was appropriate for the project because it allows Python-based analytical functionality to be exposed through an interactive web application without requiring a separately developed frontend.

Its limitation is that it does not provide the same architectural separation and frontend customization possibilities as a dedicated frontend framework and backend service. However, that additional complexity was not necessary for the project's current scope.

### Plotly

Plotly is used to create interactive visualizations.

Its capabilities include interactive charts, geographical maps, hover information and selection-based exploration. Within the project, it supports:

- National indicator visualizations.
- District comparisons.
- Population-group comparisons.
- Geographical representation of selected district indicators.
- Administrative-data distributions and historical trends.

The District Explorer uses Plotly with a GeoJSON file containing Rwanda's district boundaries. District values are associated with geographical features using the `shapeName` property.

The map implementation does not rely on a dedicated GIS backend such as GeoPandas or Folium. Instead, the application uses Plotly's geographical visualization capabilities directly.

Some map backgrounds can depend on external map tile providers, meaning that their availability may depend on network connectivity and the external provider.

### GeoJSON

GeoJSON is a geographical data format used to represent spatial features and their properties.

The project uses a Rwanda district boundary file, `geoBoundaries-RWA-ADM2.geojson`, to support district-level visualization.

The application associates survey or selected administrative observations with geographical features. This requires district names and identifiers in the analytical data to match the properties available in the geographical file.

Differences in spelling, naming conventions or district identifiers can therefore affect geographical matching.

## 3.4 FinScope Data Processing Architecture

The FinScope processing pipeline converts the original survey microdata into analytical outputs that can be consumed by the dashboard.

The main workflow is:

1. **Input:** The original FinScope Rwanda 2024 Stata dataset, `FinScope2024Rwanda.dta`.
2. **Loading:** Pandas reads the dataset and makes the relevant survey variables available for processing.
3. **Indicator construction:** Explicit indicator rules interpret survey responses and apply the appropriate numerator and denominator definitions.
4. **Weighting:** Relevant estimates use the individual survey weight, `pop_wt`.
5. **Aggregation:** Results are calculated at national, district, urban/rural and population-group levels, depending on the indicator and available data.
6. **Validation:** Processing and validation routines examine output structure, values, geographical coverage and selected consistency relationships.
7. **Export:** Processed results are written to CSV files.
8. **Application loading:** Streamlit reads and caches the processed outputs for use across dashboard pages.

Geographical and demographic breakdowns use the available survey variables, including district (`a2`), residence (`a6`), gender (`b2`), age (`b1`) and education (`c4a`).

Bank-account barrier analysis uses responses from individuals who reported not having a bank account and provided a reason, based on the relevant survey variables.

The indicator registry centralizes the definitions and metadata used by the application. This helps maintain consistency in the interpretation and presentation of indicators across dashboard components.

An important implementation qualification is that the processing script supports eight registered indicators across several breakdowns, but the currently inspected processed CSV files do not all contain the complete eight-indicator coverage for urban/rural and population-group outputs. The registered scope should therefore not be interpreted as proof that every indicator is currently available in every breakdown. Rebuilding and validating the delivered outputs is required to establish that coverage.

## 3.5 BNR Data Collection and Storage Architecture

### Browser automation using Playwright

The project uses Playwright to interact with the public BNR Financial Inclusion Dashboard.

Unlike a conventional scraper that only reads static HTML, Playwright controls an actual browser session. This allows the collection system to interact with dynamic dashboard elements, including filters, dropdowns, reporting-date controls and paginated tables.

Chromium provides the browser environment, while Playwright handles the interactions and extraction logic.

The main collection implementation is in `nbr_engine.py`, with dashboard pages and filter configurations maintained in `nbr_pages.json`.

The scraper's responsibilities include:

- Opening configured BNR dashboard pages.
- Discovering or validating available filter controls.
- Selecting relevant filter combinations.
- Selecting reporting dates.
- Waiting for dashboard content to update after interactions.
- Verifying that selected filters have taken effect.
- Extracting KPI cards and available table information.
- Extracting selected chart data where supported.
- Navigating through table pagination.
- Recording collection outcomes and relevant metadata.

The scraper also includes safeguards for handling incomplete or inconsistent observations. These include retry limits, repeated-page detection, content hashing, table-header and row-width validation, and protection against saving incomplete paginated tables.

Collection outcomes are distinguished through statuses such as complete, failed, no-data and not-applicable.

These safeguards improve collection reliability and traceability. However, browser automation remains dependent on the source dashboard's availability, structure, selectors, filter behavior and displayed information. Changes to the BNR website may require corresponding updates to the scraper.

A successful scrape also does not independently validate the underlying administrative data or establish that every available dashboard combination has been collected.

### MongoDB and PyMongo

MongoDB is used to preserve historical administrative observations.

The project uses PyMongo as the Python interface for database communication. The database is named `nbr_financial_inclusion` and contains three principal collections:

- `page_scrape_runs` — records collection executions and their outcomes.
- `page_kpi_observations` — stores extracted KPI observations.
- `page_table_observations` — stores observations extracted from dashboard tables.

Stored records preserve information such as source URL, dashboard page, requested and observed filters, reporting or snapshot date, collection timestamp, run ID, status, raw table values and content hashes.

Unique indexes help prevent duplicate records for the same page, date and filter combination. Table observations additionally use row indexes to distinguish records within a table.

The database allows the project to retain observations from earlier collection periods rather than simply replacing them with the latest values.

The scraper writes observations to MongoDB, while the dashboard's database readers retrieve and normalize relevant records for display. The application uses read-only database access for these observations.

The database connection is supplied through environment configuration rather than a committed connection string. The actual hosting provider for MongoDB is not established by the inspected repository configuration.

### Scheduled collection using GitHub Actions

GitHub Actions automates the collection process.

The project contains three principal workflows:

- `nbr-current.yml` — scheduled current-data collection.
- `nbr-backup.yml` — scheduled backup collection.
- `nbr-backfill.yml` — manually dispatched historical collection.

The scheduled workflows run weekly. They install the required Python environment, Playwright and Chromium, then execute the collection process using the MongoDB connection supplied through GitHub repository secrets.

These workflows automate data collection, not application deployment or continuous model inference.

The distinction is important: the project has an automated mechanism for regularly collecting and preserving administrative observations, while the experimental anomaly analysis remains primarily an offline or command-line process.

## 3.6 System Architecture and Data Flow

The project consists of two principal data pipelines that are presented through a common Streamlit application.

### A. FinScope survey pipeline

FinScope Data Processing Flow
1. Input: FinScope Rwanda 2024 Stata microdata.
2. Data processing: Python and Pandas load and process the survey data.
3. Indicator construction: Relevant survey responses are used to calculate indicators and apply survey weights.
4. Aggregation and validation: Results are grouped into national, district and population-group summaries, then checked for data quality and consistency.
5. Processed outputs: The resulting analytical datasets are exported as CSV files.
6. Application loading: Streamlit data loaders read and cache the processed CSV files.
7. Dashboard presentation: The dashboard pages display the resulting indicators through charts, tables and maps. Rwanda district GeoJSON boundaries provide the geographical features used for district-level maps.

The FinScope pipeline transforms survey microdata into weighted analytical indicators and group-level summaries. The resulting processed files are loaded by the application and presented through interactive visualizations, comparisons and geographical analysis.

### B. BNR administrative-data pipeline

BNR Administrative Data Collection Flow
1. Data source: The National Bank of Rwanda (BNR) Financial Inclusion Dashboard provides the administrative information.
2. Browser automation: Playwright controls Chromium to access and interact with the dashboard.
3. Filter selection: The scraper selects the required dashboard pages, filters, reporting dates and other available options.
4. Data extraction: The system extracts KPI values and table records, including paginated results.
5. Validation: Extracted information undergoes checks for completeness, consistency, repeated content and collection status.
6. Historical storage: Validated observations and collection metadata are stored in MongoDB.
7. Application access: Streamlit's MongoDB readers retrieve and normalize the stored observations.
8. Dashboard presentation: The administrative dashboard views present the retrieved information through charts, tables and other visualizations.
Collection automation: GitHub Actions initiates the scheduled weekly collection workflows. A separate manually dispatched workflow supports historical backfilling. Both use the same browser-automation pipeline to collect and store observations.

The BNR pipeline collects selected administrative observations from the dashboard, validates their structure and stores them with historical and collection metadata.

The Streamlit application retrieves the stored observations and presents them through administrative-data visualizations.

### C. Integration between the two sources

FinScope and BNR are deliberately kept separate in their units, denominators and analytical meaning.

FinScope indicators represent weighted survey estimates from the 2024 survey. BNR observations represent administrative counts and other dashboard-reported measures.

The project does not convert administrative customer counts into FinScope percentages or treat district-level administrative values as interchangeable with national survey estimates.

Instead, an indicator-mapping registry identifies possible relationships between the sources. Relationships are categorized according to whether they are relevant context, uncertain proxies, unsuitable or unavailable.

For example:

- Bank branches may provide context about financial infrastructure, but they do not directly measure bank-account ownership.
- BNR gender-filtered observations can support some comparisons where their scope matches the survey measure.
- BNR Youth and Non-Youth categories are not automatically equated with the survey's age bands.
- Education and urban/rural comparisons are not presented as directly comparable when matching administrative observations are unavailable.

The Combined National Overview includes a page-scoped FinScope contextualization assessment. It evaluates eligible relationships between selected survey indicators and administrative observations and displays a limited number of findings.

This contextualization is performed in memory and does not load the saved experimental model report JSON. It also does not recalculate FinScope estimates or infer causal relationships between the sources.

## 3.7 Application Capabilities and Analytical Components

The dashboard contains several components with distinct responsibilities.

### National Overview

The National Overview shows the national financial-inclusion picture and selected administrative context. It helps users see how a high national estimate can coexist with differences across districts, urban and rural areas, services, and reported barriers.

In Combined mode, the page provides limited contextualization between eligible FinScope findings and NBR administrative observations. The two sources remain distinct, and not every administrative indicator has a directly comparable survey measure.

### District Explorer

The District Explorer lets users examine selected financial inclusion indicators across Rwanda's 30 districts and compare a district's estimate with the national reference.

Its map, indicator-specific comparisons, and available administrative context help users investigate local differences that can be hidden by national averages. The comparisons describe survey patterns; they do not establish why a gap exists or determine how resources should be allocated.

### Population Groups

The Population Groups page compares available indicators across gender, age, education, and urban-rural categories. It helps users see how reported access, service use, saving, and resilience differ between groups nationally.

These are descriptive group comparisons, not estimates for every group within every district. Indicator availability depends on the processed breakdown data and the applicable denominator.

### FinScope Priority Explorer

The FinScope Priority Explorer is a descriptive screening aid for finding districts with relatively larger gaps across selected access and resilience indicators.

Its fixed baseline combines four indicators using equal weights and compares district estimates with national references. Users can inspect the factors behind a score and test alternative indicator combinations; these what-if scenarios do not replace the baseline.

Scores are relative points, not percentages, beneficiary counts, definitive measures of need, predictions, or investment recommendations. The page supports further investigation; local evidence is needed before choosing an intervention.

This component should also be distinguished from the experimental NBR anomaly-detection package described later in this section.

### Policy Alignment

The Policy Alignment page connects selected survey findings with published policy references and suggests questions that decision-makers and service providers can investigate.

It provides context, not proof of causes, predictions of demand, or instructions about where to invest. Findings should be validated locally before decisions are made.

### Methodology and Sources

The Methodology and Sources page explains what the indicators mean, how the data and comparisons are prepared, and where the information comes from.

It also describes uncertainty, assumptions, and limitations so users can judge what the results support and what they do not.

## 3.8 Intelligent Model Architecture and Current Capabilities

### 3.8.1 Version and nature of the model

The NBR intelligence package declares version `nbr-intelligence-0.4.4` in `init.py`.

Despite the use of the terms intelligence and adaptive, the current implementation is not a trained machine-learning model.

It is an experimental collection of explainable statistical detectors, evidence-sufficiency checks and contextualization functions. The implementation primarily uses Python's built-in statistical and numerical capabilities rather than a machine-learning framework such as scikit-learn, TensorFlow or PyTorch.

The term adaptive describes the way the experimental analysis reloads eligible historical MongoDB observations and recomputes statistical reference values when a batch experiment is run.

It does not mean the system learns from reviewer feedback, maintains a continuously trained model or automatically updates its thresholds through a learning process.

The principal implementation is located in `src/models/nbr_intelligence/`, with the following modules:

- `experiment.py` — experimental anomaly detection and analysis workflow.
- `assessment.py` — evidence sufficiency and qualification assessment.
- `contextualization.py` — FinScope-aware contextual analysis.
- `indicator_mapping.py` — relationships between administrative and survey indicators.
- `review.py` — review-queue and reviewer-field handling.

### 3.8.2 Implemented statistical detectors

The package contains several methods for identifying unusual administrative observations.

| Method | Purpose | Current implementation |
|---|---|---|
| Temporal rate/MAD detector | Identifies unusually large changes in a district's historical series | Uses changes in `log(1 + value)` and compares the target rate with previous rates using the median and median absolute deviation (MAD) |
| Temporal level/MAD baseline | Identifies values that differ from preceding observations | Compares a current value with a robust historical median and MAD; serves as a comparator rather than a validated production detector |
| Existing 50% / 8-day rule | Identifies observations that meet a simple recent-change threshold | Retained as a baseline review rule, separate from the adaptive detector |
| Cross-sectional peer detector | Identifies unusually different values among districts within the same comparison scope | Uses a modified median/MAD robust score to identify district-level outliers |

The temporal rate detector uses walk-forward fitting, meaning that it uses earlier observations to establish its reference values rather than using future observations to evaluate the past.

It requires at least three prior rates, uses a fixed robust-score threshold of 3.0 and abstains when dispersion is zero or unstable, or when training observations are discordant.

The cross-sectional peer detector requires at least ten districts, uses a fixed threshold of 3.5 and abstains when peer dispersion is zero.

The experiment also contains safeguards for identifying the exact comparison scope. This includes the dashboard page, metric, reporting date, district and canonical filter combination.

Data preparation requires suitable complete runs, matching run identifiers and filters, valid reporting dates, collection timestamps and recognized district geography.

Repeated-content snapshots and missing, nonnumeric, non-finite or negative observations are excluded. Zero is retained as a valid value. Missing district observations are not automatically interpreted as zero.

These safeguards are important because an unusual value is only meaningful when the observations being compared represent a sufficiently consistent scope.

### 3.8.3 Evidence assessment and contextualization

The model includes an evidence-assessment component that evaluates whether the available observations are sufficient for a particular comparison.

Evidence states include:

- Sufficient evidence.
- Limited evidence.
- Insufficient evidence.

These labels describe the adequacy of the evidence supporting the comparison. They do not represent the probability that an anomaly is genuine, model confidence or measured detection accuracy.

Freshness, completeness and geographical coverage are assessed separately.

The contextualization component can examine observed-date trends, relate selected NBR series to FinScope baseline indicators and compare administrative channels when their scopes and shared observation dates permit.

It preserves the original metric labels and units and abstains when a relationship cannot be established adequately.

It does not recalculate the original FinScope estimates, automatically establish equivalence between different measures or infer that one observed change caused another.

### 3.8.4 Outputs and human review

The experimental pipeline can generate JSON reports containing analytical results and contextualization information, as well as CSV review queues.

Review queues include stable candidate identifiers and fields for reviewer information, disposition, rationale, supporting evidence and review timestamps.

The implementation preserves human-entered review fields when review data is merged with subsequent outputs.

However, the presence of a review mechanism does not mean a completed model-feedback loop exists. The inspected saved review artifacts were pending, and there were no independent adjudicated labels available to train or validate the detectors.

Human review is therefore an important part of the intended development process, but its outcomes have not yet been incorporated into a validated learning system.

### 3.8.5 Dashboard integration boundary

The intelligence package and the dashboard have different levels of integration.

The Combined National Overview invokes contextualization functions and selects a limited number of eligible findings for display.

The temporal and peer anomaly experiments, however, are primarily command-line or offline analytical processes. The current application code does not establish them as a live forecasting or automated alert service.

The project also contains documentation describing an experimental anomaly-candidate panel in the Priority Explorer. However, the inspected `nbr_priority_explorer.py` implementation does not invoke the temporal or peer detectors.

The current FinScope Priority Explorer performs its own survey-based district screening, while the NBR Priority Explorer presents descriptive administrative-data distributions, trends and scope information.

Consequently, an interactive anomaly-detection panel in the Priority Explorer should not be described as an implemented dashboard feature in the current version.

## 3.9 Experimental Results and Model Validation

The experimental notes document a read-only analysis conducted on 28 October 2026.

The run examined 1,873 collection runs and 50,418 district-table documents across five irregular reporting dates. Following data preparation and exclusions, 48,988 district metric observations were retained.

The reported experimental results include:

| Experimental measure | Result |
|---|---:|
| Temporal rate/MAD walk-forward cases | 9,546 |
| Scoreable temporal cases | 6,095 |
| Temporal candidates flagged | 5,376 |
| Flagged share of scoreable cases | 88.20% |
| Temporal cases where the method abstained | 3,451 |
| Cross-sectional assessable observations | 48,930 |
| Cross-sectional candidates | 4,510 |
| Cross-sectional candidate share | 9.22% |
| Cross-sectional candidates carrying data-quality qualifications | 2,633 |

These results demonstrate that the experimental methods can process historical administrative observations and generate candidates for further investigation.

They do not demonstrate that the model reliably detects genuine financial inclusion anomalies.

The experiment reports no adjudicated anomaly labels and therefore provides no independently measured precision, recall or false-alarm rate. It also identifies substantial disagreement between detector methods and sensitivity of some flags to small changes in the observations.

The experiment's own status is `experimental_insufficient_labeled_history`.

The high temporal flag rate should therefore be treated as a reason for further investigation and validation, not as evidence of successful anomaly detection.

## 3.10 Supporting Infrastructure, Authentication and Testing

### Authentication

The application uses Streamlit's native authentication interface to support Google sign-in.

Authentication configuration is handled in `auth.py`, with an example configuration provided in `.streamlit/secrets.toml.example`.

The application checks for the required Google credentials and gates dashboard access on an authenticated Streamlit user when authentication is configured.

However, the inspected application code does not enforce the `access.allowed_emails` setting shown in the example secrets file. Role-based access control and verified email-allowlist enforcement should therefore not be claimed as implemented.

### Secrets and database configuration

MongoDB credentials are supplied through environment configuration.

The project supports loading credentials from environment variables, with local scraper development able to use a `.env` file. GitHub Actions receives the required MongoDB connection configuration through repository secrets.

This keeps database credentials separate from the main application source code.

The repository includes an example secrets configuration, but actual credentials are not part of the documentation or source code.

### Testing

The project uses pytest for automated testing and Streamlit AppTest for application-page testing.

The test suite covers areas such as:

- FinScope processing and data validation.
- MongoDB data normalization and health checks.
- Scraper behavior and extraction safeguards.
- Intelligence-model calculations and evidence assessment.
- FinScope and NBR contextualization.
- Streamlit page loading and navigation.

Some tests use synthetic observations, local processed files and monkeypatching to isolate specific behaviors.

These tests provide useful coverage of individual components. However, they do not establish that the entire live workflow—from BNR browser collection through MongoDB storage to the hosted dashboard—has been successfully validated end to end.

No GitHub Actions workflow for running the full test suite or enforcing a test-coverage threshold was identified.

### Deployment and automation

The documented local application command is:

`streamlit run app.py`

The repository includes Streamlit configuration and authentication examples, while GitHub Actions handles BNR collection.

However, no Dockerfile, hosted-platform deployment manifest or application deployment workflow was identified in the inspected repository.

The hosting platform and automated application-update process are therefore outside the capabilities established by the current repository configuration.

## 3.11 Development Constraints and Implementation Status

The project was developed within a limited period leading up to the submission deadline. Development efforts therefore prioritized establishing the core analytical infrastructure, processing the available survey data, building the interactive dashboard, implementing BNR data collection and storage, and creating an initial foundation for the experimental intelligence package.

Not all intended capabilities could be fully implemented, integrated and validated within the available timeframe.

This context is particularly relevant to the intelligence component. Version 0.4.4 establishes an experimental foundation for statistical anomaly investigation and evidence-based contextualization, but further work is required before its outputs can support a reliable operational monitoring or alerting process.

The current implementation status is summarized below.

| Component | Implemented capabilities | Remaining limitations |
|---|---|---|
| FinScope dashboard | Six analytical pages, indicator registry, processed-data loading, geographical visualization and methodology information | Some existing breakdown files do not contain the complete eight-indicator coverage supported by the rebuild script |
| BNR collection | Browser automation, filter interaction, pagination, validation, MongoDB storage and weekly scheduled collection | Depends on source availability, dashboard behavior and the quality of information exposed by BNR |
| BNR dashboard integration | FinScope, Combined and NBR Supply modes with selected administrative-data visualizations | Experimental anomaly detectors are not fully integrated into an interactive review interface |
| Intelligence package | Version 0.4.4 statistical detectors, evidence assessment, contextualization and report generation | No independent anomaly labels, validated detection performance or operational forecasting |
| Human review | Review-queue structure and preservation of reviewer-entered fields | No established feedback dataset or validated model-learning process |
| Authentication | Google sign-in through Streamlit when configured | No verified email allowlist enforcement or role-based access control |
| Deployment | Documented local application execution and automated data-collection workflows | Application hosting and automated deployment are not established in the inspected repository |
| Testing | Focused automated tests and Streamlit page smoke tests | No test CI workflow or demonstrated full live end-to-end validation |

These limitations should be understood in the context of the project's development stage, the available data and the limited implementation period. They should not be interpreted as evidence that all proposed capabilities are technically unattainable.

At the same time, development constraints do not remove the need to distinguish implemented functionality from experimental or planned features.

## 3.12 Overall System Limitations

The current system has several technical, analytical and operational limitations.

**Survey-data limitations**

FinScope Rwanda 2024 describes the survey period rather than continuously updated national conditions. In addition, the available data does not provide the complete survey-design information required to calculate formal design-based confidence intervals. The margins of error displayed by the application are indicative simple-random-sample calculations, with an optional design-effect multiplier, and should not be interpreted as complete design-based uncertainty estimates.

The currently available processed breakdown files also require further validation to ensure that all eight registered indicators are present wherever the application claims they are available.

**Administrative-data limitations**

BNR administrative observations have their own definitions, populations and reporting conventions. They cannot automatically be treated as equivalent to household survey measures.

The project has documented cases where administrative national KPIs and district tables do not reconcile. For example, an Agents discrepancy was identified, but its underlying cause was not established. Such observations require source-level clarification before they can support stronger conclusions.

**Collection limitations**

The scraper depends on the BNR dashboard's structure, filters, displayed content and availability. Website changes may affect extraction. Collection safeguards reduce the risk of storing incomplete observations but cannot guarantee the completeness or correctness of the original source.

**Historical-data limitations**

The documented intelligence experiment used five irregular reporting dates. This is insufficient to establish reliable long-term temporal behavior or support a strong chronological validation design.

**Intelligence-model limitations**

The experimental detectors have not been evaluated against independently adjudicated anomaly labels. Their precision, recall and false-alarm rates are unknown. The model should therefore be treated as a candidate-generation and investigation aid rather than a validated anomaly-detection system.

**Integration limitations**

Some FinScope-aware contextualization is available in the Combined National Overview, but not all administrative indicators have comparable survey equivalents. The experimental temporal and peer detectors are not established as interactive dashboard features.

**Operational limitations**

The application requires the relevant local processed data and external MongoDB access for its respective views. The repository does not establish an application hosting or deployment pipeline.

**Access-control limitations**

Google authentication is implemented, but role-based access and verified email-allowlist enforcement are not established in the inspected code.

**Reproducibility limitations**

The original FinScope microdata and historical BNR database observations are not fully contained in a tracked repository checkout. Reproducing the complete analytical and collection workflows requires the relevant external inputs, database configuration and credentials.

## 3.13 Future Development Roadmap

Future development should prioritize completing and validating the existing architecture before introducing more advanced analytical capabilities.

### Short-term priorities: completion and stabilization

- Rebuild and validate the FinScope urban/rural and population-group outputs to ensure that the delivered CSV files match the eight-indicator registry.
- Continue weekly BNR collection while preserving reporting dates, collection timestamps, filter combinations, run statuses and repeated-content information.
- Resolve inconsistencies between the dashboard documentation and current implementation, including the default NBR dashboard mode and descriptions of the experimental anomaly panel.
- Add automated test execution to GitHub Actions.
- Document the external requirements for MongoDB, survey microdata, secrets and application execution.
- Confirm whether an email allowlist is required and implement it in the application if necessary.

### Medium-term priorities: evidence quality and integration

- Build a longer sequence of quality-suitable weekly observations for consistent administrative series.
- Obtain independent human assessments of selected anomaly candidates.
- Keep reviewer decisions separate from model-generated results.
- Evaluate the detectors chronologically against reviewed observations before reporting detection performance.
- Review administrative source definitions and resolve unexplained differences between national KPIs and district tables.
- Expand FinScope and BNR indicator mappings only where their populations, periods, denominators and units are sufficiently comparable.
- Consider integrating anomaly candidates into the dashboard only after their usefulness and reliability have been evaluated.

The experimental notes propose at least twelve consecutive quality-suitable weekly periods for a series, followed by at least four later chronological holdout periods before reassessing temporal detection. These are proposed evaluation prerequisites, not guarantees of statistical reliability.

### Long-term possibilities: advanced analytical capabilities

Once sufficient historical data and independent validation evidence are available, the architecture could support additional capabilities, including:

- Explainable anomaly-review and alert-triage interfaces.
- More comprehensive historical monitoring summaries.
- Learning from independently verified reviewer outcomes, where appropriate.
- Forecasting selected administrative indicators, provided the data history and validation design justify it.
- More advanced cross-indicator analysis where the underlying measures and comparison scopes are demonstrably compatible.
- Better operational monitoring, access control and deployment management.

These are potential future enhancements, not capabilities of the current submitted version or established implementation commitments.

The guiding principle for future development should remain the same as the project's original objective: analytical complexity should only be introduced when the available evidence can support it and when the resulting functionality provides meaningful value to the intended users.

## 3.14 Important Source Files and Implementation Evidence

The following repository files provide the principal implementation evidence for this section.

| Area | Important files |
|---|---|
| Application entry and authentication | `app.py`, `auth.py`, `.streamlit/config.toml`, `.streamlit/secrets.toml.example` |
| FinScope processing and indicators | `build_processed_data.py`, `data.py`, `indicators.py`, `validation.py` |
| Exploratory analysis | `notebooks/01_exploratory_data_analysis.ipynb`, `notebooks/02_financial_inclusion_indicators.ipynb`, `notebooks/03_population_group_analysis.ipynb`, `notebooks/04_extended_financial_inclusion_indicators.ipynb` |
| Survey source materials | `FinScope2024Rwanda.dta`, FinScope final report and questionnaire |
| Geographical visualization | `geoBoundaries-RWA-ADM2.geojson`, `district_explorer.py` |
| Dashboard pages | `national_overview.py`, `district_explorer.py`, `population_groups.py`, `priority_explorer.py`, `policy_alignment.py`, `methodology.py` |
| BNR collection | `nbr_engine.py`, `nbr_pages.json` |
| BNR automation | `nbr-current.yml`, `nbr-backup.yml`, `nbr-backfill.yml` |
| MongoDB normalization and data health | `mongodb_district_explorer.py`, `mongodb_data_health.py` |
| Intelligence model | `experiment.py`, `assessment.py`, `contextualization.py`, `indicator_mapping.py`, `review.py` |
| Model experiment documentation | `nbr-adaptive-intelligence-experiment.md` |
| Automated testing | `tests/`, particularly `test_nbr_anomaly_experiment.py`, `test_nbr_contextualization.py` and `test_pages_smoke.py` |


## 4. Dashboard Pages and Analysis Mode

### 4.1 Dashboard Overview

The Rwanda Financial Inclusion Gap Explorer provides six main dashboard pages. Each page addresses a different aspect of financial inclusion analysis, allowing users to move from national-level observations to geographical comparisons, population-group differences, exploratory district screening, policy context, and methodological explanations.

The dashboard is designed for interactive exploration rather than simply presenting static reports. Users can select indicators, compare geographical areas and population groups, examine relative differences, and investigate the context behind observed results.

The six implemented pages are:

1. National Overview
2. District Explorer
3. Population Groups
4. Priority Explorer
5. Policy Alignment
6. Methodology and Sources

### 4.2 National Overview

The National Overview shows the national financial-inclusion picture and helps explain why a strong national headline does not necessarily mean every district or community has the same experience.

The page presents core FinScope indicators, urban-rural comparisons, district-level variation, saving and resilience patterns, and reported barriers to bank-account ownership. Weighted population figures associated with reported barriers are not counts of potential beneficiaries.

Users can use these summaries to identify differences worth exploring further. In Combined mode, eligible NBR administrative observations may provide additional context, but they remain distinct from survey estimates.

The page therefore serves as the starting point for exploring the country's financial inclusion landscape before moving into more detailed geographical or demographic analysis.

### 4.3 District Explorer

The District Explorer enables users to investigate geographical differences across Rwanda's 30 districts and see how a selected district compares with the national estimate.

The map, indicator-specific ranking, district details, and available NBR supply information help reveal local patterns that can be hidden by national averages.

The page provides:
- An interactive district-level map.
- An indicator selection control.
- Indicator-specific comparisons and a district summary table.
- Comparisons against national survey estimates.
- Indicator descriptions and interpretation.
- Map highlighting, hover information, and display options.

For each indicator, higher or lower values can have different meanings. The page explains the indicator's direction so users can interpret the comparison rather than treat every high value as good or every district rank as an overall inclusion score.

These descriptive comparisons can point to areas for further investigation, but they do not explain why a gap exists or establish that a difference is statistically significant.

### 4.4 Population Groups

The Population Groups page compares available financial-inclusion indicators across demographic and residential categories at the national group level.

Users can explore indicators across:
- Gender.
- Age groups.
- Education levels.
- Urban and rural residence.

The page presents percentage-based comparisons using the available processed population-group datasets. Users can select an indicator and examine how its values differ between the relevant groups.

The comparisons help show how reported access, service use, and resilience vary between groups. They are descriptive summaries, not district-by-group estimates or evidence of what caused a difference. The displayed margins are illustrative guides, not formal significance tests.

The availability of indicators depends on the columns present in the corresponding processed datasets. Consequently, not every registered indicator is necessarily available across every population-group breakdown.

### 4.5 Priority Explorer

The Priority Explorer helps screen for districts with relatively larger access and resilience gaps compared with national survey estimates.

The fixed baseline equally combines directional gaps for four indicators: bank-account ownership, registered mobile-money use, adults who do not save, and emergency funds. The page shows the baseline score and rank, the indicators contributing to a score, and how selected what-if scenarios may change district comparisons.

It also shows how stable rankings are across alternative indicator combinations and provides illustrative uncertainty context.

Users can explore the Top 10, Top 15, or all districts and examine whether the resulting rankings remain stable or are sensitive to indicator selection.

Scores are relative comparison points—not percentages, probabilities, counts of people in need, or funding recommendations. They help users decide what may warrant closer investigation; they do not establish causes or investment reach.

### 4.6 Policy Alignment

The Policy Alignment page connects selected findings with national priorities and published policy references, and offers examples of questions stakeholders may investigate.

It helps users consider the relevance of the evidence without claiming that the survey establishes causes, predicts demand, or decides which intervention or investment should be chosen. Local validation is needed before acting on a gap.

Its role is to provide context for interpreting the evidence presented elsewhere in the dashboard.

### 4.7 Methodology and Sources

The Methodology and Sources page explains what the dashboard's indicators mean, how its estimates and comparisons are produced, and where the information originates.

It covers:
- Survey weighting and the calculation of weighted estimates.
- Indicator definitions and their corresponding survey variables.
- Uncertainty and margin-of-error considerations.
- Data-quality checks.
- Descriptions of the underlying data sources.
- Methodological assumptions and analytical limitations.

It also sets out uncertainty and limitations, helping users understand what conclusions the results can support and where caution is needed.

### 4.8 Analysis Mode

The dashboard includes an Analysis Mode selector in the sidebar. This feature allows users to choose the data perspective through which they explore financial inclusion.

Analysis Mode is implemented as a source-selection and contextualization mechanism. It does not activate an artificial intelligence system or automatically change the underlying FinScope survey calculations.

Three modes are available:

**Combined Mode**

Combined mode presents FinScope survey findings alongside relevant NBR administrative observations.

FinScope remains the primary source for understanding individual financial inclusion, while NBR observations provide additional context about selected financial services and their administrative or institutional footprint.

The two sources retain their separate definitions, units, and interpretations. NBR observations are not substituted for FinScope estimates or merged into the survey calculations.

**FinScope Mode**

FinScope mode focuses exclusively on the processed FinScope Rwanda 2024 survey datasets.

NBR contextual information is suppressed, allowing users to examine survey-based indicators, geographical differences, demographic comparisons, and related exploratory analysis without the additional administrative-data layer.

**NBR Supply Mode**

NBR Supply mode presents the available administrative observations collected from the National Bank of Rwanda's Financial Inclusion Dashboard.

Depending on the page and available observations, users can explore administrative indicators, district-level information, service-supply patterns, and observed changes across reporting periods.

These observations are retrieved from the project's MongoDB data layer and presented separately from the FinScope survey estimates.

### 4.9 How Analysis Mode Affects the Dashboard

The selected mode is maintained through Streamlit session state and is checked by the relevant dashboard page modules when rendering their content.

The mode determines which data-source views and contextual components are displayed.

In practical terms:

- Combined mode presents survey findings with relevant NBR context.
- FinScope mode presents survey-based analysis without NBR contextual information.
- NBR Supply mode displays the available administrative-data views.

The National Overview, District Explorer, Population Groups, and Priority Explorer contain mode-dependent rendering logic. The selected mode can therefore change the information and interpretation presented on these pages.

However, changing modes does not modify the original FinScope survey observations, indicator definitions, or weighted estimates.

The sidebar also provides a **Refresh NBR Observations** control. This clears relevant cached NBR results so that the application can retrieve the available administrative observations again. The availability of refreshed information depends on the external MongoDB data source and the observations already collected.

### 4.10 Relationship Between Analysis Mode and the Experimental Intelligence Package

The project includes a separate experimental NBR intelligence package. It contains statistical procedures for examining temporal changes, comparing observations across districts, assessing evidence quality, and contextualizing selected administrative indicators.

These procedures are experimental and should not be interpreted as a validated production forecasting or anomaly-detection system.

Analysis Mode itself is not a model execution switch. Selecting Combined, FinScope, or NBR Supply primarily determines which data-source views and contextualization components are displayed.

Some NBR contextualization functionality is used by the dashboard, while the more extensive temporal and peer-comparison experiments are primarily part of the separate analytical workflow.

The distinction is important: the dashboard's interactive source-selection functionality and the experimental statistical intelligence package are related parts of the project, but they are not the same feature.

### 4.11 User Navigation and Interaction

When users open the application, they are presented with the Streamlit dashboard, its sidebar navigation, the Analysis Mode selector, and the National Overview page as the default starting point.

Users can navigate between the six pages through the sidebar and change the selected data perspective without leaving the application.

The dashboard's interactive controls allow users to select indicators, examine district distributions, compare population groups, inspect priority rankings, and explore available administrative observations.

Access to the application is subject to the configured authentication checks.

Overall, the dashboard combines geographical exploration, demographic comparison, exploratory priority screening, policy contextualization, and methodological transparency within a single interface.

## 5. Vision, Feasibility and the Path Towards a More Intelligent Financial Inclusion Platform

### 5.1 Beyond Presenting Financial Inclusion Statistics

The Rwanda Financial Inclusion Gap Explorer is intended to become more than an interactive presentation of financial inclusion statistics. Its broader ambition is to establish a practical evidence-exploration and monitoring platform that helps stakeholders understand where financial inclusion gaps exist, how those gaps differ across population groups and geographical areas, and how the available evidence changes over time,as well as meeting the the remaining percentage of financial exclusion.

Financial inclusion is not simply a question of whether financial services exist within a country. It also concerns who can access them, who actually uses them, which services remain unavailable or inconvenient, and what circumstances may prevent different population groups from benefiting from them.

A strong national financial inclusion figure can therefore coexist with important differences between districts, demographic groups, and service environments. Understanding these differences requires more than a single national percentage or an occasional survey report.

The system seeks to make these differences easier to investigate by bringing together complementary forms of evidence:

- Household survey information that describes individuals' access to and use of financial services.
- Administrative observations that provide additional information about financial institutions, service channels, and geographical service distribution.
- Historical observations that make it possible to examine changes across reporting periods.
- Transparent analytical procedures that help identify unusual patterns, relative gaps, and areas that deserve further investigation.

The ultimate ambition is to move from simply asking *what is the level of financial inclusion?* towards asking more useful questions:

- Which districts show relatively weaker financial inclusion outcomes?
- Which population groups experience different levels of access and use?
- Where does the administrative service footprint appear limited relative to the observed financial inclusion situation?
- Are selected indicators changing over time?
- Which observed differences deserve further investigation?
- How strong and reliable is the evidence supporting each observation?

The platform is intended to make these questions easier to explore without presenting statistical observations as definitive explanations or policy decisions.

### 5.2 Why the Proposed System Is Feasible

The proposed direction is technically feasible because the project already has several of its essential foundations implemented.

Rather than beginning with a theoretical machine-learning concept, the project has established working components that can be progressively improved and integrated.

**First, the survey analysis foundation already exists.**

The FinScope Rwanda 2024 processing pipeline produces structured datasets from which national, district, urban-rural, and population-group comparisons can be explored. Indicator definitions are centralized, survey weights are applied, and the dashboard provides interactive visualizations of the resulting estimates.

This provides an established analytical baseline for understanding financial inclusion from the perspective of individuals and households.

**Second, an administrative data collection mechanism has been implemented.**

The BNR Financial Inclusion Dashboard is accessed through Playwright browser automation. The scraper interacts with dashboard controls, selects available filters, extracts supported indicators and paginated tables, and performs validation before storing observations.

MongoDB provides historical storage for collected observations and their associated metadata. GitHub Actions supports scheduled collection workflows, while a separate manual workflow supports historical backfilling.

This establishes the foundation for collecting administrative observations repeatedly instead of relying exclusively on a single downloaded dataset.

**Third, the project already has an experimental statistical intelligence foundation.**

The NBR intelligence package contains temporal comparison procedures, cross-sectional district comparisons, evidence-quality assessment, contextualization logic, and candidate review mechanisms.

These components demonstrate a practical starting point for more advanced analysis. They are not yet a validated production model, but they provide an existing framework that can be tested and improved as more suitable historical observations become available.

**Finally, the application already provides an interactive environment for presenting the evidence.**

Streamlit, Plotly, the existing page structure, and the Analysis Mode selector provide a foundation for gradually integrating improved administrative observations and validated analytical outputs into the user experience.

Consequently, the proposed development path is an extension of an existing system rather than the construction of an entirely new platform.

### 5.3 Strengthening Administrative Data Collection

One of the most important areas for further development is the reliability, continuity, and coverage of administrative data collection.

The existing Playwright scraper provides a foundation for interacting with the BNR dashboard and extracting supported information. However, a reliable monitoring system requires more than successful extraction during an individual run.

Several improvements remain important.

**Collection continuity and historical depth**

The current automated workflows establish weekly collection, but the usefulness of historical comparisons depends on maintaining a sufficiently long sequence of quality-suitable observations.

More consistent historical coverage would make it possible to distinguish isolated changes from recurring patterns and examine how selected indicators behave across different reporting periods.

The system should continue preserving reporting dates, collection timestamps, filter combinations, run identifiers, and extraction status so that historical observations can be interpreted correctly.

**Coverage of dashboard indicators and filters**

The scraper currently supports configured dashboard pages and their available filters. Further work is needed to assess whether all relevant service categories, geographical levels, reporting periods, and filter combinations can be collected reliably.


**Resilience to changes in the source dashboard**

Browser-based extraction depends on the structure and behaviour of the external dashboard. Changes to page layouts, selectors, filter options, pagination, or displayed metrics can affect extraction.

Future improvements should include stronger source-change detection, automated extraction health checks, clearer failure reporting, and procedures for reviewing unexpected changes before they affect stored observations.

**Data quality and provenance**

The existing validation mechanisms provide an important starting point. Further strengthening should focus on monitoring missing observations, incomplete reporting periods, duplicate or repeated content, inconsistent district coverage, unexpected value changes, and changes in indicator definitions.

A successful collection run should not automatically be interpreted as evidence that the source information is complete, current, or comparable with previous observations.

It is also important to distinguish the project's weekly collection schedule from the BNR dashboard's own update schedule. Repeatedly collecting a dashboard does not guarantee that every underlying indicator has been updated between collection dates.

The long-term objective is therefore not merely to collect more data, but to establish a dependable, traceable, and quality-controlled administrative observation history.

### 5.4 Improving the Experimental Intelligence Model

The experimental NBR intelligence package represents an important direction for extending the platform beyond descriptive visualization.

Its purpose is to examine administrative observations systematically, identify patterns that may deserve attention, and provide evidence that analysts can investigate.

The current implementation includes temporal rate comparisons using robust statistical techniques, cross-sectional district comparisons, evidence-quality assessments, and contextualization procedures.

However, these methods remain experimental. Their outputs should be treated as candidates for investigation rather than confirmed anomalies or predictions.

Several improvements are necessary before the intelligence component can be considered sufficiently reliable for operational use.

**Building a stronger historical reference**

Temporal detection depends on having enough comparable historical observations to establish meaningful reference patterns.

The proposed development direction is to accumulate at least 12 consecutive quality-suitable weekly periods and reserve at least four later chronological periods for holdout evaluation. These are proposed minimum evaluation targets, not guarantees that the model will become reliable once they are reached.

The additional history should help assess whether detected changes are unusual relative to previous observations rather than simply reflecting limited or irregular historical coverage.

**Independent review and labelled evidence**

The current experiments do not have an established set of independently adjudicated anomaly labels.

This makes it difficult to determine how many flagged observations represent meaningful changes, how many are false alarms, and how many relevant changes the detectors fail to identify.

A structured human-review process is therefore an important next step. Analysts should be able to inspect flagged observations, examine their supporting evidence, and record whether a candidate is confirmed, rejected, or remains inconclusive, together with an explanation.

These review decisions could gradually provide the reference information needed to evaluate and improve the detection procedures.

**Chronological model evaluation**

Future evaluation should preserve the order of observations. Historical data should be used to establish reference patterns, while later observations should be reserved for testing.

This would help assess how the detectors behave when presented with information they have not previously encountered.

Evaluation should consider more than the number of flags produced. It should examine stability, sensitivity to small changes in input data, false-positive behaviour where labels become available, abstention rates, and the consistency of results across indicators and districts.

**Improving evidence assessment and explanations**

An important feature of the proposed intelligence system is its emphasis on explainability.

A flagged observation should not appear as an unexplained warning. It should be accompanied by information about the indicator, geographical area, reporting period, comparison baseline, observed change, applicable method, and evidence limitations.

The system should also be able to abstain when historical coverage, data quality, or comparison conditions are inadequate.

Evidence sufficiency should not be confused with the probability that an observation is anomalous or with proven model accuracy.

The objective is to build an analytical assistant that helps users understand why an observation deserves attention, while preserving the distinction between statistical evidence and human interpretation.

### 5.5 Completing the Combined Financial Inclusion View

One of the most valuable opportunities for the project is to develop a more meaningful combined view of FinScope survey evidence and BNR administrative observations.

The two sources offer complementary perspectives, but they do not measure exactly the same things.

FinScope provides information about individuals and households, including financial access, service use, saving behaviour, borrowing, and reported barriers.

BNR administrative observations provide information about selected financial-sector activities and service channels, depending on the indicators available through its dashboard.

Combining these sources can provide a richer analytical perspective, but it requires careful treatment of their differences.

**Establishing comparable indicators**

The first requirement is a clear mapping between relevant FinScope indicators and BNR administrative observations.

For example, bank account ownership in FinScope should not automatically be treated as equivalent to the number of active bank accounts reported administratively. The former describes individuals reporting account ownership, while the latter may represent administrative account counts with different definitions and possible multiple accounts per person.

Similarly, the presence of financial service agents or branches does not directly establish that individuals use those services or can conveniently access them.

Future development should therefore expand the existing indicator mapping registry and explicitly classify relationships as directly comparable, contextual, uncertain proxy, unsuitable, or unavailable.

**Aligning geographical and population definitions**

A combined analysis also requires careful attention to geographical coverage, population definitions, and reporting periods.

District observations should only be compared where geographical definitions and coverage are sufficiently consistent. Administrative age categories should not automatically be equated with survey age groups, and institutional categories should not be assumed to match survey definitions.

Where meaningful alignment is not possible, the application should present the sources separately rather than force an inaccurate comparison.

**Introducing temporal context**

FinScope 2024 provides a survey-based reference for its survey period, while BNR observations can be collected repeatedly.

This creates an opportunity to examine administrative changes around the survey baseline and investigate whether selected service indicators appear to change over time.

However, repeated administrative observations do not automatically demonstrate that household financial inclusion has increased or decreased. Changes in administrative counts may reflect account activity, reporting practices, institutional coverage, or other factors.

The combined view should therefore communicate the date and nature of each observation and avoid implying that administrative movements directly represent changes in individual financial inclusion.

**Connecting service availability with practical access**

An additional opportunity is to investigate the relationship between the availability of financial services and the financial inclusion outcomes observed in different districts.

For example, a district may contain financial institutions or service channels while some residents still face substantial practical difficulties reaching or using them. A person may technically be financially included but still need to travel a considerable distance to access a bank branch.

This illustrates why financial inclusion, service availability, practical accessibility, and actual usage should be examined as related but distinct concepts.

The current data does not directly measure individual travel times or establish that service availability causes a particular inclusion outcome. Future work could investigate whether additional geographical, transport, infrastructure, or population-density information would support more meaningful accessibility analysis.

**Developing a genuinely integrated user experience**

The existing Combined mode already provides a starting point for displaying survey findings alongside administrative context.

However, a more complete combined experience requires stronger indicator mappings, consistent geographical and temporal references, clearer explanations of source differences, and more carefully designed cross-source comparisons.

The goal should not be to merge every available number into a single score. It should be to help users understand how different sources complement one another, where their findings are consistent, where they differ, and where the available evidence is insufficient to draw a conclusion.

### 5.6 A Progressive and Achievable Development Path

The project should evolve through a sequence of improvements, with each stage building on capabilities that already exist.

**Stage 1: Strengthen the existing foundation**

- Maintain reliable scheduled administrative data collection.
- Expand and validate supported BNR dashboard coverage.
- Improve extraction monitoring and historical data quality checks.
- Rebuild and validate processed survey breakdowns where indicator coverage is incomplete.
- Improve documentation of data sources, definitions, and external dependencies.

**Stage 2: Establish a dependable analytical history**

- Accumulate sufficiently consistent historical observations.
- Identify indicators and geographical comparisons suitable for temporal analysis.
- Introduce independent human review of experimental findings.
- Establish chronological holdout evaluation.
- Assess detector stability, false alarms, abstentions, and sensitivity.

**Stage 3: Develop a stronger combined analytical experience**

- Expand and validate the FinScope-to-BNR indicator mapping.
- Improve alignment of geographical units, population definitions, and reporting periods.
- Introduce clearly qualified cross-source comparisons.
- Present contextual administrative trends alongside relevant survey findings.
- Communicate differences between access, availability, and actual usage.

**Stage 4: Integrate validated intelligence into the dashboard**

- Introduce reviewed analytical candidates into appropriate dashboard views.
- Provide explanations, evidence references, comparison baselines, and limitations.
- Allow users to distinguish confirmed observations, unverified candidates, and insufficient evidence.
- Establish procedures for monitoring the analytical components as new data becomes available.

More advanced forecasting and automated alerting could be considered later, but only after sufficient historical evidence and independent evaluation justify their use.

### 5.7 Expected Long-Term Value

When these improvements are progressively implemented, the Rwanda Financial Inclusion Gap Explorer could provide several important benefits.

For policymakers and government analysts, it could make geographical and population-level differences easier to identify and investigate.

For financial institutions and service providers, it could provide a clearer picture of how administrative service coverage relates to observed financial inclusion patterns.

For researchers and development practitioners, it could offer an accessible environment for examining survey findings alongside complementary administrative evidence.

For district-level stakeholders, it could help identify questions requiring further local investigation rather than relying exclusively on national averages.

Most importantly, the system could encourage a more continuous and evidence-driven approach to financial inclusion analysis. Instead of treating each survey publication as an isolated analytical event, stakeholders could use the survey as a detailed reference point and complement it with regularly collected administrative observations.

### 5.8 Overall Vision

The long-term vision is to develop a transparent, explainable, and progressively improving financial inclusion intelligence platform for Rwanda.

Its value will not come from the number of charts, the complexity of its algorithms, or the appearance of artificial intelligence. It will come from the quality of the evidence it brings together, the reliability of its data collection, the defensibility of its analytical methods, and its ability to help users ask better questions.

The project already demonstrates that its core components can work together: survey processing, district and population-group analysis, automated administrative data collection, historical storage, experimental statistical assessment, and interactive visualization.

The remaining challenge is to strengthen these components, establish the evidence needed to validate the experimental methods, and develop a more complete combined analytical experience.

The intended outcome is not a system that replaces researchers, policymakers, or financial-sector experts. It is a system that equips them with clearer evidence, more useful comparisons, and a stronger basis for deciding where further investigation and intervention may be warranted.

## 6. Conclusion

The Rwanda Financial Inclusion Gap Explorer represents an effort to make financial inclusion evidence more accessible, interpretable, and useful for decision-making in Rwanda. It addresses an important analytical challenge: national financial inclusion statistics provide an essential overview, but they do not always reveal the geographical differences, population-level disparities, and practical service-access challenges that exist beneath the national picture.

By transforming FinScope Rwanda 2024 survey data into interactive national, district, and population-group analyses, the platform provides users with a structured way to explore these differences. Its Priority Explorer introduces an additional approach to identifying districts with relatively larger gaps against national benchmarks, while the Policy Alignment and Methodology pages help connect the findings to broader development priorities and explain the assumptions behind the analysis.

The integration of administrative observations from the National Bank of Rwanda introduces another dimension to the project. Through browser automation, scheduled collection workflows, and MongoDB historical storage, the system establishes a foundation for observing selected financial-sector indicators across reporting periods. These observations complement the household survey evidence without replacing it or treating fundamentally different measurements as equivalent.

The project also establishes an experimental statistical intelligence foundation for examining administrative changes, comparing districts, and assessing the quality of available evidence. Although these analytical methods require further historical data, independent review, and rigorous evaluation before they can support operational conclusions, they demonstrate a feasible direction for extending the platform beyond conventional descriptive reporting.

Nevertheless, the current implementation has important areas for improvement. Administrative data collection requires continued strengthening, the experimental intelligence methods require proper validation, and the combined analytical experience needs more comprehensive indicator alignment and contextual integration. These are important development priorities rather than reasons to disregard the foundation already established.

Ultimately, the ambition of the Rwanda Financial Inclusion Gap Explorer is to support a more continuous, transparent, and evidence-driven understanding of financial inclusion in Rwanda. It is not intended to replace official statistics, financial-sector expertise, or policy judgement. Rather, it seeks to equip researchers, policymakers, financial institutions, and development practitioners with an accessible environment in which they can explore evidence, identify differences, investigate emerging patterns, and determine where further attention may be needed.

The project therefore represents both a functioning analytical dashboard and a foundation for a broader financial inclusion intelligence platform: one that can progressively become more comprehensive as data collection improves, historical evidence grows, analytical methods are validated, and complementary sources are brought together responsibly.