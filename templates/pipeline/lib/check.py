"""Environment check: Python modules, project paths, external tools. Run it first in a new session."""
from __future__ import annotations

import shutil

from . import paths


def run(args) -> int:
    problems = []
    import numpy
    import PIL
    print(f"numpy {numpy.__version__}, pillow {PIL.__version__}")
    print(f"mod {paths.MOD}, mob {paths.MOB}, package {paths.PACKAGE}")
    for label, p in [("project", paths.PROJECT), ("resources", paths.RES), ("lock", paths.PROJECT / "mcforge-project.json")]:
        ok = p.exists()
        print(f"{label:10s} {'ok' if ok else 'MISSING'}  {p}")
        if not ok:
            problems.append(label)
    for tool in (paths.CONFIG.get("toolkit", "minecraft-forge"), "ffmpeg", "ffprobe", "magick", "blender", "assetforge"):
        print(f"{tool:16s} {shutil.which(tool) or 'not on PATH (only needed by the commands that use it)'}")
    return 1 if problems else 0
