"""Subcommand dispatch. Each generator module exposes run(args) -> int and, optionally, validate(args) -> int.

`all` runs ALL_ORDER; a command's validator runs right after it when --validate is given, so `all --validate` is
the full offline gate.

Project commands live in mob/, never in lib/ (`pipeline --force` refreshes lib/): an optional mob/commands.py with
    COMMANDS = {"blocks": "mob.shroomblock", "overlays": "mob.overlays"}   # name -> module with run(args)
    ALL_ORDER = ["rig", "model", "texture", "overlays", "cubes", "blocks", "anim", "sheets", "sprites", "sounds"]
adds them (ALL_ORDER is optional and replaces the default order).
"""
from __future__ import annotations

import argparse
import importlib
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
