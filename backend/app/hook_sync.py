from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from .blender_sync import send_blender_command


DEFAULT_HOOK_ROWS = 15
DEFAULT_HOOK_COLUMNS = 21
MAX_HOOK_MATERIAL_SLOTS = 16

DEFAULT_HOOK_RENDER_SETTINGS: dict[str, Any] = {
    "hookScale": 0.07,
    "legWidth": 0.67,
    "loopHeight": 2.2,
    "handleScale": 0.6,
    "legZOffset": 0.218,
    "tubeRadius": 0.25,
    "curveResolution": 7,
    "tubeResolution": 11,
    "textureScaleU": 1.06,
    "textureScaleV": 0.93,
    "textureOffsetV": -0.44,
    "textureSideFlatten": 0.0,
    "arc1VPadding": 0.0,
    "fillRatio": 1.0,
    "seed": 1,
}

DEFAULT_HOOK_STITCH_LEGEND: list[dict[str, Any]] = [
    {"code": 0, "symbol": "empty", "abbreviation": "empty", "label": "Empty / no stitch", "archetype": "empty", "supported": True},
    {"code": 1, "symbol": "loop", "abbreviation": "hk", "label": "Standard interlocking hook loop", "archetype": "standard_hook_loop", "supported": True},
    {"code": 2, "symbol": "ch", "abbreviation": "ch", "label": "Chain / foundation", "archetype": "chain_foundation", "supported": False, "fallbackCode": 1},
    {"code": 3, "symbol": "sl st", "abbreviation": "sl st", "label": "Slip stitch", "archetype": "slip_stitch", "supported": False, "fallbackCode": 1},
    {"code": 4, "symbol": "sc", "abbreviation": "sc", "label": "Single crochet", "archetype": "single_crochet", "supported": False, "fallbackCode": 1},
    {"code": 5, "symbol": "dc", "abbreviation": "dc", "label": "Double crochet", "archetype": "double_crochet", "supported": False, "fallbackCode": 1},
    {"code": 6, "symbol": "V", "abbreviation": "k", "label": "Knit V", "archetype": "knit_v", "supported": False, "fallbackCode": 1},
    {"code": 7, "symbol": "p", "abbreviation": "p", "label": "Purl bump", "archetype": "purl_bump", "supported": False, "fallbackCode": 1},
    {"code": 8, "symbol": "yo", "abbreviation": "yo", "label": "Yarn-over / open hole", "archetype": "yarn_over_open", "supported": False, "fallbackCode": 1},
    {"code": 9, "symbol": "tuck", "abbreviation": "tuck", "label": "Tuck stitch", "archetype": "tuck", "supported": False, "fallbackCode": 1},
    {"code": 10, "symbol": "miss", "abbreviation": "miss", "label": "Miss / float", "archetype": "miss_float", "supported": False, "fallbackCode": 1},
    {"code": 11, "symbol": "cable", "abbreviation": "cable", "label": "Cable / crossing", "archetype": "cable_crossing", "supported": False, "fallbackCode": 1},
]

HOOK_STRUCTURE_FAMILIES = {"crochet_hook", "knit_chart", "machine_knit", "generic_loop_grid"}
HOOK_ROW_DIRECTIONS = {"right_to_left", "left_to_right", "alternating", "in_the_round"}
HOOK_SOURCE_KINDS = {"builtin", "generated", "literal", "user-authored", "imported", "catalog-reference"}
HOOK_SOURCE_ACCESSES = {"builtin", "public-domain", "catalog", "local", "linked"}
HOOK_STITCH_ARCHETYPES = {
    "empty",
    "standard_hook_loop",
    "chain_foundation",
    "slip_stitch",
    "single_crochet",
    "double_crochet",
    "knit_v",
    "purl_bump",
    "yarn_over_open",
    "tuck",
    "miss_float",
    "cable_crossing",
    "reserved",
}


HOOK_GEOMETRY_PY = r"""
import math
from mathutils import Vector


def _hook_clamp(value, minimum, maximum):
    return min(maximum, max(minimum, value))


def _hook_float(value, default):
    try:
        parsed = float(value)
    except Exception:
        return default
    return parsed if parsed == parsed else default


def _hook_int(value, default):
    try:
        return int(round(float(value)))
    except Exception:
        return default


def _catmull_rom(p0, p1, p2, p3, t):
    t2 = t * t
    t3 = t2 * t
    return (p1 * 2.0 + (p2 - p0) * t + (p0 * 2.0 - p1 * 5.0 + p2 * 4.0 - p3) * t2 + (-p0 + p1 * 3.0 - p2 * 3.0 + p3) * t3) * 0.5


def _sample_controls(controls, resolution):
    padded = [controls[0], *controls, controls[-1]]
    points = []
    for index in range(1, len(padded) - 2):
        for step in range(resolution):
            t = step / float(resolution)
            points.append(_catmull_rom(padded[index - 1], padded[index], padded[index + 1], padded[index + 2], t))
    points.append(controls[-1])
    return points


def _sample_hook_cell_strip(row, col, phase, settings):
    leg_width = _hook_clamp(_hook_float(settings.get('legWidth'), 0.71), 0.05, 1.25)
    loop_height = _hook_clamp(_hook_float(settings.get('loopHeight'), 2.08), 0.05, 8.0)
    handle_scale = _hook_clamp(_hook_float(settings.get('handleScale'), 0.6), 0.05, 2.0)
    leg_z_offset = _hook_clamp(_hook_float(settings.get('legZOffset'), 0.218), -2.0, 2.0)
    curve_resolution = max(4, min(96, _hook_int(settings.get('curveResolution'), 7)))

    row_shift = 0.48 if row % 2 else 0.0
    row_pitch = 0.82
    x0 = float(col) + row_shift
    x1 = float(col + 1) + row_shift
    cx = x0 + 0.5
    row_base = -float(row) * row_pitch
    swing = min(0.48, max(0.18, leg_width * 0.52))
    crown = min(0.42, max(0.12, handle_scale * 0.46))
    z_mid = leg_z_offset * 0.72
    z_top = leg_z_offset + loop_height * 0.12
    z_under = -abs(leg_z_offset) * 0.28
    lower_pull = 0.24 if row % 2 else -0.02

    if phase == 0:
        controls = [
            Vector((x0, row_base - 0.50, 0.0)),
            Vector((x0 + 0.18, row_base - 0.50 + swing * 0.55, z_mid)),
            Vector((cx, row_base + crown, z_top)),
            Vector((x1 - 0.18, row_base - 0.50 + swing * 0.55, z_mid)),
            Vector((x1, row_base - 0.50, 0.0)),
        ]
    else:
        controls = [
            Vector((x0, row_base - 0.08 + lower_pull, z_mid * 0.35)),
            Vector((x0 + 0.22, row_base - 0.70 + lower_pull * 0.35, z_under)),
            Vector((cx, row_base - 0.90 + lower_pull * 0.15, z_under - loop_height * 0.018)),
            Vector((x1 - 0.22, row_base - 0.70 + lower_pull * 0.35, z_under)),
            Vector((x1, row_base - 0.08 + lower_pull, z_mid * 0.35)),
        ]
    return _sample_controls(controls, curve_resolution)


def _sample_hook_wale_cell(row, col, settings, phase=0):
    leg_width = _hook_clamp(_hook_float(settings.get('legWidth'), 0.67), 0.05, 1.25)
    loop_height = _hook_clamp(_hook_float(settings.get('loopHeight'), 2.2), 0.05, 8.0)
    handle_scale = _hook_clamp(_hook_float(settings.get('handleScale'), 0.6), 0.05, 2.0)
    leg_z_offset = _hook_clamp(_hook_float(settings.get('legZOffset'), 0.218), -2.0, 2.0)
    curve_resolution = max(5, min(96, _hook_int(settings.get('curveResolution'), 7)))

    row_pitch = _hook_clamp(0.62 + loop_height * 0.095, 0.58, 1.22)
    center_x = float(col) + 0.5
    y_top = -float(row) * row_pitch
    y_mid = y_top - row_pitch * 0.5
    y_bottom = y_top - row_pitch

    # Paired mirrored wales reproduce the pre-V2 hook family better than a
    # single zig-zag strand: each column has left/right hook legs that trade
    # over-under depth and make the dark gaps read as loop interiors.
    phase_side = -1.0 if phase == 0 else 1.0
    side = phase_side if row % 2 == 0 else -phase_side
    swing = _hook_clamp(leg_width * 0.27 + handle_scale * 0.045, 0.12, 0.38)
    waist = _hook_clamp(swing * 0.20, 0.035, 0.12)
    shoulder = _hook_clamp(swing * 0.56, 0.08, 0.24)
    over = 1.0 if (row + col + phase) % 2 == 0 else -1.0
    z_front = leg_z_offset + loop_height * 0.042
    z_back = -abs(leg_z_offset) * 0.42 - loop_height * 0.014
    z_center = leg_z_offset * 0.18
    top_x = center_x - side * shoulder
    outer_x = center_x + side * swing
    inner_x = center_x - side * waist
    exit_x = center_x + side * shoulder

    controls = [
        Vector((top_x, y_top, z_center)),
        Vector((center_x - side * shoulder, y_top - row_pitch * 0.16, z_front if over > 0 else z_back)),
        Vector((inner_x, y_top - row_pitch * 0.28, z_front * 0.74 if over > 0 else z_back * 0.74)),
        Vector((outer_x, y_mid, z_front if over > 0 else z_back)),
        Vector((inner_x, y_bottom + row_pitch * 0.28, z_back if over > 0 else z_front)),
        Vector((center_x - side * shoulder, y_bottom + row_pitch * 0.16, z_back * 0.55 if over > 0 else z_front * 0.55)),
        Vector((exit_x, y_bottom, z_center)),
    ]
    return _sample_controls(controls, curve_resolution)


def _iter_active_runs(row, columns):
    start = None
    for col in range(columns):
        flat_index = row * columns + col
        stitch_code = int(attributes['stitch_code'][flat_index])
        if stitch_code != 0 and start is None:
            start = col
        if (stitch_code == 0 or col == columns - 1) and start is not None:
            end = col - 1 if stitch_code == 0 else col
            yield start, end
            start = None


def _iter_active_column_runs(col, rows, columns):
    start = None
    for row in range(rows):
        flat_index = row * columns + col
        stitch_code = int(attributes['stitch_code'][flat_index])
        if stitch_code != 0 and start is None:
            start = row
        if (stitch_code == 0 or row == rows - 1) and start is not None:
            end = row - 1 if stitch_code == 0 else row
            yield start, end
            start = None


def _fallback_material(index):
    if index == 0:
        material = bpy.data.materials.get('RopeTexture') or bpy.data.materials.get('Rope')
        if material is not None:
            return material
    name = 'HookMaterial_' + str(index + 1).zfill(2)
    material = bpy.data.materials.get(name)
    if material is None:
        material = bpy.data.materials.new(name)
        color_seed = (index * 0.137) % 1.0
        material.diffuse_color = (0.55 + color_seed * 0.25, 0.46 + (1.0 - color_seed) * 0.20, 0.34 + color_seed * 0.18, 1.0)
    return material


def _append_material_slots(mesh, existing_materials):
    for index in range(16):
        material = existing_materials[index] if index < len(existing_materials) and existing_materials[index] is not None else _fallback_material(index)
        mesh.materials.append(material)


def _write_int_face_attr(mesh, name, values):
    attr = mesh.attributes.new(name, 'INT', 'FACE')
    for index, value in enumerate(values):
        attr.data[index].value = int(value)


def _write_float_face_attr(mesh, name, values):
    attr = mesh.attributes.new(name, 'FLOAT', 'FACE')
    for index, value in enumerate(values):
        attr.data[index].value = float(value)


def _write_float_point_attr(mesh, name, values):
    attr = mesh.attributes.new(name, 'FLOAT', 'POINT')
    for index, value in enumerate(values):
        attr.data[index].value = float(value)


def _write_vector_point_attr(mesh, name, values):
    attr = mesh.attributes.new(name, 'FLOAT_VECTOR', 'POINT')
    for index, value in enumerate(values):
        attr.data[index].vector = values[index]


def create_hook_geometry_mesh(target_obj):
    rows = int(pattern['rows'])
    columns = int(pattern['columns'])
    settings = pattern.get('renderSettings') or {}
    pattern_scale_ratio = _hook_clamp(_hook_float(settings.get('hookScale'), 0.07) / 0.07, 0.25, 4.0)
    tube_radius = _hook_clamp(_hook_float(settings.get('tubeRadius'), 0.25) * pattern_scale_ratio, 0.002, 0.9)
    tube_resolution = max(3, min(64, _hook_int(settings.get('tubeResolution'), 11)))
    texture_scale_u = _hook_float(settings.get('textureScaleU'), 1.0)
    texture_scale_v = _hook_float(settings.get('textureScaleV'), 0.47)
    texture_offset_v = _hook_float(settings.get('textureOffsetV'), -0.46)

    vertices = []
    faces = []
    point_u_along = []
    point_v_around = []
    point_uv_scaled = []
    face_stitch_code = []
    face_chain_id = []
    face_chain_u_index = []
    face_material_id = []
    face_source_image_width_px = []
    face_texture_world_width_bu = []
    face_material_slots = []
    strip_components = 0

    def emit_strip(path, path_flat_indices, phase):
        if len(path) < 2:
            return False
        distances = [0.0]
        total = 0.0
        for path_index in range(1, len(path)):
            total += (path[path_index] - path[path_index - 1]).length
            distances.append(total)
        if total <= 0.000001:
            total = 1.0

        start_vertex = len(vertices)
        u_phase_offset = phase * 0.5
        for path_index, point in enumerate(path):
            if path_index == 0:
                tangent = path[1] - path[0]
            elif path_index == len(path) - 1:
                tangent = path[-1] - path[-2]
            else:
                tangent = path[path_index + 1] - path[path_index - 1]
            if tangent.length <= 0.000001:
                tangent = Vector((1.0, 0.0, 0.0))
            tangent.normalize()
            up = Vector((0.0, 0.0, 1.0))
            normal = tangent.cross(up)
            if normal.length <= 0.000001:
                normal = Vector((1.0, 0.0, 0.0))
            normal.normalize()
            binormal = normal.cross(tangent)
            if binormal.length <= 0.000001:
                binormal = up.copy()
            binormal.normalize()

            u_value = distances[path_index] + u_phase_offset
            for around in range(tube_resolution):
                angle = (math.tau * around) / float(tube_resolution)
                offset = normal * (math.cos(angle) * tube_radius) + binormal * (math.sin(angle) * tube_radius)
                vertices.append(tuple(point + offset))
                v_value = around / float(tube_resolution)
                point_u_along.append(u_value)
                point_v_around.append(v_value)
                point_uv_scaled.append((u_value * texture_scale_u, v_value * texture_scale_v + texture_offset_v, 0.0))

        for path_index in range(len(path) - 1):
            flat_index = path_flat_indices[path_index]
            stitch_code = int(attributes['stitch_code'][flat_index])
            chain_id = int(attributes['chain_id'][flat_index])
            chain_u_index = int(attributes['chain_u_index'][flat_index])
            material_slot = max(0, min(15, int(attributes['chain_material_id'][flat_index])))
            for around in range(tube_resolution):
                a = start_vertex + path_index * tube_resolution + around
                b = start_vertex + path_index * tube_resolution + ((around + 1) % tube_resolution)
                c = start_vertex + (path_index + 1) * tube_resolution + ((around + 1) % tube_resolution)
                d = start_vertex + (path_index + 1) * tube_resolution + around
                faces.append((a, b, c, d))
                face_stitch_code.append(stitch_code)
                face_chain_id.append(chain_id)
                face_chain_u_index.append(chain_u_index)
                face_material_id.append(material_slot + 1)
                face_source_image_width_px.append(1.0)
                face_texture_world_width_bu.append(1.0)
                face_material_slots.append(material_slot)
        return True

    for col in range(columns):
        for phase in (0, 1):
            for start_row, end_row in _iter_active_column_runs(col, rows, columns):
                path = []
                path_flat_indices = []
                for row in range(start_row, end_row + 1):
                    flat_index = row * columns + col
                    cell_points = _sample_hook_wale_cell(row, col, settings, phase)
                    if path:
                        cell_points = cell_points[1:]
                    path.extend(cell_points)
                    path_flat_indices.extend([flat_index] * len(cell_points))
                if emit_strip(path, path_flat_indices, phase):
                    strip_components += 1

    mesh = bpy.data.meshes.new(target_obj.name + '_HookMesh')
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    existing_materials = [slot.material for slot in getattr(target_obj, 'material_slots', [])]
    _append_material_slots(mesh, existing_materials)
    for face_index, material_slot in enumerate(face_material_slots):
        mesh.polygons[face_index].material_index = material_slot
    if faces:
        _write_int_face_attr(mesh, 'stitch_code_sampled', face_stitch_code)
        _write_int_face_attr(mesh, 'chain_id', face_chain_id)
        _write_int_face_attr(mesh, 'chain_u_index', face_chain_u_index)
        _write_int_face_attr(mesh, 'material_id', face_material_id)
        _write_float_face_attr(mesh, 'source_image_width_px', face_source_image_width_px)
        _write_float_face_attr(mesh, 'texture_world_width_bu', face_texture_world_width_bu)
        _write_float_point_attr(mesh, 'u_along', point_u_along)
        _write_float_point_attr(mesh, 'v_around', point_v_around)
        _write_vector_point_attr(mesh, 'uv_scaled', point_uv_scaled)

    old_mesh = target_obj.data
    target_obj.data = mesh
    if old_mesh is not None and old_mesh.users == 0:
        bpy.data.meshes.remove(old_mesh)
    target_obj['hook_generated_vertices'] = len(vertices)
    target_obj['hook_generated_faces'] = len(faces)
    target_obj['hook_generated_components'] = strip_components
    target_obj['hook_generated_construction'] = 'interlocking_vertical_wales'
    return {
        'vertices': len(vertices),
        'faces': len(faces),
        'components': strip_components,
        'construction': 'interlocking_vertical_wales',
    }
"""


HOOK_LIVE_CONTROL_PY = r"""
from bpy.app.handlers import persistent


HOOK_RENDER_SOCKET_MAP = {
    'Pattern Scale': ('hookScale', float),
    'Leg Width': ('legWidth', float),
    'Loop Height': ('loopHeight', float),
    'Handle Scale': ('handleScale', float),
    'Leg Z Offset': ('legZOffset', float),
    'Half Tube Radius': ('tubeRadius', float),
    'Curve Resolution': ('curveResolution', int),
    'Tube Resolution': ('tubeResolution', int),
    'Texture Scale U': ('textureScaleU', float),
    'Texture Scale V': ('textureScaleV', float),
    'Texture Offset V': ('textureOffsetV', float),
    'Texture Side Flatten': ('textureSideFlatten', float),
    'Arc 1 V Padding': ('arc1VPadding', float),
    'Seed': ('seed', int),
}


def _hook_json_loads(value, fallback):
    if not value:
        return fallback
    try:
        parsed = json.loads(value)
    except Exception:
        return fallback
    return parsed if isinstance(parsed, dict) else fallback


def _hook_socket_identifier(node_group, name):
    try:
        return ensure_socket(node_group, name).identifier
    except Exception:
        return None


def _hook_modifier_value(modifier, node_group, name, fallback):
    identifier = _hook_socket_identifier(node_group, name)
    if not identifier:
        return fallback
    try:
        value = modifier[identifier]
    except Exception:
        return fallback
    return fallback if value is None else value


def _hook_numeric_modifier_value(modifier, node_group, name, fallback, caster):
    value = _hook_modifier_value(modifier, node_group, name, fallback)
    try:
        if caster is int:
            return int(round(float(value)))
        return float(value)
    except Exception:
        return fallback


def _hook_matrix_value(source, row, col, rows, columns, fallback, repeat=None):
    if repeat and repeat.get('mode') == 'tile':
        repeat_rows = max(1, int(repeat.get('rows') or rows or 1))
        repeat_columns = max(1, int(repeat.get('columns') or columns or 1))
        row_index = row % repeat_rows
        col_index = col % repeat_columns
    else:
        row_index = row
        col_index = col
    if isinstance(source, list) and row_index < len(source) and isinstance(source[row_index], list) and col_index < len(source[row_index]):
        return source[row_index][col_index]
    return fallback(row, col)


def _hook_resized_matrix(source, rows, columns, fallback, repeat=None):
    out = []
    for row in range(rows):
        out_row = []
        for col in range(columns):
            try:
                value = int(round(float(_hook_matrix_value(source, row, col, rows, columns, fallback, repeat))))
            except Exception:
                value = int(fallback(row, col))
            out_row.append(value)
        out.append(out_row)
    return out


def _compute_live_hook_face_attributes(live_pattern):
    rows = max(1, int(live_pattern.get('rows') or 1))
    columns = max(1, int(live_pattern.get('columns') or 1))
    repeat = live_pattern.get('repeat') if isinstance(live_pattern.get('repeat'), dict) else None
    stitch_codes = _hook_resized_matrix(live_pattern.get('stitchCodes'), rows, columns, lambda _r, _c: 1, repeat)
    chain_ids = _hook_resized_matrix(live_pattern.get('chainIds'), rows, columns, lambda _r, c: c, repeat)
    course_ids = _hook_resized_matrix(live_pattern.get('courseIds'), rows, columns, lambda r, _c: r, repeat)
    wale_ids = _hook_resized_matrix(live_pattern.get('waleIds'), rows, columns, lambda _r, c: c, repeat)

    chains = live_pattern.get('chains') if isinstance(live_pattern.get('chains'), list) else []
    material_by_chain = {}
    for chain in chains:
        if not isinstance(chain, dict):
            continue
        try:
            chain_id = max(0, int(round(float(chain.get('id', 0)))))
            material_by_chain[chain_id] = max(0, min(15, int(round(float(chain.get('materialSlot', 0))))))
        except Exception:
            continue

    active_by_chain = {}
    for row in range(rows):
        for col in range(columns):
            stitch_code = int(stitch_codes[row][col])
            if stitch_code == 0:
                continue
            chain_id = max(0, int(chain_ids[row][col]))
            active_by_chain.setdefault(chain_id, []).append((row, col))
            material_by_chain.setdefault(chain_id, 0)

    u_index_lookup = {}
    for chain_cells in active_by_chain.values():
        for index, cell in enumerate(sorted(chain_cells)):
            u_index_lookup[cell] = index

    out = {
        'stitch_code': [],
        'chain_id': [],
        'chain_u_index': [],
        'chain_material_id': [],
        'course_id': [],
        'wale_id': [],
    }
    for row in range(rows):
        for col in range(columns):
            stitch_code = int(stitch_codes[row][col])
            chain_id = max(0, int(chain_ids[row][col])) if stitch_code != 0 else -1
            out['stitch_code'].append(stitch_code)
            out['chain_id'].append(chain_id)
            out['chain_u_index'].append(u_index_lookup.get((row, col), -1))
            out['chain_material_id'].append(material_by_chain.get(chain_id, -1) if chain_id >= 0 else -1)
            out['course_id'].append(max(0, int(course_ids[row][col])) if stitch_code != 0 else -1)
            out['wale_id'].append(max(0, int(wale_ids[row][col])) if stitch_code != 0 else -1)
    return out


def _live_hook_build_spec(live_pattern, live_attributes):
    rows = max(1, int(live_pattern.get('rows') or 1))
    columns = max(1, int(live_pattern.get('columns') or 1))
    stitch_values = [int(value) for value in live_attributes.get('stitch_code', [])]
    stitch_counts = {}
    for stitch_code in stitch_values:
        stitch_counts[str(stitch_code)] = stitch_counts.get(str(stitch_code), 0) + 1

    legend_by_code = {}
    for entry in live_pattern.get('stitchLegend') if isinstance(live_pattern.get('stitchLegend'), list) else []:
        if not isinstance(entry, dict):
            continue
        try:
            legend_by_code[int(entry.get('code'))] = entry
        except Exception:
            continue
    unsupported_codes = []
    fallback_codes = {}
    for code_text, count in stitch_counts.items():
        code = int(code_text)
        if count <= 0 or code == 0:
            continue
        legend = legend_by_code.get(code, {})
        if not bool(legend.get('supported')):
            unsupported_codes.append(code)
            try:
                fallback_codes[str(code)] = int(legend.get('fallbackCode') or 1)
            except Exception:
                fallback_codes[str(code)] = 1

    chain_counts = {}
    material_by_chain = {}
    for index, chain_id in enumerate(live_attributes.get('chain_id', [])):
        chain_id = int(chain_id)
        if chain_id < 0:
            continue
        chain_counts[chain_id] = chain_counts.get(chain_id, 0) + 1
        material_values = live_attributes.get('chain_material_id', [])
        if index < len(material_values):
            material_by_chain[chain_id] = int(material_values[index])
    chains = []
    for chain in live_pattern.get('chains') if isinstance(live_pattern.get('chains'), list) else []:
        if not isinstance(chain, dict):
            continue
        try:
            chain_id = int(chain.get('id'))
        except Exception:
            continue
        active_count = int(chain_counts.get(chain_id, 0))
        if active_count <= 0:
            continue
        chains.append({
            'id': chain_id,
            'materialSlot': int(material_by_chain.get(chain_id, chain.get('materialSlot', 0))),
            'direction': str(chain.get('direction') or 'vertical'),
            'activeCells': active_count,
            'uIndexRange': [0, max(0, active_count - 1)],
        })

    active_cells = sum(count for code, count in ((int(key), value) for key, value in stitch_counts.items()) if code != 0)
    material_slots = sorted(set(int(value) for value in live_attributes.get('chain_material_id', []) if int(value) >= 0))
    spec = json.loads(json.dumps(build_spec))
    spec['frontendIntent'] = dict(spec.get('frontendIntent') or {})
    spec['frontendIntent'].update({
        'structureType': live_pattern.get('structureType', 'hook'),
        'structureFamily': live_pattern.get('structureFamily', 'crochet_hook'),
        'rowDirection': live_pattern.get('rowDirection', 'alternating'),
        'repeat': live_pattern.get('repeat'),
        'title': live_pattern.get('title', ''),
        'source': live_pattern.get('source') if isinstance(live_pattern.get('source'), dict) else {},
        'gauge': live_pattern.get('gauge') if isinstance(live_pattern.get('gauge'), dict) else None,
    })
    spec['grid'] = {
        'rows': rows,
        'columns': columns,
        'totalCells': rows * columns,
        'activeCells': active_cells,
        'emptyCells': rows * columns - active_cells,
        'visibleRows': rows,
        'visibleColumns': columns,
    }
    spec['stitches'] = {
        'counts': {key: stitch_counts[key] for key in sorted(stitch_counts, key=lambda item: int(item))},
        'supportedCodes': sorted(int(code) for code, count in stitch_counts.items() if count > 0 and bool(legend_by_code.get(int(code), {}).get('supported'))),
        'unsupportedCodes': sorted(unsupported_codes),
        'fallbackCodes': fallback_codes,
        'v1RenderedCodes': sorted(int(code) for code, count in stitch_counts.items() if count > 0 and int(code) != 0),
        'v1GeometryArchetype': 'standard_interlocking_hook_loop',
    }
    spec['continuity'] = dict(spec.get('continuity') or {})
    spec['continuity'].update({
        'chainModel': 'per_chain_active_cell_order',
        'uIndexAttribute': 'chain_u_index',
        'chainIdAttribute': 'chain_id',
        'courseIdAttribute': 'course_id',
        'waleIdAttribute': 'wale_id',
        'sparseCellsDoNotResetU': True,
        'chains': chains,
    })
    spec['materials'] = dict(spec.get('materials') or {})
    spec['materials'].update({
        'slotBase': 0,
        'maxSlots': 16,
        'usedSlots': material_slots,
        'attribute': 'chain_material_id',
        'generatedMaterialIdAttribute': 'material_id',
    })
    spec['renderSettings'] = live_pattern.get('renderSettings') if isinstance(live_pattern.get('renderSettings'), dict) else {}
    spec['attributes'] = {
        'faceAttributeCount': len(stitch_values),
        'names': sorted(live_attributes.keys()),
    }
    return spec


def _hook_pattern_from_modifier(target_obj, hook_mod, hook_group):
    source_pattern = _hook_json_loads(
        target_obj.get('_hook_source_pattern_json'),
        _hook_json_loads(target_obj.get('_hook_live_pattern_json'), pattern),
    )
    live_pattern = json.loads(json.dumps(source_pattern))
    rows = max(1, _hook_numeric_modifier_value(hook_mod, hook_group, 'Row', int(source_pattern.get('rows') or 1), int))
    columns = max(1, _hook_numeric_modifier_value(hook_mod, hook_group, 'Columns', int(source_pattern.get('columns') or 1), int))
    live_pattern['rows'] = rows
    live_pattern['columns'] = columns

    settings = dict(source_pattern.get('renderSettings') if isinstance(source_pattern.get('renderSettings'), dict) else {})
    for socket_name, (setting_key, caster) in HOOK_RENDER_SOCKET_MAP.items():
        fallback = settings.get(setting_key, 0)
        settings[setting_key] = _hook_numeric_modifier_value(hook_mod, hook_group, socket_name, fallback, caster)
    live_pattern['renderSettings'] = settings
    return live_pattern


def _hook_live_signature(live_pattern):
    settings = live_pattern.get('renderSettings') if isinstance(live_pattern.get('renderSettings'), dict) else {}
    return json.dumps({
        'rows': int(live_pattern.get('rows') or 0),
        'columns': int(live_pattern.get('columns') or 0),
        'settings': {key: settings.get(key) for key in sorted(settings)},
    }, sort_keys=True)


def show_reference_hook_modifier(modifier):
    if modifier is None:
        return {'viewport': None, 'render': None}
    modifier.show_viewport = True
    modifier.show_render = True
    return {'viewport': modifier.show_viewport, 'render': modifier.show_render}


def rebuild_hook_from_modifier(target_name=target_object_name, force=False):
    target_obj = bpy.data.objects.get(target_name)
    if target_obj is None:
        return {'changed': False, 'reason': 'missing target'}
    hook_mod = target_obj.modifiers.get('Hook')
    if hook_mod is None or hook_mod.type != 'NODES' or hook_mod.node_group is None:
        return {'changed': False, 'reason': 'missing hook modifier'}
    hook_group = hook_mod.node_group
    live_pattern = _hook_pattern_from_modifier(target_obj, hook_mod, hook_group)
    signature = _hook_live_signature(live_pattern)
    if not force and target_obj.get('_hook_live_socket_signature') == signature:
        return {'changed': False, 'reason': 'unchanged'}

    globals()['pattern'] = live_pattern
    globals()['attributes'] = _compute_live_hook_face_attributes(live_pattern)
    live_build_spec = _live_hook_build_spec(live_pattern, globals()['attributes'])
    target_obj['_hook_live_socket_signature'] = signature
    target_obj['_hook_live_pattern_json'] = json.dumps(live_pattern)
    target_obj['_hook_build_spec_json'] = json.dumps(live_build_spec)
    target_obj['hook_build_mode'] = live_build_spec.get('buildMode', '')
    target_obj['hook_interpreter'] = live_build_spec.get('interpreter', '')

    maybe_set_modifier_input(hook_mod, hook_group, 'Draft Rows', int(live_pattern['rows']))
    maybe_set_modifier_input(hook_mod, hook_group, 'Draft Columns', int(live_pattern['columns']))
    hook_draft = create_hook_draft_object()
    modifier_display = show_reference_hook_modifier(hook_mod)
    bpy.context.view_layer.update()
    geometry_summary = evaluated_hook_geometry_summary(target_obj, 'gn_reference_rows_columns_material')
    target_obj['hook_pattern_title'] = live_pattern.get('title', '')
    target_obj['hook_source_label'] = live_pattern.get('sourceLabel', '')
    target_obj['hook_live_controls_active'] = True
    return {
        'changed': True,
        'reason': 'rebuilt',
        'rows': live_pattern['rows'],
        'columns': live_pattern['columns'],
        'draftObject': hook_draft.name,
        'geometry': geometry_summary,
        'modifierDisplay': modifier_display,
    }


def _remove_existing_hook_live_handlers():
    removed = 0
    for handler in list(bpy.app.handlers.depsgraph_update_post):
        if getattr(handler, '__name__', '') == 'procedural_hook_live_control_handler':
            bpy.app.handlers.depsgraph_update_post.remove(handler)
            removed += 1
    return removed


def disable_hook_live_control_handler():
    removed = _remove_existing_hook_live_handlers()
    timer_removed = False
    old_timer = bpy.app.driver_namespace.get('procedural_hook_live_control_timer')
    if old_timer is not None:
        try:
            if bpy.app.timers.is_registered(old_timer):
                bpy.app.timers.unregister(old_timer)
                timer_removed = True
        except Exception:
            pass
    bpy.app.driver_namespace.pop('procedural_hook_live_control_timer', None)
    return {
        'installed': False,
        'reason': 'native_modifier_controls',
        'removedExistingHandlers': removed,
        'timerRemoved': timer_removed,
    }


def install_native_hook_refresh_handler(target_name=target_object_name):
    disabled = disable_hook_live_control_handler()
    namespace = bpy.app.driver_namespace
    old_timer = namespace.get('procedural_hook_native_refresh_timer')
    timer_removed = False
    if old_timer is not None:
        try:
            if bpy.app.timers.is_registered(old_timer):
                bpy.app.timers.unregister(old_timer)
                timer_removed = True
        except Exception:
            pass

    watched_sockets = [
        'Row',
        'Columns',
        'Pattern Scale',
        'Leg Width',
        'Loop Height',
        'Handle Scale',
        'Leg Z Offset',
        'Half Tube Radius',
        'Curve Resolution',
        'Tube Resolution',
        'Texture Scale U',
        'Texture Scale V',
        'Texture Offset V',
        'Texture Side Flatten',
    ]

    def native_hook_signature(target_obj):
        hook_mod = target_obj.modifiers.get('Hook')
        if hook_mod is None or hook_mod.type != 'NODES' or hook_mod.node_group is None:
            return ''
        values = {}
        for socket_name in watched_sockets:
            identifier = _hook_socket_identifier(hook_mod.node_group, socket_name)
            if not identifier:
                continue
            try:
                value = hook_mod[identifier]
            except Exception:
                continue
            try:
                values[socket_name] = float(value)
            except Exception:
                values[socket_name] = str(value)
        return json.dumps(values, sort_keys=True)

    def procedural_hook_native_refresh_timer():
        target_obj = bpy.data.objects.get(target_name)
        if target_obj is None:
            return None
        hook_mod = target_obj.modifiers.get('Hook')
        if hook_mod is None:
            return None
        signature = native_hook_signature(target_obj)
        if target_obj.get('_hook_native_socket_signature') != signature:
            target_obj['_hook_native_socket_signature'] = signature
            previous = hook_mod.show_viewport
            hook_mod.show_viewport = False
            bpy.context.view_layer.update()
            hook_mod.show_viewport = previous
            bpy.context.view_layer.update()
        return 0.35

    namespace['procedural_hook_native_refresh_timer'] = procedural_hook_native_refresh_timer
    bpy.app.timers.register(procedural_hook_native_refresh_timer, first_interval=0.35, persistent=True)
    target_obj = bpy.data.objects.get(target_name)
    if target_obj is not None:
        target_obj['_hook_native_socket_signature'] = native_hook_signature(target_obj)
    return {
        'installed': True,
        'reason': 'native_modifier_refresh',
        'disabledGeneratedBridge': disabled,
        'timerRemoved': timer_removed,
        'timerRegistered': True,
    }


def install_hook_live_control_handler(target_name=target_object_name, force_rebuild=False):
    removed = _remove_existing_hook_live_handlers()
    namespace = bpy.app.driver_namespace
    old_timer = namespace.get('procedural_hook_live_control_timer')
    timer_removed = False
    if old_timer is not None:
        try:
            if bpy.app.timers.is_registered(old_timer):
                bpy.app.timers.unregister(old_timer)
                timer_removed = True
        except Exception:
            pass

    @persistent
    def procedural_hook_live_control_handler(_scene, _depsgraph):
        if getattr(procedural_hook_live_control_handler, '_busy', False):
            return
        procedural_hook_live_control_handler._busy = True
        try:
            rebuild_hook_from_modifier(target_name, force=False)
        except Exception as exc:
            target_obj = bpy.data.objects.get(target_name)
            if target_obj is not None:
                target_obj['hook_live_control_error'] = str(exc)
        finally:
            procedural_hook_live_control_handler._busy = False

    def procedural_hook_live_control_timer():
        if getattr(procedural_hook_live_control_timer, '_busy', False):
            return 0.35
        procedural_hook_live_control_timer._busy = True
        try:
            rebuild_hook_from_modifier(target_name, force=False)
        except Exception as exc:
            target_obj = bpy.data.objects.get(target_name)
            if target_obj is not None:
                target_obj['hook_live_control_error'] = str(exc)
        finally:
            procedural_hook_live_control_timer._busy = False
        return 0.35 if bpy.data.objects.get(target_name) is not None else None

    bpy.app.handlers.depsgraph_update_post.append(procedural_hook_live_control_handler)
    namespace['procedural_hook_live_control_timer'] = procedural_hook_live_control_timer
    bpy.app.timers.register(procedural_hook_live_control_timer, first_interval=0.35, persistent=True)
    initial = rebuild_hook_from_modifier(target_name, force=force_rebuild)
    return {
        'installed': True,
        'removedExistingHandlers': removed,
        'timerRemoved': timer_removed,
        'timerRegistered': True,
        'initial': initial,
    }
"""


def _int(value: Any, fallback: int) -> int:
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return fallback


def _float(value: Any, fallback: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed == parsed else fallback


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return min(maximum, max(minimum, value))


def _choice(value: Any, fallback: str, allowed: set[str]) -> str:
    parsed = str(value) if value is not None else ""
    return parsed if parsed in allowed else fallback


def _normalize_repeat(value: Any) -> dict[str, int | str] | None:
    raw = value if isinstance(value, dict) else None
    if not raw:
        return None
    rows = int(_clamp(_int(raw.get("rows"), 0), 1, 400))
    columns = int(_clamp(_int(raw.get("columns"), 0), 1, 400))
    return {"mode": "tile", "rows": rows, "columns": columns}


def _matrix(value: Any, rows: int, columns: int, fallback, repeat: dict[str, Any] | None = None) -> list[list[int]]:
    source = value if isinstance(value, list) else []
    out: list[list[int]] = []
    for row in range(rows):
        source_row_index = row % int(repeat["rows"]) if repeat and repeat.get("mode") == "tile" else row
        source_row = source[source_row_index] if source_row_index < len(source) and isinstance(source[source_row_index], list) else []
        out_row: list[int] = []
        for col in range(columns):
            source_col_index = col % int(repeat["columns"]) if repeat and repeat.get("mode") == "tile" else col
            raw = source_row[source_col_index] if source_col_index < len(source_row) else None
            out_row.append(_int(raw, fallback(row, col)))
        out.append(out_row)
    return out


def _normalize_stitch_legend(value: Any) -> list[dict[str, Any]]:
    by_code = {int(entry["code"]): dict(entry) for entry in DEFAULT_HOOK_STITCH_LEGEND}
    for entry in value if isinstance(value, list) else []:
        if not isinstance(entry, dict):
            continue
        code = int(_clamp(_int(entry.get("code"), -1), 0, 999))
        fallback = by_code.get(code, {})
        by_code[code] = {
            "code": code,
            "symbol": str(entry.get("symbol") or fallback.get("symbol") or f"code-{code}"),
            "abbreviation": str(entry.get("abbreviation") or fallback.get("abbreviation") or ""),
            "label": str(entry.get("label") or fallback.get("label") or f"Reserved stitch {code}"),
            "archetype": _choice(entry.get("archetype"), str(fallback.get("archetype") or "reserved"), HOOK_STITCH_ARCHETYPES),
            "supported": bool(entry.get("supported")) or code in (0, 1),
            "fallbackCode": int(_clamp(_int(entry.get("fallbackCode"), _int(fallback.get("fallbackCode"), 1)), 0, 999)),
            "notes": str(entry.get("notes") or fallback.get("notes") or ""),
        }
    return [by_code[key] for key in sorted(by_code)]


def _normalize_gauge(value: Any) -> dict[str, Any] | None:
    raw = value if isinstance(value, dict) else None
    if not raw:
        return None
    gauge: dict[str, Any] = {"unit": _choice(raw.get("unit"), "bu", {"bu", "cm", "in"})}
    for key in ("stitchesPerUnit", "rowsPerUnit", "density", "openness", "loopHeight", "tension"):
        parsed = _float(raw.get(key), float("nan"))
        if parsed == parsed:
            gauge[key] = parsed
    return gauge


def _normalize_source(value: Any, title: Any, source_label: Any) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    return {
        "kind": _choice(raw.get("kind"), "builtin", HOOK_SOURCE_KINDS),
        "access": _choice(raw.get("access"), "builtin", HOOK_SOURCE_ACCESSES),
        "title": str(raw.get("title") or title or ""),
        "author": str(raw.get("author") or ""),
        "site": str(raw.get("site") or ""),
        "book": str(raw.get("book") or ""),
        "url": str(raw.get("url") or ""),
        "note": str(raw.get("note") or source_label or ""),
    }


def normalize_hook_render_settings(value: Any) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    fallback = DEFAULT_HOOK_RENDER_SETTINGS
    return {
        "hookScale": _clamp(_float(raw.get("hookScale"), fallback["hookScale"]), 0.001, 10.0),
        "legWidth": _clamp(_float(raw.get("legWidth"), fallback["legWidth"]), 0.05, 10.0),
        "loopHeight": _clamp(_float(raw.get("loopHeight"), fallback["loopHeight"]), 0.05, 20.0),
        "handleScale": _clamp(_float(raw.get("handleScale"), fallback["handleScale"]), 0.01, 10.0),
        "legZOffset": _clamp(_float(raw.get("legZOffset"), fallback["legZOffset"]), -10.0, 10.0),
        "tubeRadius": _clamp(_float(raw.get("tubeRadius"), fallback["tubeRadius"]), 0.001, 2.0),
        "curveResolution": int(_clamp(_int(raw.get("curveResolution"), fallback["curveResolution"]), 3, 96)),
        "tubeResolution": int(_clamp(_int(raw.get("tubeResolution"), fallback["tubeResolution"]), 3, 64)),
        "textureScaleU": _clamp(_float(raw.get("textureScaleU"), fallback["textureScaleU"]), 0.0001, 100.0),
        "textureScaleV": _clamp(_float(raw.get("textureScaleV"), fallback["textureScaleV"]), 0.0001, 100.0),
        "textureOffsetV": _clamp(_float(raw.get("textureOffsetV"), fallback["textureOffsetV"]), -100.0, 100.0),
        "textureSideFlatten": _clamp(_float(raw.get("textureSideFlatten"), fallback["textureSideFlatten"]), 0.0, 1.0),
        "arc1VPadding": _clamp(_float(raw.get("arc1VPadding"), fallback["arc1VPadding"]), 0.0, 0.5),
        "fillRatio": _clamp(_float(raw.get("fillRatio"), fallback["fillRatio"]), 0.1, 1.0),
        "seed": int(_clamp(_int(raw.get("seed"), fallback["seed"]), 0, 9999)),
    }


def normalize_hook_pattern(pattern: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(pattern, dict):
        raise ValueError("hook pattern must be an object.")
    rows = int(_clamp(_int(pattern.get("rows"), DEFAULT_HOOK_ROWS), 1, 200))
    columns = int(_clamp(_int(pattern.get("columns"), DEFAULT_HOOK_COLUMNS), 1, 200))
    repeat = _normalize_repeat(pattern.get("repeat"))
    stitch_codes = _matrix(pattern.get("stitchCodes"), rows, columns, lambda _r, _c: 1, repeat)
    stitch_codes = [[int(_clamp(code, 0, 999)) for code in row] for row in stitch_codes]
    chain_ids = _matrix(pattern.get("chainIds"), rows, columns, lambda _r, c: c, repeat)
    chain_ids = [[max(0, chain_id) for chain_id in row] for row in chain_ids]
    course_ids = _matrix(pattern.get("courseIds"), rows, columns, lambda r, _c: r, repeat)
    course_ids = [[max(0, course_id) for course_id in row] for row in course_ids]
    wale_ids = _matrix(pattern.get("waleIds"), rows, columns, lambda _r, c: c, repeat)
    wale_ids = [[max(0, wale_id) for wale_id in row] for row in wale_ids]

    chain_by_id: dict[int, dict[str, Any]] = {}
    for chain in pattern.get("chains") or []:
        if not isinstance(chain, dict):
            continue
        chain_id = max(0, _int(chain.get("id"), len(chain_by_id)))
        material_slot = int(_clamp(_int(chain.get("materialSlot"), 0), 0, MAX_HOOK_MATERIAL_SLOTS - 1))
        chain_by_id[chain_id] = {
            "id": chain_id,
            "materialSlot": material_slot,
            "direction": _choice(chain.get("direction"), "vertical", {"vertical", "horizontal", "course", "wale"}),
            "label": chain.get("label"),
        }
    for row in chain_ids:
        for chain_id in row:
            chain_by_id.setdefault(chain_id, {
                "id": chain_id,
                "materialSlot": 0,
                "direction": "vertical",
                "label": f"Chain {chain_id + 1}",
            })

    return {
        "version": 1,
        "structureType": "hook",
        "structureFamily": _choice(pattern.get("structureFamily"), "crochet_hook", HOOK_STRUCTURE_FAMILIES),
        "rowDirection": _choice(pattern.get("rowDirection"), "alternating", HOOK_ROW_DIRECTIONS),
        "rows": rows,
        "columns": columns,
        "repeat": repeat,
        "stitchCodes": stitch_codes,
        "chainIds": chain_ids,
        "courseIds": course_ids,
        "waleIds": wale_ids,
        "chains": [chain_by_id[key] for key in sorted(chain_by_id)],
        "stitchLegend": _normalize_stitch_legend(pattern.get("stitchLegend")),
        "gauge": _normalize_gauge(pattern.get("gauge")),
        "source": _normalize_source(pattern.get("source"), pattern.get("title"), pattern.get("sourceLabel")),
        "title": str(pattern.get("title") or "Hook Pattern"),
        "sourceLabel": str(pattern.get("sourceLabel") or "Hook preset"),
        "renderSettings": normalize_hook_render_settings(pattern.get("renderSettings")),
    }


def compute_hook_face_attributes(pattern: dict[str, Any]) -> dict[str, list[int]]:
    normalized = normalize_hook_pattern(pattern)
    material_by_chain = {
        int(chain["id"]): int(chain["materialSlot"])
        for chain in normalized["chains"]
    }
    active_by_chain: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for row, stitch_row in enumerate(normalized["stitchCodes"]):
        for col, stitch_code in enumerate(stitch_row):
            if stitch_code != 0:
                active_by_chain[normalized["chainIds"][row][col]].append((row, col))

    u_index_lookup: dict[tuple[int, int], int] = {}
    for _chain_id, cells in active_by_chain.items():
        for index, cell in enumerate(sorted(cells)):
            u_index_lookup[cell] = index

    stitch_codes: list[int] = []
    chain_ids: list[int] = []
    chain_u_indices: list[int] = []
    chain_material_ids: list[int] = []
    course_ids: list[int] = []
    wale_ids: list[int] = []
    for row in range(normalized["rows"]):
        for col in range(normalized["columns"]):
            stitch_code = normalized["stitchCodes"][row][col]
            chain_id = normalized["chainIds"][row][col] if stitch_code != 0 else -1
            stitch_codes.append(stitch_code)
            chain_ids.append(chain_id)
            chain_u_indices.append(u_index_lookup.get((row, col), -1))
            chain_material_ids.append(material_by_chain.get(chain_id, -1) if chain_id >= 0 else -1)
            course_ids.append(int(normalized["courseIds"][row][col]) if stitch_code != 0 else -1)
            wale_ids.append(int(normalized["waleIds"][row][col]) if stitch_code != 0 else -1)

    return {
        "stitch_code": stitch_codes,
        "chain_id": chain_ids,
        "chain_u_index": chain_u_indices,
        "chain_material_id": chain_material_ids,
        "course_id": course_ids,
        "wale_id": wale_ids,
    }


def used_material_slots(pattern: dict[str, Any]) -> list[int]:
    normalized = normalize_hook_pattern(pattern)
    used_chain_ids = {
        normalized["chainIds"][row][col]
        for row in range(normalized["rows"])
        for col in range(normalized["columns"])
        if normalized["stitchCodes"][row][col] != 0
    }
    return sorted({
        int(chain["materialSlot"])
        for chain in normalized["chains"]
        if int(chain["id"]) in used_chain_ids
    })


def build_hook_build_spec(pattern: dict[str, Any]) -> dict[str, Any]:
    """Resolve frontend chart intent into the Blender build contract."""
    normalized = normalize_hook_pattern(pattern)
    attributes = compute_hook_face_attributes(normalized)
    stitch_counts: dict[int, int] = defaultdict(int)
    chain_active_counts: dict[int, int] = defaultdict(int)
    for row in range(normalized["rows"]):
        for col in range(normalized["columns"]):
            stitch_code = int(normalized["stitchCodes"][row][col])
            stitch_counts[stitch_code] += 1
            if stitch_code != 0:
                chain_active_counts[int(normalized["chainIds"][row][col])] += 1

    legend_by_code = {
        int(entry["code"]): entry
        for entry in normalized["stitchLegend"]
        if isinstance(entry, dict) and "code" in entry
    }
    unsupported_codes = sorted(
        code
        for code, count in stitch_counts.items()
        if count > 0 and code != 0 and not bool(legend_by_code.get(code, {}).get("supported"))
    )
    fallback_codes = {
        str(code): int(legend_by_code.get(code, {}).get("fallbackCode") or 1)
        for code in unsupported_codes
    }
    active_cells = sum(count for code, count in stitch_counts.items() if code != 0)
    total_cells = normalized["rows"] * normalized["columns"]
    chains = []
    for chain in normalized["chains"]:
        chain_id = int(chain["id"])
        active_count = int(chain_active_counts.get(chain_id, 0))
        if active_count <= 0:
            continue
        chains.append({
            "id": chain_id,
            "materialSlot": int(chain["materialSlot"]),
            "direction": str(chain.get("direction") or "vertical"),
            "activeCells": active_count,
            "uIndexRange": [0, max(0, active_count - 1)],
        })

    return {
        "version": 1,
        "buildMode": "gn_reference_bridge_v1",
        "interpreter": "hook_pattern_document_to_reference_gn",
        "productionObject": "ProceduralHook",
        "draftObject": "HookDraft_Live",
        "visualReference": {
            "role": "calibration_reference_only",
            "name": "Pre-V2 Procedural Hook",
            "expectedObjectName": "HookVisualReference_PreV2",
            "baselineSettings": dict(DEFAULT_HOOK_RENDER_SETTINGS),
        },
        "frontendIntent": {
            "structureType": normalized["structureType"],
            "structureFamily": normalized["structureFamily"],
            "rowDirection": normalized["rowDirection"],
            "repeat": normalized["repeat"],
            "title": normalized["title"],
            "source": normalized["source"],
            "gauge": normalized["gauge"],
        },
        "grid": {
            "rows": normalized["rows"],
            "columns": normalized["columns"],
            "totalCells": total_cells,
            "activeCells": active_cells,
            "emptyCells": total_cells - active_cells,
            "visibleRows": normalized["rows"],
            "visibleColumns": normalized["columns"],
        },
        "stitches": {
            "counts": {str(code): int(stitch_counts[code]) for code in sorted(stitch_counts)},
            "supportedCodes": sorted(
                code
                for code, count in stitch_counts.items()
                if count > 0 and bool(legend_by_code.get(code, {}).get("supported"))
            ),
            "unsupportedCodes": unsupported_codes,
            "fallbackCodes": fallback_codes,
            "v1RenderedCodes": sorted(code for code, count in stitch_counts.items() if count > 0 and code != 0),
            "v1GeometryArchetype": "standard_interlocking_hook_loop",
        },
        "continuity": {
            "chainModel": "per_chain_active_cell_order",
            "uIndexAttribute": "chain_u_index",
            "chainIdAttribute": "chain_id",
            "courseIdAttribute": "course_id",
            "waleIdAttribute": "wale_id",
            "sparseCellsDoNotResetU": True,
            "chains": chains,
        },
        "materials": {
            "slotBase": 0,
            "maxSlots": MAX_HOOK_MATERIAL_SLOTS,
            "usedSlots": used_material_slots(normalized),
            "attribute": "chain_material_id",
            "generatedMaterialIdAttribute": "material_id",
        },
        "renderSettings": normalized["renderSettings"],
        "attributes": {
            "faceAttributeCount": len(attributes["stitch_code"]),
            "names": sorted(attributes.keys()),
        },
    }


def build_hook_sync_code(
    pattern: dict[str, Any],
    *,
    target_object_name: str = "ProceduralHook",
    draft_object_name: str = "HookDraft_Live",
    draft_collection_name: str = "Fabric Drafts",
    fit_target_name: str = "Space",
) -> str:
    normalized = normalize_hook_pattern(pattern)
    attributes = compute_hook_face_attributes(normalized)
    build_spec = build_hook_build_spec(normalized)
    pattern_json = json.dumps(normalized)
    attributes_json = json.dumps(attributes)
    build_spec_json = json.dumps(build_spec)
    return f"""
import bpy
import json

pattern = json.loads({pattern_json!r})
attributes = json.loads({attributes_json!r})
build_spec = json.loads({build_spec_json!r})
target_object_name = {json.dumps(target_object_name)}
draft_object_name = {json.dumps(draft_object_name)}
draft_collection_name = {json.dumps(draft_collection_name)}
fit_target_name = {json.dumps(fit_target_name)}

def ensure_collection(name):
    collection = bpy.data.collections.get(name)
    if collection is None:
        collection = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(collection)
    return collection

def ensure_socket(group, name):
    interface = getattr(group, 'interface', None)
    if interface is None:
        raise KeyError(name)
    for item in interface.items_tree:
        if getattr(item, 'item_type', None) == 'SOCKET' and getattr(item, 'in_out', None) == 'INPUT' and item.name == name:
            return item
    raise KeyError(name)

def maybe_set_modifier_input(modifier, node_group, name, value):
    try:
        socket = ensure_socket(node_group, name)
    except KeyError:
        return False
    try:
        modifier[socket.identifier] = value
        return True
    except Exception:
        return False

def find_hook_material_adapter(target_obj):
    for name in ('Hook Material UV', 'Hook Material UV Adapter'):
        modifier = target_obj.modifiers.get(name)
        if modifier is not None and modifier.type == 'NODES' and modifier.node_group is not None:
            return modifier
    return None

def repair_hook_modifier_output(node_group):
    output_node = next((node for node in node_group.nodes if node.bl_idname == 'NodeGroupOutput'), None)
    if output_node is None or 'Geometry' not in output_node.inputs:
        return {{'ok': False, 'source': None, 'reason': 'missing output geometry socket'}}

    source_node = None
    for name in ('Inputs', 'Group Input'):
        candidate = node_group.nodes.get(name)
        if candidate is not None and 'Geometry' in candidate.outputs:
            source_node = candidate
            break
    if source_node is None:
        return {{'ok': False, 'source': None, 'reason': 'missing generated geometry input node'}}

    for link in list(output_node.inputs['Geometry'].links):
        node_group.links.remove(link)
    node_group.links.new(source_node.outputs['Geometry'], output_node.inputs['Geometry'])
    return {{'ok': True, 'source': source_node.name, 'reason': None}}

def remove_hook_socket_drivers(target_obj, modifier):
    removed = []
    animation_data = getattr(target_obj, 'animation_data', None)
    if animation_data is None or not animation_data.drivers:
        return removed
    prefix = 'modifiers["' + modifier.name + '"]["Socket_'
    for fcurve in list(animation_data.drivers):
        if fcurve.data_path.startswith(prefix):
            removed.append({{
                'data_path': fcurve.data_path,
                'array_index': fcurve.array_index,
                'expression': getattr(getattr(fcurve, 'driver', None), 'expression', ''),
            }})
            try:
                animation_data.drivers.remove(fcurve)
            except Exception:
                pass
    return removed

def create_hook_draft_object():
    rows = int(pattern['rows'])
    columns = int(pattern['columns'])
    vertices = []
    for row in range(rows + 1):
        for col in range(columns + 1):
            vertices.append((float(col), float(-row), 0.0))
    faces = []
    for row in range(rows):
        for col in range(columns):
            base = row * (columns + 1) + col
            faces.append((base, base + 1, base + columns + 2, base + columns + 1))
    mesh = bpy.data.meshes.new(draft_object_name + 'Mesh')
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    for attr_name, values in attributes.items():
        attr = mesh.attributes.new(attr_name, 'INT', 'FACE')
        for index, value in enumerate(values):
            attr.data[index].value = int(value)
    existing = bpy.data.objects.get(draft_object_name)
    if existing is not None:
        old_mesh = existing.data
        existing.data = mesh
        if old_mesh is not None and old_mesh.users == 0:
            bpy.data.meshes.remove(old_mesh)
        obj = existing
    else:
        obj = bpy.data.objects.new(draft_object_name, mesh)
        collection = ensure_collection(draft_collection_name)
        collection.objects.link(obj)
    obj.hide_render = True
    obj.hide_viewport = True
    obj['hook_rows'] = rows
    obj['hook_columns'] = columns
    obj['hook_title'] = pattern.get('title', '')
    obj['hook_source_label'] = pattern.get('sourceLabel', '')
    return obj

def evaluated_hook_geometry_summary(target_obj, construction):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = target_obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    try:
        return {{
            'vertices': len(mesh.vertices),
            'faces': len(mesh.polygons),
            'components': int(target_obj.get('hook_generated_components', 0)),
            'construction': construction,
        }}
    finally:
        evaluated.to_mesh_clear()

{HOOK_GEOMETRY_PY}
{HOOK_LIVE_CONTROL_PY}

hook_draft = create_hook_draft_object()
target_obj = bpy.data.objects.get(target_object_name)
if target_obj is None:
    raise RuntimeError('Hook target object not found: ' + target_object_name)
hook_mod = target_obj.modifiers.get('Hook')
if hook_mod is None or hook_mod.type != 'NODES' or hook_mod.node_group is None:
    raise RuntimeError('Hook modifier not found on ' + target_object_name)
hook_group = hook_mod.node_group
output_repair = {{'ok': True, 'source': 'reference_gn_output', 'reason': None}}
removed_drivers = remove_hook_socket_drivers(target_obj, hook_mod)
settings = pattern.get('renderSettings') or {{}}

socket_results = {{}}
def set_socket(name, value):
    socket_results[name] = maybe_set_modifier_input(hook_mod, hook_group, name, value)

set_socket('Draft Object', hook_draft)
set_socket('Draft Rows', int(pattern['rows']))
set_socket('Draft Columns', int(pattern['columns']))
set_socket('Row', int(pattern['rows']))
set_socket('Columns', int(pattern['columns']))
set_socket('Pattern Scale', float(settings.get('hookScale', 0.07)))
set_socket('Leg Width', float(settings.get('legWidth', 0.71)))
set_socket('Loop Height', float(settings.get('loopHeight', 2.08)))
set_socket('Handle Scale', float(settings.get('handleScale', 0.6)))
set_socket('Leg Z Offset', float(settings.get('legZOffset', 0.218)))
set_socket('Half Tube Radius', float(settings.get('tubeRadius', 0.25)))
set_socket('Curve Resolution', int(settings.get('curveResolution', 7)))
set_socket('Tube Resolution', int(settings.get('tubeResolution', 11)))
set_socket('Texture Scale U', float(settings.get('textureScaleU', 1.06)))
set_socket('Texture Scale V', float(settings.get('textureScaleV', 0.93)))
set_socket('Texture Offset V', float(settings.get('textureOffsetV', -0.44)))
set_socket('Texture Side Flatten', float(settings.get('textureSideFlatten', 0.0)))
set_socket('Arc 1 V Padding', float(settings.get('arc1VPadding', 0.0)))
set_socket('Seed', int(settings.get('seed', 1)))

material_adapter_results = {{}}
material_adapter_mod = find_hook_material_adapter(target_obj)
if material_adapter_mod is not None:
    material_adapter_group = material_adapter_mod.node_group
    for socket_name, value in (
        ('Draft Object', hook_draft),
        ('Draft Rows', int(pattern['rows'])),
        ('Draft Columns', int(pattern['columns'])),
        ('Columns', int(pattern['columns'])),
    ):
        material_adapter_results[socket_name] = maybe_set_modifier_input(
            material_adapter_mod,
            material_adapter_group,
            socket_name,
            value,
        )

fit_mod = target_obj.modifiers.get('Fit To Space') or target_obj.modifiers.get('Swatch Fit')
if fit_mod and fit_mod.type == 'NODES' and fit_mod.node_group:
    fit_group = fit_mod.node_group
    fit_target = bpy.data.objects.get(fit_target_name)
    if fit_target is not None:
        maybe_set_modifier_input(fit_mod, fit_group, 'Target Plane', fit_target)
    maybe_set_modifier_input(fit_mod, fit_group, 'Fill Ratio', float(settings.get('fillRatio', 1.0)))

target_obj['hook_pattern_title'] = pattern.get('title', '')
target_obj['hook_source_label'] = pattern.get('sourceLabel', '')
target_obj['hook_contract_version'] = 1
target_obj['hook_build_mode'] = build_spec.get('buildMode', '')
target_obj['hook_interpreter'] = build_spec.get('interpreter', '')
target_obj['hook_visual_mode'] = 'gn_reference_rows_columns_material_uv_v1'
target_obj['hook_visual_reference_role'] = 'pre_v2_calibration_reference_only'
target_obj['_hook_source_pattern_json'] = json.dumps(pattern)
target_obj['_hook_live_pattern_json'] = json.dumps(pattern)
target_obj['_hook_build_spec_json'] = json.dumps(build_spec)

modifier_display = show_reference_hook_modifier(hook_mod)
live_control_summary = disable_hook_live_control_handler()
bpy.context.view_layer.update()
geometry_summary = evaluated_hook_geometry_summary(target_obj, 'gn_reference_rows_columns_material')
print(json.dumps({{
    'status': 'ok',
    'target': target_object_name,
    'draftObject': draft_object_name,
    'buildSpec': build_spec,
    'rows': pattern['rows'],
    'columns': pattern['columns'],
    'activeCells': sum(1 for value in attributes['stitch_code'] if value != 0),
    'materialSlots': sorted(set(value for value in attributes['chain_material_id'] if value >= 0)),
    'stitchCounts': {{str(code): attributes['stitch_code'].count(code) for code in sorted(set(attributes['stitch_code']))}},
    'geometry': geometry_summary,
    'modifierDisplay': modifier_display,
    'modifierOutput': output_repair,
    'removedDrivers': removed_drivers,
    'sockets': socket_results,
    'materialAdapter': {{
        'name': material_adapter_mod.name if material_adapter_mod is not None else None,
        'sockets': material_adapter_results,
    }},
    'liveControls': live_control_summary,
}}))
"""


def sync_hook_to_blender(
    pattern: dict[str, Any],
    *,
    target_object_name: str = "ProceduralHook",
    draft_object_name: str = "HookDraft_Live",
) -> dict[str, Any]:
    code = build_hook_sync_code(
        pattern,
        target_object_name=target_object_name,
        draft_object_name=draft_object_name,
    )
    return send_blender_command("execute_code", {"code": code})
