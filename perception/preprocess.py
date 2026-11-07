"""Strict annotation cropping and the DINOv2 RGB preprocessing recipe."""

import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps


def load_rgb(image: str | Path | Image.Image) -> Image.Image:
    if isinstance(image, Image.Image):
        return ImageOps.exif_transpose(image).convert("RGB")
    with Image.open(image) as opened:
        return ImageOps.exif_transpose(opened).convert("RGB")


def crop_organism(image: Image.Image, bbox: dict) -> Image.Image:
    """FathomNet uses pixel x/y/width/height. Clip partial boxes, reject empty ones.

    Do not EXIF-rotate before cropping: annotations use original image coordinates.
    """
    x, y, w, h = (float(bbox[k]) for k in ("x", "y", "width", "height"))
    if not all(math.isfinite(v) for v in (x, y, w, h)) or w <= 0 or h <= 0:
        raise ValueError("Bounding box must contain finite coordinates and positive dimensions")
    left, top = max(0, math.floor(x)), max(0, math.floor(y))
    right, bottom = min(image.width, math.ceil(x + w)), min(image.height, math.ceil(y + h))
    if right <= left or bottom <= top:
        raise ValueError("Bounding box does not overlap the image")
    return image.crop((left, top, right, bottom)).convert("RGB")


def dinov2_pixels(image: str | Path | Image.Image) -> np.ndarray:
    image = load_rgb(image)
    # Match facebook/dinov2-small: shortest edge 256, bicubic, centre crop 224.
    w, h = image.size
    size = (256, int(256 * h / w)) if w <= h else (int(256 * w / h), 256)
    image = image.resize(size, Image.Resampling.BICUBIC)
    left, top = (image.width - 224) // 2, (image.height - 224) // 2
    pixels = np.asarray(image.crop((left, top, left + 224, top + 224)), dtype=np.float32) / 255
    pixels = (pixels - np.array([.485, .456, .406], dtype=np.float32)) / np.array(
        [.229, .224, .225], dtype=np.float32
    )
    return pixels.transpose(2, 0, 1).copy()
