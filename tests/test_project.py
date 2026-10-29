"""Check project pins and update selection with actual files and bounded metadata fixtures."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

from mcforge import project
from mcforge.workbench import init_project


def metadata(*versions):
    return ("<metadata><versioning><versions>" + "".join(f"<version>{v}</version>" for v in versions)
            + "</versions></versioning></metadata>").encode()


class ProjectTests(unittest.TestCase):
    def setUp(self):
        base = Path(__file__).resolve().parents[1] / "local/test-temp"
        base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.mod = self.root / "mod"
        init_project(self.mod, "garden", "dev.example.garden", "Garden", with_tests=True)
        self.lock = self.mod / "mcforge-project.json"

    def write_lock(self, **changes):
        data = json.loads(self.lock.read_text())
        data.update(changes)
        self.lock.write_text(json.dumps(data), encoding="utf-8")

    def rewrite(self, name, before, after):
        path = self.mod / name
        text = path.read_text(encoding="utf-8")
        self.assertIn(before, text)
        path.write_text(text.replace(before, after), encoding="utf-8")

    def test_reads_actual_mdk_target_and_ignores_commented_examples(self):
        build = self.mod / "build.gradle"
        with build.open("a", encoding="utf-8") as stream:
            stream.write("\n// neoForge { version = '99.1.1' }\n/* java.toolchain.languageVersion = JavaLanguageVersion.of(99) */\n")
        target = project.read_target(self.mod)
        self.assertEqual({key: target[key] for key in ("minecraft", "neo_version", "java_major", "gradle", "moddev", "parchment_minecraft", "parchment_mappings")},
                         {"minecraft": "1.21.1", "neo_version": "21.1.265", "java_major": 21, "gradle": "9.2.1", "moddev": "2.0.148", "parchment_minecraft": "1.21.1", "parchment_mappings": "2024.11.17"})
        self.assertEqual(len(target["gradle_wrapper_sha256"]), 64)
        self.assertEqual(len(target["gradle_distribution_sha256"]), 64)
        self.assertTrue(target["gradle_distribution_url"].endswith("gradle-9.2.1-bin.zip"))

    def test_resolves_explicit_literals_and_plain_project_properties(self):
        properties = self.mod / "gradle.properties"
        with properties.open("a", encoding="utf-8") as stream:
            stream.write("\njava_version=21\nplugin_version=2.0.149\n")
        self.rewrite("build.gradle", "JavaLanguageVersion.of(21)", "JavaLanguageVersion.of(project.java_version)")
        self.rewrite("build.gradle", "version '2.0.148'", "version project.plugin_version")
        self.rewrite("build.gradle", "version = project.neo_version", 'version = "${neo_version}"')
        target = project.read_target(self.mod)
        self.assertEqual(target["java_major"], 21)
        self.assertEqual(target["moddev"], "2.0.149")
        self.assertEqual(target["neo_version"], "21.1.265")

    def test_new_complete_lock_is_accepted_without_mutation(self):
        target = project.read_target(self.mod)
        self.write_lock(target=target)
        before = {path.relative_to(self.mod).as_posix(): path.read_bytes() for path in self.mod.rglob("*") if path.is_file()}
        result = project.inspect_project(self.mod)
        self.assertEqual(result["lock_status"], "locked")
        self.assertEqual(result["drift"], [])
        self.assertEqual(result["errors"], [])
        self.assertEqual(before, {path.relative_to(self.mod).as_posix(): path.read_bytes() for path in self.mod.rglob("*") if path.is_file()})

    def test_legacy_lock_warns_and_still_checks_original_pins(self):
        lock = json.loads(self.lock.read_text())
        lock.pop("target", None)
        self.lock.write_text(json.dumps(lock))
        result = project.inspect_project(self.mod)
        self.assertEqual(result["lock_status"], "legacy")
        self.assertTrue(result["warnings"])
        self.assertEqual(result["errors"], [])
        self.rewrite("gradle.properties", "neo_version=21.1.265", "neo_version=21.1.266")
        result = project.inspect_project(self.mod)
        self.assertEqual(result["lock_status"], "drift")
        self.assertEqual(result["drift"][0], {"field": "neo_version", "locked": "21.1.265", "actual": "21.1.266"})

    def test_distribution_plugin_mappings_and_wrapper_changes_are_drift(self):
        target = project.read_target(self.mod)
        self.write_lock(target=target)
        self.rewrite("build.gradle", "version '2.0.148'", "version '2.0.149'")
        self.rewrite("gradle.properties", "parchment_mappings_version=2024.11.17", "parchment_mappings_version=2025.01.01")
        self.rewrite("gradle/wrapper/gradle-wrapper.properties", "gradle-9.2.1-bin.zip", "gradle-9.8.2-bin.zip")
        self.rewrite("gradle/wrapper/gradle-wrapper.properties", target["gradle_distribution_sha256"], "0" * 64)
        (self.mod / "gradle/wrapper/gradle-wrapper.jar").write_bytes(b"different wrapper")
        result = project.inspect_project(self.mod)
        fields = {row["field"] for row in result["drift"]}
        self.assertTrue({"moddev", "parchment_mappings", "gradle", "gradle_distribution_url", "gradle_distribution_sha256", "gradle_wrapper_sha256"}.issubset(fields))
        self.assertEqual(result["lock_status"], "drift")

    def test_duplicate_dynamic_and_missing_pins_fail_explicitly(self):
        properties = self.mod / "gradle.properties"
        original_properties = properties.read_text()
        properties.write_text(original_properties + "\nneo_version=21.1.265\n")
        self.assertIn("Duplicate", project.inspect_project(self.mod)["errors"][0])
        properties.write_text(original_properties)
        self.rewrite("build.gradle", "version '2.0.148'", "version '2.+'");
        self.assertIn("Cannot resolve", project.inspect_project(self.mod)["errors"][0])
        self.rewrite("build.gradle", "version '2.+'", "version '2.0.148'")
        self.rewrite("build.gradle", "version = project.neo_version", "version = chooseNeoForge()")
        result = project.inspect_project(self.mod)
        self.assertEqual(result["lock_status"], "unresolved")
        self.assertIn("Cannot resolve", result["errors"][0])
        (self.mod / "build.gradle").unlink()
        self.assertEqual(project.inspect_project(self.mod)["lock_status"], "unresolved")

    def test_missing_checksum_unsafe_url_and_unvalidated_target_are_not_ready(self):
        wrapper = self.mod / "gradle/wrapper/gradle-wrapper.properties"
        original = wrapper.read_text()
        wrapper.write_text("\n".join(line for line in original.splitlines() if not line.startswith("distributionSha256Sum=")))
        self.assertIn("SHA256", project.inspect_project(self.mod)["errors"][0])
        wrapper.write_text(original.replace("https\\://services.gradle.org", "https\\://user:private@services.gradle.org"))
        result = project.inspect_project(self.mod)
        self.assertIn("credential-free", result["errors"][0])
        self.assertNotIn("private", json.dumps(result))
        wrapper.write_text(original)
        self.rewrite("build.gradle", "JavaLanguageVersion.of(21)", "JavaLanguageVersion.of(25)")
        self.assertIn("outside the tested", project.inspect_project(self.mod)["errors"][0])

    def test_malformed_or_partial_lock_cannot_claim_full_pinning(self):
        self.write_lock(target={"minecraft": "1.21.1"})
        self.assertEqual(project.inspect_project(self.mod)["lock_status"], "drift")
        self.lock.write_text("[]")
        self.assertEqual(project.inspect_project(self.mod)["lock_status"], "unresolved")
        self.lock.write_text("not JSON")
        self.assertTrue(project.inspect_project(self.mod)["errors"])

    def update_metadata(self, url):
        if url == project.NEOFORGE_METADATA:
            return metadata("21.1.9", "21.1.265", "21.1.266", "21.1.999-beta", "21.2.1", "26.3.0.99")
        if url == project.MODDEV_METADATA:
            return metadata("2.0.9", "2.0.148", "2.0.149", "3.0.0-beta")
        if url == project.GRADLE_CURRENT:
            return json.dumps({"version": "9.8.2", "snapshot": False}).encode()
        return metadata("2024.11.17", "2025.01.01", "2026.01.01-SNAPSHOT")

    def test_update_candidates_use_numeric_stable_versions_and_separate_ports(self):
        before = self.lock.read_bytes()
        with patch.object(project, "_fetch", side_effect=self.update_metadata):
            result = project.check_updates(self.mod)
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["candidates"]["neo_version"]["latest"], "21.1.266")
        self.assertEqual(result["candidates"]["moddev"]["latest"], "2.0.149")
        self.assertEqual(result["candidates"]["parchment_mappings"]["latest"], "2025.01.01")
        self.assertEqual(result["candidates"]["gradle"]["latest"], "9.8.2")
        self.assertTrue(all(row["update_available"] for row in result["candidates"].values()))
        self.assertEqual(result["ports"][0]["neo_version"], "26.3.0.99")
        self.assertTrue(all(not row["neo_version"].startswith("21.1.") for row in result["ports"]))
        self.assertEqual(self.lock.read_bytes(), before)

    def test_network_failure_is_unknown_and_other_components_still_report(self):
        def fetch(url):
            if url == project.MODDEV_METADATA:
                raise urllib.error.URLError("fixture network unavailable")
            return self.update_metadata(url)
        with patch.object(project, "_fetch", side_effect=fetch):
            result = project.check_updates(self.mod)
        self.assertEqual(len(result["errors"]), 1)
        self.assertNotIn("moddev", result["candidates"])
        self.assertIn("neo_version", result["candidates"])
        self.assertIn("metadata unavailable", result["errors"][0])

    def test_malformed_and_empty_metadata_do_not_report_current_as_latest(self):
        for body in (b"not XML", metadata("21.1.1-beta"), b'<!DOCTYPE metadata [<!ENTITY x "bad">]><metadata/>'):
            with self.subTest(body=body):
                with patch.object(project, "_fetch", return_value=body):
                    result = project.check_updates(self.mod)
                self.assertTrue(result["errors"])
                self.assertEqual(result["candidates"], {})

    def test_metadata_download_limits_and_https_redirects(self):
        response = io.BytesIO(b"x" * (project.MAX_TEXT + 1))
        response.geturl = lambda: project.NEOFORGE_METADATA
        with patch.object(project.urllib.request, "urlopen", return_value=response):
            with self.assertRaisesRegex(ValueError, "limit"):
                project._fetch(project.NEOFORGE_METADATA)
        response = io.BytesIO(b"<metadata/>")
        response.geturl = lambda: "http://example.invalid/metadata"
        with patch.object(project.urllib.request, "urlopen", return_value=response):
            with self.assertRaisesRegex(ValueError, "HTTPS"):
                project._fetch(project.NEOFORGE_METADATA)


if __name__ == "__main__":
    unittest.main()
