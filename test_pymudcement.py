import pytest
import math
from physics import DrillingHydraulicsEngine, WellSegment, RheologyModel, NozzleInput
from cementing_engine import CementingEngine, PrimaryCementingInput
from gradients import PressureGradientProfile

def test_hydrostatic_pressure():
    """Test hydrostatic pressure calculation via ECD."""
    engine = DrillingHydraulicsEngine(
        surface_mud_weight_ppg=12.5,
        flow_rate_gpm=550,
        total_depth_ft=10000,
        plastic_viscosity_cp=22,
        yield_point_lb_100ft2=16
    )
    engine.add_segment(WellSegment(
        name="Test",
        length_ft=10000,
        pipe_od_in=5.0,
        pipe_id_in=4.276,
        hole_id_in=8.5,
        mud_weight_ppg=12.5,
        viscosity_cp=22,
        yield_point_lb_100ft2=16
    ))
    for _ in range(3):
        engine.add_nozzle(NozzleInput(size_in_32nds=12))
    results = engine.solve()
    # Hydrostatic component should be approx 12.5*0.052*10000 = 6500 psi
    # But SPP includes friction, so we check ECD is >= MW
    assert results["equivalent_circulating_density_ecd_ppg"] >= 12.5

def test_annular_volume():
    engine = CementingEngine()
    vol = engine.calculate_annular_volume_bbl(8.5, 7.0, 5000, 15.0)
    # Expected: ~ (π/4)*(8.5^2-7^2)/144*5000*(1.15)/5.6146
    expected = (math.pi/4) * ((8.5**2 - 7**2)/144) * 5000 * 1.15 / 5.6146
    assert abs(vol - expected) < 0.01

def test_gradient_profile():
    depths = [5000, 10000]
    pore = [9.0, 9.5]
    frac = [14.0, 15.5]
    profile = PressureGradientProfile(depths, pore, frac)
    assert profile.get_pore_at_depth(7500) == 9.25
    assert profile.get_frac_at_depth(10000) == 15.5

def test_cementing_design():
    params = PrimaryCementingInput(
        hole_diameter_in=8.5,
        casing_od_in=7.0,
        casing_id_in=6.276,
        interval_length_ft=5000,
        washout_factor_pct=15.0,
        shoe_track_length_ft=40.0,
        lead_slurry_density_ppg=12.5,
        tail_slurry_density_ppg=15.8,
        spacer_density_ppg=11.0,
        displacement_fluid_density_ppg=10.0,
        tail_slurry_length_ft=500.0,
        bht_fahrenheit=180.0
    )
    engine = CementingEngine()
    result = engine.design_primary_job(params)
    assert result["lead_slurry_volume_bbl"] > 0
    assert result["tail_slurry_volume_bbl"] > 0
    assert result["recommended_plug_bumping_pressure_psi"] > 0