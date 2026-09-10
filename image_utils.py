from __future__ import annotations

import base64
import io
import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageFilter


def open_rgb(path: str | Path) -> Image.Image:
    return Image.open(path).convert("RGB")


def open_mask(path: str | Path) -> Image.Image:
    image = Image.open(path)
    if "A" in image.getbands():
        image = image.getchannel("A")
    else:
        image = image.convert("L")
    return image


def save_data_url(data_url: str, path: str | Path) -> Path:
    if "," not in data_url:
        raise ValueError("Expected a data URL")
    _, encoded = data_url.split(",", 1)
    raw = base64.b64decode(encoded)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(io.BytesIO(raw)) as im:
        im.save(path, "PNG")
    return path


def image_to_data_url(path: str | Path) -> str:
    raw = Path(path).read_bytes()
    return "data:image/png;base64," + base64.b64encode(raw).decode("ascii")


def process_mask(mask: Image.Image, size: tuple[int, int], expand: int = 8, feather: float = 2.0, invert: bool = False) -> Image.Image:
    mask = mask.convert("L").resize(size, Image.Resampling.LANCZOS)
    arr = np.asarray(mask, dtype=np.uint8)
    if arr.max() > 0:
        arr = np.where(arr >= 128, 255, 0).astype(np.uint8)
    mask = Image.fromarray(arr, mode="L")
    if invert:
        mask = Image.fromarray(255 - np.asarray(mask, dtype=np.uint8), mode="L")
    if expand > 0:
        kernel = max(3, expand * 2 + 1)
        if kernel % 2 == 0:
            kernel += 1
        mask = mask.filter(ImageFilter.MaxFilter(kernel))
    elif expand < 0:
        kernel = max(3, abs(expand) * 2 + 1)
        if kernel % 2 == 0:
            kernel += 1
        inv = Image.fromarray(255 - np.asarray(mask, dtype=np.uint8), mode="L")
        inv = inv.filter(ImageFilter.MaxFilter(kernel))
        mask = Image.fromarray(255 - np.asarray(inv, dtype=np.uint8), mode="L")
    if feather > 0:
        mask = mask.filter(ImageFilter.GaussianBlur(radius=float(feather)))
    return mask


def alpha_bbox(mask: Image.Image, padding: int = 4) -> tuple[int, int, int, int]:
    bbox = mask.getbbox()
    if not bbox:
        raise ValueError("Mask is empty")
    left, top, right, bottom = bbox
    left = max(0, left - padding)
    top = max(0, top - padding)
    right = min(mask.width, right + padding)
    bottom = min(mask.height, bottom + padding)
    return left, top, right, bottom


def build_scene_assets(source_path: str | Path, revealed_path: str | Path, mask_path: str | Path, out_dir: str | Path, *, expand: int = 8, feather: float = 2.0, invert_mask: bool = False, crop_padding: int = 6) -> dict[str, Any]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    source = open_rgb(source_path)
    revealed = open_rgb(revealed_path).resize(source.size, Image.Resampling.LANCZOS)
    raw_mask = open_mask(mask_path)
    mask = process_mask(raw_mask, source.size, expand=expand, feather=feather, invert=invert_mask)
    plate = Image.composite(revealed, source, mask)
    plate_path = out_dir / "plate.png"
    plate.save(plate_path)
    mask_path_out = out_dir / "cloth_mask.png"
    mask.save(mask_path_out)
    cloth_rgba = source.convert("RGBA")
    cloth_rgba.putalpha(mask)
    cloth_rgba.save(out_dir / "cloth_full.png")
    bbox = alpha_bbox(mask, padding=crop_padding)
    cloth_crop = cloth_rgba.crop(bbox)
    cloth_crop.save(out_dir / "cloth.png")
    metadata = {
        "version": 1,
        "width": source.width,
        "height": source.height,
        "cloth_bbox": {"x": bbox[0], "y": bbox[1], "width": bbox[2] - bbox[0], "height": bbox[3] - bbox[1]},
        "mesh": {"cols": 16, "rows": 16, "constraint_iterations": 5, "damping": 0.985},
        "assets": {"plate": "plate.png", "cloth": "cloth.png", "mask": "cloth_mask.png", "source": "source.png", "revealed": "revealed.png"},
    }
    (out_dir / "scene.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata
