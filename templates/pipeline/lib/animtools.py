"""Animation toolkit: pose algebra, clip registry with easing, grounding, key reduction, GeckoLib JSON export,
event ticks as generated Java constants, contact sheets and validators.

A clip is a function of time t in [0, length] returning a pose {bone: [rot deg, pos px, scale]}: offsets that
GeckoLib adds to the rest pose. Clips are sampled, reduced per channel (keys that linear interpolation
reproduces within tolerance are dropped) and grounded when asked. mob/clips.py registers them with @clip.

Conventions (rotation in Blockbench-true degrees; verify the signs once on your rig with `anim sheet`):
JSON writes rotation keys as [-rx, -ry, rz] and position keys as [-px, py, pz].

Rules that save iterations:
- Full-body and locomotion clips are grounded (the lowest leg point sits at y = 0 on every frame). Upper-body
  actions key only upper-body bones and stay ungrounded, so the base controller keeps driving the legs.
- A clip whose point is a fixed contact (a seat, a mount, a prop held by two characters) is grounded once by its
  rest pose (`rest=`), not per frame, or the contact drifts.
- Events (`events={"contact": [0.3]}`) are exported twice: as ticks in gen/<Mob>Clips.java for the server, which
  decides every effect, and on the clip's GeckoLib timeline for client-only reactions (springs, particles).
- Looping clips must end where they start; the validator checks every channel.
- Never key a procedural bone; the validator refuses it.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from . import paths, rigtools

SAMPLE_FPS = 20
ROT_TOL, POS_TOL, SCL_TOL = 0.25, 0.02, 0.003
I3 = (0.0, 0.0, 0.0)
ONE = (1.0, 1.0, 1.0)


# ---------------------------------------------------------------- easing
def clamp01(x):
    return min(1.0, max(0.0, x))


def ease_in_out(x):
    x = clamp01(x)
    return x * x * (3 - 2 * x)


def ease_out(x):
    return 1 - (1 - clamp01(x)) ** 3


def ease_in(x):
    return clamp01(x) ** 3


def back_out(x, s=1.7):
    """Overshoots a little past 1 before settling: anticipation and follow-through for free."""
    x = clamp01(x) - 1
    return x * x * ((s + 1) * x + s) + 1


def smooth_pulse(t, a, b, rise=0.3):
    """0 outside [a, b], eased up to 1 and back down inside it (rise = fraction of the span used to ramp)."""
    if t <= a or t >= b:
        return 0.0
    u = (t - a) / (b - a)
    if u < rise:
        return ease_in_out(u / rise)
    if u > 1 - rise:
        return ease_in_out((1 - u) / rise)
    return 1.0


def osc(t, period, phase=0.0):
    return math.sin(2 * math.pi * (t / period + phase))


# ---------------------------------------------------------------- poses
Pose = dict  # bone -> [rot(3), pos(3), scl(3)]


def add(*poses: Pose, weights=None) -> Pose:
    """Weighted sum of offsets (scale multiplies around 1)."""
    weights = weights or [1.0] * len(poses)
    out: dict = {}
    for p, w in zip(poses, weights):
        for b, (r, q, s) in p.items():
            R0, Q0, S0 = out.get(b, [I3, I3, ONE])
            out[b] = [tuple(R0[i] + w * r[i] for i in range(3)), tuple(Q0[i] + w * q[i] for i in range(3)),
                      tuple(S0[i] * (1 + w * (s[i] - 1)) for i in range(3))]
    return out


def blend(a: Pose, b: Pose, k: float) -> Pose:
    """Linear blend a -> b with factor k (missing bones are rest)."""
    return add(a, b, weights=[1 - k, k])


def keyed(t, keys, ease=ease_in_out):
    """Interpolate a list of (time, Pose) with easing between neighbours."""
    if t <= keys[0][0]:
        return keys[0][1]
    for (t0, p0), (t1, p1) in zip(keys, keys[1:]):
        if t <= t1:
            return blend(p0, p1, ease((t - t0) / (t1 - t0) if t1 > t0 else 1.0))
    return keys[-1][1]


def R(b, x=0.0, y=0.0, z=0.0) -> Pose:
    return {b: [(x, y, z), I3, ONE]}


def T(b, x=0.0, y=0.0, z=0.0) -> Pose:
    return {b: [I3, (x, y, z), ONE]}


def S(b, x=1.0, y=1.0, z=1.0) -> Pose:
    return {b: [I3, I3, (x, y, z)]}


def sides(fn) -> Pose:
    """Apply a side builder to both sides: fn(suffix, sign) with sign -1 for the left."""
    return add(fn("l", -1), fn("r", 1))


# ---------------------------------------------------------------- clip registry
@dataclass
class Clip:
    name: str
    length: float
    fn: Callable[[float], Pose]
    loop: object = True                 # True | False | "hold_on_last_frame"
    ground: str | None = "legs"         # None | "legs" (the rig's LEGS) | "all"
    events: dict = field(default_factory=dict)   # name -> [seconds]
    group: str = "base"
    fps: int = SAMPLE_FPS
    air: Callable[[float], float] | None = None   # root height (px) added after grounding: jumps and falls
    rest: Callable[[], Pose] | None = None        # ground once by this pose instead of per frame


CLIPS: dict[str, Clip] = {}


def clip(name, length, loop=True, ground="legs", events=None, group="base", fps=SAMPLE_FPS, air=None, rest=None):
    def deco(fn):
        CLIPS[name] = Clip(name, length, fn, loop, ground, events or {}, group, fps, air, rest)
        return fn
    return deco


def load_clips():
    import mob.clips  # noqa: F401  (its @clip registrations run on import)
    return CLIPS


# ---------------------------------------------------------------- sampling, grounding, reduction
_MODEL = None


def model():
    """The built geometry, loaded once (for grounding, IK and sheets)."""
    global _MODEL
    if _MODEL is None:
        from .render import Model
        tex = paths.TEX / f"{paths.MOB}.png"
        _MODEL = Model(paths.GEO / f"{paths.MOB}.geo.json", tex if tex.exists() else None)
    return _MODEL


def as_tuples(p: Pose) -> dict:
    return {b: (tuple(v[0]), tuple(v[1]), tuple(v[2])) for b, v in p.items()}


def default_hidden() -> set:
    """Swap-group members other than the first are hidden in previews and grounding."""
    m = rigtools.manifest()
    return {b for members in m["swap_groups"].values() for b in members[1:]}


def lowest(p: Pose, mode: str) -> float:
    m = rigtools.manifest()
    return model().lowest_point(as_tuples(p), m["legs"] if mode == "legs" else None, default_hidden())


def sample(c: Clip):
    n = max(2, int(round(c.length * c.fps)) + 1)
    times = [c.length * i / (n - 1) for i in range(n)]
    rest_low = lowest(c.rest(), c.ground or "legs") if c.rest is not None else None
    frames = []
    for t in times:
        p = dict(c.fn(t))
        lift = 0.0
        if c.ground:
            lift -= rest_low if rest_low is not None else lowest(p, c.ground)
        if c.air:
            lift += c.air(t)
        if lift:
            r, q, s = p.get("root", [I3, I3, ONE])
            p["root"] = [r, (q[0], q[1] + lift, q[2]), s]
        frames.append(p)
    return times, frames


def _reduce(times, vals, tol):
    """Indices of the keys to keep: a key is dropped when linear interpolation of its neighbours reproduces it."""
    keep = [0]
    for i in range(1, len(times) - 1):
        a, b = keep[-1], i + 1
        for j in range(a + 1, i + 1):
            u = (times[j] - times[a]) / (times[b] - times[a])
            if max(abs(vals[a][k] + (vals[b][k] - vals[a][k]) * u - vals[j][k]) for k in range(3)) > tol:
                keep.append(i)
                break
    keep.append(len(times) - 1)
    return keep


def _key(t):
    return f"{t:.4f}".rstrip("0").rstrip(".") if t else "0.0"


def to_json(c: Clip, times, frames):
    bones = sorted({b for f in frames for b in f})
    out = {}
    for b in bones:
        chans = {}
        for ci, key, tol in ((0, "rotation", ROT_TOL), (1, "position", POS_TOL), (2, "scale", SCL_TOL)):
            vals = [tuple(f.get(b, [I3, I3, ONE])[ci]) for f in frames]
            neutral = ONE if ci == 2 else I3
            if all(max(abs(v[k] - neutral[k]) for k in range(3)) < tol for v in vals):
                continue
            kf = {}
            for i in _reduce(times, vals, tol):
                v = vals[i]
                if ci == 0:
                    w = [round(-v[0], 3) + 0.0, round(-v[1], 3) + 0.0, round(v[2], 3) + 0.0]
                elif ci == 1:
                    w = [round(-v[0], 4) + 0.0, round(v[1], 4) + 0.0, round(v[2], 4) + 0.0]
                else:
                    w = [round(v[0], 4), round(v[1], 4), round(v[2], 4)]
                kf[_key(times[i])] = w
            chans[key] = kf
        if chans:
            out[b] = chans
    body = {"loop": c.loop, "animation_length": round(c.length, 4), "bones": out}
    # events also go on the GeckoLib instruction timeline ("name#index;") for client-only reactions
    timeline = {}
    for ev, ts in sorted(c.events.items()):
        for i, t in enumerate(ts):
            timeline[_key(t)] = timeline.get(_key(t), "") + f"{ev}#{i};"
    if timeline:
        body["timeline"] = dict(sorted(timeline.items(), key=lambda kv: float(kv[0])))
    return body


def java_clips(clips) -> str:
    cls = paths.PASCAL + "Clips"
    lines = ["// GENERATED by asset-pipeline/lib/animtools.py - do not edit; change mob/clips.py and rerun `build_assets.py anim`.",
             f"package {paths.PACKAGE}.gen;", "", "import java.util.List;", "import java.util.Map;", "",
             f"/** Clip names, lengths and event ticks of the {paths.MOB} animations (server timing reads these, never the client). */",
             f"public final class {cls} {{", f"    private {cls}() {{}}", ""]
    for c in clips:
        cn = c.name.upper()
        lines.append(f'    public static final String {cn} = "{c.name}";')
        lines.append(f"    public static final int {cn}_TICKS = {int(round(c.length * 20))};")
        for ev, ts in sorted(c.events.items()):
            lines.append(f"    public static final int[] {cn}_{ev.upper()} = {{{', '.join(str(int(round(x * 20))) for x in ts)}}};")
    one = [c.name.upper() for c in clips if c.loop is not True]
    loops = [c.name.upper() for c in clips if c.loop is True]
    lines += ["", "    /** Clips that play once (trigger them on an action controller). */",
              f"    public static final List<String> ONE_SHOT = List.of({', '.join(one)});",
              f"    public static final List<String> LOOPING = List.of({', '.join(loops)});", "",
              "    public static final Map<String, Integer> LENGTH_TICKS = Map.ofEntries(",
              ",\n".join(f"            Map.entry({c.name.upper()}, {c.name.upper()}_TICKS)" for c in clips) + ");", "}"]
    return "\n".join(lines) + "\n"


def run(args) -> int:
    clips = load_clips()
    anims = {}
    for name, c in clips.items():
        times, frames = sample(c)
        anims[name] = to_json(c, times, frames)
    target = paths.ANIM / f"{paths.MOB}.animation.json"
    paths.write_json(target, {"format_version": "1.8.0", "animations": anims}, compact=True)
    paths.write_text(paths.JAVA_GEN / f"{paths.PASCAL}Clips.java", java_clips(list(clips.values())))
    groups = {}
    for c in clips.values():
        groups.setdefault(c.group, []).append(c.name)
    print(f"anim: {len(anims)} clips, {target.stat().st_size // 1024} KiB; " + ", ".join(f"{g}: {len(n)}" for g, n in groups.items()))
    rest = getattr(args, "rest", []) or []
    if "sheet" in rest:
        contact_sheets(groups=[r for r in rest if r != "sheet"] or None)
    return 0


def contact_sheets(groups=None, frames_per_clip=6, yaw=30.0):
    """media/anim/<group>_contact.png: six frames of every clip under game lighting. Look at them before the client."""
    from .render import render, sheet
    m = model()
    hidden = default_hidden()
    by_group = {}
    for c in load_clips().values():
        if not groups or c.group in groups:
            by_group.setdefault(c.group, []).append(c)
    for g, clips in by_group.items():
        ims, labs = [], []
        for c in clips:
            times, frames = sample(c)
            for k in np.linspace(0, len(frames) - 1, frames_per_clip).astype(int):
                ims.append(render(m, yaw, 8, 5.0, size=(220, 260), pose=as_tuples(frames[k]), hidden=hidden, center=(0, 14)))
                labs.append(f"{c.name} {times[k]:.2f}")
        out = paths.MEDIA / "anim" / f"{g}_contact.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        sheet(ims, labs, cols=frames_per_clip).save(out)
        print(f"sheet: {out} ({len(clips)} clips)")


def validate(args) -> int:
    clips = load_clips()
    anim = json.loads((paths.ANIM / f"{paths.MOB}.animation.json").read_text(encoding="utf-8"))
    errs = rigtools.check_clip_bones(rigtools.load_manifest(), anim)
    for name, body in anim["animations"].items():
        if body.get("loop") is True:
            for bone, chans in body["bones"].items():
                for key, kf in chans.items():
                    ks = sorted(kf, key=float)
                    a, b = kf[ks[0]], kf[ks[-1]]
                    tol = {"rotation": 1.0, "position": 0.05, "scale": 0.01}[key]
                    if float(ks[0]) == 0.0 and abs(float(ks[-1]) - body["animation_length"]) < 1e-3:
                        if max(abs(a[i] - b[i]) for i in range(3)) > tol:
                            errs.append(f"{name}: {bone}.{key} does not loop ({a} vs {b})")
        for t in body.get("timeline", {}):
            if float(t) > body["animation_length"] + 1e-6:
                errs.append(f"{name}: event at {t}s is after the clip ends")
    src = (paths.JAVA_GEN / f"{paths.PASCAL}Clips.java").read_text(encoding="utf-8")
    for name in anim["animations"]:
        if f'"{name}"' not in src:
            errs.append(f"{paths.PASCAL}Clips.java lacks {name}")
    # grounded clips: the lowest leg point really is on the floor at every sampled frame
    for c in clips.values():
        if c.ground and c.rest is None and c.air is None:
            times, frames = sample(c)
            worst = max(abs(lowest(f, c.ground)) for f in frames)
            if worst > 0.05:
                errs.append(f"{c.name}: grounding is off by {worst:.3f} px")
    for e in errs[:40]:
        print("ANIM ERROR:", e)
    print(f"anim validate: {len(anim['animations'])} clips, {len(errs)} error(s)")
    return 1 if errs else 0
