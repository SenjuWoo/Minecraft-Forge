"""End-to-end check of one bundled target, as CI runs it.

Scaffolds the target (without the template's example content, so the
stripped main class is compiled too), adds every content kind, makes server-load evidence
available the way that target needs, runs `verify` and asserts the receipt:
compile, package and server load passed, client/gameplay honestly not run, the
generated classes are in the JAR and test code is not. On neoforge-1.21.1 it also
builds a GeckoLib mob the 1.4 way (library by version, asset pipeline, mob kit), so
the kit classes compile and load on a clean machine.

    python scripts/ci_target.py TARGET_ID [WORK_DIR]
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
CONTENT = [["block", "ruby_block"], ["item", "ruby"], ["food", "honey_bun"], ["sword", "bone_sword"], ["toolset", "ruby"],
           ["armor", "ruby"], ["furniture", "oak_chair"], ["furniture", "brass_lamp", "--shape", "lamp"],
           ["mob", "cave_boar"], ["mob", "bone_golem", "--shape", "biped", "--hostile"], ["mob", "moss_blob", "--shape", "blob"]]


def run(*arguments: str) -> dict | None:
    completed = subprocess.run([sys.executable, "-m", "mcforge", *arguments], cwd=ROOT, capture_output=True, text=True)
    sys.stderr.write(completed.stderr[-4000:])
    if completed.returncode:
        raise SystemExit(f"mcforge {' '.join(arguments)} exited {completed.returncode}")
    return json.loads(completed.stdout) if completed.stdout.strip().startswith("{") else None


def main() -> int:
    target = sys.argv[1]
    work = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "local" / "ci-targets"
    work.mkdir(parents=True, exist_ok=True)
    mod_id = "ci" + target.replace("-", "").replace(".", "")
    project = work / target
    if project.exists():
        raise SystemExit(f"{project} exists; pick an empty work directory")
    run("init", str(project), "--target", target, "--mod-id", mod_id, "--package", f"dev.mcforge.{mod_id}", "--name", f"CI {target}",
        "--no-examples")
    kit = None
    for spec in CONTENT:
        result = run("add", str(project), *spec)
        kit = result["java"]["status"]
    lock = json.loads((project / "mcforge-project.json").read_text(encoding="utf-8"))
    verify = ["verify", str(project)]
    if target == "neoforge-1.21.1":
        run("tests", str(project))
        # A GeckoLib mob: the library by version number (resolved to the NeoForge file's id), the generated assets
        # and constants of the pipeline example, and the kit classes that read them.
        resolved = run("libs", "--add", "geckolib", "--project", str(project), "--version", "4.9.3")
        assert resolved["loader"] == "neoforge" and resolved["version"] == "4.9.3", resolved
        pipe = run("pipeline", str(project), "--mob", "ci_sentinel", "--dir", str((work / f"{target}-pipeline").resolve()))
        run("kit", str(project), "geomob", "--mob", "ci_sentinel")
        built = subprocess.run([sys.executable, str(Path(pipe["pipeline"]) / "build_assets.py"), "all", "--validate"], cwd=ROOT,
                               env=dict(os.environ, PIPELINE_NO_VENV="1", PYTHONPATH=str(ROOT),
                                        MCFORGE_COMMAND=json.dumps([sys.executable, "-m", "mcforge"])))
        if built.returncode:
            raise SystemExit(f"the scaffolded asset pipeline exited {built.returncode}")
        # The screenshot driver must compile in the test source set and stay inert on the game-test server.
        run("devshots", str(project), "--subject", f"{mod_id}:ci_sentinel")
    elif lock["family"] != "fabric-loom":
        verify.append("--load")
    run(*verify)
    receipt = json.loads((project / "build/mcforge/verification.json").read_text(encoding="utf-8"))
    tiers = receipt["tiers"]
    assert receipt["status"] == "passed", receipt.get("error")
    assert tiers["compile"] == tiers["package"] == tiers["server_load"] == "passed", tiers
    assert tiers["client_load"] == tiers["gameplay"] == "not_run", tiers
    with zipfile.ZipFile(receipt["artifact"]["path"]) as archive:
        names = set(archive.namelist())
    package = f"dev/mcforge/{mod_id}"
    if kit == "generated":
        for name in ("content/CaveBoarEntity.class", "content/RubyArmorContent.class", "content/OakChairBlock.class",
                     "content/client/CaveBoarEntityModel.class"):
            assert f"{package}/{name}" in names, f"{name} missing from the mod JAR"
    assert not any(name.startswith(f"{package}/testing/") for name in names), "test code leaked into the mod JAR"
    assert f"assets/{mod_id}/textures/entity/cave_boar.png" in names
    if target == "neoforge-1.21.1":
        for name in ("ci_sentinel/CiSentinelEntity.class", "ci_sentinel/client/CiSentinelModel.class", "kit/SpringBones.class",
                     "kit/SharedBoneLayer.class", "gen/CiSentinelRig.class", "gen/CiSentinelClips.class"):
            assert f"{package}/{name}" in names, f"{name} missing from the mod JAR"
        for name in ("geo/entity/ci_sentinel.geo.json", "animations/entity/ci_sentinel.animation.json", "textures/entity/ci_sentinel.png"):
            assert f"assets/{mod_id}/{name}" in names, f"{name} missing from the mod JAR"
        # The arena regression test: a horse at ArenaTests.STAND stays on the floor, alive and unhurt.
        assert any("largemobstandsunhurtonthearenafloor" in name.lower() for name in receipt["tests"]["names"]), receipt["tests"]
    run("verify", str(project), "--check")
    print(json.dumps({"target": target, "kit": kit, "tiers": tiers, "tests": receipt["tests"], "jar": receipt["artifact"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
