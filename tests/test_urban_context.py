import unittest
import numpy as np

from core.urban_context import UrbanContextModel


class UrbanContextTests(unittest.TestCase):
    def test_urban_context_flattens_roads_and_buildings(self):
        model = UrbanContextModel()
        hm = np.full((64, 64), 80.0, dtype=np.float32)
        osm = {
            "roads": [{"coords": [(0.0, 0.0), (0.1, 0.1)]}],
            "buildings": [{"coords": [(0.0, 0.0), (0.01, 0.0), (0.01, 0.01)]}],
        }
        out = model.apply_to_heightmap(hm, osm)
        self.assertTrue((out <= 80.0).all())
        self.assertTrue((out >= 64.0).any())
        self.assertTrue((out == 66.0).any() or (out == 64.0).any())


if __name__ == "__main__":
    unittest.main()
