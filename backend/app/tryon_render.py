"""Try-On 3D render — drape the generated fabric onto objects in Objects.blend.

This is the Step 4 backend. It takes the user's fabric texture (the seamless
tile from Step 3, or the flat render preview as a fallback), swaps it into the
fabric material of `Renders/Objects.blend`, enables the collection(s) for a
chosen object, and renders it headlessly with the scene's AUTHORED camera (the
angled, intentionally-cropped framing the artist set up). Several targets
selected at once are rendered ONE AT A TIME by a single worker thread, so the UI
can show each result as it lands.

Design + rationale: docs/TryOn3DRender/.

The scene is organized into collections — one per showcase object:
  - "Backdrop_Cloth_08" : the draped cloth (on by default)
  - "Cushion"           : the puffed cushion
  - "Sphere"            : a curved backdrop + physics collider
  - "Collection"        : the camera (always kept on)
A target names the collection(s) it needs; everything else (except the camera's
collection) is excluded for that render. The camera is left exactly as authored.

Reuses the `render_jobs` registry so the existing
`GET /api/blender/render-jobs/{id}` (+ `/image`) endpoints serve Try-On jobs
unchanged. Try-On is ALWAYS headless against Objects.blend — it never uses the
live MCP session (that session holds the weave file, not the object scene).
"""
from __future__ import annotations

import json
import os
import queue
import shutil
import threading
import uuid
from pathlib import Path
from typing import Any

from . import render_jobs
from .render_jobs import (
    HeadlessBlenderConfig,
    RenderJob,
    build_headless_render_command,
    load_headless_blender_config,
)
from .runtime_paths import PROJECT_ROOT, RENDER_JOBS_ROOT, ensure_runtime_dirs


DEFAULT_TRYON_BLEND_FILE = PROJECT_ROOT / "Renders" / "Objects.blend"
DEFAULT_TRYON_TARGETS_FILE = PROJECT_ROOT / "Renders" / "tryon_targets.json"

DEFAULT_RESOLUTION = 1600
MIN_RESOLUTION = 256
MAX_RESOLUTION = 4096
DEFAULT_SAMPLES = 96
MIN_SAMPLES = 1
MAX_SAMPLES = 1024
DEFAULT_FABRIC_MATERIAL = "Material.001"

# Default selectable objects, seeded from the current Objects.blend. Each target
# enables one collection and renders with the authored camera. Override the whole
# catalog with Renders/tryon_targets.json (a bare array or {"targets":[...]}).
# See docs/TryOn3DRender/data_contract.md.
DEFAULT_TARGETS: tuple[dict[str, Any], ...] = (
    {
        "id": "draped_cloth",
        "label": "Draped Cloth",
        "description": "Your fabric draped over a hanging cloth form.",
        "collections": ["Backdrop_Cloth_08"],
        "camera": "",
        "fabricMaterial": "Material.001",
    },
    {
        "id": "cushion",
        "label": "Cushion",
        "description": "Your fabric on a soft puffed cushion.",
        "collections": ["Cushion"],
        "camera": "",
        "fabricMaterial": "Material.001",
    },
)


def tryon_blend_file() -> Path:
    return Path(os.environ.get("TRYON_BLEND_FILE", str(DEFAULT_TRYON_BLEND_FILE))).expanduser()


def tryon_targets_file() -> Path:
    return Path(os.environ.get("TRYON_TARGETS_FILE", str(DEFAULT_TRYON_TARGETS_FILE))).expanduser()


def _as_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str) and item]


def _normalize_target(raw: dict[str, Any]) -> dict[str, Any] | None:
    target_id = raw.get("id")
    if not isinstance(target_id, str) or not target_id:
        return None
    return {
        "id": target_id,
        "label": str(raw.get("label") or target_id),
        "description": str(raw.get("description") or ""),
        "collections": _as_str_list(raw.get("collections")),
        # "" (or missing) means: keep the scene's authored active camera.
        "camera": str(raw.get("camera") or ""),
        "fabricMaterial": str(raw.get("fabricMaterial") or DEFAULT_FABRIC_MATERIAL),
    }


def load_tryon_targets() -> list[dict[str, Any]]:
    """Return the target catalog. Override file wins if present and valid;
    otherwise the built-in defaults."""
    override_path = tryon_targets_file()
    if override_path.exists():
        try:
            data = json.loads(override_path.read_text(encoding="utf-8"))
            raw_targets = data.get("targets") if isinstance(data, dict) else data
            if isinstance(raw_targets, list):
                normalized = [_normalize_target(item) for item in raw_targets if isinstance(item, dict)]
                normalized = [item for item in normalized if item is not None]
                if normalized:
                    return normalized
        except (ValueError, OSError):
            pass
    return [_normalize_target(dict(item)) for item in DEFAULT_TARGETS]  # type: ignore[misc]


def get_tryon_target(target_id: str) -> dict[str, Any] | None:
    for target in load_tryon_targets():
        if target["id"] == target_id:
            return target
    return None


def public_targets() -> list[dict[str, Any]]:
    return [
        {"id": t["id"], "label": t["label"], "description": t["description"]}
        for t in load_tryon_targets()
    ]


# This Python body runs inside headless Blender opened on Objects.blend. It reads
# the inlined `_TRYON` config dict and renders one target by enabling its
# collection(s) and rendering with the authored camera. Kept as a string so it
# ships to the subprocess; the calling code only fills in `_TRYON`.
_TRYON_BODY = r'''
import bpy, json, os

_status = {"ok": False, "target": _TRYON.get("targetId"), "steps": []}

def _step(msg):
    _status["steps"].append(msg)

def _find_image_node(mat, bsdf_input_name, via_normal_map=False):
    nt = mat.node_tree
    bsdf = None
    for n in nt.nodes:
        if n.type == 'BSDF_PRINCIPLED':
            bsdf = n
            break
    if bsdf is None:
        return None
    sock = bsdf.inputs.get(bsdf_input_name)
    if sock is None or not sock.is_linked:
        return None
    src = sock.links[0].from_node
    if via_normal_map:
        if src.type != 'NORMAL_MAP':
            return None
        cin = src.inputs.get('Color')
        if cin is None or not cin.is_linked:
            return None
        src = cin.links[0].from_node
    return src if src.type == 'TEX_IMAGE' else None

def _walk(lc):
    yield lc
    for child in lc.children:
        for sub in _walk(child):
            yield sub

try:
    mat_name = _TRYON.get("fabricMaterial") or "Material.001"
    mat = bpy.data.materials.get(mat_name)
    if mat is None or not mat.use_nodes:
        raise RuntimeError("fabric material not found or has no nodes: " + str(mat_name))

    # --- diffuse swap ---
    dnode = _find_image_node(mat, 'Base Color') or mat.node_tree.nodes.get('Image Texture.001')
    if dnode is None:
        raise RuntimeError("could not find a base-color image-texture node on " + mat_name)
    dnode.image = bpy.data.images.load(_TRYON["fabricDiffuse"], check_existing=False)
    _step("diffuse->" + dnode.name)

    # --- normal: swap if provided, else neutralize ---
    nmap = None
    for n in mat.node_tree.nodes:
        if n.type == 'NORMAL_MAP':
            nmap = n
            break
    if _TRYON.get("fabricNormal"):
        nnode = _find_image_node(mat, 'Normal', via_normal_map=True) or mat.node_tree.nodes.get('Image Texture.002')
        if nnode is not None:
            nnode.image = bpy.data.images.load(_TRYON["fabricNormal"], check_existing=False)
            _step("normal->" + nnode.name)
    elif nmap is not None and 'Strength' in nmap.inputs:
        nmap.inputs['Strength'].default_value = 0.0
        _step("normal strength->0")

    # --- camera: choose, but DO NOT move it (authored framing is intentional) ---
    cam = None
    cam_name = _TRYON.get("camera")
    if cam_name:
        cam = bpy.data.objects.get(cam_name)
    if cam is None:
        cam = bpy.context.scene.camera
    if cam is None:
        for o in bpy.data.objects:
            if o.type == 'CAMERA':
                cam = o
                break
    if cam is None:
        raise RuntimeError("no camera available in the scene")
    bpy.context.scene.camera = cam

    # --- collections: enable the target's, keep the camera's, exclude the rest ---
    keep = set()
    for coll in cam.users_collection:
        keep.add(coll.name)
    keep.add("Collection")  # camera holder in the default scene
    enable = set(_TRYON.get("collections", []))
    if not enable:
        raise RuntimeError("target lists no collections: " + str(_TRYON.get("targetId")))

    toggled = []
    for lc in _walk(bpy.context.view_layer.layer_collection):
        if lc.name == bpy.context.view_layer.layer_collection.name:
            continue  # never exclude the scene master
        want = (lc.name in enable) or (lc.name in keep)
        lc.exclude = not want
        if want:
            lc.collection.hide_render = False
            toggled.append(lc.name)
    _step("enabled=" + ",".join(sorted(toggled)))
    bpy.context.view_layer.update()

    # --- render settings ---
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    try:
        sc.cycles.samples = int(_TRYON["samples"])
    except Exception:
        pass
    res = int(_TRYON["resolution"])
    sc.render.resolution_x = res
    sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = True
    sc.render.image_settings.file_format = 'PNG'
    sc.render.image_settings.color_mode = 'RGBA'
    sc.render.filepath = _TRYON["renderPath"]
    bpy.ops.render.render(write_still=True)
    _status["ok"] = os.path.exists(_TRYON["renderPath"])
except Exception as exc:
    _status["error"] = str(exc)

print("TRYON_STATUS=" + json.dumps(_status))
'''


def build_tryon_render_script(
    target: dict[str, Any],
    *,
    fabric_diffuse: str | Path,
    render_path: str | Path,
    fabric_normal: str | Path | None = None,
    resolution: int = DEFAULT_RESOLUTION,
    samples: int = DEFAULT_SAMPLES,
) -> str:
    config = {
        "targetId": target["id"],
        "fabricMaterial": target.get("fabricMaterial") or DEFAULT_FABRIC_MATERIAL,
        "fabricDiffuse": str(fabric_diffuse),
        "fabricNormal": str(fabric_normal) if fabric_normal else None,
        "collections": target.get("collections", []),
        "camera": target.get("camera") or "",
        "resolution": int(resolution),
        "samples": int(samples),
        "renderPath": str(Path(render_path)),
    }
    return "import json\n_TRYON = json.loads(" + repr(json.dumps(config)) + ")\n" + _TRYON_BODY


def _clamp(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(round(float(value)))
    except (TypeError, ValueError):
        return default
    return min(maximum, max(minimum, parsed))


def resolve_source_image(source_job_id: str) -> Path:
    """Resolve a finished Step-3 render/tile job id to its on-disk image."""
    image_path = render_jobs.get_render_image_path(source_job_id)
    if image_path is None or not image_path.exists():
        raise ValueError(
            f"Source render '{source_job_id}' has no finished image yet. "
            "Render or tile your fabric on Step 3 first."
        )
    return image_path


def _tryon_blender_config() -> HeadlessBlenderConfig:
    base = load_headless_blender_config()
    return HeadlessBlenderConfig(
        blender_binary=base.blender_binary,
        blend_file=tryon_blend_file(),
        runtime_root=base.runtime_root,
    )


# ---- single-worker sequential render queue --------------------------------
_QUEUE: "queue.Queue[tuple[str, list[str], HeadlessBlenderConfig]]" = queue.Queue()
_WORKER: threading.Thread | None = None
_WORKER_LOCK = threading.Lock()
_BATCHES: dict[str, list[str]] = {}


def _worker_loop() -> None:
    while True:
        job_id, command, config = _QUEUE.get()
        try:
            # _run_headless_render handles status transitions + image_url and
            # never raises (it records failures on the job), so the queue keeps
            # draining even if a render dies.
            render_jobs._run_headless_render(job_id, command, config)
        except Exception:  # pragma: no cover - defensive; runner is non-throwing
            pass
        finally:
            _QUEUE.task_done()


def _ensure_worker() -> None:
    global _WORKER
    with _WORKER_LOCK:
        if _WORKER is None or not _WORKER.is_alive():
            _WORKER = threading.Thread(target=_worker_loop, daemon=True, name="tryon-render-worker")
            _WORKER.start()


def submit_tryon_render_batch(
    target_ids: list[str],
    *,
    source_image_path: Path,
    normal_image_path: Path | None = None,
    resolution: int | None = None,
    samples: int | None = None,
) -> dict[str, Any]:
    ensure_runtime_dirs()
    if not target_ids:
        raise ValueError("Select at least one object to render.")

    catalog = {t["id"]: t for t in load_tryon_targets()}
    targets: list[dict[str, Any]] = []
    for target_id in target_ids:
        target = catalog.get(target_id)
        if target is None:
            raise ValueError(f"Unknown render target: {target_id}")
        targets.append(target)

    config = _tryon_blender_config()
    # Validate the blend + binary exist up front so submit fails fast with a
    # clear message instead of every job dying in the worker.
    render_jobs.validate_headless_blender_config(config)

    res = _clamp(resolution, DEFAULT_RESOLUTION, MIN_RESOLUTION, MAX_RESOLUTION)
    smp = _clamp(samples, DEFAULT_SAMPLES, MIN_SAMPLES, MAX_SAMPLES)

    batch_id = f"tryon_{uuid.uuid4().hex[:10]}"
    jobs_summary: list[dict[str, Any]] = []
    job_ids: list[str] = []

    diffuse_suffix = source_image_path.suffix or ".png"
    normal_suffix = normal_image_path.suffix if normal_image_path else ".png"

    for index, target in enumerate(targets):
        job_id = f"{batch_id}_{index}"
        job_dir = RENDER_JOBS_ROOT / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        diffuse_dest = job_dir / f"fabric_diffuse{diffuse_suffix}"
        shutil.copyfile(source_image_path, diffuse_dest)
        normal_dest: Path | None = None
        if normal_image_path is not None and normal_image_path.exists():
            normal_dest = job_dir / f"fabric_normal{normal_suffix}"
            shutil.copyfile(normal_image_path, normal_dest)

        render_path = job_dir / "preview.png"
        script_text = build_tryon_render_script(
            target,
            fabric_diffuse=diffuse_dest,
            fabric_normal=normal_dest,
            render_path=render_path,
            resolution=res,
            samples=smp,
        )
        script_path = job_dir / "render_job.py"
        script_path.write_text(script_text, encoding="utf-8")
        (job_dir / "tryon.json").write_text(
            json.dumps(
                {
                    "batchId": batch_id,
                    "targetId": target["id"],
                    "target": target,
                    "sourceImage": str(source_image_path),
                    "resolution": res,
                    "samples": smp,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        job = RenderJob(
            id=job_id,
            status="queued",
            message=f"Queued '{target['label']}' for the Try-On render.",
            draft_title=target["label"],
            target_object_name=target["id"],
            draft_object_name=batch_id,
            created_at=render_jobs._utc_now(),
            job_dir=job_dir,
            render_path=render_path,
            script_path=script_path,
            stdout_path=job_dir / "stdout.log",
            stderr_path=job_dir / "stderr.log",
        )
        with render_jobs._LOCK:
            render_jobs._JOBS[job_id] = job

        command = build_headless_render_command(config, script_path=script_path)
        _ensure_worker()
        _QUEUE.put((job_id, command, config))

        job_ids.append(job_id)
        jobs_summary.append(
            {
                "targetId": target["id"],
                "label": target["label"],
                "jobId": job_id,
                "status": "queued",
            }
        )

    _BATCHES[batch_id] = job_ids
    return {"batchId": batch_id, "jobs": jobs_summary}


def get_tryon_batch(batch_id: str) -> dict[str, Any] | None:
    job_ids = _BATCHES.get(batch_id)
    if job_ids is None:
        return None
    jobs = []
    for job_id in job_ids:
        snapshot = render_jobs.get_render_job(job_id)
        if snapshot is not None:
            jobs.append(snapshot)
    return {"batchId": batch_id, "jobs": jobs}
