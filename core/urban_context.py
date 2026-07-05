"""Urban and street-level heuristics for more realistic map generation."""

import math
import numpy as np


class UrbanContextModel:
    """Heuristics for approximating street grids, building footprints, and lots."""

    def __init__(self):
        self.default_block_size = 20

    def infer_street_grid(self, osm_features: dict, width: int, height: int) -> list[tuple[tuple[int, int], tuple[int, int]]]:
        roads = osm_features.get("roads", [])
        if not roads:
            return []

        lines = []
        for feat in roads[:15]:
            coords = feat.get("coords", [])
            if len(coords) < 2:
                continue
            pts = []
            for lat, lng in coords:
                x = int(((lng + 180.0) * 10.0)) % width
                z = int(((lat + 90.0) * 10.0)) % height
                pts.append((x, z))
            if len(pts) >= 2:
                lines.append((pts[0], pts[-1]))
        return lines[:20]

    def infer_building_blocks(self, osm_features: dict, width: int, height: int) -> list[tuple[int, int, int, int]]:
        buildings = osm_features.get("buildings", [])
        blocks = []
        for feat in buildings[:30]:
            coords = feat.get("coords", [])
            if len(coords) < 3:
                continue
            xs = [int((lng + 180.0) * 10.0) % width for lat, lng in coords]
            zs = [int((lat + 90.0) * 10.0) % height for lat, lng in coords]
            if not xs or not zs:
                continue
            min_x, max_x = min(xs), max(xs)
            min_z, max_z = min(zs), max(zs)
            blocks.append((min_x, min_z, max(max_x - min_x, 8), max(max_z - min_z, 8)))
        return blocks

    def apply_to_heightmap(self, hmap: np.ndarray, osm_features: dict) -> np.ndarray:
        hm = hmap.copy()
        width, height = hm.shape[1], hm.shape[0]
        streets = self.infer_street_grid(osm_features, width, height)
        for start, end in streets:
            sx, sz = start
            ex, ez = end
            if abs(ex - sx) > abs(ez - sz):
                steps = max(abs(ex - sx), 1)
                for i in range(steps):
                    x = sx + (ex - sx) * i // steps
                    z = sz + (ez - sz) * i // steps
                    if 0 <= x < width and 0 <= z < height:
                        hm[z, x] = min(hm[z, x], 66.0)
            else:
                steps = max(abs(ez - sz), 1)
                for i in range(steps):
                    x = sx + (ex - sx) * i // steps
                    z = sz + (ez - sz) * i // steps
                    if 0 <= x < width and 0 <= z < height:
                        hm[z, x] = min(hm[z, x], 66.0)

        for x, z, w, h in self.infer_building_blocks(osm_features, width, height):
            x = max(0, min(width - 1, x))
            z = max(0, min(height - 1, z))
            w = max(8, min(width - x, w))
            h = max(8, min(height - z, h))
            for row in range(z, min(height, z + h)):
                for col in range(x, min(width, x + w)):
                    hm[row, col] = max(hm[row, col], 64.0)
        return hm
