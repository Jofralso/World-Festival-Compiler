# 🎪 FestivalWorld Builder — Complete Tutorial

Build Minecraft festival worlds from topographic maps.

---

## Quick start

```bash
# 1. Launch the GUI
festivalworld serve

# 2. Open http://localhost:8420 in your browser
# 3. Drop in a heightmap, click "Build World"
```

## CLI commands

```bash
festivalworld build --map heightmap.png --style "techno"
festivalworld plan --map heightmap.png --export plan.json
festivalworld preview --map heightmap.png --output preview_out
festivalworld serve           # Web GUI at :8420
festivalworld schematics      # List installed schematics
```

---

## File types explained

### 1. Topographic map (`--map`)

What the pipeline accepts:

| Format | Extension | Notes |
|--------|-----------|-------|
| Grayscale PNG | `.png` | White = high, black = low |
| JPEG | `.jpg` | Auto-converted to grayscale |
| GeoTIFF | `.tif` / `.tiff` | Reads first band |
| 16-bit PNG | `.png` | Higher precision terrain |
| DEM | `.dem` | If supported by OpenCV |

The pipeline detects terrain type (mountain / flat / coastal) and
finds flat zones suitable for placing stages.

**Example:** `/home/z3rt/festivalworld/examples/heightmap_example.png`
— 512×512 synthetic terrain with a mountain ridge, valley, and a central flat plateau
(the plateau is where stages get placed).

### 2. Festival reference images (`--refs`)

Any images you want the AI to consider when planning layout:
- Stage photos (main stage, secondary stages)
- Lighting references
- Crowd area layouts
- Camping zone sketches
- Entrance gate designs

These are **informational** — they help you document intent.
The current pipeline uses them as upload records; future AI
integration (LLM vision) will analyse them for style cues.

### 3. WorldEdit schematics

WorldEdit `.schematic` files define 3D structures that get placed
at planned locations. The pipeline generates a `.we` script that
runs in-game via WorldEdit (`//schematic load` + `//paste`).

Schematic library (in `schematics/`):

| Directory | Used for |
|-----------|----------|
| `main_stage/` | Main performance stage |
| `techno_stage/` | Secondary electronic stage |
| `dnb_arena/` | Drum & bass arena |
| `acoustic_stage/` | Small chill stage |
| `lighting_rig/` | Lighting towers around stages |
| `crowd_barrier/` | Crowd control barriers |
| `entrance_gate/` | Festival entrance |
| `ferris_wheel/` | Carnival ride |
| `camping_tent/` | Camping plot marker |
| `spawn_platform/` | Player spawn |
| `path_block/` | Path segments |

---

## Step-by-step workflow

### 🎯 Goal: a Minecraft festival world from a map image

**Step 1 — prepare your heightmap**

Take a topographic map (contour map, DEM, satellite elevation data).
Export it as a grayscale PNG where:
- **White pixels** = high elevation (mountains)
- **Black pixels** = low elevation (valleys/flat)

Recommended size: 512×512 pixels (each pixel = 1 block).

**Step 2 — preview the map**

```bash
festivalworld preview --map my_heightmap.png --output preview_out
```

Generates 4 visualisation images in `preview_out/`:

| Image | What it shows |
|-------|---------------|
| `contours.png` | Topographic contour lines overlaid |
| `flat_zones.png` | Buildable flat areas highlighted in green |
| `stage_plan.png` | Festival layout (stages, camping, paths) |
| `terrain_3d.png` | 3D surface plot (requires matplotlib) |

Also prints terrain info: height range, terrain type, contour count,
and largest flat zone location.

**In the GUI:** drop a map and click **Analyse Map** — instantly see
all 4 overlay views switchable via tabs, plus terrain stats.

**Step 3 — analyse**

```bash
festivalworld plan --map my_heightmap.png --export plan.json
```

Output shows:
- Terrain type
- Number of flat zones found
- Suggested stage positions
- Camping zones and paths

**Step 3 — inspect the plan**

Open `plan.json`:

```json
{
  "main_stage": {"x": 250, "z": 250, "radius": 80},
  "secondary_stages": [...],
  "camping": [...],
  "paths": [...]
}
```

**Step 4 — build the world**

```bash
festivalworld build --map my_heightmap.png --style "electronic festival" --name my_festival
```

Output in `./output/my_festival/`:

| File | What it is |
|------|------------|
| `heightmap.png` | Normalised heightmap for WorldPainter |
| `festival_plan.json` | The layout plan |
| `place_structures.we` | WorldEdit command script |
| `world_manifest.json` | Build summary |

**Step 5 — import into Minecraft**

**Option A: WorldPainter (terrain)**
1. Open WorldPainter → Import → Height Map
2. Select `heightmap.png`
3. Export as Minecraft world

**Option B: Direct world file** (future)

**Step 6 — place structures**

1. Install WorldEdit on your server
2. Copy `.schematic` files to `plugins/WorldEdit/schematics/`
3. Run in-game: `/schematic load place_structures`
4. Or use the `.we` script: `//cs place_structures.we`

---

## GUI guide

The web GUI at `http://localhost:8420` provides a visual interface:

1. **🗺️ Topographic Map** — drag & drop your heightmap
2. **📸 Festival References** — add reference photos
3. **🧱 Schematic Library** — upload custom schematics
4. **⚙️ Configuration** — choose style, world name, scale
5. **🔍 Analyse Map** — detect terrain + generate 4 overlay previews + plan layout
6. **🗺️ Map Preview** — switch between tabs: Raw, Contours, Flat Zones, Stage Plan, 3D
7. **📋 Festival Plan** — see the AI-generated plan as JSON or summary
8. **⚡ Build World** — run the full pipeline
9. **📦 Build Output** — see generated file list

---

## Example files

All located in `/home/z3rt/festivalworld/examples/`:

### Maps
- `heightmap_example.png` — 512×512 grayscale heightmap (mountain + flat plateau)
- `heightmap_example_16bit.png` — 16-bit version for higher precision
- `dem_example.tif` — Minimal GeoTIFF with geo-tags

### Reference images
- `main_stage_concept.jpg` — Main stage concept art
- `lighting_rig_ref.jpg` — Lighting rig reference
- `crowd_area_ref.jpg` — Crowd area layout
- `camping_layout.jpg` — Camping zone plan
- `entrance_gate_ref.jpg` — Entrance gate design

### Schematics
`examples/schematics/` — 5 valid WorldEdit `.schematic` files:
- `main_stage.schematic` — 21×10×21 stage structure (stone floor + pillars + glowstone)
- `techno_stage.schematic` — 15×8×15 techno stage
- `lighting_rig.schematic` — 5×12×5 lighting tower
- `crowd_barrier.schematic` — 7×3×2 barrier segment
- `entrance_gate.schematic` — 9×7×3 gate arch

### Plan
- `festival_plan_example.json` — Example festival layout plan

### Try the full demo

```bash
# CLI: preview first
festivalworld preview --map examples/heightmap_example.png --output /tmp/preview
open /tmp/preview/terrain_3d.png   # 3D terrain view

# CLI: then build
festivalworld build --map examples/heightmap_example.png \
  --style "electronic festival" --name demo_festival \
  --output /tmp/demo_output

# Or use the GUI:
festivalworld serve
# → open http://localhost:8420
# → drop heightmap_example.png into the map zone
# → click "Analyse Map" → see overlays in tabs
# → click "Build World"
```

---

## API reference

When the server is running:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Web GUI |
| `/health` | GET | Health check |
| `/gui/` | GET | Web GUI (main page) |
| `/gui/preview` | POST | Analyse + return overlay images (multipart: map_file) |
| `/gui/plan` | POST | Analyse map (multipart: map_file, style) |
| `/gui/build` | POST | Build world (multipart: map_file, style, world_name) |
| `/api/plan` | POST | JSON API — analyse map |
| `/api/build` | POST | JSON API — build world |
| `/api/schematics` | GET | List known schematic types |

---

## Extending the system

### Add new schematics

1. Build a structure in Minecraft with WorldEdit
2. Select it: `//pos1` + `//pos2`
3. Save: `//schematic save my_stage`
4. Copy to `schematics/my_stage/`
5. Add entry in `festivalworld/core/structures.py` `SCHEMATIC_LIBRARY`

### Custom stage styles

Edit `festivalworld/core/layout.py` — add new stage names
and their style mappings in `_pick_stages()`.

### Live control (MIDI/OSC)

The pipeline generates a `festival_plan.json`. This can be consumed
by external tools to sync lighting, BPM triggers, and stage effects.
Future versions will include MIDI → Minecraft event bindings.
