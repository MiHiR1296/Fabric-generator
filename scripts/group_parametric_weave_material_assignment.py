"""Collapse the visible Material 1..16 assignment chain.

Creates `PW Helper - Apply Material Slots 16`, then replaces the main graph's
visible Set Material 1..16 cascade with one named helper node.
"""

from __future__ import annotations

from pathlib import Path

import bpy


NODE_GROUP_NAME = "Parametric Weave knotty"
HELPER_GROUP_NAME = "PW Helper - Apply Material Slots 16"
MATERIAL_FRAME_NAME = "PW Layout - Material Assignment"


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

    helper.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    helper.interface.new_socket("Material Id", in_out="INPUT", socket_type="NodeSocketInt")
    for index in range(1, 17):
        helper.interface.new_socket(f"Material {index}", in_out="INPUT", socket_type="NodeSocketMaterial")
    helper.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")

    nodes = helper.nodes
    links = helper.links
    group_input = nodes.new("NodeGroupInput")
    group_input.name = "Input: geometry + material id + slots"
    group_input.location = (-1000, 0)
    group_output = nodes.new("NodeGroupOutput")
    group_output.name = "Output: assigned geometry"
    group_output.location = (4300, 0)

    previous_geometry = get_socket(group_input.outputs, "Geometry")
    first_set = nodes.new("GeometryNodeSetMaterial")
    first_set.name = "Apply Material 1"
    first_set.label = "Default all geometry to Material 1"
    first_set.location = (-620, -120)
    links.new(previous_geometry, first_set.inputs["Geometry"])
    links.new(get_socket(group_input.outputs, "Material 1"), first_set.inputs["Material"])
    previous_geometry = first_set.outputs["Geometry"]

    for index in range(2, 17):
        compare = nodes.new("FunctionNodeCompare")
        compare.name = f"Material Id == {index}"
        compare.label = f"Material {index}?"
        compare.data_type = "INT"
        compare.operation = "EQUAL"
        compare.location = (-620 + ((index - 2) % 5) * 270, 520 - ((index - 2) // 5) * 170)
        links.new(get_socket(group_input.outputs, "Material Id"), compare.inputs[2])
        compare.inputs[3].default_value = index

        set_material = nodes.new("GeometryNodeSetMaterial")
        set_material.name = f"Apply Material {index}"
        set_material.label = f"Apply Material {index}"
        set_material.location = (-360 + (index - 2) * 270, -120)
        links.new(previous_geometry, set_material.inputs["Geometry"])
        links.new(compare.outputs["Result"], set_material.inputs["Selection"])
        links.new(get_socket(group_input.outputs, f"Material {index}"), set_material.inputs["Material"])
        previous_geometry = set_material.outputs["Geometry"]

    links.new(previous_geometry, get_socket(group_output.inputs, "Geometry"))
    return helper


def replace_assignment_chain(main_group, helper):
    nodes = main_group.nodes
    links = main_group.links
    start = nodes.get("Set Material.001")
    final = nodes.get("PW Set Material 16")
    material_input = nodes.get("PW Input - Material Slots")
    material_id_face = nodes.get("PW Material Id Face")
    frame = nodes.get(MATERIAL_FRAME_NAME)

    if start is None or final is None or material_input is None or material_id_face is None:
        raise RuntimeError("Missing material assignment chain nodes.")

    geometry_sources = [(link.from_node, link.from_socket) for link in list(links) if link.to_socket == start.inputs["Geometry"]]
    if not geometry_sources:
        raise RuntimeError("Material assignment chain has no geometry input link.")
    output_destinations = [(link.to_node, link.to_socket) for link in list(links) if link.from_socket == final.outputs["Geometry"]]

    existing = nodes.get("PW Apply Active Material Slots")
    if existing is not None:
        nodes.remove(existing)
    group_node = nodes.new("GeometryNodeGroup")
    group_node.node_tree = helper
    group_node.name = "PW Apply Active Material Slots"
    group_node.label = "Apply active Material 1..16 slots"
    group_node.location = (120, -120)
    if frame is not None:
        group_node.parent = frame

    source_node, source_socket = geometry_sources[0]
    links.new(source_socket, get_socket(group_node.inputs, "Geometry"))
    links.new(get_socket(material_id_face.outputs, "Value"), get_socket(group_node.inputs, "Material Id"))
    for index in range(1, 17):
        links.new(get_socket(material_input.outputs, f"Material {index}"), get_socket(group_node.inputs, f"Material {index}"))
    for _, destination_socket in output_destinations:
        links.new(get_socket(group_node.outputs, "Geometry"), destination_socket)

    removed = 0
    for name in ["Set Material.001", *[f"PW Set Material {index}" for index in range(2, 17)]]:
        node = nodes.get(name)
        if node is not None:
            nodes.remove(node)
            removed += 1
    for index in range(2, 17):
        node = nodes.get(f"PW Material Is {index}")
        if node is not None:
            nodes.remove(node)
            removed += 1
    return removed


def main():
    main_group = bpy.data.node_groups.get(NODE_GROUP_NAME)
    if main_group is None:
        raise SystemExit(f"Node group not found: {NODE_GROUP_NAME}")

    helper = ensure_helper_group()
    removed = replace_assignment_chain(main_group, helper)

    filepath = bpy.data.filepath
    if not filepath:
        raise SystemExit("Loaded blend has no filepath; refusing to save.")
    bpy.ops.wm.save_as_mainfile(filepath=str(Path(filepath)))
    print("Material assignment grouping complete")
    print(f"  Helper group: {HELPER_GROUP_NAME}")
    print(f"  Visible compare/set nodes removed: {removed}")
    print("  Group node created: PW Apply Active Material Slots")


if __name__ == "__main__":
    main()
