"""Structure placement engine — converts layout into WorldEdit schematics."""

from pathlib import Path
from .layout import FestivalPlan, StageZone, CampingZone, PathSegment


SCHEMATIC_LIBRARY = {
    "main_stage": "main_stage",
    "techno_stage": "techno_stage",
    "dnb_arena": "dnb_arena",
    "acoustic": "acoustic_stage",
    "lighting_rig": "lighting_rig",
    "crowd_barrier": "crowd_barrier",
    "entrance_gate": "entrance_gate",
    "ferris_wheel": "ferris_wheel",
    "camping_tent": "camping_tent",
    "path_block": "path_block",
    "spawn_platform": "spawn_platform",
}


class StructurePlacer:
    def __init__(self, schematic_dir: Path):
        self.schematic_dir = schematic_dir
        self.we_commands: list[str] = []

    def place(self, plan: FestivalPlan) -> list[str]:
        self.we_commands = []
        self._place_spawn(plan.spawn)
        self._place_stage(plan.main_stage)
        for stage in plan.secondary_stages:
            self._place_stage(stage)
        self._place_camping(plan.camping)
        self._place_paths(plan.paths)
        self._place_entrance(plan.entrance)
        self._place_lighting(plan)
        self._place_barriers(plan)
        return self.we_commands

    def _schematic(self, key: str) -> str:
        return SCHEMATIC_LIBRARY.get(key, key)

    def _paste(self, schematic: str, x: int, z: int, y: int = 64) -> str:
        return (
            f"//schematic load {self._schematic(schematic)}\n"
            f"//paste {x} {y} {z}"
        )

    def _place_spawn(self, spawn: tuple[int, int]) -> None:
        self.we_commands.append(self._paste("spawn_platform", spawn[0], spawn[1]))
        self.we_commands.append(f"/spawnpoint @p {spawn[0]} 64 {spawn[1]}")

    def _place_stage(self, stage: StageZone) -> None:
        self.we_commands.append(
            f"# Stage: {stage.name} ({stage.style}) at {stage.x}, {stage.z} radius={stage.radius}"
        )
        self.we_commands.append(self._paste(stage.style, stage.x, stage.z))
        self.we_commands.append(
            f"/fill ~{stage.x - stage.radius} 63 ~{stage.z - stage.radius} "
            f"~{stage.x + stage.radius} 64 ~{stage.z + stage.radius} "
            f"minecraft:polished_andesite replace minecraft:grass_block"
        )

    def _place_camping(self, zones: list[CampingZone]) -> None:
        for i, zone in enumerate(zones):
            self.we_commands.append(f"# Camping zone {i + 1} at {zone.x}, {zone.z}")
            for row in range(0, zone.width, 12):
                for col in range(0, zone.depth, 12):
                    tx = zone.x + row
                    tz = zone.z + col
                    self.we_commands.append(self._paste("camping_tent", tx, tz))

    def _place_paths(self, paths: list[PathSegment]) -> None:
        for p in paths:
            self.we_commands.append(f"# Path: {p.start} -> {p.end}")
            self.we_commands.append(
                f"/fill {p.start[0]} 63 {p.start[1]} {p.end[0]} 63 {p.end[1]} "
                f"minecraft:stone_brick_slab"
            )

    def _place_entrance(self, entrance: tuple[int, int]) -> None:
        self.we_commands.append(self._paste("entrance_gate", entrance[0], entrance[1]))

    def _place_lighting(self, plan: FestivalPlan) -> None:
        r = plan.main_stage.radius
        cx, cz = plan.main_stage.x, plan.main_stage.z
        for angle in range(0, 360, 30):
            import math
            lx = int(cx + r * math.cos(math.radians(angle)))
            lz = int(cz + r * math.sin(math.radians(angle)))
            self.we_commands.append(self._paste("lighting_rig", lx, lz))

    def _place_barriers(self, plan: FestivalPlan) -> None:
        r = plan.main_stage.radius
        cx, cz = plan.main_stage.x, plan.main_stage.z
        for angle in range(0, 360, 15):
            import math
            bx = int(cx + (r + 5) * math.cos(math.radians(angle)))
            bz = int(cz + (r + 5) * math.sin(math.radians(angle)))
            self.we_commands.append(self._paste("crowd_barrier", bx, bz))

    def export_schematic_script(self, path: Path) -> None:
        path.write_text("\n".join(self.we_commands))
