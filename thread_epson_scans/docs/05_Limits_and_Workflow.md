# 05 — Limits, Gotchas, and Adding a New Yarn

## Hard limits

### Cycles texture cap (16384 px on any axis)

Cycles silently downsamples any texture larger than 16384 px on a single axis to 16384 — without warning. Several yarns scan to wider than that:

| Yarn | RGB width (preprocessed) |
|---|---|
| red_shiny | 17033 |
| white_red_t1 | 17033 |
| pragati_black_white | 13765 |
| white_red_t2 | 16259 |
| white_red_tile | 16112 |

`resize_for_cycles.py` writes Lanczos-downsampled `_max16384` copies into `bands_out/_resized/` for any oversized image. The Blender side loads the `_resized` file when present.

**Crucially, the procedural Scale U math always uses the TRUE pixel width** (`meta.image_size_px[0]`), not the loaded texture's pixel width. This is what keeps "1 image at 1600 DPI = N meters of physical yarn" correct even when the loaded image was downsampled. `build_batch_index.py` carries `image_width_px` directly from `meta.json`, untouched by resizing.

### Single shared Scale U for warp + weft

`Math.013.in[1]` reads from `PW U - Scale U Final`, a single value used for all strands regardless of orientation. The auto-scale formula uses `Warp Threads × Spacing` for the strand length. As long as `Warp Threads = Weft Threads`, that's the same as the weft straight length — no problem.

If you ever go non-square (say warp = 50, weft = 100), the weft strands will be sampled at the warp's Scale U, and the texture density on weft strands will be wrong by the ratio of counts. To fix, the chain would need to be split into separate warp/weft Scale U paths driven by the corresponding Compensated U attributes — not done.

### One Material 1..4 pool, currently all set to the same material

`blender_apply_yarn.py` writes the same Material into Material 1..4. If you want per-strand variation (alternating colors, different yarns for warp vs weft), modify the apply script to set them independently and adjust `Warp Length 1..4` / `Warp Material 1..4` (and weft equivalents) accordingly.

### Out-of-domain inputs

`band_segmenter.py` is built for **single yarn strand** scans on a uniform background. Inputs like `white_red_tile` (a fabric-tile photo, not a single thread) produce a meta.json with degenerate band ranges (core spanning nearly the whole image), which then renders as visual mush. The script does not currently flag this — easy follow-up: detect when `core_height / image_height > 0.8` and emit a warning.

### Texture Scale U interpretation

`Texture Scale U` is a multiplier on top of the procedural auto-scale, not a raw value:

- `Texture Scale U = 1.0` → procedurally physically correct (1 image-world-width per strand-image-world-width). For our weave scale, this comes out to ~14× tiling.
- `Texture Scale U ≈ 1 / auto_scale` (≈ 0.07 for current settings) → image fits exactly once per strand, no tiling.
- `Texture Scale U > 1.0` → tile more densely than physical density.

Adjust per-render based on the visual outcome you want. There's no "right" value — it's an aesthetic tradeoff. See the Open Questions section for the larger discussion.

## Gotchas

### `uv_scaled` vs `UVMap`

Materials read the `uv_scaled` attribute, NOT `UVMap`. New materials authored from the shader editor must use `ShaderNodeAttribute(attribute_name='uv_scaled', attribute_type='GEOMETRY')`. Default UVMap reads (0,0) and the cloth comes out as one solid color.

### Mapping node — passthrough only

Material `ShaderNodeMapping` should be Location=(0,0,0), Scale=(1,1,1), Rotation=(0,0,0). Older materials (e.g. `Sample_10`) had `Scale.x = 0.4` and `Scale.y = 1.0, Location.y = 0.5` to compensate for the GN's prior simple Scale U / V — those compensations are wrong now that the GN does its own scaling. `blender_apply_yarn.py` always writes a fresh passthrough mapping.

### Alpha must be connected for the fiber-halo look

Without `Image Texture(alpha) → BSDF.Alpha`, the fiber halo regions render as opaque colored fibers and the woven cloth looks more like a solid weave. With it connected, the halo gives the wispy yarn look. The two prior failure modes:

- Alpha image colorspace was sRGB → too aggressive transparency. Fix: load alpha with `colorspace_settings.name = 'Non-Color'` (the script already does this).
- Material's transparency render method was the wrong mode → cloth went fully transparent in Cycles. Fix: `m.surface_render_method = 'DITHERED'` (Blender 4.2+).

### Modifier defaults vs modifier values

Setting a default on an interface socket only affects newly-created modifiers. Pre-existing modifiers keep whatever value they had. If you change a default and don't see it reflected in the viewport, you need to write the value into `mod[socket_id]` for every existing modifier (or recreate the modifier).

## Adding a new yarn — full workflow

1. **Capture the scan** at 1600 DPI on the Epson, save as TIFF. Yarn should run roughly horizontal or vertical against a clean paper background — orientation auto-detect handles either.

2. **Run yarn_pipeline** (preprocess + seamless + alpha):
   ```bash
   python Scripts/yarn_pipeline.py path/to/NEW.tif preproc_out/
   ```

3. **Run band_segmenter**:
   ```bash
   python Scripts/band_segmenter.py preproc_out/NEW_seamless.png alpha_out/NEW_alpha.png bands_out/NEW/
   ```
   Inspect `bands_out/NEW/overlay.png` — the green/red lines should sit cleanly at the core/fiber boundaries. If they're way off, the alpha matte is probably bad (re-run alpha_pipeline with a different `--preset`).

4. **(if scan > 16384 px)** Run the resizer:
   ```bash
   python Scripts/resize_for_cycles.py
   ```

5. **Refresh the batch index**:
   ```bash
   python Scripts/build_batch_index.py
   ```

6. **In Blender**, edit `YARN` at the top of `blender_apply_yarn.py` to your new yarn's folder name, then run it (Text Editor `Run Script`, or `exec(open('Scripts/blender_apply_yarn.py').read())` in the Python console).

7. **Tune `Texture Scale U` on the modifier** to taste. `1.0` is procedurally physical density. Drop towards `1 / (Threads × Spacing × Scanner Pixels Per BU / Image Width Px)` to get one image per strand.

8. **Render**: F12 for a single yarn, or run `blender_batch_render.py` to render every yarn into its own folder.

## Open questions / known unknowns

- **The "right" default for Texture Scale U** is genuinely ambiguous — physical density tiles densely at our weave scale; one-image-per-strand stretches obviously. We're keeping the procedural chain in place but defaulting the multiplier to 1.0; the user dials it per-yarn for now.
- **Roughness and normal maps from band_segmenter** are written but not sampled by the material. Wiring them in requires a per-band sampling chain in the shader (or pre-baking into a single combined map).
- **Twist period from the FFT** is in `meta.twist.twist_period_px` but not consumed anywhere downstream yet. Could be used to align rendered twist phase across adjacent strands, or to rotate the V coordinate for procedurally generated extra twist on top of the photographed twist.
- **Eevee Next vs Cycles parity** — both render with the current pipeline, but Eevee Next does not honor the alpha matte through volumetrics or transmission. If we ever add SSS to the BSDF, expect divergence.
