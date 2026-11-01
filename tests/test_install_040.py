"""Check the versionless local install, backup and no-overwrite behavior."""
from pathlib import Path
import tempfile
import unittest

from mcforge import install
from mcforge.workbench import ROOT


class InstallTests(unittest.TestCase):
    def setUp(self):
        base = Path(__file__).resolve().parents[1] / "local/test-temp"
        base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "install"

    def test_install_copies_product_and_writes_launcher(self):
        result = install.install_toolkit(self.root)
        self.assertEqual(result["root"], str(self.root.resolve()))
        self.assertTrue((self.root / "mcforge/__init__.py").is_file())
        self.assertTrue((self.root / "docs/ASSETS.md").is_file())
        self.assertTrue((self.root / "vendor/neoforge-1.21.1-mdk.zip").is_file())
        self.assertTrue(install.launcher_path(self.root).is_file())
        self.assertFalse((self.root / "local").exists())
        self.assertFalse((self.root / "dist").exists())
        self.assertFalse((self.root / "STATE.md").exists())
        self.assertGreater(result["files"], 40)

    def test_existing_install_requires_force_and_keeps_backup(self):
        install.install_toolkit(self.root)
        with self.assertRaises(ValueError):
            install.install_toolkit(self.root)
        result = install.install_toolkit(self.root, force=True)
        self.assertIsNotNone(result["backup"])
        self.assertTrue(Path(result["backup"]).is_dir())
        self.assertTrue((self.root / "mcforge/__init__.py").is_file())

    def test_source_root_is_rejected(self):
        with self.assertRaises(ValueError):
            install.install_toolkit(ROOT.resolve())


if __name__ == "__main__":
    unittest.main()
