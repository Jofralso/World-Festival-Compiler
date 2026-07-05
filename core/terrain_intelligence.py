"""Multi-source terrain intelligence engine.

This module combines local map/terrain files, remote map resources, and online search results
into a structured understanding of a location before building a world.
"""

import base64
import io
import json
import math
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image


class TerrainIntelligence:
    """Analyse terrain inputs and gather supporting reference data."""

    def __init__(self, cache_dir: Path | None = None):
        self.cache_dir = cache_dir or Path.home() / ".cache" / "festivalworld" / "terrain_intel"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def ingest_local_file(self, path: str | Path) -> dict[str, Any]:
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(path)

        suffix = path.suffix.lower()
        if suffix in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}:
            return self._analyze_image(path)
        if suffix == ".json":
            return {"type": "json", "content": json.loads(path.read_text())}
        return {"type": "unknown", "path": str(path)}

    def _analyze_image(self, path: Path) -> dict[str, Any]:
        img = Image.open(path).convert("L")
        arr = np.array(img, dtype=np.float32)
        arr = cv2.resize(arr, (256, 256), interpolation=cv2.INTER_AREA)
        hist = np.histogram(arr, bins=16)[0]
        mean = float(arr.mean())
        std = float(arr.std())
        return {
            "type": "image",
            "size": [arr.shape[1], arr.shape[0]],
            "mean_brightness": mean,
            "brightness_std": std,
            "histogram": hist.tolist(),
            "terrain_hint": self._classify_image(arr),
        }

    def _classify_image(self, arr: np.ndarray) -> str:
        mean = float(arr.mean())
        std = float(arr.std())
        if std < 10:
            return "flat"
        if mean > 180:
            return "bright_highland"
        if mean < 80:
            return "dark_lowland"
        return "mixed"

    def search_online_resources(self, query: str, limit: int = 6) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        seen: set[str] = set()
        for term in self._build_search_terms(query):
            try:
                url = "https://duckduckgo.com/html/?q=" + urllib.parse.quote(term)
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=8) as resp:
                    html = resp.read().decode("utf-8", errors="ignore")
                for match in re.findall(r'https?://[^"\s<>]+', html):
                    cleaned = match.rstrip('.,;)')
                    if cleaned.endswith((".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff")):
                        if cleaned not in seen:
                            seen.add(cleaned)
                            results.append({"type": "image", "url": cleaned, "source": term})
                            if len(results) >= limit:
                                return results
                    elif cleaned.startswith("https://") and any(token in cleaned.lower() for token in ["wiki", "openstreetmap", "topo", "geology", "terrain"]):
                        if cleaned not in seen:
                            seen.add(cleaned)
                            results.append({"type": "resource", "url": cleaned, "source": term})
                            if len(results) >= limit:
                                return results
            except Exception:
                continue
        return results[:limit]

    def _build_search_terms(self, query: str) -> list[str]:
        cleaned = re.sub(r"[^a-zA-Z0-9]+", " ", query).strip()
        if not cleaned:
            return ["topographic map"]
        parts = [p for p in cleaned.split() if len(p) > 2]
        base = " ".join(parts)
        return [
            f"{base} topographic map",
            f"{base} terrain map",
            f"{base} festival map",
            f"{base} satellite image",
            f"{base} elevation data",
        ]

    def build_context_profile(self, query: str, local_inputs: list[str | Path] | None = None) -> dict[str, Any]:
        local_contexts = []
        if local_inputs:
            for item in local_inputs:
                try:
                    local_contexts.append(self.ingest_local_file(item))
                except Exception:
                    continue

        online_resources = self.search_online_resources(query)
        profile = {
            "query": query,
            "local_inputs": local_contexts,
            "online_resources": online_resources,
            "terrain_summary": self._summarize_context(local_contexts),
        }
        return profile

    def _summarize_context(self, local_contexts: list[dict[str, Any]]) -> dict[str, Any]:
        if not local_contexts:
            return {"signal": "no_local_inputs"}

        image_inputs = [c for c in local_contexts if c.get("type") == "image"]
        if not image_inputs:
            return {"signal": "non_image_inputs"}

        mean_brightness = sum(c.get("mean_brightness", 0.0) for c in image_inputs) / max(1, len(image_inputs))
        stds = sum(c.get("brightness_std", 0.0) for c in image_inputs) / max(1, len(image_inputs))
        hints = [c.get("terrain_hint", "mixed") for c in image_inputs]
        return {
            "signal": "image_inputs",
            "mean_brightness": round(mean_brightness, 2),
            "brightness_std": round(stds, 2),
            "terrain_hints": hints,
        }
