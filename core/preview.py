"""Terrain preview engine — generates visualization images."""

import io
import base64
import numpy as np
import cv2
from pathlib import Path
from dataclasses import dataclass, asdict


@dataclass
class TerrainInfo:
    width: int
    height: int
    min_height: float
    max_height: float
    mean_height: float
    terrain_type: str
    flat_zone_count: int
    flat_zones: list[dict]
    contours: int


def analyse_terrain(
    heightmap: np.ndarray,
    flat_zones: list[tuple[int, int, int, int]],
    terrain_type: str,
) -> TerrainInfo:
    zones_dict = [
        {"x": x, "z": z, "w": w, "h": h, "area": w * h}
        for x, z, w, h in flat_zones
    ]
    _, binary = cv2.threshold(heightmap.astype(np.uint8), 128, 255, cv2.THRESH_BINARY)
    contours_found, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    return TerrainInfo(
        width=heightmap.shape[1],
        height=heightmap.shape[0],
        min_height=round(float(heightmap.min()), 1),
        max_height=round(float(heightmap.max()), 1),
        mean_height=round(float(heightmap.mean()), 1),
        terrain_type=terrain_type,
        flat_zone_count=len(flat_zones),
        flat_zones=sorted(zones_dict, key=lambda z: -z["area"]),
        contours=len(contours_found),
    )


def render_contour_map(heightmap: np.ndarray) -> np.ndarray:
    """Return BGR image with contour lines overlaid."""
    gray = heightmap.astype(np.uint8)
    color = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    edges = cv2.Canny(gray, 30, 100)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(color, contours, -1, (0, 200, 255), 1)
    return color


def render_flat_zone_map(
    heightmap: np.ndarray,
    flat_zones: list[tuple[int, int, int, int]],
) -> np.ndarray:
    """Return BGR image with flat zones highlighted in green."""
    gray = heightmap.astype(np.uint8)
    color = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    overlay = color.copy()

    for x, z, w, h in flat_zones:
        cv2.rectangle(overlay, (x, z), (x + w, z + h), (0, 220, 0), -1)
        cv2.rectangle(color, (x, z), (x + w, z + h), (0, 255, 0), 2)
        label = f"{w}x{h}"
        cv2.putText(color, label, (x + 4, z + 16),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)

    return cv2.addWeighted(overlay, 0.25, color, 0.75, 0)


def render_stage_map(
    heightmap: np.ndarray,
    flat_zones: list[tuple[int, int, int, int]],
    plan: "FestivalPlan | None" = None,
) -> np.ndarray:
    """Return BGR image with stages, camping, and paths plotted."""
    from .layout import FestivalPlan

    gray = heightmap.astype(np.uint8)
    color = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)

    for x, z, w, h in flat_zones:
        cv2.rectangle(color, (x, z), (x + w, z + h), (60, 60, 60), 1)

    if plan is not None:
        ms = plan.main_stage
        cv2.circle(color, (ms.x, ms.z), ms.radius, (0, 0, 255), 2)
        cv2.circle(color, (ms.x, ms.z), 4, (0, 0, 255), -1)
        cv2.putText(color, "MAIN STAGE", (ms.x - 40, ms.z - ms.radius - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)

        for ss in plan.secondary_stages:
            cv2.circle(color, (ss.x, ss.z), ss.radius, (255, 165, 0), 2)
            cv2.circle(color, (ss.x, ss.z), 3, (255, 165, 0), -1)
            cv2.putText(color, ss.name.upper(), (ss.x - 30, ss.z - ss.radius - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 165, 0), 1)

        for c in plan.camping:
            cv2.rectangle(color, (c.x, c.z), (c.x + c.width, c.z + c.depth),
                          (255, 255, 0), 2)
            cv2.putText(color, "CAMP", (c.x + 4, c.z + 14),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 0), 1)

        for p in plan.paths:
            cv2.line(color, p.start, p.end, (200, 200, 200), 1, cv2.LINE_AA)

        ex, ez = plan.entrance
        cv2.rectangle(color, (ex - 6, ez - 6), (ex + 6, ez + 6), (0, 255, 255), -1)
        cv2.putText(color, "ENTRANCE", (ex + 10, ez + 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)

    return color


def render_all_maps(
    heightmap: np.ndarray,
    flat_zones: list[tuple[int, int, int, int]],
    plan: "FestivalPlan | None" = None,
) -> dict[str, np.ndarray]:
    return {
        "contours": render_contour_map(heightmap),
        "flat_zones": render_flat_zone_map(heightmap, flat_zones),
        "stage_plan": render_stage_map(heightmap, flat_zones, plan),
    }


def img_to_base64(img: np.ndarray) -> str:
    """Convert OpenCV BGR image to base64 data URI."""
    _, buf = cv2.imencode(".png", img)
    return base64.b64encode(buf).decode()


def img_to_bytes(img: np.ndarray) -> bytes:
    _, buf = cv2.imencode(".png", img)
    return buf.tobytes()


def try_3d_plot(heightmap: np.ndarray, output_path: Path) -> bool:
    """Attempt a 3D surface plot using matplotlib. Returns True on success."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from mpl_toolkits.mplot3d import Axes3D  # noqa

        fig = plt.figure(figsize=(10, 8))
        ax = fig.add_subplot(111, projection="3d")

        h, w = heightmap.shape
        X, Y = np.meshgrid(np.arange(w), np.arange(h))
        stride = max(1, min(h, w) // 64)

        surf = ax.plot_surface(
            X[::stride, ::stride],
            Y[::stride, ::stride],
            heightmap[::stride, ::stride],
            cmap="terrain",
            linewidth=0,
            antialiased=True,
        )
        fig.colorbar(surf, ax=ax, shrink=0.5, aspect=10, label="Height")
        ax.set_xlabel("X (blocks)")
        ax.set_ylabel("Z (blocks)")
        ax.set_zlabel("Height")
        ax.set_title("FestivalWorld Terrain — 3D Preview")

        fig.savefig(str(output_path), dpi=120, bbox_inches="tight")
        plt.close(fig)
        return True
    except ImportError:
        return False
    except Exception:
        return False
