import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import struct
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from mcforge import __version__
from mcforge.__main__ import emit, main, search_sources
from mcforge import workbench


class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        scratch = Path(__file__).resolve().parents[1] / "local" / "test-temp"
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.root = Path(self.temp.name)
        self.assertTrue(self.root.resolve().is_relative_to(scratch.resolve()))
        self.addCleanup(self.temp.cleanup)

    def test_vendor_bytes_wrapper_and_license_are_pinned(self):
        manifest = workbench.verify_vendor()
        archive_path = workbench.ROOT / "vendor" / manifest["archive"]
        self.assertEqual(hashlib.sha256(archive_path.read_bytes()).hexdigest(), manifest["sha256"])
        with zipfile.ZipFile(archive_path) as archive:
            wrapper = next(name for name in archive.namelist() if name.endswith("gradle/wrapper/gradle-wrapper.jar"))
            self.assertEqual(hashlib.sha256(archive.read(wrapper)).hexdigest(), manifest["gradle_wrapper_sha256"])
            for license_name in manifest["licenses"]:
                license_path = next(name for name in archive.namelist() if name.endswith("/" + license_name))
                self.assertIn(b"Permission is hereby granted", archive.read(license_path))

    def test_init_transforms_namespace_and_preserves_binary_and_license(self):
        destination = self.root / "Garden Mod"
        result = workbench.init_project(destination, "garden_mod", "dev.woo.garden", "Garden Mod", "21.1.265")
        self.assertEqual(result["lock"]["toolkit_version"], __version__)
        self.assertEqual(result["lock"]["minecraft"], "1.21.1")
        self.assertEqual(result["lock"]["java_major"], 21)
        self.assertEqual(result["lock"]["mod_id"], "garden_mod")
        self.assertEqual(json.loads((destination / "mcforge-project.json").read_text()), result["lock"])
        java = list((destination / "src/main/java/dev/woo/garden").glob("*.java"))
        self.assertTrue(java)
        for path in java:
            self.assertIn("package dev.woo.garden;", path.read_text())
            self.assertNotIn("com.example.examplemod", path.read_text())
        self.assertFalse((destination / "src/main/java/com").exists())
        self.assertTrue((destination / "src/main/resources/assets/garden_mod").is_dir())
        self.assertFalse((destination / "src/main/resources/assets/examplemod").exists())
        properties = dict(line.split("=", 1) for line in (destination / "gradle.properties").read_text().splitlines() if "=" in line and not line.startswith("#"))
        self.assertEqual({key: properties[key] for key in ("mod_id", "mod_group_id", "mod_name", "neo_version", "org.gradle.daemon")}, {
            "mod_id": "garden_mod", "mod_group_id": "dev.woo.garden", "mod_name": "Garden Mod", "neo_version": "21.1.265", "org.gradle.daemon": "false",
        })
        self.assertNotIn("foojay", (destination / "settings.gradle").read_text())
        self.assertFalse((destination / ".github").exists())
        manifest = workbench.verify_vendor()
        wrapper_properties = (destination / "gradle/wrapper/gradle-wrapper.properties").read_text()
        self.assertEqual(wrapper_properties.count("distributionSha256Sum="), 1)
        self.assertIn("distributionSha256Sum=" + manifest["gradle_distribution_sha256"], wrapper_properties)
        self.assertIn("gradle-" + manifest["gradle"] + "-bin.zip", wrapper_properties)
        self.assertEqual(hashlib.sha256((destination / "gradle/wrapper/gradle-wrapper.jar").read_bytes()).hexdigest(), manifest["gradle_wrapper_sha256"])
        with zipfile.ZipFile(workbench.ROOT / "vendor" / manifest["archive"]) as archive:
            for license_name in manifest["licenses"]:
                source = next(name for name in archive.namelist() if name.endswith("/" + license_name))
                self.assertEqual((destination / license_name).read_bytes(), archive.read(source))

    def test_init_never_overwrites_existing_data_or_leaves_invalid_projects(self):
        existing = self.root / "existing"
        existing.mkdir()
        marker = existing / "keep.txt"
        marker.write_bytes(b"personal edit")
        with self.assertRaisesRegex(ValueError, "never overwritten"):
            workbench.init_project(existing, "garden", "dev.woo.garden", "Garden")
        self.assertEqual(marker.read_bytes(), b"personal edit")
        baseline = sorted(path.name for path in self.root.iterdir())
        invalid = [
            ("Bad-ID", "dev.woo.garden", "Garden", "21.1.265"),
            ("garden", "dev.class.garden", "Garden", "21.1.265"),
            ("garden", "garden", "Garden", "21.1.265"),
            ("garden", "dev.woo.garden", "Garden\nInjected", "21.1.265"),
            ("garden", "dev.woo.garden", "Garden", "21.2.1"),
        ]
        for mod_id, package, name, neo_version in invalid:
            with self.subTest(mod_id=mod_id, package=package, name=name, neo_version=neo_version):
                with self.assertRaises(ValueError):
                    workbench.init_project(self.root / "invalid", mod_id, package, name, neo_version)
                self.assertEqual(sorted(path.name for path in self.root.iterdir()), baseline)

    def test_outputs_cannot_enter_launcher_or_moved_instance(self):
        with self.assertRaisesRegex(ValueError, "read-only"):
            workbench.guard_output(workbench.default_launcher() / "instances" / "NeverCreated" / "report.json")
        moved = self.root / "moved-instance"
        moved.mkdir()
        (moved / "instance.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "read-only"):
            workbench.guard_output(moved / "mods" / "new-mod")
        workbench.guard_output(self.root / "owned-development")

    def test_vendor_corruption_fails_before_creating_project(self):
        vendor = self.root / "vendor"
        vendor.mkdir()
        manifest = workbench.verify_vendor()
        (vendor / "manifest.json").write_text(json.dumps(manifest))
        (vendor / manifest["archive"]).write_bytes(b"corrupted template")
        with patch.object(workbench, "ROOT", self.root):
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                workbench.init_project(self.root / "project", "garden", "dev.woo.garden", "Garden")
        self.assertFalse((self.root / "project").exists())

    def test_unsafe_template_entry_rolls_back_staging(self):
        vendor = self.root / "vendor"
        vendor.mkdir()
        manifest = dict(workbench.verify_vendor())
        archive_path = vendor / manifest["archive"]
        with zipfile.ZipFile(archive_path, "w") as archive:
            archive.writestr("template/../escaped.txt", "must never be extracted")
        manifest["sha256"] = hashlib.sha256(archive_path.read_bytes()).hexdigest()
        (vendor / "manifest.json").write_text(json.dumps(manifest))
        with patch.object(workbench, "ROOT", self.root):
            with self.assertRaisesRegex(ValueError, "Unsafe template"):
                workbench.init_project(self.root / "project", "garden", "dev.woo.garden", "Garden")
        self.assertEqual([path.name for path in self.root.iterdir()], ["vendor"])

    def test_explicit_java_requires_matching_jdk_and_does_not_fall_through(self):
        java_home = self.root / "fake-jdk"
        (java_home / "bin").mkdir(parents=True)
        suffix = ".exe" if os.name == "nt" else ""
        (java_home / "bin" / ("java" + suffix)).touch()
        compiler = java_home / "bin" / ("javac" + suffix)
        compiler.touch()
        completed = subprocess.CompletedProcess([], 0, stdout="", stderr='openjdk version "21.0.7"\n')
        with patch("mcforge.workbench.subprocess.run", return_value=completed) as run:
            self.assertEqual(workbench.select_java(java_home), java_home.resolve())
            self.assertEqual(run.call_args.args[0], [str(java_home.resolve() / "bin" / ("java" + suffix)), "-version"])
        wrong = subprocess.CompletedProcess([], 0, stdout="", stderr='openjdk version "25.0.1"\n')
        with patch("mcforge.workbench.subprocess.run", return_value=wrong) as run:
            with self.assertRaisesRegex(ValueError, "JDK 21"):
                workbench.select_java(java_home)
            self.assertEqual(run.call_count, 1)
        compiler.unlink()
        with patch("mcforge.workbench.subprocess.run", return_value=completed):
            with self.assertRaisesRegex(ValueError, "javac"):
                workbench.select_java(java_home)

    def test_source_jar_search_is_literal_bounded_and_reports_line_numbers(self):
        sources = self.root / "sources.jar"
        with zipfile.ZipFile(sources, "w") as archive:
            archive.writestr("dev/Example.java", "package dev;\nString value = \"a.*\";\nString other = \"abc\";\n")
            archive.writestr("ignored.txt", "a.*")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(search_sources(sources, "a.*"), 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result["matches"], [{"file": "dev/Example.java", "line": 2, "text": 'String value = "a.*";'}])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(search_sources(sources, "does not occur"), 1)
        with zipfile.ZipFile(sources, "w") as archive:
            archive.writestr("dev/Many.java", "hit\n" * 70)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            search_sources(sources, "hit")
        self.assertEqual(len(json.loads(output.getvalue())["matches"]), 50)

    def test_cli_failures_return_json_and_report_files_are_exclusive(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), contextlib.redirect_stdout(io.StringIO()):
            code = main(["init", str(self.root / "invalid"), "--mod-id", "INVALID", "--package", "dev.woo.garden", "--name", "Garden"])
        self.assertEqual(code, 2)
        self.assertIn("mod-id", json.loads(stderr.getvalue())["error"])
        self.assertFalse((self.root / "invalid").exists())
        malformed = self.root / "bad.jar"
        malformed.write_bytes(b"not a zip")
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["sources", str(malformed), "query"]), 2)
        self.assertIn("error", json.loads(stderr.getvalue()))
        report = self.root / "report.json"
        with contextlib.redirect_stdout(io.StringIO()):
            emit({"first": True}, report)
        with self.assertRaises(FileExistsError):
            emit({"second": True}, report)
        self.assertEqual(json.loads(report.read_text()), {"first": True})

    def test_cli_reports_corrupt_compressed_source_archive(self):
        archive_path = self.root / "corrupt-compression.jar"
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("Broken.java", "public class Broken {}\n" * 20)
        raw = bytearray(archive_path.read_bytes())
        name_length, extra_length = struct.unpack_from("<HH", raw, 26)
        offset = 30 + name_length + extra_length
        raw[offset:offset + 3] = b"\xff\xff\xff"
        archive_path.write_bytes(raw)
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["sources", str(archive_path), "class"]), 2)
        self.assertIn("error", json.loads(stderr.getvalue()))

    @unittest.skipUnless(shutil.which("rg"), "directory source search requires installed ripgrep")
    def test_directory_sources_bound_results_and_reap_real_ripgrep(self):
        sources = self.root / "sources"
        sources.mkdir()
        for number in range(20):
            (sources / f"Example{number}.java").write_text('String value = "a.*";\n' * 10)
        (sources / "ignore.txt").write_text("a.*\n" * 100)
        processes = []
        real_popen = subprocess.Popen

        def observe_process(*args, **kwargs):
            process = real_popen(*args, **kwargs)
            processes.append(process)
            return process

        output = io.StringIO()
        with patch("mcforge.__main__.subprocess.Popen", side_effect=observe_process), contextlib.redirect_stdout(output):
            self.assertEqual(search_sources(sources, "a.*"), 0)
        lines = output.getvalue().splitlines()
        self.assertEqual(len(lines), 50)
        self.assertTrue(all('.java:' in line and line.endswith('String value = "a.*";') for line in lines))
        self.assertEqual(len(processes), 1)
        self.assertIsNotNone(processes[0].poll())
        self.assertTrue(processes[0].stdout.closed)
        output = io.StringIO()
        with patch("mcforge.__main__.subprocess.Popen", side_effect=observe_process), contextlib.redirect_stdout(output):
            self.assertEqual(search_sources(sources, "no such literal"), 1)
        self.assertEqual(output.getvalue(), "")
        self.assertEqual(len(processes), 2)
        self.assertTrue(all(process.poll() is not None and process.stdout.closed for process in processes))

    def test_doctor_honors_explicit_bad_java_home_without_fallback(self):
        missing = self.root / "missing-jdk"
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(["doctor", "--java-home", str(missing)]), 1)
        result = json.loads(output.getvalue())
        self.assertFalse(result["ready"])
        self.assertEqual(len(result["java"]), 1)
        self.assertEqual(result["java"][0]["home"], str(missing.resolve()))
        self.assertEqual(result["java"][0]["error"], "java executable missing")
        self.assertTrue(result["missing"])
        self.assertFalse(missing.exists())


if __name__ == "__main__":
    unittest.main()
