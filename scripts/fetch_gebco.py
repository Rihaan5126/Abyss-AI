"""Download GEBCO_2025 around Monterey Bay and write the committed 30x30 terrain crop.

    python -m scripts.fetch_gebco

The box is aligned to GEBCO's 15-arc-second cells so no resampling occurs. The crop is
the all-ocean window with the most varied slope. It is chosen from terrain alone, so
the choice cannot favour any planner. Each run checks sample cells against the
service's point lookup and refuses to write the crop if any disagree.
"""

from __future__ import annotations

import argparse
import json
import math
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image

from abyss.terrain import GEBCO_CITATION, terrain_from_depth

SERVICE = "https://gis.ccom.unh.edu/server/rest/services/GEBCO2025/GEBCO_2025_IS/ImageServer"
CELLS_PER_DEGREE = 240
METRES_PER_DEGREE_LAT = 111_320.0
USER_AGENT = "ABYSS-hackathon-terrain-fetch"
WEST, SOUTH, EAST, NORTH = -122.5, 36.4, -121.75, 37.15
CROP_SIZE = 30
CROP_STEP = 5
N_CHECKS = 8


def _get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def download_box(path: Path) -> np.ndarray:
    query = urllib.parse.urlencode(
        {
            "bbox": f"{WEST},{SOUTH},{EAST},{NORTH}",
            "bboxSR": 4326,
            "imageSR": 4326,
            "size": f"{round((EAST - WEST) * CELLS_PER_DEGREE)},"
            f"{round((NORTH - SOUTH) * CELLS_PER_DEGREE)}",
            "format": "tiff",
            "pixelType": "S16",
            "interpolation": "RSP_NearestNeighbor",
            "f": "image",
        }
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_get(f"{SERVICE}/exportImage?{query}"))
    with Image.open(path) as image:
        return np.array(image).astype(int)


def lookup(lon: float, lat: float) -> int:
    query = urllib.parse.urlencode(
        {
            "geometry": json.dumps({"x": lon, "y": lat, "spatialReference": {"wkid": 4326}}),
            "geometryType": "esriGeometryPoint",
            "returnGeometry": "false",
            "returnCatalogItems": "false",
            "f": "json",
        }
    )
    return int(float(json.loads(_get(f"{SERVICE}/identify?{query}"))["value"]))


def cell_centre(row: int, col: int) -> tuple[float, float]:
    return WEST + (col + 0.5) / CELLS_PER_DEGREE, NORTH - (row + 0.5) / CELLS_PER_DEGREE


def cell_sizes(row_centre: int) -> tuple[float, float]:
    """Return (north-south, east-west) cell size in metres at this row."""
    _, lat = cell_centre(row_centre, 0)
    height = METRES_PER_DEGREE_LAT / CELLS_PER_DEGREE
    return height, height * math.cos(math.radians(lat))


def verify(box: np.ndarray) -> None:
    rng = np.random.default_rng(0)
    rows = rng.integers(box.shape[0], size=N_CHECKS)
    cols = rng.integers(box.shape[1], size=N_CHECKS)
    for row, col in zip(rows.tolist(), cols.tolist()):
        lon, lat = cell_centre(row, col)
        expected = lookup(lon, lat)
        if expected != box[row, col]:
            raise RuntimeError(
                f"Cell ({row}, {col}) at {lon:.5f}, {lat:.5f}: "
                f"file has {box[row, col]}, service has {expected}"
            )
    print(f"Checked {N_CHECKS} cells against the point lookup: all match")


def select_crop(box: np.ndarray) -> tuple[int, int]:
    best, best_score = None, -1.0
    for row in range(0, box.shape[0] - CROP_SIZE + 1, CROP_STEP):
        for col in range(0, box.shape[1] - CROP_SIZE + 1, CROP_STEP):
            window = box[row : row + CROP_SIZE, col : col + CROP_SIZE]
            if (window >= 0).any():
                continue
            height, width = cell_sizes(row + CROP_SIZE // 2)
            score = terrain_from_depth(-window, height, "gebco", width).slope_deg.std()
            if score > best_score:
                best, best_score = (row, col), float(score)
    if best is None:
        raise RuntimeError("No all-ocean window in the box")
    return best


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--raw", type=Path, default=Path("data/raw/gebco_2025_monterey.tif"))
    parser.add_argument("--out", type=Path, default=Path("data/gebco/monterey_canyon_30x30.json"))
    args = parser.parse_args()

    box = download_box(args.raw)
    verify(box)
    row, col = select_crop(box)
    crop = box[row : row + CROP_SIZE, col : col + CROP_SIZE]
    height, width = cell_sizes(row + CROP_SIZE // 2)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(
            {
                "dataset": "GEBCO_2025 Grid",
                "citation": GEBCO_CITATION,
                "served_by": SERVICE,
                "selection": "All-ocean 30x30 window with the highest slope std, terrain only",
                "units": "metres, negative below sea level",
                "row_order": "north to south",
                "west": WEST + col / CELLS_PER_DEGREE,
                "north": NORTH - row / CELLS_PER_DEGREE,
                "cells_per_degree": CELLS_PER_DEGREE,
                "cell_height_m": round(height, 1),
                "cell_width_m": round(width, 1),
                "elevation_m": crop.tolist(),
            }
        ),
        encoding="utf-8",
    )
    print(f"Crop at box cell ({row}, {col}), depth {-crop.max()} to {-crop.min()} m: {args.out}")


if __name__ == "__main__":
    main()
