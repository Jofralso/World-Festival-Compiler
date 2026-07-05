"""GUI routes for the FestivalWorld Builder web interface."""

import io
import json
from pathlib import Path
import numpy as np
from PIL import Image as PILImage
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse

from ..core.config import Settings
from ..core.pipeline import FestivalWorldPipeline
from ..core.preprocessor import load_heightmap, find_flat_zones, classify_terrain
from ..core.layout import LayoutPlanner
from ..core.llm import LLMConfig

router = APIRouter(prefix="/gui")


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def gui_index():
    html_path = Path(__file__).parent / "templates" / "gui.html"
    return HTMLResponse(html_path.read_text())


@router.post("/plan")
async def gui_plan(
    map_file: UploadFile = File(...),
    style: str = Form("electronic festival"),
    min_area: int = Form(400),
):
    map_path = Path(f"/tmp/fw_{map_file.filename}")
    map_path.write_bytes(await map_file.read())

    try:
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
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        map_path.unlink(missing_ok=True)


@router.post("/build")
async def gui_build(
    map_file: UploadFile = File(...),
    style: str = Form("electronic festival"),
    world_name: str = Form("festival_world"),
    ref_files: list[UploadFile] = File(default=[]),
    schematic_files: list[UploadFile] = File(default=[]),
    use_llm: bool = Form(False),
    llm_model: str = Form("llama3.1"),
    llm_url: str = Form("http://localhost:11434"),
):
    settings = Settings(style=style, minecraft_world_name=world_name)
    llm_cfg = LLMConfig(base_url=llm_url, model=llm_model)
    pipeline = FestivalWorldPipeline(settings, use_llm=use_llm, llm_config=llm_cfg)

    map_path = Path(f"/tmp/fw_build_{map_file.filename}")
    map_path.write_bytes(await map_file.read())

    refs_dir = Path(f"/tmp/fw_refs_{world_name}")
    schem_dir = Path(f"/tmp/fw_schems_{world_name}")

    try:
        if ref_files:
            refs_dir.mkdir(parents=True, exist_ok=True)
            for ref in ref_files:
                (refs_dir / ref.filename).write_bytes(await ref.read())

        if schematic_files:
            schem_dir.mkdir(parents=True, exist_ok=True)
            for s in schematic_files:
                (schem_dir / s.filename).write_bytes(await s.read())
            settings.schematic_dir = schem_dir

        result = pipeline.build(map_path=map_path)

        if not result.success:
            raise HTTPException(status_code=500, detail=result.message)

        output_tree = []
        if result.output_path and result.output_path.exists():
            output_tree = sorted(
                p.name for p in result.output_path.iterdir() if p.is_file()
            )

        return {
            "success": True,
            "message": result.message,
            "output_path": str(result.output_path),
            "output_tree": output_tree,
        }
    except Exception as e:
        if not isinstance(e, HTTPException):
            raise HTTPException(status_code=500, detail=str(e))
        raise
    finally:
        map_path.unlink(missing_ok=True)
        import shutil
        if refs_dir.exists():
            shutil.rmtree(refs_dir, ignore_errors=True)
        if schem_dir.exists():
            shutil.rmtree(schem_dir, ignore_errors=True)


@router.post("/preview")
async def gui_preview(
    map_file: UploadFile = File(...),
    min_area: int = Form(400),
):
    """Analyse a map and return terrain info + overlay images as base64."""
    from ..core.preview import (
        analyse_terrain,
        render_all_maps,
        img_to_base64,
        try_3d_plot,
    )

    map_path = Path(f"/tmp/fw_preview_{map_file.filename}")
    map_path.write_bytes(await map_file.read())

    try:
        hmap = load_heightmap(map_path)
        terrain = classify_terrain(hmap)
        zones = find_flat_zones(hmap, min_area=min_area)

        info = analyse_terrain(hmap, zones, terrain)
        maps = render_all_maps(hmap, zones)

        response = {
            "info": {
                "width": info.width,
                "height": info.height,
                "min_height": info.min_height,
                "max_height": info.max_height,
                "mean_height": info.mean_height,
                "terrain_type": info.terrain_type,
                "flat_zone_count": info.flat_zone_count,
                "contours": info.contours,
                "flat_zones": info.flat_zones[:5],
            },
            "images": {
                "contours": f"data:image/png;base64,{img_to_base64(maps['contours'])}",
                "flat_zones": f"data:image/png;base64,{img_to_base64(maps['flat_zones'])}",
                "stage_plan": f"data:image/png;base64,{img_to_base64(maps['stage_plan'])}",
            },
        }

        three_d_path = Path("/tmp/fw_preview_3d.png")
        if try_3d_plot(hmap, three_d_path):
            import base64
            response["images"]["terrain_3d"] = (
                f"data:image/png;base64,{base64.b64encode(three_d_path.read_bytes()).decode()}"
            )
            three_d_path.unlink(missing_ok=True)

        return response
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        map_path.unlink(missing_ok=True)


# ─────────────────────────────────────────────
# GEO SEARCH & TERRAIN
# ─────────────────────────────────────────────

@router.post("/search")
async def gui_search(query: str = Form(...), limit: int = Form(5)):
    """Search for a place by name using Nominatim."""
    from ..core.geo import search_place
    try:
        results = search_place(query, limit=limit)
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/terrain")
async def gui_terrain(
    lat: float = Form(...),
    lng: float = Form(...),
    diameter_km: float = Form(10.0),
    srtm_resolution: str = Form("SRTMGL3"),
):
    """Download SRTM+OSM for a location and return terrain info + overlay images."""
    from ..core.geo import download_srtm, download_osm_features, expand_bounds_to_diameter
    from ..core.worldgen import WorldBuilder
    from ..core.preprocessor import classify_terrain, find_flat_zones
    import base64

    try:
        bounds = expand_bounds_to_diameter((lat, lng), diameter_km)

        srtm = download_srtm(bounds, resolution=srtm_resolution)
        osm = download_osm_features(bounds)

        wb = WorldBuilder(diameter_blocks=int(diameter_km * 1000))
        wb.from_srtm(srtm, bounds, osm)

        from ..core.preview import render_all_maps, img_to_base64
        hmap_8 = wb.get_export_heightmap()
        terrain = classify_terrain(hmap_8)
        zones = find_flat_zones(hmap_8, min_area=200)
        maps = render_all_maps(hmap_8, zones)

        feature_counts = {
            "roads": len(osm.get("roads", [])),
            "buildings": len(osm.get("buildings", [])),
            "water_bodies": len(osm.get("water", [])),
            "parks": len(osm.get("parks", [])),
        }

        # Downsampled heightmap for 3D preview in browser (max 600px)
        h_preview = hmap_8
        h_max = max(h_preview.shape)
        if h_max > 600:
            scale = 600 / h_max
            pil_img = PILImage.fromarray(h_preview)
            pil_img = pil_img.resize((int(h_preview.shape[1] * scale), int(h_preview.shape[0] * scale)), PILImage.LANCZOS)
            h_preview = np.array(pil_img, dtype=np.uint8)
        raw_buf = io.BytesIO()
        PILImage.fromarray(h_preview).save(raw_buf, format="PNG")
        raw_b64 = base64.b64encode(raw_buf.getvalue()).decode()

        return {
            "bounds": {"south": bounds[0], "west": bounds[1], "north": bounds[2], "east": bounds[3]},
            "diameter_km": diameter_km,
            "terrain": terrain,
            "flat_zones_count": len(zones),
            "feature_counts": feature_counts,
            "heightmap_b64": raw_b64,
            "heightmap_size": {"width": h_preview.shape[1], "height": h_preview.shape[0]},
            "images": {
                "raw": f"data:image/png;base64,{raw_b64}",
                "contours": f"data:image/png;base64,{img_to_base64(maps['contours'])}",
                "flat_zones": f"data:image/png;base64,{img_to_base64(maps['flat_zones'])}",
                "stage_plan": f"data:image/png;base64,{img_to_base64(maps['stage_plan'])}",
            },
        }
    except Exception as e:
        import traceback
        raise HTTPException(status_code=400, detail=f"{e}\n{traceback.format_exc()}")


@router.post("/festival-images")
async def gui_festival_images(name: str = Form(...), limit: int = Form(6)):
    """Search for publicly available images via Wikipedia and free image APIs."""
    import urllib.request, urllib.parse, json, re

    images = []
    seen = set()

    # 1. Try Wikipedia API for the festival page + images
    try:
        query = urllib.parse.quote(name)
        url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={query}+festival&format=json&srlimit=3"
        req = urllib.request.Request(url, headers={"User-Agent": "FestivalWorld/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
        for page in data.get("query", {}).get("search", []):
            title = urllib.parse.quote(page["title"])
            img_url = f"https://en.wikipedia.org/w/api.php?action=query&titles={title}&prop=pageimages&format=json&pithumbsize=400"
            req2 = urllib.request.Request(img_url, headers={"User-Agent": "FestivalWorld/1.0"})
            with urllib.request.urlopen(req2, timeout=5) as resp2:
                img_data = json.loads(resp2.read())
            for p in img_data.get("query", {}).get("pages", {}).values():
                src = p.get("thumbnail", {}).get("source", "")
                if src and src not in seen:
                    images.append(src)
                    seen.add(src)
    except Exception:
        pass

    # 2. Try Unsplash source (free, no key for basic usage)
    if len(images) < limit:
        try:
            query = urllib.parse.quote(f"{name} festival")
            url = f"https://source.unsplash.com/400x300/?{query}"
            # Unsplash source redirects, we just collect a few variations
            for term in [name, f"{name} festival", f"{name} music"]:
                u = f"https://source.unsplash.com/400x300/?{urllib.parse.quote(term)}"
                if u not in seen:
                    images.append(u)
                    seen.add(u)
        except Exception:
            pass

    return {"images": images[:limit]}


@router.post("/build-geo")
async def gui_build_geo(
    lat: float = Form(...),
    lng: float = Form(...),
    style: str = Form("electronic festival"),
    world_name: str = Form("festival_world"),
    diameter_km: float = Form(10.0),
    srtm_resolution: str = Form("SRTMGL3"),
    use_llm: bool = Form(False),
    llm_model: str = Form("llama3.1"),
    llm_url: str = Form("http://localhost:11434"),
    festival_name: str = Form(""),
    festival_images: str = Form(""),
):
    """Build a festival world from real-world geo data.
    If festival_name and festival_images are provided, AI vision model
    analyzes the images and generates custom stage designs."""
    settings = Settings(style=style, minecraft_world_name=world_name)
    llm_cfg = LLMConfig(base_url=llm_url, model=llm_model)
    pipeline = FestivalWorldPipeline(settings, use_llm=use_llm, llm_config=llm_cfg)

    try:
        img_list = [u.strip() for u in festival_images.split(",") if u.strip()] if festival_images else []

        result = pipeline.build_from_geo(
            center_lat=lat,
            center_lng=lng,
            diameter_km=diameter_km,
            srtm_resolution=srtm_resolution,
            festival_name=festival_name,
            festival_images=img_list,
        )

        if not result.success:
            raise HTTPException(status_code=500, detail=result.message)

        output_tree = []
        heightmap_b64 = None
        heightmap_size = None
        ai_structures = pipeline.ai_structures if hasattr(pipeline, 'ai_structures') else []
        if result.output_path and result.output_path.exists():
            output_tree = sorted(p.name for p in result.output_path.iterdir() if p.is_file())
            hmap_path = result.output_path / "heightmap.png"
            if hmap_path.exists():
                from PIL import Image as PILImage
                import base64, io as _io
                img = PILImage.open(hmap_path)
                w, h = img.size
                if max(w, h) > 512:
                    scale = 512 / max(w, h)
                    img = img.resize((int(w * scale), int(h * scale)), PILImage.LANCZOS)
                buf = _io.BytesIO()
                img.save(buf, format="PNG")
                heightmap_b64 = base64.b64encode(buf.getvalue()).decode()
                heightmap_size = {"width": img.width, "height": img.height}

        return {
            "success": True,
            "message": result.message,
            "output_path": str(result.output_path),
            "output_tree": output_tree,
            "heightmap_b64": heightmap_b64,
            "heightmap_size": heightmap_size,
            "ai_structures": ai_structures,
        }
    except Exception as e:
        if not isinstance(e, HTTPException):
            raise HTTPException(status_code=500, detail=str(e))
        raise
