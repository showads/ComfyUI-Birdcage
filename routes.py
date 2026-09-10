from __future__ import annotations

import json
import traceback
from pathlib import Path
from typing import Any

from aiohttp import web

from .config import WEB_DIR, data_dir, presets_dir
from .scene_compiler import SceneCompiler
from .session_store import SessionStore
from .workflow_manager import SEMANTIC_FIELDS, WorkflowManager

try:
    import folder_paths
    import comfy.samplers
    from server import PromptServer
except Exception as exc:
    raise RuntimeError("Bird Cage routes must be imported inside ComfyUI") from exc

routes = PromptServer.instance.routes
sessions = SessionStore()
workflows = WorkflowManager()
compiler = SceneCompiler(sessions, workflows)


def _json_error(exc: Exception, status: int = 400) -> web.Response:
    return web.json_response({"ok": False, "error": str(exc), "type": exc.__class__.__name__}, status=status)


def _asset_url(session_id: str, name: str) -> str:
    return f"/bird-cage/api/session/{session_id}/asset/{name}"


def _scene_payload(session_id: str) -> dict[str, Any]:
    meta = sessions.read_meta(session_id)
    scene_path = sessions.path(session_id) / "scene.json"
    scene = json.loads(scene_path.read_text(encoding="utf-8")) if scene_path.exists() else None
    if scene:
        assets = dict(scene.get("assets", {}))
        scene["asset_urls"] = {key: _asset_url(session_id, filename) for key, filename in assets.items() if (sessions.path(session_id) / filename).exists()}
    return {"session": meta, "scene": scene}


def _model_lists() -> dict[str, Any]:
    def names(category: str) -> list[str]:
        try: return folder_paths.get_filename_list(category)
        except Exception: return []
    samplers, schedulers = [], []
    try: samplers = list(comfy.samplers.KSampler.SAMPLERS)
    except Exception:
        try: samplers = list(comfy.samplers.SAMPLER_NAMES)
        except Exception: pass
    try: schedulers = list(comfy.samplers.KSampler.SCHEDULERS)
    except Exception:
        try: schedulers = list(comfy.samplers.SCHEDULER_NAMES)
        except Exception: pass
    return {"checkpoints": names("checkpoints"), "diffusion_models": names("diffusion_models") or names("unet"), "loras": names("loras"), "vae": names("vae"), "text_encoders": names("text_encoders") or names("clip"), "samplers": samplers, "schedulers": schedulers}


@routes.get("/bird-cage")
async def bird_cage_redirect(request): raise web.HTTPFound("/bird-cage/")

@routes.get("/bird-cage/")
async def bird_cage_index(request): return web.FileResponse(WEB_DIR / "index.html")

@routes.get("/bird-cage/assets/{name:.*}")
async def bird_cage_static(request):
    raw = request.match_info["name"]
    target = (WEB_DIR / raw).resolve()
    if WEB_DIR.resolve() not in target.parents or not target.exists() or not target.is_file(): raise web.HTTPNotFound()
    return web.FileResponse(target)

@routes.get("/bird-cage/api/config")
async def api_config(request):
    return web.json_response({"ok": True, "version": "0.1.0", "semantic_fields": SEMANTIC_FIELDS, "profiles": workflows.list_profiles(), "models": _model_lists(), "data_dir": str(data_dir()), "defaults": {"detector_prompt": "cloth sheet covering the object", "reveal_prompt": "Preserve the exact camera angle, lighting, background, table, and composition. Remove the cloth covering the object and reveal what is underneath. Keep unrelated areas unchanged.", "cleanup_prompt": "Preserve the composition and repair the revealed region with natural geometry, edges, shadows, and lighting.", "refine_prompt": "Preserve the scene and composition. Make the displaced fabric, folds, occlusion, contact shadows, and newly revealed area physically realistic. Do not change unrelated areas."}})

@routes.get("/bird-cage/api/sessions")
async def api_sessions(request): return web.json_response({"ok": True, "sessions": sessions.list()})

@routes.post("/bird-cage/api/session")
async def api_create_session(request):
    try:
        payload = await request.json(); meta = sessions.create(payload.get("name")); return web.json_response({"ok": True, "session": meta})
    except Exception as exc: return _json_error(exc)

@routes.get("/bird-cage/api/session/{session_id}")
async def api_get_session(request):
    try: return web.json_response({"ok": True, **_scene_payload(request.match_info["session_id"])})
    except FileNotFoundError as exc: return _json_error(exc, 404)
    except Exception as exc: return _json_error(exc)

@routes.get("/bird-cage/api/session/{session_id}/asset/{name}")
async def api_session_asset(request):
    try: return web.FileResponse(sessions.asset(request.match_info["session_id"], request.match_info["name"]))
    except FileNotFoundError: raise web.HTTPNotFound()
    except Exception as exc: return _json_error(exc)

@routes.post("/bird-cage/api/session/{session_id}/upload")
async def api_upload(request):
    try:
        session_id = request.match_info["session_id"]
        reader = await request.multipart(); role = None; incoming = None
        while True:
            field = await reader.next()
            if field is None: break
            if field.name == "role": role = (await field.text()).strip()
            elif field.name == "file": incoming = field; break
        if role not in {"source", "revealed", "manual_mask"}: raise ValueError("role must be source, revealed, or manual_mask")
        if incoming is None: raise ValueError("Missing file")
        session = sessions.path(session_id); temp = session / f".{role}-upload"
        with temp.open("wb") as f:
            while chunk := await incoming.read_chunk(): f.write(chunk)
        from PIL import Image
        with Image.open(temp) as image:
            if role == "manual_mask":
                image = image.getchannel("A") if "A" in image.getbands() else image.convert("L"); image.save(session / "manual_mask.png", "PNG")
            else: image.convert("RGB").save(session / f"{role}.png", "PNG")
        temp.unlink(missing_ok=True); sessions.write_meta(session_id, {"status": "uploaded"})
        return web.json_response({"ok": True, **_scene_payload(session_id)})
    except FileNotFoundError as exc: return _json_error(exc, 404)
    except Exception as exc: return _json_error(exc)

@routes.post("/bird-cage/api/session/{session_id}/manual-mask")
async def api_manual_mask(request):
    try:
        session_id = request.match_info["session_id"]; payload = await request.json()
        from .image_utils import save_data_url
        save_data_url(payload["data_url"], sessions.path(session_id) / "manual_mask.png")
        return web.json_response({"ok": True})
    except Exception as exc: return _json_error(exc)

@routes.post("/bird-cage/api/session/{session_id}/compile")
async def api_compile(request):
    try:
        payload = await request.json(); result = await compiler.compile(request.match_info["session_id"], payload)
        return web.json_response({"ok": True, **result, **_scene_payload(request.match_info["session_id"])})
    except FileNotFoundError as exc: return _json_error(exc, 404)
    except Exception as exc:
        traceback.print_exc(); sessions.write_meta(request.match_info["session_id"], {"status": "error", "error": str(exc)}); return _json_error(exc, 500)

@routes.post("/bird-cage/api/session/{session_id}/refine")
async def api_refine(request):
    try:
        payload = await request.json(); result = await compiler.refine(request.match_info["session_id"], payload)
        result["asset_url"] = _asset_url(request.match_info["session_id"], result["asset"])
        return web.json_response({"ok": True, **result})
    except Exception as exc: traceback.print_exc(); return _json_error(exc, 500)

@routes.get("/bird-cage/api/workflows")
async def api_workflow_list(request): return web.json_response({"ok": True, "profiles": workflows.list_profiles()})

@routes.post("/bird-cage/api/workflows/inspect")
async def api_workflow_inspect(request):
    try:
        payload = await request.json(); workflow = payload.get("workflow", payload); return web.json_response({"ok": True, "nodes": workflows.inspect_workflow(workflow)})
    except Exception as exc: return _json_error(exc)

@routes.post("/bird-cage/api/workflows")
async def api_workflow_save(request):
    try:
        payload = await request.json(); profile = workflows.save_profile(stage=payload["stage"], name=payload["name"], workflow=payload["workflow"], bindings=payload.get("bindings", {}), output_node=payload.get("output_node"), description=payload.get("description", ""))
        return web.json_response({"ok": True, "profile": profile, "profiles": workflows.list_profiles()})
    except Exception as exc: return _json_error(exc)

@routes.delete("/bird-cage/api/workflows/{stage}/{name}")
async def api_workflow_delete(request):
    try: workflows.delete_profile(request.match_info["stage"], request.match_info["name"]); return web.json_response({"ok": True, "profiles": workflows.list_profiles()})
    except Exception as exc: return _json_error(exc)

@routes.get("/bird-cage/api/presets")
async def api_presets(request):
    rows=[]; root=presets_dir()
    for p in sorted(root.glob("*.json")):
        try: rows.append({"name":p.stem,"data":json.loads(p.read_text(encoding="utf-8"))})
        except Exception: continue
    return web.json_response({"ok": True, "presets": rows})

@routes.post("/bird-cage/api/presets/{name}")
async def api_save_preset(request):
    try:
        name=Path(request.match_info["name"]).name
        if not name or name in {".",".."}: raise ValueError("Invalid preset name")
        payload=await request.json(); path=presets_dir()/f"{name}.json"; path.write_text(json.dumps(payload,indent=2),encoding="utf-8")
        return web.json_response({"ok":True,"name":name})
    except Exception as exc: return _json_error(exc)
