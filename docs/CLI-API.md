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

### plan
```bash
python3 -m cli plan --map <terrain-file> --export <plan.json>
```

### preview
```bash
python3 -m cli preview --map <terrain-file> --output <directory>
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
