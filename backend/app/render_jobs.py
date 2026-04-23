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
from .blender_sync import build_blender_sync_code, validate_drawdown_matrix
from .fabric_project import (
    build_project_snapshot,
    normalize_color_bindings,
    save_project_snapshot,
    validate_project_bindings,
)
from .runtime_paths import BLEND_FILE_PATH, PROJECTS_ROOT, RENDER_JOBS_ROOT, YARN_ASSETS_ROOT, ensure_runtime_dirs
from .yarn_assets import get_ready_yarn_assets_lookup


DEFAULT_BLENDER_BINARY = Path("/Applications/Blender.app/Contents/MacOS/Blender")
DEFAULT_BLEND_FILE = BLEND_FILE_PATH
DEFAULT_RUNTIME_ROOT = RENDER_JOBS_ROOT


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
    preview_only: bool = False,
) -> str:
    drawdown = validate_drawdown_matrix(draft.get("drawdown"))
    render_path_json = json.dumps(str(Path(render_path)))
    target_name_json = json.dumps(target_object_name)
    normalized_material_assets = [
        {
            "id": str(entry["id"]),
            "diffusePath": str(entry["diffuse_path"]),
            "alphaPath": str(entry["alpha_path"]),
        }
        for entry in (material_assets or [])
    ]
    material_count = (
        len(normalized_material_assets)
        if normalized_material_assets
        else (atlas_bundle.rows if atlas_bundle is not None else None)
    )
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
    material_assets_setup = f"""
material_assets = {json.dumps(normalized_material_assets)}
"""
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

def find_template_material():
    for name in ('MAterial_01', 'Material_01'):
        material = bpy.data.materials.get(name)
        if material is not None:
            return material
    return None

def find_principled_node(material):
    for node in material.node_tree.nodes:
        if node.bl_idname == 'ShaderNodeBsdfPrincipled':
            return node
    return None

def find_connected_image_texture(material, socket_name):
    shader = find_principled_node(material)
    if shader is None:
        return None
    socket = shader.inputs.get(socket_name)
    if socket is None:
        return None
    queue = [link.from_node for link in socket.links]
    seen = set()
    while queue:
        node = queue.pop(0)
        if node.name in seen:
            continue
        seen.add(node.name)
        if node.bl_idname == 'ShaderNodeTexImage':
            return node
        for input_socket in node.inputs:
            for link in input_socket.links:
                queue.append(link.from_node)
    return None

def ensure_template_preview_material(template_material, asset_entry, index):
    material_name = f"FabricStudioMaterial_{index:02d}_{asset_entry['id'][:8]}"
    material = bpy.data.materials.get(material_name)
    if material is None:
        material = template_material.copy()
        material.name = material_name

    diffuse_node = find_connected_image_texture(material, 'Base Color')
    alpha_node = find_connected_image_texture(material, 'Alpha')
    if diffuse_node is None or alpha_node is None:
        raise RuntimeError(
            "The template material must have image textures connected to Principled BSDF Base Color and Alpha."
        )

    diffuse_node.image = ensure_image(f"{material_name}_Diffuse", asset_entry['diffusePath'], 'sRGB')
    alpha_node.image = ensure_image(f"{material_name}_Alpha", asset_entry['alphaPath'], 'Non-Color')
    return material

def remove_socket_links(socket):
    for link in list(socket.links):
        socket.id_data.links.remove(link)

def ensure_colour_material_chain(weave_group, materials):
    if not materials:
        return

    curve_material_node = weave_group.nodes.get('Set Material')
    mesh_material_node = weave_group.nodes.get('Set Material.001') or curve_material_node
    if mesh_material_node is None:
        raise RuntimeError("Weave From Draft is missing the Set Material nodes needed for preview rendering.")

    for node in (curve_material_node, mesh_material_node):
        if node is not None:
            node.inputs['Material'].default_value = materials[0]

    if len(materials) == 1:
        return

    colour_attr = weave_group.nodes.get('Render Colour Id')
    if colour_attr is None:
        colour_attr = weave_group.nodes.new('GeometryNodeInputNamedAttribute')
        colour_attr.name = 'Render Colour Id'
    colour_attr.location = (mesh_material_node.location.x + 40.0, mesh_material_node.location.y - 340.0)
    colour_attr.data_type = 'INT'
    colour_attr.inputs['Name'].default_value = 'colour_id'

    downstream_sockets = [link.to_socket for link in mesh_material_node.outputs['Geometry'].links]
    remove_socket_links(mesh_material_node.outputs['Geometry'])

    previous_node = mesh_material_node
    for material_index, material in enumerate(materials[1:], start=1):
        compare_node = weave_group.nodes.get(f'Render Material Match {material_index + 1}')
        if compare_node is None:
            compare_node = weave_group.nodes.new('FunctionNodeCompare')
            compare_node.name = f'Render Material Match {material_index + 1}'
        compare_node.location = (
            mesh_material_node.location.x + 260.0 * material_index,
            mesh_material_node.location.y - 300.0,
        )
        compare_node.data_type = 'INT'
        compare_node.operation = 'EQUAL'
        compare_node.inputs[3].default_value = material_index

        set_material_node = weave_group.nodes.get(f'Render Set Material {material_index + 1}')
        if set_material_node is None:
            set_material_node = weave_group.nodes.new('GeometryNodeSetMaterial')
            set_material_node.name = f'Render Set Material {material_index + 1}'
        set_material_node.location = (
            mesh_material_node.location.x + 260.0 * material_index,
            mesh_material_node.location.y,
        )
        set_material_node.inputs['Material'].default_value = material

        for input_socket in compare_node.inputs:
            remove_socket_links(input_socket)
        remove_socket_links(set_material_node.inputs['Geometry'])
        remove_socket_links(set_material_node.inputs['Selection'])

        weave_group.links.new(previous_node.outputs['Geometry'], set_material_node.inputs['Geometry'])
        weave_group.links.new(colour_attr.outputs['Attribute'], compare_node.inputs[2])
        weave_group.links.new(compare_node.outputs['Result'], set_material_node.inputs['Selection'])
        previous_node = set_material_node

    for socket in downstream_sockets:
        weave_group.links.new(previous_node.outputs['Geometry'], socket)

def build_template_preview_materials(material_assets):
    if not material_assets:
        return []
    template_material = find_template_material()
    if template_material is None:
        raise RuntimeError(
            "Blender is missing the MAterial_01 template material required for yarn preview rendering."
        )
    return [
        ensure_template_preview_material(template_material, asset_entry, index)
        for index, asset_entry in enumerate(material_assets, start=1)
    ]
"""

    if atlas_bundle is not None:
        atlas_setup = f"""
atlas_diffuse_path = {json.dumps(str(atlas_bundle.diffuse_path))}
atlas_alpha_path = {json.dumps(str(atlas_bundle.alpha_path))}
atlas_rows = {atlas_bundle.rows}

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
    if normalized_material_assets and len(normalized_material_assets) <= 4:
        preview_setup = """
    preview_materials = build_template_preview_materials(material_assets)
    """
    elif atlas_bundle is not None:
        preview_setup = """
    preview_materials = [ensure_atlas_preview_material(
        'FabricStudioAtlasMaterial',
        atlas_diffuse_path,
        atlas_alpha_path,
        atlas_rows,
    )]
    """

    common_scene_setup = f"""{sync_code}

{material_helpers}
{material_assets_setup}
{atlas_setup}

scene = bpy.context.scene
scene.render.use_file_extension = True
scene.render.image_settings.file_format = 'PNG'
scene.render.filepath = {render_path_json}

target_obj = bpy.data.objects.get({target_name_json})
if target_obj is not None:
    target_obj.hide_render = False
    target_obj.hide_viewport = False
{preview_setup}
    if target_obj.data is not None and hasattr(target_obj.data, 'materials'):
        target_obj.data.materials.clear()
        for preview_material in preview_materials:
            target_obj.data.materials.append(preview_material)
    weave_group = bpy.data.node_groups.get('Weave From Draft')
    if weave_group is not None and preview_materials:
        if len(preview_materials) <= 4:
            ensure_colour_material_chain(weave_group, preview_materials)
        else:
            for node_name in ('Set Material', 'Set Material.001'):
                node = weave_group.nodes.get(node_name)
                if node is not None:
                    try:
                        node.inputs['Material'].default_value = preview_materials[0]
                    except Exception:
                        pass

bpy.context.view_layer.update()
"""
    if preview_only:
        return common_scene_setup + f"""
def ensure_material_camera_view(target_name):
    target = bpy.data.objects.get(target_name)
    if target is None:
        return False

    view_layer = bpy.context.view_layer
    try:
        bpy.ops.object.select_all(action='DESELECT')
    except Exception:
        pass

    target.hide_set(False)
    target.hide_viewport = False
    target.select_set(True)
    view_layer.objects.active = target

    scene = bpy.context.scene
    if scene.camera is None:
        fallback_camera = bpy.data.objects.get('Camera')
        if fallback_camera is not None and fallback_camera.type == 'CAMERA':
            scene.camera = fallback_camera

    for window in bpy.context.window_manager.windows:
        screen = window.screen
        for area in screen.areas:
            if area.type != 'VIEW_3D':
                continue
            space = next((space for space in area.spaces if space.type == 'VIEW_3D'), None)
            region = next((region for region in area.regions if region.type == 'WINDOW'), None)
            if space is None or region is None:
                continue

            space.shading.type = 'MATERIAL'
            space.shading.use_scene_lights = True
            space.shading.use_scene_world = True
            space.overlay.show_overlays = False

            with bpy.context.temp_override(window=window, screen=screen, area=area, region=region, space_data=space):
                try:
                    bpy.ops.view3d.view_camera()
                except Exception:
                    try:
                        bpy.ops.view3d.view_selected(use_all_regions=False)
                    except Exception:
                        pass
            return True
    return False

preview_view_found = ensure_material_camera_view({target_name_json})
bpy.context.view_layer.update()

print({{
    'status': 'preview_ready',
    'preview_view_found': preview_view_found,
    'render_path': scene.render.filepath,
}})
"""

    return common_scene_setup + """
bpy.ops.render.render(write_still=True)

print({
    'status': 'rendered',
    'render_path': scene.render.filepath,
})
"""


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

    command = build_headless_render_command(config, script_path=script_path)

    with _LOCK:
        _JOBS[job.id] = job

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
    atlas_entries: list[dict[str, Any]] = []

    for asset in ordered_assets:
        if not asset.diffuseFilename or not asset.alphaFilename:
            raise ValueError(f"Yarn asset {asset.label} is missing processed outputs.")
        atlas_entries.append(
            {
                "id": asset.id,
                "diffuse_path": YARN_ASSETS_ROOT / asset.id / asset.diffuseFilename,
                "alpha_path": YARN_ASSETS_ROOT / asset.id / asset.alphaFilename,
            }
        )

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
        material_assets=atlas_entries if len(atlas_entries) <= 4 else None,
    )
    payload = project_snapshot.to_dict()
    payload["atlas"] = atlas_bundle.to_dict()
    payload["materialAssets"] = [
        {
            "id": str(entry["id"]),
            "diffusePath": str(entry["diffuse_path"]),
            "alphaPath": str(entry["alpha_path"]),
        }
        for entry in atlas_entries
    ]
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
