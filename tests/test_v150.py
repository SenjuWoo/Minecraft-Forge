"""1.5.0: lessons of the later mob builds - bone rest rotation, Euler continuity, the IK pole, project commands,
planned sounds, palette anchors, selective render passes, the audio post-processor, copies in audio-check and the
opt-in audio scene."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import textwrap
import unittest
import wave

from mcforge import audiocheck, devshots, kit, pipeline
from mcforge.scaffold import init_project
from tests.test_v100 import ROOT, Temp
from tests.test_v130 import ogg
from tests.test_v140 import HAVE_NUMPY

HAVE_FFMPEG = shutil.which("ffmpeg") is not None


class Passes(Temp):
    def test_geomob_renderer_filters_cubes_and_the_passes_kit_ships_alone(self):
        project = self.make("neoforge-1.21.1")
        kit.add_kit(project, "passes")
        base = project / "src/main/java/dev/example/probe"
        passes = (base / "kit/CubePasses.java").read_text(encoding="utf-8")
        for needle in ("package dev.example.probe.kit;", "interface Filtered", "static synchronized Set<GeoCube> resolve(",
                       "class GlowLayer<T extends GeoAnimatable> extends AutoGlowingGeoLayer<T>", "renderer.reRender("):
            self.assertIn(needle, passes)
        kit.add_kit(project, "geomob", "cave_stalker", force=True)
        renderer = (base / "cave_stalker/client/CaveStalkerRenderer.java").read_text(encoding="utf-8")
        self.assertIn("implements CubePasses.Filtered", renderer)
        self.assertIn("public void renderCube(PoseStack poseStack, GeoCube cube, VertexConsumer buffer", renderer)
        self.assertNotRegex(renderer, r"@[A-Z_]+@")
        self.assertIn("templates/kit/common/CubePasses.java", kit.template_files())


class AudioCopies(Temp):
    def test_identical_variants_of_one_event_are_a_problem(self):
        project = self.make("neoforge-1.21.1")
        folder = project / "src/main/resources/assets/probe/sounds/mob"
        folder.mkdir(parents=True)
        (folder / "step_1.ogg").write_bytes(ogg())
        (folder / "step_2.ogg").write_bytes(ogg())                    # the generator returned the same take twice
        (folder / "hiss_1.ogg").write_bytes(ogg(samples=44100))
        (folder / "hiss_2.ogg").write_bytes(ogg(samples=22050))
        (project / "src/main/resources/assets/probe/sounds.json").write_text(json.dumps({
            "mob.step": {"sounds": ["probe:mob/step_1", "probe:mob/step_2"]},
            "mob.hiss": {"sounds": ["probe:mob/hiss_1", "probe:mob/hiss_2"]}}), encoding="utf-8")
        result = audiocheck.check_audio(project, measure=False)
        copies = [p for p in result["problems"] if "same audio" in p]
        self.assertEqual(len(copies), 1, result["problems"])
        self.assertIn("mob/step_1 and mob/step_2", copies[0])


class AudioScene(unittest.TestCase):
    def test_audio_scene_is_opt_in_and_scenes_clean_up(self):
        scenes = (ROOT / "templates/devshots/DevScenes.java").read_text(encoding="utf-8")
        engine = (ROOT / "templates/devshots/DevShots.java").read_text(encoding="utf-8")
        self.assertIn('if (DevShots.named("audio"))', scenes)
        self.assertIn("BuiltInRegistries.SOUND_EVENT.keySet()", scenes)
        self.assertIn("static boolean named(String scene)", engine)
        self.assertIn("return scenesFilter().isBlank() || named(scene);", engine)


@unittest.skipUnless(HAVE_NUMPY, "numpy and Pillow are needed to run the scaffolded pipeline")
class PipelineLessons(Temp):
    def setUp(self):
        super().setUp()
        (self.root / "mod").mkdir()
        self.project = self.root / "mod" / "source"
        init_project(self.project, "probe", "dev.example.probe", "Probe Mod", target_id="neoforge-1.21.1")
        self.pipe = Path(pipeline.add_pipeline(self.project, "cave_stalker")["pipeline"])
        kit.add_kit(self.project, "geomob", "cave_stalker")
        self.env = dict(os.environ, PIPELINE_NO_VENV="1", PYTHONPATH=str(ROOT),
                        MCFORGE_COMMAND=json.dumps([sys.executable, "-m", "mcforge"]))

    def build(self, *args, ok=True):
        done = subprocess.run([sys.executable, str(self.pipe / "build_assets.py"), *args], capture_output=True, text=True,
                              env=self.env, timeout=600)
        if ok:
            self.assertEqual(done.returncode, 0, done.stdout[-3000:] + done.stderr[-3000:])
        return done

    def snippet(self, code):
        script = self.root / "snippet.py"
        script.write_text("import sys\nsys.path.insert(0, %r)\n" % str(self.pipe) + textwrap.dedent(code), encoding="utf-8")
        done = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, env=self.env, timeout=300, cwd=self.pipe)
        self.assertEqual(done.returncode, 0, done.stdout[-3000:] + done.stderr[-3000:])
        return done.stdout

    def test_rest_rotation_ik_pole_euler_and_cube_lists(self):
        rig = self.pipe / "mob/rig.py"
        text = rig.read_text(encoding="utf-8")
        old = '("tail", "hips", (0, 11, 3)),'
        self.assertIn(old, text)
        rig.write_text(text.replace(old, '("tail", "hips", (0, 11, 3), (45, 10, 5)),'), encoding="utf-8")
        self.build("all", "--validate")
        geo = json.loads((self.project / "src/main/resources/assets/probe/geo/entity/cave_stalker.geo.json").read_text(encoding="utf-8"))
        bones = {b["name"]: b for b in geo["minecraft:geometry"][0]["bones"]}
        self.assertEqual(bones["tail"]["rotation"], [-45.0, -10.0, 5.0])        # Bedrock layout [-rx, -ry, rz]
        self.assertNotIn("rotation", bones["hips"])
        bb = json.loads((self.root / "mod/media/cave_stalker.bbmodel").read_text(encoding="utf-8"))

        def find(nodes, name):
            for n in nodes:
                if isinstance(n, dict):
                    if n.get("name") == name:
                        return n
                    hit = find(n.get("children", []), name)
                    if hit:
                        return hit
            return None
        self.assertEqual(find(bb["outliner"], "tail")["rotation"], [45.0, 10.0, 5.0])
        # the glowmask of the example gets a cube list for the selective glow pass
        cubes = (self.project / "src/main/java/dev/example/probe/gen/CaveStalkerCubes.java").read_text(encoding="utf-8")
        self.assertIn("public static final String[] GLOWMASK = {", cubes)
        out = self.snippet("""
            from lib import ik, animtools as A, rigtools
            # mirrored rest rotation: (rx, ry, rz) on the left side becomes (rx, -ry, -rz) on the right
            rigtools.R.BONES.append(("probe_L", "hips", (-1, 10, 0), (5, 10, 20)))
            rows = {b[0]: b[3] for b in rigtools.bones()}
            assert rows["probe_l"] == (5.0, 10.0, 20.0) and rows["probe_r"] == (5.0, -10.0, -20.0), rows
            # the knee points toward the pole, for the default negative flex range
            m = A.model()
            hip, knee0 = m.bones["thigh_l"]["pivot"], m.bones["shin_l"]["pivot"]
            foot = (knee0[0], 0.0, knee0[2])
            target = (hip[0], hip[1] - 0.6 * (hip[1] - foot[1]), hip[2])
            for pole, sign in (((0, 0, -1), -1), ((0, 0, 1), 1)):
                pose = ik.two_bone("thigh_l", "shin_l", foot, target, {}, pole=pole)
                k = ik.bone_point(pose, "shin_l", knee0)
                end = ik.bone_point(pose, "shin_l", foot)
                assert abs(end[1] - target[1]) < 0.05 and abs(end[2] - target[2]) < 0.05, (end, target)
                assert k[2] * sign > 0.5, (pole, k)
            # Euler continuity: the far representative of a rotation becomes the near one
            vals = A.unwrap_euler([(0, 0, 0), (179.9, 48.0, -178.9)])
            assert max(abs(v) for v in vals[1]) < 135, vals
            print("ok")
        """)
        self.assertIn("ok", out)

    def test_project_commands_and_planned_sounds(self):
        (self.pipe / "mob/hello.py").write_text("def run(args):\n    print('hello from mob')\n    return 0\n", encoding="utf-8")
        (self.pipe / "mob/commands.py").write_text('COMMANDS = {"hello": "mob.hello"}\n', encoding="utf-8")
        self.assertIn("hello from mob", self.build("hello").stdout)
        sounds = self.pipe / "mob/sounds.py"
        sounds.write_text(sounds.read_text(encoding="utf-8").replace(
            "PLANNED = {}", 'PLANNED = {"roar": ("Roars", "roar_*", {})}'), encoding="utf-8")
        done = self.build("sounds", "--validate")
        self.assertIn("1 planned", done.stdout)
        (self.pipe / "mob/commands.py").write_text('ALL_ORDER = ["rig", "nope"]\n', encoding="utf-8")
        bad = self.build("all", ok=False)
        self.assertNotEqual(bad.returncode, 0)
        self.assertIn("unknown commands: nope", bad.stdout + bad.stderr)

    def test_palette_anchors_space_steps_evenly(self):
        out = self.snippet("""
            import numpy as np
            from PIL import Image
            from lib import palette
            rng = np.random.default_rng(3)
            img = np.zeros((40, 80, 3), np.uint8)
            img[:, :40] = np.clip(np.array([200, 120, 60]) * rng.uniform(0.4, 1.1, (40, 40, 1)), 0, 255)
            img[:, 40:] = (40, 160, 230)                       # a neighbouring material inside the box
            Image.fromarray(img).save("ref.png")
            ramp = palette.ramp_from_image("ref.png", [(0, 0, 80, 40)], steps=4, keep=palette.hsv_filter(0.0, 0.15, 0.3, 1.0))
            lum = [np.array(palette.rgb(h)) @ palette.LUMA for h in ramp]
            gaps = np.diff(lum)
            assert all(g > 10 for g in gaps) and max(gaps) - min(gaps) < 20, (ramp, lum)
            assert all(palette.rgb(h)[0] > palette.rgb(h)[2] for h in ramp), ramp     # the blue neighbour was filtered out
            print("ok")
        """)
        self.assertIn("ok", out)

    @unittest.skipUnless(HAVE_FFMPEG, "ffmpeg is needed to process audio")
    def test_audio_export_levels_and_the_validator_catches_copies(self):
        staging = self.pipe / "audio/export/sfx"
        staging.mkdir(parents=True)

        def tone(path, freq, amp, seconds=0.4):
            n = int(44100 * seconds)
            with wave.open(str(path), "wb") as w:
                w.setnchannels(2)
                w.setsampwidth(2)
                w.setframerate(44100)
                frames = bytearray()
                for i in range(n):
                    v = int(amp * 32767 * math.sin(2 * math.pi * freq * i / 44100))
                    frames += v.to_bytes(2, "little", signed=True) * 2
                w.writeframes(bytes(frames))
        tone(staging / "zap_1.wav", 440, 0.02)                # quiet stereo take
        tone(staging / "zap_2.wav", 660, 0.9)                 # hot take
        self.build("audio", "export")
        folder = self.project / "src/main/resources/assets/probe/sounds/cave_stalker"
        self.assertEqual(sorted(p.name for p in folder.glob("*.ogg")), ["zap_1.ogg", "zap_2.ogg"])
        self.build("audio", "--validate")
        shutil.copyfile(folder / "zap_1.ogg", folder / "zap_3.ogg")
        bad = self.build("audio", "--validate", ok=False)
        self.assertNotEqual(bad.returncode, 0)
        self.assertIn("are copies", bad.stdout)


class DevshotsTemplatesStillFill(Temp):
    def test_scenes_template_compiles_its_placeholders(self):
        project = self.root / "shots"
        init_project(project, "shots", "dev.example.shots", "Shots", with_tests=True, examples=False)
        result = devshots.add_devshots(project)
        text = Path(result["scenes"]).read_text(encoding="utf-8")
        self.assertNotRegex(text, r"@[A-Z_]+@")
        self.assertIn("import net.minecraft.core.registries.BuiltInRegistries;", text)


if __name__ == "__main__":
    unittest.main()
