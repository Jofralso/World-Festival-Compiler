"""FastAPI orchestration server."""

from pathlib import Path
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from ..core.config import Settings
from ..core.pipeline import FestivalWorldPipeline
from ..core.layout import FestivalPlan

app = FastAPI(
    title="FestivalWorld Builder API",
    version="0.1.0",
    description="Procedural festival world compiler",
)


@app.get("/")
async def root():
    return RedirectResponse(url="/gui/")


static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

from .gui_routes import router as gui_router
app.include_router(gui_router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "festivalworld"}


@app.post("/build")
async def api_build(
    map_file: UploadFile | None = File(None),
    style: str = Form("electronic festival"),
    world_name: str = Form("festival_world"),
):
    settings = Settings(style=style, minecraft_world_name=world_name)
    pipeline = FestivalWorldPipeline(settings)

    if map_file:
        map_path = Path(f"/tmp/{map_file.filename}")
        map_path.write_bytes(await map_file.read())
        result = pipeline.build(map_path=map_path)
    else:
        result = pipeline.build()

    if not result.success:
        raise HTTPException(status_code=500, detail=result.message)

    return {
        "success": True,
        "message": result.message,
        "output_path": str(result.output_path),
    }


@app.post("/plan")
async def api_plan(
    map_file: UploadFile = File(...),
    style: str = Form("electronic festival"),
    min_area: int = Form(400),
):
    from ..core.preprocessor import load_heightmap, find_flat_zones, classify_terrain
    from ..core.layout import LayoutPlanner

    map_path = Path(f"/tmp/{map_file.filename}")
    map_path.write_bytes(await map_file.read())
    hmap = load_heightmap(map_path)
    terrain = classify_terrain(hmap)
    zones = find_flat_zones(hmap, min_area=min_area)

    planner = LayoutPlanner()
    plan = planner.plan(zones, terrain, map_size=hmap.shape[::-1], style=style)

    return {
        "terrain": terrain,
        "flat_zones_count": len(zones),
        "plan": plan.to_dict(),
    }


@app.get("/schematics")
async def api_schematics():
    from ..core.structures import SCHEMATIC_LIBRARY
    return {"schematics": list(SCHEMATIC_LIBRARY.keys())}


def start_server(host: str = "127.0.0.1", port: int = 8420) -> None:
    import uvicorn
    uvicorn.run(app, host=host, port=port)
