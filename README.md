# FestivalWorld Compiler

FestivalWorld Compiler is a local-first procedural world generator for building Minecraft festival environments from terrain maps, festival references, and public image inspiration. It combines terrain analysis, festival layout planning, schematic placement, and optional AI-assisted stage generation into a single build pipeline.

## What it does

- Reads grayscale terrain maps, DEMs, and similar height inputs.
- Detects flat zones and classifies terrain.
- Plans realistic festival layouts with stages, camping, paths, entrance, and spawn.
- Generates WorldEdit-compatible placement output.
- Supports AI-assisted stage generation from festival-name-based image discovery and public reference metadata.
- Exposes a web GUI and REST API for interactive generation.

## Core features

### Terrain intelligence
- Heightmap ingestion from PNG, JPEG, GeoTIFF, and DEM-style inputs.
- Terrain classification such as flat, mountain, coastal, or mixed.
- Flat-zone detection and contour analysis.

### Festival planning
- Main stage, secondary stages, camping, entrance, spawn, and path planning.
- Realism heuristics that keep stages spaced and camping away from the core.
- Optional AI-driven layout adjustments from image reference context.

### AI-assisted stage design
- Searches for publicly available festival imagery using festival names.
- Extracts lightweight metadata such as title, snippet, orientation hint, and scene hint.
- Uses that context to bias stage placement and overall festival flow.
- Can generate a stage concept that is exported as a block structure overlay.

### Build workflow
- CLI build, plan, preview, and schematic-list commands.
- FastAPI web server with GUI and API endpoints.
- Visible build progress in the web UI.

## Quick start

### Install dependencies

```bash
python3 -m pip install -r requirements.txt
```

If requirements are not present, install the commonly used runtime packages manually:

```bash
python3 -m pip install numpy pillow opencv-python fastapi uvicorn requests
```

### CLI usage

```bash
python3 -m cli build --map examples/heightmap_example.png --style "electronic festival" --name demo_festival
python3 -m cli plan --map examples/heightmap_example.png --export output/demo_plan.json
python3 -m cli preview --map examples/heightmap_example.png --output output/previews
python3 -m cli serve
```

### Web GUI

```bash
python3 -m cli serve
```

Then open http://127.0.0.1:8420.

## Project structure

- core/: terrain parsing, planning, world generation, AI stage logic, and preview rendering
- api/: FastAPI server and web UI assets
- schematics/: example Minecraft schematics used for structures
- examples/: sample maps and festival plan examples
- output/: generated build artifacts
- tests/: regression tests for layout realism and AI context features

## Documentation

- [tutorial.md](tutorial.md) for a practical walkthrough
- [docs/FEATURES.md](docs/FEATURES.md) for the full feature wiki
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the implementation overview
- [docs/CLI-API.md](docs/CLI-API.md) for commands and API endpoints

## Roadmap

- richer satellite and street-view style understanding
- stronger reference-image based terrain shaping
- more advanced schematic generation and world export options
- tighter real-time preview and simulation experience
