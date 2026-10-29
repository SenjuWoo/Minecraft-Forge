"""Source discovery uses only matching prepared project artifacts, never shared caches."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from mcforge import workbench
from mcforge.sources import resolve_sources


class SourcesTests(unittest.TestCase):
    def setUp(self):
        scratch = Path(__file__).resolve().parents[1] / "local/test-temp"
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / "project"
        workbench.init_project(self.project, "sourceprobe", "dev.mcforge.sourceprobe", "Source Probe")
        self.artifacts = self.project / "build/moddev/artifacts"
        self.artifacts.mkdir(parents=True)

    def archive(self, name, *, java=True):
        path = self.artifacts / name
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("dev/Probe.java" if java else "dev/Probe.class", "package dev; class Probe {}")
        return path

    def test_prefers_exact_sources_and_returns_project_target(self):
        source = self.archive("neoforge-21.1.265-sources.jar")
        self.archive("neoforge-21.1.265-merged.jar")
        self.archive("neoforge-21.1.999-sources.jar")
        result = resolve_sources(self.project)
        self.assertEqual(result["source"], str(source.resolve()))
        self.assertEqual(result["project"], str(self.project.resolve()))
        self.assertEqual(result["kind"], "neoforge")
        self.assertEqual(result["target"]["neo_version"], "21.1.265")

    def test_matching_merged_sources_are_supported_when_sources_jar_is_absent(self):
        source = self.archive("neoforge-21.1.265-merged.jar")
        result = resolve_sources(self.project)
        self.assertEqual(result["source"], str(source.resolve()))
        self.assertEqual(result["kind"], "merged")

    def test_missing_or_wrong_version_never_selects_another_artifact(self):
        self.archive("neoforge-21.1.264-sources.jar")
        self.archive("neoforge-21.1.265.jar", java=False)
        with self.assertRaisesRegex(ValueError, "No prepared sources.*21.1.265.*createMinecraftArtifacts"):
            resolve_sources(self.project)
        self.assertEqual(len(list(self.artifacts.iterdir())), 2)

    def test_invalid_preferred_archive_does_not_silently_use_merged(self):
        source = self.archive("neoforge-21.1.265-sources.jar", java=False)
        self.archive("neoforge-21.1.265-merged.jar")
        with self.assertRaisesRegex(ValueError, "no inspectable Java"):
            resolve_sources(self.project)
        source.write_bytes(b"not a zip")
        with self.assertRaisesRegex(ValueError, "artifact is invalid"):
            resolve_sources(self.project)

    def test_archive_and_entry_limits_are_enforced(self):
        self.archive("neoforge-21.1.265-sources.jar")
        with patch("mcforge.sources.MAX_ARCHIVE_BYTES", 1):
            with self.assertRaisesRegex(ValueError, "512 MiB"):
                resolve_sources(self.project)
        with patch("mcforge.sources.MAX_ARCHIVE_ENTRIES", 0):
            with self.assertRaisesRegex(ValueError, "too many entries"):
                resolve_sources(self.project)
        with patch("mcforge.sources.MAX_METADATA_BYTES", 1):
            with self.assertRaisesRegex(ValueError, "no inspectable Java"):
                resolve_sources(self.project)

    @unittest.skipIf(os.name == "nt", "Windows filenames cannot differ only by case")
    def test_case_equivalent_source_candidates_are_ambiguous(self):
        self.archive("neoforge-21.1.265-sources.jar")
        self.archive("NeoForge-21.1.265-sources.jar")
        with self.assertRaisesRegex(ValueError, "Ambiguous"):
            resolve_sources(self.project)


if __name__ == "__main__":
    unittest.main()
