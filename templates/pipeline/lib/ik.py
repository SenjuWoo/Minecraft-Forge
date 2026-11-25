"""Inverse kinematics on the real rig, so contact is solved instead of hand-keyed.

two_bone() puts the end point of a two-bone limb (arm + forearm, thigh + shin) on a target in model space for
the body pose of that frame; bone_point() says where any rest-pose point of a bone is under a pose (the target
for "hand on knee", "paw on the ground", "muzzle to the bowl"). Hands that must stay planted while the body moves
are re-solved every frame from the same world target.

Reaching further than the limb is long gives the straight limb pointed at the target: add body motion (a lean, a
dropped shoulder, a twist toward that side) to the pose first, as a person would.
"""
from __future__ import annotations

import math

import numpy as np

from . import animtools as A
from .render import R as rot_matrix

_CACHE: dict = {}


def bone_point(pose, bone: str, rest_point) -> tuple:
    """Where a point given in rest model coordinates (px) ends up under the pose."""
    v = A.model().bone_matrix(A.as_tuples(pose or {}), bone) @ np.array([*rest_point, 1.0])
    return tuple(float(x) for x in v[:3])


def bone_box(bone: str):
    """Rest-pose bounds (lo, hi) of a bone's own cubes."""
    cubes = A.model().bones[bone]["cubes"]
    return (tuple(min(c[0][i] for c in cubes) for i in range(3)), tuple(max(c[1][i] for c in cubes) for i in range(3)))


def _euler_zyx(Q):
    """Degrees (x, y, z) with Q = Rz @ Ry @ Rx (GeckoLib's order)."""
    b = math.asin(max(-1.0, min(1.0, -Q[2, 0])))
    if abs(math.cos(b)) > 1e-6:
        return math.degrees(math.atan2(Q[2, 1], Q[2, 2])), math.degrees(b), math.degrees(math.atan2(Q[1, 0], Q[0, 0]))
    return math.degrees(math.atan2(-Q[1, 2], Q[1, 1])), math.degrees(b), 0.0


def _frame(a, b):
    """Orthonormal frame with first axis a and second axis b made perpendicular to it (columns)."""
    a = a / np.linalg.norm(a)
    b = b - a * (a @ b)
    b = b / np.linalg.norm(b)
    return np.stack([a, b, np.cross(a, b)], axis=1)


def _side(v, axis):
    """The part of v perpendicular to axis, normalised; None when v runs along the axis."""
    a = np.asarray(axis, float)
    a = a / max(np.linalg.norm(a), 1e-9)
    p = np.asarray(v, float) - a * (a @ np.asarray(v, float))
    n = float(np.linalg.norm(p))
    return p / n if n > 1e-5 else None


def two_bone(upper: str, lower: str, end_point, target, pose=None, pole=(0.0, 0.0, 1.0), flex=(-150.0, 0.0)) -> dict:
    """Rotations for `upper` and `lower` that put `end_point` (rest coordinates, e.g. the palm or the sole) on `target`.

    The middle joint flexes about its local X axis within `flex` degrees (the bend comes from the distance, by
    bisection on the limb's own geometry); the upper bone then aligns the solved chain with the target and turns
    the middle joint toward `pole` (model space: where the elbow or knee should point). Returns a Pose to add().

    The joint's side is measured from the solved limb itself, so the pole means the same thing for either sign of
    `flex` (before 1.5.0 a negative flex range turned the joint away from the pole; a pole that was mirrored to get
    the right knee must be un-mirrored).
    """
    m = A.model()
    pose = pose or {}
    parent = m.bones[upper]["parent"]
    chain = tuple((b, tuple(round(v, 1) for v in pose[b][0]), tuple(round(v, 2) for v in pose[b][1])) for b in m.chain(parent) if b in pose)
    key = (upper, lower, tuple(round(x, 2) for x in end_point), tuple(round(x, 2) for x in target), chain, tuple(pole), tuple(flex))
    if key in _CACHE:
        return _CACHE[key]
    U, L = m.bones[upper], m.bones[lower]
    S0, E0, P0 = np.array(U["pivot"]), np.array(L["pivot"]), np.array(end_point, float)
    Mp = m.bone_matrix(A.as_tuples(pose), parent) if parent else np.eye(4)
    Rp = Mp[:3, :3]
    start = (Mp @ np.array([*S0, 1.0]))[:3]
    inv = np.linalg.inv(Rp)
    tl = inv @ (np.array(target, float) - start)          # target in the parent's frame
    pl = inv @ np.array(pole, float)
    D = float(np.linalg.norm(tl))
    up, lo = E0 - S0, P0 - E0

    def reach(theta):
        return float(np.linalg.norm(up + rot_matrix(theta, 0, 0)[:3, :3] @ lo))

    a, b = flex
    if (reach(a) - D) * (reach(b) - D) > 0:               # out of range: the closer end of the flex range
        theta = a if abs(reach(a) - D) < abs(reach(b) - D) else b
    else:
        ra = reach(a)
        for _ in range(40):
            mid = (a + b) / 2
            if (reach(mid) - D) * (ra - D) > 0:
                a, ra = mid, reach(mid)
            else:
                b = mid
        theta = (a + b) / 2
    w = up + rot_matrix(theta, 0, 0)[:3, :3] @ lo          # start -> end in the upper bone's rest frame
    t_hat = tl / max(D, 1e-6)
    knee = _side(up, w)                                    # where the middle joint sits off the start -> end line
    if knee is None:                                       # a straight limb: the side it would bend to
        probe = flex[0] if abs(flex[0]) > abs(flex[1]) else flex[1]
        knee = _side(up, up + rot_matrix(probe * 0.5, 0, 0)[:3, :3] @ lo)
    want = _side(pl, t_hat)                                # the pole, perpendicular to the target line
    if want is None:
        want = _side(np.array([0.0, 0.0, -1.0]), t_hat) if abs(t_hat[2]) < 0.99 else np.array([0.0, 1.0, 0.0])
    if knee is None:
        Q = _frame(t_hat, want) @ _frame(w, np.array([1.0, 0.0, 0.0])).T
    else:
        Q = _frame(t_hat, want) @ _frame(w, knee).T         # start -> end onto the target line, joint side onto the pole
    rest = U["rest"]
    # the representative nearest the rest pose: blends from rest and additive offsets then take the short way round
    ex, ey, ez = A.nearest_euler(_euler_zyx(Q), tuple(rest))
    out = A.add(A.R(upper, ex - rest[0], ey - rest[1], ez - rest[2]), A.R(lower, theta))
    _CACHE[key] = out
    return out


def two_bone_blend(upper, lower, end_point, target, pose, k, rest_pose=None, **kw) -> dict:
    """Blend from `rest_pose` (default: the limb at rest) to the IK solution by k (0..1): reaching and letting go.

    The solution's upper rotation is taken as the Euler representative nearest the start, so the blend takes the short
    path. A linear blend still moves the hand on an arc of its own: when the in-between path must clear the body,
    move the target along a model-space path instead and solve two_bone() every frame."""
    rest_pose = rest_pose or {}
    if k <= 1e-3:
        return rest_pose
    solved = two_bone(upper, lower, end_point, target, pose, **kw)
    if upper in rest_pose:
        rest = A.model().bones[upper]["rest"]
        start = tuple(rest[i] + rest_pose[upper][0][i] for i in range(3))
        r, q, s = solved[upper]
        near = A.nearest_euler(tuple(rest[i] + r[i] for i in range(3)), start)
        solved = dict(solved)
        solved[upper] = [tuple(near[i] - rest[i] for i in range(3)), q, s]
    return A.blend(rest_pose, solved, k)
