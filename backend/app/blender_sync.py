from __future__ import annotations

import json
import os
import socket
from dataclasses import dataclass
from typing import Any

from .blender_session import (
    begin_blender_command,
    finish_blender_command,
    managed_session_enabled,
    mark_blender_transport_error,
    restart_blender_session,
)


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


def _send_socket_command(
    config: BlenderSocketConfig,
    payload: dict[str, Any],
) -> dict[str, Any]:
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


def _is_transport_error(response: dict[str, Any]) -> bool:
    if response.get("status") != "error":
        return False
    message = str(response.get("message") or "").lower()
    return any(
        fragment in message
        for fragment in (
            "timed out after",
            "could not connect to blender",
            "socket error",
            "closed the connection",
        )
    )


def send_blender_command(command_type: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    config = load_blender_socket_config()
    payload = {"type": command_type, "params": params or {}}
    begun = False

    try:
        begin_blender_command(reason=command_type)
        begun = True
        response = _send_socket_command(config, payload)
        if managed_session_enabled() and _is_transport_error(response):
            mark_blender_transport_error(str(response.get("message") or "Transport error talking to Blender."))
            restart_blender_session(reason=f"retrying {command_type}")
            response = _send_socket_command(config, payload)
        return response
    except Exception as exc:
        mark_blender_transport_error(str(exc))
        return {"status": "error", "message": str(exc)}
    finally:
        if begun:
            finish_blender_command()


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

    def map_unit_setting(key: str, minimum: float, maximum: float) -> float | None:
        value = maybe_float(key)
        if value is None:
            return None
        unit_value = min(1.0, max(0.0, value))
        return minimum + (maximum - minimum) * unit_value

    warp_threads_override = maybe_int("warpThreads")
    weft_threads_override = maybe_int("weftThreads")
    spacing_override = map_unit_setting("spacing", 0.03, 0.1)
    pattern_noise_x_override = map_unit_setting("patternNoiseX", 0.0, 0.03)
    pattern_noise_y_override = map_unit_setting("patternNoiseY", 0.0, 0.03)
    amplitude_override = maybe_float("amplitude")
    thread_radius_override = maybe_float("threadRadius")
    thread_subdivisions_override = maybe_float("threadSubdivisions")
    ply_count_override = maybe_int("plyCount")
    ply_radius_override = maybe_float("plyRadius")
    twist_amount_override = maybe_float("twistAmount")
    ply_resolution_override = maybe_int("plyResolution")
    texture_scale_u_override = maybe_float("textureScaleU")
    texture_scale_v_override = maybe_float("textureScaleV")
    texture_offset_v_override = maybe_float("textureOffsetV")
    texture_side_flatten_override = maybe_float("textureSideFlatten")
    lump_strength_override = maybe_float("lumpStrength")
    lump_scale_override = maybe_float("lumpScale")
    fiber_density_override = maybe_float("fiberDensity")
    fiber_length_override = maybe_float("fiberLength")
    fiber_thickness_override = maybe_float("fiberThickness")
    fiber_frizz_override = maybe_float("fiberFrizz")
    fiber_subdivs_override = maybe_int("fiberSubdivs")
    seed_override = maybe_int("seed")
    fill_ratio_override = maybe_float("fillRatio")

    default_warp_threads = max(cols, 180)
    default_weft_threads = max(rows, 180)
    if warp_threads_override is not None:
        warp_threads_override = max(warp_threads_override, default_warp_threads)
    if weft_threads_override is not None:
        weft_threads_override = max(weft_threads_override, default_weft_threads)
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
pattern_noise_x_override = {repr(pattern_noise_x_override)}
pattern_noise_y_override = {repr(pattern_noise_y_override)}
amplitude_override = {repr(amplitude_override)}
thread_radius_override = {repr(thread_radius_override)}
thread_subdivisions_override = {repr(thread_subdivisions_override)}
ply_count_override = {repr(ply_count_override)}
ply_radius_override = {repr(ply_radius_override)}
twist_amount_override = {repr(twist_amount_override)}
ply_resolution_override = {repr(ply_resolution_override)}
texture_scale_u_override = {repr(texture_scale_u_override)}
texture_scale_v_override = {repr(texture_scale_v_override)}
texture_offset_v_override = {repr(texture_offset_v_override)}
texture_side_flatten_override = {repr(texture_side_flatten_override)}
lump_strength_override = {repr(lump_strength_override)}
lump_scale_override = {repr(lump_scale_override)}
fiber_density_override = {repr(fiber_density_override)}
fiber_length_override = {repr(fiber_length_override)}
fiber_thickness_override = {repr(fiber_thickness_override)}
fiber_frizz_override = {repr(fiber_frizz_override)}
fiber_subdivs_override = {repr(fiber_subdivs_override)}
seed_override = {repr(seed_override)}
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

def has_modifier_input(node_group, name):
    try:
        ensure_socket(node_group, name)
        return True
    except KeyError:
        return False

def maybe_set_modifier_input(modifier, node_group, name, value):
    try:
        set_modifier_input(modifier, node_group, name, value)
        return True
    except KeyError:
        return False

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

def suppress_default_override(value, default):
    if value is None:
        return None
    try:
        if abs(float(value) - float(default)) <= 0.000001:
            return None
    except Exception:
        pass
    return value

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

def ensure_interface_socket(group, name, socket_type, default=None):
    for item in group.interface.items_tree:
        if getattr(item, 'item_type', None) == 'SOCKET' and getattr(item, 'in_out', None) == 'INPUT' and item.name == name:
            return item
    socket = group.interface.new_socket(name=name, in_out='INPUT', socket_type=socket_type)
    if default is not None and hasattr(socket, 'default_value'):
        try:
            socket.default_value = default
        except Exception:
            pass
    return socket

def ensure_node(group, name, node_type, location):
    node = group.nodes.get(name)
    if node is None:
        node = group.nodes.new(node_type)
        node.name = name
    node.location = location
    return node

def output_socket(node, name):
    socket = node.outputs.get(name)
    if socket is None:
        raise RuntimeError(f"Node {{node.name}} is missing output {{name}}.")
    return socket

def input_socket(node, name):
    socket = node.inputs.get(name)
    if socket is None:
        raise RuntimeError(f"Node {{node.name}} is missing input {{name}}.")
    return socket

def link_once(group, from_socket, to_socket):
    clear_input_links(group.links, to_socket)
    group.links.new(from_socket, to_socket)

def configure_math_node(node, operation):
    node.operation = operation
    return node

def configure_sample_index_node(node):
    node.data_type = 'INT'
    node.domain = 'FACE'
    return node

def ensure_scan_knotty_draft_sampling(group):
    ensure_interface_socket(group, 'Draft Object', 'NodeSocketObject')
    ensure_interface_socket(group, 'Draft Columns', 'NodeSocketInt', cols)
    ensure_interface_socket(group, 'Draft Rows', 'NodeSocketInt', rows)

    pattern_input = ensure_node(group, 'PW Draft Input', 'NodeGroupInput', (1370, -760))
    draft_object_info = ensure_node(group, 'PW Draft Object Info', 'GeometryNodeObjectInfo', (1600, -760))
    draft_attr = ensure_node(group, 'PW Draft Cell Code', 'GeometryNodeInputNamedAttribute', (1600, -940))
    draft_attr.data_type = 'INT'
    input_socket(draft_attr, 'Name').default_value = 'cell_code'

    warp_curve = group.nodes.get('Curve of Point')
    weft_curve = group.nodes.get('Curve of Point.001')
    warp_z_sign = group.nodes.get('Math.005')
    weft_z_sign = group.nodes.get('Math.011')
    if not all((warp_curve, weft_curve, warp_z_sign, weft_z_sign)):
        raise RuntimeError("Parametric Weave knotty is missing the curve-index or Z offset nodes needed for draft sampling.")

    link_once(group, output_socket(pattern_input, 'Draft Object'), input_socket(draft_object_info, 'Object'))

    warp_col_mod = configure_math_node(ensure_node(group, 'PW Draft Warp Col Mod', 'ShaderNodeMath', (1860, -720)), 'MODULO')
    warp_row_mod = configure_math_node(ensure_node(group, 'PW Draft Warp Row Mod', 'ShaderNodeMath', (1860, -900)), 'MODULO')
    warp_row_offset = configure_math_node(ensure_node(group, 'PW Draft Warp Row Offset', 'ShaderNodeMath', (2080, -900)), 'MULTIPLY')
    warp_face_index = configure_math_node(ensure_node(group, 'PW Draft Warp Face Index', 'ShaderNodeMath', (2300, -820)), 'ADD')
    warp_sample = configure_sample_index_node(ensure_node(group, 'PW Draft Warp Sample', 'GeometryNodeSampleIndex', (2520, -820)))
    warp_sample_sign = configure_math_node(ensure_node(group, 'PW Draft Warp Sign', 'ShaderNodeMath', (2740, -820)), 'MULTIPLY_ADD')
    input_socket(warp_sample_sign, 'Value').default_value = 0.5
    warp_sample_sign.inputs[1].default_value = -2.0
    warp_sample_sign.inputs[2].default_value = 1.0

    link_once(group, output_socket(warp_curve, 'Index in Curve'), warp_col_mod.inputs[0])
    link_once(group, output_socket(pattern_input, 'Draft Columns'), warp_col_mod.inputs[1])
    link_once(group, output_socket(warp_curve, 'Curve Index'), warp_row_mod.inputs[0])
    link_once(group, output_socket(pattern_input, 'Draft Rows'), warp_row_mod.inputs[1])
    link_once(group, warp_row_mod.outputs['Value'], warp_row_offset.inputs[0])
    link_once(group, output_socket(pattern_input, 'Draft Columns'), warp_row_offset.inputs[1])
    link_once(group, warp_row_offset.outputs['Value'], warp_face_index.inputs[0])
    link_once(group, warp_col_mod.outputs['Value'], warp_face_index.inputs[1])
    link_once(group, output_socket(draft_object_info, 'Geometry'), input_socket(warp_sample, 'Geometry'))
    link_once(group, output_socket(draft_attr, 'Attribute'), input_socket(warp_sample, 'Value'))
    link_once(group, warp_face_index.outputs['Value'], input_socket(warp_sample, 'Index'))
    link_once(group, warp_sample.outputs['Value'], warp_sample_sign.inputs[0])
    link_once(group, warp_sample_sign.outputs['Value'], warp_z_sign.inputs[0])

    if warp_material_ids is not None and weft_material_ids is not None:
        warp_material_store = group.nodes.get('PW Warp Material Id')
        if warp_material_store is not None:
            warp_material_attr = ensure_named_attribute_node(group, 'PW Draft Warp Material Id', 'warp_material_id', (2520, -560))
            warp_material_sample = configure_sample_index_node(ensure_node(group, 'PW Draft Warp Material Sample', 'GeometryNodeSampleIndex', (2740, -560)))
            warp_material_one_based = configure_math_node(ensure_node(group, 'PW Draft Warp Material One Based', 'ShaderNodeMath', (2960, -560)), 'ADD')
            warp_material_one_based.inputs[1].default_value = 1.0
            link_once(group, output_socket(draft_object_info, 'Geometry'), input_socket(warp_material_sample, 'Geometry'))
            link_once(group, output_socket(warp_material_attr, 'Attribute'), input_socket(warp_material_sample, 'Value'))
            link_once(group, warp_face_index.outputs['Value'], input_socket(warp_material_sample, 'Index'))
            link_once(group, warp_material_sample.outputs['Value'], warp_material_one_based.inputs[0])
            link_once(group, warp_material_one_based.outputs['Value'], input_socket(warp_material_store, 'Value'))

    weft_row_mod = configure_math_node(ensure_node(group, 'PW Draft Weft Row Mod', 'ShaderNodeMath', (1860, -1160)), 'MODULO')
    weft_col_mod = configure_math_node(ensure_node(group, 'PW Draft Weft Col Mod', 'ShaderNodeMath', (1860, -1340)), 'MODULO')
    weft_row_offset = configure_math_node(ensure_node(group, 'PW Draft Weft Row Offset', 'ShaderNodeMath', (2080, -1160)), 'MULTIPLY')
    weft_face_index = configure_math_node(ensure_node(group, 'PW Draft Weft Face Index', 'ShaderNodeMath', (2300, -1240)), 'ADD')
    weft_sample = configure_sample_index_node(ensure_node(group, 'PW Draft Weft Sample', 'GeometryNodeSampleIndex', (2520, -1240)))
    weft_sample_sign = configure_math_node(ensure_node(group, 'PW Draft Weft Sign', 'ShaderNodeMath', (2740, -1240)), 'MULTIPLY_ADD')
    input_socket(weft_sample_sign, 'Value').default_value = 0.5
    weft_sample_sign.inputs[1].default_value = 2.0
    weft_sample_sign.inputs[2].default_value = -1.0

    link_once(group, output_socket(weft_curve, 'Index in Curve'), weft_row_mod.inputs[0])
    link_once(group, output_socket(pattern_input, 'Draft Rows'), weft_row_mod.inputs[1])
    link_once(group, output_socket(weft_curve, 'Curve Index'), weft_col_mod.inputs[0])
    link_once(group, output_socket(pattern_input, 'Draft Columns'), weft_col_mod.inputs[1])
    link_once(group, weft_row_mod.outputs['Value'], weft_row_offset.inputs[0])
    link_once(group, output_socket(pattern_input, 'Draft Columns'), weft_row_offset.inputs[1])
    link_once(group, weft_row_offset.outputs['Value'], weft_face_index.inputs[0])
    link_once(group, weft_col_mod.outputs['Value'], weft_face_index.inputs[1])
    link_once(group, output_socket(draft_object_info, 'Geometry'), input_socket(weft_sample, 'Geometry'))
    link_once(group, output_socket(draft_attr, 'Attribute'), input_socket(weft_sample, 'Value'))
    link_once(group, weft_face_index.outputs['Value'], input_socket(weft_sample, 'Index'))
    link_once(group, weft_sample.outputs['Value'], weft_sample_sign.inputs[0])
    link_once(group, weft_sample_sign.outputs['Value'], weft_z_sign.inputs[0])

    if warp_material_ids is not None and weft_material_ids is not None:
        weft_material_store = group.nodes.get('PW Weft Material Id')
        if weft_material_store is not None:
            weft_material_attr = ensure_named_attribute_node(group, 'PW Draft Weft Material Id', 'weft_material_id', (2520, -1500))
            weft_material_sample = configure_sample_index_node(ensure_node(group, 'PW Draft Weft Material Sample', 'GeometryNodeSampleIndex', (2740, -1500)))
            weft_material_one_based = configure_math_node(ensure_node(group, 'PW Draft Weft Material One Based', 'ShaderNodeMath', (2960, -1500)), 'ADD')
            weft_material_one_based.inputs[1].default_value = 1.0
            link_once(group, output_socket(draft_object_info, 'Geometry'), input_socket(weft_material_sample, 'Geometry'))
            link_once(group, output_socket(weft_material_attr, 'Attribute'), input_socket(weft_material_sample, 'Value'))
            link_once(group, weft_face_index.outputs['Value'], input_socket(weft_material_sample, 'Index'))
            link_once(group, weft_material_sample.outputs['Value'], weft_material_one_based.inputs[0])
            link_once(group, weft_material_one_based.outputs['Value'], input_socket(weft_material_store, 'Value'))

target_obj = bpy.data.objects.get(target_object_name)
if target_obj is None:
    mesh = bpy.data.meshes.new(f"{{target_object_name}}Mesh")
    mesh.from_pydata([(0.0, 0.0, 0.0)], [], [])
    mesh.update()
    target_obj = bpy.data.objects.new(target_object_name, mesh)
    bpy.context.scene.collection.objects.link(target_obj)

weave_mod = target_obj.modifiers.get('Weave')
existing_group = weave_mod.node_group if weave_mod and weave_mod.type == 'NODES' else None
weave_group = None
if existing_group is not None and existing_group.name == 'Parametric Weave knotty':
    weave_group = existing_group
if weave_group is None:
    weave_group = bpy.data.node_groups.get('Parametric Weave knotty')
if weave_group is None:
    weave_group = bpy.data.node_groups.get('Weave From Draft')
if weave_group is None:
    raise RuntimeError("Blender is missing the 'Parametric Weave knotty' or 'Weave From Draft' geometry-node group.")

uses_scan_knotty_group = weave_group.name == 'Parametric Weave knotty'
if uses_scan_knotty_group:
    ensure_scan_knotty_draft_sampling(weave_group)

uses_draft_object = has_modifier_input(weave_group, 'Draft Object')
draft_obj = None
if uses_draft_object:
    draft_collection = ensure_collection(draft_collection_name)
    draft_obj = create_or_update_pattern_object(draft_object_name, matrix, draft_collection)

if uses_draft_object and not uses_scan_knotty_group and warp_material_ids is not None and weft_material_ids is not None:
    ensure_draft_colour_id_sampling(weave_group)

if uses_scan_knotty_group:
    amplitude_override = suppress_default_override(amplitude_override, 0.008)
    thread_radius_override = suppress_default_override(thread_radius_override, 0.028)
    thread_subdivisions_override = suppress_default_override(thread_subdivisions_override, 8.0)
    texture_scale_u_override = suppress_default_override(texture_scale_u_override, 8.0)
    texture_scale_v_override = suppress_default_override(texture_scale_v_override, 0.5)
    texture_offset_v_override = suppress_default_override(texture_offset_v_override, 0.0)
    texture_side_flatten_override = suppress_default_override(texture_side_flatten_override, 0.7)
    seed_override = suppress_default_override(seed_override, 0)

preserved = {{}}
if weave_mod and weave_mod.type == 'NODES' and weave_mod.node_group:
    old_group = weave_mod.node_group
    for socket_name in (
        'Warp Threads',
        'Weft Threads',
        'Spacing',
        'Pattern Noise X',
        'Pattern Noise Y',
        'Amplitude',
        'Thread Radius',
        'Main Strand Radius',
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
if uses_draft_object:
    set_modifier_input(weave_mod, weave_group, 'Draft Object', draft_obj)
    set_modifier_input(weave_mod, weave_group, 'Draft Columns', cols)
    set_modifier_input(weave_mod, weave_group, 'Draft Rows', rows)
maybe_set_modifier_input(weave_mod, weave_group, 'Warp Threads', int(round(pick_value(warp_threads_override, None, default_warp_threads))))
maybe_set_modifier_input(weave_mod, weave_group, 'Weft Threads', int(round(pick_value(weft_threads_override, None, default_weft_threads))))
maybe_set_modifier_input(weave_mod, weave_group, 'Spacing', pick_value(spacing_override, preserved.get('Spacing'), 0.05))
maybe_set_modifier_input(weave_mod, weave_group, 'Pattern Noise X', pick_value(pattern_noise_x_override, preserved.get('Pattern Noise X'), 0.0))
maybe_set_modifier_input(weave_mod, weave_group, 'Pattern Noise Y', pick_value(pattern_noise_y_override, preserved.get('Pattern Noise Y'), 0.0))
maybe_set_modifier_input(weave_mod, weave_group, 'Amplitude', pick_value(amplitude_override, preserved.get('Amplitude'), 0.008))
thread_radius_preserved = preserved.get('Thread Radius')
if thread_radius_preserved is None:
    thread_radius_preserved = preserved.get('Main Strand Radius')
thread_radius_value = pick_value(thread_radius_override, thread_radius_preserved, 0.028)
if not maybe_set_modifier_input(weave_mod, weave_group, 'Thread Radius', thread_radius_value):
    maybe_set_modifier_input(weave_mod, weave_group, 'Main Strand Radius', thread_radius_value)
maybe_set_modifier_input(weave_mod, weave_group, 'Thread Subdivisions', pick_value(thread_subdivisions_override, preserved.get('Thread Subdivisions'), 8.0))
maybe_set_modifier_input(weave_mod, weave_group, 'Ply Count', int(round(pick_value(ply_count_override, preserved.get('Ply Count'), 3))))
maybe_set_modifier_input(weave_mod, weave_group, 'Ply Radius', pick_value(ply_radius_override, preserved.get('Ply Radius'), 0.013))
maybe_set_modifier_input(weave_mod, weave_group, 'Twist Amount', pick_value(twist_amount_override, preserved.get('Twist Amount'), 16.0))
maybe_set_modifier_input(weave_mod, weave_group, 'Ply Resolution', int(round(pick_value(ply_resolution_override, preserved.get('Ply Resolution'), 5))))
maybe_set_modifier_input(weave_mod, weave_group, 'Texture Scale U', pick_value(texture_scale_u_override, preserved.get('Texture Scale U'), 8.0))
if uses_scan_knotty_group:
    maybe_set_modifier_input(weave_mod, weave_group, 'Texture Scale V', 1.0)
    maybe_set_modifier_input(weave_mod, weave_group, 'Texture Offset V', 0.0)
    maybe_set_modifier_input(weave_mod, weave_group, 'Texture Side Flatten', 0.0)
    maybe_set_modifier_input(weave_mod, weave_group, 'Sub Texture Scale V', 0.0)
    maybe_set_modifier_input(weave_mod, weave_group, 'Sub Texture Offset V', 0.0)
else:
    maybe_set_modifier_input(weave_mod, weave_group, 'Texture Scale V', pick_value(texture_scale_v_override, preserved.get('Texture Scale V'), 0.5))
    maybe_set_modifier_input(weave_mod, weave_group, 'Texture Offset V', pick_value(texture_offset_v_override, preserved.get('Texture Offset V'), 0.0))
    maybe_set_modifier_input(weave_mod, weave_group, 'Texture Side Flatten', pick_value(texture_side_flatten_override, preserved.get('Texture Side Flatten'), 0.7))
maybe_set_modifier_input(weave_mod, weave_group, 'Lump Strength', pick_value(lump_strength_override, preserved.get('Lump Strength'), 0.0015))
maybe_set_modifier_input(weave_mod, weave_group, 'Lump Scale', pick_value(lump_scale_override, preserved.get('Lump Scale'), 6.0))
maybe_set_modifier_input(weave_mod, weave_group, 'Fiber Density', pick_value(fiber_density_override, preserved.get('Fiber Density'), 0.0))
maybe_set_modifier_input(weave_mod, weave_group, 'Fiber Length', pick_value(fiber_length_override, preserved.get('Fiber Length'), 0.04))
maybe_set_modifier_input(weave_mod, weave_group, 'Fiber Thickness', pick_value(fiber_thickness_override, preserved.get('Fiber Thickness'), 0.15))
maybe_set_modifier_input(weave_mod, weave_group, 'Fiber Frizz', pick_value(fiber_frizz_override, preserved.get('Fiber Frizz'), 0.02))
maybe_set_modifier_input(weave_mod, weave_group, 'Fiber Subdivs', int(round(pick_value(fiber_subdivs_override, preserved.get('Fiber Subdivs'), 4))))
maybe_set_modifier_input(weave_mod, weave_group, 'Seed', int(round(pick_value(seed_override, preserved.get('Seed'), 0))))
material_count_floor = material_count_override if material_count_override is not None else max(len(warp_colors), len(weft_colors), 2)
material_count_value = preserved.get('Material Count')
if material_count_value is None:
    material_count_value = material_count_floor
else:
    material_count_value = max(int(material_count_value), material_count_floor)
maybe_set_modifier_input(weave_mod, weave_group, 'Material Count', material_count_value)

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

if target_obj.data is not None and hasattr(target_obj.data, 'materials') and not has_modifier_input(weave_group, 'Material 1'):
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
    'draft_object': draft_obj.name if draft_obj is not None else None,
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
