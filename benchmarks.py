"""
Industry standard benchmark values for cementing volumes.
Based on typical Halliburton/Schlumberger guidelines.
"""

from typing import Dict, Any, Optional

# Benchmark volumes in barrels per 100 ft of annular interval
# Key: "casing_OD_x_hole_size"
INDUSTRY_VOLUMES = {
    "7_x_8.5": {
        "lead_bbl_per_100ft": 28.3,
        "tail_bbl_per_100ft": 10.1,
        "spacer_bbl": 35.0,
        "description": "7\" casing in 8.5\" hole"
    },
    "7_x_9.875": {
        "lead_bbl_per_100ft": 33.2,
        "tail_bbl_per_100ft": 12.4,
        "spacer_bbl": 40.0,
        "description": "7\" casing in 9.875\" hole"
    },
    "9.625_x_12.25": {
        "lead_bbl_per_100ft": 42.5,
        "tail_bbl_per_100ft": 15.2,
        "spacer_bbl": 50.0,
        "description": "9.625\" casing in 12.25\" hole"
    },
    "9.625_x_14.75": {
        "lead_bbl_per_100ft": 52.8,
        "tail_bbl_per_100ft": 18.9,
        "spacer_bbl": 60.0,
        "description": "9.625\" casing in 14.75\" hole"
    },
    "13.375_x_17.5": {
        "lead_bbl_per_100ft": 72.5,
        "tail_bbl_per_100ft": 25.3,
        "spacer_bbl": 80.0,
        "description": "13.375\" casing in 17.5\" hole"
    }
}

def get_benchmark_key(casing_od: float, hole_dia: float) -> Optional[str]:
    """Find matching benchmark key from casing OD and hole size."""
    # Round to nearest 0.1 to match keys
    casing_str = f"{casing_od:.1f}" if casing_od % 0.125 == 0 else f"{casing_od:.0f}"
    hole_str = f"{hole_dia:.1f}" if hole_dia % 0.125 == 0 else f"{hole_dia:.0f}"
    key = f"{casing_str}_x_{hole_str}"
    if key in INDUSTRY_VOLUMES:
        return key
    # Try fuzzy match: find closest
    best_key = None
    best_dist = float('inf')
    for k in INDUSTRY_VOLUMES:
        parts = k.split('_x_')
        if len(parts) != 2:
            continue
        try:
            c_bench = float(parts[0])
            h_bench = float(parts[1])
            dist = abs(c_bench - casing_od) + abs(h_bench - hole_dia)
            if dist < best_dist:
                best_dist = dist
                best_key = k
        except:
            continue
    if best_key and best_dist < 1.0:  # within 1 inch total
        return best_key
    return None

def compare_cementing_results(software_results: Dict[str, Any], 
                              casing_od: float, 
                              hole_dia: float,
                              interval_length: float) -> Dict[str, Any]:
    """
    Compare software cementing results with industry benchmarks.
    Returns deviation percentages.
    """
    key = get_benchmark_key(casing_od, hole_dia)
    if not key:
        return {"error": f"No benchmark available for {casing_od}\" casing in {hole_dia}\" hole."}
    
    benchmark = INDUSTRY_VOLUMES[key]
    
    # Compute expected volumes for the given interval length
    length_factor = interval_length / 100.0
    expected_lead = benchmark["lead_bbl_per_100ft"] * length_factor
    expected_tail = benchmark["tail_bbl_per_100ft"] * length_factor
    
    software_lead = software_results.get("lead_slurry_volume_bbl", 0)
    software_tail = software_results.get("tail_slurry_volume_bbl", 0)
    
    return {
        "benchmark_key": key,
        "description": benchmark["description"],
        "lead_slurry": {
            "software": software_lead,
            "industry": expected_lead,
            "deviation_pct": (software_lead - expected_lead) / expected_lead * 100 if expected_lead > 0 else 0
        },
        "tail_slurry": {
            "software": software_tail,
            "industry": expected_tail,
            "deviation_pct": (software_tail - expected_tail) / expected_tail * 100 if expected_tail > 0 else 0
        },
        "spacer": {
            "software": software_results.get("spacer_volume_bbl", 0),
            "industry": benchmark["spacer_bbl"],
            "deviation_pct": (software_results.get("spacer_volume_bbl", 0) - benchmark["spacer_bbl"]) / benchmark["spacer_bbl"] * 100
        }
    }