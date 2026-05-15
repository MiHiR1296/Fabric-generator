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

### Rule 12 — The 5 footgun sockets are additive, not absolute.

`Texture Scale V`, `Texture Offset V`, `Texture Side Flatten`, `Sub Texture Scale V`, `Sub Texture Offset V` are **additive deltas** to the main strand's mapping when applied to sub-strand geometry.

| Socket | Pinned value | Meaning of the pin |
|---|---|---|
| `Texture Scale V` | 1.0 | V scale = main strand × 1 (no change) |
| `Texture Offset V` | 0.0 | No additional V shift |
| `Texture Side Flatten` | 0.0 | Cross-section maps as flat ribbon (no cylindrical projection compensation) |
| `Sub Texture Scale V` | 0.0 | Sub-strand V scale delta = 0 → aligned with main |
| `Sub Texture Offset V` | 0.0 | Sub-strand V offset delta = 0 → aligned with main |

Setting `Sub Texture Scale V = 1` does **not** mean "use the same V scale as main"; it means "main + 1", which **doubles** the Arc 2 V mapping and visibly misaligns the fiber bands. Easy to break in a one-line "tweak".

Inherited from the older Arc 2 sub-strand documentation. Always push these defensively even though they're the .blend's defaults.

---

### Rule 13 — Piecewise Map Ranges must be continuous at their split boundaries.

Correct V values and correct split fractions are not enough. The Map Range direction also has to match the coordinate direction. Phase 3k found Arc 2 had the right three sections and the right four V endpoints, but each section ran the wrong way for `v_around`.

For this graph, `v_around=0` is the top outer edge and `v_around=1` is the bottom outer edge. Arc 2 must therefore be continuous as:

```text
Arc2 Top:  Arc 2 V Max -> Arc 1 V Max
Arc2 Core: Arc 1 V Max -> Arc 1 V Min
Arc2 Bot:  Arc 1 V Min -> Arc 2 V Min
```

When editing any piecewise texture map, write the expected boundary values first, then verify each adjacent pair meets at the same V.

---

### Rule 14 — If UVs are stored before Fit To Space, per-material U carries the fit correction.

`Parametric Weave knotty` stores the texture coordinate before the `Fit To Space` modifier scales the visible fabric to the Space plane. The graph's raw U length is therefore `Warp Threads * Spacing`, not the final viewport size.

For scan-driven yarns, root `Texture Scale U` stays neutral and the setup/render script pushes the correction into each `Material N Texture Scale U`:

```text
root_texture_scale_u = 1.0
material_texture_scale_u = (max(Space X/Y) * Fill Ratio) / (Warp Threads * Spacing) * texture_u_calibration
Material N Texture Scale U = bandMeta.texture_scale_u * material_texture_scale_u
```

`texture_u_calibration` defaults to `0.1` after Phase 4d. That means the fit-aware U scale is divided by ten by default because the user validated that behavior across three versions. Keep treating it as a calibration factor, not a Blender-unit fact.

Do not put this correction on root `Texture Scale U`; it is global and will hide per-material differences. Root U should read `1.0` unless we intentionally add a global artistic override.

---

### Rule 15 — Use Linear sampling for photographic yarn previews.

Generated direct material nodes should use `Linear` interpolation for scanned yarn textures. `Closest` is useful for debugging texels, but it makes Cycles-safe downscales, especially tall-but-thin yarn strips such as `16384 × 144`, look visibly pixelated in the live viewport.

Keep the Cycles cap decision separate from the sampling decision: the cap protects Blender/GPU limits; interpolation controls how the preview is filtered.

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

## Open items (to revisit when relevant)

- **Arc 2 geometry split needs visual approval.** Phase 3q now computes/stores the split from Arc 1/Arc 2 profile radii (`0.015 / 0.025 -> 0.6`, splits `0.2 / 0.8`). Confirm in the live viewport before turning this into a polished final graph.
- **Internal switch-chain names still say "Core" / "Fiber"** (`PW Material Core V Min Select N`, etc.). Interface was renamed to Arc 1/2 in Phase 3d but internals weren't. Cosmetic.
- **Two-Set-Material-nodes architecture is fragile.** `Set Material` (one) was bypassed in the final geometry chain (no path to Group Output); `Set Material.001` is the only active one. Confusing for the artist — would simplify to one node with one interface input.
