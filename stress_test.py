"""
Stress testing the PyMudCement Optima Pro engine with random inputs.
This demonstrates robustness and can be presented in the viva.
"""

import random
import sys
from typing import Dict, List, Any
from physics import DrillingHydraulicsEngine, WellSegment, RheologyModel, NozzleInput
from cementing_engine import CementingEngine, PrimaryCementingInput

class StressTestSuite:
    def __init__(self, num_tests: int = 100):
        self.num_tests = num_tests
        self.results = []
        self.failures = []

    def random_well_config(self) -> Dict[str, Any]:
        """Generate random well parameters within realistic ranges."""
        return {
            "depth": random.uniform(5000, 25000),
            "flow_rate": random.uniform(200, 1000),
            "mw": random.uniform(8.0, 18.0),
            "pv": random.uniform(10, 50),
            "yp": random.uniform(5, 30),
            "hole_dia": random.uniform(6.0, 12.25),
            "pipe_od": random.uniform(3.5, 6.75),
            "pipe_id": random.uniform(2.0, 5.0),  # ensure pipe_id < pipe_od
            "rheology": random.choice([r for r in RheologyModel])
        }

    def test_hydraulics_stability(self) -> Dict[str, Any]:
        """Test hydraulics engine with many random configurations."""
        print(f"Running {self.num_tests} hydraulics stress tests...")
        passed = 0
        for i in range(self.num_tests):
            config = self.random_well_config()
            # Ensure pipe_id < pipe_od
            if config["pipe_id"] >= config["pipe_od"]:
                config["pipe_id"] = config["pipe_od"] * 0.8
            try:
                engine = DrillingHydraulicsEngine(
                    surface_mud_weight_ppg=config["mw"],
                    flow_rate_gpm=config["flow_rate"],
                    total_depth_ft=config["depth"],
                    plastic_viscosity_cp=config["pv"],
                    yield_point_lb_100ft2=config["yp"],
                    rheology_model=config["rheology"]
                )
                engine.add_segment(WellSegment(
                    name=f"Stress Test {i}",
                    length_ft=config["depth"],
                    pipe_od_in=config["pipe_od"],
                    pipe_id_in=config["pipe_id"],
                    hole_id_in=config["hole_dia"],
                    mud_weight_ppg=config["mw"],
                    viscosity_cp=config["pv"],
                    yield_point_lb_100ft2=config["yp"]
                ))
                # Add nozzles
                for _ in range(3):
                    engine.add_nozzle(NozzleInput(size_in_32nds=random.randint(10, 20)))
                results = engine.solve()
                
                # Basic sanity checks
                assert results["equivalent_circulating_density_ecd_ppg"] > 0
                assert results["standpipe_pressure_spp_psi"] > 0
                assert results["total_annular_pressure_loss_psi"] >= 0
                passed += 1
                self.results.append({"passed": True, "config": config})
            except Exception as e:
                self.failures.append({"config": config, "error": str(e)})
                self.results.append({"passed": False, "error": str(e), "config": config})
        
        return {
            "total": self.num_tests,
            "passed": passed,
            "failed": self.num_tests - passed,
            "pass_rate": passed / self.num_tests * 100,
            "failures": self.failures[:5]  # show first 5 failures
        }

    def test_cementing_stability(self) -> Dict[str, Any]:
        """Test cementing engine with random inputs."""
        print(f"Running {self.num_tests} cementing stress tests...")
        passed = 0
        for i in range(self.num_tests):
            try:
                hole = random.uniform(6.0, 12.25)
                casing_od = random.uniform(4.5, 9.625)
                if casing_od >= hole:
                    casing_od = hole * 0.8
                casing_id = casing_od * random.uniform(0.8, 0.95)
                params = PrimaryCementingInput(
                    hole_diameter_in=hole,
                    casing_od_in=casing_od,
                    casing_id_in=casing_id,
                    interval_length_ft=random.uniform(1000, 10000),
                    washout_factor_pct=random.uniform(0, 30),
                    shoe_track_length_ft=random.uniform(20, 80),
                    lead_slurry_density_ppg=random.uniform(10, 14),
                    tail_slurry_density_ppg=random.uniform(14, 18),
                    spacer_density_ppg=random.uniform(9, 13),
                    displacement_fluid_density_ppg=random.uniform(8, 11),
                    tail_slurry_length_ft=random.uniform(200, 1500),
                    bht_fahrenheit=random.uniform(100, 300)
                )
                engine = CementingEngine()
                result = engine.design_primary_job(params)
                # Basic sanity checks
                assert result["lead_slurry_volume_bbl"] >= 0
                assert result["tail_slurry_volume_bbl"] >= 0
                assert result["recommended_plug_bumping_pressure_psi"] > 0
                passed += 1
            except Exception as e:
                self.failures.append({"params": params.dict(), "error": str(e)})
        
        return {
            "total": self.num_tests,
            "passed": passed,
            "failed": self.num_tests - passed,
            "pass_rate": passed / self.num_tests * 100,
            "failures": self.failures[:5]
        }

    def run_all(self) -> Dict[str, Any]:
        hydra = self.test_hydraulics_stability()
        cement = self.test_cementing_stability()
        return {
            "hydraulics": hydra,
            "cementing": cement,
            "overall_pass_rate": (hydra["passed"] + cement["passed"]) / (2 * self.num_tests) * 100
        }

if __name__ == "__main__":
    suite = StressTestSuite(num_tests=50)  # 50 each for speed
    results = suite.run_all()
    print("\n" + "="*60)
    print("STRESS TEST RESULTS")
    print("="*60)
    print(f"Hydraulics: {results['hydraulics']['passed']}/{results['hydraulics']['total']} passed ({results['hydraulics']['pass_rate']:.1f}%)")
    print(f"Cementing:  {results['cementing']['passed']}/{results['cementing']['total']} passed ({results['cementing']['pass_rate']:.1f}%)")
    print(f"Overall pass rate: {results['overall_pass_rate']:.1f}%")
    if results['hydraulics']['failures']:
        print("\nSample Hydraulics Failures:")
        for f in results['hydraulics']['failures']:
            print(f"  Error: {f['error']}")
    if results['cementing']['failures']:
        print("\nSample Cementing Failures:")
        for f in results['cementing']['failures']:
            print(f"  Error: {f['error']}")