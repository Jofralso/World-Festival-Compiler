# CLI and API Reference

## CLI commands

### build
```bash
python3 -m cli build --map <terrain-file> --style <festival-style> --name <world-name>
```

Options:
- --map, -m: terrain file path
- --refs, -r: reference image directory
- --style, -s: festival style label
- --output, -o: output directory
- --use-llm: enable optional local LLM support
- --llm-model: model name for local LLM integration
- --llm-url: local LLM server URL

### plan
```bash
python3 -m cli plan --map <terrain-file> --export <plan.json>
```

### preview
```bash
python3 -m cli preview --map <terrain-file> --output <directory>
```

### deploy
```bash
python3 -m cli deploy --export-dir <build-output> --server-dir <server-output> --world-name <world-name>
```

### serve
```bash
python3 -m cli serve --host 127.0.0.1 --port 8420
```

## API endpoints

When the server is running:

- GET /health
- GET /gui/
- POST /gui/preview
- POST /gui/plan
- POST /gui/build
- POST /api/plan
- POST /api/build
- GET /api/schematics

## Typical workflow

1. Run the build command for a terrain map.
2. Preview the generated layout if needed.
3. Deploy the export bundle into a server-ready folder.
4. Use the exported manifest and WorldEdit script inside your preferred Minecraft workflow.
