"""Build the clean diagnostic geometry-node rebuild.

Run through Blender/Python. The script saves the current file as a separate
`Codex_ParametricWeave.flat-arc1-rebuild.blend`, renames the previous
`Parametric Weave knotty` group for rollback, and creates a new node group with
the same public socket contract.

The generated group keeps the deliberately inspectable rebuild layout, while
restoring the original Arc1 core surface plus Arc2/sub-strand halo profile.
Arc2 U stays deterministic in the same yarn stream as Arc1; do not rebuild the
old nearest-surface Arc2 U sampler, which caused small endpoint shrink.
"""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

import bpy


NODE_GROUP_NAME = "Parametric Weave knotty"
TARGET_OBJECT_NAME = "ParametricWeave"
WEAVE_MODIFIER_NAME = "Weave"
REBUILD_SUFFIX = "flat-arc1-rebuild"


FRAME_SPECS = {
    "Inputs": {"label": "Inputs", "location": (-5200, 900), "color": (0.22, 0.27, 0.33)},
    "Draft Sampling": {"label": "Draft Sampling", "location": (-4100, 900), "color": (0.17, 0.33, 0.34)},
    "Warp Curves": {"label": "Warp Curves", "location": (-2750, 1150), "color": (0.25, 0.32, 0.21)},
    "Weft Curves": {"label": "Weft Curves", "location": (-2750, -250), "color": (0.25, 0.28, 0.38)},
    "Flat Arc1 Profile": {"label": "Arc1 + Arc2 Profile", "location": (-1250, 900), "color": (0.32, 0.25, 0.18)},
    "Texture U": {"label": "Texture U", "location": (250, 1150), "color": (0.18, 0.26, 0.36)},
    "Texture V": {"label": "Texture V", "location": (250, -250), "color": (0.20, 0.24, 0.34)},
    "Material Selection": {"label": "Material Selection", "location": (1750, 900), "color": (0.30, 0.22, 0.32)},
    "Resolution Diagnostics": {"label": "Resolution Diagnostics", "location": (3200, 900), "color": (0.34, 0.25, 0.17)},
    "Debug Attributes": {"label": "Debug Attributes", "location": (4550, 900), "color": (0.23, 0.30, 0.23)},
    "Output": {"label": "Output", "location": (5900, 900), "color": (0.28, 0.28, 0.28)},
}


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def rebuild_filepath(current: Path) -> Path:
    if current.stem.endswith(REBUILD_SUFFIX):
        return current
    return current.with_name(f"{current.stem}.{REBUILD_SUFFIX}{current.suffix}")


def save_working_copy() -> Path:
    current = Path(bpy.data.filepath)
    if not current:
        raise RuntimeError("The active Blender file has no filepath.")
    target = rebuild_filepath(current)
    if target.exists():
        backup = target.with_name(f"{target.stem}.pre-{timestamp()}{target.suffix}")
        shutil.copy2(target, backup)
        print(f"[flat-arc1] Existing rebuild copy backed up: {backup}")
    bpy.ops.wm.save_as_mainfile(filepath=str(target))
    print(f"[flat-arc1] Working copy active: {target}")
    return target


def get_socket(sockets, name: str):
    socket = sockets.get(name)
    if socket is None:
        raise KeyError(name)
    return socket


def link(group, from_socket, to_socket):
    group.links.new(from_socket, to_socket)


def clear_group(group):
    group.nodes.clear()
    group.interface.clear()


def create_group_input(group, name, frame=None, location=(0, 0)):
    node = group.nodes.new("NodeGroupInput")
    node.name = name
    node.label = name
    node.parent = frame
    node.location = location
    return node


def create_node(group, name, bl_idname, frame=None, location=(0, 0), label=None):
    node = group.nodes.new(bl_idname)
    node.name = name
    node.label = label if label is not None else name
    node.parent = frame
    node.location = location
    return node


def create_math(group, name, operation, frame=None, location=(0, 0), defaults=None):
    node = create_node(group, name, "ShaderNodeMath", frame, location)
    node.operation = operation
    if defaults:
        for index, value in defaults.items():
            node.inputs[index].default_value = value
    return node


def create_value(group, name, value, frame=None, location=(0, 0)):
    node = create_node(group, name, "ShaderNodeValue", frame, location)
    node.outputs["Value"].default_value = value
    return node


def create_int_math(group, name, operation, frame=None, location=(0, 0), defaults=None):
    node = create_node(group, name, "FunctionNodeIntegerMath", frame, location)
    node.operation = operation
    if defaults:
        for index, value in defaults.items():
            node.inputs[index].default_value = int(value)
    return node


def create_compare_int(group, name, frame=None, location=(0, 0), equals_value=1):
    node = create_node(group, name, "FunctionNodeCompare", frame, location)
    node.data_type = "INT"
    node.operation = "EQUAL"
    node.inputs[3].default_value = int(equals_value)
    return node


def create_combine(group, name, frame=None, location=(0, 0), defaults=None):
    node = create_node(group, name, "ShaderNodeCombineXYZ", frame, location)
    if defaults:
        for index, value in defaults.items():
            node.inputs[index].default_value = value
    return node


def create_named_attr(group, name, attr_name, data_type, frame=None, location=(0, 0)):
    node = create_node(group, name, "GeometryNodeInputNamedAttribute", frame, location)
    node.data_type = data_type
    node.inputs["Name"].default_value = attr_name
    return node


def create_store_attr(group, name, attr_name, data_type, domain, frame=None, location=(0, 0)):
    node = create_node(group, name, "GeometryNodeStoreNamedAttribute", frame, location)
    node.data_type = data_type
    node.domain = domain
    node.inputs["Name"].default_value = attr_name
    return node


def add_socket(group, name, socket_type, *, parent=None, default=None, in_out="INPUT"):
    socket = group.interface.new_socket(name, in_out=in_out, socket_type=socket_type, parent=parent)
    if default is not None and hasattr(socket, "default_value"):
        try:
            socket.default_value = default
        except Exception:
            pass
    return socket


def build_interface(group):
    add_socket(group, "Geometry", "NodeSocketGeometry", in_out="OUTPUT")
    add_socket(group, "Geometry", "NodeSocketGeometry")
    add_socket(group, "Scanner Pixels Per BU", "NodeSocketFloat", default=62992.16)
    add_socket(group, "Texture Scale U", "NodeSocketFloat", default=1.0)
    add_socket(group, "Draft Object", "NodeSocketObject")
    add_socket(group, "Draft Columns", "NodeSocketInt", default=8)
    add_socket(group, "Draft Rows", "NodeSocketInt", default=8)
    add_socket(group, "Arc 1 V Padding", "NodeSocketFloat", default=0.008)
    add_socket(group, "Arc 2 Endpoint Pinch", "NodeSocketFloat", default=0.0)
    add_socket(group, "Arc 2 Apex Pinch", "NodeSocketFloat", default=0.0)
    add_socket(group, "Arc 2 Apex Min Radius", "NodeSocketFloat", default=0.0)
    add_socket(group, "Arc 2 Bend Smoothing", "NodeSocketFloat", default=0.0)

    pattern = group.interface.new_panel("Pattern")
    add_socket(group, "Warp Threads", "NodeSocketInt", parent=pattern, default=80)
    add_socket(group, "Weft Threads", "NodeSocketInt", parent=pattern, default=80)
    add_socket(group, "Spacing", "NodeSocketFloat", parent=pattern, default=0.026)
    add_socket(group, "Amplitude", "NodeSocketFloat", parent=pattern, default=0.008)

    surface = group.interface.new_panel("Surface")
    add_socket(group, "Thread Subdivisions", "NodeSocketFloat", parent=surface, default=8.0)
    add_socket(group, "Arc 2 Boundary Inset", "NodeSocketFloat", parent=surface, default=0.0)
    add_socket(group, "Arc 2 Match Arc 1 V Rate", "NodeSocketBool", parent=surface, default=False)

    texture = group.interface.new_panel("Texture")
    add_socket(group, "Texture Scale V", "NodeSocketFloat", parent=texture, default=1.0)
    add_socket(group, "Texture Offset V", "NodeSocketFloat", parent=texture, default=0.0)

    general = group.interface.new_panel("General")
    add_socket(group, "Seed", "NodeSocketInt", parent=general, default=0)

    imperfections = group.interface.new_panel("Imperfections")
    add_socket(group, "Wobble Amount", "NodeSocketFloat", parent=imperfections, default=0.0)
    add_socket(group, "Wobble Scale", "NodeSocketFloat", parent=imperfections, default=13.52)
    add_socket(group, "Pattern Noise X", "NodeSocketFloat", parent=imperfections, default=0.0)
    add_socket(group, "Pattern Noise Y", "NodeSocketFloat", parent=imperfections, default=0.0)
    add_socket(group, "UV Random U", "NodeSocketFloat", parent=imperfections, default=0.0)
    add_socket(group, "UV Random V", "NodeSocketFloat", parent=imperfections, default=0.0)
    add_socket(group, "U Stride Per Warp End", "NodeSocketFloat", parent=imperfections, default=0.0)
    add_socket(group, "U Stride Per Weft Pick", "NodeSocketFloat", parent=imperfections, default=0.0)

    loose = group.interface.new_panel("Loose Strands")
    add_socket(group, "Loose Strand Density", "NodeSocketFloat", parent=loose, default=0.0)
    add_socket(group, "Loose Strand Length", "NodeSocketFloat", parent=loose, default=0.02)
    add_socket(group, "Loose Strand Thickness", "NodeSocketFloat", parent=loose, default=0.0001)
    add_socket(group, "Loose Strand Frizz", "NodeSocketFloat", parent=loose, default=0.005)

    material_slots = group.interface.new_panel("Material Slots")
    for index in range(1, 17):
        add_socket(group, f"Material {index}", "NodeSocketMaterial", parent=material_slots)

    sub_strand = group.interface.new_panel("Sub Strand")
    add_socket(group, "Sub Strand Enable", "NodeSocketBool", parent=sub_strand, default=True)
    add_socket(group, "Sub Texture Scale V", "NodeSocketFloat", parent=sub_strand, default=1.0)
    add_socket(group, "Sub Texture Offset V", "NodeSocketFloat", parent=sub_strand, default=0.0)

    v_band = group.interface.new_panel("V-Band Mapping", default_closed=True)
    for index in range(1, 17):
        add_socket(group, f"Material {index} Image Width Px", "NodeSocketFloat", parent=v_band, default=1.0)
        add_socket(group, f"Material {index} Texture Scale U", "NodeSocketFloat", parent=v_band, default=1.0)
        add_socket(group, f"Material {index} Arc 1 V Min", "NodeSocketFloat", parent=v_band, default=0.0)
        add_socket(group, f"Material {index} Arc 1 V Max", "NodeSocketFloat", parent=v_band, default=1.0)
        add_socket(group, f"Material {index} Arc 2 V Min", "NodeSocketFloat", parent=v_band, default=0.0)
        add_socket(group, f"Material {index} Arc 2 V Max", "NodeSocketFloat", parent=v_band, default=1.0)


def create_frames(group):
    frames = {}
    for key, spec in FRAME_SPECS.items():
        frame = group.nodes.new("NodeFrame")
        frame.name = f"PW FlatArc1 - {key}"
        frame.label = spec["label"]
        frame.location = spec["location"]
        frame.use_custom_color = True
        frame.color = spec["color"]
        frames[key] = frame
    return frames


def create_material_selector(group, frames, material_id_socket, input_node, socket_suffix, y_offset):
    frame = frames["Material Selection"]
    previous_socket = get_socket(input_node.outputs, f"Material 1 {socket_suffix}")
    previous_node = None
    for index in range(2, 17):
        compare = create_compare_int(
            group,
            f"PW FlatArc1 Select {socket_suffix} Is {index}",
            frame,
            (40 + (index - 2) * 150, y_offset),
            index,
        )
        switch = create_node(
            group,
            f"PW FlatArc1 Select {socket_suffix} {index}",
            "GeometryNodeSwitch",
            frame,
            (40 + (index - 2) * 150, y_offset - 170),
        )
        switch.input_type = "FLOAT"
        link(group, material_id_socket, compare.inputs[2])
        link(group, compare.outputs["Result"], switch.inputs["Switch"])
        link(group, previous_socket, switch.inputs["False"])
        link(group, get_socket(input_node.outputs, f"Material {index} {socket_suffix}"), switch.inputs["True"])
        previous_socket = switch.outputs["Output"]
        previous_node = switch
    return previous_socket, previous_node


def create_material_applier(group, frames, geometry_socket, material_id_socket, input_node):
    frame = frames["Material Selection"]
    base = create_node(
        group,
        "PW FlatArc1 Apply Material 1",
        "GeometryNodeSetMaterial",
        frame,
        (2300, -180),
    )
    link(group, geometry_socket, base.inputs["Geometry"])
    link(group, get_socket(input_node.outputs, "Material 1"), base.inputs["Material"])
    previous_geometry = base.outputs["Geometry"]

    for index in range(2, 17):
        compare = create_compare_int(
            group,
            f"PW FlatArc1 Material Is {index}",
            frame,
            (2300 + (index - 2) * 180, -430),
            index,
        )
        set_material = create_node(
            group,
            f"PW FlatArc1 Apply Material {index}",
            "GeometryNodeSetMaterial",
            frame,
            (2480 + (index - 2) * 180, -180),
        )
        link(group, material_id_socket, compare.inputs[2])
        link(group, previous_geometry, set_material.inputs["Geometry"])
        link(group, compare.outputs["Result"], set_material.inputs["Selection"])
        link(group, get_socket(input_node.outputs, f"Material {index}"), set_material.inputs["Material"])
        previous_geometry = set_material.outputs["Geometry"]

    return previous_geometry


def build_draft_sampling(group, frames, draft_input, curve_node_name, curve_index_source, index_in_curve_source, thread_subdivision_socket, draft_span_socket, draft_across_socket, *, is_warp: bool):
    frame = frames["Draft Sampling"]
    prefix = "Warp" if is_warp else "Weft"
    sample_axis = "Row" if is_warp else "Col"
    across_axis = "Col" if is_warp else "Row"

    # The frontend zoom sockets (`Warp Threads` / `Weft Threads`) are display
    # strand counts. The draft itself is a repeat. Sample the drawdown by
    # logical thread index, not by raw profile-subdivision point index.
    thread_div = create_math(
        group,
        f"PW FlatArc1 {prefix} Logical Thread Divide",
        "DIVIDE",
        frame,
        (80, 160 if is_warp else -560),
    )
    thread_floor = create_math(
        group,
        f"PW FlatArc1 {prefix} Logical Thread Floor",
        "FLOOR",
        frame,
        (280, 160 if is_warp else -560),
    )
    # Keep the row/col "Mod" node names as the visible contract, but feed them
    # from logical thread index. backend sync skips relinking for this marked
    # Flat Arc1 group so this input is not overwritten.
    along_mod = create_math(
        group,
        f"PW Draft {prefix} {sample_axis} Mod",
        "MODULO",
        frame,
        (480, 160 if is_warp else -560),
    )
    across_mod = create_math(
        group,
        f"PW Draft {prefix} {across_axis} Mod",
        "MODULO",
        frame,
        (80, -40 if is_warp else -760),
    )
    row_offset = create_math(
        group,
        f"PW Draft {prefix} Row Offset",
        "MULTIPLY",
        frame,
        (700, 60 if is_warp else -660),
    )
    face_index = create_math(
        group,
        f"PW Draft {prefix} Face Index",
        "ADD",
        frame,
        (900, 60 if is_warp else -660),
    )

    link(group, index_in_curve_source, thread_div.inputs[0])
    link(group, thread_subdivision_socket, thread_div.inputs[1])
    link(group, thread_div.outputs["Value"], thread_floor.inputs[0])
    link(group, thread_floor.outputs["Value"], along_mod.inputs[0])
    link(group, draft_span_socket, along_mod.inputs[1])

    link(group, curve_index_source, across_mod.inputs[0])
    link(group, draft_across_socket, across_mod.inputs[1])

    if is_warp:
        link(group, along_mod.outputs["Value"], row_offset.inputs[0])
        link(group, get_socket(draft_input.outputs, "Draft Columns"), row_offset.inputs[1])
        link(group, row_offset.outputs["Value"], face_index.inputs[0])
        link(group, across_mod.outputs["Value"], face_index.inputs[1])
    else:
        link(group, across_mod.outputs["Value"], row_offset.inputs[0])
        link(group, get_socket(draft_input.outputs, "Draft Columns"), row_offset.inputs[1])
        link(group, row_offset.outputs["Value"], face_index.inputs[0])
        link(group, along_mod.outputs["Value"], face_index.inputs[1])

    return face_index


def create_curve_branch(group, frames, inputs, *, is_warp: bool):
    curve_frame = frames["Warp Curves"] if is_warp else frames["Weft Curves"]
    prefix = "Warp" if is_warp else "Weft"
    base_count_name = "Warp Threads" if is_warp else "Weft Threads"
    length_count_name = "Weft Threads" if is_warp else "Warp Threads"
    stride_name = "U Stride Per Warp End" if is_warp else "U Stride Per Weft Pick"

    strand_count = get_socket(inputs.outputs, base_count_name)
    length_threads = get_socket(inputs.outputs, length_count_name)
    spacing = get_socket(inputs.outputs, "Spacing")
    subdivs = get_socket(inputs.outputs, "Thread Subdivisions")

    sample_point_count = create_math(
        group,
        f"PW FlatArc1 {prefix} Sample Point Count",
        "MULTIPLY",
        curve_frame,
        (-690, 310),
    )
    link(group, length_threads, sample_point_count.inputs[0])
    link(group, subdivs, sample_point_count.inputs[1])

    sample_spacing = create_math(
        group,
        f"PW FlatArc1 {prefix} Sample Spacing",
        "DIVIDE",
        curve_frame,
        (-690, 90),
    )
    link(group, spacing, sample_spacing.inputs[0])
    link(group, subdivs, sample_spacing.inputs[1])

    points_offset = create_combine(group, f"PW FlatArc1 {prefix} Points Offset", curve_frame, (-470, 470))
    instance_offset = create_combine(group, f"PW FlatArc1 {prefix} Instance Offset", curve_frame, (-470, 160))
    if is_warp:
        link(group, spacing, points_offset.inputs["X"])
        link(group, sample_spacing.outputs["Value"], instance_offset.inputs["Y"])
    else:
        link(group, spacing, points_offset.inputs["Y"])
        link(group, sample_spacing.outputs["Value"], instance_offset.inputs["X"])

    points_line = create_node(group, f"PW FlatArc1 {prefix} Strand Points", "GeometryNodeMeshLine", curve_frame, (-250, 470))
    points_line.mode = "OFFSET"
    link(group, strand_count, points_line.inputs["Count"])
    link(group, points_offset.outputs["Vector"], points_line.inputs["Offset"])

    instance_line = create_node(group, f"PW FlatArc1 {prefix} Path Instance", "GeometryNodeMeshLine", curve_frame, (-250, 160))
    instance_line.mode = "OFFSET"
    link(group, sample_point_count.outputs["Value"], instance_line.inputs["Count"])
    link(group, instance_offset.outputs["Vector"], instance_line.inputs["Offset"])

    instance = create_node(group, f"PW FlatArc1 {prefix} Instance Paths", "GeometryNodeInstanceOnPoints", curve_frame, (-10, 360))
    link(group, points_line.outputs["Mesh"], instance.inputs["Points"])
    link(group, instance_line.outputs["Mesh"], instance.inputs["Instance"])

    realize = create_node(group, f"PW FlatArc1 {prefix} Realize Paths", "GeometryNodeRealizeInstances", curve_frame, (220, 360))
    link(group, instance.outputs["Instances"], realize.inputs["Geometry"])

    to_curve = create_node(group, f"PW FlatArc1 {prefix} Mesh To Curve", "GeometryNodeMeshToCurve", curve_frame, (440, 360))
    link(group, realize.outputs["Geometry"], to_curve.inputs["Mesh"])

    index = create_node(group, f"PW FlatArc1 {prefix} Point Index", "GeometryNodeInputIndex", curve_frame, (650, 580))
    curve_of_point_name = "Curve of Point" if is_warp else "Curve of Point.001"
    curve_of_point = create_node(group, curve_of_point_name, "GeometryNodeCurveOfPoint", curve_frame, (850, 580))
    link(group, index.outputs["Index"], curve_of_point.inputs["Point Index"])

    draft_input = inputs
    face_index = build_draft_sampling(
        group,
        frames,
        draft_input,
        curve_of_point_name,
        curve_of_point.outputs["Curve Index"],
        curve_of_point.outputs["Index in Curve"],
        get_socket(draft_input.outputs, "Thread Subdivisions"),
        get_socket(draft_input.outputs, "Draft Rows" if is_warp else "Draft Columns"),
        get_socket(draft_input.outputs, "Draft Columns" if is_warp else "Draft Rows"),
        is_warp=is_warp,
    )

    draft_object_info = group.nodes.get("PW Draft Object Info")
    cell_code = group.nodes.get("PW Draft Cell Code")
    material_attr = group.nodes.get(f"PW Draft {prefix} Material Id")

    cell_sample = create_node(group, f"PW Draft {prefix} Sample", "GeometryNodeSampleIndex", frames["Draft Sampling"], (1120, 130 if is_warp else -590))
    cell_sample.data_type = "INT"
    cell_sample.domain = "FACE"
    link(group, draft_object_info.outputs["Geometry"], cell_sample.inputs["Geometry"])
    link(group, cell_code.outputs["Attribute"], cell_sample.inputs["Value"])
    link(group, face_index.outputs["Value"], cell_sample.inputs["Index"])

    material_sample = create_node(group, f"PW Draft {prefix} Material Sample", "GeometryNodeSampleIndex", frames["Draft Sampling"], (1120, -80 if is_warp else -800))
    material_sample.data_type = "INT"
    material_sample.domain = "FACE"
    link(group, draft_object_info.outputs["Geometry"], material_sample.inputs["Geometry"])
    link(group, material_attr.outputs["Attribute"], material_sample.inputs["Value"])
    link(group, face_index.outputs["Value"], material_sample.inputs["Index"])

    material_one_based = create_math(
        group,
        f"PW Draft {prefix} Material One Based",
        "ADD",
        frames["Draft Sampling"],
        (1320, -80 if is_warp else -800),
        {1: 1.0},
    )
    link(group, material_sample.outputs["Value"], material_one_based.inputs[0])

    sign = create_math(
        group,
        f"PW Draft {prefix} Sign",
        "MULTIPLY_ADD",
        frames["Draft Sampling"],
        (1320, 130 if is_warp else -590),
        {1: 2.0 if is_warp else -2.0, 2: -1.0 if is_warp else 1.0},
    )
    link(group, cell_sample.outputs["Value"], sign.inputs[0])

    half_amp = create_math(group, f"PW FlatArc1 {prefix} Half Amplitude", "MULTIPLY", curve_frame, (650, 220), {1: 0.5})
    link(group, get_socket(inputs.outputs, "Amplitude"), half_amp.inputs[0])
    z_offset = create_math(group, f"PW FlatArc1 {prefix} Z Offset", "MULTIPLY", curve_frame, (850, 220))
    link(group, sign.outputs["Value"], z_offset.inputs[0])
    link(group, half_amp.outputs["Value"], z_offset.inputs[1])
    offset_vector = create_combine(group, f"PW FlatArc1 {prefix} Bend Offset", curve_frame, (1050, 220))
    link(group, z_offset.outputs["Value"], offset_vector.inputs["Z"])

    set_position = create_node(group, f"PW FlatArc1 {prefix} Set Position", "GeometryNodeSetPosition", curve_frame, (1260, 360))
    link(group, to_curve.outputs["Curve"], set_position.inputs["Geometry"])
    link(group, offset_vector.outputs["Vector"], set_position.inputs["Offset"])

    try:
        normal = create_node(group, f"PW FlatArc1 {prefix} Set Curve Normal", "GeometryNodeSetCurveNormal", curve_frame, (1480, 360))
        normal.inputs["Mode"].default_value = "Z Up"
        link(group, set_position.outputs["Geometry"], normal.inputs["Curve"])
        geometry_socket = normal.outputs["Curve"]
    except Exception:
        geometry_socket = set_position.outputs["Geometry"]

    store_cell = create_store_attr(group, f"PW FlatArc1 {prefix} Store cell_code_sampled", "cell_code_sampled", "INT", "POINT", curve_frame, (1700, 510))
    link(group, geometry_socket, store_cell.inputs["Geometry"])
    link(group, cell_sample.outputs["Value"], store_cell.inputs["Value"])

    store_material = create_store_attr(group, f"PW FlatArc1 {prefix} Store material_id", "material_id", "INT", "POINT", curve_frame, (1920, 510))
    link(group, store_cell.outputs["Geometry"], store_material.inputs["Geometry"])
    link(group, material_one_based.outputs["Value"], store_material.inputs["Value"])

    spline_param = create_node(group, f"PW FlatArc1 {prefix} Spline Parameter", "GeometryNodeSplineParameter", curve_frame, (1700, 170))
    spline_len = create_node(group, f"PW FlatArc1 {prefix} Spline Length", "GeometryNodeSplineLength", curve_frame, (1700, -10))
    store_u_factor = create_store_attr(group, f"PW FlatArc1 {prefix} Store u_along", "u_along", "FLOAT", "POINT", curve_frame, (2140, 510))
    link(group, store_material.outputs["Geometry"], store_u_factor.inputs["Geometry"])
    link(group, spline_param.outputs["Factor"], store_u_factor.inputs["Value"])

    store_length = create_store_attr(group, f"PW FlatArc1 {prefix} Store strand_length_bu", "strand_length_bu", "FLOAT", "POINT", curve_frame, (2360, 510))
    link(group, store_u_factor.outputs["Geometry"], store_length.inputs["Geometry"])
    link(group, spline_len.outputs["Length"], store_length.inputs["Value"])

    random_u = create_node(group, f"PW FlatArc1 {prefix} Random U", "FunctionNodeRandomValue", curve_frame, (1920, 70))
    random_u.data_type = "FLOAT"
    random_u.inputs[2].default_value = 0.0
    random_u.inputs[3].default_value = 1.0
    link(group, curve_of_point.outputs["Curve Index"], random_u.inputs["ID"])
    link(group, get_socket(inputs.outputs, "Seed"), random_u.inputs["Seed"])

    random_scaled = create_math(group, f"PW FlatArc1 {prefix} Random U Scaled", "MULTIPLY", curve_frame, (2140, 70))
    link(group, random_u.outputs[1], random_scaled.inputs[0])
    link(group, get_socket(inputs.outputs, "UV Random U"), random_scaled.inputs[1])

    stride_index = create_math(group, f"PW FlatArc1 {prefix} U Stride x Index", "MULTIPLY", curve_frame, (1920, -130))
    link(group, curve_of_point.outputs["Curve Index"], stride_index.inputs[0])
    link(group, get_socket(inputs.outputs, stride_name), stride_index.inputs[1])

    uv_offset_sum = create_math(group, f"PW FlatArc1 {prefix} UV Offset U", "ADD", curve_frame, (2360, 70))
    link(group, stride_index.outputs["Value"], uv_offset_sum.inputs[0])
    link(group, random_scaled.outputs["Value"], uv_offset_sum.inputs[1])

    store_offset = create_store_attr(group, f"PW FlatArc1 {prefix} Store uv_offset_u", "uv_offset_u", "FLOAT", "POINT", curve_frame, (2580, 510))
    link(group, store_length.outputs["Geometry"], store_offset.inputs["Geometry"])
    link(group, uv_offset_sum.outputs["Value"], store_offset.inputs["Value"])

    store_offset_v = create_store_attr(group, f"PW FlatArc1 {prefix} Store uv_offset_v", "uv_offset_v", "FLOAT", "POINT", curve_frame, (2800, 510))
    link(group, store_offset.outputs["Geometry"], store_offset_v.inputs["Geometry"])
    store_offset_v.inputs["Value"].default_value = 0.0

    return store_offset_v.outputs["Geometry"]


def build_flat_arc1_group(group):
    clear_group(group)
    build_interface(group)
    frames = create_frames(group)

    inputs = create_group_input(group, "PW FlatArc1 Input", frames["Inputs"], (-80, 80))
    draft_input = create_group_input(group, "PW Draft Input", frames["Draft Sampling"], (-220, 280))
    material_input = create_group_input(group, "PW FlatArc1 Material Metadata", frames["Material Selection"], (-260, 470))

    output = create_node(group, "Group Output", "NodeGroupOutput", frames["Output"], (240, 80))

    draft_info = create_node(group, "PW Draft Object Info", "GeometryNodeObjectInfo", frames["Draft Sampling"], (-20, 460))
    link(group, get_socket(draft_input.outputs, "Draft Object"), draft_info.inputs["Object"])
    cell_code = create_named_attr(group, "PW Draft Cell Code", "cell_code", "INT", frames["Draft Sampling"], (-20, 260))
    create_named_attr(group, "PW Draft Warp Material Id", "warp_material_id", "INT", frames["Draft Sampling"], (-20, 60))
    create_named_attr(group, "PW Draft Weft Material Id", "weft_material_id", "INT", frames["Draft Sampling"], (-20, -140))

    warp_curves = create_curve_branch(group, frames, draft_input, is_warp=True)
    weft_curves = create_curve_branch(group, frames, draft_input, is_warp=False)

    join_curves = create_node(group, "PW FlatArc1 Join Warp Weft Curves", "GeometryNodeJoinGeometry", frames["Flat Arc1 Profile"], (-620, 360))
    link(group, warp_curves, join_curves.inputs["Geometry"])
    link(group, weft_curves, join_curves.inputs["Geometry"])

    arc1_radius_value = create_value(group, "PW Band - Geo Arc1 Radius Value", 0.015, frames["Flat Arc1 Profile"], (-620, 120))
    arc2_radius_value = create_value(group, "PW Band - Geo Arc2 Radius Value", 0.025, frames["Flat Arc1 Profile"], (-620, -80))
    core_frac_raw = create_math(group, "PW Band - Geo Core Frac Raw", "DIVIDE", frames["Flat Arc1 Profile"], (-410, 20))
    link(group, arc1_radius_value.outputs["Value"], core_frac_raw.inputs[0])
    link(group, arc2_radius_value.outputs["Value"], core_frac_raw.inputs[1])
    core_frac = create_math(group, "PW Band - Geo Core Frac", "MINIMUM", frames["Flat Arc1 Profile"], (-200, 20), {1: 1.0})
    link(group, core_frac_raw.outputs["Value"], core_frac.inputs[0])
    half_core_frac = create_math(group, "PW Band - Geo Half Core Frac", "MULTIPLY", frames["Flat Arc1 Profile"], (10, 20), {1: 0.5})
    link(group, core_frac.outputs["Value"], half_core_frac.inputs[0])
    split_min = create_math(group, "PW Band - Split Minus", "SUBTRACT", frames["Flat Arc1 Profile"], (220, 80), {0: 0.5})
    link(group, half_core_frac.outputs["Value"], split_min.inputs[1])
    split_plus = create_math(group, "PW Band - Split Plus", "ADD", frames["Flat Arc1 Profile"], (220, -80), {0: 0.5})
    link(group, half_core_frac.outputs["Value"], split_plus.inputs[1])

    arc1_profile = create_node(group, "PW Arc1 Sample Profile", "GeometryNodeCurveArc", frames["Flat Arc1 Profile"], (470, 250), label="Arc1 profile")
    arc1_profile.mode = "RADIUS"
    arc1_profile.inputs["Resolution"].default_value = 11
    arc1_profile.inputs["Start Angle"].default_value = -0.5235987901687622
    arc1_profile.inputs["Sweep Angle"].default_value = -2.090904474258423
    link(group, arc1_radius_value.outputs["Value"], arc1_profile.inputs["Radius"])
    arc1_factor = create_node(group, "PW Arc1 Sample Profile Factor", "GeometryNodeSplineParameter", frames["Flat Arc1 Profile"], (690, 30))
    arc1_store_v = create_store_attr(group, "PW Arc1 Sample Store v_around", "v_around", "FLOAT", "POINT", frames["Flat Arc1 Profile"], (920, 250))
    link(group, arc1_profile.outputs["Curve"], arc1_store_v.inputs["Geometry"])
    link(group, arc1_factor.outputs["Factor"], arc1_store_v.inputs["Value"])
    arc1_store_main = create_store_attr(group, "PW Arc1 Sample Tag Main", "is_sub_strand", "FLOAT", "POINT", frames["Flat Arc1 Profile"], (1140, 250))
    link(group, arc1_store_v.outputs["Geometry"], arc1_store_main.inputs["Geometry"])
    arc1_store_main.inputs["Value"].default_value = 0.0
    arc1_store_natural = create_store_attr(group, "PW Arc1 Store Profile Natural", "pw_profile_natural", "FLOAT", "POINT", frames["Flat Arc1 Profile"], (1360, 250))
    link(group, arc1_store_main.outputs["Geometry"], arc1_store_natural.inputs["Geometry"])
    arc1_store_natural.inputs["Value"].default_value = 0.0
    arc1_store_actual = create_store_attr(group, "PW Arc1 Store Profile Actual", "pw_profile_actual", "FLOAT", "POINT", frames["Flat Arc1 Profile"], (1580, 250))
    link(group, arc1_store_natural.outputs["Geometry"], arc1_store_actual.inputs["Geometry"])
    arc1_store_actual.inputs["Value"].default_value = 0.0

    arc1_curve_to_mesh = create_node(group, "PW Arc1 Sample Curve To Mesh", "GeometryNodeCurveToMesh", frames["Flat Arc1 Profile"], (1800, 360), label="Arc1 sample surface")
    link(group, join_curves.outputs["Geometry"], arc1_curve_to_mesh.inputs["Curve"])
    link(group, arc1_store_actual.outputs["Geometry"], arc1_curve_to_mesh.inputs["Profile Curve"])
    arc1_curve_to_mesh.inputs["Fill Caps"].default_value = False

    arc2_arc = create_node(group, "PW Arc2 Profile Arc", "GeometryNodeCurveArc", frames["Flat Arc1 Profile"], (470, -280), label="Arc2 halo profile")
    arc2_arc.mode = "RADIUS"
    arc2_arc.inputs["Resolution"].default_value = 8
    arc2_arc.inputs["Start Angle"].default_value = 0.5235987901687622
    arc2_arc.inputs["Sweep Angle"].default_value = 2.094395160675049
    link(group, arc2_radius_value.outputs["Value"], arc2_arc.inputs["Radius"])
    arc2_line = create_node(group, "PW Arc2 Profile Points", "GeometryNodeMeshLine", frames["Flat Arc1 Profile"], (470, -600))
    arc2_line.mode = "OFFSET"
    arc2_line.inputs["Count"].default_value = 31
    arc2_line.inputs["Offset"].default_value = (1.0 / 30.0, 0.0, 0.0)
    arc2_position = create_node(group, "PW Arc2 Profile Position", "GeometryNodeInputPosition", frames["Flat Arc1 Profile"], (690, -780))
    arc2_natural = create_node(group, "PW Arc2 Profile Natural Factor", "ShaderNodeSeparateXYZ", frames["Flat Arc1 Profile"], (910, -780))
    link(group, arc2_position.outputs["Position"], arc2_natural.inputs["Vector"])
    arc2_sample = create_node(group, "PW Arc2 Profile Sample Arc", "GeometryNodeSampleCurve", frames["Flat Arc1 Profile"], (910, -500))
    link(group, arc2_arc.outputs["Curve"], arc2_sample.inputs["Curves"])
    link(group, arc2_natural.outputs["X"], arc2_sample.inputs["Factor"])

    arc2_store_natural = create_store_attr(group, "PW Arc2 Store Profile Natural", "pw_profile_natural", "FLOAT", "POINT", frames["Flat Arc1 Profile"], (1140, -600))
    link(group, arc2_line.outputs["Mesh"], arc2_store_natural.inputs["Geometry"])
    link(group, arc2_natural.outputs["X"], arc2_store_natural.inputs["Value"])
    arc2_store_actual = create_store_attr(group, "PW Arc2 Store Profile Actual", "pw_profile_actual", "FLOAT", "POINT", frames["Flat Arc1 Profile"], (1360, -600))
    link(group, arc2_store_natural.outputs["Geometry"], arc2_store_actual.inputs["Geometry"])
    link(group, arc2_natural.outputs["X"], arc2_store_actual.inputs["Value"])
    arc2_store_v = create_store_attr(group, "PW Arc2 Store v_around", "v_around", "FLOAT", "POINT", frames["Flat Arc1 Profile"], (1580, -600))
    link(group, arc2_store_actual.outputs["Geometry"], arc2_store_v.inputs["Geometry"])
    link(group, arc2_natural.outputs["X"], arc2_store_v.inputs["Value"])
    arc2_store_sub = create_store_attr(group, "PW Arc2 Tag Sub Strand", "is_sub_strand", "FLOAT", "POINT", frames["Flat Arc1 Profile"], (1800, -600))
    link(group, arc2_store_v.outputs["Geometry"], arc2_store_sub.inputs["Geometry"])
    arc2_store_sub.inputs["Value"].default_value = 1.0
    arc2_set_position = create_node(group, "PW Arc2 Set Profile Position", "GeometryNodeSetPosition", frames["Flat Arc1 Profile"], (2020, -600))
    link(group, arc2_store_sub.outputs["Geometry"], arc2_set_position.inputs["Geometry"])
    link(group, arc2_sample.outputs["Position"], arc2_set_position.inputs["Position"])
    arc2_profile_curve = create_node(group, "PW Arc2 Profile Mesh To Curve", "GeometryNodeMeshToCurve", frames["Flat Arc1 Profile"], (2240, -600))
    link(group, arc2_set_position.outputs["Geometry"], arc2_profile_curve.inputs["Mesh"])

    arc2_curve_to_mesh = create_node(group, "PW Arc2 Curve To Mesh", "GeometryNodeCurveToMesh", frames["Flat Arc1 Profile"], (2460, -60), label="Arc2 halo surface")
    link(group, join_curves.outputs["Geometry"], arc2_curve_to_mesh.inputs["Curve"])
    link(group, arc2_profile_curve.outputs["Curve"], arc2_curve_to_mesh.inputs["Profile Curve"])
    arc2_curve_to_mesh.inputs["Fill Caps"].default_value = False

    join_surfaces = create_node(group, "PW Join Arc1 And Arc2 Surfaces", "GeometryNodeJoinGeometry", frames["Flat Arc1 Profile"], (2680, 220))
    link(group, arc2_curve_to_mesh.outputs["Mesh"], join_surfaces.inputs["Geometry"])
    link(group, arc1_curve_to_mesh.outputs["Mesh"], join_surfaces.inputs["Geometry"])
    sub_enable_switch = create_node(group, "PW Sub Strand Enable Switch", "GeometryNodeSwitch", frames["Flat Arc1 Profile"], (2900, 220))
    sub_enable_switch.input_type = "GEOMETRY"
    link(group, get_socket(inputs.outputs, "Sub Strand Enable"), sub_enable_switch.inputs["Switch"])
    link(group, arc1_curve_to_mesh.outputs["Mesh"], sub_enable_switch.inputs["False"])
    link(group, join_surfaces.outputs["Geometry"], sub_enable_switch.inputs["True"])

    store_arc1_radius = create_store_attr(group, "PW Debug Store Arc1 Radius", "arc1_radius_geometry", "FLOAT", "POINT", frames["Flat Arc1 Profile"], (3120, 220))
    link(group, sub_enable_switch.outputs["Output"], store_arc1_radius.inputs["Geometry"])
    link(group, arc1_radius_value.outputs["Value"], store_arc1_radius.inputs["Value"])
    store_arc2_radius = create_store_attr(group, "PW Debug Store Arc2 Radius", "arc2_radius_geometry", "FLOAT", "POINT", frames["Flat Arc1 Profile"], (3340, 220))
    link(group, store_arc1_radius.outputs["Geometry"], store_arc2_radius.inputs["Geometry"])
    link(group, arc2_radius_value.outputs["Value"], store_arc2_radius.inputs["Value"])
    store_core_frac_raw = create_store_attr(group, "PW Debug Store Arc2 Core Frac Raw", "arc2_core_frac_raw", "FLOAT", "POINT", frames["Flat Arc1 Profile"], (3560, 220))
    link(group, store_arc2_radius.outputs["Geometry"], store_core_frac_raw.inputs["Geometry"])
    link(group, core_frac_raw.outputs["Value"], store_core_frac_raw.inputs["Value"])
    store_core_frac = create_store_attr(group, "PW Debug Store Arc2 Core Frac", "arc2_core_frac_geometry", "FLOAT", "POINT", frames["Flat Arc1 Profile"], (3780, 220))
    link(group, store_core_frac_raw.outputs["Geometry"], store_core_frac.inputs["Geometry"])
    link(group, core_frac.outputs["Value"], store_core_frac.inputs["Value"])
    store_split_min = create_store_attr(group, "PW Debug Store Arc2 Split Min", "arc2_core_split_min", "FLOAT", "POINT", frames["Flat Arc1 Profile"], (4000, 220))
    link(group, store_core_frac.outputs["Geometry"], store_split_min.inputs["Geometry"])
    link(group, split_min.outputs["Value"], store_split_min.inputs["Value"])
    store_split_max = create_store_attr(group, "PW Debug Store Arc2 Split Max", "arc2_core_split_max", "FLOAT", "POINT", frames["Flat Arc1 Profile"], (4220, 220))
    link(group, store_split_min.outputs["Geometry"], store_split_max.inputs["Geometry"])
    link(group, split_plus.outputs["Value"], store_split_max.inputs["Value"])
    profiled_mesh = store_split_max.outputs["Geometry"]

    material_id_attr = create_named_attr(group, "PW FlatArc1 Read material_id", "material_id", "INT", frames["Material Selection"], (-260, 160))
    image_width, _ = create_material_selector(group, frames, material_id_attr.outputs["Attribute"], material_input, "Image Width Px", 220)
    material_scale_u, _ = create_material_selector(group, frames, material_id_attr.outputs["Attribute"], material_input, "Texture Scale U", -260)
    arc1_min, _ = create_material_selector(group, frames, material_id_attr.outputs["Attribute"], material_input, "Arc 1 V Min", -740)
    arc1_max, _ = create_material_selector(group, frames, material_id_attr.outputs["Attribute"], material_input, "Arc 1 V Max", -1220)
    arc2_min, _ = create_material_selector(group, frames, material_id_attr.outputs["Attribute"], material_input, "Arc 2 V Min", -1700)
    arc2_max, _ = create_material_selector(group, frames, material_id_attr.outputs["Attribute"], material_input, "Arc 2 V Max", -2180)

    texture_world_width = create_math(group, "PW FlatArc1 Texture World Width BU", "DIVIDE", frames["Resolution Diagnostics"], (-320, 340))
    link(group, image_width, texture_world_width.inputs[0])
    link(group, get_socket(inputs.outputs, "Scanner Pixels Per BU"), texture_world_width.inputs[1])

    u_factor_attr = create_named_attr(group, "PW FlatArc1 Read u_along", "u_along", "FLOAT", frames["Texture U"], (-260, 480))
    strand_length_attr = create_named_attr(group, "PW FlatArc1 Read strand_length_bu", "strand_length_bu", "FLOAT", frames["Texture U"], (-260, 260))
    uv_offset_attr = create_named_attr(group, "PW FlatArc1 Read uv_offset_u", "uv_offset_u", "FLOAT", frames["Texture U"], (-260, 40))

    repeats_per_strand = create_math(group, "PW FlatArc1 Repeats Per Strand", "DIVIDE", frames["Texture U"], (-20, 260))
    link(group, strand_length_attr.outputs["Attribute"], repeats_per_strand.inputs[0])
    link(group, texture_world_width.outputs["Value"], repeats_per_strand.inputs[1])
    root_u = create_math(group, "PW FlatArc1 Root Texture Scale U", "MULTIPLY", frames["Texture U"], (200, 260))
    link(group, repeats_per_strand.outputs["Value"], root_u.inputs[0])
    link(group, get_socket(inputs.outputs, "Texture Scale U"), root_u.inputs[1])
    final_u_scale = create_math(group, "PW FlatArc1 Material Texture Scale U", "MULTIPLY", frames["Texture U"], (420, 260))
    link(group, root_u.outputs["Value"], final_u_scale.inputs[0])
    link(group, material_scale_u, final_u_scale.inputs[1])
    u_scaled = create_math(group, "PW FlatArc1 U Factor x Scale", "MULTIPLY", frames["Texture U"], (640, 260))
    link(group, u_factor_attr.outputs["Attribute"], u_scaled.inputs[0])
    link(group, final_u_scale.outputs["Value"], u_scaled.inputs[1])
    # Deterministic same-strand U: Arc1 and Arc2 share this one U stream.
    # The older nearest-surface Arc2 U transfer is intentionally not rebuilt;
    # it introduced small endpoint shrink / plateaus on Arc2.
    final_u = create_math(group, "PW FlatArc1 Final U", "ADD", frames["Texture U"], (860, 260))
    link(group, u_scaled.outputs["Value"], final_u.inputs[0])
    link(group, uv_offset_attr.outputs["Attribute"], final_u.inputs[1])

    v_attr = create_named_attr(group, "PW FlatArc1 Read v_around", "v_around", "FLOAT", frames["Texture V"], (-260, 420))
    is_sub_attr = create_named_attr(group, "PW FlatArc1 Read is_sub_strand", "is_sub_strand", "FLOAT", frames["Texture V"], (-260, 220))

    raw_padded_min = create_math(group, "PW FlatArc1 Arc1 Raw Padded Min", "SUBTRACT", frames["Texture V"], (-20, 260))
    link(group, arc1_min, raw_padded_min.inputs[0])
    link(group, get_socket(inputs.outputs, "Arc 1 V Padding"), raw_padded_min.inputs[1])
    padded_min = create_math(group, "PW FlatArc1 Arc1 Padded Min Clamp", "MAXIMUM", frames["Texture V"], (200, 260))
    link(group, raw_padded_min.outputs["Value"], padded_min.inputs[0])
    link(group, arc2_min, padded_min.inputs[1])
    raw_padded_max = create_math(group, "PW FlatArc1 Arc1 Raw Padded Max", "ADD", frames["Texture V"], (-20, 40))
    link(group, arc1_max, raw_padded_max.inputs[0])
    link(group, get_socket(inputs.outputs, "Arc 1 V Padding"), raw_padded_max.inputs[1])
    padded_max = create_math(group, "PW FlatArc1 Arc1 Padded Max Clamp", "MINIMUM", frames["Texture V"], (200, 40))
    link(group, raw_padded_max.outputs["Value"], padded_max.inputs[0])
    link(group, arc2_max, padded_max.inputs[1])

    v_times_pi = create_math(group, "PW MatchProjV - v around x sweep", "MULTIPLY", frames["Texture V"], (-20, 560), {1: 3.141592653589793})
    link(group, v_attr.outputs["Attribute"], v_times_pi.inputs[0])
    cos_theta = create_math(group, "PW MatchProjV - cos theta", "COSINE", frames["Texture V"], (200, 560))
    link(group, v_times_pi.outputs["Value"], cos_theta.inputs[0])
    cos_delta = create_math(group, "PW MatchProjV - cos start minus cos", "SUBTRACT", frames["Texture V"], (420, 560), {0: 1.0})
    link(group, cos_theta.outputs["Value"], cos_delta.inputs[1])
    projected_v = create_math(group, "PW MatchProjV - projected factor", "DIVIDE", frames["Texture V"], (640, 560), {1: 2.0})
    link(group, cos_delta.outputs["Value"], projected_v.inputs[0])

    v_span = create_math(group, "PW FlatArc1 Arc1 Padded Span", "SUBTRACT", frames["Texture V"], (420, 150))
    link(group, padded_max.outputs["Value"], v_span.inputs[0])
    link(group, padded_min.outputs["Value"], v_span.inputs[1])
    arc1_scaled_v = create_math(group, "PW FlatArc1 Projected V x Span", "MULTIPLY", frames["Texture V"], (860, 420))
    link(group, projected_v.outputs["Value"], arc1_scaled_v.inputs[0])
    link(group, v_span.outputs["Value"], arc1_scaled_v.inputs[1])
    arc1_v = create_math(group, "PW Band - Arc1 V", "ADD", frames["Texture V"], (1080, 420))
    link(group, arc1_scaled_v.outputs["Value"], arc1_v.inputs[0])
    link(group, padded_min.outputs["Value"], arc1_v.inputs[1])

    core_span = create_math(group, "PW U - Sec Core Span", "SUBTRACT", frames["Texture V"], (420, -120))
    link(group, arc1_max, core_span.inputs[0])
    link(group, arc1_min, core_span.inputs[1])
    core_width = create_math(group, "PW U - Sec Core Width", "SUBTRACT", frames["Texture V"], (420, -320))
    link(group, split_plus.outputs["Value"], core_width.inputs[0])
    link(group, split_min.outputs["Value"], core_width.inputs[1])
    core_width_safe = create_math(group, "PW U - Sec Core Width Safe", "MAXIMUM", frames["Texture V"], (640, -320), {1: 0.000001})
    link(group, core_width.outputs["Value"], core_width_safe.inputs[0])
    core_slope = create_math(group, "PW U - Sec Core Slope", "DIVIDE", frames["Texture V"], (860, -220))
    link(group, core_span.outputs["Value"], core_slope.inputs[0])
    link(group, core_width_safe.outputs["Value"], core_slope.inputs[1])
    top_delta = create_math(group, "PW HaloFlow - Top Delta From Core Rate", "MULTIPLY", frames["Texture V"], (1080, -260))
    link(group, core_slope.outputs["Value"], top_delta.inputs[0])
    link(group, split_min.outputs["Value"], top_delta.inputs[1])
    top_outer = create_math(group, "PW HaloFlow - Top Outer Free V", "SUBTRACT", frames["Texture V"], (1300, -260))
    link(group, arc1_min, top_outer.inputs[0])
    link(group, top_delta.outputs["Value"], top_outer.inputs[1])
    arc2_v_scaled = create_math(group, "PW HaloFlow - v around x core rate", "MULTIPLY", frames["Texture V"], (1080, -40))
    link(group, v_attr.outputs["Attribute"], arc2_v_scaled.inputs[0])
    link(group, core_slope.outputs["Value"], arc2_v_scaled.inputs[1])
    arc2_v = create_math(group, "PW Band - Arc2 V", "ADD", frames["Texture V"], (1300, -40))
    link(group, top_outer.outputs["Value"], arc2_v.inputs[0])
    link(group, arc2_v_scaled.outputs["Value"], arc2_v.inputs[1])

    band_diff = create_math(group, "PW Band - Diff", "SUBTRACT", frames["Texture V"], (1520, 200))
    link(group, arc2_v.outputs["Value"], band_diff.inputs[0])
    link(group, arc1_v.outputs["Value"], band_diff.inputs[1])
    band_v = create_math(group, "PW Band - Band V", "MULTIPLY_ADD", frames["Texture V"], (1740, 200))
    link(group, is_sub_attr.outputs["Attribute"], band_v.inputs[0])
    link(group, band_diff.outputs["Value"], band_v.inputs[1])
    link(group, arc1_v.outputs["Value"], band_v.inputs[2])

    v_center = create_math(group, "Texture V Center", "SUBTRACT", frames["Texture V"], (1960, 300), {1: 0.5})
    link(group, band_v.outputs["Value"], v_center.inputs[0])
    v_scale = create_math(group, "PW FlatArc1 Scale V + Sub*is_sub", "MULTIPLY_ADD", frames["Texture V"], (1960, 70))
    link(group, is_sub_attr.outputs["Attribute"], v_scale.inputs[0])
    link(group, get_socket(inputs.outputs, "Sub Texture Scale V"), v_scale.inputs[1])
    link(group, get_socket(inputs.outputs, "Texture Scale V"), v_scale.inputs[2])
    v_offset = create_math(group, "PW FlatArc1 Offset V + Sub*is_sub", "MULTIPLY_ADD", frames["Texture V"], (1960, -160))
    link(group, is_sub_attr.outputs["Attribute"], v_offset.inputs[0])
    link(group, get_socket(inputs.outputs, "Sub Texture Offset V"), v_offset.inputs[1])
    link(group, get_socket(inputs.outputs, "Texture Offset V"), v_offset.inputs[2])
    v_base = create_math(group, "Texture V Base", "ADD", frames["Texture V"], (2180, -40), {0: 0.5})
    link(group, v_offset.outputs["Value"], v_base.inputs[1])
    v_texture_scale = create_math(group, "PW FlatArc1 Texture V Scaled Around Center", "MULTIPLY", frames["Texture V"], (2180, 220))
    link(group, v_center.outputs["Value"], v_texture_scale.inputs[0])
    link(group, v_scale.outputs["Value"], v_texture_scale.inputs[1])
    final_v = create_math(group, "PW FlatArc1 Final V", "ADD", frames["Texture V"], (2400, 140))
    link(group, v_texture_scale.outputs["Value"], final_v.inputs[0])
    link(group, v_base.outputs["Value"], final_v.inputs[1])

    uv_vector = create_combine(group, "PW FlatArc1 uv_scaled Vector", frames["Debug Attributes"], (-360, 260))
    link(group, final_u.outputs["Value"], uv_vector.inputs["X"])
    link(group, final_v.outputs["Value"], uv_vector.inputs["Y"])

    store_uv = create_store_attr(group, "PW FlatArc1 Store uv_scaled", "uv_scaled", "FLOAT2", "POINT", frames["Debug Attributes"], (-120, 440))
    link(group, profiled_mesh, store_uv.inputs["Geometry"])
    link(group, uv_vector.outputs["Vector"], store_uv.inputs["Value"])

    section_ratio_value = create_value(group, "PW U - Section Ratio", 1.0, frames["Texture U"], (1060, 40))
    store_section_ratio = create_store_attr(group, "PW FlatArc1 Store pw_section_ratio", "pw_section_ratio", "FLOAT", "POINT", frames["Debug Attributes"], (120, 440))
    link(group, store_uv.outputs["Geometry"], store_section_ratio.inputs["Geometry"])
    link(group, section_ratio_value.outputs["Value"], store_section_ratio.inputs["Value"])
    store_section_slope = create_store_attr(group, "PW FlatArc1 Store pw_section_slope", "pw_section_slope", "FLOAT", "POINT", frames["Debug Attributes"], (360, 440))
    link(group, store_section_ratio.outputs["Geometry"], store_section_slope.inputs["Geometry"])
    link(group, core_slope.outputs["Value"], store_section_slope.inputs["Value"])

    store_image_width = create_store_attr(group, "PW FlatArc1 Store source_image_width_px", "source_image_width_px", "FLOAT", "POINT", frames["Resolution Diagnostics"], (0, 120))
    link(group, store_section_slope.outputs["Geometry"], store_image_width.inputs["Geometry"])
    link(group, image_width, store_image_width.inputs["Value"])

    store_world_width = create_store_attr(group, "PW FlatArc1 Store texture_world_width_bu", "texture_world_width_bu", "FLOAT", "POINT", frames["Resolution Diagnostics"], (240, 120))
    link(group, store_image_width.outputs["Geometry"], store_world_width.inputs["Geometry"])
    link(group, texture_world_width.outputs["Value"], store_world_width.inputs["Value"])

    source_density = create_math(group, "PW FlatArc1 Source Pixels Per BU", "DIVIDE", frames["Resolution Diagnostics"], (0, -120))
    link(group, image_width, source_density.inputs[0])
    link(group, texture_world_width.outputs["Value"], source_density.inputs[1])
    store_texel_ratio = create_store_attr(group, "PW FlatArc1 Store screen_texel_ratio_estimate", "screen_texel_ratio_estimate", "FLOAT", "POINT", frames["Resolution Diagnostics"], (480, 120))
    link(group, store_world_width.outputs["Geometry"], store_texel_ratio.inputs["Geometry"])
    link(group, source_density.outputs["Value"], store_texel_ratio.inputs["Value"])

    material_index = create_int_math(group, "PW FlatArc1 Material Index Zero Based", "SUBTRACT", frames["Material Selection"], (2100, 120), {1: 1})
    link(group, material_id_attr.outputs["Attribute"], material_index.inputs[0])
    set_material_index = create_node(group, "PW FlatArc1 Set Material Index", "GeometryNodeSetMaterialIndex", frames["Material Selection"], (2300, 120))
    link(group, store_texel_ratio.outputs["Geometry"], set_material_index.inputs["Geometry"])
    link(group, material_index.outputs["Value"], set_material_index.inputs["Material Index"])

    material_applied = create_material_applier(
        group,
        frames,
        set_material_index.outputs["Geometry"],
        material_id_attr.outputs["Attribute"],
        material_input,
    )

    link(group, material_applied, output.inputs["Geometry"])


def socket_identifier(group, name: str):
    for item in group.interface.items_tree:
        if getattr(item, "item_type", None) == "SOCKET" and getattr(item, "in_out", None) == "INPUT" and item.name == name:
            return item.identifier
    return None


def set_modifier_value(modifier, group, name: str, value):
    ident = socket_identifier(group, name)
    if ident is not None:
        try:
            modifier[ident] = value
        except Exception:
            pass


def collect_existing_values(old_group, modifier):
    values = {}
    if old_group is None or modifier is None:
        return values
    for item in old_group.interface.items_tree:
        if getattr(item, "item_type", None) == "SOCKET" and getattr(item, "in_out", None) == "INPUT":
            try:
                values[item.name] = modifier[item.identifier]
            except Exception:
                pass
    return values


def assign_group_to_modifier(group, existing_values):
    obj = bpy.data.objects.get(TARGET_OBJECT_NAME)
    if obj is None:
        mesh = bpy.data.meshes.new(f"{TARGET_OBJECT_NAME}Mesh")
        obj = bpy.data.objects.new(TARGET_OBJECT_NAME, mesh)
        bpy.context.scene.collection.objects.link(obj)
    modifier = obj.modifiers.get(WEAVE_MODIFIER_NAME)
    if modifier is None or modifier.type != "NODES":
        modifier = obj.modifiers.new(WEAVE_MODIFIER_NAME, "NODES")
    modifier.node_group = group
    for item in group.interface.items_tree:
        if getattr(item, "item_type", None) != "SOCKET" or getattr(item, "in_out", None) != "INPUT":
            continue
        if item.name in existing_values:
            set_modifier_value(modifier, group, item.name, existing_values[item.name])
    # Diagnostic baseline: avoid inherited stale scatter unless the web push
    # intentionally overrides it.
    set_modifier_value(modifier, group, "UV Random U", 0.0)
    set_modifier_value(modifier, group, "Texture Scale V", 1.0)
    set_modifier_value(modifier, group, "Texture Offset V", 0.0)
    set_modifier_value(modifier, group, "Sub Strand Enable", True)
    set_modifier_value(modifier, group, "Sub Texture Scale V", 1.0)
    set_modifier_value(modifier, group, "Sub Texture Offset V", 0.0)
    return obj, modifier


def create_rebuild_group():
    old_group = bpy.data.node_groups.get(NODE_GROUP_NAME)
    obj = bpy.data.objects.get(TARGET_OBJECT_NAME)
    modifier = obj.modifiers.get(WEAVE_MODIFIER_NAME) if obj else None
    existing_values = collect_existing_values(old_group, modifier)

    if old_group is not None:
        old_group.name = f"{NODE_GROUP_NAME}.pre-flat-arc1-{timestamp()}"
        print(f"[flat-arc1] Previous node group renamed: {old_group.name}")

    group = bpy.data.node_groups.new(NODE_GROUP_NAME, "GeometryNodeTree")
    group["flat_arc1_sampling_contract"] = "logical_thread_tiling_v1"
    build_flat_arc1_group(group)
    obj, modifier = assign_group_to_modifier(group, existing_values)
    return group, obj, modifier


def summarize(group):
    return {
        "node_group": group.name,
        "nodes": len(group.nodes),
        "links": len(group.links),
        "frames": sum(1 for node in group.nodes if node.bl_idname == "NodeFrame"),
        "group_inputs": sum(1 for node in group.nodes if node.bl_idname == "NodeGroupInput"),
    }


def main():
    output_path = save_working_copy()
    group, obj, modifier = create_rebuild_group()
    bpy.context.view_layer.update()
    bpy.ops.wm.save_as_mainfile(filepath=str(output_path))
    print("[flat-arc1] Rebuild complete")
    print({
        "file": str(output_path),
        "object": obj.name,
        "modifier": modifier.name,
        **summarize(group),
    })


if __name__ == "__main__":
    main()
