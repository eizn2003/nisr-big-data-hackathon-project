import os
import pandas as pd
import matplotlib.pyplot as plt

# 1. LOAD THE CSV MATRIX SAVED BY YOUR ENGINE
CSV_PATH = "data_outputs/step_3_2_indicators.csv"

if not os.path.exists(CSV_PATH):
    raise FileNotFoundError(f"Error: Run your step3.2.py script first to create {CSV_PATH}")

# Read the clean data
df = pd.read_csv(CSV_PATH)

# Sort districts from highest inclusion percentage to lowest
df_sorted = df.sort_values(by="Percentage (%)", ascending=True)

# 2. CALCULATE ERROR BAR WIDTHS USING YOUR LOWER AND UPPER CONFIDENCE BOUNDS
lower_err = df_sorted["Percentage (%)"] - df_sorted["95% CI Lower (%)"]
upper_err = df_sorted["95% CI Upper (%)"] - df_sorted["Percentage (%)"]
asymmetric_error = [lower_err, upper_err]

# 3. BUILD THE VISUAL REPRESENTATION CHART
plt.figure(figsize=(10, 12), constrained_layout=True)

# Plot the main percentage as dots, and confidence intervals as error bar lines
plt.errorbar(
    x=df_sorted["Percentage (%)"], 
    y=df_sorted["District Name"] if "District Name" in df_sorted.columns else df_sorted["a2"], 
    xerr=asymmetric_error, 
    fmt='o',            # 'o' means draw a clean circular point estimate dot
    color='darkblue',   # Color of your main point estimate dot
    ecolor='crimson',   # Color of your confidence interval error bar brackets
    elinewidth=2,       # Thickness of the error bars
    capsize=4,          # Adds clear end-caps to the interval brackets
    label="Weighted Estimate & 95% CI"
)

# Add clear text metadata
plt.title("Rwanda Financial Inclusion Indicators by District (Step 3.2)", fontsize=14, fontweight='bold', pad=15)
plt.xlabel("Financial Inclusion Rate (%) - Variable: e1", fontsize=12, labelpad=10)
plt.ylabel("Rwandan District Name", fontsize=12)
plt.grid(axis='x', linestyle='--', alpha=0.5)
plt.xlim(0, 50)  # Fits your data range beautifully

# Draw a vertical national reference line to show who is above/below average
plt.axvline(x=df["Percentage (%)"].mean(), color='green', linestyle='-.', alpha=0.7, label="National Sample Average")
plt.legend(loc="lower right")

# 4. EXPORT THE GRAPH AS A HIGH-QUALITY PNG PICTURE FOR YOUR PRESENTATION
output_img = "data_outputs/step_3_2_district_ranking.png"
os.makedirs("data_outputs", exist_ok=True)
plt.savefig(output_img, dpi=300, bbox_inches="tight")

print(f"\nSuccess! Your presentation ranking chart with error bars is saved at: {output_img}")
plt.show()
