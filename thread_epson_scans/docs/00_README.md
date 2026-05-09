# Yarn-to-Weave Pipeline — Documentation Index

End-to-end: turn a high-DPI scan of a single piece of yarn into a Blender material that maps that yarn photorealistically onto the **Parametric Weave knotty** geometry node group's two-arc cross-section, then render the woven fabric.

The pipeline lives in two adjacent folders inside `thread_epson_scans/`:

```
thread_epson_scans/
├── Scripts/    # all preprocessing + Blender automation scripts
├── docs/       # this folder
├── *.tif       # raw Epson scans (1600 DPI)
├── preproc_out/  alpha_out/  bands_out/   # per-stage outputs
└── bands_out/_resized/   # cycles-safe (≤16384 px) downscales
```

## Read in this order

1. **[01_Pipeline_Overview.md](01_Pipeline_Overview.md)** — what each stage does and how data flows from raw TIFF to a rendered woven cloth.
2. **[02_Preprocess_Scripts.md](02_Preprocess_Scripts.md)** — every script in `Scripts/`, what it consumes, what it emits, how to run.
3. **[03_Blender_Modifier_Reference.md](03_Blender_Modifier_Reference.md)** — every input socket on the GN modifier, what to feed it, where the value comes from.
4. **[04_GN_Architecture.md](04_GN_Architecture.md)** — the band-V remap (Arc 1 / Arc 2 piecewise) and the procedural Scale U chain we wired into the graph, with traces of the relevant nodes.
5. **[05_Limits_and_Workflow.md](05_Limits_and_Workflow.md)** — known limits, gotchas, and how to add a new yarn from scratch.

## TL;DR — adding a new yarn

```bash
# 1. Drop the raw TIFF anywhere readable, then preprocess + alpha + seamless
python Scripts/yarn_pipeline.py NEW.tif preproc_out/

# 2. Band-segment to produce meta.json with V-band boundaries + twist FFT
python Scripts/band_segmenter.py preproc_out/NEW_seamless.png alpha_out/NEW_alpha.png \
       bands_out/NEW/

# 3. (One-time) make a Cycles-safe downscale if the image > 16384 px
python Scripts/resize_for_cycles.py

# 4. Refresh the batch index Blender reads
python Scripts/build_batch_index.py

# 5. Inside Blender (Text Editor or MCP):
#       exec(open('.../Scripts/blender_apply_yarn.py').read())
#    or to render every yarn:
#       exec(open('.../Scripts/blender_batch_render.py').read())
```
