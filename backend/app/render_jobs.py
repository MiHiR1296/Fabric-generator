from __future__ import annotations

import json
import os
import subprocess
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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
    has_direct_material_assets = (
        bool(normalized_material_assets)
        and len(normalized_material_assets) <= MAX_DIRECT_PREVIEW_MATERIALS
        and all(entry.get("diffuse_path") and entry.get("alpha_path") for entry in normalized_material_assets)
    )
    material_count = (
        len(normalized_material_assets)
        if has_direct_material_assets
        else (atlas_bundle.rows if atlas_bundle is not None else None)
    )
    preview_render_resolution = _int_env(
        "WEAVE_PREVIEW_RENDER_RESOLUTION",
        DEFAULT_PREVIEW_RENDER_RESOLUTION,
        minimum=512,
        maximum=8192,
    )
    preview_render_samples = _int_env(
        "WEAVE_PREVIEW_RENDER_SAMPLES",
        DEFAULT_PREVIEW_RENDER_SAMPLES,
        minimum=1,
        maximum=4096,
    )
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
    alpha_output = alpha_tex.outputs['Alpha'] if use_rgba_tiled else alpha_tex.outputs['Color']
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
        if not asset.diffuseFilename or not asset.alphaFilename:
            raise ValueError(f"Yarn asset {asset.label} is missing processed outputs.")
        source_rgba_path = YARN_ASSETS_ROOT / asset.id / asset.sourceFilename
        source_diffuse_path = YARN_ASSETS_ROOT / asset.id / asset.diffuseFilename
        source_alpha_path = YARN_ASSETS_ROOT / asset.id / asset.alphaFilename
        # Prefer the Cycles-safe downscale (≤ 16384 px). It's the original file
        # when the source was already small enough — see yarn_assets.py:_ensure_cycles_safe_texture.
        diffuse_rel = asset.renderDiffuseFilename or asset.diffuseFilename
        alpha_rel = asset.renderAlphaFilename or asset.alphaFilename
        diffuse_path = YARN_ASSETS_ROOT / asset.id / diffuse_rel
        alpha_path = YARN_ASSETS_ROOT / asset.id / alpha_rel
        atlas_entries.append(
            {
                "id": asset.id,
                "diffuse_path": diffuse_path,
                "alpha_path": alpha_path,
            }
        )
        material_entry = build_material_asset_entry(asset)
        material_entry["diffuse_path"] = str(diffuse_path)
        material_entry["alpha_path"] = str(alpha_path)
        tile_payload = _material_tile_payload(asset, source_diffuse_path, source_alpha_path, source_rgba_path)
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


def _job_snapshot(job: RenderJob) -> dict[str, Any]:
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
        "logTail": job.log_tail,
    }


def _relative_asset_paths_to_absolute(asset: Any, filenames: list[str] | None) -> list[Path]:
    return [YARN_ASSETS_ROOT / asset.id / filename for filename in filenames or [] if filename]


def _material_tile_payload(
    asset: Any,
    diffuse_path: Path,
    alpha_path: Path,
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
