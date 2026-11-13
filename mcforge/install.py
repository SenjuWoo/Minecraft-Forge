"""Install or update the portable toolkit in a versionless local root.

The install is a plain file copy from the explicit product allowlist, followed
by an atomic directory swap. A previous install is kept as a timestamped
backup. No PATH, registry, launcher or global Python settings are changed.
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import tempfile
import time
import uuid

from . import __version__
from .product import product_files
from .workbench import ROOT


def default_root() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
        return base / "Minecraft-Tools" / "Minecraft-Forge"
    return Path.home() / ".local/share/minecraft-forge"


def launcher_path(root: Path) -> Path:
    return root / ("Minecraft-Forge.cmd" if os.name == "nt" else "Minecraft-Forge")


def _write_launcher(stage: Path):
    if os.name == "nt":
        (stage / "Minecraft-Forge.cmd").write_text(
            "@echo off\n"
            "setlocal\n"
            "cd /d \"%~dp0\"\n"
            "if defined UABS_PYTHON (\n"
            "  \"%UABS_PYTHON%\" -m mcforge %*\n"
            ") else (\n"
            "  python -m mcforge %*\n"
            ")\n"
            "exit /b %ERRORLEVEL%\n",
            encoding="utf-8",
            newline="\r\n",
        )
    else:
        launcher = stage / "Minecraft-Forge"
        launcher.write_text(
            "#!/bin/sh\n"
            "cd \"$(dirname \"$0\")\" || exit 1\n"
            "exec \"${UABS_PYTHON:-python3}\" -m mcforge \"$@\"\n",
            encoding="utf-8",
            newline="\n",
        )
        launcher.chmod(0o755)


def install_toolkit(root: Path | None = None, force: bool = False) -> dict:
    """Copy the product to ``root``; replace an existing install only with force."""
    source = ROOT
    target = Path(root).expanduser().resolve() if root else default_root().resolve()
    if target == source or (source in target.parents and (source / "local") not in target.parents):
        raise ValueError("Install root must be outside the source tree; use --root for a dedicated location")
    if target.exists() and not force:
        raise ValueError(f"Install root already exists: {target}; pass --force to replace it")
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{target.name}-", dir=target.parent))
    backup = None
    try:
        files = product_files(source)
        for path in files:
            relative = path.relative_to(source)
            destination = stage / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
        _write_launcher(stage)
        if target.exists():
            backup = target.with_name(target.name + ".bak-" + time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6])
            target.rename(backup)
        stage.rename(target)
        # The previous install's local/ holds the Gradle cache, fetched templates and test scratch: keep it.
        if backup is not None and (backup / "local").is_dir():
            (backup / "local").rename(target / "local")
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        if backup is not None and not target.exists():
            backup.rename(target)
        raise
    launcher = launcher_path(target)
    return {
        "root": str(target),
        "version": __version__,
        "files": len(files),
        "launcher": str(launcher),
        "backup": str(backup) if backup else None,
        "kept": ["local"] if (target / "local").is_dir() else [],
        "next": f"{launcher} doctor",
    }
