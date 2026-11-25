"""Subcommand dispatch. Each generator module exposes run(args) -> int and, optionally, validate(args) -> int.

`all` runs ALL_ORDER; a command's validator runs right after it when --validate is given, so `all --validate` is
the full offline gate.

Project commands live in mob/, never in lib/ (`pipeline --force` refreshes lib/): an optional mob/commands.py with
    COMMANDS = {"blocks": "mob.shroomblock", "overlays": "mob.overlays"}   # name -> module with run(args)
    ALL_ORDER = ["rig", "model", "texture", "overlays", "cubes", "blocks", "anim", "sheets", "sprites", "sounds"]
adds them (ALL_ORDER is optional and replaces the default order).

Several mobs (pipeline.json "mobs"): every command runs once per mob, each in its own process (PIPELINE_MOB); select
with --mob NAME[,NAME] (default: all). plan and release run once.
"""
from __future__ import annotations

import argparse
import importlib
import os
import subprocess
import sys
import time

COMMANDS = {
    "check": "lib.check",
    "rig": "lib.rigtools",
    "model": "lib.modeltools",
    "texture": "lib.painter",
    "anim": "lib.animtools",
    "sheets": "lib.sheets",
    "sprites": "lib.pixel",
    "sounds": "lib.soundtools",
    "world": "lib.worldgen",
    "springs": "lib.springtune",
    "release": "lib.release",
    "plan": "lib.plantools",
    "cubes": "lib.texelcubes",
    "audio": "lib.audiotools",
}
ALL_ORDER = ["rig", "model", "texture", "cubes", "anim", "sheets", "sprites", "sounds"]
PROJECT_WIDE = {"plan", "release"}


def _split_mobs(argv: list[str]) -> tuple[list[str], list[str] | None]:
    out, selected, i = [], None, 0
    while i < len(argv):
        if argv[i] == "--mob" and i + 1 < len(argv):
            value, i = argv[i + 1], i + 2
        elif argv[i].startswith("--mob="):
            value, i = argv[i].split("=", 1)[1], i + 1
        else:
            out.append(argv[i])
            i += 1
            continue
        selected = (selected or []) + [name for name in value.split(",") if name]
    return out, selected


def _each_mob(argv: list[str], selected: list[str] | None) -> int:
    """Run the command once per selected mob, each in a fresh process: generators keep module state per mob."""
    from . import paths
    command = next((a for a in argv if not a.startswith("-")), "")
    names = paths.MOBS if not selected or selected == ["all"] else selected
    unknown = [name for name in names if name not in paths.MOBS]
    if unknown:
        raise SystemExit(f"--mob names unknown mobs: {', '.join(unknown)} (pipeline.json mobs: {', '.join(paths.MOBS)})")
    if command in PROJECT_WIDE:
        names = [paths.PRIMARY]
    for name in names:
        print(f"[mob {name}]", flush=True)
        rc = subprocess.run([sys.executable, "-I", str(paths.PIPE / "build_assets.py"), *argv],
                            env=dict(os.environ, PIPELINE_MOB=name)).returncode
        if rc:
            return rc
    return 0


def _project_commands():
    try:
        extra = importlib.import_module("mob.commands")
    except ModuleNotFoundError as error:
        if error.name != "mob.commands":
            raise
        return dict(COMMANDS), list(ALL_ORDER)
    commands = dict(COMMANDS) | dict(getattr(extra, "COMMANDS", {}))
    order = list(getattr(extra, "ALL_ORDER", ALL_ORDER))
    unknown = [name for name in order if name not in commands]
    if unknown:
        raise SystemExit(f"mob/commands.py ALL_ORDER names unknown commands: {', '.join(unknown)}")
    return commands, order


def main(argv: list[str]) -> int:
    from . import paths
    argv, selected = _split_mobs(argv)
    if len(paths.MOBS) > 1 and not os.environ.get("PIPELINE_MOB"):
        return _each_mob(argv, selected)
    if selected and selected not in (["all"], [paths.MOB]):
        raise SystemExit(f"--mob {','.join(selected)}: this pipeline builds {paths.MOB} (add mobs with `pipeline PROJECT --mob NAME --add`)")
    commands, all_order = _project_commands()
    ap = argparse.ArgumentParser(prog="build_assets.py")
    ap.add_argument("command", choices=[*commands, "all"])
    ap.add_argument("--validate", action="store_true", help="run the generator's validators and fail on findings")
    ap.add_argument("rest", nargs="*", help="command-specific arguments")
    args = ap.parse_args(argv)
    targets = all_order if args.command == "all" else [args.command]
    for name in targets:
        mod = importlib.import_module(commands[name])
        t0 = time.perf_counter()
        rc = mod.run(args)
        if rc == 0 and args.validate and hasattr(mod, "validate"):
            rc = mod.validate(args)
        print(f"[{name}] exit={rc} in {time.perf_counter() - t0:.1f}s", flush=True)
        if rc:
            return rc
    return 0
