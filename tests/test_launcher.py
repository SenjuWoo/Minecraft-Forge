"""The PowerShell launcher, started the way a user or an agent starts it."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def hosts():
    return [path for path in (shutil.which("powershell.exe"), shutil.which("pwsh")) if path]


@unittest.skipUnless(os.name == "nt" and hosts(), "PowerShell launcher is Windows-only")
class LauncherTests(unittest.TestCase):
    def run_launcher(self, host, script, *arguments):
        return subprocess.run([host, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(script), *arguments],
                              capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)

    def test_real_launcher_reports_the_package_version(self):
        from mcforge import __version__

        for host in hosts():
            with self.subTest(host=Path(host).name):
                done = self.run_launcher(host, ROOT / "Minecraft-Forge.ps1", "--version")
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                self.assertIn(__version__, done.stdout)

    def test_arguments_and_exit_code_survive_an_awkward_folder(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td).resolve() / "!mc tools (x)"
            package = home / "mcforge"
            package.mkdir(parents=True)
            shutil.copyfile(ROOT / "Minecraft-Forge.ps1", home / "Minecraft-Forge.ps1")
            (package / "__init__.py").write_text("", encoding="utf-8")
            (package / "__main__.py").write_text(
                "import json, os, sys\n"
                "print(json.dumps({'home': os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'args': sys.argv[1:]}))\n"
                "sys.exit(7)\n", encoding="utf-8")
            arguments = ["init", str(home / "My Mod (1)"), "--name", 'say "hi"', "--flag"]
            for host in hosts():
                with self.subTest(host=Path(host).name):
                    done = self.run_launcher(host, home / "Minecraft-Forge.ps1", *arguments)
                    self.assertEqual(done.returncode, 7, done.stdout + done.stderr)
                    seen = json.loads(done.stdout.strip().splitlines()[-1])
                    self.assertTrue(os.path.samefile(seen["home"], home))
                    self.assertEqual(seen["args"][:2], arguments[:2])
                    self.assertEqual(seen["args"][-1], "--flag")

    def test_the_callers_pythonpath_is_restored(self):
        script = (ROOT / "Minecraft-Forge.ps1").read_text(encoding="utf-8")
        self.assertIn("-P -m mcforge @args", script)
        self.assertNotIn("run_module(", script, "an inline -c program loses its quotes under Windows PowerShell 5.1")
        self.assertIn("$env:PYTHONPATH = $previousPath", script)


if __name__ == "__main__":
    unittest.main()
