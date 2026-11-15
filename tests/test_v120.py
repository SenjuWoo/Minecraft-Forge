"""1.2.0: arena stand height, --no-examples, model-check, run-* exclusions, BOM and progress-line handling."""
import base64
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import unittest
from unittest.mock import patch
import zipfile

from mcforge import modelcheck, project, verification, workbench
from mcforge.scaffold import init_project, strip_example_java
from tests.test_v100 import ROOT, Temp

MDKS = ("neoforge-1.21.1-mdk.zip", "neoforge-26.3-mdk.zip", "forge-1.20.1-mdk.zip", "forge-26.3-mdk.zip")


def cube(name, low, high, **extra):
    return {"uuid": name, "name": name, "type": "cube", "from": low, "to": high, **extra}


class ArenaTests(Temp):
    def test_starter_ships_the_arena_test_with_the_corrected_stand_height(self):
        path = self.root / "arena"
        init_project(path, "garden", "dev.example.garden", "Garden", with_tests=True)
        source = (path / "src/gameTest/java/dev/example/garden/testing/ArenaTests.java").read_text(encoding="utf-8")
        self.assertIn("STAND = new BlockPos(7, 2, 7)", source)
        self.assertIn('@GameTestHolder("garden")', source)
        self.assertIn('template = "arena"', source)
        self.assertIn("runAfterDelay(100", source)
        self.assertTrue((path / "src/gameTest/java/dev/example/garden/testing/SmokeTests.java").is_file())

    def test_load_tests_include_the_arena_test(self):
        path = self.make("neoforge-1.21.1")
        result = workbench.add_load_tests(path)
        self.assertIn("ArenaTests.largeMobStandsUnhurtOnTheArenaFloor", result["tests"])
        self.assertTrue((path / "src/gameTest/java/dev/example/probe/testing/ArenaTests.java").is_file())
        self.assertTrue((path / "src/gameTest/resources/data/probe/structure/arena.nbt").is_file())

    def test_testing_guide_puts_mobs_on_the_floor(self):
        guide = (ROOT / "docs/TESTING.md").read_text(encoding="utf-8")
        self.assertIn("(7, 2, 7)", guide)
        self.assertNotIn("new BlockPos(7, 1, 7)` is the centre", guide)


class NoExamplesTests(Temp):
    def test_stripper_leaves_a_compilable_shape_on_every_mdk(self):
        for name in MDKS:
            with self.subTest(mdk=name), zipfile.ZipFile(ROOT / "vendor" / name) as archive:
                entry = next(item for item in archive.namelist() if item.endswith("ExampleMod.java"))
                original = archive.read(entry).decode("utf-8")
                stripped = strip_example_java(original)
                self.assertNotRegex(stripped, r"EXAMPLE_|addCreative|BuildCreativeModeTabContentsEvent")
                for kept in ("class ExampleMod", 'MODID = "examplemod"', "BLOCKS", "ITEMS", "CREATIVE_MODE_TABS"):
                    self.assertIn(kept, stripped)
                self.assertEqual(stripped.count("{"), stripped.count("}"))
                self.assertLess(len(stripped), len(original))

    def test_unexpected_template_keeps_examples_with_a_warning(self):
        with self.assertRaisesRegex(ValueError, "still referenced"):
            strip_example_java("class A { void f() { use(EXAMPLE_ITEM); } }")

    def test_init_without_examples_and_with_tests(self):
        path = self.root / "mob"
        result = init_project(path, "horse", "dev.example.horse", "Horse", with_tests=True, examples=False)
        testing = path / "src/gameTest/java/dev/example/horse/testing"
        self.assertEqual(sorted(p.name for p in testing.iterdir()), ["ArenaTests.java", "LoadSmokeTest.java", "TestMod.java"])
        main = (path / "src/main/java/dev/example/horse/ExampleMod.java").read_text(encoding="utf-8")
        self.assertNotIn("EXAMPLE_", main)
        lang = json.loads((path / "src/main/resources/assets/horse/lang/en_us.json").read_text(encoding="utf-8"))
        self.assertFalse({"itemGroup.horse", "block.horse.example_block", "item.horse.example_item"} & set(lang))
        self.assertIn("horse.configuration.title", lang)
        self.assertEqual((result["lock"]["examples"], result["lock"]["starter"], result["lock"]["with_tests"]), (False, False, True))
        self.assertEqual(result["next"], "gradle PROJECT tasks; verify PROJECT")
        self.assertNotIn("warnings", result)

    def test_quickstart_without_examples_generates_no_example_assets(self):
        path = self.root / "q"
        result = workbench.quickstart_project(path, "qmob", "dev.example.qmob", "Q", examples=False)
        self.assertEqual(result["assets"], [])
        self.assertEqual(result["next"], "verify PROJECT")
        self.assertFalse((path / "src/main/resources/assets/qmob/textures/block/example_block.png").exists())
        fabric = self.root / "f"
        result = workbench.quickstart_project(fabric, "qfab", "dev.example.qfab", "Q", loader="fabric", minecraft="1.21.1", examples=False)
        self.assertEqual(result["assets"], [])
        self.assertFalse(list(fabric.rglob("example_block*")))

    def test_cli_flag_reaches_init_and_quickstart(self):
        code, output, _ = self.invoke(["init", str(self.root / "c"), "--mod-id", "cli", "--package", "dev.example.cli", "--name", "C",
                                       "--target", "forge-1.20.1", "--no-examples"])
        self.assertEqual(code, 0)
        self.assertFalse(json.loads(output)["lock"]["examples"])
        self.assertNotIn("EXAMPLE_", (self.root / "c/src/main/java/dev/example/cli/ExampleMod.java").read_text(encoding="utf-8"))


class ModelCheckTests(Temp):
    def write(self, name, data):
        path = self.root / name
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def bbmodel(self, cubes, groups=None):
        groups = groups or [{"uuid": "g", "name": "body", "origin": [0, 0, 0], "rotation": [0, 0, 0], "children": [c["uuid"] for c in cubes]}]
        return {"meta": {"format_version": "4.10", "model_format": "geckolib_model"}, "elements": cubes, "outliner": groups}

    def test_coplanar_same_facing_overlap_is_found_and_offset_fixes_it(self):
        found = modelcheck.check_model(self.write("a.bbmodel", self.bbmodel([cube("a", [0, 0, 0], [4, 4, 4]), cube("b", [2, 0, 2], [6, 3, 6])])))
        self.assertEqual(found["status"], "z_fighting")
        self.assertEqual({hit["face"] for hit in found["z_fighting"]}, {"down"})
        self.assertEqual(found["z_fighting"][0]["overlap"], [2.0, 2.0])
        fixed = modelcheck.check_model(self.write("b.bbmodel", self.bbmodel([cube("a", [0, 0, 0], [4, 4, 4]), cube("b", [2, -0.05, 2], [6, 3, 6])])))
        self.assertEqual(fixed["status"], "clean")

    def test_overlap_inside_a_third_cube_is_hidden(self):
        cubes = [cube("a", [0, 2, 0], [4, 4, 4]), cube("b", [0, 2, 0], [4, 5, 4]), cube("core", [-1, 0, -1], [5, 3, 5])]
        result = modelcheck.check_model(self.write("c.bbmodel", self.bbmodel(cubes)))
        self.assertNotIn("down", {hit["face"] for hit in result["z_fighting"]})

    def test_overlap_covered_by_a_touching_cube_is_hidden(self):
        pair = [cube("a", [0, 2, 0], [4, 4, 4]), cube("b", [0, 2, 0], [4, 5, 4])]
        exposed = modelcheck.check_model(self.write("t1.bbmodel", self.bbmodel(pair)))
        self.assertIn("down", {hit["face"] for hit in exposed["z_fighting"]})
        covered = modelcheck.check_model(self.write("t2.bbmodel", self.bbmodel(pair + [cube("below", [-1, 0, -1], [5, 2, 5])])))
        self.assertNotIn("down", {hit["face"] for hit in covered["z_fighting"]})

    def test_texture_index_zero_is_a_textured_face(self):
        faces = {name: {"uv": [0, 0, 4, 4], "texture": 0} for name in ("north", "east", "south", "west", "up", "down")}
        untextured = dict(faces, down={"uv": [0, 0, 4, 4], "texture": None})
        found = modelcheck.check_model(self.write("u1.bbmodel", self.bbmodel(
            [cube("a", [0, 0, 0], [4, 4, 4], faces=faces), cube("b", [0, 0, 0], [4, 2, 4], faces=faces)])))
        self.assertIn("down", {hit["face"] for hit in found["z_fighting"]})
        skipped = modelcheck.check_model(self.write("u2.bbmodel", self.bbmodel(
            [cube("a", [0, 0, 0], [4, 4, 4], faces=untextured), cube("b", [0, 0, 0], [4, 2, 4], faces=faces)])))
        self.assertNotIn("down", {hit["face"] for hit in skipped["z_fighting"]})

    def test_different_rotation_frames_are_not_compared(self):
        groups = [{"uuid": "g1", "name": "a", "origin": [0, 0, 0], "rotation": [0, 0, 0], "children": ["a"]},
                  {"uuid": "g2", "name": "b", "origin": [0, 0, 0], "rotation": [30, 0, 0], "children": ["b"]}]
        result = modelcheck.check_model(self.write("d.bbmodel", self.bbmodel([cube("a", [0, 0, 0], [4, 4, 4]), cube("b", [0, 0, 0], [4, 4, 4])], groups)))
        self.assertEqual((result["frames"], result["status"]), (2, "clean"))

    def test_geo_json_and_block_model(self):
        geo = {"format_version": "1.12.0", "minecraft:geometry": [{"description": {"identifier": "geometry.x"}, "bones": [
            {"name": "root", "pivot": [0, 0, 0]},
            {"name": "body", "parent": "root", "pivot": [0, 0, 0], "cubes": [
                {"origin": [-4, 0, 0], "size": [4, 4, 4], "uv": [0, 0]},
                {"origin": [-4, 0, 0], "size": [4, 4, 2], "uv": {"north": {"uv": [0, 0], "uv_size": [4, 4]}}}]}]}]}
        result = modelcheck.check_model(self.write("x.geo.json", geo))
        self.assertEqual((result["format"], [hit["face"] for hit in result["z_fighting"]]), ("geo", ["north"]))
        block = {"elements": [{"from": [0, 0, 0], "to": [16, 8, 16], "faces": {"up": {}, "down": {}}},
                              {"from": [4, 0, 4], "to": [12, 4, 12], "faces": {"up": {}}}]}
        result = modelcheck.check_model(self.write("block.json", block))
        self.assertEqual((result["format"], result["status"]), ("block", "clean"))

    def test_cli_exit_code(self):
        path = self.write("e.bbmodel", self.bbmodel([cube("a", [0, 0, 0], [4, 4, 4]), cube("b", [0, 0, 0], [4, 2, 4])]))
        code, output, _ = self.invoke(["model-check", str(path)])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(output)["status"], "z_fighting")
        clean = self.write("f.bbmodel", self.bbmodel([cube("a", [0, 0, 0], [4, 4, 4])]))
        self.assertEqual(self.invoke(["model-check", str(clean)])[0], 0)


class InputAndOutputTests(Temp):
    def test_every_root_run_directory_is_excluded_from_verification_inputs(self):
        path = self.make("neoforge-1.21.1")
        for folder in ("run", "run-devshots", "run-data"):
            (path / folder / "screenshots").mkdir(parents=True)
            (path / folder / "screenshots/a.png").write_bytes(b"png")
        (path / "src/main/resources/runtime.txt").write_text("kept", encoding="utf-8")
        inputs = verification._inputs(path)
        self.assertFalse([name for name in inputs if name.startswith("run")])
        self.assertIn("src/main/resources/runtime.txt", inputs)

    def test_bom_before_a_property_is_an_error_and_before_a_comment_a_warning(self):
        path = self.make("neoforge-1.21.1")
        properties = path / "gradle.properties"
        text = properties.read_text(encoding="utf-8")
        properties.write_bytes(b"\xef\xbb\xbf" + text.encode("utf-8"))
        self.assertTrue(text.lstrip().startswith("#"))
        report = project.inspect_project(path)
        self.assertTrue(any("byte-order mark" in warning for warning in report["warnings"]))
        lines = [line for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]
        properties.write_bytes(b"\xef\xbb\xbf" + "\n".join(lines).encode("utf-8") + b"\n")
        with self.assertRaisesRegex(ValueError, "byte-order mark.*Gradle does not see"):
            project.read_target(path)

    def test_progress_lines_can_be_turned_off(self):
        import io
        stream = io.StringIO()
        workbench.progress("Gradle log: x", stream)
        with patch.dict(os.environ, {"MCFORGE_INFO": "off"}):
            workbench.progress("hidden", stream)
        self.assertEqual(stream.getvalue(), "Gradle log: x\n")


@unittest.skipUnless(os.name == "nt" and shutil.which("powershell.exe"), "Windows PowerShell 5.1 only")
class LauncherStderrTests(Temp):
    def test_merged_stderr_does_not_abort_a_successful_run(self):
        home = self.root / "launcher"
        (home / "mcforge").mkdir(parents=True)
        shutil.copyfile(ROOT / "Minecraft-Forge.ps1", home / "Minecraft-Forge.ps1")
        (home / "mcforge/__init__.py").write_text("", encoding="utf-8")
        (home / "mcforge/__main__.py").write_text(
            "import sys\nprint('Gradle log: x', file=sys.stderr, flush=True)\nprint('{\"ok\": true}')\nsys.exit(0)\n", encoding="utf-8")
        command = "$out = & '" + str(home / "Minecraft-Forge.ps1") + "' doctor 2>&1; $out | ForEach-Object { \"$_\" }; exit $LASTEXITCODE"
        done = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", command],
                              capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn('{"ok": true}', done.stdout)


if __name__ == "__main__":
    unittest.main()
