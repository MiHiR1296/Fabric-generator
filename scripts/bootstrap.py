#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
FRONTEND_DIR = ROOT / "frontend"
DEFAULT_MAC_BLENDER = Path("/Applications/Blender.app/Contents/MacOS/Blender")


def _run(command: list[str], *, cwd: Path | None = None) -> None:
    print(f"+ {' '.join(command)}")
    subprocess.run(command, cwd=str(cwd) if cwd else None, check=True)


def _python_in_venv() -> Path:
    if platform.system().lower().startswith("win"):
        return BACKEND_DIR / ".venv" / "Scripts" / "python.exe"
    return BACKEND_DIR / ".venv" / "bin" / "python"


def _detect_blender() -> Path | None:
    env_value = os.environ.get("BLENDER_BINARY_PATH", "").strip()
    if env_value:
        candidate = Path(env_value).expanduser()
        if candidate.exists():
            return candidate
    which_path = shutil.which("blender")
    if which_path:
        return Path(which_path)
    if DEFAULT_MAC_BLENDER.exists():
        return DEFAULT_MAC_BLENDER
    return None


def _install_blender() -> None:
    if _detect_blender() is not None:
        print("Blender is already available; skipping system install.")
        return

    system = platform.system().lower()
    if system == "darwin" and shutil.which("brew"):
        _run(["brew", "install", "--cask", "blender"])
        return
    if shutil.which("apt-get"):
        _run(["sudo", "apt-get", "update"])
        _run(["sudo", "apt-get", "install", "-y", "blender"])
        return
    if shutil.which("dnf"):
        _run(["sudo", "dnf", "install", "-y", "blender"])
        return
    if shutil.which("yum"):
        _run(["sudo", "yum", "install", "-y", "blender"])
        return
    raise SystemExit(
        "Blender is missing and no supported automatic install route was found. "
        "Install Blender manually or set BLENDER_BINARY_PATH."
    )


def _install_backend() -> None:
    venv_python = _python_in_venv()
    if not venv_python.exists():
        _run([sys.executable, "-m", "venv", str(BACKEND_DIR / ".venv")], cwd=ROOT)
    _run([str(venv_python), "-m", "pip", "install", "--upgrade", "pip"], cwd=BACKEND_DIR)
    _run([str(venv_python), "-m", "pip", "install", "-r", "requirements.txt"], cwd=BACKEND_DIR)


def _install_frontend(*, with_playwright: bool) -> None:
    if shutil.which("npm") is None:
        raise SystemExit("npm was not found. Install Node.js 20+ first or run scripts/setup_doctor.py.")
    _run(["npm", "install"], cwd=FRONTEND_DIR)
    if with_playwright:
        _run(["npx", "playwright", "install", "chromium"], cwd=FRONTEND_DIR)

def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap Fabric Generator on a new machine.")
    parser.add_argument("--with-playwright", action="store_true", help="Install the Chromium browser used by e2e tests.")
    parser.add_argument("--install-blender", action="store_true", help="Attempt to install Blender through a supported package manager.")
    parser.add_argument("--skip-backend", action="store_true", help="Skip backend virtualenv and Python dependency installation.")
    parser.add_argument("--skip-frontend", action="store_true", help="Skip frontend npm installation.")
    args = parser.parse_args()

    if sys.version_info[:2] < (3, 9):
        raise SystemExit("Python 3.9 or newer is required. Run scripts/setup_doctor.py for guidance.")

    if args.install_blender:
        _install_blender()

    if not args.skip_backend:
        _install_backend()

    if not args.skip_frontend:
        _install_frontend(with_playwright=args.with_playwright)

    print()
    print("Bootstrap complete.")
    print("Next steps:")
    print("- Run `python3 scripts/setup_doctor.py --strict` to verify the machine state.")
    print("- Start the backend with `make backend-dev`.")
    print("- Start the frontend with `make frontend-dev`.")
    print("- On Linux servers, set BLENDER_LAUNCH_PREFIX to an xvfb-run wrapper before starting the backend.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
