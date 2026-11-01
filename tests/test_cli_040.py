"""Dispatch compatibility for the 0.4.0 asset, quickstart and install commands."""
import contextlib
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from mcforge import __main__ as cli


class Cli040Tests(unittest.TestCase):
    def invoke(self, arguments):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = cli.main(arguments)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_asset_parses_repeated_ids_and_options(self):
        result = {"generated": []}
        with patch("mcforge.assets.generate_assets", return_value=result) as generate:
            code, output, _ = self.invoke(["asset", "mod", "--id", "ruby_block:block", "--id", "ruby:item",
                                           "--style", "gem", "--size", "32", "--force"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output), result)
        generate.assert_called_once_with(Path("mod"), [("ruby_block", "block"), ("ruby", "item")],
                                         style="gem", size=32, force=True)

    def test_asset_rejects_malformed_id(self):
        code, _, error = self.invoke(["asset", "mod", "--id", "ruby"])
        self.assertEqual(code, 2)
        self.assertIn("ID:KIND", json.loads(error)["error"])

    def test_quickstart_forwards_tests_and_style(self):
        result = {"project": "mod"}
        with patch.object(cli, "quickstart_project", return_value=result) as quick:
            code, output, _ = self.invoke(["quickstart", "mod", "--mod-id", "garden", "--package", "dev.example.garden",
                                           "--name", "Garden", "--no-tests", "--style", "gem", "--size", "32"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output), result)
        quick.assert_called_once_with(Path("mod"), "garden", "dev.example.garden", "Garden", "21.1.265",
                                      with_tests=False, style="gem", size=32)

    def test_install_forwards_root_and_force(self):
        with patch("mcforge.install.install_toolkit", return_value={"root": "target"}) as installer:
            code, output, _ = self.invoke(["install", "--root", "target", "--force"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output)["root"], "target")
        installer.assert_called_once_with(Path("target"), True)


if __name__ == "__main__":
    unittest.main()
