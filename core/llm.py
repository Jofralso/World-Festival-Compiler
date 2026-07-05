"""Local LLM integration via Ollama — AI-assisted festival layout planning."""

import json
import urllib.request
import urllib.error
from dataclasses import dataclass
from typing import Any

from .layout import FestivalPlan, StageZone, CampingZone, PathSegment


@dataclass
class LLMConfig:
    base_url: str = "http://localhost:11434"
    model: str = "llama3.1"
    timeout: int = 120


def check_ollama(url: str) -> bool:
    """Check if Ollama server is reachable."""
    try:
        req = urllib.request.Request(f"{url}/api/tags")
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status == 200
    except Exception:
        return False


def list_models(url: str) -> list[str]:
    """List available models from Ollama."""
    try:
        req = urllib.request.Request(f"{url}/api/tags")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            return [m["name"] for m in data.get("models", [])]
    except Exception:
        return []


def generate(prompt: str, config: LLMConfig) -> str:
    """Send a prompt to Ollama and return the response text."""
    payload = json.dumps({
        "model": config.model,
        "prompt": prompt,
        "stream": False,
        "temperature": 0.7,
        "num_predict": 4096,
        "format": "json",
    }).encode()

    req = urllib.request.Request(
        f"{config.base_url}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=config.timeout) as resp:
        result = json.loads(resp.read())
    return result.get("response", "")


BUILD_PROMPT = """You are a festival layout designer for a Minecraft world generator.
Given terrain analysis and a festival style, output a JSON festival layout plan.

TERRAIN TYPE: {terrain_type}
MAP SIZE: {width} x {height} blocks (x, z coordinates)
FLAT ZONES (buildable areas with x, z, w, h):
{flat_zones}
FESTIVAL STYLE: {style}

RULES:
- Main stage goes on the largest flat zone.
- Secondary stages on smaller flat zones.
- Camping zones on remaining flat areas or near edges.
- Entrance on map edge (x=0, z near center).
- Spawn near main stage entrance.
- All coordinates must be within map bounds (0-{width} for x, 0-{height} for z).
- Choose creative stage styles matching the festival (e.g., "techno", "dnb", "acoustic", "main").

Output ONLY valid JSON with this exact structure (no markdown, no extra text):
{{
  "main_stage": {{"x": <int>, "z": <int>, "radius": <int 40-100>, "style": "<string>"}},
  "secondary_stages": [
    {{"x": <int>, "z": <int>, "radius": <int 30-70>, "style": "<string>"}}
  ],
  "camping": [
    {{"x": <int>, "z": <int>, "width": <int 50-100>, "depth": <int 50-100>}}
  ],
  "entrance": [<int>, <int>],
  "spawn": [<int>, <int>],
  "description": "<brief explanation of layout choices>"
}}"""


class LLMPlanner:
    """Festival layout planner powered by a local LLM via Ollama."""

    def __init__(self, config: LLMConfig | None = None):
        self.config = config or LLMConfig()
        self._available: bool | None = None

    @property
    def available(self) -> bool:
        if self._available is None:
            self._available = check_ollama(self.config.base_url)
        return self._available

    def plan(
        self,
        flat_zones: list[tuple[int, int, int, int]],
        terrain_type: str,
        map_size: tuple[int, int] = (512, 512),
        style: str = "electronic festival",
    ) -> FestivalPlan | None:
        """Generate a festival plan using the local LLM.
        Returns None if the LLM is unavailable or output is invalid."""
        if not self.available:
            return None

        mw, mh = map_size
        zones_str = "\n".join(
            f"  - Zone at ({x}, {z}): {w}x{h} blocks (area {w*h})"
            for x, z, w, h in sorted(flat_zones, key=lambda t: -t[2] * t[3])
        ) if flat_zones else "  - No flat zones detected (use map center)"

        prompt = BUILD_PROMPT.format(
            terrain_type=terrain_type,
            width=mw,
            height=mh,
            flat_zones=zones_str or "None",
            style=style,
        )

        try:
            raw = generate(prompt, self.config)
            return self._parse(raw, mw, mh, style)
        except Exception as e:
            import warnings
            warnings.warn(f"LLM planning failed: {e}")
            return None

    def _parse(self, raw: str, mw: int, mh: int, style: str) -> FestivalPlan | None:
        """Parse LLM JSON output into a FestivalPlan with bounds clamping."""
        import re

        # Try to extract JSON from the response (handle markdown fences)
        json_match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not json_match:
            return None

        try:
            data = json.loads(json_match.group(0))
        except json.JSONDecodeError:
            return None

        # Clamp coordinates to map bounds
        def clamp(val: int, lo: int, hi: int) -> int:
            return max(lo, min(hi, val))

        ms = data.get("main_stage", {})
        main = StageZone(
            name="main_stage",
            x=clamp(int(ms.get("x", mw // 2)), 10, mw - 10),
            z=clamp(int(ms.get("z", mh // 2)), 10, mh - 10),
            radius=clamp(int(ms.get("radius", 60)), 30, 120),
            style=ms.get("style", style),
        )

        secondary = []
        for i, s in enumerate(data.get("secondary_stages", [])):
            secondary.append(StageZone(
                name=f"secondary_{i + 1}",
                x=clamp(int(s.get("x", 0)), 10, mw - 10),
                z=clamp(int(s.get("z", 0)), 10, mh - 10),
                radius=clamp(int(s.get("radius", 40)), 20, 80),
                style=s.get("style", "acoustic"),
            ))

        camping = []
        for c in data.get("camping", []):
            camping.append(CampingZone(
                x=clamp(int(c.get("x", 0)), 5, mw - 60),
                z=clamp(int(c.get("z", 0)), 5, mh - 60),
                width=clamp(int(c.get("width", 70)), 30, 120),
                depth=clamp(int(c.get("depth", 70)), 30, 120),
            ))

        entrance = (
            clamp(int(data.get("entrance", [0, mh // 2])[0]), 0, mw),
            clamp(int(data.get("entrance", [0, mh // 2])[1]), 0, mh),
        )
        spawn = (
            clamp(int(data.get("spawn", [main.x, main.z - main.radius - 20])[0]), 0, mw),
            clamp(int(data.get("spawn", [main.x, main.z - main.radius - 20])[1]), 0, mh),
        )

        # Build paths connecting key points
        paths = [
            PathSegment(start=entrance, end=(main.x, main.z)),
        ]
        for s in secondary:
            paths.append(PathSegment(start=(main.x, main.z), end=(s.x, s.z)))
        for c in camping:
            cx = c.x + c.width // 2
            cz = c.z + c.depth // 2
            paths.append(PathSegment(start=(main.x, main.z), end=(cx, cz)))

        return FestivalPlan(
            main_stage=main,
            secondary_stages=secondary,
            camping=camping,
            paths=paths,
            entrance=entrance,
            spawn=spawn,
        )
