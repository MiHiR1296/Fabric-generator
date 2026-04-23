from __future__ import annotations

import os
import traceback

import addon_utils
import bpy


ADDON_MODULE = "BlenderMCPAddon"
TARGET_PORT = int(os.environ.get("BLENDER_PORT", "9875"))
START_DELAY_SECONDS = float(os.environ.get("BLENDER_MCP_START_DELAY_SECONDS", "2"))
MAX_ATTEMPTS = int(os.environ.get("BLENDER_MCP_START_MAX_ATTEMPTS", "30"))
_STATE = {"attempts": 0}


def ensure_blender_mcp_server():
    _STATE["attempts"] += 1
    try:
        addon_utils.enable(ADDON_MODULE, default_set=True, persistent=True)

        scene = bpy.context.scene
        if hasattr(scene, "blendermcp_port"):
            scene.blendermcp_port = TARGET_PORT

        if (
            hasattr(bpy.types, "blendermcp_server")
            and bpy.types.blendermcp_server
            and getattr(bpy.types.blendermcp_server, "port", None) != TARGET_PORT
        ):
            try:
                bpy.ops.blendermcp.stop_server()
            except Exception:
                traceback.print_exc()

        if hasattr(bpy.ops, "blendermcp") and hasattr(bpy.ops.blendermcp, "start_server"):
            result = bpy.ops.blendermcp.start_server()
            print(f"Managed BlenderMCP startup result: {result} on port {TARGET_PORT}")
            return None
    except Exception:
        traceback.print_exc()

    if _STATE["attempts"] >= MAX_ATTEMPTS:
        print(
            f"Managed BlenderMCP startup gave up after {_STATE['attempts']} attempts "
            f"on port {TARGET_PORT}."
        )
        return None

    return 1.0


bpy.app.timers.register(ensure_blender_mcp_server, first_interval=START_DELAY_SECONDS)
