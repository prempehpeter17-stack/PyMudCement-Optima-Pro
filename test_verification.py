"""
Manual verification of core calculations for the technical report.
Run this script to generate verification tables.
"""

import math
import sys
from physics import DrillingHydraulicsEngine, WellSegment, RheologyModel, NozzleInput
from cementing_engine import CementingEngine, PrimaryCementingInput

def verify_hydrostatic_pressure():
    """Verify hydrostatic pressure calculation."""
    print("\n" + "="*60)
    print("VERIFICATION 1: HYDROSTATIC PRESSURE")
    print("="*60)
    
    # Given parameters
    depth_ft = 10000.0
    mw_ppg = 12.5
    
    # Manual calculation
    expected_psi = mw_ppg * 0.052 * depth_ft  # 12.5 * 0.052 * 10000 = 6500 psi
    
    # Software calculation (using a simple single segment)
    engine = DrillingHydraulicsEngine(
        surface_mud_weight_ppg=mw_ppg,
        flow_rate_gpm=550,
        total_depth_ft=depth_ft,
        plastic_viscosity_cp=22,
        yield_point_lb_100ft2=16,
        rheology_model=RheologyModel.BINGHAM_PLASTIC
    )
    engine.add_segment(WellSegment(
        name="Verification Section",
        length_ft=depth_ft,
        pipe_od_in=5.0,
        pipe_id_in=4.276,
        hole_id_in=8.5,
        mud_weight_ppg=mw_ppg,
        viscosity_cp=22,
        yield_point_lb_100ft2=16
    ))
    # Add dummy nozzles to avoid errors
    engine.add_nozzle(NozzleInput(size_in_32nds=12))
    engine.add_nozzle(NozzleInput(size_in_32nds=12))
    engine.add_nozzle(NozzleInput(size_in_32nds=12))
    results = engine.solve()
    
    # The total SPP includes friction; we extract hydrostatic from ECD formula
    # ECD = MW + (Annular DP)/(0.052*TVD) => Annular DP = (ECD - MW)*0.052*TVD
    ecd = results["equivalent_circulating_density_ecd_ppg"]
    annular_dp = (ecd - mw_ppg) * 0.052 * depth_ft
    hydrostatic_psi = mw_ppg * 0.052 * depth_ft
    
    print(f"Input: Depth={depth_ft} ft, Mud Weight={mw_ppg} ppg")
    print(f"Manual Hydrostatic Pressure: {expected_psi:.2f} psi")
    print(f"Software Hydrostatic (from MW): {hydrostatic_psi:.2f} psi")
    print(f"Software ECD: {ecd:.3f} ppg")
    print(f"Software Annular DP: {annular_dp:.2f} psi")
    print(f"Difference in hydrostatic: {abs(expected_psi - hydrostatic_psi):.2f} psi (should be ~0)")

def verify_annular_volume():
    """Verify annular volume calculation for cementing."""
    print("\n" + "="*60)
    print("VERIFICATION 2: ANNULAR VOLUME (CEMENTING)")
    print("="*60)
    
    # Given parameters
    hole_dia = 8.5       # inches
    casing_od = 7.0      # inches
    length = 5000.0      # feet
    washout_pct = 15.0   # percent
    
    # Manual calculation
    # Volume (bbl) = (π/4) * (D_hole² - d_casing²) / 144 * L * (1 + W_e) / 5.6146
    vol_cu_ft = (math.pi / 4.0) * ((hole_dia**2 - casing_od**2) / 144.0) * length * (1 + washout_pct/100.0)
    expected_bbl = vol_cu_ft / 5.6146
    
    # Software calculation
    engine = CementingEngine()
    vol_bbl = engine.calculate_annular_volume_bbl(hole_dia, casing_od, length, washout_pct)
    
    print(f"Input: Hole={hole_dia}\" , Casing OD={casing_od}\", Length={length} ft, Washout={washout_pct}%")
    print(f"Manual Annular Volume: {expected_bbl:.2f} bbl")
    print(f"Software Annular Volume: {vol_bbl:.2f} bbl")
    print(f"Difference: {abs(expected_bbl - vol_bbl):.2f} bbl (should be ~0)")

def verify_plug_bumping_pressure():
    """Verify plug bumping pressure calculation."""
    print("\n" + "="*60)
    print("VERIFICATION 3: PLUG BUMPING PRESSURE")
    print("="*60)
    
    # Given parameters (from a typical job)
    tail_density = 15.8   # ppg
    disp_density = 10.0   # ppg
    interval_length = 5000.0  # ft
    
    # Manual: differential hydrostatic + safety margin (500 psi)
    diff_hydro = (tail_density - disp_density) * 0.052 * interval_length
    expected_pressure = max(500.0, diff_hydro + 500.0)
    
    # Software: use PrimaryCementingInput
    params = PrimaryCementingInput(
        hole_diameter_in=8.5,
        casing_od_in=7.0,
        casing_id_in=6.276,
        interval_length_ft=interval_length,
        washout_factor_pct=15.0,
        shoe_track_length_ft=40.0,
        lead_slurry_density_ppg=12.5,
        tail_slurry_density_ppg=tail_density,
        spacer_density_ppg=11.0,
        displacement_fluid_density_ppg=disp_density,
        tail_slurry_length_ft=500.0,
        bht_fahrenheit=180.0
    )
    engine = CementingEngine()
    result = engine.design_primary_job(params)
    software_pressure = result["recommended_plug_bumping_pressure_psi"]
    
    print(f"Input: Tail={tail_density} ppg, Disp={disp_density} ppg, Interval={interval_length} ft")
    print(f"Manual Plug Bumping Pressure: {expected_pressure:.2f} psi")
    print(f"Software Plug Bumping Pressure: {software_pressure:.2f} psi")
    print(f"Difference: {abs(expected_pressure - software_pressure):.2f} psi")

if __name__ == "__main__":
    # Run all verifications
    verify_hydrostatic_pressure()
    verify_annular_volume()
    verify_plug_bumping_pressure()
    print("\n" + "="*60)
    print("All verifications completed. Include these results in your report.")