import numpy as np
from typing import Dict, List, Any, Optional

class DrillingKnowledgeBase:
    """
    A lightweight vector-style knowledge base for drilling engineering lessons learned,
    IADC/API guidelines, and operational failure modes.
    """
    def __init__(self):
        # Local mock database containing high-fidelity operational knowledge
        self.kb = [
            {
                "hazard": "Pack-off / Hole Cleaning Failure",
                "keywords": ["ecd_high", "pressure_spike", "cuttings", "annular_loss"],
                "diagnosis": "Accumulated drill cuttings are settling in the annulus, restricting flow area and spiking dynamic pressures.",
                "actions": [
                    "Back off the bottom immediately to avoid sticking the BHA.",
                    "Reciprocate the drill string while gradually increasing pump rate to lift the bed.",
                    "Monitor torque spikes; if torque increases, discontinue rotation."
                ]
            },
            {
                "hazard": "Lost Circulation",
                "keywords": ["ecd_low", "pressure_drop", "losses", "fracture"],
                "diagnosis": "Equivalent Circulating Density has breached the formation fracture gradient, creating induced fractures.",
                "actions": [
                    "Immediately stage down mud pumps to lower equivalent circulating density.",
                    "Prepare to spot a Lost Circulation Material (LCM) pill across the loss zone.",
                    "Monitor fluid levels in the active pits closely to calculate loss rate."
                ]
            },
            {
                "hazard": "Bit Balling",
                "keywords": ["rop_low", "pressure_spike", "torque_low"],
                "diagnosis": "Sticky argillaceous formations (shale) are packing around the bit cutters, destroying cutting efficiency.",
                "actions": [
                    "Pick up off bottom and pump high-velocity sweeps.",
                    "Spin the string at high RPM (off-bottom) to attempt to clear the cutters via centrifugal force.",
                    "Consider adding anti-balling chemical treatment to the active system."
                ]
            }
        ]

    def query_knowledge(self, diagnostic_tags: List[str]) -> List[Dict[str, Any]]:
        """Simulates semantic matching by analyzing tag intersections and weights."""
        matches = []
        for entry in self.kb:
            # Check how many diagnostic keywords overlap with the entry
            intersection = set(diagnostic_tags).intersection(set(entry["keywords"]))
            if intersection:
                match_score = len(intersection) / len(entry["keywords"])
                matches.append((match_score, entry))
       
        # Sort by best structural match
        matches.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in matches]

class DiagnosticEngine:
    """
    Evaluates real-time sensor outputs against theoretical physics baselines
    to trigger proactive engineering warnings.
    """
    def __init__(self, knowledge_base: DrillingKnowledgeBase):
        self.kb = knowledge_base
        # Standard structural operational limits
        self.ECD_UPPER_LIMIT_MULTIPLIER = 1.08  # 8% over ESD indicates high packing risk
        self.ECD_LOWER_LIMIT_MULTIPLIER = 0.95  # 5% below ESD indicates dynamic downhole losses

    def analyze_telemetry(self, physics_metrics: Dict[str, Any], historical_esd: float) -> Dict[str, Any]:
        """
        Interprets physics engine snapshots to diagnose faults and extract recommendations.
        """
        current_ecd = physics_metrics.get("ecd_ppg", 0.0)
        friction_loss = physics_metrics.get("total_annular_friction_loss_psi", 0.0)
       
        diagnostic_tags = []
        status = "OPERATIONAL_NOMINAL"
        severity = "GREEN"
        summary = "Wellbore hydraulics are operating within safe planned margins."
       
        # 1. Evaluate anomalies against physics limits
        if current_ecd > (historical_esd * self.ECD_UPPER_LIMIT_MULTIPLIER):
            status = "ANOMALY_CRITICAL_HIGH"
            severity = "RED"
            diagnostic_tags.extend(["ecd_high", "pressure_spike", "annular_loss"])
            summary = "Critical ECD spike detected. Annular geometry is choking or packing off."
           
        elif current_ecd < (historical_esd * self.ECD_LOWER_LIMIT_MULTIPLIER) and friction_loss > 0:
            status = "ANOMALY_CRITICAL_LOW"
            severity = "RED"
            diagnostic_tags.extend(["ecd_low", "pressure_drop", "losses"])
            summary = "Severe pressure drop detected downhole. Potential fluid loss or severe washouts."

        # 2. Query the knowledge base if an anomaly is captured
        recommendations = []
        matched_hazard = "None"
        detailed_diagnosis = "No structural faults observed."
       
        if diagnostic_tags:
            kb_results = self.kb.query_knowledge(diagnostic_tags)
            if kb_results:
                primary_match = kb_results[0]
                matched_hazard = primary_match["hazard"]
                detailed_diagnosis = primary_match["diagnosis"]
                recommendations = primary_match["actions"]

        return {
            "status": status,
            "severity": severity,
            "summary": summary,
            "matched_hazard": matched_hazard,
            "detailed_diagnosis": detailed_diagnosis,
            "actionable_recommendations": recommendations
        }

# --- Integrated Test Loop ---
if __name__ == "__main__":
    print("Testing AI Engine & Failure Diagnostics...")
   
    # Initialize components
    kb = DrillingKnowledgeBase()
    ai_diagnostics = DiagnosticEngine(knowledge_base=kb)
   
    # Case A: Nominal Physics Snapshot
    nominal_snapshot = {"ecd_ppg": 10.4, "total_annular_friction_loss_psi": 250.0}
    result_a = ai_diagnostics.analyze_telemetry(nominal_snapshot, historical_esd=10.2)
   
    print("\n[Test 1] Nominal Conditions Output:")
    print(f"Status: {result_a['status']} | Severity: {result_a['severity']}")
   
    # Case B: Unsafe Packed-off Condition (High Friction / Spiked ECD)
    abnormal_snapshot = {"ecd_ppg": 11.2, "total_annular_friction_loss_psi": 980.0}
    result_b = ai_diagnostics.analyze_telemetry(abnormal_snapshot, historical_esd=10.2)
   
    print("\n[Test 2] Pack-Off Hazard Detected:")
    print(f"Status: {result_b['status']} | Severity: {result_b['severity']}")
    print(f"Hazard Type: {result_b['matched_hazard']}")
    print(f"Root Cause: {result_b['detailed_diagnosis']}")
    print("Mitigation Blueprint:")
    for step in result_b['actionable_recommendations']:
        print(f" -> {step}")