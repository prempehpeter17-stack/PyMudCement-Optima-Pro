# physics.py
"""
Drilling Hydraulics Engine – PyMudCement Optima Pro
Bingham Plastic, Power Law, Herschel-Bulkley with laminar/turbulent
regime detection and proper TVD-based ECD.
"""
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
    length_ft: float = Field(..., ge=0, description="Length of segment in feet (MD)")
    pipe_od_in: float = Field(..., gt=0, description="Outer diameter of pipe in inches")
    pipe_id_in: float = Field(..., gt=0, description="Inner diameter of pipe in inches")
    hole_id_in: float = Field(..., gt=0, description="Hole size or casing ID in inches")
    mud_weight_ppg: float = Field(..., gt=0, description="Fluid density in ppg")
    viscosity_cp: float = Field(default=20.0, ge=0, description="Plastic Viscosity (cP)")
    yield_point_lb_100ft2: float = Field(default=15.0, ge=0, description="Yield Point (lb/100ft2)")
    tau_0_lb_100ft2: float = Field(default=5.0, ge=0, description="Yield stress for Herschel-Bulkley")
    n_index: float = Field(default=0.65, gt=0, le=1.0, description="Flow behavior index (n)")
    k_consistency: float = Field(default=300.0, gt=0, description="Consistency index")


class DrillingHydraulicsEngine:
    def __init__(
        self,
        surface_mud_weight_ppg: float,
        flow_rate_gpm: float,
        total_depth_ft: float,
        true_vertical_depth_ft: Optional[float] = None,
        plastic_viscosity_cp: float = 20.0,
        yield_point_lb_100ft2: float = 15.0,
        rheology_model: RheologyModel = RheologyModel.BINGHAM_PLASTIC,
    ):
        """
        total_depth_ft  = Measured Depth (MD)
        true_vertical_depth_ft = True Vertical Depth (TVD).
            If None, assumes vertical well (TVD = MD).
            ECD always uses TVD.
        """
        self.surface_mud_weight_ppg = max(0.1, surface_mud_weight_ppg)
        self.flow_rate_gpm = max(0.1, flow_rate_gpm)
        self.total_depth_ft = max(1.0, total_depth_ft)
        self.true_vertical_depth_ft = (
            max(1.0, true_vertical_depth_ft)
            if true_vertical_depth_ft is not None
            else self.total_depth_ft
        )
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

    @staticmethod
    def _reynolds_annular(mud_weight_ppg, v_fpm, dh_in, pv_cp, yp_lb100) -> float:
        if v_fpm <= 0 or dh_in <= 0:
            return 0.0
        effective_visc = pv_cp + (yp_lb100 * dh_in) / (5.0 * max(v_fpm, 0.1))
        return (928.0 * mud_weight_ppg * v_fpm * dh_in) / max(effective_visc, 0.1)

    @staticmethod
    def _reynolds_pipe(mud_weight_ppg, v_fpm, d_in, pv_cp, yp_lb100) -> float:
        if v_fpm <= 0 or d_in <= 0:
            return 0.0
        effective_visc = pv_cp + (yp_lb100 * d_in) / (6.0 * max(v_fpm, 0.1))
        return (928.0 * mud_weight_ppg * v_fpm * d_in) / max(effective_visc, 0.1)

    @staticmethod
    def _is_turbulent(re: float, critical_re: float = 2100.0) -> bool:
        return re > critical_re

    def calculate_annular_friction_gradient(self, seg: WellSegment, v_ann_fpm: float):
        dh = seg.hole_id_in - seg.pipe_od_in
        if dh <= 0:
            return 0.0, "N/A"

        re = self._reynolds_annular(
            seg.mud_weight_ppg, v_ann_fpm, dh,
            seg.viscosity_cp, seg.yield_point_lb_100ft2
        )
        turbulent = self._is_turbulent(re)

        if self.rheology_model == RheologyModel.NEWTONIAN:
            if turbulent:
                f = 0.0791 / (re ** 0.25) if re > 0 else 0.02
                dp_dl = (f * seg.mud_weight_ppg * (v_ann_fpm ** 2)) / (25.8 * dh)
            else:
                dp_dl = (seg.viscosity_cp * v_ann_fpm) / (1500 * (dh ** 2))
            return dp_dl, "Turbulent" if turbulent else "Laminar"

        elif self.rheology_model == RheologyModel.BINGHAM_PLASTIC:
            if turbulent:
                dp_dl = (
                    (seg.viscosity_cp ** 0.2)
                    * (seg.mud_weight_ppg ** 0.8)
                    * (v_ann_fpm ** 1.8)
                ) / (1800.0 * (dh ** 1.2))
            else:
                dp_dl = (
                    (seg.viscosity_cp * v_ann_fpm) / (1000.0 * (dh ** 2))
                    + seg.yield_point_lb_100ft2 / (200.0 * dh)
                )
            return dp_dl, "Turbulent" if turbulent else "Laminar"

        elif self.rheology_model == RheologyModel.POWER_LAW:
            n, k = seg.n_index, seg.k_consistency
            v_sec = v_ann_fpm / 60.0
            shear_rate = ((2 * n + 1) / (3 * n)) * ((12 * v_sec) / (dh / 12.0))
            dp_dl = (k * (shear_rate ** n)) / (300.0 * dh)
            return dp_dl, "Turbulent" if turbulent else "Laminar"

        elif self.rheology_model == RheologyModel.HERSCHEL_BULKLEY:
            n, k, tau_0 = seg.n_index, seg.k_consistency, seg.tau_0_lb_100ft2
            v_sec = v_ann_fpm / 60.0
            shear_rate = ((2 * n + 1) / (3 * n)) * ((12 * v_sec) / (dh / 12.0))
            dp_dl = (tau_0 + (k * (shear_rate ** n))) / (300.0 * dh)
            return dp_dl, "Turbulent" if turbulent else "Laminar"

        return 0.0, "N/A"

    def calculate_pipe_friction_gradient(self, seg: WellSegment, v_pipe_fpm: float):
        d_int = seg.pipe_id_in
        if d_int <= 0:
            return 0.0, "N/A"

        re = self._reynolds_pipe(
            seg.mud_weight_ppg, v_pipe_fpm, d_int,
            seg.viscosity_cp, seg.yield_point_lb_100ft2
        )
        turbulent = self._is_turbulent(re)

        if turbulent:
            dp_dl = (
                (seg.viscosity_cp ** 0.2)
                * (seg.mud_weight_ppg ** 0.8)
                * (v_pipe_fpm ** 1.8)
            ) / (1800.0 * (d_int ** 1.2))
        else:
            dp_dl = (
                (seg.viscosity_cp * v_pipe_fpm) / (1500.0 * (d_int ** 2))
                + seg.yield_point_lb_100ft2 / (225.0 * d_int)
            )
        return dp_dl, "Turbulent" if turbulent else "Laminar"

    @staticmethod
    def calculate_cuttings_slip_velocity(
        mud_weight_ppg: float,
        plastic_viscosity_cp: float,
        cuttings_diameter_in: float = 0.25,
        cuttings_density_ppg: float = 21.0,
    ) -> float:
        rho_f = mud_weight_ppg * 1000.0 / 8.34
        rho_p = cuttings_density_ppg * 1000.0 / 8.34
        d = cuttings_diameter_in * 0.0254
        mu = max(plastic_viscosity_cp * 0.001, 1e-6)
        g = 9.81
        v_stokes = (d ** 2 * (rho_p - rho_f) * g) / (18.0 * mu)
        v_slip_ms = v_stokes * 0.7
        return max(v_slip_ms * 196.85, 1.0)

    def calculate_bit_hydraulics(self, mud_weight_ppg: float) -> Dict[str, float]:
        empty = {
            "tna_sq_in": 0.0,
            "bit_pressure_drop_psi": 0.0,
            "jet_velocity_fps": 0.0,
            "hydraulic_horsepower_hhp": 0.0,
            "jif_lbf": 0.0,
        }
        if not self.nozzles:
            return empty

        tna = sum(math.pi * ((n.size_in_32nds / 64.0) ** 2) for n in self.nozzles)
        if tna <= 0:
            return empty

        v_jet = (0.3208 * self.flow_rate_gpm) / tna
        bit_dp = (mud_weight_ppg * (self.flow_rate_gpm ** 2)) / (10858.0 * (tna ** 2))
        hhp = (self.flow_rate_gpm * bit_dp) / 1714.0
        jif = (mud_weight_ppg * self.flow_rate_gpm * v_jet) / 1930.0

        return {
            "tna_sq_in": round(tna, 4),
            "bit_pressure_drop_psi": round(bit_dp, 2),
            "jet_velocity_fps": round(v_jet, 2),
            "hydraulic_horsepower_hhp": round(hhp, 2),
            "jif_lbf": round(jif, 2),
        }

    def solve(self) -> Dict[str, Any]:
        if not self.segments:
            raise ValueError("No wellbore segments provided for physics evaluation.")

        total_annular_dp_psi = 0.0
        total_pipe_dp_psi = 0.0
        segment_results = []
        cumulative_md = 0.0

        for idx, seg in enumerate(self.segments):
            v_ann = self.calculate_annular_velocity(
                self.flow_rate_gpm, seg.hole_id_in, seg.pipe_od_in
            )
            v_pipe = self.calculate_pipe_velocity(self.flow_rate_gpm, seg.pipe_id_in)

            dp_dl_ann, regime_ann = self.calculate_annular_friction_gradient(seg, v_ann)
            dp_dl_pipe, regime_pipe = self.calculate_pipe_friction_gradient(seg, v_pipe)

            seg_ann_loss = dp_dl_ann * seg.length_ft
            seg_pipe_loss = dp_dl_pipe * seg.length_ft

            total_annular_dp_psi += seg_ann_loss
            total_pipe_dp_psi += seg_pipe_loss
            cumulative_md += seg.length_ft

            local_ecd = seg.mud_weight_ppg + (
                total_annular_dp_psi / (0.052 * max(1.0, cumulative_md))
            )

            segment_results.append({
                "segment_index": idx + 1,
                "segment_name": seg.name,
                "length_ft": seg.length_ft,
                "annular_velocity_fpm": round(v_ann, 2),
                "pipe_velocity_fpm": round(v_pipe, 2),
                "annular_loss_psi": round(seg_ann_loss, 2),
                "pipe_loss_psi": round(seg_pipe_loss, 2),
                "annular_flow_regime": regime_ann,
                "pipe_flow_regime": regime_pipe,
                "local_ecd_ppg": round(local_ecd, 3),
            })

        bit_results = self.calculate_bit_hydraulics(self.surface_mud_weight_ppg)
        surface_equipment_loss = 50.0
        total_spp_psi = (
            surface_equipment_loss
            + total_pipe_dp_psi
            + bit_results["bit_pressure_drop_psi"]
            + total_annular_dp_psi
        )

        # ECD always uses True Vertical Depth
        bottomhole_ecd = self.surface_mud_weight_ppg + (
            total_annular_dp_psi / (0.052 * self.true_vertical_depth_ft)
        )

        return {
            "rheology_model_used": self.rheology_model.value,
            "flow_rate_gpm": round(self.flow_rate_gpm, 2),
            "total_depth_ft": round(self.total_depth_ft, 2),
            "true_vertical_depth_ft": round(self.true_vertical_depth_ft, 2),
            "surface_mud_weight_ppg": round(self.surface_mud_weight_ppg, 2),
            "plastic_viscosity_cp": round(self.plastic_viscosity_cp, 2),
            "yield_point_lb_100ft2": round(self.yield_point_lb_100ft2, 2),
            "equivalent_circulating_density_ecd_ppg": round(bottomhole_ecd, 3),
            "standpipe_pressure_spp_psi": round(total_spp_psi, 2),
            "total_annular_pressure_loss_psi": round(total_annular_dp_psi, 2),
            "total_pipe_pressure_loss_psi": round(total_pipe_dp_psi, 2),
            "bit_hydraulics": bit_results,
            "segment_breakdown": segment_results,
        }


class DiagnosticEngine:
    def __init__(self, ecd_upper_threshold_delta: float = 1.5, max_spp_limit: float = 3500.0):
        self.ecd_upper_threshold_delta = ecd_upper_threshold_delta
        self.max_spp_limit = max_spp_limit

    def analyze_telemetry(self, physics_metrics: Dict[str, Any], historical_esd: float) -> Dict[str, Any]:
        ecd = physics_metrics.get("equivalent_circulating_density_ecd_ppg", 0.0)
        spp = physics_metrics.get("standpipe_pressure_spp_psi", 0.0)

        severity = "GREEN"
        status_msg = "SUCCESS"
        matched_hazard = "None"
        recommendations = [
            "Maintain current drilling parameters and pump SPM.",
            "Continue regular monitoring of shaker cuttings and torque/drag trends.",
        ]

        if ecd > (historical_esd + self.ecd_upper_threshold_delta):
            severity = "RED"
            matched_hazard = "Excessive ECD / High Risk of Formation Fracturing"
            recommendations = [
                "Reduce flow rate (GPM) or pump speed to lower annular friction pressure drop.",
                "Dilute or treat mud to lower Plastic Viscosity (PV) and Yield Point (YP).",
                "Verify hole cleaning status; check for cuttings pack-off along the annulus.",
            ]
        elif spp > self.max_spp_limit:
            severity = "YELLOW"
            matched_hazard = "High Standpipe Pressure (SPP Warning)"
            recommendations = [
                "Check standpipe manifold and surface line valve alignments.",
                "Inspect bit nozzles for partial plugging or balling.",
                "Verify drill string internal restrictions.",
            ]

        return {
            "status": status_msg,
            "severity": severity,
            "matched_hazard": matched_hazard,
            "detailed_diagnosis": (
                f"Operating ECD is {ecd:.2f} ppg (Surface Mud Weight: {historical_esd:.2f} ppg) "
                f"with Standpipe Pressure at {spp:.1f} psi."
            ),
            "actionable_recommendations": recommendations,
        }
