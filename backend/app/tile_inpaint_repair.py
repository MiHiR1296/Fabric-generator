from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from PIL import Image, ImageChops, ImageDraw, ImageFilter


InpaintCallable = Callable[[Image.Image, Image.Image], Image.Image]


@dataclass(frozen=True)
class TileInpaintRepairResult:
    input_path: str
    output_path: str
    pass_a_mask_path: str | None
    pass_a_output_path: str | None
    pass_b_rolled_input_path: str | None
    pass_b_mask_path: str | None
    pass_b_rolled_output_path: str | None
    final_retile_preview_path: str | None
    width: int
    height: int
    seam_radius_px: int
    context_px: int
    color_match_strength: float
    elapsed_seconds: float


def build_cross_mask(
    size: tuple[int, int],
    *,
    seam_x: int | None = None,
    seam_y: int | None = None,
    radius_px: int = 48,
) -> Image.Image:
    """Return an L mask where white pixels mark seam bands to inpaint."""
    width, height = size
    radius = max(1, int(radius_px))
    mask = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(mask)

    if seam_x is not None:
        x0 = max(0, int(seam_x) - radius)
        x1 = min(width, int(seam_x) + radius)
        if x1 > x0:
            draw.rectangle((x0, 0, x1 - 1, height - 1), fill=255)

    if seam_y is not None:
        y0 = max(0, int(seam_y) - radius)
        y1 = min(height, int(seam_y) + radius)
        if y1 > y0:
            draw.rectangle((0, y0, width - 1, y1 - 1), fill=255)

    return mask


def roll_image(image: Image.Image, *, dx: int, dy: int) -> Image.Image:
    """Wrap-offset an image, moving opposite edges into view."""
    return ImageChops.offset(image, int(dx), int(dy))


def paste_only_retile_preview(image: Image.Image, *, repetitions: int = 2) -> Image.Image:
    repetitions = max(1, int(repetitions))
    tile = image.convert("RGBA")
    width, height = tile.size
    out = Image.new("RGBA", (width * repetitions, height * repetitions), (0, 0, 0, 0))
    for row in range(repetitions):
        for col in range(repetitions):
            out.paste(tile, (col * width, row * height))
    return out


def _binary_mask(mask: Image.Image) -> Image.Image:
    return mask.convert("L").point(lambda value: 255 if value > 127 else 0)


def inpaint_pil_with_lama(image: Image.Image, mask: Image.Image) -> Image.Image:
    """Run the repo's existing LaMa model on a PIL image and binary mask."""
    import numpy as np
    import torch

    from . import yarnseamless_routes as lama

    lama.ensure_model_loaded()
    image_rgb = image.convert("RGB")
    mask_l = _binary_mask(mask)
    image_t, mask_t = lama.prepare_img_and_mask(image_rgb, mask_l, lama.device)
    start = time.time()
    with torch.inference_mode():
        result = lama.model(image_t, mask_t)
    if lama.device is not None and lama.device.type == "mps":
        torch.mps.synchronize()
    result_np = result[0].permute(1, 2, 0).detach().cpu().numpy()
    result_np = np.clip(result_np * 255, 0, 255).astype(np.uint8)
    print(f"[tile-inpaint] LaMa crop {image_rgb.size} in {time.time() - start:.2f}s")
    return Image.fromarray(result_np).resize(image_rgb.size)


def _center_window(length: int, center: int, window_size: int) -> tuple[int, int]:
    window = max(1, min(int(window_size), int(length)))
    start = max(0, int(center) - window // 2)
    end = min(int(length), start + window)
    start = max(0, end - window)
    return start, end


def _color_match_masked_pixels(
    original_crop: Image.Image,
    result_crop: Image.Image,
    mask: Image.Image,
    *,
    strength: float,
    ring_px: int = 24,
) -> Image.Image:
    if strength <= 0:
        return result_crop

    import numpy as np

    mask_l = _binary_mask(mask)
    mask_arr = np.asarray(mask_l) > 127
    if not mask_arr.any():
        return result_crop

    filter_size = max(3, int(ring_px) * 2 + 1)
    if filter_size % 2 == 0:
        filter_size += 1
    dilated = mask_l.filter(ImageFilter.MaxFilter(filter_size))
    ring_arr = (np.asarray(dilated) > 127) & ~mask_arr
    if not ring_arr.any():
        ring_arr = ~mask_arr
    if not ring_arr.any():
        return result_crop

    original = np.asarray(original_crop.convert("RGB"), dtype=np.float32)
    result = np.asarray(result_crop.convert("RGB"), dtype=np.float32)

    source_ring = original[ring_arr]
    result_mask = result[mask_arr]
    if source_ring.size == 0 or result_mask.size == 0:
        return result_crop

    source_mean = source_ring.mean(axis=0)
    source_std = np.maximum(source_ring.std(axis=0), 1.0)
    result_mean = result_mask.mean(axis=0)
    result_std = np.maximum(result_mask.std(axis=0), 1.0)

    matched = (result_mask - result_mean) * (source_std / result_std) + source_mean
    # Values above 1.0 intentionally over-drive the match a little. This is
    # useful when LaMa keeps creating a subtly darker seam after exact matching.
    strength = max(0.0, min(1.5, float(strength)))
    adjusted = result_mask * (1.0 - strength) + matched * strength

    out = result.copy()
    out[mask_arr] = np.clip(adjusted, 0, 255)
    return Image.fromarray(out.astype(np.uint8))


def _inpaint_masked_window(
    image: Image.Image,
    mask: Image.Image,
    box: tuple[int, int, int, int],
    *,
    inpaint_fn: InpaintCallable,
    color_match_strength: float = 0.0,
    debug_dir: Path | None = None,
    debug_name: str | None = None,
) -> Image.Image:
    x0, y0, x1, y1 = box
    if x1 <= x0 or y1 <= y0:
        return image

    local_mask = _binary_mask(mask.crop(box))
    if local_mask.getbbox() is None:
        return image

    base_rgba = image.convert("RGBA")
    base_rgb = base_rgba.convert("RGB")
    crop_rgb = base_rgb.crop(box)

    if debug_dir and debug_name:
        debug_dir.mkdir(parents=True, exist_ok=True)
        crop_rgb.save(debug_dir / f"{debug_name}_input.png")
        local_mask.save(debug_dir / f"{debug_name}_mask.png")

    result_crop = inpaint_fn(crop_rgb, local_mask).convert("RGB")
    if result_crop.size != crop_rgb.size:
        result_crop = result_crop.resize(crop_rgb.size)
    if color_match_strength > 0:
        if debug_dir and debug_name:
            result_crop.save(debug_dir / f"{debug_name}_lama_raw.png")
        result_crop = _color_match_masked_pixels(
            crop_rgb,
            result_crop,
            local_mask,
            strength=color_match_strength,
        )

    if debug_dir and debug_name:
        result_crop.save(debug_dir / f"{debug_name}_output.png")

    repaired_rgb = base_rgb.copy()
    repaired_rgb.paste(result_crop, (x0, y0), local_mask)

    alpha = base_rgba.getchannel("A")
    repaired = Image.merge("RGBA", (*repaired_rgb.split(), alpha))
    return repaired


def repair_center_cross_once(
    image: Image.Image,
    *,
    seam_radius_px: int = 48,
    context_px: int = 640,
    inpaint_fn: InpaintCallable = inpaint_pil_with_lama,
    color_match_strength: float = 0.0,
    debug_dir: Path | None = None,
    debug_prefix: str = "pass",
) -> tuple[Image.Image, Image.Image]:
    """Repair the center vertical and horizontal seam bands once."""
    width, height = image.size
    seam_x = width // 2
    seam_y = height // 2
    context = max(seam_radius_px * 2 + 32, int(context_px))

    vertical_mask = build_cross_mask(
        (width, height),
        seam_x=seam_x,
        radius_px=seam_radius_px,
    )
    horizontal_mask = build_cross_mask(
        (width, height),
        seam_y=seam_y,
        radius_px=seam_radius_px,
    )
    full_mask = ImageChops.lighter(vertical_mask, horizontal_mask)

    if debug_dir is not None:
        debug_dir.mkdir(parents=True, exist_ok=True)
        full_mask.save(debug_dir / f"{debug_prefix}_mask.png")

    x0, x1 = _center_window(width, seam_x, context)
    repaired = _inpaint_masked_window(
        image,
        vertical_mask,
        (x0, 0, x1, height),
        inpaint_fn=inpaint_fn,
        color_match_strength=color_match_strength,
        debug_dir=debug_dir,
        debug_name=f"{debug_prefix}_vertical",
    )

    y0, y1 = _center_window(height, seam_y, context)
    repaired = _inpaint_masked_window(
        repaired,
        horizontal_mask,
        (0, y0, width, y1),
        inpaint_fn=inpaint_fn,
        color_match_strength=color_match_strength,
        debug_dir=debug_dir,
        debug_name=f"{debug_prefix}_horizontal",
    )
    return repaired, full_mask


def repair_tile_with_two_pass_inpaint(
    input_path: str | Path,
    output_path: str | Path,
    *,
    debug_dir: str | Path | None = None,
    prefix: str = "tile_inpaint",
    seam_radius_px: int = 48,
    context_px: int = 640,
    inpaint_fn: InpaintCallable = inpaint_pil_with_lama,
    color_match_strength: float = 0.0,
    save_debug_outputs: bool = True,
    save_retile_preview: bool = False,
) -> TileInpaintRepairResult:
    """Run center-cross repair, offset-cross repair, then roll back."""
    start = time.time()
    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    debug_root = (Path(debug_dir) if debug_dir is not None else output_path.parent) if save_debug_outputs else None
    if debug_root is not None:
        debug_root.mkdir(parents=True, exist_ok=True)

    source = Image.open(input_path).convert("RGBA")
    width, height = source.size
    if width < 2 or height < 2:
        raise ValueError("Tile repair requires an image larger than 1x1.")

    if debug_root is not None:
        source.save(debug_root / f"{prefix}_input.png")

    pass_a, mask_a = repair_center_cross_once(
        source,
        seam_radius_px=seam_radius_px,
        context_px=context_px,
        inpaint_fn=inpaint_fn,
        color_match_strength=color_match_strength,
        debug_dir=debug_root,
        debug_prefix=f"{prefix}_pass_a_center",
    )
    pass_a_path: Path | None = None
    pass_a_mask_path: Path | None = None
    if debug_root is not None:
        pass_a_path = debug_root / f"{prefix}_pass_a_center_output.png"
        pass_a.save(pass_a_path)
        pass_a_mask_path = debug_root / f"{prefix}_pass_a_center_mask.png"
        mask_a.save(pass_a_mask_path)

    rolled_input = roll_image(pass_a, dx=width // 2, dy=height // 2)
    rolled_input_path: Path | None = None
    if debug_root is not None:
        rolled_input_path = debug_root / f"{prefix}_pass_b_rolled_input.png"
        rolled_input.save(rolled_input_path)

    pass_b_rolled, mask_b = repair_center_cross_once(
        rolled_input,
        seam_radius_px=seam_radius_px,
        context_px=context_px,
        inpaint_fn=inpaint_fn,
        color_match_strength=color_match_strength,
        debug_dir=debug_root,
        debug_prefix=f"{prefix}_pass_b_offset",
    )
    pass_b_path: Path | None = None
    pass_b_mask_path: Path | None = None
    if debug_root is not None:
        pass_b_path = debug_root / f"{prefix}_pass_b_rolled_output.png"
        pass_b_rolled.save(pass_b_path)
        pass_b_mask_path = debug_root / f"{prefix}_pass_b_offset_mask.png"
        mask_b.save(pass_b_mask_path)

    final = roll_image(pass_b_rolled, dx=-(width // 2), dy=-(height // 2))
    final.save(output_path)

    preview_path: Path | None = None
    if save_retile_preview:
        preview_root = Path(debug_dir) if debug_dir is not None else output_path.parent
        preview_root.mkdir(parents=True, exist_ok=True)
        preview_path = preview_root / f"{prefix}_diagnostic_repeated_2x2.png"
        paste_only_retile_preview(final, repetitions=2).save(preview_path)

    elapsed = round(time.time() - start, 2)
    result = TileInpaintRepairResult(
        input_path=str(input_path),
        output_path=str(output_path),
        pass_a_mask_path=str(pass_a_mask_path) if pass_a_mask_path else None,
        pass_a_output_path=str(pass_a_path) if pass_a_path else None,
        pass_b_rolled_input_path=str(rolled_input_path) if rolled_input_path else None,
        pass_b_mask_path=str(pass_b_mask_path) if pass_b_mask_path else None,
        pass_b_rolled_output_path=str(pass_b_path) if pass_b_path else None,
        final_retile_preview_path=str(preview_path) if preview_path else None,
        width=width,
        height=height,
        seam_radius_px=int(seam_radius_px),
        context_px=int(context_px),
        color_match_strength=round(float(color_match_strength), 4),
        elapsed_seconds=elapsed,
    )
    if debug_root is not None:
        (debug_root / f"{prefix}_summary.json").write_text(json.dumps(asdict(result), indent=2), encoding="utf-8")
    return result


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Two-pass LaMa repair for paste-only fabric tile seams.")
    parser.add_argument("input", help="Input paste-only tile image.")
    parser.add_argument("output", help="Final repaired output PNG.")
    parser.add_argument("--debug-dir", default=None, help="Directory for masks and intermediate images.")
    parser.add_argument("--prefix", default="tile_inpaint", help="Output filename prefix for debug images.")
    parser.add_argument("--seam-radius", type=int, default=48, help="Half-width of the seam mask band in pixels.")
    parser.add_argument("--context", type=int, default=640, help="Inpaint crop/window width around each seam.")
    parser.add_argument(
        "--color-match",
        type=float,
        default=0.0,
        help="0..1.5 strength for matching inpainted pixels back to the local surrounding color.",
    )
    parser.add_argument(
        "--retile-preview",
        action="store_true",
        help="Save a diagnostic repeat of the repaired 2x2 image. This creates a 4x4 source-tile layout.",
    )
    parser.add_argument("--no-debug", action="store_true", help="Only save the final repaired output image.")
    parser.add_argument(
        "--no-retile-preview",
        action="store_true",
        help="Deprecated compatibility flag. Repeated previews are already off by default.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    result = repair_tile_with_two_pass_inpaint(
        args.input,
        args.output,
        debug_dir=args.debug_dir,
        prefix=args.prefix,
        seam_radius_px=args.seam_radius,
        context_px=args.context,
        color_match_strength=args.color_match,
        save_debug_outputs=not args.no_debug,
        save_retile_preview=args.retile_preview and not args.no_retile_preview,
    )
    print(json.dumps(asdict(result), indent=2))


if __name__ == "__main__":
    main()
