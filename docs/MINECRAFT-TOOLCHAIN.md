# Minecraft toolchain integration

FestivalWorld Compiler is designed to export into the same kinds of workflows used by serious Minecraft map and server builders.

## Supported real-world tools

### WorldEdit
- Writes placement commands in a WorldEdit-compatible script.
- Supports schematic loading and paste commands for stages, barriers, lighting, and entrances.

### WorldPainter
- Exports a normalized heightmap image suitable for import into WorldPainter.
- This is the main bridge between procedural terrain generation and manual refinement.

### Paper/Fabric server workflow
- Generates a plugin-style manifest describing the output structure for server deployment and downstream automation.
- The manifest is intended for use with tooling or custom plugin wrappers that want to place festival content in a real server world.

## Recommended workflow

1. Generate terrain and festival plan.
2. Export the heightmap and placement script.
3. Import the terrain into WorldPainter for manual shaping.
4. Apply the WorldEdit script in a server world.
5. Use the plugin manifest as a deployment descriptor for automation.

## Export files

- heightmap.png
- festival_plan.json
- place_structures.we
- plugin_manifest.json
- world_manifest.json
- plugins/festivalworld/plugin.yml
- plugins/festivalworld/README.md
