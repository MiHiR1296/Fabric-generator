# System Setup Workflow

This repo now includes an automated setup path for teammates and for future server rollout work.

## Fast Path

From the repo root:

```bash
python3 scripts/setup_doctor.py
python3 scripts/bootstrap.py --with-playwright
```

If Blender is missing and the machine has a supported package manager:

```bash
python3 scripts/bootstrap.py --install-blender
```

## What The Doctor Checks

`scripts/setup_doctor.py` reports:

- Python version and executable path
- Node.js and npm availability
- Git availability
- Blender availability
- optional GitHub CLI
- optional Linux server helpers such as `xvfb-run` and `nvidia-smi`
- whether `backend/.venv` and `frontend/node_modules` already exist
- whether Playwright browsers have been installed
- the exact backend and frontend package manifests used by this repo

Current validated baseline:

- Python 3.9+
- Node.js 20+
- Blender available locally or through `BLENDER_BINARY_PATH`

Use strict mode in CI or on a fresh machine if you want a non-zero exit code when required tools are missing:

```bash
python3 scripts/setup_doctor.py --strict
```

## What Bootstrap Installs

`scripts/bootstrap.py` handles the safe repo-local setup steps:

- creates `backend/.venv` when needed
- upgrades `pip`
- installs `backend/requirements.txt`
- runs `npm install` in `frontend/`
- optionally installs the Playwright Chromium browser with `--with-playwright`
- optionally tries to install Blender through `brew`, `apt-get`, `dnf`, or `yum`

## Current Dependency Manifests

Backend Python packages from `backend/requirements.txt`:

- `fastapi>=0.115,<1`
- `uvicorn>=0.30,<1`
- `python-multipart>=0.0.9,<1`
- `numpy>=1.26,<3`
- `opencv-python>=4.10,<5`
- `Pillow>=10,<12`
- `scipy>=1.10,<2`
- `matplotlib>=3.7,<4`
- `tqdm>=4.64,<5`
- `torch>=2.2,<3`
- `torchvision>=0.17,<1`
- `simple-lama-inpainting>=0.1,<1`

Frontend npm packages from `frontend/package.json`:

- runtime:
  - `react`
  - `react-dom`
- dev:
  - `@vitejs/plugin-react`
  - `playwright`
  - `vite`

## Local Development Workflow

1. Run the doctor.
2. Run bootstrap.
3. Start the backend: `make backend-dev`
4. Start the frontend: `make frontend-dev`
5. Open `http://127.0.0.1:5180`

For local Blender preview testing, the backend can either:

- attach to an already-running Blender MCP session with `BLENDER_SESSION_MODE=attach`
- or launch Blender on demand with `BLENDER_SESSION_MODE=managed`

## Terminal-Only Linux Server Workflow

For servers where you only get shell access, the managed Blender launcher now supports a command prefix wrapper through `BLENDER_LAUNCH_PREFIX`.

Example:

```bash
export BLENDER_SESSION_MODE=managed
export BLENDER_LAUNCH_PREFIX='xvfb-run -a -s "-screen 0 1920x1080x24"'
python -m app.main
```

That lets the backend launch Blender inside a virtual display instead of requiring an interactive desktop to already be open.

Recommended server checks:

- install Blender
- install `xvfb-run`
- confirm NVIDIA drivers with `nvidia-smi`
- confirm the backend can start and stop managed Blender sessions cleanly
- confirm `/api/blender/live-preview` works before moving on to final render jobs

## Sharing With Teammates

When handing this repo to someone else, ask them to send back the output of:

```bash
python3 scripts/setup_doctor.py
```

That one report should tell us whether they are missing Blender, Node, Python, Playwright, or Linux display dependencies before they spend time debugging the app itself.
