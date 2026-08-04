import math
import logging
from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, model_validator

logger = logging.getLogger("PyMudCementOptimaPro.v5_6")

# ==========================================
# 1. RHEOLOGY CONVERTER & STABLE FANN FITTER
# ==========================================

class RheologyConverter:
    """Rigorous Field-to-SI-to-Field conversion pipeline."""
    
    @staticmethod
    def lb100ft2_to_pa(val: float) -> float:
        return val * 0.4788026

    @staticmethod
    def pa_to_lb100ft2(val: float) -> float:
        return val / 0.4788026

    @staticmethod
    def ppg_to_kgm3(val: float) -> float:
        return val * 119.8264

    @staticmethod
    def gpm_to_m3s(val: float) -> float:
        return val * 0.0000630902

    @staticmethod
    def inch_to_m(val: float) -> float:
        return val * 0.0254

    @staticmethod
    def ft_to_m(val: float) -> float:
        return val * 0.3048

    @staticmethod
    def pas_to_psi(val: float) -> float:
        return val * 0.000145038


class RheologyFitter:
    """Derives Herschel-Bulkley parameters with safe ratio protection."""

    @staticmethod
    def fit_hb_from_fann(r600: float, r300: float, r3: float) -> Dict[str, float]:
        tau_600 = 1.067 * max(0.1, r600)
        tau_300 = 1.067 * max(0.1, r300)
        tau_0 = 1.067 * max(0.1, r3)

        tau_600 = max(tau_0 + 0.1, tau_600)
        tau_300 = max(tau_0 + 0.05, tau_300)

        ratio = max(1.001, (tau_600 - tau_0) / (tau_300 - tau_0))
        n = max(0.1, min(1.0, math.log10(ratio) / math.log10(600.0 / 300.0)))
        
        k_field = (tau_300 - tau_0) / (511.0 ** n)
        
        return {
            "n_index": round(n, 3),
            "k_consistency_field": round(k_field, 4),
            "tau_0_lb100ft2": round(tau_0, 2)
        }


# ==========================================
# 2. DOMAIN & CONFIGURATION MODELS
# ==========================================

class WellControlWindow(BaseModel):
    pore_pressure_ppg: float = Field(..., gt=0)
    fracture_gradient_ppg: float = Field(..., gt=0)

class TripParameters(BaseModel):
    pipe_velocity_ftmin: float = Field(default=90.0, ge=0)
    trip_time_seconds: float = Field(default=2.0, gt=0, description="Time step duration for transient acceleration shock calculation")
    acceleration_ftmin2: float = Field(default=0.0, ge=0, description="Pipe acceleration rate during trip maneuver")
    is_tripping_in: bool = Field(default=True)
    pipe_closed_ended: bool = Field(default=False)

class DrillingParameters(BaseModel):
    rop_ft_hr: float = Field(default=60.0, ge=0.0)

class CuttingParameters(BaseModel):
    diameter_in: float = Field(default=0.25, gt=0)
    density_ppg: float = Field(default=21.0, gt=0)
    shape_factor: float = Field(default=0.9, gt=0, le=1.0)

class BitParameters(BaseModel):
    bit_diameter_in: float = Field(default=8.5, gt=0)
    nozzle_sizes_16ths: List[float] = Field(default_factory=lambda: [12.0, 12.0, 12.0])
    discharge_coefficient: float = Field(default=0.95, gt=0, le=1.0, description="Empirical nozzle discharge coefficient")

    @model_validator(mode="after")
    def validate_nozzles(self):
        for nozzle in self.nozzle_sizes_16ths:
            if nozzle <= 0 or nozzle > 32:
                raise ValueError(f"Invalid nozzle size: {nozzle}/16\". Must be between 1 and 32.")
        return self

    @property
    def total_flow_area_sqin(self) -> float:
        return sum((math.pi / 4.0) * ((size / 16.0) ** 2) for size in self.nozzle_sizes_16ths)

    @property
    def bit_area_sqin(self) -> float:
        return (math.pi / 4.0) * (self.bit_diameter_in ** 2)

class MotorPerformance(BaseModel):
    max_rpm: float = Field(default=160.0, gt=0)
    torque_constant: float = Field(default=3.5, gt=0)
    rated_flow_gpm: float = Field(default=500.0, gt=0)
    mechanical_efficiency: float = Field(default=0.85, gt=0, le=1.0)

class BHAParameters(BaseModel):
    has_mud_motor: bool = Field(default=False)
    motor_spec: Optional[MotorPerformance] = Field(default_factory=MotorPerformance)
    motor_operating_dp_psi: float = Field(default=450.0, ge=0)
    mwd_tool_dp_psi: float = Field(default=120.0, ge=0)
    bha_length_ft: float = Field(default=120.0, ge=0)
    bha_inner_diameter_in: float = Field(default=2.812, gt=0)

class WellSegment(BaseModel):
    name: str = Field(default="Segment")
    length_md_ft: float = Field(..., ge=0)
    tvd_segment_ft: float = Field(..., ge=0)
    inclination_deg: float = Field(default=0.0, ge=0.0, le=90.0)
    azimuth_deg: float = Field(default=0.0, ge=0.0, le=360.0)
    
    pipe_od_in: float = Field(..., gt=0)
    pipe_id_in: float = Field(..., gt=0)
    hole_id_in: float = Field(..., gt=0)
    mud_weight_ppg: float = Field(..., gt=0)

    eccentricity_ratio: float = Field(default=0.0, ge=0.0, lt=1.0)
    rpm: float = Field(default=0.0, ge=0.0, le=300.0)

    viscosity_cp: float = Field(default=20.0, ge=0)
    yield_point_lb_100ft2: float = Field(default=15.0, ge=0)
    tau_0_lb_100ft2: float = Field(default=5.0, ge=0)
    n_index: float = Field(default=0.65, gt=0, le=1.0)
    k_consistency: float = Field(default=0.3, gt=0)
    
    temperature_f: float = Field(default=80.0)

    @model_validator(mode="after")
    def validate_geometry(self):
        if self.pipe_id_in >= self.pipe_od_in:
            raise ValueError(f"[{self.name}] Pipe ID >= Pipe OD.")
        if self.pipe_od_in >= self.hole_id_in:
            raise ValueError(f"[{self.name}] Pipe OD >= Hole ID.")
        if self.tvd_segment_ft > self.length_md_ft:
            raise ValueError(f"[{self.name}] Segment TVD exceeds MD.")
        return self

    def get_temperature_corrected_viscosity(self) -> float:
        return max(1.0, self.viscosity_cp * math.exp(-0.01 * (self.temperature_f - 80.0)))

    def apply_fann_readings(self, r600: float, r300: float, r3: float) -> None:
        hb = RheologyFitter.fit_hb_from_fann(r600, r300, r3)
        self.n_index = hb["n_index"]
        self.k_consistency = hb["k_consistency_field"]
        self.tau_0_lb_100ft2 = hb["tau_0_lb100ft2"]


# ==========================================
# 3. ADVANCED HYDRAULICS ENGINE (v5.6.0)
# ==========================================

class DrillingHydraulicsEngineV56:
    """v5.6.0 Commercial Production Engine with Metzner-Reed Reynolds correlations and depth profiling."""

    def __init__(
        self,
        surface_mud_weight_ppg: float,
        flow_rate_gpm: float,
        drilling_params: Optional[DrillingParameters] = None,
        bha_spec: Optional[BHAParameters] = None,
        bit_spec: Optional[BitParameters] = None,
        cuttings_spec: Optional[CuttingParameters] = None,
        safety_window: Optional[WellControlWindow] = None
    ):
        self.surface_mud_weight_ppg = max(0.1, surface_mud_weight_ppg)
        self.flow_rate_gpm = max(0.0, flow_rate_gpm)
        self.drilling_params = drilling_params if drilling_params else DrillingParameters()
        self.bha = bha_spec if bha_spec else BHAParameters()
        self.bit = bit_spec if bit_spec else BitParameters()
        self.cuttings = cuttings_spec if cuttings_spec else CuttingParameters()
        self.safety_window = safety_window
        self.segments: List[WellSegment] = []

    def add_segment(self, segment: WellSegment) -> None:
        self.segments.append(segment)

    def _solve_metzner_reed_hb_si(
        self, 
        d_inner_m: float, 
        d_outer_m: float, 
        length_m: float, 
        rho_kgm3: float, 
        q_m3s: float, 
        seg: WellSegment, 
        is_annulus: bool = False
    ) -> Dict[str, Any]:
        """Calculates pressure loss using Metzner-Reed Generalized Reynolds Number and Dodge-Metzner correlations."""
        if length_m <= 0:
            return {"dp_psi": 0.0, "reynolds_number": 0.0, "flow_regime": "LAMINAR"}

        tau_0_pa = RheologyConverter.lb100ft2_to_pa(seg.tau_0_lb_100ft2)
        k_si = seg.k_consistency * 0.4788026 * ((1.0 / 51.0) ** seg.n_index)

        if is_annulus:
            dh_m = d_outer_m - d_inner_m
            area_m2 = (math.pi / 4.0) * (d_outer_m**2 - d_inner_m**2)
            v_m_s = q_m3s / max(1e-6, area_m2)
            # General shear rate geometric factor for Herschel-Bulkley annular flow
            shear_rate_wall = ((2.0 * seg.n_index + 1.0) / (3.0 * seg.n_index)) * ((12.0 * abs(v_m_s)) / dh_m)
        else:
            dh_m = d_inner_m
            area_m2 = (math.pi / 4.0) * (d_inner_m**2)
            v_m_s = q_m3s / max(1e-6, area_m2)
            shear_rate_wall = ((3.0 * seg.n_index + 1.0) / (4.0 * seg.n_index)) * ((8.0 * abs(v_m_s)) / dh_m)

        if abs(v_m_s) <= 1e-6:
            return {"dp_psi": 0.0, "reynolds_number": 0.0, "flow_regime": "LAMINAR"}

        # Generalized Metzner-Reed Reynolds Number Formulation for HB fluids
        apparent_visc_pas = (tau_0_pa / max(0.001, shear_rate_wall)) + k_si * (shear_rate_wall ** (seg.n_index - 1.0))
        re_mr = (rho_kgm3 * (abs(v_m_s) ** (2.0 - seg.n_index)) * (dh_m ** seg.n_index)) / (k_si * (8.0 ** (seg.n_index - 1.0)) * (((3.0 * seg.n_index + 1.0) / (4.0 * seg.n_index)) ** seg.n_index))

        # Critical Reynolds limit for non-Newtonian transition behavior
        re_crit = 3250.0 - 1150.0 * seg.n_index

        if re_mr < re_crit:
            f_factor = 16.0 / max(1.0, re_mr)
            flow_regime = "LAMINAR"
        elif re_mr < 4000.0:
            # Transitional blending interpolation
            f_laminar = 16.0 / max(1.0, re_crit)
            f_turbulent = (0.0014 / (seg.n_index ** 2.5)) + (0.125 / (re_mr ** (0.32 / seg.n_index)))
            blend = (re_mr - re_crit) / max(1.0, (4000.0 - re_crit))
            f_factor = f_laminar * (1.0 - blend) + f_turbulent * blend
            flow_regime = "TRANSITIONAL"
        else:
            # Dodge-Metzner turbulent correlation for non-Newtonian flow
            f_factor = (0.0014 / (seg.n_index ** 2.5)) + (0.125 / (re_mr ** (0.32 / seg.n_index)))
            flow_regime = "TURBULENT"

        dp_pa = (2.0 * f_factor * length_m * rho_kgm3 * (v_m_s ** 2)) / dh_m

        if is_annulus and seg.eccentricity_ratio > 0:
            e = seg.eccentricity_ratio
            d_ratio = seg.pipe_od_in / seg.hole_id_in
            r_e = 1.0 - (0.072 * (e / seg.n_index) * (d_ratio ** 0.8454)) - (1.5 * (e ** 2) * math.sqrt(seg.n_index) * (d_ratio ** 0.1852)) + (0.96 * (e ** 3) * math.sqrt(seg.n_index) * (d_ratio ** 0.2527))
            dp_pa *= max(0.40, min(1.0, r_e))

        return {
            "dp_psi": RheologyConverter.pas_to_psi(dp_pa),
            "reynolds_number": round(re_mr, 1),
            "flow_regime": flow_regime
        }

    def calculate_cuttings_transport_v56(self, seg: WellSegment) -> Dict[str, Any]:
        """Calculates transport efficiency using physically aligned inclination slip correction."""
        v_ann_fpm = (24.51 * self.flow_rate_gpm) / (seg.hole_id_in ** 2 - seg.pipe_od_in ** 2)
        pv_eff = seg.get_temperature_corrected_viscosity()

        density_delta = self.cuttings.density_ppg - seg.mud_weight_ppg
        v_slip_base = (0.45 * max(0.1, density_delta)) * (self.cuttings.diameter_in ** 0.667) / ((seg.mud_weight_ppg ** 0.333) * (pv_eff ** 0.333)) * 60.0

        inc_rad = math.radians(seg.inclination_deg)
        # Corrected physical trend: slip velocity peaks at intermediate/deviated angles (around 45-60 deg) due to bed sliding
        inc_slip_modifier = math.sin(2.0 * inc_rad) + 0.3 * (1.0 - math.cos(inc_rad))
        rpm_benefit = 1.0 - min(0.50, (seg.rpm / 120.0) * 0.40 * math.sin(inc_rad))
        
        effective_slip_v = v_slip_base * max(0.2, inc_slip_modifier) * rpm_benefit
        transport_ratio = max(0.0, min(100.0, (1.0 - (effective_slip_v / max(0.1, v_ann_fpm))) * 100.0))

        transport_eff_decimal = max(0.05, transport_ratio / 100.0)
        cuttings_loading_pct = (
            (self.drilling_params.rop_ft_hr * (seg.hole_id_in ** 2)) / 
            (1471.0 * max(1.0, self.flow_rate_gpm) * transport_eff_decimal)
        ) * 100.0

        if cuttings_loading_pct > 5.0 or transport_ratio < 50.0:
            pack_off_risk = "PACK-OFF RISK"
        elif cuttings_loading_pct > 3.0 or transport_ratio < 70.0:
            pack_off_risk = "MODERATE LOADING"
        else:
            pack_off_risk = "CLEAN HOLE"

        clearance_in = (seg.hole_id_in - seg.pipe_od_in) * 0.5
        bed_height_est_in = clearance_in * (1.0 - transport_eff_decimal) * (1.0 + 0.5 * seg.eccentricity_ratio)

        return {
            "annular_velocity_fpm": round(v_ann_fpm, 1),
            "effective_slip_velocity_fpm": round(effective_slip_v, 1),
            "transport_ratio_pct": round(transport_ratio, 1),
            "estimated_annular_cuttings_loading_pct": round(cuttings_loading_pct, 2),
            "pack_off_risk": pack_off_risk,
            "estimated_bed_height_in": round(bed_height_est_in, 2)
        }

    def calculate_surge_swab_pressure(self, trip_params: TripParameters) -> Dict[str, Any]:
        """Calculates transient surge/swab pressure using correct time-step acceleration mechanics."""
        direction_sign = 1.0 if trip_params.is_tripping_in else -1.0
        
        # Dimensionally correct velocity increment: v_final = v_initial + (acceleration * time_step)
        accel_ft_min = trip_params.acceleration_ftmin2 * (trip_params.trip_time_seconds / 60.0)
        net_trip_vel_ftmin = trip_params.pipe_velocity_ftmin + accel_ft_min
        v_pipe_m_s = abs(RheologyConverter.ft_to_m(net_trip_vel_ftmin / 60.0))

        total_surge_swab_psi = 0.0

        for seg in self.segments:
            k_c = 0.45 if seg.eccentricity_ratio < 0.5 else 0.35
            pipe_area = math.pi / 4.0 * (RheologyConverter.inch_to_m(seg.pipe_od_in) ** 2)
            if not trip_params.pipe_closed_ended:
                pipe_area -= math.pi / 4.0 * (RheologyConverter.inch_to_m(seg.pipe_id_in) ** 2)

            q_displaced_m3s = pipe_area * v_pipe_m_s * k_c
            
            solver_res = self._solve_metzner_reed_hb_si(
                d_inner_m=RheologyConverter.inch_to_m(seg.pipe_od_in),
                d_outer_m=RheologyConverter.inch_to_m(seg.hole_id_in),
                length_m=RheologyConverter.ft_to_m(seg.length_md_ft),
                rho_kgm3=RheologyConverter.ppg_to_kgm3(seg.mud_weight_ppg),
                q_m3s=q_displaced_m3s,
                seg=seg,
                is_annulus=True
            )
            total_surge_swab_psi += (solver_res["dp_psi"] * direction_sign)

        effective_tvd = max(1.0, sum(s.tvd_segment_ft for s in self.segments))
        delta_ecd_ppg = total_surge_swab_psi / (0.052 * effective_tvd)

        return {
            "operation": "SURGE" if trip_params.is_tripping_in else "SWAB",
            "pressure_change_psi": round(total_surge_swab_psi, 2),
            "equivalent_density_delta_ppg": round(delta_ecd_ppg, 3)
        }

    def calculate_motor_performance(self) -> Dict[str, float]:
        if not self.bha.has_mud_motor or not self.bha.motor_spec:
            return {"motor_rpm": 0.0, "motor_torque_ft_lbf": 0.0, "motor_dp_psi": 0.0}

        spec = self.bha.motor_spec
        flow_ratio = self.flow_rate_gpm / max(1.0, spec.rated_flow_gpm)
        motor_dp = self.bha.motor_operating_dp_psi * (flow_ratio ** 2)
        motor_rpm = spec.max_rpm * flow_ratio
        motor_torque = spec.torque_constant * motor_dp * spec.mechanical_efficiency

        return {
            "motor_dp_psi": round(motor_dp, 2),
            "motor_rpm": round(motor_rpm, 1),
            "motor_torque_ft_lbf": round(motor_torque, 1)
        }

    def solve_v56(self, trip_params: Optional[TripParameters] = None) -> Dict[str, Any]:
        """Executes full production simulation with depth-indexed profiling and well control safety margins."""
        total_annular_dp = 0.0
        total_pipe_dp = 0.0
        segment_logs = []
        ecd_profile = []
        cumulative_tvd = 0.0
        cumulative_annular_dp = 0.0

        for seg in self.segments:
            d_pipe_in_m = RheologyConverter.inch_to_m(seg.pipe_id_in)
            d_pipe_out_m = RheologyConverter.inch_to_m(seg.pipe_od_in)
            d_hole_m = RheologyConverter.inch_to_m(seg.hole_id_in)
            length_m = RheologyConverter.ft_to_m(seg.length_md_ft)
            rho_kgm3 = RheologyConverter.ppg_to_kgm3(seg.mud_weight_ppg)
            q_m3s = RheologyConverter.gpm_to_m3s(self.flow_rate_gpm)

            pipe_solve = self._solve_metzner_reed_hb_si(d_pipe_in_m, 0.0, length_m, rho_kgm3, q_m3s, seg, is_annulus=False)
            ann_solve = self._solve_metzner_reed_hb_si(d_pipe_out_m, d_hole_m, length_m, rho_kgm3, q_m3s, seg, is_annulus=True)

            total_pipe_dp += pipe_solve["dp_psi"]
            total_annular_dp += ann_solve["dp_psi"]
            
            cumulative_tvd += seg.tvd_segment_ft
            cumulative_annular_dp += ann_solve["dp_psi"]
            
            # Depth-indexed ECD calculation profile point
            seg_hydrostatic = seg.mud_weight_ppg + (cumulative_annular_dp / (0.052 * max(1.0, cumulative_tvd)))
            ecd_profile.append({
                "depth_md_ft": round(seg.length_md_ft, 1),
                "depth_tvd_ft": round(cumulative_tvd, 1),
                "ecd_ppg": round(seg_hydrostatic, 2)
            })

            transport_eval = self.calculate_cuttings_transport_v56(seg)
            segment_logs.append({
                "segment": seg.name,
                "annular_dp_psi": round(ann_solve["dp_psi"], 2),
                "pipe_dp_psi": round(pipe_solve["dp_psi"], 2),
                "annular_reynolds": ann_solve["reynolds_number"],
                "flow_regime": ann_solve["flow_regime"],
                "transport_ratio_pct": transport_eval["transport_ratio_pct"],
                "estimated_annular_cuttings_loading_pct": transport_eval["estimated_annular_cuttings_loading_pct"],
                "pack_off_risk": transport_eval["pack_off_risk"],
                "bed_height_in": transport_eval["estimated_bed_height_in"]
            })

        motor_perf = self.calculate_motor_performance()
        bha_dp = self.bha.mwd_tool_dp_psi + motor_perf["motor_dp_psi"]

        tfa = self.bit.total_flow_area_sqin
        cd = self.bit.discharge_coefficient
        # Mud-specific bit nozzle pressure drop incorporating discharge coefficient Cd
        bit_dp = (1.08 * (10 ** -4) * self.surface_mud_weight_ppg * (self.flow_rate_gpm ** 2)) / max(1e-4, ((cd ** 2) * (tfa ** 2)))
        jet_velocity_fps = (0.3208 * self.flow_rate_gpm) / max(1e-4, (cd * tfa))
        impact_force_lbf = 0.000516 * self.surface_mud_weight_ppg * self.flow_rate_gpm * jet_velocity_fps
        bit_hhp = (self.flow_rate_gpm * bit_dp) / 1714.0
        hsi = bit_hhp / max(1e-4, self.bit.bit_area_sqin)

        surface_losses = 50.0
        total_spp = surface_losses + total_pipe_dp + bha_dp + bit_dp + total_annular_dp
        
        effective_tvd = max(1.0, sum(s.tvd_segment_ft for s in self.segments))
        static_hydrostatic = 0.052 * self.surface_mud_weight_ppg * effective_tvd
        friction_pressure_total = total_spp - static_hydrostatic  # total system friction overview
        bottomhole_dynamic_pressure = static_hydrostatic + total_annular_dp

        ecd = self.surface_mud_weight_ppg + (total_annular_dp / (0.052 * effective_tvd))
        total_hhp = (self.flow_rate_gpm * total_spp) / 1714.0

        surge_swab_results = self.calculate_surge_swab_pressure(trip_params) if trip_params else {"operation": "NONE", "pressure_change_psi": 0.0, "equivalent_density_delta_ppg": 0.0}
        dynamic_trip_ecd = ecd + surge_swab_results["equivalent_density_delta_ppg"]

        window_eval = {"status": "NOT_EVALUATED", "margin_to_pore_ppg": None, "margin_to_fracture_ppg": None, "fracture_margin_psi": None, "kick_margin_psi": None}
        if self.safety_window:
            margin_frac_ppg = self.safety_window.fracture_gradient_ppg - dynamic_trip_ecd
            margin_pore_ppg = dynamic_trip_ecd - self.safety_window.pore_pressure_ppg
            
            # Pressure margins expressed directly in psi
            fracture_margin_psi = margin_frac_ppg * 0.052 * effective_tvd
            kick_margin_psi = margin_pore_ppg * 0.052 * effective_tvd

            window_eval["margin_to_pore_ppg"] = round(margin_pore_ppg, 3)
            window_eval["margin_to_fracture_ppg"] = round(margin_frac_ppg, 3)
            window_eval["fracture_margin_psi"] = round(fracture_margin_psi, 1)
            window_eval["kick_margin_psi"] = round(kick_margin_psi, 1)

            if dynamic_trip_ecd > self.safety_window.fracture_gradient_ppg:
                window_eval["status"] = "FORMATION_FRACTURE_RISK"
            elif dynamic_trip_ecd < self.safety_window.pore_pressure_ppg:
                window_eval["status"] = "KICK_RISK"
            else:
                window_eval["status"] = "SAFE"

        return {
            "version": "5.6.0-PRO",
            "engine_metadata": {
                "rheology_model": "Herschel-Bulkley Metzner-Reed",
                "units": "Field Input / SI Internal",
                "status": "Production Validation Release"
            },
            "model_confidence": {
                "rheology": "HIGH",
                "cuttings_transport": "MEDIUM",
                "surge_swab": "MEDIUM"
            },
            "pressure_summary": {
                "static_hydrostatic_pressure_psi": round(static_hydrostatic, 2),
                "friction_pressure_psi": round(total_annular_dp + total_pipe_dp + bha_dp + bit_dp, 2),
                "bottomhole_circulating_pressure_psi": round(bottomhole_dynamic_pressure, 2),
                "standpipe_pressure_spp_psi": round(total_spp, 2)
            },
            "ecd_profile_by_depth": ecd_profile,
            "equivalent_circulating_density_ecd_ppg": round(ecd, 3),
            "dynamic_trip_ecd_ppg": round(dynamic_trip_ecd, 3),
            "hydraulic_horsepower_hhp": round(total_hhp, 1),
            "effective_tvd_ft": round(effective_tvd, 1),
            "motor_performance": motor_perf,
            "bit_hydraulics": {
                "bit_dp_psi": round(bit_dp, 2),
                "jet_velocity_fps": round(jet_velocity_fps, 1),
                "impact_force_lbf": round(impact_force_lbf, 1),
                "bit_hhp": round(bit_hhp, 2),
                "hsi_hp_sqin": round(hsi, 2)
            },
            "surge_swab_analysis": surge_swab_results,
            "safety_window_evaluation": window_eval,
            "segments_analysis": segment_logs
        }
