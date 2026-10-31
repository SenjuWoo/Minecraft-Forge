"""Regression checks for the release-hygiene gate."""

import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "check_hygiene", ROOT / "scripts" / "check_hygiene.py"
)
assert SPEC is not None and SPEC.loader is not None
check_hygiene = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check_hygiene)


class HygieneTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / "local/test-temp"
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_clean_source_passes(self):
        self.assertEqual(
            check_hygiene.scan([self.write("README.md", "NeoForge 1.21.1\n")], self.root),
            [],
        )

    def test_stale_account_and_placeholder_fail(self):
        stale = "Shugoki" + "Fable"
        placeholder = "0.0" + "NONE"
        problems = check_hygiene.scan(
            [self.write("README.md", f"{stale}\n{placeholder}\n")], self.root
        )
        self.assertEqual(len(problems), 2)

    def test_machine_path_and_token_fail(self):
        machine = "C:" + "\\Users\\example\\mod"
        token = "ghp_" + "a" * 36
        problems = check_hygiene.scan(
            [self.write("notes.md", f"{machine}\n{token}\n")], self.root
        )
        self.assertEqual(len(problems), 2)

    def test_binary_and_local_outputs_fail(self):
        binary = self.write("mod.jar", "")
        local = self.write("local/report.md", "ok")
        problems = check_hygiene.scan([binary, local], self.root)
        self.assertEqual(len(problems), 2)

    @unittest.skipUnless((ROOT / ".git").exists(), "source checkout only")
    def test_repository_source_passes(self):
        files = check_hygiene.tracked_files()
        self.assertEqual(check_hygiene.scan(files), [])


if __name__ == "__main__":
    unittest.main()
