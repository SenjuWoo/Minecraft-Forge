"""Spring tuning from the client trace: one step of "measure, scale, rerun".

The SpringBones kit prints, once a second, `MCFORGE-TRACE spring id=<scene> name=<bone> peak=<p90> ...` where
peak is the spring's unclamped output as a fraction of its clamp during ordinary motion (hits and landings are
left out). Ordinary motion should peak at 65-85 %: lower looks stiff, higher rides the clamp.

`build_assets.py springs [scene] [log=FILE]` reads the last dev client log, takes each bone's last peak in
that scene (default: any) and writes spring_gains.json so the peak lands on 75 %. The springs are linear below
the clamp, so one step lands close: rerun `rig`, the client scene and this command until `--validate` passes.
Record peaks from scripted stations (a NoAI subject moved by the scene); AI wandering differs from run to run.
"""
from __future__ import annotations

import re
from pathlib import Path

from . import paths, rigtools

TARGET, LOW, HIGH = 0.75, 0.65, 0.85
LINE = re.compile(r"MCFORGE-TRACE spring (.*)")
KV = re.compile(r"(\w+)=(\S+)")


def options(args):
    """(scene or None, log path) from `springs [scene] [log=FILE]`."""
    scene, log = None, paths.PROJECT / "run-devshots/logs/latest.log"
    for token in getattr(args, "rest", []) or []:
        if token.startswith("log="):
            log = Path(token[4:])
        else:
            scene = token
    return scene, log


def peaks(args) -> dict:
    scene, log = options(args)
    if not log.is_file():
        raise SystemExit(f"no dev client log at {log}: run the client scene first (minecraft-forge verify PROJECT --client)")
    out = {}
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        m = LINE.search(line)
        if m:
            rec = dict(KV.findall(m.group(1)))
            if scene is None or rec.get("id") == scene:
                out[rec.get("name")] = float(rec.get("peak", "nan"))
    return out


def run(args) -> int:
    measured = peaks(args)
    if not measured:
        print("springs: no spring trace in the log (start the client with -Dmcforge.trace=true; the devShots run sets it)")
        return 1
    current = {s["bone"]: s["gain"] for s in rigtools.manifest()["springs"]}
    tuned = dict(rigtools.gains())
    for bone, peak in sorted(measured.items()):
        if bone not in current:
            continue
        gain = current[bone]
        if peak != peak or peak <= 1e-4:
            new = gain * 4.0            # never excited: push hard, the next run measures it
        elif LOW + 0.03 <= peak <= HIGH - 0.03:
            new = gain                  # inside the band with a margin for run-to-run frame timing
        else:
            new = gain * TARGET / peak
        new = max(0.05, min(400.0, new))
        tuned[bone] = round(new, 4)
        print(f"  {bone:24s} peak {peak:6.3f}  gain {gain:8.4f} -> {new:8.4f}{'' if new == gain else '  (retuned)'}")
    paths.write_json(rigtools.GAINS, tuned)
    print(f"springs: wrote {rigtools.GAINS.name}; rerun `build_assets.py rig`, rebuild and trace again")
    return 0


def validate(args) -> int:
    measured = peaks(args)
    wanted = {s["bone"] for s in rigtools.manifest()["springs"]}
    errs = [f"{bone}: no trace" for bone in sorted(wanted - set(measured))]
    errs += [f"{bone}: peak {peak:.3f} outside {LOW}-{HIGH}" for bone, peak in sorted(measured.items())
             if bone in wanted and not (LOW <= peak <= HIGH)]
    for e in errs:
        print("SPRING ERROR:", e)
    print(f"springs validate: {len(errs)} error(s)")
    return 1 if errs else 0
