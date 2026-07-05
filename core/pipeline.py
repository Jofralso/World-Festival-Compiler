"""Main pipeline — orchestrates the full festival world build."""

from pathlib import Path
import shutil
import subprocess
import json

import numpy as np

from .geo import download_srtm, download_osm_features, expand_bounds_to_diameter
from .config import Settings
from .preprocessor import (
    load_heightmap,
    find_flat_zones,
    classify_terrain,
    normalize_heightmap,
    contours_from_map,
)
from .layout import LayoutPlanner
from .llm import LLMPlanner, LLMConfig
from .structures import StructurePlacer
from .worldgen import WorldBuilder
from .ai_stages import AIStageGenerator, AIStage
from .terrain_intelligence import TerrainIntelligence


class BuildResult:
    """Result of a festival world build."""

    def __init__(self, success: bool, message: str, output_path: Path | None = None):
        self.success = success
        self.message = message
        self.output_path = output_path

    def __repr__(self):
        status = "✓" if self.success else "✗"
        return f"[{status}] {self.message}"


class FestivalWorldPipeline:
    """End-to-end pipeline: map → festival layout → Minecraft world."""

    def __init__(self, settings: Settings | None = None, use_llm: bool = False, llm_config: LLMConfig | None = None):
        self.settings = settings or Settings()
        self.layout_planner = LayoutPlanner()
        self.llm_planner = LLMPlanner(llm_config or LLMConfig())
        self.use_llm = use_llm
        self.terrain_type: str = "flat"
        self.heightmap: np.ndarray | None = None
        self.flat_zones: list[tuple[int, int, int, int]] = []
        self.plan = None
        self.we_commands: list[str] = []
        self.terrain_intelligence = TerrainIntelligence()
        self._progress_messages: list[str] = []

    def preprocess_map(self, map_path: Path) -> None:
        """Load and analyse the topographic input."""
        self.heightmap = load_heightmap(map_path)
        self.terrain_type = classify_terrain(self.heightmap)
        self.flat_zones = find_flat_zones(self.heightmap)
        self.terrain_context = self.terrain_intelligence.build_context_profile(
            query=self.settings.minecraft_world_name,
            local_inputs=[map_path],
        )

    def generate_heightmap(self, size: tuple[int, int] = (512, 512)) -> None:
        """Generate a heightmap from scratch if no map is provided."""
        rng = np.random.default_rng(42)
        base = rng.uniform(0, 0.3, size)

        cx, cy = size[0] // 2, size[1] // 2
        X, Y = np.ogrid[:size[0], :size[1]]
        dist = np.sqrt((X - cx) ** 2 + (Y - cy) ** 2)
        mound = np.exp(-dist ** 2 / (2 * (size[0] // 6) ** 2)) * 0.7

        noise = rng.normal(0, 0.05, size)
        noise = np.clip(noise, -0.1, 0.1)

        self.heightmap = normalize_heightmap((base + mound + noise) * 255)
        self.terrain_type = classify_terrain(self.heightmap)
        self.flat_zones = find_flat_zones(self.heightmap)

    def build_layout(self) -> None:
        """Create the festival layout plan from the analysed terrain."""
        mh, mw = self.heightmap.shape if self.heightmap is not None else (512, 512)

        if self.use_llm and self.llm_planner.available:
            llm_plan = self.llm_planner.plan(
                flat_zones=self.flat_zones,
                terrain_type=self.terrain_type,
                map_size=(mw, mh),
                style=self.settings.style,
            )
            if llm_plan is not None:
                self.plan = llm_plan
                return

        self.plan = self.layout_planner.plan(
            flat_zones=self.flat_zones,
            terrain_type=self.terrain_type,
            map_size=(mw, mh),
            style=self.settings.style,
        )

    def export_worldpainter_project(self, output_path: Path) -> None:
        """Export heightmap in a format WorldPainter can import."""
        if self.heightmap is None:
            raise RuntimeError("No heightmap to export")

        output_path.mkdir(parents=True, exist_ok=True)
        hmap_path = output_path / "heightmap.png"

        cv2_available = False
        try:
            import cv2
            cv2.imwrite(str(hmap_path), self.heightmap.astype(np.uint8))
            cv2_available = True
        except ImportError:
            pass

        if not cv2_available:
            try:
                from PIL import Image
                img = Image.fromarray(self.heightmap.astype(np.uint8))
                img.save(hmap_path)
            except ImportError:
                np.savetxt(output_path / "heightmap.csv", self.heightmap, delimiter=",")

        if self.plan:
            self.plan.to_json(output_path / "festival_plan.json")

        if self.we_commands:
            script_path = output_path / "place_structures.we"
            script_path.write_text("\n".join(self.we_commands))

    def export_minecraft_world(self, output_path: Path) -> None:
        """Write out everything needed for the Minecraft world."""
        output_path.mkdir(parents=True, exist_ok=True)
        self.export_worldpainter_project(output_path)
        info = {
            "world_name": self.settings.minecraft_world_name,
            "terrain_type": self.terrain_type,
            "style": self.settings.style,
            "scale": self.settings.scale,
            "stages": len(self.plan.secondary_stages) + 1 if self.plan else 0,
            "camping_zones": len(self.plan.camping) if self.plan else 0,
        }
        (output_path / "world_manifest.json").write_text(json.dumps(info, indent=2))

    def place_structures(self) -> None:
        """Run structure placement engine."""
        if self.plan is None:
            raise RuntimeError("No festival plan to place structures from")
        placer = StructurePlacer(self.settings.schematic_dir)
        self.we_commands = placer.place(self.plan)

    def build(self, map_path: Path | None = None) -> BuildResult:
        """Run the full pipeline."""
        try:
            if map_path and map_path.exists():
                self.preprocess_map(map_path)
            else:
                self.generate_heightmap()

            self.build_layout()

            if self.plan:
                self.place_structures()

            out = self.settings.output_dir / self.settings.minecraft_world_name
            self.export_minecraft_world(out)

            return BuildResult(
                success=True,
                message=f"Festival world built at {out} "
                f"(terrain: {self.terrain_type}, "
                f"{len(self.plan.secondary_stages) + 1} stages, "
                f"{len(self.plan.camping)} camping zones)",
                output_path=out,
            )
        except Exception as e:
            return BuildResult(success=False, message=str(e))

    def build_from_geo(
        self,
        center_lat: float,
        center_lng: float,
        diameter_km: float = 10.0,
        srtm_resolution: str = "SRTMGL3",
        festival_name: str = "",
        festival_images: list[str] = None,
    ) -> BuildResult:
        """Build a festival world from real-world geo data.

        Downloads SRTM elevation data and OSM features for the area,
        generates a 10k×10k block world, places the festival layout,
        and exports everything. If festival_name + images provided,
        AI vision model generates custom stage designs.
        """
        import time
        start = time.time()

        try:
            self._progress_messages = []
            self._log_progress("Expanding bounds to {:.1f} km diameter...".format(diameter_km))
            bounds = expand_bounds_to_diameter((center_lat, center_lng), diameter_km)

            self._log_progress("Downloading SRTM elevation data...")
            srtm = download_srtm(bounds, resolution=srtm_resolution)

            self._log_progress("Downloading OSM features (roads, buildings, water)...")
            osm = download_osm_features(bounds)

            self._log_progress("Analyzing terrain context from local and online resources...")
            self.terrain_context = self.terrain_intelligence.build_context_profile(
                query=festival_name or f"{center_lat},{center_lng}",
                local_inputs=[str(Path(f"/tmp/{festival_name or 'terrain'}.png"))] if False else [],
            )
            if self.terrain_context.get("online_resources"):
                self._log_progress("Found {} online terrain reference resources".format(len(self.terrain_context["online_resources"])))

            self._log_progress("Building world terrain ({}x{} blocks)...".format(
                int(diameter_km * 1000), int(diameter_km * 1000)))

            wb = WorldBuilder(diameter_blocks=int(diameter_km * 1000))
            wb.from_srtm(srtm, bounds, osm)

            self.heightmap = wb.heightmap
            self.flat_zones = wb.flat_zones
            self.terrain_type = classify_terrain(wb._to_8bit(wb.heightmap))
            self.biome_map = wb.biome_map

            self._log_progress("Planning festival layout ({} flat zones)...".format(len(self.flat_zones)))
            mh, mw = self.heightmap.shape
            if self.use_llm and self.llm_planner.available:
                llm_plan = self.llm_planner.plan(
                    flat_zones=self.flat_zones,
                    terrain_type=self.terrain_type,
                    map_size=(mw, mh),
                    style=self.settings.style,
                )
                if llm_plan is not None:
                    self.plan = llm_plan
            if self.plan is None:
                self.plan = self.layout_planner.plan(
                    flat_zones=self.flat_zones,
                    terrain_type=self.terrain_type,
                    map_size=(mw, mh),
                    style=self.settings.style,
                )

            # AI-powered stage generation from festival images
            self.ai_structures = []
            if festival_name and festival_images:
                self._log_progress("Generating AI stage designs from festival images...")
                try:
                    ai_gen = AIStageGenerator(
                        ollama_url=self.llm_planner.config.base_url if self.llm_planner.available else "http://localhost:11434",
                    )
                    design = ai_gen.analyze_images(festival_images, festival_name)
                    if self.plan:
                        reference_context = {
                            "orientation_hint": design.get("orientation_hint", "front-facing"),
                            "scene_hint": design.get("scene_hint", "stage"),
                        }
                        self.plan = self.layout_planner.apply_reference_context(
                            self.plan,
                            reference_context,
                            (self.heightmap.shape[1], self.heightmap.shape[0]),
                        )
                        cx, cz = self.plan.main_stage.x, self.plan.main_stage.z
                        stage = ai_gen.generate_stage(design, cx, cz)
                        self.heightmap = ai_gen.place_in_world(self.heightmap, stage, cx, cz)
                        self.ai_structures = ai_gen.export_structure(stage, cx, cz)
                        self._log_progress("AI stage '{}' placed at ({}, {})".format(stage.style, cx, cz))
                except Exception as e:
                    import warnings
                    warnings.warn(f"AI stage generation failed: {e}")

            if self.plan:
                self._log_progress("Placing structures...")
                self.place_structures()

            out = self.settings.output_dir / self.settings.minecraft_world_name
            self._log_progress("Exporting to {}...".format(out))
            self.export_minecraft_world(out)

            elapsed = time.time() - start
            return BuildResult(
                success=True,
                message="Festival world built in {:.0f}s (terrain: {}, {} stages, {} camping, {:.1f} km)".format(
                    elapsed,
                    self.terrain_type,
                    len(self.plan.secondary_stages) + 1 if self.plan else 0,
                    len(self.plan.camping) if self.plan else 0,
                    diameter_km,
                ),
                output_path=out,
            )
        except Exception as e:
            return BuildResult(success=False, message=str(e))

    def _log_progress(self, msg: str) -> None:
        """Emit a progress message (captured by the API if streaming)."""
        import warnings
        warnings.warn(msg)
        if hasattr(self, '_progress_callback') and self._progress_callback:
            self._progress_callback(msg)
        if hasattr(self, '_progress_messages'):
            self._progress_messages.append(msg)
