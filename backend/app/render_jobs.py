from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from .atlas import AtlasBundle, build_yarn_atlas
from .blender_live import APPLY_METADATA_PY, build_material_asset_entry
from .blender_sync import build_blender_sync_code, send_blender_command, validate_drawdown_matrix
from .fabric_project import (
    build_project_snapshot,
    normalize_color_bindings,
    save_project_snapshot,
    validate_project_bindings,
)
from .runtime_paths import BLEND_FILE_PATH, PROJECTS_ROOT, RENDER_JOBS_ROOT, YARN_ASSETS_ROOT, ensure_runtime_dirs
from .tile_inpaint_repair import repair_tile_with_two_pass_inpaint
from .yarn_assets import (
    ensure_cycles_tiled_rgba_texture_set,
    ensure_cycles_tiled_texture_set,
    get_ready_yarn_assets_lookup,
)


def _is_live_render_mode() -> bool:
    # BLENDER_LIVE_RENDER=1 (or true/yes/on) routes render jobs to the open
    # Blender session over MCP instead of spawning a headless subprocess.
    # Used during BlenderFixes development so changes show up in the open
    # viewport. Default off — production keeps using headless.
    return os.environ.get("BLENDER_LIVE_RENDER", "").lower() in ("1", "true", "yes", "on")


DEFAULT_BLENDER_BINARY = Path("/Applications/Blender.app/Contents/MacOS/Blender")
DEFAULT_BLEND_FILE = BLEND_FILE_PATH
DEFAULT_RUNTIME_ROOT = RENDER_JOBS_ROOT
MAX_DIRECT_PREVIEW_MATERIALS = 16
DEFAULT_PREVIEW_RENDER_RESOLUTION = 3200
DEFAULT_PREVIEW_RENDER_SAMPLES = 96
DEFAULT_TEXTURE_INTERPOLATION = "Linear"
TEXTURE_INTERPOLATION_MODES = {"Linear", "Closest", "Cubic", "Smart"}
DEFAULT_CUTOUT_BLEND_METHOD = "BLEND"
DEFAULT_SURFACE_RENDER_METHOD = "BLENDED"
CUTOUT_BLEND_METHODS = {"OPAQUE", "CLIP", "HASHED", "BLEND"}
SURFACE_RENDER_METHODS = {"DITHERED", "BLENDED"}
DEFAULT_TILE_COUNT = 4
DEFAULT_TILE_RESOLUTION = 1200
DEFAULT_TILE_GUARD_THREADS = 0
DEFAULT_TILE_RENDER_SAMPLES = 40
DEFAULT_TILE_ORTHO_SCALE = 2.975
DEFAULT_TILE_VARIATION_STRENGTH = 0.0
DEFAULT_TILE_REPAIR_SEAM_RADIUS = 12
DEFAULT_TILE_REPAIR_CONTEXT = 640
DEFAULT_TILE_REPAIR_COLOR_MATCH_STRENGTH = 1.2
ALLOWED_TILE_COUNTS = {4}


@dataclass(frozen=True)
class HeadlessBlenderConfig:
    blender_binary: Path
    blend_file: Path
    runtime_root: Path


@dataclass
class RenderJob:
    id: str
    status: str
    message: str
    draft_title: str
    target_object_name: str
    draft_object_name: str
    created_at: str
    job_dir: Path
    render_path: Path
    script_path: Path
    stdout_path: Path
    stderr_path: Path
    tile_source_paths: list[Path] = field(default_factory=list)
    started_at: str | None = None
    finished_at: str | None = None
    image_url: str | None = None
    log_tail: list[str] = field(default_factory=list)


_JOBS: dict[str, RenderJob] = {}
_LOCK = threading.Lock()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_headless_blender_config() -> HeadlessBlenderConfig:
    ensure_runtime_dirs()
    blender_binary = Path(os.environ.get("BLENDER_BINARY_PATH", str(DEFAULT_BLENDER_BINARY))).expanduser()
    blend_file = Path(os.environ.get("WEAVE_BLEND_FILE", str(DEFAULT_BLEND_FILE))).expanduser()
    runtime_root = Path(os.environ.get("WEAVE_RENDER_ROOT", str(DEFAULT_RUNTIME_ROOT))).expanduser()
    return HeadlessBlenderConfig(
        blender_binary=blender_binary,
        blend_file=blend_file,
        runtime_root=runtime_root,
    )


def _int_env(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = os.environ.get(name)
    try:
        value = int(round(float(raw))) if raw is not None else default
    except (TypeError, ValueError):
        value = default
    return min(maximum, max(minimum, value))


def _texture_interpolation_env() -> str:
    value = os.environ.get("WEAVE_TEXTURE_INTERPOLATION", DEFAULT_TEXTURE_INTERPOLATION)
    return value if value in TEXTURE_INTERPOLATION_MODES else DEFAULT_TEXTURE_INTERPOLATION


def _enum_env(name: str, default: str, allowed: set[str]) -> str:
    value = os.environ.get(name, default).upper()
    return value if value in allowed else default


def validate_headless_blender_config(config: HeadlessBlenderConfig) -> None:
    if not config.blender_binary.exists():
        raise FileNotFoundError(f"Blender binary not found at {config.blender_binary}")
    if not config.blender_binary.is_file():
        raise FileNotFoundError(f"Blender binary path is not a file: {config.blender_binary}")
    if not config.blend_file.exists():
        raise FileNotFoundError(f"Blend file not found at {config.blend_file}")
    if not config.blend_file.is_file():
        raise FileNotFoundError(f"Blend file path is not a file: {config.blend_file}")
    config.runtime_root.mkdir(parents=True, exist_ok=True)


def build_headless_render_script(
    draft: dict[str, Any],
    *,
    render_path: str | Path,
    target_object_name: str = "ParametricWeave",
    draft_object_name: str = "WebDraft_Live",
    atlas_bundle: AtlasBundle | None = None,
    warp_material_ids: list[int] | None = None,
    weft_material_ids: list[int] | None = None,
    material_assets: list[dict[str, Any]] | None = None,
    weave_modifier_name: str = "Weave",
    render_still: bool = True,
    render_resolution: int | None = None,
    render_samples: int | None = None,
    tile_render_mode: bool = False,
    tile_ortho_scale: float | None = None,
) -> str:
    drawdown = validate_drawdown_matrix(draft.get("drawdown"))
    render_path_json = json.dumps(str(Path(render_path)))
    target_name_json = json.dumps(target_object_name)
    normalized_material_assets: list[dict[str, Any]] = []
    for entry in material_assets or []:
        normalized = dict(entry)
        for path_key in (
            "diffuse_path",
            "alpha_path",
            "rgba_path",
            "diffuse_tile_pattern",
            "alpha_tile_pattern",
            "rgba_tile_pattern",
        ):
            if normalized.get(path_key) is not None:
                normalized[path_key] = str(normalized[path_key])
        for path_list_key in ("diffuse_tile_paths", "alpha_tile_paths", "rgba_tile_paths"):
            if normalized.get(path_list_key):
                normalized[path_list_key] = [str(path) for path in normalized[path_list_key]]
        normalized_material_assets.append(normalized)
    material_assets_json = json.dumps(normalized_material_assets)

    def _can_use_direct_preview_material(entry: dict[str, Any]) -> bool:
        texture_mode = entry.get("texture_mode")
        tile_count = int(entry.get("texture_tile_count") or 0)
        if texture_mode == "udim_rgba_tiled":
            return bool(entry.get("rgba_tile_pattern") and tile_count > 1)
        if texture_mode == "rgba_single":
            return bool(entry.get("rgba_path"))
        if texture_mode == "udim_tiled":
            return bool(entry.get("diffuse_tile_pattern") and entry.get("alpha_tile_pattern") and tile_count > 1)
        return bool(entry.get("diffuse_path") and entry.get("alpha_path"))

    has_direct_material_assets = (
        bool(normalized_material_assets)
        and len(normalized_material_assets) <= MAX_DIRECT_PREVIEW_MATERIALS
        and all(_can_use_direct_preview_material(entry) for entry in normalized_material_assets)
    )
    material_count = (
        len(normalized_material_assets)
        if has_direct_material_assets
        else (atlas_bundle.rows if atlas_bundle is not None else None)
    )
    if render_resolution is None:
        preview_render_resolution = _int_env(
            "WEAVE_PREVIEW_RENDER_RESOLUTION",
            DEFAULT_PREVIEW_RENDER_RESOLUTION,
            minimum=512,
            maximum=8192,
        )
    else:
        preview_render_resolution = min(8192, max(512, int(round(render_resolution))))
    if render_samples is None:
        preview_render_samples = _int_env(
            "WEAVE_PREVIEW_RENDER_SAMPLES",
            DEFAULT_PREVIEW_RENDER_SAMPLES,
            minimum=1,
            maximum=4096,
        )
    else:
        preview_render_samples = min(4096, max(1, int(round(render_samples))))
    texture_interpolation = _texture_interpolation_env()
    cutout_blend_method = _enum_env(
        "WEAVE_CUTOUT_BLEND_METHOD",
        DEFAULT_CUTOUT_BLEND_METHOD,
        CUTOUT_BLEND_METHODS,
    )
    surface_render_method = _enum_env(
        "WEAVE_SURFACE_RENDER_METHOD",
        DEFAULT_SURFACE_RENDER_METHOD,
        SURFACE_RENDER_METHODS,
    )
    modifier_name_json = json.dumps(weave_modifier_name)
    sync_code = build_blender_sync_code(
        {
            **draft,
            "drawdown": drawdown,
        },
        target_object_name=target_object_name,
        draft_object_name=draft_object_name,
        warp_material_ids=warp_material_ids,
        weft_material_ids=weft_material_ids,
        material_count=material_count,
    )

    atlas_setup = ""
    preview_setup = """
    preview_materials = [ensure_preview_material(
        'WebDraftPreviewMaterial',
        warp_colors[0] if warp_colors else '#f3ede2',
        weft_colors[0] if weft_colors else '#b85e3c',
    )]
    """
    material_helpers = """
def hex_to_rgba(value):
    raw = str(value or '').strip().lstrip('#')
    if len(raw) == 3:
        raw = ''.join(part * 2 for part in raw)
    if len(raw) != 6:
        return (0.7, 0.7, 0.7, 1.0)
    return (
        int(raw[0:2], 16) / 255.0,
        int(raw[2:4], 16) / 255.0,
        int(raw[4:6], 16) / 255.0,
        1.0,
    )

def ensure_preview_material(name, warp_hex, weft_hex):
    material = bpy.data.materials.get(name)
    if material is None:
        material = bpy.data.materials.new(name=name)

    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()

    output = nodes.new('ShaderNodeOutputMaterial')
    output.location = (440, 0)
    shader = nodes.new('ShaderNodeBsdfPrincipled')
    shader.location = (200, 0)
    shader.inputs['Roughness'].default_value = 0.72
    attribute = nodes.new('ShaderNodeAttribute')
    attribute.location = (-560, -40)
    attribute.attribute_name = 'thread_kind'
    compare = nodes.new('ShaderNodeMath')
    compare.location = (-350, -40)
    compare.operation = 'GREATER_THAN'
    compare.inputs[1].default_value = 0.5
    mix = nodes.new('ShaderNodeMixRGB')
    mix.location = (-60, 0)
    mix.inputs['Color1'].default_value = hex_to_rgba(warp_hex)
    mix.inputs['Color2'].default_value = hex_to_rgba(weft_hex)

    links.new(attribute.outputs['Fac'], compare.inputs[0])
    links.new(compare.outputs[0], mix.inputs['Fac'])
    links.new(mix.outputs['Color'], shader.inputs['Base Color'])
    links.new(shader.outputs['BSDF'], output.inputs['Surface'])
    return material

def ensure_image(name, image_path, colorspace=None):
    image = bpy.data.images.get(name)
    if image is None:
        image = bpy.data.images.load(image_path, check_existing=True)
    else:
        image.filepath = image_path
        image.reload()
    if colorspace:
        image.colorspace_settings.name = colorspace
    return image


def ensure_udim_image(name, image_pattern, tile_count, colorspace=None):
    image = bpy.data.images.get(name)
    if image is not None and getattr(image, 'source', None) != 'TILED':
        bpy.data.images.remove(image)
        image = None
    if image is None:
        image = bpy.data.images.new(name, width=1, height=1, tiled=True)
    image.filepath = image_pattern
    existing = {tile.number for tile in image.tiles}
    for tile_number in range(1001, 1001 + int(tile_count)):
        if tile_number not in existing:
            image.tiles.new(tile_number)
    if colorspace:
        image.colorspace_settings.name = colorspace
    try:
        image.reload()
    except Exception:
        pass
    return image


def configure_texture_node(texture_node, extension='REPEAT'):
    try:
        texture_node.extension = extension
    except Exception:
        pass
    try:
        texture_node.interpolation = _PW_TEXTURE_INTERPOLATION
    except Exception:
        pass

def configure_cutout_material(material):
    try:
        material.blend_method = _PW_CUTOUT_BLEND_METHOD
    except Exception:
        pass
    if hasattr(material, 'surface_render_method'):
        try:
            material.surface_render_method = _PW_SURFACE_RENDER_METHOD
        except Exception:
            pass
    try:
        material.use_screen_refraction = False
    except Exception:
        pass

def safe_material_suffix(value, fallback):
    raw = str(value or fallback)
    safe = ''.join(ch if ch.isalnum() else '_' for ch in raw)
    return safe[:32] or str(fallback)

def ensure_texture_preview_material(asset_entry, index):
    suffix = safe_material_suffix(asset_entry.get('id'), f'material_{index}')
    material_name = f"FabricStudioMaterial_{index:02d}_{suffix}"
    material = bpy.data.materials.get(material_name)
    if material is None:
        material = bpy.data.materials.new(name=material_name)

    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()

    output = nodes.new('ShaderNodeOutputMaterial')
    output.location = (620, 0)
    shader = nodes.new('ShaderNodeBsdfPrincipled')
    shader.location = (380, 0)
    shader.inputs['Roughness'].default_value = 0.72
    shader.inputs['Alpha'].default_value = 1.0

    use_rgba_tiled = (
        asset_entry.get('texture_mode') == 'udim_rgba_tiled'
        and asset_entry.get('rgba_tile_pattern')
        and int(asset_entry.get('texture_tile_count') or 0) > 1
    )
    use_rgba_single = (
        asset_entry.get('texture_mode') == 'rgba_single'
        and asset_entry.get('rgba_path')
    )
    use_tiled = (
        asset_entry.get('texture_mode') == 'udim_tiled'
        and asset_entry.get('diffuse_tile_pattern')
        and asset_entry.get('alpha_tile_pattern')
        and int(asset_entry.get('texture_tile_count') or 0) > 1
    )

    diffuse_tex = nodes.new('ShaderNodeTexImage')
    diffuse_tex.name = 'FabricStudioDiffuseNode'
    diffuse_tex.location = (80, 80)
    alpha_tex = nodes.new('ShaderNodeTexImage')
    alpha_tex.name = 'FabricStudioAlphaNode'
    alpha_tex.location = (80, -160)
    if use_rgba_tiled:
        tile_count = int(asset_entry.get('texture_tile_count') or 1)
        rgba_image = ensure_udim_image(
            f"{material_name}_RGBA_UDIM",
            asset_entry['rgba_tile_pattern'],
            tile_count,
            'sRGB',
        )
        diffuse_tex.image = rgba_image
        alpha_tex.image = rgba_image
        configure_texture_node(diffuse_tex, 'CLIP')
        configure_texture_node(alpha_tex, 'CLIP')
    elif use_rgba_single:
        rgba_image = ensure_image(f"{material_name}_RGBA", asset_entry['rgba_path'], 'sRGB')
        diffuse_tex.image = rgba_image
        alpha_tex.image = rgba_image
        configure_texture_node(diffuse_tex)
        configure_texture_node(alpha_tex)
    elif use_tiled:
        tile_count = int(asset_entry.get('texture_tile_count') or 1)
        diffuse_tex.image = ensure_udim_image(
            f"{material_name}_Diffuse_UDIM",
            asset_entry['diffuse_tile_pattern'],
            tile_count,
            'sRGB',
        )
        alpha_tex.image = ensure_udim_image(
            f"{material_name}_Alpha_UDIM",
            asset_entry['alpha_tile_pattern'],
            tile_count,
            'Non-Color',
        )
        configure_texture_node(diffuse_tex, 'CLIP')
        configure_texture_node(alpha_tex, 'CLIP')
    else:
        diffuse_tex.image = ensure_image(f"{material_name}_Diffuse", asset_entry['diffuse_path'], 'sRGB')
        alpha_tex.image = ensure_image(f"{material_name}_Alpha", asset_entry['alpha_path'], 'Non-Color')
        configure_texture_node(diffuse_tex)
        configure_texture_node(alpha_tex)

    uv_attr = nodes.new('ShaderNodeAttribute')
    uv_attr.location = (-430, 20)
    uv_attr.attribute_name = 'uv_scaled'
    try:
        uv_attr.attribute_type = 'GEOMETRY'
    except Exception:
        pass

    if use_rgba_tiled or use_tiled:
        uv_sep = nodes.new('ShaderNodeSeparateXYZ')
        uv_sep.location = (-220, 20)
        u_fract = nodes.new('ShaderNodeMath')
        u_fract.location = (-20, -80)
        u_fract.operation = 'FRACT'
        u_tile_scale = nodes.new('ShaderNodeMath')
        u_tile_scale.location = (170, -80)
        u_tile_scale.operation = 'MULTIPLY'
        u_tile_scale.inputs[1].default_value = float(asset_entry.get('texture_tile_count') or 1)
        tiled_vector = nodes.new('ShaderNodeCombineXYZ')
        tiled_vector.location = (380, -40)
        diffuse_tex.location = (600, 80)
        alpha_tex.location = (600, -160)

        links.new(uv_attr.outputs['Vector'], uv_sep.inputs['Vector'])
        links.new(uv_sep.outputs['X'], u_fract.inputs[0])
        links.new(u_fract.outputs[0], u_tile_scale.inputs[0])
        links.new(u_tile_scale.outputs[0], tiled_vector.inputs['X'])
        links.new(uv_sep.outputs['Y'], tiled_vector.inputs['Y'])
        links.new(uv_sep.outputs['Z'], tiled_vector.inputs['Z'])
        links.new(tiled_vector.outputs['Vector'], diffuse_tex.inputs['Vector'])
        links.new(tiled_vector.outputs['Vector'], alpha_tex.inputs['Vector'])
    else:
        mapping = nodes.new('ShaderNodeMapping')
        mapping.location = (-180, 20)
        links.new(uv_attr.outputs['Vector'], mapping.inputs['Vector'])
        links.new(mapping.outputs['Vector'], diffuse_tex.inputs['Vector'])
        links.new(mapping.outputs['Vector'], alpha_tex.inputs['Vector'])
    links.new(diffuse_tex.outputs['Color'], shader.inputs['Base Color'])
    alpha_output = alpha_tex.outputs['Alpha'] if (use_rgba_tiled or use_rgba_single) else alpha_tex.outputs['Color']
    links.new(alpha_output, shader.inputs['Alpha'])
    links.new(shader.outputs['BSDF'], output.inputs['Surface'])

    configure_cutout_material(material)
    return material

def has_modifier_input(node_group, name):
    try:
        ensure_socket(node_group, name)
        return True
    except Exception:
        return False

def compress_material_runs(material_ids):
    runs = []
    for material_id in material_ids or []:
        one_based_material_id = int(material_id) + 1
        if runs and runs[-1][1] == one_based_material_id:
            runs[-1][0] += 1
        else:
            runs.append([1, one_based_material_id])
    return runs

def apply_material_cycle_inputs(modifier, node_group, prefix, material_ids):
    runs = compress_material_runs(material_ids)
    if not runs:
        return
    maybe_set_modifier_input(modifier, node_group, f'{prefix} Offset', 0)
    for index in range(4):
        length_value = runs[index][0] if index < len(runs) else 0
        material_value = runs[index][1] if index < len(runs) else min(index + 1, max(1, len(runs)))
        maybe_set_modifier_input(modifier, node_group, f'{prefix} Length {index + 1}', int(length_value))
        maybe_set_modifier_input(modifier, node_group, f'{prefix} Material {index + 1}', int(material_value))

def apply_modifier_material_slots(modifier, node_group, materials, warp_ids, weft_ids, material_assets=None):
    summary = {'materials': 0, 'cleared': 0, 'bandMeta': None}
    if modifier is None or node_group is None:
        return summary

    for index, material in enumerate(materials, start=1):
        try:
            set_modifier_input(modifier, node_group, f'Material {index}', material)
            summary['materials'] += 1
        except Exception:
            break
    for index in range(len(materials) + 1, 17):
        try:
            if maybe_set_modifier_input(modifier, node_group, f'Material {index}', None):
                summary['cleared'] += 1
        except Exception:
            pass

    if material_assets:
        try:
            summary['bandMeta'] = _pw_apply_modifier_material_metadata(modifier, material_assets)
        except Exception as exc:
            summary['bandMeta'] = {'error': str(exc)}

    try:
        apply_material_cycle_inputs(modifier, node_group, 'Warp', warp_ids)
        apply_material_cycle_inputs(modifier, node_group, 'Weft', weft_ids)
    except Exception as exc:
        summary['cycle_error'] = str(exc)
    return summary

def build_generated_preview_materials(material_assets):
    if not material_assets:
        return []
    return [
        ensure_texture_preview_material(asset_entry, index)
        for index, asset_entry in enumerate(material_assets, start=1)
    ]
"""

    if atlas_bundle is not None:
        atlas_setup = f"""
atlas_diffuse_path = {json.dumps(str(atlas_bundle.diffuse_path))}
atlas_alpha_path = {json.dumps(str(atlas_bundle.alpha_path))}
atlas_rows = {atlas_bundle.rows}

def ensure_image(name, image_path, colorspace):
    image = bpy.data.images.get(name)
    if image is None:
        image = bpy.data.images.load(image_path, check_existing=True)
    else:
        image.filepath = image_path
        image.reload()
    image.colorspace_settings.name = colorspace
    return image

def ensure_atlas_preview_material(name, diffuse_path, alpha_path, rows):
    material = bpy.data.materials.get(name)
    if material is None:
        material = bpy.data.materials.new(name=name)

    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()

    output = nodes.new('ShaderNodeOutputMaterial')
    output.location = (960, 0)
    transparent = nodes.new('ShaderNodeBsdfTransparent')
    transparent.location = (520, 160)
    shader = nodes.new('ShaderNodeBsdfPrincipled')
    shader.location = (520, -40)
    shader.inputs['Roughness'].default_value = 0.72
    mix_shader = nodes.new('ShaderNodeMixShader')
    mix_shader.location = (760, 40)

    uv_attr = nodes.new('ShaderNodeAttribute')
    uv_attr.location = (-980, -220)
    uv_attr.attribute_name = 'uv_scaled'
    uv_sep = nodes.new('ShaderNodeSeparateXYZ')
    uv_sep.location = (-760, -220)
    u_fract = nodes.new('ShaderNodeMath')
    u_fract.location = (-520, -340)
    u_fract.operation = 'FRACT'
    v_fract = nodes.new('ShaderNodeMath')
    v_fract.location = (-520, -180)
    v_fract.operation = 'FRACT'

    colour_attr = nodes.new('ShaderNodeAttribute')
    colour_attr.location = (-980, 20)
    colour_attr.attribute_name = 'colour_id'
    row_add = nodes.new('ShaderNodeMath')
    row_add.location = (-300, -40)
    row_add.operation = 'ADD'
    row_add.inputs[1].default_value = 0.0
    row_divide = nodes.new('ShaderNodeMath')
    row_divide.location = (-100, -40)
    row_divide.operation = 'DIVIDE'
    row_divide.inputs[1].default_value = float(max(rows, 1))

    atlas_vector = nodes.new('ShaderNodeCombineXYZ')
    atlas_vector.location = (120, -140)
    diffuse_tex = nodes.new('ShaderNodeTexImage')
    diffuse_tex.location = (320, -120)
    diffuse_tex.image = ensure_image('FabricStudioDiffuseAtlas', diffuse_path, 'sRGB')
    alpha_tex = nodes.new('ShaderNodeTexImage')
    alpha_tex.location = (320, 100)
    alpha_tex.image = ensure_image('FabricStudioAlphaAtlas', alpha_path, 'Non-Color')
    alpha_bw = nodes.new('ShaderNodeRGBToBW')
    alpha_bw.location = (520, 100)

    links.new(uv_attr.outputs['Vector'], uv_sep.inputs['Vector'])
    links.new(uv_sep.outputs['X'], u_fract.inputs[0])
    links.new(uv_sep.outputs['Y'], v_fract.inputs[0])
    links.new(colour_attr.outputs['Fac'], row_add.inputs[0])
    links.new(v_fract.outputs[0], row_add.inputs[1])
    links.new(row_add.outputs[0], row_divide.inputs[0])
    links.new(u_fract.outputs[0], atlas_vector.inputs['X'])
    links.new(row_divide.outputs[0], atlas_vector.inputs['Y'])
    links.new(atlas_vector.outputs['Vector'], diffuse_tex.inputs['Vector'])
    links.new(atlas_vector.outputs['Vector'], alpha_tex.inputs['Vector'])
    links.new(diffuse_tex.outputs['Color'], shader.inputs['Base Color'])
    links.new(alpha_tex.outputs['Color'], alpha_bw.inputs['Color'])
    links.new(alpha_bw.outputs['Val'], mix_shader.inputs['Fac'])
    links.new(transparent.outputs['BSDF'], mix_shader.inputs[1])
    links.new(shader.outputs['BSDF'], mix_shader.inputs[2])
    links.new(mix_shader.outputs['Shader'], output.inputs['Surface'])
    return material
"""
        preview_setup = """
    preview_materials = [ensure_atlas_preview_material(
        'FabricStudioAtlasMaterial',
        atlas_diffuse_path,
        atlas_alpha_path,
        atlas_rows,
    ) for _index in range(max(1, min(int(atlas_rows), 16)))]
    """
    if has_direct_material_assets:
        preview_setup = """
    preview_materials = build_generated_preview_materials(_PW_MATERIAL_ASSETS)
    """

    render_action = (
        "bpy.ops.render.render(write_still=True)"
        if render_still
        else "print({'status': 'setup_only_render_skipped'})"
    )
    result_status = "rendered" if render_still else "setup_ready"
    tile_camera_setup = ""
    if tile_render_mode:
        tile_camera_setup = f"_PW_TILE_ORTHO_SCALE = {repr(tile_ortho_scale)}\n" + """
def _pw_world_bounds(objects):
    try:
        from mathutils import Vector
    except Exception:
        return None
    coords = []
    for obj in objects:
        if obj is None:
            continue
        try:
            matrix = obj.matrix_world
            for corner in obj.bound_box:
                coords.append(matrix @ Vector(corner))
        except Exception:
            pass
    if not coords:
        return None
    min_corner = coords[0].copy()
    max_corner = coords[0].copy()
    for coord in coords[1:]:
        min_corner.x = min(min_corner.x, coord.x)
        min_corner.y = min(min_corner.y, coord.y)
        min_corner.z = min(min_corner.z, coord.z)
        max_corner.x = max(max_corner.x, coord.x)
        max_corner.y = max(max_corner.y, coord.y)
        max_corner.z = max(max_corner.z, coord.z)
    return min_corner, max_corner


def _pw_configure_tile_camera(scene, target_obj):
    fit_obj = bpy.data.objects.get('Space')
    bounds = _pw_world_bounds([fit_obj]) or _pw_world_bounds([target_obj])
    if bounds is None:
        print({'tile_camera': 'skipped', 'reason': 'no_bounds'})
        return

    min_corner, max_corner = bounds
    size_x = max(max_corner.x - min_corner.x, 0.001)
    size_y = max(max_corner.y - min_corner.y, 0.001)
    size_z = max(max_corner.z - min_corner.z, 0.001)
    center_x = (min_corner.x + max_corner.x) * 0.5
    center_y = (min_corner.y + max_corner.y) * 0.5
    center_z = (min_corner.z + max_corner.z) * 0.5
    ortho_scale = (
        float(_PW_TILE_ORTHO_SCALE)
        if _PW_TILE_ORTHO_SCALE is not None
        else max(size_x, size_y) * 1.0005
    )

    camera_name = 'SeamlessTileCamera'
    camera_obj = bpy.data.objects.get(camera_name)
    if camera_obj is None or getattr(camera_obj, 'type', None) != 'CAMERA':
        camera_data = bpy.data.cameras.new('SeamlessTileCameraData')
        camera_obj = bpy.data.objects.new(camera_name, camera_data)
        scene.collection.objects.link(camera_obj)
    camera_data = camera_obj.data
    camera_data.name = 'SeamlessTileCameraData'
    camera_data.type = 'ORTHO'
    camera_data.ortho_scale = ortho_scale
    camera_obj.location = (
        center_x,
        center_y,
        center_z + size_z + max(ortho_scale, 1.0) * 2.0,
    )
    # Blender cameras look down their local -Z axis; zero rotation gives a
    # square, top-down XY capture for the fitted fabric plane.
    camera_obj.rotation_euler = (0.0, 0.0, 0.0)
    scene.camera = camera_obj
    print({
        'tile_camera': 'configured',
        'camera': camera_obj.name,
        'ortho_scale': camera_data.ortho_scale,
        'source_bounds': 'Space' if fit_obj is not None else getattr(target_obj, 'name', None),
    })


try:
    _pw_configure_tile_camera(scene, target_obj)
except Exception as exc:
    print({'tile_camera': 'failed', 'error': str(exc)})
"""

    return f"""{sync_code}

{material_helpers}
{atlas_setup}
{APPLY_METADATA_PY}

_PW_MATERIAL_ASSETS = json.loads({repr(material_assets_json)})
_PW_MODIFIER_NAME = {modifier_name_json}
_PW_TEXTURE_SCALE_U_MULTIPLIER = float(globals().get('material_texture_scale_u', 1.0))
_PW_PREVIEW_RENDER_RESOLUTION = {repr(preview_render_resolution)}
_PW_PREVIEW_RENDER_SAMPLES = {repr(preview_render_samples)}
_PW_TEXTURE_INTERPOLATION = {repr(texture_interpolation)}
_PW_CUTOUT_BLEND_METHOD = {repr(cutout_blend_method)}
_PW_SURFACE_RENDER_METHOD = {repr(surface_render_method)}

scene = bpy.context.scene
try:
    scene.render.engine = 'CYCLES'
except Exception:
    pass
scene.render.use_file_extension = True
scene.render.image_settings.file_format = 'PNG'
scene.render.filepath = {render_path_json}
scene.render.resolution_x = int(_PW_PREVIEW_RENDER_RESOLUTION)
scene.render.resolution_y = int(_PW_PREVIEW_RENDER_RESOLUTION)
scene.render.resolution_percentage = 100
if getattr(scene, 'cycles', None) is not None:
    try:
        scene.cycles.samples = int(_PW_PREVIEW_RENDER_SAMPLES)
    except Exception:
        pass
    try:
        scene.cycles.use_denoising = True
    except Exception:
        pass

target_obj = bpy.data.objects.get({target_name_json})
if target_obj is not None:
    target_obj.hide_render = False
    target_obj.hide_viewport = False
{preview_setup}
    if target_obj.data is not None and hasattr(target_obj.data, 'materials'):
        target_obj.data.materials.clear()
        for preview_material in preview_materials:
            target_obj.data.materials.append(preview_material)
    weave_mod = target_obj.modifiers.get(_PW_MODIFIER_NAME)
    weave_group = weave_mod.node_group if weave_mod is not None and getattr(weave_mod, 'node_group', None) else None
    if weave_group is None:
        weave_group = (
            bpy.data.node_groups.get('Parametric Weave knotty')
            or bpy.data.node_groups.get('Weave From Draft')
        )
    if weave_group is not None and preview_materials:
        _pw_summary = apply_modifier_material_slots(
            weave_mod,
            weave_group,
            preview_materials,
            warp_material_ids,
            weft_material_ids,
            _PW_MATERIAL_ASSETS,
        )
        print('[phase3h] material slots pushed:', _pw_summary)
        if not has_modifier_input(weave_group, 'Material 1'):
            for node_name in ('Set Material', 'Set Material.001'):
                node = weave_group.nodes.get(node_name)
                if node is not None:
                    try:
                        node.inputs['Material'].default_value = preview_materials[0]
                    except Exception:
                        pass

bpy.context.view_layer.update()
{tile_camera_setup}
print({{
    'phase4f_preview_quality': {{
        'engine': scene.render.engine,
        'resolution_x': scene.render.resolution_x,
        'resolution_y': scene.render.resolution_y,
        'resolution_percentage': scene.render.resolution_percentage,
        'cycles_samples': getattr(getattr(scene, 'cycles', None), 'samples', None),
    }}
}})
{render_action}

print({{
    'status': {json.dumps(result_status)},
    'render_path': scene.render.filepath,
}})
"""


def build_project_material_payloads(ordered_assets: list[Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    atlas_entries: list[dict[str, Any]] = []
    material_assets: list[dict[str, Any]] = []

    for asset in ordered_assets:
        source_rgba_path = (
            YARN_ASSETS_ROOT / asset.id / asset.sourceFilename
            if getattr(asset, "sourceFilename", None)
            else None
        )
        source_diffuse_path = (
            YARN_ASSETS_ROOT / asset.id / asset.diffuseFilename
            if getattr(asset, "diffuseFilename", None)
            else None
        )
        source_alpha_path = (
            YARN_ASSETS_ROOT / asset.id / asset.alphaFilename
            if getattr(asset, "alphaFilename", None)
            else None
        )
        rgba_render_mode = getattr(asset, "renderTextureMode", None) in ("rgba_single", "rgba_tiled")
        rgba_preferred = bool(
            source_rgba_path
            and source_rgba_path.exists()
            and (rgba_render_mode or not (source_diffuse_path and source_alpha_path))
        )
        material_entry = build_material_asset_entry(asset)
        if rgba_preferred:
            atlas_entries.append({
                "id": asset.id,
                "rgba_path": source_rgba_path,
            })
            material_entry["texture_mode"] = "rgba_single"
            material_entry["rgba_path"] = str(source_rgba_path)
        elif source_diffuse_path and source_alpha_path:
            # Prefer the Cycles-safe downscale (≤ 16384 px) when only split
            # diffuse/alpha assets are available.
            diffuse_rel = asset.renderDiffuseFilename or asset.diffuseFilename
            alpha_rel = asset.renderAlphaFilename or asset.alphaFilename
            diffuse_path = YARN_ASSETS_ROOT / asset.id / diffuse_rel
            alpha_path = YARN_ASSETS_ROOT / asset.id / alpha_rel
            atlas_entries.append({
                "id": asset.id,
                "diffuse_path": diffuse_path,
                "alpha_path": alpha_path,
            })
            material_entry["diffuse_path"] = str(diffuse_path)
            material_entry["alpha_path"] = str(alpha_path)
        else:
            raise ValueError(f"Yarn asset {asset.label} is missing renderable texture outputs.")

        tile_payload = _material_tile_payload(
            asset,
            source_diffuse_path,
            source_alpha_path,
            source_rgba_path if rgba_preferred else None,
        )
        if tile_payload:
            material_entry.update(tile_payload)
        material_assets.append(material_entry)

    return atlas_entries, material_assets


def build_headless_render_command(
    config: HeadlessBlenderConfig,
    *,
    script_path: str | Path,
) -> list[str]:
    validate_headless_blender_config(config)
    return [
        str(config.blender_binary),
        "-b",
        str(config.blend_file),
        "--python",
        str(Path(script_path)),
    ]


def _tail_lines(path: Path, limit: int = 40) -> list[str]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    return lines[-limit:]


def _keep_tile_debug_outputs() -> bool:
    return os.environ.get("WEAVE_KEEP_TILE_DEBUG", "").lower() in ("1", "true", "yes", "on")


def _cleanup_tile_job_dir(job_dir: Path, *, keep_paths: set[Path]) -> None:
    keep_resolved = {path.resolve() for path in keep_paths}
    for child in job_dir.iterdir():
        if child.resolve() in keep_resolved:
            continue
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
        else:
            child.unlink(missing_ok=True)


def _job_snapshot(job: RenderJob) -> dict[str, Any]:
    tile_source_urls = [
        f"/api/blender/render-jobs/{job.id}/tile-sources/{index + 1}"
        for index, path in enumerate(job.tile_source_paths)
        if path.exists()
    ]
    return {
        "id": job.id,
        "status": job.status,
        "message": job.message,
        "draftTitle": job.draft_title,
        "targetObjectName": job.target_object_name,
        "draftObjectName": job.draft_object_name,
        "createdAt": job.created_at,
        "startedAt": job.started_at,
        "finishedAt": job.finished_at,
        "imageUrl": job.image_url,
        "tileSourceImageUrls": tile_source_urls,
        "logTail": job.log_tail,
    }


def _relative_asset_paths_to_absolute(asset: Any, filenames: list[str] | None) -> list[Path]:
    return [YARN_ASSETS_ROOT / asset.id / filename for filename in filenames or [] if filename]


def _material_tile_payload(
    asset: Any,
    diffuse_path: Path | None,
    alpha_path: Path | None,
    rgba_path: Path | None = None,
) -> dict[str, Any] | None:
    tile_count = int(getattr(asset, "renderTileCount", 0) or 0)
    rgba_pattern = getattr(asset, "renderRgbaTilePattern", None)
    diffuse_pattern = getattr(asset, "renderDiffuseTilePattern", None)
    alpha_pattern = getattr(asset, "renderAlphaTilePattern", None)
    rgba_tile_paths = _relative_asset_paths_to_absolute(
        asset,
        getattr(asset, "renderRgbaTileFilenames", None),
    )
    diffuse_tile_paths = _relative_asset_paths_to_absolute(
        asset,
        getattr(asset, "renderDiffuseTileFilenames", None),
    )
    alpha_tile_paths = _relative_asset_paths_to_absolute(
        asset,
        getattr(asset, "renderAlphaTileFilenames", None),
    )

    if (
        tile_count > 1
        and rgba_pattern
        and len(rgba_tile_paths) == tile_count
        and all(path.exists() for path in rgba_tile_paths)
    ):
        return {
            "texture_mode": "udim_rgba_tiled",
            "texture_tile_count": tile_count,
            "texture_tile_width_px": getattr(asset, "renderTileWidthPx", None),
            "texture_tile_height_px": getattr(asset, "renderTileHeightPx", None),
            "rgba_tile_pattern": str(YARN_ASSETS_ROOT / asset.id / rgba_pattern),
            "rgba_tile_paths": [str(path) for path in rgba_tile_paths],
        }

    if (
        tile_count > 1
        and diffuse_pattern
        and alpha_pattern
        and len(diffuse_tile_paths) == tile_count
        and len(alpha_tile_paths) == tile_count
        and all(path.exists() for path in [*diffuse_tile_paths, *alpha_tile_paths])
    ):
        return {
            "texture_mode": "udim_tiled",
            "texture_tile_count": tile_count,
            "texture_tile_width_px": getattr(asset, "renderTileWidthPx", None),
            "texture_tile_height_px": getattr(asset, "renderTileHeightPx", None),
            "diffuse_tile_pattern": str(YARN_ASSETS_ROOT / asset.id / diffuse_pattern),
            "alpha_tile_pattern": str(YARN_ASSETS_ROOT / asset.id / alpha_pattern),
            "diffuse_tile_paths": [str(path) for path in diffuse_tile_paths],
            "alpha_tile_paths": [str(path) for path in alpha_tile_paths],
        }

    if rgba_path and rgba_path.exists():
        rgba_tiled = ensure_cycles_tiled_rgba_texture_set(
            rgba_path,
            YARN_ASSETS_ROOT / asset.id / "cycles_tiled",
        )
        if rgba_tiled:
            return {
                "texture_mode": "udim_rgba_tiled",
                "texture_tile_count": int(rgba_tiled["tile_count"]),
                "texture_tile_width_px": int(rgba_tiled["tile_width_px"]),
                "texture_tile_height_px": int(rgba_tiled["tile_height_px"]),
                "rgba_tile_pattern": str(rgba_tiled["rgba_pattern"]),
                "rgba_tile_paths": [str(path) for path in rgba_tiled["rgba_paths"]],
            }
        return None

    if diffuse_path is None or alpha_path is None:
        return None
    if not diffuse_path.exists() or not alpha_path.exists():
        return None

    tiled = ensure_cycles_tiled_texture_set(
        diffuse_path,
        alpha_path,
        YARN_ASSETS_ROOT / asset.id / "cycles_tiled",
    )
    if not tiled:
        return None

    return {
        "texture_mode": "udim_tiled",
        "texture_tile_count": int(tiled["tile_count"]),
        "texture_tile_width_px": int(tiled["tile_width_px"]),
        "texture_tile_height_px": int(tiled["tile_height_px"]),
        "diffuse_tile_pattern": str(tiled["diffuse_pattern"]),
        "alpha_tile_pattern": str(tiled["alpha_pattern"]),
        "diffuse_tile_paths": [str(path) for path in tiled["diffuse_paths"]],
        "alpha_tile_paths": [str(path) for path in tiled["alpha_paths"]],
    }


def _update_job(job_id: str, **changes: Any) -> None:
    with _LOCK:
        job = _JOBS[job_id]
        for key, value in changes.items():
            setattr(job, key, value)


def _run_headless_render(job_id: str, command: list[str], config: HeadlessBlenderConfig) -> None:
    with _LOCK:
        job = _JOBS[job_id]
        job.status = "running"
        job.started_at = _utc_now()
        job.message = "Blender is generating the preview render in the background."

    try:
        with job.stdout_path.open("w", encoding="utf-8") as stdout_handle, job.stderr_path.open(
            "w",
            encoding="utf-8",
        ) as stderr_handle:
            completed = subprocess.run(
                command,
                cwd=str(config.blend_file.parent),
                stdout=stdout_handle,
                stderr=stderr_handle,
                check=False,
                text=True,
            )

        if completed.returncode != 0:
            combined = _tail_lines(job.stderr_path, 24) or _tail_lines(job.stdout_path, 24)
            raise RuntimeError(
                "Headless Blender exited with a non-zero status. "
                + (" | ".join(combined) if combined else f"Exit code {completed.returncode}.")
            )

        if not job.render_path.exists():
            raise RuntimeError("Blender finished without creating a preview image.")

        _update_job(
            job_id,
            status="succeeded",
            finished_at=_utc_now(),
            message="Preview render ready.",
            image_url=f"/api/blender/render-jobs/{job_id}/image",
            log_tail=_tail_lines(job.stdout_path, 18),
        )
    except Exception as exc:
        log_tail = _tail_lines(job.stderr_path, 20)
        if not log_tail:
            log_tail = _tail_lines(job.stdout_path, 20)
        _update_job(
            job_id,
            status="failed",
            finished_at=_utc_now(),
            message=str(exc),
            log_tail=log_tail,
        )


def _run_live_render(job_id: str, script_text: str) -> None:
    """Send the render script to the live Blender on the MCP socket and let
    that session execute it (rendering against the open scene the user is
    already looking at). Dev-only path — see docs/BlenderFixes/ for rationale."""
    with _LOCK:
        job = _JOBS[job_id]
        job.status = "running"
        job.started_at = _utc_now()
        job.message = "Live Blender (MCP) is rendering in the open session."

    try:
        # Long renders need a generous timeout. Override locally without
        # touching the global default that other call sites depend on.
        prev_timeout = os.environ.get("BLENDER_TIMEOUT_SECONDS")
        os.environ["BLENDER_TIMEOUT_SECONDS"] = os.environ.get("BLENDER_LIVE_TIMEOUT_SECONDS", "900")
        try:
            response = send_blender_command("execute_code", {"code": script_text})
        finally:
            if prev_timeout is None:
                os.environ.pop("BLENDER_TIMEOUT_SECONDS", None)
            else:
                os.environ["BLENDER_TIMEOUT_SECONDS"] = prev_timeout

        if response.get("status") != "success":
            raise RuntimeError(
                f"Live Blender refused the render script: {response.get('message') or response}"
            )

        stdout_text = ((response.get("result") or {}).get("result") or "")
        try:
            job.stdout_path.write_text(stdout_text, encoding="utf-8")
        except Exception:
            pass

        if not job.render_path.exists():
            raise RuntimeError(
                "Live Blender finished without creating a preview image. "
                "Check that scene.render.filepath in the emitted script points at a writable location."
            )

        _update_job(
            job_id,
            status="succeeded",
            finished_at=_utc_now(),
            message="Live preview ready (rendered in open Blender session).",
            image_url=f"/api/blender/render-jobs/{job_id}/image",
            log_tail=stdout_text.splitlines()[-18:],
        )
    except Exception as exc:
        _update_job(
            job_id,
            status="failed",
            finished_at=_utc_now(),
            message=f"Live render failed: {exc}",
            log_tail=[],
        )


def _execute_live_script(script_text: str) -> str:
    prev_timeout = os.environ.get("BLENDER_TIMEOUT_SECONDS")
    os.environ["BLENDER_TIMEOUT_SECONDS"] = os.environ.get("BLENDER_LIVE_TIMEOUT_SECONDS", "900")
    try:
        response = send_blender_command("execute_code", {"code": script_text})
    finally:
        if prev_timeout is None:
            os.environ.pop("BLENDER_TIMEOUT_SECONDS", None)
        else:
            os.environ["BLENDER_TIMEOUT_SECONDS"] = prev_timeout

    if response.get("status") != "success":
        raise RuntimeError(
            f"Live Blender refused the render script: {response.get('message') or response}"
        )
    return str(((response.get("result") or {}).get("result") or ""))


def _tile_grid_for_count(tile_count: int) -> tuple[int, int]:
    if tile_count == 12:
        return 4, 3
    side = int(math.ceil(math.sqrt(tile_count)))
    return side, int(math.ceil(tile_count / side))


def _next_multiple(value: int, period: int) -> int:
    period = max(1, int(period))
    return int(math.ceil(max(1, int(value)) / period) * period)


def _lcm_positive(values: list[int]) -> int:
    result = 1
    for value in values:
        value = int(value)
        if value > 0:
            result = math.lcm(result, value)
    return max(1, result)


def _coerce_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(round(float(value)))
    except (TypeError, ValueError):
        parsed = default
    return min(maximum, max(minimum, parsed))


def _coerce_float(value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return min(maximum, max(minimum, parsed))


def _normalize_tile_options(options: dict[str, Any] | None) -> dict[str, Any]:
    raw = options or {}
    tile_count = _coerce_int(raw.get("tileCount"), DEFAULT_TILE_COUNT, 1, 12)
    if tile_count not in ALLOWED_TILE_COUNTS:
        tile_count = DEFAULT_TILE_COUNT
    tile_resolution = DEFAULT_TILE_RESOLUTION
    guard_threads = DEFAULT_TILE_GUARD_THREADS
    variation_strength = DEFAULT_TILE_VARIATION_STRENGTH
    columns, rows = _tile_grid_for_count(tile_count)
    return {
        "tileCount": tile_count,
        "tileResolution": tile_resolution,
        "guardThreads": guard_threads,
        "variationStrength": variation_strength,
        "columns": columns,
        "rows": rows,
    }


def _draft_tile_render_settings(
    draft: dict[str, Any],
    *,
    tile_index: int,
    base_warp_threads: int,
    base_weft_threads: int,
    full_warp_threads: int,
    full_weft_threads: int,
    variation_strength: float,
) -> dict[str, Any]:
    settings = dict(draft.get("renderSettings") if isinstance(draft.get("renderSettings"), dict) else {})
    base_seed = _coerce_int(settings.get("seed"), 0, 0, 1_000_000)
    settings["warpThreads"] = full_warp_threads
    settings["weftThreads"] = full_weft_threads
    settings["seed"] = (base_seed + tile_index * 7919) % 1_000_000

    if variation_strength > 0:
        # Keep variation modest. This pass uses overlap blending, not a true
        # edge-profile contract, so wild per-tile drift would make seams worse.
        def jitter(key: str, prime: int, amount: float) -> None:
            base = _coerce_float(settings.get(key), 0.0, 0.0, 1.0)
            unit = ((tile_index * prime) % 997) / 996.0
            settings[key] = min(1.0, max(0.0, base + (unit - 0.5) * amount * variation_strength))

        jitter("patternNoiseX", 313, 0.08)
        jitter("patternNoiseY", 577, 0.08)
        uv_base = _coerce_float(settings.get("uvRandomU"), 1.0, 0.0, 20.0)
        uv_unit = ((tile_index * 733) % 997) / 996.0
        settings["uvRandomU"] = min(20.0, max(0.0, uv_base + (uv_unit - 0.5) * 1.5 * variation_strength))

    return {
        **draft,
        "renderSettings": settings,
        "tileExportMeta": {
            "tileIndex": tile_index,
            "baseWarpThreads": base_warp_threads,
            "baseWeftThreads": base_weft_threads,
            "fullWarpThreads": full_warp_threads,
            "fullWeftThreads": full_weft_threads,
        },
    }


def _tile_weight_mask(width: int, height: int, guard_px: int) -> np.ndarray:
    if guard_px <= 0:
        return np.ones((height, width, 1), dtype=np.float32)

    def axis_weights(length: int) -> np.ndarray:
        weights = np.ones((length,), dtype=np.float32)
        edge = min(guard_px, max(0, length // 2))
        if edge <= 0:
            return weights
        ramp_up = np.linspace(0.001, 1.0, edge, endpoint=True, dtype=np.float32)
        ramp_down = np.linspace(1.0, 0.001, edge, endpoint=True, dtype=np.float32)
        weights[:edge] = ramp_up
        weights[-edge:] = np.minimum(weights[-edge:], ramp_down)
        return weights

    x = axis_weights(width)
    y = axis_weights(height)
    return (y[:, None] * x[None, :])[:, :, None]


def _wrapped_segments(src_len: int, dest_start: int, canvas_len: int) -> list[tuple[int, int, int, int]]:
    if src_len <= 0 or canvas_len <= 0:
        return []

    segments: list[tuple[int, int, int, int]] = []
    remaining = int(src_len)
    src0 = 0
    dest = int(dest_start)
    while remaining > 0:
        dest_mod = dest % canvas_len
        step = min(remaining, canvas_len - dest_mod)
        segments.append((src0, src0 + step, dest_mod, dest_mod + step))
        src0 += step
        dest += step
        remaining -= step
    return segments


def _stitch_tile_grid(
    tile_paths: list[Path],
    *,
    output_path: Path,
    columns: int,
    rows: int,
    tile_resolution: int,
    guard_px: int,
) -> None:
    final_width = columns * tile_resolution
    final_height = rows * tile_resolution
    if guard_px <= 0:
        output = Image.new("RGBA", (final_width, final_height), (0, 0, 0, 0))
        for index, tile_path in enumerate(tile_paths):
            col = index % columns
            row = index // columns
            if row >= rows:
                break
            with Image.open(tile_path) as image:
                rgba = image.convert("RGBA")
                if rgba.size != (tile_resolution, tile_resolution):
                    raise ValueError(
                        f"Zero-guard tile stitching expected {tile_resolution}x{tile_resolution} renders, "
                        f"but {tile_path.name} is {rgba.size[0]}x{rgba.size[1]}."
                    )
                output.paste(rgba, (col * tile_resolution, row * tile_resolution))
        output.save(output_path)
        return

    accum = np.zeros((final_height, final_width, 4), dtype=np.float32)
    weights = np.zeros((final_height, final_width, 1), dtype=np.float32)

    for index, tile_path in enumerate(tile_paths):
        col = index % columns
        row = index // columns
        if row >= rows:
            break

        with Image.open(tile_path) as image:
            rgba = image.convert("RGBA")
            tile = np.asarray(rgba, dtype=np.float32)
        height, width = tile.shape[:2]
        mask = _tile_weight_mask(width, height, guard_px)

        dst_x = col * tile_resolution - guard_px
        dst_y = row * tile_resolution - guard_px
        x_segments = _wrapped_segments(width, dst_x, final_width)
        y_segments = _wrapped_segments(height, dst_y, final_height)
        for src_x0, src_x1, dst_x0, dst_x1 in x_segments:
            for src_y0, src_y1, dst_y0, dst_y1 in y_segments:
                tile_crop = tile[src_y0:src_y1, src_x0:src_x1]
                mask_crop = mask[src_y0:src_y1, src_x0:src_x1]
                accum[dst_y0:dst_y1, dst_x0:dst_x1] += tile_crop * mask_crop
                weights[dst_y0:dst_y1, dst_x0:dst_x1] += mask_crop

    normalized = accum / np.maximum(weights, 1e-6)
    output = Image.fromarray(np.clip(normalized, 0, 255).astype(np.uint8))
    output.save(output_path)


def _run_tile_render_job(
    job_id: str,
    *,
    normalized_draft: dict[str, Any],
    target_object_name: str,
    draft_object_name: str,
    atlas_bundle: AtlasBundle,
    warp_material_ids: list[int],
    weft_material_ids: list[int],
    material_assets: list[dict[str, Any]],
    tile_options: dict[str, Any],
) -> None:
    with _LOCK:
        job = _JOBS[job_id]
        job.status = "running"
        job.started_at = _utc_now()
        job.message = "Preparing seamless tile export."

    config = load_headless_blender_config()
    try:
        validate_headless_blender_config(config)
        tile_count = int(tile_options["tileCount"])
        columns = int(tile_options["columns"])
        rows = int(tile_options["rows"])
        tile_resolution = int(tile_options["tileResolution"])
        guard_threads = int(tile_options["guardThreads"])
        variation_strength = float(tile_options["variationStrength"])

        settings = normalized_draft.get("renderSettings") if isinstance(normalized_draft.get("renderSettings"), dict) else {}
        drawdown = validate_drawdown_matrix(normalized_draft.get("drawdown"))
        warp_repeat = _lcm_positive([len(drawdown[0]), len(warp_material_ids or [])])
        weft_repeat = _lcm_positive([len(drawdown), len(weft_material_ids or [])])
        base_warp_threads = _coerce_int(
            settings.get("warpThreads"),
            max(len(drawdown[0]), 80),
            max(len(drawdown[0]), 1),
            400,
        )
        base_weft_threads = _coerce_int(
            settings.get("weftThreads"),
            max(len(drawdown), 80),
            max(len(drawdown), 1),
            400,
        )
        base_warp_threads = _next_multiple(base_warp_threads, warp_repeat)
        base_weft_threads = _next_multiple(base_weft_threads, weft_repeat)
        full_warp_threads = base_warp_threads + 2 * guard_threads
        full_weft_threads = base_weft_threads + 2 * guard_threads
        crop_ratio = max(
            full_warp_threads / max(base_warp_threads, 1),
            full_weft_threads / max(base_weft_threads, 1),
        )
        full_resolution = min(8192, max(tile_resolution, int(math.ceil(tile_resolution * crop_ratio))))
        guard_px = max(0, int(round((full_resolution - tile_resolution) / 2)))

        tile_dir = job.job_dir / "tiles"
        tile_dir.mkdir(parents=True, exist_ok=True)
        source_tiles_dir = job.job_dir / "source_tiles"
        source_tiles_dir.mkdir(parents=True, exist_ok=True)
        rendered_tiles: list[Path] = []
        combined_log: list[str] = [
            f"tile_count={tile_count}",
            f"grid={columns}x{rows}",
            f"tile_resolution={tile_resolution}",
            f"full_resolution={full_resolution}",
            f"guard_threads={guard_threads}",
            f"guard_px={guard_px}",
            f"warp_repeat={warp_repeat}",
            f"weft_repeat={weft_repeat}",
            f"base_threads={base_warp_threads}x{base_weft_threads}",
            f"full_threads={full_warp_threads}x{full_weft_threads}",
            f"variation_strength={variation_strength}",
            f"seam_repair=r{DEFAULT_TILE_REPAIR_SEAM_RADIUS}_color{DEFAULT_TILE_REPAIR_COLOR_MATCH_STRENGTH:g}",
        ]

        for index in range(tile_count):
            tile_render_path = tile_dir / f"tile_{index + 1:02d}_overscan.png"
            tile_script_path = tile_dir / f"tile_{index + 1:02d}_render.py"
            tile_draft = _draft_tile_render_settings(
                normalized_draft,
                tile_index=index,
                base_warp_threads=base_warp_threads,
                base_weft_threads=base_weft_threads,
                full_warp_threads=full_warp_threads,
                full_weft_threads=full_weft_threads,
                variation_strength=variation_strength,
            )
            script_text = build_headless_render_script(
                tile_draft,
                render_path=tile_render_path,
                target_object_name=target_object_name,
                draft_object_name=draft_object_name,
                atlas_bundle=atlas_bundle,
                warp_material_ids=warp_material_ids,
                weft_material_ids=weft_material_ids,
                material_assets=material_assets,
                render_resolution=full_resolution,
                render_samples=DEFAULT_TILE_RENDER_SAMPLES,
                tile_render_mode=True,
                tile_ortho_scale=DEFAULT_TILE_ORTHO_SCALE,
            )
            tile_script_path.write_text(script_text, encoding="utf-8")
            _update_job(
                job_id,
                message=f"Rendering tile {index + 1} of {tile_count}.",
                log_tail=combined_log[-18:],
            )

            if _is_live_render_mode():
                stdout_text = _execute_live_script(script_text)
                (tile_dir / f"tile_{index + 1:02d}_stdout.log").write_text(stdout_text, encoding="utf-8")
                combined_log.extend(stdout_text.splitlines()[-8:])
            else:
                tile_stdout = tile_dir / f"tile_{index + 1:02d}_stdout.log"
                tile_stderr = tile_dir / f"tile_{index + 1:02d}_stderr.log"
                command = build_headless_render_command(config, script_path=tile_script_path)
                with tile_stdout.open("w", encoding="utf-8") as stdout_handle, tile_stderr.open(
                    "w",
                    encoding="utf-8",
                ) as stderr_handle:
                    completed = subprocess.run(
                        command,
                        cwd=str(config.blend_file.parent),
                        stdout=stdout_handle,
                        stderr=stderr_handle,
                        check=False,
                        text=True,
                    )
                if completed.returncode != 0:
                    combined = _tail_lines(tile_stderr, 24) or _tail_lines(tile_stdout, 24)
                    raise RuntimeError(
                        f"Tile {index + 1} render failed. "
                        + (" | ".join(combined) if combined else f"Exit code {completed.returncode}.")
                    )
                combined_log.extend(_tail_lines(tile_stdout, 8))

            if not tile_render_path.exists():
                raise RuntimeError(f"Tile {index + 1} render finished without creating {tile_render_path.name}.")
            rendered_tiles.append(tile_render_path)
            source_tile_path = source_tiles_dir / f"source_tile_{index + 1:02d}.png"
            shutil.copyfile(tile_render_path, source_tile_path)
            with _LOCK:
                _JOBS[job_id].tile_source_paths.append(source_tile_path)

        _update_job(
            job_id,
            message="Stitching tile renders before seam repair.",
            log_tail=combined_log[-18:],
        )
        raw_stitched_path = job.job_dir / "tile_export_raw_stitched.png"
        _stitch_tile_grid(
            rendered_tiles,
            output_path=raw_stitched_path,
            columns=columns,
            rows=rows,
            tile_resolution=tile_resolution,
            guard_px=guard_px,
        )
        if not raw_stitched_path.exists():
            raise RuntimeError("Tile stitching finished without creating the raw stitched texture.")

        _update_job(
            job_id,
            message="Repairing tile seams with the final inpaint pass.",
            log_tail=combined_log[-18:],
        )
        repair_result = repair_tile_with_two_pass_inpaint(
            raw_stitched_path,
            job.render_path,
            prefix="tile_seam_repair",
            seam_radius_px=DEFAULT_TILE_REPAIR_SEAM_RADIUS,
            context_px=DEFAULT_TILE_REPAIR_CONTEXT,
            color_match_strength=DEFAULT_TILE_REPAIR_COLOR_MATCH_STRENGTH,
            save_debug_outputs=_keep_tile_debug_outputs(),
            save_retile_preview=False,
        )
        combined_log.extend(
            [
                f"repair_seam_radius={repair_result.seam_radius_px}",
                f"repair_color_match={repair_result.color_match_strength:g}",
                f"repair_elapsed_seconds={repair_result.elapsed_seconds:g}",
            ]
        )
        if not job.render_path.exists():
            raise RuntimeError("Tile seam repair finished without creating the final texture.")

        if not _keep_tile_debug_outputs():
            _cleanup_tile_job_dir(job.job_dir, keep_paths={job.render_path, source_tiles_dir})

        _update_job(
            job_id,
            status="succeeded",
            finished_at=_utc_now(),
            message=f"Seam-repaired tile texture ready ({columns}x{rows}).",
            image_url=f"/api/blender/render-jobs/{job_id}/image",
            log_tail=combined_log[-18:],
        )
    except Exception as exc:
        _update_job(
            job_id,
            status="failed",
            finished_at=_utc_now(),
            message=f"Tile export failed: {exc}",
            log_tail=_tail_lines(job.stderr_path, 20) or _tail_lines(job.stdout_path, 20),
        )


def _create_render_job(
    draft_title: str,
    target_object_name: str,
    draft_object_name: str,
    job_dir: Path,
    script_text: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    config = load_headless_blender_config()
    validate_headless_blender_config(config)

    render_path = job_dir / "preview.png"
    script_path = job_dir / "render_job.py"
    stdout_path = job_dir / "stdout.log"
    stderr_path = job_dir / "stderr.log"
    payload_path = job_dir / "draft.json"

    payload_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    script_path.write_text(script_text, encoding="utf-8")

    job = RenderJob(
        id=job_dir.name,
        status="queued",
        message="Render job queued. Blender will build the draft and render a preview next.",
        draft_title=draft_title,
        target_object_name=target_object_name,
        draft_object_name=draft_object_name,
        created_at=_utc_now(),
        job_dir=job_dir,
        render_path=render_path,
        script_path=script_path,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
    )

    with _LOCK:
        _JOBS[job.id] = job

    if _is_live_render_mode():
        # Dev mode: send the script to the live Blender via MCP. No subprocess.
        thread = threading.Thread(
            target=_run_live_render,
            args=(job.id, script_text),
            daemon=True,
            name=f"render-job-live-{job.id}",
        )
    else:
        # Production: spawn headless Blender against the .blend on disk.
        command = build_headless_render_command(config, script_path=script_path)
        thread = threading.Thread(
            target=_run_headless_render,
            args=(job.id, command, config),
            daemon=True,
            name=f"render-job-{job.id}",
        )
    thread.start()
    return _job_snapshot(job)


def submit_render_job(
    draft: dict[str, Any],
    *,
    target_object_name: str = "ParametricWeave",
    draft_object_name: str = "WebDraft_Live",
) -> dict[str, Any]:
    ensure_runtime_dirs()
    drawdown = validate_drawdown_matrix(draft.get("drawdown"))
    draft_title = str(draft.get("title") or "Untitled Draft")
    normalized_draft = {
        **draft,
        "drawdown": drawdown,
    }

    job_id = uuid.uuid4().hex[:12]
    job_dir = DEFAULT_RUNTIME_ROOT / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    script_text = build_headless_render_script(
        normalized_draft,
        render_path=job_dir / "preview.png",
        target_object_name=target_object_name,
        draft_object_name=draft_object_name,
    )
    return _create_render_job(
        draft_title,
        target_object_name,
        draft_object_name,
        job_dir,
        script_text,
        normalized_draft,
    )


def submit_project_render_job(
    project_payload: dict[str, Any],
    *,
    target_object_name: str = "ParametricWeave",
    draft_object_name: str = "WebDraft_Live",
) -> dict[str, Any]:
    ensure_runtime_dirs()
    draft = project_payload.get("draft")
    if not isinstance(draft, dict):
        raise ValueError("render-project requires a draft object.")

    drawdown = validate_drawdown_matrix(draft.get("drawdown"))
    normalized_draft = {
        **draft,
        "drawdown": drawdown,
    }
    bindings = normalize_color_bindings(project_payload.get("colorBindings"))
    assets_lookup = get_ready_yarn_assets_lookup()
    bindings, warp_material_ids, weft_material_ids, ordered_assets = validate_project_bindings(
        normalized_draft,
        bindings,
        assets_lookup,
    )
    if not ordered_assets:
        raise ValueError("At least one ready yarn asset must be assigned before rendering.")

    job_id = uuid.uuid4().hex[:12]
    job_dir = DEFAULT_RUNTIME_ROOT / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    atlas_entries, material_assets = build_project_material_payloads(ordered_assets)

    atlas_bundle = build_yarn_atlas(atlas_entries, job_dir / "atlas")
    project_snapshot = build_project_snapshot(normalized_draft, bindings, ordered_assets)
    save_project_snapshot(project_snapshot, job_dir / "project.json")
    save_project_snapshot(project_snapshot, PROJECTS_ROOT / f"{job_id}.json")

    script_text = build_headless_render_script(
        normalized_draft,
        render_path=job_dir / "preview.png",
        target_object_name=target_object_name,
        draft_object_name=draft_object_name,
        atlas_bundle=atlas_bundle,
        warp_material_ids=warp_material_ids,
        weft_material_ids=weft_material_ids,
        material_assets=material_assets,
    )
    payload = project_snapshot.to_dict()
    payload["atlas"] = atlas_bundle.to_dict()
    payload["warpMaterialIds"] = warp_material_ids
    payload["weftMaterialIds"] = weft_material_ids
    draft_title = str(normalized_draft.get("title") or "Untitled Draft")

    return _create_render_job(
        draft_title,
        target_object_name,
        draft_object_name,
        job_dir,
        script_text,
        payload,
    )


def submit_project_tile_render_job(
    project_payload: dict[str, Any],
    *,
    tile_options: dict[str, Any] | None = None,
    target_object_name: str = "ParametricWeave",
    draft_object_name: str = "WebDraft_Live",
) -> dict[str, Any]:
    ensure_runtime_dirs()
    draft = project_payload.get("draft")
    if not isinstance(draft, dict):
        raise ValueError("render-project-tiles requires a draft object.")

    drawdown = validate_drawdown_matrix(draft.get("drawdown"))
    normalized_draft = {
        **draft,
        "drawdown": drawdown,
    }
    bindings = normalize_color_bindings(project_payload.get("colorBindings"))
    assets_lookup = get_ready_yarn_assets_lookup()
    bindings, warp_material_ids, weft_material_ids, ordered_assets = validate_project_bindings(
        normalized_draft,
        bindings,
        assets_lookup,
    )
    if not ordered_assets:
        raise ValueError("At least one ready yarn asset must be assigned before tile export.")

    options = _normalize_tile_options(tile_options)
    job_id = f"tiles_{uuid.uuid4().hex[:12]}"
    job_dir = DEFAULT_RUNTIME_ROOT / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    atlas_entries, material_assets = build_project_material_payloads(ordered_assets)
    atlas_bundle = build_yarn_atlas(atlas_entries, job_dir / "atlas")
    project_snapshot = build_project_snapshot(normalized_draft, bindings, ordered_assets)
    save_project_snapshot(project_snapshot, job_dir / "project.json")

    payload = project_snapshot.to_dict()
    payload["atlas"] = atlas_bundle.to_dict()
    payload["warpMaterialIds"] = warp_material_ids
    payload["weftMaterialIds"] = weft_material_ids
    payload["tileExport"] = options
    (job_dir / "tile_export.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    draft_title = str(normalized_draft.get("title") or "Untitled Draft")
    job = RenderJob(
        id=job_id,
        status="queued",
        message="Tile export queued. Blender will render and repair the 2x2 texture next.",
        draft_title=draft_title,
        target_object_name=target_object_name,
        draft_object_name=draft_object_name,
        created_at=_utc_now(),
        job_dir=job_dir,
        render_path=job_dir / "tile_export.png",
        script_path=job_dir / "tile_export.json",
        stdout_path=job_dir / "stdout.log",
        stderr_path=job_dir / "stderr.log",
    )
    with _LOCK:
        _JOBS[job.id] = job

    thread = threading.Thread(
        target=_run_tile_render_job,
        kwargs={
            "job_id": job.id,
            "normalized_draft": normalized_draft,
            "target_object_name": target_object_name,
            "draft_object_name": draft_object_name,
            "atlas_bundle": atlas_bundle,
            "warp_material_ids": warp_material_ids,
            "weft_material_ids": weft_material_ids,
            "material_assets": material_assets,
            "tile_options": options,
        },
        daemon=True,
        name=f"tile-render-job-{job.id}",
    )
    thread.start()
    return _job_snapshot(job)


def get_render_job(job_id: str) -> dict[str, Any] | None:
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            return None
        return _job_snapshot(job)


def get_render_image_path(job_id: str) -> Path | None:
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is None or not job.render_path.exists():
            return None
        return job.render_path


def get_tile_source_image_path(job_id: str, source_index: int) -> Path | None:
    if source_index < 1:
        return None
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            return None
        try:
            image_path = job.tile_source_paths[source_index - 1]
        except IndexError:
            return None
        if not image_path.exists():
            return None
        return image_path
