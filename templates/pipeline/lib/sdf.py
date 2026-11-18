"""Vectorised implicit shapes (numpy). A shape is a callable f(X, Y, Z) -> array, negative inside.

Coordinates are Blockbench model pixels (y up, front -Z, +X = the model's own right side). Values are not true
distances (superellipsoids are normalised implicit functions); they are compared with 0, used for gradients
(normals) and for a soft ambient-occlusion estimate, so a consistent scale near the surface is enough.
Every constructor returns a Shape with .f and .bounds ((x0, y0, z0), (x1, y1, z1)).

Modelling notes:
- superellipsoid n > 2 gives squarer, chunkier forms that read well as Minecraft cubes; n = 2 is an ellipsoid.
- smooth_union k 0.3-0.8 blends parts softly (shoulders into torso); a plain union keeps a crease.
- Cut lines (hems, collars, openings) are intersect/subtract with a halfspace or a second shape, not paint.
- A thin shell around a body (clothing, gel) is inflate(body, d) minus the body or simply the inflated shape on its
  own layer; 0.35-0.9 px reads as a separate layer without looking padded.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np


@dataclass
class Shape:
    f: Callable
    bounds: tuple

    def __call__(self, X, Y, Z):
        return self.f(X, Y, Z)


def _b(lo, hi):
    return (tuple(float(v) for v in lo), tuple(float(v) for v in hi))


def ellipsoid(c, r) -> Shape:
    c, r = np.asarray(c, float), np.asarray(r, float)
    k = float(r.min())

    def f(X, Y, Z):
        q = np.sqrt(((X - c[0]) / r[0]) ** 2 + ((Y - c[1]) / r[1]) ** 2 + ((Z - c[2]) / r[2]) ** 2)
        return (q - 1.0) * k
    return Shape(f, _b(c - r, c + r))


def superellipsoid(c, r, n=2.5) -> Shape:
    c, r = np.asarray(c, float), np.asarray(r, float)
    k = float(r.min())

    def f(X, Y, Z):
        q = (np.abs((X - c[0]) / r[0]) ** n + np.abs((Y - c[1]) / r[1]) ** n + np.abs((Z - c[2]) / r[2]) ** n) ** (1.0 / n)
        return (q - 1.0) * k
    return Shape(f, _b(c - r, c + r))


def capsule(a, b, ra, rb=None, squash=(1.0, 1.0, 1.0)) -> Shape:
    """Tapered round capsule a->b; squash scales the radial distance per axis (e.g. (1, 1, 0.8) flattens in z)."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    rb = ra if rb is None else rb
    s = np.asarray(squash, float)
    d = b - a
    L2 = float(d @ d) or 1e-9

    def f(X, Y, Z):
        px, py, pz = X - a[0], Y - a[1], Z - a[2]
        t = np.clip((px * d[0] + py * d[1] + pz * d[2]) / L2, 0.0, 1.0)
        qx, qy, qz = (px - t * d[0]) / s[0], (py - t * d[1]) / s[1], (pz - t * d[2]) / s[2]
        r = ra + (rb - ra) * t
        return np.sqrt(qx * qx + qy * qy + qz * qz) - r
    big = max(ra, rb) * float(s.max())
    return Shape(f, _b(np.minimum(a, b) - big, np.maximum(a, b) + big))


def box(lo, hi, round_=0.0) -> Shape:
    lo, hi = np.asarray(lo, float), np.asarray(hi, float)
    c, h = (lo + hi) / 2, (hi - lo) / 2 - round_

    def f(X, Y, Z):
        qx, qy, qz = np.abs(X - c[0]) - h[0], np.abs(Y - c[1]) - h[1], np.abs(Z - c[2]) - h[2]
        out = np.sqrt(np.maximum(qx, 0) ** 2 + np.maximum(qy, 0) ** 2 + np.maximum(qz, 0) ** 2)
        inside = np.minimum(np.maximum(qx, np.maximum(qy, qz)), 0)
        return out + inside - round_
    return Shape(f, _b(lo, hi))


def torus(c, major, minor, axis="y", squash=1.0) -> Shape:
    """Ring around `axis` through c: major radius to the tube centre, minor the tube radius (squash flattens the tube
    along the axis)."""
    c = np.asarray(c, float)
    a = "xyz".index(axis)
    b1, b2 = [i for i in range(3) if i != a]

    def f(X, Y, Z):
        p = (X - c[0], Y - c[1], Z - c[2])
        q = np.sqrt(p[b1] * p[b1] + p[b2] * p[b2]) - major
        return np.sqrt(q * q + (p[a] / squash) ** 2) - minor
    reach = np.full(3, major + minor)
    reach[a] = minor * squash
    return Shape(f, _b(c - reach, c + reach))


def union(*shapes) -> Shape:
    def f(X, Y, Z):
        v = shapes[0](X, Y, Z)
        for s in shapes[1:]:
            v = np.minimum(v, s(X, Y, Z))
        return v
    lo = np.min([s.bounds[0] for s in shapes], axis=0)
    hi = np.max([s.bounds[1] for s in shapes], axis=0)
    return Shape(f, _b(lo, hi))


def smooth_union(k, *shapes) -> Shape:
    def f(X, Y, Z):
        v = shapes[0](X, Y, Z)
        for s in shapes[1:]:
            w = s(X, Y, Z)
            h = np.clip(0.5 + 0.5 * (w - v) / k, 0.0, 1.0)
            v = w * (1 - h) + v * h - k * h * (1 - h)
        return v
    lo = np.min([s.bounds[0] for s in shapes], axis=0) - k
    hi = np.max([s.bounds[1] for s in shapes], axis=0) + k
    return Shape(f, _b(lo, hi))


def subtract(keep: Shape, *cuts: Shape) -> Shape:
    def f(X, Y, Z):
        v = keep(X, Y, Z)
        for c in cuts:
            v = np.maximum(v, -c(X, Y, Z))
        return v
    return Shape(f, keep.bounds)


def smooth_subtract(k, keep: Shape, cut: Shape) -> Shape:
    def f(X, Y, Z):
        a, b = keep(X, Y, Z), -cut(X, Y, Z)
        h = np.clip(0.5 - 0.5 * (b - a) / k, 0.0, 1.0)
        return b * (1 - h) + a * h + k * h * (1 - h)
    return Shape(f, keep.bounds)


def intersect(a: Shape, *others: Shape) -> Shape:
    def f(X, Y, Z):
        v = a(X, Y, Z)
        for o in others:
            v = np.maximum(v, o(X, Y, Z))
        return v
    lo = np.max([a.bounds[0]] + [o.bounds[0] for o in others], axis=0)
    hi = np.min([a.bounds[1]] + [o.bounds[1] for o in others], axis=0)
    return Shape(f, _b(lo, hi))


def halfspace(normal, point) -> Shape:
    """Inside where (p - point) . normal < 0. Unbounded; use only inside intersect/subtract."""
    n = np.asarray(normal, float)
    n = n / np.linalg.norm(n)
    p0 = np.asarray(point, float)

    def f(X, Y, Z):
        return (X - p0[0]) * n[0] + (Y - p0[1]) * n[1] + (Z - p0[2]) * n[2]
    return Shape(f, _b([-1e3] * 3, [1e3] * 3))


def inflate(s: Shape, d: float) -> Shape:
    def f(X, Y, Z):
        return s(X, Y, Z) - d
    lo, hi = np.asarray(s.bounds[0]) - d, np.asarray(s.bounds[1]) + d
    return Shape(f, _b(lo, hi))


def mirror_x(s: Shape) -> Shape:
    """The same shape on the other side of the model (x -> -x)."""
    (x0, y0, z0), (x1, y1, z1) = s.bounds
    return Shape(lambda X, Y, Z: s(-X, Y, Z), _b((-x1, y0, z0), (-x0, y1, z1)))


def warp(s: Shape, fn, margin=2.0) -> Shape:
    """Domain warp: fn(X, Y, Z) -> (X', Y', Z') applied before evaluating s (bends, twists, tapers)."""
    def f(X, Y, Z):
        return s(*fn(X, Y, Z))
    lo, hi = np.asarray(s.bounds[0]) - margin, np.asarray(s.bounds[1]) + margin
    return Shape(f, _b(lo, hi))


def gradient(s: Shape, X, Y, Z, h=0.05):
    """Unit normal by central differences."""
    gx = s(X + h, Y, Z) - s(X - h, Y, Z)
    gy = s(X, Y + h, Z) - s(X, Y - h, Z)
    gz = s(X, Y, Z + h) - s(X, Y, Z - h)
    n = np.stack([gx, gy, gz], -1)
    length = np.linalg.norm(n, axis=-1, keepdims=True)
    return n / np.maximum(length, 1e-9)
