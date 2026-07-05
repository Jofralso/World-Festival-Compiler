"""AI-powered stage generation — uses Ollama vision model to create Minecraft structures from festival images."""

import json
import urllib.request
import urllib.parse
import base64
import re
import numpy as np
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


@dataclass
class AIStage:
    name: str
    style: str
    width: int
    depth: int
    height: int
    blocks: list  # list of (x, y, z, block_id) relative to origin
    color_scheme: list[str]
    description: str


@dataclass
class AIStructure:
    stage: AIStage
    entrance: AIStage | None = None
    lighting: list[AIStage] = None

    def to_dict(self) -> dict:
        return {
            "stage": asdict(self.stage),
            "entrance": asdict(self.entrance) if self.entrance else None,
            "lighting": [asdict(l) for l in (self.lighting or [])],
        }


STAGE_TEMPLATES = {
    "main": {
        "width": 40, "depth": 30, "height": 15,
        "colors": ["#ff4444", "#ffffff", "#ff8800"],
        "pattern": "grand",
    },
    "electronic": {
        "width": 35, "depth": 25, "height": 12,
        "colors": ["#00ff88", "#ff00ff", "#0088ff"],
        "pattern": "modern",
    },
    "techno": {
        "width": 30, "depth": 20, "height": 10,
        "colors": ["#222222", "#ff0000", "#888888"],
        "pattern": "industrial",
    },
    "acoustic": {
        "width": 25, "depth": 20, "height": 8,
        "colors": ["#8B4513", "#deb887", "#228B22"],
        "pattern": "rustic",
    },
    "dnb": {
        "width": 35, "depth": 25, "height": 14,
        "colors": ["#ff6600", "#00ccff", "#330066"],
        "pattern": "neon",
    },
}

BLOCK_IDS = {
    "air": 0,
    "stone": 1,
    "grass": 2,
    "dirt": 3,
    "cobblestone": 4,
    "planks": 5,
    "oak_planks": 5,
    "spruce_planks": 5,
    "birch_planks": 5,
    "stone_bricks": 98,
    "bricks": 45,
    "wool": 35,
    "white_wool": 35,
    "orange_wool": 35,
    "magenta_wool": 35,
    "light_blue_wool": 35,
    "yellow_wool": 35,
    "lime_wool": 35,
    "pink_wool": 35,
    "gray_wool": 35,
    "cyan_wool": 35,
    "purple_wool": 35,
    "blue_wool": 35,
    "brown_wool": 35,
    "green_wool": 35,
    "red_wool": 35,
    "black_wool": 35,
    "glass": 20,
    "glowstone": 89,
    "sea_lantern": 169,
    "redstone_lamp": 123,
    "iron_block": 42,
    "gold_block": 41,
    "diamond_block": 57,
    "netherite_block": 16,
    "polished_andesite": 98,
    "polished_diorite": 98,
    "polished_granite": 98,
    "sandstone": 24,
    "red_sandstone": 179,
    "terracotta": 172,
    "white_terracotta": 172,
    "concrete": 251,
    "white_concrete": 251,
    "black_concrete": 251,
    "red_concrete": 251,
    "blue_concrete": 251,
    "green_concrete": 251,
    "yellow_concrete": 251,
    "fence": 85,
    "oak_fence": 85,
    "torch": 50,
    "redstone_torch": 76,
    "oak_stairs": 53,
    "spruce_stairs": 134,
    "slab": 44,
    "stone_slab": 44,
}

COLOR_TO_BLOCK = {
    "#ff0000": "red_concrete", "#00ff00": "lime_concrete",
    "#0000ff": "blue_concrete", "#ffffff": "white_concrete",
    "#000000": "black_concrete", "#ffff00": "yellow_concrete",
    "#ff00ff": "magenta_concrete", "#00ffff": "cyan_concrete",
    "#ff8800": "orange_concrete", "#8800ff": "purple_concrete",
    "#0088ff": "light_blue_concrete", "#00ff88": "lime_concrete",
    "#ff4444": "red_concrete", "#ff6600": "orange_concrete",
    "#00ccff": "light_blue_concrete", "#330066": "purple_concrete",
    "#222222": "black_concrete", "#888888": "gray_wool",
    "#8B4513": "brown_wool", "#deb887": "sandstone",
    "#228B22": "green_concrete", "#ff8800": "orange_concrete",
}


def build_image_search_queries(festival_name: str) -> list[str]:
    """Create several likely image-search phrases from a festival name."""
    name = re.sub(r"[^a-zA-Z0-9]+", " ", festival_name).strip()
    if not name:
        return ["music festival stage"]

    tokens = [t for t in name.split() if len(t) > 2]
    base = " ".join(tokens)
    queries = [
        f"{base} festival stage",
        f"{base} festival crowd",
        f"{base} festival lighting",
        f"{base} stage design",
        f"{base} music festival",
    ]
    if len(tokens) > 1:
        queries.append(f"{tokens[0]} {tokens[-1]} festival")
    return list(dict.fromkeys(queries))


def search_image_urls(festival_name: str, limit: int = 6) -> list[str]:
    """Find image URLs online from a festival name using public search endpoints."""
    refs = search_image_references(festival_name, limit=limit)
    return [ref["image_url"] for ref in refs]


def search_image_references(festival_name: str, limit: int = 6, html: str | None = None) -> list[dict[str, Any]]:
    """Find public image references and extract lightweight metadata for stage orientation hints."""
    if not festival_name:
        return []

    references: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    queries = build_image_search_queries(festival_name)[:4]

    for query in queries:
        try:
            encoded = urllib.parse.quote(query)
            if html is None:
                req = urllib.request.Request(
                    f"https://duckduckgo.com/html/?q={encoded}",
                    headers={"User-Agent": "Mozilla/5.0"},
                )
                with urllib.request.urlopen(req, timeout=8) as resp:
                    html = resp.read().decode("utf-8", errors="ignore")

            title_matches = re.findall(r'<a[^>]+class=["\'][^"\']*result__a[^"\']*["\'][^>]*>(.*?)</a>', html, re.I | re.S)
            snippet_matches = re.findall(r'<a[^>]+class=["\'][^"\']*result__snippet[^"\']*["\'][^>]*>(.*?)</a>', html, re.I | re.S)
            image_matches = re.findall(r'<img[^>]+src=["\'](https?://[^"\']+)["\']', html, re.I)

            title = re.sub(r'<.*?>', ' ', title_matches[0] if title_matches else '')
            title = re.sub(r'\s+', ' ', title).strip() if title else ""
            snippet = re.sub(r'<.*?>', ' ', snippet_matches[0] if snippet_matches else '')
            snippet = re.sub(r'\s+', ' ', snippet).strip() if snippet else ""
            image_url = image_matches[0] if image_matches else None

            if image_url and image_url not in seen_urls:
                orientation_hint = "front-facing"
                scene_hint = "stage"
                text_blob = f"{title} {snippet}".lower()
                if any(word in text_blob for word in ["crowd", "audience", "spectator", "festival crowd"]):
                    orientation_hint = "crowd-facing"
                if any(word in text_blob for word in ["lighting", "night", "sunset", "pyro", "drone"]):
                    scene_hint = "stage lighting"
                elif any(word in text_blob for word in ["crowd", "audience", "people"]):
                    scene_hint = "crowd scene"

                references.append({
                    "title": title or query,
                    "image_url": image_url,
                    "snippet": snippet,
                    "orientation_hint": orientation_hint,
                    "scene_hint": scene_hint,
                })
                seen_urls.add(image_url)

                if len(references) >= limit:
                    return references
        except Exception:
            continue

    return references[:limit]


def _block_id(name: str) -> int:
    return BLOCK_IDS.get(name, 1)


def _color_to_block_id(hex_color: str) -> int:
    block_name = COLOR_TO_BLOCK.get(hex_color.lower(), "white_concrete")
    return _block_id(block_name)


class AIStageGenerator:
    def __init__(self, ollama_url: str = "http://localhost:11434", model: str = "llava:7b"):
        self.ollama_url = ollama_url
        self.model = model

    def analyze_images(self, image_urls: list[str], festival_name: str) -> dict[str, Any]:
        """Analyze festival images using public references and optional vision analysis."""
        references = []
        if image_urls:
            references = [{"image_url": url, "title": "", "snippet": "", "orientation_hint": "front-facing", "scene_hint": "stage"} for url in image_urls]
        else:
            references = search_image_references(festival_name)

        if not references:
            return self._default_design(festival_name)

        base_design = self._default_design(festival_name)
        for ref in references[:2]:
            image_url = ref.get("image_url")
            title = ref.get("title", "")
            snippet = ref.get("snippet", "")
            orientation_hint = ref.get("orientation_hint", "front-facing")
            scene_hint = ref.get("scene_hint", "stage")

            try:
                design = self._query_vision(image_url, festival_name)
            except Exception:
                continue

            if title:
                design.setdefault("reference_title", title)
            if snippet:
                design.setdefault("reference_snippet", snippet)
            design["orientation_hint"] = orientation_hint
            design["scene_hint"] = scene_hint
            design.setdefault("location_bias", "central")
            if orientation_hint == "crowd-facing":
                design["location_bias"] = "crowd_front"
            elif scene_hint == "stage lighting":
                design["location_bias"] = "lighting_focus"
            return design

        return base_design

    def _query_vision(self, image_url: str, festival_name: str) -> dict:
        """Send an image to the vision model and parse the response."""
        prompt = (
            f"Look at this image of '{festival_name}' festival. "
            "Describe the main stage design in detail: shape, size, colors, materials, "
            "lighting, and architectural style. Then output ONLY valid JSON with these fields:\n"
            '{"stage_style": "modern/rustic/futuristic/grand/etc", '
            '"width_blocks": <int 15-50>, "depth_blocks": <int 10-35>, '
            '"height_blocks": <int 5-20>, '
            '"colors": ["#hex1", "#hex2", "#hex3"], '
            '"description": "<2 sentence description>"}\n'
            "No markdown, no extra text, only JSON."
        )

        payload = json.dumps({
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "temperature": 0.3,
            "num_predict": 512,
            "images": [image_url],
        }).encode()

        req = urllib.request.Request(
            f"{self.ollama_url}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read())

        response_text = result.get("response", "")
        import re
        json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass
        return self._default_design(festival_name)

    def _default_design(self, festival_name: str) -> dict:
        return {
            "stage_style": "modern",
            "width_blocks": 35,
            "depth_blocks": 25,
            "height_blocks": 12,
            "colors": ["#00ff88", "#ff00ff", "#0088ff"],
            "description": f"A modern {festival_name} festival stage with vibrant lighting and multiple levels.",
        }

    def generate_stage(self, design: dict, x: int, z: int, ground_y: int = 63) -> AIStage:
        """Convert AI design into Minecraft block structure."""
        w = max(design.get("width_blocks", 35) // 2 * 2, 10)
        d = max(design.get("depth_blocks", 25) // 2 * 2, 10)
        h = max(min(design.get("height_blocks", 12), 20), 4)

        colors = design.get("colors", ["#ffffff", "#888888", "#444444"])
        description = design.get("description", "Festival stage")
        style = design.get("stage_style", "modern")

        blocks = []
        hw, hd = w // 2, d // 2

        color_block_ids = [_color_to_block_id(c) for c in colors[:3]]
        while len(color_block_ids) < 3:
            color_block_ids.append(_block_id("white_concrete"))

        floor_block = _block_id("polished_andesite")
        accent = color_block_ids[0]
        primary = color_block_ids[1]
        trim = color_block_ids[2]

        # Floor platform
        for bx in range(-hw, hw + 1):
            for bz in range(-hd, hd + 1):
                blocks.append((bx, 0, bz, floor_block))

        # Stage back wall
        for by in range(1, h):
            for bx in range(-hw + 2, hw - 1):
                block_id = accent if by == h - 1 else (primary if by % 3 == 0 else floor_block)
                blocks.append((bx, by, -hd + 1, block_id))

        # Stage pillars at corners
        for bx in [-hw + 2, hw - 2]:
            for by in range(1, h):
                blocks.append((bx, by, -hd + 1, trim))
            for by in range(1, min(h, 5)):
                blocks.append((bx, by, -hd + 2, trim))

        # Roof/canopy
        if h >= 4:
            for bx in range(-hw, hw + 1):
                for bz in range(-hd, hd + 1):
                    if abs(bx) <= 2 or abs(bz) <= 2:
                        continue
                    blocks.append((bx, h - 1, bz, accent))

        # Glowstone lighting on ceiling
        for bx in range(-hw + 4, hw - 2, 6):
            for bz in range(-hd + 3, 0, 5):
                blocks.append((bx, h - 1, bz, _block_id("glowstone")))

        # Front decorations
        for bx in range(-hw + 3, hw - 2, 4):
            blocks.append((bx, 1, 0, _block_id("fence")))
            blocks.append((bx, 2, 0, _block_id("torch")))

        # Side walls (partial)
        for by in range(1, h - 1):
            for bz in range(-hd + 2, 1):
                blocks.append((-hw + 2, by, bz, floor_block))
                blocks.append((hw - 2, by, bz, floor_block))

        return AIStage(
            name=f"ai_{style}_stage",
            style=style,
            width=w,
            depth=d,
            height=h,
            blocks=blocks,
            color_scheme=colors,
            description=description,
        )

    def place_in_world(
        self,
        heightmap: np.ndarray,
        stage: AIStage,
        center_x: int,
        center_z: int,
    ) -> np.ndarray:
        """Place AI-generated stage blocks into the world heightmap.
        Returns modified heightmap (elevation raised for the stage platform).
        """
        hm = heightmap.copy()
        y_base = int(np.median(hm[max(0, center_z - 5):min(hm.shape[0], center_z + 5),
                                   max(0, center_x - 5):min(hm.shape[1], center_x + 5)]))
        y_base = max(y_base, 63)

        for bx, by, bz, bid in stage.blocks:
            wx = center_x + bx
            wz = center_z + bz
            wy = y_base + by

            if 0 <= wx < hm.shape[1] and 0 <= wz < hm.shape[0]:
                if wy > hm[wz, wx]:
                    hm[wz, wx] = float(wy)

        platform_hw = stage.width // 2
        platform_hd = stage.depth // 2
        for wz in range(center_z - platform_hd, center_z + platform_hd + 1):
            for wx in range(center_x - platform_hw, center_x + platform_hw + 1):
                if 0 <= wx < hm.shape[1] and 0 <= wz < hm.shape[0]:
                    hm[wz, wx] = max(hm[wz, wx], float(y_base))

        return hm

    def export_structure(self, stage: AIStage, center_x: int, center_z: int, ground_y: int = 63) -> list[dict]:
        """Export block structure for the 3D viewer overlay."""
        exported = []
        y_base = ground_y
        for bx, by, bz, bid in stage.blocks:
            exported.append({
                "x": center_x + bx,
                "y": y_base + by,
                "z": center_z + bz,
                "block_id": bid,
            })
        return exported
