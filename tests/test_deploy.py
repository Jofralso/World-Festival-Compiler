import tempfile
import unittest
from pathlib import Path

from core.deploy import deploy_to_server


class DeployTests(unittest.TestCase):
    def test_deploy_to_server_copies_export_bundle(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            export_dir = Path(tmpdir) / "export"
            export_dir.mkdir(parents=True, exist_ok=True)
            (export_dir / "place_structures.we").write_text("//paste")
            (export_dir / "plugin_manifest.json").write_text("{}")
            (export_dir / "festival_plan.json").write_text("{}")
            (export_dir / "heightmap.png").write_bytes(b"png")

            server_dir = Path(tmpdir) / "server"
            result = deploy_to_server(export_dir, server_dir, world_name="world")

            self.assertTrue(result["ready"])
            self.assertTrue((server_dir / "plugins" / "festivalworld" / "place_structures.we").exists())
            self.assertTrue((server_dir / "plugins" / "festivalworld" / "deploy.sh").exists())

    def test_deploy_to_server_handles_missing_structure_script(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            export_dir = Path(tmpdir) / "export"
            export_dir.mkdir(parents=True, exist_ok=True)
            (export_dir / "plugin_manifest.json").write_text("{}")
            (export_dir / "festival_plan.json").write_text("{}")
            (export_dir / "heightmap.png").write_bytes(b"png")

            server_dir = Path(tmpdir) / "server"
            result = deploy_to_server(export_dir, server_dir, world_name="world")

            self.assertTrue(result["ready"])
            self.assertTrue((server_dir / "plugins" / "festivalworld" / "plugin_manifest.json").exists())
            self.assertTrue((server_dir / "plugins" / "festivalworld" / "deploy.sh").exists())


if __name__ == "__main__":
    unittest.main()
