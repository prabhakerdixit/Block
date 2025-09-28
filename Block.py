# app.py
import os
import glob
import re
import pandas as pd
import streamlit as st

st.set_page_config(layout="wide", page_title="Block Data Explorer")

# ------------------- data load -------------------
@st.cache_data(show_spinner="Loading main data...")
def load_block_data():
    path = "./Data"
    all_files = glob.glob(os.path.join(path, "*.csv"))

    if not all_files:
        return pd.DataFrame()

    frames = []
    for file in all_files:
        df = pd.read_csv(
            file,
            na_values=["-", "--", "N/A", "NA", "null", "Null", "NULL", "", " "],
            keep_default_na=True,
        )
        frames.append(df)

    df_merged = pd.concat(frames, ignore_index=True)

    # Ensure expected columns exist
    expected = [
        "Board","Station","Block Section","Direction","Type",
        "Requested Start Time","Requested End Time",
        "Permitted Start Time","Permitted End Time",
        "Line Number","Remark","Extension End Time","Clear Time",
        "Total Duration (In Minutes)","Burst Duration (In Minutes)",
        "Division","Block Requested Date"
    ]
    for c in expected:
        if c not in df_merged.columns:
            df_merged[c] = pd.NA

    # Build ID
    df_merged["ID"] = (
        df_merged["Station"].astype(str) + "/" +
        df_merged["Block Section"].astype(str) + "/" +
        df_merged["Block Section"].astype(str) + "/" +
        df_merged["Requested Start Time"].astype(str) + "/" +
        df_merged["Requested End Time"].astype(str) + "/" +
        df_merged["Permitted Start Time"].astype(str) + "/" +
        df_merged["Permitted End Time"].astype(str)
    )

    # Drop duplicates
    df_merged = df_merged.drop_duplicates(subset=["ID"], keep="first")

    # Clean & parse datetime-like columns
    time_cols = [
        "Requested Start Time","Requested End Time",
        "Permitted Start Time","Permitted End Time","Clear Time",
        "Block Requested Date"
    ]
    for col in time_cols:
        df_merged[col] = (
            df_merged[col]
            .astype("string")
            .str.strip()
            .replace({"-": pd.NA, "--": pd.NA})
        )
        df_merged[col] = pd.to_datetime(df_merged[col], errors="coerce", dayfirst=True)

    # Compute durations (minutes)
    df_merged["Demanded"] = (
        (df_merged["Requested End Time"] - df_merged["Requested Start Time"])
        .dt.total_seconds().div(60)
    )
    df_merged["Granted"] = (
        (df_merged["Permitted End Time"] - df_merged["Permitted Start Time"])
        .dt.total_seconds().div(60)
    )
    df_merged["Availed"] = (
        (df_merged["Clear Time"] - df_merged["Permitted Start Time"])
        .dt.total_seconds().div(60)
    )
    df_merged["Burst"] = df_merged["Granted"] - df_merged["Availed"]

    return df_merged

# ------------------- helpers -------------------
def minutes_to_hhmm(minutes: float) -> str:
    """Convert minutes (float) to HH:MM string safely."""
    if pd.isna(minutes):
        return ""
    total_minutes = int(round(minutes))
    hours, mins = divmod(total_minutes, 60)
    return f"{hours:02d}:{mins:02d}"

def format_duration_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Format key duration columns into HH:MM strings for display."""
    df = df.copy()
    for col in ["Demanded", "Granted", "Availed", "Burst Duration (In Minutes)"]:
        if col in df.columns:
            df[col] = df[col].apply(minutes_to_hhmm)
    return df

# ------------------- app -------------------
# File uploader first
uploaded_file = st.file_uploader("Upload CSV or Excel", type=["csv", "xlsx", "xls"])

if uploaded_file is not None:
    if uploaded_file.name.endswith(".csv"):
        df_merged = pd.read_csv(
            uploaded_file,
            na_values=["-", "--", "N/A", "NA", "null", "Null", "NULL", "", " "],
            keep_default_na=True,
        )
    else:  # Excel
        df_merged = pd.read_excel(
            uploaded_file,
            na_values=["-", "--", "N/A", "NA", "null", "Null", "NULL", "", " "],
            keep_default_na=True,
        )
else:
    df_merged = load_block_data()

if df_merged.empty:
    st.warning("No data found. Please upload a file or add CSVs to ./Data.")
    st.stop()

# Remove margin top
st.markdown(
    """
    <style>
    div.block-container {padding-top: 1.5rem;}
    </style>
    """,
    unsafe_allow_html=True,
)

st.subheader("Block Data Explorer")

# Exact-match filters
filters_map = {
    "Board": "Board",
    "Station": "Station",
    "Block Section": "Block Section",
    "Direction": "Direction",
    "Type": "Type",
    "Line Number": "Line Number",
    "Remark": "Remark",
    "Division": "Division",
}

options_map = {
    label: sorted(list(df_merged[col].dropna().astype(str).unique()))
    if col in df_merged.columns else []
    for label, col in filters_map.items()
}

st.subheader("Filters")
selected = {}
cols = st.columns(len(filters_map))
for i, label in enumerate(filters_map.keys()):
    selected[label] = cols[i].multiselect(
        label=label,
        options=options_map[label],
        default=[],
        key=f"flt_{label}",
    )

# Remark search
remark_query = st.text_input("Type to search Remarks (case-insensitive):", value="")

# ---------- Apply filters ----------
df_view = df_merged.copy()
for label, selections in selected.items():
    col_name = filters_map[label]
    if selections and col_name in df_view.columns:
        df_view = df_view[df_view[col_name].astype(str).isin([str(s) for s in selections])]
if "Remark" in df_view.columns and remark_query:
    df_view = df_view[
        df_view["Remark"].astype("string").str.contains(
            re.escape(remark_query), case=False, na=False, regex=True
        )
    ]

# ---------- Display ----------
preferred_order = [
    "Board","Division","Line Number","Station","Block Section","Direction","Type",
    "Requested Start Time","Requested End Time","Permitted Start Time","Permitted End Time",
    "Clear Time","Demanded","Granted","Availed","Burst","Remark","ID"
]
cols_existing = [c for c in preferred_order if c in df_view.columns]
remaining = [c for c in df_view.columns if c not in cols_existing]
ordered_cols = cols_existing + remaining

# --- Group By ---
st.subheader("Group By")
col1, col2 = st.columns(2)

groupby_options_exact = [
    "Board","Station","Block Section","Direction","Type",
    "Requested Start Time","Requested End Time",
    "Permitted Start Time","Permitted End Time",
    "Line Number","Remark","Extension End Time","Clear Time",
    "Total Duration (In Minutes)","Burst Duration (In Minutes)",
    "Division","Block Requested Date"
]
groupby_options = [c for c in groupby_options_exact if c in df_view.columns]

with col1:
    default_group = ["Type"] if "Type" in groupby_options else []
    group_cols = st.multiselect(
        "Group by columns:",
        options=groupby_options,
        default=default_group
    )

default_numeric = [
    "Demanded", "Granted", "Availed", "Burst Duration (In Minutes)"
]
numeric_cols = [c for c in default_numeric if c in df_view.columns]

with col2:
    selected_numeric = st.multiselect(
        "Numeric columns to aggregate (sum):",
        options=numeric_cols,
        default=numeric_cols
    )

for c in selected_numeric:
    df_view[c] = pd.to_numeric(df_view[c], errors="coerce")

if group_cols:
    gb = df_view.groupby(group_cols, dropna=False)
    agg_dict = {c: "sum" for c in selected_numeric} if selected_numeric else {}
    grouped = gb.agg(agg_dict) if agg_dict else gb.size().to_frame("Rows")
    if agg_dict:
        grouped["Rows"] = gb.size()
    grouped = grouped.reset_index()

    grouped_display = format_duration_columns(grouped)

    if "Rows" in grouped_display.columns:
        display_cols = ["Rows"] + [c for c in grouped_display.columns if c != "Rows"]
        grouped_display = grouped_display[display_cols]

    st.dataframe(grouped_display, use_container_width=True)
else:
    df_display = format_duration_columns(df_view[ordered_cols])
    st.dataframe(df_display, use_container_width=True)

df_view.to_csv("BlockAllData.csv")
