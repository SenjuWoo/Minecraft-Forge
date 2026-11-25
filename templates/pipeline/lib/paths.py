"""Project paths, read from pipeline.json. Generators write only below the mod's resources, the gen/ Java package,
MEDIA (review images) and BUILD (intermediate, git-ignored).

Several mobs: "mob" is the first (package mob/, build/, media/, palette.json, spring_gains.json as before); every
other name in "mobs" has its package in mobs/<name>/ and its own build/<name>/ and media/<name>/. A mobs/<name>/
palette.json replaces the shared palette for that mob; its spring gains are mobs/<name>/spring_gains.json."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

PIPE = Path(__file__).resolve().parent.parent
CONFIG = json.loads((PIPE / "pipeline.json").read_text(encoding="utf-8"))
MOD = CONFIG["mod_id"]
PRIMARY = CONFIG["mob"]
MOBS = list(dict.fromkeys([PRIMARY, *CONFIG.get("mobs", [])]))
MOB = os.environ.get("PIPELINE_MOB") or PRIMARY
if MOB not in MOBS:
    raise SystemExit(f"PIPELINE_MOB={MOB!r} is not in pipeline.json (mobs: {', '.join(MOBS)})")
PACKAGE = CONFIG["package"]
PASCAL = "".join(part.capitalize() for part in MOB.split("_"))
PROJECT = (PIPE / CONFIG["project"]).resolve()
ROOT = PIPE.parent
RES = PROJECT / "src/main/resources"
ASSETS = RES / "assets" / MOD
DATA = RES / "data" / MOD
JAVA_GEN = PROJECT.joinpath("src/main/java", *PACKAGE.split("."), "gen")
GEO = ASSETS / "geo/entity"
ANIM = ASSETS / "animations/entity"
TEX = ASSETS / "textures/entity"
SOUNDS = ASSETS / "sounds"
MOB_DIR = PIPE / "mob" if MOB == PRIMARY else PIPE / "mobs" / MOB
MEDIA = (PIPE / CONFIG.get("media", "../media")).resolve() / ("" if MOB == PRIMARY else MOB)
BUILD = PIPE / "build" / ("" if MOB == PRIMARY else MOB)


def ensure(*dirs: Path) -> None:
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def write_json(path: Path, value, compact: bool = False) -> None:
    write_text(path, json.dumps(value, separators=(",", ":")) + "\n" if compact else json.dumps(value, indent=1, ensure_ascii=False) + "\n")


def forge(*args: str) -> subprocess.CompletedProcess:
    """Run the toolkit CLI (model-check, audio-check ...). The command comes from pipeline.json ("toolkit": a name on
    PATH or an argument list); the environment variable MCFORGE_COMMAND (a JSON list) overrides it."""
    command = CONFIG.get("toolkit", "minecraft-forge")
    if os.environ.get("MCFORGE_COMMAND"):
        command = json.loads(os.environ["MCFORGE_COMMAND"])
    prefix = [shutil.which(command) or command] if isinstance(command, str) else list(command)
    return subprocess.run([*prefix, *args], capture_output=True, text=True, shell=False)
