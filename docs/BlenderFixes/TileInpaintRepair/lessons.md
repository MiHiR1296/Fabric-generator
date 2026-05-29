# Lessons - tile inpaint repair

> **Read this before** adapting the yarn inpainting flow to repair Blender tile seams.

Each lesson follows the Rule, Why, and Concrete example shape used by the main BlenderFixes docs.

---

## Rule 1 - Repair both the visible center seam and the wraparound seam.

**Why**: A `2 x 2` paste-only preview has a cross in the center, but the final texture's outer edges are also future seams. If only the center is repaired, tiling the repaired image can reveal a new border at the image boundary.

**Concrete example**: After inpainting the center cross, roll the image by `width / 2` and `height / 2`. The old corners meet at the center. Inpaint that cross too, then roll back.

---

## Rule 2 - Prefer procedural masks before AI seam detection.

**Why**: The tile seam coordinates are known exactly from the paste layout. Detection adds uncertainty and can miss soft seam halos.

**Concrete example**: For a `2400 x 2400` image made from four `1200 x 1200` tiles, the first mask is simply a vertical band around `x = 1200` plus a horizontal band around `y = 1200`.

---

## Rule 3 - Keep the first proof image repair-only.

**Why**: The goal is to determine whether inpainting can repair the rendered cross. Mixing in Blender graph edits, camera changes, guard threads, and seam repair at the same time makes the result hard to interpret.

**Concrete example**: Use `NormalCamera_Ortho2975_PasteOnly_2x2_1200.png` as the first input, save masks/intermediates, and do not save any `.blend` changes.

---

## Rule 4 - Avoid full-image LaMa calls until memory behavior is known.

**Why**: A full `2400 x 2400` inpaint can be slow or memory-heavy, especially on MPS. The visible damaged area is a narrow cross, so the model does not need to see the whole image in one call.

**Concrete example**: Crop a vertical seam window and horizontal seam window, inpaint those chunks, then paste them back. If the intersection looks odd, inpaint the center square as a small third crop.

---

## Rule 5 - Do not confuse seam repair with graph-level tileability.

**Why**: Inpainting is a practical post-render repair layer. It can hide the current rendered edge, but it does not create a procedural boundary contract for draft state, yarn U phase, random fields, or geometry.

**Concrete example**: `SeamlessTileMode/` continues to own Blender boundary-contract work. `TileInpaintRepair/` owns post-render mask and LaMa repair tests.

---

## Rule 6 - Preserve original opacity unless alpha damage is proven.

**Why**: The current LaMa endpoint returns RGB, and the diagnostic tile images are fully opaque. Repairing alpha adds complexity without value for the first proof.

**Concrete example**: For the first fabric tile repair, inpaint RGB and keep alpha at 255 or preserve the original alpha channel.

---

## Rule 7 - Keep mask width as an internal quality knob.

**Why**: Wider masks hide the seam better but repaint more woven detail. Narrower masks preserve more source texture but can leave the seam visible. This is a tuning/calibration value, not a material design control.

**Concrete example**: On `NormalCamera_Ortho2975_PasteOnly_2x2_1200.png`, `r12` preserves more original weave detail but leaves more seam evidence; `r48` removes the cross more strongly but the repaired band is softer.

---

## Rule 8 - Treat color drift separately from seam shape.

**Why**: A narrow inpaint mask can preserve the weave structure while still producing a visible seam if the generated pixels are darker or lighter than the surrounding yarn. This makes the repair read like a new thread instead of a removed boundary.

**Concrete example**: The raw `r12` output can look like a dark yarn line. Matching the masked pixels back toward the local ring color with `--color-match 0.5` reduces that artifact without widening the visible repair band.

---

## Rule 9 - Do not treat repeated previews as final 2x2 outputs.

**Why**: The repaired inpaint output in this track is already a `2 x 2` tile assembly. Repeating that repaired image again creates a larger diagnostic layout that reads as `4 x 4` source tiles.

**Concrete example**: `NormalCamera_Ortho2975_InpaintTileable_r6_color_2x2_1200.png` is the real output. A repeated preview of that image is only for checking edge behavior and should be named as a diagnostic, not as the final retiled result.

---

## Rule 10 - Make production tile repair quiet by default.

**Why**: Inpaint experiments need masks, crops, summaries, raw LaMa outputs, and comparison sheets. End users need the final texture. Keeping research artifacts for every localhost render quickly fills the runtime folder and makes the output contract unclear.

**Concrete example**: The frontend tile button runs `r12 + color-match 1.2` without debug outputs. The backend deletes temporary tile renders and raw stitched images after success. Set `WEAVE_KEEP_TILE_DEBUG=1` only when investigating a failed or suspicious render.

---

## Rule 11 - Preserve source renders when diagnosing clarity.

**Why**: A soft final texture can come from the Blender render, the paste/stitch step, or the inpaint band. Showing the four source renders makes that split visible without keeping every low-level debug artifact.

**Concrete example**: A normal frontend tile job keeps `source_tiles/source_tile_01.png` through `source_tile_04.png` and exposes them below the final repaired preview. It still deletes scripts, logs, raw stitch output, and LaMa crop masks unless debug mode is enabled.
