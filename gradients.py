"""
Handles pore pressure and fracture gradient profiles.
"""

import numpy as np
from typing import List, Dict, Any, Optional

class PressureGradientProfile:
    def __init__(self, depths: List[float], pore_pressures: List[float], frac_gradients: List[float]):
        """
        Initialize with depth, pore pressure (ppg), and fracture gradient (ppg) arrays.
        All arrays must be same length and sorted by depth.
        """
        if not (len(depths) == len(pore_pressures) == len(frac_gradients)):
            raise ValueError("All arrays must have same length.")
        if len(depths) == 0:
            raise ValueError("At least one data point required.")
        # Ensure sorted
        self.depths = np.array(sorted(depths))
        # Reorder other arrays accordingly
        idx = np.argsort(depths)
        self.pore = np.array(pore_pressures)[idx]
        self.frac = np.array(frac_gradients)[idx]
        self._validate()

    def _validate(self):
        """Check that pore < fracture at each depth."""
        for i in range(len(self.depths)):
            if self.pore[i] >= self.frac[i]:
                raise ValueError(f"Pore pressure ({self.pore[i]}) >= Fracture gradient ({self.frac[i]}) at depth {self.depths[i]}")

    def get_pore_at_depth(self, depth: float) -> float:
        """Interpolate pore pressure at given depth."""
        return float(np.interp(depth, self.depths, self.pore))

    def get_frac_at_depth(self, depth: float) -> float:
        """Interpolate fracture gradient at given depth."""
        return float(np.interp(depth, self.depths, self.frac))

    def get_safe_window(self, depth: float) -> Dict[str, float]:
        """
        Return safe mud weight window.
        Returns min (pore + 0.3 ppg safety) and max (fracture - 0.2 ppg).
        """
        pore = self.get_pore_at_depth(depth)
        frac = self.get_frac_at_depth(depth)
        return {
            "min_mw_ppg": pore + 0.3,
            "max_mw_ppg": frac - 0.2,
            "pore": pore,
            "fracture": frac
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "depths": self.depths.tolist(),
            "pore_pressures": self.pore.tolist(),
            "frac_gradients": self.frac.tolist()
        }

    @classmethod
    def from_dataframe(cls, df):
        """Create profile from a DataFrame with columns Depth, Pore, Fracture."""
        depths = df["Depth"].tolist()
        pore = df["Pore"].tolist()
        frac = df["Fracture"].tolist()
        return cls(depths, pore, frac)