# Current State

Snapshot date: 2026-06-05

Source: live Blender MCP on `127.0.0.1:9876`, plus current repository code.

## Live Blender Readback

```text
blend_path: /Users/mihirbotle/Desktop/Impetus/3D Fabric/yarnseamless UI/Fabric-generator-tryon/Codex_ParametricWeave.blend
blender_file_dirty: true
scene: Scene
object_count: 7
materials_count: 16
target object: ParametricWeave
modifier: Weave
node group: Parametric Weave knotty
```

Important sockets:

| Socket | Identifier | Live value |
| --- | --- | ---: |
| Texture Scale U | `Socket_97` | `1.0` |
| Texture Scale V | `Socket_43` | `1.0` |
| Texture Offset V | `Socket_44` | `0.0` |
| Sub Texture Scale V | `Socket_87` | `1.0` |
| Sub Texture Offset V | `Socket_88` | `0.0` |
| Sub Strand Enable | `Socket_84` | `True` |
| Thread Subdivisions | `Socket_9` | `8.0` |
| Arc 1 V Padding | `Socket_244` | `0.019999999552965164` |
| U Stride Per Warp End | `Socket_245` | `0.209680438041687` |
| U Stride Per Weft Pick | `Socket_246` | `0.209680438041687` |
| Material 1 Image Width Px | `Socket_103` | `47058.0` |
| Material 1 Texture Scale U | `Socket_104` | `0.07530806958675385` |
| Material 1 Arc 1 V Min | `Socket_105` | `0.47116968035697937` |
| Material 1 Arc 1 V Max | `Socket_106` | `0.53047776222229` |
| Material 1 Arc 2 V Min | `Socket_108` | `0.44645798206329346` |
| Material 1 Arc 2 V Max | `Socket_107` | `0.5551894307136536` |

Missing sockets:

```text
Texture World Width BU
Profile V Steps
```

## Arc 2 U Truth

The live graph uses deterministic same-strand U for Arc 2:

```text
PW StrandXferU - Use Same-Strand Arc1 U On Arc2
  Switch <- PW StrandXferU - Is Arc2.Result
  False  <- PW U - Per Section Multiplier.Value
  True   <- PW UV U Add.Value
  label  = Arc2 deterministic same-strand U (nearest-surface removed)
```

The old nearest-surface transfer is muted:

```text
PW StrandXferU - Sample Same-Strand Arc1 U
  mute  = true
  label = UNUSED - nearest-surface Arc2 U caused endpoint shrink
```

This means Arc 2 is not using the rejected independent own-U bypass. It remains
in the same yarn U stream as Arc 1 while avoiding nearest-surface plateaus and
endpoint shrink.

## Arc 2 V Truth

The live graph is back on the approved free-flow Arc 2 halo path after the
user rejected the exact metadata endpoint-fit attempt and pressed Cmd+Z:

```text
PW Band - Arc2 Top.To Min <- PW HaloFlow - Top Outer Free V
PW Band - Arc2 Bot.To Max <- PW HaloFlow - Bot Outer Free V
Math.015 input 1 <- PW Input - Texture UV Output.Sub Texture Scale V
Math.015 input 2 <- PW Input - Texture UV Output.Texture Scale V
Math.015 label = Scale V + Sub*is_sub
```

Pinned socket values remain:

```text
Texture Scale V = 1.0
Sub Texture Scale V = 1.0
Texture Offset V = 0.0
Sub Texture Offset V = 0.0
```

Live evaluated `uv_scaled.y` after undo:

```text
Arc 1 = 0.4631696939468384..0.5384777784347534
Arc 2 = 0.40280061960220337..0.6004942655563354
```

The measured Material 1 Arc 2 metadata silhouette remains:

```text
Material 1 Arc 2 V Min = 0.44645798206329346
Material 1 Arc 2 V Max = 0.5551894307136536
```

The mismatch is intentionally retained for now because exact endpoint-fit
sampling damaged the Arc 2 look and feel.

## Material Truth

Active generated material:

```text
FabricStudioMaterial_01_8f6b8d8f9a4b
```

Current user-verified material state after the 2026-06-05 Blender edit:

```text
PBR nodes present: true
FabricStudioAlphaRemap present: stale/orphan only, not linked to shader alpha
FabricStudioAlphaCurve present: false
Alpha link: FabricStudioDiffuseNode.Alpha -> Principled BSDF.Alpha
```

The earlier Phase 1 alpha-remap experiment is now superseded for RGBA yarn
materials. Current generated code keeps `_PW_ALPHA_REMAP_ENABLED = False` by
default and does not create a separate `RGBA_Alpha` image node on the RGBA path.
Set `WEAVE_ALPHA_REMAP_ENABLED=1` only for an explicit A/B or artist override.

After the rejected Phase 4 A/B and Cmd+Z, the open Blender session reports
`bpy.data.is_dirty = true` because the live setup/material refresh and undo
history touched the session. The `.blend` was not saved as part of this pass.

## Repository State At Start

Existing user/generated state at the start of the pass:

```text
 M Codex_ParametricWeave.blend
?? Codex_ParametricWeave.flat-arc1-rebuild.blend
?? PROJECT_REVIEW_REVISION_2.html
?? blender-method-deep-learning.html
?? runtime/texture_resolution_* review folders
```

This pass must not revert or overwrite those artifacts. Git already sees the
saved blend as modified from the repository baseline, and the open Blender
session has unsaved state from live diagnostics/undo history.
