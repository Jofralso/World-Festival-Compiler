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

    structure_script = export_dir / "place_structures.we"
    if not structure_script.exists():
        for candidate in ("place_structures.we", "world_edit_script.we", "structure_script.we"):
            candidate_path = export_dir / candidate
            if candidate_path.exists():
                structure_script = candidate_path
                break

    if structure_script.exists():
        shutil.copy2(structure_script, plugin_dir / structure_script.name)

    manifest_path = export_dir / "plugin_manifest.json"
    if manifest_path.exists():
        shutil.copy2(manifest_path, plugin_dir / manifest_path.name)

    plan_path = export_dir / "festival_plan.json"
    if plan_path.exists():
        shutil.copy2(plan_path, plugin_dir / plan_path.name)

    heightmap_path = export_dir / "heightmap.png"
    if heightmap_path.exists():
        shutil.copy2(heightmap_path, plugin_dir / heightmap_path.name)

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
