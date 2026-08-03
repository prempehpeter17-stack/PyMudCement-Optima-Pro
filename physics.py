# physics_engine.py
import math
import logging
from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger("PyMudCementOptimaPro.PhysicsEngine")

class RheologyModel(str, Enum):
    NEWTONIAN = "Newtonian"
    BINGHAM_PLASTIC = "Bingham Plastic"
    POWER_LAW = "Power Law"
    HERSCHEL_BULKLEY = "Herschel-Bulkley"

class NozzleInput(BaseModel):
    size_in_32nds: int = Field(..., gt=0, description="Nozzle size in 1/32 inches")

class WellSegment(BaseModel):
    name: str = Field(default="Segment", description="Segment identifier")
    length_ft: float = Field(..., ge=0, description="Length of segment in feet")
    pipe_od_in: float = Field(..., gt=0, description="Outer diameter of pipe in inches")
    pipe_id_in: float = Field(..., gt=0, description="Inner diameter of pipe in inches")
    hole_id_in: float = Field(..., gt=0, description="Hole size or casing ID in inches")
    mud_weight_ppg: float = Field(..., gt=0, description="Fluid density in ppg")
    viscosity_cp: float = Field(default=20.0, ge=0, description="Plastic Viscosity (cP)")
    yield_point_lb_100ft2: float = Field(default=15.0, ge=0, description="Yield Point (lb/100ft²)")
    tau_0_lb_100ft2: float = Field(default=5.0, ge=0, description="Yield stress for Herschel-Bulkley")
    n_index: float = Field(default=0.65, gt=0, le=1.0, description="Flow behavior index (n)")
    k_consistency: float = Field(default=300.0, gt=0, description="Consistency index")

class DrillingHydraulicsEngine:
    def __init__(
        self,
        surface_mud_weight_ppg: float,
        flow_rate_gpm: float,
        total_depth_ft: float,
        plastic_viscosity_cp: float = 20.0,
        yield_point_lb_100ft2: float = 15.0,
        rheology_model: RheologyModel = RheologyModel.BINGHAM_PLASTIC
    ):
        self.surface_mud_weight_ppg = max(0.1, surface_mud_weight_ppg)
        self.flow_rate_gpm = max(0.1, flow_rate_gpm)
        self.total_depth_ft = max(1.0, total_depth_ft)
        self.plastic_viscosity_cp = plastic_viscosity_cp
        self.yield_point_lb_100ft2 = yield_point_lb_100ft2
        self.rheology_model = rheology_model
        self.segments: List[WellSegment] = []
        self.nozzles: List[NozzleInput] = []

    def add_segment(self, segment: WellSegment) -> None:
        self.segments.append(segment)

    def add_nozzle(self, nozzle: NozzleInput) -> None:
        self.nozzles.append(nozzle)

    @staticmethod
    def calculate_pipe_velocity(flow_rate_gpm: float, pipe_id_in: float) -> float:
        if pipe_id_in <= 0:
            raise ValueError("Pipe ID must be strictly greater than 0.")
        return (24.51 * flow_rate_gpm) / (pipe_id_in ** 2)

    @staticmethod
    def calculate_annular_velocity(flow_rate_gpm: float, hole_id_in: float, pipe_od_in: float) -> float:
        annular_area = hole_id_in ** 2 - pipe_od_in ** 2
        if annular_area <= 0:
            raise ValueError("Hole ID must be strictly greater than Pipe OD.")
        return (24.51 * flow_rate_gpm) / annular_area

    def calculate_annular_friction_gradient(self, seg: WellSegment, v_ann_fpm: float) -> float:
        dh = seg.hole_id_in - seg.pipe_od_in
        if dh <= 0:
            return 0.0

        if self.rheology_model == RheologyModel.NEWTONIAN:
            return (seg.viscosity_cp * v_ann_fpm) / (1500 * (dh ** 2))
        elif self.rheology_model == RheologyModel.BINGHAM_PLASTIC:
            return ((seg.viscosity_cp * v_ann_fpm) / (1000 * (dh ** 2))) + (seg.yield_point_lb_100ft2 / (200 * dh))
        elif self.rheology_model == RheologyModel.POWER_LAW:
            n, k = seg.n_index, seg.k_consistency
            v_sec = v_ann_fpm / 60.0
            shear_rate = ((2 * n + 1) / (3 * n)) * ((12 * v_sec) / (dh / 12.0))
            return (k * (shear_rate ** n)) / (300 * dh)
        elif self.rheology_model == RheologyModel.HERSCHEL_BULKLEY:
            n, k, tau_0 = seg.n_index, seg.k_consistency, seg.tau_0_lb_100ft2
            v_sec = v_ann_fpm / 60.0
            shear_rate = ((2 * n + 1) / (3 * n)) * ((12 * v_sec) / (dh / 12.0))
            return (tau_0 + (k * (shear_rate ** n))) / (300 * dh)
        return 0.0

    def calculate_pipe_friction_gradient(self, seg: WellSegment, v_pipe_fpm: float) -> float:
        d_int = seg.pipe_id_in
        if d_int <= 0:
            return 0.0
        return ((seg.viscosity_cp * v_pipe_fpm) / (1500 * (d_int ** 2))) + (seg.yield_point_lb_100ft2 / (225 * d_int))

    def calculate_bit_hydraulics(self, mud_weight_ppg: float) -> Dict[str, float]:
        if not self.nozzles:
            return {"tna_sq_in": 0.0, "bit_pressure_drop_psi": 0.0, "jet_velocity_fps": 0.0, "hydraulic_horsepower_hhp": 0.0, "jif_lbf": 0.0}

        tna = sum(math.pi * ((n.size_in_32nds / 64.0) ** 2) for n in self.nozzles)
        if tna <= 0:
            return {"tna_sq_in": 0.0, "bit_pressure_drop_psi": 0.0, "jet_velocity_fps": 0.0, "hydraulic_horsepower_hhp": 0.0, "jif_lbf": 0.0}

        v_jet = (0.3208 * self.flow_rate_gpm) / tna
        bit_dp = (mud_weight_ppg * (self.flow_rate_gpm ** 2)) / (10858 * (tna ** 2))
        hhp = (self.flow_rate_gpm * bit_dp) / 1714.0
        jif = (mud_weight_ppg * self.flow_rate_gpm * v_jet) / 1930.0

        return {
            "tna_sq_in": round(tna, 4),
            "bit_pressure_drop_psi": round(bit_dp, 2),
            "jet_velocity_fps": round(v_jet, 2),
            "hydraulic_horsepower_hhp": round(hhp, 2),
            "jif_lbf": round(jif, 2)
        }

    def solve(self) -> Dict[str, Any]:
        if not self.segments:
            raise ValueError("No wellbore segments provided for physics evaluation.")

        total_annular_dp_psi = 0.0
        total_pipe_dp_psi = 0.0
        segment_results = []
        cumulative_depth = 0.0

        for idx, seg in enumerate(self.segments):
            v_ann = self.calculate_annular_velocity(self.flow_rate_gpm, seg.hole_id_in, seg.pipe_od_in)
            v_pipe = self.calculate_pipe_velocity(self.flow_rate_gpm, seg.pipe_id_in)

            dp_dl_ann = self.calculate_annular_friction_gradient(seg, v_ann)
            dp_dl_pipe = self.calculate_pipe_friction_gradient(seg, v_pipe)

            seg_ann_loss = dp_dl_ann * seg.length_ft
            seg_pipe_loss = dp_dl_pipe * seg.length_ft

            total_annular_dp_psi += seg_ann_loss
            total_pipe_dp_psi += seg_pipe_loss
            cumulative_depth += seg.length_ft

            local_ecd = seg.mud_weight_ppg + (total_annular_dp_psi / (0.052 * max(1.0, cumulative_depth)))

            segment_results.append({
                "segment_index": idx + 1,
                "segment_name": seg.name,
                "length_ft": seg.length_ft,
                "annular_velocity_fpm": round(v_ann, 2),
                "pipe_velocity_fpm": round(v_pipe, 2),
                "annular_loss_psi": round(seg_ann_loss, 2),
                "pipe_loss_psi": round(seg_pipe_loss, 2),
                "local_ecd_ppg": round(local_ecd, 3)
            })

        bit_results = self.calculate_bit_hydraulics(self.surface_mud_weight_ppg)
        surface_equipment_loss = 50.0
        total_spp_psi = surface_equipment_loss + total_pipe_dp_psi + bit_results["bit_pressure_drop_psi"] + total_annular_dp_psi
        bottomhole_ecd = self.surface_mud_weight_ppg + (total_annular_dp_psi / (0.052 * self.total_depth_ft))

        return {
            "rheology_model_used": self.rheology_model.value,
            "flow_rate_gpm": round(self.flow_rate_gpm, 2),
            "total_depth_ft": round(self.total_depth_ft, 2),
            "surface_mud_weight_ppg": round(self.surface_mud_weight_ppg, 2),
            "plastic_viscosity_cp": round(self.plastic_viscosity_cp, 2),
            "yield_point_lb_100ft2": round(self.yield_point_lb_100ft2, 2),
            "equivalent_circulating_density_ecd_ppg": round(bottomhole_ecd, 3),
            "standpipe_pressure_spp_psi": round(total_spp_psi, 2),
            "total_annular_pressure_loss_psi": round(total_annular_dp_psi, 2),
            "total_pipe_pressure_loss_psi": round(total_pipe_dp_psi, 2),
            "bit_hydraulics": bit_results,
            "segment_breakdown": segment_results
        }