# Tile Inpaint Repair

Planning and test log for repairing visible seams in Blender fabric tile exports with the existing LaMa inpainting workflow.

This folder is separate from `SeamlessTileMode/` on purpose. `SeamlessTileMode` tracks Blender-side tile rendering, guard bands, cameras, and paste-only assembly. This folder tracks the post-render image repair idea:

```text
Blender render(s)
  -> paste-only tile assembly
  -> inpaint center cross
  -> offset corners to center
  -> inpaint wraparound cross
  -> offset back
  -> final tileable texture
```

The goal is to test whether the existing yarn inpainting machinery can remove the cross seam created by repeated rendered fabric edges, without changing the geometry-node graph first.

## Current Status

**Date**: 2026-05-26

Status: `r12 + color-match 1.2` is the current production repair default for the frontend tile button. Manual CLI experiments can still save masks/intermediates; normal backend tile jobs save the final image plus the four Blender source renders used to build it.

Known context from the current tile tests:

- normal Blender `Camera` / `Camera.001` is enough for this test path
- `1200 x 1200`, `cycles.samples = 40`
- zero guard edges
- paste-only placement, no overlap, no blending
- current best candidate from manual tests is `Camera.001.ortho_scale = 2.975`
- the visible cross is not transparent gap; it is the rendered fabric edge repeated at tile boundaries
- production tile export is fixed to `2 x 2`, `1200 px`, `guardThreads = 0`, `variationStrength = 0`
- production seam repair is fixed to `seam_radius_px = 12`, `color_match_strength = 1.2`
- production tile jobs preserve the four source renders for frontend inspection, then clear lower-level temp files

Relevant scratch outputs live outside the repo docs here:

```text
/Users/mihirbotle/Desktop/Impetus/3D Fabric/yarnseamless UI/Tiling Generator/
  NormalCamera_Ortho2975_Source_1200.png
  NormalCamera_Ortho2975_PasteOnly_2x2_1200.png
  NormalCamera_Ortho2975_InpaintTileable_r6_color_2x2_1200.png
  NormalCamera_Ortho2975_InpaintTileable_r12_2x2_1200.png
  NormalCamera_Ortho2975_InpaintTileable_r12_color05_2x2_1200.png
  NormalCamera_Ortho2975_InpaintTileable_r12_color_2x2_1200.png
  NormalCamera_Ortho2975_InpaintTileable_r12_color12_2x2_1200.png
  NormalCamera_Ortho2975_InpaintTileable_r32_2x2_1200.png
  NormalCamera_Ortho2975_InpaintTileable_r48_2x2_1200.png
  NormalCamera_Ortho2975_InpaintComparison_CenterCross_r12_r32_r48.png
  NormalCamera_Ortho2975_InpaintComparison_RetiledWrap_r12_r32_r48.png
  NormalCamera_Ortho2975_InpaintComparison_2x2_r6_color.png
  NormalCamera_Ortho2975_InpaintComparison_2x2_r12_color12.png
  NormalCamera_Ortho2975_InpaintComparison_r12_color_sweep.png
  NormalCamera_Ortho2975_InpaintComparison_r12_color_sweep_retiled.png
  NormalCamera_Ortho2975_InpaintComparison_CenterCross.png
  NormalCamera_Ortho2975_InpaintComparison_RetiledWrap.png
  NormalCamera_Ortho297_Source_1200.png
  NormalCamera_Ortho2965_Source_1200.png
  NormalCamera_Ortho295_Source_1200.png
```

The reusable helper currently lives at:

```text
backend/app/tile_inpaint_repair.py
```

The repaired output is already a `2 x 2` image. Repeating that repaired image again creates a `4 x 4` source-tile diagnostic preview, so repeated previews are opt-in only and should not be treated as the final output.

## Documentation Index

Read in this order:

| # | doc | what it covers |
|---|---|---|
| 1 | [architecture.md](architecture.md) | Two-pass inpaint repair architecture, current code surfaces, masks, offset pass, and integration options. |
| 2 | [phase_log.md](phase_log.md) | Append-only investigation and test log. |
| 3 | [lessons.md](lessons.md) | Rules learned while adapting yarn inpainting to fabric tile seams. |

## Intended Test

Start with one controlled `2 x 2` result:

```text
source tile: 1200 x 1200
assembled:   2400 x 2400
seams:       x = 1200, y = 1200
```

The repair should run two passes:

```text
Pass A - center cross
  mask x = 1200 vertical band
  mask y = 1200 horizontal band
  inpaint only those bands

Pass B - wraparound cross
  roll repaired image by width / 2 and height / 2
  old corners now meet at the center
  mask the new center cross
  inpaint only those bands
  roll image back
```

This is different from only hiding the first cross. Pass B is what makes the final image's outer edges less visible when the whole repaired texture is tiled again.

## Logging Rules

- Record every test with input image path, mask width, inpaint crop/chunk size, output path, and visual result.
- Say whether the test touched code, Blender, both, or neither.
- If the test uses the LaMa model, record whether it used the FastAPI endpoint or direct backend Python.
- Keep Blender camera/framing tests in `SeamlessTileMode/`; keep post-render seam repair tests here.
- Do not save `.blend` changes for inpaint-only experiments.
