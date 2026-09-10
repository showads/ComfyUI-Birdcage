from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

from .config import profiles_dir

VALID_STAGES = {"segment", "reveal", "cleanup", "refine"}
SAFE_NAME = re.compile(r"[^A-Za-z0-9_.-]+")
SEMANTIC_FIELDS = [
    "source_image", "mask_image", "reference_image", "prompt", "negative_prompt",
    "steps", "cfg", "guidance", "sampler", "scheduler", "seed", "denoise",
    "checkpoint", "diffusion_model", "vae", "text_encoder",
    "lora_1_name", "lora_1_strength_model", "lora_1_strength_clip",
    "lora_2_name", "lora_2_strength_model", "lora_2_strength_clip",
    "lora_3_name", "lora_3_strength_model", "lora_3_strength_clip",
    "lora_4_name", "lora_4_strength_model", "lora_4_strength_clip",
    "detector_prompt", "box_threshold", "text_threshold",
]

class WorkflowManager:
    def __init__(self, root: Path | None = None):
        self.root = root or profiles_dir(); self.root.mkdir(parents=True, exist_ok=True)
    def _safe(self, name: str) -> str:
        name = SAFE_NAME.sub("-", name).strip("-.")
        if not name: raise ValueError("Profile name is empty")
        return name[:100]
    def _path(self, stage: str, name: str) -> Path:
        if stage not in VALID_STAGES: raise ValueError(f"Unknown workflow stage: {stage}")
        d = self.root / stage; d.mkdir(parents=True, exist_ok=True)
        return d / f"{self._safe(name)}.json"
    def save_profile(self, *, stage: str, name: str, workflow: dict[str, Any], bindings: dict[str, Any], output_node: str | None = None, description: str = "") -> dict[str, Any]:
        if not isinstance(workflow, dict) or not workflow: raise ValueError("workflow must be a non-empty API-format workflow object")
        if isinstance(workflow.get("nodes"), list): raise ValueError("This is a graph-format workflow. Export using 'Save (API Format)' and import that JSON instead.")
        clean_bindings = {}
        for key, targets in (bindings or {}).items():
            if key not in SEMANTIC_FIELDS and not key.startswith("extra."): continue
            if isinstance(targets, dict): targets = [targets]
            clean=[]
            for t in targets or []:
                node, input_name = str(t.get("node", "")), str(t.get("input", ""))
                if node in workflow and input_name in workflow[node].get("inputs", {}): clean.append({"node":node,"input":input_name})
            if clean: clean_bindings[key]=clean
        profile={"version":1,"stage":stage,"name":self._safe(name),"description":description,"output_node":str(output_node) if output_node not in (None,"") else None,"bindings":clean_bindings,"workflow":workflow}
        self._path(stage,name).write_text(json.dumps(profile,indent=2),encoding="utf-8")
        return self.summary(profile)
    def summary(self, profile): return {k: profile.get(k) for k in ("version","stage","name","description","output_node","bindings")}
    def load_profile(self, stage, name):
        path=self._path(stage,name)
        if not path.exists(): raise FileNotFoundError(f"Workflow profile not found: {stage}/{name}")
        return json.loads(path.read_text(encoding="utf-8"))
    def list_profiles(self):
        out={stage:[] for stage in sorted(VALID_STAGES)}
        for stage in out:
            d=self.root/stage
            if not d.exists(): continue
            for p in sorted(d.glob("*.json")):
                try: out[stage].append(self.summary(json.loads(p.read_text(encoding="utf-8"))))
                except Exception: continue
        return out
    def delete_profile(self, stage, name):
        path=self._path(stage,name)
        if path.exists(): path.unlink()
    def apply(self, profile, values):
        workflow=copy.deepcopy(profile["workflow"])
        for key, targets in profile.get("bindings",{}).items():
            value=self._lookup_value(values,key)
            if value is _MISSING: continue
            for target in targets: workflow[str(target["node"])]["inputs"][target["input"]]=value
        return workflow
    def _lookup_value(self, values, key):
        return values.get("extra",{}).get(key[6:],_MISSING) if key.startswith("extra.") else values.get(key,_MISSING)
    @staticmethod
    def inspect_workflow(workflow):
        if isinstance(workflow.get("nodes"),list): raise ValueError("Graph-format JSON detected; API-format JSON is required")
        nodes=[]
        for node_id,node in workflow.items():
            if not isinstance(node,dict) or "class_type" not in node: continue
            inputs=node.get("inputs",{})
            nodes.append({"id":str(node_id),"class_type":node.get("class_type",""),"title":node.get("_meta",{}).get("title") or node.get("class_type",""),"inputs":[{"name":k,"value":v,"bindable":not(isinstance(v,list) and len(v)==2 and isinstance(v[0],str))} for k,v in inputs.items()]})
        return nodes

class _Missing: pass
_MISSING=_Missing()
