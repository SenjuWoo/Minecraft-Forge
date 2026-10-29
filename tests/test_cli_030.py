"""Keep new command dispatch compatible without network or Gradle execution."""
import contextlib
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from mcforge import __main__ as cli


class Cli030Tests(unittest.TestCase):
    def invoke(self, arguments):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = cli.main(arguments)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_project_doctor_requires_matching_java_and_no_drift(self):
        info = {"target": {"minecraft": "1.21.1", "neo_version": "21.1.265", "java_major": 21},
                "lock_status": "locked", "errors": [], "drift": []}
        vendor = {"neo_version": "21.1.265", "commit": "fixture", "sha256": "fixture"}
        jdk = {"jdk": True, "major": 21, "exit_code": 0}
        with patch("mcforge.project.inspect_project", return_value=info) as inspect, \
                patch.object(cli, "java_candidates", return_value=[Path("jdk")]), \
                patch.object(cli, "check_java", return_value=jdk), \
                patch.object(cli, "verify_vendor", return_value=vendor):
            code, output, _ = self.invoke(["doctor", "--project", "mod"])
            self.assertEqual(code, 0)
            self.assertTrue(json.loads(output)["ready"])
            inspect.assert_called_with(Path("mod"))
            info["drift"] = [{"field": "neo_version"}]
            code, output, _ = self.invoke(["doctor", "--project", "mod"])
            self.assertEqual(code, 1)
            self.assertFalse(json.loads(output)["ready"])
            info["drift"] = []
            jdk["major"] = 25
            code, output, _ = self.invoke(["doctor", "--project", "mod"])
            self.assertEqual(code, 1)
            self.assertFalse(json.loads(output)["ready"])

    def test_updates_reports_partial_lookup_failure_with_nonzero_status(self):
        result = {"current": {}, "candidates": {}, "errors": ["metadata unavailable"]}
        with patch("mcforge.project.check_updates", return_value=result) as updates:
            code, output, _ = self.invoke(["updates", "mod"])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(output), result)
        updates.assert_called_once_with(Path("mod"))

    def test_verify_check_never_starts_new_build(self):
        with patch("mcforge.verification.check_receipt", return_value={"status": "passed"}) as check, \
                patch("mcforge.verification.verify_project") as build:
            code, output, _ = self.invoke(["verify", "mod", "--check"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output)["status"], "passed")
        check.assert_called_once_with(Path("mod"))
        build.assert_not_called()

    def test_verify_check_rejects_new_java_selection_before_any_work(self):
        with patch("mcforge.verification.check_receipt") as check, \
                patch("mcforge.verification.verify_project") as build:
            code, _, error = self.invoke(["verify", "mod", "--check", "--java-home", "jdk"])
        self.assertEqual(code, 2)
        self.assertIn("cannot be combined", json.loads(error)["error"])
        check.assert_not_called()
        build.assert_not_called()

    def test_starter_verification_forwards_selected_java(self):
        with patch("mcforge.verification.verify_project", return_value={"status": "passed"}) as build:
            code, _, _ = self.invoke(["verify", "mod", "--starter", "--java-home", "jdk"])
        self.assertEqual(code, 0)
        build.assert_called_once_with(Path("mod"), Path("jdk"), starter=True)

    def test_original_source_command_keeps_literal_query(self):
        query = r"event/handler\literal.*"
        with patch.object(cli, "search_sources", return_value=1) as search:
            code, _, _ = self.invoke(["sources", "sources.jar", query])
        self.assertEqual(code, 1)
        search.assert_called_once_with(Path("sources.jar"), query)

    def test_project_sources_print_location_or_search_literal_query(self):
        source = {"source": "prepared-sources.jar", "kind": "neoforge"}
        query = r"event/handler\literal.*"
        with patch("mcforge.sources.resolve_sources", return_value=source) as resolve, \
                patch.object(cli, "search_sources", return_value=0) as search:
            code, output, _ = self.invoke(["sources", "--project", "mod"])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(output), source)
            search.assert_not_called()
            code, _, error = self.invoke(["sources", "--project", "mod", query])
        self.assertEqual(code, 0)
        self.assertIn(source["source"], error)
        resolve.assert_called_with(Path("mod"))
        search.assert_called_once_with(Path(source["source"]), query)

    def test_gradle_forwards_allowed_diagnostics_and_preserves_exit_code(self):
        with patch.object(cli, "run_gradle", return_value=7) as run:
            code, _, _ = self.invoke(["gradle", "mod", "tasks", "--all", "--offline", "--stacktrace",
                                      "--info", "--rerun-tasks", "--java-home", "jdk", "--log", "new.log"])
        self.assertEqual(code, 7)
        run.assert_called_once_with(Path("mod"), ["tasks"], Path("jdk"),
                                    options=["--all", "--offline", "--stacktrace", "--info", "--rerun-tasks"],
                                    log_path=Path("new.log"))


if __name__ == "__main__":
    unittest.main()
