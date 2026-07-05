"""Image / DEM preprocessing engine."""

from pathlib import Path
import numpy as np
import cv2


def load_heightmap(path: Path, target_size: tuple[int, int] = (512, 512)) -> np.ndarray:
    img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise ValueError(f"Cannot load image from {path}")
    resized = cv2.resize(img, target_size, interpolation=cv2.INTER_LANCZOS4)
    return resized.astype(np.float32)


def contours_from_map(heightmap: np.ndarray, threshold: int = 128) -> list[np.ndarray]:
    _, binary = cv2.threshold(heightmap.astype(np.uint8), threshold, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    return contours


def find_flat_zones(
    heightmap: np.ndarray, slope_threshold: float = 5.0, min_area: int = 400
) -> list[tuple[int, int, int, int]]:
    grad_x = cv2.Sobel(heightmap, cv2.CV_32F, 1, 0, ksize=3)
    grad_y = cv2.Sobel(heightmap, cv2.CV_32F, 0, 1, ksize=3)
    slope = np.sqrt(grad_x ** 2 + grad_y ** 2)

    flat_mask = slope < slope_threshold
    flat_mask = (flat_mask * 255).astype(np.uint8)

    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(flat_mask, connectivity=8)
    zones = []
    for i in range(1, num_labels):
        area = stats[i, cv2.CC_STAT_AREA]
        if area >= min_area:
            x = stats[i, cv2.CC_STAT_LEFT]
            y = stats[i, cv2.CC_STAT_TOP]
            w = stats[i, cv2.CC_STAT_WIDTH]
            h = stats[i, cv2.CC_STAT_HEIGHT]
            zones.append((int(x), int(y), int(w), int(h)))
    return zones


def classify_terrain(heightmap: np.ndarray) -> str:
    grad_x = cv2.Sobel(heightmap, cv2.CV_32F, 1, 0, ksize=3)
    grad_y = cv2.Sobel(heightmap, cv2.CV_32F, 0, 1, ksize=3)
    mean_slope = np.mean(np.sqrt(grad_x ** 2 + grad_y ** 2))

    low = np.percentile(heightmap, 10)
    high = np.percentile(heightmap, 90)
    vertical_relief = high - low

    if mean_slope < 8 and vertical_relief < 20:
        return "flat"
    elif mean_slope > 30:
        return "mountain"
    else:
        return "coastal"


def normalize_heightmap(heightmap: np.ndarray, target_min: int = 4, target_max: int = 128) -> np.ndarray:
    h_min, h_max = heightmap.min(), heightmap.max()
    if h_max == h_min:
        return np.full_like(heightmap, target_min)
    normalized = (heightmap - h_min) / (h_max - h_min)
    return (normalized * (target_max - target_min) + target_min).astype(np.float32)
