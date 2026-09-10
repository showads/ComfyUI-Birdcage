from __future__ import annotations

import os
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parent
WEB_DIR = PLUGIN_DIR / "web"
BUILTIN_WORKFLOWS_DIR = PLUGIN_DIR / "workflows"
BUILTIN_PRESETS_DIR = PLUGIN_DIR / "presets"


def data_dir() -> Path:
    """Persistent writable storage. Defaults to ComfyUI/output/bird-cage."""
    env = os.getenv("BIRDCAGE_DATA_DIR")
    if env:
        root = Path(env).expanduser().resolve()
    else:
        try:
            import folder_paths

            root = Path(folder_paths.get_output_directory()) / "bird-cage"
        except Exception:
            root = PLUGIN_DIR / "data"
    root.mkdir(parents=True, exist_ok=True)
    return root


def sessions_dir() -> Path:
    p = data_dir() / "sessions"
    p.mkdir(parents=True, exist_ok=True)
    return p


def profiles_dir() -> Path:
    p = data_dir() / "profiles"
    p.mkdir(parents=True, exist_ok=True)
    return p


def presets_dir() -> Path:
    p = data_dir() / "presets"
    p.mkdir(parents=True, exist_ok=True)
    return p
