"""Geo data pipeline — geocoding, SRTM elevation, OSM features, satellite imagery.

All data is cached locally. Uses free APIs (Nominatim, OpenTopography, Overpass).
No API keys required — rate-limited but suitable for offline/personal use.
"""

import io
import json
import math
import struct
import time
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import numpy as np

CACHE_DIR = Path.home() / ".cache" / "festivalworld"
USER_AGENT = "FestivalWorldBuilder/1.0 (local-tool)"


# ─────────────────────────────────────────────
# 1. PLACE SEARCH (Nominatim)
# ─────────────────────────────────────────────

def search_place(query: str, limit: int = 5) -> list[dict]:
    """Search for a place by name. Returns list of {name, lat, lng, bounds, type}."""
    url = (
        "https://nominatim.openstreetmap.org/search?"
        + urlencode({"q": query, "format": "json", "limit": limit, "addressdetails": "1"})
    )
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=15) as resp:
        results = json.loads(resp.read())

    places = []
    for r in results:
        b = r.get("boundingbox", [])
        places.append({
            "name": r.get("display_name", ""),
            "lat": float(r["lat"]),
            "lng": float(r["lon"]),
            "bounds": (
                float(b[0]) if len(b) > 0 else float(r["lat"]) - 0.05,
                float(b[2]) if len(b) > 2 else float(r["lon"]) - 0.05,
                float(b[1]) if len(b) > 1 else float(r["lat"]) + 0.05,
                float(b[3]) if len(b) > 3 else float(r["lon"]) + 0.05,
            ) if b else None,
            "type": r.get("type", "unknown"),
            "osm_id": r.get("osm_id"),
        })
    return places


# ─────────────────────────────────────────────
# 2. ELEVATION (SRTM — multi-source with fallback)
# ─────────────────────────────────────────────

def _srtm_cache_path(bounds: tuple[float, float, float, float]) -> Path:
    key = f"srtm_{bounds[0]:.4f}_{bounds[1]:.4f}_{bounds[2]:.4f}_{bounds[3]:.4f}.npy"
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / key





def _optimal_zoom(bounds: tuple[float, float, float, float]) -> int:
    """Pick the best zoom level for terrain tiles covering the bounds.
    
    z10: ~20km/tile, z11: ~10km/tile, z12: ~6km/tile, z13: ~3km/tile
    """
    s, w, n, e = bounds
    lat_span = n - s
    lng_span = e - w
    diag_deg = math.sqrt(lat_span ** 2 + lng_span ** 2)
    # ~111km per degree, tile at z covers ~360/2^z * 111 km at equator
    for z in range(14, 5, -1):
        tile_span = 360.0 / (2 ** z)
        if tile_span * 2 >= diag_deg:
            return z
    return 10


def _tile_xy(lat: float, lng: float, zoom: int) -> tuple[int, int]:
    """Convert lat/lng to Web Mercator tile x,y."""
    n = 2.0 ** zoom
    x = int((lng + 180.0) / 360.0 * n)
    y = int((1.0 - math.log(
        math.tan(math.radians(lat)) + 1.0 / math.cos(math.radians(lat))
    ) / math.pi) / 2.0 * n)
    return x, y


def _tile_bounds(x: int, y: int, zoom: int) -> tuple[float, float, float, float]:
    """Get (south, west, north, east) for a tile."""
    n = 2.0 ** zoom
    lng = x / n * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    lng2 = (x + 1) / n * 360.0 - 180.0
    lat2 = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n))))
    return (lat2, lng, lat, lng2)  # s,w,n,e


def _download_terrain_tile(x: int, y: int, zoom: int) -> np.ndarray | None:
    """Download a single terrain tile from AWS Open Data.

    Returns 512x512 float32 array or None.
    """
    url = f"https://s3.amazonaws.com/elevation-tiles-prod/geotiff/{zoom}/{x}/{y}.tif"
    req = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(req, timeout=30) as resp:
            data = resp.read()
    except HTTPError:
        return None

    try:
        from PIL import Image
        img = Image.open(io.BytesIO(data))
        arr = np.array(img, dtype=np.float32)
        arr[arr < -1000] = 0.0  # void pixels
        return arr
    except Exception:
        return None


def download_srtm(
    bounds: tuple[float, float, float, float],
    resolution: str = "SRTMGL3",
    force: bool = False,
    api_key: str = "",
) -> np.ndarray:
    """Download elevation data for the given bounding box.

    Primary source: AWS Open Data terrain tiles (free, no key).
    Fallback: OpenTopography API (requires api_key).

    Args:
        bounds: (south, west, north, east) in decimal degrees.
        resolution: Ignored (uses best available AWS data).
        force: Re-download even if cached.
        api_key: OpenTopography API key (optional fallback).

    Returns:
        2D numpy array of float32 elevation values (meters).
    """
    cache = _srtm_cache_path(bounds)
    if cache.exists() and not force:
        return np.load(cache)

    s, w, n, e = bounds
    zoom = _optimal_zoom(bounds)

    # Primary: AWS Open Data terrain tiles
    try:
        hmap = _download_aws_terrain(bounds, zoom)
        if hmap is not None:
            np.save(cache, hmap)
            return hmap
    except Exception:
        pass

    # Fallback: OpenTopography with API key
    if api_key:
        try:
            hmap = _download_opentopography(bounds, resolution, api_key)
            if hmap is not None:
                np.save(cache, hmap)
                return hmap
        except Exception:
            pass

    raise RuntimeError(
        "Could not download elevation data. "
        "Please ensure internet access. "
        "For areas outside the US, you may need an OpenTopography API key."
    )


def _download_aws_terrain(
    bounds: tuple[float, float, float, float],
    zoom: int,
) -> np.ndarray | None:
    """Download and mosaic AWS Open Data terrain tiles for the given bounds."""
    s, w, n, e = bounds

    # Find all tiles covering the bounds
    x1, y1 = _tile_xy(n, w, zoom)  # top-left
    x2, y2 = _tile_xy(s, e, zoom)  # bottom-right

    x1, x2 = min(x1, x2), max(x1, x2)
    y1, y2 = min(y1, y2), max(y1, y2)

    tiles: list[tuple[int, int, np.ndarray]] = []
    tile_size = 512  # AWS tiles are 512x512

    for x in range(x1, x2 + 1):
        for y in range(y1, y2 + 1):
            t = _download_terrain_tile(x, y, zoom)
            if t is not None:
                tiles.append((x, y, t))

    if not tiles:
        return None

    # Mosaic tiles
    n_x = x2 - x1 + 1
    n_y = y2 - y1 + 1
    full = np.zeros((n_y * tile_size, n_x * tile_size), dtype=np.float32)

    for (tx, ty, data) in tiles:
        ix = (tx - x1) * tile_size
        iy = (ty - y1) * tile_size
        h, w_data = data.shape
        full[iy:iy + h, ix:ix + w_data] = data

    # Convert 180-degree coordinate system: tile Y increases southward
    # But we want it increasing northward for our convention
    full = full[::-1, :]  # flip Y

    # Crop to exact bounds (approximate pixel-based)
    # Full covers from tile_bounds(x1,y2+1) to tile_bounds(x2+1,y1)
    tb_s, tb_w, tb_n, tb_e = _tile_bounds(x1, y1, zoom)
    tb_s2, tb_w2, tb_n2, tb_e2 = _tile_bounds(x2, y1, zoom)
    tb_s3, tb_w3, tb_n3, tb_e3 = _tile_bounds(x1, y2, zoom)
    # The full array covers: lat tb_s3 to tb_n, lng tb_w to tb_e2
    full_s = max(s, min(x1, x2))  # approximate
    # Actually: compute exact pixel crop
    # Full covers from tb_s (south) to tb_n (north) in Y
    # and from tb_w (west) to tb_e2 (east) in X
    actual_s = tb_s3
    actual_n = tb_n
    actual_w = tb_w
    actual_e = tb_e2

    h_full, w_full = full.shape
    px_top = int(((actual_n - n) / (actual_n - actual_s)) * h_full)
    px_bottom = int(((actual_n - s) / (actual_n - actual_s)) * h_full)
    px_left = int(((w - actual_w) / (actual_e - actual_w)) * w_full)
    px_right = int(((e - actual_w) / (actual_e - actual_w)) * w_full)

    px_top = max(0, px_top)
    px_bottom = min(h_full, px_bottom)
    px_left = max(0, px_left)
    px_right = min(w_full, px_right)

    if px_bottom > px_top and px_right > px_left:
        full = full[px_top:px_bottom, px_left:px_right]

    return full


def _download_opentopography(
    bounds: tuple, resolution: str, api_key: str,
) -> np.ndarray | None:
    """Download via OpenTopography API."""
    s, w, n, e = bounds
    params: dict = {
        "demtype": resolution,
        "south": s, "west": w, "north": n, "east": e,
        "output": "GTiff",
    }
    if api_key:
        params["API_key"] = api_key

    url = "https://portal.opentopography.org/API/globaldem?" + urlencode(params)
    req = Request(url, headers={"User-Agent": USER_AGENT})

    try:
        with urlopen(req, timeout=120) as resp:
            data = resp.read()
    except HTTPError:
        return None

    return _parse_geotiff_band(data)


def _parse_geotiff_band(data: bytes) -> np.ndarray | None:
    """Extract first band from GeoTIFF."""
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(data))
        return np.array(img, dtype=np.float32)
    except Exception:
        pass

    # Raw 32-bit float GeoTIFF fallback
    for offset in [0, 512, 1024, 2048]:
        try:
            arr = np.frombuffer(data, dtype=">f4", offset=offset)
            if len(arr) > 1000 and not np.all(arr == 0):
                size = int(math.isqrt(len(arr)))
                if size * size <= len(arr):
                    return arr[: size * size].reshape(size, size)
        except Exception:
            continue

    return None





# ─────────────────────────────────────────────
# 3. OPENSTREETMAP FEATURES (Overpass API)
# ─────────────────────────────────────────────

def _osm_cache_path(bounds: tuple) -> Path:
    key = f"osm_{bounds[0]:.4f}_{bounds[1]:.4f}_{bounds[2]:.4f}_{bounds[3]:.4f}.json"
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / key


def download_osm_features(
    bounds: tuple[float, float, float, float],
    force: bool = False,
) -> dict:
    """Download OSM features (roads, buildings, water, landuse) for bounds.

    Returns dict with keys: roads, buildings, water, landuse
    Each is a list of {type, coords, tags, id}.
    """
    cache = _osm_cache_path(bounds)
    if cache.exists() and not force:
        return json.loads(cache.read_text())

    s, w, n, e = bounds
    overpass_query = f"""
    [out:json][timeout:90];
    (
      way["highway"]({s},{w},{n},{e});
      way["building"]({s},{w},{n},{e});
      way["natural"="water"]({s},{w},{n},{e});
      relation["natural"="water"]({s},{w},{n},{e});
      way["landuse"]({s},{w},{n},{e});
      way["waterway"]({s},{w},{n},{e});
      way["leisure"="park"]({s},{w},{n},{e});
      way["leisure"="pitch"]({s},{w},{n},{e});
    );
    out body;
    >;
    out skel qt;
    """

    url = "https://overpass-api.de/api/interpreter"
    req = Request(
        url,
        data=urlencode({"data": overpass_query}).encode(),
        headers={"User-Agent": USER_AGENT, "Content-Type": "application/x-www-form-urlencoded"},
    )

    with urlopen(req, timeout=120) as resp:
        raw = json.loads(resp.read())

    features = _classify_osm_elements(raw, bounds)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(features, indent=2))
    return features


def _classify_osm_elements(raw: dict, bounds: tuple) -> dict:
    """Classify OSM elements into roads, buildings, water, landuse."""
    nodes = {}
    ways = {}

    for el in raw.get("elements", []):
        if el["type"] == "node":
            nodes[el["id"]] = (el.get("lat", 0), el.get("lon", 0))
        elif el["type"] == "way":
            ways[el["id"]] = el

    result = {"roads": [], "buildings": [], "water": [], "landuse": [], "parks": []}

    for wid, way in ways.items():
        tags = way.get("tags", {})
        coords = [
            (nodes[n][0], nodes[n][1])
            for n in way.get("nodes", [])
            if n in nodes
        ]
        if not coords:
            continue

        entry = {"id": wid, "coords": coords, "tags": tags}

        if "highway" in tags:
            entry["type"] = tags.get("highway", "road")
            entry["name"] = tags.get("name", "")
            result["roads"].append(entry)
        elif "building" in tags:
            entry["type"] = tags.get("building", "yes")
            result["buildings"].append(entry)
        elif tags.get("natural") == "water" or "waterway" in tags:
            entry["type"] = tags.get("natural", tags.get("waterway", "water"))
            entry["name"] = tags.get("name", "")
            result["water"].append(entry)
        elif "landuse" in tags:
            entry["type"] = tags["landuse"]
            result["landuse"].append(entry)
        elif "leisure" in tags:
            entry["type"] = tags["leisure"]
            result["parks"].append(entry)

    return result


# ─────────────────────────────────────────────
# 4. SATELLITE IMAGERY (Tile download)
# ─────────────────────────────────────────────

def _tile_coords(lat: float, lng: float, zoom: int) -> tuple[int, int]:
    """Convert lat/lng to tile x/y at given zoom level."""
    n = 2.0 ** zoom
    x = int((lng + 180.0) / 360.0 * n)
    y = int((1.0 - math.log(math.tan(math.radians(lat)) + 1.0 / math.cos(math.radians(lat))) / math.pi) / 2.0 * n)
    return x, y


def download_satellite_tile(
    lat: float, lng: float, zoom: int = 15,
    tile_url: str = "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
) -> bytes:
    """Download a single map tile at the given lat/lng/zoom."""
    x, y = _tile_coords(lat, lng, zoom)
    url = tile_url.format(z=zoom, x=x, y=y)
    req = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(req, timeout=15) as resp:
            return resp.read()
    except HTTPError:
        return b""


# ─────────────────────────────────────────────
# 5. COORDINATE UTILITIES
# ─────────────────────────────────────────────

def latlng_to_block(lat: float, lng: float, origin: tuple[float, float], scale: float = 1.0) -> tuple[int, int]:
    """Convert (lat, lng) to Minecraft block coordinates.

    Uses simple equirectangular projection. scale = blocks per meter.
    At the equator, 1° ≈ 111320 m.
    """
    ori_lat, ori_lng = origin
    R = 111320.0  # meters per degree at equator
    dx = (lng - ori_lng) * R * math.cos(math.radians(ori_lat)) * scale
    dz = (lat - ori_lat) * R * scale  # Minecraft Z points south, lat increases north
    return (int(round(dx)), int(round(-dz)))  # Flip Z so -Z = north


def bounds_to_blocks(
    bounds: tuple[float, float, float, float],
    scale: float = 1.0,
) -> tuple[int, int, int, int]:
    """Convert geo bounds to Minecraft block extents."""
    s, w, n, e = bounds
    ori = (s, w)
    x1, z1 = latlng_to_block(n, w, ori, scale)
    x2, z2 = latlng_to_block(n, e, ori, scale)
    x3, z3 = latlng_to_block(s, w, ori, scale)
    x4, z4 = latlng_to_block(s, e, ori, scale)
    min_x = min(x1, x2, x3, x4)
    max_x = max(x1, x2, x3, x4)
    min_z = min(z1, z2, z3, z4)
    max_z = max(z1, z2, z3, z4)
    return min_x, min_z, max_x, max_z


def expand_bounds_to_diameter(
    center: tuple[float, float],
    diameter_km: float = 10.0,
) -> tuple[float, float, float, float]:
    """Expand a center point to a bounding box covering `diameter_km` across."""
    lat, lng = center
    R = 111320.0
    half_deg_lat = (diameter_km * 500) / R
    half_deg_lng = half_deg_lat / math.cos(math.radians(lat))
    return (lat - half_deg_lat, lng - half_deg_lng, lat + half_deg_lat, lng + half_deg_lng)
