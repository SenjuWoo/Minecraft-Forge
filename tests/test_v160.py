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

from test_links import ClassFile

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


if __name__ == "__main__":
    unittest.main()
