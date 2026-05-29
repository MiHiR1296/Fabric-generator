"""Restore the Arc1 mesh path required by same-strand Arc2 U sampling.

The same-strand transfer node needs an Arc1-only mesh in its Sample Nearest
Surface `Mesh` input. Older working sessions intended this path to be:

    Arc1 profile -> Curve to Mesh -> Store is_sub_strand=0
        -> final Join Geometry
        -> PW StrandXferU - Sample Same-Strand Arc1 U.Mesh

This script recreates that path without undoing the graph cleanup/helper groups.
"""

from __future__ import annotations

from pathlib import Path

import bpy


NODE_GROUP_NAME = "Parametric Weave knotty"
PROFILE_FRAME_NAME = "PW Layout - Profile / Mesh"


def get_socket(sockets, name):
    socket = sockets.get(name)
    if socket is None:
        raise KeyError(name)
    return socket


def link_once(group, from_socket, to_socket):
    for link in group.links:
        if link.from_socket == from_socket and link.to_socket == to_socket:
            return False
    group.links.new(from_socket, to_socket)
    return True


def remove_links_to(group, to_socket):
    for link in list(group.links):
        if link.to_socket == to_socket:
            group.links.remove(link)


def ensure_node(group, name, bl_idname, label="", parent=None, location=(0, 0)):
    node = group.nodes.get(name)
    if node is None:
        node = group.nodes.new(bl_idname)
        node.name = name
    node.label = label
    node.parent = parent
    node.location = location
    return node


def main():
    group = bpy.data.node_groups.get(NODE_GROUP_NAME)
    if group is None:
        raise SystemExit(f"Node group not found: {NODE_GROUP_NAME}")

    nodes = group.nodes
    frame = nodes.get(PROFILE_FRAME_NAME)

    all_curves = nodes.get("PW All Curves Join")
    arc1_radius = nodes.get("PW Band - Geo Arc1 Radius Value")
    join_geometry = nodes.get("Join Geometry.001")
    sampler = nodes.get("PW StrandXferU - Sample Same-Strand Arc1 U")
    if None in {all_curves, arc1_radius, join_geometry, sampler}:
        missing = [
            name
            for name, node in {
                "PW All Curves Join": all_curves,
                "PW Band - Geo Arc1 Radius Value": arc1_radius,
                "Join Geometry.001": join_geometry,
                "PW StrandXferU - Sample Same-Strand Arc1 U": sampler,
            }.items()
            if node is None
        ]
        raise RuntimeError(f"Missing required nodes: {missing}")

    arc = ensure_node(
        group,
        "PW Arc1 Sample Profile",
        "GeometryNodeCurveArc",
        "Arc1 profile for same-strand U sampling",
        frame,
        (90, -520),
    )
    arc.inputs["Resolution"].default_value = 11
    arc.inputs["Radius"].default_value = 0.014999999664723873
    arc.inputs["Start Angle"].default_value = -0.5235987901687622
    arc.inputs["Sweep Angle"].default_value = -2.090904474258423
    if "Offset Angle" in arc.inputs:
        arc.inputs["Offset Angle"].default_value = 0.0
    if "Connect Center" in arc.inputs:
        arc.inputs["Connect Center"].default_value = False
    if "Invert Arc" in arc.inputs:
        arc.inputs["Invert Arc"].default_value = False
    remove_links_to(group, arc.inputs["Radius"])
    link_once(group, get_socket(arc1_radius.outputs, "Value"), arc.inputs["Radius"])

    spline = ensure_node(
        group,
        "PW Arc1 Sample Profile Factor",
        "GeometryNodeSplineParameter",
        "Arc1 profile v_around factor",
        frame,
        (90, -740),
    )

    store_v = ensure_node(
        group,
        "PW Arc1 Sample Store v_around",
        "GeometryNodeStoreNamedAttribute",
        "Arc1 sample v_around",
        frame,
        (330, -520),
    )
    store_v.data_type = "FLOAT"
    store_v.domain = "POINT"
    store_v.inputs["Name"].default_value = "v_around"
    remove_links_to(group, store_v.inputs["Geometry"])
    remove_links_to(group, store_v.inputs["Value"])
    link_once(group, get_socket(arc.outputs, "Curve"), store_v.inputs["Geometry"])
    link_once(group, get_socket(spline.outputs, "Factor"), store_v.inputs["Value"])

    curve_to_mesh = ensure_node(
        group,
        "PW Arc1 Sample Curve To Mesh",
        "GeometryNodeCurveToMesh",
        "Arc1 sample surface",
        frame,
        (590, -520),
    )
    curve_to_mesh.inputs["Scale"].default_value = 1.0
    curve_to_mesh.inputs["Fill Caps"].default_value = False
    remove_links_to(group, curve_to_mesh.inputs["Curve"])
    remove_links_to(group, curve_to_mesh.inputs["Profile Curve"])
    link_once(group, get_socket(all_curves.outputs, "Geometry"), curve_to_mesh.inputs["Curve"])
    link_once(group, get_socket(store_v.outputs, "Geometry"), curve_to_mesh.inputs["Profile Curve"])

    tag_main = ensure_node(
        group,
        "PW Arc1 Sample Tag Main",
        "GeometryNodeStoreNamedAttribute",
        "Tag Arc1 sample mesh as main",
        frame,
        (850, -520),
    )
    tag_main.data_type = "FLOAT"
    tag_main.domain = "POINT"
    tag_main.inputs["Name"].default_value = "is_sub_strand"
    tag_main.inputs["Value"].default_value = 0.0
    remove_links_to(group, tag_main.inputs["Geometry"])
    link_once(group, get_socket(curve_to_mesh.outputs, "Mesh"), tag_main.inputs["Geometry"])

    linked_join = link_once(group, get_socket(tag_main.outputs, "Geometry"), join_geometry.inputs["Geometry"])

    remove_links_to(group, sampler.inputs["Mesh"])
    linked_sampler = link_once(group, get_socket(tag_main.outputs, "Geometry"), sampler.inputs["Mesh"])

    filepath = bpy.data.filepath
    if not filepath:
        raise SystemExit("Loaded blend has no filepath; refusing to save.")
    bpy.ops.wm.save_as_mainfile(filepath=str(Path(filepath)))
    print("Arc1 sampling path restored")
    print(f"  Joined Arc1 sample mesh into Join Geometry.001: {linked_join}")
    print(f"  Connected Arc1 sample mesh to same-strand sampler: {linked_sampler}")


if __name__ == "__main__":
    main()
