"""Festival layout planner — AI-driven zone placement."""

import math
import random
import json
from dataclasses import dataclass, asdict
from pathlib import Path

import numpy as np


@dataclass
class StageZone:
    name: str
    x: int
    z: int
    radius: int = 60
    style: str = "main"


@dataclass
class CampingZone:
    x: int
    z: int
    width: int
    depth: int


@dataclass
class PathSegment:
    start: tuple[int, int]
    end: tuple[int, int]


@dataclass
class FestivalPlan:
    main_stage: StageZone
    secondary_stages: list[StageZone]
    camping: list[CampingZone]
    paths: list[PathSegment]
    entrance: tuple[int, int]
    spawn: tuple[int, int]

    def to_dict(self) -> dict:
        return {
            "main_stage": asdict(self.main_stage),
            "secondary_stages": [asdict(s) for s in self.secondary_stages],
            "camping": [asdict(c) for c in self.camping],
            "paths": [{"start": list(p.start), "end": list(p.end)} for p in self.paths],
            "entrance": list(self.entrance),
            "spawn": list(self.spawn),
        }

    def to_json(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_dict(), indent=2))

    @classmethod
    def from_json(cls, path: Path) -> "FestivalPlan":
        data = json.loads(path.read_text())
        return cls(
            main_stage=StageZone(**data["main_stage"]),
            secondary_stages=[StageZone(**s) for s in data["secondary_stages"]],
            camping=[CampingZone(**c) for c in data["camping"]],
            paths=[PathSegment(tuple(p["start"]), tuple(p["end"])) for p in data["paths"]],
            entrance=tuple(data["entrance"]),
            spawn=tuple(data["spawn"]),
        )


class LayoutPlanner:
    def __init__(self, rng: random.Random | None = None):
        self.rng = rng or random.Random()

    def plan(
        self,
        flat_zones: list[tuple[int, int, int, int]],
        terrain_type: str,
        map_size: tuple[int, int] = (512, 512),
        style: str = "electronic festival",
    ) -> FestivalPlan:
        mw, mh = map_size
        stages = self._pick_stages(flat_zones, map_size, style)
        main = stages[0] if stages else StageZone("main_stage", mw // 2, mh // 2, 80, self._pick_stage_style("main", style))
        secondary = stages[1:] if len(stages) > 1 else []

        entrance = self._pick_entrance(main, map_size)
        spawn = self._pick_spawn(main, entrance)

        camping = self._place_camping(main, secondary, map_size)
        paths = self._build_paths(main, secondary, entrance, camping)

        return FestivalPlan(
            main_stage=main,
            secondary_stages=secondary,
            camping=camping,
            paths=paths,
            entrance=entrance,
            spawn=spawn,
        )

    def apply_reference_context(
        self,
        plan: FestivalPlan,
        reference: dict[str, str],
        map_size: tuple[int, int],
    ) -> FestivalPlan:
        """Bias the layout using stage reference metadata from public images."""
        if not reference:
            return plan

        mw, mh = map_size
        main = plan.main_stage
        orientation = reference.get("orientation_hint", "")
        scene_hint = reference.get("scene_hint", "")

        if orientation == "crowd-facing" or "crowd" in scene_hint.lower():
            main = StageZone(
                name=main.name,
                x=max(80, min(mw - 80, main.x + 35)),
                z=max(80, min(mh - 80, main.z - 25)),
                radius=main.radius,
                style=main.style,
            )
            entrance = (0, max(40, min(mh - 40, main.z + 55)))
            spawn = (max(30, main.x - 70), max(30, main.z - main.radius - 20))
            return FestivalPlan(
                main_stage=main,
                secondary_stages=plan.secondary_stages,
                camping=plan.camping,
                paths=plan.paths,
                entrance=entrance,
                spawn=spawn,
            )

        return plan

    def _pick_stages(
        self, flat_zones: list[tuple[int, int, int, int]], map_size: tuple[int, int], style: str
    ) -> list[StageZone]:
        mw, mh = map_size
        center_x, center_z = mw // 2, mh // 2
        candidates: list[tuple[float, int, int, int, int, int]] = []

        for x, y, w, h in flat_zones:
            area = w * h
            cx, cz = x + w // 2, y + h // 2
            centrality = math.hypot(cx - center_x, cz - center_z)
            edge_bonus = min(cx, mw - cx, cz, mh - cz)
            score = area - centrality * 0.15 + edge_bonus * 0.4
            candidates.append((score, area, cx, cz, w, h))

        candidates.sort(key=lambda t: (-t[0], -t[1]))
        if not candidates:
            return [
                StageZone("main_stage", mw // 2, mh // 2, 70, self._pick_stage_style("main", style)),
            ]

        stages: list[StageZone] = []
        selected_centers: list[tuple[int, int]] = []
        min_separation = 120

        main_score, _, main_x, main_z, main_w, main_h = candidates[0]
        main_radius = self._radius_for_zone(main_w, main_h, role="main")
        stages.append(StageZone("main_stage", main_x, main_z, main_radius, self._pick_stage_style("main", style)))
        selected_centers.append((main_x, main_z))

        for idx, candidate in enumerate(candidates[1:], start=1):
            _, _, cx, cz, w, h = candidate
            if any(self._distance((cx, cz), center) < max(min_separation, main_radius + 60) for center in selected_centers):
                continue
            radius = self._radius_for_zone(w, h, role="secondary")
            stages.append(StageZone(f"secondary_{idx}", cx, cz, radius, self._pick_stage_style("secondary", style)))
            selected_centers.append((cx, cz))
            if len(stages) >= 4:
                break

        if len(stages) < 4:
            for idx, candidate in enumerate(candidates[1:], start=1):
                _, _, cx, cz, w, h = candidate
                if any(self._distance((cx, cz), center) < 90 for center in selected_centers):
                    continue
                radius = self._radius_for_zone(w, h, role="secondary")
                stages.append(StageZone(f"secondary_{len(stages)}", cx, cz, radius, self._pick_stage_style("secondary", style)))
                selected_centers.append((cx, cz))
                if len(stages) >= 4:
                    break

        return stages

    def _place_camping(
        self, main: StageZone, secondary: list[StageZone], map_size: tuple[int, int]
    ) -> list[CampingZone]:
        mw, mh = map_size
        zones: list[CampingZone] = []
        min_distance = main.radius + 120
        width = min(120, max(70, mw // 18))
        depth = min(120, max(70, mh // 18))

        offsets = [
            (-min(mw, mh) // 5, min(mw, mh) // 8),
            (min(mw, mh) // 6, -min(mw, mh) // 5),
            (-min(mw, mh) // 7, -min(mw, mh) // 4),
        ]

        for ox, oz in offsets:
            cx = max(20, min(mw - width - 20, main.x + ox))
            cz = max(20, min(mh - depth - 20, main.z + oz))
            if self._distance((cx, cz), (main.x, main.z)) < min_distance:
                cx = max(20, min(mw - width - 20, main.x + ox * 2))
                cz = max(20, min(mh - depth - 20, main.z + oz * 2))
            if any(self._distance((cx, cz), (z.x, z.z)) < 100 for z in zones):
                continue
            zones.append(CampingZone(x=cx, z=cz, width=width, depth=depth))
            if len(zones) >= 3:
                break

        if not zones:
            zones.append(CampingZone(max(20, main.x + 140), max(20, main.z + 140), width, depth))
        return zones

    def _build_paths(
        self,
        main: StageZone,
        secondary: list[StageZone],
        entrance: tuple[int, int],
        camping: list[CampingZone],
    ) -> list[PathSegment]:
        paths: list[PathSegment] = []
        for start, end in self._route_points(entrance, (main.x, main.z), offset=40):
            paths.append(PathSegment(start=start, end=end))

        for s in secondary:
            for start, end in self._route_points((main.x, main.z), (s.x, s.z), offset=25):
                paths.append(PathSegment(start=start, end=end))

        for c in camping:
            for start, end in self._route_points((main.x, main.z), (c.x, c.z), offset=20):
                paths.append(PathSegment(start=start, end=end))

        return paths

    def _pick_entrance(self, main: StageZone, map_size: tuple[int, int]) -> tuple[int, int]:
        mw, mh = map_size
        if main.x < mw // 2:
            return (0, max(20, min(mh - 20, main.z + self.rng.randint(-40, 40))))
        return (mw, max(20, min(mh - 20, main.z + self.rng.randint(-40, 40))))

    def _pick_spawn(self, main: StageZone, entrance: tuple[int, int]) -> tuple[int, int]:
        offset_x = 30 if entrance[0] == 0 else -30
        return (max(10, min(main.x + offset_x, 500)), max(20, main.z - main.radius - 30))

    def _pick_stage_style(self, role: str, style: str) -> str:
        text = style.lower()
        if role == "main":
            if "techno" in text or "electronic" in text:
                return "mixed"
            if "dnb" in text:
                return "main_stage"
            return "main_stage"
        if "techno" in text or "electronic" in text:
            return "techno_stage"
        if "dnb" in text:
            return "dnb_arena"
        if "acoustic" in text or "folk" in text or "chill" in text:
            return "acoustic"
        return "acoustic"

    def _radius_for_zone(self, width: int, height: int, role: str) -> int:
        base = min(min(width, height) // 2, 120)
        if role == "main":
            return max(60, min(95, base + 15))
        return max(30, min(70, base + 5))

    def _distance(self, a: tuple[int, int], b: tuple[int, int]) -> float:
        return math.hypot(a[0] - b[0], a[1] - b[1])

    def _route_points(self, start: tuple[int, int], end: tuple[int, int], offset: int) -> list[tuple[tuple[int, int], tuple[int, int]]]:
        mid_x = (start[0] + end[0]) // 2
        mid_z = (start[1] + end[1]) // 2
        bend_x = mid_x + (offset if end[0] >= start[0] else -offset)
        bend_z = mid_z + (offset if end[1] >= start[1] else -offset)
        return [
            (start, (bend_x, bend_z)),
            ((bend_x, bend_z), end),
        ]
