# cementing_engine.py
"""
Primary Cementing & P&A Engineering Calculations Engine – PyMudCement Optima Pro
All volumes calculated dynamically from geometry (no hard-coded spacer).
"""
import math
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field


class Additive(BaseModel):
    name: str
    category: str
    recommended_concentration_pct: float
    description: str


CEMENT_ADDITIVES_DB: Dict[str, Additive] = {
    "Lignosulfonate": Additive(
        name="Lignosulfonate",
        category="Retarder",
        recommended_concentration_pct=0.3,
        description="Extends slurry thickening time for high bottom-hole temperatures (>170F).",
    ),
    "Calcium Chloride": Additive(
        name="Calcium Chloride",
        category="Accelerator",
        recommended_concentration_pct=2.0,
        description="Accelerates early compressive strength development at shallow, cold intervals.",
    ),
    "Barite": Additive(
        name="Barite",
        category="Weighting Agent",
        recommended_concentration_pct=15.0,
        description="Increases cement slurry density for high-pressure zones.",
    ),
    "HEC Polymer": Additive(
        name="HEC Polymer",
        category="Fluid Loss Control",
        recommended_concentration_pct=0.5,
        description="Prevents fluid filtration loss into permeable formations.",
    ),
}


class PrimaryCementingInput(BaseModel):
    hole_diameter_in: float = Field(..., gt=0)
    casing_od_in: float = Field(..., gt=0)
    casing_id_in: float = Field(..., gt=0)
    interval_length_ft: float = Field(..., gt=0)
    washout_factor_pct: float = Field(default=15.0, ge=0)
    shoe_track_length_ft: float = Field(default=40.0, ge=0)
    lead_slurry_density_ppg: float = Field(default=12.5, gt=0)
    tail_slurry_density_ppg: float = Field(default=15.8, gt=0)
    spacer_density_ppg: float = Field(default=11.0, gt=0)
    displacement_fluid_density_ppg: float = Field(default=10.0, gt=0)
    tail_slurry_length_ft: float = Field(default=500.0, ge=0)
    bht_fahrenheit: float = Field(default=180.0, ge=0)
    spacer_annular_length_ft: float = Field(default=500.0, ge=0)
    spacer_volume_override_bbl: Optional[float] = Field(default=None, ge=0)
    true_vertical_depth_ft: Optional[float] = Field(default=None, ge=0)


class CementingEngine:
    @staticmethod
    def calculate_annular_volume_bbl(
        hole_dia_in: float, casing_od_in: float, length_ft: float, washout_pct: float = 0.0
    ) -> float:
        if hole_dia_in <= casing_od_in:
            raise ValueError("Hole diameter must be greater than casing outer diameter.")
        we = washout_pct / 100.0
        vol_cu_ft = (math.pi / 4.0) * ((hole_dia_in**2 - casing_od_in**2) / 144.0) * length_ft * (1.0 + we)
        return vol_cu_ft / 5.6146

    @staticmethod
    def calculate_pipe_capacity_bbl(pipe_id_in: float, length_ft: float) -> float:
        vol_cu_ft = (math.pi / 4.0) * ((pipe_id_in**2) / 144.0) * length_ft
        return vol_cu_ft / 5.6146

    @staticmethod
    def compare_with_industry(software_results, casing_od, hole_dia, interval_length):
        from benchmarks import compare_cementing_results
        return compare_cementing_results(software_results, casing_od, hole_dia, interval_length)

    def design_primary_job(self, params: PrimaryCementingInput) -> Dict[str, Any]:
        lead_length = max(0.0, params.interval_length_ft - params.tail_slurry_length_ft)

        tail_vol_bbl = self.calculate_annular_volume_bbl(
            params.hole_diameter_in, params.casing_od_in,
            params.tail_slurry_length_ft, params.washout_factor_pct
        )
        lead_vol_bbl = (
            self.calculate_annular_volume_bbl(
                params.hole_diameter_in, params.casing_od_in,
                lead_length, params.washout_factor_pct
            ) if lead_length > 0 else 0.0
        )

        shoe_track_vol_bbl = self.calculate_pipe_capacity_bbl(params.casing_id_in, params.shoe_track_length_ft)
        displacement_vol_bbl = self.calculate_pipe_capacity_bbl(
            params.casing_id_in, max(0.0, params.interval_length_ft - params.shoe_track_length_ft)
        )
        total_tail_slurry_bbl = tail_vol_bbl + shoe_track_vol_bbl

        if params.spacer_volume_override_bbl is not None:
            spacer_vol_bbl = params.spacer_volume_override_bbl
            spacer_method = "user_override"
        else:
            spacer_vol_bbl = self.calculate_annular_volume_bbl(
                params.hole_diameter_in, params.casing_od_in,
                params.spacer_annular_length_ft, washout_pct=0.0
            )
            spacer_method = "calculated_from_annular_length"

        tvd = params.true_vertical_depth_ft if params.true_vertical_depth_ft is not None else params.interval_length_ft
        diff_hydrostatic_psi = (params.tail_slurry_density_ppg - params.displacement_fluid_density_ppg) * 0.052 * tvd
        plug_bumping_pressure_psi = max(500.0, diff_hydrostatic_psi + 500.0)

        suggested_additives = []
        if params.bht_fahrenheit > 170.0:
            suggested_additives.append(CEMENT_ADDITIVES_DB["Lignosulfonate"].model_dump())
        else:
            suggested_additives.append(CEMENT_ADDITIVES_DB["Calcium Chloride"].model_dump())
        suggested_additives.append(CEMENT_ADDITIVES_DB["HEC Polymer"].model_dump())

        return {
            "lead_slurry_volume_bbl": round(lead_vol_bbl, 2),
            "tail_slurry_volume_bbl": round(total_tail_slurry_bbl, 2),
            "spacer_volume_bbl": round(spacer_vol_bbl, 2),
            "spacer_calculation_method": spacer_method,
            "spacer_annular_length_ft": params.spacer_annular_length_ft,
            "displacement_volume_bbl": round(displacement_vol_bbl, 2),
            "shoe_track_capacity_bbl": round(shoe_track_vol_bbl, 2),
            "differential_hydrostatic_psi": round(diff_hydrostatic_psi, 2),
            "recommended_plug_bumping_pressure_psi": round(plug_bumping_pressure_psi, 2),
            "tvd_used_ft": round(tvd, 2),
            "suggested_additives": suggested_additives,
        }

    def design_abandonment_plug(self, hole_dia_in, plug_length_ft, slurry_density_ppg, mud_density_ppg):
        plug_vol_cu_ft = (math.pi / 4.0) * ((hole_dia_in**2) / 144.0) * plug_length_ft
        plug_vol_bbl = plug_vol_cu_ft / 5.6146
        sacks_of_cement = plug_vol_cu_ft / 1.18
        hydrostatic_gain_psi = (slurry_density_ppg - mud_density_ppg) * 0.052 * plug_length_ft
        return {
            "plug_length_ft": plug_length_ft,
            "plug_volume_bbl": round(plug_vol_bbl, 2),
            "cement_sacks_required": math.ceil(sacks_of_cement),
            "net_hydrostatic_gain_psi": round(hydrostatic_gain_psi, 2),
        }
