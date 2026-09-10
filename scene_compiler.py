from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any, Callable

from PIL import Image

from .comfy_runner import ComfyRunner
from .image_utils import build_scene_assets, save_data_url
from .session_store import SessionStore
from .workflow_manager import WorkflowManager

Progress = Callable[[str, str], None]


class SceneCompiler:
    def __init__(self, sessions: SessionStore, workflows: WorkflowManager):
        self.sessions = sessions
        self.workflows = workflows
        self.runner = ComfyRunner()

    def _comfy_input_name(self, session_id: str, local_path: Path, role: str) -> str:
        import folder_paths

        sub = Path("bird-cage") / session_id
        dest_dir = Path(folder_paths.get_input_directory()) / sub
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{role}.png"
        with Image.open(local_path) as image:
            image.save(dest, "PNG")
        return (sub / dest.name).as_posix()

    async def _run_stage(self, stage: str, profile_name: str, values: dict[str, Any]) -> tuple[Path, str]:
        profile = self.workflows.load_profile(stage, profile_name)
        prompt = self.workflows.apply(profile, values)
        result = await self.runner.run(prompt, output_node=profile.get("output_node"))
        if not result["image"]:
            raise RuntimeError(f"{stage}/{profile_name} completed but did not expose an image output. Set the profile output node to a PreviewImage/SaveImage-style node.")
        return self.runner.image_ref_path(result["image"]), result["prompt_id"]

    async def compile(self, session_id: str, settings: dict[str, Any], progress: Progress | None = None) -> dict[str, Any]:
        progress = progress or (lambda *_: None)
        session = self.sessions.path(session_id)
        source = session / "source.png"
        if not source.exists():
            raise FileNotFoundError("Upload a source image first")

        self.sessions.write_meta(session_id, {"status": "compiling", "compile_started": time.time()})
        prompt_ids: dict[str, str] = {}
        source_input = self._comfy_input_name(session_id, source, "source")

        mask = session / "manual_mask.png"
        segment_profile = settings.get("segment_profile")
        if segment_profile:
            progress("segment", "Detecting and segmenting the draggable cloth")
            values = self._generation_values(settings.get("segment", {}), source_image=source_input)
            values["detector_prompt"] = settings.get("detector_prompt", values.get("prompt", "cloth sheet covering the object"))
            values["prompt"] = settings.get("detector_prompt", values.get("prompt", "cloth sheet covering the object"))
            values["box_threshold"] = float(settings.get("box_threshold", 0.30))
            values["text_threshold"] = float(settings.get("text_threshold", 0.25))
            result_path, pid = await self._run_stage("segment", segment_profile, values)
            shutil.copy2(result_path, mask)
            prompt_ids["segment"] = pid
        elif not mask.exists():
            raise RuntimeError("No segmentation workflow is selected and no manual cloth mask has been uploaded/drawn.")

        revealed = session / "revealed.png"
        reveal_profile = settings.get("reveal_profile")
        if reveal_profile:
            progress("reveal", "Generating the hidden/revealed state")
            mask_input = self._comfy_input_name(session_id, mask, "mask")
            values = self._generation_values(settings.get("reveal", {}), source_image=source_input, mask_image=mask_input)
            values["prompt"] = settings.get("reveal_prompt", values.get("prompt", "Reveal what is underneath while preserving everything else."))
            values["negative_prompt"] = settings.get("negative_prompt", values.get("negative_prompt", ""))
            result_path, pid = await self._run_stage("reveal", reveal_profile, values)
            shutil.copy2(result_path, revealed)
            prompt_ids["reveal"] = pid
        elif not revealed.exists():
            raise RuntimeError("No reveal workflow is selected and no revealed-state image has been uploaded.")

        cleanup_profile = settings.get("cleanup_profile")
        if cleanup_profile:
            progress("cleanup", "Cleaning the revealed plate")
            revealed_input = self._comfy_input_name(session_id, revealed, "revealed-pre-cleanup")
            mask_input = self._comfy_input_name(session_id, mask, "mask-cleanup")
            values = self._generation_values(settings.get("cleanup", {}), source_image=revealed_input, mask_image=mask_input, reference_image=source_input)
            values["prompt"] = settings.get("cleanup_prompt", "Preserve the composition and repair the revealed region with consistent lighting and geometry.")
            result_path, pid = await self._run_stage("cleanup", cleanup_profile, values)
            shutil.copy2(result_path, revealed)
            prompt_ids["cleanup"] = pid

        progress("layers", "Building the interactive scene layers")
        metadata = build_scene_assets(
            session / "source.png",
            session / "revealed.png",
            mask,
            session,
            expand=int(settings.get("mask_expand", 8)),
            feather=float(settings.get("mask_feather", 2.0)),
            invert_mask=bool(settings.get("invert_mask", False)),
        )
        metadata["session_id"] = session_id
        metadata["refine"] = {"enabled": bool(settings.get("refine_enabled", True)), "debounce_ms": int(settings.get("refine_debounce_ms", 450))}
        (session / "scene.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        meta = self.sessions.write_meta(session_id, {"status": "ready", "compile_finished": time.time(), "prompt_ids": prompt_ids, "scene": metadata})
        return {"session": meta, "scene": metadata}

    async def refine(self, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        session = self.sessions.path(session_id)
        profile_name = payload.get("profile")
        if not profile_name:
            raise ValueError("Choose a refine workflow profile")
        composite = save_data_url(payload["composite_data_url"], session / "refine_input.png")
        mask = save_data_url(payload["mask_data_url"], session / "refine_mask.png")
        composite_input = self._comfy_input_name(session_id, composite, "refine-input")
        mask_input = self._comfy_input_name(session_id, mask, "refine-mask")
        plate_input = self._comfy_input_name(session_id, session / "plate.png", "refine-reference")

        values = self._generation_values(payload.get("settings", {}), source_image=composite_input, mask_image=mask_input, reference_image=plate_input)
        values["prompt"] = payload.get("prompt", "Preserve the scene. Make the moved fabric, folds, occlusion, shadows, and revealed region physically realistic without changing unrelated areas.")
        values["negative_prompt"] = payload.get("negative_prompt", "")
        output_path, prompt_id = await self._run_stage("refine", profile_name, values)
        target = session / f"refined-{prompt_id[:8]}.png"
        from PIL import ImageFilter
        base = Image.open(composite).convert("RGB")
        refined = Image.open(output_path).convert("RGB").resize(base.size, Image.Resampling.LANCZOS)
        refine_mask = Image.open(mask).convert("L").resize(base.size, Image.Resampling.LANCZOS).filter(ImageFilter.GaussianBlur(radius=6.0))
        Image.composite(refined, base, refine_mask).save(target, "PNG")
        return {"prompt_id": prompt_id, "asset": target.name}

    @staticmethod
    def _generation_values(settings: dict[str, Any], **overrides: Any) -> dict[str, Any]:
        values = {
            "steps": settings.get("steps", 4), "cfg": settings.get("cfg", 1.0), "guidance": settings.get("guidance", settings.get("cfg", 1.0)),
            "sampler": settings.get("sampler", "euler"), "scheduler": settings.get("scheduler", "simple"), "seed": settings.get("seed", 42),
            "denoise": settings.get("denoise", 1.0), "checkpoint": settings.get("checkpoint", ""), "diffusion_model": settings.get("diffusion_model", ""),
            "vae": settings.get("vae", ""), "text_encoder": settings.get("text_encoder", ""), "negative_prompt": settings.get("negative_prompt", ""),
        }
        for i, lora in enumerate(settings.get("loras", [])[:4], start=1):
            values[f"lora_{i}_name"] = lora.get("name", "")
            values[f"lora_{i}_strength_model"] = lora.get("strength_model", lora.get("strength", 1.0))
            values[f"lora_{i}_strength_clip"] = lora.get("strength_clip", lora.get("strength", 1.0))
        values.update(overrides)
        values["extra"] = settings.get("extra", {})
        return values
