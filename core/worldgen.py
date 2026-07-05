"""Large-world terrain generation — scales SRTM+OSM data to 10k×10k Minecraft worlds.

Pipeline:
  SRTM heightmap (30-90m res) → bicubic upscale to 10k×10k
  + OSM features → carve roads, flatten buildings, add water
  + Procedural outpainting → fill areas outside SRTM bounds
  + Biome classification → elevation + OSM → Minecraft biome map
"""

import math
import json
from pathlib import Path
from typing import Any
import warnings

import cv2

import numpy as np

from .preprocessor import normalize_heightmap, find_flat_zones
from .geo_context import LocalGeoContextEngine
from .urban_context import UrbanContextModel


# ─────────────────────────────────────────────
# 1. SCALING
# ─────────────────────────────────────────────

def upscale_heightmap(
    hmap: np.ndarray,
    target_size: tuple[int, int],
    method: str = "bicubic",
) -> np.ndarray:
    """Upscale a low-res heightmap (e.g. SRTM) to Minecraft block resolution.

    Args:
        hmap: Input heightmap (2D float32, meters).
        target_size: (width, height) in blocks (e.g. (10000, 10000)).
        method: 'bicubic', 'bilinear', or 'nearest'.

    Returns:
        Upscaled heightmap as 2D float32.
    """
    if hmap.shape == target_size:
        return hmap.astype(np.float32)

    # Use OpenCV if available for speed
    try:
        import cv2
        interp = {
            "bicubic": cv2.INTER_CUBIC,
            "bilinear": cv2.INTER_LINEAR,
            "nearest": cv2.INTER_NEAREST,
        }.get(method, cv2.INTER_CUBIC)
        up = cv2.resize(hmap, target_size, interpolation=interp)
        return up.astype(np.float32)
    except ImportError:
        pass

    # Fallback: scipy or numpy-based
    try:
        from scipy.ndimage import zoom
        h, w = hmap.shape
        target_h, target_w = target_size
        factors = (target_h / h, target_w / w)
        order = {"bicubic": 3, "bilinear": 1, "nearest": 0}.get(method, 3)
        up = zoom(hmap, factors, order=order)
        return up.astype(np.float32)
    except ImportError:
        pass

    # Last resort: simple repeat (nearest neighbor)
    h, w = hmap.shape
    target_h, target_w = target_size
    rh = target_h // h
    rw = target_w // w
    up = np.repeat(np.repeat(hmap, rh, axis=0), rw, axis=1)
    # Trim/pad to exact size
    if up.shape[0] > target_h:
        up = up[:target_h, :]
    if up.shape[1] > target_w:
        up = up[:, :target_w]
    if up.shape[0] < target_h:
        pad_h = target_h - up.shape[0]
        up = np.pad(up, ((0, pad_h), (0, 0)), mode="edge")
    if up.shape[1] < target_w:
        pad_w = target_w - up.shape[1]
        up = np.pad(up, ((0, 0), (0, pad_w)), mode="edge")
    return up.astype(np.float32)


# ─────────────────────────────────────────────
# 2. OSM FEATURE INTEGRATION
# ─────────────────────────────────────────────

def geo_to_block_coords(
    lats: list[float],
    lngs: list[float],
    bounds: tuple[float, float, float, float],
    grid_shape: tuple[int, int],
) -> np.ndarray:
    """Project geo coordinates onto a block-heightmap grid.

    Args:
        lats, lngs: coordinate lists (same length).
        bounds: (south, west, north, east).
        grid_shape: (height, width) of the target heightmap.

    Returns:
        (N, 2) array of (row, col) indices.
    """
    s, w, n, e = bounds
    h, w_grid = grid_shape
    lats_a = np.asarray(lats, dtype=np.float64)
    lngs_a = np.asarray(lngs, dtype=np.float64)
    rows = ((n - lats_a) / (n - s) * (h - 1)).astype(np.int32)
    cols = ((lngs_a - w) / (e - w) * (w_grid - 1)).astype(np.int32)
    rows = np.clip(rows, 0, h - 1)
    cols = np.clip(cols, 0, w_grid - 1)
    return np.column_stack([rows, cols])


def infer_satellite_context(satellite_image: np.ndarray) -> dict[str, Any]:
    """Infer coarse terrain context from a satellite-style image.

    The goal is not full semantic segmentation, but to provide a conservative signal
    for likely water bodies so the generator does not invent water in dry terrain.
    """
    if satellite_image is None:
        return {"water_mask": np.zeros((0, 0), dtype=bool), "confidence": 0.0}

    img = np.asarray(satellite_image)
    if img.ndim == 2:
        img = np.repeat(img[:, :, None], 3, axis=2)
    if img.shape[0] == 0 or img.shape[1] == 0:
        return {"water_mask": np.zeros((0, 0), dtype=bool), "confidence": 0.0}

    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    _, mask = cv2.threshold(gray, 110, 255, cv2.THRESH_BINARY_INV)
    blue_channel = img[:, :, 2].astype(np.float32)
    green_channel = img[:, :, 1].astype(np.float32)
    red_channel = img[:, :, 0].astype(np.float32)

    blue_bias = (blue_channel > green_channel + 20) & (blue_channel > red_channel + 20)
    dark_pixels = gray < 140
    water_mask = blue_bias & dark_pixels & (mask > 0)
    water_mask = cv2.medianBlur(water_mask.astype(np.uint8), 5).astype(bool)

    confidence = float(water_mask.mean()) if water_mask.size else 0.0
    return {"water_mask": water_mask, "confidence": confidence}


def integrate_osm_features(
    heightmap: np.ndarray,
    osm_features: dict,
    bounds: tuple[float, float, float, float],
    satellite_context: dict[str, Any] | None = None,
) -> tuple[np.ndarray, dict]:
    """Carve OSM features into the heightmap.

    Modifies the heightmap in-place:
      - Roads: flattened to surrounding ground level.
      - Buildings: flattened (cleared) with a small buffer.
      - Water: set to heightmap minimum (sea level).
      - Parks: smoothed (slightly flattened).

    Returns:
        (modified heightmap, feature mask dict)
    """
    h, w = heightmap.shape
    masks = {}

    # Water: apply only when OSM evidence and satellite context both agree.
    water_coords = []
    for feat in osm_features.get("water", []):
        lats = [c[0] for c in feat["coords"]]
        lngs = [c[1] for c in feat["coords"]]
        pts = geo_to_block_coords(lats, lngs, bounds, (h, w))
        water_coords.extend(pts.tolist())

    satellite_mask = None
    if satellite_context:
        sat_mask = np.asarray(satellite_context.get("water_mask", np.zeros((h, w), dtype=bool)))
        if sat_mask.shape != (h, w):
            sat_mask = cv2.resize(sat_mask.astype(np.uint8), (w, h), interpolation=cv2.INTER_LINEAR).astype(bool)
        satellite_mask = sat_mask

    if water_coords:
        yy = np.array([p[0] for p in water_coords])
        xx = np.array([p[1] for p in water_coords])
        mask = np.zeros((h, w), dtype=bool)
        yy = np.clip(yy, 0, h - 1)
        xx = np.clip(xx, 0, w - 1)
        mask[yy, xx] = True
        if has_binary_dilation:
            try:
                from scipy.ndimage import binary_dilation
                mask = binary_dilation(mask, iterations=2)
            except ImportError:
                pass
        if satellite_mask is not None and satellite_mask.any():
            mask &= satellite_mask
        if not mask.any():
            mask = np.zeros((h, w), dtype=bool)
        sea_level = float(np.percentile(heightmap, 5))
        heightmap[mask] = sea_level
        masks["water"] = mask

    # Roads: flatten to local ground
    for feat in osm_features.get("roads", []):
        lats = [c[0] for c in feat["coords"]]
        lngs = [c[1] for c in feat["coords"]]
        pts = geo_to_block_coords(lats, lngs, bounds, (h, w))
        if len(pts) < 2:
            continue
        road_width = _road_width(feat.get("type", "road"))
        _carve_path(heightmap, pts, road_width, heightmap)

    # Buildings: clear to flat
    for feat in osm_features.get("buildings", []):
        lats = [c[0] for c in feat["coords"]]
        lngs = [c[1] for c in feat["coords"]]
        pts = geo_to_block_coords(lats, lngs, bounds, (h, w))
        if len(pts) < 3:
            continue
        _flatten_polygon(heightmap, pts, heightmap)

    # Parks: gentle smoothing
    park_coords = []
    for feat in osm_features.get("parks", []):
        lats = [c[0] for c in feat["coords"]]
        lngs = [c[1] for c in feat["coords"]]
        pts = geo_to_block_coords(lats, lngs, bounds, (h, w))
        park_coords.extend(pts.tolist())

    if park_coords:
        yy = np.array([p[0] for p in park_coords])
        xx = np.array([p[1] for p in park_coords])
        yy = np.clip(yy, 0, h - 1)
        xx = np.clip(xx, 0, w - 1)
        mask_p = np.zeros((h, w), dtype=bool)
        mask_p[yy, xx] = True
        try:
            from scipy.ndimage import uniform_filter
            smooth = uniform_filter(heightmap, size=7)
            heightmap[mask_p] = smooth[mask_p]
        except ImportError:
            pass
        masks["parks"] = mask_p

    return heightmap, masks


try:
    from scipy.ndimage import binary_dilation as _bdi
    has_binary_dilation = True
except ImportError:
    has_binary_dilation = False


def _road_width(highway_type: str) -> int:
    return {
        "motorway": 5,
        "trunk": 4,
        "primary": 3,
        "secondary": 3,
        "tertiary": 2,
        "residential": 2,
        "track": 1,
        "path": 1,
        "footway": 1,
        "cycleway": 1,
    }.get(highway_type, 2)


def _carve_path(
    heightmap: np.ndarray,
    points: np.ndarray,
    width: int,
    ref_array: np.ndarray,
) -> None:
    """Carve a path (road/river) through the heightmap efficiently."""
    if len(points) < 2:
        return
    h, w = heightmap.shape
    half = width // 2

    # Collect all sample points along the path
    all_ys = []
    all_xs = []
    for i in range(len(points) - 1):
        y1, x1 = points[i]
        y2, x2 = points[i + 1]
        dy = y2 - y1
        dx = x2 - x1
        steps = max(abs(dy), abs(dx)) + 1
        if steps == 0:
            continue
        for t in range(steps + 1):
            frac = t / steps
            yy = int(round(y1 + dy * frac))
            xx = int(round(x1 + dx * frac))
            all_ys.append(yy)
            all_xs.append(xx)

    if not all_ys:
        return

    # Apply road width using vectorized broadcast
    y_arr = np.array(all_ys)
    x_arr = np.array(all_xs)
    wy_offs = np.arange(-half, half + 1)
    wx_offs = np.arange(-half, half + 1)
    yy_all = (y_arr[:, None, None] + wy_offs[None, :, None]).flatten()
    xx_all = (x_arr[:, None, None] + wx_offs[None, None, :]).flatten()
    yy_all = np.clip(yy_all, 0, h - 1)
    xx_all = np.clip(xx_all, 0, w - 1)
    heightmap[yy_all, xx_all] = ref_array[yy_all, xx_all]


def _flatten_polygon(
    heightmap: np.ndarray,
    points: np.ndarray,
    ref_array: np.ndarray,
) -> None:
    """Flatten area within a polygon to its mean height. Uses bounding box optimization."""
    if len(points) < 3:
        return
    h, w = heightmap.shape
    poly = np.asarray(points)

    # Compute bounding box
    y_min = max(0, int(poly[:, 0].min()) - 4)
    y_max = min(h, int(poly[:, 0].max()) + 4)
    x_min = max(0, int(poly[:, 1].min()) - 4)
    x_max = min(w, int(poly[:, 1].max()) + 4)

    if y_max <= y_min or x_max <= x_min:
        return

    # Mean height from reference
    mask_ys = np.clip(poly[:, 0].astype(int), 0, h - 1)
    mask_xs = np.clip(poly[:, 1].astype(int), 0, w - 1)
    mean_h = float(np.mean(ref_array[mask_ys, mask_xs]))

    # Check only pixels in bounding box
    yy, xx = np.mgrid[y_min:y_max, x_min:x_max]
    flat_yy = yy.flatten()
    flat_xx = xx.flatten()
    inside = _points_in_polygon(flat_yy, flat_xx, poly)
    mask = inside.reshape(yy.shape)

    # Apply
    heightmap[y_min:y_max, x_min:x_max][mask] = mean_h


def _points_in_polygon(
    ys: np.ndarray, xs: np.ndarray, polygon: np.ndarray,
) -> np.ndarray:
    """Fast ray-casting point-in-polygon for many points (vectorized).
    Avoids division by zero by skipping horizontal edges."""
    n = len(polygon)
    inside = np.zeros(len(ys), dtype=bool)
    j = n - 1
    for i in range(n):
        yi, xi = polygon[i]
        yj, xj = polygon[j]
        # Skip horizontal edges (division by zero)
        dy = yj - yi
        if dy == 0:
            j = i
            continue
        cond = ((yi > ys) != (yj > ys)) & (xs < (xj - xi) * (ys - yi) / dy + xi)
        inside ^= cond
        j = i
    return inside


# ─────────────────────────────────────────────
# 3. PROCEDURAL OUTPAINTING (fill outside real data)
# ─────────────────────────────────────────────

def procedural_outpaint(
    heightmap: np.ndarray,
    target_size: tuple[int, int],
    seed: int = 42,
    octaves: int = 6,
) -> np.ndarray:
    """Fill a heightmap to `target_size` with procedurally generated terrain
    where real data is missing. Uses Perlin-like noise blended with edge values.

    Args:
        heightmap: Existing heightmap (may be smaller than target).
        target_size: Desired (height, width).
        seed: RNG seed.
        octaves: Noise octaves for detail.

    Returns:
        Filled heightmap of exact target_size.
    """
    th, tw = target_size
    h, w = heightmap.shape

    if h >= th and w >= tw:
        return heightmap[:th, :tw]

    result = np.zeros((th, tw), dtype=np.float32)
    result[:h, :w] = heightmap

    rng = np.random.default_rng(seed)

    # Generate noise for the missing area
    noise = _fbm_noise(th, tw, octaves=octaves, rng=rng)

    # Edge values for seamless blending
    edge_right = heightmap[:, -1:] if w < tw else None
    edge_bottom = heightmap[-1:, :] if h < th else None
    edge_corner = heightmap[-1, -1] if h < th and w < tw else 0.0

    # Fill right extension
    if w < tw:
        for x in range(w, tw):
            frac = (x - w) / max(tw - w - 1, 1)
            for y in range(min(h, th)):
                base = float(edge_right[min(y, h - 1), 0]) if edge_right is not None else 0.0
                noise_val = float(noise[y % th, x % tw]) * 20 * frac
                result[y, x] = base + noise_val

    # Fill bottom extension
    if h < th:
        for y in range(h, th):
            frac = (y - h) / max(th - h - 1, 1)
            for x in range(tw):
                base = float(edge_bottom[0, min(x, w - 1)]) if edge_bottom is not None else 0.0
                noise_val = float(noise[y % th, x % tw]) * 20 * frac
                result[y, x] = base + noise_val

    # Fill bottom-right corner (when both h < th and w < tw)
    if h < th and w < tw:
        for y in range(h, th):
            fy = (y - h) / max(th - h - 1, 1)
            for x in range(w, tw):
                fx = (x - w) / max(tw - w - 1, 1)
                base = edge_corner
                noise_val = float(noise[y % th, x % tw]) * 20 * max(fy, fx)
                result[y, x] = base + noise_val

    return result


def _fbm_noise(
    height: int,
    width: int,
    octaves: int = 6,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """Simple fractal Brownian motion noise."""
    rng = rng or np.random.default_rng()
    noise = np.zeros((height, width), dtype=np.float32)
    amplitude = 1.0
    frequency = 1.0
    max_val = 0.0

    for _ in range(octaves):
        # Generate grid noise and interpolate
        h_small = max(2, int(height / frequency))
        w_small = max(2, int(width / frequency))
        grid = rng.uniform(-1, 1, (h_small, w_small)).astype(np.float32)

        # Upscale to target size
        try:
            import cv2
            up = cv2.resize(grid, (width, height), interpolation=cv2.INTER_LINEAR)
        except ImportError:
            try:
                from scipy.ndimage import zoom
                up = zoom(grid, (height / h_small, width / w_small), order=1)
            except ImportError:
                up = np.kron(grid, np.ones((2, 2)))[:height, :width]

        noise += amplitude * up
        max_val += amplitude
        amplitude *= 0.5
        frequency *= 2.0

    return noise / max_val if max_val > 0 else noise


# ─────────────────────────────────────────────
# 4. BIOME MAP
# ─────────────────────────────────────────────

BIOME_COLORS = {
    "ocean":       (0x00, 0x00, 0x80),
    "beach":       (0xFC, 0xE8, 0xA0),
    "plains":      (0x8D, 0xB3, 0x60),
    "forest":      (0x05, 0x7C, 0x05),
    "dark_forest": (0x05, 0x52, 0x05),
    "taiga":       (0x0B, 0x66, 0x59),
    "swamp":       (0x59, 0x60, 0x0F),
    "desert":      (0xE9, 0xE3, 0x75),
    "savanna":     (0x9B, 0xA4, 0x4E),
    "mountains":   (0x8B, 0x8B, 0x8B),
    "stone":       (0x70, 0x70, 0x70),
    "snow":        (0xF0, 0xF0, 0xF0),
}


def generate_biome_map(
    heightmap: np.ndarray,
    osm_features: dict | None = None,
    sea_level_percentile: float = 10.0,
) -> np.ndarray:
    """Generate a Minecraft-style biome map from heightmap and optional OSM features.

    Returns:
        2D uint8 array where each value maps to a biome index.
    """
    h, w = heightmap.shape
    h_min = float(heightmap.min())
    h_max = float(heightmap.max())
    sea_level = float(np.percentile(heightmap, sea_level_percentile))

    biomes = np.zeros((h, w), dtype=np.uint8)

    # Water
    biomes[heightmap <= sea_level] = 0  # ocean

    # Elevation-based biomes
    land = heightmap > sea_level
    h_range = h_max - sea_level if h_max > sea_level else 1.0

    # Normalize land elevation 0-1
    land_h = (heightmap - sea_level) / h_range

    # Beach (within 1m of sea level)
    beach = (heightmap > sea_level) & (heightmap <= sea_level + 2.0)
    biomes[beach] = 1  # beach

    # Low elevation: plains / swamp
    low = land & (land_h <= 0.2) & ~beach
    biomes[low] = 2  # plains

    # Mid-low: forest
    mid_low = land & (land_h > 0.2) & (land_h <= 0.4) & ~beach
    biomes[mid_low] = 3  # forest

    # Mid: taiga / dark forest
    mid = land & (land_h > 0.4) & (land_h <= 0.6) & ~beach
    biomes[mid] = 4  # dark_forest

    # Mid-high: savanna / desert
    mid_high = land & (land_h > 0.6) & (land_h <= 0.8) & ~beach
    biomes[mid_high] = 5  # savanna

    # High: stone / mountains
    high = land & (land_h > 0.8) & (land_h <= 0.95) & ~beach
    biomes[high] = 6  # mountains

    # Peak: snow
    peak = land & (land_h > 0.95) & ~beach
    biomes[peak] = 7  # snow

    # Apply OSM water override
    return biomes


def biome_to_height_adjustment(biome_id: int) -> float:
    """Return height offset for a given biome."""
    return {
        0: -10.0,   # ocean
        1: 0.0,     # beach
        2: 0.0,     # plains
        3: 2.0,     # forest
        4: 3.0,     # dark_forest
        5: 0.0,     # savanna
        6: 5.0,     # mountains (already high)
        7: 10.0,    # snow
    }.get(biome_id, 0.0)


# ─────────────────────────────────────────────
# 5. WORLD BUILDER (high-level)
# ─────────────────────────────────────────────

class WorldBuilder:
    """Orchestrates the full world generation from geo data."""

    def __init__(self, diameter_blocks: int = 10000):
        self.diameter = diameter_blocks
        self.heightmap: np.ndarray | None = None
        self.biome_map: np.ndarray | None = None
        self.satellite_image: np.ndarray | None = None
        self.feature_masks: dict = {}
        self.flat_zones: list = []
        self.osm_features: dict = {}
        self.origin: tuple[float, float] = (0.0, 0.0)
        self.bounds: tuple[float, float, float, float] = (0, 0, 0, 0)
        self.context_engine = LocalGeoContextEngine()
        self.urban_context = UrbanContextModel()

    def from_srtm(
        self,
        srtm_hmap: np.ndarray,
        srtm_bounds: tuple[float, float, float, float],
        osm_features: dict | None = None,
    ) -> None:
        """Build world from SRTM data and optional OSM features."""
        self.bounds = srtm_bounds
        self.osm_features = osm_features or {}
        self.origin = (srtm_bounds[0], srtm_bounds[1])  # south-west corner

        target = (self.diameter, self.diameter)

        # Upscale
        hmap = upscale_heightmap(srtm_hmap, target, method="bicubic")

        # Outpaint to fill diameter
        if hmap.shape[0] < self.diameter or hmap.shape[1] < self.diameter:
            hmap = procedural_outpaint(hmap, target, seed=int(round(self.origin[0] * 100 + self.origin[1] * 100)))

        # Learn from prior maps and bias generation toward similar real-world patterns
        context = self.context_engine.predict_for(srtm_bounds)
        self.context_summary = context

        # Integrate OSM features with conservative satellite-based water validation
        satellite_context = None
        if getattr(self, "satellite_image", None) is not None:
            satellite_context = infer_satellite_context(self.satellite_image)
        if osm_features:
            hmap, masks = integrate_osm_features(hmap, osm_features, srtm_bounds, satellite_context=satellite_context)
            self.feature_masks = masks

        if context.get("water_bias", 0.0) > 0.25:
            hmap = hmap - float(context["water_bias"]) * 4.0
        if context.get("building_density", 0.0) > 0.25:
            hmap = hmap + float(context["building_density"]) * 1.5

        if osm_features:
            hmap = self.urban_context.apply_to_heightmap(hmap, osm_features)

        # Normalize to Minecraft height range (sea level = 63, max ~200)
        hmap = self._normalize_to_minecraft(hmap)

        self.heightmap = hmap
        self.biome_map = generate_biome_map(hmap, osm_features)

        # Remember this build for future map generations
        self.context_engine.remember(
            bounds=srtm_bounds,
            summary={
                "building_density": min(1.0, max(0.0, float(context.get("building_density", 0.0)) + 0.1)),
                "water_bias": min(1.0, max(0.0, float(context.get("water_bias", 0.0)) + 0.05)),
                "road_density": min(1.0, max(0.0, float(context.get("road_density", 0.0)) + 0.05)),
            },
        )

        # Detect flat zones
        self.flat_zones = find_flat_zones(
            self._to_8bit(hmap),
            min_area=200,
        )

    def _normalize_to_minecraft(self, hmap: np.ndarray) -> np.ndarray:
        """Normalize elevation values to Minecraft-compatible range."""
        sea_level = np.percentile(hmap, 10)
        max_el = np.percentile(hmap, 99)

        # Scale so that sea_level → 63 (sea level in MC)
        # and max → ~200 (build height)
        hmap_mc = 63.0 + (hmap - sea_level) * (140.0 / max(max_el - sea_level, 1))
        hmap_mc = np.clip(hmap_mc, 60, 220)
        return hmap_mc.astype(np.float32)

    def _to_8bit(self, hmap: np.ndarray) -> np.ndarray:
        """Convert to 0-255 uint8 for compatibility with existing functions."""
        h = hmap.copy()
        h = (h - h.min()) / max(h.max() - h.min(), 1) * 255
        return h.astype(np.uint8)

    def get_export_heightmap(self) -> np.ndarray:
        """Return a uint8 heightmap suitable for PNG export."""
        return self._to_8bit(self.heightmap)
