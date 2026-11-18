"""The animation clips of this mob. Each @clip function returns a pose for time t: offsets (degrees, pixels,
scale) that GeckoLib adds to the rest pose. lib/animtools.py samples, grounds, reduces and exports them.

Sign conventions on this rig (check them once with `build_assets.py anim sheet` when you change the rig):
  thigh forward +rotX, knee bend (shin back) -rotX, torso bend forward -rotX, head up +rotX,
  turn to the model's left +rotY, arm_r outward +rotZ, arm_l outward -rotZ.

What reads as alive at Minecraft scale:
- Overlap: let the torso, arms and head lag the hips by a fraction of the cycle instead of moving together.
- Asymmetry: weight on one leg at rest, a hip pop once per idle loop, slightly different arm swing per side.
- Anticipation and follow-through on every action: a wind-up before the strike (back_out easing) and a settle
  after it; the contact frame is a tick the server knows (events), the rest is free.
- Springs do the secondary motion (ears, tail): do not key those bones.
"""
from lib.animtools import R, S, T, add, back_out, clip, ease_in, ease_out, keyed, osc, sides, smooth_pulse  # noqa: F401

import math


def stance(t=0.0) -> dict:
    """Relaxed stand: a slow breath, arms loose, weight slightly on the right leg."""
    br = osc(t, 4.0)
    return add(R("torso", 1.0 + 0.8 * br, 0, 1.5), R("head", -1.0 + 0.5 * br),
               R("arm_l", 3, 0, -6), R("arm_r", 3, 0, 6), R("forearm_l", -8), R("forearm_r", -8),
               R("thigh_l", 2, 0, -1.5), R("shin_l", -4), R("hips", 0, 0, -1.5))


@clip("idle", 4.0)
def _idle(t):
    look = smooth_pulse(t, 1.4, 2.8, 0.35)          # a glance to one side once per loop
    return add(stance(t), R("head", 0, 14 * look, 2 * look), R("torso", 0, 4 * look, 0))


WALK_PERIOD = 1.0


@clip("walk", WALK_PERIOD, events={"step_l": [WALK_PERIOD * 0.25], "step_r": [WALK_PERIOD * 0.75]})
def _walk(t):
    ph = (t / WALK_PERIOD) % 1.0
    s = math.sin(2 * math.pi * ph)
    p = []
    for side, sign, off in (("l", -1, 0.0), ("r", 1, 0.5)):
        q = (ph + off) % 1.0
        swing = math.sin(2 * math.pi * q)
        lift = max(0.0, math.sin(2 * math.pi * q + math.pi * 0.35))
        p += [R(f"thigh_{side}", 26 * swing, 0, sign * 2), R(f"shin_{side}", -(10 + 34 * lift)),
              R(f"arm_{side}", -14 * swing, 0, sign * 6), R(f"forearm_{side}", -14 - 8 * max(0, swing))]
    # hips are lowest at double support and highest when the legs pass; grounding supplies the bob itself
    p += [R("hips", 0, 7 * s, -4 * s), R("torso", -3, -6 * s, 2.5 * s), R("head", 2, 4 * s, -1.5 * s), R("tail", -6, -8 * s, 0)]
    return add(*p)


ATTACK = 0.7


@clip("attack", ATTACK, loop=False, ground=None, events={"contact": [0.3]}, group="action")
def _attack(t):
    """Right-arm swipe: wind up for 0.2 s, strike at 0.3 s, settle. Upper body only, so the walk keeps the legs."""
    wind = smooth_pulse(t, 0.0, 0.26, 0.5)
    strike = back_out((t - 0.2) / 0.12) if t > 0.2 else 0.0
    settle = 1 - ease_out((t - 0.4) / 0.3) if t > 0.4 else 1.0
    k = strike * settle
    return add(R("torso", -6 * k + 4 * wind, -28 * k + 16 * wind, 0),
               R("arm_r", -95 * k + 40 * wind, 0, 18 * wind + 10 * k), R("forearm_r", -20 - 30 * wind + 10 * k),
               R("arm_l", 12 * k, 0, -8 * k), R("head", 4 * k, 10 * k, 0))


@clip("hurt", 0.4, loop=False, ground=None, group="action")
def _hurt(t):
    k = smooth_pulse(t, 0.0, 0.4, 0.3)
    return add(R("torso", 12 * k, 0, 5 * k), R("head", 16 * k, 0, -6 * k), R("arm_l", -18 * k, 0, -22 * k), R("arm_r", -18 * k, 0, 22 * k))


DEATH = 1.5


@clip("death", DEATH, loop="hold_on_last_frame", ground="all", group="base")
def _death(t):
    """Knees give way, then the body tips forward. Grounded on everything, so it lies on the floor."""
    k = ease_in(t / 0.6)
    fall = ease_out((t - 0.45) / 0.8) if t > 0.45 else 0.0
    return add(sides(lambda sd, sg: add(R(f"thigh_{sd}", 50 * k * (1 - fall) + 10 * fall, 0, sg * 6 * fall),
                                         R(f"shin_{sd}", -80 * k * (1 - fall) - 8 * fall),
                                         R(f"arm_{sd}", -30 * fall, 0, sg * 50 * fall))),
               R("root", 86 * fall, 0, 0), R("head", 10 * fall, 12 * fall, 0), T("root", 0, 0, 6 * fall))
