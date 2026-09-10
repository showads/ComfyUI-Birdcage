from __future__ import annotations

import numpy as np
import torch
from PIL import Image

from .image_utils import process_mask
from .session_store import SessionStore


def pil_to_image_tensor(image: Image.Image) -> torch.Tensor:
    arr = np.asarray(image.convert("RGB"), dtype=np.float32) / 255.0
    return torch.from_numpy(arr)[None, ...]


def pil_to_mask_tensor(mask: Image.Image) -> torch.Tensor:
    arr = np.asarray(mask.convert("L"), dtype=np.float32) / 255.0
    return torch.from_numpy(arr)[None, ...]


def tensor_to_pil(image: torch.Tensor) -> Image.Image:
    arr = image[0].detach().cpu().numpy()
    arr = np.clip(arr * 255.0, 0, 255).astype(np.uint8)
    return Image.fromarray(arr, mode="RGB")


def mask_tensor_to_pil(mask: torch.Tensor) -> Image.Image:
    arr = mask[0].detach().cpu().numpy()
    arr = np.clip(arr * 255.0, 0, 255).astype(np.uint8)
    return Image.fromarray(arr, mode="L")


class BirdCageSceneLayers:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"source": ("IMAGE",), "revealed": ("IMAGE",), "cloth_mask": ("MASK",), "mask_expand": ("INT", {"default": 8, "min": -64, "max": 128, "step": 1}), "mask_feather": ("FLOAT", {"default": 2.0, "min": 0.0, "max": 64.0, "step": 0.25})}}

    RETURN_TYPES = ("IMAGE", "IMAGE", "MASK")
    RETURN_NAMES = ("revealed_plate", "cloth_rgb", "cloth_mask")
    FUNCTION = "build"
    CATEGORY = "Bird Cage"

    def build(self, source, revealed, cloth_mask, mask_expand=8, mask_feather=2.0):
        src = tensor_to_pil(source)
        rev = tensor_to_pil(revealed).resize(src.size, Image.Resampling.LANCZOS)
        mask = process_mask(mask_tensor_to_pil(cloth_mask), src.size, expand=mask_expand, feather=mask_feather)
        plate = Image.composite(rev, src, mask)
        return (pil_to_image_tensor(plate), pil_to_image_tensor(src), pil_to_mask_tensor(mask))


class BirdCageSessionLoader:
    @classmethod
    def INPUT_TYPES(cls):
        store = SessionStore()
        sessions = [s["id"] for s in store.list()] or ["(no sessions yet)"]
        return {"required": {"session_id": (sessions,)}}

    RETURN_TYPES = ("IMAGE", "IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("revealed_plate", "cloth_rgb", "cloth_mask", "scene_json")
    FUNCTION = "load"
    CATEGORY = "Bird Cage"

    @classmethod
    def IS_CHANGED(cls, session_id):
        try:
            p = SessionStore().path(session_id) / "scene.json"
            return p.stat().st_mtime_ns
        except Exception:
            return float("nan")

    def load(self, session_id):
        if session_id == "(no sessions yet)":
            raise RuntimeError("Create a Bird Cage session at /bird-cage/ first")
        path = SessionStore().path(session_id)
        plate = Image.open(path / "plate.png").convert("RGB")
        source = Image.open(path / "source.png").convert("RGB")
        mask = Image.open(path / "cloth_mask.png").convert("L")
        scene = (path / "scene.json").read_text(encoding="utf-8")
        return (pil_to_image_tensor(plate), pil_to_image_tensor(source), pil_to_mask_tensor(mask), scene)


NODE_CLASS_MAPPINGS = {"BirdCageSceneLayers": BirdCageSceneLayers, "BirdCageSessionLoader": BirdCageSessionLoader}
NODE_DISPLAY_NAME_MAPPINGS = {"BirdCageSceneLayers": "Bird Cage: Build Scene Layers", "BirdCageSessionLoader": "Bird Cage: Load Session"}
