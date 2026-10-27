import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from mcforge.inventory import discover_instances, inspect_jar, inventory


class InventoryTests(unittest.TestCase):
    def setUp(self):
        scratch = Path(__file__).resolve().parents[1] / "local" / "test-temp"
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.assertTrue(self.root.resolve().is_relative_to(scratch.resolve()))

    def jar(self, name, entries):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            for entry, content in entries.items():
                archive.writestr(entry, content)
        return path

    def metadata(self, mod_id="example", version="1.0"):
        return f'[[mods]]\nmodId = "{mod_id}"\nversion = "{version}"\n'

    def test_neoforge_manifest_dependencies_and_nested(self):
        metadata = self.metadata(version="${file.jarVersion}") + '\n[[dependencies.example]]\nmodId="neoforge"\ntype="required"\nversionRange="[21.1,)"\nside="BOTH"\n'
        path = self.jar("example.jar", {
            "META-INF/neoforge.mods.toml": metadata,
            "META-INF/mods.toml": self.metadata(),
            "fabric.mod.json": json.dumps({"id": "example", "version": "1.0"}),
            "META-INF/MANIFEST.MF": "Manifest-Version: 1.0\r\nImplementation-Version: 1.2.\r\n 3\r\n\r\n",
            "META-INF/jarjar/metadata.json": json.dumps({"jars": [{"path": "META-INF/jarjar/lib.jar", "identifier": {"group": "a", "artifact": "b"}, "version": {"range": "[1,)", "artifactVersion": "1"}}]}),
        })
        result = inspect_jar(path, True)
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["mods"][0]["version"], "1.2.3")
        self.assertEqual(len(result["mods"]), 1)
        self.assertFalse(result["foreign_fabric_only"])
        self.assertEqual(result["dependencies"][0]["version_range"], "[21.1,)")
        self.assertEqual(result["nested_jars"][0]["identifier"]["artifact"], "b")
        self.assertEqual(len(result["sha256"]), 64)

    def test_fabric_only_and_malformed_are_reported(self):
        path = self.jar("fabric.jar", {"fabric.mod.json": json.dumps({"id": "fabricmod", "version": "1", "environment": "client", "depends": {"minecraft": ["1.21.1"]}})})
        result = inspect_jar(path)
        self.assertTrue(result["foreign_fabric_only"])
        self.assertEqual(result["mods"][0]["side"], "client")
        self.assertEqual(result["dependencies"][0]["version_range"], ["1.21.1"])
        malformed = self.jar("bad.jar", {"META-INF/neoforge.mods.toml": "[[broken", "META-INF/jarjar/metadata.json": "[]"})
        self.assertEqual(len(inspect_jar(malformed)["errors"]), 2)
        plain = self.root / "plain.jar"
        plain.write_bytes(b"not a zip")
        self.assertTrue(inspect_jar(plain)["errors"])

    def test_limits_apply_to_metadata_and_whole_archives(self):
        path = self.jar("large.jar", {"fabric.mod.json": "x" * 100})
        with patch("mcforge.inventory.MAX_METADATA_BYTES", 50):
            self.assertTrue(inspect_jar(path)["errors"])
        with patch("mcforge.inventory.MAX_ARCHIVE_BYTES", 1):
            self.assertTrue(inspect_jar(path)["errors"])

    def test_launcher_schema_duplicate_ids_and_disabled(self):
        instance = self.root / "instances" / "Pack"
        instance.mkdir(parents=True)
        (instance / "instance.json").write_text(json.dumps({"id": "1.21.1", "javaVersion": {"majorVersion": 21}, "launcher": {"name": "Display name", "version": "1.21.1", "loaderVersion": {"type": "NeoForge", "version": "21.1.265"}}}))
        self.jar("instances/Pack/mods/a.jar", {"META-INF/neoforge.mods.toml": self.metadata()})
        self.jar("instances/Pack/mods/b.jar", {"META-INF/neoforge.mods.toml": self.metadata()})
        self.jar("instances/Pack/mods/invalid.jar", {"fabric.mod.json": "{"})
        (instance / "disabledmods").mkdir()
        (instance / "disabledmods" / "off.jar").touch()
        (instance / "mods" / "another.jar.disabled").touch()
        crashes = instance / "crash-reports"
        crashes.mkdir()
        (crashes / "crash.txt").write_text("Description: Unexpected error\njava.lang.VerifyError: Bad type on operand stack\nprivate user log omitted")
        result = inventory(instance)
        self.assertEqual(result["name"], "Display name")
        self.assertEqual(result["loader"], {"type": "NeoForge", "version": "21.1.265"})
        self.assertEqual(result["java_major"], 21)
        self.assertEqual(len(result["enabled"]), 3)
        self.assertEqual(result["duplicates"], [{"mod_id": "example", "files": ["a.jar", "b.jar"]}])
        self.assertEqual(set(result["disabled"]), {"off.jar", "another.jar.disabled"})
        self.assertEqual(result["crashes"][0]["exception"], "java.lang.VerifyError: Bad type on operand stack")
        self.assertNotIn("private user", json.dumps(result["crashes"]))
        self.assertEqual(discover_instances(self.root)[0]["name"], "Display name")


if __name__ == "__main__":
    unittest.main()
