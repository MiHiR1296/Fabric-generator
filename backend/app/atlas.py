from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image


@dataclass(frozen=True)
class AtlasBundle:
    diffuse_path: Path
    alpha_path: Path
    rows: int
    tile_width: int
    tile_height: int
    asset_rows: dict[str, int]

    def to_dict(self) -> dict:
        return {
            "diffusePath": str(self.diffuse_path),
            "alphaPath": str(self.alpha_path),
            "rows": self.rows,
            "tileWidth": self.tile_width,
            "tileHeight": self.tile_height,
            "assetRows": self.asset_rows,
        }


def _fit_tile(image: Image.Image, size: tuple[int, int], mode: str) -> Image.Image:
    if image.mode != mode:
        image = image.convert(mode)
    return image.resize(size, Image.Resampling.LANCZOS)


def build_yarn_atlas(asset_images: list[dict], output_dir: Path) -> AtlasBundle:
    if not asset_images:
        raise ValueError("Cannot build a yarn atlas without at least one ready yarn asset.")

    output_dir.mkdir(parents=True, exist_ok=True)
    diffuse_inputs: list[tuple[str, Image.Image]] = []
    alpha_inputs: list[tuple[str, Image.Image]] = []
    max_width = 0
    max_height = 0

    for entry in asset_images:
        asset_id = str(entry["id"])
        diffuse_image = Image.open(entry["diffuse_path"]).convert("RGB")
        alpha_image = Image.open(entry["alpha_path"]).convert("L")
        max_width = max(max_width, diffuse_image.width, alpha_image.width)
        max_height = max(max_height, diffuse_image.height, alpha_image.height)
        diffuse_inputs.append((asset_id, diffuse_image))
        alpha_inputs.append((asset_id, alpha_image))

    rows = len(diffuse_inputs)
    atlas_size = (max_width, max_height * rows)
    diffuse_atlas = Image.new("RGB", atlas_size, (0, 0, 0))
    alpha_atlas = Image.new("L", atlas_size, 0)
    asset_rows: dict[str, int] = {}

    for row_index, ((asset_id, diffuse_image), (_, alpha_image)) in enumerate(zip(diffuse_inputs, alpha_inputs)):
        atlas_row = row_index
        asset_rows[asset_id] = atlas_row
        paste_y = (rows - atlas_row - 1) * max_height
        diffuse_atlas.paste(_fit_tile(diffuse_image, (max_width, max_height), "RGB"), (0, paste_y))
        alpha_atlas.paste(_fit_tile(alpha_image, (max_width, max_height), "L"), (0, paste_y))

    diffuse_path = output_dir / "diffuse_atlas.png"
    alpha_path = output_dir / "alpha_atlas.png"
    diffuse_atlas.save(diffuse_path)
    alpha_atlas.save(alpha_path)

    return AtlasBundle(
        diffuse_path=diffuse_path,
        alpha_path=alpha_path,
        rows=rows,
        tile_width=max_width,
        tile_height=max_height,
        asset_rows=asset_rows,
    )
