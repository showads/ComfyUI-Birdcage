"""ComfyUI Bird Cage - interactive AI scene compiler and standalone UI."""

from .nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS

# Importing routes registers aiohttp endpoints with ComfyUI's PromptServer.
try:
    from . import routes as _routes  # noqa: F401
except Exception as exc:  # Keep node loading alive in non-ComfyUI test environments.
    print(f"[Bird Cage] route registration skipped: {exc}")

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
