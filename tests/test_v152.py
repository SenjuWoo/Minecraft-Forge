"""1.5.2: lessons of the next mob builds and the pack audit - several mobs in one pipeline, frame-rate independent
springs, the IK blend representative, finer voxel offsets for small parts, a shared sound bank, a devshots world that
keeps hostile actors, deploy that checks dependencies, refuses a running game and keeps a ledger, and an inventory
that knows FML libraries and dependency gaps."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap
import unittest
from unittest import mock
import zipfile

from mcforge import inventory, launchers, pipeline
from mcforge.scaffold import init_project
from tests.test_v100 import ROOT, Temp
from tests.test_v140 import HAVE_NUMPY


def jar(path: Path, entries: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        for name, text in entries.items():
            archive.writestr(name, text)
    return path


def neo_jar(path: Path, mod_id: str, version: str, needs: dict | None = None) -> Path:
    deps = "".join(f'[[dependencies.{mod_id}]]\nmodId="{dep}"\ntype="required"\nversionRange="{spec}"\nside="BOTH"\n'
                   for dep, spec in (needs or {}).items())
    toml = f'modLoader="javafml"\nloaderVersion="[4,)"\nlicense="MIT"\n[[mods]]\nmodId="{mod_id}"\nversion="{version}"\n' + deps
    return jar(path, {"META-INF/neoforge.mods.toml": toml})


class Templates(unittest.TestCase):
    def test_springs_average_force_over_short_frames(self):
        text = (ROOT / "templates/kit/common/SpringBones.java").read_text(encoding="utf-8")
        for needle in ("final Vector3f pending = new Vector3f();", "s.pending.fma((float) dt, s.force);",
                       "if (steps == 0) {", "s.filtered.lerp(mean, blend);"):
            self.assertIn(needle, text)
        self.assertNotIn("s.filtered.lerp(s.force, blend);", text)

    def test_devshots_world_keeps_hostile_actors(self):
        engine = (ROOT / "templates/devshots/DevShots.java").read_text(encoding="utf-8")
        scenes = (ROOT / "templates/devshots/DevScenes.java").read_text(encoding="utf-8")
        self.assertIn("Difficulty.NORMAL", engine)
        self.assertNotIn("Difficulty.PEACEFUL", engine)
        self.assertIn('.cmd("difficulty normal")', scenes)
        self.assertIn('.cmd("kill @e[type=!minecraft:player]")', scenes)
        self.assertLess(scenes.index("kill @e[type=!minecraft:player]"), scenes.index('"summon " + DevShots.SUBJECT'))


class Inventory(Temp):
    def test_multi_loader_library_with_fabric_metadata_is_not_foreign(self):
        lib = jar(self.root / "eqlib.jar", {"fabric.mod.json": json.dumps({"schemaVersion": 1, "id": "eqlib", "version": "1.0.3"}),
                                            "META-INF/services/net.neoforged.neoforgespi.locating.IDependencyLocator": "x.Y\n",
                                            "META-INF/MANIFEST.MF": "Manifest-Version: 1.0\nFMLModType: LIBRARY\n\n"})
        result = inventory.inspect_jar(lib)
        self.assertFalse(result["foreign_fabric_only"])
        self.assertEqual(result["fml"]["mod_type"], "LIBRARY")
        plain = jar(self.root / "fabric.jar", {"fabric.mod.json": json.dumps({"schemaVersion": 1, "id": "f", "version": "1"})})
        self.assertTrue(inventory.inspect_jar(plain)["foreign_fabric_only"])

    def test_dependency_problems_and_deployed_ledger(self):
        game = self.root / "inst"
        (game / "instance.json").parent.mkdir(parents=True)
        (game / "instance.json").write_text(json.dumps({"launcher": {"name": "I", "version": "1.21.1",
                                                                     "loaderVersion": {"type": "NeoForge", "version": "21.1.265"}}}))
        neo_jar(game / "mods/a.jar", "alpha", "1.0.0", {"geckolib": "[4.9.3,)", "ghost": "[1,)", "neoforge": "[21,)"})
        neo_jar(game / "mods/b.jar", "beta", "1.0.0", {"alpha": "[2.0,)"})
        neo_jar(game / "mods/geckolib.jar", "geckolib", "4.9.4")
        (game / "mcforge-deployed.json").write_text(json.dumps({"gone": {"file": "gone-1.0.0.jar", "sha256": "0"},
                                                                "alpha": {"file": "a.jar", "sha256": "0"}}))
        result = inventory.inventory(game)
        rows = {(p["jar"], p["needs"]): p["status"] for p in result["dependency_problems"]}
        self.assertEqual(rows, {("a.jar", "ghost"): "missing", ("b.jar", "alpha"): "outside_range"})
        self.assertEqual([row["mod_id"] for row in result["deployed_missing"]], ["gone"])

    def test_version_ranges(self):
        check = launchers.version_in_range
        self.assertTrue(check("4.9.4", "[4.9.3,)"))
        self.assertFalse(check("4.9.2", "[4.9.3,)"))
        self.assertFalse(check("2.0", "[1.0,2.0)"))
        self.assertTrue(check("2.0", "[1.0,2.0]"))
        self.assertTrue(check("4.9.3", "4.9"))
        self.assertIsNone(check("${file.jarVersion}", "[1,)"))
        self.assertTrue(check("anything", "*"))


class Deploy(Temp):
    def setUp(self):
        super().setUp()
        self.mod = self.root / "mod"
        self.mod.mkdir()
        (self.mod / "mcforge-project.json").write_text(json.dumps({"mod_id": "probe", "loader": "neoforge", "minecraft": "1.21.1"}))
        neo_jar(self.mod / "build/libs/probe-1.0.0.jar", "probe", "1.0.0", {"geckolib": "[4.9.3,)"})
        self.inst = self.root / "inst"
        self.inst.mkdir()
        (self.inst / "instance.json").write_text(json.dumps({"launcher": {"name": "I", "version": "1.21.1",
                                                                          "loaderVersion": {"type": "NeoForge", "version": "21.1.265"}}}))
        (self.inst / "mods").mkdir()

    def test_missing_dependency_is_a_mismatch(self):
        with mock.patch.object(launchers, "running_games", return_value=[]):
            with self.assertRaisesRegex(ValueError, "required dependency geckolib"):
                launchers.deploy(self.mod, self.inst, unverified=True)
            plan = launchers.deploy(self.mod, self.inst, unverified=True, allow_mismatch=True)
        self.assertEqual(plan["dependencies"][0]["status"], "missing")

    def test_running_game_blocks_apply_and_apply_writes_the_ledger(self):
        neo_jar(self.inst / "mods/geckolib.jar", "geckolib", "4.9.4")
        with mock.patch.object(launchers, "running_games", return_value=[4242]):
            plan = launchers.deploy(self.mod, self.inst, unverified=True)
            self.assertEqual(plan["game_running"], [4242])
            self.assertEqual(plan["dependencies"][0]["status"], "ok")
            with self.assertRaisesRegex(ValueError, "PID 4242"):
                launchers.deploy(self.mod, self.inst, unverified=True, apply=True)
        self.assertFalse((self.inst / "mods/probe-1.0.0.jar").exists())
        with mock.patch.object(launchers, "running_games", return_value=[]):
            done = launchers.deploy(self.mod, self.inst, unverified=True, apply=True)
        self.assertTrue(done["applied"])
        ledger = json.loads((self.inst / "mcforge-deployed.json").read_text(encoding="utf-8"))
        self.assertEqual(ledger["probe"]["file"], "probe-1.0.0.jar")
        self.assertEqual(ledger["probe"]["sha256"], done["sha256"])
        self.assertEqual(inventory.inventory(self.inst)["deployed_missing"], [])
        (self.inst / "mods/probe-1.0.0.jar").unlink()
        self.assertEqual([r["mod_id"] for r in inventory.inventory(self.inst)["deployed_missing"]], ["probe"])

    def test_running_games_reads_the_process_list(self):
        self.assertIsInstance(launchers.running_games(self.inst), (list, type(None)))
        self.assertEqual(launchers.running_games(self.inst) or [], [])


@unittest.skipUnless(HAVE_NUMPY, "numpy and Pillow are needed to run the scaffolded pipeline")
class SeveralMobs(Temp):
    def setUp(self):
        super().setUp()
        (self.root / "mod").mkdir()
        self.project = self.root / "mod" / "source"
        init_project(self.project, "probe", "dev.example.probe", "Probe Mod", target_id="neoforge-1.21.1")
        self.pipe = Path(pipeline.add_pipeline(self.project, "cave_stalker")["pipeline"])
        self.env = dict(os.environ, PIPELINE_NO_VENV="1", PYTHONPATH=str(ROOT),
                        MCFORGE_COMMAND=json.dumps([sys.executable, "-m", "mcforge"]))

    def build(self, *args, ok=True):
        done = subprocess.run([sys.executable, str(self.pipe / "build_assets.py"), *args], capture_output=True, text=True,
                              env=self.env, timeout=900)
        if ok:
            self.assertEqual(done.returncode, 0, done.stdout[-3000:] + done.stderr[-3000:])
        return done

    def test_add_second_mob_shares_lib_and_keeps_outputs_apart(self):
        with self.assertRaisesRegex(ValueError, "pass --add"):
            pipeline.add_pipeline(self.project, "mire_hound")
        added = pipeline.add_pipeline(self.project, "mire_hound", add=True)
        self.assertIn("mobs/mire_hound/rig.py", added["created"])
        config = json.loads((self.pipe / "pipeline.json").read_text(encoding="utf-8"))
        self.assertEqual(config["mobs"], ["cave_stalker", "mire_hound"])
        self.assertEqual(config["mob"], "cave_stalker")
        with self.assertRaisesRegex(ValueError, "already a mob"):
            pipeline.add_pipeline(self.project, "mire_hound", add=True)
        # the second mob's own palette replaces the shared one; its rig imports lib.animtools at import time (the
        # import cycle a golem family hit)
        shared = json.loads((self.pipe / "palette.json").read_text(encoding="utf-8"))
        (self.pipe / "mobs/mire_hound/palette.json").write_text(json.dumps(shared), encoding="utf-8")
        rig = self.pipe / "mobs/mire_hound/rig.py"
        rig.write_text("from lib import animtools as _A  # noqa: F401\n" + rig.read_text(encoding="utf-8"), encoding="utf-8")
        out = self.build("rig").stdout
        self.assertIn("[mob cave_stalker]", out)
        self.assertIn("[mob mire_hound]", out)
        gen = self.project / "src/main/java/dev/example/probe/gen"
        self.assertTrue((gen / "CaveStalkerRig.java").is_file())
        self.assertTrue((gen / "MireHoundRig.java").is_file())
        self.assertTrue((self.pipe / "build/rig_manifest.json").is_file())
        self.assertTrue((self.pipe / "build/mire_hound/rig_manifest.json").is_file())
        probe = textwrap.dedent("""
            import sys
            sys.path.insert(0, %r)
            from lib import paths, palette, rigtools
            print(paths.MOB, paths.MOB_DIR.name, paths.BUILD.name, paths.MEDIA.name, palette.PALETTE_JSON.parent.name, rigtools.GAINS.parent.name)
        """ % str(self.pipe))
        script = self.root / "probe.py"
        script.write_text(probe, encoding="utf-8")
        done = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, timeout=120,
                              env=dict(self.env, PIPELINE_MOB="mire_hound"), cwd=self.pipe)
        self.assertEqual(done.stdout.split(), ["mire_hound", "mire_hound", "mire_hound", "mire_hound", "mire_hound", "mire_hound"], done.stderr)
        only = self.build("check", "--mob", "mire_hound").stdout
        self.assertNotIn("[mob cave_stalker]", only)
        self.assertIn("mob mire_hound", only)
        bad = self.build("check", "--mob", "nobody", ok=False)
        self.assertNotEqual(bad.returncode, 0)
        self.assertIn("unknown mobs: nobody", bad.stderr + bad.stdout)

    def test_ik_blend_representative_voxel_offsets_and_shared_sound_bank(self):
        script = self.root / "snippet.py"
        script.write_text("import sys\nsys.path.insert(0, %r)\n" % str(self.pipe) + textwrap.dedent("""
            from lib import animtools as A, voxel as V, paths
            assert A.nearest_euler((179.9, 48.0, -178.9)) == (-0.1 + 0.0, 132.0, 1.1 + 0.0) or \\
                max(abs(a - b) for a, b in zip(A.nearest_euler((179.9, 48.0, -178.9)), (-0.1, 132.0, 1.1))) < 1e-9
            assert A.unwrap_euler([(10, 0, 0), (370, 0, 0)]) == [(10, 0, 0), (10, 0, 0)]
            import numpy as np
            class Ball:
                bounds = ((-0.3, -0.3, -0.3), (0.3, 0.3, 0.3))
                def __call__(self, x, y, z):
                    return np.sqrt(x * x + y * y + z * z) - 0.3
            placer = V.Placer()
            V.voxel_blob(placer, "a", Ball(), 0.1, "b", 10)
            _, clashes, off = V.voxel_blob(placer, "b", Ball(), 0.1, "b", 10)
            assert clashes == 0 and 0 < off < 0.1, (clashes, off)
            folder = paths.SOUNDS / "other_mob"
            folder.mkdir(parents=True, exist_ok=True)
            print("ok")
        """), encoding="utf-8")
        done = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, env=self.env, timeout=300, cwd=self.pipe)
        self.assertEqual(done.returncode, 0, done.stdout[-3000:] + done.stderr[-3000:])
        # shared bank: an event of this mob plays another mob's files
        sounds = self.project / "src/main/resources/assets/probe/sounds"
        for name in ("step_1", "step_2"):
            (sounds / "other_mob" / f"{name}.ogg").write_bytes(b"OggS")
        (self.pipe / "mob/sounds.py").write_text(
            'PLANNED = {}\nEVENTS = {"step": ("Steps", "other_mob/step_*", {"pitch": 1.15})}\n', encoding="utf-8")
        self.build("sounds")
        table = json.loads((self.project / "src/main/resources/assets/probe/sounds.json").read_text(encoding="utf-8"))
        names = [entry["name"] for entry in table["cave_stalker.step"]["sounds"]]
        self.assertEqual(names, ["probe:other_mob/step_1", "probe:other_mob/step_2"])


if __name__ == "__main__":
    unittest.main()
