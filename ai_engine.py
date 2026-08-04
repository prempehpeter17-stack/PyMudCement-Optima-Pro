import math
import logging
from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, model_validator

logger = logging.getLogger("PyMudCementOptimaPro.v5_1")

# ==========================================
# 1. ENHANCED GEOMETRY & BHA MODELS (v5.1)
# ==========================================

class BHAParameters(BaseModel):
    """BHA, Motor, and Telemetry Tool hydraulic properties."""
    has_mud_motor: bool = Field(default=False, description="Whether a PDM is in the BHA")
    motor_no_load_dp_psi: float = Field(default=150.0, ge=0, description="Differential pressure across motor under no load (psi)")
    motor_operating_dp_psi: float = Field(default=450.0, ge=0, description="Operating differential pressure across motor (psi)")
    mwd_tool_dp_psi: float = Field(default=120.0, ge=0, description="Pressure drop across MWD/LWD pulses/restrictors (psi)")
    bha_length_ft: float = Field(default=120.0, ge=0, description="Total BHA assembly length in feet")
    bha_inner_diameter_in: float = Field(default=2.812, gt=0, description="Average BHA bore inner diameter in inches")

class WellSegment(BaseModel):
    name: str = Field(default="Segment", description="Segment identifier")
    length_md_ft: float = Field(..., ge=0, description="Measured length of segment in feet")
    tvd_segment_ft: float = Field(..., ge=0, description="True Vertical Depth delta of segment in feet")
    inclination_deg: float = Field(default=0.0, ge=0.0, le=90.0, description="Average section inclination in degrees")
    azimuth_deg: float = Field(default=0.0, ge=0.0, le=360.0, description="Section azimuth in degrees")
    
    pipe_od_in: float = Field(..., gt=0, description="Outer diameter of pipe in inches")
    pipe_id_in: float = Field(..., gt=0, description="Inner diameter of pipe in inches")
    hole_id_in: float = Field(..., gt=0, description="Hole size or casing ID in inches")
    mud_weight_ppg: float = Field(..., gt=0, description="Fluid density in ppg")

    # v5.1 Dynamic Mechanics & Positioning Extensions
    eccentricity_ratio: float = Field(default=0.0, ge=0.0, lt=1.0, description="Pipe eccentricity e (0 = centered, 0.99 = touching wall)")
    rpm: float = Field(default=0.0, ge=0.0, le=300.0, description="Drill string rotation speed in RPM")

    viscosity_cp: float = Field(default=20.0, ge=0, description="Plastic Viscosity (cP) at reference 80°F")
    yield_point_lb_100ft2: float = Field(default=15.0, ge=0, description="Yield Point (lb/100ft²)")
    tau_0_lb_100ft2: float = Field(default=5.0, ge=0, description="Yield stress for Herschel-Bulkley")
    n_index: float = Field(default=0.65, gt=0, le=1.0, description="Flow behavior index (n)")
    k_consistency: float = Field(default=300.0, gt=0, description="Consistency index")
    
    temperature_f: float = Field(default=80.0, description="Average section temperature in °F")

    @model_validator(mode="after")
    def validate_geometry_and_depth(self):
        if self.pipe_id_in >= self.pipe_od_in:
            raise ValueError(f"[{self.name}] Pipe ID ({self.pipe_id_in}\") must be smaller than Pipe OD ({self.pipe_od_in}\").")
        if self.pipe_od_in >= self.hole_id_in:
            raise ValueError(f"[{self.name}] Pipe OD ({self.pipe_od_in}\") must be smaller than Hole ID ({self.hole_id_in}\").")
        if self.tvd_segment_ft > self.length_md_ft:
            raise ValueError(f"[{self.name}] Segment TVD ({self.tvd_segment_ft} ft) cannot exceed MD ({self.length_md_ft} ft).")
        return self

    def get_temperature_corrected_viscosity(self) -> float:
        """Thermal viscosity decay relative to baseline 80°F."""
        return max(1.0, self.viscosity_cp * math.exp(-0.01 * (self.temperature_f - 80.0)))


# ==========================================
# 2. ADVANCED v5.1 HYDRAULICS ENGINE
# ==========================================

class DrillingHydraulicsEngineV5:
    """v5.1 Engine with Eccentricity, RPM Agitation, and BHA Motors."""

    def __init__(
        self,
        surface_mud_weight_ppg: float,
        flow_rate_gpm: float,
        total_md_ft: float,
        total_tvd_ft: float,
        bha_spec: Optional[BHAParameters] = None
    ):
        self.surface_mud_weight_ppg = max(0.1, surface_mud_weight_ppg)
        self.flow_rate_gpm = max(0.0, flow_rate_gpm)
        self.total_md_ft = max(1.0, total_md_ft)
        self.total_tvd_ft = max(1.0, min(total_tvd_ft, total_md_ft))
        self.bha = bha_spec if bha_spec else BHAParameters()
        self.segments: List[WellSegment] = []

    def add_segment(self, segment: WellSegment) -> None:
        self.segments.append(segment)

    @staticmethod
    def calculate_eccentricity_correction_factor(e: float, d_pipe: float, d_hole: float, n: float = 0.65) -> float:
        """
        Haciislamoglu eccentricity friction pressure reduction factor R_e.
        R_e = dp/dl_eccentric / dp/dl_concentric
        """
        if e <= 0.0:
            return 1.0
        d_ratio = d_pipe / d_hole
        # Haciislamoglu correlation for non-Newtonian yield fluids
        r_e = 1.0 - (0.072 * (e / n) * (d_ratio ** 0.8454)) - (1.5 * (e ** 2) * math.sqrt(n) * (d_ratio ** 0.1852)) + (0.96 * (e ** 3) * math.sqrt(n) * (d_ratio ** 0.2527))
        return max(0.40, min(1.0, r_e))

    def calculate_annular_friction_gradient(self, seg: WellSegment) -> float:
        """Calculates concentric annular friction loss modified by pipe eccentricity."""
        dh = seg.hole_id_in - seg.pipe_od_in
        if dh <= 0:
            return 0.0

        v_ann_fpm = (24.51 * self.flow_rate_gpm) / (seg.hole_id_in ** 2 - seg.pipe_od_in ** 2)
        pv_eff = seg.get_temperature_corrected_viscosity()
        yp = seg.yield_point_lb_100ft2

        # Base concentric Bingham pressure loss gradient (psi/ft)
        dp_dl_concentric = ((pv_eff * v_ann_fpm) / (1000.0 * (dh ** 2))) + (yp / (200.0 * dh))
        
        # Apply Eccentricity Correction Factor
        r_e = self.calculate_eccentricity_correction_factor(seg.eccentricity_ratio, seg.pipe_od_in, seg.hole_id_in, seg.n_index)
        return dp_dl_concentric * r_e

    def calculate_cuttings_transport_v51(self, seg: WellSegment, rop_fph: float = 60.0) -> Dict[str, Any]:
        """
        Cuttings transport ratio with RPM rotational agitation and inclination-adjusted slip velocity.
        """
        v_ann_fpm = (24.51 * self.flow_rate_gpm) / (seg.hole_id_in ** 2 - seg.pipe_od_in ** 2)
        pv_eff = seg.get_temperature_corrected_viscosity()

        # Base vertical slip velocity (ft/min)
        v_slip_base = (0.45 * (seg.mud_weight_ppg - 2.0)) * (0.25 ** 0.667) / ((seg.mud_weight_ppg ** 0.333) * (pv_eff ** 0.333)) * 60.0
        
        # Inclination Penalty
        inc_rad = math.radians(seg.inclination_deg)
        inc_factor = 1.0 + (0.5 * math.sin(inc_rad * 2.0)) if seg.inclination_deg > 0 else 1.0
        
        # RPM Agitation Lift Factor (Rotation breaks fluid gel and mechanically lifts bed)
        rpm_benefit = 1.0 - min(0.40, (seg.rpm / 150.0) * 0.35 * math.sin(inc_rad))
        
        effective_slip_v = v_slip_base * inc_factor * rpm_benefit
        transport_ratio = max(0.0, min(100.0, (1.0 - (effective_slip_v / max(0.1, v_ann_fpm))) * 100.0))

        # Bed Height estimation considering eccentricity (eccentric pipes restrict low-side clearance)
        clearance_in = (seg.hole_id_in - seg.pipe_od_in) * 0.5
        bed_height_est_in = clearance_in * ((100.0 - transport_ratio) / 100.0) * (1.0 + 0.5 * seg.eccentricity_ratio)

        return {
            "annular_velocity_fpm": round(v_ann_fpm, 1),
            "effective_slip_velocity_fpm": round(effective_slip_v, 1),
            "transport_ratio_pct": round(transport_ratio, 1),
            "estimated_bed_height_in": round(bed_height_est_in, 2),
            "rpm_agitation_boost_pct": round((1.0 - rpm_benefit) * 100.0, 1)
        }

    def calculate_bha_pressure_loss(self) -> Dict[str, float]:
        """Calculates internal pressure drops caused by Mud Motors, MWD tools, and BHA bore restriction."""
        if not self.bha:
            return {"total_bha_dp_psi": 0.0, "motor_dp_psi": 0.0, "mwd_dp_psi": 0.0, "bha_bore_dp_psi": 0.0}

        motor_dp = self.bha.motor_operating_dp_psi if self.bha.has_mud_motor else 0.0
        mwd_dp = self.bha.mwd_tool_dp_psi
        
        # Internal BHA pipe friction loss
        v_bha = (24.51 * self.flow_rate_gpm) / (self.bha.bha_inner_diameter_in ** 2)
        bha_bore_dp = ((15.0 * v_bha) / (1500.0 * (self.bha.bha_inner_diameter_in ** 2))) * self.bha.bha_length_ft

        total_bha_loss = motor_dp + mwd_dp + bha_bore_dp
        return {
            "total_bha_dp_psi": round(total_bha_loss, 2),
            "motor_dp_psi": round(motor_dp, 2),
            "mwd_dp_psi": round(mwd_dp, 2),
            "bha_bore_dp_psi": round(bha_bore_dp, 2)
        }

    def solve_v51() -> Dict[str, Any]:
        """Executes full v5.1 hydraulics engine simulation."""
        total_annular_dp = 0.0
        total_pipe_dp = 0.0
        segment_logs = []

        for seg in self.segments:
            ann_grad = self.calculate_annular_friction_gradient(seg)
            seg_ann_dp = ann_grad * seg.length_md_ft
            
            v_pipe = (24.51 * self.flow_rate_gpm) / (seg.pipe_id_in ** 2)
            pipe_grad = ((seg.get_temperature_corrected_viscosity() * v_pipe) / (1500.0 * (seg.pipe_id_in ** 2)))
            seg_pipe_dp = pipe_grad * seg.length_md_ft

            total_annular_dp += seg_ann_dp
            total_pipe_dp += seg_pipe_dp

            transport_eval = self.calculate_cuttings_transport_v51(seg)
            segment_logs.append({
                "segment": seg.name,
                "eccentricity": seg.eccentricity_ratio,
                "rpm": seg.rpm,
                "annular_dp_psi": round(seg_ann_dp, 2),
                "transport_ratio_pct": transport_eval["transport_ratio_pct"],
                "bed_height_in": transport_eval["estimated_bed_height_in"]
            })

        bha_losses = self.calculate_bha_pressure_loss()
        surface_losses = 50.0
        total_spp = surface_losses + total_pipe_dp + bha_losses["total_bha_dp_psi"] + total_annular_dp
        ecd = self.surface_mud_weight_ppg + (total_annular_dp / (0.052 * self.total_tvd_ft))

        return {
            "version": "5.1-PROT",
            "standpipe_pressure_spp_psi": round(total_spp, 2),
            "equivalent_circulating_density_ecd_ppg": round(ecd, 3),
            "total_bha_pressure_loss_psi": bha_losses["total_bha_dp_psi"],
            "bha_breakdown": bha_losses,
            "segments_analysis": segment_logs
        }
