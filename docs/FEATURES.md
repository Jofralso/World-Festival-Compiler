# Feature Wiki

## 1. Terrain-aware festival generation

The pipeline starts from a terrain source and translates it into a place where a festival can exist. It detects flat areas, classifies the landscape, and proposes where the main stage should sit.

### Included capabilities
- grayscale and DEM-style terrain ingestion
- contour and slope analysis
- flat-zone selection for buildable areas
- terrain type classification for realistic stage placement

## 2. Festival layout planning

The planner computes a staged layout that resembles a real festival site rather than a simple symmetric arrangement.

### Current heuristics
- main stage placed in a strong central area
- secondary stages separated from the core
- camping zones kept away from the main performance area
- paths routed between stages, entrance, and camping
- entrance and spawn chosen to create a believable arrival flow

## 3. AI-assisted reference understanding

When a festival name is provided, the system can search for publicly available imagery and derive lightweight metadata from those references.

### Metadata used
- title
- snippet/description
- image URL
- orientation hint: front-facing or crowd-facing
- scene hint: stage, crowd scene, stage lighting

That metadata is used to bias the layout and better support stage orientation and audience-facing placement.

## 4. Web UI and build visualization

The web experience shows progress as the system builds the world. Users can see the major stages of the process rather than waiting silently.

### Visible phases
- map analysis
- terrain context gathering
- layout planning
- AI reference analysis
- structure placement
- export

## 5. Export and world tooling

The generator produces export artifacts suitable for Minecraft map workflows.

### Output artifacts
- festival plan JSON
- WorldEdit placement script
- world manifest
- heightmap export for external terrain tools

## 6. Local-first design

The project is designed to work without a heavyweight cloud dependency stack. It can run with local heuristics and optional local model support when available.

## 7. Future direction

Planned improvements include:
- richer public image understanding
- satellite and street-view inspired realism
- stronger terrain shaping from visual references
- live preview overlays and more immersive build feedback
