"""Binary-compatibility ("link") check between the JARs of one mods folder, read from class files only.

A mod compiled against another mod's API calls exact members: owner class, name and JVM descriptor. When the
other mod changes that member while every declared version range is still satisfied, the game fails at runtime
with NoSuchMethodError, NoSuchFieldError, AbstractMethodError or NoClassDefFoundError. This module predicts those
failures from the JAR bytes: it never extracts to disk and never runs installed code.
"""

from __future__ import annotations

import io
from pathlib import Path
import time
import zipfile
import zlib

from .inventory import MAX_ARCHIVE_BYTES, MAX_ARCHIVE_ENTRIES


MAX_CLASS_BYTES = 16 * 1024 * 1024
MAX_NESTED_BYTES = 128 * 1024 * 1024
MAX_NESTED_DEPTH = 3
MAX_ERRORS = 100
MAX_UNRESOLVED_EXAMPLES = 5
# NeoForge/Forge jar-in-jar and Fabric nested JARs.
NESTED_DIRS = ("META-INF/jarjar/", "META-INF/jars/")
VERSIONS_DIR = "META-INF/versions/"
# Members owned by the JDK, the game, the loaders and Mixin are not between two mods; mods do not ship them.
# Libraries on the game and loader classpath (the library list of a vanilla + NeoForge 1.21.1 instance) are not in
# mods/ either; a mod that shades a few of their classes must not make the rest look missing.
PLATFORM_PREFIXES = ("java/", "javax/", "jdk/", "sun/", "net/minecraft/", "com/mojang/", "net/neoforged/",
                     "net/minecraftforge/", "net/fabricmc/", "org/spongepowered/", "[",
                     "com/google/common/", "com/google/gson/", "com/google/thirdparty/", "com/google/errorprone/",
                     "com/ibm/icu/", "oshi/", "com/sun/jna/", "io/netty/", "it/unimi/dsi/fastutil/", "joptsimple/",
                     "org/apache/commons/lang3/", "org/apache/commons/io/", "org/apache/commons/codec/",
                     "org/apache/commons/compress/", "org/apache/commons/logging/", "org/apache/http/",
                     "org/apache/logging/log4j/", "org/slf4j/", "org/joml/", "org/lwjgl/", "com/jcraft/", "net/jpountz/",
                     "org/objectweb/asm/", "com/electronwill/nightconfig/", "cpw/mods/", "net/jodah/typetools/",
                     "org/antlr/", "org/apache/maven/", "org/codehaus/plexus/", "net/minecrell/terminalconsole/",
                     "org/jline/", "org/openjdk/nashorn/", "com/machinezoo/noexception/", "org/checkerframework/")
MIXIN_ANNOTATION = b"Lorg/spongepowered/asm/mixin/Mixin;"
# mixin-*: only mixin classes make the reference. A mixin config plugin may drop such a mixin when the target mod
# version does not match, but nothing in the JARs proves that, so they count as problems too.
BLOCKING = ("missing", "abstract-missing", "class-missing", "mixin-missing", "mixin-class-missing")

# A corrupt entry or nested JAR is recorded and skipped; it never aborts the scan of the other JARs.
READ_ERRORS = (ValueError, OSError, EOFError, zipfile.BadZipFile, RuntimeError, NotImplementedError, zlib.error)
try:
    import lzma
    READ_ERRORS += (lzma.LZMAError,)
except ImportError:
    pass

ACC_STATIC = 0x0008
ACC_INTERFACE = 0x0200
ACC_ABSTRACT = 0x0400

_OBJECT = {("toString", "()Ljava/lang/String;"), ("hashCode", "()I"), ("equals", "(Ljava/lang/Object;)Z"),
           ("getClass", "()Ljava/lang/Class;"), ("notify", "()V"), ("notifyAll", "()V"), ("wait", "()V"),
           ("wait", "(J)V"), ("wait", "(JI)V"), ("clone", "()Ljava/lang/Object;"), ("finalize", "()V")}
# The few JDK roots every mod class ends in; their members are fixed, so a lookup that reaches them is decided
# instead of counted as unresolved.
JDK_ROOTS = {
    "java/lang/Object": _OBJECT,
    "java/lang/Record": _OBJECT,
    "java/lang/Enum": _OBJECT | {("name", "()Ljava/lang/String;"), ("ordinal", "()I"),
                                 ("compareTo", "(Ljava/lang/Enum;)I"), ("compareTo", "(Ljava/lang/Object;)I"),
                                 ("getDeclaringClass", "()Ljava/lang/Class;"),
                                 ("valueOf", "(Ljava/lang/Class;Ljava/lang/String;)Ljava/lang/Enum;"),
                                 ("describeConstable", "()Ljava/util/Optional;")},
}


class ClassInfo:
    __slots__ = ("jar", "access", "super", "interfaces", "methods", "fields", "mixin")

    def __init__(self, jar, access, super_name, interfaces, methods, fields, mixin):
        self.jar, self.access, self.super, self.interfaces = jar, access, super_name, interfaces
        self.methods, self.fields, self.mixin = methods, fields, mixin


def _u2(data, pos):
    return (data[pos] << 8) | data[pos + 1]


def _skip_attributes(data, pos):
    count = _u2(data, pos)
    pos += 2
    for _ in range(count):
        pos += 6 + int.from_bytes(data[pos + 2:pos + 6], "big")
    return pos


def parse_class(data: bytes):
    """Return (name, access, super, interfaces, methods {(name, descriptor): access}, fields {(name, descriptor)},
    @Mixin targets or None, member references to non-platform owners) from the class header, constant pool, fields
    and methods tables and the class annotations of a mixin. Code and other attributes are skipped, never interpreted."""
    if len(data) < 10 or data[:4] != b"\xca\xfe\xba\xbe":
        raise ValueError("not a class file")
    try:
        count = _u2(data, 8)
        utf = [None] * count
        classes = [0] * count
        nat = {}
        member_refs = []
        pos, i = 10, 1
        while i < count:
            tag = data[pos]
            if tag == 1:
                size = _u2(data, pos + 1)
                utf[i] = data[pos + 3:pos + 3 + size]
                pos += 3 + size
            elif tag == 7:
                classes[i] = _u2(data, pos + 1)
                pos += 3
            elif tag in (9, 10, 11):
                member_refs.append((tag, _u2(data, pos + 1), _u2(data, pos + 3)))
                pos += 5
            elif tag == 12:
                nat[i] = (_u2(data, pos + 1), _u2(data, pos + 3))
                pos += 5
            elif tag in (3, 4, 17, 18):
                pos += 5
            elif tag in (5, 6):
                pos += 9
                i += 1  # long and double take two constant-pool slots
            elif tag in (8, 16, 19, 20):
                pos += 3
            elif tag == 15:
                pos += 4
            else:
                raise ValueError(f"unknown constant-pool tag {tag} at entry {i}")
            i += 1
        decoded = {}

        def text(index):
            value = decoded.get(index)
            if value is None:
                raw = utf[index]
                if raw is None:
                    raise ValueError(f"constant-pool entry {index} is not UTF-8")
                value = decoded[index] = raw.decode("utf-8", "replace")
            return value

        def class_name(index):
            return text(classes[index]) if index else None

        access = _u2(data, pos)
        name = class_name(_u2(data, pos + 2))
        super_name = class_name(_u2(data, pos + 4))
        pos += 6
        interfaces = tuple(class_name(_u2(data, pos + 2 + 2 * n)) for n in range(_u2(data, pos)))
        pos += 2 + 2 * len(interfaces)
        fields = set()
        field_count = _u2(data, pos)
        pos += 2
        for _ in range(field_count):
            fields.add((text(_u2(data, pos + 2)), text(_u2(data, pos + 4))))
            pos = _skip_attributes(data, pos + 6)
        methods = {}
        method_count = _u2(data, pos)
        pos += 2
        for _ in range(method_count):
            methods[(text(_u2(data, pos + 2)), text(_u2(data, pos + 4)))] = _u2(data, pos)
            pos = _skip_attributes(data, pos + 6)
        if pos > len(data):
            raise ValueError("truncated class file")
        targets = _mixin_targets(data, pos, text) if MIXIN_ANNOTATION in data else None
        refs = []
        for tag, owner_index, nat_index in member_refs:
            owner = class_name(owner_index)
            if owner is None or owner.startswith(PLATFORM_PREFIXES):
                continue
            member, descriptor = nat[nat_index]
            refs.append(("field" if tag == 9 else "method", owner, text(member), text(descriptor)))
    except (IndexError, KeyError) as error:
        raise ValueError(f"truncated or inconsistent class file ({type(error).__name__})") from None
    return name, access, super_name, interfaces, methods, fields, targets, refs


def _element(data, pos, text, out):
    """Skip one annotation element_value; collect class ('c') and string ('s') constants into out."""
    tag = data[pos]
    if tag in (0x73, 0x63):  # 's', 'c'
        out.append(text(_u2(data, pos + 1)))
        return pos + 3
    if tag in b"BCDFIJSZ":
        return pos + 3
    if tag == 0x65:  # 'e'
        return pos + 5
    if tag == 0x40:  # '@'
        return _annotation(data, pos + 1, text, None)
    if tag == 0x5B:  # '['
        count = _u2(data, pos + 1)
        pos += 3
        for _ in range(count):
            pos = _element(data, pos, text, out)
        return pos
    raise ValueError(f"unknown annotation element tag {tag}")


def _annotation(data, pos, text, found):
    kind = text(_u2(data, pos))
    pairs = _u2(data, pos + 2)
    pos += 4
    for _ in range(pairs):
        key = text(_u2(data, pos))
        values = []
        pos = _element(data, pos + 2, text, values)
        if found is not None and kind == "Lorg/spongepowered/asm/mixin/Mixin;" and key in ("value", "targets"):
            found.extend(values)
    return pos


def _mixin_targets(data, pos, text) -> tuple:
    """Target classes named by the class's @Mixin annotation (value = classes, targets = names)."""
    found = []
    count = _u2(data, pos)
    pos += 2
    for _ in range(count):
        name = text(_u2(data, pos))
        end = pos + 6 + int.from_bytes(data[pos + 2:pos + 6], "big")
        if name in ("RuntimeInvisibleAnnotations", "RuntimeVisibleAnnotations"):
            cursor = pos + 8
            for _ in range(_u2(data, pos + 6)):
                cursor = _annotation(data, cursor, text, found)
        pos = end
    targets = []
    for value in found:
        if value.startswith("L") and value.endswith(";"):
            value = value[1:-1]
        targets.append(value.replace(".", "/"))
    return tuple(targets)


def _bounded_member(archive: zipfile.ZipFile, info: zipfile.ZipInfo, limit: int) -> bytes:
    if info.file_size > limit:
        raise ValueError(f"exceeds {limit} byte inspection limit")
    with archive.open(info) as handle:
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f"exceeds {limit} byte read limit")
    return data


class _Scanner:
    def __init__(self, java: int):
        self.java = java
        self.jars: list[str] = []
        self.index: dict[str, list[ClassInfo]] = {}
        self.refs: list[dict] = []
        self.prefixes: dict[str, set[int]] = {}
        self.packages: dict[str, set[int]] = {}
        # target class -> (name, descriptor) of members that mixins aimed at it declare (and may add at runtime)
        self.mixin_members: dict[str, set[tuple[str, str]]] = {}
        self.errors: list[str] = []
        self.error_total = 0
        self.classes = 0

    def error(self, text: str):
        self.error_total += 1
        if len(self.errors) < MAX_ERRORS:
            self.errors.append(text)

    def scan(self, archive: zipfile.ZipFile, label: str, depth: int = 0):
        entries = archive.infolist()
        if len(entries) > MAX_ARCHIVE_ENTRIES:
            raise ValueError("archive exceeds entry inspection limit")
        jar = len(self.jars)
        self.jars.append(label)
        self.refs.append({})
        chosen: dict[str, tuple[int, zipfile.ZipInfo]] = {}
        nested = []
        for info in entries:
            name = info.filename
            if name.endswith(".class"):
                release = 0
                if name.startswith("META-INF/"):
                    # Multi-release JARs: the JVM uses the highest versions/N/ copy with N <= the running Java.
                    if not name.startswith(VERSIONS_DIR):
                        continue
                    number, _, rest = name[len(VERSIONS_DIR):].partition("/")
                    if not number.isdigit() or int(number) > self.java or not rest:
                        continue
                    release, name = int(number), rest
                base = name.rpartition("/")[2]
                if base in ("module-info.class", "package-info.class"):
                    continue
                if name not in chosen or chosen[name][0] < release:
                    chosen[name] = (release, info)
            elif depth < MAX_NESTED_DEPTH and name.endswith(".jar") and name.startswith(NESTED_DIRS):
                nested.append(info)
        refs = self.refs[jar]
        for entry, (_, info) in chosen.items():
            try:
                name, access, super_name, interfaces, methods, fields, targets, class_refs = parse_class(
                    _bounded_member(archive, info, MAX_CLASS_BYTES))
            except READ_ERRORS as error:
                self.error(f"{label}: {info.filename}: {error}")
                continue
            if not name:
                self.error(f"{label}: {info.filename}: class has no name")
                continue
            self.classes += 1
            mixin = targets is not None
            if mixin:
                for target in targets:
                    members = self.mixin_members.setdefault(target, set())
                    members.update(methods)
                    members.update(fields)
            self.index.setdefault(name, []).append(ClassInfo(jar, access, super_name, interfaces, methods, fields, mixin))
            self.prefixes.setdefault(_prefix(name), set()).add(jar)
            self.packages.setdefault(name.rpartition("/")[0], set()).add(jar)
            for ref in class_refs:
                seen = refs.get(ref)
                if seen is None:
                    refs[ref] = [1, name, mixin]
                else:
                    seen[0] += 1
                    if seen[2] and not mixin:
                        seen[1], seen[2] = name, False
        for info in nested:
            child = f"{label}!/{info.filename}"
            try:
                with zipfile.ZipFile(io.BytesIO(_bounded_member(archive, info, MAX_NESTED_BYTES))) as inner:
                    self.scan(inner, child, depth + 1)
            except READ_ERRORS as error:
                self.error(f"{child}: {error}")


def _prefix(name: str) -> str:
    return "/".join(name.split("/")[:3])


class _Resolver:
    def __init__(self, index: dict[str, list[ClassInfo]], mixin_members: dict[str, set]):
        self.index = index
        self.mixin_members = mixin_members
        self.cache: dict[tuple, tuple] = {}

    def lookup(self, kind: str, owner: str, member: str, descriptor: str) -> tuple:
        """("ok",) | ("missing",) | ("unresolved", why): a supertype outside the scanned JARs, or a mixin aimed at
        the owner or a supertype declares the member (it may be added at runtime)."""
        key = (kind, owner, member, descriptor)
        hit = self.cache.get(key)
        if hit is not None:
            return hit
        wanted = (member, descriptor)
        queue, seen, outside, targeted = [owner], {owner}, None, None
        result = None
        while queue and result is None:
            name = queue.pop()
            root = JDK_ROOTS.get(name)
            if root is not None:
                if kind == "method" and wanted in root:
                    result = ("ok",)
                continue
            infos = self.index.get(name)
            if not infos:
                outside = outside or name
                continue
            if wanted in self.mixin_members.get(name, ()):
                targeted = targeted or name
            for info in infos:
                if wanted in (info.methods if kind == "method" else info.fields):
                    result = ("ok",)
                    break
                for parent in (info.super, *info.interfaces):
                    if parent and parent not in seen:
                        seen.add(parent)
                        queue.append(parent)
        if result is None:
            result = (("unresolved", outside) if outside else ("unresolved", f"declared by a mixin into {targeted}") if targeted
                      else ("missing",))
        self.cache[key] = result
        return result


def _definer_jars(infos: list[ClassInfo]) -> set[int]:
    return {info.jar for info in infos}


def check_jars(paths, java: int = 21) -> dict:
    """Check member references between the given JARs (plus their nested JARs) for one runtime."""
    started = time.perf_counter()
    scanner = _Scanner(java)
    top = 0
    for path in sorted(Path(item) for item in paths):
        try:
            if path.stat().st_size > MAX_ARCHIVE_BYTES:
                raise ValueError("archive exceeds 512 MiB inspection limit")
            with zipfile.ZipFile(path) as archive:
                scanner.scan(archive, path.name)
            top += 1
        except READ_ERRORS as error:
            scanner.error(f"{path.name}: {error}")
    index, jars = scanner.index, scanner.jars
    resolver = _Resolver(index, scanner.mixin_members)
    problems: dict[tuple, dict] = {}
    unresolved = 0
    reasons: dict[str, int] = {}
    examples: list[dict] = []
    checked = 0

    def report(kind, jar, from_class, owner_jars, owner, member, descriptor, count=1):
        key = (kind, jars[jar], owner, member, descriptor)
        row = problems.get(key)
        if row is None:
            problems[key] = {"kind": kind, "from_jar": jars[jar], "from_class": from_class,
                             "owner_jar": ", ".join(sorted(jars[n] for n in owner_jars)) or None,
                             "owner": owner, "member": member, "descriptor": descriptor, "count": count}
        else:
            row["count"] += count

    def note_unresolved(jar, from_class, owner, member, descriptor, via):
        nonlocal unresolved
        unresolved += 1
        reason = ("declared by a mixin" if via.startswith("declared by a mixin") else
                  "package not shipped" if via.startswith("package not shipped") else "supertype outside the scanned JARs")
        reasons[reason] = reasons.get(reason, 0) + 1
        if len(examples) < MAX_UNRESOLVED_EXAMPLES:
            examples.append({"from_jar": jars[jar], "from_class": from_class, "owner": owner, "member": member,
                             "descriptor": descriptor, "via": via})

    for jar, refs in enumerate(scanner.refs):
        for (kind, owner, member, descriptor), (count, from_class, mixin_only) in refs.items():
            infos = index.get(owner)
            if not infos:
                # A class nobody ships, in a package another scanned JAR defines: NoClassDefFoundError when reached.
                # Only the same package counts: a missing sibling package is usually optional compat code for a mod
                # that is not installed (same group, other artifact), so it is counted as unresolved.
                owners = scanner.packages.get(owner.rpartition("/")[0], set()) - {jar}
                if owners:
                    report("mixin-class-missing" if mixin_only else "class-missing", jar, from_class, owners, owner, "", "", count)
                elif scanner.prefixes.get(_prefix(owner), set()) - {jar}:
                    note_unresolved(jar, from_class, owner, member, descriptor, "package not shipped by any scanned JAR")
                continue
            definers = _definer_jars(infos)
            if jar in definers:
                continue
            checked += 1
            result = resolver.lookup(kind, owner, member, descriptor)
            if result[0] == "ok":
                continue
            if result[0] == "unresolved":
                note_unresolved(jar, from_class, owner, member, descriptor, result[1])
            else:
                report("mixin-missing" if mixin_only else "missing", jar, from_class, definers, owner, member, descriptor, count)

    for name, infos in index.items():
        for info in infos:
            if info.access & (ACC_INTERFACE | ACC_ABSTRACT) or info.mixin:
                continue
            _abstract_check(index, scanner.mixin_members, name, info, report, note_unresolved)

    order = {kind: n for n, kind in enumerate(BLOCKING)}
    rows = sorted(problems.values(), key=lambda row: (order[row["kind"]], row["from_jar"], row["owner"], row["member"]))
    errors = list(scanner.errors)
    if scanner.error_total > len(errors):
        errors.append(f"... {scanner.error_total - len(errors)} more errors")
    return {"jars": top, "nested_jars": len(jars) - top, "classes": scanner.classes, "checked_refs": checked,
            "problems": rows, "unresolved": unresolved, "unresolved_reasons": reasons, "unresolved_examples": examples, "errors": errors,
            "java": java, "seconds": round(time.perf_counter() - started, 2)}


def _abstract_check(index, mixin_members, name, info, report, note_unresolved):
    """A concrete class that implements another JAR's interface but lacks one of its abstract methods throws
    AbstractMethodError when that method is called."""
    concrete = set()
    interfaces = list(info.interfaces)
    leaves = None
    current = info
    seen_supers = {name}
    # A mixin aimed at the class or one of its superclasses that declares the method can add it at runtime, so
    # that gap is unresolved rather than a predicted AbstractMethodError. A prefixed name (mod$method) alone is
    # not evidence: an API may declare such a name itself (an abstract sodium$push, for example).
    mixed = set(mixin_members.get(name, ()))
    while True:
        concrete.update(key for key, access in current.methods.items() if not access & ACC_ABSTRACT)
        parent = current.super
        if parent is None:
            break
        if parent in JDK_ROOTS:
            concrete.update(JDK_ROOTS[parent])
            break
        if parent in seen_supers:
            break
        seen_supers.add(parent)
        candidates = index.get(parent)
        if not candidates:
            leaves = parent
            break
        current = next((item for item in candidates if item.jar == info.jar), candidates[0])
        interfaces.extend(current.interfaces)
        mixed.update(mixin_members.get(parent, ()))
    if not interfaces:
        return
    closure: dict[str, list[ClassInfo]] = {}
    queue = list(interfaces)
    while queue:
        iface = queue.pop()
        if iface in closure or iface.startswith(PLATFORM_PREFIXES):
            continue
        definers = index.get(iface)
        if not definers:
            continue
        closure[iface] = definers
        for item in definers:
            queue.extend(item.interfaces)
    defaults = {key for definers in closure.values() for item in definers
                for key, access in item.methods.items() if not access & (ACC_ABSTRACT | ACC_STATIC)}
    for iface, definers in closure.items():
        owner_jars = {item.jar for item in definers}
        if info.jar in owner_jars:
            continue
        abstract = None
        for item in definers:
            keys = {key for key, access in item.methods.items() if access & ACC_ABSTRACT and not access & ACC_STATIC}
            abstract = keys if abstract is None else abstract & keys
        for member, descriptor in sorted(abstract or ()):
            if (member, descriptor) in concrete or (member, descriptor) in defaults:
                continue
            if leaves:
                note_unresolved(info.jar, name, iface, member, descriptor, leaves)
            elif (member, descriptor) in mixed:
                note_unresolved(info.jar, name, iface, member, descriptor, "declared by a mixin into the class")
            else:
                report("abstract-missing", info.jar, name, owner_jars, iface, member, descriptor)


def check_mods_dir(mods: Path, java: int = 21) -> dict:
    mods = Path(mods)
    if not mods.is_dir():
        raise ValueError(f"mods folder does not exist: {mods}")
    result = check_jars(sorted(mods.glob("*.jar")), java)
    result["mods_dir"] = str(mods)
    return result


def check_instance(instance: Path, java: int = 21) -> dict:
    from .launchers import game_dir
    return check_mods_dir(game_dir(Path(instance)) / "mods", java)


def blocking(result: dict) -> bool:
    return any(row["kind"] in BLOCKING for row in result["problems"])


def summary_lines(result: dict) -> list[str]:
    """Short human report: problems first, one line each."""
    lines = []
    for row in result["problems"]:
        target = row["owner"] + (f".{row['member']}" if row["member"] else "")
        if row["member"]:
            target += row["descriptor"] if row["descriptor"].startswith("(") else f":{row['descriptor']}"
        times = f"  (x{row['count']})" if row["count"] > 1 else ""
        lines.append(f"{row['kind'].upper():<20}{row['from_jar']} -> {row['owner_jar'] or '?'}  {target}{times}")
    lines.append(f"{result['jars']} jars (+{result['nested_jars']} nested), {result['classes']} classes, "
                 f"{result['checked_refs']} cross-jar references checked in {result['seconds']} s")
    reasons = ", ".join(f"{key} {value}" for key, value in sorted(result.get("unresolved_reasons", {}).items()))
    lines.append(f"problems: {len(result['problems'])}; unresolved (not decidable from the JARs): {result['unresolved']}"
                 f"{f' ({reasons})' if reasons else ''}; read errors: {len(result['errors'])}")
    return lines
