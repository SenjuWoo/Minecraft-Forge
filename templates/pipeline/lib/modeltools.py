"""Model: mob/model.py parts -> voxel cubes -> GeckoLib geometry, plus build/model_faces.json (the UV map the
painter reads) and build/model_report.json. `model --validate` checks the cube budget, UV bounds, that every
listed bone carries geometry, and runs the toolkit's independent model-check (z-fighting must be zero)."""
from __future__ import annotations

import json
from dataclasses import dataclass

from . import paths, rigtools
from .sdf import Shape
from .voxel import FACES, Placer, assign_uv, box_part, voxel_blob


@dataclass
class Part:
    name: str
    bone: str
    kind: str                       # "blob" (implicit shape) | "box" (lo, hi)
    mat: str                        # material name in mob/paint.py
    shape: Shape | None = None
    lo: tuple = ()
    hi: tuple = ()
    cell: float = 1.0
    tpp: float = 2
    normal_shape: Shape | None = None   # a smoother shape to shade from (e.g. the union the part belongs to)
    hide: tuple = ()                # faces never shown (plate backs)
    geo: str = ""                   # "" = the main geometry; any other name builds <mob>_<geo>.geo.json with the same bones


def load_parts() -> list[Part]:
    from mob import model as M
    return M.parts()


def build(geo: str = ""):
    parts = [p for p in load_parts() if p.geo == geo]
    placer = Placer()
    cubes, report = [], []
    for p in parts:
        if p.kind == "blob":
            cs, clashes, off = voxel_blob(placer, p.name, p.shape, p.cell, p.bone, p.tpp, p.mat, hide_faces=p.hide)
        else:
            cs, clashes = box_part(placer, p.name, p.lo, p.hi, p.bone, p.tpp, p.mat, faces=[f for f in FACES if f not in p.hide])
            off = 0.0
        cubes += cs
        report.append({"part": p.name, "bone": p.bone, "cubes": len(cs), "clashes": clashes, "offset": round(off, 3)})
    W, H = assign_uv(cubes)
    return parts, cubes, W, H, report


def geo_name(geo: str = "") -> str:
    return paths.MOB + (f"_{geo}" if geo else "")


def geo_json(cubes, W, H, geo: str = "") -> dict:
    from mob import model as M
    m = rigtools.manifest()
    by_bone = {}
    for c in cubes:
        by_bone.setdefault(c.bone, []).append(c)
    bones = []
    for b in m["bones"]:
        e = {"name": b["name"], "pivot": [-b["pivot"][0] + 0.0, b["pivot"][1], b["pivot"][2]]}
        if b["parent"]:
            e["parent"] = b["parent"]
        own = by_bone.pop(b["name"], [])
        if own:
            # Bedrock layout: x mirrored (origin [-x1, y0, z0]); GeckoLib undoes it at load time
            e["cubes"] = [{"origin": [round(-c.hi[0], 4) + 0.0, c.lo[1], c.lo[2]],
                           "size": [round(c.hi[i] - c.lo[i], 4) for i in range(3)],
                           "uv": {f: {"uv": [u, v], "uv_size": [w, h]} for f, (u, v, w, h) in c.uv.items()}} for c in own]
        bones.append(e)
    if by_bone:
        raise ValueError(f"cubes on bones missing from the rig: {sorted(by_bone)}")
    bw, bh, by = M.VISIBLE_BOUNDS
    return {"format_version": "1.12.0", "minecraft:geometry": [{
        "description": {"identifier": f"geometry.{geo_name(geo)}", "texture_width": W, "texture_height": H,
                        "visible_bounds_width": bw, "visible_bounds_height": bh, "visible_bounds_offset": [0, by, 0]},
        "bones": bones}]}


def faces_json(cubes, W, H) -> dict:
    return {"texture": [W, H], "cubes": [{"name": c.name, "blob": c.blob, "bone": c.bone, "lo": c.lo, "hi": c.hi, "tpp": c.tpp,
                                           "mat": c.material, "uv": c.uv} for c in cubes]}


def geos() -> list[str]:
    return sorted({p.geo for p in load_parts()})


def run(args) -> int:
    total = 0
    for geo in geos():
        parts, cubes, W, H, report = build(geo)
        name = geo_name(geo)
        paths.write_json(paths.GEO / f"{name}.geo.json", geo_json(cubes, W, H, geo), compact=True)
        paths.write_json(paths.BUILD / f"{name}_faces.json", faces_json(cubes, W, H), compact=True)
        paths.write_json(paths.BUILD / f"{name}_report.json", report)
        faces = sum(len(c.faces) for c in cubes)
        clashes = sum(r["clashes"] for r in report)
        total += len(cubes)
        print(f"model {name}: {len(parts)} parts, {len(cubes)} cubes, {faces} of {len(cubes) * 6} faces kept, atlas {W}x{H}, "
              f"cross-blob clashes {clashes}")
        big = sorted(report, key=lambda r: -r["cubes"])[:6]
        print("  largest:", ", ".join(f"{r['part']}={r['cubes']}" for r in big))
    return 0


def validate(args) -> int:
    from mob import model as M
    errs = []
    for geo in geos():
        name = geo_name(geo)
        geo_path = paths.GEO / f"{name}.geo.json"
        data = json.loads(geo_path.read_text(encoding="utf-8"))["minecraft:geometry"][0]
        n = sum(len(b.get("cubes", [])) for b in data["bones"])
        if not geo:
            if n > M.CAP:
                errs.append(f"cube count {n} over the hard cap {M.CAP}")
            elif n > M.BUDGET:
                print(f"WARNING: cube count {n} over budget {M.BUDGET} (cap {M.CAP})")
            have = {b["name"] for b in data["bones"] if b.get("cubes")}
            for b in sorted(set(M.MUST_HAVE) - have):
                errs.append(f"bone {b} has no geometry")
        W, H = data["description"]["texture_width"], data["description"]["texture_height"]
        for b in data["bones"]:
            for c in b.get("cubes", []):
                for f, uv in c["uv"].items():
                    u, v = uv["uv"]
                    w, h = uv["uv_size"]
                    if u < 0 or v < 0 or u + w > W or v + h > H:
                        errs.append(f"{name} {b['name']}: {f} UV outside the texture")
        r = paths.forge("model-check", str(geo_path))
        try:
            mc = json.loads(r.stdout)
            zf = mc.get("z_fighting", [])
            print(f"model-check {geo_path.name}: status={mc.get('status')} z_fighting={len(zf)}")
            for z in zf[:6]:
                print("  ", z)
            if zf:
                errs.append(f"{geo_path.name}: {len(zf)} z-fighting pair(s)")
        except (json.JSONDecodeError, AttributeError):
            print((r.stdout or r.stderr or "")[-600:])
            errs.append(f"model-check {geo_path.name} did not run (exit {r.returncode})")
        print(f"model validate {name}: {n} cubes")
    for e in errs[:20]:
        print("MODEL ERROR:", e)
    print(f"model validate: {len(errs)} error(s)")
    return 1 if errs else 0
