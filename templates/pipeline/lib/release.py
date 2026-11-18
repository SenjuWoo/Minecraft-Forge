"""Release staging: copy the verified JAR to ../mod/<file> and write ../mod/MANIFEST.json with its SHA-256, the
target, the evidence tiers and the tested / untested lists. The JAR comes from the latest toolkit verification
receipt, so only a build that passed `minecraft-forge verify` is ever staged. Nothing here publishes anything.

    build_assets.py release

The tested / untested lists are read from ../docs/VALIDATION.md: bullets under a heading that starts with
"Verified" and under one that starts with "Not verified". Say there what nobody has checked (audio by ear,
the pack runtime, shaders): an honest untested list is part of the release.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path

from . import paths

MOD = paths.ROOT / "mod"


def run(args=None) -> int:
    receipt_path = paths.PROJECT / "build/mcforge/verification.json"
    if not receipt_path.is_file():
        print("release: no verification receipt; run minecraft-forge verify PROJECT first")
        return 1
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt.get("status") != "passed":
        print("release: the latest verification did not pass")
        return 1
    jar = Path(receipt["artifact"]["path"])
    if not jar.is_file():
        print(f"release: {jar.name} is gone; verify again")
        return 1
    sha = hashlib.sha256(jar.read_bytes()).hexdigest()
    if receipt["artifact"].get("sha256") != sha:
        print("release: the built JAR differs from the verified one; run minecraft-forge verify again")
        return 1
    MOD.mkdir(exist_ok=True)
    for old in MOD.glob(f"{paths.MOD}-*.jar"):
        old.unlink()
    out = MOD / jar.name
    shutil.copyfile(jar, out)
    tested, untested = [], []
    validation = paths.ROOT / "docs" / "VALIDATION.md"
    if validation.exists():
        section = None
        for line in validation.read_text(encoding="utf-8").splitlines():
            if line.startswith("#"):
                section = line.lstrip("# ").strip().lower()
            elif line.startswith("- ") and section:
                (tested if section.startswith("verified") else untested if section.startswith("not verified") else []).append(line[2:].strip())
    props = (paths.PROJECT / "gradle.properties").read_text(encoding="utf-8")
    version = re.search(r"^mod_version\s*=\s*(.+)$", props, re.M)
    lock = json.loads((paths.PROJECT / "mcforge-project.json").read_text(encoding="utf-8"))
    manifest = {"mod_id": paths.MOD, "version": version.group(1).strip() if version else None, "file": out.name, "sha256": sha,
                "size": out.stat().st_size, "minecraft": lock.get("minecraft"), "loader": lock.get("loader", "neoforge"),
                "loader_version": lock.get("loader_version") or lock.get("neo_version"), "verified_run": receipt.get("run_id"),
                "tiers": receipt.get("tiers"), "tests": receipt.get("tests"), "tested": tested, "untested": untested}
    paths.write_text(MOD / "MANIFEST.json", json.dumps(manifest, indent=2) + "\n")
    print(f"release: mod/{out.name} sha256 {sha[:16]}... ({len(tested)} tested, {len(untested)} untested)")
    return 0
