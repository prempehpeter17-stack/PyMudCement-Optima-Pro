import math
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

class Additive(BaseModel):
    name: str
    category: str  # Retarder, Accelerator, Weighting Agent, Fluid Loss
    recommended_concentration_pct: float
    description: str

# Automated Additive Look-up Database
CEMENT_ADDITIVES_DB: Dict[str, Additive] = {
    "Lignosulfonate": Additive(
        name="Lignosulfonate",
        category="Retarder",
        recommended_concentration_pct=0.3,
        description="Extends slurry thickening time for high bottom-hole temperatures (>170°F)."
    ),
    "Calcium Chloride": Additive(
        name="Calcium Chloride",
        category="Accelerator",
        recommended_concentration_pct=2.0,
        description="Accelerates early compressive strength development at shallow, cold intervals."
    ),
    "Barite": Additive(
        name="Barite",
        category="Weighting Agent",
        recommended_concentration_pct=15.0,
        description="Increases cement slurry density for high-pressure zones."
    ),
    "HEC Polymer": Additive(
        name="HEC Polymer",
        category="Fluid Loss Control",
        recommended_concentration_pct=0.5,
        description="Prevents fluid filtration loss into permeable formations."
    )
}

class PrimaryCementingInput(BaseModel):
    hole_diameter_in: float = Field(..., gt=0, description="Hole ID (in)")
    casing_od_in: float = Field(..., gt=0, description="Casing Outer Diameter (in)")
    casing_id_in: float = Field(..., gt=0, description="Casing Inner Diameter (in)")
    interval_length_ft: float = Field(..., gt=0, description="Length of cemented interval (ft)")
    washout_factor_pct: float = Field(default=15.0, ge=0, description="Open-hole excess factor % (e.g., 15 for 15%)")
    shoe_track_length_ft: float = Field(default=40.0, ge=0, description="Shoe track length (ft)")
   
    # Fluid Densities (ppg)
    lead_slurry_density_ppg: float = Field(default=12.5, gt=0)
    tail_slurry_density_ppg: float = Field(default=15.8, gt=0)
    spacer_density_ppg: float = Field(default=11.0, gt=0)
    displacement_fluid_density_ppg: float = Field(default=10.0, gt=0)
   
    # Coverage Ratios
    tail_slurry_length_ft: float = Field(default=500.0, ge=0)
    bht_fahrenheit: float = Field(default=180.0, ge=0)

class CementingEngine:
    """Primary Cementing & P&A Engineering Calculations Engine."""

    @staticmethod
    def calculate_annular_volume_bbl(hole_dia_in: float, casing_od_in: float, length_ft: float, washout_pct: float = 0.0) -> float:
        """Calculates annular capacity volume in barrels using standard volumetric equations."""
        if hole_dia_in <= casing_od_in:
            raise ValueError("Hole diameter must be greater than casing outer diameter.")
       
        we = washout_pct / 100.0
        # Volume (cu ft) = (pi / 4) * ((D_hole^2 - d_casing^2) / 144) * L * (1 + We)
        vol_cu_ft = (math.pi / 4.0) * ((hole_dia_in**2 - casing_od_in**2) / 144.0) * length_ft * (1.0 + we)
        return vol_cu_ft / 5.6146  # Convert ft³ to bbl

    @staticmethod
    def calculate_pipe_capacity_bbl(pipe_id_in: float, length_ft: float) -> float:
        """Calculates internal volume capacity of a pipe/casing string in barrels."""
        vol_cu_ft = (math.pi / 4.0) * ((pipe_id_in**2) / 144.0) * length_ft
        return vol_cu_ft / 5.6146

    def design_primary_job(self, params: PrimaryCementingInput) -> Dict[str, Any]:
        """Calculates volumes for lead/tail slurry, spacers, displacement, and plug bumping pressure."""
        lead_length = max(0.0, params.interval_length_ft - params.tail_slurry_length_ft)
       
        # Volumetrics
        tail_vol_bbl = self.calculate_annular_volume_bbl(
            params.hole_diameter_in, params.casing_od_in, params.tail_slurry_length_ft, params.washout_factor_pct
        )
        lead_vol_bbl = self.calculate_annular_volume_bbl(
            params.hole_diameter_in, params.casing_od_in, lead_length, params.washout_factor_pct
        ) if lead_length > 0 else 0.0
       
        shoe_track_vol_bbl = self.calculate_pipe_capacity_bbl(params.casing_id_in, params.shoe_track_length_ft)
        displacement_vol_bbl = self.calculate_pipe_capacity_bbl(
            params.casing_id_in, max(0.0, params.interval_length_ft - params.shoe_track_length_ft)
        )
       
        total_tail_slurry_bbl = tail_vol_bbl + shoe_track_vol_bbl
       
        # Operational Limits: Plug Bumping Pressure Calculation
        # Differential Hydrostatic Pressure = (rho_cement - rho_disp) * 0.052 * TVD
        diff_hydrostatic_psi = (params.tail_slurry_density_ppg - params.displacement_fluid_density_ppg) * 0.052 * params.interval_length_ft
        plug_bumping_pressure_psi = max(500.0, diff_hydrostatic_psi + 500.0)  # Safety margin +500 psi
       
        # Recommended Additives based on temperature
        suggested_additives = []
        if params.bht_fahrenheit > 170.0:
            suggested_additives.append(CEMENT_ADDITIVES_DB["Lignosulfonate"].model_dump())
        else:
            suggested_additives.append(CEMENT_ADDITIVES_DB["Calcium Chloride"].model_dump())
           
        suggested_additives.append(CEMENT_ADDITIVES_DB["HEC Polymer"].model_dump())

        return {
            "lead_slurry_volume_bbl": round(lead_vol_bbl, 2),
            "tail_slurry_volume_bbl": round(total_tail_slurry_bbl, 2),
            "spacer_volume_bbl": round(50.0, 2),  # Standard 50 bbl spacer sweep
            "displacement_volume_bbl": round(displacement_vol_bbl, 2),
            "shoe_track_capacity_bbl": round(shoe_track_vol_bbl, 2),
            "differential_hydrostatic_psi": round(diff_hydrostatic_psi, 2),
            "recommended_plug_bumping_pressure_psi": round(plug_bumping_pressure_psi, 2),
            "suggested_additives": suggested_additives
        }

    def design_abandonment_plug(
        self, hole_dia_in: float, plug_length_ft: float, slurry_density_ppg: float, mud_density_ppg: float
    ) -> Dict[str, Any]:
        """Calculates volume and hydrostatic parameters for Open-Hole P&A / Side-Track Plugs."""
        plug_vol_cu_ft = (math.pi / 4.0) * ((hole_dia_in**2) / 144.0) * plug_length_ft
        plug_vol_bbl = plug_vol_cu_ft / 5.6146
        sacks_of_cement = plug_vol_cu_ft / 1.18  # Standard API Class G yield (1.18 cu ft / sk)
       
        hydrostatic_gain_psi = (slurry_density_ppg - mud_density_ppg) * 0.052 * plug_length_ft

        return {
            "plug_length_ft": plug_length_ft,
            "plug_volume_bbl": round(plug_vol_bbl, 2),
            "cement_sacks_required": math.ceil(sacks_of_cement),
            "net_hydrostatic_gain_psi": round(hydrostatic_gain_psi, 2)
        }