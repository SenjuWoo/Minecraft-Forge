"""PLAN.md helpers for a task-table plan (| ID | Task | Status | Depends on | Verify | Evidence |).

    build_assets.py plan status T05 complete "cmd:... @ <sha> exit=0"     update one row
    build_assets.py plan reprove                                          rerun every complete task's Verify at HEAD
    build_assets.py plan reprove check                                    no reruns: is every evidence cell current?

reprove reruns each distinct `cmd:` Verify of the complete tasks once, in plan order, from the project root and
rewrites the Evidence cell as `cmd:<command> @ <HEAD sha> exit=<n>`; a `file:<path>` Verify passes when the file
exists and is not empty. Use it before a release: evidence recorded many commits ago proves little about the
commit that ships. Keep PLAN.md and STATE.md out of the commits whose hashes they record (untracked ledgers), or
recording evidence stales it.
"""
from __future__ import annotations

import re
import subprocess

from . import paths

PLAN = paths.ROOT / "PLAN.md"
ROW = re.compile(r"\| *(T\d+[a-z]?) *\|")


def _rows():
    lines = PLAN.read_text(encoding="utf-8").splitlines()
    out = []
    for i, line in enumerate(lines):
        m = ROW.match(line)
        cells = [c.strip() for c in line.strip().strip("|").split(" | ")]
        if m and len(cells) >= 6:
            out.append({"i": i, "id": m.group(1), "cells": cells})
    return lines, out


def _write(lines, row):
    lines[row["i"]] = "| " + " | ".join(row["cells"]) + " |"


def _head() -> str:
    r = subprocess.run(["git", "-C", str(paths.ROOT), "rev-parse", "--short", "HEAD"], capture_output=True, text=True)
    return r.stdout.strip() or "nogit"


def status(task, state, evidence) -> int:
    lines, rows = _rows()
    for row in rows:
        if row["id"] == task:
            row["cells"][2] = state
            if evidence:
                row["cells"][-1] = evidence
            _write(lines, row)
            PLAN.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
            print(f"plan: {task} -> {state}")
            return 0
    print(f"plan: {task} not found")
    return 1


def reprove(check: bool) -> int:
    lines, rows = _rows()
    sha = _head()
    done: dict[str, int] = {}
    bad = 0
    for row in rows:
        if row["cells"][2] != "complete":
            continue
        verify = row["cells"][4]
        if check:
            ok = f"@ {sha}" in row["cells"][-1] and row["cells"][-1].rstrip().endswith("exit=0")
            if not ok:
                bad += 1
                print(f"  STALE {row['id']}: {row['cells'][-1][:90]}")
            continue
        if verify.startswith("cmd:"):
            command = verify[4:].strip()
            if command not in done:
                print(f"[{row['id']}] {command}", flush=True)
                done[command] = subprocess.run(command, shell=True, cwd=paths.ROOT).returncode
            code = done[command]
            row["cells"][-1] = f"cmd:{command} @ {sha} exit={code}"
        elif verify.startswith("file:"):
            target = paths.ROOT / verify[5:].strip()
            code = 0 if target.is_file() and target.stat().st_size > 0 else 1
            row["cells"][-1] = f"file:{verify[5:].strip()} @ {sha} exit={code}"
        else:
            continue
        if code:
            bad += 1
            row["cells"][2] = "blocked"
        _write(lines, row)
    if not check:
        PLAN.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"plan reprove{' check' if check else ''}: {bad} problem(s) at {sha}")
    return 1 if bad else 0


def run(args) -> int:
    rest = list(getattr(args, "rest", []) or [])
    if not PLAN.is_file():
        print(f"plan: {PLAN} does not exist")
        return 1
    if rest[:1] == ["status"] and len(rest) >= 3:
        return status(rest[1], rest[2], rest[3] if len(rest) > 3 else "")
    if rest[:1] == ["reprove"]:
        return reprove("check" in rest[1:])
    print(__doc__)
    return 2
