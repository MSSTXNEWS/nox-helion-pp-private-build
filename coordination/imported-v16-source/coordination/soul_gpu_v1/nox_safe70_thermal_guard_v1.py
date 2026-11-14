"""SAFE70 thermal policy: confirm mild hotspot excursions, fail closed.
No GPU access, pure state machine. Sampling frequency owned by live controller.
"""
from __future__ import annotations
import math

SOFT_HOTSPOT_C = 70.0
HARD_HOTSPOT_C = 75.0
CONSECUTIVE_SAMPLES = 3

class ThermalGuard:
    def __init__(self, soft=SOFT_HOTSPOT_C, hard=HARD_HOTSPOT_C,
                 consecutive=CONSECUTIVE_SAMPLES):
        if not 0 < soft < hard or consecutive < 1:
            raise ValueError("Invalid thermal policy")
        self.soft = soft
        self.hard = hard
        self.consecutive = consecutive
        self.streak = 0

    def sample(self, value):
        """Return (stop_reason_or_None, consecutive_hot_samples).
        Invalid sensor values are an immediate safety hold, not normal samples.
        """
        if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value < 110:
            self.streak = 0
            return "SENSOR_INVALID", 0
        if value >= self.hard:
            self.streak = self.consecutive
            return "HOTSPOT>=75C", self.streak
        if value >= self.soft:
            self.streak += 1
            if self.streak >= self.consecutive:
                return "HOTSPOT>=70C", self.streak
            return None, self.streak
        self.streak = 0
        return None, self.streak
