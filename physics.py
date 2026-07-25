import math
from enum import Enum
from typing import List, Dict, Optional
from pydantic import BaseModel, Field

# =====================================================================
# 1. Rheology Enums & Data Models
# =====================================================================
class RheologyModel(str, Enum):
    NEWTONIAN = "Newtonian"
    BINGHAM_PLASTIC = "Bingham Plastic"
    POWER_LAW = "Power Law"
    HERSCHEL_BULKLEY = "Herschel-Bulkley"

class NozzleInput(BaseModel):
    size_in_32nds: int = Field(..., gt=0, description="Nozzle size in 1/32 inches (e.g., 12 for 12/32\")")

class WellSegment(BaseModel):
    name: str = Field(default="Segment", description="Segment identifier (e.g., Drill Pipe in 12.25in Hole)")
    length_ft: float = Field(..., gt=0, description="Length of this segment in feet")
    pipe_od_in: float = Field(..., gt=0, description="Outer diameter of drill pipe/collar in inches")
    pipe_id_in: float = Field(..., gt=0, description="Inner diameter of drill pipe/collar in inches")
    hole_id_in: float = Field(..., gt=0, description="Hole size or casing inner diameter in inches")
    mud_weight_ppg: float = Field(..., gt=0, description="Fluid density in ppg")
   
    # Rheological parameters
    viscosity_cp: float = Field(default=20.0, gt=0, description="Apparent or Plastic Viscosity (cP)")
    yield_point_lb_100ft2: float = Field(default=15.0, ge=0, description="Yield Point (lb/100ft²)")
    tau_0_lb_100ft2: float = Field(default=5.0, ge=0, description="Yield stress for Herschel-Bulkley (lb/100ft²)")
    n_index: float = Field(default=0.65, gt=0, le=1.0, description="Flow behavior index (n)")
    k_consistency: float = Field(default=300.0, gt=0, description="Consistency index (eq. cP or eq. mPa·s)")

# =====================================================================
# 2. Complete Physics & Hydraulics Engine
# =====================================================================
class DrillingHydraulicsEngine:
    """
    Industrial Drilling Hydraulics Physics Engine.
    Computes fluid velocities, regime-specific frictional pressure drops across
    multi-geometry wellbores, bit nozzle hydraulics, and Dynamic ECD.
    """

    def __init__(
        self,
        surface_mud_weight_ppg: float,
        flow_rate_gpm: float,
        total_depth_ft: float,
        rheology_model: RheologyModel = RheologyModel.BINGHAM_PLASTIC
    ):
        self.surface_mud_weight_ppg = surface_mud_weight_ppg
        self.flow_rate_gpm = flow_rate_gpm
        self.total_depth_ft = total_depth_ft
        self.rheology_model = rheology_model
        self.segments: List[WellSegment] = []
        self.nozzles: List[NozzleInput] = []

    def add_segment(self, segment: WellSegment) -> None:
        self.segments.append(segment)

    def add_nozzle(self, nozzle: NozzleInput) -> None:
        self.nozzles.append(nozzle)

    # -----------------------------------------------------------------
    # Velocity Computations
    # -----------------------------------------------------------------
    @staticmethod
    def calculate_pipe_velocity(flow_rate_gpm: float, pipe_id_in: float) -> float:
        """Calculates internal pipe velocity in ft/min."""
        pipe_area = math.pi * (pipe_id_in ** 2) / 4.0
        if pipe_area <= 0:
            raise ValueError("Pipe ID must be greater than 0.")
        return (24.51 * flow_rate_gpm) / (pipe_id_in ** 2)

    @staticmethod
    def calculate_annular_velocity(flow_rate_gpm: float, hole_id_in: float, pipe_od_in: float) -> float:
        """Calculates annular fluid velocity in ft/min."""
        annular_area = hole_id_in ** 2 - pipe_od_in ** 2
        if annular_area <= 0:
            raise ValueError("Hole ID must be strictly greater than Pipe OD.")
        return (24.51 * flow_rate_gpm) / annular_area

    # -----------------------------------------------------------------
    # Frictional Pressure Loss Computations (psi/ft)
    # -----------------------------------------------------------------
    def calculate_annular_friction_gradient(self, seg: WellSegment, v_ann_fpm: float) -> float:
        """
        Calculates annular friction pressure gradient (psi/ft) based on selected Rheology Model.
        """
        dh = seg.hole_id_in - seg.pipe_od_in  # Hydraulic diameter (inches)

        if self.rheology_model == RheologyModel.NEWTONIAN:
            # Standard Newtonian fluid flow
            return (seg.viscosity_cp * v_ann_fpm) / (1500 * (dh ** 2))

        elif self.rheology_model == RheologyModel.BINGHAM_PLASTIC:
            # API RP 13D Bingham Plastic model
            pv = seg.viscosity_cp
            yp = seg.yield_point_lb_100ft2
            return ((pv * v_ann_fpm) / (1000 * (dh ** 2))) + (yp / (200 * dh))

        elif self.rheology_model == RheologyModel.POWER_LAW:
            # Ostwald-de Waele Power Law model
            n = seg.n_index
            k = seg.k_consistency
            v_sec = v_ann_fpm / 60.0  # Convert to ft/s
            shear_rate = ((2 * n + 1) / (3 * n)) * ((12 * v_sec) / (dh / 12.0))
            tau = k * (shear_rate ** n)
            return (tau / (300 * dh))

        elif self.rheology_model == RheologyModel.HERSCHEL_BULKLEY:
            # Yield-Power-Law (Herschel-Bulkley) model
            n = seg.n_index
            k = seg.k_consistency
            tau_0 = seg.tau_0_lb_100ft2
            v_sec = v_ann_fpm / 60.0
            shear_rate = ((2 * n + 1) / (3 * n)) * ((12 * v_sec) / (dh / 12.0))
            tau = tau_0 + (k * (shear_rate ** n))
            return (tau / (300 * dh))

        return 0.0

    def calculate_pipe_friction_gradient(self, seg: WellSegment, v_pipe_fpm: float) -> float:
        """Calculates internal pipe friction pressure gradient (psi/ft)."""
        d_int = seg.pipe_id_in
        pv = seg.viscosity_cp
        yp = seg.yield_point_lb_100ft2
       
        # Bingham Plastic flow inside drill pipe
        return ((pv * v_pipe_fpm) / (1500 * (d_int ** 2))) + (yp / (225 * d_int))

    # -----------------------------------------------------------------
    # Bit Hydraulics & Nozzles
    # -----------------------------------------------------------------
    def calculate_bit_hydraulics(self, mud_weight_ppg: float) -> Dict[str, float]:
        """Calculates total nozzle area (TNA), pressure drop across the bit, JIF, and HHP."""
        if not self.nozzles:
            return {
                "tna_sq_in": 0.0,
                "bit_pressure_drop_psi": 0.0,
                "jet_velocity_fps": 0.0,
                "hydraulic_horsepower_hhp": 0.0,
                "jif_lbf": 0.0
            }

        # Total Nozzle Area (TNA) in square inches: TNA = sum(pi * (d_i / 64)^2)
        tna = sum(math.pi * ((n.size_in_32nds / 64.0) ** 2) for n in self.nozzles)
       
        if tna <= 0:
            return {"tna_sq_in": 0.0, "bit_pressure_drop_psi": 0.0, "jet_velocity_fps": 0.0, "hydraulic_horsepower_hhp": 0.0, "jif_lbf": 0.0}

        # Jet velocity (ft/s)
        v_jet = (0.3208 * self.flow_rate_gpm) / tna
       
        # Bit pressure loss (psi) using discharge coefficient Cd = 0.95
        bit_dp = (mud_weight_ppg * (self.flow_rate_gpm ** 2)) / (10858 * (tna ** 2))
       
        # Hydraulic Horsepower (HHP)
        hhp = (self.flow_rate_gpm * bit_dp) / 1714.0
       
        # Jet Impact Force (JIF) in lbf
        jif = (mud_weight_ppg * self.flow_rate_gpm * v_jet) / 1930.0

        return {
            "tna_sq_in": round(tna, 4),
            "bit_pressure_drop_psi": round(bit_dp, 2),
            "jet_velocity_fps": round(v_jet, 2),
            "hydraulic_horsepower_hhp": round(hhp, 2),
            "jif_lbf": round(jif, 2)
        }

    # -----------------------------------------------------------------
    # Cuttings Transport & Hole Cleaning Index
    # -----------------------------------------------------------------
    @staticmethod
    def calculate_cuttings_transport_ratio(v_ann_fpm: float, mud_weight_ppg: float, pv_cp: float) -> float:
        """
        Estimates Cuttings Transport Ratio (CTR) and slip velocity using Moore's correlation.
        """
        if v_ann_fpm <= 0:
            return 0.0
       
        # Particle slip velocity estimation (assuming average 0.25" cutting size, 2.65 SG)
        cutting_density_ppg = 22.1  # ~2.65 SG
        density_diff = cutting_density_ppg - mud_weight_ppg
       
        # Simplified slip velocity (ft/min)
        v_slip = (113.4 * (0.25 ** 0.66) * (density_diff ** 0.66)) / ((mud_weight_ppg ** 0.33) * (pv_cp ** 0.33))
       
        ctr = (v_ann_fpm - v_slip) / v_ann_fpm
        return max(0.0, min(round(ctr * 100, 2), 100.0))  # Percentage efficiency

    # -----------------------------------------------------------------
    # Primary Execution Engine
    # -----------------------------------------------------------------
    def solve() -> Dict[str, any]:
        """
        Executes multi-segment hydraulics calculations down the wellbore.
        Computes section-by-section annular loss, drillstring pressure loss,
        bit hydraulics, total SPP, and Dynamic Bottomhole ECD.
        """
        if not self.segments:
            raise ValueError("No wellbore segments provided for physics evaluation.")

        total_annular_dp_psi = 0.0
        total_pipe_dp_psi = 0.0
        total_hydrostatic_psi = 0.0
        segment_results = []
        cumulative_depth = 0.0

        for idx, seg in enumerate(self.segments):
            # 1. Velocities
            v_ann = self.calculate_annular_velocity(self.flow_rate_gpm, seg.hole_id_in, seg.pipe_od_in)
            v_pipe = self.calculate_pipe_velocity(self.flow_rate_gpm, seg.pipe_id_in)

            # 2. Segment Pressure Losses
            dp_dl_ann = self.calculate_annular_friction_gradient(seg, v_ann)
            dp_dl_pipe = self.calculate_pipe_friction_gradient(seg, v_pipe)

            seg_ann_loss = dp_dl_ann * seg.length_ft
            seg_pipe_loss = dp_dl_pipe * seg.length_ft
            seg_hydrostatic = 0.052 * seg.mud_weight_ppg * seg.length_ft

            total_annular_dp_psi += seg_ann_loss
            total_pipe_dp_psi += seg_pipe_loss
            total_hydrostatic_psi += seg_hydrostatic

            cumulative_depth += seg.length_ft

            # 3. Local Dynamic ECD at segment base
            local_ecd = seg.mud_weight_ppg + (total_annular_dp_psi / (0.052 * cumulative_depth))

            # 4. Hole Cleaning Transport Efficiency
            transport_eff = self.calculate_cuttings_transport_ratio(v_ann, seg.mud_weight_ppg, seg.viscosity_cp)

            segment_results.append({
                "segment_index": idx + 1,
                "segment_name": seg.name,
                "length_ft": seg.length_ft,
                "annular_velocity_fpm": round(v_ann, 2),
                "pipe_velocity_fpm": round(v_pipe, 2),
                "annular_loss_psi": round(seg_ann_loss, 2),
                "pipe_loss_psi": round(seg_pipe_loss, 2),
                "local_ecd_ppg": round(local_ecd, 3),
                "cuttings_transport_efficiency_pct": transport_eff
            })

        # Bit Hydraulics Calculations
        bit_results = self.calculate_bit_hydraulics(self.surface_mud_weight_ppg)

        # Standpipe Pressure (SPP) = Surface Loss + Drillstring Loss + Bit Loss + Annular Loss
        surface_equipment_loss = 50.0  # Constant estimate for standpipe, swivel, kelly
        total_spp_psi = surface_equipment_loss + total_pipe_dp_psi + bit_results["bit_pressure_drop_psi"] + total_annular_dp_psi

        # Final Bottomhole Equivalent Circulating Density (ECD)
        bottomhole_ecd = self.surface_density_contribution(total_annular_dp_psi)

        return {
            "rheology_model_used": self.rheology_model.value,
            "flow_rate_gpm": self.flow_rate_gpm,
            "total_depth_ft": self.total_depth_ft,
            "surface_mud_weight_ppg": self.surface_mud_weight_ppg,
            "bottomhole_ecd_ppg": round(bottomhole_ecd, 3),
            "standpipe_pressure_spp_psi": round(total_spp_psi, 2),
            "total_annular_pressure_loss_psi": round(total_annular_dp_psi, 2),
            "total_drillstring_pressure_loss_psi": round(total_pipe_dp_psi, 2),
            "bit_hydraulics": bit_results,
            "segment_breakdown": segment_results
        }

    def surface_density_contribution(self, total_annular_dp_psi: float) -> float:
        """Computes true bottomhole Equivalent Circulating Density (ECD)."""
        if self.total_depth_ft <= 0:
            return self.surface_mud_weight_ppg
        return self.surface_mud_weight_ppg + (total_annular_dp_psi / (0.052 * self.total_depth_ft))