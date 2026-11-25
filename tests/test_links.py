import contextlib
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zipfile

from mcforge import __main__ as cli
from mcforge.links import check_jars, check_mods_dir, parse_class


def u2(value):
    return struct.pack(">H", value)


class ClassFile:
    """Minimal class-file writer: constant pool, header, fields and methods; enough for the link check."""

    def __init__(self, name, super_name="java/lang/Object", interfaces=(), access=0x0021):
        self.name, self.super_name, self.interfaces, self.access = name, super_name, tuple(interfaces), access
        self.pool, self.keys = [], {}
        self.fields, self.methods, self.refs, self.mixin = [], [], [], None

    def entry(self, key, payload):
        if key not in self.keys:
            self.pool.append(payload)
            self.keys[key] = len(self.pool)
        return self.keys[key]

    def utf8(self, text):
        raw = text.encode()
        return self.entry(("utf8", text), b"\x01" + u2(len(raw)) + raw)

    def cls(self, name):
        return self.entry(("class", name), b"\x07" + u2(self.utf8(name)))

    def nat(self, name, descriptor):
        return self.entry(("nat", name, descriptor), b"\x0c" + u2(self.utf8(name)) + u2(self.utf8(descriptor)))

    def field(self, name, descriptor, access=0x0001):
        self.fields.append((access, name, descriptor))
        return self

    def method(self, name, descriptor, access=0x0001):
        self.methods.append((access, name, descriptor))
        return self

    def call(self, owner, name, descriptor, interface=False):
        self.refs.append((11 if interface else 10, owner, name, descriptor))
        return self

    def get(self, owner, name, descriptor):
        self.refs.append((9, owner, name, descriptor))
        return self

    def mixin_into(self, *targets):
        self.mixin = targets
        return self

    def build(self):
        this, parent = self.cls(self.name), self.cls(self.super_name) if self.super_name else 0
        interfaces = [self.cls(name) for name in self.interfaces]
        for tag, owner, name, descriptor in self.refs:
            self.entry(("ref", tag, owner, name, descriptor), bytes([tag]) + u2(self.cls(owner)) + u2(self.nat(name, descriptor)))
        # A Code-like attribute with arbitrary bytes on every method proves the parser skips attributes by length.
        code, constant = self.utf8("Code"), self.utf8("ConstantValue")
        members = [(access, self.utf8(name), self.utf8(descriptor)) for access, name, descriptor in self.fields]
        methods = [(access, self.utf8(name), self.utf8(descriptor)) for access, name, descriptor in self.methods]
        attributes = b""
        if self.mixin is not None:
            annotations, annotation = self.utf8("RuntimeInvisibleAnnotations"), self.utf8("Lorg/spongepowered/asm/mixin/Mixin;")
            value, targets = self.utf8("value"), [self.utf8(f"L{name};") for name in self.mixin]
            body = u2(1) + u2(annotation) + u2(1) + u2(value) + b"[" + u2(len(targets)) + b"".join(b"c" + u2(t) for t in targets)
            attributes = u2(annotations) + struct.pack(">I", len(body)) + body
        out = b"\xca\xfe\xba\xbe" + u2(0) + u2(65) + u2(len(self.pool) + 1) + b"".join(self.pool)
        out += u2(self.access) + u2(this) + u2(parent) + u2(len(interfaces)) + b"".join(u2(i) for i in interfaces)
        out += u2(len(members)) + b"".join(u2(a) + u2(n) + u2(d) + u2(1) + u2(constant) + struct.pack(">I", 2) + u2(0)
                                           for a, n, d in members)
        out += u2(len(methods)) + b"".join(u2(a) + u2(n) + u2(d) + u2(1) + u2(code) + struct.pack(">I", 5) + b"\x00\x01\x02\x03\x04"
                                           for a, n, d in methods)
        out += u2(1 if attributes else 0) + attributes
        return out


class LinkTests(unittest.TestCase):
    def setUp(self):
        scratch = Path(__file__).resolve().parents[1] / "local" / "test-temp"
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.mods = self.root / "mods"
        self.mods.mkdir()

    def jar(self, name, classes=(), extra=None, folder=None):
        path = (folder or self.mods) / name
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            for item in classes:
                archive.writestr(item.name + ".class", item.build())
            for entry, content in (extra or {}).items():
                archive.writestr(entry, content)
        return path

    def api(self, run="(I)V"):
        return ClassFile("com/example/api/Api").method("run", run).field("COUNT", "I")

    def caller(self):
        return ClassFile("com/example/user/User").method("go", "()V").call("com/example/api/Api", "run", "(I)V") \
            .get("com/example/api/Api", "COUNT", "I").call("java/lang/String", "length", "()I")

    def kinds(self, result):
        return [row["kind"] for row in result["problems"]]

    def test_parser_reads_header_members_and_references(self):
        name, access, parent, interfaces, methods, fields, mixin, refs = parse_class(self.caller().build())
        self.assertEqual((name, parent, interfaces, mixin), ("com/example/user/User", "java/lang/Object", (), None))
        self.assertIn(("go", "()V"), methods)
        # java/ owners are platform members and never collected
        self.assertEqual(sorted(refs), [("field", "com/example/api/Api", "COUNT", "I"), ("method", "com/example/api/Api", "run", "(I)V")])

    def test_existing_member_is_ok(self):
        self.jar("api.jar", [self.api()])
        self.jar("user.jar", [self.caller()])
        result = check_mods_dir(self.mods)
        self.assertEqual((result["jars"], result["classes"], result["checked_refs"]), (2, 2, 2))
        self.assertEqual(result["problems"], [])
        self.assertEqual(result["errors"], [])

    def test_changed_descriptor_is_missing(self):
        self.jar("api.jar", [self.api(run="(J)V")])
        self.jar("user.jar", [self.caller()])
        result = check_mods_dir(self.mods)
        self.assertEqual(len(result["problems"]), 1)
        row = result["problems"][0]
        self.assertEqual((row["kind"], row["from_jar"], row["owner_jar"], row["owner"], row["member"], row["descriptor"]),
                         ("missing", "user.jar", "api.jar", "com/example/api/Api", "run", "(I)V"))
        self.assertEqual(row["from_class"], "com/example/user/User")

    def test_duplicate_references_are_grouped(self):
        self.jar("api.jar", [self.api(run="(J)V")])
        self.jar("user.jar", [self.caller(), ClassFile("com/example/user/Other").call("com/example/api/Api", "run", "(I)V")])
        result = check_mods_dir(self.mods)
        self.assertEqual([(row["kind"], row["count"]) for row in result["problems"]], [("missing", 2)])

    def writer(self):
        return ClassFile("com/example/api/Writer", access=0x0601).method("push", "(J)V", 0x0401).method("mod$push", "(J)V", 0x0401) \
            .method("helper", "()V", 0x0001).method("of", "()Lcom/example/api/Writer;", 0x0009)

    def test_unimplemented_interface_method_is_abstract_missing(self):
        self.jar("api.jar", [self.writer()])
        self.jar("user.jar", [ClassFile("com/example/user/Impl", interfaces=["com/example/api/Writer"]).method("push", "(J)V")])
        result = check_mods_dir(self.mods)
        # a prefixed name is not evidence of a mixin on its own; default and static methods need no implementation
        self.assertEqual([(row["kind"], row["member"], row["from_class"]) for row in result["problems"]],
                         [("abstract-missing", "mod$push", "com/example/user/Impl")])

    def test_abstract_and_mixin_classes_are_not_implementations(self):
        self.jar("api.jar", [self.writer()])
        self.jar("user.jar", [ClassFile("com/example/user/Base", interfaces=["com/example/api/Writer"], access=0x0421),
                              ClassFile("com/example/user/WriterMixin", interfaces=["com/example/api/Writer"]).mixin_into("net/minecraft/Thing")])
        self.assertEqual(check_mods_dir(self.mods)["problems"], [])

    def test_member_a_mixin_declares_on_the_class_is_unresolved(self):
        self.jar("api.jar", [self.writer()])
        self.jar("user.jar", [ClassFile("com/example/user/Impl", interfaces=["com/example/api/Writer"]).method("push", "(J)V")])
        self.jar("other.jar", [ClassFile("com/example/other/ImplMixin").method("mod$push", "(J)V").mixin_into("com/example/user/Impl")])
        result = check_mods_dir(self.mods)
        self.assertEqual(result["problems"], [])
        self.assertEqual(result["unresolved_reasons"], {"declared by a mixin": 1})

    def test_inherited_implementation_counts(self):
        self.jar("api.jar", [self.writer()])
        self.jar("user.jar", [ClassFile("com/example/user/Parent").method("push", "(J)V").method("mod$push", "(J)V"),
                              ClassFile("com/example/user/Child", "com/example/user/Parent", ["com/example/api/Writer"])])
        self.assertEqual(check_mods_dir(self.mods)["problems"], [])

    def test_members_inherited_from_jdk_roots_implement_interface_methods(self):
        self.jar("api.jar", [ClassFile("com/example/api/Named", access=0x0601).method("name", "()Ljava/lang/String;", 0x0401)
                             .method("toString", "()Ljava/lang/String;", 0x0401)])
        self.jar("user.jar", [ClassFile("com/example/user/Kind", "java/lang/Enum", ["com/example/api/Named"], access=0x4031),
                              ClassFile("com/example/user/Plain", interfaces=["com/example/api/Named"]).method("name", "()Ljava/lang/String;")])
        self.assertEqual(check_mods_dir(self.mods)["problems"], [])

    def test_corrupt_compressed_entry_is_recorded_and_the_scan_goes_on(self):
        path = self.jar("api.jar", [self.api(run="(J)V"), ClassFile("com/example/api/Victim").method("x", "()V")])
        self.jar("user.jar", [self.caller()])
        with zipfile.ZipFile(path) as archive:
            info = archive.getinfo("com/example/api/Victim.class")
        raw = bytearray(path.read_bytes())
        name_length, extra_length = struct.unpack("<HH", raw[info.header_offset + 26:info.header_offset + 30])
        start = info.header_offset + 30 + name_length + extra_length
        raw[start:start + info.compress_size] = b"\xff" * info.compress_size  # reserved deflate block type
        path.write_bytes(bytes(raw))
        result = check_mods_dir(self.mods)
        self.assertTrue(any("Victim.class" in error for error in result["errors"]), result["errors"])
        self.assertEqual(self.kinds(result), ["missing"])

    def test_supertype_outside_the_index_is_unresolved_not_missing(self):
        self.jar("api.jar", [ClassFile("com/example/api/Screen", "net/minecraft/client/gui/screens/Screen")])
        self.jar("user.jar", [ClassFile("com/example/user/User").call("com/example/api/Screen", "render", "()V")])
        result = check_mods_dir(self.mods)
        self.assertEqual(result["problems"], [])
        self.assertEqual(result["unresolved"], 1)
        self.assertEqual(result["unresolved_examples"][0]["via"], "net/minecraft/client/gui/screens/Screen")

    def test_object_members_resolve(self):
        self.jar("api.jar", [self.api()])
        self.jar("user.jar", [ClassFile("com/example/user/User").call("com/example/api/Api", "hashCode", "()I")])
        result = check_mods_dir(self.mods)
        self.assertEqual((result["problems"], result["unresolved"]), ([], 0))

    def test_nested_jar_owner_is_indexed(self):
        inner = self.root / "lib.jar"
        self.jar("lib.jar", [ClassFile("org/lib/Thing").method("old", "()V")], folder=self.root)
        self.jar("outer.jar", [ClassFile("com/example/outer/Main")], {"META-INF/jarjar/lib.jar": inner.read_bytes()})
        self.jar("user.jar", [ClassFile("com/example/user/User").call("org/lib/Thing", "old", "()V").call("org/lib/Thing", "new", "()V")])
        result = check_mods_dir(self.mods)
        self.assertEqual((result["jars"], result["nested_jars"], result["checked_refs"]), (2, 1, 2))
        self.assertEqual([(row["kind"], row["member"], row["owner_jar"]) for row in result["problems"]],
                         [("missing", "new", "outer.jar!/META-INF/jarjar/lib.jar")])

    def test_malformed_class_is_recorded_without_crashing(self):
        self.jar("api.jar", [self.api(run="(J)V")], {"com/example/api/Broken.class": b"\xca\xfe\xba\xbe\x00\x00\x00\x41\x00\x09\x01",
                                                     "com/example/api/Junk.class": b"not a class"})
        self.jar("user.jar", [self.caller()])
        self.jar("bad.jar", extra={})
        (self.mods / "notzip.jar").write_bytes(b"plain text")
        result = check_mods_dir(self.mods)
        self.assertEqual(len(result["errors"]), 3)
        self.assertTrue(any("Broken.class" in error for error in result["errors"]))
        self.assertTrue(any("notzip.jar" in error for error in result["errors"]))
        self.assertEqual(self.kinds(result), ["missing"])

    def test_missing_class_in_a_shipped_package_versus_an_unshipped_sibling(self):
        self.jar("api.jar", [ClassFile("com/example/api/core/Present")])
        self.jar("user.jar", [ClassFile("com/example/user/User").call("com/example/api/core/Gone", "x", "()V")
                              .call("com/example/api/compat/Optional", "y", "()V").call("org/elsewhere/Thing", "z", "()V")])
        result = check_mods_dir(self.mods)
        self.assertEqual([(row["kind"], row["owner"]) for row in result["problems"]], [("class-missing", "com/example/api/core/Gone")])
        self.assertEqual(result["unresolved_reasons"], {"package not shipped": 1})

    def test_reference_made_only_by_a_mixin_is_labelled(self):
        self.jar("api.jar", [self.api(run="(J)V")])
        self.jar("user.jar", [ClassFile("com/example/user/UserMixin").call("com/example/api/Api", "run", "(I)V").mixin_into("net/minecraft/A")])
        self.assertEqual(self.kinds(check_mods_dir(self.mods)), ["mixin-missing"])
        code, output, _ = self.invoke(["links", "--mods-dir", str(self.mods)])
        self.assertEqual(code, 1)
        self.assertTrue(output.startswith("MIXIN-MISSING"), output)

    def test_multi_release_picks_highest_version_not_above_java(self):
        base = ClassFile("com/example/api/Api")
        java17 = ClassFile("com/example/api/Api").method("fast", "()V")
        java25 = ClassFile("com/example/api/Api").method("fast", "()V").method("faster", "()V")
        self.jar("api.jar", [base], {"META-INF/versions/17/com/example/api/Api.class": java17.build(),
                                     "META-INF/versions/25/com/example/api/Api.class": java25.build()})
        self.jar("user.jar", [ClassFile("com/example/user/User").call("com/example/api/Api", "fast", "()V")
                              .call("com/example/api/Api", "faster", "()V")])
        self.assertEqual([row["member"] for row in check_mods_dir(self.mods, java=21)["problems"]], ["faster"])
        self.assertEqual(check_mods_dir(self.mods, java=25)["problems"], [])
        self.assertEqual(check_jars(sorted(self.mods.glob("*.jar")))["classes"], 2)

    def invoke(self, arguments):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = cli.main(arguments)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_cli_links_exit_codes_and_outputs(self):
        self.jar("api.jar", [self.api()])
        self.jar("user.jar", [self.caller()])
        code, output, _ = self.invoke(["links", "--mods-dir", str(self.mods)])
        self.assertEqual(code, 0)
        self.assertIn("2 jars (+0 nested), 2 classes, 2 cross-jar references checked", output)
        code, output, _ = self.invoke(["links", "--instance", str(self.root), "--json"])
        self.assertEqual((code, json.loads(output)["problems"]), (0, []))
        self.jar("api.jar", [self.api(run="(J)V")])
        code, output, _ = self.invoke(["links", "--mods-dir", str(self.mods)])
        self.assertEqual(code, 1)
        self.assertTrue(output.startswith("MISSING             user.jar -> api.jar  com/example/api/Api.run(I)V"), output)
        code, _, error = self.invoke(["links", "--mods-dir", str(self.root / "absent")])
        self.assertEqual(code, 2)
        self.assertIn("mods folder does not exist", error)

    def test_inventory_links_adds_the_report(self):
        self.jar("api.jar", [self.api(run="(J)V")])
        self.jar("user.jar", [self.caller()])
        code, output, _ = self.invoke(["inventory", "--instance", str(self.root), "--links"])
        data = json.loads(output)
        self.assertEqual(self.kinds(data["links"]), ["missing"])
        self.assertIn(code, (0, 1))
        code, output, _ = self.invoke(["inventory", "--instance", str(self.root)])
        self.assertNotIn("links", json.loads(output))
        empty = self.root / "empty"
        empty.mkdir()
        code, output, _ = self.invoke(["inventory", "--instance", str(empty), "--links"])
        self.assertEqual(code, 1)
        self.assertIn("mods folder does not exist", json.loads(output)["links"]["error"])


if __name__ == "__main__":
    unittest.main()
