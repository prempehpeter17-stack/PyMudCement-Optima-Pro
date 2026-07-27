import logging
from typing import Dict, Any, List, Optional
from enum import Enum 

logger = logging.getLogger("PyMudCementOptimaPro.AIEngine") 

class RheologyModel(str, Enum):
    BINGHAM_PLASTIC = "Bingham Plastic"
    HERSCHEL_BULKLEY = "Herschel-Bulkley"
    POWER_LAW = "Power Law" 

class WellSegment:
    """Represents a discrete section of the drill string or wellbore geometry."""
    def __init__(
        self,
        name: str,
        length_ft: float,
        pipe_od_in: float,
        pipe_id_in: float,
        hole_id_in: float,
        mud_weight_ppg: float
    ):
        self.name = name
        self.length_ft = max(0.0, length_ft)
        self.pipe_od_in = max(0.1, pipe_od_in)
        self.pipe_id_in = max(0.1, pipe_id_in)
        self.hole_id_in = max(0.1, hole_id_in)
        self.mud_weight_ppg = max(0.0, mud_weight_ppg) 

class DrillingHydraulicsEngine:
    """Physics-based calculations engine for wellbore hydraulics and pressure losses."""
    def __init__(
        self,
        surface_mud_weight_ppg: float,
        flow_rate_gpm: float,
        total_depth_ft: float,
        plastic_viscosity_cp: float = 20.0,
        yield_point_lb_100ft2: float = 15.0,
        rheology_model: RheologyModel = RheologyModel.BINGHAM_PLASTIC
    ):
        self.surface_mud_weight_ppg = surface_mud_weight_ppg
        self.flow_rate_gpm = flow_rate_gpm
        self.total_depth_ft = max(1.0, total_depth_ft)
        self.plastic_viscosity_cp = plastic_viscosity_cp
        self.yield_point_lb_100ft2 = yield_point_lb_100ft2
        self.rheology_model = rheology_model
        self.segments: List[WellSegment] = [] 

    def add_segment(self, segment: WellSegment) -> None:
        """Adds a well segment to the drill string model."""
        self.segments.append(segment) 

    def solve(self) -> Dict[str, Any]:
        """Calculates segment-by-segment pressure losses, total SPP, and ECD."""
        total_annular_loss = 0.0
        total_pipe_loss = 0.0 

        for seg in self.segments:
            # Annular Velocity (ft/min)
            annular_area = max(0.001, (seg.hole_id_in**2 - seg.pipe_od_in**2))
            annular_velocity = (24.5 * self.flow_rate_gpm) / annular_area 

            # Bingham Plastic Hydraulics Formulation
            annular_loss = (
                (self.plastic_viscosity_cp * annular_velocity) / (1000 * (seg.hole_id_in - seg.pipe_od_in)**2) +
                (self.yield_point_lb_100ft2 / (225 * (seg.hole_id_in - seg.pipe_od_in)))
            ) * (seg.length_ft / 1000) 

            pipe_velocity = (24.5 * self.flow_rate_gpm) / max(0.001, seg.pipe_id_in**2)
            pipe_loss = (
                (self.plastic_viscosity_cp * pipe_velocity) / (1000 * seg.pipe_id_in**2)
            ) * (seg.length_ft / 1000) 

            total_annular_loss += max(5.0, annular_loss)
            total_pipe_loss += max(20.0, pipe_loss) 

        # Standpipe Pressure (SPP) including bit nozzle pressure drop estimate (~300 psi)
        spp = total_annular_loss + total_pipe_loss + 300.0
        
        # Equivalent Circulating Density (ECD)
        ecd = self.surface_mud_weight_ppg + (total_annular_loss / (0.052 * self.total_depth_ft)) 

        return {
            "flow_rate_gpm": round(self.flow_rate_gpm, 2),
            "total_depth_ft": round(self.total_depth_ft, 2),
            "surface_mud_weight_ppg": round(self.surface_mud_weight_ppg, 2),
            "plastic_viscosity_cp": round(self.plastic_viscosity_cp, 2),
            "yield_point_lb_100ft2": round(self.yield_point_lb_100ft2, 2),
            "total_annular_pressure_loss_psi": round(total_annular_loss, 2),
            "total_pipe_pressure_loss_psi": round(total_pipe_loss, 2),
            "standpipe_pressure_spp_psi": round(spp, 2),
            "equivalent_circulating_density_ecd_ppg": round(ecd, 2)
        } 

class DiagnosticEngine:
    """AI Telemetry Diagnostic Module for Hazard Analysis & Operational Recommendations."""
    def __init__(self, ecd_upper_threshold_delta: float = 1.5, max_spp_limit: float = 3500.0):
        self.ecd_upper_threshold_delta = ecd_upper_threshold_delta
        self.max_spp_limit = max_spp_limit 

    def analyze_telemetry(self, physics_metrics: Dict[str, Any], historical_esd: float) -> Dict[str, Any]:
        """Evaluates physics results against operational safety bounds and generates advice."""
        ecd = physics_metrics.get("equivalent_circulating_density_ecd_ppg", 0.0)
        spp = physics_metrics.get("standpipe_pressure_spp_psi", 0.0) 

        severity = "GREEN"
        status_msg = "SUCCESS"
        matched_hazard = "None"
        recommendations = [
            "Maintain current drilling parameters and pump SPM.",
            "Continue regular monitoring of shaker cuttings and torque/drag trends."
        ] 

        # Hazard Rule Checks
        if ecd > (historical_esd + self.ecd_upper_threshold_delta):
            severity = "RED"
            matched_hazard = "Excessive ECD / High Risk of Formation Fracturing"
            recommendations = [
                "Reduce flow rate (GPM) or pump speed to lower annular friction pressure drop.",
                "Dilute or treat mud to lower Plastic Viscosity (PV) and Yield Point (YP).",
                "Verify hole cleaning status; check for cuttings pack-off along the annulus."
            ]
        elif spp > self.max_spp_limit:
            severity = "YELLOW"
            matched_hazard = "High Standpipe Pressure (SPP Warning)"
            recommendations = [
                "Check standpipe manifold and surface line valve alignments.",
                "Inspect bit nozzles for partial plugging or balling.",
                "Verify drill string internal restrictions."
            ] 

        return {
            "status": status_msg,
            "severity": severity,
            "matched_hazard": matched_hazard,
            "detailed_diagnosis": (
                f"Operating ECD is {ecd:.2f} ppg (Surface Mud Weight: {historical_esd:.2f} ppg) "
                f"with Standpipe Pressure at {spp:.1f} psi."
            ),
            "actionable_recommendations": recommendations
        }
