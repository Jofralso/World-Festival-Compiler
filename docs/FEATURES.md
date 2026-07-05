# Feature Wiki

FestivalWorld Compiler is designed as a local-first world-building engine for realistic festival environments. The feature set spans terrain analysis, layout planning, AI-assisted context enrichment, visible build progress, and server-ready export.

## 1. Terrain-aware festival generation

The pipeline starts from a terrain source and turns it into a buildable festival site. It detects flat areas, classifies the landscape, and proposes where the main stage should sit.

### Included capabilities
- grayscale and DEM-style terrain ingestion
- contour and slope analysis
- flat-zone selection for buildable areas
- terrain type classification for realistic stage placement
- terrain heuristics that steer layouts toward practical and believable festival form

## 2. Festival layout planning

The planner computes a staged layout that resembles a real festival site rather than a simple symmetric arrangement.

### Current heuristics
- main stage placed in a strong central area
- secondary stages separated from the core
- camping zones kept away from the main performance area
- paths routed between stages, entrance, and camping
- entrance and spawn chosen to create a believable arrival flow
- spacing and zoning rules that reduce crowding and improve realism

## 3. AI-assisted reference understanding

When a festival name is provided, the system can search for publicly available imagery and derive lightweight metadata from those references.

### Metadata used
- title
- snippet/description
- image URL
- orientation hint: front-facing or crowd-facing
- scene hint: stage, crowd scene, stage lighting

That metadata is used to bias the layout and better support stage orientation and audience-facing placement.

## 4. Visible build workflow

The web experience shows progress as the system builds the world. Users can observe the major stages of the process rather than waiting silently.

### Visible phases
- map analysis
- terrain context gathering
- layout planning
- AI reference analysis
- structure placement
- export and deployment staging

## 5. Export and world tooling

The generator produces export artifacts suitable for Minecraft map workflows and downstream automation.

### Output artifacts
- festival_plan.json
- place_structures.we
- world_manifest.json
- heightmap.png
- plugin_manifest.json
- server-ready deployment folders for local or remote hosting

## 6. Local-first design

The project is designed to work without a heavyweight cloud dependency stack. It can run with local heuristics and optional local model support when available.

## 7. Deployment and plugin integration

The project now includes a local deployment path that prepares a server-ready export bundle and a Paper plugin scaffold for triggering the workflow from a server environment.

### Included deployment features
- one-step deployment command from the repository CLI
- server-ready folder staging for Paper-compatible workflows
- plugin entry point for local deployment invocation

## 8. Future direction

Planned improvements include:
- richer public image understanding
- satellite and street-view inspired realism
- stronger terrain shaping from visual references
- live preview overlays and more immersive build feedback
- deeper integration with real Minecraft server deployment flows
