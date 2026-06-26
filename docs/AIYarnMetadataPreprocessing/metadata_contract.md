# Metadata Contract For AI Yarn Experiments

This is the target shape for AI-generated yarn metadata. It mirrors the
existing library contract while adding AI provenance and sanity-check fields.

## Library Folder

Each accepted AI yarn is written as:

```text
yarn_library/<yarn_id>/
  rgba.png
  input_thumb.jpg
  metadata.json
```

The `yarn_id` can be deterministic during experiments so repeated runs are easy
to compare:

```text
20260611_100000_a10000
```

For a future UI implementation, IDs should use the normal library ID generator.

## Required Top-Level Fields

```json
{
  "schemaVersion": 1,
  "id": "20260611_100000_a10000",
  "label": "AI Yarn 01",
  "createdAt": "2026-06-11T10:00:00Z",
  "source": {
    "kind": "ai_generated_rgba",
    "asset_dir": "/absolute/source/folder",
    "rgba_filename": "tinted_rgba.png",
    "measurement_filename": "measurements.json",
    "scan_size_px": null
  },
  "image_size_px": [2752, 1536],
  "dpi": 1600.0
}
```

`source.kind = "ai_generated_rgba"` is the switch that lets future code apply
the AI-specific metadata path without touching scanned yarns.

## Physical Scale

Until AI generation supplies calibrated physical scale, use:

```json
{
  "physical_scale": {
    "declared_dpi": 1600.0,
    "confidence": "metadata_only",
    "texture_world_width_m": 0.043688,
    "notes": [
      "AI-generated source has no original scanner capture; physical scale uses declared 1600 dpi for parity with scanned yarns."
    ]
  }
}
```

Do not claim high confidence for AI-generated dimensions just because the PNG
dimensions are known.

## Width And Length

`width` is the dense Arc 1 core height, inclusive:

```json
{
  "width": {
    "px": 136,
    "mm": 2.159,
    "top_y_in_export": 692,
    "bottom_y_in_export": 827,
    "description": "Top-to-bottom of the unified solid thread band, in the EXPORT image's coordinates."
  },
  "length": {
    "px": 2752,
    "mm": 43.688,
    "description": "Left-to-right of the export image (no wraparound)."
  }
}
```

`length.px` is always the actual PNG width, not the AI JSON's length field.

## Bands

The final AI band layout keeps Arc 1 and Arc 2 separate:

```json
{
  "bands_px": {
    "core": [692, 827],
    "fiber_top": [530, 692],
    "fiber_bot": [827, 987]
  },
  "bands_v_norm": {
    "_convention": "blender (V=0 bottom, V=1 top)",
    "core": [0.46158854166666663, 0.5494791666666667],
    "fiber_top": [0.5494791666666667, 0.6549479166666667],
    "fiber_bot": [0.357421875, 0.46158854166666663]
  },
  "thickness_px": {
    "core_height": 136,
    "fiber_top_height": 162,
    "fiber_bot_height": 160
  }
}
```

`fiber_top` and `fiber_bot` are intentionally outer-support ranges. They
should be wider than the dense core whenever the AI image contains wispy
fibers.

## Params

The AI params should identify the experimental detector:

```json
{
  "params": {
    "algorithm": "ai_high_alpha_core_full_support_arc2",
    "core_alpha_threshold": 224,
    "core_density_fraction": 0.95,
    "arc2_alpha_threshold": 5,
    "arc2_row_density": 0.02
  }
}
```

This prevents future code from confusing AI-generated metadata with scanned
`fwhm_density_walk` metadata.

## Blender Block

The Blender block should be fully ready for direct push:

```json
{
  "blender": {
    "schema_version": 1,
    "texture_world_width_m": 0.043688,
    "texture_world_width_mm": 43.688,
    "image_width_px": 2752,
    "scanner_pixels_per_bu": 62992.16,
    "core_v_min": 0.46158854166666663,
    "core_v_max": 0.5494791666666667,
    "fiber_top_v_min": 0.5494791666666667,
    "fiber_bot_v_max": 0.46158854166666663,
    "fiber_bot_v_min": 0.357421875,
    "fiber_top_v_max": 0.6549479166666667,
    "top_halo_frac": 0.353711,
    "bot_halo_frac": 0.349345,
    "texture_scale_u": 0.21719511589158455,
    "texture_scale_u_strategy": "ai_alpha_mass_equivalent_width_v2",
    "texture_scale_u_previous_core_only": 0.146484375,
    "texture_scale_u_raw_alpha_mass": 0.21719511589158455,
    "texture_scale_u_boost": 1.482972,
    "texture_scale_u_alpha_equivalent_width_px": 200.171,
    "texture_scale_u_alpha_power": 1.5,
    "texture_scale_u_max_boost": 2.0,
    "v_band_strategy": "ai_dense_core_plus_full_alpha_support_arc2"
  }
}
```

Important:

- `texture_scale_u` is explicit. It is not the scanned-yarn auto fallback.
- `texture_scale_u_strategy = "ai_alpha_mass_equivalent_width_v2"` means U
  scale was derived from opacity-weighted visible width, not dense core only.
- `texture_scale_u_previous_core_only` keeps the earlier core-only value for
  comparison.
- `core_v_min/max` feed Arc 1.
- `fiber_bot_v_min` and `fiber_top_v_max` feed Arc 2 outer extents.
- `fiber_top_v_min` and `fiber_bot_v_max` mirror the core boundaries and are
  retained for diagnostics/back-compat.

## AI Sanity Check

Every AI metadata file should keep a provenance block:

```json
{
  "ai_sanity_check": {
    "source_measurements_file": "/absolute/path/measurements.json",
    "source_rgba_file": "/absolute/path/tinted_rgba.png",
    "size_matches_png": true,
    "ai_measurements": {
      "core_band_px": [698, 824],
      "core_width_px": 127,
      "fiber_extent_px": [694, 825]
    },
    "v_band_check": {
      "previous": {},
      "updated": {},
      "strategy": "strict high-alpha core, wider low-alpha Arc 2 support"
    },
    "u_scale_check": {
      "core_v_span": 0.087890625,
      "arc1_v_around_span": 0.6,
      "corrected_texture_scale_u": 0.146484375,
      "strategy": "ai_dense_core_over_arc1_span_after_arc2_support_fix"
    }
  }
}
```

This block is diagnostic. Blender does not consume it.
