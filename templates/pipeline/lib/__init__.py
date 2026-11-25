"""Pipeline machinery (scaffolded by the Minecraft Forge toolkit). Yours to edit.

Several mobs can share this lib: pipeline.json "mob" is the first one (package mob/), "mobs" lists every mob and the
others live in mobs/<name>/. build_assets.py runs each selected mob in its own process with PIPELINE_MOB=<name>;
here that mob's package is installed as `mob` before any generator imports it.
"""
from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path

_MOB = os.environ.get("PIPELINE_MOB")
if _MOB and "mob" not in sys.modules:
    _CONFIG = json.loads((Path(__file__).resolve().parent.parent / "pipeline.json").read_text(encoding="utf-8"))
    if _MOB != _CONFIG["mob"]:
        sys.modules["mob"] = importlib.import_module(f"mobs.{_MOB}")
