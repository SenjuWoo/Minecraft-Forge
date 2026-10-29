"""Check opt-in starter boundaries without downloading or launching Minecraft."""
import contextlib
import gzip
import io
import json
from pathlib import Path
import runpy
import shutil
import struct
import tempfile
import tomllib
import unittest
from unittest.mock import patch

from mcforge import workbench
from mcforge.__main__ import main


class StarterTests(unittest.TestCase):
    def setUp(self):
        scratch = Path(__file__).resolve().parents[1] / "local/test-temp"
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.assertTrue(self.root.resolve().is_relative_to(scratch.resolve()))

    def create(self, path="project", mod_id="garden_mod", package="dev.example.garden"):
        destination = self.root / path
        result = workbench.init_project(destination, mod_id, package, "Garden", with_tests=True)
        return destination, result

    def test_optional_starter_renders_isolated_sources_metadata_and_binary_structure(self):
        project, result = self.create()
        self.assertTrue(result["lock"]["with_tests"])
        self.assertEqual(json.loads((project / "mcforge-project.json").read_text()), result["lock"])
        sources = project / "src/gameTest/java/dev/example/garden/testing"
        self.assertEqual({path.name for path in sources.glob("*.java")}, {"TestMod.java", "SmokeTests.java", "ExampleRecipes.java"})
        for source in sources.glob("*.java"):
            text = source.read_text(encoding="utf-8")
            self.assertIn("package dev.example.garden.testing;", text)
            self.assertNotIn("@PACKAGE@", text)
            self.assertNotIn("@MOD_ID@", text)
        self.assertFalse((project / "src/main/java/dev/example/garden/testing").exists())
        self.assertFalse((project / "src/main/resources/data/garden_mod/structure/empty.nbt").exists())

        metadata = tomllib.loads((project / "src/gameTest/resources/META-INF/neoforge.mods.toml").read_text(encoding="utf-8"))
        self.assertEqual(metadata["mods"][0]["modId"], "garden_mod_tests")
        dependencies = metadata["dependencies"]["garden_mod_tests"]
        required = [entry for entry in dependencies if entry["modId"] == "garden_mod"]
        self.assertEqual(len(required), 1)
        self.assertEqual(required[0]["type"], "required")
        self.assertEqual(required[0]["versionRange"], "[0,)")

        nbt = project / "src/gameTest/resources/data/garden_mod/structure/empty.nbt"
        raw = gzip.decompress(nbt.read_bytes())
        self.assertTrue(raw.startswith(b"\x0a\x00\x00"), "Structure must be a named-root NBT compound")
        self.assertIn(b"DataVersion" + struct.pack(">i", 3955), raw)
        self.assertIn(b"minecraft:air", raw)
        self.assertIn(b"palette", raw)
        build = (project / "build.gradle").read_text(encoding="utf-8")
        self.assertIn("gameTest", build)
        self.assertIn('"${mod_id}_tests"', build)
        self.assertIn('neoForge.mods[project.mod_id]', build)
        self.assertNotIn("@MOD_ID@", build)
        self.assertIn("verify PROJECT --starter", (project / "STATE.md").read_text())
        self.assertIn("build/reports/gametest/results.xml", (project / "STATE.md").read_text())
        self.assertIn("unverified", (project / "STATE.md").read_text().lower())

    def test_default_starter_remains_bare_and_accepts_full_length_mod_id(self):
        project = self.root / "bare"
        result = workbench.init_project(project, "a" * 64, "dev.example.bare", "Bare")
        self.assertFalse(result["lock"].get("with_tests", False))
        self.assertFalse((project / "src/gameTest").exists())
        self.assertFalse((project / "src/main/java/dev/example/bare/testing").exists())

    def test_package_containing_template_mod_id_is_preserved(self):
        for with_tests in (False, True):
            project = self.root / ("tested" if with_tests else "bare-package")
            workbench.init_project(project, "garden", "dev.examplemod.feature", "Garden", with_tests=with_tests)
            for source in (project / "src/main/java/dev/examplemod/feature").glob("*.java"):
                self.assertIn("package dev.examplemod.feature;", source.read_text())
                self.assertNotIn("package dev.garden.feature;", source.read_text())
            if with_tests:
                source = project / "src/gameTest/java/dev/examplemod/feature/testing/SmokeTests.java"
                self.assertIn("import dev.examplemod.feature.ExampleMod;", source.read_text())

    def test_test_mod_suffix_limit_is_checked_before_writes(self):
        baseline = sorted(path.name for path in self.root.iterdir())
        with self.assertRaisesRegex(ValueError, "58|test.*ID|test.*id"):
            self.create(mod_id="a" * 59)
        self.assertEqual(sorted(path.name for path in self.root.iterdir()), baseline)
        project, _ = self.create(mod_id="a" * 58)
        metadata = tomllib.loads((project / "src/gameTest/resources/META-INF/neoforge.mods.toml").read_text())
        self.assertEqual(metadata["mods"][0]["modId"], "a" * 58 + "_tests")
        self.assertEqual(len(metadata["mods"][0]["modId"]), 64)

    def test_missing_testing_overlay_rolls_back_without_partial_project(self):
        toolkit = self.root / "toolkit"
        toolkit.mkdir()
        shutil.copytree(workbench.ROOT / "vendor", toolkit / "vendor")
        project = self.root / "missing-overlay"
        with patch.object(workbench, "ROOT", toolkit):
            with self.assertRaises((OSError, ValueError)):
                workbench.init_project(project, "garden", "dev.example.garden", "Garden", with_tests=True)
        self.assertFalse(project.exists())
        self.assertEqual(sorted(path.name for path in self.root.iterdir()), ["toolkit"])

    def test_cli_with_tests_creates_real_optional_starter(self):
        project = self.root / "cli"
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = main(["init", str(project), "--mod-id", "cli_mod", "--package", "dev.example.cli", "--name", "CLI Mod", "--with-tests"])
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(stdout.getvalue())["lock"]["with_tests"])
        self.assertTrue((project / "src/gameTest/java/dev/example/cli/testing/SmokeTests.java").is_file())

    def test_package_rejects_incomplete_testing_overlay(self):
        source = workbench.ROOT
        toolkit = self.root / "toolkit"
        toolkit.mkdir()
        for name in ("Minecraft-Forge.ps1", "README.md", "AGENTS.md", "LICENSE", "THIRD-PARTY.md", "CHANGELOG.md", "CONTRIBUTING.md", "SECURITY.md"):
            shutil.copyfile(source / name, toolkit / name)
        for name in ("vendor", "skills", "templates"):
            shutil.copytree(source / name, toolkit / name)
        (toolkit / "templates/testing/src/gameTest/java/SmokeTests.java").unlink()
        entrypoint = runpy.run_path(str(source / "scripts/package.py"))["main"]
        with patch.dict(entrypoint.__globals__, {"ROOT": toolkit}), patch.object(workbench, "ROOT", toolkit):
            with self.assertRaisesRegex(ValueError, "template|Template|starter|Starter"):
                entrypoint()
        self.assertFalse((toolkit / "dist").exists())


if __name__ == "__main__":
    unittest.main()
