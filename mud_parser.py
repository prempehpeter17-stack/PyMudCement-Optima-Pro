import pandas as pd
import io
from typing import Dict, Any, List, Optional

def parse_mud_report(file_bytes: bytes, file_type: str = "csv") -> Dict[str, Any]:
    """
    Parse uploaded mud report (CSV or Excel) to extract PV, YP, and mud weight 
    with depth-dependent data.

    Expected columns: Depth, PV_cP, YP_lb/100ft2, MudWeight_ppg.
    Returns a dict with the full dataframe and summary statistics.
    """
    if file_type == "csv":
        df = pd.read_csv(io.BytesIO(file_bytes))
    else:  # Excel
        df = pd.read_excel(io.BytesIO(file_bytes), engine="openpyxl")

    # Validate required columns
    required_cols = ["Depth", "PV_cP", "YP_lb/100ft2", "MudWeight_ppg"]
    missing = [col for col in required_cols if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required column(s): {missing}")

    # Clean data
    df = df.dropna(subset=required_cols)
    if df.empty:
        raise ValueError("No valid data rows found.")

    # Sort by depth
    df = df.sort_values("Depth")

    # Compute summary statistics
    pv_mean = float(df["PV_cP"].mean())
    yp_mean = float(df["YP_lb/100ft2"].mean())
    mw_mean = float(df["MudWeight_ppg"].mean())

    # Return full dataset plus metadata
    return {
        "dataframe": df,
        "pv_cp": pv_mean,
        "yp": yp_mean,
        "mw_ppg": mw_mean,
        "min_depth": float(df["Depth"].min()),
        "max_depth": float(df["Depth"].max()),
        "trend": {
            "depths": df["Depth"].tolist(),
            "pv": df["PV_cP"].tolist(),
            "yp": df["YP_lb/100ft2"].tolist(),
            "mw": df["MudWeight_ppg"].tolist(),
        },
        "row_count": len(df)
    }