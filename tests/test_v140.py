"""1.4.0: voxel fixes and shapes, library version ids, scripted devshots, devlog gate, Java kits, the asset pipeline
scaffold, local guides and the corrected top/bottom face UV direction."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from mcforge import __main__ as cli
from mcforge import devlog, devshots, kit, libs, modelcheck, pipeline, plan, preview, product, verification, voxel
from mcforge.scaffold import init_project
from tests.test_v100 import ROOT, Temp

HAVE_NUMPY = importlib.util.find_spec("numpy") is not None and importlib.util.find_spec("PIL") is not None


class FieldReports(Temp):
    def test_voxel_output_passes_model_check_at_its_default_tolerance(self):
        # The second blob's grid puts its front and back faces 0.006 px from the first blob's: inside model-check's
        # 0.01 px tolerance, outside the old 0.005 px placement window (which produced two z-fighting pairs here).
        spec = {"name": "pair", "cell": 1.0, "bones": [{"name": "root", "pivot": [0, 0, 0]}], "blobs": [
            {"name": "a", "bone": "root", "shape": {"box": {"min": [0, 0, 0], "max": [4, 4, 4]}}},
            {"name": "b", "bone": "root", "shape": {"box": {"min": [1.5, 0.5, 0.006], "max": [3.5, 2.5, 4.006]}}}]}

        def findings():
            path = self.root / "pair.geo.json"
            path.write_text(json.dumps(voxel.build_voxel_model(spec)["geo"]), encoding="utf-8")
            return modelcheck.check_model(path)["z_fighting"]
        self.assertEqual(findings(), [])
        self.assertGreater(voxel.PLANE_WINDOW, 0.01)
        with patch.object(voxel, "PLANE_WINDOW", 0.005):
            self.assertEqual(len(findings()), 2)

    def test_library_version_number_resolves_to_this_loaders_version_id(self):
        rows = [{"version_number": "4.9.3", "id": "NeoBuild1", "version_type": "release", "dependencies": [],
                 "files": [{"primary": True, "filename": "geckolib-neoforge-1.21.1-4.9.3.jar", "url": "https://example.invalid/n", "hashes": {}}]}]
        with patch("mcforge.libs._get", return_value=rows) as get:
            result = libs.resolve("geckolib", "neoforge", "1.21.1", "4.9.3")
        self.assertEqual(result["maven"], "maven.modrinth:geckolib:NeoBuild1")
        self.assertIn("neoforge", get.call_args[0][0])   # the query is filtered to the project's loader
        with patch("mcforge.libs._get", return_value=rows):
            self.assertEqual(libs.resolve("geckolib", "neoforge", "1.21.1", "NeoBuild1")["version"], "4.9.3")

    def test_driver_handles_the_first_launch_screen(self):
        driver = (ROOT / devshots.TEMPLATE).read_text(encoding="utf-8")
        self.assertIn("AccessibilityOnboardingScreen", driver)
        self.assertIn("onboardAccessibility = false", driver)


class UvDirection(Temp):
    def test_top_and_bottom_faces_follow_the_geckolib_quad_builder(self):
        low, high = (0.0, 0.0, 0.0), (4.0, 2.0, 6.0)
        # up: u grows toward -X, v toward -Z; down: u toward -X, v toward +Z
        self.assertEqual(preview._face_fraction("up", (4.0, 2.0, 6.0), low, high), (0.0, 0.0))
        self.assertEqual(preview._face_fraction("up", (0.0, 2.0, 0.0), low, high), (1.0, 1.0))
        self.assertEqual(preview._face_fraction("down", (4.0, 0.0, 0.0), low, high), (0.0, 0.0))
        self.assertEqual(preview._face_fraction("down", (0.0, 0.0, 6.0), low, high), (1.0, 1.0))
        # side faces read left to right, top to bottom from outside
        self.assertEqual(preview._face_fraction("north", (4.0, 2.0, 0.0), low, high), (0.0, 0.0))
        self.assertEqual(preview._face_fraction("east", (4.0, 2.0, 6.0), low, high), (0.0, 0.0))

    @unittest.skipUnless(HAVE_NUMPY, "numpy and Pillow are needed for the pipeline templates")
    def test_pipeline_face_table_agrees_with_the_preview(self):
        sys.path.insert(0, str(ROOT / "templates/pipeline"))
        try:
            spec = importlib.util.spec_from_file_location("pipeline_voxel", ROOT / "templates/pipeline/lib/voxel.py")
            module = importlib.util.module_from_spec(spec)
            sys.modules["pipeline_voxel"] = module
            spec.loader.exec_module(module)
        finally:
            sys.path.pop(0)
        low, high = (0.0, 0.0, 0.0), (4.0, 2.0, 6.0)
        for face in module.FACES:
            for point, (s, t) in module.face_corners(low, high, face):
                u, v = preview._face_fraction(face, point, low, high)
                self.assertAlmostEqual(u, s, msg=face)
                self.assertAlmostEqual(v, t, msg=face)


class VoxelShapes(Temp):
    def base(self, shape, **blob):
        return {"name": "shape", "cell": 0.5, "bones": [{"name": "root", "pivot": [0, 0, 0]}],
                "blobs": [{"name": "part", "bone": "root", "shape": shape} | blob]}

    def test_intersect_halfspace_and_torus(self):
        ball = {"ellipsoid": {"center": [0, 4, 0], "radii": [4, 4, 4]}}
        whole = voxel.build_voxel_model(self.base(ball))["report"]
        half = voxel.build_voxel_model(self.base({"intersect": [ball, {"halfspace": {"point": [0, 4, 0], "normal": [0, 1, 0]}}]}))
        self.assertLess(half["report"]["bounds"][1][1], 4.3)             # everything above y = 4 is cut away
        self.assertLess(half["report"]["cubes"], whole["cubes"])
        ring = voxel.build_voxel_model(self.base({"torus": {"center": [0, 4, 0], "axis": "y", "major": 4, "minor": 1}}))
        low, high = ring["report"]["bounds"]
        self.assertAlmostEqual(high[0] - low[0], 10.0, delta=0.6)
        self.assertAlmostEqual(high[1] - low[1], 2.0, delta=0.6)
        f, _ = voxel.build_shape({"torus": {"center": [0, 0, 0], "axis": "y", "major": 4, "minor": 1}})
        self.assertGreater(f(0, 0, 0), 0)                                # the hole
        self.assertLess(f(4, 0, 0), 0)                                   # the tube

    def test_bad_new_shapes_fail_with_a_reason(self):
        with self.assertRaisesRegex(ValueError, "unbounded"):
            voxel.build_voxel_model(self.base({"halfspace": {"point": [0, 0, 0], "normal": [0, 1, 0]}}))
        with self.assertRaisesRegex(ValueError, "do not overlap"):
            voxel.build_shape({"intersect": [{"box": {"min": [0, 0, 0], "max": [1, 1, 1]}}, {"box": {"min": [5, 5, 5], "max": [6, 6, 6]}}]})
        with self.assertRaisesRegex(ValueError, "torus.axis"):
            voxel.build_shape({"torus": {"center": [0, 0, 0], "axis": "w", "major": 2, "minor": 1}})

    def test_per_blob_texel_density(self):
        box = {"box": {"min": [0, 0, 0], "max": [2, 2, 2]}}
        coarse = voxel.build_voxel_model(self.base(box) | {"cell": 2.0})
        fine = voxel.build_voxel_model(self.base(box, texels_per_pixel=8) | {"cell": 2.0})
        size = lambda built: built["geo"]["minecraft:geometry"][0]["bones"][0]["cubes"][0]["uv"]["north"]["uv_size"]
        self.assertEqual(size(coarse), [4, 4])
        self.assertEqual(size(fine), [16, 16])


class DevShotsV2(Temp):
    def project(self):
        path = self.root / "shots"
        init_project(path, "shots", "dev.example.shots", "Shots", with_tests=True, examples=False)
        return path

    def test_engine_is_replaceable_and_the_scene_script_is_kept(self):
        project = self.project()
        first = devshots.add_devshots(project)
        self.assertTrue(first["scenes_written"])
        scenes = Path(first["scenes"])
        self.assertIn("package dev.example.shots.testing;", scenes.read_text(encoding="utf-8"))
        scenes.write_text(scenes.read_text(encoding="utf-8") + "// my scene\n", encoding="utf-8")
        second = devshots.add_devshots(project, force=True)
        self.assertFalse(second["scenes_written"])
        self.assertIn("// my scene", scenes.read_text(encoding="utf-8"))
        build = (project / "build.gradle").read_text(encoding="utf-8")
        self.assertIn("'mcforge.trace', 'true'", build)
        engine = Path(first["driver"]).read_text(encoding="utf-8")
        for needle in ("DevScenes.build()", "scenes.txt", "MCFORGE-TRACE", "static void onServer", "Script burst("):
            self.assertIn(needle, engine)

    def test_scene_filter_file(self):
        project = self.project()
        self.assertEqual(devshots.set_scenes(project, "turntable, night"), "turntable,night")
        self.assertEqual((project / "run-devshots/scenes.txt").read_text(encoding="utf-8"), "turntable,night\n")
        self.assertEqual(devshots.set_scenes(project, None), "")
        self.assertEqual((project / "run-devshots/scenes.txt").read_text(encoding="utf-8"), "")
        with self.assertRaisesRegex(ValueError, "--scenes"):
            devshots.set_scenes(project, "Bad Scene!")
        code, _, error = self.invoke(["verify", str(project), "--scenes", "a"])
        self.assertEqual(code, 2)
        self.assertIn("--client", error)

    def test_world_setting_and_locate_support(self):
        project = self.project()
        self.assertEqual(devshots.set_world(project, None), "flat")
        self.assertEqual(devshots.set_world(project, "normal"), "normal")
        self.assertEqual((project / "run-devshots/world.txt").read_text(encoding="utf-8").strip(), "normal")
        with self.assertRaisesRegex(ValueError, "flat or normal"):
            devshots.set_world(project, "amplified")
        code, _, error = self.invoke(["verify", str(project), "--world", "normal"])
        self.assertEqual(code, 2)
        self.assertIn("--client", error)
        engine = (ROOT / devshots.TEMPLATE).read_text(encoding="utf-8")
        # structures are generated only in the normal world, and every search is bounded
        self.assertIn("new WorldOptions(SEED, NORMAL_WORLD, false)", engine)
        self.assertIn("findNearestMapStructure(level, HolderSet.direct(holder), BlockPos.ZERO,", engine)
        self.assertIn("MCFORGE-TRACE", engine)
        self.assertIn("NORMAL_WORLD", (ROOT / devshots.SCENES_TEMPLATE).read_text(encoding="utf-8"))

    def test_identical_consecutive_screenshots_are_reported(self):
        files = []
        for index, content in enumerate([b"a", b"b", b"b", b"b", b"c", b"c", b"d", b"d", b"d", b"d"]):
            path = self.root / f"devshots_{index}.png"
            path.write_bytes(content)
            files.append(path)
        self.assertEqual(verification.frozen_frames(files), ["devshots_3.png", "devshots_8.png"])
        self.assertEqual(verification.frozen_frames(files[:3]), [])


LOG = """[12:00:01] [Render thread/INFO] [dev.example.probe.testing.DevShots/]: MCFORGE-DEVSHOTS script steps=40
[12:00:02] [Render thread/INFO] [x/]: MCFORGE-TRACE spring id=physics name=tail_phys peak=0.400 max=0.9 clamp=1.000
[12:00:03] [Render thread/INFO] [x/]: MCFORGE-TRACE spring id=physics name=tail_phys peak=0.720 max=0.9 clamp=1.000
[12:00:03] [Render thread/INFO] [x/]: MCFORGE-TRACE spring id=physics name=ear_l_phys peak=0.930 max=1.2 clamp=1.000
[12:00:03] [Render thread/INFO] [x/]: MCFORGE-TRACE spring id=other name=ear_l_phys peak=0.100 max=1.2 clamp=1.000
[12:00:04] [Render thread/INFO] [x/]: MCFORGE-TRACE chain id=teleport_1 stretch=1.60
[12:00:04] [Render thread/INFO] [x/]: MCFORGE-TRACE chain id=walk stretch=1.04
[12:00:05] [Render thread/INFO] [x/]: MCFORGE-TRACE fps scene=one fps=120
[12:00:05] [Render thread/INFO] [x/]: MCFORGE-TRACE fps scene=eight fps=60
[12:00:05] [Render thread/INFO] [x/]: MCFORGE-TRACE hit target=5 hurt=1
[12:00:05] [Render thread/INFO] [x/]: MCFORGE-TRACE hit target=9 hurt=1
[12:00:06] [Render thread/WARN] [minecraft/SoundEngine]: Missing sound for event: minecraft:item.goat_horn.play
[12:00:09] [Render thread/INFO] [dev.example.probe.testing.DevShots/]: MCFORGE-DEVSHOTS done 12 subject=probe:thing scenes=all
"""
RULES = {"gates": {"final": [
    {"kind": "spring", "where": {"id": "physics"}, "group_by": "name", "pick": "last", "field": "peak", "min": 0.65, "max": 0.85},
    {"kind": "chain", "skip": {"id": "teleport*"}, "field": "stretch", "min": 0.9, "max": 1.15},
    {"kind": "fps", "compare": {"field": "fps", "a": {"scene": "eight"}, "b": {"scene": "one"}, "min_ratio": 0.6}, "severity": "warn"},
    {"kind": "hit", "distinct_min": {"target": 3}},
    {"kind": "level", "field": "err", "max": 5}], "quick": [{"kind": "chain", "field": "stretch", "max": 2.0, "count_min": 2}]}}


class DevLog(Temp):
    def setUp(self):
        super().setUp()
        self.project = self.make("neoforge-1.21.1")
        self.log = self.root / "latest.log"
        self.rules = self.root / "rules.json"
        self.rules.write_text(json.dumps(RULES), encoding="utf-8")

    def run_gate(self, text, gate=None, rules=True):
        self.log.write_text(text, encoding="utf-8")
        return devlog.check_devlog(self.project, self.log, self.rules if rules else None, gate)

    def test_clean_log_passes_without_rules_and_foreign_noise_is_ignored(self):
        result = self.run_gate(LOG, rules=False)
        self.assertEqual((result["status"], result["done"], result["problems"]), ("passed", 12, []))
        self.assertEqual(result["traces"]["spring"]["count"], 4)
        self.assertEqual(result["traces"]["spring"]["tail_phys.peak"], {"min": 0.4, "max": 0.72, "last": 0.72})

    def test_rules_report_each_failing_check_and_warnings_do_not_fail(self):
        result = self.run_gate(LOG)
        text = "\n".join(result["problems"])
        self.assertIn("spring: peak = 0.93 outside 0.65..0.85 (ear_l_phys)", text)      # tail_phys' last value 0.72 passes
        self.assertNotIn("tail_phys", text)
        self.assertNotIn("chain", text)                                                # the teleport frame is skipped
        self.assertIn("hit: target has 2 distinct value(s)", text)
        self.assertIn("level: 0 trace record(s), need at least 1", text)
        self.assertEqual(len(result["problems"]), 3)
        self.assertEqual(len(result["warnings"]), 1)                                   # fps 60/120 = 0.5 < 0.6, severity warn
        self.assertEqual(self.run_gate(LOG, gate="quick")["status"], "passed")
        with self.assertRaisesRegex(ValueError, "not in the rules"):
            self.run_gate(LOG, gate="missing")

    def test_built_in_checks(self):
        unfinished = self.run_gate(LOG.rsplit("\n", 2)[0] + "\n", rules=False)
        self.assertIn("did not finish", unfinished["problems"][0])
        bad = LOG + ("[12:00:10] [Render thread/WARN] [minecraft/SoundEngine]: Unable to play unknown soundEvent: probe:thing.roar\n"
                     "[12:00:11] [Render thread/WARN] [minecraft/ModelBakery]: Unable to load model: 'probe:item/thing_spawn_egg'\n"
                     "[12:00:12] [Render thread/ERROR] [minecraft/Minecraft]: Error executing task\n"
                     "java.lang.NullPointerException: boom\n\tat dev.example.probe.client.ThingModel.setCustomAnimations(ThingModel.java:40)\n"
                     "[12:00:13] [Render thread/ERROR] [minecraft/Other]: Exception in some other mod\n\tat com.other.Thing.run(Thing.java:1)\n")
        result = self.run_gate(bad, rules=False)
        self.assertEqual(len(result["unknown_sounds"]), 1)
        self.assertEqual(len(result["missing_assets"]), 1)
        self.assertEqual(len(result["errors"]), 1)                                     # only the one naming this mod's package
        self.assertEqual(result["status"], "failed")
        failed = self.run_gate(LOG.replace("MCFORGE-DEVSHOTS done 12", "MCFORGE-DEVSHOTS failed: step 3 threw x"), rules=False)
        self.assertIn("the driver failed: step 3 threw x", failed["problems"][0])

    def test_cli_exit_codes_and_default_log(self):
        logs = self.project / "run-devshots/logs"
        logs.mkdir(parents=True)
        (logs / "latest.log").write_text(LOG, encoding="utf-8")
        code, out, _ = self.invoke(["devlog", str(self.project)])
        self.assertEqual((code, json.loads(out)["status"]), (0, "passed"))
        code, out, _ = self.invoke(["devlog", str(self.project), "--rules", str(self.rules)])
        self.assertEqual(code, 1)
        (logs / "latest.log").unlink()
        code, _, error = self.invoke(["devlog", str(self.project)])
        self.assertEqual(code, 2)
        self.assertIn("No dev client log", error)


class Kits(Temp):
    def test_geomob_writes_a_self_contained_mob_and_keeps_generated_classes(self):
        project = self.make("neoforge-1.21.1")
        result = kit.add_kit(project, "geomob", "cave_stalker", hitbox=(0.9, 2.0))
        base = project / "src/main/java/dev/example/probe"
        for relative in ("kit/BoneMath.java", "kit/SpringBones.java", "kit/SharedBoneLayer.java", "kit/DevTrace.java",
                         "cave_stalker/CaveStalkerEntity.java", "cave_stalker/CaveStalkerContent.java",
                         "cave_stalker/client/CaveStalkerModel.java", "cave_stalker/client/CaveStalkerRenderer.java",
                         "cave_stalker/client/CaveStalkerClient.java", "gen/CaveStalkerRig.java", "gen/CaveStalkerClips.java"):
            text = (base / relative).read_text(encoding="utf-8")
            self.assertNotRegex(text, r"@[A-Z_]+@", relative)
            self.assertIn("package dev.example.probe", text)
        content = (base / "cave_stalker/CaveStalkerContent.java").read_text(encoding="utf-8")
        self.assertIn('.sized(0.9f, 2f).eyeHeight(1.70f)', content)
        self.assertIn('MOD_ID = "probe"', content)
        lang = json.loads((project / "src/main/resources/assets/probe/lang/en_us.json").read_text(encoding="utf-8"))
        self.assertEqual(lang["entity.probe.cave_stalker"], "Cave Stalker")
        toml = (project / "src/main/templates/META-INF/neoforge.mods.toml").read_text(encoding="utf-8")
        self.assertEqual(toml.count('modId="geckolib"'), 1)
        self.assertTrue(any("libs --add geckolib" in note for note in result["notes"]))
        # generated gen/ classes belong to the pipeline: a second run, even with --force, keeps them
        rig = base / "gen/CaveStalkerRig.java"
        rig.write_text(rig.read_text(encoding="utf-8") + "// generated by the pipeline\n", encoding="utf-8")
        again = kit.add_kit(project, "geomob", "cave_stalker", force=True)
        self.assertIn("// generated by the pipeline", rig.read_text(encoding="utf-8"))
        self.assertIn("src/main/java/dev/example/probe/gen/CaveStalkerRig.java", again["kept"])
        self.assertEqual((project / "src/main/templates/META-INF/neoforge.mods.toml").read_text(encoding="utf-8").count('modId="geckolib"'), 1)

    def test_single_kits_guards_and_packaging(self):
        project = self.make("neoforge-1.21.1")
        result = kit.add_kit(project, "springs")
        self.assertEqual(sorted(Path(p).name for p in result["created"]), ["BoneMath.java", "DevTrace.java", "SpringBones.java"])
        self.assertEqual(kit.add_kit(project, "springs")["created"], [])
        with self.assertRaisesRegex(ValueError, "--mob"):
            kit.add_kit(project, "geomob")
        with self.assertRaisesRegex(ValueError, "NeoForge 1.21.1"):
            kit.add_kit(self.make("fabric-1.21.1", "fab"), "springs")
        code, _, error = self.invoke(["kit", str(project), "geomob", "--mob", "x", "--hitbox", "wide"])
        self.assertEqual(code, 2)
        shipped = {path.relative_to(ROOT).as_posix() for path in product.product_files(ROOT)}
        for name in kit.template_files() + pipeline.template_files() + ["templates/devshots/DevScenes.java", "docs/API.md", "docs/MOBS.md"]:
            self.assertIn(name, shipped)

    def test_home_kit_builds_on_the_mob_and_ships_its_gametests(self):
        project = self.root / "homed"
        init_project(project, "homed", "dev.example.homed", "Homed", with_tests=True, examples=False)
        with self.assertRaisesRegex(ValueError, "geomob --mob den_keeper first"):
            kit.add_kit(project, "home", "den_keeper")
        kit.add_kit(project, "geomob", "den_keeper")
        result = kit.add_kit(project, "home", "den_keeper")
        base = project / "src/main/java/dev/example/homed/den_keeper/home"
        for name in ("DenKeeperHomeBlock", "DenKeeperHomeBlockEntity", "DenKeeperHomeStructure", "DenKeeperHomePiece", "DenKeeperHomeContent"):
            text = (base / f"{name}.java").read_text(encoding="utf-8")
            self.assertNotRegex(text, r"@[A-Z_]+@", name)
        tests = (project / "src/gameTest/java/dev/example/homed/testing/DenKeeperHomeTests.java").read_text(encoding="utf-8")
        self.assertIn('@GameTestHolder("homed")', tests)
        self.assertIn("homeFormsOneResident", tests)
        entity = (base / "DenKeeperHomeBlockEntity.java").read_text(encoding="utf-8")
        self.assertIn('HOME_KEY = "homed:den_keeper_home"', entity)
        self.assertIn("isPositionEntityTicking", entity)                # an unloaded resident is not a missing one
        assets = project / "src/main/resources/assets/homed"
        self.assertTrue((assets / "blockstates/den_keeper_home.json").is_file())
        self.assertEqual(json.loads((assets / "lang/en_us.json").read_text(encoding="utf-8"))["block.homed.den_keeper_home"], "Den Keeper Home")
        self.assertTrue(any("structures on" in note for note in result["notes"]))
        with self.assertRaisesRegex(ValueError, "--mob"):
            kit.add_kit(project, "home")


class Pipeline(Temp):
    def scaffold(self):
        (self.root / "mod").mkdir()
        project = self.root / "mod" / "source"
        init_project(project, "probe", "dev.example.probe", "Probe Mod", target_id="neoforge-1.21.1")
        return project, pipeline.add_pipeline(project, "cave_stalker")

    def test_scaffold_layout_ownership_and_refresh(self):
        project, result = self.scaffold()
        target = Path(result["pipeline"])
        self.assertEqual(target, self.root / "mod" / "asset-pipeline")
        config = json.loads((target / "pipeline.json").read_text(encoding="utf-8"))
        self.assertEqual((config["mod_id"], config["mob"], config["package"], config["project"]),
                         ("probe", "cave_stalker", "dev.example.probe", "../source"))
        self.assertTrue((target / ".gitignore").is_file())
        self.assertFalse((target / "gitignore.txt").exists())
        rig = target / "mob/rig.py"
        engine = target / "lib/voxel.py"
        rig.write_text("# mine\n", encoding="utf-8")
        engine.write_text("# stale\n", encoding="utf-8")
        again = pipeline.add_pipeline(project, "cave_stalker", force=True)
        self.assertEqual(rig.read_text(encoding="utf-8"), "# mine\n")                 # mob/ is the project's
        self.assertIn("FACE_AXES", engine.read_text(encoding="utf-8"))                # lib/ is refreshed
        self.assertIn("lib/voxel.py", again["refreshed"])
        with self.assertRaisesRegex(ValueError, "second mob"):
            pipeline.add_pipeline(project, "other_mob")
        self.assertEqual(json.loads((project / "mcforge-project.json").read_text())["pipelines"], {"cave_stalker": "../asset-pipeline"})

    @unittest.skipUnless(HAVE_NUMPY, "numpy and Pillow are needed to run the scaffolded pipeline")
    def test_scaffolded_pipeline_builds_and_validates_the_example(self):
        project, result = self.scaffold()
        kit.add_kit(project, "geomob", "cave_stalker")
        env = dict(os.environ, PIPELINE_NO_VENV="1", PYTHONPATH=str(ROOT),
                   MCFORGE_COMMAND=json.dumps([sys.executable, "-m", "mcforge"]))
        script = str(Path(result["pipeline"]) / "build_assets.py")
        done = subprocess.run([sys.executable, script, "all", "--validate"], capture_output=True, text=True, env=env, timeout=600)
        self.assertEqual(done.returncode, 0, done.stdout[-3000:] + done.stderr[-3000:])
        self.assertIn("z_fighting=0", done.stdout)
        assets = project / "src/main/resources/assets/probe"
        geo = assets / "geo/entity/cave_stalker.geo.json"
        self.assertEqual(modelcheck.check_model(geo)["z_fighting"], [])
        for relative in ("textures/entity/cave_stalker.png", "textures/entity/cave_stalker_glowmask.png",
                         "textures/entity/cave_stalker_uvtest.png", "animations/entity/cave_stalker.animation.json"):
            self.assertTrue((assets / relative).is_file(), relative)
        clips = json.loads((assets / "animations/entity/cave_stalker.animation.json").read_text(encoding="utf-8"))["animations"]
        self.assertEqual(sorted(clips), ["attack", "death", "hurt", "idle", "walk"])
        self.assertEqual(clips["walk"]["timeline"], {"0.25": "step_l#0;", "0.75": "step_r#0;"})
        self.assertNotIn("tail_phys", clips["walk"]["bones"])                          # procedural bones are never keyed
        gen = project / "src/main/java/dev/example/probe/gen"
        java = (gen / "CaveStalkerClips.java").read_text(encoding="utf-8")
        self.assertIn("public static final int[] ATTACK_CONTACT = {6};", java)
        self.assertIn("GENERATED", java)                                               # the kit's placeholder was replaced
        rig = (gen / "CaveStalkerRig.java").read_text(encoding="utf-8")
        self.assertIn('new SpringBones.Def(TAIL_PHYS, 110.0f, 8.0f, 22.0f, 0.0f, 0.06f, 0.0f, -1.0f, 3.5f, 3.0f)', rig)
        self.assertTrue((self.root / "mod/media/look/sheet.png").is_file())
        self.assertTrue((self.root / "mod/media/cave_stalker.bbmodel").is_file())
        # the offline preview of the toolkit renders the generated geometry with its texture
        code, out, _ = self.invoke(["preview", str(project), str(geo)])
        self.assertEqual(code, 0, out)
        # the opt-in world step: a template that holds the home block, and the complete set of worldgen files
        world = subprocess.run([sys.executable, script, "world", "--validate"], capture_output=True, text=True, env=env, timeout=120)
        self.assertEqual(world.returncode, 0, world.stdout + world.stderr)
        data = project / "src/main/resources/data/probe"
        for relative in ("structure/sentinel_den.nbt", "worldgen/structure/sentinel_den.json", "worldgen/structure_set/sentinel_dens.json",
                         "worldgen/template_pool/sentinel_den.json", "tags/worldgen/biome/has_structure/sentinel_den.json"):
            self.assertTrue((data / relative).is_file(), relative)
        import gzip
        self.assertIn(b"probe:cave_stalker_home", gzip.decompress((data / "structure/sentinel_den.nbt").read_bytes()))
        (data / "worldgen/structure_set/sentinel_dens.json").unlink()
        broken = subprocess.run([sys.executable, script, "world", "--validate"], capture_output=True, text=True, env=env, timeout=120)
        self.assertEqual(broken.returncode, 0)                           # run() rewrites the set, so validation passes again
        # spring tuning: a traced peak of 0.30 on a gain of 3.0 becomes 7.5 (target 0.75)
        log = project / "run-devshots/logs"
        log.mkdir(parents=True)
        (log / "latest.log").write_text("x MCFORGE-TRACE spring id=physics name=tail_phys peak=0.300 max=0.4 clamp=1.000\n", encoding="utf-8")
        tune = subprocess.run([sys.executable, script, "springs", "physics"], capture_output=True, text=True, env=env, timeout=120)
        self.assertEqual(tune.returncode, 0, tune.stdout + tune.stderr)
        gains = json.loads((Path(result["pipeline"]) / "spring_gains.json").read_text(encoding="utf-8"))
        self.assertAlmostEqual(gains["tail_phys"], 7.5, places=3)


class Guides(Temp):
    def test_bundled_guides_exist_and_new_topics_route(self):
        for name, file in cli.GUIDES.items():
            self.assertTrue((ROOT / "docs" / file).is_file(), name)
        code, out, _ = self.invoke(["guide", "api"])
        self.assertEqual(code, 0)
        self.assertIn("GeckoLibCache", out)
        routed = plan.plan("a detailed animated companion mob with a custom model")
        route = next(step for step in routed["steps"] if step.get("route") == "character mob (GeckoLib)")
        self.assertEqual(route["guide"], "mobs")
        self.assertTrue(any(command.startswith("pipeline ") for command in route["commands"]))

    def test_worldgen_requests_route_to_the_home_kit(self):
        routed = plan.plan("a forge keeper mob that lives in a structure next to lava in the nether")
        route = next(step for step in routed["steps"] if step.get("route") == "homes, structures and spawns")
        self.assertEqual(route["guide"], "worldgen")
        self.assertTrue(any("structures on" in pitfall or "structures off" in pitfall for pitfall in route["pitfalls"]))
        code, out, _ = self.invoke(["guide", "worldgen"])
        self.assertEqual(code, 0)
        self.assertIn("structure generation on", out)

    def test_local_guides_load_by_name_and_never_shadow_bundled_ones(self):
        folder = self.root / "private"
        folder.mkdir()
        (folder / "house-style.md").write_text("# House style\nPrivate notes.\n", encoding="utf-8")
        (folder / "entities.md").write_text("shadow attempt\n", encoding="utf-8")
        (folder / "Bad Name!.md").write_text("ignored\n", encoding="utf-8")
        # a machine may hold real private guides beside the toolkit: the test looks only at its own folder
        with patch.dict(os.environ, {"MCFORGE_GUIDES": str(folder)}), patch.object(cli, "local_guide_dirs", lambda: [folder]):
            self.assertEqual(list(cli.local_guides()), ["house-style"])
            code, out, _ = self.invoke(["guide", "house-style"])
            self.assertEqual((code, out.strip().splitlines()[0]), (0, "# House style"))
            code, out, _ = self.invoke(["guide", "entities"])
            self.assertIn("Animated entities", out)
            code, out, _ = self.invoke(["guide", "list"])
            self.assertEqual(list(json.loads(out)["local"]), ["house-style"])
            self.assertEqual(plan.plan("a mob")["local_guides"], ["house-style"])
            self.assertEqual(cli.capabilities()["local_guides"], ["house-style"])
        code, _, error = self.invoke(["guide", "nope"])
        self.assertEqual(code, 2)
        self.assertIn("Unknown guide", error)
        # private guides are machine-local: the product allowlist never includes local/
        self.assertFalse(any("local" in path.relative_to(ROOT).parts for path in product.product_files(ROOT)))


if __name__ == "__main__":
    unittest.main()
