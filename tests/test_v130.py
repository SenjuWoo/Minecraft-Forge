"""1.3.0: voxel models, pose evaluator and grounding, geo previews with game lighting, audio-check, devshots, word gate."""
import hashlib
import json
from pathlib import Path
import struct
import sys
import unittest

from mcforge import audiocheck, devshots, geckopose, modelcheck, preview, verification, voxel
from mcforge.pixelart import read_png
from mcforge.scaffold import init_project
from tests.test_v100 import ROOT, Temp

sys.path.insert(0, str(ROOT / "scripts"))
import check_hygiene  # noqa: E402


def geo(bones, width=16, height=16):
    return {"format_version": "1.12.0", "minecraft:geometry": [{"description": {"identifier": "geometry.t", "texture_width": width,
                                                                                "texture_height": height}, "bones": bones}]}


class PoseTests(Temp):
    def write(self, name, data):
        path = self.root / name
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_grounding_a_kneeling_leg_matches_the_hand_computed_offset(self):
        model = self.write("t.geo.json", geo([
            {"name": "root", "pivot": [0, 0, 0]},
            {"name": "leg", "parent": "root", "pivot": [0, 4, 0], "cubes": [{"origin": [-1, 0, -1], "size": [2, 4, 2], "uv": [0, 0]}]}]))
        # JSON rotation x is negated: [-90, 0, 0] is +90 degrees about X in Blockbench space, lifting the foot to y = 3.
        clips = self.write("t.animation.json", {"format_version": "1.8.0", "animations": {"animation.t.kneel": {
            "animation_length": 1.0, "bones": {"leg": {"rotation": {"0.0": [0, 0, 0], "1.0": [-90, 0, 0]}}}}}})
        data, report = geckopose.ground_animations(model, clips, ["leg"], ["kneel"])
        keys = data["animations"]["animation.t.kneel"]["bones"]["root"]["position"]
        self.assertEqual(keys["0.0"], [0.0, 0.0, 0.0])
        self.assertEqual(keys["1.0"], [0.0, -3.0, 0.0])
        self.assertEqual(report["clips"]["animation.t.kneel"]["frames"], 2)

    def test_mirrored_x_and_z_rotation_order(self):
        # A cube at Blockbench x 2..4 (Bedrock origin x = -4) turned +90 degrees about Z lands at y 2..4.
        model = self.write("z.geo.json", geo([
            {"name": "root", "pivot": [0, 0, 0]},
            {"name": "arm", "parent": "root", "pivot": [0, 0, 0], "cubes": [{"origin": [-4, 0, -1], "size": [2, 1, 2], "uv": [0, 0]}]}]))
        clips = self.write("z.animation.json", {"animations": {"a.z": {"animation_length": 0.5, "bones": {
            "arm": {"rotation": {"0.0": [0, 0, 90], "0.5": [0, 0, 90]}}}}}})
        data, _ = geckopose.ground_animations(model, clips, ["arm"], ["z"], fps=4)
        keys = data["animations"]["a.z"]["bones"]["root"]["position"]
        self.assertTrue(all(abs(value[1] + 2.0) < 1e-6 for value in keys.values()), keys)
        self.assertEqual(len(keys), 3)

    def test_molang_and_unknown_bones_are_refused(self):
        model = self.write("m.geo.json", geo([{"name": "root", "pivot": [0, 0, 0]},
                                              {"name": "leg", "parent": "root", "pivot": [0, 4, 0], "cubes": [{"origin": [0, 0, 0], "size": [1, 4, 1]}]}]))
        clips = self.write("m.animation.json", {"animations": {"a.m": {"animation_length": 1, "bones": {"leg": {"rotation": ["math.sin(q.anim_time)", 0, 0]}}}}})
        with self.assertRaisesRegex(ValueError, "Molang"):
            geckopose.ground_animations(model, clips, ["leg"], ["m"])
        with self.assertRaisesRegex(ValueError, "Unknown bones"):
            geckopose.ground_animations(model, clips, ["tail"], ["m"])

    def test_geo_preview_uses_game_lighting_and_skips_missing_faces(self):
        self.assertAlmostEqual(preview.vanilla_shade((0, 1, 0)), 1.0)
        self.assertAlmostEqual(preview.vanilla_shade((0, -1, 0)), 0.4)
        self.assertAlmostEqual(preview.vanilla_shade((0, 0, -1)), 0.6 * 0.7 / 1.2369317 + 0.4, places=5)
        self.assertAlmostEqual(preview.vanilla_shade((1, 0, 0)), preview.vanilla_shade((-1, 0, 0)))
        texture = self.root / "t.png"
        from mcforge.pixelart import blank, png_bytes, put
        image = blank(16, 16)
        for y in range(16):
            for x in range(16):
                put(image, x, y, (200, 50, 50))
        texture.write_bytes(png_bytes(image))
        model = self.write("p.geo.json", geo([{"name": "root", "pivot": [0, 0, 0], "cubes": [
            {"origin": [-4, 0, -4], "size": [8, 8, 8], "uv": {"north": {"uv": [0, 0], "uv_size": [8, 8]}}}]}]))
        result = preview.preview_geo(model, read_png(texture.read_bytes()), self.root / "out.png", 128)
        self.assertEqual((result["cubes"], result["light"], result["uv"]), (1, "vanilla", "per-face"))
        rendered = read_png((self.root / "out.png").read_bytes())
        reds = {tuple(row[i:i + 3]) for row in rendered for i in range(0, len(row), 4) if row[i] > row[i + 1] + 40}
        # Only the north face exists: one flat shade of red, the other faces are skipped like GeckoLib skips them.
        self.assertEqual(len(reds), 1)


class VoxelTests(Temp):
    def test_partition_covers_every_cell_once(self):
        f, bounds = voxel.build_shape({"smooth_union": {"k": 0.4, "of": [
            {"ellipsoid": {"center": [0, 0, 0], "radii": [4, 3, 5]}}, {"capsule": {"a": [0, 2, -3], "b": [0, 5, -6], "ra": 2, "rb": 1}}]}})
        occupied, n, _ = voxel.voxelize(f, bounds, 0.8)
        boxes = voxel.partition(occupied, n)
        seen = bytearray(len(occupied))
        for lo, hi in boxes:
            for i in range(lo[0], hi[0]):
                for j in range(lo[1], hi[1]):
                    for k in range(lo[2], hi[2]):
                        index = (i * n[1] + j) * n[2] + k
                        self.assertEqual(seen[index], 0, "boxes overlap")
                        seen[index] = 1
        self.assertEqual(seen, occupied)
        self.assertLess(len(boxes), sum(occupied))

    def test_example_spec_builds_clean_geckolib_files(self):
        spec = json.loads((ROOT / "templates/voxel/example.json").read_text(encoding="utf-8"))
        built = voxel.build_voxel_model(spec)
        report = built["report"]
        self.assertGreater(report["faces_omitted"], 0)
        self.assertEqual(report["warnings"], [])
        path = self.root / "toad.geo.json"
        path.write_text(json.dumps(built["geo"]), encoding="utf-8")
        self.assertEqual(modelcheck.check_model(path)["status"], "clean")
        bbmodel = self.root / "toad.bbmodel"
        bbmodel.write_text(json.dumps(built["bbmodel"]), encoding="utf-8")
        self.assertEqual(modelcheck.check_model(bbmodel)["status"], "clean")
        description = built["geo"]["minecraft:geometry"][0]["description"]
        texture = read_png(built["texture"])
        self.assertEqual((description["texture_width"], description["texture_height"]), (len(texture[0]) // 4, len(texture)))
        faces = sum(len(cube["uv"]) for bone in built["geo"]["minecraft:geometry"][0]["bones"] for cube in bone.get("cubes", []))
        self.assertEqual(faces, report["faces_kept"])

    def test_bad_specs_fail_with_a_reason(self):
        for spec, message in (({"name": "x", "blobs": []}, "blobs"), ({"name": "Bad"}, "lowercase"),
                              ({"name": "x", "blobs": [{"name": "a", "bone": "nope", "shape": {"box": {"min": [0, 0, 0], "max": [1, 1, 1]}}}]}, "unknown bone"),
                              ({"name": "x", "blobs": [{"name": "a", "bone": "root", "shape": {"cone": {}}}]}, "Unknown shape")):
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                voxel.build_voxel_model(spec)

    def test_cli_writes_into_a_project(self):
        project = self.make("neoforge-1.21.1")
        code, output, _ = self.invoke(["voxel", str(ROOT / "templates/voxel/example.json"), "--project", str(project)])
        self.assertEqual(code, 0)
        result = json.loads(output)
        self.assertTrue((project / "src/main/resources/assets/probe/geo/entity/bog_toad.geo.json").is_file())
        self.assertTrue((project / "blockbench/bog_toad_uvtest.png").is_file())
        self.assertEqual(result["model_check"]["status"], "clean")
        self.assertEqual(self.invoke(["voxel", str(ROOT / "templates/voxel/example.json"), "--project", str(project)])[0], 2)


def ogg(channels=1, rate=44100, samples=88200) -> bytes:
    first = (b"OggS" + bytes([0, 2]) + struct.pack("<q", 0) + bytes(12) + bytes([1, 30]) + b"\x01vorbis"
             + struct.pack("<I", 0) + bytes([channels]) + struct.pack("<I", rate) + bytes(12))
    return first + b"OggS" + bytes([0, 4]) + struct.pack("<q", samples) + bytes(16)


class AudioTests(Temp):
    def test_report_matches_events_registrations_and_files(self):
        project = self.make("neoforge-1.21.1")
        assets = project / "src/main/resources/assets/probe"
        (assets / "sounds/mob").mkdir(parents=True)
        (assets / "sounds/mob/roar.ogg").write_bytes(ogg())
        (assets / "sounds/mob/wind.ogg").write_bytes(ogg(channels=2, samples=44100 * 30))
        (assets / "sounds.json").write_text(json.dumps({
            "mob.roar": {"subtitle": "subtitles.probe.roar", "sounds": ["probe:mob/roar"]},
            "mob.wind": {"sounds": [{"name": "probe:mob/wind"}]},
            "mob.gone": {"sounds": ["probe:mob/gone"]}}), encoding="utf-8")
        java = project / "src/main/java/dev/example/probe/Sounds.java"
        java.write_text('class Sounds { static final DeferredHolder<SoundEvent, SoundEvent> ROAR = reg("mob.roar");\n'
                        'static final DeferredHolder<SoundEvent, SoundEvent> WIND = SOUNDS.register("mob.wind", () -> null);\n'
                        'static final DeferredHolder<SoundEvent, SoundEvent> HISS = reg("mob.hiss"); }', encoding="utf-8")
        result = audiocheck.check_audio(project, measure=False)
        self.assertEqual(sorted(result["registered_ids"]), ["mob.hiss", "mob.roar", "mob.wind"])
        problems, warnings = " | ".join(result["problems"]), " | ".join(result["warnings"])
        self.assertIn("mob/gone.ogg does not exist", problems)
        self.assertIn("probe:mob.hiss is registered but sounds.json has no entry", problems)
        self.assertIn("2 channels", warnings)
        self.assertIn('"stream": true', warnings)
        self.assertIn("subtitles.probe.roar", warnings)
        roar = next(row for row in result["files"] if row["file"].endswith("roar.ogg"))
        self.assertEqual((roar["channels"], roar["sample_rate"], roar["duration"]), (1, 44100, 2.0))
        self.assertEqual(result["status"], "problems")


class DevShotsTests(Temp):
    def test_scaffold_needs_the_test_mod_and_is_idempotent(self):
        bare = self.make("neoforge-1.21.1")
        with self.assertRaisesRegex(ValueError, "tests PROJECT"):
            devshots.add_devshots(bare)
        with self.assertRaisesRegex(ValueError, "NeoForge 1.21.1"):
            devshots.add_devshots(self.make("fabric-1.21.1", "fab"))
        project = self.root / "shots"
        init_project(project, "shots", "dev.example.shots", "Shots", with_tests=True, examples=False)
        result = devshots.add_devshots(project)
        self.assertEqual(result["subject"], "minecraft:pig")
        driver = (project / "src/gameTest/java/dev/example/shots/testing/DevShots.java").read_text(encoding="utf-8")
        self.assertIn("package dev.example.shots.testing;", driver)
        self.assertNotIn("@PACKAGE@", driver)
        self.assertIn("pauseOnLostFocus = false", driver)
        with self.assertRaisesRegex(ValueError, "--force"):
            devshots.add_devshots(project)
        devshots.add_devshots(project, "minecraft:cow", force=True)
        build = (project / "build.gradle").read_text(encoding="utf-8")
        self.assertEqual(build.count(devshots.BEGIN), 1)
        self.assertIn("'mcforge.devshots.subject', 'minecraft:cow'", build)
        self.assertEqual(json.loads((project / "mcforge-project.json").read_text())["devshots"], {"subject": "minecraft:cow"})

    def test_client_verification_requires_the_scaffold(self):
        project = self.make("neoforge-1.21.1")
        with self.assertRaisesRegex(ValueError, "devshots PROJECT"):
            verification.verify_project(project, client=True)
        code, _, error = self.invoke(["verify", str(project), "--check", "--client"])
        self.assertEqual(code, 2)


class WordGateTests(Temp):
    def test_blocked_words_are_found_by_hash_only(self):
        blocked = {hashlib.sha256(b"zzqx").hexdigest()[:16]}
        path = self.root / "notes.md"
        path.write_text("A line with ZZQX in it, and zzqxy which is a different word.", encoding="utf-8")
        problems = check_hygiene.scan([path], self.root, blocked)
        self.assertEqual(len(problems), 1)
        self.assertIn("1 word(s)", problems[0])
        source = (ROOT / "scripts/check_hygiene.py").read_text(encoding="utf-8")
        self.assertGreater(len(check_hygiene.BLOCKED_WORD_HASHES), 40)
        self.assertEqual(check_hygiene.blocked_words(source), 0)


if __name__ == "__main__":
    unittest.main()
