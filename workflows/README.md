# Workflow templates

Runtime workflow profiles are created from `/bird-cage/` and stored in ComfyUI's Bird Cage data directory rather than this repository.

Use **Save (API Format)** in ComfyUI, then import the resulting JSON on Bird Cage's **Workflows** tab. The profile editor binds app-level semantic values to literal node inputs.

This directory intentionally does not bundle a third-party SAM/GroundingDINO graph because node class names differ between packs. It also avoids bundling model-specific FLUX.2 weights or requiring a specific loader implementation.
