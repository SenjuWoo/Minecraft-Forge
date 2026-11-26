"""1.6.0: class-version check in links, packcompat, plan routes and the backport guide."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from mcforge import __main__ as cli
from mcforge import plan
from mcforge.links import blocking, check_mods_dir, check_instance, java_home_major, instance_java, summary_lines

try:  # discover -s tests puts tests/ on sys.path; `python -m unittest tests.test_v160` does not
    from test_links import ClassFile
except ImportError:
    from tests.test_links import ClassFile

ROOT = Path(__file__).resolve().parents[1]


def class_bytes(item: ClassFile, major: int) -> bytes:
    data = bytearray(item.build())
    data[6:8] = major.to_bytes(2, "big")
    return bytes(data)


class Temp(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / "local" / "test-temp"
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def invoke(self, arguments):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = cli.main(arguments)
        return code, stdout.getvalue(), stderr.getvalue()


class JavaTooNew(Temp):
    def setUp(self):
        super().setUp()
        self.mods = self.root / "mods"
        self.mods.mkdir()

    def jar(self, path, entries):
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, data in entries.items():
                archive.writestr(name, data)
        return path

    def test_classes_for_a_newer_java_are_reported_and_block(self):
        self.jar(self.mods / "fine.jar", {"com/example/fine/A.class": class_bytes(ClassFile("com/example/fine/A"), 65)})
        self.jar(self.mods / "new.jar", {"com/example/new/A.class": class_bytes(ClassFile("com/example/new/A"), 69),
                                         "com/example/new/B.class": class_bytes(ClassFile("com/example/new/B"), 69),
                                         "com/example/new/C.class": class_bytes(ClassFile("com/example/new/C"), 65)})
        result = check_mods_dir(self.mods, 21)
        self.assertEqual(result["problems"], [])
        self.assertEqual(result["java_too_new"], [{"jar": "new.jar", "classes": 2, "class_major": 69, "needs_java": 25,
                                                   "runs_java": 21, "example_class": "com/example/new/A", "loader": None,
                                                   "loaded_at_startup": [], "mixin_plugins": {}, "guarded": False}])
        self.assertTrue(blocking(result))
        self.assertTrue(summary_lines(result)[0].startswith("JAVA-TOO-NEW            new.jar  2 classes need Java 25"))
        self.assertEqual(check_mods_dir(self.mods, 25)["java_too_new"], [])
        code, output, _ = self.invoke(["links", "--mods-dir", str(self.mods)])
        self.assertEqual(code, 1)
        self.assertTrue(output.startswith("JAVA-TOO-NEW"), output)
        self.assertIn("java: 21 (default 21", output)
        code, output, _ = self.invoke(["links", "--mods-dir", str(self.mods), "--java", "25", "--json"])
        self.assertEqual((code, json.loads(output)["java_too_new"], json.loads(output)["java_source"]), (0, [], "--java"))

    def test_nested_module_is_named_and_multi_release_copies_above_the_runtime_are_ignored(self):
        inner = self.jar(self.root / "opencl.jar", {"org/example/cl/Kernel.class": class_bytes(ClassFile("org/example/cl/Kernel"), 69)})
        self.jar(self.mods / "outer.jar", {"com/example/outer/Main.class": class_bytes(ClassFile("com/example/outer/Main"), 65),
                                           "META-INF/jarjar/opencl.jar": inner.read_bytes()})
        # a multi-release JAR whose Java 25 copy is never loaded on Java 21
        self.jar(self.mods / "multi.jar", {"com/example/multi/A.class": class_bytes(ClassFile("com/example/multi/A"), 65),
                                           "META-INF/versions/25/com/example/multi/A.class": class_bytes(ClassFile("com/example/multi/A"), 69)})
        rows = check_mods_dir(self.mods, 21)["java_too_new"]
        self.assertEqual([(row["jar"], row["needs_java"]) for row in rows], [("outer.jar!/META-INF/jarjar/opencl.jar", 25)])

    def module(self, name, plugin=None, service=False, loader="lowcodefml"):
        """A C2ME-style module: low-code mod, one mixin config, classes compiled for Java 25."""
        package = f"com/example/{name}"
        entries = {f"{package}/A.class": class_bytes(ClassFile(f"{package}/A"), 69),
                   "META-INF/neoforge.mods.toml": f'modLoader="{loader}"\n[[mods]]\nmodId="{name}"\n[[mixins]]\nconfig="{name}.mixins.json"\n',
                   f"{name}.mixins.json": json.dumps({"package": package, "mixins": ["A"]} | ({"plugin": plugin} if plugin else {}))}
        if service:
            entries["META-INF/services/net.neoforged.neoforgespi.locating.IModFileCandidateLocator"] = f"{package.replace('/', '.')}.A\n"
        return entries

    def test_a_module_whose_mixin_plugin_runs_on_this_java_is_guarded(self):
        self.jar(self.mods / "base.jar", {"com/example/base/ModulePlugin.class": class_bytes(ClassFile("com/example/base/ModulePlugin"), 65)})
        self.jar(self.mods / "guarded.jar", self.module("guarded", plugin="com.example.base.ModulePlugin"))
        result = check_mods_dir(self.mods, 21)
        row = result["java_too_new"][0]
        self.assertEqual((row["guarded"], row["loader"], row["mixin_plugins"]),
                         (True, "lowcodefml", {"guarded.mixins.json": "com/example/base/ModulePlugin"}))
        self.assertFalse(blocking(result))
        self.assertTrue(summary_lines(result)[0].startswith("JAVA-TOO-NEW (guarded)  guarded.jar"))
        code, _, _ = self.invoke(["links", "--mods-dir", str(self.mods)])
        self.assertEqual(code, 0)
        # no plugin, a plugin that is itself too new, an ordinary mod, or a loader service: not guarded
        self.jar(self.mods / "bare.jar", self.module("bare"))
        self.jar(self.mods / "selfplug.jar", self.module("selfplug", plugin="com.example.selfplug.A"))
        self.jar(self.mods / "javamod.jar", self.module("javamod", plugin="com.example.base.ModulePlugin", loader="javafml"))
        self.jar(self.mods / "service.jar", self.module("service", plugin="com.example.base.ModulePlugin", service=True))
        rows = {row["jar"]: row for row in check_mods_dir(self.mods, 21)["java_too_new"]}
        self.assertEqual({name: row["guarded"] for name, row in rows.items()},
                         {"bare.jar": False, "guarded.jar": True, "javamod.jar": False, "selfplug.jar": False, "service.jar": False})
        self.assertEqual(rows["service.jar"]["loaded_at_startup"],
                         ["net.neoforged.neoforgespi.locating.IModFileCandidateLocator -> com/example/service/A"])
        code, output, _ = self.invoke(["links", "--mods-dir", str(self.mods)])
        self.assertEqual(code, 1)
        self.assertIn("loaded at startup: net.neoforged.neoforgespi.locating.IModFileCandidateLocator", output)

    def test_instance_java_comes_from_the_instance_setting(self):
        jdk = self.root / "jdk-25"
        (jdk / "bin").mkdir(parents=True)
        (jdk / "release").write_text('IMPLEMENTOR="Example"\nJAVA_VERSION="25.0.1"\n', encoding="utf-8")
        legacy = self.root / "jre8"
        legacy.mkdir()
        (legacy / "release").write_text('JAVA_VERSION="1.8.0_392"\n', encoding="utf-8")
        self.assertEqual((java_home_major(jdk), java_home_major(jdk / "bin" / "java.exe"), java_home_major(legacy)), (25, 25, 8))
        self.assertIsNone(java_home_major(self.root / "absent"))

        at = self.root / "at"
        (at / "mods").mkdir(parents=True)
        meta = {"launcher": {"version": "1.21.1", "javaPath": str(jdk), "useJavaProvidedByMinecraft": False},
                "javaVersion": {"majorVersion": 21}}
        (at / "instance.json").write_text(json.dumps(meta), encoding="utf-8")
        major, source = instance_java(at)
        self.assertEqual(major, 25)
        self.assertIn("instance Java path", source)
        meta["launcher"]["useJavaProvidedByMinecraft"] = True
        (at / "instance.json").write_text(json.dumps(meta), encoding="utf-8")
        self.assertEqual(instance_java(at), (21, "instance.json javaVersion.majorVersion"))

        prism = self.root / "prism"
        (prism / "minecraft" / "mods").mkdir(parents=True)
        (prism / "mmc-pack.json").write_text(json.dumps({"components": [{"uid": "net.minecraft", "version": "1.20.1"}]}), encoding="utf-8")
        (prism / "instance.cfg").write_text(f"name=P\nOverrideJavaLocation=true\nJavaPath={jdk / 'bin' / 'java.exe'}\n", encoding="utf-8")
        self.assertEqual(instance_java(prism)[0], 25)
        (prism / "instance.cfg").write_text(f"name=P\nOverrideJavaLocation=false\nJavaPath={jdk / 'bin' / 'java.exe'}\n", encoding="utf-8")
        major, source = instance_java(prism)
        self.assertEqual(major, 17)
        self.assertIn("Minecraft 1.20.1 requires Java 17", source)

        bare = self.root / "bare"
        (bare / "mods").mkdir(parents=True)
        self.assertEqual(instance_java(bare)[0], 21)

    def test_links_instance_uses_the_resolved_java(self):
        jdk = self.root / "jdk-25"
        jdk.mkdir()
        (jdk / "release").write_text('JAVA_VERSION="25"\n', encoding="utf-8")
        instance = self.root / "inst"
        (instance / "mods").mkdir(parents=True)
        (instance / "instance.json").write_text(json.dumps({"launcher": {"version": "1.21.1", "javaPath": str(jdk)},
                                                            "javaVersion": {"majorVersion": 21}}), encoding="utf-8")
        self.jar(instance / "mods" / "new.jar", {"com/example/new/A.class": class_bytes(ClassFile("com/example/new/A"), 69)})
        self.assertEqual(check_instance(instance)["java_too_new"], [])
        self.assertEqual(len(check_instance(instance, 21)["java_too_new"]), 1)
        (instance / "instance.json").write_text(json.dumps({"launcher": {"version": "1.21.1"}, "javaVersion": {"majorVersion": 21}}),
                                                encoding="utf-8")
        code, output, _ = self.invoke(["links", "--instance", str(instance), "--json"])
        data = json.loads(output)
        self.assertEqual((code, data["java"], data["java_too_new"][0]["needs_java"]), (1, 21, 25))
        code, output, _ = self.invoke(["inventory", "--instance", str(instance), "--links"])
        self.assertEqual(json.loads(output)["links"]["java_too_new"][0]["jar"], "new.jar")


class PackCompat(Temp):
    MODEL = "assets/minecraft/models/block/thing.json"

    def make_pack(self, extra=None, name="Fancy.zip"):
        newer = {"textures": {"all": {"sprite": "minecraft:block/thing", "force_translucent": True}},
                 "elements": [{"from": [0, 0, 0], "to": [16, 16, 16], "shade_direction_override": "up", "light_emission": 7,
                               "rotation": {"origin": [8, 8, 8], "x": 10, "y": -90},
                               "faces": {"north": {"texture": {"sprite": "#all"}}}},
                              {"from": [0, 0, 0], "to": [1, 1, 1], "rotation": {"origin": [0, 0, 0], "axis": "z", "angle": 30}}]}
        meta = {"pack": {"pack_format": 15, "description": "x"},
                "overlays": {"entries": [{"directory": "ov_old", "formats": [19, 999]},
                                         {"directory": "ov_new", "formats": [50, 999]},
                                         {"directory": "ov_obj", "formats": {"min_inclusive": 30, "max_inclusive": 40}}]}}
        entries = {"pack.mcmeta": json.dumps(meta),
                   "assets/minecraft/models/block/plain.json": json.dumps({"parent": "block/cube_all"}),
                   "ov_old/" + self.MODEL: json.dumps(newer),
                   self.MODEL: json.dumps({"parent": "block/cube_all"}),
                   "ov_new/assets/minecraft/models/block/later.json": json.dumps({"elements": [{"rotation": {"x": 90}}]}),
                   "ov_obj/assets/minecraft/models/item/gem.json": json.dumps({"textures": {"layer0": {"sprite": "item/gem"}}}),
                   "../evil/assets/minecraft/models/block/evil.json": json.dumps({"elements": [{"rotation": {"x": 90}}]}),
                   "assets/minecraft/blockstates/heart.json": json.dumps({"variants": {"active=true": {"model": "block/a"}}}),
                   "assets/minecraft/blockstates/sign.json": json.dumps({"variants": {"facing=north": {"model": "block/s"}}})}
        entries.update(extra or {})
        path = self.root / name
        with zipfile.ZipFile(path, "w") as archive:
            for entry, data in entries.items():
                archive.writestr(entry, data)
        return path

    def mod_jar(self):
        path = self.root / "mod.jar"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("assets/minecraft/blockstates/heart.json", json.dumps({"variants": {"state=awake": {"model": "block/a"}}}))
            archive.writestr("assets/minecraft/blockstates/sign.json", json.dumps({"variants": {"": {"model": "block/s"}}}))
        return path

    def test_rules_overlays_and_blockstates(self):
        out = self.root / "out"
        code, output, _ = self.invoke(["packcompat", str(self.make_pack()), "--minecraft", "1.21.1", "--mod-jar", str(self.mod_jar()),
                                       "--out", str(out)])
        self.assertEqual(code, 0, output)
        result = json.loads(output)
        self.assertEqual(result["pack_format"], [34, 0])
        self.assertEqual(result["overlays_active"], ["ov_old", "ov_obj"])
        self.assertEqual([item["directory"] for item in result["overlays_skipped"]], ["ov_new"])
        self.assertEqual(sorted(item["path"] for item in result["rewritten"]),
                         ["assets/minecraft/models/block/thing.json", "assets/minecraft/models/item/gem.json"])
        model = json.loads((out / self.MODEL).read_text(encoding="utf-8"))
        first, second = model["elements"]
        self.assertEqual(model["textures"]["all"], "minecraft:block/thing")
        self.assertEqual((first["shade"], first["neoforge_data"], first["faces"]["north"]["texture"]), (False, {"block_light": 7}, "#all"))
        self.assertNotIn("shade_direction_override", first)
        self.assertEqual((first["rotation"]["axis"], first["rotation"]["angle"]), ("y", -45.0))
        self.assertNotIn("x", first["rotation"])
        self.assertEqual(second["rotation"]["angle"], 22.5)
        self.assertEqual(result["fallbacks"], 3)  # Euler reduced, -90 clamped, 30 clamped
        self.assertFalse((out / "assets/minecraft/models/block/later.json").exists())
        self.assertFalse((out / "assets/minecraft/models/block/plain.json").exists())
        self.assertFalse(any("evil" in str(path) for path in out.rglob("*")))
        self.assertTrue(any("unsafe names" in warning for warning in result["warnings"]))
        # heart: the pack's `active` property is not on the mod's block; sign: the mod's "" key gives no verdict
        self.assertEqual([item["path"] for item in result["blockstates"]], ["assets/minecraft/blockstates/heart.json"])
        self.assertEqual(json.loads((out / "assets/minecraft/blockstates/heart.json").read_text(encoding="utf-8"))["variants"],
                         {"state=awake": {"model": "block/a"}})
        self.assertEqual(json.loads((out / "pack.mcmeta").read_text(encoding="utf-8"))["pack"]["pack_format"], 34)
        # a newer target applies the later overlay too, and the output says the rules were checked on 1.21.1
        newer = json.loads(self.invoke(["packcompat", str(self.make_pack()), "--minecraft", "1.21.5", "--out", str(self.root / "o2")])[1])
        self.assertEqual(newer["overlays_active"], ["ov_old", "ov_new"])
        self.assertTrue(any("checked on 1.21.1" in warning for warning in newer["warnings"]))

    def test_folder_pack_reads_like_the_zip(self):
        folder = self.root / "FancyDir"
        with zipfile.ZipFile(self.make_pack()) as archive:
            for info in archive.infolist():
                if ".." not in info.filename:
                    target = folder / info.filename
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(archive.read(info))
        code, output, _ = self.invoke(["packcompat", str(folder), "--minecraft", "1.21.1", "--out", str(self.root / "dir-out")])
        result = json.loads(output)
        self.assertEqual((code, result["overlays_active"], result["files"]), (0, ["ov_old", "ov_obj"], 2))
        self.assertTrue((self.root / "dir-out" / self.MODEL).is_file())
        self.assertIn("FancyDir: models rewritten", (self.root / "dir-out" / "pack.mcmeta").read_text(encoding="utf-8"))

    def test_spriteless_texture_object_and_malformed_rotation(self):
        bad = "assets/minecraft/models/block/bad.json"
        bare = "assets/minecraft/models/block/bare.json"
        pack = self.make_pack({bad: json.dumps({"elements": [{"rotation": {"origin": [0, 0, 0], "y": "abc"}}]}),
                               bare: json.dumps({"textures": {"all": {"force_translucent": True}}})}, name="Odd.zip")
        out = self.root / "odd"
        code, output, _ = self.invoke(["packcompat", str(pack), "--minecraft", "1.21.1", "--out", str(out)])
        result = json.loads(output)
        self.assertEqual(code, 0, output)
        self.assertTrue(any(entry.startswith(bad + ":") for entry in result["unreadable"]), result["unreadable"])
        self.assertFalse((out / bad).exists())
        self.assertEqual(json.loads((out / bare).read_text(encoding="utf-8"))["textures"]["all"], "#missing")
        self.assertTrue((out / self.MODEL).is_file())  # the other files were still rewritten

    def test_destination_rules(self):
        pack = self.make_pack()
        out = self.root / "out"
        self.assertEqual(self.invoke(["packcompat", str(pack), "--minecraft", "1.21.1", "--out", str(out)])[0], 0)
        (out / "stale.json").write_text("{}", encoding="utf-8")
        self.assertEqual(self.invoke(["packcompat", str(pack), "--minecraft", "1.21.1", "--out", str(out)])[0], 0)
        self.assertFalse((out / "stale.json").exists())  # a previous packcompat output is replaced
        foreign = self.root / "foreign"
        foreign.mkdir()
        (foreign / "keep.txt").write_text("mine", encoding="utf-8")
        code, _, error = self.invoke(["packcompat", str(pack), "--minecraft", "1.21.1", "--out", str(foreign)])
        self.assertEqual(code, 2)
        self.assertIn("not written by packcompat", error)
        self.assertTrue((foreign / "keep.txt").is_file())
        # nothing to rewrite: no pack is written
        plain = self.make_pack({"ov_old/" + self.MODEL: json.dumps({"parent": "block/cube_all"}),
                                "ov_obj/assets/minecraft/models/item/gem.json": "{}"}, name="Plain.zip")
        result = json.loads(self.invoke(["packcompat", str(plain), "--minecraft", "1.21.1", "--out", str(self.root / "none")])[1])
        self.assertEqual((result["written"], result["rewritten"]), (False, []))
        self.assertFalse((self.root / "none").exists())

    def test_instance_needs_apply_and_out_inside_an_instance_is_refused(self):
        instance = self.root / "inst"
        (instance / "resourcepacks").mkdir(parents=True)
        (instance / "mods").mkdir()
        (instance / "instance.json").write_text(json.dumps({"launcher": {"version": "1.21.1"}}), encoding="utf-8")
        (instance / "options.txt").write_text('version=3955\nresourcePacks:["vanilla","file/Fancy.zip","file/Other"]\n', encoding="utf-8")
        pack = self.make_pack()
        code, _, error = self.invoke(["packcompat", str(pack), "--minecraft", "1.21.1", "--out", str(instance / "resourcepacks" / "x")])
        self.assertEqual(code, 2)
        self.assertIn("--instance INSTANCE --apply", error)
        self.assertFalse((instance / "resourcepacks" / "x").exists())
        code, output, _ = self.invoke(["packcompat", str(pack), "--minecraft", "1.21.1", "--instance", str(instance)])
        plan_only = json.loads(output)
        self.assertEqual((code, plan_only["written"]), (0, False))
        self.assertFalse((instance / "resourcepacks" / "Fancy-compat").exists())
        self.assertEqual(plan_only["options_txt"]["suggested"], 'resourcePacks:["vanilla","file/Fancy.zip","file/Fancy-compat","file/Other"]')
        code, output, _ = self.invoke(["packcompat", str(pack), "--minecraft", "1.21.1", "--instance", str(instance), "--apply"])
        self.assertEqual((code, json.loads(output)["written"]), (0, True))
        self.assertTrue((instance / "resourcepacks" / "Fancy-compat" / self.MODEL).is_file())
        self.assertIn('"file/Fancy.zip","file/Other"', (instance / "options.txt").read_text(encoding="utf-8"))  # never edited
        self.assertEqual(self.invoke(["packcompat", str(pack), "--minecraft", "1.21.1", "--out", str(self.root / "o"), "--apply"])[0], 2)


class Routes(Temp):
    def routes(self, request):
        result = plan.plan(request)
        return result, {step.get("route"): step for step in result["steps"] if step.get("route")}

    def test_backport_targets_the_older_version_and_loads_the_guide(self):
        result, routes = self.routes("backport 26.3 content into a 1.21.1 neoforge pack")
        step = routes["backport newer content into an older pack"]
        self.assertEqual((result["minecraft"], step["guide"]), ("1.21.1", "backport"))
        self.assertTrue(result["steps"][0]["commands"][1].endswith("--loader neoforge --minecraft 1.21.1"))
        self.assertTrue(any(command.startswith("setup-java --major 25") for command in step["commands"]))
        self.assertIn("backport newer content into an older pack", self.routes("bring newer version content into my older pack")[1])
        # one version: unchanged behaviour
        self.assertEqual(plan.plan("forge 1.20.1 ruby armor")["minecraft"], "1.20.1")

    def test_pack_symptoms_route_to_packcompat_and_links(self):
        result, routes = self.routes("resource pack missing model, purple-black blocks after pack update")
        self.assertFalse(result["mod_needed"])
        self.assertNotIn("block", routes)
        self.assertTrue(routes["resource pack models the game cannot read"]["commands"][0].startswith("packcompat "))
        for request in ("resource pack shows missing purple black models after update",
                        "missing purple black models in my resource pack",
                        "my resource pack models are missing after the pack update"):
            result, routes = self.routes(request)
            self.assertEqual(list(routes), ["resource pack models the game cannot read"], request)
            self.assertFalse(result["mod_needed"], request)
        # making a pack is still the pack route
        self.assertIn("resource pack", self.routes("a resource pack that retextures stone black")[1])
        result, routes = self.routes("the game closes silently at load")
        self.assertFalse(result["mod_needed"])
        self.assertTrue(routes["silent exit while loading"]["commands"][0].startswith("links --instance"))

    def test_backport_guide_is_bundled(self):
        self.assertEqual(cli.GUIDES["backport"], "BACKPORT.md")
        text = cli.guide_text("backport")
        for needle in ("setup-java --major 25", "oracle", "clampedLerp", "packcompat", "Out of scope"):
            self.assertIn(needle, text)
        self.assertIn("backport", cli.capabilities()["guides"])
        self.assertIn("packcompat", cli.capabilities()["commands"])


if __name__ == "__main__":
    unittest.main()
