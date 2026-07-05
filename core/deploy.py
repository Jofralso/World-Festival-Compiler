"""Automation helpers for deploying FestivalWorld exports to a Minecraft server."""

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any


def deploy_to_server(export_dir: Path, server_dir: Path, world_name: str | None = None) -> dict[str, Any]:
    """Copy the generated export bundle into a server-ready layout.

    This creates a plugin scaffold and a deployment script that can be used by a
    server wrapper or a manual deployment process. The goal is to minimize manual
    steps and make the export immediately usable for automation.
    """
    export_dir = Path(export_dir)
    server_dir = Path(server_dir)
    world_name = world_name or export_dir.name

    plugin_dir = server_dir / "plugins" / "festivalworld"
    plugin_dir.mkdir(parents=True, exist_ok=True)

    shutil.copy2(export_dir / "place_structures.we", plugin_dir / "place_structures.we")
    shutil.copy2(export_dir / "plugin_manifest.json", plugin_dir / "plugin_manifest.json")
    shutil.copy2(export_dir / "festival_plan.json", plugin_dir / "festival_plan.json")
    shutil.copy2(export_dir / "heightmap.png", plugin_dir / "heightmap.png")

    deploy_script = plugin_dir / "deploy.sh"
    deploy_script.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
DIR=$(cd "$(dirname "$0")" && pwd)
if [ -f "$DIR/place_structures.we" ]; then
  echo "FestivalWorld export ready at $DIR"
  echo "Next step: run the WorldEdit script in your server world or wrap it in a plugin command."
fi
"""
    )
    os.chmod(deploy_script, 0o755)

    return {
        "server_dir": str(server_dir),
        "plugin_dir": str(plugin_dir),
        "world_name": world_name,
        "ready": True,
    }
