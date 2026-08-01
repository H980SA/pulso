"""Load the pinned project-local Blender MCP addon without a global install."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import bpy


project_dir = Path(os.environ["PULSO_PROJECT_DIR"]).resolve()
addon_path = project_dir / ".tools" / "vendor" / "blender-mcp" / "addon.py"

if not addon_path.is_file():
    raise RuntimeError(f"Pinned Blender MCP addon not found: {addon_path}")

spec = importlib.util.spec_from_file_location("pulso_blender_mcp", addon_path)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Unable to load Blender MCP addon: {addon_path}")

module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.register()

scene = bpy.context.scene
scene.blendermcp_use_polyhaven = True
scene.blendermcp_use_sketchfab = False
scene.blendermcp_use_hyper3d = False
scene.blendermcp_use_hunyuan3d = False

print(f"Pulso Blender MCP loaded from {addon_path}")
print("Pulso Blender MCP listening on localhost:9876")

