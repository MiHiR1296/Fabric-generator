"""Phase 3 — push bandMeta.blender to the live Blender modifier.

This module is the single source of truth for the `bandMeta.blender.*` ->
`Parametric Weave knotty` socket mapping. It is consumed by:

  - `render_jobs.py` (headless): the helper bodies and the bandMeta -> entry
    transform are reused so headless renders apply the same per-Material
    sockets the live session would see.
  - `main.py` (live): `push_bandmeta_to_live_blender(...)` posts the same code
    body to the running BlenderMCPAddon socket (default 9876, override via
    BLENDER_PORT) so the user can iterate without firing a render job.

The socket map matches the .blend currently on 9876 — Material 1..16 family
with `Image Width Px / Texture Scale U / Arc 1 V Min/Max / Arc 2 V Min/Max`
per material, plus the legacy global sockets and pinned footgun sockets
(Rule 3).
"""
from __future__ import annotations

import json
from typing import Any

from .blender_sync import send_blender_command


MAX_MATERIAL_SLOTS = 16

# Per-Material socket suffix, the matching key inside `bandMeta.blender`, and
# the safe default to push when the value is missing.
#
# Phase 3e (2026-05-14): Arc 2 sockets carry STRAND-SILHOUETTE OUTER EXTENTS
# so the fiber halo renders correctly. The .blend's Arc 2 Top/Bot Map Range
# inner links were rewired to read from Arc 1 V Min/Max (the inner cutoffs)
# and Arc 2 V Min/Max (the outer extents) in tandem with this mapping change.
#
#   Arc 1 V Min/Max <- core_v_min / core_v_max          (the dense core)
#   Arc 2 V Min     <- fiber_bot_v_min                  (strand bottommost V)
#   Arc 2 V Max     <- fiber_top_v_max                  (strand topmost V)
PER_MATERIAL_SOCKETS: tuple[tuple[str, str, float], ...] = (
    ("Image Width Px", "image_width_px", 1.0),
    ("Texture Scale U", "texture_scale_u", 1.0),
    ("Arc 1 V Min", "core_v_min", 0.0),
    ("Arc 1 V Max", "core_v_max", 1.0),
    ("Arc 2 V Min", "fiber_bot_v_min", 0.0),
    ("Arc 2 V Max", "fiber_top_v_max", 1.0),
    # Phase 3g — per-yarn Arc 2 split fractions. Sockets don't exist on the
    # .blend yet (Pass 2 will add + wire them); push code skips missing
    # sockets silently. Defaults 0.0 mean "no halo" → split == 0 / 1 → the
    # current symmetric `r` behaviour is preserved if the sockets are absent.
    ("Top Halo Frac", "top_halo_frac", 0.0),
    ("Bot Halo Frac", "bot_halo_frac", 0.0),
)

# Truly-global sockets that the graph still consumes. The legacy
# `Image Width Px / Image Arc 1/2 V Min/Max` sockets were removed from the
# .blend on 2026-05-14 once we confirmed they had no Group Input consumers —
# the per-Material V-band sockets are the only path the graph uses now.
GLOBAL_SOCKETS: tuple[tuple[str, str, float], ...] = (
    ("Scanner Pixels Per BU", "scanner_pixels_per_bu", 1.0),
)

# Pinned defaults — Rule 3 in lessons.md. The V-related sockets are additive
# deltas, NOT absolute overrides; leaving them at zero/one is the only safe
# shape for scan-driven yarns. We push them defensively even though they're the
# .blend's defaults — protects against someone tweaking the file.
#
# Sub Strand Enable is also pinned here because Arc 2's halo mapping is gated
# by the is_sub_strand attribute — without sub-strand geometry, PW Band - Band V
# falls back to Arc 1 only (core texture stretched across the whole strand,
# no halo). Pinning True keeps Arc 2 active. See BlenderFixes/phase_log.md.
PINNED_FOOTGUN_SOCKETS: tuple[tuple[str, float | bool], ...] = (
    ("Sub Strand Enable", True),
    ("Texture Scale V", 1.0),
    ("Texture Offset V", 0.0),
    ("Texture Side Flatten", 0.0),
    ("Sub Texture Scale V", 0.0),
    ("Sub Texture Offset V", 0.0),
)


def _coerce_float(value: Any, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed == parsed else default


def build_material_asset_entry(asset: Any) -> dict[str, Any]:
    """Project a YarnAsset's `bandMeta.blender` into a flat dict the live-push
    code understands. Producer pre-computes everything; this is just a
    field-rename pass.

    Phase 3g back-compat: yarns saved before the producer learned to emit
    `top_halo_frac` / `bot_halo_frac` still have `thickness_px` (core_height,
    fiber_top_height, fiber_bot_height). We derive the fractions on-the-fly
    here so push works for them without an on-disk migration."""
    band_meta = getattr(asset, "bandMeta", None) or {}
    if not isinstance(band_meta, dict):
        band_meta = {}
    blender = band_meta.get("blender") or {}
    if not isinstance(blender, dict):
        blender = {}

    th = band_meta.get("thickness_px") or {}
    fallback_top_frac = 0.0
    fallback_bot_frac = 0.0
    if isinstance(th, dict):
        core_h = th.get("core_height")
        top_h = th.get("fiber_top_height")
        bot_h = th.get("fiber_bot_height")
        if (isinstance(core_h, int) and isinstance(top_h, int)
                and isinstance(bot_h, int) and (core_h + top_h + bot_h) > 0):
            total = float(core_h + top_h + bot_h)
            fallback_top_frac = round(top_h / total, 6)
            fallback_bot_frac = round(bot_h / total, 6)
    # Six V-band fields are projected. Arc 1 uses the core (inner pair); Arc 2
    # uses the strand-silhouette outer extents (Phase 3e). The legacy inner
    # fiber pair is kept in the entry for back-compat (older .blend revisions
    # could re-read them) but the live push code does not currently map them.
    return {
        "id": getattr(asset, "id", None) or band_meta.get("library_yarn_id") or "",
        "label": getattr(asset, "label", None) or band_meta.get("name") or "",
        "scanner_pixels_per_bu": _coerce_float(blender.get("scanner_pixels_per_bu"), 1.0),
        "image_width_px": max(1.0, _coerce_float(blender.get("image_width_px"), 1.0)),
        "texture_scale_u": _coerce_float(blender.get("texture_scale_u"), 1.0),
        "core_v_min": _coerce_float(blender.get("core_v_min"), 0.0),
        "core_v_max": _coerce_float(blender.get("core_v_max"), 1.0),
        # Outer extents = the strand silhouette's bottommost and topmost V.
        # These land on Material N Arc 2 V Min / Arc 2 V Max sockets.
        "fiber_bot_v_min": _coerce_float(blender.get("fiber_bot_v_min"), 0.0),
        "fiber_top_v_max": _coerce_float(blender.get("fiber_top_v_max"), 1.0),
        # Inner-pair retained for diagnostics / future revival.
        "fiber_top_v_min": _coerce_float(blender.get("fiber_top_v_min"), 0.0),
        "fiber_bot_v_max": _coerce_float(blender.get("fiber_bot_v_max"), 1.0),
        # Phase 3g — Arc 2 V split fractions (top/bot hair height / total).
        # Producer emits these on new saves; for older yarns we fall back to
        # the value computed from thickness_px above so push still works.
        "top_halo_frac": _coerce_float(blender.get("top_halo_frac"), fallback_top_frac),
        "bot_halo_frac": _coerce_float(blender.get("bot_halo_frac"), fallback_bot_frac),
    }


# This Python body is run inside Blender (live MCP socket or headless script).
# Reads `_PW_MATERIAL_ASSETS` (list of entry dicts) and `_PW_TARGET` (object
# name) from the calling scope, mutates the modifier in place. The constants
# above are inlined into the body so the two code paths cannot drift.
APPLY_METADATA_PY = """
import bpy

_PER_MATERIAL_SOCKETS = """ + repr(PER_MATERIAL_SOCKETS) + """
_GLOBAL_SOCKETS = """ + repr(GLOBAL_SOCKETS) + """
_PINNED_FOOTGUN_SOCKETS = """ + repr(PINNED_FOOTGUN_SOCKETS) + """
_MAX_MATERIAL_SLOTS = """ + repr(MAX_MATERIAL_SLOTS) + """


def _pw_socket_identifier(node_group, name):
    interface = getattr(node_group, 'interface', None)
    if interface is None:
        return None
    for item in interface.items_tree:
        if getattr(item, 'item_type', None) == 'SOCKET' and item.in_out == 'INPUT' and item.name == name:
            return item.identifier
    return None


def _pw_set_socket(modifier, node_group, name, value):
    ident = _pw_socket_identifier(node_group, name)
    if ident is None:
        return False
    try:
        modifier[ident] = value
        return True
    except Exception:
        return False


def _pw_apply_modifier_material_metadata(modifier, material_assets):
    node_group = getattr(modifier, 'node_group', None)
    if modifier is None or node_group is None:
        return {'applied': 0, 'skipped': 0, 'pinned': 0, 'globals': 0}

    try:
        texture_scale_u_multiplier = float(globals().get('_PW_TEXTURE_SCALE_U_MULTIPLIER', 1.0))
    except Exception:
        texture_scale_u_multiplier = 1.0

    applied = 0
    skipped = 0
    pinned = 0
    globals_set = 0

    for socket_name, default_value in _PINNED_FOOTGUN_SOCKETS:
        if _pw_set_socket(modifier, node_group, socket_name, default_value):
            pinned += 1

    if material_assets:
        first = material_assets[0]
        for socket_name, key, default in _GLOBAL_SOCKETS:
            if _pw_set_socket(modifier, node_group, socket_name, float(first.get(key, default))):
                globals_set += 1

        for index, entry in enumerate(material_assets[:_MAX_MATERIAL_SLOTS], start=1):
            for suffix, key, default in _PER_MATERIAL_SOCKETS:
                socket_name = 'Material ' + str(index) + ' ' + suffix
                socket_value = float(entry.get(key, default))
                if suffix == 'Texture Scale U':
                    socket_value *= texture_scale_u_multiplier
                if _pw_set_socket(modifier, node_group, socket_name, socket_value):
                    applied += 1
                else:
                    skipped += 1

    return {
        'applied': applied,
        'skipped': skipped,
        'pinned': pinned,
        'globals': globals_set,
    }
"""


def _live_push_script(
    material_assets: list[dict[str, Any]],
    target_object_name: str,
    modifier_name: str,
) -> str:
    """Build the Python body shipped to the live Blender MCP socket."""
    payload_json = json.dumps(material_assets)
    target_json = json.dumps(target_object_name)
    modifier_json = json.dumps(modifier_name)

    body = APPLY_METADATA_PY + """

_PW_MATERIAL_ASSETS = json.loads(""" + json.dumps(payload_json) + """)
_PW_TARGET = """ + target_json + """
_PW_MODIFIER = """ + modifier_json + """

_obj = bpy.data.objects.get(_PW_TARGET)
if _obj is None:
    result = {'status': 'error', 'message': 'object not found: ' + _PW_TARGET}
else:
    _mod = _obj.modifiers.get(_PW_MODIFIER)
    if _mod is None:
        result = {'status': 'error', 'message': 'modifier not found: ' + _PW_MODIFIER}
    else:
        _summary = _pw_apply_modifier_material_metadata(_mod, _PW_MATERIAL_ASSETS)
        try:
            _obj.update_tag()
            bpy.context.view_layer.update()
        except Exception:
            pass
        result = {
            'status': 'success',
            'object': _PW_TARGET,
            'modifier': _PW_MODIFIER,
            'material_count': len(_PW_MATERIAL_ASSETS),
            'sockets': _summary,
        }

import json as _json
print(_json.dumps(result))
"""
    # The MCP addon's execute_code captures stdout via the response, but
    # we also want to keep this body re-usable for headless (where stdout
    # ends up in stdout.log). The trailing import json is intentional —
    # the live script needs json.loads and we don't want to assume the
    # parent script already imported it.
    body = "import json\n" + body
    return body


def push_bandmeta_to_live_blender(
    material_assets: list[dict[str, Any]],
    *,
    target_object_name: str = "ParametricWeave",
    modifier_name: str = "Weave",
) -> dict[str, Any]:
    """Push bandMeta.blender values to the running Blender session.

    `material_assets` is a list of entries from `build_material_asset_entry`.
    Returns the BlenderMCPAddon response (status/result or status/message).
    """
    code = _live_push_script(material_assets, target_object_name, modifier_name)
    response = send_blender_command("execute_code", {"code": code})
    return response
