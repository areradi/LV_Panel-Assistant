import json
import math
import subprocess
import sys
import unittest

from lv_assist.s201_c10_preview import preview


class S201C10PreviewTests(unittest.TestCase):
    def sample(self, part="S201-C10", **inputs):
        conditions = {"current_type": "AC", "frequency_hz": 50,
                      "reference_temp_c": 30, "voltage_across_pole_v": 230}
        return preview(part, **(conditions | inputs))

    def test_catalogue_readings_include_provenance(self):
        result = self.sample(trip_current_a=30, fault_current_a=6000)
        self.assertEqual(result["mode"], "PREVIEW_ONLY")
        self.assertEqual(result["source"]["trip_page"], 11)
        self.assertEqual(result["source"]["energy_page"], 13)
        self.assertEqual(result["trip"]["fast_s_approx"], 3.3)
        self.assertEqual(result["trip"]["slow_s_approx"], 60)
        self.assertEqual(result["energy"]["a2s_approx"], 17000)

    def test_midpoint_on_log_axes(self):
        result = self.sample(trip_current_a=math.sqrt(20 * 30), fault_current_a=math.sqrt(3000 * 4000))
        self.assertAlmostEqual(result["trip"]["slow_s_approx"], 120)
        self.assertAlmostEqual(result["energy"]["a2s_approx"], 9017.76025, places=4)

    def test_conditions_are_inequalities_not_samples(self):
        for current, operator, seconds in ((11.3, ">", 3600), (14.5, "<", 3600),
                                           (50, ">", 0.1), (100, "<", 0.1)):
            with self.subTest(current=current):
                trip = self.sample(trip_current_a=current)["trip"]
                self.assertEqual(trip["test_limit"], {"operator": operator, "seconds": seconds})
                self.assertIsNone(trip["fast_s_approx"])
        self.assertIsNone(self.sample(trip_current_a=100)["trip"]["slow_s_approx"])

    def test_magnetic_gap_and_out_of_range(self):
        self.assertIsNone(self.sample(trip_current_a=55)["trip"]["fast_s_approx"])
        self.assertIsNone(self.sample(trip_current_a=70)["trip"]["fast_s_approx"])
        result = self.sample(trip_current_a=101, fault_current_a=6001)
        self.assertEqual(result["trip"]["status"], "INSUFFICIENT_DATA")
        self.assertEqual(result["energy"]["status"], "INSUFFICIENT_DATA")
        self.assertEqual(self.sample(fault_current_a=999)["energy"]["status"], "INSUFFICIENT_DATA")

    def test_scope_failures_and_independent_energy_gate(self):
        self.assertEqual(self.sample("S201-C10NA", trip_current_a=30)["status"], "INSUFFICIENT_DATA")
        for conditions in ({"current_type": "DC"}, {"reference_temp_c": 40}, {"frequency_hz": 100}):
            self.assertEqual(self.sample(trip_current_a=30, **conditions)["status"], "INSUFFICIENT_DATA")
        for voltage in (400, None):
            result = self.sample(trip_current_a=30, fault_current_a=4000, voltage_across_pole_v=voltage)
            self.assertEqual(result["trip"]["slow_s_approx"], 60)
            self.assertEqual(result["energy"]["status"], "INSUFFICIENT_DATA")

    def test_invalid_current(self):
        for current in (0, -1, math.inf, math.nan):
            with self.assertRaises(ValueError):
                self.sample(trip_current_a=current)

    def test_command_outputs_preview_json(self):
        command = [sys.executable, "-B", "-m", "lv_assist.s201_c10_preview", "--current-type", "AC",
                   "--frequency-hz", "50", "--reference-temp-c", "30", "--trip-current-a", "30"]
        run = subprocess.run(command, check=True, capture_output=True, text=True)
        self.assertEqual(json.loads(run.stdout)["trip"]["slow_s_approx"], 60)


if __name__ == "__main__":
    unittest.main()
