from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .models import ColorBinding, FabricProject, YarnAsset


def normalize_hex_color(value: str) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        raise ValueError("Color binding entries must include a colorHex value.")
    if not raw.startswith("#"):
        raw = f"#{raw}"
    if len(raw) == 4:
        raw = "#" + "".join(part * 2 for part in raw[1:])
    if len(raw) != 7:
        raise ValueError(f"Unsupported color value: {value}")
    return raw


def derive_color_slots(draft: dict[str, Any]) -> list[dict[str, str]]:
    slots: list[dict[str, str]] = []
    for scope, values in (("warp", draft.get("warpColors") or []), ("weft", draft.get("weftColors") or [])):
        seen: set[str] = set()
        for value in values:
            color = normalize_hex_color(str(value))
            key = f"{scope}:{color}"
            if key in seen:
                continue
            seen.add(key)
            slots.append({"scope": scope, "colorHex": color})
    return slots


def normalize_color_bindings(bindings: list[dict[str, Any]] | None) -> list[ColorBinding]:
    normalized: list[ColorBinding] = []
    for entry in bindings or []:
        scope = str(entry.get("scope") or "").strip().lower()
        if scope not in {"warp", "weft"}:
            raise ValueError(f"Unsupported color binding scope: {scope or 'missing'}")
        normalized.append(
            ColorBinding(
                scope=scope,
                colorHex=normalize_hex_color(str(entry.get("colorHex") or "")),
                yarnAssetId=str(entry.get("yarnAssetId")) if entry.get("yarnAssetId") else None,
            )
        )
    return normalized


def validate_project_bindings(
    draft: dict[str, Any],
    bindings: list[ColorBinding],
    assets: dict[str, YarnAsset],
) -> tuple[list[ColorBinding], list[int], list[int], list[YarnAsset]]:
    slots = derive_color_slots(draft)
    binding_lookup = {(binding.scope, binding.colorHex): binding for binding in bindings}
    missing = [
        f"{slot['scope']} {slot['colorHex']}"
        for slot in slots
        if not binding_lookup.get((slot["scope"], slot["colorHex"])) or not binding_lookup[(slot["scope"], slot["colorHex"])].yarnAssetId
    ]
    if missing:
        raise ValueError("Every visible draft color must be assigned before rendering. Missing: " + ", ".join(missing))

    asset_rows: dict[str, int] = {}
    ordered_assets: list[YarnAsset] = []

    def material_id_for(scope: str, color_hex: str) -> int:
        binding = binding_lookup[(scope, color_hex)]
        assert binding.yarnAssetId is not None
        asset = assets.get(binding.yarnAssetId)
        if asset is None:
            raise ValueError(f"Assigned yarn asset {binding.yarnAssetId} does not exist.")
        if asset.status != "ready":
            raise ValueError(f"Assigned yarn asset {asset.label} is not ready yet.")
        if asset.id not in asset_rows:
            asset_rows[asset.id] = len(ordered_assets)
            ordered_assets.append(asset)
        return asset_rows[asset.id]

    warp_material_ids = [
        material_id_for("warp", normalize_hex_color(str(color)))
        for color in draft.get("warpColors") or []
    ]
    weft_material_ids = [
        material_id_for("weft", normalize_hex_color(str(color)))
        for color in draft.get("weftColors") or []
    ]
    return bindings, warp_material_ids, weft_material_ids, ordered_assets


def build_project_snapshot(
    draft: dict[str, Any],
    bindings: list[ColorBinding],
    yarn_assets: list[YarnAsset],
) -> FabricProject:
    return FabricProject(
        version=1,
        draft=draft,
        yarnAssets=[asset.to_dict() for asset in yarn_assets],
        colorBindings=bindings,
    )


def save_project_snapshot(project: FabricProject, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(project.to_dict(), indent=2), encoding="utf-8")
