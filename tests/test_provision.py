import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import stat
import struct
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from mcforge import provision
from mcforge.__main__ import main


class ProvisionTests(unittest.TestCase):
    def setUp(self):
        scratch = Path(__file__).resolve().parents[1] / "local" / "test-temp"
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.root = Path(self.temp.name)
        self.assertTrue(self.root.resolve().is_relative_to(scratch.resolve()))
        self.addCleanup(self.temp.cleanup)

    def archive(self, entries):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, data in entries:
                archive.writestr(name, data)
        path = self.root / "fixture.zip"
        path.write_bytes(stream.getvalue())
        return path

    def metadata(self, content=b"jdk bytes"):
        return [{"release_name": "jdk-21.0.9+10", "binary": {
            "architecture": "x64", "image_type": "jdk", "os": "windows", "jvm_impl": "hotspot",
            "package": {"link": "https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.9%2B10/OpenJDK21U-jdk_x64_windows_hotspot_21.0.9_10.zip", "checksum": hashlib.sha256(content).hexdigest(), "size": len(content)},
        }}]

    def test_extracts_safe_fixture_without_changing_bytes(self):
        archive = self.archive([("jdk-21/bin/java.exe", b"fixture java"), ("jdk-21/legal/LICENSE", b"fixture license")])
        stage = self.root / "stage"
        provision.extract_jdk(archive, stage)
        self.assertEqual((stage / "jdk-21/bin/java.exe").read_bytes(), b"fixture java")
        self.assertEqual((stage / "jdk-21/legal/LICENSE").read_bytes(), b"fixture license")

    def test_rejects_unsafe_paths_and_symlink_before_extracting(self):
        for filename in ("../outside.txt", "jdk/../../outside.txt", "/absolute.txt", "C:/drive.txt", "..\\outside.txt"):
            with self.subTest(filename=filename):
                archive = self.archive([("jdk/safe.txt", b"safe"), (filename, b"unsafe")])
                stage = self.root / "stage"
                with self.assertRaisesRegex(ValueError, "Unsafe JDK archive path"):
                    provision.extract_jdk(archive, stage)
                self.assertFalse(stage.exists())
                self.assertFalse((self.root / "outside.txt").exists())
        link = zipfile.ZipInfo("jdk/bin/link")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive = self.archive([(link, b"../../outside")])
        with self.assertRaisesRegex(ValueError, "Linked JDK archive entry"):
            provision.extract_jdk(archive, self.root / "stage")
        self.assertFalse((self.root / "stage").exists())

    def test_rejects_published_extraction_size_over_budget(self):
        archive = self.archive([("jdk/tiny.txt", b"tiny")])
        content = bytearray(archive.read_bytes())
        central = content.index(b"PK\x01\x02")
        # Advertise a huge entry in the central directory without allocating it.
        struct.pack_into("<I", content, central + 24, 1024 * 1024 * 1024 + 1)
        archive.write_bytes(content)
        with self.assertRaisesRegex(ValueError, "extraction budget"):
            provision.extract_jdk(archive, self.root / "stage")
        self.assertFalse((self.root / "stage").exists())

    def test_plan_preserves_official_identity_hash_and_has_no_writes(self):
        metadata = self.metadata()
        with patch.object(provision, "ROOT", self.root), patch.object(provision, "request", return_value=io.BytesIO(json.dumps(metadata).encode())) as request:
            plan = provision.java_plan()
        self.assertEqual(request.call_args.args, (provision.API,))
        self.assertEqual(plan["release"], metadata[0]["release_name"])
        self.assertEqual(plan["sha256"], hashlib.sha256(b"jdk bytes").hexdigest())
        self.assertEqual(plan["size_bytes"], len(b"jdk bytes"))
        self.assertEqual(plan["destination"], str(self.root / "local/tools/jdk21"))
        self.assertEqual(list(self.root.iterdir()), [])

    def test_plan_rejects_unofficial_urls_invalid_checksum_and_size(self):
        variants = [
            ("link", "http://github.com/adoptium/temurin21-binaries/releases/download/fake/jdk.zip"),
            ("link", "https://github.com.evil.invalid/adoptium/temurin21-binaries/releases/download/fake/jdk.zip"),
            ("link", "https://github.com/someone/temurin21-binaries/releases/download/fake/jdk.zip"),
            ("checksum", "bad hash"),
            ("size", 350 * 1024 * 1024 + 1),
            ("size", 0),
        ]
        for key, value in variants:
            with self.subTest(key=key, value=value):
                metadata = self.metadata()
                metadata[0]["binary"]["package"][key] = value
                with patch.object(provision, "request", return_value=io.BytesIO(json.dumps(metadata).encode())):
                    with self.assertRaises(ValueError):
                        provision.java_plan()

    @unittest.skipUnless(os.name == "nt" and platform.machine().lower() in ("amd64", "x86_64"), "Windows x64 setup provider")
    def test_setup_checks_download_hash_before_extracting(self):
        for checksum, size in (("0" * 64, 9), (hashlib.sha256(b"jdk bytes").hexdigest(), 8)):
            with self.subTest(checksum=checksum, size=size):
                metadata = self.metadata()
                metadata[0]["binary"]["package"].update(checksum=checksum, size=size)
                responses = [io.BytesIO(json.dumps(metadata).encode()), io.BytesIO(b"jdk bytes")]
                with patch.object(provision, "ROOT", self.root), patch.object(provision, "request", side_effect=responses), patch.object(provision, "check_java") as check:
                    with self.assertRaisesRegex(ValueError, "size|checksum"):
                        provision.setup_java()
                    check.assert_not_called()
                target = self.root / "local/tools/jdk21"
                self.assertFalse(target.exists())
                self.assertEqual(list(target.parent.iterdir()), [])

    @unittest.skipUnless(os.name == "nt" and platform.machine().lower() in ("amd64", "x86_64"), "Windows x64 setup provider")
    def test_setup_installs_only_validated_jdk21_and_retains_provenance(self):
        archive = self.archive([("jdk-21/bin/java.exe", b"fixture"), ("jdk-21/bin/javac.exe", b"fixture compiler")])
        content = archive.read_bytes()
        metadata = self.metadata(content)
        responses = [io.BytesIO(json.dumps(metadata).encode()), io.BytesIO(content)]
        runtime = {"major": 21, "jdk": True, "exit_code": 0}
        with patch.object(provision, "ROOT", self.root), patch.object(provision, "request", side_effect=responses), patch.object(provision, "check_java", return_value=runtime) as check:
            result = provision.setup_java()
        target = self.root / "local/tools/jdk21"
        self.assertEqual(result["installed"], str(target))
        self.assertEqual(check.call_count, 1)
        self.assertEqual((target / "bin/javac.exe").read_bytes(), b"fixture compiler")
        self.assertEqual(json.loads((target / "MCFORGE-PROVENANCE.json").read_text()), result["provenance"])
        self.assertEqual(result["provenance"]["sha256"], hashlib.sha256(content).hexdigest())

    @unittest.skipUnless(os.name == "nt" and platform.machine().lower() in ("amd64", "x86_64"), "Windows x64 setup provider")
    def test_cli_malformed_api_response_returns_json_failure(self):
        for content in (b"not json", b"[]", b"null", b'[{"binary":null}]'):
            with self.subTest(content=content):
                stderr = io.StringIO()
                with patch.object(provision, "request", return_value=io.BytesIO(content)), contextlib.redirect_stderr(stderr), contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(["setup-java", "--plan"]), 2)
                self.assertIn("error", json.loads(stderr.getvalue()))


if __name__ == "__main__":
    unittest.main()
