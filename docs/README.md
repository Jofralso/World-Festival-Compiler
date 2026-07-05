# FestivalWorld Documentation

FestivalWorld Compiler is a local-first pipeline for turning terrain data, festival references, and public-world context into a deployable Minecraft festival environment. This documentation set covers the full workflow from terrain input to server-ready deployment.

## Documentation map

- [FEATURES.md](FEATURES.md) — full feature overview and product capabilities
- [ARCHITECTURE.md](ARCHITECTURE.md) — module layout, data flow, and design principles
- [CLI-API.md](CLI-API.md) — CLI commands, web API routes, and examples
- [MINECRAFT-TOOLCHAIN.md](MINECRAFT-TOOLCHAIN.md) — WorldEdit, WorldPainter, Paper plugin, and deployment workflow

## Quick navigation

### Build a festival world
1. Prepare a heightmap or terrain image.
2. Run the build command.
3. Review the generated world artifacts in the output directory.
4. Deploy the export bundle into a server-ready folder.

### Use the web interface
1. Start the local server with the CLI.
2. Open the local GUI in your browser.
3. Submit a map and style prompt for interactive generation.

### Deploy to Minecraft
1. Build the export.
2. Run the deployment command.
3. Use the generated plugin manifest and WorldEdit script in a Paper or compatible server workflow.

## Project goals

- Realistic festival layout planning
- Local-first generation with optional AI enrichment
- Visible build progress for the user
- Export artifacts suitable for Minecraft map creation and server deployment
