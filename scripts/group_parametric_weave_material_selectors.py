"""Collapse repeated material float switch chains in Parametric Weave.

The active graph has six near-identical 16-way float switch chains for
per-material metadata. This script creates one reusable helper group,
`PW Helper - Select Material Float 16`, then replaces the visible chains with
six named group nodes.
"""

from __future__ import annotations

from pathlib import Path

import bpy


NODE_GROUP_NAME = "Parametric Weave knotty"
HELPER_GROUP_NAME = "PW Helper - Select Material Float 16"
VBAND_FRAME_NAME = "PW Layout - V Band Mapping"
MATERIAL_FRAME_NAME = "PW Layout - Material Assignment"


FAMILIES = [
    {
        "prefix": "PW Material Image Width",
        "socket_suffix": "Image Width Px",
        "node_name": "PW Select Active Material - Image Width Px",
        "label": "Select active material image width",
    },
    {
        "prefix": "PW Material Texture Scale U",
        "socket_suffix": "Texture Scale U",
        "node_name": "PW Select Active Material - Texture Scale U",
        "label": "Select active material U scale",
    },
    {
        "prefix": "PW Material Core V Min",
        "socket_suffix": "Arc 1 V Min",
        "node_name": "PW Select Active Material - Arc 1 V Min",
        "label": "Select active material Arc 1 V min",
    },
    {
        "prefix": "PW Material Core V Max",
        "socket_suffix": "Arc 1 V Max",
        "node_name": "PW Select Active Material - Arc 1 V Max",
        "label": "Select active material Arc 1 V max",
    },
    {
        "prefix": "PW Material Fiber Bot V Max",
        "socket_suffix": "Arc 2 V Min",
        "node_name": "PW Select Active Material - Arc 2 V Min",
        "label": "Select active material Arc 2 V min",
    },
    {
        "prefix": "PW Material Fiber Top V Min",
        "socket_suffix": "Arc 2 V Max",
        "node_name": "PW Select Active Material - Arc 2 V Max",
        "label": "Select active material Arc 2 V max",
    },
]


def absolute_location(node):
    x = node.location.x
    y = node.location.y
    parent = node.parent
    while parent is not None:
        x += parent.location.x
        y += parent.location.y
        parent = parent.parent
    return x, y


def set_parent_preserve_location(node, frame):
    x, y = absolute_location(node)
    fx, fy = absolute_location(frame)
    node.parent = frame
    node.location = (x - fx, y - fy)


def get_socket(sockets, name):
    socket = sockets.get(name)
    if socket is None:
        raise KeyError(name)
    return socket


def clear_helper_group(group):
    group.nodes.clear()
    group.interface.clear()


def ensure_helper_group():
    helper = bpy.data.node_groups.get(HELPER_GROUP_NAME)
    if helper is None:
        helper = bpy.data.node_groups.new(HELPER_GROUP_NAME, "GeometryNodeTree")
    clear_helper_group(helper)

    helper.interface.new_socket("Material Id", in_out="INPUT", socket_type="NodeSocketInt")
    for index in range(1, 17):
        helper.interface.new_socket(f"Value {index}", in_out="INPUT", socket_type="NodeSocketFloat")
    helper.interface.new_socket("Value", in_out="OUTPUT", socket_type="NodeSocketFloat")

    nodes = helper.nodes
    links = helper.links
    group_input = nodes.new("NodeGroupInput")
    group_input.name = "Input: material id + 16 float values"
    group_input.location = (-1000, 0)
    group_output = nodes.new("NodeGroupOutput")
    group_output.name = "Output: active material value"
    group_output.location = (3600, 0)

    previous_socket = get_socket(group_input.outputs, "Value 1")
    for index in range(2, 17):
        compare = nodes.new("FunctionNodeCompare")
        compare.name = f"Material Id == {index}"
        compare.label = f"Material {index}?"
        compare.data_type = "INT"
        compare.operation = "EQUAL"
        compare.location = (-620 + ((index - 2) % 5) * 280, 520 - ((index - 2) // 5) * 180)
        links.new(get_socket(group_input.outputs, "Material Id"), compare.inputs[2])
        compare.inputs[3].default_value = index

        switch = nodes.new("GeometryNodeSwitch")
        switch.name = f"Use Value {index}"
        switch.label = f"Use value {index}"
        switch.input_type = "FLOAT"
        switch.location = (-360 + (index - 2) * 240, -260)
        links.new(compare.outputs["Result"], switch.inputs["Switch"])
        links.new(previous_socket, switch.inputs["False"])
        links.new(get_socket(group_input.outputs, f"Value {index}"), switch.inputs["True"])
        previous_socket = switch.outputs["Output"]

    links.new(previous_socket, get_socket(group_output.inputs, "Value"))
    return helper


def make_selector_node(main_group, helper, family, index):
    nodes = main_group.nodes
    links = main_group.links
    frame = nodes.get(VBAND_FRAME_NAME)
    metadata_input = nodes.get("PW Input - Material Metadata")
    material_id_face = nodes.get("PW Material Id Face")
    if metadata_input is None or material_id_face is None:
        raise RuntimeError("Missing material metadata input or material id face node.")

    existing = nodes.get(family["node_name"])
    if existing is not None:
        nodes.remove(existing)

    node = nodes.new("GeometryNodeGroup")
    node.node_tree = helper
    node.name = family["node_name"]
    node.label = family["label"]
    node.location = (220 + (index % 2) * 520, -180 - (index // 2) * 260)
    if frame is not None:
        node.parent = frame

    links.new(get_socket(material_id_face.outputs, "Value"), get_socket(node.inputs, "Material Id"))
    for material_index in range(1, 17):
        source_name = f"Material {material_index} {family['socket_suffix']}"
        links.new(get_socket(metadata_input.outputs, source_name), get_socket(node.inputs, f"Value {material_index}"))

    return node


def replace_family(main_group, helper, family, index):
    nodes = main_group.nodes
    links = main_group.links
    final_node = nodes.get(f"{family['prefix']} Select 16")
    if final_node is None:
        print(f"SKIP missing final selector for {family['prefix']}")
        return 0

    output_socket = get_socket(final_node.outputs, "Output")
    destinations = [(link.to_node, link.to_socket) for link in list(links) if link.from_socket == output_socket]

    selector = make_selector_node(main_group, helper, family, index)
    for to_node, to_socket in destinations:
        links.new(get_socket(selector.outputs, "Value"), to_socket)

    removed = 0
    for name in [f"{family['prefix']} Base", *[f"{family['prefix']} Select {i}" for i in range(2, 17)]]:
        node = nodes.get(name)
        if node is not None:
            nodes.remove(node)
            removed += 1
    return removed


def move_compare_nodes_to_material_frame(main_group):
    frame = main_group.nodes.get(MATERIAL_FRAME_NAME)
    if frame is None:
        return 0
    moved = 0
    for index in range(2, 17):
        node = main_group.nodes.get(f"PW Material Is {index}")
        if node is None:
            continue
        set_parent_preserve_location(node, frame)
        node.location = (80 + ((index - 2) % 5) * 230, -560 - ((index - 2) // 5) * 140)
        moved += 1
    return moved


def main():
    main_group = bpy.data.node_groups.get(NODE_GROUP_NAME)
    if main_group is None:
        raise SystemExit(f"Node group not found: {NODE_GROUP_NAME}")

    helper = ensure_helper_group()
    removed = 0
    for index, family in enumerate(FAMILIES):
        removed += replace_family(main_group, helper, family, index)
    moved_compares = move_compare_nodes_to_material_frame(main_group)

    filepath = bpy.data.filepath
    if not filepath:
        raise SystemExit("Loaded blend has no filepath; refusing to save.")
    bpy.ops.wm.save_as_mainfile(filepath=str(Path(filepath)))
    print("Material selector grouping complete")
    print(f"  Helper group: {HELPER_GROUP_NAME}")
    print(f"  Visible switch/reroute nodes removed: {removed}")
    print(f"  Group selector nodes created: {len(FAMILIES)}")
    print(f"  Material compare nodes moved: {moved_compares}")


if __name__ == "__main__":
    main()
