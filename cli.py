"""FestivalWorld Builder CLI."""

import argparse
import sys
from pathlib import Path

if __package__ in {None, ""}:
    import os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from .core.config import Settings
    from .core.pipeline import FestivalWorldPipeline
except ImportError:
    from core.config import Settings
    from core.pipeline import FestivalWorldPipeline


def build(args: argparse.Namespace) -> None:
    settings = Settings(
        map_path=Path(args.map) if args.map else None,
        refs_path=Path(args.refs) if args.refs else None,
        style=args.style,
        scale=args.scale,
        output_dir=Path(args.output),
        minecraft_world_name=args.name,
    )
    try:
        from .core.llm import LLMConfig
    except ImportError:
        from core.llm import LLMConfig
    llm_cfg = LLMConfig(base_url=args.llm_url, model=args.llm_model)
    pipeline = FestivalWorldPipeline(settings, use_llm=args.use_llm, llm_config=llm_cfg)
    result = pipeline.build(map_path=settings.map_path)

    print(result)
    if not result.success:
        sys.exit(1)


def plan_cmd(args: argparse.Namespace) -> None:
    """Analyse a map and show the festival plan without building."""
    try:
        from .core.preprocessor import load_heightmap, find_flat_zones, classify_terrain
        from .core.layout import LayoutPlanner
    except ImportError:
        from core.preprocessor import load_heightmap, find_flat_zones, classify_terrain
        from core.layout import LayoutPlanner

    hmap = load_heightmap(Path(args.map))
    terrain = classify_terrain(hmap)
    zones = find_flat_zones(hmap, min_area=int(args.min_area))

    planner = LayoutPlanner()
    plan = planner.plan(zones, terrain, map_size=hmap.shape[::-1], style=args.style)

    print(f"Terrain: {terrain}")
    print(f"Flat zones detected: {len(zones)}")
    print(f"Main stage: ({plan.main_stage.x}, {plan.main_stage.z}) radius={plan.main_stage.radius}")
    print(f"Secondary stages: {len(plan.secondary_stages)}")
    print(f"Camping zones: {len(plan.camping)}")
    print(f"Paths: {len(plan.paths)}")

    if args.export:
        plan.to_json(Path(args.export))


def serve(args: argparse.Namespace) -> None:
    """Start the FastAPI orchestration server."""
    try:
        from .api.server import start_server
    except ImportError:
        from api.server import start_server
    start_server(host=args.host, port=args.port)


def preview_cmd(args: argparse.Namespace) -> None:
    """Preview a topographic map with terrain analysis and overlays."""
    try:
        from .core.preprocessor import load_heightmap, find_flat_zones, classify_terrain
        from .core.preview import analyse_terrain, render_all_maps, try_3d_plot
    except ImportError:
        from core.preprocessor import load_heightmap, find_flat_zones, classify_terrain
        from core.preview import analyse_terrain, render_all_maps, try_3d_plot
    from pathlib import Path

    map_path = Path(args.map)
    if not map_path.exists():
        print(f"Map not found: {map_path}")
        sys.exit(1)

    hmap = load_heightmap(map_path)
    terrain = classify_terrain(hmap)
    zones = find_flat_zones(hmap, min_area=int(args.min_area))

    info = analyse_terrain(hmap, zones, terrain)

    print(f"Map: {map_path.name}")
    print(f"Size: {info.width}×{info.height}")
    print(f"Height range: {info.min_height} – {info.max_height} (mean {info.mean_height})")
    print(f"Terrain type: {info.terrain_type}")
    print(f"Contour lines: {info.contours}")
    print(f"Flat zones: {info.flat_zone_count}")
    if info.flat_zones:
        print(f"  Largest: {info.flat_zones[0]['w']}×{info.flat_zones[0]['h']} "
              f"at ({info.flat_zones[0]['x']}, {info.flat_zones[0]['z']})")

    if args.output:
        out_dir = Path(args.output)
        out_dir.mkdir(parents=True, exist_ok=True)

        maps = render_all_maps(hmap, zones)
        for name, img in maps.items():
            ext = "png"
            from .core.preview import img_to_bytes
            (out_dir / f"{name}.{ext}").write_bytes(img_to_bytes(img))
        print(f"\nPreviews saved to {out_dir}/")
        print(f"  contours.png — contour lines")
        print(f"  flat_zones.png — highlighted flat areas")
        print(f"  stage_plan.png — festival layout (if available)")

        three_d = out_dir / "terrain_3d.png"
        if try_3d_plot(hmap, three_d):
            print(f"  terrain_3d.png — 3D terrain")

    if args.show:
        try:
            from .core.preview import img_to_bytes
            maps = render_all_maps(hmap, zones)
            for name, img in maps.items():
                path = f"/tmp/fw_preview_{name}.png"
                Path(path).write_bytes(img_to_bytes(img))
                print(f"  Wrote {path} (open in image viewer)")
        except Exception as e:
            print(f"  Preview display error: {e}")


def deploy(args: argparse.Namespace) -> None:
    """Copy the generated export into a server-ready deployment directory."""
    try:
        from .core.deploy import deploy_to_server
    except ImportError:
        from core.deploy import deploy_to_server

    export_dir = Path(args.export_dir)
    server_dir = Path(args.server_dir)
    result = deploy_to_server(export_dir, server_dir, world_name=args.world_name)
    print(result)


def list_schematics(args: argparse.Namespace) -> None:
    """List available schematics in the library."""
    schematic_dir = Path(args.dir)
    if not schematic_dir.exists():
        print(f"Schematic directory not found: {schematic_dir}")
        sys.exit(1)

    for entry in sorted(schematic_dir.iterdir()):
        if entry.is_dir():
            schematics = list(entry.glob("*.schem")) + list(entry.glob("*.schematic"))
            if schematics:
                print(f"\n{entry.name}/")
                for s in schematics:
                    print(f"  └── {s.name}")
        elif entry.suffix in (".schem", ".schematic"):
            print(entry.name)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="festivalworld",
        description="Procedural festival world compiler — generates Minecraft festival environments",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # build
    build_p = sub.add_parser("build", help="Run the full build pipeline")
    build_p.add_argument("--map", "-m", help="Path to topographic map (image/DEM)")
    build_p.add_argument("--refs", "-r", help="Directory of festival reference images")
    build_p.add_argument("--style", "-s", default="electronic festival", help="Festival style")
    build_p.add_argument("--scale", default="1:1", help="World scale")
    build_p.add_argument("--output", "-o", default="./output", help="Output directory")
    build_p.add_argument("--name", "-n", default="festival_world", help="Minecraft world name")
    build_p.add_argument("--use-llm", action="store_true", help="Use local LLM (Ollama) for AI-assisted layout")
    build_p.add_argument("--llm-model", default="llama3.1", help="Ollama model name")
    build_p.add_argument("--llm-url", default="http://localhost:11434", help="Ollama server URL")
    build_p.set_defaults(func=build)

    # plan
    plan_p = sub.add_parser("plan", help="Analyse a map and show the festival plan")
    plan_p.add_argument("--map", "-m", required=True, help="Path to topographic map")
    plan_p.add_argument("--style", "-s", default="electronic festival", help="Festival style")
    plan_p.add_argument("--min-area", default=400, help="Minimum flat zone area")
    plan_p.add_argument("--export", "-e", help="Export plan JSON to file")
    plan_p.set_defaults(func=plan_cmd)

    # serve
    serve_p = sub.add_parser("serve", help="Start the API orchestration server")
    serve_p.add_argument("--host", default="127.0.0.1")
    serve_p.add_argument("--port", type=int, default=8420)
    serve_p.set_defaults(func=serve)

    # preview
    prev_p = sub.add_parser("preview", help="Preview a map with terrain overlays")
    prev_p.add_argument("--map", "-m", required=True, help="Path to topographic map")
    prev_p.add_argument("--min-area", default=400, help="Minimum flat zone area")
    prev_p.add_argument("--output", "-o", help="Directory to save preview images")
    prev_p.add_argument("--show", action="store_true", help="Generate temp preview images")
    prev_p.set_defaults(func=preview_cmd)

    # deploy
    deploy_p = sub.add_parser("deploy", help="Deploy an exported festival build to a server-ready directory")
    deploy_p.add_argument("--export-dir", required=True, help="Path to the generated export directory")
    deploy_p.add_argument("--server-dir", required=True, help="Target Minecraft server directory")
    deploy_p.add_argument("--world-name", help="Optional world folder name")
    deploy_p.set_defaults(func=deploy)

    # schematics
    schem_p = sub.add_parser("schematics", help="List available schematics")
    schem_p.add_argument("--dir", "-d", default="./schematics", help="Schematic library directory")
    schem_p.set_defaults(func=list_schematics)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
