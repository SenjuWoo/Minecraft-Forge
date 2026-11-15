"""1.3.1 audit fixes: installed launcher cwd, error contract, search loader, pack archive name, target facts, guards."""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
import zipfile

from mcforge import __main__ as cli
from mcforge import content, geckopose, install, launchers, packs, pixelart, targets, voxel
from mcforge.assets import generate_assets
from tests.test_v100 import ALL_TARGETS, ROOT, Temp


class InstalledLauncherTests(Temp):
    def test_relative_paths_resolve_against_the_callers_folder(self):
        root = self.root / "install"
        install.install_toolkit(root)
        work = self.root / "caller dir"
        work.mkdir()
        launcher = install.launcher_path(root)
        command = ["cmd", "/c", str(launcher)] if os.name == "nt" else [str(launcher)]
        # A folder named mcforge beside the caller must not shadow the installed package.
        (work / "mcforge").mkdir()
        done = subprocess.run(command + ["pack", "relpack", "--kind", "data", "--name", "Rel"], cwd=work, capture_output=True,
                              text=True, env=os.environ | {"UABS_PYTHON": sys.executable})
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertTrue((work / "relpack/pack.mcmeta").is_file(), "the pack belongs in the caller's folder")
        self.assertFalse((root / "relpack").exists(), "nothing may be written into the install root")
        self.assertEqual(Path(json.loads(done.stdout)["pack"]), (work / "relpack").resolve())

    def test_install_reports_the_backups_it_left_behind(self):
        root = self.root / "install"
        install.install_toolkit(root)
        first = install.install_toolkit(root, force=True)
        second = install.install_toolkit(root, force=True)
        self.assertEqual(sorted(second["backups"]), sorted([first["backup"], second["backup"]]))


class ErrorContractTests(Temp):
    def test_corrupt_png_is_a_json_error_with_exit_2(self):
        bad = self.root / "bad.png"
        bad.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\x02IHDRxx")
        code, output, error = self.invoke(["preview", str(self.root), str(bad), "--output", str(self.root / "out.png")])
        self.assertEqual(code, 2)
        self.assertEqual(output, "")
        self.assertIn("PNG", json.loads(error)["error"])
        with self.assertRaisesRegex(ValueError, "truncated or corrupt"):
            pixelart.read_png(pixelart.png_bytes(pixelart.blank(4, 4))[:40])

    def test_missing_lock_key_names_the_key(self):
        project = self.root / "mod"
        project.mkdir()
        (project / "mcforge-project.json").write_text("{}", encoding="utf-8")
        code, _, error = self.invoke(["audio-check", str(project)])
        self.assertEqual(code, 2)
        self.assertRegex(json.loads(error)["error"], r"[Mm]issing .*mod_id")

    def test_unexpected_index_error_keeps_the_contract(self):
        with patch("mcforge.plan.plan", side_effect=IndexError("list index out of range")):
            code, output, error = self.invoke(["plan", "anything"])
        self.assertEqual((code, output), (2, ""))
        self.assertIn("IndexError", json.loads(error)["error"])

    def test_keyframes_at_the_same_time_do_not_compare_values(self):
        self.assertEqual(geckopose.sample({"0": {"post": [0, 0, 0]}, "0.0": {"post": [2, 2, 2]}, "1": [4, 4, 4]}, 0.5), (3.0, 3.0, 3.0))


class SearchTests(Temp):
    def search(self, *arguments):
        seen = {}

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def read(self, _):
                return b'{"hits": []}'

        def opened(request, timeout):
            seen["url"] = request.full_url
            return Response()

        with patch("urllib.request.urlopen", side_effect=opened):
            code, output, _ = self.invoke(["search", "boar", *arguments])
        self.assertEqual(code, 0)
        return seen["url"], json.loads(output)

    def test_search_filters_by_the_requested_loader(self):
        url, _ = self.search("--loader", "fabric", "--minecraft", "1.20.1")
        self.assertIn("categories%3Afabric", url)
        self.assertNotIn("neoforge", url)
        self.assertIn("versions%3A1.20.1", url)

    def test_search_default_stays_neoforge_1_21_1(self):
        url, result = self.search()
        self.assertIn("categories%3Aneoforge", url)
        self.assertEqual(result["loader"], "neoforge")


class PackArchiveTests(Temp):
    def test_zip_keeps_a_dotted_folder_name(self):
        result = packs.create_pack(self.root / "My.Pack", "data", "My.Pack", "1.21.1", archive=True)
        self.assertEqual(Path(result["zip"]).name, "My.Pack.zip")
        self.assertTrue((self.root / "My.Pack.zip").is_file())

    def test_existing_zip_is_refused_before_anything_is_written(self):
        (self.root / "Pack.zip").write_bytes(b"keep")
        with self.assertRaisesRegex(ValueError, "exists"):
            packs.create_pack(self.root / "Pack", "data", "Pack", "1.21.1", archive=True)
        self.assertFalse((self.root / "Pack").exists())
        self.assertEqual((self.root / "Pack.zip").read_bytes(), b"keep")


class TargetFactTests(Temp):
    def test_every_bundled_target_states_the_loader_version_its_template_builds(self):
        registry = targets.load_targets()["targets"]
        self.assertEqual(sorted(registry), sorted(ALL_TARGETS))
        for name in ALL_TARGETS:
            with self.subTest(target=name):
                self.assertRegex(registry[name].get("loader_version") or "", r"^\d+(\.\d+)+$")
                project = self.make(name, "probe" + name.split("-")[0])
                lock = json.loads((project / "mcforge-project.json").read_text(encoding="utf-8"))
                actual = lock["target"].get("neo_version") or lock["target"].get("forge_version") or lock["target"].get("loader_version")
                self.assertEqual(registry[name]["loader_version"], actual)

    def test_every_bundled_template_is_hash_checked(self):
        self.assertEqual(sorted(targets.verify_all_templates()), sorted(ALL_TARGETS))
        with patch.object(targets, "_digest", return_value="0" * 64), self.assertRaisesRegex(ValueError, "hash mismatch"):
            targets.verify_all_templates()

    def test_fetched_fabric_template_compares_loom_versions_as_numbers(self):
        self.assertEqual(targets.fabric_gradle_java(17, "1.5.8"), 21)
        self.assertEqual(targets.fabric_gradle_java(17, "1.9.2"), 21)
        self.assertEqual(targets.fabric_gradle_java(21, "1.19.4"), 25)
        self.assertEqual(targets.fabric_gradle_java(25, "1.100.0"), 25)


class DeployBackupTests(Temp):
    def test_an_unrecognised_jar_with_the_same_name_is_backed_up_not_overwritten(self):
        mod = self.root / "mod"
        (mod / "build/libs").mkdir(parents=True)
        (mod / "mcforge-project.json").write_text(json.dumps({"mod_id": "probe", "loader": "fabric", "minecraft": "1.21.1"}), encoding="utf-8")
        with zipfile.ZipFile(mod / "build/libs/probe-2.0.0.jar", "w") as archive:
            archive.writestr("fabric.mod.json", json.dumps({"schemaVersion": 1, "id": "probe", "version": "2.0.0"}))
        instance = self.root / "inst"
        (instance / "mods").mkdir(parents=True)
        (instance / "instance.json").write_text(json.dumps({"launcher": {"name": "I", "version": "1.21.1",
                                                                         "loaderVersion": {"type": "Fabric", "version": "0.20.1"}}}), encoding="utf-8")
        (instance / "mods/probe-2.0.0.jar").write_bytes(b"not a readable jar, but somebody's file")
        plan = launchers.deploy(mod, instance, unverified=True)
        self.assertEqual([Path(path).name for path in plan["replaces"]], ["probe-2.0.0.jar"])
        done = launchers.deploy(mod, instance, unverified=True, apply=True)
        saved = list((instance / "mcforge-backups").rglob("probe-2.0.0.jar"))
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0].read_bytes(), b"not a readable jar, but somebody's file")
        self.assertTrue(zipfile.is_zipfile(done["destination"]))


class WriteGuardTests(Temp):
    def test_content_commands_refuse_a_project_inside_a_launcher_instance(self):
        instance = self.root / "prism-inst"
        project = instance / "minecraft/planted"
        project.mkdir(parents=True)
        (instance / "mmc-pack.json").write_text('{"components": []}', encoding="utf-8")
        (project / "mcforge-project.json").write_text(json.dumps({"mod_id": "probe", "package": "dev.example.probe", "minecraft": "1.21.1",
                                                                  "family": "neoforge-mdg"}), encoding="utf-8")
        spec = self.root / "spec.json"
        spec.write_text(json.dumps({"name": "dot", "blobs": [{"name": "b", "bone": "root",
                                                               "shape": {"box": {"min": [0, 0, 0], "max": [2, 2, 2]}}}]}), encoding="utf-8")
        for call in (lambda: content.add_content(project, "item", "ruby"),
                     lambda: generate_assets(project),
                     lambda: content.import_bbmodel(project, self.root / "none.bbmodel", block="thing"),
                     lambda: voxel.write_voxel_model(spec, project=project)):
            with self.assertRaisesRegex(ValueError, "read-only"):
                call()
        self.assertEqual(sorted(path.name for path in project.iterdir()), ["mcforge-project.json"])


class VerificationLockTests(Temp):
    def test_a_dead_owner_frees_the_lock_and_a_live_one_keeps_it(self):
        from mcforge import verification
        lock = self.root / "verification.lock"
        dead = subprocess.Popen([sys.executable, "-c", "pass"])
        dead.wait()
        lock.write_text(json.dumps({"pid": dead.pid, "run_id": "killed"}), encoding="utf-8")
        lease, note = verification._acquire(lock)
        lease.close()
        self.assertIn("stale verification lock", note)
        lock.write_text(json.dumps({"pid": os.getpid(), "run_id": "mine"}), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "already locked .*mine"):
            verification._acquire(lock)
        self.assertTrue(verification._process_alive(os.getpid()))
        self.assertFalse(verification._process_alive(dead.pid))

    @unittest.skipUnless(os.name == "nt", "drive letters and case-insensitive paths are Windows behaviour")
    def test_receipt_matches_a_differently_cased_project_path(self):
        from mcforge import verification
        project = self.root / "Mod"
        (project / "build/mcforge").mkdir(parents=True)
        receipt = {"schema": 1, "status": "passed", "project": str(project).upper(), "inputs": {}, "generated": {},
                   "target": {}, "outputs": {}}
        (project / "build/mcforge/verification.json").write_text(json.dumps(receipt), encoding="utf-8")
        with patch.object(verification, "_inputs", return_value={}), patch.object(verification, "_generated", return_value={}), \
                patch.object(verification, "_project_info", return_value={"target": {}}):
            # Past the identity check, the empty outputs fail as stale: the project itself was recognised.
            with self.assertRaisesRegex(ValueError, "artifact, test report or logs"):
                verification.check_receipt(project)


@unittest.skipUnless((ROOT / ".github/workflows/ci.yml").is_file(), "the portable package ships no CI workflow")
class WorkflowTests(unittest.TestCase):
    def test_ci_runs_once_per_commit(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        head = workflow.split("permissions:", 1)[0]
        # A bare `push:` also fires for tags and for pull-request branches, building one commit twice.
        self.assertIn("push:\n    branches: [main]", head)
        self.assertIn("pull_request:", head)


if __name__ == "__main__":
    unittest.main()
