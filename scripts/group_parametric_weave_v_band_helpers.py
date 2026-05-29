"""Collapse small V-band math islands into named helper groups."""

from __future__ import annotations

from pathlib import Path

import bpy


NODE_GROUP_NAME = "Parametric Weave knotty"
VBAND_FRAME_NAME = "PW Layout - V Band Mapping"
PADDING_GROUP_NAME = "PW Helper - Arc 1 Padding Clamp"
MATCH_GROUP_NAME = "PW Helper - Arc 2 Match Arc 1 Range"


def get_socket(sockets, name):
    socket = sockets.get(name)
    if socket is None:
        raise KeyError(name)
    return socket


def first_source(group, to_socket):
    for link in group.links:
        if link.to_socket == to_socket:
            return link.from_socket
    raise RuntimeError(f"No source linked to {to_socket.name}")


def output_destinations(group, from_socket):
    return [link.to_socket for link in list(group.links) if link.from_socket == from_socket]


def clear_group(group):
    group.nodes.clear()
    group.interface.clear()


def ensure_padding_group():
    helper = bpy.data.node_groups.get(PADDING_GROUP_NAME)
    if helper is None:
        helper = bpy.data.node_groups.new(PADDING_GROUP_NAME, "GeometryNodeTree")
    clear_group(helper)

    for name in ["Arc 1 V Min", "Arc 1 V Max", "Arc 2 V Min", "Arc 2 V Max", "Padding"]:
        helper.interface.new_socket(name, in_out="INPUT", socket_type="NodeSocketFloat")
    helper.interface.new_socket("Padded Arc 1 V Min", in_out="OUTPUT", socket_type="NodeSocketFloat")
    helper.interface.new_socket("Padded Arc 1 V Max", in_out="OUTPUT", socket_type="NodeSocketFloat")

    nodes = helper.nodes
    links = helper.links
    group_input = nodes.new("NodeGroupInput")
    group_input.location = (-900, 0)
    group_output = nodes.new("NodeGroupOutput")
    group_output.location = (620, 0)

    min_sub = nodes.new("ShaderNodeMath")
    min_sub.name = "Arc1 Min - Padding"
    min_sub.operation = "SUBTRACT"
    min_sub.location = (-500, 120)
    links.new(get_socket(group_input.outputs, "Arc 1 V Min"), min_sub.inputs[0])
    links.new(get_socket(group_input.outputs, "Padding"), min_sub.inputs[1])

    min_clamp = nodes.new("ShaderNodeMath")
    min_clamp.name = "Clamp Min Inside Arc2"
    min_clamp.operation = "MAXIMUM"
    min_clamp.location = (-180, 120)
    links.new(min_sub.outputs["Value"], min_clamp.inputs[0])
    links.new(get_socket(group_input.outputs, "Arc 2 V Min"), min_clamp.inputs[1])

    max_add = nodes.new("ShaderNodeMath")
    max_add.name = "Arc1 Max + Padding"
    max_add.operation = "ADD"
    max_add.location = (-500, -120)
    links.new(get_socket(group_input.outputs, "Arc 1 V Max"), max_add.inputs[0])
    links.new(get_socket(group_input.outputs, "Padding"), max_add.inputs[1])

    max_clamp = nodes.new("ShaderNodeMath")
    max_clamp.name = "Clamp Max Inside Arc2"
    max_clamp.operation = "MINIMUM"
    max_clamp.location = (-180, -120)
    links.new(max_add.outputs["Value"], max_clamp.inputs[0])
    links.new(get_socket(group_input.outputs, "Arc 2 V Max"), max_clamp.inputs[1])

    links.new(min_clamp.outputs["Value"], get_socket(group_output.inputs, "Padded Arc 1 V Min"))
    links.new(max_clamp.outputs["Value"], get_socket(group_output.inputs, "Padded Arc 1 V Max"))
    return helper


def ensure_match_group():
    helper = bpy.data.node_groups.get(MATCH_GROUP_NAME)
    if helper is None:
        helper = bpy.data.node_groups.new(MATCH_GROUP_NAME, "GeometryNodeTree")
    clear_group(helper)

    helper.interface.new_socket("Match Enabled", in_out="INPUT", socket_type="NodeSocketBool")
    for name in ["Piecewise Arc 2 V", "V Around", "Padded Arc 1 V Min", "Padded Arc 1 V Max"]:
        helper.interface.new_socket(name, in_out="INPUT", socket_type="NodeSocketFloat")
    helper.interface.new_socket("Arc 2 V", in_out="OUTPUT", socket_type="NodeSocketFloat")

    nodes = helper.nodes
    links = helper.links
    group_input = nodes.new("NodeGroupInput")
    group_input.location = (-1080, 0)
    group_output = nodes.new("NodeGroupOutput")
    group_output.location = (980, 0)

    mid_sum = nodes.new("ShaderNodeMath")
    mid_sum.name = "Arc1 Min + Max"
    mid_sum.operation = "ADD"
    mid_sum.location = (-720, 220)
    links.new(get_socket(group_input.outputs, "Padded Arc 1 V Min"), mid_sum.inputs[0])
    links.new(get_socket(group_input.outputs, "Padded Arc 1 V Max"), mid_sum.inputs[1])

    mid = nodes.new("ShaderNodeMath")
    mid.name = "Arc1 Midpoint"
    mid.operation = "MULTIPLY"
    mid.inputs[1].default_value = 0.5
    mid.location = (-460, 220)
    links.new(mid_sum.outputs["Value"], mid.inputs[0])

    span = nodes.new("ShaderNodeMath")
    span.name = "Arc1 Padded Span"
    span.operation = "SUBTRACT"
    span.location = (-720, 20)
    links.new(get_socket(group_input.outputs, "Padded Arc 1 V Max"), span.inputs[0])
    links.new(get_socket(group_input.outputs, "Padded Arc 1 V Min"), span.inputs[1])

    centered = nodes.new("ShaderNodeMath")
    centered.name = "V Around - 0.5"
    centered.operation = "SUBTRACT"
    centered.inputs[1].default_value = 0.5
    centered.location = (-720, -180)
    links.new(get_socket(group_input.outputs, "V Around"), centered.inputs[0])

    delta = nodes.new("ShaderNodeMath")
    delta.name = "Centered V * Span"
    delta.operation = "MULTIPLY"
    delta.location = (-180, -80)
    links.new(centered.outputs["Value"], delta.inputs[0])
    links.new(span.outputs["Value"], delta.inputs[1])

    matched = nodes.new("ShaderNodeMath")
    matched.name = "Matched Arc2 V"
    matched.operation = "ADD"
    matched.location = (120, 100)
    links.new(mid.outputs["Value"], matched.inputs[0])
    links.new(delta.outputs["Value"], matched.inputs[1])

    switch = nodes.new("GeometryNodeSwitch")
    switch.name = "Use Matched Or Piecewise"
    switch.input_type = "FLOAT"
    switch.location = (520, 0)
    links.new(get_socket(group_input.outputs, "Match Enabled"), switch.inputs["Switch"])
    links.new(get_socket(group_input.outputs, "Piecewise Arc 2 V"), switch.inputs["False"])
    links.new(matched.outputs["Value"], switch.inputs["True"])

    links.new(switch.outputs["Output"], get_socket(group_output.inputs, "Arc 2 V"))
    return helper


def replace_padding(main_group, helper):
    nodes = main_group.nodes
    links = main_group.links
    min_sub = nodes.get("PW Band - Arc1 V Min Pad Subtract")
    min_padded = nodes.get("PW Band - Arc1 V Min Padded")
    max_add = nodes.get("PW Band - Arc1 V Max Pad Add")
    max_padded = nodes.get("PW Band - Arc1 V Max Padded")
    if None in {min_sub, min_padded, max_add, max_padded}:
        return 0

    min_dests = output_destinations(main_group, min_padded.outputs["Value"])
    max_dests = output_destinations(main_group, max_padded.outputs["Value"])
    sources = {
        "Arc 1 V Min": first_source(main_group, min_sub.inputs[0]),
        "Padding": first_source(main_group, min_sub.inputs[1]),
        "Arc 2 V Min": first_source(main_group, min_padded.inputs[1]),
        "Arc 1 V Max": first_source(main_group, max_add.inputs[0]),
        "Arc 2 V Max": first_source(main_group, max_padded.inputs[1]),
    }

    frame = nodes.get(VBAND_FRAME_NAME)
    group_node = nodes.new("GeometryNodeGroup")
    group_node.node_tree = helper
    group_node.name = "PW Clamp Arc 1 V Band Inside Arc 2"
    group_node.label = "Clamp padded Arc 1 inside Arc 2"
    group_node.location = (1300, -180)
    if frame is not None:
        group_node.parent = frame

    for input_name, source_socket in sources.items():
        links.new(source_socket, get_socket(group_node.inputs, input_name))
    for to_socket in min_dests:
        links.new(get_socket(group_node.outputs, "Padded Arc 1 V Min"), to_socket)
    for to_socket in max_dests:
        links.new(get_socket(group_node.outputs, "Padded Arc 1 V Max"), to_socket)

    for node in [min_sub, min_padded, max_add, max_padded]:
        nodes.remove(node)
    return 4


def replace_match(main_group, helper):
    nodes = main_group.nodes
    links = main_group.links
    switch = nodes.get("PW MatchScale - Switch Arc2 V")
    if switch is None:
        return 0

    mid_sum = nodes.get("PW MatchScale - Mid Sum")
    centered = nodes.get("PW MatchScale - v_around - 0.5")
    if mid_sum is None or centered is None:
        return 0

    destinations = output_destinations(main_group, switch.outputs["Output"])
    sources = {
        "Match Enabled": first_source(main_group, switch.inputs["Switch"]),
        "Piecewise Arc 2 V": first_source(main_group, switch.inputs["False"]),
        "V Around": first_source(main_group, centered.inputs[0]),
        "Padded Arc 1 V Min": first_source(main_group, mid_sum.inputs[0]),
        "Padded Arc 1 V Max": first_source(main_group, mid_sum.inputs[1]),
    }

    frame = nodes.get(VBAND_FRAME_NAME)
    group_node = nodes.new("GeometryNodeGroup")
    group_node.node_tree = helper
    group_node.name = "PW Match Arc 2 V To Arc 1 Range"
    group_node.label = "Optional Arc 2 = Arc 1 V range"
    group_node.location = (1940, -180)
    if frame is not None:
        group_node.parent = frame

    for input_name, source_socket in sources.items():
        links.new(source_socket, get_socket(group_node.inputs, input_name))
    for to_socket in destinations:
        links.new(get_socket(group_node.outputs, "Arc 2 V"), to_socket)

    remove_names = [
        "PW MatchScale - GI",
        "PW MatchScale - Mid Sum",
        "PW MatchScale - Mid",
        "PW MatchScale - Padded Core Span",
        "PW MatchScale - Matched Span",
        "PW MatchScale - v_around - 0.5",
        "PW MatchScale - Delta",
        "PW MatchScale - Matched Arc2 V",
        "PW MatchScale - Switch Arc2 V",
    ]
    removed = 0
    for name in remove_names:
        node = nodes.get(name)
        if node is not None:
            nodes.remove(node)
            removed += 1
    return removed


def main():
    main_group = bpy.data.node_groups.get(NODE_GROUP_NAME)
    if main_group is None:
        raise SystemExit(f"Node group not found: {NODE_GROUP_NAME}")

    padding_group = ensure_padding_group()
    match_group = ensure_match_group()
    removed = replace_padding(main_group, padding_group)
    removed += replace_match(main_group, match_group)

    filepath = bpy.data.filepath
    if not filepath:
        raise SystemExit("Loaded blend has no filepath; refusing to save.")
    bpy.ops.wm.save_as_mainfile(filepath=str(Path(filepath)))
    print("V-band helper grouping complete")
    print(f"  Helper group: {PADDING_GROUP_NAME}")
    print(f"  Helper group: {MATCH_GROUP_NAME}")
    print(f"  Visible math/switch/input nodes removed: {removed}")


if __name__ == "__main__":
    main()
