"""The geometry of this mob as implicit shapes and hand-placed boxes. Edit this file; lib/modeltools.py voxelises
it, removes buried faces, keeps blobs from z-fighting and writes the GeckoLib geometry.

Coordinates are Blockbench pixels (y up, front -Z, +X the model's own right side); 16 px is one block at
renderer scale 1. Every part belongs to one bone of mob/rig.py and one material of mob/paint.py.

What worked across finished mobs:
- Block out the whole silhouette first (large cells, flat colours), prove orientation and scale in a client, then
  refine. A wrong proportion found after painting costs the painting.
- Cell size: 0.8-1.0 px on large forms reads as clean Minecraft steps; 0.5 px only where the detail lives (face,
  hands, small features). Finer than 0.5 looks noisy under vanilla face lighting and doubles the cube count.
- Texel density (tpp): 2 per pixel sits beside vanilla and 32x packs; 4 on the face and other detail areas; raw
  boxes for pixel-art plates (eyes, mouths) so they stay crisp.
- Budget: about 1,500 cubes renders comfortably with several instances; treat 2,600 as the point to stop adding.
- Overlapping parts on different bones (thigh into hip, arm into shoulder) hide the joint when it bends: let the
  child's shape start inside the parent's.
- Parts that swap (expressions, props) are separate blobs on separate bones at the same place; give each a small
  `stagger` so their coplanar faces differ.
"""
from lib.modeltools import Part
from lib.sdf import box, capsule, ellipsoid, mirror_x, smooth_union, superellipsoid

CELL = 1.0
CELL_DETAIL = 0.5
TPP = 2
TPP_DETAIL = 4

# Cube budget: a warning above BUDGET, an error above CAP.
BUDGET, CAP = 1500, 2600
# Bones that must carry geometry (the validator fails when a build loses one).
MUST_HAVE = ["hips", "torso", "head", "thigh_l", "thigh_r", "shin_l", "shin_r", "arm_l", "arm_r", "tail_phys", "eyes_open"]
# Geometry bounds for culling, in blocks: (width, height, y offset of the centre).
VISIBLE_BOUNDS = (3, 3, 1.0)
# A face plate shows its front only.
PLATE_BACK = ("south", "east", "west", "up", "down")


def both(name, bone, material, shape, **kw):
    """One part per side from a left-side (negative x) shape."""
    return [Part(f"{name}_l", bone.replace("_L", "_l"), "blob", material, shape, **kw),
            Part(f"{name}_r", bone.replace("_L", "_r"), "blob", material, mirror_x(shape), **kw)]


def parts() -> list[Part]:
    p = [
        Part("pelvis", "hips", "blob", "hide", superellipsoid((0, 10.5, 0), (4.2, 2.6, 2.8), 2.6)),
        Part("torso", "torso", "blob", "hide", smooth_union(0.6, superellipsoid((0, 16, 0), (4.4, 4.4, 2.9), 2.8),
                                                            ellipsoid((0, 19.5, 0), (5.0, 1.8, 2.6)))),
        Part("belly_plate", "torso", "blob", "plate", superellipsoid((0, 15.5, -2.4), (2.8, 3.0, 0.9), 3.0), cell=CELL_DETAIL, tpp=TPP_DETAIL),
        Part("head", "head", "blob", "hide", superellipsoid((0, 25, 0), (4.0, 3.8, 3.8), 3.2)),
        Part("snout", "head", "blob", "plate", superellipsoid((0, 23.6, -4.0), (1.8, 1.2, 1.0), 2.6), cell=CELL_DETAIL, tpp=TPP_DETAIL),
        Part("tail", "tail_phys", "blob", "hide", capsule((0, 10.5, 2.5), (0, 9.5, 7.0), 1.5, 1.1)),
        Part("tail_tip", "tail_tip_phys", "blob", "plate", capsule((0, 9.5, 7.0), (0, 10.5, 10.5), 1.1, 0.5), cell=CELL_DETAIL),
        # pixel-art plates: raw boxes just proud of the voxel surface, at a higher texel density, one per swap variant
        Part("eyes_open", "eyes_open", "box", "eyes_open", lo=(-3.0, 24.4, -4.30), hi=(3.0, 26.4, -4.10), tpp=8, hide=PLATE_BACK),
        Part("eyes_closed", "eyes_closed", "box", "eyes_closed", lo=(-3.0, 24.4, -4.33), hi=(3.0, 26.4, -4.13), tpp=8, hide=PLATE_BACK),
    ]
    p += both("thigh", "thigh_L", "hide", capsule((-2.5, 11.2, 0), (-2.5, 6.0, 0), 1.9, 1.6))
    p += both("shin", "shin_L", "hide", capsule((-2.5, 6.2, 0), (-2.5, 1.2, 0), 1.6, 1.3))
    p += both("foot", "shin_L", "plate", box((-3.9, 0.0, -2.6), (-1.1, 1.4, 1.4), 0.3))
    p += both("upper_arm", "arm_L", "hide", capsule((-5.6, 19.0, 0), (-5.6, 14.6, 0), 1.5, 1.3))
    p += both("forearm", "forearm_L", "hide", capsule((-5.6, 14.8, 0), (-5.6, 10.8, 0), 1.3, 1.5))
    p += both("ear", "ear_L_phys", "plate", capsule((-3.0, 27.8, 0), (-3.6, 31.5, 0.3), 1.1, 0.5, squash=(1, 1, 0.6)), cell=CELL_DETAIL)
    return p
