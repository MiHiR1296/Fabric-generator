"""Clean the saved Parametric Weave geometry-node graph.

Run with Blender:

    blender -b Codex_ParametricWeave.blend --python scripts/cleanup_parametric_weave_nodes.py

The script removes modifier sockets whose downstream links are unreachable,
deletes functional nodes that cannot reach the Group Output, fixes the Geometry
input ordering warning, and re-parents active nodes into readable frames.
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

import bpy


NODE_GROUP_NAME = "Parametric Weave knotty"


def _material_socket_names() -> set[str]:
    names: set[str] = set()
    for index in range(1, 17):
        names.add(f"Material {index} Top Halo Frac")
        names.add(f"Material {index} Bot Halo Frac")
    return names


def _cycle_socket_names() -> set[str]:
    names: set[str] = set()
    for prefix in ("Warp", "Weft"):
        names.add(f"{prefix} Offset")
        for index in range(1, 5):
            names.add(f"{prefix} Length {index}")
            names.add(f"{prefix} Material {index}")
    return names


DEPRECATED_INPUT_SOCKETS = {
    "Over Count",
    "Under Count",
    "Main Strand Radius",
    "Sub Strand Width",
    "Sub Strand Height",
    "Texture Side Flatten",
    "Match Section Slopes",
    "Arc 2 Edge Angle Mapping",
    *_material_socket_names(),
    *_cycle_socket_names(),
}

DEPRECATED_PANELS = {
    "Warp Material Cycle",
    "Weft Material Cycle",
}

FRAME_SPECS = {
    "PW Layout - Inputs / Live Data": {
        "label": "Inputs / Live Data",
        "location": (-4600, 1100),
        "color": (0.23, 0.28, 0.34),
    },
    "PW Layout - Draft Sampling": {
        "label": "Draft Sampling",
        "location": (-3400, 1100),
        "color": (0.18, 0.34, 0.34),
    },
    "PW Layout - Strand Generation / Drawdown": {
        "label": "Strand Generation / Drawdown",
        "location": (-2200, 1100),
        "color": (0.26, 0.30, 0.20),
    },
    "PW Layout - Profile / Mesh": {
        "label": "Profile / Mesh",
        "location": (-900, 1100),
        "color": (0.32, 0.25, 0.19),
    },
    "PW Layout - Texture Coordinates": {
        "label": "Texture Coordinates",
        "location": (450, 1100),
        "color": (0.20, 0.28, 0.38),
    },
    "PW Layout - Texture U/V Output": {
        "label": "Texture U/V Output",
        "location": (450, -1150),
        "color": (0.18, 0.25, 0.34),
    },
    "PW Layout - V Band Mapping": {
        "label": "Arc 1 / Arc 2 V Band Mapping",
        "location": (1800, 1100),
        "color": (0.30, 0.21, 0.32),
    },
    "PW Layout - Same-Strand U Transfer": {
        "label": "Same-Strand U Transfer",
        "location": (3150, 1100),
        "color": (0.23, 0.32, 0.23),
    },
    "PW Layout - Material Assignment": {
        "label": "Material Assignment",
        "location": (4500, 1100),
        "color": (0.31, 0.28, 0.18),
    },
    "PW Layout - Loose Strands": {
        "label": "Loose Strands",
        "location": (-2200, -1150),
        "color": (0.30, 0.22, 0.18),
    },
    "PW Layout - Assembly": {
        "label": "Assembly",
        "location": (3150, -1150),
        "color": (0.21, 0.26, 0.34),
    },
    "PW Layout - Output": {
        "label": "Output",
        "location": (4500, -1150),
        "color": (0.28, 0.28, 0.28),
    },
}

OLD_FRAME_RENAMES = {
    "PW Layout - Pattern": "PW Layout - Strand Generation / Drawdown",
    "PW Layout - Texture UV Output": "PW Layout - Texture U/V Output",
    "PW Layout - Material Slots": "PW Layout - Material Assignment",
}


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


def reachable_nodes(node_group):
    reverse_links = defaultdict(list)
    for link in node_group.links:
        reverse_links[link.to_node].append(link.from_node)

    outputs = [node for node in node_group.nodes if node.bl_idname == "NodeGroupOutput"]
    seen = set()
    stack = list(outputs)
    while stack:
        node = stack.pop()
        if node in seen:
            continue
        seen.add(node)
        stack.extend(reverse_links.get(node, ()))
    return seen


def remove_deprecated_interface_items(node_group):
    removed = []
    identifiers = []
    for item in list(node_group.interface.items_tree):
        if (
            getattr(item, "item_type", None) == "SOCKET"
            and getattr(item, "in_out", None) == "INPUT"
            and item.name in DEPRECATED_INPUT_SOCKETS
        ):
            removed.append(item.name)
            identifiers.append(item.identifier)
            node_group.interface.remove(item)

    for item in list(node_group.interface.items_tree):
        if getattr(item, "item_type", None) == "PANEL" and item.name in DEPRECATED_PANELS:
            panel_name = item.name
            node_group.interface.remove(item)
            removed.append(f"panel:{panel_name}")

    for obj in bpy.data.objects:
        for modifier in obj.modifiers:
            if getattr(modifier, "node_group", None) != node_group:
                continue
            for identifier in identifiers:
                if identifier in modifier:
                    del modifier[identifier]

    return removed


def move_geometry_input_first(node_group):
    geometry_inputs = [
        item
        for item in node_group.interface.items_tree
        if (
            getattr(item, "item_type", None) == "SOCKET"
            and getattr(item, "in_out", None) == "INPUT"
            and item.name == "Geometry"
        )
    ]
    if not geometry_inputs:
        return False
    node_group.interface.move(geometry_inputs[0], 1)
    return True


def delete_unreachable_functional_nodes(node_group):
    removed = []
    while True:
        reachable = reachable_nodes(node_group)
        dead = [
            node
            for node in node_group.nodes
            if node.bl_idname != "NodeFrame" and node not in reachable
        ]
        if not dead:
            break
        for node in dead:
            removed.append(node.name)
            node_group.nodes.remove(node)
    return removed


def ensure_frames(node_group):
    for frame in [node for node in node_group.nodes if node.bl_idname == "NodeFrame"]:
        target_name = OLD_FRAME_RENAMES.get(frame.name)
        if target_name:
            frame.name = target_name

    frames = {}
    for name, spec in FRAME_SPECS.items():
        frame = node_group.nodes.get(name)
        if frame is None:
            frame = node_group.nodes.new("NodeFrame")
            frame.name = name
        frame.label = spec["label"]
        frame.parent = None
        frame.location = spec["location"]
        frame.use_custom_color = True
        frame.color = spec["color"]
        frames[name] = frame
    return frames


def choose_frame(node):
    name = node.name
    label = node.label or ""
    text = f"{name} {label}"

    if node.bl_idname == "NodeGroupInput":
        if "Draft" in text:
            return "PW Layout - Draft Sampling"
        if "Material Metadata" in text or "Band" in text or "MatchScale" in text:
            return "PW Layout - V Band Mapping"
        if "Material Slots" in text:
            return "PW Layout - Material Assignment"
        if "Texture" in text:
            return "PW Layout - Texture Coordinates"
        if "Loose" in text:
            return "PW Layout - Loose Strands"
        return "PW Layout - Inputs / Live Data"

    if name.startswith("PW Draft") or name.startswith("Draft ") or name in {"PW Warp Material Id", "PW Weft Material Id"}:
        return "PW Layout - Draft Sampling"
    if (
        name.startswith("PW Band")
        or name.startswith("PW Material")
        or name.startswith("PW MatchScale")
        or name.startswith("PW U - Sec")
    ):
        return "PW Layout - V Band Mapping"
    if name.startswith("PW StrandXferU"):
        return "PW Layout - Same-Strand U Transfer"
    if (
        name.startswith("PW U -")
        or name.startswith("Texture ")
        or "UV" in name
        or "Spline Parameter" in name
    ):
        return "PW Layout - Texture Coordinates"
    if name.startswith("PW Profile") or "Profile" in text or "Curve" in name:
        return "PW Layout - Profile / Mesh"
    if name.startswith("PW Loose"):
        return "PW Layout - Loose Strands"
    if name.startswith("Set Material") or name.startswith("PW Set Material"):
        return "PW Layout - Material Assignment"
    if name.startswith("Join Geometry") or name.startswith("Realize Instances"):
        return "PW Layout - Assembly"
    if node.bl_idname == "NodeGroupOutput":
        return "PW Layout - Output"
    return None


def reparent_nodes(node_group, frames):
    changed = 0
    for node in list(node_group.nodes):
        if node.bl_idname == "NodeFrame":
            continue
        frame_name = choose_frame(node)
        if frame_name is None:
            continue
        frame = frames.get(frame_name)
        if frame is None or node.parent == frame:
            continue
        set_parent_preserve_location(node, frame)
        changed += 1
    return changed


def layout_frame_children(frames):
    for frame in frames.values():
        children = [node for node in bpy.context.blend_data.node_groups[NODE_GROUP_NAME].nodes if node.parent == frame]
        if not children:
            continue
        children.sort(key=lambda node: (absolute_location(node)[0], -absolute_location(node)[1], node.name))
        columns = max(1, min(5, (len(children) + 9) // 10))
        for index, node in enumerate(children):
            column = index % columns
            row = index // columns
            node.location = (90 + column * 280, -90 - row * 150)


def remove_empty_frames(node_group):
    removed = []
    for frame in list(node_group.nodes):
        if frame.bl_idname != "NodeFrame":
            continue
        if not any(node.parent == frame for node in node_group.nodes):
            removed.append(frame.name)
            node_group.nodes.remove(frame)
    return removed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    args = parser.parse_args(argv)

    node_group = bpy.data.node_groups.get(NODE_GROUP_NAME)
    if node_group is None:
        raise SystemExit(f"Node group not found: {NODE_GROUP_NAME}")

    initial_nodes = len(node_group.nodes)
    removed_sockets = remove_deprecated_interface_items(node_group)
    geometry_moved = move_geometry_input_first(node_group)
    removed_nodes = delete_unreachable_functional_nodes(node_group)
    frames = ensure_frames(node_group)
    reparented = reparent_nodes(node_group, frames)
    layout_frame_children(frames)
    removed_frames = remove_empty_frames(node_group)

    final_nodes = len(node_group.nodes)
    print("Parametric weave cleanup")
    print(f"  Initial nodes: {initial_nodes}")
    print(f"  Final nodes:   {final_nodes}")
    print(f"  Removed interface items: {len(removed_sockets)}")
    print(f"  Removed functional nodes: {len(removed_nodes)}")
    print(f"  Removed empty frames: {len(removed_frames)}")
    print(f"  Reparented active nodes: {reparented}")
    print(f"  Geometry input moved first: {geometry_moved}")
    if removed_sockets:
        print("  Interface removed:")
        for name in removed_sockets:
            print(f"    - {name}")
    if removed_nodes:
        print("  Nodes removed:")
        for name in removed_nodes:
            print(f"    - {name}")

    if not args.dry_run:
        filepath = bpy.data.filepath
        if not filepath:
            raise SystemExit("Loaded blend has no filepath; refusing to save.")
        bpy.ops.wm.save_as_mainfile(filepath=str(Path(filepath)))


if __name__ == "__main__":
    main()
