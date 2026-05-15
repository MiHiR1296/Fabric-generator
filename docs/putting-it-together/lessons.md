# Lessons

> **Read this if**: you are about to make a non-trivial change and want to avoid the traps we already paid for. Read before changing anything cross-app.

> Each lesson has the **Rule**, the **Why**, and (where useful) a **Concrete example** with file paths. Add lessons the same hour you find them — drift starts when you don't.

---

## On the data contract

### Rule 1 — The file on disk wins. Always.

If a metadata field describes a file's intrinsic property (size, channel count, hash), the producer reads it from the file, not from upstream metadata. Never trust whatever previous step said about it.

**Why**: `yarn_library/<id>/metadata.json` had `image_size_px = [46220, 301]` while the actual `rgba.png` was `42124 × 301`. The upstream `export_metadata.json` had drifted in a prior session. Anything downstream that trusted the metadata got 9.7 % wrong world-U length in Blender. Anything that opened the file got the right answer.

**Concrete fix** ([web/yarn_library.py:save_to_library](../../../web/yarn_library.py:288), 2026-05-13):
```python
# Wrong (trusts upstream):
esize = export_meta.get("export_size_px") or {}
image_W = int(esize.get("width") or 0)
if image_W <= 0:
    with Image.open(rgba_src) as im:
        image_W, image_H = im.size

# Right (file is truth):
with Image.open(rgba_src) as im:
    image_W, image_H = im.size
```

**Generalises**: any pipeline where stage N writes a file and stage N+1 records "what stage N wrote" — if N+1 ever gets re-run on its own, the recorded value can lie.

---

### Rule 2 — Producer pre-computes, consumer pushes.

If a value Blender needs is derived from other values, the producer (yarnseamless) computes it once and stores it in `metadata.blender.*`. The consumer (Fabric-generator-tryon) reads the field and pushes it to the socket. No math on the consumer side.

**Why**: `Image Width Px ÷ Scanner Pixels Per BU = texture_world_width_m` is a pixel-pitch conversion. If the consumer does this division, anyone who touches the consumer code can get it wrong. Anyone using a different DPI now has to either push two values + trust the divide, or special-case. Putting it in `metadata.blender.texture_world_width_m` makes the consumer code one line per socket and impossible to get wrong.

**Why this matters for "no DPI on the wire"**: once the producer has done the math, the consumer doesn't need to know about DPI. `metadata.dpi` exists only as provenance. The whole point: Blender never has to learn anything about scanner units.

**Concrete example** ([data_contract.md](data_contract.md) → "Derivations"):
```
texture_world_width_m = image_width_px / dpi × 0.0254
```
Done once in [web/yarn_library.py:save_to_library](../../../web/yarn_library.py). Pushed to the new `Texture World Width BU` socket by [backend/app/render_jobs.py](../../backend/app/render_jobs.py) (Phase 3 work).

**Generalises**: any unit conversion belongs to the producer. The consumer's only job is "field → socket".

---

## On the Blender file

### Rule 3 — The Arc 2 sub-strand sockets are an additive footgun.

`Sub Texture Scale V` and `Sub Texture Offset V` on `Parametric Weave knotty` are **additive deltas** applied only when `is_sub_strand = 1`. Setting `Sub Texture Scale V = 1` does NOT mean "use the same V scale as the main strand"; it means "use main scale + 1", which doubles the Arc 2 V mapping and visibly misaligns the fiber bands.

**Why**: We're inheriting this from the scan workflow ([fabric-update-node-documentation.md](../../docs/fabric-update-2026-05-09/fabric-update-node-documentation.md) was the warning). The naming feels like an absolute override; the math is additive. Easy to break in a one-line "tweak".

**Rule of practice**: for any scan-driven yarn, keep all five of these at their pinned defaults:
```
Texture Scale V       = 1
Texture Offset V      = 0
Texture Side Flatten  = 0
Sub Texture Scale V   = 0
Sub Texture Offset V  = 0
```
The consumer (`render_jobs.py`, Phase 3) should push these explicitly even though they're the file's defaults — defensive against someone tweaking the .blend.

---

## On the harness

### Rule 4 — Two installs in parallel, never sequence them.

`pip install -r requirements.txt` takes minutes (torch, opencv, simple-lama). `npm install` takes seconds. Run them at the same time as background tasks; do not sequence.

**Why**: it's 4 minutes vs 4 minutes 30 seconds, but more importantly the failure modes are independent — if pip is broken on this machine, you don't want to find out after waiting for npm.

**Concrete**: Phase 1 setup used two parallel `run_in_background` Bash calls. Both completed cleanly. No need to babysit.

---

## On documentation

### Rule 5 — Write the doc entry the same hour you make the change.

Every phase in [phase_log.md](phase_log.md) is written before the next phase starts. Every cross-app contract change is reflected in [data_contract.md](data_contract.md) before the code that depends on the new shape ships. Every gotcha that bit us becomes a lesson here.

**Why**: drift is fast and silent. The yarnseamless docs were written this way ([yarnseamless/docs/lessons.md](../../../docs/lessons.md) Lesson 15) and the result is a folder you can hand to a new contributor and have them productive within an hour. The cost is ~30 minutes of writing per phase. The return is anyone reading these can re-derive every decision.

**The trap**: "I'll write it up later." Three phases pass and the why is gone — you remember the what (it's in the code) but not the why (it's not).

---

### Rule 8 — Skipped features must be documented with their "why" and "when to revisit".

When you intentionally don't port a feature, write down (a) what it does, (b) why you skipped it, (c) when you'd add it back, and (d) the rough cost. Otherwise it shows up later as "should we have brought this in?" and you spend the same hour re-deciding.

**Why**: Phase 2b skipped three things — the SAM2/ViTMatte single-image matting routes, three batch helpers, and FastAPI lifespan warm load. Each one is a defensible decision, but in three months "why don't we have batch processing?" is a real question we'll forget the answer to. The phase_log entry now records the cost/benefit so future-us reads it once and stops asking.

**Concrete shape** (used in [phase_log.md](phase_log.md) Phase 2b → "Skipped (intentional) — with rationale"):

```
### N. <feature name>

**What it does**: …
**Why skipped**: …
**When to revisit**: …
```

Three sentences each is plenty. The point is to record the decision, not to justify it at length.

**Generalises**: any pull request whose diff is conspicuously smaller than "the obvious complete version" should explain in the description what's missing and why. A reviewer asking "why didn't you also do X" is a sign the rationale wasn't written down.

---

### Rule 7 — Port by transcription, not paraphrase, for delicate compute code.

When porting code where correctness depends on subtle algorithmic decisions (alpha math, canvas geometry, mask construction, inscribed-rectangle search, etc.) — copy it line-for-line. Replace only the API boundary (request/response shape, error path, model loader). Do not "improve" or "Pythonify" the body.

**Why**: the alpha pipeline math has had ~12 phases of iteration (see yarnseamless `docs/timeline.md`). Each phase fixed a subtle bug — the black-fill canvas trap, the achromatic-F prediction, the per-thread α<30 cutoff, the wraparound slice. A "rewrite" pulls all that history into the diff and risks losing details quietly. A "transcription" keeps every decision; the only diff is the API.

**Concrete**: `yarnseamless_routes.py` Phase 2b. 870 LOC ported in one pass, faithful at the byte level for handler bodies. Verification: a real 5 MB scan went from `/upload` → `/process` to all 4 leveled+α+F+band-viz PNGs in 32 s on MPS with byte-identical detection peaks `[551, 1202, 1895, 2534]` to what yarnseamless `web/lama_server.py` would have produced.

**Three things that supported this**:
1. **Read in chunks**, don't skim — 400 LOC at a time, see every helper.
2. **Don't touch the compute modules**. The `multithread_flow/__init__.py` `sys.path` trick (Rule 6 territory) preserves their bare-name imports so they need zero edits.
3. **Run the canonical fixture test**. The github repo had `4threads_sprayblackbg.jpg` as a golden test scan — pull it and run it before declaring the port done. Catches "I forgot a helper" failures cheaply.

**Generalises**: any time you find yourself wanting to "clean up while porting" — don't. Land the faithful port first, in its own logical phase, with verification. Refactor in a separate, isolated phase that can be reverted without losing the port.

---

### Rule 6 — Verify every transitive import on first checkout.

When adopting a Python service from another machine or repo, run a one-line smoke import for every module the entrypoint references **before** writing any new code against it. If anything is `ImportError`, stop and locate the source before proceeding.

**Why**: yarnseamless's `web/lama_server.py:31` does `sys.path.insert(0, "../multithread_flow")` and imports `split_threads`, `alpha_pipeline`, `solid_band` from there. The folder didn't exist on the local machine on 2026-05-13 even though the entrypoint script was present and the saved `yarn_library/` had output from that pipeline (processed on a different machine state we no longer had). We almost started "porting" code we didn't have. The 60-second smoke import caught it.

**Concrete check** before any port / integration work:

```bash
cd <yarnseamless>/web && python -c "
import sys; sys.path.insert(0, '../multithread_flow')
import split_threads, alpha_pipeline, solid_band, dual_alpha_pipeline, yarn_pipeline, yarn_library
print('imports OK')
"
```

If that doesn't print "imports OK", do nothing else until it does.

**Generalises**: any time you inherit a multi-folder Python service, list every module the entrypoint touches (search for `import X` / `from X import Y`) and verify each resolves. Save 30 minutes; lose hours otherwise.

---

## Open items (to revisit when relevant)

- **Cycles 16384 cap**: kept as the default in [backend/app/yarn_assets.py:_ensure_cycles_safe_texture](../../backend/app/yarn_assets.py). Override via `CYCLES_MAX_TEXTURE_DIM`. If we ever switch to CPU-only rendering for a class of jobs, raise the cap there. Tile-wise the visible loss is invisible because the texture repeats; the cap is about GPU VRAM and texture-array limits, not artistic fidelity.
- **MCP port**: 9876 not 9875. Pinned in the Makefile. If your Blender ever runs on a different port, `BLENDER_PORT=<n> make backend-dev`.
- **No auth on any endpoint**. Localhost only. If this ever leaves localhost, treat it as a project-blocking item.

---

## On editing the Blender node graph from Python (Phase 3d–3g)

These rules came out of the work documented in [../BlenderFixes/](../BlenderFixes/). Promoted here because they're cross-app concerns — every backend dev who ever pushes a value to Blender will eventually run into them.

### Rule 11 — Interface socket renames preserve wiring; deletions do not.

`it.name = "New Name"` on an `interface.items_tree` socket is non-destructive: Blender identifies sockets by stable `identifier` (e.g. `Socket_61`), and internal connections reference by identifier. `interface.remove(item)` destroys those links.

Phase 3d renamed 68 V-band sockets in one pass with zero wiring breaks. Phase 3f then *removed* 5 truly-dead globals — safe only because the audit (Rule 13) confirmed no Group Input was consuming them.

See [../BlenderFixes/lessons.md](../BlenderFixes/lessons.md) Rule 1 for the diagnostic pattern.

### Rule 12 — Three-layer bugs are normal. Trace producer, wiring, and naming together.

When a graph's interface names look right but the values look wrong, don't assume the producer is wrong in isolation. Phase 3e's underlying bug had three layers: (a) producer wrote inner-edge V values, (b) graph wired Arc 2 to switch chains carrying the wrong band's data, (c) interface socket names were ambiguous. Fixing only one layer would have left a different bug visible.

Diagnostic order: print actual modifier values → walk graph from Group Output backwards → confirm producer key → Switch chain → Map Range form a consistent triple.

See [../BlenderFixes/lessons.md](../BlenderFixes/lessons.md) Rule 2.

### Rule 13 — Audit Group Input consumers across ALL nodes before removing interface sockets.

A socket without a Group Input output link is genuinely dead. `Parametric Weave knotty` has **13 Group Input nodes** (one per logical section); checking just the first one gives wrong results. Loop all of them.

Phase 3f found 5 dead globals (`Image Width Px`, `Image Arc 1/2 V Min/Max`) by enumerating output links across all 13 Group Inputs and subtracting from the interface socket set.

See [../BlenderFixes/lessons.md](../BlenderFixes/lessons.md) Rule 3 for the audit snippet.

### Rule 14 — A gate inside a MULTIPLY_ADD silently invalidates upstream fixes.

`PW Band - Band V` is `is_sub_strand × (Arc2 V − Arc1 Map) + Arc1 Map`. Phase 3e's Arc 2 rewire was correct but invisible until Phase 3g pinned `Sub Strand Enable` — main-strand geometry had `is_sub_strand = 0`, so the whole Arc 2 computation got multiplied to zero.

Generalises: when an upstream fix doesn't change the rendered output, trace forward to the next conditional / multiplicative node. Specifically check `MATH:MULTIPLY_ADD` with a constant or attribute multiplier, `SWITCH` nodes with default-False inputs, `MIX` nodes with hidden `Fac`, `NamedAttribute` reads with undeclared attributes.

See [../BlenderFixes/lessons.md](../BlenderFixes/lessons.md) Rule 4.

### Rule 15 — Set the modifier's NodeSocketMaterial input, not the Set Material node's default.

When a `Set Material` node's `Material` input is link-driven from a Group Input (as `Material 1` in `Parametric Weave knotty` is), setting `node.inputs["Material"].default_value = mat` does nothing — the link wins. Set the modifier's interface value instead: `mod["Socket_61"] = mat`.

See [../BlenderFixes/lessons.md](../BlenderFixes/lessons.md) Rule 7.

### Rule 16 — `maybe_set_modifier_input` not `set_modifier_input` for socket names that vary across .blend revisions.

Use the tolerant setter (silently skips missing sockets) for anything that isn't guaranteed across all .blend revisions in active use. Reserve the strict setter for sockets we know must exist (`Draft Object`, `Draft Columns`, `Draft Rows`, `Spacing`).

Phase 3f's panel cleanup removed sockets the script was previously pushing — without the tolerant setter every headless render after the cleanup would have crashed.

See [../BlenderFixes/lessons.md](../BlenderFixes/lessons.md) Rule 8.

### Rule 17 — Fit-aware U scale belongs on per-material U, not root U.

The measured texture width comes from yarn metadata, but the U fit correction depends on live scene geometry: `Space` dimensions, `Fill Ratio`, `Warp Threads`, and `Spacing`. A metadata-only band push cannot safely know that whole context.

For `Parametric Weave knotty`, compute the correction during setup/render sync and apply it to each `Material N Texture Scale U`:

```text
root_texture_scale_u = 1.0
material_texture_scale_u = (max(Space X/Y) * Fill Ratio) / (Warp Threads * Spacing) * texture_u_calibration
Material N Texture Scale U = bandMeta.texture_scale_u * material_texture_scale_u
```

`texture_u_calibration` defaults to `0.1` after Phase 4d. That divides the fit-aware U scale by ten by default because the user validated that behavior across three versions. Keep it as a calibration factor, not a Blender-unit fact.

Keep root `Texture Scale U = 1.0`; it is global and will make multi-material swatches impossible to scale independently.

### Rule 18 — Nearest-neighbor texture sampling is a diagnostic mode, not the default preview.

Scanned yarn strips are photographic inputs. If the generated Blender material uses `Closest`, the live viewport can look pixelated even when the metadata and UVs are correct, especially after the Cycles-safe max-dimension downscale.

Default generated yarn material nodes to `Linear`; only use `Closest` temporarily when inspecting exact texel boundaries.

### Rule 19 — Physical scale needs source-scan corroboration.

Raw scanner files may preserve embedded DPI; processed/export PNGs may not. Save-to-library now records `metadata.physical_scale` so the UI/backend can tell whether declared DPI was corroborated by a source scan or only carried through export metadata.

Treat `physical_scale.confidence = high` as scanner-backed. Treat `metadata_only` as usable but not independently validated.

### Rule 20 — Do not use texture V span as a substitute for generated Arc 2 area.

Yarn metadata can provide the destination rows to sample: core V min/max, Arc 2 outer V min/max, and measured fiber extents. But the amount of Arc 2 geometry that should be core vs halo is a geometry-domain question.

Phase 3p confirmed the centered split still derived `Split Minus/Plus` from texture V-span ratio. Phase 3q replaced that with a first geometry-owned test: Arc 1 radius `0.015`, Arc 2 radius `0.025`, core fraction `0.6`, split `0.2 / 0.8`. Metadata now maps each interval to the correct sampled V rows; it does not decide the interval size.

### Rule 21 — Read back evaluated attributes, not just sockets.

The modifier panel can show the value you expect while a stale or bypassed node chain evaluates something else. Phase 3q added debug attributes for Arc 2 split math so the live mesh can be checked directly:

```text
arc1_radius_geometry
arc2_radius_geometry
arc2_core_frac_geometry
arc2_core_split_min
arc2_core_split_max
```

For Blender geometry-node fixes, one evaluated mesh readback is worth a page of socket inspection.

### Rule 22 — Live setup push must rerun when render settings change.

The live Blender panel can become stale even when render output is correct. `Material N Texture Scale U` depends on zoom/spacing/fillRatio/textureUCalibration, so the Web UI live-push signature must include `draft.renderSettings`, not only yarn bindings and colors.

Phase 4j added render settings to the debounced live-push signature after the modifier panel kept showing `0.5` while the current calibrated setup should have pushed `0.05`.

### Rule 23 — Arc 2 transparency can come from real alpha data.

For current scan-driven yarns, Arc 2 maps to the outer halo rows. Those rows are sparse by design: sampled alpha stats showed core rows around `203–213` average alpha, but halo rows around `20–29`. If Arc 2 looks transparent, first inspect the alpha distribution before assuming the Blender mapping is wrong.

### Rule 24 — Treat model weights and debug sessions as environment, not source.

The product needs heavyweight local artifacts: `big-lama.pt`, raw scan uploads, inpaint canvases, detection overlays, Blender autosaves, and render/debug jobs. They are important for development but poisonous in normal Git history.

Keep the raw model outside Git and point the backend at it with `BIG_LAMA_MODEL_PATH` or `LAMA_MODEL`. Keep `runtime/debug/` ignored. Use Git LFS only after the GitHub repository enables it; otherwise use release assets or external storage for any future heavyweight `.blend` / model artifact that truly needs to travel with a branch.
