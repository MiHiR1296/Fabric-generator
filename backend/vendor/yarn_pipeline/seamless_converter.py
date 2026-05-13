#!/usr/bin/env python3

import os
import shutil
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parent
DEFAULT_MODEL_PATH = MODULE_DIR / "big-lama.pt"
MODEL_CHUNK_DIR = MODULE_DIR / "model_chunks"
MODEL_CHUNK_PREFIX = "big-lama.pt.part-"


def ensure_bundled_model_path() -> str:
    if DEFAULT_MODEL_PATH.exists():
        return str(DEFAULT_MODEL_PATH)

    chunk_paths = sorted(MODEL_CHUNK_DIR.glob(f"{MODEL_CHUNK_PREFIX}*"))
    if not chunk_paths:
        return str(DEFAULT_MODEL_PATH)

    DEFAULT_MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with DEFAULT_MODEL_PATH.open("wb") as destination:
        for chunk_path in chunk_paths:
            with chunk_path.open("rb") as source:
                shutil.copyfileobj(source, destination)
    return str(DEFAULT_MODEL_PATH)


# Use bundled weights file if no LAMA_MODEL env var is set
os.environ.setdefault("LAMA_MODEL", ensure_bundled_model_path())

import argparse
import numpy as np
from matplotlib.image import imread, imsave
from PIL import Image
from simple_lama_inpainting import SimpleLama
from tqdm import tqdm

# Initialize SimpleLama model once (globally, so it's not reloaded on every call)
_simple_lama_model = None

def get_lama_model():
    """Lazy load SimpleLama model"""
    global _simple_lama_model
    if _simple_lama_model is None:
        import torch
        # Determine best available device
        if torch.backends.mps.is_available():
            device = torch.device("mps")
        elif torch.cuda.is_available():
            device = torch.device("cuda")
        else:
            device = torch.device("cpu")
        # Load model on CPU first (the .pt was saved from CUDA), then move to device
        model_path = os.environ.get("LAMA_MODEL")
        model = torch.jit.load(model_path, map_location="cpu")
        model.eval()
        model.to(device)
        # Create a SimpleLama-like wrapper
        _simple_lama_model = SimpleLama.__new__(SimpleLama)
        _simple_lama_model.model = model
        _simple_lama_model.device = device
    return _simple_lama_model

def inpaint(cropped_img_rest, cropped_mask_rest):
    """
    Inpaints using SimpleLama.

    Parameters
    ----------
    cropped_img_rest : np.ndarray
        Image to inpaint. Either float in [0,1] or uint8 in [0,255]. RGB or RGBA.
    cropped_mask_rest : np.ndarray
        Mask image. Either float in [0,1] or uint8 in [0,255].
        Convention: white (255) = REMOVE/INPAINT area, black (0) = keep.

    Returns
    -------
    np.ndarray
        The inpainted image as a uint8 NumPy array (shape HxWxC).
    """
    # Get SimpleLama model
    simple_lama = get_lama_model()

    # Normalize image to uint8
    img_np = np.asarray(cropped_img_rest)
    if img_np.dtype != np.uint8:
        img_np = np.clip(img_np, 0, 1) if np.issubdtype(img_np.dtype, np.floating) else img_np
        img_np = (img_np * 255).astype(np.uint8) if np.issubdtype(img_np.dtype, np.floating) else img_np

    # Convert to PIL Image
    if img_np.ndim == 2:
        img_pil = Image.fromarray(img_np, mode="L").convert("RGB")
    else:
        # Convert grayscale-with-channel=1 to RGB
        if img_np.ndim == 3 and img_np.shape[2] == 1:
            img_np = img_np[..., 0]
            img_pil = Image.fromarray(img_np, mode="L").convert("RGB")
        else:
            # Handle RGBA by converting to RGB
            img_pil = Image.fromarray(img_np)
            if img_pil.mode == "RGBA":
                img_pil = img_pil.convert("RGB")

    # Normalize mask to uint8 single-channel (L)
    mask_np = np.asarray(cropped_mask_rest)
    if mask_np.dtype != np.uint8:
        mask_np = np.clip(mask_np, 0, 1) if np.issubdtype(mask_np.dtype, np.floating) else mask_np
        mask_np = (mask_np * 255).astype(np.uint8) if np.issubdtype(mask_np.dtype, np.floating) else mask_np

    if mask_np.ndim == 3 and mask_np.shape[2] > 1:
        # If mask provided as RGB(A), convert to luminance
        mask_pil = Image.fromarray(mask_np).convert("L")
    else:
        mask_pil = Image.fromarray(mask_np if mask_np.ndim == 2 else mask_np[..., 0], mode="L")

    # Ensure binary mask (threshold at 127)
    mask_array = np.array(mask_pil)
    mask_array = (mask_array > 127).astype(np.uint8) * 255
    mask_pil = Image.fromarray(mask_array)

    # Perform inpainting
    result_pil = simple_lama(img_pil, mask_pil)

    # Convert result back to uint8 numpy array
    result_np = np.array(result_pil, dtype=np.uint8)

    in_h, in_w = cropped_img_rest.shape[:2]
    if result_np.shape[0] != in_h or result_np.shape[1] != in_w:
        result_np = result_np[:in_h, :in_w]

    return result_np


def process_image(image_path, output_dir):
    """Process a single image to make it seamless"""
    
    # Create output directory
    os.makedirs(output_dir, exist_ok=True)
    
    # Get filename without extension
    filename = os.path.basename(image_path)
    name, ext = os.path.splitext(filename)
    
    # Create debug directory
    debug_dir = os.path.join(output_dir, 'seamless_debugger', name)
    os.makedirs(debug_dir, exist_ok=True)

    # Load the image
    img = imread(image_path)
    if len(np.shape(img)) == 2:
        img = np.stack([img] * 3, axis=-1)
    if np.shape(img)[-1] == 4:
        img = img[:, :, :-1]
    
    # print(np.shape(img))
    height, width = img.shape[:2]
    # np.shape(img)
    
    # Tile the image to the right (h,w -> h,2w)
    # Concatenate along width axis (axis=1)
    tiled_img = np.concatenate([img, img], axis=1)

    # Create a single channel mask covering center by 100 pixels left and right
    mask = np.zeros((height, width * 2), dtype=np.uint8)

    # Calculate center and create mask covering 100 pixels left and right from center
    center_x = width  # center of the tiled image (which is 2*width wide)
    left_edge = center_x - 40
    right_edge = center_x + 40

    # Set the center region to white (255)
    mask[:, left_edge:right_edge] = 255

    # sub_plotter([tiled_img, mask])
    # imsave(f'{output_dir}/{name}_raw_right_tile.png', tiled_img)

    # --- constants ---
    h, w, _ = np.shape(img)
    inpaint_context = 128
    inpaint_buffer = 64  # keep some slack inside the overlap
    fal_cap = 640 if (h >= 1024 and w >= 1024) else 640

    # Overlap-aware stride (how much we move down each step)
    stride = fal_cap - inpaint_context
    stride = max(1, stride)  # safety

    # Number of blocks so that we cover the full height with overlap
    # last block may be shorter and will be clamped
    n_blocks = max(1, int(np.ceil((h - fal_cap) / stride)) + 1)

    x0 = int(w - fal_cap / 2)
    x1 = int(w + fal_cap / 2)

    # print('img shape:', np.shape(img))
    # print('n_blocks:', n_blocks)

    # Horizontal inpainting
    for n in tqdm(range(n_blocks), desc="Horizontal inpainting"):
        print(f"Processing horizontal block {n+1}/{n_blocks}")
        
        # y-range with overlap
        y0 = n * stride
        y1 = y0 + fal_cap

        # clamp to image height
        y0_clamped = max(0, y0)
        y1_clamped = min(h, y1)

        # --- NEW: enforce last-crop constraints (no bottom trim) ---
        if n == n_blocks - 1:
            avail = y1_clamped - y0_clamped
            # target height: ceil to multiple of 32, at least 640
            target = max(640, int(np.ceil(avail / 32.0) * 32))
            y0_clamped = max(0, y1_clamped - target)

        cropped_img_rest = tiled_img[y0_clamped:y1_clamped, x0:x1]
        cropped_mask_rest = mask[y0_clamped:y1_clamped, x0:x1]

        # print(y0_clamped, y1_clamped, x0, x1)
        # For n>0, zero out the part of the mask that overlaps with the previous block,
        # except a small buffer so we don't re-inpaint the whole overlap.
        if n > 0:
            # how many rows are actually available at the top after clamping
            avail = y1_clamped - y0_clamped
            cutoff = max(0, min(inpaint_context - inpaint_buffer, avail))
            cropped_mask_rest[:cutoff] = 0
        
        # Save debug outputs for horizontal inpainting
        imsave(f'{debug_dir}/cropped_img_rest_horizontal_{n}.png', cropped_img_rest)
        imsave(f'{debug_dir}/cropped_mask_rest_horizontal_{n}.png', cropped_mask_rest)
        
        # (debug) visualize crops
        # sub_plotter([cropped_img_rest, cropped_mask_rest])

        # Inpaint and paste back
        img_np = inpaint(cropped_img_rest, cropped_mask_rest)  # expected 0..255
        
        # Save inpainted result
        imsave(f'{debug_dir}/img_np_horizontal_{n}.png', img_np)
        
        # p(img_np)
        # print('seamless out', np.max(img_np))
        # print('tiled_img', np.max(tiled_img))

        if np.max(tiled_img) > 1 and np.max(img_np) > 1:
            tiled_img[y0_clamped:y1_clamped, x0:x1] = img_np.astype(np.float32)
        elif np.max(tiled_img) < 1 and np.max(img_np) > 1:
            tiled_img[y0_clamped:y1_clamped, x0:x1] = img_np.astype(np.float32) / 255.0
        else:
            assert 'Not expected'
        # p(tiled_img)

    # imsave(f'{output_dir}/inpaint_right.png', tiled_img)
    h_strip_w = min(w, int(fal_cap / 2))
    intersection_strip = tiled_img[:, w:w + h_strip_w].copy()  # top part
    tiled_img[:, :h_strip_w] = intersection_strip

    # orig_shape_fabric = tiled_img[:,:w]
    # horizontally_seamless_path = f'{output_dir}/horizontally_seamless.png'
    # imsave(horizontally_seamless_path, orig_shape_fabric)
    # np.shape(orig_shape_fabric)

    ## VERTICAL INPAINTING
    img = tiled_img[:h, :w]
    # print('image after verticle seamless', np.shape(img))

    tiled_img = np.concatenate([img, img], axis=0)
    # print('horizontal tiled image shape', np.shape(tiled_img))
    mask = np.zeros((height * 2, width), dtype=np.uint8)

    # Calculate center and create mask covering 200 pixels up and down from center
    center_y = height  # center of the tiled image (which is 2*height tall)
    top_edge = center_y - 40
    bottom_edge = center_y + 40

    # Set the center region to white (255)
    mask[top_edge:bottom_edge, :] = 255
    # tiled_alpha = np.concatenate([alpha, alpha], axis=0)

    # sub_plotter([tiled_img, mask])
    # imsave(f'{output_dir}/top_down_tiled.png', tiled_img)

    stride = fal_cap - inpaint_context
    stride = max(1, stride)

    # number of blocks to cover width with overlap
    n_blocks = max(1, int(np.ceil((w - fal_cap) / stride)) + 1)
    remainder = w - fal_cap * (w // fal_cap)  # just to keep your print
    # print('height', h, 'width', w)
    # print('n_blocks remainder', n_blocks, remainder)

    # fixed vertical band centered at the seam between the two tiles
    y0 = int(h - fal_cap / 2)
    y1 = int(h + fal_cap / 2)
    y0_clamped = max(0, y0)
    y1_clamped = min(tiled_img.shape[0], y1)

    # Vertical inpainting
    for n in tqdm(range(n_blocks), desc="Vertical inpainting"):
        print(f"Processing vertical block {n+1}/{n_blocks}")

        # x-range with overlap
        x0 = n * stride
        x1 = x0 + fal_cap

        # clamp to image width
        x0_clamped = max(0, x0)
        x1_clamped = min(w, x1)

        # --- NEW: enforce last-crop constraints (no right-edge trim) ---
        if n == n_blocks - 1:
            # print('x0_clamped', x0_clamped)
            avail = x1_clamped - x0_clamped
            # target width: ceil to multiple of 32, at least 640
            target = max(640, int(np.ceil(avail / 32.0) * 32))
            # keep the right edge fixed; extend left if needed
            x0_clamped = max(0, x1_clamped - target)
            # print('chosen x0_clamped', x0_clamped)
        # --- END NEW ---

        cropped_img_rest = tiled_img[y0_clamped:y1_clamped, x0_clamped:x1_clamped]
        cropped_mask_rest = mask[y0_clamped:y1_clamped, x0_clamped:x1_clamped]

        if n > 0:
            # zero the LEFT part of the overlap to preserve previous inpaint
            avail_w = x1_clamped - x0_clamped
            cutoff = max(0, min(inpaint_context - inpaint_buffer, avail_w))
            cropped_mask_rest[:, :cutoff] = 0

        # Save debug outputs for vertical inpainting
        imsave(f'{debug_dir}/cropped_img_rest_vertical_{n}.png', cropped_img_rest)
        imsave(f'{debug_dir}/cropped_mask_rest_vertical_{n}.png', cropped_mask_rest)

        # print('crops', np.shape(cropped_img_rest), np.shape(cropped_mask_rest))
        # sub_plotter([cropped_img_rest, cropped_mask_rest])

        img_np = inpaint(cropped_img_rest, cropped_mask_rest)
        
        # Save inpainted result
        imsave(f'{debug_dir}/img_np_vertical_{n}.png', img_np)
        
        # p(img_np)

        if np.max(tiled_img) > 1 and np.max(img_np) > 1:
            tiled_img[y0_clamped:y1_clamped, x0_clamped:x1_clamped] = img_np.astype(np.float32)
        elif np.max(tiled_img) < 1 and np.max(img_np) > 1:
            tiled_img[y0_clamped:y1_clamped, x0_clamped:x1_clamped] = img_np.astype(np.float32) / 255.
        else:
            assert 'Not expected'

        # out = img_np.astype(np.float32) / 255.0

    # imsave(f'{output_dir}/inpaint_top.png', tiled_img)
    # print('----saved', f'{output_dir}/inpaint_top.png')
    v_strip_h = min(h, int(fal_cap / 2))
    intersection_strip = tiled_img[h - v_strip_h: h, :].copy()  # top part
    tiled_img[-v_strip_h:, :] = intersection_strip
    orig_shape_fabric = tiled_img[h:, :]
    
    # Final save
    output_path = f'{output_dir}/{name}_seamless.png'
    imsave(output_path, orig_shape_fabric)
    print(f'Saved final seamless image: {output_path}')
    print(f'Debug outputs saved in: {debug_dir}')


def main():
    parser = argparse.ArgumentParser(description='Create seamless tileable texture from image')
    parser.add_argument('image_path', type=str, help='Path to input image')
    parser.add_argument('output_dir', type=str, help='Output directory for seamless image')
    
    args = parser.parse_args()
    
    if not os.path.exists(args.image_path):
        print(f"Error: Image path '{args.image_path}' does not exist")
        return
    
    process_image(args.image_path, args.output_dir)


if __name__ == '__main__':
    main()
