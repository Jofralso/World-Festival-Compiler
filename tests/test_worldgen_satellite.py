import unittest

import numpy as np

from core.worldgen import infer_satellite_context


class SatelliteContextTests(unittest.TestCase):
    def test_infer_satellite_context_detects_water_only_when_satellite_evidence_is_strong(self):
        dry_image = np.ones((30, 30, 3), dtype=np.uint8) * np.array([120, 140, 110], dtype=np.uint8)
        dry_context = infer_satellite_context(dry_image)
        self.assertFalse(dry_context["water_mask"].any())

        water_image = np.ones((30, 30, 3), dtype=np.uint8) * np.array([35, 70, 180], dtype=np.uint8)
        water_context = infer_satellite_context(water_image)
        self.assertTrue(water_context["water_mask"].any())


if __name__ == "__main__":
    unittest.main()
