"""The rig of this mob: bone tree, procedural bones, swap groups and springs. Edit this file; lib/rigtools.py
turns it into the skeleton, the manifest the validators read and gen/<Mob>Rig.java.

Conventions (Blockbench pixels, y up): front is -Z, +X is the model's own right side. `_l` bones sit at negative
x, `_r` at positive x. Entries whose name contains `_L` are written once for the left side and mirrored.

Rules that save iterations:
- Procedural bones (look, springs, blink, anything code writes every frame) end in `_phys` or are listed in
  EXTRA_PROCEDURAL. No clip may key them, and nothing else may write a keyed bone: one of the two silently wins.
- A sprung part hangs from its own `_phys` bone, a child of the keyed bone, with its pivot at the hinge.
- Bone scale is inherited by child bones. A part that must not squash with its parent hangs beside it, not under it.
  Chains driven by a solver (hoses, ropes) are sibling segment bones under one identity bone.
- Expressions, hands, props: one bone per variant under a common parent, listed in SWAP_GROUPS; code shows one.
"""

# (name, parent, pivot)
BONES = [
    ("root", None, (0, 0, 0)),
    ("hips", "root", (0, 11, 0)),
    ("thigh_L", "hips", (-2.5, 11, 0)),
    ("shin_L", "thigh_L", (-2.5, 6, 0)),
    ("tail", "hips", (0, 11, 3)),
    ("tail_phys", "tail", (0, 11, 3)),
    ("tail_tip_phys", "tail_phys", (0, 9.5, 7)),
    ("torso", "root", (0, 12, 0)),
    ("arm_L", "torso", (-5.5, 19, 0)),
    ("forearm_L", "arm_L", (-5.5, 14.5, 0)),
    ("head_look", "torso", (0, 21, 0)),
    ("head", "head_look", (0, 21, 0)),
    ("ear_L_phys", "head", (-3, 28, 0)),
    ("eyes_open", "head", (0, 25, -4)),
    ("eyes_closed", "head", (0, 25, -4)),
]

# The bone the head look is added to (pitch and yaw from the entity), never keyed.
LOOK = "head_look"
EXTRA_PROCEDURAL = {"head_look"}
SWAP_GROUPS = {"eyes": ["eyes_open", "eyes_closed"]}
# Leg bones (their children count too): grounded clips put the lowest point of these at y = 0.
LEGS = ["thigh_l", "thigh_r"]

# bone: stiffness k, damping c, clamps (rotation deg, position px, scale fraction), mass offset r from the hinge
# (left-side value, mirrored for _r), default gain. Paired parts get slightly different k so they never move in
# lockstep. Tune gains from the client trace (build_assets.py springs), not here: spring_gains.json overrides.
SPRINGS = [
    ("ear_l_phys", 190.0, 12.0, (16, 0.0, 0.0), (0.0, 3.0, 0.0), 4.0),
    ("ear_r_phys", 180.0, 12.0, (16, 0.0, 0.0), (0.0, 3.0, 0.0), 4.0),
    ("tail_phys", 110.0, 8.0, (22, 0.0, 0.06), (0.0, -1.0, 3.5), 3.0),
    ("tail_tip_phys", 90.0, 6.5, (26, 0.0, 0.0), (0.0, -0.5, 3.0), 3.0),
]
