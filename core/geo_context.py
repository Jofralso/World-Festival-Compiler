"""Local memory engine for learning from prior geographic builds.

This module stores lightweight summaries from past map generations and uses them to
improve future terrain and structure placement decisions without requiring remote APIs.
"""

import json
import math
from pathlib import Path
from typing import Any


class LocalGeoContextEngine:
    """Simple local memory model for geographic context learning."""

    def __init__(self, memory_path: Path | None = None):
        self.memory_path = memory_path or Path.home() / ".cache" / "festivalworld" / "geo_memory.json"
        self.memory_path.parent.mkdir(parents=True, exist_ok=True)
        self._memory: list[dict[str, Any]] = self._load()

    def _load(self) -> list[dict[str, Any]]:
        if not self.memory_path.exists():
            return []
        try:
            data = json.loads(self.memory_path.read_text())
            if isinstance(data, list):
                return data
        except Exception:
            pass
        return []

    def _save(self) -> None:
        self.memory_path.write_text(json.dumps(self._memory, indent=2))

    def remember(self, bounds: tuple[float, float, float, float], summary: dict[str, Any]) -> None:
        self._memory.append({"bounds": bounds, "summary": summary})
        self._save()

    def predict_for(self, bounds: tuple[float, float, float, float]) -> dict[str, float]:
        if not self._memory:
            return {"building_density": 0.0, "water_bias": 0.0, "road_density": 0.0}

        center_lat = (bounds[0] + bounds[2]) / 2.0
        center_lng = (bounds[1] + bounds[3]) / 2.0
        scores: list[tuple[float, dict[str, Any]]] = []
        for item in self._memory:
            b = item["bounds"]
            lat = (b[0] + b[2]) / 2.0
            lng = (b[1] + b[3]) / 2.0
            dist = math.hypot(center_lat - lat, center_lng - lng)
            scores.append((dist, item["summary"]))

        scores.sort(key=lambda t: t[0])
        weighted = {"building_density": 0.0, "water_bias": 0.0, "road_density": 0.0}
        total_weight = 0.0
        for dist, summary in scores[:5]:
            weight = max(0.05, 1.0 / (1.0 + dist))
            total_weight += weight
            for key in weighted:
                weighted[key] += weight * float(summary.get(key, 0.0))

        if total_weight:
            for key in weighted:
                weighted[key] /= total_weight
        return weighted
