import tempfile
import unittest
from pathlib import Path

import numpy as np

from core.config import Settings
from core.layout import CampingZone, FestivalPlan, StageZone
from core.pipeline import FestivalWorldPipeline


class PipelineToolchainTests(unittest.TestCase):
    def test_export_minecraft_world_creates_plugin_scaffold(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir) / "output"
            settings = Settings(output_dir=out_dir, minecraft_world_name="demo_world", schematic_dir=Path("schematics"))
            pipeline = FestivalWorldPipeline(settings)
            pipeline.heightmap = np.zeros((32, 32), dtype=np.float32)
            pipeline.plan = FestivalPlan(
                main_stage=StageZone("main_stage", 16, 16, 8, "main_stage"),
                secondary_stages=[],
                camping=[CampingZone(4, 4, 12, 12)],
                paths=[],
                entrance=(0, 8),
                spawn=(4, 4),
            )
            pipeline.we_commands = ["//schematic load main_stage", "//paste 10 64 10"]

            pipeline.export_minecraft_world(out_dir / "demo_world")

            self.assertTrue((out_dir / "demo_world" / "plugin_manifest.json").exists())
            self.assertTrue((out_dir / "demo_world" / "plugins" / "festivalworld" / "plugin.yml").exists())
            self.assertTrue((out_dir / "demo_world" / "plugins" / "festivalworld" / "README.md").exists())


if __name__ == "__main__":
    unittest.main()
