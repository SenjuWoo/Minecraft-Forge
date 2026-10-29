"""Verify freshness and failure behavior with real files and a simulated Gradle boundary."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from mcforge import verification


class VerificationTests(unittest.TestCase):
    def setUp(self):
        scratch = Path(__file__).resolve().parents[1] / "local/test-temp"
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        self.write("mcforge-project.json", json.dumps({"mod_id": "garden", "package": "dev.example.garden", "with_tests": True}))
        self.write("gradle.properties", "mod_id=garden\nmod_version=1.0.0\n")
        self.write("build.gradle", "plugins { id 'java-library' }\n")
        self.write("src/main/java/dev/example/garden/Garden.java", "class Garden {}\n")
        self.source = self.project / "src/main/java/dev/example/garden/Garden.java"
        self.report = self.project / "build/reports/gametest/results.xml"
        self.jar = self.project / "build/libs/garden-1.0.0.jar"
        self.info = {"target": {"minecraft": "1.21.1", "java_major": 21, "neo_version": "21.1.265"}, "warnings": []}
        self.addCleanup(patch.stopall)
        patch.object(verification, "_project_info", return_value=self.info).start()
        patch.object(verification, "select_java", return_value=self.project / "jdk").start()
        patch.object(verification, "check_java", return_value={"home": "fixture-jdk", "major": 21, "jdk": True}).start()

    def write(self, name, value):
        path = self.project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")
        return path

    def artifact(self, *, version="1.0.0", leak=False):
        self.jar.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(self.jar, "w") as archive:
            archive.writestr("META-INF/neoforge.mods.toml", f'[[mods]]\nmodId="garden"\nversion="{version}"\n')
            archive.writestr("dev/example/garden/Garden.class", b"compiled fixture")
            if leak:
                archive.writestr("dev/example/garden/testing/TestMod.class", b"must not ship")

    def runner(self, project, tasks, java_home, *, log_path):
        self.assertEqual(project, self.project)
        self.assertEqual(java_home, self.project / "jdk")
        log_path.write_text("Tasks: " + " ".join(tasks), encoding="utf-8")
        if tasks == ["runData"]:
            self.write("src/generated/resources/data/garden/recipe/generated.json", '{"type":"fixture"}')
        else:
            self.artifact()
            if "runGameTestServer" in tasks:
                self.write("build/reports/gametest/results.xml", '<testsuite tests="999"><testcase name="placesBlock"/><testcase name="craftsItem"/></testsuite>')
        return 0

    def run_verification(self, runner=None, **kwargs):
        with patch.object(verification, "run_gradle", side_effect=runner or self.runner):
            return verification.verify_project(self.project, **kwargs)

    def receipt(self):
        return json.loads((self.project / "build/mcforge/verification.json").read_text())

    def test_fresh_success_receipt_binds_commands_sources_generated_report_and_jar(self):
        result = self.run_verification()
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["tests"]["count"], 2)  # Actual elements, not the misleading suite count.
        saved = self.receipt()
        self.assertEqual([step["tasks"] for step in saved["commands"]], [["runData"], ["runGameTestServer", "build"]])
        self.assertTrue(all(step["exit_code"] == 0 for step in saved["commands"]))
        self.assertIn("src/main/java/dev/example/garden/Garden.java", saved["inputs"])
        self.assertIn("src/generated/resources/data/garden/recipe/generated.json", saved["generated"])
        self.assertIn("build/reports/gametest/results.xml", saved["outputs"])
        self.assertIn("build/libs/garden-1.0.0.jar", saved["outputs"])
        self.assertTrue(Path(result["logs"][0]).is_file())
        self.assertEqual(verification.check_receipt(self.project)["run_id"], result["run_id"])
        self.assertFalse((self.project / "build/mcforge/verification.lock").exists())

    def test_old_passing_xml_cannot_satisfy_new_run_that_does_not_write_report(self):
        self.run_verification()
        old_run = self.receipt()["run_id"]

        def no_report(*args, **kwargs):
            code = self.runner(*args, **kwargs)
            if "runGameTestServer" in args[1]:
                self.report.unlink()
            return code

        with self.assertRaisesRegex(ValueError, "Fresh GameTest"):
            self.run_verification(no_report)
        saved = self.receipt()
        self.assertEqual(saved["status"], "failed")
        self.assertNotEqual(saved["run_id"], old_run)
        self.assertTrue(list((self.project / "build/mcforge/verification").glob("*/previous-gametest.xml")))
        with self.assertRaisesRegex(ValueError, "successful"):
            verification.check_receipt(self.project)

    def test_changed_added_and_deleted_inputs_make_receipt_stale(self):
        self.run_verification()
        original = self.source.read_text()
        for mutation in ("changed", "added", "deleted"):
            with self.subTest(mutation=mutation):
                extra = self.project / "src/newSourceSet/java/Added.java"
                if mutation == "changed":
                    self.source.write_text("class Garden { int changed; }")
                elif mutation == "added":
                    extra.parent.mkdir(parents=True)
                    extra.write_text("class Added {}")
                else:
                    self.source.unlink()
                with self.assertRaisesRegex(ValueError, "stale"):
                    verification.check_receipt(self.project)
                self.source.write_text(original)
                if extra.exists():
                    shutil.rmtree(self.project / "src/newSourceSet")

    def test_generated_jar_report_and_log_changes_invalidate_receipt(self):
        self.run_verification()
        saved = self.receipt()
        names = ["src/generated/resources/data/garden/recipe/generated.json", "build/libs/garden-1.0.0.jar",
                 "build/reports/gametest/results.xml", next(name for name in saved["outputs"] if name.endswith(".log"))]
        for name in names:
            with self.subTest(name=name):
                path = self.project / name
                original = path.read_bytes()
                path.write_bytes(original + b"changed")
                with self.assertRaisesRegex(ValueError, "stale"):
                    verification.check_receipt(self.project)
                path.write_bytes(original)

    def test_local_dependencies_resources_and_config_are_bound_to_receipt(self):
        names = ("libs/helper.jar", "assets/extra.json", "config/build-input.properties")
        for name in names:
            self.write(name, "original")
        with (self.project / "build.gradle").open("a") as stream:
            stream.write("dependencies { implementation files('libs/helper.jar') }\n")
        self.run_verification()
        self.assertTrue(set(names).issubset(self.receipt()["inputs"]))
        for name in names:
            with self.subTest(name=name):
                self.write(name, "changed")
                with self.assertRaisesRegex(ValueError, "stale"):
                    verification.check_receipt(self.project)
                self.write(name, "original")
        self.write("libs/new.jar", "added dependency")
        with self.assertRaisesRegex(ValueError, "stale"):
            verification.check_receipt(self.project)

    def test_build_outputs_and_workspace_ledgers_do_not_invalidate_receipt(self):
        self.run_verification()
        for name in (".git/config", ".gradle/cache.bin", "build/extra.txt", "run-data/logs/debug.log", "STATE.md"):
            self.write(name, "new output or progress")
        self.assertEqual(verification.check_receipt(self.project)["status"], "passed")

    def test_changes_during_commands_fail_instead_of_issuing_current_evidence(self):
        for kind in ("source", "generated"):
            with self.subTest(kind=kind):
                def changing(*args, **kwargs):
                    code = self.runner(*args, **kwargs)
                    if "runGameTestServer" in args[1]:
                        path = self.source if kind == "source" else self.project / "src/generated/resources/data/garden/recipe/generated.json"
                        path.write_text("changed during build")
                    return code
                with self.assertRaisesRegex(ValueError, "changed"):
                    self.run_verification(changing)
                self.assertEqual(self.receipt()["status"], "failed")
                self.source.write_text("class Garden {}\n")

    def test_failed_and_interrupted_rerun_cannot_leave_old_success(self):
        self.run_verification()
        for outcome in (3, KeyboardInterrupt()):
            with self.subTest(outcome=repr(outcome)):
                def failing(*args, **kwargs):
                    self.runner(*args, **kwargs)
                    if isinstance(outcome, BaseException):
                        raise outcome
                    return outcome
                expected = KeyboardInterrupt if isinstance(outcome, BaseException) else ValueError
                with self.assertRaises(expected):
                    self.run_verification(failing)
                self.assertEqual(self.receipt()["status"], "interrupted" if expected is KeyboardInterrupt else "failed")
                self.assertFalse((self.project / "build/mcforge/verification.lock").exists())
                with self.assertRaises(ValueError):
                    verification.check_receipt(self.project)

    def test_existing_lock_blocks_concurrency_without_changing_receipt_or_lock(self):
        self.run_verification()
        original = (self.project / "build/mcforge/verification.json").read_bytes()
        lock = self.write("build/mcforge/verification.lock", '{"run_id":"another-run"}')
        with self.assertRaisesRegex(ValueError, "already locked"):
            self.run_verification()
        self.assertEqual(lock.read_text(), '{"run_id":"another-run"}')
        self.assertEqual((self.project / "build/mcforge/verification.json").read_bytes(), original)

    def test_missing_zero_failed_and_skipped_test_evidence_is_rejected(self):
        for report in ("<testsuite tests=\"9\"/>", "<testsuite><testcase name=\"bad\"><failure/></testcase></testsuite>",
                       "<testsuite><testcase name=\"skip\"><skipped/></testcase></testsuite>", "not XML"):
            with self.subTest(report=report):
                def invalid_report(*args, **kwargs):
                    code = self.runner(*args, **kwargs)
                    if "runGameTestServer" in args[1]:
                        self.report.write_text(report)
                    return code
                with self.assertRaises(ValueError):
                    self.run_verification(invalid_report)
                self.assertEqual(self.receipt()["status"], "failed")

    def test_bare_project_records_untested_coverage_instead_of_passed_tests(self):
        lock_path = self.project / "mcforge-project.json"
        lock = json.loads(lock_path.read_text())
        lock.pop("with_tests")
        lock_path.write_text(json.dumps(lock))
        result = self.run_verification()
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["tests"], {"status": "not_configured", "count": 0})
        self.assertTrue(result["warnings"])
        self.assertEqual(self.receipt()["commands"][-1]["tasks"], ["build"])

    def test_wrong_version_and_leaked_test_mod_artifact_are_rejected(self):
        for bad in ("version", "leak"):
            with self.subTest(bad=bad):
                def wrong_artifact(*args, **kwargs):
                    code = self.runner(*args, **kwargs)
                    if "runGameTestServer" in args[1]:
                        self.artifact(version="9.0" if bad == "version" else "1.0.0", leak=bad == "leak")
                    return code
                with self.assertRaisesRegex(ValueError, "identity|test content"):
                    self.run_verification(wrong_artifact)

    def test_inspection_failure_invalidates_prior_success_before_running_commands(self):
        self.run_verification()
        with patch.object(verification, "_project_info", side_effect=ValueError("Target drift")), patch.object(verification, "run_gradle") as run:
            with self.assertRaisesRegex(ValueError, "Target drift"):
                verification.verify_project(self.project)
            run.assert_not_called()
        self.assertEqual(self.receipt()["status"], "failed")

    def test_external_build_includes_fail_without_executing_them(self):
        self.write("settings.gradle", "includeBuild('../external')\n")
        with patch.object(verification, "run_gradle") as run:
            with self.assertRaisesRegex(ValueError, "external"):
                verification.verify_project(self.project)
            run.assert_not_called()
        self.assertEqual(self.receipt()["status"], "failed")

    def test_inline_and_multiline_external_builds_fail_but_comments_are_ignored(self):
        for text in ("pluginManagement { includeBuild('../external') }\n", 'rootProject.name="garden"; include(":child")\n',
                     "plugins {}\napply(\n from = 'extra.gradle'\n)\n"):
            with self.subTest(text=text):
                self.write("settings.gradle", text)
                with self.assertRaisesRegex(ValueError, "external included/applied"):
                    verification._inputs(self.project)
        self.write("settings.gradle", "// includeBuild('../external')\n/* apply from: '../external.gradle' */\n")
        self.assertIn("settings.gradle", verification._inputs(self.project))

    def test_external_literal_file_inputs_are_rejected(self):
        for value in ("../external.jar", "/opt/external.jar", "C:/external.jar", "file:///opt/external.jar"):
            with self.subTest(value=value):
                self.write("build.gradle", f"dependencies {{ implementation files('{value}') }}\n")
                with self.assertRaisesRegex(ValueError, "project-local"):
                    verification._inputs(self.project)

    def test_resource_directory_named_build_is_input_not_build_output(self):
        resource = self.write("src/main/resources/build/model.json", "original")
        self.run_verification()
        resource.write_text("changed")
        with self.assertRaisesRegex(ValueError, "stale"):
            verification.check_receipt(self.project)


if __name__ == "__main__":
    unittest.main()
