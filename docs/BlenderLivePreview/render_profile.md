# Live Cycles Render Profile

The live preview is **Cycles**. Speed comes entirely from a profile applied on
top of the existing scene — never from a different engine. This file defines
that profile, the quality tiers, and the rules that keep it both fast and
faithful.

All numbers below are **proposed starting points** (`Status: proposed`). They
must be tuned against the real `.blend` on the target machine and the winners
recorded in [phase_log.md](phase_log.md).

## What makes Cycles fast enough for "live-ish"

Five levers, in rough order of impact:

1. **GPU compute (Metal on Apple Silicon).** Set the Cycles device to the GPU,
   not CPU. Single biggest win.
   ```python
   prefs = bpy.context.preferences.addons['cycles'].preferences
   prefs.compute_device_type = 'METAL'        # or 'OPTIX'/'CUDA'/'HIP' on other hosts
   for d in prefs.devices: d.use = True
   scene.cycles.device = 'GPU'
   ```
2. **Persistent data.** Keep the dependency graph + BVH resident between frames
   so a tweak re-renders shading without rebuilding the whole scene.
   ```python
   scene.render.use_persistent_data = True
   ```
   This is the reason a *session* exists rather than one-shot renders: the first
   frame pays setup, every later frame is cheap. See
   [persistent data & the dirty matrix](#persistent-data--the-geometry-vs-shading-dirty-matrix).
3. **Adaptive sampling + denoise.** Render few samples, let adaptive sampling
   stop converged pixels early, and let the denoiser clean the rest. Low samples
   + a good denoiser reads as "clean" far cheaper than brute-force samples.
   ```python
   scene.cycles.use_adaptive_sampling = True
   scene.cycles.adaptive_threshold = 0.01
   scene.cycles.samples = 48              # tier-dependent ceiling
   scene.cycles.use_denoising = True
   scene.cycles.denoiser = 'OPENIMAGEDENOISE'   # or 'OPTIX' where available
   ```
4. **A time limit as a safety valve.** Cap wall-clock per frame so a heavy tweak
   degrades to "slightly noisier frame" instead of "30 s stall." The denoiser
   hides the early stop.
   ```python
   scene.cycles.time_limit = 6.0          # seconds, tier-dependent; 0 = unlimited
   ```
5. **Resolution.** The live tier renders smaller than the 3200 px full render.
   "High resolution" here means high *for a preview* (≈ 1280–1600 px), not
   render-final. `resolution_percentage` stays 100.

Optional, validate before adopting: `scene.render.use_simplify` with a modest
viewport subdivision cap for the live tier. The user wants high quality, so
**off by default**; revisit only if frames are too slow.

## Quality tiers (preset-selectable)

The user picks a tier by patience; the machine is fast, so default generously.

```text
tier      res(px)  samples  adaptive_thr  denoiser  time_limit(s)  ~JPEG q
--------  -------  -------  ------------  --------  -------------  -------
draft       960      24        0.02        OIDN          3           88
balanced*  1280      48        0.01        OIDN          6           90
crisp      1600      96        0.008       OIDN         12           92
```

`*` default. `crisp` is the closest honest preview of the 3200/96 full render;
`draft` is for fast structural checks (does the weave/spacing look right at
all). Tiers are data, not code — see
[presets.md](presets.md#render-quality-presets).

Full render stays **unchanged**: `CYCLES`, 3200 px, 96 samples, no time limit,
PNG output.

## Parity with the full render

The whole point is that the preview predicts the render. So the live path must
reuse the full render's:

- **Camera** — same `scene.camera` and framing. The preview is literally "what
  the camera sees."
- **World / HDRI lighting** — same world setup (`assets/hdrs`), same strength.
- **Materials** — the same generated FabricStudio materials and the same
  `bandMeta`→socket push (`APPLY_METADATA_PY`).
- **Color management** — same `scene.view_settings.view_transform`, look,
  exposure, and `scene.display_settings`. A mismatch here makes the preview lie
  about color.

Factor a shared `_pw_configure_render_scene(...)` out of the full-render script
so both paths set camera/world/color management identically and only the
**speed profile** (this file) and **film transparency** differ.

### Intentional, documented differences

| Aspect | Full render | Live preview | Why |
|---|---|---|---|
| Resolution | 3200 | 960–1600 | speed |
| Samples | 96 fixed | 24–96 adaptive | speed |
| Denoise | (render setting) | always on | hide low samples |
| Time limit | none | 3–12 s | bounded latency |
| Film transparency | may be transparent (for tiling/compositing) | **off** — show world bg | a transparent swatch is hard to read live; the lit background reads like a real swatch |
| Output | PNG (lossless, alpha) | JPEG (small, no alpha) | transport size on WAN |

Everything else matches. If a future need requires alpha in the preview (e.g.
to preview the tiling composite), add a PNG tier rather than making JPEG carry
alpha it cannot.

## Persistent data & the geometry-vs-shading dirty matrix

`use_persistent_data` caches the depsgraph and BVH. Blender re-evaluates only
the datablocks that changed, so it is **safe** across all our control changes —
but the *cost* of a frame depends on whether the change touched geometry
(forces a BVH refit/rebuild) or only shading/UV (cheap re-shade).

The exposed controls classify as:

```text
control                 socket(s)                  dirty class     frame cost
----------------------  -------------------------  --------------  ----------
Weave Zoom              Warp/Weft Threads          GEOMETRY(topo)  heaviest — topology changes
Spacing                 Spacing                    GEOMETRY        heavy — positions/scale
Pattern Noise X/Y       Pattern Noise X / Y        GEOMETRY        heavy — vertex displacement
Texture U Scatter       UV Random U                SHADING/UV      light — no topology
Arc 1 V Padding         Arc 1 V Padding            SHADING/UV      light — V-band mapping
yarn / bandMeta change  Material N * sockets        SHADING        light — re-shade only
```

Implications:

- **Light (shading/UV) tweaks are the sweet spot** for live — fast frames, exactly
  the kind of fine-tuning the user does in this mode.
- **Geometry tweaks (Weave Zoom, Spacing, Pattern Noise) cost more** because the
  BVH must refit. Still fine for "live-ish," but expect the first frame after a
  zoom change to be the slowest. The `time_limit` keeps it bounded.
- We do **not** need to manually invalidate persistent data; Blender handles
  dependency invalidation. The matrix is for *expectation-setting and tuning*
  (e.g. a heavier `time_limit` budget when a geometry socket changed), not for
  correctness. Verify the no-stale-BVH assumption in
  [risks_and_open_questions.md](risks_and_open_questions.md#r4-persistent-data-staleness).

## Kernel warm-up (the cold first frame)

The first Cycles render after Blender launches (or after a GPU device change)
**compiles GPU kernels** — several seconds, one time. Strategy:

- The **session-enter** call renders a **warm-up frame** so the cold cost is
  paid once, up front, while the user is still reading the panel — not on their
  first tweak.
- Surface it honestly in the UI: the enter step shows "warming up…" and reports
  `renderMs` for the first frame so the cold cost is visible, not mysterious.
- Subsequent frames in the same session are warm and hit the tier's expected
  cost.

## Environment overrides

So tuning needs no redeploy:

```text
BLENDER_LIVE_PREVIEW_TIMEOUT_SECONDS   socket timeout for a frame (default 120)
WEAVE_LIVE_PREVIEW_DEFAULT_TIER        draft|balanced|crisp (default balanced)
WEAVE_LIVE_PREVIEW_RES_<TIER>          override resolution per tier
WEAVE_LIVE_PREVIEW_SAMPLES_<TIER>      override sample ceiling per tier
WEAVE_LIVE_PREVIEW_TIMELIMIT_<TIER>    override seconds per tier
WEAVE_LIVE_PREVIEW_JPEG_QUALITY        transport JPEG quality (default 90)
WEAVE_LIVE_PREVIEW_DENOISER            OPENIMAGEDENOISE|OPTIX (host-dependent)
```

## Acceptance

- Live frames render in **Cycles** with the GPU device active (verify via MCP
  readback of `scene.cycles.device` and the enabled devices).
- `use_persistent_data` is `True` during a session and restored to its prior
  value on exit.
- A warm `balanced` frame on the target machine returns within roughly its
  `time_limit + transfer` budget (measure and record the real number).
- Camera, world, materials, and color management read identical between a live
  frame and a full render of the same draft (side-by-side visual check).
- Changing only a shading/UV control (Texture U Scatter, Arc 1 V Padding)
  produces a visibly faster frame than changing a geometry control (Weave Zoom).
