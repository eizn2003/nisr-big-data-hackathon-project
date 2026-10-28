import os
import warnings
import numpy as np
import pandas as pd
import polars as pl
import svy

# Suppress warnings
warnings.simplefilter(action='ignore', category=FutureWarning)
warnings.filterwarnings("ignore", message=".*CategoricalConversionWarning.*")

# ==========================================
# 1. SETUP PATHS AND LOAD DATASET 
# ==========================================
DTA_FILE_PATH = "data/datasets/rwanda_finscope_2024.dta" 

if not os.path.exists(DTA_FILE_PATH):
    raise FileNotFoundError(f"Missing absolute data asset: {DTA_FILE_PATH}")

print("Loading Stata dataset into memory cleanly...")
# SET convert_categoricals=False to read codes directly and prevent pyarrow crash
df_pandas = pd.read_stata(DTA_FILE_PATH, convert_categoricals=False)

# ==========================================
# 2. NISR SURVEY VARIABLE CONFIGURATION
# ==========================================
INDICATOR_COL = 'e1'      # Your financial inclusion target variable code (e.g., 'e1')
WEIGHT_COL    = 'pop_wt'  # Individual population weights column name
DISTRICT_COL  = 'a2'      # District codes or identifiers ('a2')
CLUSTER_COL   = 'key'     # Household identifier; this dataset has no separate PSU column

# Read only the district column with Stata labels so the report shows names, not codes.
district_names = pd.read_stata(
    DTA_FILE_PATH,
    columns=[DISTRICT_COL],
    convert_categoricals=True
)[DISTRICT_COL]
df_pandas[DISTRICT_COL] = district_names

# --- STRICT CLEANING TO AVOID PYARROW OBJECT CONFLICTS ---
# Drop rows where critical weights, districts, or clusters are blank
df_pandas = df_pandas.dropna(subset=[WEIGHT_COL, CLUSTER_COL, DISTRICT_COL]).copy()

# Force location columns to be perfectly clean text strings (replaces floating NaN values)
df_pandas[DISTRICT_COL] = df_pandas[DISTRICT_COL].astype(str).str.strip()
df_pandas[CLUSTER_COL]  = df_pandas[CLUSTER_COL].astype(str).str.strip()

# Coerce your specific indicator column into a completely clean 1.0 or 0.0 float
# If it's a numeric column, it fills empty rows with 0. If it's text, it looks for positive flags.
if df_pandas[INDICATOR_COL].dtype == 'object':
    df_pandas['target_binary'] = np.where(df_pandas[INDICATOR_COL].astype(str).str.lower().str.contains('yes|user|have|1'), 1.0, 0.0)
else:
    # If the database stored it as numbers (e.g. 1 for Yes, 2 for No)
    # Convert standard Stata '1' values to 1.0, and anything else (like 2 or NaN) to 0.0
    df_pandas['target_binary'] = np.where(df_pandas[INDICATOR_COL] == 1, 1.0, 0.0)

# ==========================================
# 3. SAFE CONVERSION TO POLARS
# ==========================================
# We only select the columns we need to prevent other uncleaned columns from breaking the script
keep_cols = [DISTRICT_COL, CLUSTER_COL, WEIGHT_COL, 'target_binary']
df_clean_pandas = df_pandas[keep_cols].copy()

# Now it converts smoothly without any type errors!
df = pl.from_pandas(df_clean_pandas)

# ==========================================
# 4. RUN WEIGHTED ESTIMATION PER DISTRICT
# ==========================================
print(f"\n--- Running Step 3.2 Estimations for: '{INDICATOR_COL}' ---")

# The dataset's a6 field is Urban_Rural, not a PSU. Use its household ID as the
# available PSU; this treats sampled households as independent sampling units.
design = svy.Design(psu=CLUSTER_COL, wgt=WEIGHT_COL)
sample = svy.Sample(data=df, design=design)

# Calculate indicators grouped cleanly by district location
estimation_results = sample.estimation.mean(['target_binary'], by=DISTRICT_COL)
results_df = pd.DataFrame(estimation_results.to_polars().to_dicts())

# Formatting output metrics matrix fields
results_df = results_df.rename(columns={
    'est': 'Point Estimate (p_hat)',
    'se': 'Std Error',
    'lci': '95% CI Lower',
    'uci': '95% CI Upper'
})

results_df['Percentage (%)'] = round(results_df['Point Estimate (p_hat)'] * 100, 2)
results_df['95% CI Lower (%)'] = round(results_df['95% CI Lower'] * 100, 2)
results_df['95% CI Upper (%)'] = round(results_df['95% CI Upper'] * 100, 2)

# Pull unweighted respondent footprints from our cleaned pandas frame
counts = df_clean_pandas.groupby(DISTRICT_COL).size().reset_index(name='Unweighted Sample Count')
final_report_df = pd.merge(counts, results_df, on=DISTRICT_COL)

# ==========================================
# 5. VIEW AND EXPORT COMPILED RESULTS
# ==========================================
print("\nFinal Step 3.2 District Summary Matrix:")
print(final_report_df[[DISTRICT_COL, 'Unweighted Sample Count', 'Percentage (%)', '95% CI Lower (%)', '95% CI Upper (%)']].to_string(index=False))

# Export to csv matrix format files
os.makedirs("data_outputs", exist_ok=True)
final_report_df.to_csv("data_outputs/step_3_2_indicators.csv", index=False)
print("\nSuccess! Step 3.2 reports fully compiled inside 'data_outputs/step_3_2_indicators.csv'")
