"""Deterministic SAFE70 thermal debounce checks. No GPU and no IO."""
import unittest
from nox_safe70_thermal_guard_v1 import ThermalGuard

class ThermalGuardTests(unittest.TestCase):
    def test_single_spike_does_not_stop(self):
        guard=ThermalGuard()
        self.assertEqual(guard.sample(70.2),(None,1))
        self.assertEqual(guard.sample(69.4),(None,0))

    def test_three_consecutive_at_soft_limit_stop(self):
        guard=ThermalGuard()
        self.assertEqual(guard.sample(70.0),(None,1))
        self.assertEqual(guard.sample(72.0),(None,2))
        self.assertEqual(guard.sample(74.9),("HOTSPOT>=70C",3))

    def test_reset_between_warnings(self):
        guard=ThermalGuard()
        for t in (71,69,71,69,71,69):
            event,count=guard.sample(t)
            self.assertIsNone(event)

    def test_emergency_immediate(self):
        self.assertEqual(ThermalGuard().sample(75.0)[0],"HOTSPOT>=75C")

    def test_emergency_after_warning(self):
        guard=ThermalGuard()
        self.assertIsNone(guard.sample(70.4)[0])
        self.assertEqual(guard.sample(79.0)[0],"HOTSPOT>=75C")

    def test_sensor_invalid_immediate(self):
        for val in (None,0,-1,float('nan'),float('inf'),110,True):
            with self.subTest(val=val):
                self.assertEqual(ThermalGuard().sample(val)[0],"SENSOR_INVALID")

    def test_thermal_count_resets_after_invalid(self):
        guard=ThermalGuard()
        self.assertEqual(guard.sample(71),(None,1))
        self.assertEqual(guard.sample(None),("SENSOR_INVALID",0))
        self.assertEqual(guard.sample(71),(None,1))

if __name__=='__main__':
    unittest.main()
