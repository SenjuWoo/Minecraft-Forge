"""Gzip NBT writer and reader (standard library only) and a structure-template builder.

Structures (a den, a camp, a shrine the mob lives in) and GameTest arenas are generated like every other asset:
structure(size, blocks) -> data/<mod>/structure/<name>.nbt. Values are typed explicitly with the wrappers below
so the file matches what StructureTemplate.load expects. DATA_VERSION is the world version of the target game
(3955 = Minecraft 1.21.1, SharedConstants.WORLD_VERSION); change it with the target.
"""
from __future__ import annotations

import gzip
import io
import struct

END, BYTE, SHORT, INT, LONG, FLOAT, DOUBLE, BYTE_ARRAY, STRING, LIST, COMPOUND, INT_ARRAY, LONG_ARRAY = range(13)
DATA_VERSION = 3955


class Tag:
    tid = None

    def __init__(self, v):
        self.v = v

    def __eq__(self, o):
        return type(self) is type(o) and self.v == o.v

    def __repr__(self):
        return f"{type(self).__name__}({self.v!r})"


class Byte(Tag):
    tid = BYTE


class Short(Tag):
    tid = SHORT


class Int(Tag):
    tid = INT


class Long(Tag):
    tid = LONG


class Float(Tag):
    tid = FLOAT


class Double(Tag):
    tid = DOUBLE


class String(Tag):
    tid = STRING


class IntArray(Tag):
    tid = INT_ARRAY


class List(Tag):
    tid = LIST

    def __init__(self, items, elem=None):
        super().__init__(list(items))
        self.elem = elem if elem is not None else (self.v[0].tid if self.v else END)


class Compound(Tag):
    tid = COMPOUND

    def __init__(self, d=None):
        super().__init__(dict(d or {}))


_FORMATS = {BYTE: ">b", SHORT: ">h", INT: ">i", LONG: ">q", FLOAT: ">f", DOUBLE: ">d"}


def _str(b, s):
    e = s.encode("utf-8")
    b.write(struct.pack(">H", len(e)))
    b.write(e)


def _payload(b, t):
    if t.tid in _FORMATS:
        b.write(struct.pack(_FORMATS[t.tid], t.v))
    elif isinstance(t, String):
        _str(b, t.v)
    elif isinstance(t, IntArray):
        b.write(struct.pack(">i", len(t.v)))
        b.write(struct.pack(f">{len(t.v)}i", *t.v))
    elif isinstance(t, List):
        b.write(struct.pack(">bi", t.elem, len(t.v)))
        for x in t.v:
            if x.tid != t.elem:
                raise TypeError("a list holds one tag type")
            _payload(b, x)
    elif isinstance(t, Compound):
        for k, x in t.v.items():
            b.write(struct.pack(">b", x.tid))
            _str(b, k)
            _payload(b, x)
        b.write(b"\x00")
    else:
        raise TypeError(t)


def dumps(root: Compound, name="") -> bytes:
    b = io.BytesIO()
    b.write(struct.pack(">b", COMPOUND))
    _str(b, name)
    _payload(b, root)
    return gzip.compress(b.getvalue(), mtime=0)   # mtime 0: the same input gives the same bytes


def _read(b, tid):
    def rd(fmt):
        return struct.unpack(fmt, b.read(struct.calcsize(fmt)))[0]
    if tid in _FORMATS:
        return {BYTE: Byte, SHORT: Short, INT: Int, LONG: Long, FLOAT: Float, DOUBLE: Double}[tid](rd(_FORMATS[tid]))
    if tid == STRING:
        return String(b.read(rd(">H")).decode("utf-8"))
    if tid == INT_ARRAY:
        n = rd(">i")
        return IntArray(list(struct.unpack(f">{n}i", b.read(4 * n))))
    if tid == LIST:
        e, n = rd(">b"), rd(">i")
        return List([_read(b, e) for _ in range(n)], e)
    if tid == COMPOUND:
        d = {}
        while True:
            t = rd(">b")
            if t == END:
                return Compound(d)
            k = b.read(rd(">H")).decode("utf-8")
            d[k] = _read(b, t)
    raise ValueError(f"unsupported tag {tid}")


def loads(data: bytes) -> Compound:
    b = io.BytesIO(gzip.decompress(data))
    if struct.unpack(">b", b.read(1))[0] != COMPOUND:
        raise ValueError("root is not a compound")
    b.read(struct.unpack(">H", b.read(2))[0])
    return _read(b, COMPOUND)


def structure(size, blocks, entities=()) -> Compound:
    """A structure template. blocks: {(x, y, z): "minecraft:stone"} or {(x, y, z): ("minecraft:oak_stairs", {"facing": "north"})};
    positions not listed stay as they are in the world (use "minecraft:air" to clear, "minecraft:structure_void" to keep).
    entities: [(x, y, z, Compound)] with the entity's own NBT (must contain "id")."""
    palette, index, rows = [], {}, []
    for (x, y, z), state in sorted(blocks.items(), key=lambda kv: (kv[0][1], kv[0][2], kv[0][0])):
        name, props = state if isinstance(state, tuple) else (state, {})
        key = (name, tuple(sorted(props.items())))
        if key not in index:
            index[key] = len(palette)
            entry = {"Name": String(name)}
            if props:
                entry["Properties"] = Compound({k: String(str(v)) for k, v in sorted(props.items())})
            palette.append(Compound(entry))
        if not all(0 <= c < s for c, s in zip((x, y, z), size)):
            raise ValueError(f"block {(x, y, z)} is outside the structure size {size}")
        rows.append(Compound({"pos": List([Int(x), Int(y), Int(z)]), "state": Int(index[key])}))
    ents = [Compound({"pos": List([Double(x), Double(y), Double(z)]), "blockPos": List([Int(int(x)), Int(int(y)), Int(int(z))]), "nbt": nbt})
            for x, y, z, nbt in entities]
    return Compound({"DataVersion": Int(DATA_VERSION), "size": List([Int(v) for v in size]), "palette": List(palette, COMPOUND),
                     "blocks": List(rows, COMPOUND), "entities": List(ents, COMPOUND)})


def selftest() -> bool:
    root = structure((3, 2, 3), {(0, 0, 0): "minecraft:stone", (1, 0, 1): ("minecraft:oak_stairs", {"facing": "north"})})
    root.v.update({"f": Float(1.5), "d": Double(-2.25), "l": Long(1 << 40), "s": Short(-3), "b": Byte(1), "ia": IntArray([1, -2, 3])})
    return loads(dumps(root)) == root and dumps(root) == dumps(root)
