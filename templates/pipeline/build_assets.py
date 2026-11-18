"""Asset pipeline entry point (scaffolded by the Minecraft Forge toolkit: pipeline PROJECT). Yours to edit.

Usage: python -I asset-pipeline/build_assets.py <command> [--validate] [args]

Commands: check rig model texture anim sheets sounds springs release plan all

Every generated file under the mod's resources and gen/ package comes from here: a fix is "change the
generator, rerun, rebuild", never a hand edit of the output. The script provisions its own virtual
environment (asset-pipeline/.venv: numpy, pillow) with uv, or with venv + pip when uv is not installed,
and re-executes itself inside it.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
VENV = HERE / ".venv"
VPY = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _have_modules() -> bool:
    try:
        import numpy  # noqa: F401
        import PIL  # noqa: F401
        return True
    except ImportError:
        return False


def _ensure_venv() -> None:
    """Re-exec inside the pipeline venv unless this interpreter already has the modules."""
    if Path(sys.prefix).resolve() == VENV.resolve() or (os.environ.get("PIPELINE_NO_VENV") and _have_modules()):
        return
    if not VPY.exists():
        requirements = str(HERE / "requirements.txt")
        if shutil.which("uv"):
            print("[pipeline] creating .venv with uv", file=sys.stderr)
            subprocess.run(["uv", "venv", "--python", sys.executable, str(VENV)], check=True)
            subprocess.run(["uv", "pip", "install", "--python", str(VPY), "-r", requirements], check=True)
        else:
            print("[pipeline] creating .venv with venv + pip", file=sys.stderr)
            subprocess.run([sys.executable, "-m", "venv", str(VENV)], check=True)
            subprocess.run([str(VPY), "-m", "pip", "install", "-r", requirements], check=True)
    # os.execv on Windows detaches the child and loses its exit code; run it and pass the code on.
    sys.exit(subprocess.run([str(VPY), "-I", str(Path(__file__).resolve()), *sys.argv[1:]]).returncode)


def main(argv: list[str]) -> int:
    _ensure_venv()
    # -I drops the script folder from sys.path; put it back for the lib and mob packages.
    sys.path.insert(0, str(HERE))
    from lib import cli
    return cli.main(argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
