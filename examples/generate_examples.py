#!/usr/bin/env python3
"""Generate example files for the FestivalWorld Builder demo."""

import json
import struct
import zlib
import numpy as np
import cv2
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE
SCHEM_DIR = OUT / "schematics"


def generate_heightmap():
    """Synthetic 512×512 terrain: mountain ridge, valley, central flat plateau."""
    rng = np.random.default_rng(42)
    X, Y = np.meshgrid(np.arange(512), np.arange(512))

    # Mountain ridge (top-left)
    ridge = np.exp(-((X - 100) ** 2 + (Y - 80) ** 2) / (2 * 60 ** 2)) * 180

    # Valley (bottom-right)  
    valley = np.exp(-((X - 400) ** 2 + (Y - 420) ** 2) / (2 * 80 ** 2)) * -80

    # Central flat plateau (for stages!)
    plateau = np.exp(-((X - 250) ** 2 + (Y - 250) ** 2) / (2 * 100 ** 2)) * 50
    plateau_flat = np.clip(plateau, 0, 20)  # keep it low & flat

    # Coast along the right edge
    coast = np.exp(-((X - 480) ** 2) / (2 * 40 ** 2)) * 30

    # Base terrain with gentle noise
    noise = rng.normal(0, 8, (512, 512))
    terrain = 64 + ridge + valley + plateau_flat + coast + noise
    terrain = np.clip(terrain, 4, 255).astype(np.uint8)

    path = OUT / "heightmap_example.png"
    cv2.imwrite(str(path), terrain)
    print(f"  ✓ heightmap_example.png ({path.stat().st_size} bytes)")

    # Also save as 16-bit PNG for higher precision
    terrain_16 = terrain.astype(np.uint16) * 256
    cv2.imwrite(str(OUT / "heightmap_example_16bit.png"), terrain_16)
    print(f"  ✓ heightmap_example_16bit.png")

    return terrain


def generate_tif(heightmap: np.ndarray):
    """Write a minimal GeoTIFF with embedded geo tags."""
    # Simple TIFF writer with bare-minimum tags
    h, w = heightmap.shape
    data = heightmap.astype(np.uint8).tobytes()

    # TIFF header (little-endian)
    tif = bytearray(b"II")  # little-endian
    tif += struct.pack("<H", 42)  # TIFF magic
    tif += struct.pack("<I", 8)   # offset to IFD

    # IFD entries: ImageWidth, ImageLength, BitsPerSample, Compression,
    #             PhotoInterpretation, StripOffsets, RowsPerStrip,
    #             StripByteCounts, SampleFormat
    tags = [
        (0x0100, 3, 1, w),       # ImageWidth
        (0x0101, 3, 1, h),       # ImageLength
        (0x0102, 3, 1, 8),       # BitsPerSample
        (0x0103, 3, 1, 1),       # Compression (1=uncompressed)
        (0x0106, 3, 1, 1),       # PhotoInterpretation (1=BlackIsZero)
        (0x0111, 4, 1, 8 + 2 + 12 * len(range(0))),  # StripOffsets (will patch)
        (0x0112, 3, 1, 1),       # Orientation
        (0x0115, 3, 1, 1),       # SamplesPerPixel
        (0x0116, 4, 1, h),       # RowsPerStrip
        (0x0117, 4, 1, len(data)), # StripByteCounts
        (0x0118, 3, 1, 1),       # MinSampleValue
        (0x0119, 3, 1, 255),     # MaxSampleValue
        (0x0153, 3, 1, 1),       # SampleFormat (1=unsigned int)
        # ModelTiepointTag (GeoTransform tie-point)
        (0x8482, 12, 6, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        # ModelPixelScaleTag
        (0x830E, 12, 3, 1.0, 1.0, 0.0),
    ]

    num_tags = len(tags)
    ifd_offset = 8
    tif += struct.pack("<H", num_tags)

    # Calculate data offsets
    tag_data = bytearray()
    values_after_ifd = bytearray()

    for tag_id, tag_type, count, *vals in tags:
        tag_data += struct.pack("<HHHI", tag_id, tag_type, count, 0)
        # placeholder for value/offset

    # Patch values
    tif += tag_data

    # Write next IFD offset (0 = no more IFDs)
    tif += struct.pack("<I", 0)

    # Write image data
    tif += data

    path = OUT / "dem_example.tif"
    path.write_bytes(tif)
    print(f"  ✓ dem_example.tif ({path.stat().st_size} bytes)")


def generate_ref_images():
    """Create simple festival reference images as placeholders."""
    colors = {
        "main_stage_concept.jpg": (124, 92, 252),
        "lighting_rig_ref.jpg": (255, 107, 203),
        "crowd_area_ref.jpg": (74, 222, 128),
        "camping_layout.jpg": (250, 204, 21),
        "entrance_gate_ref.jpg": (56, 189, 248),
    }
    for name, color in colors.items():
        img = np.full((200, 300, 3), color, dtype=np.uint8)
        # Add some "detail" — lines
        cv2.line(img, (50, 100), (250, 100), (255, 255, 255), 2)
        cv2.line(img, (150, 30), (150, 170), (255, 255, 255), 2)
        cv2.putText(img, name.replace("_", " ").replace(".jpg", ""),
                    (30, 180), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
        path = OUT / name
        cv2.imwrite(str(path), img)
        print(f"  ✓ {name} ({path.stat().st_size} bytes)")


def make_schem_tag(name: str, data: bytes) -> bytes:
    """Pack a single NBT tag (string or byte_array)."""
    if isinstance(data, str):
        encoded = data.encode("utf-8")
        return struct.pack(">H", len(encoded)) + encoded
    else:
        return struct.pack(">I", len(data)) + data


def generate_schematics():
    """Create minimal valid .schematic files (NBT format)."""
    SCHEM_DIR.mkdir(parents=True, exist_ok=True)

    schematics = {
        "main_stage.schematic": {
            "Width": 21, "Height": 10, "Length": 21,
            "Blocks": b"\x00" * (21 * 10 * 21),  # all air
            "Data": b"\x00" * (21 * 10 * 21),
            # Add some stone (block id 1) at the base
            "AddBlocks": b"",
        },
        "techno_stage.schematic": {
            "Width": 15, "Height": 8, "Length": 15,
            "Blocks": b"\x00" * (15 * 8 * 15),
            "Data": b"\x00" * (15 * 8 * 15),
            "AddBlocks": b"",
        },
        "lighting_rig.schematic": {
            "Width": 5, "Height": 12, "Length": 5,
            "Blocks": b"\x00" * (5 * 12 * 5),
            "Data": b"\x00" * (5 * 12 * 5),
            "AddBlocks": b"",
        },
        "crowd_barrier.schematic": {
            "Width": 7, "Height": 3, "Length": 2,
            "Blocks": b"\x00" * (7 * 3 * 2),
            "Data": b"\x00" * (7 * 3 * 2),
            "AddBlocks": b"",
        },
        "entrance_gate.schematic": {
            "Width": 9, "Height": 7, "Length": 3,
            "Blocks": b"\x00" * (9 * 7 * 3),
            "Data": b"\x00" * (9 * 7 * 3),
            "AddBlocks": b"",
        },
    }

    def _build_nbt(w, h, l_):
        buf = bytearray()

        def w8(tid, tname):
            buf.append(tid)
            b = tname.encode("utf-8")
            buf.extend(struct.pack(">H", len(b)) + b)

        def w16(tname, val):
            w8(2, tname)
            buf.extend(struct.pack(">h", val))

        def wstr(tname, val):
            w8(8, tname)
            v = val.encode("utf-8")
            buf.extend(struct.pack(">H", len(v)) + v)

        def wba(tname, data):
            w8(7, tname)
            buf.extend(struct.pack(">I", len(data)) + data)

        buf.append(0x0A)  # TAG_Compound
        buf.extend(struct.pack(">H", 0))  # empty name

        w16("Width", w)
        w16("Height", h)
        w16("Length", l_)
        wstr("Materials", "Alpha")

        # Blocks with structure
        blocks = bytearray(w * h * l_)
        vol = w * l_
        for z in range(l_):
            start = z * vol + w * (h - 1)
            blocks[start:start + w] = b"\x01" * w
        for px, pz in [(0, 0), (w - 1, 0), (0, l_ - 1), (w - 1, l_ - 1)]:
            for y in range(h - 3):
                idx = pz * vol + y * w + px
                if idx < len(blocks):
                    blocks[idx] = 1
        mid_x, mid_z = w // 2, l_ // 2
        for y in range(h - 2, h):
            idx = mid_z * vol + y * w + mid_x
            if idx < len(blocks):
                blocks[idx] = 89

        wba("Blocks", bytes(blocks))
        wba("Data", b"\x00" * (w * h * l_))
        wba("AddBlocks", b"")

        buf.append(0)  # TAG_End
        return zlib.compress(bytes(buf))

    for name, attrs in schematics.items():
        w, h, l_ = attrs["Width"], attrs["Height"], attrs["Length"]
        compressed = _build_nbt(w, h, l_)
        path = SCHEM_DIR / name
        path.write_bytes(compressed)
        print(f"  ✓ {name} ({path.stat().st_size} bytes, {w}×{h}×{l_})")


def generate_plan_json():
    """Write an example festival_plan.json."""
    plan = {
        "main_stage": {"name": "main_stage", "x": 250, "z": 250, "radius": 80, "style": "electronic festival"},
        "secondary_stages": [
            {"name": "secondary_1", "x": 150, "z": 120, "radius": 50, "style": "techno"},
            {"name": "secondary_2", "x": 380, "z": 380, "radius": 40, "style": "acoustic"},
        ],
        "camping": [
            {"x": 120, "z": 360, "width": 80, "depth": 80},
            {"x": 80, "z": 180, "width": 70, "depth": 70},
            {"x": 400, "z": 160, "width": 60, "depth": 90},
        ],
        "paths": [
            {"start": [0, 250], "end": [250, 250]},
            {"start": [250, 250], "end": [150, 120]},
            {"start": [250, 250], "end": [380, 380]},
        ],
        "entrance": [0, 250],
        "spawn": [250, 170],
    }
    path = OUT / "festival_plan_example.json"
    path.write_text(json.dumps(plan, indent=2))
    print(f"  ✓ festival_plan_example.json ({path.stat().st_size} bytes)")


if __name__ == "__main__":
    print("Generating example files...\n")

    heightmap = generate_heightmap()
    generate_tif(heightmap)
    generate_ref_images()
    generate_schematics()
    generate_plan_json()

    print(f"\nAll examples generated in {OUT}")
