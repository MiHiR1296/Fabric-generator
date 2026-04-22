from __future__ import annotations

import json
import os
import socket
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class BlenderSocketConfig:
    host: str
    port: int
    timeout_seconds: float


def load_blender_socket_config() -> BlenderSocketConfig:
    return BlenderSocketConfig(
        host=os.environ.get("BLENDER_HOST", "127.0.0.1"),
        port=int(os.environ.get("BLENDER_PORT", "9875")),
        timeout_seconds=float(os.environ.get("BLENDER_TIMEOUT_SECONDS", "30")),
    )


def send_blender_command(command_type: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    config = load_blender_socket_config()
    payload = {"type": command_type, "params": params or {}}

    try:
        with socket.create_connection((config.host, config.port), timeout=config.timeout_seconds) as client:
            client.settimeout(config.timeout_seconds)
            client.sendall(json.dumps(payload).encode("utf-8"))

            buffer = bytearray()
            while True:
                chunk = client.recv(8192)
                if not chunk:
                    break
                buffer.extend(chunk)
                try:
                    response = json.loads(buffer.decode("utf-8"))
                except json.JSONDecodeError:
                    continue
                if isinstance(response, dict):
                    return response
                return {"status": "error", "message": "Blender returned a non-object JSON response."}
    except socket.timeout:
        return {
            "status": "error",
            "message": (
                f"Timed out after {config.timeout_seconds} seconds waiting for Blender "
                f"at {config.host}:{config.port}."
            ),
        }
    except OSError as exc:
        return {
            "status": "error",
            "message": (
                f"Could not connect to Blender at {config.host}:{config.port}. "
                f"Socket error: {exc}"
            ),
        }

    return {"status": "error", "message": "Blender closed the connection before returning valid JSON."}


def validate_drawdown_matrix(drawdown: Any) -> list[list[int]]:
    if not isinstance(drawdown, list) or not drawdown:
        raise ValueError("Draft drawdown must be a non-empty matrix.")

    normalized: list[list[int]] = []
    expected_width: int | None = None

    for row in drawdown:
        if not isinstance(row, list) or not row:
            raise ValueError("Every drawdown row must be a non-empty list.")
        normalized_row = [1 if int(value) else 0 for value in row]
        if expected_width is None:
            expected_width = len(normalized_row)
        elif len(normalized_row) != expected_width:
            raise ValueError("All drawdown rows must have the same number of columns.")
        normalized.append(normalized_row)

    return normalized


def _normalize_material_ids(values: list[Any] | None, expected_length: int) -> list[int] | None:
    if values is None:
        return None
    if len(values) != expected_length:
        raise ValueError(
            f"Expected {expected_length} material ids, received {len(values)}."
        )
    return [max(0, int(value)) for value in values]


def build_blender_sync_code(
    draft: dict[str, Any],
    *,
    target_object_name: str = "ParametricWeave",
    draft_object_name: str = "WebDraft_Live",
    draft_collection_name: str = "Fabric Drafts",
    fit_target_name: str = "Space",
    warp_material_ids: list[Any] | None = None,
    weft_material_ids: list[Any] | None = None,
    material_count: int | None = None,
) -> str:
    matrix = validate_drawdown_matrix(draft.get("drawdown"))
    rows = len(matrix)
    cols = len(matrix[0])
    title = str(draft.get("title") or "Web Draft")
    source_label = str(draft.get("sourceLabel") or "Weaving Draft Studio")
    warp_colors = [str(value) for value in draft.get("warpColors") or []]
    weft_colors = [str(value) for value in draft.get("weftColors") or []]
    render_settings = draft.get("renderSettings") if isinstance(draft.get("renderSettings"), dict) else {}

    normalized_warp_material_ids = _normalize_material_ids(warp_material_ids, cols)
    normalized_weft_material_ids = _normalize_material_ids(weft_material_ids, rows)

    def maybe_float(key: str) -> float | None:
        value = render_settings.get(key)
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    def maybe_int(key: str) -> int | None:
        value = render_settings.get(key)
        try:
            return int(round(float(value))) if value is not None else None
        except (TypeError, ValueError):
            return None

    warp_threads_override = maybe_int("warpThreads")
    weft_threads_override = maybe_int("weftThreads")
    spacing_override = maybe_float("spacing")
    amplitude_override = maybe_float("amplitude")
    texture_scale_v_override = maybe_float("textureScaleV")
    fill_ratio_override = maybe_float("fillRatio")

    default_warp_threads = max(cols * 8, 96)
    default_weft_threads = max(rows * 8, 96)
    if material_count is None and normalized_warp_material_ids is not None and normalized_weft_material_ids is not None:
        material_count = max(normalized_warp_material_ids + normalized_weft_material_ids) + 1

    return f"""
import bpy
import json

matrix = {json.dumps(matrix)}
warp_colors = {json.dumps(warp_colors)}
weft_colors = {json.dumps(weft_colors)}
warp_material_ids = {json.dumps(normalized_warp_material_ids)}
weft_material_ids = {json.dumps(normalized_weft_material_ids)}
title = {json.dumps(title)}
source_label = {json.dumps(source_label)}
target_object_name = {json.dumps(target_object_name)}
draft_object_name = {json.dumps(draft_object_name)}
draft_collection_name = {json.dumps(draft_collection_name)}
fit_target_name = {json.dumps(fit_target_name)}
warp_threads_override = {repr(warp_threads_override)}
weft_threads_override = {repr(weft_threads_override)}
spacing_override = {repr(spacing_override)}
amplitude_override = {repr(amplitude_override)}
texture_scale_v_override = {repr(texture_scale_v_override)}
fill_ratio_override = {repr(fill_ratio_override)}
default_warp_threads = {repr(default_warp_threads)}
default_weft_threads = {repr(default_weft_threads)}
material_count_override = {repr(material_count)}
rows = len(matrix)
cols = len(matrix[0]) if rows else 0

def ensure_collection(name):
    collection = bpy.data.collections.get(name)
    if collection is None:
        collection = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(collection)
    return collection

def ensure_socket(group, name):
    for item in group.interface.items_tree:
        if getattr(item, 'item_type', None) == 'SOCKET' and getattr(item, 'in_out', None) == 'INPUT' and item.name == name:
            return item
    raise KeyError(name)

def set_modifier_input(modifier, node_group, name, value):
    socket = ensure_socket(node_group, name)
    modifier[socket.identifier] = value

def get_modifier_input(modifier, node_group, name, default=None):
    try:
        socket = ensure_socket(node_group, name)
    except KeyError:
        return default
    try:
        return modifier[socket.identifier]
    except Exception:
        return default

def pick_value(override, preserved_value, default):
    if override is not None:
        return override
    if preserved_value is not None:
        return preserved_value
    return default

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

def ensure_web_draft_material(name, warp_hex, weft_hex):
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

def _replace_face_attr(mesh, name, values):
    existing = mesh.attributes.get(name)
    if existing:
        mesh.attributes.remove(existing)
    attr = mesh.attributes.new(name, 'INT', 'FACE')
    for index, value in enumerate(values):
        attr.data[index].value = int(value)

def create_or_update_pattern_object(name, matrix, collection):
    rows = len(matrix)
    cols = len(matrix[0]) if rows else 0
    obj = bpy.data.objects.get(name)
    if obj is None or obj.type != 'MESH':
        mesh = bpy.data.meshes.new(f"{{name}}Mesh")
        obj = bpy.data.objects.new(name, mesh)
        collection.objects.link(obj)
    else:
        mesh = obj.data
        if collection not in obj.users_collection:
            collection.objects.link(obj)

    verts = []
    faces = []
    for row in range(rows + 1):
        for col in range(cols + 1):
            verts.append((float(col), -float(row), 0.0))
    for row in range(rows):
        for col in range(cols):
            start = row * (cols + 1) + col
            faces.append((start, start + 1, start + cols + 2, start + cols + 1))

    mesh.clear_geometry()
    mesh.from_pydata(verts, [], faces)
    mesh.update()

    flat_cell_code = [value for row_values in matrix for value in row_values]
    _replace_face_attr(mesh, 'cell_code', flat_cell_code)
    if warp_material_ids is not None and weft_material_ids is not None:
        flat_warp_materials = [warp_material_ids[col] for row_index in range(rows) for col in range(cols)]
        flat_weft_materials = [weft_material_ids[row_index] for row_index in range(rows) for col in range(cols)]
        _replace_face_attr(mesh, 'warp_material_id', flat_warp_materials)
        _replace_face_attr(mesh, 'weft_material_id', flat_weft_materials)

    obj.display_type = 'WIRE'
    obj.hide_render = True
    obj.hide_viewport = True
    obj['repeat_cols'] = cols
    obj['repeat_rows'] = rows
    obj['legend'] = '0 = weft over, 1 = warp over'
    obj['source_label'] = source_label
    obj['draft_title'] = title
    obj['warp_colors'] = json.dumps(warp_colors)
    obj['weft_colors'] = json.dumps(weft_colors)
    if warp_material_ids is not None:
        obj['warp_material_ids'] = json.dumps(warp_material_ids)
    if weft_material_ids is not None:
        obj['weft_material_ids'] = json.dumps(weft_material_ids)
    return obj

def clear_input_links(links, socket):
    for link in list(socket.links):
        links.remove(link)

def ensure_named_attribute_node(group, name, attribute_name, location):
    node = group.nodes.get(name)
    if node is None:
        node = group.nodes.new('GeometryNodeInputNamedAttribute')
        node.name = name
    node.location = location
    node.data_type = 'INT'
    node.inputs['Name'].default_value = attribute_name
    return node

def ensure_sample_index_node(group, name, location):
    node = group.nodes.get(name)
    if node is None:
        node = group.nodes.new('GeometryNodeSampleIndex')
        node.name = name
    node.location = location
    node.data_type = 'INT'
    node.domain = 'FACE'
    return node

def ensure_draft_colour_id_sampling(group):
    nodes = group.nodes
    links = group.links

    draft_object_info = nodes.get('Draft Object Info')
    store_warp_colour_id = nodes.get('Store Warp Colour Id')
    store_weft_colour_id = nodes.get('Store Weft Colour Id')
    warp_index_math = nodes.get('Math.004')
    weft_index_math = nodes.get('Math.010')
    if not all((draft_object_info, store_warp_colour_id, store_weft_colour_id, warp_index_math, weft_index_math)):
        raise RuntimeError("Weave From Draft is missing the nodes needed for yarn-material sampling.")

    warp_attr = ensure_named_attribute_node(group, 'Draft Warp Material Id', 'warp_material_id', (-860, -720))
    weft_attr = ensure_named_attribute_node(group, 'Draft Weft Material Id', 'weft_material_id', (-860, -940))
    warp_sample = ensure_sample_index_node(group, 'Draft Warp Material Sample', (-620, -720))
    weft_sample = ensure_sample_index_node(group, 'Draft Weft Material Sample', (-620, -940))

    clear_input_links(links, warp_sample.inputs['Geometry'])
    clear_input_links(links, warp_sample.inputs['Value'])
    clear_input_links(links, warp_sample.inputs['Index'])
    clear_input_links(links, weft_sample.inputs['Geometry'])
    clear_input_links(links, weft_sample.inputs['Value'])
    clear_input_links(links, weft_sample.inputs['Index'])
    clear_input_links(links, store_warp_colour_id.inputs['Value'])
    clear_input_links(links, store_weft_colour_id.inputs['Value'])

    links.new(draft_object_info.outputs['Geometry'], warp_sample.inputs['Geometry'])
    links.new(warp_attr.outputs['Attribute'], warp_sample.inputs['Value'])
    links.new(warp_index_math.outputs['Value'], warp_sample.inputs['Index'])
    links.new(warp_sample.outputs['Value'], store_warp_colour_id.inputs['Value'])

    links.new(draft_object_info.outputs['Geometry'], weft_sample.inputs['Geometry'])
    links.new(weft_attr.outputs['Attribute'], weft_sample.inputs['Value'])
    links.new(weft_index_math.outputs['Value'], weft_sample.inputs['Index'])
    links.new(weft_sample.outputs['Value'], store_weft_colour_id.inputs['Value'])

draft_collection = ensure_collection(draft_collection_name)
draft_obj = create_or_update_pattern_object(draft_object_name, matrix, draft_collection)

target_obj = bpy.data.objects.get(target_object_name)
if target_obj is None:
    mesh = bpy.data.meshes.new(f"{{target_object_name}}Mesh")
    mesh.from_pydata([(0.0, 0.0, 0.0)], [], [])
    mesh.update()
    target_obj = bpy.data.objects.new(target_object_name, mesh)
    bpy.context.scene.collection.objects.link(target_obj)

weave_group = bpy.data.node_groups.get('Weave From Draft')
if weave_group is None:
    raise RuntimeError("Blender is missing the 'Weave From Draft' geometry-node group.")
if warp_material_ids is not None and weft_material_ids is not None:
    ensure_draft_colour_id_sampling(weave_group)

weave_mod = target_obj.modifiers.get('Weave')
preserved = {{}}
if weave_mod and weave_mod.type == 'NODES' and weave_mod.node_group:
    old_group = weave_mod.node_group
    for socket_name in (
        'Warp Threads',
        'Weft Threads',
        'Spacing',
        'Amplitude',
        'Thread Radius',
        'Thread Subdivisions',
        'Ply Count',
        'Ply Radius',
        'Twist Amount',
        'Ply Resolution',
        'Texture Scale U',
        'Texture Scale V',
        'Texture Offset V',
        'Texture Side Flatten',
        'Lump Strength',
        'Lump Scale',
        'Fiber Density',
        'Fiber Length',
        'Fiber Thickness',
        'Fiber Frizz',
        'Fiber Subdivs',
        'Seed',
        'Material Count',
    ):
        preserved[socket_name] = get_modifier_input(weave_mod, old_group, socket_name, None)
else:
    weave_mod = target_obj.modifiers.new(name='Weave', type='NODES')

weave_mod.node_group = weave_group
set_modifier_input(weave_mod, weave_group, 'Draft Object', draft_obj)
set_modifier_input(weave_mod, weave_group, 'Draft Columns', cols)
set_modifier_input(weave_mod, weave_group, 'Draft Rows', rows)
set_modifier_input(weave_mod, weave_group, 'Warp Threads', int(round(pick_value(warp_threads_override, preserved.get('Warp Threads'), default_warp_threads))))
set_modifier_input(weave_mod, weave_group, 'Weft Threads', int(round(pick_value(weft_threads_override, preserved.get('Weft Threads'), default_weft_threads))))
set_modifier_input(weave_mod, weave_group, 'Spacing', pick_value(spacing_override, preserved.get('Spacing'), 0.03))
set_modifier_input(weave_mod, weave_group, 'Amplitude', pick_value(amplitude_override, preserved.get('Amplitude'), 0.005))
set_modifier_input(weave_mod, weave_group, 'Thread Radius', preserved.get('Thread Radius') if preserved.get('Thread Radius') is not None else 0.028)
set_modifier_input(weave_mod, weave_group, 'Thread Subdivisions', preserved.get('Thread Subdivisions') if preserved.get('Thread Subdivisions') is not None else 8.0)
set_modifier_input(weave_mod, weave_group, 'Ply Count', preserved.get('Ply Count') if preserved.get('Ply Count') is not None else 3)
set_modifier_input(weave_mod, weave_group, 'Ply Radius', preserved.get('Ply Radius') if preserved.get('Ply Radius') is not None else 0.013)
set_modifier_input(weave_mod, weave_group, 'Twist Amount', preserved.get('Twist Amount') if preserved.get('Twist Amount') is not None else 16.0)
set_modifier_input(weave_mod, weave_group, 'Ply Resolution', preserved.get('Ply Resolution') if preserved.get('Ply Resolution') is not None else 5)
set_modifier_input(weave_mod, weave_group, 'Texture Scale U', preserved.get('Texture Scale U') if preserved.get('Texture Scale U') is not None else 8.0)
set_modifier_input(weave_mod, weave_group, 'Texture Scale V', pick_value(texture_scale_v_override, preserved.get('Texture Scale V'), 0.5))
set_modifier_input(weave_mod, weave_group, 'Texture Offset V', preserved.get('Texture Offset V') if preserved.get('Texture Offset V') is not None else 0.0)
set_modifier_input(weave_mod, weave_group, 'Texture Side Flatten', preserved.get('Texture Side Flatten') if preserved.get('Texture Side Flatten') is not None else 0.7)
set_modifier_input(weave_mod, weave_group, 'Lump Strength', preserved.get('Lump Strength') if preserved.get('Lump Strength') is not None else 0.0015)
set_modifier_input(weave_mod, weave_group, 'Lump Scale', preserved.get('Lump Scale') if preserved.get('Lump Scale') is not None else 6.0)
set_modifier_input(weave_mod, weave_group, 'Fiber Density', preserved.get('Fiber Density') if preserved.get('Fiber Density') is not None else 0.0)
set_modifier_input(weave_mod, weave_group, 'Fiber Length', preserved.get('Fiber Length') if preserved.get('Fiber Length') is not None else 0.04)
set_modifier_input(weave_mod, weave_group, 'Fiber Thickness', preserved.get('Fiber Thickness') if preserved.get('Fiber Thickness') is not None else 0.15)
set_modifier_input(weave_mod, weave_group, 'Fiber Frizz', preserved.get('Fiber Frizz') if preserved.get('Fiber Frizz') is not None else 0.02)
set_modifier_input(weave_mod, weave_group, 'Fiber Subdivs', preserved.get('Fiber Subdivs') if preserved.get('Fiber Subdivs') is not None else 4)
set_modifier_input(weave_mod, weave_group, 'Seed', preserved.get('Seed') if preserved.get('Seed') is not None else 0)
material_count_floor = material_count_override if material_count_override is not None else max(len(warp_colors), len(weft_colors), 2)
material_count_value = preserved.get('Material Count')
if material_count_value is None:
    material_count_value = material_count_floor
else:
    material_count_value = max(int(material_count_value), material_count_floor)
set_modifier_input(weave_mod, weave_group, 'Material Count', material_count_value)

fit_mod = target_obj.modifiers.get('Fit To Space') or target_obj.modifiers.get('Swatch Fit')
if fit_mod and fit_mod.type == 'NODES' and fit_mod.node_group:
    fit_group = fit_mod.node_group
    fit_target = bpy.data.objects.get(fit_target_name)
    if fit_target is not None:
        try:
            set_modifier_input(fit_mod, fit_group, 'Target Plane', fit_target)
        except Exception:
            pass
    try:
        set_modifier_input(fit_mod, fit_group, 'Fill Ratio', pick_value(fill_ratio_override, None, 1.0))
    except Exception:
        pass

if target_obj.data is not None and hasattr(target_obj.data, 'materials'):
    material = ensure_web_draft_material(
        'WebDraftMaterial',
        warp_colors[0] if warp_colors else '#f3ede2',
        weft_colors[0] if weft_colors else '#b85e3c',
    )
    target_obj.data.materials.clear()
    target_obj.data.materials.append(material)
    for node_name in ('Set Material', 'Set Material.001'):
        node = weave_group.nodes.get(node_name)
        if node is not None:
            try:
                node.inputs['Material'].default_value = material
            except Exception:
                pass

target_obj['source_pattern'] = title
target_obj['source_label'] = source_label

print({{
    'status': 'ok',
    'draft_object': draft_obj.name,
    'target_object': target_obj.name,
    'rows': rows,
    'cols': cols,
    'node_group': weave_group.name,
    'material_count': material_count_value,
}})
"""


def sync_draft_to_blender(
    draft: dict[str, Any],
    *,
    target_object_name: str = "ParametricWeave",
    draft_object_name: str = "WebDraft_Live",
) -> dict[str, Any]:
    code = build_blender_sync_code(
        draft,
        target_object_name=target_object_name,
        draft_object_name=draft_object_name,
    )
    response = send_blender_command("execute_code", {"code": code})
    if response.get("status") != "success":
        raise RuntimeError(response.get("message") or "Blender could not apply the draft.")
    return response.get("result") or response
