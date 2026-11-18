"""Subcommand dispatch. Each generator module exposes run(args) -> int and, optionally, validate(args) -> int.

Add a command by adding a module and a line here. `all` runs ALL_ORDER; a command's validator runs right after it
when --validate is given, so `all --validate` is the full offline gate.
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
}
ALL_ORDER = ["rig", "model", "texture", "anim", "sheets", "sprites", "sounds"]


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="build_assets.py")
    ap.add_argument("command", choices=[*COMMANDS, "all"])
    ap.add_argument("--validate", action="store_true", help="run the generator's validators and fail on findings")
    ap.add_argument("rest", nargs="*", help="command-specific arguments")
    args = ap.parse_args(argv)
    targets = ALL_ORDER if args.command == "all" else [args.command]
    for name in targets:
        mod = importlib.import_module(COMMANDS[name])
        t0 = time.perf_counter()
        rc = mod.run(args)
        if rc == 0 and args.validate and hasattr(mod, "validate"):
            rc = mod.validate(args)
        print(f"[{name}] exit={rc} in {time.perf_counter() - t0:.1f}s", flush=True)
        if rc:
            return rc
    return 0
