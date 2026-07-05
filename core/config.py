from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    map_path: Path | None = None
    refs_path: Path | None = None
    style: str = "electronic festival"
    scale: str = "1:1"
    output_dir: Path = Path("./output")
    schematic_dir: Path = Path("./schematics")

    worldpainter_path: str = "WorldPainter"
    qgis_path: str = "qgis_process"
    worldedit_path: str = "worldedit"
    plugin_manifest_path: str = "plugins/festivalworld"

    minecraft_world_name: str = "festival_world"
    server_type: str = "paper"  # paper | fabric

    host: str = "127.0.0.1"
    port: int = 8420

    model_config = {"env_prefix": "FW_"}
