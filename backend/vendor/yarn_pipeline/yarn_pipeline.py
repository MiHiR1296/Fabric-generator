"""
Yarn pipeline orchestrator: one image in, two images out.

Given a raw yarn photo, produces two artifacts:

  1. {name}_seamless.png  — tileable diffuse map
      (orientation-corrected, centerline-leveled, core-cropped,
       then passed through the seamless inpainter)

  2. {name}_alpha.png     — alpha matte of the same seamless tile
      (pure yarn-alpha pipeline on the seamless image — no extra
       rotate/crop since the seamless image is already horizontal
       and centered)

Stages:

    INPUT  ->  [preprocess]  ->  [seamless]  ->  [alpha]  ->  OUTPUTS
              rotate+level+crop    LaMa inpaint   full yarn-alpha

=============================================================================
INTEGRATION REFERENCE — copy-paste this into any host codebase
=============================================================================

Python API (single call):

    from yarn_pipeline import run_pipeline
    result = run_pipeline(
        input_path="photo.tif",         # required: any PIL-readable image
        output_dir="/path/to/out",      # required: created if missing
        preset="auto",                  # "auto" | "white_bg" | "black_bg"
        orientation="auto",             # "auto" | "horizontal" | "vertical"
        hardcut_cutoff=None,            # 0..255 int, or None for preset default
        keep_intermediate=False,        # True -> also saves _preprocessed.png
        verbose=True,
    )
    # result = {
    #   "input":          "photo.tif",
    #   "seamless":       ".../photo_seamless.png",   # <- diffuse output
    #   "alpha":          ".../photo_alpha.png",      # <- alpha output
    #   "preprocessed":   ".../photo_preprocessed.png" or None,
    #   "preprocess_meta": {orientation, level, active_preset, ...},
    #   "alpha_meta":      {bp, wp, gamma, hardcut_cutoff, ...},
    # }

CLI (for subprocess / shell callers):

    python yarn_pipeline.py INPUT OUTPUT_DIR
        [--preset auto|white_bg|black_bg]
        [--orientation auto|horizontal|vertical]
        [--hardcut-cutoff INT]
        [--keep-intermediate]
        [--quiet]

    prints a single-line JSON of {seamless, alpha, preprocessed} on stdout.

Individual stages (reassemblable from the shell):

    # Stage 1 — preprocess only
    python alpha_pipeline.py IN OUT.png --preprocess-only

    # Stage 2 — seamless
    python seamless_converter.py IN.png OUT_DIR   # writes {name}_seamless.png

    # Stage 3 — alpha on an already-horizontal input
    python alpha_pipeline.py IN.png OUT_alpha.png --orientation horizontal --no-level

Output naming convention:

    For input      foo.tif
    outputs are    foo_seamless.png
                   foo_alpha.png
                  [foo_preprocessed.png]  if keep_intermediate=True

Performance (reference — Mac M-series, china_grey 1827×15949):
    preprocess:  ~0.5s   seamless: ~12s   alpha: ~1.5s   total: ~14s

Failure modes the caller should handle:
    FileNotFoundError           — input doesn't exist
    ValueError                  — unknown preset
    Any Exception from inpaint  — LaMa/seamless stage failure

Required local assets:
    Provide big-lama.pt through BIG_LAMA_MODEL_PATH / LAMA_MODEL, or place it
    in one of the documented local model locations. Model weights are not
    tracked in Git.
"""
import argparse
import json
import os
import shutil
import sys
import tempfile
from typing import Optional

import alpha_pipeline
import seamless_converter


def run_pipeline(
    input_path: str,
    output_dir: str,
    preset: str = "auto",
    orientation: str = "auto",
    hardcut_cutoff: Optional[int] = None,
    keep_intermediate: bool = False,
    verbose: bool = True,
) -> dict:
    """Run preprocess -> seamless -> alpha. Returns a dict of output paths
    and per-stage meta. Raises on any stage failure."""
    if not os.path.isfile(input_path):
        raise FileNotFoundError(input_path)
    os.makedirs(output_dir, exist_ok=True)

    name, _ = os.path.splitext(os.path.basename(input_path))
    tmp_dir = tempfile.mkdtemp(prefix="yarn_pipeline_")
    try:
        # --- Stage 1: preprocess ---------------------------------------
        preprocessed_path = (
            os.path.join(output_dir, f"{name}_preprocessed.png")
            if keep_intermediate
            else os.path.join(tmp_dir, f"{name}_preprocessed.png")
        )
        if verbose:
            print(f"[1/3] preprocess -> {preprocessed_path}")
        pre_meta = alpha_pipeline.preprocess(
            input_path, preprocessed_path,
            preset=preset, orientation=orientation, level=True,
        )
        if verbose:
            print(f"      orient={pre_meta['orientation']}"
                  f" preset={pre_meta['active_preset']}"
                  f" angle={pre_meta['level']['angle_deg']}°"
                  f" cropped={pre_meta['level'].get('cropped_size')}")

        # --- Stage 2: seamless ------------------------------------------
        # seamless_converter.process_image writes "{name}_seamless.png"
        # into the given dir. We point it at output_dir with the
        # preprocessed filename so the output name matches the input.
        if verbose:
            print(f"[2/3] seamless  -> {output_dir}/{name}_preprocessed_seamless.png")
        seamless_converter.process_image(preprocessed_path, output_dir)
        seamless_raw = os.path.join(output_dir, f"{name}_preprocessed_seamless.png")
        seamless_path = os.path.join(output_dir, f"{name}_seamless.png")
        if seamless_raw != seamless_path:
            os.replace(seamless_raw, seamless_path)

        # --- Stage 3: alpha ---------------------------------------------
        alpha_path = os.path.join(output_dir, f"{name}_alpha.png")
        if verbose:
            print(f"[3/3] alpha     -> {alpha_path}")
        overrides = {}
        if hardcut_cutoff is not None:
            overrides["hardcut"] = hardcut_cutoff
        # Seamless output is already horizontal + leveled, so skip those.
        alpha_meta = alpha_pipeline.run(
            seamless_path, alpha_path,
            preset=preset,
            overrides=overrides or None,
            orientation="horizontal",
            level=False,
        )
        if verbose:
            print(f"      preset={alpha_meta['active_preset']}"
                  f" bp={alpha_meta['bp']} wp={alpha_meta['wp']}"
                  f" γ={alpha_meta['gamma']} cut={alpha_meta['hardcut_cutoff']}")

        return {
            "input": input_path,
            "seamless": seamless_path,
            "alpha": alpha_path,
            "preprocessed": preprocessed_path if keep_intermediate else None,
            "preprocess_meta": pre_meta,
            "alpha_meta": alpha_meta,
        }
    finally:
        if not keep_intermediate:
            shutil.rmtree(tmp_dir, ignore_errors=True)


def _main():
    ap = argparse.ArgumentParser(description="Yarn pipeline: preprocess -> seamless -> alpha.")
    ap.add_argument("input", help="Input yarn photo (any PIL-readable format).")
    ap.add_argument("output_dir", help="Directory to write _seamless.png + _alpha.png.")
    ap.add_argument("--preset", choices=["auto", "white_bg", "black_bg"], default="auto")
    ap.add_argument("--orientation", choices=["auto", "horizontal", "vertical"], default="auto")
    ap.add_argument("--hardcut-cutoff", type=int, default=None,
                    help="Alpha-stage hardcut (0-255). Default per preset.")
    ap.add_argument("--keep-intermediate", action="store_true",
                    help="Also save the preprocessed RGB for debugging.")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    result = run_pipeline(
        input_path=args.input,
        output_dir=args.output_dir,
        preset=args.preset,
        orientation=args.orientation,
        hardcut_cutoff=args.hardcut_cutoff,
        keep_intermediate=args.keep_intermediate,
        verbose=not args.quiet,
    )
    print(json.dumps({
        "seamless": result["seamless"],
        "alpha": result["alpha"],
        "preprocessed": result["preprocessed"],
    }))


if __name__ == "__main__":
    try:
        _main()
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)
