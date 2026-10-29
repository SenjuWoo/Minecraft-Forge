"""Check native argument boundaries, durable logs and cancellation of an owned child."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from mcforge import workbench


class GradleRunnerTests(unittest.TestCase):
    def setUp(self):
        scratch = workbench.ROOT / "local/test-temp"
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        wrapper = self.root / "gradle/wrapper/gradle-wrapper.jar"
        wrapper.parent.mkdir(parents=True)
        wrapper.write_bytes(b"wrapper fixture")
        (self.root / "mcforge-project.json").write_text(json.dumps({
            "java_major": 21, "gradle_wrapper_sha256": hashlib.sha256(wrapper.read_bytes()).hexdigest()}))
        self.info = {"target": {"java_major": 21}, "errors": [], "drift": []}

    def run_child(self, code, *, options=(), log=None):
        original = subprocess.Popen
        commands = []

        def child(command, **kwargs):
            commands.append(command)
            return original([sys.executable, "-c", code], **kwargs)

        stderr = io.StringIO()
        with patch("mcforge.project.inspect_project", return_value=self.info), \
                patch.object(workbench, "select_java", return_value=self.root / "jdk"), \
                patch.object(workbench.subprocess, "Popen", side_effect=child), \
                contextlib.redirect_stderr(stderr):
            result = workbench.run_gradle(self.root, ["tasks"], options=options, log_path=log)
        return result, commands, stderr.getvalue()

    def test_allowed_native_options_and_real_output_are_logged(self):
        log = self.root / "build/mcforge/probe.log"
        result, commands, stderr = self.run_child("print('native output')", options=("--all", "--offline"), log=log)
        self.assertEqual(result, 0)
        self.assertEqual(commands[0][-3:], ["--all", "--offline", "tasks"])
        self.assertEqual(log.read_text().strip(), "native output")
        self.assertIn(str(log), stderr)
        self.assertIn("Gradle exit: 0", stderr)

    def test_failure_has_bounded_summary_and_complete_durable_log(self):
        result, _, stderr = self.run_child("import sys; [print('detail '+str(i)) for i in range(70)]; sys.exit(7)")
        self.assertEqual(result, 7)
        logs = list((self.root / "build/mcforge/logs").glob("*.log"))
        self.assertEqual(len(logs), 1)
        self.assertEqual(len(logs[0].read_text().splitlines()), 70)
        self.assertIn("detail 69", stderr)
        self.assertNotIn("detail 0\n", stderr)
        self.assertLess(len(stderr.splitlines()), 25)

    def test_no_shell_or_project_redirect_flags_reach_native_process(self):
        for value in ("--project-dir=../other", "-p", "--init-script=evil", "--gradle-user-home=x", "build;whoami", "--args=x"):
            with self.subTest(value=value), patch.object(workbench.subprocess, "Popen") as child:
                with self.assertRaisesRegex(ValueError, "Unsupported Gradle option"):
                    workbench.run_gradle(self.root, ["build"], options=(value,))
                child.assert_not_called()
        self.assertFalse((self.root / "build").exists())

    def test_drift_blocks_run_and_old_logs_are_never_overwritten(self):
        info = {**self.info, "drift": [{"field": "neo_version"}]}
        with patch("mcforge.project.inspect_project", return_value=info), patch.object(workbench.subprocess, "Popen") as child:
            with self.assertRaisesRegex(ValueError, "target is unresolved or changed"):
                workbench.run_gradle(self.root, ["build"])
            child.assert_not_called()
        log = self.root / "keep.log"
        log.write_text("personal output")
        with self.assertRaises(FileExistsError):
            self.run_child("print('new')", log=log)
        self.assertEqual(log.read_text(), "personal output")

    def test_implicit_project_or_jvm_overrides_never_reach_gradle(self):
        for key in ("ORG_GRADLE_PROJECT_neo_version", "JAVA_TOOL_OPTIONS", "JDK_JAVA_OPTIONS"):
            with self.subTest(key=key), patch.dict(os.environ, {key: "private value"}), \
                    patch.object(workbench.subprocess, "Popen") as child:
                with self.assertRaisesRegex(ValueError, "(?i)" + key) as raised:
                    workbench.run_gradle(self.root, ["build"])
                self.assertNotIn("private value", str(raised.exception))
                child.assert_not_called()

    def test_shared_init_and_project_system_properties_are_explicitly_unsupported(self):
        with patch.object(workbench, "ROOT", self.root):
            config = self.root / "local/gradle/init.d/override.gradle"
            config.parent.mkdir(parents=True)
            config.write_text("allprojects { version='other' }")
            with self.assertRaisesRegex(ValueError, "shared Gradle"):
                workbench.check_gradle_context(self.root)
            config.unlink()
            (self.root / "gradle.properties").write_text("systemProp.org.gradle.project.neo_version=other\n")
            with self.assertRaisesRegex(ValueError, "systemProp"):
                workbench.check_gradle_context(self.root)

    def test_interrupt_stops_the_real_owned_child(self):
        original = subprocess.Popen
        processes = []

        class Interrupted:
            def __init__(self, process):
                self.process = process
                self.first = True

            def wait(self, *args, **kwargs):
                if self.first:
                    self.first = False
                    raise KeyboardInterrupt
                return self.process.wait(*args, **kwargs)

            def __getattr__(self, name):
                return getattr(self.process, name)

        def child(command, **kwargs):
            process = original([sys.executable, "-c", "import time; time.sleep(120)"], **kwargs)
            processes.append(process)
            return Interrupted(process)

        with patch("mcforge.project.inspect_project", return_value=self.info), \
                patch.object(workbench, "select_java", return_value=self.root / "jdk"), \
                patch.object(workbench.subprocess, "Popen", side_effect=child), \
                contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(KeyboardInterrupt):
                workbench.run_gradle(self.root, ["build"])
        self.assertEqual(len(processes), 1)
        self.assertIsNotNone(processes[0].poll())


if __name__ == "__main__":
    unittest.main()
