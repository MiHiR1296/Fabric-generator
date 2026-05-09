# 04 — GN Architecture

How the band-V remap and the procedural Scale U math are wired into the `Parametric Weave knotty` node group. Useful when something goes wrong in the viewport and you need to know which subgraph to inspect.

The graph has 231 nodes total. We added 29 of them, all prefixed `PW Band - …`, `PW U - …`, or `PW UV …`. Everything else is the original strand-builder.

## V-band remap — Arc 1 / Arc 2 piecewise

### Inputs

The yarn-image inputs come into a second Group Input node (`PW Input - Image Bands`) attached at the band subgraph. It exposes the four band sockets plus `Main Strand Radius` so all the band math has a tidy local fan-out point.

### Arc 1 (the wide outer arc)

A single Map Range node — `PW Band - Arc1 Map`:

```
input  = v_around (Spline Parameter.001 along Arc 1)        [0, 1]
from   = [0, 1]
to     = [Image Core V Min, Image Core V Max]
output -> PW Band - Band V (the final V) and PW Band - Diff
```

Arc 1's full sweep is mapped linearly to the **core** band of the image.

### Arc 2 (the three-segment piecewise remap)

Arc 2 is wider than Arc 1 by `Sub Strand Width` (when `Sub Strand Enable` is on). To keep print-density constant across both arcs, Arc 2's V parameter is split at:

```
r        = Main Strand Radius / (Main Strand Radius + Sub Strand Width)
split-   = (1 - r) / 2     <- PW Band - Split Minus
split+   = (1 + r) / 2     <- PW Band - Split Plus
```

The Arc 2 V range `[0, 1]` is divided into three segments:

| Arc 2 V range | Maps to image V band | Map Range node |
|---|---|---|
| `[0, split-]` | `[Image Fiber Top V Min, Image Core V Min]` | `PW Band - Arc2 Top` |
| `[split-, split+]` | `[Image Core V Min, Image Core V Max]` | `PW Band - Arc2 Core` |
| `[split+, 1]` | `[Image Core V Max, Image Fiber Bot V Max]` | `PW Band - Arc2 Bot` |

The "Top" / "Bot" naming reflects Arc 2's parameter direction, NOT the geometric position; see the swap note in [03_Blender_Modifier_Reference.md](03_Blender_Modifier_Reference.md).

### Selecting which segment is active

A Map Range node always outputs a value even when its input is outside `[from_min, from_max]` — it clamps. So all three segments compute a value for every sample. We then pick one with weight masks:

```
PW Band - IsTop  = LESS_THAN(v_around, split-)         -> 0 or 1
PW Band - IsBot  = GREATER_THAN(v_around, split+)      -> 0 or 1
PW Band - IsCore = (1 - IsTop) - IsBot                 -> 0 or 1
```

Each segment's output is multiplied by its mask (`PW Band - {Top,Core,Bot} Weighted`), then added together to produce `PW Band - Arc2 V`.

### Final V switch (Arc 1 vs Arc 2)

The two arcs share strand geometry but get distinguished by the boolean attribute `is_sub_strand` (FLOAT, written by `Store Named Attribute.004` and `.005`). The final mix is one MULTIPLY_ADD:

```
PW Band - Diff   = Arc2 V - Arc1 Map.Result
PW Band - Band V = is_sub_strand × Diff + Arc1 Map.Result
```

So when `is_sub_strand = 0` (Arc 1) the V is `Arc1 Map.Result`; when `is_sub_strand = 1` (Arc 2) it's `Arc2 V`. The output is then fed into `Texture V Center` (the existing per-arc V offset chain) and finally `Math.014 → PW UV V Add → Combine XYZ.006.Y`.

## U scaling — procedural chain

`u_along` is a per-vertex FLOAT attribute already maintained by the strand builder:

```
Spline Parameter.Factor          ∈ [0, 1]                         (default for sub-strand splines)
Warp U Compensated   = factor × Warp Spline Length / Warp Straight Length     (overrides for warp)
Weft U Compensated   = factor × Weft Spline Length / Weft Straight Length     (overrides for weft)
```

Both warp and weft compensations write into the same `u_along` attribute via `Store Warp U` and `Store Weft U`. So `u_along` ranges from 0 to slightly above 1 (the `length_ratio` is `spline_length / straight_length` and exceeds 1 because the over/under wave makes the curve slightly longer than its end-to-end straight distance).

### Auto Scale U formula

The chain we added (`PW U - …`) sits right before `Math.013` (which already multiplied `u_along` by the old `Texture Scale U` socket):

```
PW U - Image World Width = Image Width Px / Scanner Pixels Per BU       (BU)
PW U - Strand Length     = Warp Threads × Spacing                       (BU)
PW U - Scale U Auto      = Strand Length / Image World Width            (multiplier)
PW U - Scale U Final     = Scale U Auto × Texture Scale U               (final multiplier)
                            ▼
                          Math.013.in[1]
```

`Math.013.out = u_along × Scale U Final` is then added to `uv_offset_u` (random-per-strand offset) by `PW UV U Add` and combined with V into `uv_scaled`.

### What "Texture Scale U = 1.0" means in practice

When `Texture Scale U = 1.0`, the auto-scale alone applies. With the current scene defaults (Threads × Spacing = 3.5 m vs image_world_width = 0.253 m for china_grey), that's `Scale U Final ≈ 13.8` — the image tiles ~14× along each strand at "1 image-world-width per strand" pixel density.

When `Texture Scale U` is dropped to `≈ 1/auto` (e.g. ~0.072 for the above case), the effective Scale U is ~1.0 and the image fits **once** along each strand. Pull it down further to stretch the image, push it past 1.0 to tile.

The procedural chain means the look stays **invariant under fabric resizing**: change Threads or Spacing and the image rescales with the strand instead of getting visually denser or sparser.

## UV write-out

The terminal node in the UV path:

```
Combine XYZ.006 (X = PW UV U Add, Y = PW UV V Add, Z = 0)
   └─▶ Store Named Attribute.002  (Name: 'uv_scaled', FLOAT2)
```

Materials read this with `ShaderNodeAttribute(name='uv_scaled', type='GEOMETRY')`. Reading the default `UVMap` attribute returns (0,0) and produces a uniform color — this was the bug behind all the "completely wrong mapping" renders before the attribute name was corrected.

## Other named attributes the GN writes

| Attribute | Writer node(s) | Used by |
|---|---|---|
| `u_along` | Store Named Attribute, Store Warp U, Store Weft U, PW Loose U Along | `Math.013` (then U scaling chain). |
| `v_around` | Store Named Attribute.001 (default), Store Named Attribute.003 (warp/weft override) | `Texture V Arc Weight`, `PW Band - Arc1 Map`, `PW Band - Arc2 *`, `PW Band - IsTop/IsBot`. |
| `uv_scaled` | Store Named Attribute.002 | Material `ShaderNodeAttribute('uv_scaled')`. |
| `uv_offset_u`, `uv_offset_v` | PW Warp/Weft/Loose UV Offset U/V | Random per-strand offsets, added in `PW UV U Add` and `PW UV V Add`. |
| `material_id` | PW Warp/Weft/Loose Material Id | Per-strand material cycling — drives `Warp Material 1..4` selection. |
| `is_sub_strand` | Store Named Attribute.004, .005 | The Arc 1 vs Arc 2 V-switch in `PW Band - Band V`. |
| `.pw_u_density_scale`, `.pw_loose_src_u`, `.pw_loose_src_scale` | Internal density/loose-strand chains. | Internal use only. |
