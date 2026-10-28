"""Fixture-level evidence checks; runtime proof comes from the real CI starter."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from scripts.verify_starter import main, verify


class StarterProofTests(unittest.TestCase):
    def setUp(self):
        scratch = Path(__file__).resolve().parents[1] / "local/test-temp"
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        self.mod_id = "garden"
        self.recipe_path = "data/garden/recipe/example_items_from_block.json"
        self.advancement_path = "data/garden/advancement/recipes/misc/example_items_from_block.json"
        self.lock = {"mod_id": self.mod_id, "package": "dev.example.garden", "with_tests": True}
        self.write_json("mcforge-project.json", self.lock)
        (self.project / "gradle.properties").write_text("mod_version=1.0.0\n", encoding="utf-8")
        self.recipe = {"type": "minecraft:crafting_shapeless", "category": "misc",
                       "ingredients": [{"item": "garden:example_block"}],
                       "result": {"id": "garden:example_item", "count": 9}}
        self.advancement = {
            "parent": "minecraft:recipes/root", "rewards": {"recipes": ["garden:example_items_from_block"]},
            "criteria": {
                "has_the_recipe": {"trigger": "minecraft:recipe_unlocked", "conditions": {"recipe": "garden:example_items_from_block"}},
                "has_example_block": {"trigger": "minecraft:inventory_changed", "conditions": {"items": [{"items": "garden:example_block"}]}}},
            "requirements": [["has_the_recipe", "has_example_block"]]}
        self.write_json("src/generated/resources/" + self.recipe_path, self.recipe)
        self.write_json("src/generated/resources/" + self.advancement_path, self.advancement)
        self.entries = {"META-INF/neoforge.mods.toml": '[[mods]]\nmodId="garden"\nversion="1.0.0"\n',
                        self.recipe_path: json.dumps(self.recipe), self.advancement_path: json.dumps(self.advancement)}
        self.jar = self.project / "build/libs/garden-1.0.0.jar"
        self.write_jar()
        self.report = self.project / "build/reports/gametest/results.xml"
        self.report.parent.mkdir(parents=True)
        self.report.write_text('<testsuite tests="999"><testcase name="SmokeTests.registeredblockcanbeplaced"/><testcase name="smoketests.generatedrecipecraftsonlytheexpectedinput"/></testsuite>', encoding="utf-8")

    def write_json(self, relative, value):
        path = self.project / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")

    def write_jar(self):
        self.jar.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(self.jar, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, value in self.entries.items():
                archive.writestr(name, value)

    def test_verifies_actual_cases_outputs_namespace_and_artifact_hash(self):
        result = verify(self.project)
        self.assertEqual(result["tests"], 2)  # Ignore the misleading suite count.
        self.assertEqual(result["sha256"], hashlib.sha256(self.jar.read_bytes()).hexdigest())
        self.assertEqual(result["recipe"], self.recipe_path)
        self.assertTrue(result["tests_excluded"])
        with contextlib.redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(main([str(self.project)]), 0)
        self.assertEqual(json.loads(stdout.getvalue())["tests"], 2)

    def test_report_requires_actual_cases_and_named_assertions(self):
        for report in ('<testsuite tests="2"/>', '<testsuite><testcase name="other"/><testcase name="another"/></testsuite>', '<testsuite><testcase name="registeredBlockCanBePlaced"/></testsuite>'):
            with self.subTest(report=report):
                self.report.write_text(report, encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "testcase|GameTest missing"):
                    verify(self.project)
        self.report.unlink()
        with self.assertRaises(OSError):
            verify(self.project)

    def test_rejects_any_failed_errored_or_skipped_report_element(self):
        good = self.report.read_text()
        for element in ("failure", "error", "skipped"):
            with self.subTest(element=element):
                self.report.write_text(good.replace("</testsuite>", f"<{element}/></testsuite>"), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "failed, errored or skipped"):
                    verify(self.project)

    def test_rejects_wrong_recipe_and_unlock_reward(self):
        bad_recipe = {**self.recipe, "result": {"id": "garden:example_item", "count": 8}}
        self.write_json("src/generated/resources/" + self.recipe_path, bad_recipe)
        with self.assertRaisesRegex(ValueError, "Generated recipe"):
            verify(self.project)
        self.write_json("src/generated/resources/" + self.recipe_path, self.recipe)
        for change in ({"rewards": {"recipes": ["wrong:recipe"]}}, {"criteria": {}}, {"requirements": [["has_the_recipe"]]}):
            self.write_json("src/generated/resources/" + self.advancement_path, {**self.advancement, **change})
            with self.assertRaises(ValueError):
                verify(self.project)

    def test_rejects_test_classes_structure_and_metadata_in_product(self):
        original = dict(self.entries)
        for leaked in ("dev/example/garden/testing/SmokeTests.class", "data/garden/structure/empty.nbt"):
            with self.subTest(leaked=leaked):
                self.entries = {**original, leaked: b"leak"}
                self.write_jar()
                with self.assertRaisesRegex(ValueError, "leaked"):
                    verify(self.project)
        self.entries = dict(original)
        self.entries["META-INF/neoforge.mods.toml"] += '[[mods]]\nmodId="garden_tests"\nversion="1.0.0"\n'
        self.write_jar()
        with self.assertRaisesRegex(ValueError, "main mod"):
            verify(self.project)

    def test_rejects_missing_or_stale_packaged_json(self):
        original = dict(self.entries)
        for name in (self.recipe_path, self.advancement_path):
            with self.subTest(name=name):
                self.entries = {k: v for k, v in original.items() if k != name}
                self.write_jar()
                with self.assertRaisesRegex(ValueError, "packaged entry"):
                    verify(self.project)
        self.entries = {**original, self.recipe_path: json.dumps({**self.recipe, "category": "building"})}
        self.write_jar()
        with self.assertRaisesRegex(ValueError, "differs"):
            verify(self.project)

    def test_artifact_selection_is_exact_or_unambiguous(self):
        extra = self.jar.with_name("garden-2.0.0.jar")
        extra.write_bytes(self.jar.read_bytes())
        self.assertEqual(Path(verify(self.project)["artifact"]), self.jar)
        (self.project / "gradle.properties").unlink()
        with self.assertRaisesRegex(ValueError, "unambiguous"):
            verify(self.project)
        extra.unlink()
        self.assertEqual(Path(verify(self.project)["artifact"]), self.jar)
        self.jar.unlink()
        with self.assertRaisesRegex(ValueError, "unambiguous"):
            verify(self.project)

    def test_rejects_missing_opt_in_and_malformed_data_with_json_cli_error(self):
        self.write_json("mcforge-project.json", {**self.lock, "with_tests": False})
        with self.assertRaisesRegex(ValueError, "with-tests"):
            verify(self.project)
        self.write_json("mcforge-project.json", self.lock)
        for content in ("{bad", "null", "[]"):
            (self.project / "src/generated/resources" / self.recipe_path).write_text(content, encoding="utf-8")
            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                self.assertEqual(main([str(self.project)]), 1)
            self.assertIn("error", json.loads(stderr.getvalue()))
        self.write_json("src/generated/resources/" + self.recipe_path, self.recipe)
        for report in ("<bad", '<!DOCTYPE test [<!ENTITY x "boom">]><testsuite/>'):
            self.report.write_text(report, encoding="utf-8")
            with contextlib.redirect_stderr(io.StringIO()) as stderr:
                self.assertEqual(main([str(self.project)]), 1)
            self.assertIn("error", json.loads(stderr.getvalue()))


if __name__ == "__main__":
    unittest.main()
