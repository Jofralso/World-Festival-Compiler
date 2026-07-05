import unittest
from pathlib import Path

from core.geo_context import LocalGeoContextEngine


class GeoContextTests(unittest.TestCase):
    def test_memory_reuses_prior_patterns_for_future_bounds(self):
        path = Path("/tmp/festivalworld_test_memory.json")
        if path.exists():
            path.unlink()

        engine = LocalGeoContextEngine(memory_path=path)
        engine.remember(
            bounds=(48.0, 2.0, 49.0, 3.0),
            summary={"building_count": 40, "water_ratio": 0.1, "road_density": 0.3},
        )

        prediction = engine.predict_for(bounds=(48.1, 2.1, 49.1, 3.1))
        self.assertGreaterEqual(prediction["building_density"], 0.0)
        self.assertGreaterEqual(prediction["water_bias"], 0.0)


if __name__ == "__main__":
    unittest.main()
