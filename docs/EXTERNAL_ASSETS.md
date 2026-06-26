# External Assets

Google Drive folder:

https://drive.google.com/drive/folders/18UPKaVFXKBNetcwFR0fXdipJ3HLsZSXU?usp=drive_link

Direct asset bundle:

https://drive.google.com/drive/folders/1z3Ucq0O4ETbsYhVzkTka9l_xxtMeQAsP

The GitHub repo contains the application code, docs, tests, the current weave Blender scene, and the Try-On object scene at `Renders/Objects.blend`. The Drive folder carries local runtime assets that should not live in Git.

## Expected Drive Contents

```text
FabricGenerator_ExternalAssets_2026-05-16/
  README_ASSETS.md
  CHECKSUMS.sha256
  yarn_library/
  models/
    big-lama.pt
```

## Setup For Teammates

Clone the repo:

```bash
git clone https://github.com/MiHiR1296/Fabric-generator.git
cd Fabric-generator
```

Download the Drive folder and place the assets like this:

```text
yarnseamless UI/
  Fabric-generator-tryon/
  yarn_library/
  big-lama.pt
```

If the assets live somewhere else, set:

```bash
export YARN_LIBRARY_ROOT="/absolute/path/to/yarn_library"
export BIG_LAMA_MODEL_PATH="/absolute/path/to/big-lama.pt"
```

Then run:

```bash
make backend-install
make frontend-install
make backend-dev
make frontend-dev
```

Open `http://127.0.0.1:5180`.

## What Not To Share

These are local generated outputs and should not be copied to Drive or Git:

```text
runtime/debug/
runtime/render_jobs/
runtime/yarn_assets/
Renders/*.png
Renders/*.exr
Renders/TMPrenders/
backend/.venv/
frontend/node_modules/
*.blend1
*.pre-*.blend
```
