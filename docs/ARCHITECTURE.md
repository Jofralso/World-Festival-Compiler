# Architecture Overview

FestivalWorld Compiler follows a modular pipeline architecture:

1. Ingest terrain input
2. Analyze terrain and detect buildable zones
3. Plan festival layout
4. Optionally enrich the layout from image references
5. Generate structures and export world artifacts
6. Stage the export for server deployment or plugin-driven use

## Main modules

### core/preprocessor.py
Responsible for loading heightmaps, extracting terrain features, and finding flat zones.

### core/layout.py
Contains the festival layout planner that chooses stage positions, camping, paths, entrance, and spawn.

### core/ai_stages.py
Handles public image discovery, reference metadata extraction, and AI-assisted stage design.

### core/worldgen.py
Builds and normalizes terrain outputs for world export.

### core/pipeline.py
Coordinates the full generation flow from terrain analysis to export.

### core/deploy.py
Stages generated exports into a deployment-ready folder for Minecraft server use.

### api/
Contains the FastAPI server and the browser-based GUI assets.

### plugins/festivalworld-paper/
Contains the Paper plugin scaffold that exposes the local deployment entry point for server-side triggering.

## Data flow

```text
heightmap / DEM
  -> terrain preprocessing
  -> flat-zone analysis
  -> layout planning
  -> optional image-reference enrichment
  -> structure placement
  -> export generation
  -> deployment staging
```

## Design principles

- modular components
- local-first processing where possible
- visible build progression
- deterministic planning with optional AI enhancement
- export-friendly artifact generation
- deployment-oriented outputs that are ready for real server workflows
