from __future__ import annotations

import json
import re
import shutil
import uuid
from pathlib import Path
from typing import Any

from .config import sessions_dir

_SAFE = re.compile(r"[^A-Za-z0-9_.-]+")


class SessionStore:
    def __init__(self, root: Path | None = None):
        self.root = root or sessions_dir()
        self.root.mkdir(parents=True, exist_ok=True)

    def create(self, name: str | None = None) -> dict[str, Any]:
        sid = uuid.uuid4().hex[:12]
        safe_name = (_SAFE.sub("-", (name or "scene")).strip("-.") or "scene")[:80]
        path = self.root / f"{sid}-{safe_name}"
        path.mkdir(parents=True, exist_ok=False)
        meta = {"id": path.name, "name": name or safe_name, "status": "new"}
        self.write_meta(path.name, meta)
        return meta

    def path(self, session_id: str) -> Path:
        if not session_id or Path(session_id).name != session_id:
            raise ValueError("Invalid session id")
        p = (self.root / session_id).resolve()
        if self.root.resolve() not in p.parents:
            raise ValueError("Invalid session path")
        if not p.exists():
            raise FileNotFoundError(session_id)
        return p

    def list(self) -> list[dict[str, Any]]:
        rows = []
        for p in sorted(self.root.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
            if not p.is_dir():
                continue
            rows.append(self.read_meta(p.name))
        return rows

    def read_meta(self, session_id: str) -> dict[str, Any]:
        p = self.path(session_id) / "session.json"
        if not p.exists():
            return {"id": session_id, "name": session_id, "status": "unknown"}
        return json.loads(p.read_text(encoding="utf-8"))

    def write_meta(self, session_id: str, data: dict[str, Any]) -> dict[str, Any]:
        p = self.path(session_id) if (self.root / session_id).exists() else self.root / session_id
        p.mkdir(parents=True, exist_ok=True)
        current = {}
        meta_path = p / "session.json"
        if meta_path.exists():
            try:
                current = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                current = {}
        current.update(data)
        current["id"] = session_id
        meta_path.write_text(json.dumps(current, indent=2), encoding="utf-8")
        return current

    def put_file(self, session_id: str, source: str | Path, target_name: str) -> Path:
        dest = self.path(session_id) / target_name
        shutil.copy2(source, dest)
        return dest

    def asset(self, session_id: str, name: str) -> Path:
        session = self.path(session_id)
        if Path(name).name != name:
            raise ValueError("Invalid asset name")
        p = (session / name).resolve()
        if session.resolve() not in p.parents:
            raise ValueError("Invalid asset path")
        if not p.exists():
            raise FileNotFoundError(name)
        return p
