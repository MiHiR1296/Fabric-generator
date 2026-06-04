# Live Blender Source Of Truth

Snapshot date: 2026-06-04

Connection:

```text
Blender MCP host: 127.0.0.1
Blender MCP port: 9876
```

This document records the live `.blend` state that the PBR V1 plan depends on.
The live file is the geometry/material source of truth for Phase 0 and any
future graph work.

## Freshness Rules

Regenerate this document:

1. Whenever a PBR phase ships.
2. Before any geometry-node graph edit.
3. After any rebuild/save of `Codex_ParametricWeave.blend`.

Attach the git commit hash or working-tree note when a phase ships. If Blender
is dirty, record that explicitly.

## File State

```text
blend_path: /Users/mihirbotle/Desktop/Impetus/3D Fabric/yarnseamless UI/Fabric-generator-tryon/Codex_ParametricWeave.blend
bpy.data.is_dirty: true
scene: Scene
object_count: 7
materials_count: 19
```

The file is dirty at this snapshot. Do not treat the saved file as identical
to the open Blender session until it has been saved or re-read.

## Scene Settings

```text
render engine: CYCLES
resolution: 3200 x 3200
resolution percentage: 100
camera: Camera
cycles device: GPU
cycles samples: 96
cycles preview samples: 512
```

Objects:

| Object | Type | Hide Viewport | Hide Render |
|---|---|---:|---:|
| `Space` | MESH | false | true |
| `Sun` | LIGHT | false | true |
| `Camera` | CAMERA | false | false |
| `Empty` | EMPTY | false | false |
| `Area` | LIGHT | false | false |
| `ParametricWeave` | MESH | false | false |
| `WebDraft_Live` | MESH | true | true |

## Target Object

```text
target object: ParametricWeave
active material slot 1: FabricStudioMaterial_01_a83a49c70af0
```

Modifier stack:

| Modifier | Type | Node Group |
|---|---|---|
| `Weave` | NODES | `Parametric Weave knotty` |
| `Fit To Space` | NODES | `Fit Geometry To Space Plane` |

## Key Weave Inputs

These are the live socket values read from `ParametricWeave.modifiers["Weave"]`.

| Meaning | Socket | Value |
|---|---|---:|
| Warp Threads | `Socket_4` | `80` |
| Weft Threads | `Socket_5` | `80` |
| Spacing | `Socket_6` | `0.026000000536441803` |
| Amplitude | `Socket_8` | `0.00800000037997961` |
| Thread Subdivisions | `Socket_9` | `8.0` |
| Texture Scale V | `Socket_43` | `1.0` |
| Texture Offset V | `Socket_44` | `0.0` |
| Material 1 | `Socket_61` | `FabricStudioMaterial_01_a83a49c70af0` |
| Sub Strand Enable | `Socket_84` | `true` |
| Sub Texture Scale V | `Socket_87` | `1.0` |
| Sub Texture Offset V | `Socket_88` | `0.0` |
| Texture Scale U | `Socket_97` | `1.0` |
| Scanner Pixels Per BU | `Socket_98` | `62992.16015625` |
| Draft Object | `Socket_100` | `WebDraft_Live` |
| Draft Columns | `Socket_101` | `8` |
| Draft Rows | `Socket_102` | `8` |
| Material 1 Image Width Px | `Socket_103` | `47058.0` |
| Material 1 Texture Scale U | `Socket_104` | `0.07530806958675385` |
| Material 1 Arc 1 V Min | `Socket_105` | `0.47116968035697937` |
| Material 1 Arc 1 V Max | `Socket_106` | `0.53047776222229` |
| Material 1 Arc 2 V Max | `Socket_107` | `0.5551894307136536` |
| Material 1 Arc 2 V Min | `Socket_108` | `0.44645798206329346` |
| Arc 1 V Padding | `Socket_244` | `0.00800000037997961` |
| U Stride Per Warp End | `Socket_245` | `0.209680438041687` |
| U Stride Per Weft Pick | `Socket_246` | `0.209680438041687` |
| Arc 2 Boundary Inset | `Socket_247` | `0.0` |
| Arc 2 Match Arc 1 V Rate | `Socket_250` | `false` |

## Evaluated Mesh

```text
vertices: 4,300,800
polygons: 4,089,600
uv_layers: []
```

Important evaluated attributes:

| Attribute | Domain | Data Type |
|---|---|---|
| `u_along` | POINT | FLOAT |
| `uv_offset_u` | POINT | FLOAT |
| `uv_offset_v` | POINT | FLOAT |
| `material_id` | POINT | INT |
| `.pw_u_density_scale` | POINT | FLOAT |
| `pw_strand_id` | POINT | INT |
| `pw_profile_natural` | POINT | FLOAT |
| `pw_profile_actual` | POINT | FLOAT |
| `v_around` | POINT | FLOAT |
| `is_sub_strand` | POINT | FLOAT |
| `material_index` | FACE | INT |
| `arc1_radius_geometry` | POINT | FLOAT |
| `arc2_radius_geometry` | POINT | FLOAT |
| `arc2_core_frac_raw` | POINT | FLOAT |
| `arc2_core_frac_geometry` | POINT | FLOAT |
| `arc2_core_split_min` | POINT | FLOAT |
| `arc2_core_split_max` | POINT | FLOAT |
| `pw_section_ratio` | POINT | FLOAT |
| `pw_section_slope` | POINT | FLOAT |
| `uv_scaled` | POINT | FLOAT2 |

PBR consequence:

```text
uv_scaled is POINT-domain FLOAT2.
There are no evaluated UV layers.
```

This is why PBR V1 uses object-space normals. Tangent-space normal maps would
require a real corner-domain UV layer or a graph conversion path, both of
which would touch the load-bearing `Parametric Weave knotty` graph.

## Active Material

```text
material: FabricStudioMaterial_01_8f6b8d8f9a4b
users: 2
fake user: false
asset id: 8f6b8d8f9a4b
texture source: RGBA UDIM diffuse plus separate Non-Color alpha image
```

Active material nodes relevant to texture sampling:

| Node | Type | Image | Colorspace | Source | Interpolation |
|---|---|---|---|---|---|
| `FabricStudioDiffuseNode` | `ShaderNodeTexImage` | `FabricStudioMaterial_01_8f6b8d8f9a4b_RGBA_UDIM` | sRGB | TILED | Linear |
| `FabricStudioAlphaNode` | `ShaderNodeTexImage` | `FabricStudioMaterial_01_8f6b8d8f9a4b_RGBA_Alpha_UDIM` | Non-Color | TILED | Linear |
| `Attribute` | `ShaderNodeAttribute` | reads `uv_scaled` | n/a | n/a | n/a |

UDIM image filepath:

```text
/Users/mihirbotle/Desktop/Impetus/3D Fabric/yarnseamless UI/Fabric-generator-tryon/runtime/yarn_assets/8f6b8d8f9a4b/cycles_tiled/rgba_<UDIM>.png
tiles: 1001, 1002, 1003
```

Active V1 PBR nodes:

| Node | Type | Source / Setting | Value |
|---|---|---|---|
| `FabricStudioNormalHeightNode` | `ShaderNodeTexImage` | Non-Color UDIM | `pbr/cycles_tiled/normal_height_<UDIM>.png` |
| `FabricStudioRoughnessSpecularNode` | `ShaderNodeTexImage` | Non-Color UDIM | `pbr/cycles_tiled/roughness_specular_<UDIM>.png` |
| `FabricStudioObjectNormalMap` | `ShaderNodeNormalMap` | Space | `OBJECT` |
| `FabricStudioObjectNormalMap` | `ShaderNodeNormalMap` | Strength | `0.1` |
| `FabricStudioHeightBump` | `ShaderNodeBump` | Strength | `1.0` |
| `FabricStudioHeightBump` | `ShaderNodeBump` | Distance | `0.0008` |
| `FabricStudioRoughnessSpecularSplit` | `ShaderNodeSeparateColor` | Channel split | roughness R, Specular IOR Level G |

## FabricStudio Materials In Memory

Live generated materials currently visible through MCP:

| Material | Users | Fake User | Notes |
|---|---:|---:|---|
| `FabricStudioMaterial_01_8f6b8d8f9a4b` | 2 | false | active slot material |
| `FabricStudioMaterial_01_e59d738c7c1f` | 1 | true | protected by fake user |

The material count for the whole file can include non-FabricStudio materials;
only generated FabricStudio materials matching the strict cleanup predicates are
eligible for pruning.

## FabricStudio Images In Memory

The session contains RGBA UDIM image datablocks for several old yarn ids:

```text
059e1c0937b5
08a7db9d6113
220144350b31
5549cf319649
a83a49c70af0
e59d738c7c1f
e7279c9b6309
651bcea04ba7
d866f49b8b2d
e747faaeb7a6
```

Some image datablocks have zero users and point to stale runtime asset ids.
The V1 cleanup pass may remove zero-user generated FabricStudio images only
after material cleanup and only when they are not referenced by protected
preview-active state.

## Interpolation Baseline

Backend generated render scripts default to:

```text
WEAVE_TEXTURE_INTERPOLATION=Linear
```

The active live material currently reports:

```text
diffuse interpolation: Cubic
alpha interpolation: Linear
```

Do not change the backend default based on this mismatch alone. Phase 0 must
render `Linear` and `Cubic` A/Bs on a baked-PBR asset and record the winner
here.

## Phase 0 PBR Acceptance Target

Active asset:

```text
a83a49c70af0
```

Required check:

```text
Bake pbr/normal_height.png for a83a49c70af0.
Normal RGB should be mostly purple/blue.
Red/green modulation should appear in the dense fiber band.
Strong red/green alpha-edge bands mean the vertical edge-extend fill failed.
```

Only after this visual check should Phase 1 rely on the object-space normal
bake as the default generator output.

## 2026-06-04 Diffuse Map Decision

Asset `8f6b8d8f9a4b` exposed a diffuse-specific issue:

```text
FabricStudioMaterial_01_8f6b8d8f9a4b_RGBA_UDIM
  filepath: runtime/yarn_assets/8f6b8d8f9a4b/cycles_tiled/rgba_<UDIM>.png
  tiles: 1001, 1002, 1003
  source size per tile: 15686 x 607
```

The RGBA UDIM tiles were pixel-identical to crops of `rgba.png` (`maxdiff = 0`),
so the disk image was not downscaled or corrupted. The later experimental
`pbr/base_color.png` branch made color look noisy and is no longer part of the
pipeline.

Current correction:

```text
generator_version: yarn_pbr_v1.3
Base Color source: runtime/yarn_assets/<id>/cycles_tiled/rgba_<UDIM>.png
Alpha source: raw RGBA alpha directly into Principled BSDF.Alpha
No FabricStudioAlphaRemap node is generated.
No pbr/base_color.png or pbr/cycles_tiled/base_color_<UDIM>.png is generated.
```

The open Blender session was patched so:

```text
FabricStudioMaterial_01_8f6b8d8f9a4b/FabricStudioDiffuseNode
  image: FabricStudioMaterial_01_8f6b8d8f9a4b_RGBA_UDIM
  filepath: runtime/yarn_assets/8f6b8d8f9a4b/cycles_tiled/rgba_<UDIM>.png
  colorspace: sRGB
  interpolation: Linear

FabricStudioAlphaNode Alpha
  -> Principled BSDF.Alpha
```
