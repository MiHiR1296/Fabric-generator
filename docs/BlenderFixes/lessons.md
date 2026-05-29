# Lessons — Blender-side

> **Read this if** you're about to touch the .blend's node groups, modifier interface, or the backend code that drives them. Read before changing anything cross-app.

Each lesson has the **Rule**, the **Why**, and a **Concrete example** with node names / socket identifiers / file paths.

---

## On editing geometry-node interfaces over MCP

### Rule 1 — Interface socket renames preserve wiring; deletions do not.

`it.name = "New Name"` on an `interface.items_tree` socket is non-destructive. Blender identifies sockets by `identifier` (a stable string like `Socket_61`), and all internal connections — Group Input outputs feeding switches, Map Range inputs, etc. — reference by identifier, not name. The rename only changes the user-facing label.

`interface.remove(item)` is destructive: the identifier disappears, every link referencing it dies, and Blender re-numbers some things.

**Why**: Phase 3d renamed 68 V-band sockets in one pass (Core/Fiber → Arc 1 / Arc 2). Zero wiring broke. Phase 3f then removed 5 truly-dead globals — that was safe only because the audit (see Rule 3) confirmed no Group Input was consuming them.

**Concrete fix pattern**:

```python
# SAFE
for it in ng.interface.items_tree:
    if it.name == old_name:
        it.name = new_name      # identifier untouched; all internal links survive

# DESTRUCTIVE — only do if you've confirmed no consumers
ng.interface.remove(item)
```

---

### Rule 2 — When a graph's interface names look right but the values look wrong, the bug can be in three places at once.

Don't assume the producer is wrong, the consumer is wrong, or the wiring is wrong in isolation. Trace all three layers.

**Why**: Phase 3e's underlying bug had three components:

1. Producer wrote *inner-edge* values to `Arc 2 V Min/Max` (effectively duplicating Arc 1)
2. Graph wired `Arc 2 Top.To Max` and `Arc 2 Bot.To Min` to switch chains that carried the wrong band's data
3. Interface socket names ("Fiber Top V Min") were ambiguous between "lower V edge of the top fiber band" and "the V value labeled Min on top fiber" — different meanings, producer and consumer chose opposite interpretations

The fix needed all three layers touched. Fixing only the producer or only the wiring would have left a different bug visible.

**Diagnostic pattern**:

1. Print the *actual values* the modifier currently holds (read `mod[it.identifier]` for every socket of interest).
2. Walk the graph from Group Output backwards (`walk_upstream`) to see every node that contributes to the final output.
3. For each producer-targeted socket, find which internal `Switch` chain it flows into, then which `Map Range` consumes that switch — these three layers must all agree on what the value means.

---

### Rule 3 — Audit Group Input consumers before removing interface sockets.

A socket without a Group Input output link is genuinely dead. Blender's interface system separates **declaration** (sockets appear in `interface.items_tree`) from **consumption** (a `GROUP_INPUT` node's output for that socket has links to other nodes).

```python
# Find truly-dead input sockets
consumed_ids = set()
for n in ng.nodes:
    if n.type == 'GROUP_INPUT':
        for o in n.outputs:
            if o.is_linked:
                consumed_ids.add(o.identifier)

dead = [it for it in ng.interface.items_tree
        if it.item_type == 'SOCKET' and it.in_out == 'INPUT'
        and it.socket_type != 'NodeSocketGeometry'
        and it.identifier not in consumed_ids]
```

**Why**: Phase 3f found 5 dead globals (`Image Width Px`, `Image Arc 1/2 V Min/Max`) that no Group Input was consuming. The producer had been pushing values to them every render — pure waste. Important: there are **multiple Group Input nodes** in `Parametric Weave knotty` (13 total — one per logical section), so checking just the first one will give wrong results. Loop ALL of them.

**Concrete sequence**:

1. Snapshot the .blend.
2. Run the audit above.
3. For each "dead" item, sanity-check by name (anything that *should* be wired but appears dead is a different bug — fix that first, don't remove).
4. `interface.remove(item)` for each truly-dead socket.
5. Update the producer's push list (`PER_MATERIAL_SOCKETS` / `GLOBAL_SOCKETS` in [blender_live.py](../../backend/app/blender_live.py)) to drop the removed names.
6. Verify viewport / render unchanged — if the geometry breaks, restore from the snapshot, the audit missed something.

---

### Rule 4 — A gate hidden inside a MULTIPLY_ADD silently invalidates upstream fixes.

Blender's Math nodes can express conditional logic via MULTIPLY_ADD: `result = a × b + c`. If `a` is an attribute that's 0 by default, `b` (the upstream computation) contributes nothing and `c` (the fallback) wins.

**Why**: Phase 3e's Arc 2 rewire was correct in isolation. But `PW Band - Band V` is `MULTIPLY_ADD`:

```
Band V = is_sub_strand × (Arc2 V − Arc1 Map) + Arc1 Map
```

On main-strand geometry `is_sub_strand = 0`, so `Band V = Arc1 Map` — Arc 2 V is computed and then thrown away. The halo never reaches the texture sampling, regardless of how correct Arc 2's outputs are.

**Diagnostic pattern**: when an upstream fix doesn't change the rendered output, trace forward from the fix point to Group Output and look for *any* node whose output depends on a multiplicative or conditional input. Specifically check:

- `MATH:MULTIPLY` / `MATH:MULTIPLY_ADD` with a constant or attribute on the multiplier input
- `SWITCH` nodes with a default-False `Switch` input
- `MIX` shader / vector / float nodes where the `Fac` is a hidden constant
- `NamedAttribute` reads where the attribute is undeclared on the geometry (returns 0)

In Phase 3g the fix was to ensure `is_sub_strand` becomes 1 — done by pinning `Sub Strand Enable = True` so sub-strand geometry gets generated and tagged with the attribute. The math then resolves to `Band V = Arc2 V` as Phase 3e intended.

---

### Rule 5 — Producer keys ≠ Blender socket names. Keep the mapping in one place.

`bandMeta.blender.core_v_min` is a producer field name; `Material N Arc 1 V Min` is a Blender socket name. They mean the same value, but renaming one doesn't rename the other.

**Why**: producer field names describe scan data (the band-detection algorithm's outputs); socket names describe what the .blend's node graph treats the value as. Decoupling lets future .blend revisions rename sockets without forcing a metadata schema bump.

**Pattern**: `PER_MATERIAL_SOCKETS` in [blender_live.py](../../backend/app/blender_live.py) is the single source of truth for the (socket name, producer key, default) triples. Add/rename in one place, both code paths (live MCP push and headless script) use it.

```python
PER_MATERIAL_SOCKETS: tuple[tuple[str, str, float], ...] = (
    ("Arc 1 V Min", "core_v_min", 0.0),
    ("Arc 1 V Max", "core_v_max", 1.0),
    ("Arc 2 V Min", "fiber_bot_v_min", 0.0),
    ("Arc 2 V Max", "fiber_top_v_max", 1.0),
    ...
)
```

Phase 3d renamed the .blend's sockets; this tuple was the only producer-side edit needed because both call sites (`_pw_apply_modifier_material_metadata` body in [blender_live.py:APPLY_METADATA_PY](../../backend/app/blender_live.py) and the live `push_bandmeta_to_live_blender` path) read from it.

---

### Rule 6 — Snapshot the .blend before destructive ops; record the path in the phase entry.

Cheap insurance. The MCP socket can execute arbitrary `bpy` code; one bad call destroys hours of node-graph work that doesn't appear in undo history (geometry-node interface edits aren't always undoable).

**Pattern**:

```python
import time, shutil, bpy
bpy.ops.wm.save_mainfile()              # flush current state
src = bpy.data.filepath
ts = time.strftime("%Y%m%d_%H%M%S")
backup = src.replace(".blend", f".pre-<change-tag>-{ts}.blend")
shutil.copy2(src, backup)
```

Recorded in [phase_log.md](phase_log.md) Phase 3d and Phase 3e. Both backups still on disk in the same folder as the canonical .blend.

---

### Rule 7 — Set the modifier's NodeSocketMaterial input, not the Set Material node's default value.

When a `Set Material` node's `Material` input is **linked** to a Group Input output (which is the case for `Material 1` in `Parametric Weave knotty`), setting `node.inputs["Material"].default_value = mat` does nothing — the link wins. You have to set the modifier's interface value:

```python
# WRONG: Material 1 socket is link-driven, default_value is ignored
set_material_node.inputs["Material"].default_value = my_material

# RIGHT: drive the link source
mod["Socket_61"] = my_material   # Material 1's identifier
```

**Why**: this bit us in Phase 3f after the live-sync attempt. I set `Set Material.Material.default_value = WebYarn_thread001` and was confused why the render didn't update — it was still rendering whatever was on `Material 1` modifier input (the old `FabricStudioMaterial_01_2ca1b1da`).

**Diagnostic**: check whether the Material input is linked first:

```python
if set_mat_node.inputs["Material"].is_linked:
    # Drive it via the modifier socket on the link source
    link = set_mat_node.inputs["Material"].links[0]
    src_socket_id = link.from_socket.identifier  # e.g. 'Socket_61'
    mod[src_socket_id] = my_material
else:
    set_mat_node.inputs["Material"].default_value = my_material
```

---

### Rule 8 — Modifier-input setters must be tolerant of missing sockets across .blend revisions.

The .blend evolves — `Parametric Weave knotty` is the current target; an older revision had `Weave From Draft` with different socket names (`Thread Radius`, `Ply Count`, `Fiber Density`, etc.). The same backend script body should run against both without crashing.

**Pattern**: use `maybe_set_modifier_input` (silently no-op on missing sockets) for any socket name that isn't guaranteed across revisions. Reserve `set_modifier_input` (which raises KeyError) for the handful of sockets we know must exist (`Draft Object`, `Draft Columns`, `Draft Rows`, `Warp Threads`, `Weft Threads`, `Spacing`).

```python
# blender_sync.py helper
def maybe_set_modifier_input(modifier, node_group, name, value):
    try:
        socket = ensure_socket(node_group, name)
    except KeyError:
        return False
    try:
        modifier[socket.identifier] = value
        return True
    except Exception:
        return False
```

Phase 3f's panel cleanup removed 5 sockets the script was previously pushing — without the tolerant setter, every headless render after the cleanup would have crashed on `KeyError: 'Image Width Px'`.

---

### Rule 9 — Re-bind the Set Material chain when swapping yarns; texture data alone isn't enough.

A material's TexImage nodes hold image references — if you swap the material on `Material 1` socket without also swapping the Image data, the texture sampling still hits the previous image. And alpha matters: different yarns have different opaque regions in V. Pushing thread001's `Arc 1/2 V Min/Max` to a socket whose material samples a different yarn's alpha will produce sections of fully-transparent strand.

**Pattern**: Render Preview must push these together as one atomic update:

1. Object material slots → generated yarn materials (`FabricStudioMaterial_XX_<asset>`)
2. Modifier `Material N` sockets → the same generated materials
3. Material N V-band sockets → that yarn's `bandMeta.blender.*` values
4. Warp/Weft material cycle sockets → the draft's material ids

The render script generated by [render_jobs.py:build_headless_render_script](../../backend/app/render_jobs.py) does this for both headless renders and Phase 3g live renders. [blender_live.py:push_bandmeta_to_live_blender](../../backend/app/blender_live.py) only pushes numeric band metadata; use Render Preview/live render when you need material images swapped too.

---

### Rule 10 — When live-rendering over MCP, override the socket timeout locally — don't touch the global default.

Long Cycles renders take minutes; the default `BLENDER_TIMEOUT_SECONDS = 30` (set in [blender_sync.py:load_blender_socket_config](../../backend/app/blender_sync.py)) is for snappy diagnostic calls. Bumping it globally would mask other timeouts.

**Pattern** (used in `_run_live_render` in [render_jobs.py](../../backend/app/render_jobs.py)):

```python
prev = os.environ.get("BLENDER_TIMEOUT_SECONDS")
os.environ["BLENDER_TIMEOUT_SECONDS"] = "900"   # 15 min
try:
    response = send_blender_command("execute_code", {"code": script})
finally:
    if prev is None:
        os.environ.pop("BLENDER_TIMEOUT_SECONDS", None)
    else:
        os.environ["BLENDER_TIMEOUT_SECONDS"] = prev
```

Scoped to the one call site that legitimately needs the long timeout. The default stays 30s for everyone else.

---

## On the .blend's design

### Rule 11 — Arc 2 only fires on sub-strand geometry. Pin Sub Strand Enable for scan-driven yarns.

The graph's halo rendering lives in Arc 2 (three-section partition), which only runs when `is_sub_strand = 1` (set on sub-strand geometry only). For real scanned yarns, you almost always want the halo, so `Sub Strand Enable` should be on.

Producer ([blender_live.py:PINNED_FOOTGUN_SOCKETS](../../backend/app/blender_live.py)) pushes `Sub Strand Enable = True` on every bandMeta push. The .blend's default is also True (set in Phase 3g). Both defenses needed because either can be toggled off and break the rendering.

**Don't disable Sub Strand Enable** for scan-driven workflows. If you want a "no halo" preview mode for some reason, the right place to add the toggle is a new interface socket (`Apply Halo To Main Strand`) wired to replace the `is_sub_strand` gate on `PW Band - Band V`.

---

### Rule 12 — The V footgun sockets are additive/phase controls, not casual tweaks.

`Texture Scale V`, `Texture Offset V`, `Texture Side Flatten`, `Sub Texture Scale V`, and `Sub Texture Offset V` are global V controls that can silently move the scan-driven band mapping. Treat them as pinned checkpoint values, not casual artistic knobs.

| Socket | Pinned value | Meaning of the pin |
|---|---|---|
| `Texture Scale V` | 1.0 | V scale = main strand × 1 (no change) |
| `Texture Offset V` | 0.0 | Neutral V phase for the 2026-05-19 approved direct-material checkpoint |
| `Texture Side Flatten` | 0.0 | Cross-section maps as flat ribbon (no cylindrical projection compensation) |
| `Sub Texture Scale V` | 1.0 | Approved checkpoint value for the sub-strand V scale control |
| `Sub Texture Offset V` | 0.0 | Sub-strand V offset delta = 0 → aligned with main |

Earlier Arc 2 sub-strand notes treated `Sub Texture Scale V = 0` and `Texture Offset V = 0.031914920` as the active pins. The 2026-05-19 visual checkpoint supersedes that active state: keep `Texture Offset V = 0`, `Sub Texture Scale V = 1`, and `Sub Texture Offset V = 0` unless a new visual checkpoint replaces them. Always push these defensively even though they're the .blend's defaults.

---

### Rule 13 — Piecewise Map Ranges must be continuous at their split boundaries.

Correct V values and correct split fractions are not enough. The Map Range direction also has to match the coordinate direction. Phase 3k found Arc 2 had the right three sections and the right four V endpoints, but each section ran the wrong way for `v_around`.

For this graph, node labels are not enough to infer the physical side being sampled. Treat Arc 2 as one stitched texture-V path with four boundary values. Phase 3k made Arc 2 continuous as:

```text
Arc2 Top:  Arc 2 V Max -> Arc 1 V Max
Arc2 Core: Arc 1 V Max -> Arc 1 V Min
Arc2 Bot:  Arc 1 V Min -> Arc 2 V Min
```

When editing any piecewise texture map, write the expected boundary values first, then verify each adjacent pair meets at the same V.

Phase 7 intentionally flipped this direction for live visual review. The first naive attempt swapped every Map Range independently and broke continuity at the split boundaries. The corrected graph reverses the whole stitched path, so it now runs:

```text
Arc2 Top:  Arc 2 V Min -> Arc 1 V Min
Arc2 Core: Arc 1 V Min -> Arc 1 V Max
Arc2 Bot:  Arc 1 V Max -> Arc 2 V Max
```

---

### Rule 14 — If UVs are stored before Fit To Space, per-material U carries the fit correction.

`Parametric Weave knotty` stores the texture coordinate before the `Fit To Space` modifier scales the visible fabric to the Space plane. The graph's raw U length is therefore `Warp Threads * Spacing`, not the final viewport size.

For scan-driven yarns, root `Texture Scale U` stays neutral and the setup/render script pushes the correction into each `Material N Texture Scale U`. The old Phase 4 fit-aware formula is retired for the current checkpoint; the active auto path is visible-span based:

```text
root_texture_scale_u = 1.0
AUTO_TEXTURE_SCALE_U_DENOMINATOR = 1.0
visible_v_span = Arc1_V_Max_Padded - Arc1_V_Min_Padded
Material N Texture Scale U = visible_v_span / AUTO_TEXTURE_SCALE_U_DENOMINATOR
```

Do not put this correction on root `Texture Scale U`; it is global and will hide per-material differences. Root U should read `1.0` unless we intentionally add a global artistic override.

---

### Rule 15 — Use Linear sampling for photographic yarn previews.

Generated direct material nodes should use `Linear` interpolation for scanned yarn textures. `Closest` is useful for debugging texels, but it makes Cycles-safe downscales, especially tall-but-thin yarn strips such as `16384 × 144`, look visibly pixelated in the live viewport.

Keep the Cycles cap decision separate from the sampling decision: the cap protects Blender/GPU limits; interpolation controls how the preview is filtered. For sharpness diagnosis, use `WEAVE_TEXTURE_INTERPOLATION=Closest` or `Smart` instead of editing the generated material by hand.

---

### Rule 16 — Keep Arc 1 geometry stable; change Arc 2 mapping around it.

Arc 1 is structural in this setup. Moving or resizing it changes strand overlap and weave behavior, not just texture appearance.

When Arc 2 needs a bigger halo/fiber envelope, change Arc 2's profile/split logic instead of moving Arc 1. Phase 3m tried a centered texture-span split:

```text
core_frac = (Arc 1 V Max - Arc 1 V Min) / max(Arc 2 V Max - Arc 2 V Min, 0.0001)
Split Minus = 0.5 - core_frac / 2
Split Plus  = 0.5 + core_frac / 2
```

Phase 3p/3q superseded that formula because texture V span is not generated geometry area. The rule still stands: Arc 1 stays stable; Arc 2 owns the extra halo area and the split math.

---

### Rule 17 — Validate physical scale at the producer; do not infer units from a visual multiplier.

The raw scanner images can carry embedded DPI while processed PNG exports may strip it. Phase 3o found the listed scanner files report about `1600 dpi`, but the processed yarn `rgba.png` reports no DPI/72 dpi depending on the reader.

The library metadata now records `physical_scale` with declared DPI, source-scan embedded DPI, processed-export embedded DPI, and a confidence label. Use that as provenance. Phase 4d's `texture_u_calibration = 0.1` default is a visual calibration that divides the fit-only U by ten; do not convert it into a Blender-unit fact.

---

### Rule 18 — Geometry chooses Arc 2 split area; texture metadata chooses sampled V rows.

`Arc 1 V Min/Max` and `Arc 2 V Min/Max` are texture destinations. They say which rows of the scanned yarn image should be sampled for core and halo. They do not, by themselves, prove how much of Arc 2's generated cross-section should be allocated to the core.

Phase 3p found the current centered Arc 2 split still uses texture V-span ratio as a proxy for generated geometry:

```text
core_frac = (Arc 1 V Max - Arc 1 V Min) / (Arc 2 V Max - Arc 2 V Min)
```

That is useful as a diagnostic, but not enough for the final model. The final Arc 2 split should be computed inside the geometry-node graph from the actual Arc 1 / Arc 2 cross-section relationship, then map those geometry regions to the existing texture V destinations.

---

### Rule 19 — Store evaluated debug attributes for geometry-node math.

Modifier panel values and node labels can lie by omission. Phase 3q found `Main Strand Radius = 0.025` in the interface, but the old `Math.017` chain still evaluated Arc 2 radius as `0.015` in the output mesh. The fix became obvious only after storing the values as attributes and reading the evaluated mesh.

For geometry-owned mapping work, store the intermediate scalars you care about on the mesh:

```text
arc1_radius_geometry
arc2_radius_geometry
arc2_core_frac_raw
arc2_core_frac_geometry
arc2_core_split_min
arc2_core_split_max
```

Then trust the evaluated attributes over the modifier panel.

---

### Rule 20 — Preserve over-wide scan detail with U tiles, not a larger single bitmap.

Cycles' single-texture dimension cap is separate from final render resolution. A `45058 x 395` yarn strip can fail as one image even when the desired final render is valid.

For long yarn strips, split the source into horizontal UDIM tiles and map `fract(uv_scaled.x) * tile_count` into UDIM U space. That keeps the full V resolution (`395px` for thread001) while every tile stays under the `16384` device limit. Keep the Cycles-safe downscale as fallback, not as the only production path.

---

### Rule 21 — Arc 1 core padding must stay inside Arc 2's silhouette.

A small Arc 1 V padding can show more of the core texture, but Arc 1 V Min/Max also feed Arc 2's inner halo boundaries. If the padding pushes Arc 1 beyond Arc 2 V Min/Max, the halo sections invert.

Put artistic core padding in the graph/modifier layer, expand Arc 1 V Min downward and Arc 1 V Max upward after material selection, and clamp the padded interval inside `fiber_bot_v_min..fiber_top_v_max`. Keep backend metadata pushes raw so the panel value is the only tuning source.

---

### Rule 22 — Live setup signatures must include render settings, not only yarn bindings.

The per-material U scale is not pure yarn metadata. It depends on live setup context:

```text
Material N Texture Scale U = bandMeta.texture_scale_u
                           * (max(Space X/Y) * Fill Ratio)
                           / (Warp Threads * Spacing)
                           * texture_u_calibration
```

If the Web UI only live-pushes when yarn bindings change, Blender can keep stale `Material N Texture Scale U` values after the user changes zoom or spacing. Phase 4j fixed this by including `draft.renderSettings` in the live-push debounce signature. This is why a value like `0.5` can remain visible in the modifier panel even though the current calibrated setup should push `0.05`.

---

### Rule 23 — A transparent-looking Arc 2 usually means the halo alpha is genuinely low.

Arc 2 samples the outer strand/fiber rows. For the current Vegeta/Horizon yarns, the saved alpha maps have dense core rows around `203–213` average alpha, while top/bottom halo rows average only `20–29`, with most halo pixels below alpha `80`. The shader uses the alpha map directly, so Arc 2 will look transparent unless we intentionally add a preview/render alpha boost, shrink the Arc 2 V span, or change the preprocessing alpha policy.

---

### Rule 24 — Warp and weft curves need an explicit Set Curve Normal node, or padding/V-band behaviour will be axis-asymmetric.

`Curve to Mesh` orients the profile arc using the curve's stored normals. Blender's default mode is **Minimum Twist**, which derives the initial normal from the curve's tangent — that initial normal differs for a Y-aligned curve vs an X-aligned curve, even with the same construction code. Result: the cross-section profile is rotated 90° (or flipped) between warp and weft strands. Texture features that depend on `v_around` direction (Arc 1 V padding, Arc 2 halo extents) end up on the camera-visible side for one axis and on the hidden side for the other.

**Why**: Phase 5 (2026-05-16) — `Arc 1 V Padding ≥ 0.05` visibly expanded the halo on weft strands from top-ortho, with no equivalent expansion on warp strands. Reading the evaluated mesh confirmed warp top-of-strand `v_around` did not match weft top-of-strand `v_around`. The graph's V-band chain was identical for both axes; the asymmetry was at the geometry orientation layer.

**Fix pattern**:

```python
scn = ng.nodes.new('GeometryNodeSetCurveNormal')
scn.inputs['Mode'].default_value = 'Z Up'      # Blender 4.6+: Mode is a NodeSocketMenu, not a node prop
ng.links.new(resample.outputs['Curve'], scn.inputs['Curve'])
ng.links.new(scn.outputs['Curve'], next_node.inputs['Curve'])
```

Insert one per axis branch — `PW Warp Set Curve Normal` between `Resample Curve` and `Store Warp U`; `PW Weft Set Curve Normal` between `Resample Curve.001` and `Store Weft U`. Verify by reading the evaluated mesh's `v_around` attribute on top-of-strand vertices: both axes should now have mean ≈ `0.5`, range `[~0.333, ~0.667]`.

**Critical gotcha**: in Blender 4.6+ the `Set Curve Normal` node has *no* `mode` Python attribute. Setting `scn.mode = 'Z_UP'` raises `AttributeError`. The mode lives on the `Mode` input socket (`NodeSocketMenu`) and accepts string literals `'Minimum Twist'`, `'Z Up'`, or `'Free'` via `default_value`.

---

### Rule 25 — Use a `NodeSocketMenu` input's `default_value` for new-style enum sockets, not a node property.

When Blender 4.6+ promoted several internal enums to interface menu sockets (e.g. `Set Curve Normal.Mode`, `Image Texture.Interpolation` on some node variants), the corresponding `node.<attr>` property was removed. Setting it raises `AttributeError: 'GeometryNodeFoo' object has no attribute 'mode'` and looks like a Python API bug.

**Why**: discovered in Phase 5 while inserting `Set Curve Normal` nodes — `scn.mode = 'Z_UP'` failed. Probing `bl_rna.properties` showed no `mode` property; `scn.inputs['Mode']` was a `NodeSocketMenu` taking string values.

**Diagnostic pattern**: if a node's enum setting won't take via the obvious `node.<attr> = ...`, list its inputs first:

```python
test = ng.nodes.new('GeometryNodeSetCurveNormal')
print([(s.name, s.bl_idname) for s in test.inputs])
# -> [('Curve', 'NodeSocketGeometry'), ('Selection', 'NodeSocketBool'),
#     ('Mode', 'NodeSocketMenu'), ('Normal', 'NodeSocketVectorXYZ')]
# 'Mode' is a NodeSocketMenu → set via test.inputs['Mode'].default_value = 'Z Up'
```

The string accepted is the menu's display label (e.g. `'Z Up'`, not `'Z_UP'`).

---

### Rule 26 — When backend code drives modifier sockets, a hot dev-server reload is not a code reload.

`make backend-dev-live` runs uvicorn with `--reload` watching the `backend/` directory. That reloads route handlers, but modules that are imported at startup and held by long-lived references (like `blender_live.PER_MATERIAL_SOCKETS`, `build_material_asset_entry`) may not pick up edits depending on the reloader's strategy. After significant edits to push-side code, the user can see "nothing changed" symptoms because the next render preview still pushes old values onto the modifier — overwriting any direct-MCP fixes from a debug session.

**Why**: discovered in Phase 5. After live-MCP pushing `Material 1 Texture Scale U = 0.0549`, the user triggered a Render Preview from the web UI; the dev-server backend with stale `blender_live.py` pushed `1.0` back onto the modifier and the squish returned. Reading the modifier after the user reported "none of the fixes worked" showed exactly that.

**How to apply**: when shipping changes to `blender_live.py`, `blender_sync.py`, or `render_jobs.py` that affect what gets pushed per render:
1. Kill the backend process (`pgrep -lf "app.main"` → `kill <pid>`) and restart with `make backend-dev-live` to get a fresh interpreter.
2. After the user's first new render preview, read back the relevant modifier socket values via MCP to confirm the new code took effect.
3. If you're debugging through direct MCP pushes, warn the user that any web-UI render preview will overwrite them until the backend restarts.

---

### Rule 27 — A piecewise map-range on one axis demands a piecewise scale on the orthogonal axis.

When a single Map Range on V is broken into multiple sections that each have a different `(To Max − To Min) / (From Max − From Min)` slope, the U axis cannot stay calibrated to one of those slopes without distorting the others. Arc 2 partitions `v_around` at fixed proportions (`0.2 / 0.6 / 0.2` per Phase 3q) but each section's texture-V span is scan-driven and very different — Top and Bot end up with V slopes ~5–10× the Core slope. A single global `Texture Scale U` tuned for the Core section reads the halos at 5–10× the wrong aspect, which shows up as hazy/stretched edges. Arc 1's full-`v_around` mapping to the same narrow core span has the same problem at a smaller ratio (~0.6 vs 1.0).

**Why**: Phase 10 (2026-05-17) — user observed halo regions look stretched along strand length and Arc 1 edges look sloppy in the same direction. The geometric split was correct; the orthogonal-axis sampling rate was the missing piece.

**How to apply**: when a piecewise Map Range owns one texture axis, derive `section_slope = section_v_span / section_v_around_width` for every section, then multiply the orthogonal axis (after its existing scale + offset add) by `section_slope / baseline_section_slope`. Gate by any geometry-mode attribute (e.g. `is_sub_strand`) so single-section regions get their own ratio instead of being forced through the piecewise path. Verify by reading the section-ratio attribute on the evaluated mesh — the distribution of ratio values should match the geometry partition.

**Unit gotcha (Phase 10a, 2026-05-17)**: when the "single-section" surface (e.g. Arc 1 main strand) lives on a *different cylinder* than the piecewise surface (Arc 2), don't compare V slopes in parametric `v_around` units — compare in *physical around-strand BU* (or rely on the construction that equalizes the two). Phase 3q's split `arc1_radius / arc2_radius = 0.6` was chosen exactly so Arc 1's full v_around and Arc 2 Core's 60% slice cover the same physical width; once you know that, Arc 1's "section slope" in the comparison must use `core_span / 0.6` (not `core_span / 1.0`), and the ratio collapses to `1.0` against Arc 2 Core — i.e. no per-section adjustment on Arc 1, which is correct because they already share a U calibration by construction.

**Side effect to declare**: multiplying *after* the offset add scales the strand-to-strand spool stride per section too, which makes the spool continuous *within each section* but discontinuous *across* the section boundary. Acceptable when the texture content on either side of that boundary is intentionally different (core vs halo) and the boundary sits in a low-α region.

**Profile-vertex alignment (Phase 10b, 2026-05-17)**: a piecewise V mapping creates a V slope discontinuity exactly at each section boundary. For the discontinuity to render as a sharp transition rather than a smeared "thick noisy band", **the profile curve must have a vertex at every section boundary fraction**. If a boundary falls between two profile vertices, the rasterizer linearly interpolates tex_v across the spanning face — mixing two sections' texture content into a single quad and producing the visual artifact the user sees as "missing rows" / "skipped letter bands" in a UV checker test. Two ways to fix: bump profile Resolution to align (`Resolution = 11` works for boundaries at `0.2 / 0.8`), or resample the profile curve to actively insert vertices at `Split Minus` and `Split Plus`. The bump is a one-line fix and works as long as the Phase 3q geometric split produces "nice" fractions; the resample is robust to arbitrary radii.

**Radius-agnostic resample pattern (Phase 10c, 2026-05-17)**: when the boundary fractions are *dynamic sockets* (driven by `arc1/arc2_radius` in this case), the profile must be rebuilt so vertices land on those dynamic values automatically. Pattern that works:

1. `Mesh Line` with `Count = K × N + 1` points uniformly spaced in `natural_factor ∈ [0, 1]` (where the natural anchors `A_min`, `A_max` are integer multiples of `1/(N)`).
2. Per-vertex piecewise `Map Range` chain: `natural → actual` with `[0, A_min] → [0, Split Minus]`, `[A_min, A_max] → [Split Minus, Split Plus]`, `[A_max, 1] → [Split Plus, 1]`. Use IsTop / IsCore / IsBot weighted sums to combine.
3. `Sample Curve` (mode = Factor) on the original arc at `actual` → vertex position.
4. `Set Position` + `Mesh to Curve` → final polyline that feeds the existing `Store v_around` chain.

The polyline's `Spline Parameter Factor` equals `cumulative_length / total_length`. Because the piecewise mapping makes within-section segments equal-length on the source arc, the natural anchor `A_min` ends up at exactly `Spline Parameter Factor = Split Minus` — automatically, for any radii. Vertex 6 (or whatever sits on `A_min`) IS the boundary vertex no matter what `Split Minus` is at runtime. The pattern generalizes to any number of sections.

**Anchor-attribute pattern (Phase 10d, 2026-05-17)**: once you start deforming the profile geometry *after* the parametric attribute is set (e.g. radially insetting boundary vertices to hide section discontinuities under an inner shell), `Spline Parameter Factor` is no longer reliable — segment lengths change, factor shifts off the anchor. Fix: bake the parametric attribute as a custom point-domain attribute on the profile mesh BEFORE the position deformation, then read it back downstream instead of recomputing from `Spline Parameter`. In Phase 10d we store `pw_profile_natural = Position.X` immediately after `Mesh Line` (before `Set Position`), and `Store Named Attribute.003` (writes `v_around`) reads from that named attribute instead of `Spline Parameter`. Now any radial / tangential / displacement edit to the profile preserves the V mapping.

**Texture-proportional split for slope match (Phase 10e, 2026-05-17)**: even after the piecewise V mapping has a vertex exactly on the boundary (Phase 10c), the *slope* on either side of the boundary differs whenever the yarn's halo/core V spans don't match the fixed geometric split. The leftover slope step shows as a tiny but visible cell-aspect band right at the boundary. The principled fix is to make the geometric split *equal to the texture proportions*: `split_minus = top_v / total_v`, `split_plus = (top_v + core_v) / total_v`. Then `tex_v / v_around` is the same constant in every section. The trade-off is that the geometric split becomes yarn-specific (Phase 3q's pure geometric split was intentionally yarn-independent, derived from profile radii). Implement as an opt-in toggle so the user can keep Phase 3q semantics by default and flip to texture-proportional for clean-render mode. The Phase 10 per-section U multiplier remains valid in both modes — it just becomes a no-op (× 1.0) when slopes match.

---

### Rule 28 — Cumulative-sin(θ) V mapping in sections that span significant angular range.

When a piecewise V section spans a significant arc of a cylindrical cross-section (e.g. Arc 2 Top covers `θ = 30°..54°` near the silhouette), **linear-in-`v_around`** allocates the same V span to every polygon — but silhouette polygons project to a much smaller screen-space footprint than face-on polygons, so they show *too much* texture content per pixel and read as a single huge stretched cell. The fix is to allocate V proportionally to `sin(θ)` (the projected screen size), which integrates cumulatively to `cos(θ_start) − cos(θ)`. Concretely:

```text
norm(v_around) = (cos(θ_start) − cos(θ(v_around))) / (cos(θ_start) − cos(θ_end))
θ(v_around)    = θ_start + (v_around − section_start) / section_natural_width × section_angle_range
```

Apply on outer sections only (Top / Bot for the Phase 3q `0.2 / 0.6 / 0.2` split); skip on Core where the section is already near face-on (`θ ≈ 90°`, `sin(θ) ≈ 1`).

**Why**: Phase 10f (2026-05-17) — user reported silhouette cells of Arc 2 reading as stretched even with Phase 10c/10d/10e in place. With `Arc 1 V Padding = 0.012` and the linear-in-`v_around` mapping, the tiny `top_v_span = 0.0025` got spread across all 20% of Top's `v_around`, so one cell stretched across the whole section width. After the cosine remap, F/G/H/A/B rows are visible in clean alphabetical order with approximately uniform cell aspect across the cross-section.

**Composition**: this is orthogonal to `Match Section Slopes` (Phase 10e). Setting Match `True` shrinks the Top/Bot sections to a tiny natural-factor range (texture-proportional), making the cosine remap operate over a small angle and have minimal visible effect. For visible Edge Angle effect, keep Match `False` (Phase 3q geometric split). The two phases solve different problems — Match fixes the slope discontinuity between sections, Edge Angle fixes the cell aspect *within* outer sections.

**Trade-off (Phase 10f postscript)**: turning Edge Angle ON introduces a *new* slope discontinuity at the section boundary — the cosine remap peaks at `sin(θ_boundary) × C`, which doesn't match Core's linear slope unless `top_v_span` is just the right size. With high `Arc 1 V Padding` shrinking `top_v_span` (e.g. 0.012 padding → 0.0025 top span), the cosine peak is ~6× smaller than Core's slope and the boundary becomes visibly discontinuous. The simpler resolution is usually **lower padding**: at `Arc 1 V Padding = 0.002` the natural halo spans are wide enough that linear-in-`v_around` already produces nearly-equal slopes everywhere (0.063 / 0.063 / 0.067 on a typical yarn). Reach for Edge Angle only when high padding is artistically necessary and the silhouette stretch needs explicit compensation.

---

### Rule 29 — Pick physical-rate match or visual range-match for concentric cylinders.

For two concentric cylinder surfaces (e.g. Arc 1 at radius `r_1` inside Arc 2 at radius `r_2`), there are two different notions of "match." To match physical cell size, the **physical V rate** (`tex_v` per BU around the strand) must be equal on both. To match the pattern rows the user sees across the silhouette, Arc 2 must sample the same V range as Arc 1 even though its physical circumference is wider.

Phase 3q's geometric `0.2 / 0.6 / 0.2` split solves this by construction: Arc 2 Core covers `60%` of `v_around` on `r_2 = 0.025`, giving physical width `0.6 × 2π × 0.025 = 0.0942 BU` — exactly equal to Arc 1's full v_around on `r_1 = 0.015` (`1.0 × 2π × 0.015 = 0.0942 BU`). With equal physical width and the same texture span, cells match.

`Match Section Slopes = True` (Phase 10e) *breaks* this equivalence — Arc 2 Core's `v_around` fraction becomes texture-proportional (not the fixed `0.6`), so its physical width drifts from Arc 1's. With Match ON and any non-trivial yarn V layout, Arc 2 cells appear larger in V than Arc 1's.

**Fix (Phase 10g, superseded by postscript/Phase 10h for the current visual target)**: when matched-section-slopes is on (or any other state that breaks the geometric equivalence), the first physically-correct option was a single linear V mapping on Arc 2 with **span scaled by `r_2 / r_1`**, centered on the padded core midpoint:

```text
tex_v(v_around) = mid_padded + (v_around − 0.5) × span_padded × (r_2 / r_1)
```

Arc 2 will sample tex_v outside `[Arc 2 V Min, Arc 2 V Max]` at the silhouette — for yarn scans this is the background region with alpha `0`, so it's invisible. For UV-checker tests it shows extra rows.

**Why**: Phase 10g (2026-05-17) — user observed Arc 2 cells looking "squished" (taller-narrower) vs Arc 1 with Match Section Slopes ON. Physical V rate was `1.21 tex_v/BU` on Arc 2 vs `1.84 tex_v/BU` on Arc 1 — 1.52× mismatch. The matched-rate mapping made both `1.84 tex_v/BU` exactly.

**Postscript (Phase 10g postscript, implemented in Phase 10h)**: "physical V rate match" produces equal cell *size* but unequal cell *count per silhouette* — Arc 2's wider cylinder fits more cells, which user perceives as Arc 2 being denser/squished. If the user actually wants equal *cells per silhouette* between the two arcs, the matching needs to be **range** match, not **rate** match: Arc 2 samples exactly Arc 1's V range with no `r_2/r_1` scaling. Cells are then physically larger on Arc 2 (proportional to cylinder radius) but the silhouette shows the same V content as Arc 1. Trade-off: Arc 2 never samples outside the padded core V range, so halo content doesn't appear on Arc 2's surface. Pick range-match for visual cell parity, rate-match for physical cell parity.

### Rule 30 — Automatic U scale must follow the visible padded V span, not the raw core span.

When `Arc 1 V Padding` expands the sampled core, the visible V span becomes:

```text
Arc1_V_Min_Padded = max(core_v_min - padding, arc2_v_min)
Arc1_V_Max_Padded = min(core_v_max + padding, arc2_v_max)
visible_v_span = Arc1_V_Max_Padded - Arc1_V_Min_Padded
```

Automatic `Material N Texture Scale U` must use `visible_v_span / AUTO_TEXTURE_SCALE_U_DENOMINATOR`. In the 2026-05-19 checkpoint, `AUTO_TEXTURE_SCALE_U_DENOMINATOR = 1.0`; `ARC1_V_AROUND_SPAN = 0.6` remains geometry/radius provenance, not the active auto-U denominator. If the formula keeps using raw `core_v_max - core_v_min`, the thread-length scale is calibrated to a V band the graph is no longer displaying.

**Why**: Phase 10h (2026-05-17) first moved the formula from raw core span to padded visible span. Phase 10u (2026-05-19) then removed the `/ 0.6` compensation from the active auto path after visual testing showed the direct web-to-Blender material looked more natural with `Material N Texture Scale U = visible_v_span / 1.0` and root `Texture Scale U = 1.0`.

---

### Rule 31 — Store U after the visible curve deformation, and scale stride by the same length ratio.

If a curve branch uses `Set Position` to create the visible over/under bend, do not store final texture U before that node. `Spline Parameter` and `Spline Length` only describe the geometry at the store node's input. Storing `u_along` before `PW Warp/Weft Set Position` measures the straight/pre-bend draft path, then the rendered curve becomes longer afterward; checker columns drift at Arc 1 / Arc 2 boundaries even when `uv_scaled.x` appears numerically consistent for matching pre-bend samples.

The fix is a pair:

```text
Set Curve Normal -> Set Position -> Store Warp/Weft U -> UV Offset U
U Stride Post-Bend Ratio = U Stride socket × Warp/Weft Length Ratio
```

**Why**: Phase 10i (2026-05-17) — the red-line viewport check showed along-thread columns still slipping after the visible-span U fix. Graph inspection showed `Store Warp U` / `Store Weft U` were upstream of `PW Warp/Weft Set Position`, while the amplitude bend happened downstream. Moving the stores after `Set Position` made evaluated `u_along` reach `1.075270` on the current swatch, matching the extra post-bend path length. Multiplying the per-strand stride by the same contextual length ratio keeps the spool offset in phase with the new U length.

**Do not confuse this with `UV Random U`.** Random U is a variation offset. This rule is about where the deterministic thread-length coordinate is measured.

---

### Rule 32 — For two visible offset shells, transfer U by same strand, not by raw screen projection.

Arc 1 and Arc 2 can have identical `uv_scaled.x/y` at the same `u_along` and `v_around` and still look shifted in the viewport. They are two different surfaces: Arc 2 has a larger radius/depth, so a point on Arc 2 projects to a different top-view X/Y location than the centerline coordinate that generated its U. If the artist is judging alignment with red lines in screen space, solve the screen-projected difference directly.

Phase 10j tried a projected-axis correction for Arc 2:

```text
axis_delta = projected_surface_axis - centerline_axis
u_correction = axis_delta / straight_length * UScale
```

That attempt was reverted because the texture became heavily distorted. The lesson still stands, but the failed implementation matters: a naive top-view projected-axis term is not enough for this swept, curved, layered geometry. It does not account for the actual visible face, interpolation across the swept profile, camera projection, or occlusion relationship between Arc 1 and Arc 2.

Phase 10k fixed the same symptom by transferring only the U component from Arc 1 to Arc 2, grouped by physical strand:

```text
pw_strand_id = curve index on warp, curve index + 10000 on weft
sampled_u    = Sample Nearest Surface(Arc 1 U, Group ID = pw_strand_id)
uv_scaled.x  = is_sub_strand ? sampled_u : original_u
```

Do not run nearest-surface transfer ungrouped. The first ungrouped preview sampled neighboring strands and created the same kind of beige/distorted strips as the projected-axis branch. Also keep V independent: Arc 2 still needs its own around-profile mapping, while U should follow the same physical strand.

**Why**: Phase 10j/10k (2026-05-17/18 local session) — after Phase 10h/10i, evaluated UVs matched but the screenshot still showed checker columns offset at the Arc 1/Arc 2 boundary. The projected correction was reverted from `Codex_ParametricWeave.pre-arc2-projected-u-fix-20260517_233330.blend`; Phase 10k then saved the grouped same-strand transfer after screenshot checks (`runtime/self_iter_strand_group_xfer_full.png`).

---

### Rule 33 — If matched Arc 2 V is active, skew that matched factor directly.

`Arc 2 Edge Angle Mapping` (Phase 10f) only affects the piecewise Arc 2 Top/Bot path. Once `Arc 2 Match Arc 1 V Rate` is ON, that path is bypassed by `PW MatchScale - Switch Arc2 V`, so toggling the old edge-angle nodes does not fix repeated-looking F/G rows in the active matched branch.

For the matched branch, keep the same V endpoints and replace the linear factor:

```text
theta       = 15deg + v_around × 150deg
projected_v = (cos(15deg) − cos(theta)) / (cos(15deg) − cos(165deg))
tex_v_arc2  = mid + (projected_v − 0.5) × matched_span
```

This is monotonic and no-repeat: the Arc 2 edge still lands on the padded min/max, but the halo-edge rows consume less vertical texture space in top view. A full `0deg..180deg` cosine ease was tested and was too aggressive; the saved `15deg..165deg` curve is the middle ground.

**Why**: Phase 10l (2026-05-18 local session) — U registration was fixed, but the user pointed out V-row repetition in the extra Arc 2 halo area. The old edge-angle toggle was bypassed by the matched branch. Phase 10l inserted `PW MatchProjV - *` into the active matched-V branch and verified the screenshot at `runtime/self_iter_v_projected_15deg_final.png`. Phase 10m supersedes the saved V shape; keep this rule as the diagnosis for why the old edge-angle toggle could not affect the active branch.

---

### Rule 34 — Project-from-view V needs both shape and phase.

If the visual target is "Project From View", do not apply one local-shell skew to every layer and call it done. Measure how the evaluated mesh projects in the target view:

```text
projected_v_arc1 = (1 - cos(pi * v_around)) / 2
projected_v_arc2 = v_around
```

Arc 1 needed the cosine factor because its top-view cross-section is circular. Arc 2 did not: in the evaluated mesh, the old matched branch's top-view coordinate was already linear in `v_around`, so applying the same cosine to Arc 2 was another local-shell remap rather than true project-from-view.

Also check the material phase. In Phase 10m, the matched active V band `0.47059187..0.52844101` was being multiplied by the checker material's `12x` V scale, so it crossed a repeat boundary and showed a G/H-to-A wrap. Setting `Texture Offset V = 0.029408127` moved that matched band to `0.50000000..0.55784911`, inside one tile. Phase 10n updates the saved state again for the full Arc 2 halo path; see Rule 35.

**Why**: Phase 10m (2026-05-18 local session) — the user clarified that the desired result was literal top/camera project-from-view continuity across R1/R2, not another `UV Random U` or Arc 2-only skew. The saved screenshot for this intermediate state is `runtime/self_iter_v_phase10m_final_projected_phase_aligned.png`.

---

### Rule 35 — When Arc 2 needs halo texture, keep matched V rate off.

`Arc 2 Match Arc 1 V Rate` is useful only when the goal is to make both arcs display the same padded Arc 1 core range. It is wrong for the final full-halo yarn contract because it prevents Arc 2 from sampling the extra texture outside Arc 1's core.

Current saved state:

```text
Arc 2 Match Arc 1 V Rate = False
Arc 2 V source           = PW Band - Arc2 V  # Top/Core/Bot piecewise path
Texture Offset V         = 0
```

That gives this evaluated V run:

```text
Arc 1/R1: 0.50250685 .. 0.56035596  # checker 12x phase 0.030 .. 0.724
Arc 2/R2: 0.50000006 .. 0.56382984  # checker 12x phase 0.000 .. 0.766
```

The core still lines up visually with Arc 1, but Arc 2's extra Top/Bot halo now owns the extra yarn/thread texture area instead of repeating the Arc 1-covered core. The previous checker phase offset remains useful history for UV-checker debugging; the approved direct-material checkpoint returned the saved offset to neutral.

**Why**: Phase 10n (2026-05-18 local session) — the user rejected the Phase 10m result because Arc 2's ends were still stretched/repeated. The issue was not U randomization; the active matched V branch was conceptually the wrong source for a core-plus-halo texture flow. Saved preview: `runtime/self_iter_v_full_arc2_piecewise_phase_repin.png`.

---

### Rule 36 — Restoring Arc 2 piecewise V means restoring masks and destinations together.

Matched-review mode can hide stale piecewise wiring because `PW Band - Diff` bypasses `PW Band - Arc2 V`. When returning to the real Arc 2 Top/Core/Bot path, verify all three layers:

```text
V source:      PW Band - Diff.Value <- PW MatchScale - Switch Arc2 V.Output
Section masks: IsTop threshold = Split Minus, IsBot threshold = Split Plus
Destinations:  Top  Arc 2 V Min -> raw Arc 1 V Min
               Core raw Arc 1 V Min -> raw Arc 1 V Max
               Bot  raw Arc 1 V Max -> Arc 2 V Max
```

For the current R1/R2 setup, `Split Minus/Plus = 0.2/0.8` because `r1/r2 = 0.015/0.025 = 0.6`. That center 60% of the wider R2 shell is the R1-equivalent core interval; the two 20% outer intervals are the additional R2 top/bottom shell area.

Also reconnect the section-aware U multiplier when the full piecewise V path is active:

```text
PW U - Per Section Multiplier.input[1] <- PW U - Section Ratio.Value
```

Otherwise the V rows are assigned correctly, but the halo texture aspect is still wrong.

**Why**: Phase 10s (2026-05-18 local session) — Phase 10r correctly forced Arc 1/Arc 2 equal-span review, but the dormant Arc 2 branch still had folded-midpoint masks from earlier experiments. Reconnecting only the final V source would have brought back a broken no-core piecewise map. The saved fix repaired the masks, V destinations, active switch state, and U section ratio together.

---

### Rule 37 — Free-flow halo V should extrapolate from the core seam, not snap to Arc 2 texture edges.

When Arc 2's top/bottom halo strips are endpoint-fitted to `Arc 2 V Min/Max`, the texture rows are forced to consume exactly the available physical strip. If the halo texture span and physical strip do not agree, the result reads stretched or over-controlled.

For a freer visual flow, keep the radius-owned split and extrapolate from the raw core seam using the core V slope:

```text
core_v_slope = (raw Arc 1 V Max - raw Arc 1 V Min) / (Split Plus - Split Minus)

top_outer_v = raw Arc 1 V Min - core_v_slope * Split Minus
bot_outer_v = raw Arc 1 V Max + core_v_slope * (1 - Split Plus)

Arc2 Top:  top_outer_v -> raw Arc 1 V Min
Arc2 Core: raw Arc 1 V Min -> raw Arc 1 V Max
Arc2 Bot:  raw Arc 1 V Max -> bot_outer_v
```

Then the top/core/bottom V slope is the same everywhere, so the U section ratio should evaluate to `1.0`. Do not leave old endpoint-fit section slopes driving U, or the debug attributes and texture aspect will disagree with the new V mapping.

**Why**: Phase 10t (2026-05-18 local session) — user pointed out that Arc 2's top and bottom should be allowed to flow outward from the core instead of snapping the UV edge to the texture edge. The saved graph now uses `PW HaloFlow - *` nodes for top/bottom outer V and reports ratio `1.0` across Arc 1 and all Arc 2 sections.

---

### Rule 38 — Drawdown-driven strand bend uses MODULO across `Draft Rows`; non-1/1 patterns visibly break.

> Replaces an earlier version of Rule 38 (2026-05-26) which incorrectly blamed `UV Random U`. UV Random U is at most a cosmetic exaggerator; the real bug is in the face-index math. See [phase_log.md Phase 10v](phase_log.md#phase-10v--diagnose-arc-2-looks-wrong-on-simple-twill-no-graph-or-code-changes) for the full retraction and evidence.

The strand bend Z offset is sampled per curve point from the drawdown:

```text
PW Draft Warp Row Mod    = (Index in Curve) % Draft Rows         <-- BUG
PW Draft Warp Col Mod    = (Curve Index)    % Draft Columns
PW Draft Warp Face Index = Warp Row Mod × Draft Columns + Warp Col Mod
PW Draft Warp Sample.Index = Warp Face Index
PW Draft Warp Sign = cell_code × 2 − 1
Math.005           = Sign × Amplitude × 0.5
Combine XYZ.002.Z  = Math.005
Set Position.Offset = Combine XYZ.002.Vector                     applied BEFORE Resample Curve
```

When `Weft Threads ≠ Draft Rows`, the strand's `Index in Curve` runs `0 .. Weft Threads − 1`, but the modulo wraps it `Weft Threads / Draft Rows` times across the drawdown. The strand "sees" each drawdown row `Weft Threads / Draft Rows` times instead of once.

The correct mapping (for a curve with `N` points sampling a drawdown with `R` rows) is integer division:

```text
row = floor(Index_in_Curve × R / N)
```

Equivalent: make the warp curve emit exactly `Draft Rows` points (and the weft curve exactly `Draft Columns` points), and keep modulo.

**Why plain weave hides it**: the buggy mapping produces an ultra-high-frequency square wave (e.g. 40 cycles/strand at 80 wefts × 20 rows). The profile sweep + cross-section averaging smear it to ~flat, which happens to look indistinguishable from a true plain weave with very small amplitude.

**Why simple twills break visibly**: 2/2 twill's drawdown column sequence `1,0,0,1,1,0,0,1,...` combined with the modulo wrap produces a `+, -, -, +` square wave at 4-point period — slow enough that the profile sweep does *not* average it out, but fast enough that each drawdown cell is chopped into 4 alternating sub-bumps. Adjacent strands' Arc 2 silhouettes overlap through those sub-bumps, creating the crescent/moon-shaped inverse-geometry overlap users report as "the texture scale changed" or "looks very wrong".

**Why `Over Count` / `Under Count` cannot help**: those Surface-panel sockets are dead in the current graph (Phase 10v Observation 1 — toggling `1 → 2 → 4` produced byte-for-byte identical strand centerline Z). The drawdown is the only place the over/under sequence is communicated to the geometry.

**Why `UV Random U` is not the cause**: it is a U-axis scramble. It does not touch Z. With it at `0.0`, twills still moon-overlap; with it at `1.0`, the moon overlaps additionally get random texture phases per lobe, which is cosmetic.

The rule:

- **Do not** lean on `Over Count` / `Under Count` to fix pattern-dependent geometry bugs — they are dead.
- **Do not** lean on `UV Random U` either — it does not affect strand Z.
- **Do** fix the row/col mapping inside `PW Draft Warp/Weft Row/Col Mod` to integer division, or rebuild the strand curves to have exactly `Draft Rows`/`Draft Columns` points each.
- Snapshot the .blend before changing those math nodes; Rule 22 still applies.

**Why**: Phase 10v final (2026-05-27 local session). Live MCP investigation:

```text
Test                                strand 0 mean Z range            interpretation
all-zeros drawdown                  flat at -0.0129                  no bend, sensible
all-ones drawdown                   flat at +0.0100                  no bend, sensible
plain weave (1/1)                   flat near -0.005                 buggy ultra-HF averaged out
2/2 twill                           ±0.014 oscillation, period ~4    buggy HF visible per cell
Over/Under = 2/2 with 2/2 twill     identical to Over/Under = 1/1   sockets are dead
Warp/Weft Threads = 20 (= Draft Rows) on 2/2 twill   bend less broken; still imperfect because Set Position acts on the unsampled curve
```

`PW Draft Warp Row Mod.operation = MODULO` is the precise misuse. Replacing with floor-divide based on point count fixes the high-frequency wrap.

---

## Open items (to revisit when relevant)

- **Protect the 2026-05-19 visual checkpoint.** Phase 10u is the approved baseline for direct web-to-Blender material preview. Any new Arc 2 split, padding, or U-scale experiment should start from a `.blend` backup and state whether it supersedes [../CHECKPOINT_2026-05-19.md](../CHECKPOINT_2026-05-19.md).
- **Internal switch-chain names still say "Core" / "Fiber"** (`PW Material Core V Min Select N`, etc.). Interface was renamed to Arc 1/2 in Phase 3d but internals weren't. Cosmetic.
- **Two-Set-Material-nodes architecture is fragile.** `Set Material` (one) was bypassed in the final geometry chain (no path to Group Output); `Set Material.001` is the only active one. Confusing for the artist — would simplify to one node with one interface input.
