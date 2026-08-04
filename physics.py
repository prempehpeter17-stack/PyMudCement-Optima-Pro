import math
import copy
import logging
from enum import Enum
from functools import lru_cache
from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Tuple, TypedDict
from pydantic import BaseModel, Field

# Logger configuration
logger = logging.getLogger("PyMudCementOptimaPro.IndustrialEngine")


# ==============================================================================
# CONFIGURABLE ENGINEERING CONSTANTS
# ==============================================================================
@dataclass(frozen=True)
class EngineConfig:
    velocity_constant: float = 24.51           # Converts GPM and area (in²) to ft/min
    flow_conversion_fps: float = 0.3208         # Converts GPM and area (in²) to ft/sec
    nozzle_area_constant: float = 64.0          # Nozzle size denominator (in 1/32nd inch units)
    hydrostatic_factor: float = 0.052           # Converts ppg * ft to psi pressure gradient
    bit_pressure_constant: float = 10858.0      # API orifice flow constant
    hhp_constant: float = 1714.0                # Converts GPM * psi to Horsepower (hp)
    jet_impact_force_constant: float = 1930.0   # Impact force factor
    cuttings_density_default_ppg: float = 21.7  # Default drill solids density (~2.6g/cc)
    temp_coefficient: float = 0.008             # Default thermal viscosity decay factor (/°F)


DEFAULT_CONFIG = EngineConfig()


# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================
@lru_cache(maxsize=128)
def calculate_cross_sectional_area(diameter_in: float) -> float:
    """Calculates cross-sectional area (in sq. inches) for a given diameter."""
    if diameter_in <= 0:
        return 0.0
    return math.pi * (diameter_in ** 2) / 4.0


# ==============================================================================
# ENUMS AND TYPED DICTS
# ==============================================================================
class RheologyModel(str, Enum):
    NEWTONIAN = "Newtonian"
    BINGHAM_PLASTIC = "Bingham Plastic"
    POWER_LAW = "Power Law"
    HERSCHEL_BULKLEY = "Herschel-Bulkley"


class FlowRegime(str, Enum):
    LAMINAR = "Laminar"
    TRANSITION = "Transition"
    TURBULENT = "Turbulent"


class BitHydraulicsResult(TypedDict):
    tna_sq_in: float
    bit_pressure_drop_psi: float
    jet_velocity_fps: float
    hhp: float
    jif_lbf: float
    hsi: float
    bit_pressure_ratio_pct: float


class SegmentCalculationResult(TypedDict):
    segment_index: int
    segment_name: str
    annular_regime: str
    pipe_regime: str
    annular_loss_psi: float
    pipe_loss_psi: float
    transport_ratio: float
    cuttings_concentration_pct: float
    local_ecd_ppg: float


# ==============================================================================
# FANN VISCOMETER DIAL READER MODULE (NEW INDUSTRIAL FEATURE)
# ==============================================================================
class ViscometerReadings(BaseModel):
    r600: float = Field(..., gt=0, description="Dial reading at 600 RPM")
    r300: float = Field(..., gt=0, description="Dial reading at 300 RPM")
    r200: Optional[float] = Field(None, gt=0, description="Dial reading at 200 RPM")
    r100: Optional[float] = Field(None, gt=0, description="Dial reading at 100 RPM")
    r6: Optional[float] = Field(None, gt=0, description="Dial reading at 6 RPM")
    r3: Optional[float] = Field(None, gt=0, description="Dial reading at 3 RPM")


class ViscometerReader:
    """
    Fits raw Fann 35 rotational viscometer dial readings to Rheology Model parameters
    per API RP 13D guidelines.
    """

    @staticmethod
    def fit_bingham_plastic(readings: ViscometerReadings) -> Dict[str, float]:
        """Calculates Plastic Viscosity (cP) and Yield Point (lb/100ft²)."""
        pv = max(1.0, readings.r600 - readings.r300)
        yp = max(0.0, readings.r300 - pv)
        return {"plastic_viscosity_cp": pv, "yield_point_lb_100ft2": yp}

    @staticmethod
    def fit_power_law(readings: ViscometerReadings) -> Dict[str, float]:
        """Calculates Flow Behavior Index (n) and Consistency Index (K)."""
        n = 3.32 * math.log10(readings.r600 / readings.r300)
        n = min(1.0, max(0.1, n))
        k = (511.0 * readings.r300) / (511.0 ** n)
        return {"n_index": round(n, 4), "k_consistency": round(k, 2)}

    @staticmethod
    def fit_herschel_bulkley(readings: ViscometerReadings) -> Dict[str, float]:
        """Calculates Yield Stress (tau_0), n_index, and K_consistency."""
        r3 = readings.r3 if readings.r3 is not None else max(1.0, readings.r300 * 0.05)
        tau_0 = max(0.0, (2.0 * r3) - readings.r6) if readings.r6 is not None else max(0.0, r3)
        
        r600_adj = max(1.0, readings.r600 - tau_0)
        r300_adj = max(1.0, readings.r300 - tau_0)
        
        n_hb = 3.32 * math.log10(r600_adj / r300_adj)
        n_hb = min(1.0, max(0.1, n_hb))
        k_hb = (511.0 * r300_adj) / (511.0 ** n_hb)
        
        return {
            "tau_0_lb_100ft2": round(tau_0, 2),
            "n_index": round(n_hb, 4),
            "k_consistency": round(k_hb, 2)
        }


# ==============================================================================
# INPUT MODELS
# ==============================================================================
class NozzleInput(BaseModel):
    size_in_32nds: int = Field(..., gt=0, description="Nozzle size in 1/32 inches")


class WellSegment(BaseModel):
    name: str = Field(default="Segment", description="Segment identifier")
    length_ft: float = Field(..., ge=0, description="Measured length of segment in feet")
    inclination_deg: float = Field(default=0.0, ge=0.0, le=90.0, description="Average inclination angle")
    tvd_start_ft: float = Field(default=0.0, ge=0.0, description="TVD at start of segment")
    tvd_end_ft: float = Field(default=0.0, ge=0.0, description="TVD at end of segment")
    
    pipe_od_in: float = Field(..., gt=0, description="Outer diameter of pipe in inches")
    pipe_id_in: float = Field(..., gt=0, description="Inner diameter of pipe in inches")
    hole_id_in: float = Field(..., gt=0, description="Hole size or casing ID in inches")
    
    mud_weight_ppg: float = Field(..., gt=0, description="Base fluid density in ppg")
    viscosity_cp: float = Field(default=20.0, ge=0, description="Plastic Viscosity or Newtonian Viscosity (cP)")
    yield_point_lb_100ft2: float = Field(default=15.0, ge=0, description="Yield Point (lb/100ft²)")
    tau_0_lb_100ft2: float = Field(default=5.0, ge=0, description="Yield stress for Herschel-Bulkley")
    n_index: float = Field(default=0.65, gt=0, le=1.0, description="Flow behavior index (n)")
    k_consistency: float = Field(default=300.0, gt=0, description="Consistency index")
    
    pipe_roughness_in: float = Field(default=0.0018, ge=0, description="Absolute commercial steel roughness (in)")


class CuttingsParameters(BaseModel):
    rop_ft_hr: float = Field(default=60.0, ge=0, description="Rate of Penetration (ft/hr)")
    cuttings_density_ppg: float = Field(default=DEFAULT_CONFIG.cuttings_density_default_ppg, gt=0)
    cuttings_diameter_in: float = Field(default=0.25, gt=0, description="Average cutting particle size")
    pipe_rotation_rpm: float = Field(default=120.0, ge=0, description="String rotation speed (RPM)")
    annular_eccentricity: float = Field(default=0.2, ge=0.0, le=1.0, description="Pipe eccentricity factor")


class PumpEfficiencyModel(BaseModel):
    volumetric_efficiency: float = Field(default=0.95, gt=0, le=1.0)
    mechanical_efficiency: float = Field(default=0.90, gt=0, le=1.0)


# ==============================================================================
# VALIDATION LAYER
# ==============================================================================
class EngineeringValidator:
    """Validation engine for detecting physical, geometric, and operational anomalies."""

    @staticmethod
    def validate_all(
        segments: List[WellSegment],
        surface_mw_ppg: float,
        flow_rate_gpm: float,
        total_md_ft: float,
        total_tvd_ft: float,
        nozzles: List[NozzleInput]
    ) -> List[str]:
        warnings = []
        
        if not (6.0 <= surface_mw_ppg <= 25.0):
            warnings.append(f"Surface mud weight ({surface_mw_ppg} ppg) is outside realistic limits (6-25 ppg).")

        if flow_rate_gpm <= 0:
            warnings.append("Flow rate must be strictly positive.")

        if total_tvd_ft > total_md_ft:
            warnings.append(f"Physical anomaly: Total TVD ({total_tvd_ft} ft) cannot exceed Total MD ({total_md_ft} ft).")

        total_segment_length = sum(s.length_ft for s in segments)
        if segments and not math.isclose(total_segment_length, total_md_ft, rel_tol=1e-2):
            warnings.append(f"Segment MD sum ({total_segment_length:.1f} ft) does not match total MD ({total_md_ft:.1f} ft).")

        for s in segments:
            if s.pipe_od_in >= s.hole_id_in:
                warnings.append(f"[{s.name}] Invalid Geometry: Pipe OD ({s.pipe_od_in}\") >= Hole ID ({s.hole_id_in}\").")
            if s.pipe_id_in >= s.pipe_od_in:
                warnings.append(f"[{s.name}] Invalid Geometry: Pipe ID ({s.pipe_id_in}\") >= Pipe OD ({s.pipe_od_in}\").")

        if nozzles:
            tna = sum(calculate_cross_sectional_area(n.size_in_32nds / 32.0) for n in nozzles)
            if tna <= 0.05 or tna >= 3.0:
                warnings.append(f"Unusual Total Nozzle Area ({tna:.3f} sq in). Check nozzle sizes.")

        return warnings


# ==============================================================================
# FLUID MECHANICS CORE (API RP 13D)
# ==============================================================================
class FluidMechanicsCore:
    """Core fluid mechanics formulas using API RP 13D specifications."""

    @staticmethod
    def adjust_viscosity_for_temperature(
        base_viscosity_cp: float, 
        surface_temp_f: float, 
        segment_temp_f: float,
        config: EngineConfig = DEFAULT_CONFIG
    ) -> float:
        delta_t = max(0.0, segment_temp_f - surface_temp_f)
        return max(1.0, base_viscosity_cp * math.exp(-config.temp_coefficient * delta_t))

    @staticmethod
    def calculate_generalized_reynolds_annulus(
        density_ppg: float,
        v_fpm: float,
        dh_in: float,
        n: float,
        k: float,
        config: EngineConfig = DEFAULT_CONFIG
    ) -> float:
        if dh_in <= 0 or v_fpm <= 0:
            return 0.0
        v_fps = v_fpm / 60.0
        kp = k * ((2.0 * n + 1.0) / (3.0 * n)) ** n
        re_gen = (12.0 ** n) * (v_fps ** (2.0 - n)) * (dh_in ** n) * (density_ppg * config.hydrostatic_factor) / (kp * 0.0208)
        return max(1.0, re_gen)

    @staticmethod
    def calculate_generalized_reynolds_pipe(
        density_ppg: float,
        v_fpm: float,
        d_in: float,
        n: float,
        k: float,
        config: EngineConfig = DEFAULT_CONFIG
    ) -> float:
        if d_in <= 0 or v_fpm <= 0:
            return 0.0
        v_fps = v_fpm / 60.0
        kp = k * ((3.0 * n + 1.0) / (4.0 * n)) ** n
        re_gen = (8.0 ** (n - 1.0)) * (density_ppg * config.hydrostatic_factor) * (v_fps ** (2.0 - n)) * (d_in ** n) / (kp * 0.0208)
        return max(1.0, re_gen)

    @staticmethod
    def determine_flow_regime(reynolds: float) -> FlowRegime:
        if reynolds < 2100.0:
            return FlowRegime.LAMINAR
        elif reynolds <= 3000.0:
            return FlowRegime.TRANSITION
        return FlowRegime.TURBULENT

    @staticmethod
    def solve_colebrook_fanning_friction(reynolds: float, relative_roughness: float) -> float:
        if reynolds < 2100.0:
            return 16.0 / reynolds

        f = 0.0055 * (1.0 + (20000.0 * relative_roughness + 10.0**6 / reynolds) ** (1.0 / 3.0))
        for _ in range(20):
            if f <= 0:
                f = 0.001
            fn = -2.0 * math.log10((relative_roughness / 3.7) + (2.51 / (reynolds * math.sqrt(f))))
            lhs = 1.0 / math.sqrt(f)
            diff = lhs - fn
            if abs(diff) < 1e-6:
                break
            f -= diff * (-0.5 * (f ** -1.5))

        return f / 4.0

    @staticmethod
    def calculate_fanning_friction_factor(
        reynolds: float, 
        n: float, 
        d_in: float, 
        roughness_in: float
    ) -> Tuple[float, FlowRegime]:
        regime = FluidMechanicsCore.determine_flow_regime(reynolds)
        rel_roughness = roughness_in / max(0.001, d_in)

        if regime == FlowRegime.LAMINAR:
            fanning_f = 16.0 / reynolds
        elif regime == FlowRegime.TRANSITION:
            f_lam = 16.0 / 2100.0
            f_turb = FluidMechanicsCore.solve_colebrook_fanning_friction(3000.0, rel_roughness)
            w = (reynolds - 2100.0) / (3000.0 - 2100.0)
            fanning_f = f_lam + w * (f_turb - f_lam)
        else:
            fanning_f = FluidMechanicsCore.solve_colebrook_fanning_friction(reynolds, rel_roughness) / (n ** 0.15)

        return fanning_f, regime


# ==============================================================================
# CUTTINGS TRANSPORT MODULE
# ==============================================================================
class CuttingsTransportEngine:
    """Hole cleaning, particle slip velocity, and bed transport module."""

    @staticmethod
    def analyze_hole_cleaning(
        seg: WellSegment,
        v_ann_fpm: float,
        cuttings: CuttingsParameters,
        temp_viscosity_cp: float
    ) -> Dict[str, float]:
        particle_diameter_ft = cuttings.cuttings_diameter_in / 12.0
        density_diff = cuttings.cuttings_density_ppg - seg.mud_weight_ppg

        v_slip_fps = 0.082 * (max(0.1, density_diff) ** 0.667) * (particle_diameter_ft ** 0.4) / (
            (seg.mud_weight_ppg ** 0.333) * ((temp_viscosity_cp / 1000.0) ** 0.333)
        ) if density_diff > 0 else 0.0
        
        v_slip_fpm = v_slip_fps * 60.0

        inclination_rad = math.radians(seg.inclination_deg)
        angle_penalty = 1.0 + (0.5 * math.sin(inclination_rad))
        eccentricity_penalty = 1.0 + (0.3 * cuttings.annular_eccentricity)
        rotation_lift_fpm = (cuttings.pipe_rotation_rpm * seg.pipe_od_in / 12.0) * 0.1
        
        adjusted_slip_fpm = max(0.0, (v_slip_fpm * angle_penalty * eccentricity_penalty) - rotation_lift_fpm)

        net_transport_velocity = v_ann_fpm - adjusted_slip_fpm
        transport_ratio = max(0.0, net_transport_velocity / max(0.1, v_ann_fpm))

        ann_area_sq_ft = (calculate_cross_sectional_area(seg.hole_id_in) - calculate_cross_sectional_area(seg.pipe_od_in)) / 144.0
        gen_rate_cuft_min = (calculate_cross_sectional_area(seg.hole_id_in) / 144.0) * (cuttings.rop_ft_hr / 60.0)

        cuttings_concentration = (gen_rate_cuft_min / (ann_area_sq_ft * net_transport_velocity)) if net_transport_velocity > 0 and ann_area_sq_ft > 0 else 0.15

        effective_mix_density_ppg = (seg.mud_weight_ppg * (1.0 - cuttings_concentration)) + (
            cuttings.cuttings_density_ppg * cuttings_concentration
        )

        return {
            "slip_velocity_fpm": round(adjusted_slip_fpm, 2),
            "transport_ratio": round(transport_ratio, 3),
            "cuttings_concentration_pct": round(cuttings_concentration * 100.0, 2),
            "effective_mixture_density_ppg": round(effective_mix_density_ppg, 3)
        }


# ==============================================================================
# MAIN ADVANCED HYDRAULICS ENGINE
# ==============================================================================
class AdvancedDrillingHydraulicsEngine:
    """Industrial Drilling Hydraulics Simulator with API RP 13D Physics Engine."""

    def __init__(
        self,
        surface_mud_weight_ppg: float,
        flow_rate_gpm: float,
        total_md_ft: float,
        total_tvd_ft: float,
        surface_temp_f: float = 70.0,
        bottomhole_temp_f: float = 180.0,
        rheology_model: RheologyModel = RheologyModel.BINGHAM_PLASTIC,
        surface_loss_psi: float = 50.0,
        bit_diameter_in: Optional[float] = None,
        cuttings_parameters: Optional[CuttingsParameters] = None,
        pump_efficiency: Optional[PumpEfficiencyModel] = None,
        config: EngineConfig = DEFAULT_CONFIG
    ):
        self.surface_mud_weight_ppg = max(0.1, surface_mud_weight_ppg)
        self.flow_rate_gpm = max(0.1, flow_rate_gpm)
        self.total_md_ft = max(1.0, total_md_ft)
        self.total_tvd_ft = max(1.0, total_tvd_ft)
        self.surface_temp_f = surface_temp_f
        self.bottomhole_temp_f = bottomhole_temp_f
        self.rheology_model = rheology_model
        self.surface_loss_psi = max(0.0, surface_loss_psi)
        self.bit_diameter_in = bit_diameter_in
        self.config = config

        self.cuttings = cuttings_parameters or CuttingsParameters()
        self.pump_efficiency = pump_efficiency or PumpEfficiencyModel()

        self.segments: List[WellSegment] = []
        self.nozzles: List[NozzleInput] = []

    def add_segment(self, segment: WellSegment) -> None:
        self.segments.append(segment)

    def add_nozzle(self, nozzle: NozzleInput) -> None:
        self.nozzles.append(nozzle)

    def _get_segment_temperature(self, seg_tvd_middle: float) -> float:
        if self.total_tvd_ft <= 0:
            return self.surface_temp_f
        frac = min(1.0, max(0.0, seg_tvd_middle / self.total_tvd_ft))
        return self.surface_temp_f + frac * (self.bottomhole_temp_f - self.surface_temp_f)

    def calculate_annular_loss_api(self, seg: WellSegment, v_ann_fpm: float, temp_visc_cp: float) -> Tuple[float, FlowRegime]:
        dh = seg.hole_id_in - seg.pipe_od_in
        if dh <= 0 or v_ann_fpm <= 0:
            return 0.0, FlowRegime.LAMINAR

        re_gen = FluidMechanicsCore.calculate_generalized_reynolds_annulus(
            seg.mud_weight_ppg, v_ann_fpm, dh, seg.n_index, seg.k_consistency, self.config
        )
        fanning_f, regime = FluidMechanicsCore.calculate_fanning_friction_factor(
            re_gen, seg.n_index, dh, seg.pipe_roughness_in
        )

        v_fps = v_ann_fpm / 60.0
        dp_dl = (fanning_f * (seg.mud_weight_ppg * self.config.hydrostatic_factor) * (v_fps ** 2)) / (25.8 * dh)
        return dp_dl, regime

    def calculate_pipe_loss_api(self, seg: WellSegment, v_pipe_fpm: float, temp_visc_cp: float) -> Tuple[float, FlowRegime]:
        d_int = seg.pipe_id_in
        if d_int <= 0 or v_pipe_fpm <= 0:
            return 0.0, FlowRegime.LAMINAR

        re_gen = FluidMechanicsCore.calculate_generalized_reynolds_pipe(
            seg.mud_weight_ppg, v_pipe_fpm, d_int, seg.n_index, seg.k_consistency, self.config
        )
        fanning_f, regime = FluidMechanicsCore.calculate_fanning_friction_factor(
            re_gen, seg.n_index, d_int, seg.pipe_roughness_in
        )

        v_fps = v_pipe_fpm / 60.0
        dp_dl = (fanning_f * (seg.mud_weight_ppg * self.config.hydrostatic_factor) * (v_fps ** 2)) / (25.8 * d_int)
        return dp_dl, regime

    def calculate_bit_hydraulics(self, total_spp_psi: float = 0.0) -> BitHydraulicsResult:
        empty_res: BitHydraulicsResult = {
            "tna_sq_in": 0.0, "bit_pressure_drop_psi": 0.0, "jet_velocity_fps": 0.0,
            "hhp": 0.0, "jif_lbf": 0.0, "hsi": 0.0, "bit_pressure_ratio_pct": 0.0
        }
        if not self.nozzles:
            return empty_res

        tna = sum(calculate_cross_sectional_area(n.size_in_32nds / 32.0) for n in self.nozzles)
        if tna <= 0:
            return empty_res

        v_jet = (self.config.flow_conversion_fps * self.flow_rate_gpm) / tna
        bit_dp = (self.surface_mud_weight_ppg * (self.flow_rate_gpm ** 2)) / (self.config.bit_pressure_constant * (tna ** 2))
        hhp = (self.flow_rate_gpm * bit_dp) / self.config.hhp_constant
        jif = (self.surface_mud_weight_ppg * self.flow_rate_gpm * v_jet) / self.config.jet_impact_force_constant

        bit_area = calculate_cross_sectional_area(self.bit_diameter_in) if self.bit_diameter_in else 0.0
        hsi = (hhp / bit_area) if bit_area > 0 else 0.0
        ratio = (bit_dp / total_spp_psi * 100.0) if total_spp_psi > 0 else 0.0

        return {
            "tna_sq_in": round(tna, 4),
            "bit_pressure_drop_psi": round(bit_dp, 2),
            "jet_velocity_fps": round(v_jet, 2),
            "hhp": round(hhp, 2),
            "jif_lbf": round(jif, 2),
            "hsi": round(hsi, 2),
            "bit_pressure_ratio_pct": round(ratio, 2)
        }

    def _compute_fixed_wellbore_hydraulics(self) -> Tuple[float, float, List[SegmentCalculationResult]]:
        total_annular_dp = 0.0
        total_pipe_dp = 0.0
        segment_results: List[SegmentCalculationResult] = []
        cumulative_tvd = 0.0

        for idx, seg in enumerate(self.segments):
            annular_area_sq_in = calculate_cross_sectional_area(seg.hole_id_in) - calculate_cross_sectional_area(seg.pipe_od_in)
            pipe_area_sq_in = calculate_cross_sectional_area(seg.pipe_id_in)

            v_ann = (self.config.velocity_constant * self.flow_rate_gpm) / max(0.01, annular_area_sq_in)
            v_pipe = (self.config.velocity_constant * self.flow_rate_gpm) / max(0.01, pipe_area_sq_in)

            seg_tvd_mid = seg.tvd_start_ft + (seg.tvd_end_ft - seg.tvd_start_ft) / 2.0
            seg_temp = self._get_segment_temperature(seg_tvd_mid)
            temp_visc = FluidMechanicsCore.adjust_viscosity_for_temperature(
                seg.viscosity_cp, self.surface_temp_f, seg_temp, self.config
            )

            dp_dl_ann, ann_regime = self.calculate_annular_loss_api(seg, v_ann, temp_visc)
            dp_dl_pipe, pipe_regime = self.calculate_pipe_loss_api(seg, v_pipe, temp_visc)

            seg_ann_loss = dp_dl_ann * seg.length_ft
            seg_pipe_loss = dp_dl_pipe * seg.length_ft

            total_annular_dp += seg_ann_loss
            total_pipe_dp += seg_pipe_loss
            cumulative_tvd += (seg.tvd_end_ft - seg.tvd_start_ft)

            hole_cleaning = CuttingsTransportEngine.analyze_hole_cleaning(
                seg, v_ann, self.cuttings, temp_visc
            )

            local_ecd = hole_cleaning["effective_mixture_density_ppg"] + (
                total_annular_dp / (self.config.hydrostatic_factor * max(1.0, cumulative_tvd))
            )

            segment_results.append({
                "segment_index": idx + 1,
                "segment_name": seg.name,
                "annular_regime": ann_regime.value,
                "pipe_regime": pipe_regime.value,
                "annular_loss_psi": round(seg_ann_loss, 2),
                "pipe_loss_psi": round(seg_pipe_loss, 2),
                "transport_ratio": hole_cleaning["transport_ratio"],
                "cuttings_concentration_pct": hole_cleaning["cuttings_concentration_pct"],
                "local_ecd_ppg": round(local_ecd, 3)
            })

        return total_annular_dp, total_pipe_dp, segment_results

    def calculate_surge_and_swab(self, trip_speed_ft_min: float = 60.0) -> Dict[str, float]:
        if not self.segments:
            return {"surge_pressure_psi": 0.0, "swab_pressure_psi": 0.0, "surge_ecd_ppg": 0.0, "swab_ecd_ppg": 0.0}

        total_surge_psi = 0.0
        for seg in self.segments:
            v_ann_trip = (self.config.velocity_constant * (trip_speed_ft_min * 0.1)) / max(
                0.01, calculate_cross_sectional_area(seg.hole_id_in) - calculate_cross_sectional_area(seg.pipe_od_in)
            )
            dp_dl_surge, _ = self.calculate_annular_loss_api(seg, v_ann_trip, seg.viscosity_cp)
            total_surge_psi += dp_dl_surge * seg.length_ft

        surge_ecd = self.surface_mud_weight_ppg + (total_surge_psi / (self.config.hydrostatic_factor * self.total_tvd_ft))
        swab_ecd = max(0.0, self.surface_mud_weight_ppg - (total_surge_psi / (self.config.hydrostatic_factor * self.total_tvd_ft)))

        return {
            "surge_pressure_psi": round(total_surge_psi, 2),
            "swab_pressure_psi": round(total_surge_psi, 2),
            "surge_ecd_ppg": round(surge_ecd, 3),
            "swab_ecd_ppg": round(swab_ecd, 3)
        }

    def generate_pressure_profile(self) -> List[Dict[str, float]]:
        profile = []
        cum_md, cum_tvd, cum_ann_dp = 0.0, 0.0, 0.0

        for seg in self.segments:
            v_ann = (self.config.velocity_constant * self.flow_rate_gpm) / max(
                0.01, calculate_cross_sectional_area(seg.hole_id_in) - calculate_cross_sectional_area(seg.pipe_od_in)
            )
            dp_dl_ann, _ = self.calculate_annular_loss_api(seg, v_ann, seg.viscosity_cp)
            
            cum_md += seg.length_ft
            cum_tvd += (seg.tvd_end_ft - seg.tvd_start_ft)
            cum_ann_dp += dp_dl_ann * seg.length_ft

            hydrostatic_psi = self.surface_mud_weight_ppg * self.config.hydrostatic_factor * cum_tvd
            ecd = self.surface_mud_weight_ppg + (cum_ann_dp / (self.config.hydrostatic_factor * max(1.0, cum_tvd)))

            profile.append({
                "measured_depth_ft": round(cum_md, 1),
                "true_vertical_depth_ft": round(cum_tvd, 1),
                "hydrostatic_pressure_psi": round(hydrostatic_psi, 2),
                "annular_friction_loss_psi": round(cum_ann_dp, 2),
                "equivalent_circulating_density_ppg": round(ecd, 3)
            })

        return profile

    def solve(self) -> Dict[str, Any]:
        if not self.segments:
            raise ValueError("No wellbore segments provided for evaluation.")

        validation_warnings = EngineeringValidator.validate_all(
            self.segments, self.surface_mud_weight_ppg, self.flow_rate_gpm,
            self.total_md_ft, self.total_tvd_ft, self.nozzles
        )

        total_annular_dp, total_pipe_dp, segment_breakdown = self._compute_fixed_wellbore_hydraulics()

        temp_bit_dp = self.calculate_bit_hydraulics()["bit_pressure_drop_psi"]
        estimated_spp = self.surface_loss_psi + total_pipe_dp + temp_bit_dp + total_annular_dp
        bit_results = self.calculate_bit_hydraulics(total_spp_psi=estimated_spp)

        final_spp_psi = self.surface_loss_psi + total_pipe_dp + bit_results["bit_pressure_drop_psi"] + total_annular_dp
        bottomhole_ecd = self.surface_mud_weight_ppg + (total_annular_dp / (self.config.hydrostatic_factor * self.total_tvd_ft))

        hydraulic_horsepower = (self.flow_rate_gpm * final_spp_psi) / self.config.hhp_constant
        brake_horsepower = hydraulic_horsepower / (self.pump_efficiency.volumetric_efficiency * self.pump_efficiency.mechanical_efficiency)

        return {
            "rheology_model": self.rheology_model.value,
            "standpipe_pressure_spp_psi": round(final_spp_psi, 2),
            "bottomhole_ecd_ppg": round(bottomhole_ecd, 3),
            "hydraulic_horsepower_hhp": round(hydraulic_horsepower, 2),
            "brake_horsepower_bhp": round(brake_horsepower, 2),
            "total_annular_loss_psi": round(total_annular_dp, 2),
            "total_pipe_loss_psi": round(total_pipe_dp, 2),
            "validation_warnings": validation_warnings,
            "bit_hydraulics": bit_results,
            "segment_breakdown": segment_breakdown
        }


# ==============================================================================
# STATE-SAFE HYDRAULICS OPTIMIZER
# ==============================================================================
class HydraulicsOptimizer:
    """Non-mutating nozzle optimizer utilizing deep-cloned engine state."""

    @staticmethod
    def optimize_nozzles_for_hhp(
        engine: AdvancedDrillingHydraulicsEngine,
        target_bit_pressure_ratio: float = 0.65
    ) -> List[int]:
        cloned_engine = copy.deepcopy(engine)
        best_nozzles = [16, 16, 16]
        closest_error = 999.0

        for nozzle_size in range(8, 28):
            test_nozzles = [NozzleInput(size_in_32nds=nozzle_size) for _ in range(3)]
            cloned_engine.nozzles = test_nozzles
            results = cloned_engine.solve()
            
            ratio = results["bit_hydraulics"]["bit_pressure_ratio_pct"] / 100.0
            error = abs(ratio - target_bit_pressure_ratio)

            if error < closest_error:
                closest_error = error
                best_nozzles = [nozzle_size, nozzle_size, nozzle_size]

        logger.info(f"Optimized Nozzles (State Preserved): {best_nozzles}")
        return best_nozzles


# ==============================================================================
# INDUSTRIAL REST API BACKEND WRAPPER (NEW COMMERCIAL FEATURE)
# ==============================================================================
class HydraulicsRequest(BaseModel):
    surface_mud_weight_ppg: float
    flow_rate_gpm: float
    total_md_ft: float
    total_tvd_ft: float
    rheology_model: RheologyModel = RheologyModel.BINGHAM_PLASTIC
    bit_diameter_in: float
    viscometer_readings: Optional[ViscometerReadings] = None
    segments: List[WellSegment]
    nozzles: List[NozzleInput]


def create_fastapi_app():
    """
    Constructs a production-ready FastAPI app instance exposing REST endpoints.
    Requires: pip install fastapi uvicorn
    """
    try:
        from fastapi import FastAPI, HTTPException
        
        app = FastAPI(
            title="Drilling Hydraulics API Engine",
            version="2.0.0",
            description="API RP 13D Compliant Hydraulics & Rheology Microservice"
        )

        @app.post("/api/v2/hydraulics/solve")
        def solve_hydraulics(request: HydraulicsRequest):
            try:
                engine = AdvancedDrillingHydraulicsEngine(
                    surface_mud_weight_ppg=request.surface_mud_weight_ppg,
                    flow_rate_gpm=request.flow_rate_gpm,
                    total_md_ft=request.total_md_ft,
                    total_tvd_ft=request.total_tvd_ft,
                    rheology_model=request.rheology_model,
                    bit_diameter_in=request.bit_diameter_in
                )
                
                # Fit rheology parameters if dial readings provided
                if request.viscometer_readings:
                    bingham = ViscometerReader.fit_bingham_plastic(request.viscometer_readings)
                    for seg in request.segments:
                        seg.viscosity_cp = bingham["plastic_viscosity_cp"]
                        seg.yield_point_lb_100ft2 = bingham["yield_point_lb_100ft2"]

                for seg in request.segments:
                    engine.add_segment(seg)
                for noz in request.nozzles:
                    engine.add_nozzle(noz)

                return engine.solve()
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))

        @app.post("/api/v2/rheology/fit-viscometer")
        def fit_viscometer(readings: ViscometerReadings):
            return {
                "bingham_plastic": ViscometerReader.fit_bingham_plastic(readings),
                "power_law": ViscometerReader.fit_power_law(readings),
                "herschel_bulkley": ViscometerReader.fit_herschel_bulkley(readings)
            }

        return app
    except ImportError:
        logger.warning("FastAPI package not installed. Microservice wrapper unmounted.")
        return None
