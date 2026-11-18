"""Views and the look checklist of this mob (lib/sheets.py renders and gates them).

Write the checklist from the brief before modelling: one row per feature the owner asked for, in the owner's
words, each mapped to the view that shows it. A feature without a row gets forgotten; a row without a current
view is a claim nobody can check. Add close-ups (large scale, a centre point) for small features.

yaw 0 shows the front, 180 the back, 90 the model's left side; pitch tilts the camera down; scale is screen
pixels per model pixel; center is (x, y) in model pixels on screen; hide/show name bones (swap variants).
"""

VIEWS = [
    {"name": "front", "yaw": 0, "pitch": 6, "scale": 9.0, "center": (0, 15)},
    {"name": "front34", "yaw": 35, "pitch": 10, "scale": 9.0, "center": (0, 15)},
    {"name": "side", "yaw": 90, "pitch": 6, "scale": 9.0, "center": (0, 15)},
    {"name": "back", "yaw": 180, "pitch": 6, "scale": 9.0, "center": (0, 15)},
    {"name": "face", "yaw": 15, "pitch": 4, "scale": 24.0, "center": (0, 25), "size": (300, 300)},
    {"name": "face_closed", "yaw": 15, "pitch": 4, "scale": 24.0, "center": (0, 25), "size": (300, 300),
     "hide": ["eyes_open"], "show": ["eyes_closed"]},
    {"name": "night", "yaw": 35, "pitch": 10, "scale": 9.0, "center": (0, 15), "light": 0.25},
]

# id: (what to look for, [views that show it])
CHECKLIST = {
    "silhouette": ("stocky biped, large head, short legs, tail clear of the ground", ["side", "front34"]),
    "face": ("two eyes with glowing pupils, a lighter snout", ["face", "night"]),
    "blink": ("closed-eye variant sits exactly where the open eyes are", ["face_closed"]),
    "ears": ("two upright ears, lighter than the head", ["front", "back"]),
    "tail": ("tail tapers to a lighter tip", ["side", "back"]),
}
