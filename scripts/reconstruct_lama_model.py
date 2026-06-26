#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import shutil
from pathlib import Path


EXPECTED_SHA256 = "7ba7aa7ac37a4d41fdbbeba3a2af7ead18058552997e3a3cd1a3b2210c9e6b4c"
CHUNK_PREFIX = "big-lama.pt.part-"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def reconstruct(repo_root: Path) -> Path:
    chunk_dir = repo_root / "backend" / "vendor" / "yarn_pipeline" / "model_chunks"
    target = repo_root / "backend" / "vendor" / "yarn_pipeline" / "big-lama.pt"
    chunk_paths = sorted(chunk_dir.glob(f"{CHUNK_PREFIX}*"))
    if not chunk_paths:
        raise SystemExit(f"No model chunks found in {chunk_dir}")

    target.parent.mkdir(parents=True, exist_ok=True)
    temp_path = target.with_name(f".{target.name}.tmp")
    with temp_path.open("wb") as destination:
        for chunk_path in chunk_paths:
            print(f"adding {chunk_path.relative_to(repo_root)}")
            with chunk_path.open("rb") as source:
                shutil.copyfileobj(source, destination)
    temp_path.replace(target)

    digest = sha256(target)
    if digest != EXPECTED_SHA256:
        target.unlink(missing_ok=True)
        raise SystemExit(
            f"Reconstructed {target} has sha256 {digest}, expected {EXPECTED_SHA256}. "
            "The model chunks are incomplete or corrupted."
        )
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description="Reconstruct backend/vendor/yarn_pipeline/big-lama.pt from tracked chunks.")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root. Defaults to this script's parent repository.",
    )
    args = parser.parse_args()
    target = reconstruct(args.repo_root.resolve())
    size_mb = target.stat().st_size / 1024 / 1024
    print(f"ready: {target} ({size_mb:.1f} MiB, sha256={EXPECTED_SHA256})")


if __name__ == "__main__":
    main()
