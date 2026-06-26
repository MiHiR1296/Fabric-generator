# Procedural Hook Rebuild

Fresh start date: 2026-06-18.

This folder is the source of truth for bringing `Procedural Hook` up to the
same product-contract level as `Parametric Weave knotty.001` while keeping the
weave renderer untouched.

## Goal

Build hook rendering as a separate fabric mode:

- target object: `ProceduralHook`
- geometry-node modifier: `Hook`
- geometry-node group: `Procedural Hook`
- hidden pattern source: `HookDraft_Live`

The Pre-V2 hook graph is a visual calibration reference, not the production
system. V2 uses a backend-generated hook mesh as the live bridge: the backend
interprets frontend pattern intent, writes `HookDraft_Live`, generates visible
hook yarn geometry on `ProceduralHook`, and the `Procedural Hook` node group
keeps the modifier/material contract stable.

For the current live shape investigation, read
[../../../docs/ProceduralHookShapeWorkbench/](../../../docs/ProceduralHookShapeWorkbench/).
That folder documents the freshly reingested Pre-V2 Geometry Nodes setup as a
shape workbench before it is adapted into the production hook/knit pipeline.
