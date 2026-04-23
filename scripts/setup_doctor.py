#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
FRONTEND_DIR = ROOT / "frontend"
DEFAULT_MAC_BLENDER = Path("/Applications/Blender.app/Contents/MacOS/Blender")
MIN_PYTHON = (3, 9, 0)
MIN_NODE = (20, 0, 0)


@dataclass
class CheckResult:
    key: str
    label: str
    required: bool
    ok: bool
    found: str | None
    required_version: str | None
    path: str | None
    install_hint: str | None
    notes: str | None = None


def _run_capture(command: list[str]) -> str | None:
    try:
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    return (completed.stdout or completed.stderr).strip() or None


def _parse_version(text: str | None) -> tuple[int, int, int] | None:
    if not text:
        return None
    match = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", text)
    if not match:
        return None
    major = int(match.group(1))
    minor = int(match.group(2))
    patch = int(match.group(3) or 0)
    return (major, minor, patch)


def _version_text(version: tuple[int, int, int] | None) -> str | None:
    if version is None:
        return None
    return ".".join(str(part) for part in version)


def _meets_minimum(found: tuple[int, int, int] | None, minimum: tuple[int, int, int] | None) -> bool:
    if minimum is None:
        return found is not None
    if found is None:
        return False
    return found >= minimum


def _detect_package_manager() -> str | None:
    for candidate in ("brew", "apt-get", "dnf", "yum"):
        if shutil.which(candidate):
            return candidate
    return None


def _blender_candidate() -> tuple[str | None, str | None]:
    env_path_value = os.environ.get("BLENDER_BINARY_PATH", "").strip()
    if env_path_value:
        path = Path(env_path_value).expanduser()
        return str(path), "BLENDER_BINARY_PATH"

    which_path = shutil.which("blender")
    if which_path:
        return which_path, "PATH"

    if DEFAULT_MAC_BLENDER.exists():
        return str(DEFAULT_MAC_BLENDER), "default-macos"

    return None, None

def _install_hint(tool: str, *, optional: bool = False) -> str | None:
    package_manager = _detect_package_manager()
    system = platform.system().lower()

    if tool == "python":
        if system == "darwin" and package_manager == "brew":
            return "brew install python@3.11"
        if package_manager == "apt-get":
            return "sudo apt-get update && sudo apt-get install -y python3.11 python3.11-venv python3-pip"
        if package_manager == "dnf":
            return "sudo dnf install -y python3.11 python3-pip"
        return "Install Python 3.11 or newer."

    if tool == "node":
        if system == "darwin" and package_manager == "brew":
            return "brew install node@20"
        if package_manager == "apt-get":
            return "Install Node.js 20+ from NodeSource or your distro package manager."
        if package_manager == "dnf":
            return "sudo dnf install -y nodejs npm"
        return "Install Node.js 20 or newer."

    if tool == "blender":
        if system == "darwin" and package_manager == "brew":
            return "brew install --cask blender"
        if package_manager == "apt-get":
            return "sudo apt-get update && sudo apt-get install -y blender"
        if package_manager == "dnf":
            return "sudo dnf install -y blender"
        if package_manager == "yum":
            return "sudo yum install -y blender"
        return "Install Blender and point BLENDER_BINARY_PATH at the binary if it is not on PATH."

    if tool == "xvfb":
        if package_manager == "apt-get":
            return "sudo apt-get update && sudo apt-get install -y xvfb"
        if package_manager == "dnf":
            return "sudo dnf install -y xorg-x11-server-Xvfb"
        if package_manager == "yum":
            return "sudo yum install -y xorg-x11-server-Xvfb"
        return None if optional else "Install Xvfb for terminal-only Linux preview hosts."

    if tool == "gh":
        if system == "darwin" and package_manager == "brew":
            return "brew install gh"
        if package_manager == "apt-get":
            return "See https://cli.github.com/ for install instructions."
        return "Install GitHub CLI if you want to push, branch, or open PRs from this machine."

    return None


def _tool_check(
    *,
    key: str,
    label: str,
    command_name: str,
    version_args: list[str],
    required: bool,
    minimum: tuple[int, int, int] | None = None,
    explicit_path: str | None = None,
    install_hint: str | None = None,
    notes: str | None = None,
) -> CheckResult:
    path = explicit_path or shutil.which(command_name)
    output = _run_capture(([path] if explicit_path else [command_name]) + version_args) if path else None
    found_version = _parse_version(output)
    found_text = output.splitlines()[0] if output else None
    ok = _meets_minimum(found_version, minimum) if required else (path is not None)
    return CheckResult(
        key=key,
        label=label,
        required=required,
        ok=ok,
        found=found_text,
        required_version=_version_text(minimum),
        path=path,
        install_hint=install_hint,
        notes=notes,
    )


def _load_python_packages() -> list[str]:
    requirements_path = BACKEND_DIR / "requirements.txt"
    if not requirements_path.exists():
        return []
    packages: list[str] = []
    for line in requirements_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        packages.append(stripped)
    return packages


def _load_frontend_packages() -> dict[str, list[str]]:
    package_path = FRONTEND_DIR / "package.json"
    if not package_path.exists():
        return {"dependencies": [], "devDependencies": []}
    package_json = json.loads(package_path.read_text(encoding="utf-8"))
    return {
        "dependencies": [f"{name}@{version}" for name, version in sorted(package_json.get("dependencies", {}).items())],
        "devDependencies": [
            f"{name}@{version}" for name, version in sorted(package_json.get("devDependencies", {}).items())
        ],
    }


def collect_report() -> dict[str, Any]:
    system = platform.system()
    blender_path, blender_source = _blender_candidate()
    checks = [
        CheckResult(
            key="python",
            label="Python",
            required=True,
            ok=sys.version_info[:3] >= MIN_PYTHON,
            found=platform.python_version(),
            required_version=_version_text(MIN_PYTHON),
            path=sys.executable,
            install_hint=_install_hint("python"),
        ),
        _tool_check(
            key="node",
            label="Node.js",
            command_name="node",
            version_args=["--version"],
            required=True,
            minimum=MIN_NODE,
            install_hint=_install_hint("node"),
        ),
        _tool_check(
            key="npm",
            label="npm",
            command_name="npm",
            version_args=["--version"],
            required=True,
            install_hint=_install_hint("node"),
        ),
        _tool_check(
            key="git",
            label="Git",
            command_name="git",
            version_args=["--version"],
            required=True,
            install_hint="Install Git from https://git-scm.com/ if it is not already present.",
        ),
        _tool_check(
            key="blender",
            label="Blender",
            command_name="blender",
            version_args=["--version"],
            required=True,
            explicit_path=blender_path,
            install_hint=_install_hint("blender"),
            notes=f"Detected via {blender_source}." if blender_source else None,
        ),
        _tool_check(
            key="gh",
            label="GitHub CLI",
            command_name="gh",
            version_args=["--version"],
            required=False,
            install_hint=_install_hint("gh", optional=True),
            notes="Optional, but useful for publishing branches and PRs from this machine.",
        ),
    ]

    if system.lower() == "linux":
        checks.append(
            _tool_check(
                key="xvfb",
                label="Xvfb",
                command_name="xvfb-run",
                version_args=["--help"],
                required=False,
                install_hint=_install_hint("xvfb", optional=True),
                notes="Recommended for managed Blender previews on terminal-only Linux servers.",
            )
        )
        checks.append(
            _tool_check(
                key="nvidia-smi",
                label="NVIDIA driver tools",
                command_name="nvidia-smi",
                version_args=["--version"],
                required=False,
                install_hint=None,
                notes="Optional, but helpful when validating GPU-backed Blender hosts.",
            )
        )

    repo_state = {
        "backendVenv": (BACKEND_DIR / ".venv").exists(),
        "frontendNodeModules": (FRONTEND_DIR / "node_modules").exists(),
        "playwrightCache": ((Path.home() / "Library" / "Caches" / "ms-playwright").exists())
        or ((Path.home() / ".cache" / "ms-playwright").exists()),
    }
    python_packages = _load_python_packages()
    frontend_packages = _load_frontend_packages()
    required_failures = [check for check in checks if check.required and not check.ok]

    return {
        "repoRoot": str(ROOT),
        "system": {
            "platform": system,
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "checks": [asdict(check) for check in checks],
        "repoState": repo_state,
        "pythonPackages": python_packages,
        "frontendPackages": frontend_packages,
        "ready": not required_failures,
        "nextSteps": [
            "python3 scripts/bootstrap.py --with-playwright",
            "python3 scripts/bootstrap.py --install-blender",
            "export BLENDER_LAUNCH_PREFIX='xvfb-run -a -s \"-screen 0 1920x1080x24\"'  # Linux servers",
        ],
    }


def _print_report(report: dict[str, Any]) -> None:
    print("Fabric Generator Setup Doctor")
    print(f"Repo: {report['repoRoot']}")
    system = report["system"]
    print(f"System: {system['platform']} {system['release']} ({system['machine']})")
    print()

    print("Required tools")
    for check in report["checks"]:
        if not check["required"]:
            continue
        state = "OK" if check["ok"] else "MISSING"
        found = check["found"] or "not found"
        print(f"- [{state}] {check['label']}: {found}")
        if check["path"]:
            print(f"  path: {check['path']}")
        if check["required_version"]:
            print(f"  required: {check['required_version']}+")
        if check["notes"]:
            print(f"  notes: {check['notes']}")
        if not check["ok"] and check["install_hint"]:
            print(f"  install: {check['install_hint']}")

    optional_checks = [check for check in report["checks"] if not check["required"]]
    if optional_checks:
        print()
        print("Optional tools")
        for check in optional_checks:
            state = "OK" if check["ok"] else "MISSING"
            found = check["found"] or "not found"
            print(f"- [{state}] {check['label']}: {found}")
            if check["notes"]:
                print(f"  notes: {check['notes']}")
            if not check["ok"] and check["install_hint"]:
                print(f"  install: {check['install_hint']}")

    print()
    print("Repo install state")
    repo_state = report["repoState"]
    print(f"- backend virtualenv present: {'yes' if repo_state['backendVenv'] else 'no'}")
    print(f"- frontend node_modules present: {'yes' if repo_state['frontendNodeModules'] else 'no'}")
    print(f"- Playwright browser cache present: {'yes' if repo_state['playwrightCache'] else 'no'}")

    print()
    print("Backend Python packages")
    for package in report["pythonPackages"]:
        print(f"- {package}")

    print()
    print("Frontend npm packages")
    for group_name in ("dependencies", "devDependencies"):
        print(f"- {group_name}:")
        packages = report["frontendPackages"][group_name]
        if not packages:
            print("  none")
            continue
        for package in packages:
            print(f"  {package}")

    print()
    print("Suggested next steps")
    for step in report["nextSteps"]:
        print(f"- {step}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check whether this machine is ready to run Fabric Generator.")
    parser.add_argument("--json", action="store_true", help="Print the report as JSON.")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when required tools are missing.")
    args = parser.parse_args()

    report = collect_report()
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        _print_report(report)

    if args.strict and not report["ready"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
