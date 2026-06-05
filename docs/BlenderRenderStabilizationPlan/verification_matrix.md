# Verification Matrix

Run these checks after every stabilization phase that touches Blender, material
generation, or socket metadata.

## Unit Tests

```bash
cd Fabric-generator-tryon
python3 -m unittest backend.tests.test_render_jobs backend.tests.test_blender_live backend.tests.test_blender_sync
python3 -m unittest backend.tests.test_yarn_pbr
```

Expected:

```text
render_jobs: RGBA materials use diffuse alpha directly by default; alpha remap stays opt-in
blender_live: Texture Scale U is pinned with the V footgun sockets
blender_sync: full project setup keeps root Texture Scale U = 1.0
yarn_pbr: stale/missing PBR still fails preflight
```

## Static Checks

```bash
python3 -m py_compile backend/app/render_jobs.py backend/app/blender_live.py backend/app/blender_sync.py
git diff --check -- backend/app/render_jobs.py backend/app/blender_live.py backend/tests/test_render_jobs.py backend/tests/test_blender_live.py docs
```

Expected:

```text
No syntax errors.
No trailing whitespace.
```

## Live Blender Readback

Use MCP or the backend health route:

```text
host: 127.0.0.1
port: 9876
object: ParametricWeave
modifier: Weave
node group: Parametric Weave knotty
```

Expected sockets:

```text
Texture Scale U      = 1.0
Texture Scale V      = 1.0
Texture Offset V     = 0.0
Sub Texture Scale V  = 1.0
Sub Texture Offset V = 0.0
Sub Strand Enable    = True
Arc 1 V Padding      = 0.02
```

Expected Arc 2 U graph:

```text
PW StrandXferU - Use Same-Strand Arc1 U On Arc2.True <- PW UV U Add.Value
PW StrandXferU - Sample Same-Strand Arc1 U.mute = true
```

Expected Arc 2 V graph:

```text
PW Band - Arc2 Top.To Min <- PW HaloFlow - Top Outer Free V
PW Band - Arc2 Bot.To Max <- PW HaloFlow - Bot Outer Free V
Math.015 input 1 <- PW Input - Texture UV Output.Sub Texture Scale V
Math.015 input 2 <- PW Input - Texture UV Output.Texture Scale V
```

Expected evaluated `uv_scaled.y` for the current Material 1 diagnostic asset:

```text
Arc 1 = 0.4631696939468384..0.5384777784347534
Arc 2 = 0.40280061960220337..0.6004942655563354
```

## Alpha / Remap A/B

Default generated setup:

```text
_PW_ALPHA_REMAP_ENABLED = False
_PW_ALPHA_REMAP_LOW = 0.1
_PW_ALPHA_REMAP_HIGH = 0.78
_PW_ALPHA_CURVE_GAMMA = 1.0
```

Expected live material after `push-project-bandmeta` or render setup:

```text
RGBA path:  FabricStudioDiffuseNode.Alpha -> Principled BSDF.Alpha
Split path: FabricStudioAlphaNode.Color -> Principled BSDF.Alpha
No default FabricStudioAlphaRemap link.
```

Opt-in remap check:

```bash
WEAVE_ALPHA_REMAP_ENABLED=1 make backend-dev-live
```

Expected generated setup behavior:

```text
Selected alpha output -> FabricStudioAlphaRemap -> Principled BSDF.Alpha
FabricStudioAlphaCurve absent when gamma = 1.0
```

## Geometry Quality Future Check

Before implementing `Profile V Steps`, capture baseline:

```text
Thread Subdivisions = 8
PW Profile - Mesh Line Count = 31
PW Profile - Mesh Line Offset = 1/30
```

After implementing `Profile V Steps = 61`:

```text
unique v_around samples = 61
profile factor domain = 0..1
mesh count increase is recorded
```

## Texture World Width Future Check

Current live equivalent:

```text
image_width_px = 47058
scanner_pixels_per_bu = 62992.16015625
texture_world_width_bu = 0.74704534
```

Expected when `Texture World Width BU` is added:

```text
direct socket value equals image_width_px / scanner_pixels_per_bu within float tolerance
U Stride Per Warp End unchanged
U Stride Per Weft Pick unchanged
```

## Render Scenarios

Verify these before calling a phase complete:

| Scenario | Expected path |
| --- | --- |
| Wide RGBA yarn | RGBA UDIM, no atlas, PBR UDIM if baked |
| Small RGBA yarn | RGBA single, no atlas |
| Split RGB/alpha legacy yarn | split direct or split UDIM |
| Missing/stale PBR | HTTP `409` preflight |
| More than 16 yarns | atlas fallback logged and visible |
